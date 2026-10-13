"""The canonical immutable generation job lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from video_app.domain.models import (
    ConditioningEvidence,
    Failure,
    GenerationRequest,
    GenerationResult,
    Progress,
    _require_non_empty,
    _require_utc_aware,
)


class InvalidTransitionError(RuntimeError):
    """Raised when code attempts a forbidden job transition."""


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}


ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class GenerationJob:
    """A valid snapshot of one generation job."""

    id: str
    request: GenerationRequest
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    backend: str | None = None
    model_revision: str | None = None
    progress: Progress | None = None
    result: GenerationResult | None = None
    failure: Failure | None = None
    cancellation_requested_at: datetime | None = None
    idempotency_key: str | None = None
    conditioning_evidence: ConditioningEvidence | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "job id")
        _require_utc_aware(self.created_at, "created_at")
        _require_utc_aware(self.updated_at, "updated_at")
        for field, value in (
            ("started_at", self.started_at),
            ("completed_at", self.completed_at),
            ("cancellation_requested_at", self.cancellation_requested_at),
        ):
            if value is not None:
                _require_utc_aware(value, field)
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at cannot precede created_at")
        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completed_at cannot precede created_at")
        for field, value in (
            ("started_at", self.started_at),
            ("completed_at", self.completed_at),
            ("cancellation_requested_at", self.cancellation_requested_at),
        ):
            if value is not None and value > self.updated_at:
                raise ValueError(f"{field} cannot follow updated_at")
        if self.idempotency_key is not None:
            _require_non_empty(self.idempotency_key, "idempotency key")
            if len(self.idempotency_key) > 200:
                raise ValueError("idempotency key must contain at most 200 characters")
        self._validate_state_shape()

    def _validate_state_shape(self) -> None:
        if self.status is JobStatus.QUEUED:
            if any(
                value is not None
                for value in (
                    self.started_at,
                    self.completed_at,
                    self.backend,
                    self.model_revision,
                    self.progress,
                    self.result,
                    self.failure,
                    self.conditioning_evidence,
                )
            ):
                raise ValueError("queued job contains execution or terminal data")
        elif self.status is JobStatus.RUNNING:
            if self.started_at is None or not self.backend or not self.model_revision:
                raise ValueError("running job requires execution identity and start time")
            if self.completed_at is not None or self.result is not None or self.failure is not None:
                raise ValueError("running job contains terminal data")
            if self.conditioning_evidence is not None:
                raise ValueError("running job cannot contain conditioning evidence")
        elif self.status is JobStatus.SUCCEEDED:
            result = self.result
            if (
                self.started_at is None
                or not self.backend
                or not self.model_revision
                or self.completed_at is None
                or result is None
                or self.failure is not None
            ):
                raise ValueError(
                    "succeeded job requires execution identity, result, and completion"
                )
            if (
                result.resolution != self.request.resolution
                and self.request.image_conditioning is None
            ):
                raise ValueError("result dimensions and frames must match the request")
            if result.frame_count != self.request.frame_count:
                raise ValueError("result frame count must match the request")
            if self.request.image_conditioning is not None:
                evidence = self.conditioning_evidence
                if evidence is None:
                    raise ValueError("image-conditioned success requires input evidence")
                if evidence.source_sha256 != self.request.image_conditioning.source_asset_sha256:
                    raise ValueError("conditioning evidence must match the frozen source")
                reference = self.request.image_conditioning.reference_video
                if reference is not None:
                    if evidence.reference_source_sha256 != reference.source_asset_sha256:
                        raise ValueError(
                            "reference conditioning evidence must match the frozen source"
                        )
                elif evidence.reference_source_sha256 is not None:
                    raise ValueError("plain image generation cannot contain reference evidence")
            elif self.conditioning_evidence is not None:
                raise ValueError("text-to-video success cannot contain conditioning evidence")
        elif self.status is JobStatus.FAILED:
            failure = self.failure
            if self.completed_at is None or failure is None or self.result is not None:
                raise ValueError("failed job requires only a failure and completion time")
            if failure.job_id != self.id:
                raise ValueError("failure job_id must match the job")
        elif self.status is JobStatus.CANCELLED and (
            self.completed_at is None
            or self.cancellation_requested_at is None
            or self.result is not None
            or self.failure is not None
        ):
            raise ValueError("cancelled job requires cancellation and no terminal payload")

    @classmethod
    def queued(
        cls,
        job_id: str,
        request: GenerationRequest,
        now: datetime,
        *,
        idempotency_key: str | None = None,
    ) -> GenerationJob:
        return cls(
            id=job_id,
            request=request,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            idempotency_key=idempotency_key,
        )

    def _require_transition(self, destination: JobStatus) -> None:
        if destination not in ALLOWED_TRANSITIONS[self.status]:
            raise InvalidTransitionError(f"cannot transition {self.status} to {destination}")

    def _require_current_or_later(self, now: datetime) -> None:
        _require_utc_aware(now, "transition time")
        if now < self.updated_at:
            raise ValueError("transition time cannot precede updated_at")

    def start(self, now: datetime, *, backend: str, model_revision: str) -> GenerationJob:
        self._require_transition(JobStatus.RUNNING)
        self._require_current_or_later(now)
        _require_non_empty(backend, "backend")
        _require_non_empty(model_revision, "model_revision")
        return replace(
            self,
            status=JobStatus.RUNNING,
            updated_at=now,
            started_at=now,
            backend=backend,
            model_revision=model_revision,
        )

    def report_progress(self, now: datetime, progress: Progress) -> GenerationJob:
        if self.status is not JobStatus.RUNNING:
            raise InvalidTransitionError("progress can only be reported for a running job")
        self._require_current_or_later(now)
        return replace(self, updated_at=now, progress=progress)

    def request_cancellation(self, now: datetime) -> GenerationJob:
        if self.status.is_terminal:
            return self
        self._require_current_or_later(now)
        if self.status is JobStatus.QUEUED:
            self._require_transition(JobStatus.CANCELLED)
            return replace(
                self,
                status=JobStatus.CANCELLED,
                updated_at=now,
                completed_at=now,
                cancellation_requested_at=now,
            )
        if self.cancellation_requested_at is not None:
            return self
        return replace(self, updated_at=now, cancellation_requested_at=now)

    def confirm_cancelled(self, now: datetime) -> GenerationJob:
        self._require_transition(JobStatus.CANCELLED)
        self._require_current_or_later(now)
        if self.status is JobStatus.RUNNING and self.cancellation_requested_at is None:
            raise InvalidTransitionError("running cancellation must be requested first")
        return replace(
            self,
            status=JobStatus.CANCELLED,
            updated_at=now,
            completed_at=now,
            progress=None,
        )

    def succeed(
        self,
        now: datetime,
        result: GenerationResult,
        conditioning_evidence: ConditioningEvidence | None = None,
    ) -> GenerationJob:
        self._require_transition(JobStatus.SUCCEEDED)
        self._require_current_or_later(now)
        if self.cancellation_requested_at is not None:
            raise InvalidTransitionError("success cannot win after cancellation was requested")
        return replace(
            self,
            status=JobStatus.SUCCEEDED,
            updated_at=now,
            completed_at=now,
            progress=None,
            result=result,
            conditioning_evidence=conditioning_evidence,
        )

    def fail(self, now: datetime, failure: Failure) -> GenerationJob:
        self._require_transition(JobStatus.FAILED)
        self._require_current_or_later(now)
        if failure.job_id != self.id:
            raise ValueError("failure job_id must match the job")
        return replace(
            self,
            status=JobStatus.FAILED,
            updated_at=now,
            completed_at=now,
            progress=None,
            failure=failure,
        )
