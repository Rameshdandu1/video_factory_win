"""Canonical SQLAlchemy metadata for the PostgreSQL job store."""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

generation_jobs = sa.Table(
    "generation_jobs",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.Column("prompt", sa.Text(), nullable=False),
    sa.Column("model", sa.Text(), nullable=False),
    sa.Column("mode", sa.Text(), nullable=False),
    sa.Column("width", sa.Integer(), nullable=False),
    sa.Column("height", sa.Integer(), nullable=False),
    sa.Column("frame_count", sa.Integer(), nullable=False),
    sa.Column("seed", sa.BigInteger(), nullable=False),
    sa.Column("backend", sa.Text()),
    sa.Column("model_revision", sa.Text()),
    sa.Column("progress_completed_units", sa.Integer()),
    sa.Column("progress_total_units", sa.Integer()),
    sa.Column("progress_stage", sa.Text()),
    sa.Column("result_storage_key", sa.Text()),
    sa.Column("result_media_type", sa.Text()),
    sa.Column("result_width", sa.Integer()),
    sa.Column("result_height", sa.Integer()),
    sa.Column("result_frame_count", sa.Integer()),
    sa.Column("result_duration_seconds", sa.Float()),
    sa.Column("result_size_bytes", sa.BigInteger()),
    sa.Column("result_sha256", sa.String(64)),
    sa.Column("result_created_at", sa.DateTime(timezone=True)),
    sa.Column("failure_code", sa.Text()),
    sa.Column("failure_message", sa.Text()),
    sa.Column("failure_retryable", sa.Boolean()),
    sa.Column("failure_correlation_id", sa.Text()),
    sa.Column("cancellation_requested_at", sa.DateTime(timezone=True)),
    sa.Column("worker_id", sa.Text()),
    sa.Column("attempt_id", sa.Text()),
    sa.Column("lease_token", sa.Text()),
    sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
    sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
    sa.CheckConstraint(
        "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
        name="ck_generation_jobs_status",
    ),
    sa.CheckConstraint("version >= 1", name="ck_generation_jobs_version"),
    sa.CheckConstraint(
        "char_length(prompt) BETWEEN 1 AND 2000",
        name="ck_generation_jobs_prompt_length",
    ),
    sa.CheckConstraint(
        "width > 0 AND height > 0 AND frame_count > 0",
        name="ck_generation_jobs_request_dimensions",
    ),
    sa.CheckConstraint(
        "(progress_completed_units IS NULL AND progress_total_units IS NULL "
        "AND progress_stage IS NULL) OR "
        "(progress_completed_units BETWEEN 0 AND progress_total_units "
        "AND progress_total_units > 0 AND char_length(progress_stage) > 0)",
        name="ck_generation_jobs_progress",
    ),
    sa.CheckConstraint(
        "(status = 'running') = (worker_id IS NOT NULL AND attempt_id IS NOT NULL "
        "AND lease_token IS NOT NULL AND heartbeat_at IS NOT NULL "
        "AND lease_expires_at IS NOT NULL)",
        name="ck_generation_jobs_active_lease",
    ),
    sa.CheckConstraint(
        "(status IN ('succeeded', 'failed', 'cancelled')) = (completed_at IS NOT NULL)",
        name="ck_generation_jobs_terminal_completion",
    ),
    sa.CheckConstraint(
        "status <> 'succeeded' OR (result_storage_key IS NOT NULL "
        "AND result_media_type = 'video/mp4' AND result_width > 0 "
        "AND result_height > 0 AND result_frame_count > 0 AND result_size_bytes > 0 "
        "AND char_length(result_sha256) = 64 AND result_created_at IS NOT NULL)",
        name="ck_generation_jobs_success_result",
    ),
    sa.CheckConstraint(
        "status <> 'failed' OR (failure_code IS NOT NULL AND failure_message IS NOT NULL "
        "AND failure_retryable IS NOT NULL AND failure_correlation_id IS NOT NULL)",
        name="ck_generation_jobs_failure",
    ),
    sa.CheckConstraint(
        "status <> 'cancelled' OR cancellation_requested_at IS NOT NULL",
        name="ck_generation_jobs_cancellation",
    ),
)

sa.Index(
    "ix_generation_jobs_claim",
    generation_jobs.c.created_at,
    generation_jobs.c.id,
    postgresql_where=generation_jobs.c.status == "queued",
)
sa.Index(
    "ix_generation_jobs_list",
    generation_jobs.c.created_at,
    generation_jobs.c.id,
)
sa.Index(
    "ix_generation_jobs_expired_lease",
    generation_jobs.c.lease_expires_at,
    postgresql_where=generation_jobs.c.status == "running",
)
