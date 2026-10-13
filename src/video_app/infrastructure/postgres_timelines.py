"""PostgreSQL persistence for immutable timeline revisions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from video_app.application.projects import ProjectNotFoundError, ProjectRevisionConflictError
from video_app.application.timelines import TimelineNotFoundError
from video_app.domain.timelines import (
    CaptionSegment,
    TimelineDraft,
    TimelineItem,
    TimelineItemKind,
    TimelineRevision,
)
from video_app.infrastructure.schema import caption_segments, projects, timeline_revisions


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("database timeline timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _item_values(item: TimelineItem) -> dict[str, object]:
    return {
        "kind": item.kind.value,
        "start_ms": item.start_ms,
        "duration_ms": item.duration_ms,
        "layer": item.layer,
        "asset_id": item.asset_id,
        "text": item.text.strip() if item.text is not None else None,
    }


def _row_to_timeline(row: RowMapping, captions: tuple[CaptionSegment, ...]) -> TimelineRevision:
    raw_items = row["items"]
    if not isinstance(raw_items, list):
        raise ValueError("database timeline items must be a JSON array")
    items = tuple(
        TimelineItem(
            kind=TimelineItemKind(cast(dict[str, Any], item)["kind"]),
            start_ms=cast(dict[str, Any], item)["start_ms"],
            duration_ms=cast(dict[str, Any], item)["duration_ms"],
            layer=cast(dict[str, Any], item)["layer"],
            asset_id=cast(dict[str, Any], item).get("asset_id"),
            text=cast(dict[str, Any], item).get("text"),
        )
        for item in raw_items
    )
    approved_at: datetime | None = row["approved_at"]
    return TimelineRevision(
        id=row["id"],
        project_id=row["project_id"],
        owner_id=row["owner_id"],
        revision=row["revision"],
        duration_ms=row["duration_ms"],
        items=items,
        captions=captions,
        fingerprint=row["fingerprint"],
        created_at=_utc(row["created_at"]),
        approved_at=_utc(approved_at) if approved_at is not None else None,
    )


async def _captions_for(
    connection: AsyncConnection, timeline_ids: tuple[str, ...]
) -> dict[str, tuple[CaptionSegment, ...]]:
    if not timeline_ids:
        return {}
    rows = (
        (
            await connection.execute(
                sa.select(caption_segments)
                .where(caption_segments.c.timeline_id.in_(timeline_ids))
                .order_by(caption_segments.c.timeline_id, caption_segments.c.position)
            )
        )
        .mappings()
        .all()
    )
    grouped: dict[str, list[CaptionSegment]] = {item: [] for item in timeline_ids}
    for row in rows:
        grouped[row["timeline_id"]].append(
            CaptionSegment(start_ms=row["start_ms"], end_ms=row["end_ms"], text=row["text"])
        )
    return {key: tuple(value) for key, value in grouped.items()}


class PostgresTimelineRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get(self, owner_id: str, project_id: str, timeline_id: str) -> TimelineRevision:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(timeline_revisions).where(
                            timeline_revisions.c.id == timeline_id,
                            timeline_revisions.c.owner_id == owner_id,
                            timeline_revisions.c.project_id == project_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise TimelineNotFoundError(timeline_id)
            captions = await _captions_for(connection, (timeline_id,))
        return _row_to_timeline(row, captions[timeline_id])

    async def create_revision(
        self,
        *,
        timeline_id: str,
        owner_id: str,
        project_id: str,
        draft: TimelineDraft,
        created_at: datetime,
    ) -> TimelineRevision:
        async with self._engine.begin() as connection:
            project_exists = await connection.scalar(
                sa.select(projects.c.id)
                .where(projects.c.id == project_id, projects.c.owner_id == owner_id)
                .with_for_update()
            )
            if project_exists is None:
                raise ProjectNotFoundError(project_id)
            current = await connection.scalar(
                sa.select(sa.func.max(timeline_revisions.c.revision)).where(
                    timeline_revisions.c.project_id == project_id
                )
            )
            revision = int(current or 0) + 1
            row = (
                (
                    await connection.execute(
                        timeline_revisions.insert()
                        .values(
                            id=timeline_id,
                            project_id=project_id,
                            owner_id=owner_id,
                            revision=revision,
                            duration_ms=draft.duration_ms,
                            items=[_item_values(item) for item in draft.items],
                            fingerprint=draft.fingerprint(),
                            created_at=created_at,
                        )
                        .returning(timeline_revisions)
                    )
                )
                .mappings()
                .one()
            )
            if draft.captions:
                await connection.execute(
                    caption_segments.insert(),
                    [
                        {
                            "timeline_id": timeline_id,
                            "position": position,
                            "start_ms": caption.start_ms,
                            "end_ms": caption.end_ms,
                            "text": caption.text.strip(),
                        }
                        for position, caption in enumerate(draft.captions)
                    ],
                )
        return _row_to_timeline(row, draft.captions)

    async def list(
        self, owner_id: str, project_id: str, *, limit: int
    ) -> tuple[TimelineRevision, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(timeline_revisions)
                        .where(
                            timeline_revisions.c.owner_id == owner_id,
                            timeline_revisions.c.project_id == project_id,
                        )
                        .order_by(timeline_revisions.c.revision.desc())
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
            captions = await _captions_for(connection, tuple(row["id"] for row in rows))
        return tuple(_row_to_timeline(row, captions[row["id"]]) for row in rows)

    async def approve(
        self,
        *,
        owner_id: str,
        project_id: str,
        timeline_id: str,
        expected_project_version: int,
        approved_at: datetime,
    ) -> TimelineRevision:
        async with self._engine.begin() as connection:
            project_version = await connection.scalar(
                sa.select(projects.c.version)
                .where(projects.c.id == project_id, projects.c.owner_id == owner_id)
                .with_for_update()
            )
            if project_version is None:
                raise ProjectNotFoundError(project_id)
            if project_version != expected_project_version:
                raise ProjectRevisionConflictError("project revision is stale")
            row = (
                (
                    await connection.execute(
                        timeline_revisions.update()
                        .where(
                            timeline_revisions.c.id == timeline_id,
                            timeline_revisions.c.project_id == project_id,
                            timeline_revisions.c.owner_id == owner_id,
                        )
                        .values(approved_at=approved_at)
                        .returning(timeline_revisions)
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise TimelineNotFoundError(timeline_id)
            await connection.execute(
                projects.update()
                .where(projects.c.id == project_id, projects.c.owner_id == owner_id)
                .values(
                    approved_timeline_revision_id=timeline_id,
                    version=expected_project_version + 1,
                    updated_at=approved_at,
                )
            )
            captions = await _captions_for(connection, (timeline_id,))
        return _row_to_timeline(row, captions[timeline_id])
