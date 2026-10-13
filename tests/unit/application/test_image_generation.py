from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast

from video_app.application.assets import AssetRepository
from video_app.application.films import FilmRepository
from video_app.application.image_generation import (
    ImageGenerationDraft,
    ImageGenerationProvider,
    ImageGenerationUnavailableError,
    SubmitImageGeneration,
)
from video_app.application.library import FilmBibleRepository
from video_app.application.ports import IdempotencyConflictError, IdentifierFactory, JobRepository
from video_app.application.projects import ProjectRepository
from video_app.domain.assets import AssetKind, AssetState
from video_app.domain.jobs import GenerationJob
from video_app.domain.library import StartingFrameStatus
from video_app.domain.models import GenerationMode, Resolution

NOW = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)


class RepositoryFixtures:
    def __init__(self) -> None:
        self.shot = SimpleNamespace(version=3)
        self.composition = SimpleNamespace(
            id="composition-a",
            status=StartingFrameStatus.APPROVED,
            shot_version=3,
            revision=1,
            fingerprint="a" * 64,
            rendered_asset_id="asset-a",
            rendered_asset_version=1,
            rendered_sha256="b" * 64,
            canvas_width=832,
            canvas_height=480,
        )
        self.asset = SimpleNamespace(
            id="asset-a",
            kind=AssetKind.IMAGE,
            state=AssetState.READY,
            version=1,
            sha256="b" * 64,
            storage_key="uploads/approved-a.png",
        )
        self.jobs: dict[tuple[str, str], GenerationJob] = {}

    async def get(self, *arguments: str) -> object:
        if len(arguments) == 2:
            return SimpleNamespace(id=arguments[-1])
        return self.asset

    async def get_shot(self, *_: str) -> object:
        return self.shot

    async def get_starting_frame_composition(self, *_: str) -> object:
        return self.composition

    async def enqueue(self, job: GenerationJob) -> GenerationJob:
        conditioning = job.request.image_conditioning
        assert job.idempotency_key is not None and conditioning is not None
        key = (conditioning.owner_id, job.idempotency_key)
        existing = self.jobs.get(key)
        if existing is not None:
            existing_conditioning = existing.request.image_conditioning
            assert existing_conditioning is not None
            if existing_conditioning.manifest_fingerprint != conditioning.manifest_fingerprint:
                raise IdempotencyConflictError
            return existing
        self.jobs[key] = job
        return job


class Clock:
    def now(self) -> datetime:
        return NOW


class Identifiers:
    def __init__(self) -> None:
        self.count = 0

    def new_job_id(self) -> str:
        self.count += 1
        return f"job-{self.count}"


class Seeds:
    def new_seed(self) -> int:
        return 42


def provider(*, enabled: bool = True) -> ImageGenerationProvider:
    return ImageGenerationProvider(
        backend_name="wan22-ti2v",
        backend_revision="wan2.2@code;task=ti2v-5B;model@model",
        model_id="wan22-ti2v-5b",
        display_name="Wan2.2 TI2V 5B",
        task="ti2v-5B",
        area_preset=Resolution(1280, 704),
        frame_count=81,
        enabled=enabled,
        runtime_state="qualified" if enabled else "not_configured",
        unavailable_reason=None if enabled else "not configured",
    )


class ImageGenerationUseCaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.fixtures = RepositoryFixtures()
        self.identifiers = Identifiers()

    def use_case(self, *, enabled: bool = True) -> SubmitImageGeneration:
        fixtures = self.fixtures
        return SubmitImageGeneration(
            projects=cast(ProjectRepository, fixtures),
            films=cast(FilmRepository, fixtures),
            film_bibles=cast(FilmBibleRepository, fixtures),
            assets=cast(AssetRepository, fixtures),
            jobs=cast(JobRepository, fixtures),
            provider=provider(enabled=enabled),
            clock=Clock(),
            identifiers=cast(IdentifierFactory, self.identifiers),
            seeds=Seeds(),
            owner_id="owner",
        )

    async def test_submission_pins_approved_pixels_and_is_idempotent(self) -> None:
        draft = ImageGenerationDraft("  subject turns toward camera  ", "request-a", seed=-7)
        first = await self.use_case()("project", "shot", "composition-a", draft)
        second = await self.use_case()("project", "shot", "composition-a", draft)

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.request.mode, GenerationMode.IMAGE_TO_VIDEO)
        self.assertEqual(first.request.prompt, "subject turns toward camera")
        self.assertEqual(first.request.seed, -7)
        manifest = first.request.image_conditioning
        assert manifest is not None
        self.assertEqual(manifest.source_asset_sha256, "b" * 64)
        self.assertEqual(manifest.source_storage_key, "uploads/approved-a.png")
        self.assertEqual(manifest.shot_version, 3)

    async def test_distinct_approved_image_bytes_produce_distinct_manifests(self) -> None:
        first = await self.use_case()(
            "project", "shot", "composition-a", ImageGenerationDraft("prompt", "one", 1)
        )
        self.fixtures.composition = SimpleNamespace(
            **{
                **vars(self.fixtures.composition),
                "id": "composition-b",
                "fingerprint": "c" * 64,
                "rendered_asset_id": "asset-b",
                "rendered_sha256": "d" * 64,
            }
        )
        self.fixtures.asset = SimpleNamespace(
            **{
                **vars(self.fixtures.asset),
                "id": "asset-b",
                "sha256": "d" * 64,
                "storage_key": "uploads/approved-b.png",
            }
        )
        second = await self.use_case()(
            "project", "shot", "composition-b", ImageGenerationDraft("prompt", "two", 1)
        )

        first_manifest = first.request.image_conditioning
        second_manifest = second.request.image_conditioning
        assert first_manifest is not None and second_manifest is not None
        self.assertNotEqual(
            first_manifest.manifest_fingerprint, second_manifest.manifest_fingerprint
        )
        self.assertNotEqual(first_manifest.source_asset_sha256, second_manifest.source_asset_sha256)

    async def test_same_idempotency_key_cannot_mutate_the_manifest(self) -> None:
        await self.use_case()(
            "project", "shot", "composition-a", ImageGenerationDraft("first", "same", 1)
        )
        with self.assertRaises(IdempotencyConflictError):
            await self.use_case()(
                "project", "shot", "composition-a", ImageGenerationDraft("changed", "same", 1)
            )

    async def test_unapproved_stale_and_unavailable_submissions_fail_closed(self) -> None:
        self.fixtures.composition.status = StartingFrameStatus.RENDERED
        with self.assertRaisesRegex(ValueError, "approved"):
            await self.use_case()(
                "project", "shot", "composition-a", ImageGenerationDraft("prompt", "one", 1)
            )
        self.fixtures.composition.status = StartingFrameStatus.APPROVED
        self.fixtures.composition.shot_version = 2
        with self.assertRaisesRegex(ValueError, "older shot revision"):
            await self.use_case()(
                "project", "shot", "composition-a", ImageGenerationDraft("prompt", "two", 1)
            )
        with self.assertRaises(ImageGenerationUnavailableError):
            await self.use_case(enabled=False)(
                "project", "shot", "composition-a", ImageGenerationDraft("prompt", "three", 1)
            )


if __name__ == "__main__":
    unittest.main()
