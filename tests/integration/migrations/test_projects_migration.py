from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine

from video_app.infrastructure.schema import generation_jobs

MIGRATION_DATABASE_URL = os.environ.get("MIGRATION_TEST_DATABASE_URL")
pytestmark = pytest.mark.integration


def _assert_disposable_database(url: str) -> None:
    database_name = url.rsplit("/", maxsplit=1)[-1].split("?", maxsplit=1)[0]
    if not database_name.endswith("_migration_test"):
        raise RuntimeError("migration tests require a database ending in _migration_test")


async def _seed_v1_and_assert_preserved(url: str, *, after_upgrade: bool) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            if after_upgrade:
                count = await connection.scalar(
                    sa.select(sa.func.count()).select_from(generation_jobs)
                )
                project_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.projects')")
                )
                asset_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.media_assets')")
                )
                metadata_column = await connection.scalar(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'media_assets' AND column_name = 'metadata'"
                    )
                )
                timeline_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.timeline_revisions')")
                )
                captions_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.caption_segments')")
                )
                film_scene_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.film_scenes')")
                )
                film_shot_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.film_shots')")
                )
                film_approval_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.film_approvals')")
                )
                library_entity_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.library_entities')")
                )
                library_version_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.library_versions')")
                )
                library_binding_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.library_version_assets')")
                )
                asset_scope_column = await connection.scalar(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'media_assets' AND column_name = 'scope'"
                    )
                )
                film_bible_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.film_bible_snapshots')")
                )
                film_bible_pin_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.film_bible_pins')")
                )
                shot_binding_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.shot_binding_revisions')")
                )
                starting_frame_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.starting_frame_compositions')")
                )
                starting_frame_layer_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.starting_frame_layers')")
                )
                shot_library_binding_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.shot_library_bindings')")
                )
                reference_guidance_table = await connection.scalar(
                    sa.text("SELECT to_regclass('public.reference_video_guidance')")
                )
                conditioning_manifest_column = await connection.scalar(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'generation_jobs' "
                        "AND column_name = 'conditioning_manifest_fingerprint'"
                    )
                )
                controlled_reference_column = await connection.scalar(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'generation_jobs' "
                        "AND column_name = 'conditioning_reference_guidance_id'"
                    )
                )
                conditioning_idempotency_index = await connection.scalar(
                    sa.text(
                        "SELECT indexname FROM pg_indexes WHERE tablename = 'generation_jobs' "
                        "AND indexname = 'uq_generation_jobs_conditioning_idempotency'"
                    )
                )
                rough_cut_manifest_column = await connection.scalar(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'generation_jobs' "
                        "AND column_name = 'rough_cut_manifest'"
                    )
                )
                rough_cut_idempotency_index = await connection.scalar(
                    sa.text(
                        "SELECT indexname FROM pg_indexes WHERE tablename = 'generation_jobs' "
                        "AND indexname = 'uq_generation_jobs_rough_cut_idempotency'"
                    )
                )
                timeline_render_manifest_column = await connection.scalar(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'generation_jobs' "
                        "AND column_name = 'timeline_render_manifest'"
                    )
                )
                timeline_render_idempotency_index = await connection.scalar(
                    sa.text(
                        "SELECT indexname FROM pg_indexes WHERE tablename = 'generation_jobs' "
                        "AND indexname = 'uq_generation_jobs_timeline_render_idempotency'"
                    )
                )
                if (
                    count != 1
                    or project_table != "projects"
                    or asset_table != "media_assets"
                    or metadata_column != "metadata"
                    or timeline_table != "timeline_revisions"
                    or captions_table != "caption_segments"
                    or film_scene_table != "film_scenes"
                    or film_shot_table != "film_shots"
                    or film_approval_table != "film_approvals"
                    or library_entity_table != "library_entities"
                    or library_version_table != "library_versions"
                    or library_binding_table != "library_version_assets"
                    or asset_scope_column != "scope"
                    or film_bible_table != "film_bible_snapshots"
                    or film_bible_pin_table != "film_bible_pins"
                    or shot_binding_table != "shot_binding_revisions"
                    or starting_frame_table != "starting_frame_compositions"
                    or starting_frame_layer_table != "starting_frame_layers"
                    or shot_library_binding_table != "shot_library_bindings"
                    or reference_guidance_table != "reference_video_guidance"
                    or conditioning_manifest_column != "conditioning_manifest_fingerprint"
                    or controlled_reference_column != "conditioning_reference_guidance_id"
                    or conditioning_idempotency_index
                    != "uq_generation_jobs_conditioning_idempotency"
                    or rough_cut_manifest_column != "rough_cut_manifest"
                    or rough_cut_idempotency_index != "uq_generation_jobs_rough_cut_idempotency"
                    or timeline_render_manifest_column != "timeline_render_manifest"
                    or timeline_render_idempotency_index
                    != "uq_generation_jobs_timeline_render_idempotency"
                ):
                    raise AssertionError("v1 data or an additive workflow table is missing")
            else:
                await connection.execute(
                    generation_jobs.insert().values(
                        id="job_existing_before_projects",
                        version=1,
                        status="queued",
                        created_at=sa.func.now(),
                        updated_at=sa.func.now(),
                        prompt="existing populated job",
                        model="wan21-t2v",
                        mode="text_to_video",
                        width=832,
                        height=480,
                        frame_count=81,
                        seed=42,
                    )
                )
    finally:
        await engine.dispose()


@unittest.skipUnless(
    MIGRATION_DATABASE_URL,
    "MIGRATION_TEST_DATABASE_URL is required for populated migration tests",
)
class ProjectMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_existing_generation_jobs(self) -> None:
        assert MIGRATION_DATABASE_URL is not None
        _assert_disposable_database(MIGRATION_DATABASE_URL)
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = MIGRATION_DATABASE_URL
        try:
            config = Config(str(Path("alembic.ini").resolve()))
            command.upgrade(config, "20260821_0001")
            asyncio.run(_seed_v1_and_assert_preserved(MIGRATION_DATABASE_URL, after_upgrade=False))
            command.upgrade(config, "head")
            asyncio.run(_seed_v1_and_assert_preserved(MIGRATION_DATABASE_URL, after_upgrade=True))
        finally:
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous
