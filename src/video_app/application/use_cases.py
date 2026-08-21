"""User-facing application use cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from video_app.application.ports import (
    ArtifactReader,
    Clock,
    IdentifierFactory,
    JobPage,
    JobRepository,
    RepositoryHealth,
    SeedSource,
)
from video_app.domain.jobs import GenerationJob, JobStatus
from video_app.domain.models import (
    DomainValidationError,
    GenerationRequestDraft,
    GenerationResult,
    ModelCapability,
    normalize_request,
)
from video_app.domain.ports import CapabilityProvider


class UnsupportedModelError(DomainValidationError):
    """Raised when a logical model is unknown or disabled."""


class UnsupportedParametersError(DomainValidationError):
    """Raised when settings are outside an enabled model capability."""


class OutputNotFoundError(LookupError):
    """Raised when a job has no readable successful output."""


class ServiceUnavailableError(RuntimeError):
    """Raised when a required application dependency is unhealthy."""


@dataclass(frozen=True, slots=True)
class JobOutput:
    job_id: str
    metadata: GenerationResult
    path: Path


def _capability_for(provider: CapabilityProvider, model_id: str) -> ModelCapability:
    matches = tuple(item for item in provider.capabilities() if item.model_id == model_id)
    if len(matches) != 1 or not matches[0].enabled:
        raise UnsupportedModelError("model is unsupported or disabled")
    return matches[0]


@dataclass(frozen=True, slots=True)
class SubmitJob:
    repository: JobRepository
    capabilities: CapabilityProvider
    clock: Clock
    identifiers: IdentifierFactory
    seeds: SeedSource

    async def __call__(self, draft: GenerationRequestDraft) -> GenerationJob:
        capability = _capability_for(self.capabilities, draft.model)
        try:
            request = normalize_request(draft, capability, self.seeds.new_seed)
        except DomainValidationError as error:
            raise UnsupportedParametersError("generation settings are unsupported") from error
        job = GenerationJob.queued(self.identifiers.new_job_id(), request, self.clock.now())
        return await self.repository.enqueue(job)


@dataclass(frozen=True, slots=True)
class GetJob:
    repository: JobRepository

    async def __call__(self, job_id: str) -> GenerationJob:
        return await self.repository.get(job_id)


@dataclass(frozen=True, slots=True)
class CancelJob:
    repository: JobRepository
    clock: Clock

    async def __call__(self, job_id: str) -> GenerationJob:
        return await self.repository.request_cancellation(job_id, self.clock.now())


@dataclass(frozen=True, slots=True)
class ListJobs:
    repository: JobRepository

    async def __call__(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        status: JobStatus | None = None,
    ) -> JobPage:
        if not 1 <= limit <= 100:
            raise DomainValidationError("job list limit must be between 1 and 100")
        return await self.repository.list_page(limit=limit, cursor=cursor, status=status)


@dataclass(frozen=True, slots=True)
class ListModels:
    capabilities: CapabilityProvider

    def __call__(self) -> tuple[ModelCapability, ...]:
        return tuple(item for item in self.capabilities.capabilities() if item.enabled)


@dataclass(frozen=True, slots=True)
class GetJobOutput:
    repository: JobRepository
    artifacts: ArtifactReader

    async def __call__(self, job_id: str) -> JobOutput:
        job = await self.repository.get(job_id)
        if job.result is None:
            raise OutputNotFoundError(job_id)
        try:
            path = self.artifacts.resolve_for_read(job.result.storage_key)
        except (FileNotFoundError, ValueError) as error:
            raise OutputNotFoundError(job_id) from error
        return JobOutput(job.id, job.result, path)


@dataclass(frozen=True, slots=True)
class HealthCheck:
    repository: RepositoryHealth

    async def __call__(self) -> None:
        try:
            await self.repository.check_health()
        except Exception as error:
            raise ServiceUnavailableError("application dependencies are unavailable") from error
