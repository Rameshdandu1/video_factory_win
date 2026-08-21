from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from video_app.domain.jobs import (
    ALLOWED_TRANSITIONS,
    GenerationJob,
    InvalidTransitionError,
    JobStatus,
)
from video_app.domain.models import (
    ErrorCode,
    Failure,
    GenerationRequest,
    GenerationResult,
    Progress,
    Resolution,
)

NOW = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(minutes=1)
REQUEST = GenerationRequest("prompt", "wan21-t2v", Resolution(832, 480), 81, 42)
RESULT = GenerationResult(
    storage_key="job/output.mp4",
    media_type="video/mp4",
    resolution=Resolution(832, 480),
    frame_count=81,
    duration_seconds=5.0,
    size_bytes=100,
    sha256="a" * 64,
    created_at=LATER,
)
FAILURE = Failure(ErrorCode.GENERATION_FAILED, "Generation failed.", True, "job-1", "c-1")


class JobLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.queued = GenerationJob.queued("job-1", REQUEST, NOW)

    def test_happy_path(self) -> None:
        running = self.queued.start(LATER, backend="fake", model_revision="fake-v1")
        running = running.report_progress(LATER, Progress(1, 2, "generating"))
        succeeded = running.succeed(LATER, RESULT)

        self.assertEqual(succeeded.status, JobStatus.SUCCEEDED)
        self.assertEqual(succeeded.result, RESULT)
        self.assertIsNone(succeeded.progress)

    def test_queued_cancellation_is_immediate_and_idempotent(self) -> None:
        cancelled = self.queued.request_cancellation(LATER)

        self.assertEqual(cancelled.status, JobStatus.CANCELLED)
        self.assertIs(cancelled.request_cancellation(LATER), cancelled)

    def test_running_cancellation_requires_confirmation(self) -> None:
        running = self.queued.start(LATER, backend="fake", model_revision="fake-v1")
        requested = running.request_cancellation(LATER)

        self.assertEqual(requested.status, JobStatus.RUNNING)
        self.assertEqual(requested.cancellation_requested_at, LATER)
        self.assertEqual(requested.confirm_cancelled(LATER).status, JobStatus.CANCELLED)

    def test_success_cannot_win_after_cancellation_request(self) -> None:
        running = self.queued.start(LATER, backend="fake", model_revision="fake-v1")
        requested = running.request_cancellation(LATER)

        with self.assertRaises(InvalidTransitionError):
            requested.succeed(LATER, RESULT)

    def test_failure_is_allowed_from_queued_and_running(self) -> None:
        self.assertEqual(self.queued.fail(LATER, FAILURE).status, JobStatus.FAILED)
        running = self.queued.start(LATER, backend="fake", model_revision="fake-v1")
        self.assertEqual(running.fail(LATER, FAILURE).status, JobStatus.FAILED)

    def test_terminal_states_reject_every_transition(self) -> None:
        running = self.queued.start(LATER, backend="fake", model_revision="fake-v1")
        terminal_jobs = (
            running.succeed(LATER, RESULT),
            running.fail(LATER, FAILURE),
            self.queued.request_cancellation(LATER),
        )
        for job in terminal_jobs:
            with self.subTest(status=job.status):
                with self.assertRaises(InvalidTransitionError):
                    job.start(LATER, backend="fake", model_revision="fake-v1")
                with self.assertRaises(InvalidTransitionError):
                    job.fail(LATER, FAILURE)

    def test_transition_table_exactly_matches_contract(self) -> None:
        self.assertEqual(
            ALLOWED_TRANSITIONS,
            {
                JobStatus.QUEUED: frozenset(
                    {JobStatus.RUNNING, JobStatus.FAILED, JobStatus.CANCELLED}
                ),
                JobStatus.RUNNING: frozenset(
                    {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
                ),
                JobStatus.SUCCEEDED: frozenset(),
                JobStatus.FAILED: frozenset(),
                JobStatus.CANCELLED: frozenset(),
            },
        )


if __name__ == "__main__":
    unittest.main()
