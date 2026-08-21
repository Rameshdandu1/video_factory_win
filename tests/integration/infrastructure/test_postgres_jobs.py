from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncEngine

from video_app.application.ports import JobLease, LeaseLostError, QueueFullError
from video_app.domain.jobs import GenerationJob, JobStatus
from video_app.domain.models import (
    DomainValidationError,
    ErrorCode,
    Failure,
    GenerationMode,
    GenerationRequest,
    GenerationResult,
    Progress,
    Resolution,
)
from video_app.infrastructure.database import DatabaseSettings, create_database_engine
from video_app.infrastructure.postgres_jobs import PostgresJobRepository
from video_app.infrastructure.schema import generation_jobs, metadata

DATABASE_URL = os.environ.get("DATABASE_URL")
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _job(job_id: str, *, created_at: datetime = NOW) -> GenerationJob:
    return GenerationJob.queued(
        job_id,
        GenerationRequest(
            prompt=f"private prompt for {job_id}",
            model="wan21-t2v",
            mode=GenerationMode.TEXT_TO_VIDEO,
            resolution=Resolution(832, 480),
            frame_count=81,
            seed=42,
        ),
        created_at,
    )


def _result(created_at: datetime) -> GenerationResult:
    return GenerationResult(
        storage_key="0123456789abcdef0123456789abcdef.mp4",
        media_type="video/mp4",
        resolution=Resolution(832, 480),
        frame_count=81,
        duration_seconds=5.0,
        size_bytes=1024,
        sha256="a" * 64,
        created_at=created_at,
    )


@unittest.skipUnless(DATABASE_URL, "DATABASE_URL is required for PostgreSQL integration tests")
class PostgresJobRepositoryTests(unittest.IsolatedAsyncioTestCase):
    engine: AsyncEngine
    repository: PostgresJobRepository

    async def asyncSetUp(self) -> None:
        assert DATABASE_URL is not None
        self.engine = create_database_engine(DatabaseSettings(DATABASE_URL))
        async with self.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
            await connection.execute(generation_jobs.delete())
        self.repository = PostgresJobRepository(
            self.engine,
            queue_capacity=10,
            cursor_secret=b"integration-test-cursor-secret-32-bytes",
        )

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _claim(
        self,
        *,
        worker: str = "worker-1",
        token: str = "token-1",
        now: datetime = NOW + timedelta(seconds=1),
        expires_at: datetime = NOW + timedelta(seconds=31),
    ) -> JobLease:
        lease = await self.repository.claim_next(
            worker_id=worker,
            attempt_id=f"attempt-{worker}",
            token=token,
            backend="fake",
            model_revision="test-revision",
            now=now,
            expires_at=expires_at,
        )
        self.assertIsNotNone(lease)
        assert lease is not None
        return lease

    async def test_concurrent_queue_admission_never_exceeds_capacity(self) -> None:
        repository = PostgresJobRepository(
            self.engine,
            queue_capacity=2,
            cursor_secret=b"integration-test-cursor-secret-32-bytes",
        )
        outcomes = await asyncio.gather(
            *(repository.enqueue(_job(f"job-{index}")) for index in range(3)),
            return_exceptions=True,
        )

        self.assertEqual(sum(isinstance(item, GenerationJob) for item in outcomes), 2)
        self.assertEqual(sum(isinstance(item, QueueFullError) for item in outcomes), 1)

    async def test_concurrent_workers_claim_distinct_oldest_jobs(self) -> None:
        await self.repository.enqueue(_job("job-a", created_at=NOW))
        await self.repository.enqueue(_job("job-b", created_at=NOW + timedelta(seconds=1)))
        await self.repository.enqueue(_job("job-c", created_at=NOW + timedelta(seconds=2)))

        leases = await asyncio.gather(
            self._claim(worker="worker-a", token="token-a", now=NOW + timedelta(seconds=2)),
            self._claim(worker="worker-b", token="token-b", now=NOW + timedelta(seconds=2)),
        )

        self.assertEqual({lease.job.id for lease in leases}, {"job-a", "job-b"})

    async def test_stale_token_cannot_heartbeat_or_succeed(self) -> None:
        await self.repository.enqueue(_job("job-a"))
        lease = await self._claim()
        stale = type(lease)(lease.job, lease.worker_id, lease.attempt_id, "stale", lease.expires_at)

        with self.assertRaises(LeaseLostError):
            await self.repository.heartbeat(
                stale,
                now=NOW + timedelta(seconds=2),
                expires_at=NOW + timedelta(seconds=32),
                progress=Progress(1, 10, "generating"),
            )
        with self.assertRaises(LeaseLostError):
            await self.repository.succeed(
                stale, _result(NOW + timedelta(seconds=2)), NOW + timedelta(seconds=2)
            )
        with self.assertRaises(LeaseLostError):
            await self.repository.fail(
                stale,
                Failure(
                    ErrorCode.GENERATION_FAILED,
                    "Generation failed.",
                    True,
                    "job-a",
                    "correlation-1",
                ),
                NOW + timedelta(seconds=2),
            )
        await self.repository.request_cancellation("job-a", NOW + timedelta(seconds=2))
        with self.assertRaises(LeaseLostError):
            await self.repository.confirm_cancelled(stale, NOW + timedelta(seconds=3))

    async def test_cancellation_prevents_success_and_then_confirms_cancelled(self) -> None:
        await self.repository.enqueue(_job("job-a"))
        lease = await self._claim()
        requested = await self.repository.request_cancellation("job-a", NOW + timedelta(seconds=2))
        self.assertIsNotNone(requested.cancellation_requested_at)

        with self.assertRaises(LeaseLostError):
            await self.repository.succeed(
                lease, _result(NOW + timedelta(seconds=3)), NOW + timedelta(seconds=3)
            )
        cancelled = await self.repository.confirm_cancelled(lease, NOW + timedelta(seconds=3))
        self.assertEqual(cancelled.status, JobStatus.CANCELLED)

    async def test_recovery_ignores_renewed_lease_then_fails_it_after_expiry(self) -> None:
        await self.repository.enqueue(_job("job-a"))
        lease = await self._claim(expires_at=NOW + timedelta(seconds=5))
        renewed = await self.repository.heartbeat(
            lease,
            now=NOW + timedelta(seconds=4),
            expires_at=NOW + timedelta(seconds=20),
            progress=None,
        )

        early = await self.repository.recover_expired(
            limit=10,
            now=NOW + timedelta(seconds=6),
            correlation_id="recovery-1",
        )
        self.assertEqual(early, ())
        self.assertEqual((await self.repository.get(renewed.job.id)).status, JobStatus.RUNNING)

        recovered = await self.repository.recover_expired(
            limit=10,
            now=NOW + timedelta(seconds=21),
            correlation_id="recovery-2",
        )
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].status, JobStatus.FAILED)
        failure = recovered[0].failure
        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertEqual(failure.correlation_id, "recovery-2")

    async def test_keyset_pagination_has_no_duplicates_or_omissions(self) -> None:
        for index in range(5):
            await self.repository.enqueue(
                _job(f"job-{index}", created_at=NOW + timedelta(seconds=index))
            )

        first = await self.repository.list_page(limit=2, cursor=None, status=None)
        second = await self.repository.list_page(limit=2, cursor=first.next_cursor, status=None)
        third = await self.repository.list_page(limit=2, cursor=second.next_cursor, status=None)
        ids = [job.id for page in (first, second, third) for job in page.items]

        self.assertEqual(ids, ["job-4", "job-3", "job-2", "job-1", "job-0"])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIsNone(third.next_cursor)

        with self.assertRaises(DomainValidationError):
            await self.repository.list_page(limit=2, cursor="tampered", status=None)


if __name__ == "__main__":
    unittest.main()
