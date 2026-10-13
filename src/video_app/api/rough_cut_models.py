"""Transport models for project-scoped approved rough-cut rendering."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator

from video_app.application.rough_cuts import RoughCutProvider
from video_app.domain.jobs import GenerationJob, JobStatus
from video_app.domain.models import ErrorCode


class RoughCutSubmitModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=200, strict=True)

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        if value.isspace() or "\x00" in value:
            raise ValueError("idempotency_key contains invalid characters")
        return value


class RoughCutProviderModel(BaseModel):
    backend: str
    backend_revision: str
    display_name: str
    enabled: bool
    runtime_state: str
    width: int
    height: int
    fps_numerator: int
    fps_denominator: int
    unavailable_reason: str | None

    @classmethod
    def from_domain(cls, value: RoughCutProvider) -> RoughCutProviderModel:
        return cls(
            backend=value.backend_name,
            backend_revision=value.backend_revision,
            display_name=value.display_name,
            enabled=value.enabled,
            runtime_state=value.runtime_state,
            width=value.width,
            height=value.height,
            fps_numerator=value.fps_numerator,
            fps_denominator=value.fps_denominator,
            unavailable_reason=value.unavailable_reason,
        )


class RoughCutProgressModel(BaseModel):
    completed_units: int
    total_units: int
    stage: str


class RoughCutResultModel(BaseModel):
    media_type: str
    download_url: str
    width: int
    height: int
    frame_count: int
    duration_seconds: float | None
    size_bytes: int
    sha256: str
    created_at: datetime


class RoughCutFailureModel(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool
    correlation_id: str


class RoughCutJobModel(BaseModel):
    id: str
    project_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    idempotency_key: str
    backend: str | None
    backend_revision: str | None
    workspace_fingerprint: str
    manifest_fingerprint: str
    shot_count: int
    duration_ms: int
    width: int
    height: int
    fps_numerator: int
    fps_denominator: int
    progress: RoughCutProgressModel | None
    result: RoughCutResultModel | None
    failure: RoughCutFailureModel | None

    @classmethod
    def from_domain(cls, job: GenerationJob) -> RoughCutJobModel:
        manifest = job.request.rough_cut
        if manifest is None or job.idempotency_key is None:
            raise ValueError("rough-cut response requires a manifest and idempotency")
        prefix = (
            f"/api/v2/projects/{quote(manifest.project_id, safe='')}/film/rough-cuts/"
            f"{quote(job.id, safe='')}"
        )
        return cls(
            id=job.id,
            project_id=manifest.project_id,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            idempotency_key=job.idempotency_key,
            backend=job.backend,
            backend_revision=job.model_revision,
            workspace_fingerprint=manifest.workspace_fingerprint,
            manifest_fingerprint=manifest.manifest_fingerprint,
            shot_count=len(manifest.items),
            duration_ms=manifest.total_duration_ms,
            width=manifest.width,
            height=manifest.height,
            fps_numerator=manifest.fps_numerator,
            fps_denominator=manifest.fps_denominator,
            progress=(
                None
                if job.progress is None
                else RoughCutProgressModel(
                    completed_units=job.progress.completed_units,
                    total_units=job.progress.total_units,
                    stage=job.progress.stage,
                )
            ),
            result=(
                None
                if job.result is None
                else RoughCutResultModel(
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
            ),
            failure=(
                None
                if job.failure is None
                else RoughCutFailureModel(
                    code=job.failure.code,
                    message=job.failure.message,
                    retryable=job.failure.retryable,
                    correlation_id=job.failure.correlation_id,
                )
            ),
        )
