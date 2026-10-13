from __future__ import annotations

import os
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from video_app.domain.assets import AssetKind, AssetState, MediaAsset, RightsDeclaration
from video_app.domain.films import (
    ApprovalStage,
    DialogueWorkflow,
    FilmApproval,
    FilmSceneDraft,
    FilmShotDraft,
    ReferenceWorkflow,
    SceneContinuity,
    film_readiness,
    pending_visual_shot_ids,
)
from video_app.domain.projects import (
    AspectRatio,
    BudgetPolicy,
    ExportSettings,
    Project,
    ProjectDraft,
    ProjectMode,
    ProjectPreset,
    ProviderSelections,
)
from video_app.infrastructure.database import DatabaseSettings, create_database_engine
from video_app.infrastructure.postgres_assets import PostgresAssetRepository
from video_app.infrastructure.postgres_films import PostgresFilmRepository
from video_app.infrastructure.postgres_projects import PostgresProjectRepository
from video_app.infrastructure.schema import (
    film_approvals,
    film_bible_pins,
    film_bible_snapshots,
    film_scenes,
    film_shots,
    media_assets,
    metadata,
    projects,
    shot_binding_revisions,
    shot_library_bindings,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
pytestmark = pytest.mark.integration


@unittest.skipUnless(DATABASE_URL, "DATABASE_URL is required for PostgreSQL integration tests")
class PostgresFilmRecoveryTests(unittest.IsolatedAsyncioTestCase):
    engine: AsyncEngine

    async def asyncSetUp(self) -> None:
        assert DATABASE_URL is not None
        self.engine = create_database_engine(DatabaseSettings(DATABASE_URL))
        async with self.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
            await connection.execute(shot_library_bindings.delete())
            await connection.execute(shot_binding_revisions.delete())
            await connection.execute(film_bible_pins.delete())
            await connection.execute(film_bible_snapshots.delete())
            await connection.execute(film_approvals.delete())
            await connection.execute(film_shots.delete())
            await connection.execute(film_scenes.delete())
            await connection.execute(media_assets.delete())
            await connection.execute(projects.delete())

    async def asyncTearDown(self) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(shot_library_bindings.delete())
            await connection.execute(shot_binding_revisions.delete())
            await connection.execute(film_bible_pins.delete())
            await connection.execute(film_bible_snapshots.delete())
            await connection.execute(film_approvals.delete())
            await connection.execute(film_shots.delete())
            await connection.execute(film_scenes.delete())
            await connection.execute(media_assets.delete())
            await connection.execute(projects.delete())
        await self.engine.dispose()

    async def test_restart_and_one_shot_replacement_preserve_unrelated_approval(self) -> None:
        project = Project.create(
            project_id="project_film_recovery",
            owner_id="owner_recovery",
            draft=ProjectDraft(
                "Recovery film",
                "te",
                ProjectMode.LONG,
                900_000,
                AspectRatio.LANDSCAPE,
                ExportSettings(1280, 720, 30),
                ProviderSelections("wan21", "uploaded"),
                BudgetPolicy(),
                ProjectPreset.TELUGU_SHORT_FILM_900,
                True,
            ),
            now=NOW,
        )
        await PostgresProjectRepository(self.engine).create(project)

        assets = PostgresAssetRepository(self.engine)
        for asset_id, kind, media_type, filename in (
            ("asset_reference", AssetKind.IMAGE, "image/png", "reference.png"),
            ("asset_storyboard", AssetKind.IMAGE, "image/png", "storyboard.png"),
            ("asset_dialogue", AssetKind.AUDIO, "audio/wav", "dialogue.wav"),
        ):
            await assets.create(
                MediaAsset(
                    asset_id,
                    project.id,
                    project.owner_id,
                    1,
                    kind,
                    AssetState.READY,
                    filename,
                    media_type,
                    f"uploads/{asset_id}",
                    100,
                    ("a" if kind is AssetKind.IMAGE else "b") * 64,
                    RightsDeclaration.PERMISSIONED,
                    NOW,
                )
            )

        repository = PostgresFilmRepository(self.engine)
        scene = await repository.save_scene(
            scene_id="scene_recovery",
            owner_id=project.owner_id,
            project_id=project.id,
            draft=FilmSceneDraft(
                0,
                "Dialogue scene",
                90_000,
                "నమస్కారం",
                "na-ma-skaa-ram",
                SceneContinuity("workshop", "warm", "blue", "toolbox", "clean", "A left; B right"),
            ),
            expected_version=None,
            now=NOW,
        )
        shot_draft = FilmShotDraft(
            0,
            10_000,
            "Independent shot",
            ReferenceWorkflow.REFERENCE_GENERATION,
            ("asset_reference",),
            "asset_storyboard",
            DialogueWorkflow.RECORDED,
            recorded_dialogue_asset_id="asset_dialogue",
        )
        first = await repository.save_shot(
            shot_id="shot_recovery_one",
            scene_id=scene.id,
            owner_id=project.owner_id,
            project_id=project.id,
            draft=shot_draft,
            expected_version=None,
            now=NOW,
        )
        second = await repository.save_shot(
            shot_id="shot_recovery_two",
            scene_id=scene.id,
            owner_id=project.owner_id,
            project_id=project.id,
            draft=replace(shot_draft, position=1, description="Unrelated shot"),
            expected_version=None,
            now=NOW,
        )
        for index, shot in enumerate((first, second), start=1):
            await repository.add_approval(
                FilmApproval(
                    f"approval_recovery_{index}",
                    project.id,
                    project.owner_id,
                    ApprovalStage.VISUAL_PERFORMANCE,
                    shot.content_fingerprint,
                    NOW,
                    scene_id=scene.id,
                    shot_id=shot.id,
                    evidence_asset_id=None,
                )
            )

        resumed = await PostgresFilmRepository(self.engine).snapshot(project.owner_id, project.id)
        self.assertEqual(pending_visual_shot_ids(resumed.shots, resumed.approvals), ())

        await PostgresFilmRepository(self.engine).save_shot(
            shot_id=first.id,
            scene_id=scene.id,
            owner_id=project.owner_id,
            project_id=project.id,
            draft=replace(first.draft, description="Replacement shot"),
            expected_version=first.version,
            now=NOW + timedelta(seconds=1),
        )
        after_replacement = await PostgresFilmRepository(self.engine).snapshot(
            project.owner_id, project.id
        )

        self.assertEqual(
            pending_visual_shot_ids(after_replacement.shots, after_replacement.approvals),
            (first.id,),
        )
        self.assertEqual(len(after_replacement.approvals), 2)
        readiness = film_readiness(
            after_replacement.scenes,
            after_replacement.shots,
            after_replacement.approvals,
            project_contract_fingerprint=project.film_contract_fingerprint(),
            target_duration_ms=project.target_duration_ms,
        )
        pending_visuals = {
            item.shot_id
            for item in readiness.pending_approvals
            if item.stage is ApprovalStage.VISUAL_PERFORMANCE
        }
        self.assertEqual(pending_visuals, {first.id})
        self.assertEqual(len(readiness.continuity_boundaries), 1)
