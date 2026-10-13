"""Add immutable bounded reference-video guidance revisions.

Revision ID: 20261013_0011
Revises: 20261013_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_0011"
down_revision: str | None = "20261013_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reference_video_guidance",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("shot_id", sa.Text(), nullable=False),
        sa.Column("shot_version", sa.BigInteger(), nullable=False),
        sa.Column("shot_binding_revision_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("source_asset_id", sa.Text(), nullable=False),
        sa.Column("source_asset_version", sa.BigInteger(), nullable=False),
        sa.Column("source_asset_sha256", sa.String(64), nullable=False),
        sa.Column("source_media_type", sa.Text(), nullable=False),
        sa.Column("source_scope", sa.Text(), nullable=False),
        sa.Column("source_inspector_revision", sa.Text(), nullable=False),
        sa.Column("source_duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("source_width", sa.Integer(), nullable=False),
        sa.Column("source_height", sa.Integer(), nullable=False),
        sa.Column("source_frame_rate_numerator", sa.Integer(), nullable=False),
        sa.Column("source_frame_rate_denominator", sa.Integer(), nullable=False),
        sa.Column("source_library_entity_id", sa.Text()),
        sa.Column("source_library_version_id", sa.Text()),
        sa.Column("source_library_version_fingerprint", sa.String(64)),
        sa.Column("trim_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("trim_end_ms", sa.BigInteger(), nullable=False),
        sa.Column("guidance_notes", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["shot_id"], ["film_shots.id"]),
        sa.ForeignKeyConstraint(["shot_binding_revision_id"], ["shot_binding_revisions.id"]),
        sa.ForeignKeyConstraint(["source_asset_id"], ["media_assets.id"]),
        sa.ForeignKeyConstraint(["source_library_entity_id"], ["library_entities.id"]),
        sa.ForeignKeyConstraint(["source_library_version_id"], ["library_versions.id"]),
        sa.UniqueConstraint("shot_id", "revision", name="uq_reference_guidance_shot_revision"),
        sa.UniqueConstraint("owner_id", "id", name="uq_reference_guidance_owner_id_id"),
        sa.CheckConstraint(
            "shot_version >= 1 AND revision >= 1", name="ck_reference_guidance_revisions"
        ),
        sa.CheckConstraint(
            "purpose IN ('motion_performance', 'shot_guidance', 'review_only')",
            name="ck_reference_guidance_purpose",
        ),
        sa.CheckConstraint("status IN ('draft', 'approved')", name="ck_reference_guidance_status"),
        sa.CheckConstraint(
            "source_asset_version >= 1", name="ck_reference_guidance_source_version"
        ),
        sa.CheckConstraint(
            "char_length(source_asset_sha256) = 64", name="ck_reference_guidance_source_sha"
        ),
        sa.CheckConstraint(
            "source_media_type LIKE 'video/%'", name="ck_reference_guidance_media_type"
        ),
        sa.CheckConstraint(
            "source_scope IN ('project', 'library')", name="ck_reference_guidance_scope"
        ),
        sa.CheckConstraint(
            "source_duration_ms > 0 AND source_width > 0 AND source_height > 0 "
            "AND source_frame_rate_numerator > 0 AND source_frame_rate_denominator > 0",
            name="ck_reference_guidance_metadata",
        ),
        sa.CheckConstraint(
            "(source_scope = 'project' AND source_library_entity_id IS NULL "
            "AND source_library_version_id IS NULL "
            "AND source_library_version_fingerprint IS NULL) OR "
            "(source_scope = 'library' AND source_library_entity_id IS NOT NULL "
            "AND source_library_version_id IS NOT NULL "
            "AND char_length(source_library_version_fingerprint) = 64)",
            name="ck_reference_guidance_provenance",
        ),
        sa.CheckConstraint(
            "trim_start_ms >= 0 AND trim_end_ms <= source_duration_ms "
            "AND trim_end_ms - trim_start_ms BETWEEN 250 AND 30000",
            name="ck_reference_guidance_trim",
        ),
        sa.CheckConstraint(
            "char_length(guidance_notes) <= 2000", name="ck_reference_guidance_notes"
        ),
        sa.CheckConstraint(
            "char_length(fingerprint) = 64", name="ck_reference_guidance_fingerprint"
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND approved_at IS NULL) OR "
            "(status = 'approved' AND approved_at IS NOT NULL)",
            name="ck_reference_guidance_approval",
        ),
    )
    op.create_index(
        "ix_reference_guidance_owner_project_shot_revision",
        "reference_video_guidance",
        ["owner_id", "project_id", "shot_id", "revision"],
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
