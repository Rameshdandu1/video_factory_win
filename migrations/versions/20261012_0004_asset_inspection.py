"""Add versioned measured asset metadata.

Revision ID: 20261012_0004
Revises: 20261012_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_0004"
down_revision: str | None = "20261012_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("metadata", sa.JSON()))
    op.add_column("media_assets", sa.Column("inspector_revision", sa.Text()))
    op.add_column("media_assets", sa.Column("inspected_at", sa.DateTime(timezone=True)))
    op.drop_constraint("ck_media_assets_version", "media_assets", type_="check")
    op.drop_constraint("ck_media_assets_state", "media_assets", type_="check")
    op.create_check_constraint("ck_media_assets_version", "media_assets", "version >= 1")
    op.create_check_constraint(
        "ck_media_assets_state", "media_assets", "state IN ('ready', 'inspected')"
    )
    op.create_check_constraint(
        "ck_media_assets_inspection",
        "media_assets",
        "(state = 'ready' AND metadata IS NULL AND "
        "inspector_revision IS NULL AND inspected_at IS NULL) OR "
        "(state = 'inspected' AND metadata IS NOT NULL AND "
        "inspector_revision IS NOT NULL AND inspected_at IS NOT NULL)",
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
