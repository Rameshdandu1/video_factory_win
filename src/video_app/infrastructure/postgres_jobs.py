"""PostgreSQL implementation of the durable generation job repository."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from video_app.application.ports import (
    JobLease,
    JobNotFoundError,
    JobPage,
    LeaseLostError,
    QueueFullError,
)
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
from video_app.infrastructure.schema import generation_jobs

_QUEUE_ADVISORY_LOCK = 370_744_949_071
_TERMINAL_LEASE_VALUES: dict[str, Any] = {
    "worker_id": None,
    "attempt_id": None,
    "lease_token": None,
    "heartbeat_at": None,
    "lease_expires_at": None,
    "progress_completed_units": None,
    "progress_total_units": None,
    "progress_stage": None,
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError("database timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _utc(value)


def _request_values(job: GenerationJob) -> dict[str, Any]:
    request = job.request
    return {
        "id": job.id,
        "version": 1,
        "status": job.status.value,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "prompt": request.prompt,
        "model": request.model,
        "mode": request.mode.value,
        "width": request.width,
        "height": request.height,
        "frame_count": request.frame_count,
        "seed": request.seed,
    }


def _row_to_job(row: RowMapping) -> GenerationJob:
    request = GenerationRequest(
        prompt=row["prompt"],
        model=row["model"],
        mode=GenerationMode(row["mode"]),
        resolution=Resolution(row["width"], row["height"]),
        frame_count=row["frame_count"],
        seed=row["seed"],
    )
    progress = None
    if row["progress_completed_units"] is not None:
        progress = Progress(
            completed_units=row["progress_completed_units"],
            total_units=row["progress_total_units"],
            stage=row["progress_stage"],
        )
    result = None
    if row["result_storage_key"] is not None:
        result = GenerationResult(
            storage_key=row["result_storage_key"],
            media_type=row["result_media_type"],
            resolution=Resolution(row["result_width"], row["result_height"]),
            frame_count=row["result_frame_count"],
            duration_seconds=row["result_duration_seconds"],
            size_bytes=row["result_size_bytes"],
            sha256=row["result_sha256"],
            created_at=_utc(row["result_created_at"]),
        )
    failure = None
    if row["failure_code"] is not None:
        failure = Failure(
            code=ErrorCode(row["failure_code"]),
            message=row["failure_message"],
            retryable=row["failure_retryable"],
            job_id=row["id"],
            correlation_id=row["failure_correlation_id"],
        )
    return GenerationJob(
        id=row["id"],
        request=request,
        status=JobStatus(row["status"]),
        created_at=_utc(row["created_at"]),
        updated_at=_utc(row["updated_at"]),
        started_at=_optional_utc(row["started_at"]),
        completed_at=_optional_utc(row["completed_at"]),
        backend=row["backend"],
        model_revision=row["model_revision"],
        progress=progress,
        result=result,
        failure=failure,
        cancellation_requested_at=_optional_utc(row["cancellation_requested_at"]),
    )


def _row_to_lease(row: RowMapping) -> JobLease:
    return JobLease(
        job=_row_to_job(row),
        worker_id=row["worker_id"],
        attempt_id=row["attempt_id"],
        token=row["lease_token"],
        expires_at=_utc(row["lease_expires_at"]),
    )


class PostgresJobRepository:
    """One PostgreSQL-backed implementation of job persistence and queue semantics."""

    def __init__(self, engine: AsyncEngine, *, queue_capacity: int, cursor_secret: bytes) -> None:
        if queue_capacity <= 0:
            raise ValueError("queue_capacity must be positive")
        if len(cursor_secret) < 32:
            raise ValueError("cursor_secret must contain at least 32 bytes")
        self._engine = engine
        self._queue_capacity = queue_capacity
        self._cursor_secret = cursor_secret

    def _encode_cursor(self, created_at: datetime, job_id: str) -> str:
        payload = json.dumps([created_at.isoformat(), job_id], separators=(",", ":")).encode(
            "utf-8"
        )
        signature = hmac.new(self._cursor_secret, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload + signature).decode("ascii").rstrip("=")

    def _decode_cursor(self, cursor: str) -> tuple[datetime, str]:
        try:
            padding = "=" * (-len(cursor) % 4)
            decoded = base64.urlsafe_b64decode(cursor + padding)
            payload, signature = decoded[:-32], decoded[-32:]
            expected = hmac.new(self._cursor_secret, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            created_text, job_id = json.loads(payload)
            created_at = _utc(datetime.fromisoformat(created_text))
            if not isinstance(job_id, str) or not job_id:
                raise ValueError
            return created_at, job_id
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise DomainValidationError("job list cursor is invalid") from error

    async def _get_on_connection(self, connection: AsyncConnection, job_id: str) -> GenerationJob:
        row = (
            (
                await connection.execute(
                    sa.select(generation_jobs).where(generation_jobs.c.id == job_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise JobNotFoundError(job_id)
        return _row_to_job(row)

    async def enqueue(self, job: GenerationJob) -> GenerationJob:
        if job.status is not JobStatus.QUEUED:
            raise ValueError("only queued jobs can be enqueued")
        async with self._engine.begin() as connection:
            await connection.execute(
                sa.text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": _QUEUE_ADVISORY_LOCK},
            )
            queued_count = await connection.scalar(
                sa.select(sa.func.count())
                .select_from(generation_jobs)
                .where(generation_jobs.c.status == JobStatus.QUEUED.value)
            )
            if queued_count is None or queued_count >= self._queue_capacity:
                raise QueueFullError("generation queue is full")
            await connection.execute(sa.insert(generation_jobs).values(**_request_values(job)))
        return job

    async def get(self, job_id: str) -> GenerationJob:
        async with self._engine.connect() as connection:
            return await self._get_on_connection(connection, job_id)

    async def list_page(
        self,
        *,
        limit: int,
        cursor: str | None,
        status: JobStatus | None,
    ) -> JobPage:
        if not 1 <= limit <= 100:
            raise DomainValidationError("job list limit must be between 1 and 100")
        statement = sa.select(generation_jobs)
        if status is not None:
            statement = statement.where(generation_jobs.c.status == status.value)
        if cursor is not None:
            created_at, job_id = self._decode_cursor(cursor)
            statement = statement.where(
                sa.or_(
                    generation_jobs.c.created_at < created_at,
                    sa.and_(
                        generation_jobs.c.created_at == created_at,
                        generation_jobs.c.id < job_id,
                    ),
                )
            )
        statement = statement.order_by(
            generation_jobs.c.created_at.desc(), generation_jobs.c.id.desc()
        ).limit(limit + 1)
        async with self._engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        items = tuple(_row_to_job(row) for row in rows[:limit])
        next_cursor = None
        if len(rows) > limit and items:
            last = items[-1]
            next_cursor = self._encode_cursor(last.created_at, last.id)
        return JobPage(items=items, next_cursor=next_cursor)

    async def request_cancellation(self, job_id: str, now: datetime) -> GenerationJob:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(generation_jobs)
                        .where(generation_jobs.c.id == job_id)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise JobNotFoundError(job_id)
            current = _row_to_job(row)
            updated = current.request_cancellation(now)
            if updated == current:
                return current
            values: dict[str, Any] = {
                "status": updated.status.value,
                "updated_at": updated.updated_at,
                "completed_at": updated.completed_at,
                "cancellation_requested_at": updated.cancellation_requested_at,
                "version": generation_jobs.c.version + 1,
            }
            if updated.status is JobStatus.CANCELLED:
                values.update(_TERMINAL_LEASE_VALUES)
            result = await connection.execute(
                sa.update(generation_jobs)
                .where(generation_jobs.c.id == job_id)
                .values(**values)
                .returning(generation_jobs)
            )
            return _row_to_job(result.mappings().one())

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
        if expires_at <= now:
            raise ValueError("lease expiry must follow claim time")
        async with self._engine.begin() as connection:
            candidate_id = await connection.scalar(
                sa.select(generation_jobs.c.id)
                .where(
                    generation_jobs.c.status == JobStatus.QUEUED.value,
                    generation_jobs.c.cancellation_requested_at.is_(None),
                )
                .order_by(generation_jobs.c.created_at, generation_jobs.c.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if candidate_id is None:
                return None
            result = await connection.execute(
                sa.update(generation_jobs)
                .where(
                    generation_jobs.c.id == candidate_id,
                    generation_jobs.c.status == JobStatus.QUEUED.value,
                    generation_jobs.c.cancellation_requested_at.is_(None),
                )
                .values(
                    status=JobStatus.RUNNING.value,
                    updated_at=now,
                    started_at=now,
                    backend=backend,
                    model_revision=model_revision,
                    worker_id=worker_id,
                    attempt_id=attempt_id,
                    lease_token=token,
                    heartbeat_at=now,
                    lease_expires_at=expires_at,
                    version=generation_jobs.c.version + 1,
                )
                .returning(generation_jobs)
            )
            row = result.mappings().one_or_none()
            return None if row is None else _row_to_lease(row)

    async def heartbeat(
        self,
        lease: JobLease,
        *,
        now: datetime,
        expires_at: datetime,
        progress: Progress | None,
    ) -> JobLease:
        if expires_at <= now:
            raise ValueError("lease expiry must follow heartbeat time")
        lease_extension = expires_at - now
        database_now = sa.func.clock_timestamp()
        extension_parameter = sa.bindparam("lease_extension", lease_extension, type_=sa.Interval())
        values: dict[str, Any] = {
            "heartbeat_at": database_now,
            "lease_expires_at": database_now + extension_parameter,
            "version": generation_jobs.c.version + 1,
        }
        if progress is not None:
            values.update(
                updated_at=database_now,
                progress_completed_units=progress.completed_units,
                progress_total_units=progress.total_units,
                progress_stage=progress.stage,
            )
        async with self._engine.begin() as connection:
            result = await connection.execute(
                sa.update(generation_jobs)
                .where(
                    generation_jobs.c.id == lease.job.id,
                    generation_jobs.c.status == JobStatus.RUNNING.value,
                    generation_jobs.c.lease_token == lease.token,
                    generation_jobs.c.lease_expires_at > database_now,
                )
                .values(**values)
                .returning(generation_jobs)
            )
            row = result.mappings().one_or_none()
            if row is None:
                raise LeaseLostError("worker lease is no longer active")
            return _row_to_lease(row)

    async def is_cancellation_requested(self, lease: JobLease) -> bool:
        async with self._engine.connect() as connection:
            row = (
                await connection.execute(
                    sa.select(generation_jobs.c.cancellation_requested_at).where(
                        generation_jobs.c.id == lease.job.id,
                        generation_jobs.c.status == JobStatus.RUNNING.value,
                        generation_jobs.c.lease_token == lease.token,
                        generation_jobs.c.lease_expires_at > sa.func.clock_timestamp(),
                    )
                )
            ).one_or_none()
        if row is None:
            raise LeaseLostError("worker lease is no longer active")
        return row[0] is not None

    async def succeed(
        self,
        lease: JobLease,
        result: GenerationResult,
        now: datetime,
    ) -> GenerationJob:
        values = {
            "status": JobStatus.SUCCEEDED.value,
            "updated_at": now,
            "completed_at": now,
            "result_storage_key": result.storage_key,
            "result_media_type": result.media_type,
            "result_width": result.resolution.width,
            "result_height": result.resolution.height,
            "result_frame_count": result.frame_count,
            "result_duration_seconds": result.duration_seconds,
            "result_size_bytes": result.size_bytes,
            "result_sha256": result.sha256,
            "result_created_at": result.created_at,
            "version": generation_jobs.c.version + 1,
            **_TERMINAL_LEASE_VALUES,
        }
        return await self._terminal_update(lease, values, now=now, require_cancellation=False)

    async def fail(
        self,
        lease: JobLease,
        failure: Failure,
        now: datetime,
    ) -> GenerationJob:
        if failure.job_id != lease.job.id:
            raise ValueError("failure job_id must match the leased job")
        values = {
            "status": JobStatus.FAILED.value,
            "updated_at": now,
            "completed_at": now,
            "failure_code": failure.code.value,
            "failure_message": failure.message,
            "failure_retryable": failure.retryable,
            "failure_correlation_id": failure.correlation_id,
            "version": generation_jobs.c.version + 1,
            **_TERMINAL_LEASE_VALUES,
        }
        return await self._terminal_update(lease, values, now=now)

    async def confirm_cancelled(self, lease: JobLease, now: datetime) -> GenerationJob:
        values = {
            "status": JobStatus.CANCELLED.value,
            "updated_at": now,
            "completed_at": now,
            "version": generation_jobs.c.version + 1,
            **_TERMINAL_LEASE_VALUES,
        }
        return await self._terminal_update(lease, values, now=now, require_cancellation=True)

    async def _terminal_update(
        self,
        lease: JobLease,
        values: dict[str, Any],
        *,
        now: datetime,
        require_cancellation: bool | None = None,
    ) -> GenerationJob:
        predicates = [
            generation_jobs.c.id == lease.job.id,
            generation_jobs.c.status == JobStatus.RUNNING.value,
            generation_jobs.c.lease_token == lease.token,
            generation_jobs.c.lease_expires_at > sa.func.clock_timestamp(),
        ]
        if require_cancellation is True:
            predicates.append(generation_jobs.c.cancellation_requested_at.is_not(None))
        elif require_cancellation is False:
            predicates.append(generation_jobs.c.cancellation_requested_at.is_(None))
        async with self._engine.begin() as connection:
            result = await connection.execute(
                sa.update(generation_jobs)
                .where(*predicates)
                .values(**values)
                .returning(generation_jobs)
            )
            row = result.mappings().one_or_none()
            if row is None:
                raise LeaseLostError("worker lease is no longer active")
            return _row_to_job(row)

    async def recover_expired(
        self,
        *,
        limit: int,
        now: datetime,
        correlation_id: str,
    ) -> tuple[GenerationJob, ...]:
        if not 1 <= limit <= 100:
            raise DomainValidationError("recovery limit must be between 1 and 100")
        recovered: list[GenerationJob] = []
        async with self._engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(generation_jobs)
                        .where(
                            generation_jobs.c.status == JobStatus.RUNNING.value,
                            generation_jobs.c.lease_expires_at <= now,
                        )
                        .order_by(generation_jobs.c.lease_expires_at, generation_jobs.c.id)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                failure = Failure(
                    code=ErrorCode.GENERATION_FAILED,
                    message="Generation worker stopped before completing the job.",
                    retryable=True,
                    job_id=row["id"],
                    correlation_id=correlation_id,
                )
                result = await connection.execute(
                    sa.update(generation_jobs)
                    .where(
                        generation_jobs.c.id == row["id"],
                        generation_jobs.c.status == JobStatus.RUNNING.value,
                        generation_jobs.c.lease_token == row["lease_token"],
                        generation_jobs.c.lease_expires_at == row["lease_expires_at"],
                        generation_jobs.c.lease_expires_at <= now,
                    )
                    .values(
                        status=JobStatus.FAILED.value,
                        updated_at=now,
                        completed_at=now,
                        failure_code=failure.code.value,
                        failure_message=failure.message,
                        failure_retryable=failure.retryable,
                        failure_correlation_id=failure.correlation_id,
                        version=generation_jobs.c.version + 1,
                        **_TERMINAL_LEASE_VALUES,
                    )
                    .returning(generation_jobs)
                )
                updated = result.mappings().one_or_none()
                if updated is not None:
                    recovered.append(_row_to_job(updated))
        return tuple(recovered)
