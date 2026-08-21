"""Leased worker orchestration for one generation job."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from video_app.application.ports import (
    ArtifactStore,
    Clock,
    IdentifierFactory,
    JobLease,
    JobRepository,
    LeaseLostError,
)
from video_app.domain.jobs import GenerationJob
from video_app.domain.models import BackendOutput, ErrorCode, Failure, Progress
from video_app.domain.ports import (
    BackendCancelledError,
    BackendFailureError,
    GenerationBackend,
    GenerationContext,
)

_SAFE_BACKEND_FAILURE_MESSAGES = {
    ErrorCode.UNSUPPORTED_PARAMETERS: "The selected model does not support these settings.",
    ErrorCode.MODEL_UNAVAILABLE: "The configured video model is unavailable.",
    ErrorCode.INSUFFICIENT_RESOURCES: "The worker has insufficient resources for this job.",
    ErrorCode.GENERATION_FAILED: "Video generation failed.",
}


@dataclass(frozen=True, slots=True)
class ProcessNextJob:
    repository: JobRepository
    artifacts: ArtifactStore
    backend: GenerationBackend
    clock: Clock
    identifiers: IdentifierFactory
    worker_id: str
    lease_duration: timedelta
    heartbeat_interval: timedelta

    def __post_init__(self) -> None:
        if not self.worker_id or self.worker_id.isspace():
            raise ValueError("worker_id must not be empty")
        if self.lease_duration.total_seconds() <= 0:
            raise ValueError("lease_duration must be positive")
        if self.heartbeat_interval.total_seconds() <= 0:
            raise ValueError("heartbeat_interval must be positive")
        if self.heartbeat_interval >= self.lease_duration / 3:
            raise ValueError("heartbeat_interval must be less than one third of lease_duration")

    async def _claim(self) -> JobLease | None:
        now = self.clock.now()
        return await self.repository.claim_next(
            worker_id=self.worker_id,
            attempt_id=self.identifiers.new_attempt_id(),
            token=self.identifiers.new_lease_token(),
            backend=self.backend.name,
            model_revision=self.backend.revision,
            now=now,
            expires_at=now + self.lease_duration,
        )

    async def _heartbeat(self, lease: JobLease, progress: Progress | None) -> JobLease:
        now = self.clock.now()
        return await self.repository.heartbeat(
            lease,
            now=now,
            expires_at=now + self.lease_duration,
            progress=progress,
        )

    def _failure(
        self,
        lease: JobLease,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = True,
    ) -> Failure:
        return Failure(
            code=code,
            message=message,
            retryable=retryable,
            job_id=lease.job.id,
            correlation_id=self.identifiers.new_correlation_id(),
        )

    async def __call__(self) -> GenerationJob | None:
        lease = await self._claim()
        if lease is None:
            return None
        active_lease = lease
        lease_lock = asyncio.Lock()
        stop_heartbeat = asyncio.Event()

        async def report_progress(progress: Progress) -> None:
            nonlocal active_lease
            async with lease_lock:
                active_lease = await self._heartbeat(active_lease, progress)

        async def is_cancelled() -> bool:
            async with lease_lock:
                lease_snapshot = active_lease
            return await self.repository.is_cancellation_requested(lease_snapshot)

        async def heartbeat_loop() -> None:
            nonlocal active_lease
            timeout = self.heartbeat_interval.total_seconds()
            while True:
                try:
                    await asyncio.wait_for(stop_heartbeat.wait(), timeout=timeout)
                    return
                except asyncio.TimeoutError:
                    async with lease_lock:
                        active_lease = await self._heartbeat(active_lease, None)

        context = GenerationContext(lease.job.id, report_progress, is_cancelled)
        generation_task = asyncio.create_task(self.backend.generate(lease.job.request, context))
        heartbeat_task = asyncio.create_task(heartbeat_loop())
        output: BackendOutput | None = None
        try:
            done, _ = await asyncio.wait(
                {generation_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                heartbeat_error = heartbeat_task.exception()
                if heartbeat_error is not None:
                    if generation_task.done() and not generation_task.cancelled():
                        generation_error = generation_task.exception()
                        if generation_error is None:
                            candidate = generation_task.result()
                            await self.artifacts.discard_candidate(candidate)
                    else:
                        generation_task.cancel()
                        await asyncio.gather(generation_task, return_exceptions=True)
                    raise heartbeat_error
                raise RuntimeError("heartbeat stopped before generation completed")
            output = generation_task.result()
        except BackendCancelledError:
            return await self.repository.confirm_cancelled(active_lease, self.clock.now())
        except BackendFailureError as error:
            failure = self._failure(
                active_lease,
                error.code,
                _SAFE_BACKEND_FAILURE_MESSAGES.get(error.code, "Video generation failed."),
                retryable=error.retryable,
            )
            return await self.repository.fail(active_lease, failure, self.clock.now())
        except LeaseLostError:
            raise
        except Exception:
            failure = self._failure(
                active_lease,
                ErrorCode.GENERATION_FAILED,
                "Video generation failed.",
            )
            return await self.repository.fail(active_lease, failure, self.clock.now())
        finally:
            stop_heartbeat.set()
            if not heartbeat_task.done():
                try:
                    await heartbeat_task
                except LeaseLostError:
                    if output is not None:
                        await self.artifacts.discard_candidate(output)
                    raise
            if not generation_task.done():
                generation_task.cancel()
                await asyncio.gather(generation_task, return_exceptions=True)

        if output is None:
            raise RuntimeError("generation completed without an output")

        try:
            result = await self.artifacts.store(lease.job.id, output, self.clock.now())
        except Exception:
            await self.artifacts.discard_candidate(output)
            failure = self._failure(
                active_lease,
                ErrorCode.OUTPUT_WRITE_FAILED,
                "Generated video could not be stored.",
            )
            return await self.repository.fail(active_lease, failure, self.clock.now())

        try:
            return await self.repository.succeed(active_lease, result, self.clock.now())
        except LeaseLostError:
            await self.artifacts.delete(result.storage_key)
            raise
