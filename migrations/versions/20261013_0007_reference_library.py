"""Add owner-scoped reusable library entities and immutable versions.

Revision ID: 20261013_0007
Revises: 20261012_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_0007"
down_revision: str | None = "20261012_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_assets",
        sa.Column("scope", sa.Text(), nullable=False, server_default="project"),
    )
    op.alter_column("media_assets", "project_id", existing_type=sa.Text(), nullable=True)
    op.create_check_constraint(
        "ck_media_assets_scope",
        "media_assets",
        "(scope = 'project' AND project_id IS NOT NULL) OR "
        "(scope = 'library' AND project_id IS NULL)",
    )
    op.create_index(
        "ix_media_assets_owner_scope_created",
        "media_assets",
        ["owner_id", "scope", "created_at", "id"],
    )

    op.create_table(
        "library_entities",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("metadata_version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "id", name="uq_library_entities_owner_id_id"),
        sa.CheckConstraint(
            "kind IN ('character', 'location', 'prop', 'shot_reference')",
            name="ck_library_entities_kind",
        ),
        sa.CheckConstraint("metadata_version >= 1", name="ck_library_entities_version"),
        sa.CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 200", name="ck_library_entities_name"
        ),
    )
    op.create_index(
        "ix_library_entities_owner_kind_updated",
        "library_entities",
        ["owner_id", "kind", "updated_at", "id"],
    )

    op.create_table(
        "library_versions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("version_number", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("invariants", sa.Text(), nullable=False),
        sa.Column("state_notes", sa.Text(), nullable=False),
        sa.Column("voice_profile_id", sa.Text()),
        sa.Column("rights_statement", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["owner_id", "entity_id"],
            ["library_entities.owner_id", "library_entities.id"],
            name="fk_library_versions_owner_entity",
        ),
        sa.UniqueConstraint("entity_id", "version_number", name="uq_library_version_number"),
        sa.UniqueConstraint("owner_id", "id", name="uq_library_versions_owner_id_id"),
        sa.CheckConstraint("version_number >= 1", name="ck_library_versions_number"),
        sa.CheckConstraint(
            "kind IN ('identity', 'wardrobe', 'location_view', 'lighting_variant', "
            "'prop_variant', 'prop_state', 'shot_reference')",
            name="ck_library_versions_kind",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'archived')", name="ck_library_versions_status"
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND approved_at IS NULL) OR "
            "(status IN ('approved', 'archived') AND approved_at IS NOT NULL)",
            name="ck_library_versions_approval",
        ),
        sa.CheckConstraint("char_length(fingerprint) = 64", name="ck_library_versions_fingerprint"),
    )
    op.create_index(
        "ix_library_versions_owner_entity_number",
        "library_versions",
        ["owner_id", "entity_id", "version_number"],
    )

    op.create_table(
        "library_version_assets",
        sa.Column("library_version_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=False),
        sa.Column("asset_version", sa.BigInteger(), nullable=False),
        sa.Column("asset_sha256", sa.String(64), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("view_label", sa.Text()),
        sa.ForeignKeyConstraint(["library_version_id"], ["library_versions.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"]),
        sa.PrimaryKeyConstraint("library_version_id", "position"),
        sa.UniqueConstraint("library_version_id", "asset_id", name="uq_library_version_asset"),
        sa.CheckConstraint("position >= 0", name="ck_library_version_asset_position"),
        sa.CheckConstraint("asset_version >= 1", name="ck_library_version_asset_version"),
        sa.CheckConstraint(
            "role IN ('identity_appearance', 'location_or_prop', 'source_layer', "
            "'starting_frame', 'motion_performance', 'shot_guidance', 'review_only')",
            name="ck_library_version_asset_role",
        ),
        sa.CheckConstraint(
            "char_length(asset_sha256) = 64", name="ck_library_version_asset_sha256"
        ),
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
