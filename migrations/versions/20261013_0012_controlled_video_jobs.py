"""Add frozen reference-video constraints and execution evidence.

Revision ID: 20261013_0012
Revises: 20261013_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_0012"
down_revision: str | None = "20261013_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = (
        sa.Column("conditioning_reference_guidance_id", sa.Text()),
        sa.Column("conditioning_reference_guidance_revision", sa.BigInteger()),
        sa.Column("conditioning_reference_guidance_fingerprint", sa.String(64)),
        sa.Column("conditioning_reference_purpose", sa.Text()),
        sa.Column("conditioning_reference_asset_id", sa.Text()),
        sa.Column("conditioning_reference_asset_version", sa.BigInteger()),
        sa.Column("conditioning_reference_asset_sha256", sa.String(64)),
        sa.Column("conditioning_reference_storage_key", sa.Text()),
        sa.Column("conditioning_reference_trim_start_ms", sa.BigInteger()),
        sa.Column("conditioning_reference_trim_end_ms", sa.BigInteger()),
        sa.Column("conditioning_controlled_operation", sa.Text()),
        sa.Column("conditioning_preserve_environment", sa.Boolean()),
        sa.Column("conditioning_constraint_plan_fingerprint", sa.String(64)),
        sa.Column("conditioning_reference_derivative_sha256", sa.String(64)),
        sa.Column("conditioning_control_fingerprint", sa.String(64)),
    )
    for column in columns:
        op.add_column("generation_jobs", column)
    op.create_foreign_key(
        "fk_generation_jobs_reference_guidance",
        "generation_jobs",
        "reference_video_guidance",
        ["conditioning_reference_guidance_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_generation_jobs_reference_asset",
        "generation_jobs",
        "media_assets",
        ["conditioning_reference_asset_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_generation_jobs_reference_conditioning",
        "generation_jobs",
        "(conditioning_reference_guidance_id IS NULL "
        "AND conditioning_reference_guidance_revision IS NULL "
        "AND conditioning_reference_guidance_fingerprint IS NULL "
        "AND conditioning_reference_purpose IS NULL "
        "AND conditioning_reference_asset_id IS NULL "
        "AND conditioning_reference_asset_version IS NULL "
        "AND conditioning_reference_asset_sha256 IS NULL "
        "AND conditioning_reference_storage_key IS NULL "
        "AND conditioning_reference_trim_start_ms IS NULL "
        "AND conditioning_reference_trim_end_ms IS NULL "
        "AND conditioning_controlled_operation IS NULL "
        "AND conditioning_preserve_environment IS NULL "
        "AND conditioning_constraint_plan_fingerprint IS NULL) OR "
        "(mode = 'image_to_video' AND conditioning_reference_guidance_id IS NOT NULL "
        "AND conditioning_reference_guidance_revision >= 1 "
        "AND char_length(conditioning_reference_guidance_fingerprint) = 64 "
        "AND conditioning_reference_purpose = 'motion_performance' "
        "AND conditioning_reference_asset_id IS NOT NULL "
        "AND conditioning_reference_asset_version >= 1 "
        "AND char_length(conditioning_reference_asset_sha256) = 64 "
        "AND conditioning_reference_storage_key IS NOT NULL "
        "AND conditioning_reference_trim_start_ms >= 0 "
        "AND conditioning_reference_trim_end_ms > conditioning_reference_trim_start_ms "
        "AND conditioning_controlled_operation IN "
        "('vace_performance_transfer', 'animate_character', 'animate_replacement') "
        "AND conditioning_preserve_environment IS NOT NULL "
        "AND ((conditioning_controlled_operation = 'vace_performance_transfer' "
        "AND conditioning_preserve_environment = true) OR "
        "(conditioning_controlled_operation IN ('animate_character', 'animate_replacement') "
        "AND conditioning_preserve_environment = false)) "
        "AND char_length(conditioning_constraint_plan_fingerprint) = 64)",
    )
    op.create_check_constraint(
        "ck_generation_jobs_reference_evidence",
        "generation_jobs",
        "(conditioning_reference_derivative_sha256 IS NULL "
        "AND conditioning_control_fingerprint IS NULL) OR "
        "(conditioning_reference_guidance_id IS NOT NULL "
        "AND char_length(conditioning_reference_derivative_sha256) = 64 "
        "AND char_length(conditioning_control_fingerprint) = 64)",
    )
    op.create_check_constraint(
        "ck_generation_jobs_reference_success_evidence",
        "generation_jobs",
        "status <> 'succeeded' OR conditioning_reference_guidance_id IS NULL OR "
        "(conditioning_reference_derivative_sha256 IS NOT NULL "
        "AND conditioning_control_fingerprint IS NOT NULL)",
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
