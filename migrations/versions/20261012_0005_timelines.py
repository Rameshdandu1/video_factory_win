"""Add immutable timeline revisions and caption segments.

Revision ID: 20261012_0005
Revises: 20261012_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_0005"
down_revision: str | None = "20261012_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "timeline_revisions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.UniqueConstraint("project_id", "revision", name="uq_timeline_project_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_timeline_revision"),
        sa.CheckConstraint("duration_ms BETWEEN 1000 AND 3600000", name="ck_timeline_duration"),
        sa.CheckConstraint("char_length(fingerprint) = 64", name="ck_timeline_fingerprint"),
    )
    op.create_table(
        "caption_segments",
        sa.Column("timeline_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["timeline_id"], ["timeline_revisions.id"]),
        sa.PrimaryKeyConstraint("timeline_id", "position"),
        sa.CheckConstraint("position >= 0", name="ck_caption_position"),
        sa.CheckConstraint("start_ms >= 0 AND end_ms > start_ms", name="ck_caption_timing"),
        sa.CheckConstraint("char_length(text) BETWEEN 1 AND 500", name="ck_caption_text"),
    )
    op.create_index(
        "ix_timeline_owner_project_revision",
        "timeline_revisions",
        ["owner_id", "project_id", "revision"],
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
