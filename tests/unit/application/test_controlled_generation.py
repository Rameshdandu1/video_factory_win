from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast

from video_app.application.assets import AssetRepository
from video_app.application.controlled_generation import (
    ConstraintConflictError,
    ControlledGenerationDraft,
    ControlledGenerationProvider,
    ControlledGenerationUnavailableError,
    SubmitControlledGeneration,
)
from video_app.application.films import FilmRepository
from video_app.application.library import FilmBibleRepository
from video_app.application.ports import IdempotencyConflictError, IdentifierFactory, JobRepository
from video_app.application.projects import ProjectRepository
from video_app.domain.assets import AssetKind, AssetState
from video_app.domain.jobs import GenerationJob
from video_app.domain.library import (
    FilmBiblePinRole,
    ReferenceGuidanceStatus,
    ReferenceVideoPurpose,
    StartingFrameStatus,
)
from video_app.domain.models import ControlledVideoOperation, GenerationMode, Resolution

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


class Fixtures:
    def __init__(self) -> None:
        self.shot = SimpleNamespace(version=2)
        self.composition = SimpleNamespace(
            id="composition_one",
            status=StartingFrameStatus.APPROVED,
            shot_version=2,
            shot_binding_revision_id="binding_one",
            revision=1,
            fingerprint="a" * 64,
            rendered_asset_id="image_one",
            rendered_asset_version=1,
            rendered_sha256="b" * 64,
            canvas_width=832,
            canvas_height=480,
            visible_speaker_entity_id="character_one",
        )
        self.guidance = SimpleNamespace(
            id="guidance_one",
            status=ReferenceGuidanceStatus.APPROVED,
            shot_version=2,
            shot_binding_revision_id="binding_one",
            revision=1,
            fingerprint="c" * 64,
            purpose=ReferenceVideoPurpose.MOTION_PERFORMANCE,
            trim_start_ms=1_000,
            trim_end_ms=4_000,
            source=SimpleNamespace(
                asset_id="video_one",
                asset_version=2,
                asset_sha256="d" * 64,
                inspector_revision="ffprobe:qualified",
            ),
        )
        self.binding = SimpleNamespace(
            id="binding_one",
            shot_version=2,
            fingerprint="e" * 64,
            bindings=(SimpleNamespace(role=FilmBiblePinRole.CHARACTER_IDENTITY),),
        )
        self.image = SimpleNamespace(
            id="image_one",
            kind=AssetKind.IMAGE,
            state=AssetState.READY,
            version=1,
            sha256="b" * 64,
            storage_key="uploads/image-one.png",
        )
        self.video = SimpleNamespace(
            id="video_one",
            kind=AssetKind.VIDEO,
            state=AssetState.INSPECTED,
            version=2,
            sha256="d" * 64,
            storage_key="uploads/video-one.mp4",
            inspector_revision="ffprobe:qualified",
        )
        self.jobs: dict[tuple[str, str], GenerationJob] = {}

    async def get(self, *arguments: str) -> object:
        if len(arguments) == 2:
            return SimpleNamespace(id=arguments[1])
        return self.image

    async def get_owner(self, *_: str) -> object:
        return self.video

    async def get_shot(self, *_: str) -> object:
        return self.shot

    async def get_starting_frame_composition(self, *_: str) -> object:
        return self.composition

    async def get_reference_video_guidance(self, *_: str) -> object:
        return self.guidance

    async def get_shot_binding_revision(self, *_: str) -> object:
        return self.binding

    async def enqueue(self, job: GenerationJob) -> GenerationJob:
        conditioning = job.request.image_conditioning
        assert conditioning is not None and job.idempotency_key is not None
        key = (conditioning.owner_id, job.idempotency_key)
        existing = self.jobs.get(key)
        if existing is not None:
            previous = existing.request.image_conditioning
            assert previous is not None
            if previous.manifest_fingerprint != conditioning.manifest_fingerprint:
                raise IdempotencyConflictError
            return existing
        self.jobs[key] = job
        return job


class Clock:
    def now(self) -> datetime:
        return NOW


class Identifiers:
    def __init__(self) -> None:
        self.value = 0

    def new_job_id(self) -> str:
        self.value += 1
        return f"controlled_job_{self.value}"


class Seeds:
    def new_seed(self) -> int:
        return 17


def vace_provider(*, enabled: bool = True) -> ControlledGenerationProvider:
    return ControlledGenerationProvider(
        id="vace-performance-transfer",
        backend_name="vace-wan21",
        backend_revision="vace@code;task=animate_anything;model@model",
        model_id="vace-wan21-1.3b-performance",
        display_name="VACE performance transfer",
        task="animate_anything:salientbboxtrack",
        operation=ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER,
        area_preset=Resolution(832, 480),
        frame_count=81,
        maximum_guidance_ms=5_063,
        preserves_starting_frame_environment=True,
        enabled=enabled,
        runtime_state="qualified" if enabled else "not_configured",
        unavailable_reason=None if enabled else "not configured",
    )


def animate_provider() -> ControlledGenerationProvider:
    return ControlledGenerationProvider(
        id="wan-animate-character",
        backend_name="wan22-animate",
        backend_revision="wan2.2@code;task=animate-14B;model@model",
        model_id="wan22-animate-14b",
        display_name="Wan Animate character",
        task="animate-14B",
        operation=ControlledVideoOperation.ANIMATE_CHARACTER,
        area_preset=Resolution(1280, 720),
        frame_count=77,
        maximum_guidance_ms=2_567,
        preserves_starting_frame_environment=False,
        enabled=True,
        runtime_state="qualified",
        unavailable_reason=None,
    )


class ControlledGenerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.fixtures = Fixtures()

    def use_case(
        self, providers: tuple[ControlledGenerationProvider, ...]
    ) -> SubmitControlledGeneration:
        fixtures = self.fixtures
        return SubmitControlledGeneration(
            projects=cast(ProjectRepository, fixtures),
            films=cast(FilmRepository, fixtures),
            film_bibles=cast(FilmBibleRepository, fixtures),
            assets=cast(AssetRepository, fixtures),
            jobs=cast(JobRepository, fixtures),
            providers=providers,
            clock=Clock(),
            identifiers=cast(IdentifierFactory, Identifiers()),
            seeds=Seeds(),
            owner_id="owner_one",
        )

    async def test_vace_freezes_both_approved_inputs_and_constraint_plan(self) -> None:
        draft = ControlledGenerationDraft(
            provider_id="vace-performance-transfer",
            prompt="  natural Telugu dialogue performance  ",
            idempotency_key="controlled-one",
            preserve_environment=True,
            seed=-7,
        )
        first = await self.use_case((vace_provider(),))(
            "project_one", "shot_one", "composition_one", "guidance_one", draft
        )
        second = await self.use_case((vace_provider(),))(
            "project_one", "shot_one", "composition_one", "guidance_one", draft
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.request.mode, GenerationMode.IMAGE_TO_VIDEO)
        self.assertEqual(first.request.prompt, "natural Telugu dialogue performance")
        conditioning = first.request.image_conditioning
        assert conditioning is not None and conditioning.reference_video is not None
        self.assertEqual(conditioning.source_asset_sha256, "b" * 64)
        self.assertEqual(conditioning.reference_video.source_asset_sha256, "d" * 64)
        self.assertEqual(conditioning.reference_video.trim_start_ms, 1_000)
        self.assertEqual(conditioning.reference_video.trim_end_ms, 4_000)
        self.assertEqual(
            conditioning.reference_video.operation,
            ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER,
        )
        self.assertEqual(len(conditioning.reference_video.constraint_plan_fingerprint), 64)

    async def test_non_conditioning_purpose_is_rejected_instead_of_reinterpreted(self) -> None:
        self.fixtures.guidance.purpose = ReferenceVideoPurpose.SHOT_GUIDANCE
        with self.assertRaisesRegex(ConstraintConflictError, "not model conditioning"):
            await self.use_case((vace_provider(),))(
                "project_one",
                "shot_one",
                "composition_one",
                "guidance_one",
                ControlledGenerationDraft(
                    "vace-performance-transfer", "prompt", "purpose-conflict", True, 1
                ),
            )

    async def test_animate_rejects_set_constraints_and_preservation_claim(self) -> None:
        provider = animate_provider()
        draft = ControlledGenerationDraft(provider.id, "prompt", "animate-conflict", False, 1)
        self.fixtures.guidance.trim_end_ms = 3_000
        self.fixtures.binding.bindings = (
            SimpleNamespace(role=FilmBiblePinRole.CHARACTER_IDENTITY),
            SimpleNamespace(role=FilmBiblePinRole.LOCATION_VIEW),
        )
        with self.assertRaisesRegex(ConstraintConflictError, "cannot preserve"):
            await self.use_case((provider,))(
                "project_one", "shot_one", "composition_one", "guidance_one", draft
            )

        self.fixtures.binding.bindings = (
            SimpleNamespace(role=FilmBiblePinRole.CHARACTER_IDENTITY),
        )
        with self.assertRaisesRegex(ConstraintConflictError, "cannot preserve"):
            await self.use_case((provider,))(
                "project_one",
                "shot_one",
                "composition_one",
                "guidance_one",
                ControlledGenerationDraft(provider.id, "prompt", "animate-preserve", True, 1),
            )

    async def test_unqualified_provider_cannot_queue_work(self) -> None:
        with self.assertRaises(ControlledGenerationUnavailableError):
            await self.use_case((vace_provider(enabled=False),))(
                "project_one",
                "shot_one",
                "composition_one",
                "guidance_one",
                ControlledGenerationDraft(
                    "vace-performance-transfer", "prompt", "disabled", True, 1
                ),
            )


if __name__ == "__main__":
    unittest.main()
