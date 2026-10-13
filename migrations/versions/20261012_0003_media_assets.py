"""Add immutable project media assets.

Revision ID: 20261012_0003
Revises: 20261012_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_0003"
down_revision: str | None = "20261012_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="ready"),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False, unique=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("rights", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.CheckConstraint("version = 1", name="ck_media_assets_version"),
        sa.CheckConstraint("kind IN ('image', 'audio', 'video')", name="ck_media_assets_kind"),
        sa.CheckConstraint("state = 'ready'", name="ck_media_assets_state"),
        sa.CheckConstraint("size_bytes > 0", name="ck_media_assets_size"),
        sa.CheckConstraint("char_length(sha256) = 64", name="ck_media_assets_sha256"),
        sa.CheckConstraint(
            "rights IN ('owned', 'licensed', 'permissioned', 'public_domain')",
            name="ck_media_assets_rights",
        ),
    )
    op.create_index(
        "ix_media_assets_owner_project_created",
        "media_assets",
        ["owner_id", "project_id", "created_at", "id"],
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
