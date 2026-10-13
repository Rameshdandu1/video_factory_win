"""Add immutable project Film Bible and shot-binding revisions.

Revision ID: 20261013_0008
Revises: 20261013_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_0008"
down_revision: str | None = "20261013_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_VERSION_KIND = (
    "version_kind IN ('identity', 'wardrobe', 'location_view', 'lighting_variant', "
    "'prop_variant', 'prop_state', 'shot_reference')"
)
_PIN_ROLE = (
    "role IN ('character_identity', 'character_wardrobe', 'location_view', "
    "'location_lighting', 'prop_variant', 'prop_state', 'shot_reference')"
)


def upgrade() -> None:
    op.create_table(
        "film_bible_snapshots",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.UniqueConstraint("project_id", "revision", name="uq_film_bible_project_revision"),
        sa.UniqueConstraint("owner_id", "id", name="uq_film_bible_owner_id_id"),
        sa.CheckConstraint("revision >= 1", name="ck_film_bible_revision"),
        sa.CheckConstraint("status IN ('draft', 'approved')", name="ck_film_bible_status"),
        sa.CheckConstraint(
            "(status = 'draft' AND approved_at IS NULL) OR "
            "(status = 'approved' AND approved_at IS NOT NULL)",
            name="ck_film_bible_approval",
        ),
        sa.CheckConstraint("char_length(fingerprint) = 64", name="ck_film_bible_fingerprint"),
    )
    op.create_index(
        "ix_film_bible_owner_project_revision",
        "film_bible_snapshots",
        ["owner_id", "project_id", "revision"],
    )
    op.create_table(
        "film_bible_pins",
        sa.Column("snapshot_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("library_version_id", sa.Text(), nullable=False),
        sa.Column("library_version_number", sa.BigInteger(), nullable=False),
        sa.Column("version_kind", sa.Text(), nullable=False),
        sa.Column("version_fingerprint", sa.String(64), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["film_bible_snapshots.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["library_entities.id"]),
        sa.ForeignKeyConstraint(["library_version_id"], ["library_versions.id"]),
        sa.PrimaryKeyConstraint("snapshot_id", "position"),
        sa.UniqueConstraint("snapshot_id", "entity_id", "role", name="uq_film_bible_pin_role"),
        sa.CheckConstraint("position >= 0", name="ck_film_bible_pin_position"),
        sa.CheckConstraint("library_version_number >= 1", name="ck_film_bible_pin_version"),
        sa.CheckConstraint(_VERSION_KIND, name="ck_film_bible_pin_kind"),
        sa.CheckConstraint(_PIN_ROLE, name="ck_film_bible_pin_role"),
        sa.CheckConstraint(
            "char_length(version_fingerprint) = 64", name="ck_film_bible_pin_fingerprint"
        ),
    )
    op.create_table(
        "shot_binding_revisions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("shot_id", sa.Text(), nullable=False),
        sa.Column("shot_version", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("film_bible_snapshot_id", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["shot_id"], ["film_shots.id"]),
        sa.ForeignKeyConstraint(["film_bible_snapshot_id"], ["film_bible_snapshots.id"]),
        sa.UniqueConstraint("shot_id", "revision", name="uq_shot_binding_revision"),
        sa.UniqueConstraint("owner_id", "id", name="uq_shot_binding_owner_id_id"),
        sa.CheckConstraint("shot_version >= 1", name="ck_shot_binding_shot_version"),
        sa.CheckConstraint("revision >= 1", name="ck_shot_binding_revision"),
        sa.CheckConstraint("char_length(fingerprint) = 64", name="ck_shot_binding_fingerprint"),
    )
    op.create_index(
        "ix_shot_bindings_owner_project_shot_revision",
        "shot_binding_revisions",
        ["owner_id", "project_id", "shot_id", "revision"],
    )
    op.create_table(
        "shot_library_bindings",
        sa.Column("binding_revision_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("library_version_id", sa.Text(), nullable=False),
        sa.Column("library_version_number", sa.BigInteger(), nullable=False),
        sa.Column("version_kind", sa.Text(), nullable=False),
        sa.Column("version_fingerprint", sa.String(64), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["binding_revision_id"], ["shot_binding_revisions.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["library_entities.id"]),
        sa.ForeignKeyConstraint(["library_version_id"], ["library_versions.id"]),
        sa.PrimaryKeyConstraint("binding_revision_id", "position"),
        sa.UniqueConstraint(
            "binding_revision_id", "entity_id", "role", name="uq_shot_library_binding_role"
        ),
        sa.CheckConstraint("position >= 0", name="ck_shot_library_binding_position"),
        sa.CheckConstraint("library_version_number >= 1", name="ck_shot_library_binding_version"),
        sa.CheckConstraint(_VERSION_KIND, name="ck_shot_library_binding_kind"),
        sa.CheckConstraint(_PIN_ROLE, name="ck_shot_library_binding_role"),
        sa.CheckConstraint(
            "char_length(version_fingerprint) = 64",
            name="ck_shot_library_binding_fingerprint",
        ),
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
