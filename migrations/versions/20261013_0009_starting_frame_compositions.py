"""Add immutable starting-frame compositions and layer provenance.

Revision ID: 20261013_0009
Revises: 20261013_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_0009"
down_revision: str | None = "20261013_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "starting_frame_compositions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("shot_id", sa.Text(), nullable=False),
        sa.Column("shot_version", sa.BigInteger(), nullable=False),
        sa.Column("shot_binding_revision_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("canvas_width", sa.Integer(), nullable=False),
        sa.Column("canvas_height", sa.Integer(), nullable=False),
        sa.Column("background_rgba", sa.String(9), nullable=False),
        sa.Column("output_rights", sa.Text(), nullable=False),
        sa.Column("framing_notes", sa.Text(), nullable=False),
        sa.Column("pose_notes", sa.Text(), nullable=False),
        sa.Column("action_notes", sa.Text(), nullable=False),
        sa.Column("lighting_notes", sa.Text(), nullable=False),
        sa.Column("visible_speaker_entity_id", sa.Text()),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rendered_asset_id", sa.Text()),
        sa.Column("rendered_asset_version", sa.BigInteger()),
        sa.Column("rendered_sha256", sa.String(64)),
        sa.Column("renderer_revision", sa.Text()),
        sa.Column("rendered_at", sa.DateTime(timezone=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["shot_id"], ["film_shots.id"]),
        sa.ForeignKeyConstraint(["shot_binding_revision_id"], ["shot_binding_revisions.id"]),
        sa.ForeignKeyConstraint(["visible_speaker_entity_id"], ["library_entities.id"]),
        sa.ForeignKeyConstraint(["rendered_asset_id"], ["media_assets.id"]),
        sa.UniqueConstraint("shot_id", "revision", name="uq_starting_frame_shot_revision"),
        sa.UniqueConstraint("owner_id", "id", name="uq_starting_frame_owner_id_id"),
        sa.CheckConstraint(
            "shot_version >= 1 AND revision >= 1", name="ck_starting_frame_revisions"
        ),
        sa.CheckConstraint("mode IN ('composed_upload', 'layered')", name="ck_starting_frame_mode"),
        sa.CheckConstraint(
            "status IN ('draft', 'rendered', 'approved')", name="ck_starting_frame_status"
        ),
        sa.CheckConstraint(
            "canvas_width BETWEEN 64 AND 4096 AND canvas_height BETWEEN 64 AND 4096 "
            "AND canvas_width * canvas_height <= 16777216",
            name="ck_starting_frame_canvas",
        ),
        sa.CheckConstraint(
            "output_rights IN ('owned', 'licensed', 'permissioned', 'public_domain')",
            name="ck_starting_frame_rights",
        ),
        sa.CheckConstraint("char_length(fingerprint) = 64", name="ck_starting_frame_fingerprint"),
        sa.CheckConstraint(
            "(status = 'draft' AND rendered_asset_id IS NULL AND rendered_asset_version IS NULL "
            "AND rendered_sha256 IS NULL AND renderer_revision IS NULL AND rendered_at IS NULL "
            "AND approved_at IS NULL) OR (status = 'rendered' AND rendered_asset_id IS NOT NULL "
            "AND rendered_asset_version IS NOT NULL AND rendered_sha256 IS NOT NULL "
            "AND renderer_revision IS NOT NULL AND rendered_at IS NOT NULL "
            "AND approved_at IS NULL) "
            "OR (status = 'approved' AND rendered_asset_id IS NOT NULL "
            "AND rendered_asset_version IS NOT NULL AND rendered_sha256 IS NOT NULL "
            "AND renderer_revision IS NOT NULL AND rendered_at IS NOT NULL "
            "AND approved_at IS NOT NULL)",
            name="ck_starting_frame_lifecycle",
        ),
    )
    op.create_index(
        "ix_starting_frames_owner_project_shot_revision",
        "starting_frame_compositions",
        ["owner_id", "project_id", "shot_id", "revision"],
    )
    op.create_table(
        "starting_frame_layers",
        sa.Column("composition_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("source_asset_id", sa.Text(), nullable=False),
        sa.Column("source_asset_version", sa.BigInteger(), nullable=False),
        sa.Column("source_asset_sha256", sa.String(64), nullable=False),
        sa.Column("source_scope", sa.Text(), nullable=False),
        sa.Column("source_library_entity_id", sa.Text()),
        sa.Column("source_library_version_id", sa.Text()),
        sa.Column("source_library_version_fingerprint", sa.String(64)),
        sa.Column("mask_asset_id", sa.Text()),
        sa.Column("mask_asset_version", sa.BigInteger()),
        sa.Column("mask_asset_sha256", sa.String(64)),
        sa.Column("mask_scope", sa.Text()),
        sa.Column("mask_library_entity_id", sa.Text()),
        sa.Column("mask_library_version_id", sa.Text()),
        sa.Column("mask_library_version_fingerprint", sa.String(64)),
        sa.Column("target_x", sa.Integer(), nullable=False),
        sa.Column("target_y", sa.Integer(), nullable=False),
        sa.Column("target_width", sa.Integer(), nullable=False),
        sa.Column("target_height", sa.Integer(), nullable=False),
        sa.Column("rotation_millidegrees", sa.Integer(), nullable=False),
        sa.Column("opacity_basis_points", sa.Integer(), nullable=False),
        sa.Column("fit", sa.Text(), nullable=False),
        sa.Column("crop_x", sa.Integer()),
        sa.Column("crop_y", sa.Integer()),
        sa.Column("crop_width", sa.Integer()),
        sa.Column("crop_height", sa.Integer()),
        sa.ForeignKeyConstraint(["composition_id"], ["starting_frame_compositions.id"]),
        sa.ForeignKeyConstraint(["source_asset_id"], ["media_assets.id"]),
        sa.ForeignKeyConstraint(["source_library_entity_id"], ["library_entities.id"]),
        sa.ForeignKeyConstraint(["source_library_version_id"], ["library_versions.id"]),
        sa.ForeignKeyConstraint(["mask_asset_id"], ["media_assets.id"]),
        sa.ForeignKeyConstraint(["mask_library_entity_id"], ["library_entities.id"]),
        sa.ForeignKeyConstraint(["mask_library_version_id"], ["library_versions.id"]),
        sa.PrimaryKeyConstraint("composition_id", "position"),
        sa.CheckConstraint("position >= 0", name="ck_starting_frame_layer_position"),
        sa.CheckConstraint(
            "role IN ('starting_frame', 'background', 'character', 'prop', 'overlay')",
            name="ck_starting_frame_layer_role",
        ),
        sa.CheckConstraint("source_asset_version >= 1", name="ck_starting_frame_source_version"),
        sa.CheckConstraint(
            "source_scope IN ('project', 'library')", name="ck_starting_frame_source_scope"
        ),
        sa.CheckConstraint(
            "char_length(source_asset_sha256) = 64", name="ck_starting_frame_source_sha"
        ),
        sa.CheckConstraint(
            "(source_scope = 'project' AND source_library_entity_id IS NULL "
            "AND source_library_version_id IS NULL AND source_library_version_fingerprint IS NULL) "
            "OR (source_scope = 'library' AND source_library_entity_id IS NOT NULL "
            "AND source_library_version_id IS NOT NULL "
            "AND source_library_version_fingerprint IS NOT NULL)",
            name="ck_starting_frame_source_provenance",
        ),
        sa.CheckConstraint(
            "source_library_version_fingerprint IS NULL "
            "OR char_length(source_library_version_fingerprint) = 64",
            name="ck_starting_frame_source_version_fingerprint",
        ),
        sa.CheckConstraint(
            "(mask_asset_id IS NULL AND mask_asset_version IS NULL AND mask_asset_sha256 IS NULL "
            "AND mask_scope IS NULL AND mask_library_entity_id IS NULL "
            "AND mask_library_version_id IS NULL AND mask_library_version_fingerprint IS NULL) "
            "OR (mask_asset_id IS NOT NULL AND mask_asset_version IS NOT NULL "
            "AND mask_asset_version >= 1 AND mask_asset_sha256 IS NOT NULL "
            "AND char_length(mask_asset_sha256) = 64 AND mask_scope IS NOT NULL "
            "AND ((mask_scope = 'project' "
            "AND mask_library_entity_id IS NULL AND mask_library_version_id IS NULL "
            "AND mask_library_version_fingerprint IS NULL) OR (mask_scope = 'library' "
            "AND mask_library_entity_id IS NOT NULL AND mask_library_version_id IS NOT NULL "
            "AND char_length(mask_library_version_fingerprint) = 64)))",
            name="ck_starting_frame_mask",
        ),
        sa.CheckConstraint(
            "target_width BETWEEN 1 AND 8192 AND target_height BETWEEN 1 AND 8192",
            name="ck_starting_frame_target_size",
        ),
        sa.CheckConstraint(
            "rotation_millidegrees BETWEEN -360000 AND 360000",
            name="ck_starting_frame_rotation",
        ),
        sa.CheckConstraint(
            "opacity_basis_points BETWEEN 0 AND 10000", name="ck_starting_frame_opacity"
        ),
        sa.CheckConstraint("fit IN ('contain', 'cover', 'stretch')", name="ck_starting_frame_fit"),
        sa.CheckConstraint(
            "(crop_x IS NULL AND crop_y IS NULL AND crop_width IS NULL AND crop_height IS NULL) "
            "OR (crop_x IS NOT NULL AND crop_y IS NOT NULL AND crop_width IS NOT NULL "
            "AND crop_height IS NOT NULL AND crop_x >= 0 AND crop_y >= 0 "
            "AND crop_width > 0 AND crop_height > 0)",
            name="ck_starting_frame_crop",
        ),
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
