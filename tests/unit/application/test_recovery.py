from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

from video_app.application.recovery import RecoverExpiredLeases
from video_app.domain.jobs import GenerationJob
from video_app.domain.models import DomainValidationError

NOW = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FixedClock:
    def now(self) -> datetime:
        return NOW


class FixedIdentifiers:
    def new_correlation_id(self) -> str:
        return "correlation-1"


class RecordingRecoveryRepository:
    def __init__(self) -> None:
        self.call: tuple[int, datetime, str] | None = None

    async def recover_expired(
        self,
        *,
        limit: int,
        now: datetime,
        correlation_id: str,
    ) -> tuple[GenerationJob, ...]:
        self.call = (limit, now, correlation_id)
        return ()


class RecoverExpiredLeasesTests(unittest.IsolatedAsyncioTestCase):
    async def test_supplies_bounded_limit_time_and_correlation_id(self) -> None:
        repository = RecordingRecoveryRepository()
        recover = RecoverExpiredLeases(repository, FixedClock(), FixedIdentifiers())

        result = await recover(limit=25)

        self.assertEqual(result, ())
        self.assertEqual(repository.call, (25, NOW, "correlation-1"))

    async def test_rejects_invalid_limit_without_calling_repository(self) -> None:
        repository = RecordingRecoveryRepository()
        recover = RecoverExpiredLeases(repository, FixedClock(), FixedIdentifiers())

        with self.assertRaises(DomainValidationError):
            await recover(limit=0)
        self.assertIsNone(repository.call)


if __name__ == "__main__":
    unittest.main()
