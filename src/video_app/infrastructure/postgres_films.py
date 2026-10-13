"""PostgreSQL repository for Telugu film scenes, shots, and approvals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from video_app.application.films import FilmRepository, FilmSubjectNotFoundError, FilmWorkspace
from video_app.application.projects import ProjectRevisionConflictError
from video_app.domain.films import (
    ApprovalStage,
    DialogueWorkflow,
    FilmApproval,
    FilmScene,
    FilmSceneDraft,
    FilmShot,
    FilmShotDraft,
    ReferenceWorkflow,
    SceneContinuity,
)
from video_app.infrastructure.schema import film_approvals, film_scenes, film_shots


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("film timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _scene(row: RowMapping) -> FilmScene:
    continuity = cast(dict[str, Any], row["continuity"])
    draft = FilmSceneDraft(
        position=row["position"],
        title=row["title"],
        target_duration_ms=row["target_duration_ms"],
        telugu_script=row["telugu_script"],
        pronunciation_notes=row["pronunciation_notes"],
        continuity=SceneContinuity(**continuity),
    )
    return FilmScene(
        id=row["id"],
        project_id=row["project_id"],
        owner_id=row["owner_id"],
        version=row["version"],
        draft=draft,
        content_fingerprint=row["content_fingerprint"],
        created_at=_utc(row["created_at"]),
        updated_at=_utc(row["updated_at"]),
    )


def _shot(row: RowMapping) -> FilmShot:
    references = row["character_reference_asset_ids"]
    if not isinstance(references, list) or not all(isinstance(item, str) for item in references):
        raise ValueError("film shot references must be a string array")
    draft = FilmShotDraft(
        position=row["position"],
        target_duration_ms=row["target_duration_ms"],
        description=row["description"],
        reference_workflow=ReferenceWorkflow(row["reference_workflow"]),
        character_reference_asset_ids=tuple(references),
        dialogue_workflow=DialogueWorkflow(row["dialogue_workflow"]),
        storyboard_asset_id=row["storyboard_asset_id"],
        source_footage_asset_id=row["source_footage_asset_id"],
        recorded_dialogue_asset_id=row["recorded_dialogue_asset_id"],
    )
    return FilmShot(
        id=row["id"],
        scene_id=row["scene_id"],
        project_id=row["project_id"],
        owner_id=row["owner_id"],
        version=row["version"],
        draft=draft,
        content_fingerprint=row["content_fingerprint"],
        created_at=_utc(row["created_at"]),
        updated_at=_utc(row["updated_at"]),
    )


def _approval(row: RowMapping) -> FilmApproval:
    return FilmApproval(
        id=row["id"],
        project_id=row["project_id"],
        owner_id=row["owner_id"],
        stage=ApprovalStage(row["stage"]),
        subject_fingerprint=row["subject_fingerprint"],
        approved_at=_utc(row["approved_at"]),
        scene_id=row["scene_id"],
        shot_id=row["shot_id"],
        evidence_asset_id=row["evidence_asset_id"],
    )


class PostgresFilmRepository(FilmRepository):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save_scene(
        self,
        *,
        scene_id: str,
        owner_id: str,
        project_id: str,
        draft: FilmSceneDraft,
        expected_version: int | None,
        now: datetime,
    ) -> FilmScene:
        values = {
            "position": draft.position,
            "title": draft.title.strip(),
            "target_duration_ms": draft.target_duration_ms,
            "telugu_script": draft.telugu_script.strip(),
            "pronunciation_notes": draft.pronunciation_notes.strip(),
            "continuity": {
                "location": draft.continuity.location.strip(),
                "lighting": draft.continuity.lighting.strip(),
                "wardrobe": draft.continuity.wardrobe.strip(),
                "props": draft.continuity.props.strip(),
                "physical_state": draft.continuity.physical_state.strip(),
                "character_positions": draft.continuity.character_positions.strip(),
            },
            "content_fingerprint": draft.fingerprint(),
            "updated_at": now,
        }
        row: RowMapping | None
        async with self._engine.begin() as connection:
            if expected_version is None:
                row = (
                    (
                        await connection.execute(
                            film_scenes.insert()
                            .values(
                                id=scene_id,
                                project_id=project_id,
                                owner_id=owner_id,
                                version=1,
                                created_at=now,
                                **values,
                            )
                            .returning(film_scenes)
                        )
                    )
                    .mappings()
                    .one()
                )
            else:
                row = (
                    (
                        await connection.execute(
                            film_scenes.update()
                            .where(
                                film_scenes.c.id == scene_id,
                                film_scenes.c.owner_id == owner_id,
                                film_scenes.c.project_id == project_id,
                                film_scenes.c.version == expected_version,
                            )
                            .values(version=expected_version + 1, **values)
                            .returning(film_scenes)
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ProjectRevisionConflictError("scene revision is stale")
        assert row is not None
        return _scene(row)

    async def save_shot(
        self,
        *,
        shot_id: str,
        scene_id: str,
        owner_id: str,
        project_id: str,
        draft: FilmShotDraft,
        expected_version: int | None,
        now: datetime,
    ) -> FilmShot:
        values = {
            "position": draft.position,
            "target_duration_ms": draft.target_duration_ms,
            "description": draft.description.strip(),
            "reference_workflow": draft.reference_workflow.value,
            "character_reference_asset_ids": list(draft.character_reference_asset_ids),
            "dialogue_workflow": draft.dialogue_workflow.value,
            "storyboard_asset_id": draft.storyboard_asset_id,
            "source_footage_asset_id": draft.source_footage_asset_id,
            "recorded_dialogue_asset_id": draft.recorded_dialogue_asset_id,
            "content_fingerprint": draft.fingerprint(),
            "updated_at": now,
        }
        row: RowMapping | None
        async with self._engine.begin() as connection:
            if expected_version is None:
                row = (
                    (
                        await connection.execute(
                            film_shots.insert()
                            .values(
                                id=shot_id,
                                scene_id=scene_id,
                                project_id=project_id,
                                owner_id=owner_id,
                                version=1,
                                created_at=now,
                                **values,
                            )
                            .returning(film_shots)
                        )
                    )
                    .mappings()
                    .one()
                )
            else:
                row = (
                    (
                        await connection.execute(
                            film_shots.update()
                            .where(
                                film_shots.c.id == shot_id,
                                film_shots.c.scene_id == scene_id,
                                film_shots.c.owner_id == owner_id,
                                film_shots.c.version == expected_version,
                            )
                            .values(version=expected_version + 1, **values)
                            .returning(film_shots)
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ProjectRevisionConflictError("shot revision is stale")
        assert row is not None
        return _shot(row)

    async def get_scene(self, owner_id: str, project_id: str, scene_id: str) -> FilmScene:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(film_scenes).where(
                            film_scenes.c.id == scene_id,
                            film_scenes.c.owner_id == owner_id,
                            film_scenes.c.project_id == project_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise FilmSubjectNotFoundError(scene_id)
        return _scene(row)

    async def get_shot(self, owner_id: str, project_id: str, shot_id: str) -> FilmShot:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(film_shots).where(
                            film_shots.c.id == shot_id,
                            film_shots.c.owner_id == owner_id,
                            film_shots.c.project_id == project_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise FilmSubjectNotFoundError(shot_id)
        return _shot(row)

    async def snapshot(self, owner_id: str, project_id: str) -> FilmWorkspace:
        async with self._engine.connect() as connection:
            scene_rows = (
                (
                    await connection.execute(
                        sa.select(film_scenes)
                        .where(
                            film_scenes.c.owner_id == owner_id,
                            film_scenes.c.project_id == project_id,
                        )
                        .order_by(film_scenes.c.position)
                    )
                )
                .mappings()
                .all()
            )
            shot_rows = (
                (
                    await connection.execute(
                        sa.select(film_shots)
                        .where(
                            film_shots.c.owner_id == owner_id, film_shots.c.project_id == project_id
                        )
                        .order_by(film_shots.c.scene_id, film_shots.c.position)
                    )
                )
                .mappings()
                .all()
            )
            approval_rows = (
                (
                    await connection.execute(
                        sa.select(film_approvals)
                        .where(
                            film_approvals.c.owner_id == owner_id,
                            film_approvals.c.project_id == project_id,
                        )
                        .order_by(film_approvals.c.approved_at)
                    )
                )
                .mappings()
                .all()
            )
        return FilmWorkspace(
            tuple(_scene(row) for row in scene_rows),
            tuple(_shot(row) for row in shot_rows),
            tuple(_approval(row) for row in approval_rows),
        )

    async def add_approval(self, approval: FilmApproval) -> FilmApproval:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        film_approvals.insert()
                        .values(
                            id=approval.id,
                            project_id=approval.project_id,
                            scene_id=approval.scene_id,
                            shot_id=approval.shot_id,
                            owner_id=approval.owner_id,
                            stage=approval.stage.value,
                            subject_fingerprint=approval.subject_fingerprint,
                            evidence_asset_id=approval.evidence_asset_id,
                            approved_at=approval.approved_at,
                        )
                        .returning(film_approvals)
                    )
                )
                .mappings()
                .one()
            )
        return _approval(row)
