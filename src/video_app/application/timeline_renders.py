"""Approved timeline rendering through the canonical durable job queue."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from video_app.application.assets import AssetRepository
from video_app.application.image_generation import validate_generation_idempotency_key
from video_app.application.ports import (
    ArtifactReader,
    Clock,
    IdentifierFactory,
    JobNotFoundError,
    JobRepository,
)
from video_app.application.projects import ProjectRepository
from video_app.application.timelines import TimelineRepository
from video_app.domain.assets import AssetKind, AssetState, MediaAsset
from video_app.domain.jobs import GenerationJob
from video_app.domain.models import (
    DomainValidationError,
    GenerationMode,
    GenerationRequest,
    Resolution,
    TimelineRenderCaption,
    TimelineRenderItem,
    TimelineRenderManifest,
    TimelineRenderSource,
)
from video_app.domain.timelines import TimelineItemKind


class TimelineRenderUnavailableError(RuntimeError):
    """Raised when no qualified final-timeline renderer is available."""


class TimelineRenderNotFoundError(LookupError):
    """Raised when a render is absent or outside the owner/project/timeline boundary."""


@dataclass(frozen=True, slots=True)
class TimelineRenderProvider:
    backend_name: str
    backend_revision: str
    display_name: str
    enabled: bool
    runtime_state: str
    width: int
    height: int
    fps_numerator: int
    fps_denominator: int
    duration_ms: int
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.backend_name, "timeline-render backend name"),
            (self.backend_revision, "timeline-render backend revision"),
            (self.display_name, "timeline-render display name"),
            (self.runtime_state, "timeline-render runtime state"),
        ):
            if not value or value.isspace():
                raise ValueError(f"{field} must not be empty")
        if (
            min(
                self.width,
                self.height,
                self.fps_numerator,
                self.fps_denominator,
                self.duration_ms,
            )
            <= 0
        ):
            raise ValueError("timeline-render export profile must be positive")
        if self.enabled and self.unavailable_reason is not None:
            raise ValueError("enabled timeline-render providers cannot have a reason")
        if not self.enabled and not self.unavailable_reason:
            raise ValueError("disabled timeline-render providers require a reason")


def _source(asset: MediaAsset) -> TimelineRenderSource:
    if asset.kind is AssetKind.IMAGE:
        duration_ms = None
    else:
        assert asset.metadata is not None
        duration_ms = asset.metadata.duration_ms
    return TimelineRenderSource(
        asset_id=asset.id,
        asset_version=asset.version,
        sha256=asset.sha256,
        storage_key=asset.storage_key,
        media_kind=asset.kind.value,
        measured_duration_ms=duration_ms,
    )


def _validate_timed_asset(asset: MediaAsset, required_duration_ms: int) -> None:
    if asset.state is not AssetState.INSPECTED or asset.metadata is None:
        raise DomainValidationError("timeline audio and video must be inspected")
    if asset.metadata.duration_ms < required_duration_ms:
        raise DomainValidationError("timeline media is shorter than its scheduled duration")
    if asset.kind is AssetKind.AUDIO and any(
        value is None
        for value in (
            asset.metadata.sample_rate,
            asset.metadata.channels,
            asset.metadata.sample_count,
        )
    ):
        raise DomainValidationError("timeline audio requires complete measured audio metadata")
    if asset.kind is AssetKind.VIDEO and any(
        value is None
        for value in (
            asset.metadata.width,
            asset.metadata.height,
            asset.metadata.frame_rate_numerator,
            asset.metadata.frame_rate_denominator,
        )
    ):
        raise DomainValidationError("timeline video requires complete measured video metadata")


@dataclass(frozen=True, slots=True)
class SubmitTimelineRender:
    projects: ProjectRepository
    timelines: TimelineRepository
    assets: AssetRepository
    jobs: JobRepository
    provider: TimelineRenderProvider
    clock: Clock
    identifiers: IdentifierFactory
    owner_id: str

    async def __call__(
        self, project_id: str, timeline_id: str, *, idempotency_key: str
    ) -> GenerationJob:
        validate_generation_idempotency_key(idempotency_key)
        if not self.provider.enabled:
            raise TimelineRenderUnavailableError(
                self.provider.unavailable_reason or "The final timeline renderer is not configured."
            )
        project = await self.projects.get(self.owner_id, project_id)
        timeline = await self.timelines.get(self.owner_id, project_id, timeline_id)
        if project.approved_timeline_revision_id != timeline_id or timeline.approved_at is None:
            raise DomainValidationError("rendering requires the project's approved timeline")
        if (
            project.export_settings.width != self.provider.width
            or project.export_settings.height != self.provider.height
            or project.export_settings.fps_numerator != self.provider.fps_numerator
            or project.export_settings.fps_denominator != self.provider.fps_denominator
            or project.target_duration_ms != self.provider.duration_ms
        ):
            raise DomainValidationError(
                "project export settings do not match the qualified timeline renderer"
            )

        visual_items = sorted(
            (item for item in timeline.items if item.kind is not TimelineItemKind.AUDIO),
            key=lambda item: (item.start_ms, item.layer),
        )
        audio_items = sorted(
            (item for item in timeline.items if item.kind is TimelineItemKind.AUDIO),
            key=lambda item: (item.start_ms, item.layer),
        )
        expected_start = 0
        for item in visual_items:
            if item.layer != 0 or item.start_ms != expected_start:
                raise DomainValidationError(
                    "approved timeline visuals must be contiguous on layer zero"
                )
            expected_start += item.duration_ms
        if expected_start != project.target_duration_ms:
            raise DomainValidationError(
                "approved timeline visuals must fill the complete project duration"
            )
        if len(audio_items) > 32:
            raise DomainValidationError("timeline renders support at most 32 audio items")

        asset_ids = sorted(
            {item.asset_id for item in (*visual_items, *audio_items) if item.asset_id is not None}
        )
        assets = {
            asset_id: await self.assets.get(self.owner_id, project_id, asset_id)
            for asset_id in asset_ids
        }
        render_items: list[TimelineRenderItem] = []
        for item in (*visual_items, *audio_items):
            source = None
            if item.asset_id is not None:
                asset = assets[item.asset_id]
                expected_kind = AssetKind(item.kind.value)
                if asset.kind is not expected_kind:
                    raise DomainValidationError(
                        "timeline item kind does not match its current media asset"
                    )
                if asset.kind is not AssetKind.IMAGE:
                    _validate_timed_asset(asset, item.duration_ms)
                source = _source(asset)
            render_items.append(
                TimelineRenderItem(
                    kind=item.kind.value,
                    start_ms=item.start_ms,
                    duration_ms=item.duration_ms,
                    layer=item.layer,
                    source=source,
                    text=item.text,
                )
            )

        manifest = TimelineRenderManifest.create(
            owner_id=self.owner_id,
            project_id=project_id,
            timeline_id=timeline.id,
            timeline_revision=timeline.revision,
            timeline_fingerprint=timeline.fingerprint,
            width=project.export_settings.width,
            height=project.export_settings.height,
            fps_numerator=project.export_settings.fps_numerator,
            fps_denominator=project.export_settings.fps_denominator,
            total_duration_ms=project.target_duration_ms,
            required_backend=self.provider.backend_name,
            required_backend_revision=self.provider.backend_revision,
            items=tuple(render_items),
            captions=tuple(
                TimelineRenderCaption(item.start_ms, item.end_ms, item.text)
                for item in timeline.captions
            ),
        )
        request = GenerationRequest(
            prompt=f"Approved timeline {manifest.timeline_fingerprint[:12]}",
            model=self.provider.backend_name,
            resolution=Resolution(manifest.width, manifest.height),
            frame_count=manifest.frame_count,
            seed=0,
            mode=GenerationMode.TIMELINE_RENDER,
            timeline_render=manifest,
        )
        return await self.jobs.enqueue(
            GenerationJob.queued(
                self.identifiers.new_job_id(),
                request,
                self.clock.now(),
                idempotency_key=idempotency_key,
            )
        )


def _require_owned_render(
    job: GenerationJob, owner_id: str, project_id: str, timeline_id: str
) -> None:
    manifest = job.request.timeline_render
    if (
        manifest is None
        or manifest.owner_id != owner_id
        or manifest.project_id != project_id
        or manifest.timeline_id != timeline_id
    ):
        raise TimelineRenderNotFoundError(job.id)


@dataclass(frozen=True, slots=True)
class GetTimelineRender:
    jobs: JobRepository
    owner_id: str

    async def __call__(self, project_id: str, timeline_id: str, job_id: str) -> GenerationJob:
        try:
            job = await self.jobs.get(job_id)
        except JobNotFoundError as error:
            raise TimelineRenderNotFoundError(job_id) from error
        _require_owned_render(job, self.owner_id, project_id, timeline_id)
        return job


@dataclass(frozen=True, slots=True)
class CancelTimelineRender:
    jobs: JobRepository
    clock: Clock
    owner_id: str

    async def __call__(self, project_id: str, timeline_id: str, job_id: str) -> GenerationJob:
        try:
            job = await self.jobs.get(job_id)
        except JobNotFoundError as error:
            raise TimelineRenderNotFoundError(job_id) from error
        _require_owned_render(job, self.owner_id, project_id, timeline_id)
        return await self.jobs.request_cancellation(job_id, self.clock.now())


@dataclass(frozen=True, slots=True)
class GetTimelineRenderOutput:
    jobs: JobRepository
    artifacts: ArtifactReader
    owner_id: str

    async def __call__(self, project_id: str, timeline_id: str, job_id: str) -> Path:
        try:
            job = await self.jobs.get(job_id)
        except JobNotFoundError as error:
            raise TimelineRenderNotFoundError(job_id) from error
        _require_owned_render(job, self.owner_id, project_id, timeline_id)
        if job.result is None:
            raise TimelineRenderNotFoundError(job_id)
        return self.artifacts.resolve_for_read(job.result.storage_key)
