"""Infrastructure ports required by application use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from video_app.domain.jobs import GenerationJob, JobStatus
from video_app.domain.models import BackendOutput, Failure, GenerationResult, Progress


class JobNotFoundError(LookupError):
    """Raised when an opaque job ID is not present."""


class QueueFullError(RuntimeError):
    """Raised when bounded queue admission rejects a submission."""


class LeaseLostError(RuntimeError):
    """Raised when a worker no longer owns the claimed job lease."""


@dataclass(frozen=True, slots=True)
class JobLease:
    job: GenerationJob
    worker_id: str
    attempt_id: str
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class JobPage:
    items: tuple[GenerationJob, ...]
    next_cursor: str | None


class JobRepository(Protocol):
    async def enqueue(self, job: GenerationJob) -> GenerationJob: ...

    async def get(self, job_id: str) -> GenerationJob: ...

    async def list_page(
        self,
        *,
        limit: int,
        cursor: str | None,
        status: JobStatus | None,
    ) -> JobPage: ...

    async def request_cancellation(self, job_id: str, now: datetime) -> GenerationJob: ...

    async def claim_next(
        self,
        *,
        worker_id: str,
        attempt_id: str,
        token: str,
        backend: str,
        model_revision: str,
        now: datetime,
        expires_at: datetime,
    ) -> JobLease | None: ...

    async def heartbeat(
        self,
        lease: JobLease,
        *,
        now: datetime,
        expires_at: datetime,
        progress: Progress | None,
    ) -> JobLease: ...

    async def is_cancellation_requested(self, lease: JobLease) -> bool: ...

    async def succeed(
        self,
        lease: JobLease,
        result: GenerationResult,
        now: datetime,
    ) -> GenerationJob: ...

    async def fail(
        self,
        lease: JobLease,
        failure: Failure,
        now: datetime,
    ) -> GenerationJob: ...

    async def confirm_cancelled(self, lease: JobLease, now: datetime) -> GenerationJob: ...


class ExpiredLeaseRepository(Protocol):
    async def recover_expired(
        self,
        *,
        limit: int,
        now: datetime,
        correlation_id: str,
    ) -> tuple[GenerationJob, ...]: ...


class RepositoryHealth(Protocol):
    async def check_health(self) -> None: ...


class ArtifactStore(Protocol):
    async def store(
        self,
        job_id: str,
        output: BackendOutput,
        created_at: datetime,
    ) -> GenerationResult: ...

    async def discard_candidate(self, output: BackendOutput) -> None: ...

    async def delete(self, storage_key: str) -> None: ...


class ArtifactReader(Protocol):
    def resolve_for_read(self, storage_key: str) -> Path: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdentifierFactory(Protocol):
    def new_job_id(self) -> str: ...

    def new_attempt_id(self) -> str: ...

    def new_lease_token(self) -> str: ...

    def new_correlation_id(self) -> str: ...


class CorrelationIdentifierFactory(Protocol):
    def new_correlation_id(self) -> str: ...


class SeedSource(Protocol):
    def new_seed(self) -> int: ...
