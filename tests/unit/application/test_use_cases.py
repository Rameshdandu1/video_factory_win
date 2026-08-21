from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from video_app.application.ports import (
    JobLease,
    JobNotFoundError,
    JobPage,
    LeaseLostError,
)
from video_app.application.use_cases import CancelJob, GetJob, ListJobs, SubmitJob
from video_app.application.worker import ProcessNextJob
from video_app.backends.fake import FakeBackend
from video_app.domain.jobs import GenerationJob, JobStatus
from video_app.domain.models import (
    BackendOutput,
    DomainValidationError,
    ErrorCode,
    Failure,
    GenerationMode,
    GenerationRequest,
    GenerationRequestDraft,
    GenerationResult,
    ModelCapability,
    Progress,
    Resolution,
)
from video_app.domain.ports import BackendFailureError, GenerationContext

NOW = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)
RESOLUTION = Resolution(832, 480)
CAPABILITY = ModelCapability(
    model_id="wan21-t2v",
    display_name="Wan2.1 Text to Video",
    modes=frozenset({GenerationMode.TEXT_TO_VIDEO}),
    resolutions=frozenset({RESOLUTION}),
    frame_counts=frozenset({81}),
)
DRAFT = GenerationRequestDraft("  private prompt  ", "wan21-t2v", 832, 480, 81)


@dataclass
class FixedClock:
    value: datetime = NOW

    def now(self) -> datetime:
        return self.value


class FixedIdentifiers:
    def __init__(self) -> None:
        self.counter = 0

    def _next(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}-{self.counter}"

    def new_job_id(self) -> str:
        return self._next("job")

    def new_attempt_id(self) -> str:
        return self._next("attempt")

    def new_lease_token(self) -> str:
        return self._next("lease")

    def new_correlation_id(self) -> str:
        return self._next("correlation")


class FixedSeeds:
    def new_seed(self) -> int:
        return 42


class MemoryRepository:
    def __init__(self) -> None:
        self.jobs: dict[str, GenerationJob] = {}
        self.active_lease: JobLease | None = None
        self.cancel_on_progress = False
        self.idle_heartbeats = 0
        self.lose_lease_on_idle_heartbeat = False

    async def enqueue(self, job: GenerationJob) -> GenerationJob:
        self.jobs[job.id] = job
        return job

    async def get(self, job_id: str) -> GenerationJob:
        try:
            return self.jobs[job_id]
        except KeyError as error:
            raise JobNotFoundError(job_id) from error

    async def list_page(
        self,
        *,
        limit: int,
        cursor: str | None,
        status: JobStatus | None,
    ) -> JobPage:
        del cursor
        jobs = sorted(self.jobs.values(), key=lambda job: (job.created_at, job.id), reverse=True)
        if status is not None:
            jobs = [job for job in jobs if job.status is status]
        return JobPage(tuple(jobs[:limit]), None)

    async def request_cancellation(self, job_id: str, now: datetime) -> GenerationJob:
        job = await self.get(job_id)
        updated = job.request_cancellation(now)
        self.jobs[job_id] = updated
        return updated

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
    ) -> JobLease | None:
        queued = sorted(
            (job for job in self.jobs.values() if job.status is JobStatus.QUEUED),
            key=lambda job: (job.created_at, job.id),
        )
        if not queued:
            return None
        running = queued[0].start(now, backend=backend, model_revision=model_revision)
        self.jobs[running.id] = running
        self.active_lease = JobLease(running, worker_id, attempt_id, token, expires_at)
        return self.active_lease

    def _owned(self, lease: JobLease) -> GenerationJob:
        if self.active_lease is None or self.active_lease.token != lease.token:
            raise LeaseLostError("lease lost")
        return self.jobs[lease.job.id]

    async def heartbeat(
        self,
        lease: JobLease,
        *,
        now: datetime,
        expires_at: datetime,
        progress: Progress | None,
    ) -> JobLease:
        if progress is None:
            self.idle_heartbeats += 1
            if self.lose_lease_on_idle_heartbeat:
                raise LeaseLostError("lease lost")
        current = self._owned(lease)
        if progress is not None:
            current = current.report_progress(now, progress)
        if self.cancel_on_progress:
            current = current.request_cancellation(now)
        self.jobs[current.id] = current
        self.active_lease = replace(lease, job=current, expires_at=expires_at)
        return self.active_lease

    async def is_cancellation_requested(self, lease: JobLease) -> bool:
        current = self._owned(lease)
        return current.cancellation_requested_at is not None

    async def succeed(
        self,
        lease: JobLease,
        result: GenerationResult,
        now: datetime,
    ) -> GenerationJob:
        current = self._owned(lease)
        completed = current.succeed(now, result)
        self.jobs[current.id] = completed
        return completed

    async def fail(
        self,
        lease: JobLease,
        failure: Failure,
        now: datetime,
    ) -> GenerationJob:
        current = self._owned(lease)
        failed = current.fail(now, failure)
        self.jobs[current.id] = failed
        return failed

    async def confirm_cancelled(self, lease: JobLease, now: datetime) -> GenerationJob:
        current = self._owned(lease)
        cancelled = current.confirm_cancelled(now)
        self.jobs[current.id] = cancelled
        return cancelled


class MemoryArtifacts:
    def __init__(self, *, fail_store: bool = False) -> None:
        self.fail_store = fail_store
        self.keys: set[str] = set()

    async def store(
        self,
        job_id: str,
        output: BackendOutput,
        created_at: datetime,
    ) -> GenerationResult:
        if self.fail_store:
            raise OSError("private storage failure")
        payload = output.temporary_path.read_bytes()
        output.temporary_path.unlink()
        key = f"{job_id}/output.mp4"
        self.keys.add(key)
        return GenerationResult(
            storage_key=key,
            media_type="video/mp4",
            resolution=output.resolution,
            frame_count=output.frame_count,
            duration_seconds=output.duration_seconds,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            created_at=created_at,
        )

    async def discard_candidate(self, output: BackendOutput) -> None:
        output.temporary_path.unlink(missing_ok=True)

    async def delete(self, storage_key: str) -> None:
        self.keys.discard(storage_key)


class BackendFailureBackend:
    name = "wan21"
    revision = "wan21-test-revision"

    def capabilities(self) -> tuple[ModelCapability, ...]:
        return (CAPABILITY,)

    async def generate(
        self,
        request: GenerationRequest,
        context: GenerationContext,
    ) -> BackendOutput:
        del request, context
        try:
            raise RuntimeError("private checkpoint path C:/secret/checkpoint")
        except RuntimeError as error:
            raise BackendFailureError(
                ErrorCode.MODEL_UNAVAILABLE,
                retryable=False,
            ) from error


class ApplicationUseCaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.repository = MemoryRepository()
        self.clock = FixedClock()
        self.identifiers = FixedIdentifiers()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.backend = FakeBackend(
            Path(self.temporary_directory.name).resolve(),
            (CAPABILITY,),
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def submit(self) -> GenerationJob:
        return await SubmitJob(
            self.repository,
            self.backend,
            self.clock,
            self.identifiers,
            FixedSeeds(),
        )(DRAFT)

    async def test_submit_get_list_and_cancel(self) -> None:
        submitted = await self.submit()
        fetched = await GetJob(self.repository)(submitted.id)
        page = await ListJobs(self.repository)(limit=20)
        cancelled = await CancelJob(self.repository, self.clock)(submitted.id)

        self.assertEqual(submitted.request.prompt, "private prompt")
        self.assertEqual(submitted.request.seed, 42)
        self.assertEqual(fetched, submitted)
        self.assertEqual(page.items, (submitted,))
        self.assertEqual(cancelled.status, JobStatus.CANCELLED)

    async def test_list_rejects_invalid_limit(self) -> None:
        with self.assertRaises(DomainValidationError):
            await ListJobs(self.repository)(limit=101)

    async def test_worker_completes_job_through_backend_and_artifact_ports(self) -> None:
        submitted = await self.submit()
        artifacts = MemoryArtifacts()
        processed = await ProcessNextJob(
            self.repository,
            artifacts,
            self.backend,
            self.clock,
            self.identifiers,
            "worker-1",
            timedelta(seconds=30),
            timedelta(seconds=5),
        )()

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.id, submitted.id)
        self.assertEqual(processed.status, JobStatus.SUCCEEDED)
        self.assertIsNotNone(processed.result)
        self.assertEqual(len(artifacts.keys), 1)

    async def test_worker_honors_running_cancellation(self) -> None:
        await self.submit()
        self.repository.cancel_on_progress = True
        processed = await ProcessNextJob(
            self.repository,
            MemoryArtifacts(),
            self.backend,
            self.clock,
            self.identifiers,
            "worker-1",
            timedelta(seconds=30),
            timedelta(seconds=5),
        )()

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, JobStatus.CANCELLED)
        self.assertEqual(list(Path(self.temporary_directory.name).iterdir()), [])

    async def test_storage_failure_is_safely_translated_and_candidate_is_removed(self) -> None:
        await self.submit()
        processed = await ProcessNextJob(
            self.repository,
            MemoryArtifacts(fail_store=True),
            self.backend,
            self.clock,
            self.identifiers,
            "worker-1",
            timedelta(seconds=30),
            timedelta(seconds=5),
        )()

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, JobStatus.FAILED)
        self.assertIsNotNone(processed.failure)
        assert processed.failure is not None
        self.assertEqual(processed.failure.code.value, "OUTPUT_WRITE_FAILED")
        self.assertNotIn("private", processed.failure.message)
        self.assertEqual(list(Path(self.temporary_directory.name).iterdir()), [])

    async def test_backend_failure_uses_safe_code_and_retryability_without_leaking_cause(
        self,
    ) -> None:
        await self.submit()
        processed = await ProcessNextJob(
            self.repository,
            MemoryArtifacts(),
            BackendFailureBackend(),
            self.clock,
            self.identifiers,
            "worker-1",
            timedelta(seconds=30),
            timedelta(seconds=5),
        )()

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, JobStatus.FAILED)
        self.assertIsNotNone(processed.failure)
        assert processed.failure is not None
        self.assertEqual(processed.failure.code, ErrorCode.MODEL_UNAVAILABLE)
        self.assertFalse(processed.failure.retryable)
        self.assertTrue(processed.failure.message.strip())
        self.assertNotIn("private checkpoint", processed.failure.message)
        self.assertNotIn("C:/secret", processed.failure.message)

    async def test_worker_renews_lease_without_waiting_for_backend_progress(self) -> None:
        await self.submit()
        slow_backend = FakeBackend(
            Path(self.temporary_directory.name).resolve(),
            (CAPABILITY,),
            steps=1,
            step_delay_seconds=0.04,
        )
        processed = await ProcessNextJob(
            self.repository,
            MemoryArtifacts(),
            slow_backend,
            self.clock,
            self.identifiers,
            "worker-1",
            timedelta(seconds=0.09),
            timedelta(seconds=0.02),
        )()

        self.assertIsNotNone(processed)
        self.assertGreaterEqual(self.repository.idle_heartbeats, 1)

    async def test_lease_loss_stops_generation_and_prevents_terminal_publish(self) -> None:
        submitted = await self.submit()
        self.repository.lose_lease_on_idle_heartbeat = True
        slow_backend = FakeBackend(
            Path(self.temporary_directory.name).resolve(),
            (CAPABILITY,),
            steps=1,
            step_delay_seconds=0.04,
        )

        with self.assertRaises(LeaseLostError):
            await ProcessNextJob(
                self.repository,
                MemoryArtifacts(),
                slow_backend,
                self.clock,
                self.identifiers,
                "worker-1",
                timedelta(seconds=0.09),
                timedelta(seconds=0.02),
            )()

        self.assertEqual(self.repository.jobs[submitted.id].status, JobStatus.RUNNING)
        self.assertEqual(list(Path(self.temporary_directory.name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
