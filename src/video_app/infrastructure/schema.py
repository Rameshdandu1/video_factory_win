"""Canonical SQLAlchemy metadata for the PostgreSQL job store."""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

generation_jobs = sa.Table(
    "generation_jobs",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.Column("prompt", sa.Text(), nullable=False),
    sa.Column("model", sa.Text(), nullable=False),
    sa.Column("mode", sa.Text(), nullable=False),
    sa.Column("width", sa.Integer(), nullable=False),
    sa.Column("height", sa.Integer(), nullable=False),
    sa.Column("frame_count", sa.Integer(), nullable=False),
    sa.Column("seed", sa.BigInteger(), nullable=False),
    sa.Column("idempotency_key", sa.Text()),
    sa.Column("conditioning_owner_id", sa.Text()),
    sa.Column("conditioning_project_id", sa.Text(), sa.ForeignKey("projects.id")),
    sa.Column("conditioning_shot_id", sa.Text(), sa.ForeignKey("film_shots.id")),
    sa.Column("conditioning_shot_version", sa.BigInteger()),
    sa.Column(
        "conditioning_composition_id", sa.Text(), sa.ForeignKey("starting_frame_compositions.id")
    ),
    sa.Column("conditioning_composition_revision", sa.BigInteger()),
    sa.Column("conditioning_composition_fingerprint", sa.String(64)),
    sa.Column("conditioning_source_asset_id", sa.Text(), sa.ForeignKey("media_assets.id")),
    sa.Column("conditioning_source_asset_version", sa.BigInteger()),
    sa.Column("conditioning_source_asset_sha256", sa.String(64)),
    sa.Column("conditioning_source_storage_key", sa.Text()),
    sa.Column("conditioning_source_width", sa.Integer()),
    sa.Column("conditioning_source_height", sa.Integer()),
    sa.Column("conditioning_required_backend", sa.Text()),
    sa.Column("conditioning_required_backend_revision", sa.Text()),
    sa.Column("conditioning_manifest_fingerprint", sa.String(64)),
    sa.Column(
        "conditioning_reference_guidance_id",
        sa.Text(),
        sa.ForeignKey("reference_video_guidance.id"),
    ),
    sa.Column("conditioning_reference_guidance_revision", sa.BigInteger()),
    sa.Column("conditioning_reference_guidance_fingerprint", sa.String(64)),
    sa.Column("conditioning_reference_purpose", sa.Text()),
    sa.Column("conditioning_reference_asset_id", sa.Text(), sa.ForeignKey("media_assets.id")),
    sa.Column("conditioning_reference_asset_version", sa.BigInteger()),
    sa.Column("conditioning_reference_asset_sha256", sa.String(64)),
    sa.Column("conditioning_reference_storage_key", sa.Text()),
    sa.Column("conditioning_reference_trim_start_ms", sa.BigInteger()),
    sa.Column("conditioning_reference_trim_end_ms", sa.BigInteger()),
    sa.Column("conditioning_controlled_operation", sa.Text()),
    sa.Column("conditioning_preserve_environment", sa.Boolean()),
    sa.Column("conditioning_constraint_plan_fingerprint", sa.String(64)),
    sa.Column("conditioning_derivative_sha256", sa.String(64)),
    sa.Column("conditioning_derivative_width", sa.Integer()),
    sa.Column("conditioning_derivative_height", sa.Integer()),
    sa.Column("conditioning_reference_derivative_sha256", sa.String(64)),
    sa.Column("conditioning_control_fingerprint", sa.String(64)),
    sa.Column("rough_cut_project_id", sa.Text(), sa.ForeignKey("projects.id")),
    sa.Column("rough_cut_workspace_fingerprint", sa.String(64)),
    sa.Column("rough_cut_required_backend", sa.Text()),
    sa.Column("rough_cut_required_backend_revision", sa.Text()),
    sa.Column("rough_cut_manifest_fingerprint", sa.String(64)),
    sa.Column("rough_cut_manifest", sa.JSON()),
    sa.Column("timeline_render_project_id", sa.Text(), sa.ForeignKey("projects.id")),
    sa.Column("timeline_render_timeline_id", sa.Text(), sa.ForeignKey("timeline_revisions.id")),
    sa.Column("timeline_render_timeline_revision", sa.BigInteger()),
    sa.Column("timeline_render_timeline_fingerprint", sa.String(64)),
    sa.Column("timeline_render_required_backend", sa.Text()),
    sa.Column("timeline_render_required_backend_revision", sa.Text()),
    sa.Column("timeline_render_manifest_fingerprint", sa.String(64)),
    sa.Column("timeline_render_manifest", sa.JSON()),
    sa.Column("backend", sa.Text()),
    sa.Column("model_revision", sa.Text()),
    sa.Column("progress_completed_units", sa.Integer()),
    sa.Column("progress_total_units", sa.Integer()),
    sa.Column("progress_stage", sa.Text()),
    sa.Column("result_storage_key", sa.Text()),
    sa.Column("result_media_type", sa.Text()),
    sa.Column("result_width", sa.Integer()),
    sa.Column("result_height", sa.Integer()),
    sa.Column("result_frame_count", sa.Integer()),
    sa.Column("result_duration_seconds", sa.Float()),
    sa.Column("result_size_bytes", sa.BigInteger()),
    sa.Column("result_sha256", sa.String(64)),
    sa.Column("result_created_at", sa.DateTime(timezone=True)),
    sa.Column("failure_code", sa.Text()),
    sa.Column("failure_message", sa.Text()),
    sa.Column("failure_retryable", sa.Boolean()),
    sa.Column("failure_correlation_id", sa.Text()),
    sa.Column("cancellation_requested_at", sa.DateTime(timezone=True)),
    sa.Column("worker_id", sa.Text()),
    sa.Column("attempt_id", sa.Text()),
    sa.Column("lease_token", sa.Text()),
    sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
    sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
    sa.CheckConstraint(
        "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
        name="ck_generation_jobs_status",
    ),
    sa.CheckConstraint("version >= 1", name="ck_generation_jobs_version"),
    sa.CheckConstraint(
        "char_length(prompt) BETWEEN 1 AND 2000",
        name="ck_generation_jobs_prompt_length",
    ),
    sa.CheckConstraint(
        "width > 0 AND height > 0 AND frame_count > 0",
        name="ck_generation_jobs_request_dimensions",
    ),
    sa.CheckConstraint(
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
        name="ck_generation_jobs_image_conditioning",
    ),
    sa.CheckConstraint(
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
        name="ck_generation_jobs_reference_conditioning",
    ),
    sa.CheckConstraint(
        "(conditioning_derivative_sha256 IS NULL "
        "AND conditioning_derivative_width IS NULL "
        "AND conditioning_derivative_height IS NULL) OR "
        "(char_length(conditioning_derivative_sha256) = 64 "
        "AND conditioning_derivative_width > 0 AND conditioning_derivative_height > 0)",
        name="ck_generation_jobs_conditioning_evidence",
    ),
    sa.CheckConstraint(
        "(conditioning_reference_derivative_sha256 IS NULL "
        "AND conditioning_control_fingerprint IS NULL) OR "
        "(conditioning_reference_guidance_id IS NOT NULL "
        "AND char_length(conditioning_reference_derivative_sha256) = 64 "
        "AND char_length(conditioning_control_fingerprint) = 64)",
        name="ck_generation_jobs_reference_evidence",
    ),
    sa.CheckConstraint(
        "status <> 'succeeded' OR conditioning_reference_guidance_id IS NULL OR "
        "(conditioning_reference_derivative_sha256 IS NOT NULL "
        "AND conditioning_control_fingerprint IS NOT NULL)",
        name="ck_generation_jobs_reference_success_evidence",
    ),
    sa.CheckConstraint(
        "status <> 'succeeded' OR mode <> 'image_to_video' OR "
        "(conditioning_derivative_sha256 IS NOT NULL "
        "AND conditioning_derivative_width > 0 AND conditioning_derivative_height > 0)",
        name="ck_generation_jobs_image_success_evidence",
    ),
    sa.CheckConstraint(
        "(mode <> 'rough_cut' AND rough_cut_project_id IS NULL "
        "AND rough_cut_workspace_fingerprint IS NULL AND rough_cut_required_backend IS NULL "
        "AND rough_cut_required_backend_revision IS NULL "
        "AND rough_cut_manifest_fingerprint IS NULL AND rough_cut_manifest IS NULL) OR "
        "(mode = 'rough_cut' AND idempotency_key IS NOT NULL "
        "AND rough_cut_project_id IS NOT NULL "
        "AND char_length(rough_cut_workspace_fingerprint) = 64 "
        "AND rough_cut_required_backend IS NOT NULL "
        "AND rough_cut_required_backend_revision IS NOT NULL "
        "AND char_length(rough_cut_manifest_fingerprint) = 64 "
        "AND rough_cut_manifest IS NOT NULL)",
        name="ck_generation_jobs_rough_cut_manifest",
    ),
    sa.CheckConstraint(
        "(mode <> 'timeline_render' AND timeline_render_project_id IS NULL "
        "AND timeline_render_timeline_id IS NULL "
        "AND timeline_render_timeline_revision IS NULL "
        "AND timeline_render_timeline_fingerprint IS NULL "
        "AND timeline_render_required_backend IS NULL "
        "AND timeline_render_required_backend_revision IS NULL "
        "AND timeline_render_manifest_fingerprint IS NULL "
        "AND timeline_render_manifest IS NULL) OR "
        "(mode = 'timeline_render' AND idempotency_key IS NOT NULL "
        "AND timeline_render_project_id IS NOT NULL "
        "AND timeline_render_timeline_id IS NOT NULL "
        "AND timeline_render_timeline_revision >= 1 "
        "AND char_length(timeline_render_timeline_fingerprint) = 64 "
        "AND timeline_render_required_backend IS NOT NULL "
        "AND timeline_render_required_backend_revision IS NOT NULL "
        "AND char_length(timeline_render_manifest_fingerprint) = 64 "
        "AND timeline_render_manifest IS NOT NULL)",
        name="ck_generation_jobs_timeline_render_manifest",
    ),
    sa.CheckConstraint(
        "(progress_completed_units IS NULL AND progress_total_units IS NULL "
        "AND progress_stage IS NULL) OR "
        "(progress_completed_units BETWEEN 0 AND progress_total_units "
        "AND progress_total_units > 0 AND char_length(progress_stage) > 0)",
        name="ck_generation_jobs_progress",
    ),
    sa.CheckConstraint(
        "(status = 'running') = (worker_id IS NOT NULL AND attempt_id IS NOT NULL "
        "AND lease_token IS NOT NULL AND heartbeat_at IS NOT NULL "
        "AND lease_expires_at IS NOT NULL)",
        name="ck_generation_jobs_active_lease",
    ),
    sa.CheckConstraint(
        "(status IN ('succeeded', 'failed', 'cancelled')) = (completed_at IS NOT NULL)",
        name="ck_generation_jobs_terminal_completion",
    ),
    sa.CheckConstraint(
        "status <> 'succeeded' OR (result_storage_key IS NOT NULL "
        "AND result_media_type = 'video/mp4' AND result_width > 0 "
        "AND result_height > 0 AND result_frame_count > 0 AND result_size_bytes > 0 "
        "AND char_length(result_sha256) = 64 AND result_created_at IS NOT NULL)",
        name="ck_generation_jobs_success_result",
    ),
    sa.CheckConstraint(
        "status <> 'failed' OR (failure_code IS NOT NULL AND failure_message IS NOT NULL "
        "AND failure_retryable IS NOT NULL AND failure_correlation_id IS NOT NULL)",
        name="ck_generation_jobs_failure",
    ),
    sa.CheckConstraint(
        "status <> 'cancelled' OR cancellation_requested_at IS NOT NULL",
        name="ck_generation_jobs_cancellation",
    ),
)

sa.Index(
    "uq_generation_jobs_conditioning_idempotency",
    generation_jobs.c.conditioning_owner_id,
    generation_jobs.c.idempotency_key,
    unique=True,
    postgresql_where=generation_jobs.c.idempotency_key.is_not(None),
)

sa.Index(
    "uq_generation_jobs_rough_cut_idempotency",
    generation_jobs.c.rough_cut_project_id,
    generation_jobs.c.idempotency_key,
    unique=True,
    postgresql_where=generation_jobs.c.rough_cut_project_id.is_not(None),
)

sa.Index(
    "uq_generation_jobs_timeline_render_idempotency",
    generation_jobs.c.timeline_render_project_id,
    generation_jobs.c.idempotency_key,
    unique=True,
    postgresql_where=generation_jobs.c.timeline_render_project_id.is_not(None),
)

projects = sa.Table(
    "projects",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("owner_id", sa.Text(), nullable=False),
    sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
    sa.Column("state", sa.Text(), nullable=False, server_default="draft"),
    sa.Column("title", sa.Text(), nullable=False),
    sa.Column("language", sa.Text(), nullable=False),
    sa.Column("mode", sa.Text(), nullable=False),
    sa.Column("target_duration_ms", sa.BigInteger(), nullable=False),
    sa.Column("aspect_ratio", sa.Text(), nullable=False),
    sa.Column("export_settings", sa.JSON(), nullable=False),
    sa.Column("providers", sa.JSON(), nullable=False),
    sa.Column("budget_policy", sa.JSON(), nullable=False),
    sa.Column("approved_timeline_revision_id", sa.Text()),
    sa.Column("preset", sa.Text(), nullable=False, server_default="standard"),
    sa.Column(
        "titles_and_credits_within_target", sa.Boolean(), nullable=False, server_default=sa.true()
    ),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("version >= 1", name="ck_projects_version"),
    sa.CheckConstraint(
        "state IN ('draft', 'active', 'paused', 'archived')",
        name="ck_projects_state",
    ),
    sa.CheckConstraint("mode IN ('short', 'long')", name="ck_projects_mode"),
    sa.CheckConstraint(
        "aspect_ratio IN ('9:16', '16:9', '1:1')",
        name="ck_projects_aspect_ratio",
    ),
    sa.CheckConstraint(
        "target_duration_ms BETWEEN 1000 AND 3600000",
        name="ck_projects_duration",
    ),
    sa.CheckConstraint(
        "preset IN ('standard', 'telugu_short_film_900')", name="ck_projects_preset"
    ),
    sa.UniqueConstraint("owner_id", "id", name="uq_projects_owner_id_id"),
)

sa.Index("ix_projects_owner_updated", projects.c.owner_id, projects.c.updated_at, projects.c.id)

media_assets = sa.Table(
    "media_assets",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id")),
    sa.Column("owner_id", sa.Text(), nullable=False),
    sa.Column("scope", sa.Text(), nullable=False, server_default="project"),
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
    sa.Column("metadata", sa.JSON()),
    sa.Column("inspector_revision", sa.Text()),
    sa.Column("inspected_at", sa.DateTime(timezone=True)),
    sa.CheckConstraint("version >= 1", name="ck_media_assets_version"),
    sa.CheckConstraint(
        "(scope = 'project' AND project_id IS NOT NULL) OR "
        "(scope = 'library' AND project_id IS NULL)",
        name="ck_media_assets_scope",
    ),
    sa.CheckConstraint("kind IN ('image', 'audio', 'video')", name="ck_media_assets_kind"),
    sa.CheckConstraint("state IN ('ready', 'inspected')", name="ck_media_assets_state"),
    sa.CheckConstraint(
        "(state = 'ready' AND metadata IS NULL AND "
        "inspector_revision IS NULL AND inspected_at IS NULL) OR "
        "(state = 'inspected' AND metadata IS NOT NULL AND "
        "inspector_revision IS NOT NULL AND inspected_at IS NOT NULL)",
        name="ck_media_assets_inspection",
    ),
    sa.CheckConstraint("size_bytes > 0", name="ck_media_assets_size"),
    sa.CheckConstraint("char_length(sha256) = 64", name="ck_media_assets_sha256"),
    sa.CheckConstraint(
        "rights IN ('owned', 'licensed', 'permissioned', 'public_domain')",
        name="ck_media_assets_rights",
    ),
)

sa.Index(
    "ix_media_assets_owner_project_created",
    media_assets.c.owner_id,
    media_assets.c.project_id,
    media_assets.c.created_at,
    media_assets.c.id,
)

sa.Index(
    "ix_media_assets_owner_scope_created",
    media_assets.c.owner_id,
    media_assets.c.scope,
    media_assets.c.created_at,
    media_assets.c.id,
)

library_entities = sa.Table(
    "library_entities",
    metadata,
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

sa.Index(
    "ix_library_entities_owner_kind_updated",
    library_entities.c.owner_id,
    library_entities.c.kind,
    library_entities.c.updated_at,
    library_entities.c.id,
)

library_versions = sa.Table(
    "library_versions",
    metadata,
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

library_version_assets = sa.Table(
    "library_version_assets",
    metadata,
    sa.Column(
        "library_version_id", sa.Text(), sa.ForeignKey("library_versions.id"), nullable=False
    ),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("asset_id", sa.Text(), sa.ForeignKey("media_assets.id"), nullable=False),
    sa.Column("asset_version", sa.BigInteger(), nullable=False),
    sa.Column("asset_sha256", sa.String(64), nullable=False),
    sa.Column("role", sa.Text(), nullable=False),
    sa.Column("view_label", sa.Text()),
    sa.PrimaryKeyConstraint("library_version_id", "position"),
    sa.UniqueConstraint("library_version_id", "asset_id", name="uq_library_version_asset"),
    sa.CheckConstraint("position >= 0", name="ck_library_version_asset_position"),
    sa.CheckConstraint("asset_version >= 1", name="ck_library_version_asset_version"),
    sa.CheckConstraint(
        "role IN ('identity_appearance', 'location_or_prop', 'source_layer', "
        "'starting_frame', 'motion_performance', 'shot_guidance', 'review_only')",
        name="ck_library_version_asset_role",
    ),
    sa.CheckConstraint("char_length(asset_sha256) = 64", name="ck_library_version_asset_sha256"),
)

sa.Index(
    "ix_library_versions_owner_entity_number",
    library_versions.c.owner_id,
    library_versions.c.entity_id,
    library_versions.c.version_number,
)

film_bible_snapshots = sa.Table(
    "film_bible_snapshots",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
    sa.Column("owner_id", sa.Text(), nullable=False),
    sa.Column("revision", sa.BigInteger(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
    sa.Column("fingerprint", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
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

film_bible_pins = sa.Table(
    "film_bible_pins",
    metadata,
    sa.Column("snapshot_id", sa.Text(), sa.ForeignKey("film_bible_snapshots.id"), nullable=False),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("entity_id", sa.Text(), sa.ForeignKey("library_entities.id"), nullable=False),
    sa.Column(
        "library_version_id", sa.Text(), sa.ForeignKey("library_versions.id"), nullable=False
    ),
    sa.Column("library_version_number", sa.BigInteger(), nullable=False),
    sa.Column("version_kind", sa.Text(), nullable=False),
    sa.Column("version_fingerprint", sa.String(64), nullable=False),
    sa.Column("role", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("snapshot_id", "position"),
    sa.UniqueConstraint("snapshot_id", "entity_id", "role", name="uq_film_bible_pin_role"),
    sa.CheckConstraint("position >= 0", name="ck_film_bible_pin_position"),
    sa.CheckConstraint("library_version_number >= 1", name="ck_film_bible_pin_version"),
    sa.CheckConstraint(
        "version_kind IN ('identity', 'wardrobe', 'location_view', 'lighting_variant', "
        "'prop_variant', 'prop_state', 'shot_reference')",
        name="ck_film_bible_pin_kind",
    ),
    sa.CheckConstraint(
        "role IN ('character_identity', 'character_wardrobe', 'location_view', "
        "'location_lighting', 'prop_variant', 'prop_state', 'shot_reference')",
        name="ck_film_bible_pin_role",
    ),
    sa.CheckConstraint(
        "char_length(version_fingerprint) = 64", name="ck_film_bible_pin_fingerprint"
    ),
)

sa.Index(
    "ix_film_bible_owner_project_revision",
    film_bible_snapshots.c.owner_id,
    film_bible_snapshots.c.project_id,
    film_bible_snapshots.c.revision,
)

timeline_revisions = sa.Table(
    "timeline_revisions",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
    sa.Column("owner_id", sa.Text(), nullable=False),
    sa.Column("revision", sa.BigInteger(), nullable=False),
    sa.Column("duration_ms", sa.BigInteger(), nullable=False),
    sa.Column("items", sa.JSON(), nullable=False),
    sa.Column("fingerprint", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("project_id", "revision", name="uq_timeline_project_revision"),
    sa.CheckConstraint("revision >= 1", name="ck_timeline_revision"),
    sa.CheckConstraint("duration_ms BETWEEN 1000 AND 3600000", name="ck_timeline_duration"),
    sa.CheckConstraint("char_length(fingerprint) = 64", name="ck_timeline_fingerprint"),
)

caption_segments = sa.Table(
    "caption_segments",
    metadata,
    sa.Column("timeline_id", sa.Text(), sa.ForeignKey("timeline_revisions.id"), nullable=False),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("start_ms", sa.BigInteger(), nullable=False),
    sa.Column("end_ms", sa.BigInteger(), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("timeline_id", "position"),
    sa.CheckConstraint("position >= 0", name="ck_caption_position"),
    sa.CheckConstraint("start_ms >= 0 AND end_ms > start_ms", name="ck_caption_timing"),
    sa.CheckConstraint("char_length(text) BETWEEN 1 AND 500", name="ck_caption_text"),
)

sa.Index(
    "ix_timeline_owner_project_revision",
    timeline_revisions.c.owner_id,
    timeline_revisions.c.project_id,
    timeline_revisions.c.revision,
)

film_scenes = sa.Table(
    "film_scenes",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
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
    sa.UniqueConstraint("project_id", "position", name="uq_film_scene_position"),
    sa.CheckConstraint("version >= 1", name="ck_film_scene_version"),
    sa.CheckConstraint("target_duration_ms > 0", name="ck_film_scene_duration"),
    sa.CheckConstraint("char_length(content_fingerprint) = 64", name="ck_film_scene_fingerprint"),
)

film_shots = sa.Table(
    "film_shots",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("scene_id", sa.Text(), sa.ForeignKey("film_scenes.id"), nullable=False),
    sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
    sa.Column("owner_id", sa.Text(), nullable=False),
    sa.Column("version", sa.BigInteger(), nullable=False),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("target_duration_ms", sa.BigInteger(), nullable=False),
    sa.Column("description", sa.Text(), nullable=False),
    sa.Column("reference_workflow", sa.Text(), nullable=False),
    sa.Column("character_reference_asset_ids", sa.JSON(), nullable=False),
    sa.Column("dialogue_workflow", sa.Text(), nullable=False),
    sa.Column("storyboard_asset_id", sa.Text(), sa.ForeignKey("media_assets.id"), nullable=False),
    sa.Column("source_footage_asset_id", sa.Text(), sa.ForeignKey("media_assets.id")),
    sa.Column("recorded_dialogue_asset_id", sa.Text(), sa.ForeignKey("media_assets.id")),
    sa.Column("content_fingerprint", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
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
    sa.CheckConstraint("char_length(content_fingerprint) = 64", name="ck_film_shot_fingerprint"),
)

shot_binding_revisions = sa.Table(
    "shot_binding_revisions",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
    sa.Column("owner_id", sa.Text(), nullable=False),
    sa.Column("shot_id", sa.Text(), sa.ForeignKey("film_shots.id"), nullable=False),
    sa.Column("shot_version", sa.BigInteger(), nullable=False),
    sa.Column("revision", sa.BigInteger(), nullable=False),
    sa.Column(
        "film_bible_snapshot_id",
        sa.Text(),
        sa.ForeignKey("film_bible_snapshots.id"),
        nullable=False,
    ),
    sa.Column("fingerprint", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("shot_id", "revision", name="uq_shot_binding_revision"),
    sa.UniqueConstraint("owner_id", "id", name="uq_shot_binding_owner_id_id"),
    sa.CheckConstraint("shot_version >= 1", name="ck_shot_binding_shot_version"),
    sa.CheckConstraint("revision >= 1", name="ck_shot_binding_revision"),
    sa.CheckConstraint("char_length(fingerprint) = 64", name="ck_shot_binding_fingerprint"),
)

shot_library_bindings = sa.Table(
    "shot_library_bindings",
    metadata,
    sa.Column(
        "binding_revision_id",
        sa.Text(),
        sa.ForeignKey("shot_binding_revisions.id"),
        nullable=False,
    ),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("entity_id", sa.Text(), sa.ForeignKey("library_entities.id"), nullable=False),
    sa.Column(
        "library_version_id", sa.Text(), sa.ForeignKey("library_versions.id"), nullable=False
    ),
    sa.Column("library_version_number", sa.BigInteger(), nullable=False),
    sa.Column("version_kind", sa.Text(), nullable=False),
    sa.Column("version_fingerprint", sa.String(64), nullable=False),
    sa.Column("role", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("binding_revision_id", "position"),
    sa.UniqueConstraint(
        "binding_revision_id", "entity_id", "role", name="uq_shot_library_binding_role"
    ),
    sa.CheckConstraint("position >= 0", name="ck_shot_library_binding_position"),
    sa.CheckConstraint("library_version_number >= 1", name="ck_shot_library_binding_version"),
    sa.CheckConstraint(
        "version_kind IN ('identity', 'wardrobe', 'location_view', 'lighting_variant', "
        "'prop_variant', 'prop_state', 'shot_reference')",
        name="ck_shot_library_binding_kind",
    ),
    sa.CheckConstraint(
        "role IN ('character_identity', 'character_wardrobe', 'location_view', "
        "'location_lighting', 'prop_variant', 'prop_state', 'shot_reference')",
        name="ck_shot_library_binding_role",
    ),
    sa.CheckConstraint(
        "char_length(version_fingerprint) = 64",
        name="ck_shot_library_binding_fingerprint",
    ),
)

sa.Index(
    "ix_shot_bindings_owner_project_shot_revision",
    shot_binding_revisions.c.owner_id,
    shot_binding_revisions.c.project_id,
    shot_binding_revisions.c.shot_id,
    shot_binding_revisions.c.revision,
)

starting_frame_compositions = sa.Table(
    "starting_frame_compositions",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
    sa.Column("owner_id", sa.Text(), nullable=False),
    sa.Column("shot_id", sa.Text(), sa.ForeignKey("film_shots.id"), nullable=False),
    sa.Column("shot_version", sa.BigInteger(), nullable=False),
    sa.Column(
        "shot_binding_revision_id",
        sa.Text(),
        sa.ForeignKey("shot_binding_revisions.id"),
        nullable=False,
    ),
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
    sa.Column("visible_speaker_entity_id", sa.Text(), sa.ForeignKey("library_entities.id")),
    sa.Column("fingerprint", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("rendered_asset_id", sa.Text(), sa.ForeignKey("media_assets.id")),
    sa.Column("rendered_asset_version", sa.BigInteger()),
    sa.Column("rendered_sha256", sa.String(64)),
    sa.Column("renderer_revision", sa.Text()),
    sa.Column("rendered_at", sa.DateTime(timezone=True)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("shot_id", "revision", name="uq_starting_frame_shot_revision"),
    sa.UniqueConstraint("owner_id", "id", name="uq_starting_frame_owner_id_id"),
    sa.CheckConstraint("shot_version >= 1 AND revision >= 1", name="ck_starting_frame_revisions"),
    sa.CheckConstraint("mode IN ('composed_upload', 'layered')", name="ck_starting_frame_mode"),
    sa.CheckConstraint(
        "status IN ('draft', 'rendered', 'approved')", name="ck_starting_frame_status"
    ),
    sa.CheckConstraint(
        "canvas_width BETWEEN 64 AND 4096 AND canvas_height BETWEEN 64 AND 4096 "
        "AND canvas_width * canvas_height <= 16777216",
        name="ck_starting_frame_canvas",
    ),
    sa.CheckConstraint("char_length(background_rgba) = 9", name="ck_starting_frame_background"),
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
        "AND renderer_revision IS NOT NULL AND rendered_at IS NOT NULL AND approved_at IS NULL) "
        "OR (status = 'approved' AND rendered_asset_id IS NOT NULL "
        "AND rendered_asset_version IS NOT NULL AND rendered_sha256 IS NOT NULL "
        "AND renderer_revision IS NOT NULL AND rendered_at IS NOT NULL "
        "AND approved_at IS NOT NULL)",
        name="ck_starting_frame_lifecycle",
    ),
)

starting_frame_layers = sa.Table(
    "starting_frame_layers",
    metadata,
    sa.Column(
        "composition_id",
        sa.Text(),
        sa.ForeignKey("starting_frame_compositions.id"),
        nullable=False,
    ),
    sa.Column("position", sa.Integer(), nullable=False),
    sa.Column("role", sa.Text(), nullable=False),
    sa.Column("source_asset_id", sa.Text(), sa.ForeignKey("media_assets.id"), nullable=False),
    sa.Column("source_asset_version", sa.BigInteger(), nullable=False),
    sa.Column("source_asset_sha256", sa.String(64), nullable=False),
    sa.Column("source_scope", sa.Text(), nullable=False),
    sa.Column("source_library_entity_id", sa.Text(), sa.ForeignKey("library_entities.id")),
    sa.Column("source_library_version_id", sa.Text(), sa.ForeignKey("library_versions.id")),
    sa.Column("source_library_version_fingerprint", sa.String(64)),
    sa.Column("mask_asset_id", sa.Text(), sa.ForeignKey("media_assets.id")),
    sa.Column("mask_asset_version", sa.BigInteger()),
    sa.Column("mask_asset_sha256", sa.String(64)),
    sa.Column("mask_scope", sa.Text()),
    sa.Column("mask_library_entity_id", sa.Text(), sa.ForeignKey("library_entities.id")),
    sa.Column("mask_library_version_id", sa.Text(), sa.ForeignKey("library_versions.id")),
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

sa.Index(
    "ix_starting_frames_owner_project_shot_revision",
    starting_frame_compositions.c.owner_id,
    starting_frame_compositions.c.project_id,
    starting_frame_compositions.c.shot_id,
    starting_frame_compositions.c.revision,
)

reference_video_guidance = sa.Table(
    "reference_video_guidance",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
    sa.Column("owner_id", sa.Text(), nullable=False),
    sa.Column("shot_id", sa.Text(), sa.ForeignKey("film_shots.id"), nullable=False),
    sa.Column("shot_version", sa.BigInteger(), nullable=False),
    sa.Column(
        "shot_binding_revision_id",
        sa.Text(),
        sa.ForeignKey("shot_binding_revisions.id"),
        nullable=False,
    ),
    sa.Column("revision", sa.BigInteger(), nullable=False),
    sa.Column("purpose", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
    sa.Column("source_asset_id", sa.Text(), sa.ForeignKey("media_assets.id"), nullable=False),
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
    sa.Column("source_library_entity_id", sa.Text(), sa.ForeignKey("library_entities.id")),
    sa.Column("source_library_version_id", sa.Text(), sa.ForeignKey("library_versions.id")),
    sa.Column("source_library_version_fingerprint", sa.String(64)),
    sa.Column("trim_start_ms", sa.BigInteger(), nullable=False),
    sa.Column("trim_end_ms", sa.BigInteger(), nullable=False),
    sa.Column("guidance_notes", sa.Text(), nullable=False),
    sa.Column("fingerprint", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
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
    sa.CheckConstraint("source_asset_version >= 1", name="ck_reference_guidance_source_version"),
    sa.CheckConstraint(
        "char_length(source_asset_sha256) = 64", name="ck_reference_guidance_source_sha"
    ),
    sa.CheckConstraint("source_media_type LIKE 'video/%'", name="ck_reference_guidance_media_type"),
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
    sa.CheckConstraint("char_length(guidance_notes) <= 2000", name="ck_reference_guidance_notes"),
    sa.CheckConstraint("char_length(fingerprint) = 64", name="ck_reference_guidance_fingerprint"),
    sa.CheckConstraint(
        "(status = 'draft' AND approved_at IS NULL) OR "
        "(status = 'approved' AND approved_at IS NOT NULL)",
        name="ck_reference_guidance_approval",
    ),
)

sa.Index(
    "ix_reference_guidance_owner_project_shot_revision",
    reference_video_guidance.c.owner_id,
    reference_video_guidance.c.project_id,
    reference_video_guidance.c.shot_id,
    reference_video_guidance.c.revision,
)

film_approvals = sa.Table(
    "film_approvals",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
    sa.Column("scene_id", sa.Text(), sa.ForeignKey("film_scenes.id")),
    sa.Column("shot_id", sa.Text(), sa.ForeignKey("film_shots.id")),
    sa.Column("owner_id", sa.Text(), nullable=False),
    sa.Column("stage", sa.Text(), nullable=False),
    sa.Column("subject_fingerprint", sa.String(64), nullable=False),
    sa.Column("evidence_asset_id", sa.Text(), sa.ForeignKey("media_assets.id")),
    sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
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
        "'lip_sync', 'adjacent_shot_continuity', 'rough_cut', 'dialogue_90_seconds', "
        "'sequence_180_seconds', 'film_900_seconds', 'final_sound_mix')",
        name="ck_film_approval_stage",
    ),
)

sa.Index(
    "ix_film_scenes_project_position",
    film_scenes.c.owner_id,
    film_scenes.c.project_id,
    film_scenes.c.position,
)
sa.Index(
    "ix_film_shots_scene_position",
    film_shots.c.owner_id,
    film_shots.c.scene_id,
    film_shots.c.position,
)

sa.Index(
    "ix_generation_jobs_claim",
    generation_jobs.c.created_at,
    generation_jobs.c.id,
    postgresql_where=generation_jobs.c.status == "queued",
)
sa.Index(
    "ix_generation_jobs_list",
    generation_jobs.c.created_at,
    generation_jobs.c.id,
)
sa.Index(
    "ix_generation_jobs_expired_lease",
    generation_jobs.c.lease_expires_at,
    postgresql_where=generation_jobs.c.status == "running",
)
