"""PostgreSQL repository for owner-scoped project records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from video_app.application.projects import (
    ProjectNotFoundError,
    ProjectRevisionConflictError,
)
from video_app.domain.projects import (
    AspectRatio,
    BudgetPolicy,
    ExportSettings,
    Project,
    ProjectMode,
    ProjectPreset,
    ProjectState,
    ProviderSelections,
)
from video_app.infrastructure.schema import projects


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("database project timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"database {field} must be a JSON object")
    return cast(dict[str, Any], value)


def _row_to_project(row: RowMapping) -> Project:
    export = _object(row["export_settings"], "export_settings")
    providers = _object(row["providers"], "providers")
    budget = _object(row["budget_policy"], "budget_policy")
    return Project(
        id=row["id"],
        owner_id=row["owner_id"],
        version=row["version"],
        state=ProjectState(row["state"]),
        title=row["title"],
        language=row["language"],
        mode=ProjectMode(row["mode"]),
        target_duration_ms=row["target_duration_ms"],
        aspect_ratio=AspectRatio(row["aspect_ratio"]),
        export_settings=ExportSettings(
            width=export["width"],
            height=export["height"],
            fps_numerator=export["fps_numerator"],
            fps_denominator=export["fps_denominator"],
        ),
        providers=ProviderSelections(
            video=providers["video"],
            speech=providers.get("speech"),
            lip_sync=providers.get("lip_sync"),
            caption_alignment=providers.get("caption_alignment"),
        ),
        budget_policy=BudgetPolicy(
            max_compute_seconds=budget.get("max_compute_seconds"),
            max_cost_micros=budget.get("max_cost_micros"),
            automatic_expensive_retries=budget["automatic_expensive_retries"],
        ),
        approved_timeline_revision_id=row["approved_timeline_revision_id"],
        created_at=_utc(row["created_at"]),
        updated_at=_utc(row["updated_at"]),
        preset=ProjectPreset(row["preset"]),
        titles_and_credits_within_target=row["titles_and_credits_within_target"],
    )


def _values(project: Project) -> dict[str, object]:
    return {
        "id": project.id,
        "owner_id": project.owner_id,
        "version": project.version,
        "state": project.state.value,
        "title": project.title,
        "language": project.language,
        "mode": project.mode.value,
        "target_duration_ms": project.target_duration_ms,
        "aspect_ratio": project.aspect_ratio.value,
        "export_settings": {
            "width": project.export_settings.width,
            "height": project.export_settings.height,
            "fps_numerator": project.export_settings.fps_numerator,
            "fps_denominator": project.export_settings.fps_denominator,
        },
        "providers": {
            "video": project.providers.video,
            "speech": project.providers.speech,
            "lip_sync": project.providers.lip_sync,
            "caption_alignment": project.providers.caption_alignment,
        },
        "budget_policy": {
            "max_compute_seconds": project.budget_policy.max_compute_seconds,
            "max_cost_micros": project.budget_policy.max_cost_micros,
            "automatic_expensive_retries": project.budget_policy.automatic_expensive_retries,
        },
        "approved_timeline_revision_id": project.approved_timeline_revision_id,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "preset": project.preset.value,
        "titles_and_credits_within_target": project.titles_and_credits_within_target,
    }


class PostgresProjectRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self, project: Project) -> Project:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        projects.insert().values(**_values(project)).returning(projects)
                    )
                )
                .mappings()
                .one()
            )
        return _row_to_project(row)

    async def get(self, owner_id: str, project_id: str) -> Project:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(projects).where(
                            projects.c.owner_id == owner_id,
                            projects.c.id == project_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ProjectNotFoundError(project_id)
        return _row_to_project(row)

    async def list(self, owner_id: str, *, limit: int) -> tuple[Project, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(projects)
                        .where(projects.c.owner_id == owner_id)
                        .order_by(projects.c.updated_at.desc(), projects.c.id.desc())
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_row_to_project(row) for row in rows)

    async def update(self, project: Project, *, expected_version: int) -> Project:
        values = _values(project)
        values.pop("id")
        values.pop("owner_id")
        values.pop("created_at")
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        projects.update()
                        .where(
                            projects.c.id == project.id,
                            projects.c.owner_id == project.owner_id,
                            projects.c.version == expected_version,
                        )
                        .values(**values)
                        .returning(projects)
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                exists = await connection.scalar(
                    sa.select(sa.literal(True)).where(
                        projects.c.id == project.id,
                        projects.c.owner_id == project.owner_id,
                    )
                )
                if exists:
                    raise ProjectRevisionConflictError("project revision is stale")
                raise ProjectNotFoundError(project.id)
        return _row_to_project(row)
