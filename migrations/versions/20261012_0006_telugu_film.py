"""Add Telugu short-film preset and film workflow entities.

Revision ID: 20261012_0006
Revises: 20261012_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_0006"
down_revision: str | None = "20261012_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects", sa.Column("preset", sa.Text(), nullable=False, server_default="standard")
    )
    op.add_column(
        "projects",
        sa.Column(
            "titles_and_credits_within_target",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_check_constraint(
        "ck_projects_preset",
        "projects",
        "preset IN ('standard', 'telugu_short_film_900')",
    )
    op.create_table(
        "film_scenes",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("target_duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("telugu_script", sa.Text(), nullable=False),
        sa.Column("pronunciation_notes", sa.Text(), nullable=False),
        sa.Column("continuity", sa.JSON(), nullable=False),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.UniqueConstraint("project_id", "position", name="uq_film_scene_position"),
        sa.CheckConstraint("version >= 1", name="ck_film_scene_version"),
        sa.CheckConstraint("target_duration_ms > 0", name="ck_film_scene_duration"),
        sa.CheckConstraint(
            "char_length(content_fingerprint) = 64", name="ck_film_scene_fingerprint"
        ),
    )
    op.create_table(
        "film_shots",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("scene_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("target_duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reference_workflow", sa.Text(), nullable=False),
        sa.Column("character_reference_asset_ids", sa.JSON(), nullable=False),
        sa.Column("dialogue_workflow", sa.Text(), nullable=False),
        sa.Column("storyboard_asset_id", sa.Text(), nullable=False),
        sa.Column("source_footage_asset_id", sa.Text()),
        sa.Column("recorded_dialogue_asset_id", sa.Text()),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["film_scenes.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["storyboard_asset_id"], ["media_assets.id"]),
        sa.ForeignKeyConstraint(["source_footage_asset_id"], ["media_assets.id"]),
        sa.ForeignKeyConstraint(["recorded_dialogue_asset_id"], ["media_assets.id"]),
        sa.UniqueConstraint("scene_id", "position", name="uq_film_shot_position"),
        sa.CheckConstraint("version >= 1", name="ck_film_shot_version"),
        sa.CheckConstraint("target_duration_ms > 0", name="ck_film_shot_duration"),
        sa.CheckConstraint(
            "reference_workflow IN ('reference_generation', 'approved_source_footage')",
            name="ck_film_shot_reference_workflow",
        ),
        sa.CheckConstraint(
            "dialogue_workflow IN ('tts', 'recorded')",
            name="ck_film_shot_dialogue_workflow",
        ),
        sa.CheckConstraint(
            "char_length(content_fingerprint) = 64", name="ck_film_shot_fingerprint"
        ),
    )
    op.create_table(
        "film_approvals",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("scene_id", sa.Text()),
        sa.Column("shot_id", sa.Text()),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("subject_fingerprint", sa.String(64), nullable=False),
        sa.Column("evidence_asset_id", sa.Text()),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["film_scenes.id"]),
        sa.ForeignKeyConstraint(["shot_id"], ["film_shots.id"]),
        sa.ForeignKeyConstraint(["evidence_asset_id"], ["media_assets.id"]),
        sa.UniqueConstraint(
            "project_id",
            "scene_id",
            "shot_id",
            "stage",
            "subject_fingerprint",
            name="uq_film_approval_subject",
        ),
        sa.CheckConstraint(
            "stage IN ('character_references', 'identity_workflow', 'telugu_script', "
            "'pronunciation', 'voice_performance', 'storyboard', 'visual_performance', "
            "'lip_sync', 'adjacent_shot_continuity', 'rough_cut', "
            "'dialogue_90_seconds', 'sequence_180_seconds', 'film_900_seconds', "
            "'final_sound_mix')",
            name="ck_film_approval_stage",
        ),
    )
    op.create_index(
        "ix_film_scenes_project_position", "film_scenes", ["owner_id", "project_id", "position"]
    )
    op.create_index(
        "ix_film_shots_scene_position", "film_shots", ["owner_id", "scene_id", "position"]
    )


def downgrade() -> None:
    raise NotImplementedError("Production schema migrations are forward-only")
