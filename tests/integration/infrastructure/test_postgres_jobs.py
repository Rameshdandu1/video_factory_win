from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
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
    RoughCutItem,
    RoughCutManifest,
    RoughCutSource,
    TimelineRenderItem,
    TimelineRenderManifest,
)
from video_app.infrastructure.database import DatabaseSettings, create_database_engine
from video_app.infrastructure.postgres_jobs import PostgresJobRepository
from video_app.infrastructure.schema import (
    generation_jobs,
    metadata,
    projects,
    timeline_revisions,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
NOW = datetime.now(timezone.utc).replace(microsecond=0)
pytestmark = pytest.mark.integration


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


def _rough_cut_job(job_id: str) -> GenerationJob:
    manifest = RoughCutManifest.create(
        owner_id="owner-rough-cut",
        project_id="project-rough-cut-job-test",
        workspace_fingerprint="a" * 64,
        width=1280,
        height=720,
        fps_numerator=24,
        fps_denominator=1,
        total_duration_ms=900_000,
        required_backend="ffmpeg-rough-cut",
        required_backend_revision="ffmpeg-rough-cut-v1",
        items=(
            RoughCutItem(
                scene_id="scene-one",
                scene_version=1,
                scene_fingerprint="b" * 64,
                scene_position=0,
                shot_id="shot-one",
                shot_version=1,
                shot_fingerprint="c" * 64,
                shot_position=0,
                duration_ms=900_000,
                storyboard=RoughCutSource("image-one", 1, "d" * 64, "uploads/image.png"),
                dialogue=RoughCutSource("audio-one", 1, "e" * 64, "uploads/audio.wav"),
            ),
        ),
    )
    return GenerationJob.queued(
        job_id,
        GenerationRequest(
            prompt="Approved rough cut",
            model="ffmpeg-rough-cut",
            mode=GenerationMode.ROUGH_CUT,
            resolution=Resolution(1280, 720),
            frame_count=21_600,
            seed=0,
            rough_cut=manifest,
        ),
        NOW,
        idempotency_key="rough-cut-request-one",
    )


def _timeline_render_job(job_id: str) -> GenerationJob:
    manifest = TimelineRenderManifest.create(
        owner_id="owner-timeline-render",
        project_id="project-timeline-render-job-test",
        timeline_id="timeline-render-job-test",
        timeline_revision=1,
        timeline_fingerprint="f" * 64,
        width=1280,
        height=720,
        fps_numerator=24,
        fps_denominator=1,
        total_duration_ms=1_000,
        required_backend="ffmpeg-timeline-render",
        required_backend_revision="ffmpeg-timeline-render-v1",
        items=(TimelineRenderItem("title_card", 0, 1_000, 0, text="తెలుగు"),),
        captions=(),
    )
    return GenerationJob.queued(
        job_id,
        GenerationRequest(
            prompt="Approved timeline",
            model="ffmpeg-timeline-render",
            mode=GenerationMode.TIMELINE_RENDER,
            resolution=Resolution(1280, 720),
            frame_count=24,
            seed=0,
            timeline_render=manifest,
        ),
        NOW,
        idempotency_key="timeline-render-request-one",
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
        expires_at: datetime = NOW + timedelta(seconds=300),
    ) -> JobLease:
        lease = await self.repository.claim_next(
            worker_id=worker,
            attempt_id=f"attempt-{worker}",
            token=token,
            backend="fake",
            model_revision="test-revision",
            supported_models=frozenset({"wan21-t2v"}),
            supported_modes=frozenset({GenerationMode.TEXT_TO_VIDEO}),
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

    async def test_rough_cut_manifest_round_trips_and_only_matching_worker_claims(self) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                projects.delete().where(projects.c.id == "project-rough-cut-job-test")
            )
            await connection.execute(
                sa.insert(projects).values(
                    id="project-rough-cut-job-test",
                    owner_id="owner-rough-cut",
                    version=1,
                    state="draft",
                    title="Rough-cut queue test",
                    language="te",
                    mode="long",
                    target_duration_ms=900_000,
                    aspect_ratio="16:9",
                    export_settings={
                        "width": 1280,
                        "height": 720,
                        "fps_numerator": 24,
                        "fps_denominator": 1,
                    },
                    providers={},
                    budget_policy={},
                    preset="telugu_short_film_900",
                    titles_and_credits_within_target=True,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        queued = await self.repository.enqueue(_rough_cut_job("rough-cut-job"))
        stored = await self.repository.get(queued.id)
        self.assertEqual(stored.request.rough_cut, queued.request.rough_cut)
        self.assertEqual(
            await self.repository.claim_next(
                worker_id="wrong-worker",
                attempt_id="wrong-attempt",
                token="wrong-token",
                backend="fake",
                model_revision="test-revision",
                supported_models=frozenset({"ffmpeg-rough-cut"}),
                supported_modes=frozenset({GenerationMode.ROUGH_CUT}),
                now=NOW + timedelta(seconds=1),
                expires_at=NOW + timedelta(seconds=61),
            ),
            None,
        )
        lease = await self.repository.claim_next(
            worker_id="rough-worker",
            attempt_id="rough-attempt",
            token="rough-token",
            backend="ffmpeg-rough-cut",
            model_revision="ffmpeg-rough-cut-v1",
            supported_models=frozenset({"ffmpeg-rough-cut"}),
            supported_modes=frozenset({GenerationMode.ROUGH_CUT}),
            now=NOW + timedelta(seconds=2),
            expires_at=NOW + timedelta(seconds=62),
        )
        self.assertIsNotNone(lease)

    async def test_timeline_render_manifest_round_trips_and_routes_exact_worker(self) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                timeline_revisions.delete().where(
                    timeline_revisions.c.id == "timeline-render-job-test"
                )
            )
            await connection.execute(
                projects.delete().where(projects.c.id == "project-timeline-render-job-test")
            )
            await connection.execute(
                sa.insert(projects).values(
                    id="project-timeline-render-job-test",
                    owner_id="owner-timeline-render",
                    version=1,
                    state="draft",
                    title="Timeline render queue test",
                    language="te",
                    mode="short",
                    target_duration_ms=1_000,
                    aspect_ratio="16:9",
                    export_settings={
                        "width": 1280,
                        "height": 720,
                        "fps_numerator": 24,
                        "fps_denominator": 1,
                    },
                    providers={},
                    budget_policy={},
                    preset="standard",
                    titles_and_credits_within_target=True,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await connection.execute(
                sa.insert(timeline_revisions).values(
                    id="timeline-render-job-test",
                    project_id="project-timeline-render-job-test",
                    owner_id="owner-timeline-render",
                    revision=1,
                    duration_ms=1_000,
                    items=[
                        {
                            "kind": "title_card",
                            "start_ms": 0,
                            "duration_ms": 1_000,
                            "layer": 0,
                            "asset_id": None,
                            "text": "తెలుగు",
                        }
                    ],
                    fingerprint="f" * 64,
                    created_at=NOW,
                    approved_at=NOW,
                )
            )
        queued = await self.repository.enqueue(_timeline_render_job("timeline-render-job"))
        stored = await self.repository.get(queued.id)
        self.assertEqual(stored.request.timeline_render, queued.request.timeline_render)
        wrong = await self.repository.claim_next(
            worker_id="wrong-worker",
            attempt_id="wrong-attempt",
            token="wrong-token",
            backend="fake",
            model_revision="test-revision",
            supported_models=frozenset({"ffmpeg-timeline-render"}),
            supported_modes=frozenset({GenerationMode.TIMELINE_RENDER}),
            now=NOW + timedelta(seconds=1),
            expires_at=NOW + timedelta(seconds=61),
        )
        self.assertIsNone(wrong)
        lease = await self.repository.claim_next(
            worker_id="timeline-worker",
            attempt_id="timeline-attempt",
            token="timeline-token",
            backend="ffmpeg-timeline-render",
            model_revision="ffmpeg-timeline-render-v1",
            supported_models=frozenset({"ffmpeg-timeline-render"}),
            supported_modes=frozenset({GenerationMode.TIMELINE_RENDER}),
            now=NOW + timedelta(seconds=2),
            expires_at=NOW + timedelta(seconds=62),
        )
        self.assertIsNotNone(lease)

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
                stale,
                _result(NOW + timedelta(seconds=2)),
                None,
                NOW + timedelta(seconds=2),
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
                lease,
                _result(NOW + timedelta(seconds=3)),
                None,
                NOW + timedelta(seconds=3),
            )
        cancelled = await self.repository.confirm_cancelled(lease, NOW + timedelta(seconds=3))
        self.assertEqual(cancelled.status, JobStatus.CANCELLED)

    async def test_recovery_ignores_renewed_lease_then_fails_it_after_expiry(self) -> None:
        baseline = datetime.now(timezone.utc)
        await self.repository.enqueue(_job("job-a", created_at=baseline))
        lease = await self._claim(
            now=baseline + timedelta(seconds=1),
            expires_at=baseline + timedelta(seconds=30),
        )
        renewed = await self.repository.heartbeat(
            lease,
            now=baseline + timedelta(seconds=2),
            expires_at=baseline + timedelta(seconds=62),
            progress=None,
        )

        early = await self.repository.recover_expired(
            limit=10,
            now=baseline + timedelta(seconds=31),
            correlation_id="recovery-1",
        )
        self.assertEqual(early, ())
        self.assertEqual((await self.repository.get(renewed.job.id)).status, JobStatus.RUNNING)

        recovered = await self.repository.recover_expired(
            limit=10,
            now=baseline + timedelta(seconds=63),
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
