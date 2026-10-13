"""Add immutable approved-timeline manifests to the canonical job queue.

Revision ID: 20261013_0014
Revises: 20261013_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261013_0014"
down_revision: str | None = "20261013_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("generation_jobs", sa.Column("timeline_render_project_id", sa.Text()))
    op.add_column("generation_jobs", sa.Column("timeline_render_timeline_id", sa.Text()))
    op.add_column(
        "generation_jobs", sa.Column("timeline_render_timeline_revision", sa.BigInteger())
    )
    op.add_column(
        "generation_jobs", sa.Column("timeline_render_timeline_fingerprint", sa.String(64))
    )
    op.add_column("generation_jobs", sa.Column("timeline_render_required_backend", sa.Text()))
    op.add_column(
        "generation_jobs", sa.Column("timeline_render_required_backend_revision", sa.Text())
    )
    op.add_column(
        "generation_jobs", sa.Column("timeline_render_manifest_fingerprint", sa.String(64))
    )
    op.add_column(
        "generation_jobs",
        sa.Column("timeline_render_manifest", postgresql.JSONB(astext_type=sa.Text())),
    )
    op.create_foreign_key(
        "fk_generation_jobs_timeline_render_project",
        "generation_jobs",
        "projects",
        ["timeline_render_project_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_generation_jobs_timeline_render_timeline",
        "generation_jobs",
        "timeline_revisions",
        ["timeline_render_timeline_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_generation_jobs_timeline_render_manifest",
        "generation_jobs",
        "(mode <> 'timeline_render' AND timeline_render_project_id IS NULL "
        "AND timeline_render_timeline_id IS NULL "
        "AND timeline_render_timeline_revision IS NULL "
        "AND timeline_render_timeline_fingerprint IS NULL "
        "AND timeline_render_required_backend IS NULL "
        "AND timeline_render_required_backend_revision IS NULL "
        "AND timeline_render_manifest_fingerprint IS NULL "
        "AND timeline_render_manifest IS NULL) OR "
        "(mode = 'timeline_render' AND idempotency_key IS NOT NULL "
        "AND timeline_render_project_id IS NOT NULL "
        "AND timeline_render_timeline_id IS NOT NULL "
        "AND timeline_render_timeline_revision >= 1 "
        "AND char_length(timeline_render_timeline_fingerprint) = 64 "
        "AND timeline_render_required_backend IS NOT NULL "
        "AND timeline_render_required_backend_revision IS NOT NULL "
        "AND char_length(timeline_render_manifest_fingerprint) = 64 "
        "AND timeline_render_manifest IS NOT NULL)",
    )
    op.create_index(
        "uq_generation_jobs_timeline_render_idempotency",
        "generation_jobs",
        ["timeline_render_project_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("timeline_render_project_id IS NOT NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration: restore from backup instead of downgrading")
