"""Approved still plus approved reference-video submission through the canonical queue."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from video_app.application.assets import AssetRepository
from video_app.application.films import FilmRepository
from video_app.application.image_generation import (
    normalize_generation_prompt,
    validate_generation_idempotency_key,
)
from video_app.application.library import FilmBibleRepository
from video_app.application.ports import Clock, IdentifierFactory, JobRepository, SeedSource
from video_app.application.projects import ProjectRepository
from video_app.domain.assets import AssetKind, AssetState
from video_app.domain.jobs import GenerationJob
from video_app.domain.library import (
    FilmBiblePinRole,
    ReferenceGuidanceStatus,
    ReferenceVideoPurpose,
    StartingFrameStatus,
)
from video_app.domain.models import (
    MAX_SEED,
    MIN_SEED,
    ControlledVideoOperation,
    DomainValidationError,
    GenerationMode,
    GenerationRequest,
    ImageConditioning,
    ReferenceVideoConditioning,
    Resolution,
)


class ControlledGenerationUnavailableError(RuntimeError):
    """Raised when an explicitly selected controlled-video runtime is unavailable."""


class ConstraintConflictError(ValueError):
    """Raised when a provider would have to ignore or reinterpret a frozen constraint."""


@dataclass(frozen=True, slots=True)
class ControlledGenerationProvider:
    id: str
    backend_name: str
    backend_revision: str
    model_id: str
    display_name: str
    task: str
    operation: ControlledVideoOperation
    area_preset: Resolution
    frame_count: int
    maximum_guidance_ms: int
    preserves_starting_frame_environment: bool
    enabled: bool
    runtime_state: str
    unavailable_reason: str | None

    def __post_init__(self) -> None:
        for value, field in (
            (self.id, "controlled provider id"),
            (self.backend_name, "controlled backend name"),
            (self.backend_revision, "controlled backend revision"),
            (self.model_id, "controlled model id"),
            (self.display_name, "controlled display name"),
            (self.task, "controlled task"),
            (self.runtime_state, "controlled runtime state"),
        ):
            if not value or value.isspace():
                raise ValueError(f"{field} must not be empty")
        if self.frame_count < 1 or self.maximum_guidance_ms < 250:
            raise ValueError("controlled provider limits must be positive")
        if self.enabled and self.unavailable_reason is not None:
            raise ValueError("enabled providers cannot have an unavailable reason")
        if not self.enabled and not self.unavailable_reason:
            raise ValueError("disabled providers require an unavailable reason")
        expected_preservation = self.operation is ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER
        if self.preserves_starting_frame_environment != expected_preservation:
            raise ValueError("provider preservation semantics must match its operation")


@dataclass(frozen=True, slots=True)
class ControlledGenerationDraft:
    provider_id: str
    prompt: str
    idempotency_key: str
    preserve_environment: bool
    seed: int | None = None


def _provider_by_id(
    providers: tuple[ControlledGenerationProvider, ...], provider_id: str
) -> ControlledGenerationProvider:
    return next(
        (provider for provider in providers if provider.id == provider_id),
        None,
    ) or (_raise_unknown_provider(provider_id))


def _raise_unknown_provider(provider_id: str) -> ControlledGenerationProvider:
    raise DomainValidationError(f"unsupported controlled-generation provider: {provider_id}")


def _constraint_plan(
    *,
    provider: ControlledGenerationProvider,
    purpose: ReferenceVideoPurpose,
    guidance_duration_ms: int,
    preserve_environment: bool,
    has_environment_bindings: bool,
    visible_speaker_entity_id: str | None,
) -> dict[str, object]:
    if purpose is not ReferenceVideoPurpose.MOTION_PERFORMANCE:
        raise ConstraintConflictError(
            "shot-guidance and review-only references are not model conditioning"
        )
    if guidance_duration_ms > provider.maximum_guidance_ms:
        raise ConstraintConflictError("the approved range exceeds the provider clip limit")
    if provider.operation is ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER:
        if not preserve_environment:
            raise ConstraintConflictError(
                "VACE performance transfer requires the approved starting-frame environment"
            )
    else:
        if preserve_environment or has_environment_bindings:
            raise ConstraintConflictError(
                "Wan Animate cannot preserve a separately selected set or prop in this workflow"
            )
        if visible_speaker_entity_id is None:
            raise ConstraintConflictError(
                "Wan Animate requires an explicitly associated visible character"
            )
    return {
        "operation": provider.operation.value,
        "guidance_purpose": purpose.value,
        "preserve_environment": preserve_environment,
        "has_environment_bindings": has_environment_bindings,
        "starting_frame_consumed": True,
        "reference_video_consumed": True,
        "source_video_environment_allowed": (
            provider.operation is ControlledVideoOperation.ANIMATE_REPLACEMENT
        ),
        "continuity_review_required": True,
    }


@dataclass(frozen=True, slots=True)
class SubmitControlledGeneration:
    projects: ProjectRepository
    films: FilmRepository
    film_bibles: FilmBibleRepository
    assets: AssetRepository
    jobs: JobRepository
    providers: tuple[ControlledGenerationProvider, ...]
    clock: Clock
    identifiers: IdentifierFactory
    seeds: SeedSource
    owner_id: str

    async def __call__(
        self,
        project_id: str,
        shot_id: str,
        composition_id: str,
        guidance_id: str,
        draft: ControlledGenerationDraft,
    ) -> GenerationJob:
        provider = _provider_by_id(self.providers, draft.provider_id)
        if not provider.enabled:
            raise ControlledGenerationUnavailableError(provider.runtime_state)
        await self.projects.get(self.owner_id, project_id)
        shot = await self.films.get_shot(self.owner_id, project_id, shot_id)
        composition = await self.film_bibles.get_starting_frame_composition(
            self.owner_id, project_id, shot_id, composition_id
        )
        guidance = await self.film_bibles.get_reference_video_guidance(
            self.owner_id, project_id, shot_id, guidance_id
        )
        if composition.status is not StartingFrameStatus.APPROVED:
            raise DomainValidationError("controlled generation requires an approved starting frame")
        if guidance.status is not ReferenceGuidanceStatus.APPROVED:
            raise DomainValidationError(
                "controlled generation requires approved reference guidance"
            )
        if composition.shot_version != shot.version or guidance.shot_version != shot.version:
            raise DomainValidationError("controlled-generation inputs belong to an older shot")
        if composition.shot_binding_revision_id != guidance.shot_binding_revision_id:
            raise ConstraintConflictError(
                "starting frame and reference use different shot bindings"
            )
        binding = await self.film_bibles.get_shot_binding_revision(
            self.owner_id,
            project_id,
            shot_id,
            composition.shot_binding_revision_id,
        )
        if binding.shot_version != shot.version:
            raise DomainValidationError("controlled generation requires current shot bindings")
        has_environment_bindings = any(
            item.role
            in {
                FilmBiblePinRole.LOCATION_VIEW,
                FilmBiblePinRole.LOCATION_LIGHTING,
                FilmBiblePinRole.PROP_VARIANT,
                FilmBiblePinRole.PROP_STATE,
            }
            for item in binding.bindings
        )
        plan = _constraint_plan(
            provider=provider,
            purpose=guidance.purpose,
            guidance_duration_ms=guidance.trim_end_ms - guidance.trim_start_ms,
            preserve_environment=draft.preserve_environment,
            has_environment_bindings=has_environment_bindings,
            visible_speaker_entity_id=composition.visible_speaker_entity_id,
        )
        if (
            composition.rendered_asset_id is None
            or composition.rendered_asset_version is None
            or composition.rendered_sha256 is None
        ):
            raise DomainValidationError("approved starting-frame metadata is incomplete")
        image_asset = await self.assets.get(
            self.owner_id, project_id, composition.rendered_asset_id
        )
        if (
            image_asset.kind is not AssetKind.IMAGE
            or image_asset.state not in {AssetState.READY, AssetState.INSPECTED}
            or image_asset.version != composition.rendered_asset_version
            or image_asset.sha256 != composition.rendered_sha256
        ):
            raise DomainValidationError("starting-frame bytes no longer match their approval pin")
        reference_asset = await self.assets.get_owner(self.owner_id, guidance.source.asset_id)
        if (
            reference_asset.kind is not AssetKind.VIDEO
            or reference_asset.state is not AssetState.INSPECTED
            or reference_asset.version != guidance.source.asset_version
            or reference_asset.sha256 != guidance.source.asset_sha256
            or reference_asset.inspector_revision != guidance.source.inspector_revision
        ):
            raise DomainValidationError("reference-video bytes no longer match their approval pin")

        prompt = normalize_generation_prompt(draft.prompt)
        idempotency_key = validate_generation_idempotency_key(draft.idempotency_key)
        seed = self.seeds.new_seed() if draft.seed is None else draft.seed
        if not MIN_SEED <= seed <= MAX_SEED:
            raise DomainValidationError("seed must be a signed 64-bit integer")
        plan_fingerprint = hashlib.sha256(
            json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        manifest_payload = {
            "owner_id": self.owner_id,
            "project_id": project_id,
            "shot_id": shot_id,
            "shot_version": shot.version,
            "shot_binding_revision_id": binding.id,
            "shot_binding_fingerprint": binding.fingerprint,
            "composition_id": composition.id,
            "composition_revision": composition.revision,
            "composition_fingerprint": composition.fingerprint,
            "image_asset_id": image_asset.id,
            "image_asset_version": image_asset.version,
            "image_asset_sha256": image_asset.sha256,
            "guidance_id": guidance.id,
            "guidance_revision": guidance.revision,
            "guidance_fingerprint": guidance.fingerprint,
            "reference_asset_id": reference_asset.id,
            "reference_asset_version": reference_asset.version,
            "reference_asset_sha256": reference_asset.sha256,
            "trim_start_ms": guidance.trim_start_ms,
            "trim_end_ms": guidance.trim_end_ms,
            "constraint_plan_fingerprint": plan_fingerprint,
            "backend": provider.backend_name,
            "backend_revision": provider.backend_revision,
            "model": provider.model_id,
            "task": provider.task,
            "prompt": prompt,
            "seed": seed,
        }
        manifest_fingerprint = hashlib.sha256(
            json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        reference = ReferenceVideoConditioning(
            guidance_id=guidance.id,
            guidance_revision=guidance.revision,
            guidance_fingerprint=guidance.fingerprint,
            purpose=guidance.purpose.value,
            source_asset_id=reference_asset.id,
            source_asset_version=reference_asset.version,
            source_asset_sha256=reference_asset.sha256,
            source_storage_key=reference_asset.storage_key,
            trim_start_ms=guidance.trim_start_ms,
            trim_end_ms=guidance.trim_end_ms,
            operation=provider.operation,
            preserve_environment=draft.preserve_environment,
            constraint_plan_fingerprint=plan_fingerprint,
        )
        conditioning = ImageConditioning(
            owner_id=self.owner_id,
            project_id=project_id,
            shot_id=shot_id,
            shot_version=shot.version,
            composition_id=composition.id,
            composition_revision=composition.revision,
            composition_fingerprint=composition.fingerprint,
            source_asset_id=image_asset.id,
            source_asset_version=image_asset.version,
            source_asset_sha256=image_asset.sha256,
            source_storage_key=image_asset.storage_key,
            source_width=composition.canvas_width,
            source_height=composition.canvas_height,
            required_backend=provider.backend_name,
            required_backend_revision=provider.backend_revision,
            manifest_fingerprint=manifest_fingerprint,
            reference_video=reference,
        )
        request = GenerationRequest(
            prompt=prompt,
            model=provider.model_id,
            resolution=provider.area_preset,
            frame_count=provider.frame_count,
            seed=seed,
            mode=GenerationMode.IMAGE_TO_VIDEO,
            image_conditioning=conditioning,
        )
        return await self.jobs.enqueue(
            GenerationJob.queued(
                self.identifiers.new_job_id(),
                request,
                self.clock.now(),
                idempotency_key=idempotency_key,
            )
        )
