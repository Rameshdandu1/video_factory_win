"""Add owner-scoped versioned projects.

Revision ID: 20261012_0002
Revises: 20260821_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_0002"
down_revision: str | None = "20260821_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("state", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("target_duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("aspect_ratio", sa.Text(), nullable=False),
        sa.Column("export_settings", sa.JSON(), nullable=False),
        sa.Column("providers", sa.JSON(), nullable=False),
        sa.Column("budget_policy", sa.JSON(), nullable=False),
        sa.Column("approved_timeline_revision_id", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_projects_version"),
        sa.CheckConstraint(
            "state IN ('draft', 'active', 'paused', 'archived')",
            name="ck_projects_state",
        ),
        sa.CheckConstraint("mode IN ('short', 'long')", name="ck_projects_mode"),
        sa.CheckConstraint(
            "aspect_ratio IN ('9:16', '16:9', '1:1')",
            name="ck_projects_aspect_ratio",
        ),
        sa.CheckConstraint(
            "target_duration_ms BETWEEN 1000 AND 3600000",
            name="ck_projects_duration",
        ),
        sa.UniqueConstraint("owner_id", "id", name="uq_projects_owner_id_id"),
    )
    op.create_index(
        "ix_projects_owner_updated",
        "projects",
        ["owner_id", "updated_at", "id"],
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
