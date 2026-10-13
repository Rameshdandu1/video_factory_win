"""Add immutable rough-cut manifests to the canonical job queue.

Revision ID: 20261013_0013
Revises: 20261013_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261013_0013"
down_revision: str | None = "20261013_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("generation_jobs", sa.Column("rough_cut_project_id", sa.Text()))
    op.add_column("generation_jobs", sa.Column("rough_cut_workspace_fingerprint", sa.String(64)))
    op.add_column("generation_jobs", sa.Column("rough_cut_required_backend", sa.Text()))
    op.add_column("generation_jobs", sa.Column("rough_cut_required_backend_revision", sa.Text()))
    op.add_column("generation_jobs", sa.Column("rough_cut_manifest_fingerprint", sa.String(64)))
    op.add_column(
        "generation_jobs",
        sa.Column("rough_cut_manifest", postgresql.JSONB(astext_type=sa.Text())),
    )
    op.create_foreign_key(
        "fk_generation_jobs_rough_cut_project",
        "generation_jobs",
        "projects",
        ["rough_cut_project_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_generation_jobs_rough_cut_manifest",
        "generation_jobs",
        "(mode <> 'rough_cut' AND rough_cut_project_id IS NULL "
        "AND rough_cut_workspace_fingerprint IS NULL AND rough_cut_required_backend IS NULL "
        "AND rough_cut_required_backend_revision IS NULL "
        "AND rough_cut_manifest_fingerprint IS NULL AND rough_cut_manifest IS NULL) OR "
        "(mode = 'rough_cut' AND idempotency_key IS NOT NULL "
        "AND rough_cut_project_id IS NOT NULL "
        "AND char_length(rough_cut_workspace_fingerprint) = 64 "
        "AND rough_cut_required_backend IS NOT NULL "
        "AND rough_cut_required_backend_revision IS NOT NULL "
        "AND char_length(rough_cut_manifest_fingerprint) = 64 "
        "AND rough_cut_manifest IS NOT NULL)",
    )
    op.create_index(
        "uq_generation_jobs_rough_cut_idempotency",
        "generation_jobs",
        ["rough_cut_project_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("rough_cut_project_id IS NOT NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration: restore from backup instead of downgrading")
