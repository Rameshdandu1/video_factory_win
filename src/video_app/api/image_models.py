"""Transport models for shot-scoped reference-driven image generation."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator

from video_app.application.controlled_generation import (
    ControlledGenerationDraft,
    ControlledGenerationProvider,
)
from video_app.application.image_generation import (
    ImageGenerationDraft,
    ImageGenerationProvider,
)
from video_app.domain.jobs import GenerationJob, JobStatus
from video_app.domain.models import MAX_SEED, MIN_SEED, ErrorCode


class ImageGenerationDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(strict=True)
    idempotency_key: str = Field(min_length=1, max_length=200, strict=True)
    seed: str | None = Field(default=None, strict=True)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        if not 1 <= len(value.strip()) <= 2_000:
            raise ValueError("prompt must contain between 1 and 2000 characters")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        if value.isspace() or "\x00" in value:
            raise ValueError("idempotency_key contains invalid characters")
        return value

    @field_validator("seed")
    @classmethod
    def validate_seed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value or value.strip() != value or value.removeprefix("-").isdigit() is False:
            raise ValueError("seed must be a decimal signed 64-bit integer string")
        parsed = int(value)
        if not MIN_SEED <= parsed <= MAX_SEED:
            raise ValueError("seed must be a decimal signed 64-bit integer string")
        return value

    def to_domain(self) -> ImageGenerationDraft:
        return ImageGenerationDraft(
            prompt=self.prompt,
            idempotency_key=self.idempotency_key,
            seed=None if self.seed is None else int(self.seed),
        )


class ControlledGenerationDraftModel(ImageGenerationDraftModel):
    provider_id: str = Field(min_length=1, max_length=100, strict=True)
    preserve_environment: bool = Field(strict=True)

    def to_controlled_domain(self) -> ControlledGenerationDraft:
        return ControlledGenerationDraft(
            provider_id=self.provider_id,
            prompt=self.prompt,
            idempotency_key=self.idempotency_key,
            preserve_environment=self.preserve_environment,
            seed=None if self.seed is None else int(self.seed),
        )


class ImageGenerationProviderModel(BaseModel):
    backend: str
    backend_revision: str
    model: str
    display_name: str
    task: str
    area_width: int
    area_height: int
    frame_count: int
    enabled: bool
    runtime_state: str
    unavailable_reason: str | None

    @classmethod
    def from_domain(cls, value: ImageGenerationProvider) -> ImageGenerationProviderModel:
        return cls(
            backend=value.backend_name,
            backend_revision=value.backend_revision,
            model=value.model_id,
            display_name=value.display_name,
            task=value.task,
            area_width=value.area_preset.width,
            area_height=value.area_preset.height,
            frame_count=value.frame_count,
            enabled=value.enabled,
            runtime_state=value.runtime_state,
            unavailable_reason=value.unavailable_reason,
        )


class ControlledGenerationProviderModel(BaseModel):
    id: str
    backend: str
    backend_revision: str
    model: str
    display_name: str
    task: str
    operation: str
    area_width: int
    area_height: int
    frame_count: int
    maximum_guidance_ms: int
    preserves_starting_frame_environment: bool
    enabled: bool
    runtime_state: str
    unavailable_reason: str | None

    @classmethod
    def from_domain(cls, value: ControlledGenerationProvider) -> ControlledGenerationProviderModel:
        return cls(
            id=value.id,
            backend=value.backend_name,
            backend_revision=value.backend_revision,
            model=value.model_id,
            display_name=value.display_name,
            task=value.task,
            operation=value.operation.value,
            area_width=value.area_preset.width,
            area_height=value.area_preset.height,
            frame_count=value.frame_count,
            maximum_guidance_ms=value.maximum_guidance_ms,
            preserves_starting_frame_environment=value.preserves_starting_frame_environment,
            enabled=value.enabled,
            runtime_state=value.runtime_state,
            unavailable_reason=value.unavailable_reason,
        )


class ControlledGenerationProviderListModel(BaseModel):
    items: tuple[ControlledGenerationProviderModel, ...]


class ReferenceVideoConditioningModel(BaseModel):
    guidance_id: str
    guidance_revision: int
    guidance_fingerprint: str
    purpose: str
    source_asset_id: str
    source_asset_version: int
    source_asset_sha256: str
    trim_start_ms: int
    trim_end_ms: int
    operation: str
    preserve_environment: bool
    constraint_plan_fingerprint: str


class ImageConditioningModel(BaseModel):
    project_id: str
    shot_id: str
    shot_version: int
    composition_id: str
    composition_revision: int
    composition_fingerprint: str
    source_asset_id: str
    source_asset_version: int
    source_asset_sha256: str
    source_width: int
    source_height: int
    manifest_fingerprint: str
    reference_video: ReferenceVideoConditioningModel | None


class ConditioningEvidenceModel(BaseModel):
    source_sha256: str
    derivative_sha256: str
    derivative_width: int
    derivative_height: int
    reference_source_sha256: str | None
    reference_derivative_sha256: str | None
    control_fingerprint: str | None


class ImageGenerationRequestModel(BaseModel):
    prompt: str
    model: str
    area_width: int
    area_height: int
    frame_count: int
    seed: str


class ImageGenerationProgressModel(BaseModel):
    completed_units: int
    total_units: int
    stage: str


class ImageGenerationResultModel(BaseModel):
    media_type: str
    download_url: str
    width: int
    height: int
    frame_count: int
    duration_seconds: float | None
    size_bytes: int
    sha256: str
    created_at: datetime


class ImageGenerationFailureModel(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool
    correlation_id: str


class ImageGenerationJobModel(BaseModel):
    id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    idempotency_key: str
    request: ImageGenerationRequestModel
    conditioning: ImageConditioningModel
    backend: str | None
    backend_revision: str | None
    progress: ImageGenerationProgressModel | None
    conditioning_evidence: ConditioningEvidenceModel | None
    result: ImageGenerationResultModel | None
    failure: ImageGenerationFailureModel | None

    @classmethod
    def from_domain(cls, job: GenerationJob) -> ImageGenerationJobModel:
        conditioning = job.request.image_conditioning
        if conditioning is None or job.idempotency_key is None:
            raise ValueError("image generation response requires conditioning and idempotency")
        prefix = (
            f"/api/v2/projects/{quote(conditioning.project_id, safe='')}/film/shots/"
            f"{quote(conditioning.shot_id, safe='')}/generations/{quote(job.id, safe='')}"
        )
        progress = (
            None
            if job.progress is None
            else ImageGenerationProgressModel(
                completed_units=job.progress.completed_units,
                total_units=job.progress.total_units,
                stage=job.progress.stage,
            )
        )
        evidence = (
            None
            if job.conditioning_evidence is None
            else ConditioningEvidenceModel(
                source_sha256=job.conditioning_evidence.source_sha256,
                derivative_sha256=job.conditioning_evidence.derivative_sha256,
                derivative_width=job.conditioning_evidence.derivative_width,
                derivative_height=job.conditioning_evidence.derivative_height,
                reference_source_sha256=job.conditioning_evidence.reference_source_sha256,
                reference_derivative_sha256=(job.conditioning_evidence.reference_derivative_sha256),
                control_fingerprint=job.conditioning_evidence.control_fingerprint,
            )
        )
        result = (
            None
            if job.result is None
            else ImageGenerationResultModel(
                media_type=job.result.media_type,
                download_url=f"{prefix}/output",
                width=job.result.resolution.width,
                height=job.result.resolution.height,
                frame_count=job.result.frame_count,
                duration_seconds=job.result.duration_seconds,
                size_bytes=job.result.size_bytes,
                sha256=job.result.sha256,
                created_at=job.result.created_at,
            )
        )
        failure = (
            None
            if job.failure is None
            else ImageGenerationFailureModel(
                code=job.failure.code,
                message=job.failure.message,
                retryable=job.failure.retryable,
                correlation_id=job.failure.correlation_id,
            )
        )
        return cls(
            id=job.id,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            idempotency_key=job.idempotency_key,
            request=ImageGenerationRequestModel(
                prompt=job.request.prompt,
                model=job.request.model,
                area_width=job.request.width,
                area_height=job.request.height,
                frame_count=job.request.frame_count,
                seed=str(job.request.seed),
            ),
            conditioning=ImageConditioningModel(
                project_id=conditioning.project_id,
                shot_id=conditioning.shot_id,
                shot_version=conditioning.shot_version,
                composition_id=conditioning.composition_id,
                composition_revision=conditioning.composition_revision,
                composition_fingerprint=conditioning.composition_fingerprint,
                source_asset_id=conditioning.source_asset_id,
                source_asset_version=conditioning.source_asset_version,
                source_asset_sha256=conditioning.source_asset_sha256,
                source_width=conditioning.source_width,
                source_height=conditioning.source_height,
                manifest_fingerprint=conditioning.manifest_fingerprint,
                reference_video=(
                    None
                    if conditioning.reference_video is None
                    else ReferenceVideoConditioningModel(
                        guidance_id=conditioning.reference_video.guidance_id,
                        guidance_revision=conditioning.reference_video.guidance_revision,
                        guidance_fingerprint=conditioning.reference_video.guidance_fingerprint,
                        purpose=conditioning.reference_video.purpose,
                        source_asset_id=conditioning.reference_video.source_asset_id,
                        source_asset_version=conditioning.reference_video.source_asset_version,
                        source_asset_sha256=conditioning.reference_video.source_asset_sha256,
                        trim_start_ms=conditioning.reference_video.trim_start_ms,
                        trim_end_ms=conditioning.reference_video.trim_end_ms,
                        operation=conditioning.reference_video.operation.value,
                        preserve_environment=(conditioning.reference_video.preserve_environment),
                        constraint_plan_fingerprint=(
                            conditioning.reference_video.constraint_plan_fingerprint
                        ),
                    )
                ),
            ),
            backend=job.backend,
            backend_revision=job.model_revision,
            progress=progress,
            conditioning_evidence=evidence,
            result=result,
            failure=failure,
        )
