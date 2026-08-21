"""User-facing application use cases."""

from __future__ import annotations

from dataclasses import dataclass

from video_app.application.ports import (
    Clock,
    IdentifierFactory,
    JobPage,
    JobRepository,
    SeedSource,
)
from video_app.domain.jobs import GenerationJob, JobStatus
from video_app.domain.models import (
    DomainValidationError,
    GenerationRequestDraft,
    ModelCapability,
    normalize_request,
)
from video_app.domain.ports import GenerationBackend


def _capability_for(backend: GenerationBackend, model_id: str) -> ModelCapability:
    matches = tuple(item for item in backend.capabilities() if item.model_id == model_id)
    if len(matches) != 1:
        raise DomainValidationError("model must resolve to exactly one backend capability")
    return matches[0]


@dataclass(frozen=True, slots=True)
class SubmitJob:
    repository: JobRepository
    backend: GenerationBackend
    clock: Clock
    identifiers: IdentifierFactory
    seeds: SeedSource

    async def __call__(self, draft: GenerationRequestDraft) -> GenerationJob:
        request = normalize_request(
            draft,
            _capability_for(self.backend, draft.model),
            self.seeds.new_seed,
        )
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

