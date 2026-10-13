"""Composition root for API and worker processes."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from video_app.api.app import ApiServices, create_app
from video_app.application.assets import (
    InspectLibraryAsset,
    InspectProjectAsset,
    ListLibraryAssets,
    ListProjectAssets,
    UploadLibraryAsset,
    UploadProjectAsset,
)
from video_app.application.controlled_generation import (
    ControlledGenerationProvider,
    SubmitControlledGeneration,
)
from video_app.application.films import (
    ApproveFilmSubject,
    GetFilmReadiness,
    GetFilmWorkspace,
    SaveFilmScene,
    SaveFilmShot,
)
from video_app.application.image_generation import (
    CancelImageGeneration,
    GetImageGeneration,
    GetImageGenerationOutput,
    ImageGenerationProvider,
    SubmitImageGeneration,
)
from video_app.application.library import (
    ApproveFilmBibleSnapshot,
    ApproveLibraryVersion,
    ApproveReferenceVideoGuidance,
    ApproveStartingFrameComposition,
    CreateFilmBibleSnapshot,
    CreateLibraryEntity,
    CreateLibraryVersion,
    CreateReferenceVideoGuidance,
    CreateShotBindingRevision,
    CreateStartingFrameComposition,
    GetLibraryEntity,
    GetReferenceVideoPreview,
    GetStartingFramePreview,
    ListAffectedShots,
    ListFilmBibleSnapshots,
    ListLibraryEntities,
    ListLibraryVersions,
    ListReferenceVideoGuidance,
    ListShotBindingRevisions,
    ListStartingFrameCompositions,
    RenderStartingFrameComposition,
    ResolveFilmBibleName,
    UpdateLibraryEntity,
)
from video_app.application.projects import CreateProject, GetProject, ListProjects, UpdateProject
from video_app.application.recovery import RecoverExpiredLeases
from video_app.application.rough_cuts import (
    CancelRoughCut,
    GetRoughCut,
    GetRoughCutOutput,
    RoughCutProvider,
    SubmitRoughCut,
)
from video_app.application.runner import WorkerRunner
from video_app.application.timeline_renders import (
    CancelTimelineRender,
    GetTimelineRender,
    GetTimelineRenderOutput,
    SubmitTimelineRender,
    TimelineRenderProvider,
)
from video_app.application.timelines import (
    ApproveTimelineRevision,
    CreateTimelineRevision,
    ListTimelineRevisions,
)
from video_app.application.use_cases import (
    CancelJob,
    GetJob,
    GetJobOutput,
    HealthCheck,
    ListJobs,
    ListModels,
    SubmitJob,
)
from video_app.application.worker import ProcessNextJob
from video_app.backends.fake import FakeBackend
from video_app.domain.models import ControlledVideoOperation, Resolution
from video_app.domain.ports import GenerationBackend
from video_app.infrastructure.database import create_database_engine
from video_app.infrastructure.media import FfprobeMediaInspector, PillowStartingFrameRenderer
from video_app.infrastructure.postgres_assets import PostgresAssetRepository
from video_app.infrastructure.postgres_films import PostgresFilmRepository
from video_app.infrastructure.postgres_jobs import PostgresJobRepository
from video_app.infrastructure.postgres_library import PostgresLibraryRepository
from video_app.infrastructure.postgres_projects import PostgresProjectRepository
from video_app.infrastructure.postgres_timelines import PostgresTimelineRepository
from video_app.infrastructure.runtime import (
    RuntimeSettings,
    SecureIdentifiers,
    SecureSeedSource,
    StaticCapabilityProvider,
    UtcClock,
)
from video_app.infrastructure.storage import LocalArtifactStore


@dataclass(frozen=True, slots=True)
class RuntimeComponents:
    settings: RuntimeSettings
    engine: AsyncEngine
    repository: PostgresJobRepository
    artifacts: LocalArtifactStore
    temporary_root: Path
    capabilities: StaticCapabilityProvider
    clock: UtcClock
    identifiers: SecureIdentifiers


def build_runtime(settings: RuntimeSettings) -> RuntimeComponents:
    data_root = settings.data_root.resolve()
    artifact_root = data_root / "artifacts"
    temporary_root = data_root / "temporary"
    artifact_root.mkdir(parents=True, exist_ok=True)
    temporary_root.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(settings.database)
    return RuntimeComponents(
        settings=settings,
        engine=engine,
        repository=PostgresJobRepository(
            engine,
            queue_capacity=settings.queue_capacity,
            cursor_secret=settings.cursor_secret,
        ),
        artifacts=LocalArtifactStore(artifact_root),
        temporary_root=temporary_root,
        capabilities=StaticCapabilityProvider((settings.capability,)),
        clock=UtcClock(),
        identifiers=SecureIdentifiers(),
    )


def create_api_app(settings: RuntimeSettings) -> FastAPI:
    runtime = build_runtime(settings)
    project_repository = PostgresProjectRepository(runtime.engine)
    asset_repository = PostgresAssetRepository(runtime.engine)
    timeline_repository = PostgresTimelineRepository(runtime.engine)
    film_repository = PostgresFilmRepository(runtime.engine)
    library_repository = PostgresLibraryRepository(runtime.engine)
    starting_frame_renderer = PillowStartingFrameRenderer(runtime.temporary_root)
    inspector = (
        FfprobeMediaInspector(
            executable=settings.media.ffprobe_executable,
            expected_sha256=settings.media.ffprobe_sha256,
            expected_version_line=settings.media.ffprobe_version_line,
            timeout_seconds=settings.media.timeout_seconds,
            max_output_bytes=settings.media.max_output_bytes,
        )
        if settings.media is not None
        else None
    )
    from video_app.backends.wan22 import (
        WAN22_BACKEND_REVISION,
        WAN22_MODEL_ID,
    )

    image_provider = ImageGenerationProvider(
        backend_name="wan22-ti2v",
        backend_revision=WAN22_BACKEND_REVISION,
        model_id=WAN22_MODEL_ID,
        display_name="Wan2.2 TI2V 5B",
        task="ti2v-5B",
        area_preset=Resolution(1280, 704),
        frame_count=81,
        enabled=settings.wan22 is not None,
        runtime_state="qualified" if settings.wan22 is not None else "not_configured",
        unavailable_reason=None
        if settings.wan22 is not None
        else "A qualified Wan2.2 TI2V runtime is not configured.",
    )
    from video_app.backends.animate import (
        ANIMATE_BACKEND_REVISION,
        ANIMATE_MODEL_ID,
        ANIMATE_TASK,
    )
    from video_app.backends.vace import VACE_BACKEND_REVISION, VACE_MODEL_ID, VACE_TASK

    controlled_providers = (
        ControlledGenerationProvider(
            id="vace-performance-transfer",
            backend_name="vace-wan21",
            backend_revision=VACE_BACKEND_REVISION,
            model_id=VACE_MODEL_ID,
            display_name="VACE Wan2.1 performance transfer",
            task=VACE_TASK,
            operation=ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER,
            area_preset=Resolution(832, 480),
            frame_count=81,
            maximum_guidance_ms=5_063,
            preserves_starting_frame_environment=True,
            enabled=settings.vace is not None,
            runtime_state="qualified" if settings.vace is not None else "not_configured",
            unavailable_reason=None
            if settings.vace is not None
            else "A qualified VACE runtime is not configured.",
        ),
        ControlledGenerationProvider(
            id="wan-animate-character",
            backend_name="wan22-animate",
            backend_revision=ANIMATE_BACKEND_REVISION,
            model_id=ANIMATE_MODEL_ID,
            display_name="Wan2.2-Animate character animation",
            task=ANIMATE_TASK,
            operation=ControlledVideoOperation.ANIMATE_CHARACTER,
            area_preset=Resolution(1280, 720),
            frame_count=77,
            maximum_guidance_ms=2_567,
            preserves_starting_frame_environment=False,
            enabled=settings.animate is not None,
            runtime_state="qualified" if settings.animate is not None else "not_configured",
            unavailable_reason=None
            if settings.animate is not None
            else "A qualified Wan2.2-Animate runtime is not configured.",
        ),
        ControlledGenerationProvider(
            id="wan-animate-replacement",
            backend_name="wan22-animate",
            backend_revision=ANIMATE_BACKEND_REVISION,
            model_id=ANIMATE_MODEL_ID,
            display_name="Wan2.2-Animate character replacement",
            task=ANIMATE_TASK,
            operation=ControlledVideoOperation.ANIMATE_REPLACEMENT,
            area_preset=Resolution(1280, 720),
            frame_count=77,
            maximum_guidance_ms=2_567,
            preserves_starting_frame_environment=False,
            enabled=settings.animate is not None,
            runtime_state="qualified" if settings.animate is not None else "not_configured",
            unavailable_reason=None
            if settings.animate is not None
            else "A qualified Wan2.2-Animate runtime is not configured.",
        ),
    )
    from video_app.backends.rough_cut import ROUGH_CUT_BACKEND_NAME, ROUGH_CUT_BACKEND_REVISION

    rough_settings = settings.rough_cut
    rough_cut_provider = RoughCutProvider(
        backend_name=ROUGH_CUT_BACKEND_NAME,
        backend_revision=ROUGH_CUT_BACKEND_REVISION,
        display_name="Approved storyboard rough cut",
        enabled=rough_settings is not None,
        runtime_state="qualified" if rough_settings is not None else "not_configured",
        width=rough_settings.width if rough_settings is not None else 1280,
        height=rough_settings.height if rough_settings is not None else 720,
        fps_numerator=rough_settings.fps_numerator if rough_settings is not None else 24,
        fps_denominator=rough_settings.fps_denominator if rough_settings is not None else 1,
        unavailable_reason=(
            None
            if rough_settings is not None
            else "A qualified pinned FFmpeg rough-cut runtime is not configured."
        ),
    )
    from video_app.backends.timeline_render import (
        TIMELINE_RENDER_BACKEND_NAME,
        TIMELINE_RENDER_BACKEND_REVISION,
    )

    timeline_settings = settings.timeline_render
    timeline_render_provider = TimelineRenderProvider(
        backend_name=TIMELINE_RENDER_BACKEND_NAME,
        backend_revision=TIMELINE_RENDER_BACKEND_REVISION,
        display_name="Approved final timeline render",
        enabled=timeline_settings is not None,
        runtime_state="qualified" if timeline_settings is not None else "not_configured",
        width=timeline_settings.width if timeline_settings is not None else 1280,
        height=timeline_settings.height if timeline_settings is not None else 720,
        fps_numerator=(timeline_settings.fps_numerator if timeline_settings is not None else 24),
        fps_denominator=(timeline_settings.fps_denominator if timeline_settings is not None else 1),
        duration_ms=(timeline_settings.duration_ms if timeline_settings is not None else 900_000),
        unavailable_reason=(
            None
            if timeline_settings is not None
            else "A qualified pinned final-timeline renderer is not configured."
        ),
    )
    services = ApiServices(
        submit_job=SubmitJob(
            runtime.repository,
            runtime.capabilities,
            runtime.clock,
            runtime.identifiers,
            SecureSeedSource(),
        ),
        get_job=GetJob(runtime.repository),
        list_jobs=ListJobs(runtime.repository),
        cancel_job=CancelJob(runtime.repository, runtime.clock),
        get_output=GetJobOutput(runtime.repository, runtime.artifacts),
        list_models=ListModels(runtime.capabilities),
        health_check=HealthCheck(runtime.repository),
        identifiers=runtime.identifiers,
        close=runtime.engine.dispose,
        create_project=CreateProject(
            project_repository,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        get_project=GetProject(project_repository, settings.owner_id),
        list_projects=ListProjects(project_repository, settings.owner_id),
        update_project=UpdateProject(project_repository, runtime.clock, settings.owner_id),
        upload_project_asset=UploadProjectAsset(
            project_repository,
            asset_repository,
            runtime.artifacts,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
            settings.max_upload_bytes,
        ),
        list_project_assets=ListProjectAssets(
            project_repository,
            asset_repository,
            settings.owner_id,
        ),
        inspect_project_asset=InspectProjectAsset(
            project_repository,
            asset_repository,
            runtime.artifacts,
            inspector,
            runtime.clock,
            settings.owner_id,
        ),
        create_timeline_revision=CreateTimelineRevision(
            project_repository,
            asset_repository,
            timeline_repository,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        list_timeline_revisions=ListTimelineRevisions(
            project_repository,
            timeline_repository,
            settings.owner_id,
        ),
        approve_timeline_revision=ApproveTimelineRevision(
            project_repository,
            timeline_repository,
            runtime.clock,
            settings.owner_id,
        ),
        save_film_scene=SaveFilmScene(
            project_repository,
            film_repository,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        save_film_shot=SaveFilmShot(
            project_repository,
            asset_repository,
            film_repository,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        get_film_workspace=GetFilmWorkspace(
            project_repository,
            film_repository,
            settings.owner_id,
        ),
        get_film_readiness=GetFilmReadiness(
            project_repository,
            film_repository,
            settings.owner_id,
        ),
        approve_film_subject=ApproveFilmSubject(
            project_repository,
            asset_repository,
            film_repository,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        upload_library_asset=UploadLibraryAsset(
            asset_repository,
            runtime.artifacts,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
            settings.max_upload_bytes,
        ),
        list_library_assets=ListLibraryAssets(asset_repository, settings.owner_id),
        inspect_library_asset=InspectLibraryAsset(
            asset_repository,
            runtime.artifacts,
            inspector,
            runtime.clock,
            settings.owner_id,
        ),
        create_library_entity=CreateLibraryEntity(
            library_repository,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        get_library_entity=GetLibraryEntity(library_repository, settings.owner_id),
        list_library_entities=ListLibraryEntities(library_repository, settings.owner_id),
        update_library_entity=UpdateLibraryEntity(
            library_repository,
            runtime.clock,
            settings.owner_id,
        ),
        create_library_version=CreateLibraryVersion(
            library_repository,
            asset_repository,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        list_library_versions=ListLibraryVersions(library_repository, settings.owner_id),
        approve_library_version=ApproveLibraryVersion(
            library_repository,
            runtime.clock,
            settings.owner_id,
        ),
        create_film_bible_snapshot=CreateFilmBibleSnapshot(
            project_repository,
            library_repository,
            library_repository,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        list_film_bible_snapshots=ListFilmBibleSnapshots(
            project_repository,
            library_repository,
            settings.owner_id,
        ),
        approve_film_bible_snapshot=ApproveFilmBibleSnapshot(
            project_repository,
            library_repository,
            runtime.clock,
            settings.owner_id,
        ),
        resolve_film_bible_name=ResolveFilmBibleName(
            project_repository,
            library_repository,
            library_repository,
            settings.owner_id,
        ),
        create_shot_binding_revision=CreateShotBindingRevision(
            project_repository,
            film_repository,
            library_repository,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        list_shot_binding_revisions=ListShotBindingRevisions(
            project_repository,
            film_repository,
            library_repository,
            settings.owner_id,
        ),
        list_affected_shots=ListAffectedShots(
            project_repository,
            library_repository,
            library_repository,
            settings.owner_id,
        ),
        create_starting_frame_composition=CreateStartingFrameComposition(
            project_repository,
            film_repository,
            library_repository,
            library_repository,
            asset_repository,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        list_starting_frame_compositions=ListStartingFrameCompositions(
            project_repository,
            film_repository,
            library_repository,
            settings.owner_id,
        ),
        render_starting_frame_composition=RenderStartingFrameComposition(
            project_repository,
            film_repository,
            library_repository,
            asset_repository,
            runtime.artifacts,
            starting_frame_renderer,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        approve_starting_frame_composition=ApproveStartingFrameComposition(
            project_repository,
            film_repository,
            library_repository,
            asset_repository,
            runtime.clock,
            settings.owner_id,
        ),
        get_starting_frame_preview=GetStartingFramePreview(
            project_repository,
            film_repository,
            library_repository,
            asset_repository,
            runtime.artifacts,
            settings.owner_id,
        ),
        create_reference_video_guidance=CreateReferenceVideoGuidance(
            project_repository,
            film_repository,
            library_repository,
            library_repository,
            asset_repository,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        list_reference_video_guidance=ListReferenceVideoGuidance(
            project_repository,
            film_repository,
            library_repository,
            settings.owner_id,
        ),
        approve_reference_video_guidance=ApproveReferenceVideoGuidance(
            project_repository,
            film_repository,
            library_repository,
            library_repository,
            asset_repository,
            runtime.clock,
            settings.owner_id,
        ),
        get_reference_video_preview=GetReferenceVideoPreview(
            project_repository,
            film_repository,
            library_repository,
            asset_repository,
            runtime.artifacts,
            settings.owner_id,
        ),
        image_generation_provider=image_provider,
        submit_image_generation=SubmitImageGeneration(
            project_repository,
            film_repository,
            library_repository,
            asset_repository,
            runtime.repository,
            image_provider,
            runtime.clock,
            runtime.identifiers,
            SecureSeedSource(),
            settings.owner_id,
        ),
        get_image_generation=GetImageGeneration(runtime.repository, settings.owner_id),
        cancel_image_generation=CancelImageGeneration(
            runtime.repository, runtime.clock, settings.owner_id
        ),
        get_image_generation_output=GetImageGenerationOutput(
            runtime.repository, runtime.artifacts, settings.owner_id
        ),
        controlled_generation_providers=controlled_providers,
        submit_controlled_generation=SubmitControlledGeneration(
            project_repository,
            film_repository,
            library_repository,
            asset_repository,
            runtime.repository,
            controlled_providers,
            runtime.clock,
            runtime.identifiers,
            SecureSeedSource(),
            settings.owner_id,
        ),
        rough_cut_provider=rough_cut_provider,
        submit_rough_cut=SubmitRoughCut(
            project_repository,
            film_repository,
            asset_repository,
            runtime.repository,
            rough_cut_provider,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        get_rough_cut=GetRoughCut(runtime.repository, settings.owner_id),
        cancel_rough_cut=CancelRoughCut(runtime.repository, runtime.clock, settings.owner_id),
        get_rough_cut_output=GetRoughCutOutput(
            runtime.repository, runtime.artifacts, settings.owner_id
        ),
        timeline_render_provider=timeline_render_provider,
        submit_timeline_render=SubmitTimelineRender(
            project_repository,
            timeline_repository,
            asset_repository,
            runtime.repository,
            timeline_render_provider,
            runtime.clock,
            runtime.identifiers,
            settings.owner_id,
        ),
        get_timeline_render=GetTimelineRender(runtime.repository, settings.owner_id),
        cancel_timeline_render=CancelTimelineRender(
            runtime.repository, runtime.clock, settings.owner_id
        ),
        get_timeline_render_output=GetTimelineRenderOutput(
            runtime.repository, runtime.artifacts, settings.owner_id
        ),
    )
    return create_app(services)


def create_api_app_from_environment() -> FastAPI:
    return create_api_app(RuntimeSettings.from_environment())


def _build_generation_backend(
    settings: RuntimeSettings,
    temporary_root: Path,
) -> GenerationBackend:
    if settings.backend_name == "fake":
        return FakeBackend(temporary_root, (settings.capability,))
    if settings.backend_name == "wan21" and settings.wan21 is not None:
        from video_app.backends.wan21 import Wan21Backend

        return Wan21Backend(
            repository_root=settings.wan21.repository_root,
            checkpoint_dir=settings.wan21.checkpoint_dir,
            python_executable=settings.wan21.python_executable,
            output_root=temporary_root,
            task=settings.wan21.task,
            model_revision=settings.wan21.model_revision,
            model_capabilities=(settings.capability,),
        )
    if settings.backend_name == "wan22" and settings.wan22 is not None:
        from video_app.backends.wan22 import Wan22Backend

        return Wan22Backend(
            repository_root=settings.wan22.repository_root,
            checkpoint_dir=settings.wan22.checkpoint_dir,
            python_executable=settings.wan22.python_executable,
            output_root=temporary_root,
            checkpoint_manifest_sha256=settings.wan22.checkpoint_manifest_sha256,
            minimum_free_disk_bytes=settings.wan22.minimum_free_disk_bytes,
            minimum_free_vram_bytes=settings.wan22.minimum_free_vram_bytes,
            deadline_seconds=settings.wan22.deadline_seconds,
        )
    if settings.backend_name == "vace" and settings.vace is not None:
        from video_app.backends.controlled import ControlledRuntime
        from video_app.backends.vace import (
            VACE_BACKEND_REVISION,
            VACE_CODE_REVISION,
            VACE_MODEL_ID,
            VACE_TASK,
            VaceBackend,
        )

        return VaceBackend(
            ControlledRuntime(
                backend_name="vace-wan21",
                backend_revision=VACE_BACKEND_REVISION,
                code_revision=VACE_CODE_REVISION,
                model_id=VACE_MODEL_ID,
                display_name="VACE Wan2.1 performance transfer",
                task=VACE_TASK,
                operations=frozenset({ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER}),
                repository_root=settings.vace.repository_root,
                checkpoint_dir=settings.vace.checkpoint_dir,
                python_executable=settings.vace.python_executable,
                ffmpeg_executable=settings.vace.ffmpeg_executable,
                ffmpeg_sha256=settings.vace.ffmpeg_sha256,
                ffmpeg_version_line=settings.vace.ffmpeg_version_line,
                output_root=temporary_root,
                checkpoint_manifest_sha256=settings.vace.checkpoint_manifest_sha256,
                resolution=Resolution(832, 480),
                frame_count=81,
                input_fps=16,
                minimum_free_disk_bytes=settings.vace.minimum_free_disk_bytes,
                minimum_free_vram_bytes=settings.vace.minimum_free_vram_bytes,
                deadline_seconds=settings.vace.deadline_seconds,
            )
        )
    if settings.backend_name == "wan22-animate" and settings.animate is not None:
        from video_app.backends.animate import (
            ANIMATE_BACKEND_REVISION,
            ANIMATE_CODE_REVISION,
            ANIMATE_MODEL_ID,
            ANIMATE_TASK,
            WanAnimateBackend,
        )
        from video_app.backends.controlled import ControlledRuntime

        return WanAnimateBackend(
            ControlledRuntime(
                backend_name="wan22-animate",
                backend_revision=ANIMATE_BACKEND_REVISION,
                code_revision=ANIMATE_CODE_REVISION,
                model_id=ANIMATE_MODEL_ID,
                display_name="Wan2.2-Animate 14B",
                task=ANIMATE_TASK,
                operations=frozenset(
                    {
                        ControlledVideoOperation.ANIMATE_CHARACTER,
                        ControlledVideoOperation.ANIMATE_REPLACEMENT,
                    }
                ),
                repository_root=settings.animate.repository_root,
                checkpoint_dir=settings.animate.checkpoint_dir,
                python_executable=settings.animate.python_executable,
                ffmpeg_executable=settings.animate.ffmpeg_executable,
                ffmpeg_sha256=settings.animate.ffmpeg_sha256,
                ffmpeg_version_line=settings.animate.ffmpeg_version_line,
                output_root=temporary_root,
                checkpoint_manifest_sha256=settings.animate.checkpoint_manifest_sha256,
                resolution=Resolution(1280, 720),
                frame_count=77,
                input_fps=30,
                minimum_free_disk_bytes=settings.animate.minimum_free_disk_bytes,
                minimum_free_vram_bytes=settings.animate.minimum_free_vram_bytes,
                deadline_seconds=settings.animate.deadline_seconds,
            )
        )
    if settings.backend_name == "ffmpeg-rough-cut" and settings.rough_cut is not None:
        if settings.media is None:
            raise RuntimeError("rough-cut backend requires ffprobe settings")
        from video_app.backends.rough_cut import FfmpegRoughCutBackend, RoughCutRuntime

        rough = settings.rough_cut
        frame_numerator = 900_000 * rough.fps_numerator
        frame_denominator = 1_000 * rough.fps_denominator
        if frame_numerator % frame_denominator != 0:
            raise RuntimeError("rough-cut target duration does not resolve to whole frames")
        return FfmpegRoughCutBackend(
            RoughCutRuntime(
                ffmpeg_executable=rough.ffmpeg_executable,
                ffmpeg_sha256=rough.ffmpeg_sha256,
                ffmpeg_version_line=rough.ffmpeg_version_line,
                ffprobe_executable=settings.media.ffprobe_executable,
                ffprobe_sha256=settings.media.ffprobe_sha256,
                ffprobe_version_line=settings.media.ffprobe_version_line,
                output_root=temporary_root,
                resolution=Resolution(rough.width, rough.height),
                fps_numerator=rough.fps_numerator,
                fps_denominator=rough.fps_denominator,
                frame_count=frame_numerator // frame_denominator,
                deadline_seconds=rough.deadline_seconds,
            )
        )
    if settings.backend_name == "ffmpeg-timeline-render" and settings.timeline_render is not None:
        if settings.media is None:
            raise RuntimeError("timeline-render backend requires ffprobe settings")
        from video_app.backends.timeline_render import (
            FfmpegTimelineRenderBackend,
            TimelineRenderRuntime,
        )

        timeline = settings.timeline_render
        frame_numerator = timeline.duration_ms * timeline.fps_numerator
        frame_denominator = 1_000 * timeline.fps_denominator
        if frame_numerator % frame_denominator != 0:
            raise RuntimeError("timeline-render duration does not resolve to whole frames")
        return FfmpegTimelineRenderBackend(
            TimelineRenderRuntime(
                ffmpeg_executable=timeline.ffmpeg_executable,
                ffmpeg_sha256=timeline.ffmpeg_sha256,
                ffmpeg_version_line=timeline.ffmpeg_version_line,
                ffprobe_executable=settings.media.ffprobe_executable,
                ffprobe_sha256=settings.media.ffprobe_sha256,
                ffprobe_version_line=settings.media.ffprobe_version_line,
                font_file=timeline.font_file,
                font_sha256=timeline.font_sha256,
                font_family=timeline.font_family,
                output_root=temporary_root,
                resolution=Resolution(timeline.width, timeline.height),
                fps_numerator=timeline.fps_numerator,
                fps_denominator=timeline.fps_denominator,
                frame_count=frame_numerator // frame_denominator,
                duration_ms=timeline.duration_ms,
                deadline_seconds=timeline.deadline_seconds,
            )
        )
    raise RuntimeError("generation backend settings are inconsistent")


def build_worker(settings: RuntimeSettings) -> tuple[WorkerRunner, AsyncEngine]:
    runtime = build_runtime(settings)
    backend = _build_generation_backend(settings, runtime.temporary_root)
    process_next = ProcessNextJob(
        repository=runtime.repository,
        artifacts=runtime.artifacts,
        backend=backend,
        clock=runtime.clock,
        identifiers=runtime.identifiers,
        worker_id=f"worker_{uuid4().hex}",
        lease_duration=settings.lease_duration,
        heartbeat_interval=settings.heartbeat_interval,
    )
    recovery = RecoverExpiredLeases(
        runtime.repository,
        runtime.clock,
        runtime.identifiers,
    )
    return (
        WorkerRunner(process_next, recovery, settings.poll_interval_seconds),
        runtime.engine,
    )


def _settings_from_file(value: str) -> RuntimeSettings:
    return RuntimeSettings.from_file(Path(value).resolve(strict=True))


def api_main() -> None:
    parser = argparse.ArgumentParser(description="Run the video generation API")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()
    settings = _settings_from_file(arguments.env_file)
    uvicorn.run(create_api_app(settings), host=arguments.host, port=arguments.port)


async def _run_worker(settings: RuntimeSettings, *, once: bool) -> None:
    runner, engine = build_worker(settings)
    try:
        if once:
            await runner.run_once()
        else:
            await runner.run_until_stopped(asyncio.Event())
    finally:
        await engine.dispose()


def worker_main() -> None:
    parser = argparse.ArgumentParser(description="Run the video generation worker")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args()
    try:
        asyncio.run(_run_worker(_settings_from_file(arguments.env_file), once=arguments.once))
    except KeyboardInterrupt:
        return
