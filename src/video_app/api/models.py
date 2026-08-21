"""Pydantic transport models and explicit domain mappings for Generation Contract v1."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator

from video_app.application.ports import JobPage
from video_app.domain.jobs import GenerationJob, JobStatus
from video_app.domain.models import (
    ErrorCode,
    GenerationMode,
    GenerationRequestDraft,
    ModelCapability,
)


class GenerationRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: GenerationMode
    prompt: str = Field(strict=True)
    model: str = Field(min_length=1, strict=True)
    width: int = Field(gt=0, strict=True)
    height: int = Field(gt=0, strict=True)
    frame_count: int = Field(gt=0, strict=True)
    seed: int | None = Field(default=None, ge=-(2**63), le=2**63 - 1, strict=True)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        if not 1 <= len(value.strip()) <= 2_000:
            raise ValueError("prompt must contain between 1 and 2000 characters")
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if value.isspace():
            raise ValueError("model must not be empty")
        return value

    def to_domain(self) -> GenerationRequestDraft:
        return GenerationRequestDraft(
            mode=self.mode,
            prompt=self.prompt,
            model=self.model,
            width=self.width,
            height=self.height,
            frame_count=self.frame_count,
            seed=self.seed,
        )


class NormalizedRequestModel(BaseModel):
    mode: GenerationMode
    prompt: str
    model: str
    width: int
    height: int
    frame_count: int
    seed: int


class ProgressModel(BaseModel):
    completed_units: int
    total_units: int
    stage: str


class ResultModel(BaseModel):
    media_type: str
    download_url: str
    width: int
    height: int
    frame_count: int
    duration_seconds: float | None
    size_bytes: int
    sha256: str
    created_at: datetime


class FailureModel(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool
    job_id: str
    correlation_id: str


class JobModel(BaseModel):
    id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    request: NormalizedRequestModel
    backend: str | None
    model_revision: str | None
    progress: ProgressModel | None
    result: ResultModel | None
    failure: FailureModel | None

    @classmethod
    def from_domain(cls, job: GenerationJob) -> JobModel:
        request = job.request
        progress = None
        if job.progress is not None:
            progress = ProgressModel(
                completed_units=job.progress.completed_units,
                total_units=job.progress.total_units,
                stage=job.progress.stage,
            )
        result = None
        if job.result is not None:
            result = ResultModel(
                media_type=job.result.media_type,
                download_url=f"/api/v1/jobs/{quote(job.id, safe='')}/output",
                width=job.result.resolution.width,
                height=job.result.resolution.height,
                frame_count=job.result.frame_count,
                duration_seconds=job.result.duration_seconds,
                size_bytes=job.result.size_bytes,
                sha256=job.result.sha256,
                created_at=job.result.created_at,
            )
        failure = None
        if job.failure is not None:
            failure = FailureModel(
                code=job.failure.code,
                message=job.failure.message,
                retryable=job.failure.retryable,
                job_id=job.failure.job_id,
                correlation_id=job.failure.correlation_id,
            )
        return cls(
            id=job.id,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            request=NormalizedRequestModel(
                mode=request.mode,
                prompt=request.prompt,
                model=request.model,
                width=request.width,
                height=request.height,
                frame_count=request.frame_count,
                seed=request.seed,
            ),
            backend=job.backend,
            model_revision=job.model_revision,
            progress=progress,
            result=result,
            failure=failure,
        )


class JobPageModel(BaseModel):
    items: tuple[JobModel, ...]
    next_cursor: str | None

    @classmethod
    def from_domain(cls, page: JobPage) -> JobPageModel:
        return cls(
            items=tuple(JobModel.from_domain(job) for job in page.items),
            next_cursor=page.next_cursor,
        )


class ResolutionModel(BaseModel):
    width: int
    height: int


class ModelCapabilityModel(BaseModel):
    id: str
    display_name: str
    modes: tuple[GenerationMode, ...]
    resolutions: tuple[ResolutionModel, ...]
    frame_counts: tuple[int, ...]
    enabled: bool

    @classmethod
    def from_domain(cls, capability: ModelCapability) -> ModelCapabilityModel:
        return cls(
            id=capability.model_id,
            display_name=capability.display_name,
            modes=tuple(sorted(capability.modes, key=lambda mode: mode.value)),
            resolutions=tuple(
                ResolutionModel(width=item.width, height=item.height)
                for item in sorted(capability.resolutions)
            ),
            frame_counts=tuple(sorted(capability.frame_counts)),
            enabled=capability.enabled,
        )


class ModelListModel(BaseModel):
    items: tuple[ModelCapabilityModel, ...]


class HealthModel(BaseModel):
    status: str


class ApiErrorModel(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool
    correlation_id: str
    job_id: str | None = None
    fields: tuple[str, ...] = ()
