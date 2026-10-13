"""Add immutable image-conditioning manifests to canonical jobs.

Revision ID: 20261013_0010
Revises: 20261013_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_0010"
down_revision: str | None = "20261013_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = (
        sa.Column("idempotency_key", sa.Text()),
        sa.Column("conditioning_owner_id", sa.Text()),
        sa.Column("conditioning_project_id", sa.Text()),
        sa.Column("conditioning_shot_id", sa.Text()),
        sa.Column("conditioning_shot_version", sa.BigInteger()),
        sa.Column("conditioning_composition_id", sa.Text()),
        sa.Column("conditioning_composition_revision", sa.BigInteger()),
        sa.Column("conditioning_composition_fingerprint", sa.String(64)),
        sa.Column("conditioning_source_asset_id", sa.Text()),
        sa.Column("conditioning_source_asset_version", sa.BigInteger()),
        sa.Column("conditioning_source_asset_sha256", sa.String(64)),
        sa.Column("conditioning_source_storage_key", sa.Text()),
        sa.Column("conditioning_source_width", sa.Integer()),
        sa.Column("conditioning_source_height", sa.Integer()),
        sa.Column("conditioning_required_backend", sa.Text()),
        sa.Column("conditioning_required_backend_revision", sa.Text()),
        sa.Column("conditioning_manifest_fingerprint", sa.String(64)),
        sa.Column("conditioning_derivative_sha256", sa.String(64)),
        sa.Column("conditioning_derivative_width", sa.Integer()),
        sa.Column("conditioning_derivative_height", sa.Integer()),
    )
    for column in columns:
        op.add_column("generation_jobs", column)

    op.create_foreign_key(
        "fk_generation_jobs_conditioning_project",
        "generation_jobs",
        "projects",
        ["conditioning_project_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_generation_jobs_conditioning_shot",
        "generation_jobs",
        "film_shots",
        ["conditioning_shot_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_generation_jobs_conditioning_composition",
        "generation_jobs",
        "starting_frame_compositions",
        ["conditioning_composition_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_generation_jobs_conditioning_source_asset",
        "generation_jobs",
        "media_assets",
        ["conditioning_source_asset_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_generation_jobs_image_conditioning",
        "generation_jobs",
        "(mode <> 'image_to_video' AND conditioning_owner_id IS NULL "
        "AND conditioning_project_id IS NULL AND conditioning_shot_id IS NULL "
        "AND conditioning_shot_version IS NULL AND conditioning_composition_id IS NULL "
        "AND conditioning_composition_revision IS NULL "
        "AND conditioning_composition_fingerprint IS NULL "
        "AND conditioning_source_asset_id IS NULL "
        "AND conditioning_source_asset_version IS NULL "
        "AND conditioning_source_asset_sha256 IS NULL "
        "AND conditioning_source_storage_key IS NULL "
        "AND conditioning_source_width IS NULL AND conditioning_source_height IS NULL "
        "AND conditioning_required_backend IS NULL "
        "AND conditioning_required_backend_revision IS NULL "
        "AND conditioning_manifest_fingerprint IS NULL) OR "
        "(mode = 'image_to_video' AND idempotency_key IS NOT NULL "
        "AND conditioning_owner_id IS NOT NULL "
        "AND conditioning_project_id IS NOT NULL AND conditioning_shot_id IS NOT NULL "
        "AND conditioning_shot_version >= 1 AND conditioning_composition_id IS NOT NULL "
        "AND conditioning_composition_revision >= 1 "
        "AND char_length(conditioning_composition_fingerprint) = 64 "
        "AND conditioning_source_asset_id IS NOT NULL "
        "AND conditioning_source_asset_version >= 1 "
        "AND char_length(conditioning_source_asset_sha256) = 64 "
        "AND conditioning_source_storage_key IS NOT NULL "
        "AND conditioning_source_width >= 64 AND conditioning_source_height >= 64 "
        "AND conditioning_required_backend IS NOT NULL "
        "AND conditioning_required_backend_revision IS NOT NULL "
        "AND char_length(conditioning_manifest_fingerprint) = 64)",
    )
    op.create_check_constraint(
        "ck_generation_jobs_conditioning_evidence",
        "generation_jobs",
        "(conditioning_derivative_sha256 IS NULL "
        "AND conditioning_derivative_width IS NULL "
        "AND conditioning_derivative_height IS NULL) OR "
        "(char_length(conditioning_derivative_sha256) = 64 "
        "AND conditioning_derivative_width > 0 AND conditioning_derivative_height > 0)",
    )
    op.create_check_constraint(
        "ck_generation_jobs_image_success_evidence",
        "generation_jobs",
        "status <> 'succeeded' OR mode <> 'image_to_video' OR "
        "(conditioning_derivative_sha256 IS NOT NULL "
        "AND conditioning_derivative_width > 0 AND conditioning_derivative_height > 0)",
    )
    op.create_index(
        "uq_generation_jobs_conditioning_idempotency",
        "generation_jobs",
        ["conditioning_owner_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
