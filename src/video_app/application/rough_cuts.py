"""Approved storyboard-and-dialogue rough cuts through the canonical durable queue."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from video_app.application.assets import AssetRepository
from video_app.application.films import FilmRepository
from video_app.application.image_generation import validate_generation_idempotency_key
from video_app.application.ports import (
    ArtifactReader,
    Clock,
    IdentifierFactory,
    JobNotFoundError,
    JobRepository,
)
from video_app.application.projects import ProjectRepository
from video_app.domain.assets import AssetKind, AssetState, MediaAsset
from video_app.domain.films import (
    ApprovalStage,
    DialogueWorkflow,
    FilmApproval,
    film_workspace_fingerprint,
)
from video_app.domain.jobs import GenerationJob
from video_app.domain.models import (
    DomainValidationError,
    GenerationMode,
    GenerationRequest,
    Resolution,
    RoughCutItem,
    RoughCutManifest,
    RoughCutSource,
)
from video_app.domain.projects import ProjectPreset


class RoughCutUnavailableError(RuntimeError):
    """Raised when no qualified renderer is available."""


class RoughCutNotFoundError(LookupError):
    """Raised when a job is absent or belongs to another film."""


@dataclass(frozen=True, slots=True)
class RoughCutProvider:
    backend_name: str
    backend_revision: str
    display_name: str
    enabled: bool
    runtime_state: str
    width: int
    height: int
    fps_numerator: int
    fps_denominator: int
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.backend_name, "rough-cut backend name"),
            (self.backend_revision, "rough-cut backend revision"),
            (self.display_name, "rough-cut display name"),
            (self.runtime_state, "rough-cut runtime state"),
        ):
            if not value or value.isspace():
                raise ValueError(f"{field} must not be empty")
        if min(self.width, self.height, self.fps_numerator, self.fps_denominator) <= 0:
            raise ValueError("rough-cut export profile must be positive")
        if self.enabled and self.unavailable_reason is not None:
            raise ValueError("enabled rough-cut providers cannot have an unavailable reason")
        if not self.enabled and not self.unavailable_reason:
            raise ValueError("disabled rough-cut providers require an unavailable reason")


def _current_approval(
    approvals: tuple[FilmApproval, ...],
    stage: ApprovalStage,
    fingerprint: str,
    *,
    scene_id: str | None = None,
    shot_id: str | None = None,
) -> FilmApproval | None:
    return next(
        (
            item
            for item in reversed(approvals)
            if item.stage is stage
            and item.subject_fingerprint == fingerprint
            and item.scene_id == scene_id
            and item.shot_id == shot_id
        ),
        None,
    )


def _source(asset: MediaAsset) -> RoughCutSource:
    return RoughCutSource(asset.id, asset.version, asset.sha256, asset.storage_key)


@dataclass(frozen=True, slots=True)
class SubmitRoughCut:
    projects: ProjectRepository
    films: FilmRepository
    assets: AssetRepository
    jobs: JobRepository
    provider: RoughCutProvider
    clock: Clock
    identifiers: IdentifierFactory
    owner_id: str

    async def __call__(self, project_id: str, *, idempotency_key: str) -> GenerationJob:
        validate_generation_idempotency_key(idempotency_key)
        if not self.provider.enabled:
            raise RoughCutUnavailableError(
                self.provider.unavailable_reason or "The rough-cut renderer is not configured."
            )
        project = await self.projects.get(self.owner_id, project_id)
        if project.preset is not ProjectPreset.TELUGU_SHORT_FILM_900:
            raise DomainValidationError("rough cuts require the Telugu 900-second preset")
        if (
            project.export_settings.width != self.provider.width
            or project.export_settings.height != self.provider.height
            or project.export_settings.fps_numerator != self.provider.fps_numerator
            or project.export_settings.fps_denominator != self.provider.fps_denominator
        ):
            raise DomainValidationError(
                "project export settings do not match the qualified rough-cut runtime"
            )
        workspace = await self.films.snapshot(self.owner_id, project_id)
        if not workspace.scenes or not workspace.shots:
            raise DomainValidationError("rough cut requires scenes and shots")
        ordered_scenes = tuple(sorted(workspace.scenes, key=lambda item: item.draft.position))
        if len({item.draft.position for item in ordered_scenes}) != len(ordered_scenes):
            raise DomainValidationError("scene positions must be unique")
        if (
            sum(item.draft.target_duration_ms for item in ordered_scenes)
            != project.target_duration_ms
        ):
            raise DomainValidationError("scene targets must fill the complete film duration")

        items: list[RoughCutItem] = []
        for scene in ordered_scenes:
            for stage in (ApprovalStage.TELUGU_SCRIPT, ApprovalStage.PRONUNCIATION):
                if (
                    _current_approval(
                        workspace.approvals,
                        stage,
                        scene.content_fingerprint,
                        scene_id=scene.id,
                    )
                    is None
                ):
                    raise DomainValidationError(
                        "approve every current script and pronunciation before rendering"
                    )
            scene_shots = tuple(
                sorted(
                    (item for item in workspace.shots if item.scene_id == scene.id),
                    key=lambda item: item.draft.position,
                )
            )
            if not scene_shots or len({item.draft.position for item in scene_shots}) != len(
                scene_shots
            ):
                raise DomainValidationError("each scene requires uniquely positioned shots")
            if sum(item.draft.target_duration_ms for item in scene_shots) != (
                scene.draft.target_duration_ms
            ):
                raise DomainValidationError("shot targets must fill their complete scene duration")
            for shot in scene_shots:
                if shot.draft.dialogue_workflow is not DialogueWorkflow.RECORDED:
                    raise DomainValidationError(
                        "Phase 7A rough cuts require approved recorded dialogue for every shot"
                    )
                assert shot.draft.recorded_dialogue_asset_id is not None
                storyboard_approval = _current_approval(
                    workspace.approvals,
                    ApprovalStage.STORYBOARD,
                    shot.content_fingerprint,
                    scene_id=scene.id,
                    shot_id=shot.id,
                )
                voice_approval = _current_approval(
                    workspace.approvals,
                    ApprovalStage.VOICE_PERFORMANCE,
                    shot.content_fingerprint,
                    scene_id=scene.id,
                    shot_id=shot.id,
                )
                if (
                    storyboard_approval is None
                    or storyboard_approval.evidence_asset_id != shot.draft.storyboard_asset_id
                ):
                    raise DomainValidationError("approve each current storyboard before rendering")
                if (
                    voice_approval is None
                    or voice_approval.evidence_asset_id != shot.draft.recorded_dialogue_asset_id
                ):
                    raise DomainValidationError(
                        "approve each attached recorded dialogue performance before rendering"
                    )
                storyboard = await self.assets.get(
                    self.owner_id, project_id, shot.draft.storyboard_asset_id
                )
                dialogue = await self.assets.get(
                    self.owner_id, project_id, shot.draft.recorded_dialogue_asset_id
                )
                if storyboard.kind is not AssetKind.IMAGE:
                    raise DomainValidationError("rough-cut storyboards must be image assets")
                if (
                    dialogue.kind is not AssetKind.AUDIO
                    or dialogue.state is not AssetState.INSPECTED
                    or dialogue.metadata is None
                ):
                    raise DomainValidationError(
                        "rough-cut dialogue must be an inspected audio asset"
                    )
                items.append(
                    RoughCutItem(
                        scene_id=scene.id,
                        scene_version=scene.version,
                        scene_fingerprint=scene.content_fingerprint,
                        scene_position=scene.draft.position,
                        shot_id=shot.id,
                        shot_version=shot.version,
                        shot_fingerprint=shot.content_fingerprint,
                        shot_position=shot.draft.position,
                        duration_ms=shot.draft.target_duration_ms,
                        storyboard=_source(storyboard),
                        dialogue=_source(dialogue),
                    )
                )

        manifest = RoughCutManifest.create(
            owner_id=self.owner_id,
            project_id=project_id,
            workspace_fingerprint=film_workspace_fingerprint(
                workspace.scenes,
                workspace.shots,
                project.film_contract_fingerprint(),
            ),
            width=project.export_settings.width,
            height=project.export_settings.height,
            fps_numerator=project.export_settings.fps_numerator,
            fps_denominator=project.export_settings.fps_denominator,
            total_duration_ms=project.target_duration_ms,
            required_backend=self.provider.backend_name,
            required_backend_revision=self.provider.backend_revision,
            items=tuple(items),
        )
        request = GenerationRequest(
            prompt=f"Approved rough cut {manifest.workspace_fingerprint[:12]}",
            model=self.provider.backend_name,
            resolution=Resolution(manifest.width, manifest.height),
            frame_count=manifest.frame_count,
            seed=0,
            mode=GenerationMode.ROUGH_CUT,
            rough_cut=manifest,
        )
        return await self.jobs.enqueue(
            GenerationJob.queued(
                self.identifiers.new_job_id(),
                request,
                self.clock.now(),
                idempotency_key=idempotency_key,
            )
        )


def _require_owned_rough_cut(job: GenerationJob, owner_id: str, project_id: str) -> None:
    manifest = job.request.rough_cut
    if manifest is None or manifest.owner_id != owner_id or manifest.project_id != project_id:
        raise RoughCutNotFoundError(job.id)


@dataclass(frozen=True, slots=True)
class GetRoughCut:
    jobs: JobRepository
    owner_id: str

    async def __call__(self, project_id: str, job_id: str) -> GenerationJob:
        try:
            job = await self.jobs.get(job_id)
        except JobNotFoundError as error:
            raise RoughCutNotFoundError(job_id) from error
        _require_owned_rough_cut(job, self.owner_id, project_id)
        return job


@dataclass(frozen=True, slots=True)
class CancelRoughCut:
    jobs: JobRepository
    clock: Clock
    owner_id: str

    async def __call__(self, project_id: str, job_id: str) -> GenerationJob:
        try:
            job = await self.jobs.get(job_id)
        except JobNotFoundError as error:
            raise RoughCutNotFoundError(job_id) from error
        _require_owned_rough_cut(job, self.owner_id, project_id)
        return await self.jobs.request_cancellation(job_id, self.clock.now())


@dataclass(frozen=True, slots=True)
class GetRoughCutOutput:
    jobs: JobRepository
    artifacts: ArtifactReader
    owner_id: str

    async def __call__(self, project_id: str, job_id: str) -> Path:
        try:
            job = await self.jobs.get(job_id)
        except JobNotFoundError as error:
            raise RoughCutNotFoundError(job_id) from error
        _require_owned_rough_cut(job, self.owner_id, project_id)
        if job.result is None:
            raise RoughCutNotFoundError(job_id)
        return self.artifacts.resolve_for_read(job.result.storage_key)
