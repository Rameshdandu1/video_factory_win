"""Create the authoritative generation jobs table.

Revision ID: 20260821_0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_jobs",
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
    op.create_index(
        "ix_generation_jobs_claim",
        "generation_jobs",
        ["created_at", "id"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "ix_generation_jobs_list",
        "generation_jobs",
        ["created_at", "id"],
    )
    op.create_index(
        "ix_generation_jobs_expired_lease",
        "generation_jobs",
        ["lease_expires_at"],
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
