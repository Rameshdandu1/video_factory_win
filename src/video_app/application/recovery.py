"""Application use case for terminally failing expired worker leases."""

from __future__ import annotations

from dataclasses import dataclass

from video_app.application.ports import (
    Clock,
    CorrelationIdentifierFactory,
    ExpiredLeaseRepository,
)
from video_app.domain.jobs import GenerationJob
from video_app.domain.models import DomainValidationError


@dataclass(frozen=True, slots=True)
class RecoverExpiredLeases:
    repository: ExpiredLeaseRepository
    clock: Clock
    identifiers: CorrelationIdentifierFactory

    async def __call__(self, *, limit: int = 20) -> tuple[GenerationJob, ...]:
        if not 1 <= limit <= 100:
            raise DomainValidationError("recovery limit must be between 1 and 100")
        return await self.repository.recover_expired(
            limit=limit,
            now=self.clock.now(),
            correlation_id=self.identifiers.new_correlation_id(),
        )
