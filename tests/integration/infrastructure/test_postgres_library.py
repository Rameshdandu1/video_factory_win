from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from video_app.application.library import LibraryEntityNotFoundError
from video_app.domain.assets import (
    AssetKind,
    AssetScope,
    AssetState,
    MediaAsset,
    RightsDeclaration,
)
from video_app.domain.library import (
    FilmBiblePin,
    FilmBiblePinRole,
    FilmBibleSnapshot,
    LibraryAssetBinding,
    LibraryEntity,
    LibraryEntityKind,
    LibraryVersion,
    LibraryVersionKind,
    ReferenceRole,
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
from video_app.infrastructure.postgres_library import PostgresLibraryRepository
from video_app.infrastructure.postgres_projects import PostgresProjectRepository
from video_app.infrastructure.schema import (
    film_bible_pins,
    film_bible_snapshots,
    library_entities,
    library_version_assets,
    library_versions,
    media_assets,
    metadata,
    projects,
    shot_binding_revisions,
    shot_library_bindings,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)
pytestmark = pytest.mark.integration


@unittest.skipUnless(DATABASE_URL, "DATABASE_URL is required for PostgreSQL integration tests")
class PostgresLibraryRecoveryTests(unittest.IsolatedAsyncioTestCase):
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
            await connection.execute(library_version_assets.delete())
            await connection.execute(library_versions.delete())
            await connection.execute(library_entities.delete())
            await connection.execute(media_assets.delete())
            await connection.execute(projects.delete())

    async def asyncTearDown(self) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(shot_library_bindings.delete())
            await connection.execute(shot_binding_revisions.delete())
            await connection.execute(film_bible_pins.delete())
            await connection.execute(film_bible_snapshots.delete())
            await connection.execute(library_version_assets.delete())
            await connection.execute(library_versions.delete())
            await connection.execute(library_entities.delete())
            await connection.execute(media_assets.delete())
            await connection.execute(projects.delete())
        await self.engine.dispose()

    async def test_restart_preserves_exact_version_and_owner_boundary(self) -> None:
        asset = MediaAsset(
            id="asset_library_restart",
            project_id=None,
            owner_id="owner_a",
            version=1,
            kind=AssetKind.IMAGE,
            state=AssetState.READY,
            original_filename="arjun.png",
            media_type="image/png",
            storage_key="uploads/library-restart.png",
            size_bytes=128,
            sha256="a" * 64,
            rights=RightsDeclaration.PERMISSIONED,
            created_at=NOW,
            scope=AssetScope.LIBRARY,
        )
        await PostgresAssetRepository(self.engine).create(asset)
        entity = LibraryEntity.create(
            entity_id="library_restart",
            owner_id="owner_a",
            kind=LibraryEntityKind.CHARACTER,
            display_name="Arjun",
            aliases=("అర్జున్",),
            now=NOW,
        )
        repository = PostgresLibraryRepository(self.engine)
        await repository.create_entity(entity)
        version = LibraryVersion.create(
            version_id="library_version_restart",
            entity=entity,
            version_number=1,
            kind=LibraryVersionKind.IDENTITY,
            label="Identity pack",
            notes="",
            invariants="Hair and face",
            state_notes="Neutral",
            voice_profile_id=None,
            rights_statement="Permission recorded",
            bindings=(
                LibraryAssetBinding(
                    asset.id,
                    asset.version,
                    asset.sha256,
                    ReferenceRole.IDENTITY_APPEARANCE,
                    "front",
                ),
            ),
            now=NOW,
        )
        await repository.create_version(version)
        await repository.approve_version(version.approve(now=NOW + timedelta(seconds=1)))
        project = Project.create(
            project_id="project_library_restart",
            owner_id="owner_a",
            draft=ProjectDraft(
                "Reference film",
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
        snapshot = FilmBibleSnapshot.create(
            snapshot_id="film_bible_restart",
            project_id=project.id,
            owner_id=project.owner_id,
            revision=1,
            pins=(
                FilmBiblePin(
                    entity_id=entity.id,
                    library_version_id=version.id,
                    library_version_number=version.version_number,
                    version_kind=version.kind,
                    version_fingerprint=version.fingerprint,
                    role=FilmBiblePinRole.CHARACTER_IDENTITY,
                ),
            ),
            now=NOW,
        )
        await repository.create_film_bible_snapshot(snapshot)
        await repository.approve_film_bible_snapshot(
            snapshot.approve(now=NOW + timedelta(seconds=2))
        )

        restarted = PostgresLibraryRepository(self.engine)
        recovered = await restarted.get_version("owner_a", entity.id, version.id)
        recovered_snapshot = await restarted.get_film_bible_snapshot(
            "owner_a", project.id, snapshot.id
        )
        self.assertEqual(recovered.bindings[0].asset_sha256, asset.sha256)
        self.assertEqual(recovered.fingerprint, version.fingerprint)
        self.assertIsNotNone(recovered.approved_at)
        self.assertEqual(recovered_snapshot.pins[0].library_version_id, version.id)
        self.assertEqual(recovered_snapshot.fingerprint, snapshot.fingerprint)
        with self.assertRaises(LibraryEntityNotFoundError):
            await restarted.get_entity("owner_b", entity.id)
