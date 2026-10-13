import {
  ERROR_CODES,
  type ApiError,
  type AffectedShotList,
  type ControlledGenerationDraft,
  type ControlledGenerationProvider,
  type ControlledGenerationProviderList,
  type ErrorCode,
  type FilmApproval,
  type FilmApprovalRequest,
  type FilmReadiness,
  type FilmScene,
  type FilmSceneSave,
  type FilmShot,
  type FilmShotSave,
  type FilmWorkspace,
  type FilmBibleNameResolution,
  type FilmBiblePinSelection,
  type FilmBibleSnapshot,
  type FilmBibleSnapshotList,
  type GenerationMode,
  type GenerationRequest,
  type GenerationResult,
  type Health,
  type ImageGenerationDraft,
  type ImageGenerationJob,
  type ImageGenerationProvider,
  type Job,
  type JobFailure,
  type JobPage,
  type JobStatus,
  type LibraryEntity,
  type LibraryEntityDraft,
  type LibraryEntityKind,
  type LibraryEntityList,
  type LibraryVersion,
  type LibraryVersionDraft,
  type LibraryVersionList,
  type ModelCapability,
  type ModelList,
  type MediaAsset,
  type MediaAssetList,
  type AssetKind,
  type RightsDeclaration,
  type RoughCutJob,
  type RoughCutProvider,
  type NormalizedRequest,
  type Progress,
  type Project,
  type ProjectDraft,
  type ProjectList,
  type ReferenceVideoGuidance,
  type ReferenceVideoGuidanceDraft,
  type ReferenceVideoGuidanceList,
  type Resolution,
  type ShotBindingRevision,
  type ShotBindingRevisionDraft,
  type ShotBindingRevisionList,
  type StartingFrameComposition,
  type StartingFrameCompositionList,
  type StartingFrameDraft,
  type TimelineDraft,
  type TimelineRenderJob,
  type TimelineRenderProvider,
  type TimelineRevision,
  type TimelineRevisionList,
} from './contracts'

export interface ListJobsOptions {
  limit?: number
  cursor?: string
  status?: JobStatus
  signal?: AbortSignal
}

export interface ApiClientOptions {
  baseUrl?: string
  fetch?: typeof globalThis.fetch
}

export type ApiClientErrorKind = 'api' | 'network' | 'invalid_response'

export interface ApiClientErrorOptions {
  kind: ApiClientErrorKind
  status: number | null
  code: ErrorCode
  message: string
  retryable: boolean
  correlation_id?: string | null
  job_id?: string | null
  fields?: string[]
}

const errorCodeSet: ReadonlySet<string> = new Set(ERROR_CODES)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isErrorCode(value: unknown): value is ErrorCode {
  return typeof value === 'string' && errorCodeSet.has(value)
}

function isGenerationMode(value: unknown): value is GenerationMode {
  return value === 'text_to_video'
}

function isJobStatus(value: unknown): value is JobStatus {
  return (
    value === 'queued' ||
    value === 'running' ||
    value === 'succeeded' ||
    value === 'failed' ||
    value === 'cancelled'
  )
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isInteger(value: unknown): value is number {
  return isFiniteNumber(value) && Number.isInteger(value)
}

function isPositiveInteger(value: unknown): value is number {
  return isInteger(value) && value > 0
}

function isNonNegativeInteger(value: unknown): value is number {
  return isInteger(value) && value >= 0
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isStringOrNull(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isUtcTimestamp(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /(?:Z|[+-]00:00)$/u.test(value) &&
    Number.isFinite(Date.parse(value))
  )
}

function isNullablePositiveInteger(value: unknown): value is number | null {
  return value === null || isPositiveInteger(value)
}

function isProject(value: unknown): value is Project {
  if (!isRecord(value)) {
    return false
  }
  const exportSettings = value.export_settings
  const providers = value.providers
  const budget = value.budget_policy
  return (
    isNonEmptyString(value.id) &&
    isPositiveInteger(value.version) &&
    ['draft', 'active', 'paused', 'archived'].includes(String(value.state)) &&
    isNonEmptyString(value.title) &&
    isNonEmptyString(value.language) &&
    (value.mode === 'short' || value.mode === 'long') &&
    (value.preset === 'standard' || value.preset === 'telugu_short_film_900') &&
    typeof value.titles_and_credits_within_target === 'boolean' &&
    isPositiveInteger(value.target_duration_ms) &&
    value.target_duration_ms <= 3_600_000 &&
    (value.aspect_ratio === '9:16' ||
      value.aspect_ratio === '16:9' ||
      value.aspect_ratio === '1:1') &&
    isRecord(exportSettings) &&
    isPositiveInteger(exportSettings.width) &&
    isPositiveInteger(exportSettings.height) &&
    isPositiveInteger(exportSettings.fps_numerator) &&
    isPositiveInteger(exportSettings.fps_denominator) &&
    isRecord(providers) &&
    isNonEmptyString(providers.video) &&
    isStringOrNull(providers.speech) &&
    isStringOrNull(providers.lip_sync) &&
    isStringOrNull(providers.caption_alignment) &&
    isRecord(budget) &&
    isNullablePositiveInteger(budget.max_compute_seconds) &&
    isNullablePositiveInteger(budget.max_cost_micros) &&
    isNonNegativeInteger(budget.automatic_expensive_retries) &&
    budget.automatic_expensive_retries <= 3 &&
    isStringOrNull(value.approved_timeline_revision_id) &&
    isUtcTimestamp(value.created_at) &&
    isUtcTimestamp(value.updated_at) &&
    Date.parse(value.updated_at) >= Date.parse(value.created_at)
  )
}

function isProjectList(value: unknown): value is ProjectList {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isProject)
}

function isMediaAsset(value: unknown): value is MediaAsset {
  if (!isRecord(value)) return false
  const metadata = value.metadata
  const metadataValid =
    metadata === null ||
    (isRecord(metadata) &&
      isNonEmptyString(metadata.format_name) &&
      isPositiveInteger(metadata.duration_ms) &&
      (metadata.width === null || isPositiveInteger(metadata.width)) &&
      (metadata.height === null || isPositiveInteger(metadata.height)) &&
      (metadata.frame_rate_numerator === null ||
        isPositiveInteger(metadata.frame_rate_numerator)) &&
      (metadata.frame_rate_denominator === null ||
        isPositiveInteger(metadata.frame_rate_denominator)) &&
      (metadata.sample_rate === null || isPositiveInteger(metadata.sample_rate)) &&
      (metadata.channels === null || isPositiveInteger(metadata.channels)) &&
      (metadata.sample_count === null || isPositiveInteger(metadata.sample_count)))
  return (
    isNonEmptyString(value.id) &&
    (value.project_id === null || isNonEmptyString(value.project_id)) &&
    (value.scope === 'project' || value.scope === 'library') &&
    ((value.scope === 'project' && isNonEmptyString(value.project_id)) ||
      (value.scope === 'library' && value.project_id === null)) &&
    isPositiveInteger(value.version) &&
    ['image', 'audio', 'video'].includes(String(value.kind)) &&
    (value.state === 'ready' || value.state === 'inspected') &&
    isNonEmptyString(value.original_filename) &&
    isNonEmptyString(value.media_type) &&
    isPositiveInteger(value.size_bytes) &&
    typeof value.sha256 === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.sha256) &&
    ['owned', 'licensed', 'permissioned', 'public_domain'].includes(String(value.rights)) &&
    isUtcTimestamp(value.created_at) &&
    metadataValid &&
    isStringOrNull(value.inspector_revision) &&
    (value.inspected_at === null || isUtcTimestamp(value.inspected_at)) &&
    ((value.state === 'ready' &&
      value.metadata === null &&
      value.inspector_revision === null &&
      value.inspected_at === null) ||
      (value.state === 'inspected' &&
        value.metadata !== null &&
        isNonEmptyString(value.inspector_revision) &&
        isUtcTimestamp(value.inspected_at)))
  )
}

function isMediaAssetList(value: unknown): value is MediaAssetList {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isMediaAsset)
}

const libraryEntityKinds = new Set(['character', 'location', 'prop', 'shot_reference'])
const libraryVersionKinds = new Set([
  'identity',
  'wardrobe',
  'location_view',
  'lighting_variant',
  'prop_variant',
  'prop_state',
  'shot_reference',
])
const referenceRoles = new Set([
  'identity_appearance',
  'location_or_prop',
  'source_layer',
  'starting_frame',
  'motion_performance',
  'shot_guidance',
  'review_only',
])
const filmBiblePinRoles = new Set([
  'character_identity',
  'character_wardrobe',
  'location_view',
  'location_lighting',
  'prop_variant',
  'prop_state',
  'shot_reference',
])

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isNonEmptyString)
}

function isLibraryEntity(value: unknown): value is LibraryEntity {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    libraryEntityKinds.has(String(value.kind)) &&
    isPositiveInteger(value.metadata_version) &&
    isNonEmptyString(value.display_name) &&
    isStringArray(value.aliases) &&
    isUtcTimestamp(value.created_at) &&
    isUtcTimestamp(value.updated_at)
  )
}

function isLibraryEntityList(value: unknown): value is LibraryEntityList {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isLibraryEntity)
}

function isLibraryBinding(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.asset_id) &&
    isPositiveInteger(value.asset_version) &&
    typeof value.asset_sha256 === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.asset_sha256) &&
    referenceRoles.has(String(value.role)) &&
    isStringOrNull(value.view_label)
  )
}

function isLibraryVersion(value: unknown): value is LibraryVersion {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.entity_id) &&
    isPositiveInteger(value.version_number) &&
    libraryVersionKinds.has(String(value.kind)) &&
    ['draft', 'approved', 'archived'].includes(String(value.status)) &&
    isNonEmptyString(value.label) &&
    typeof value.notes === 'string' &&
    typeof value.invariants === 'string' &&
    typeof value.state_notes === 'string' &&
    isStringOrNull(value.voice_profile_id) &&
    typeof value.rights_statement === 'string' &&
    Array.isArray(value.assets) &&
    value.assets.length > 0 &&
    value.assets.every(isLibraryBinding) &&
    typeof value.fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.fingerprint) &&
    isUtcTimestamp(value.created_at) &&
    (value.approved_at === null || isUtcTimestamp(value.approved_at))
  )
}

function isLibraryVersionList(value: unknown): value is LibraryVersionList {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isLibraryVersion)
}

function isFilmBiblePin(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.entity_id) &&
    isNonEmptyString(value.library_version_id) &&
    isPositiveInteger(value.library_version_number) &&
    libraryVersionKinds.has(String(value.version_kind)) &&
    typeof value.version_fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.version_fingerprint) &&
    filmBiblePinRoles.has(String(value.role))
  )
}

function isFilmBibleSnapshot(value: unknown): value is FilmBibleSnapshot {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.project_id) &&
    isPositiveInteger(value.revision) &&
    (value.status === 'draft' || value.status === 'approved') &&
    Array.isArray(value.pins) &&
    value.pins.length > 0 &&
    value.pins.every(isFilmBiblePin) &&
    typeof value.fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.fingerprint) &&
    isUtcTimestamp(value.created_at) &&
    (value.approved_at === null || isUtcTimestamp(value.approved_at))
  )
}

function isFilmBibleSnapshotList(value: unknown): value is FilmBibleSnapshotList {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isFilmBibleSnapshot)
}

function isFilmBibleNameResolution(value: unknown): value is FilmBibleNameResolution {
  return (
    isRecord(value) &&
    isNonEmptyString(value.mention) &&
    ['resolved', 'ambiguous', 'unresolved'].includes(String(value.status)) &&
    Array.isArray(value.candidates) &&
    value.candidates.every(
      (candidate) =>
        isRecord(candidate) &&
        isNonEmptyString(candidate.entity_id) &&
        isNonEmptyString(candidate.display_name) &&
        libraryEntityKinds.has(String(candidate.entity_kind)) &&
        Array.isArray(candidate.pins) &&
        candidate.pins.every(isFilmBiblePin),
    )
  )
}

function isShotBindingRevision(value: unknown): value is ShotBindingRevision {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.project_id) &&
    isNonEmptyString(value.shot_id) &&
    isPositiveInteger(value.shot_version) &&
    isPositiveInteger(value.revision) &&
    isNonEmptyString(value.film_bible_snapshot_id) &&
    Array.isArray(value.bindings) &&
    value.bindings.length > 0 &&
    value.bindings.every(isFilmBiblePin) &&
    typeof value.fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.fingerprint) &&
    isUtcTimestamp(value.created_at)
  )
}

function isShotBindingRevisionList(value: unknown): value is ShotBindingRevisionList {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isShotBindingRevision)
}

function isAffectedShotList(value: unknown): value is AffectedShotList {
  return (
    isRecord(value) &&
    isNonEmptyString(value.entity_id) &&
    isNonEmptyString(value.library_version_id) &&
    isStringArray(value.shot_ids)
  )
}

function isCompositionAsset(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.asset_id) &&
    isPositiveInteger(value.asset_version) &&
    typeof value.asset_sha256 === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.asset_sha256) &&
    (value.scope === 'project' || value.scope === 'library') &&
    isStringOrNull(value.library_entity_id) &&
    isStringOrNull(value.library_version_id) &&
    isStringOrNull(value.library_version_fingerprint) &&
    ((value.scope === 'project' &&
      value.library_entity_id === null &&
      value.library_version_id === null &&
      value.library_version_fingerprint === null) ||
      (value.scope === 'library' &&
        isNonEmptyString(value.library_entity_id) &&
        isNonEmptyString(value.library_version_id) &&
        typeof value.library_version_fingerprint === 'string' &&
        /^[0-9a-f]{64}$/u.test(value.library_version_fingerprint)))
  )
}

function isLayerTransform(value: unknown): boolean {
  if (!isRecord(value)) return false
  const crop = value.crop
  return (
    isInteger(value.x) &&
    isInteger(value.y) &&
    isPositiveInteger(value.width) &&
    isPositiveInteger(value.height) &&
    isInteger(value.rotation_millidegrees) &&
    isNonNegativeInteger(value.opacity_basis_points) &&
    value.opacity_basis_points <= 10_000 &&
    ['contain', 'cover', 'stretch'].includes(String(value.fit)) &&
    (crop === null ||
      (isRecord(crop) &&
        isNonNegativeInteger(crop.x) &&
        isNonNegativeInteger(crop.y) &&
        isPositiveInteger(crop.width) &&
        isPositiveInteger(crop.height)))
  )
}

function isStartingFrameLayer(value: unknown): boolean {
  return (
    isRecord(value) &&
    ['starting_frame', 'background', 'character', 'prop', 'overlay'].includes(String(value.role)) &&
    isCompositionAsset(value.source) &&
    isLayerTransform(value.transform) &&
    (value.mask === null || isCompositionAsset(value.mask))
  )
}

function isStartingFrameComposition(value: unknown): value is StartingFrameComposition {
  if (!isRecord(value)) return false
  const rendered = value.status === 'rendered' || value.status === 'approved'
  return (
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.project_id) &&
    isNonEmptyString(value.shot_id) &&
    isPositiveInteger(value.shot_version) &&
    isNonEmptyString(value.shot_binding_revision_id) &&
    isPositiveInteger(value.revision) &&
    (value.mode === 'composed_upload' || value.mode === 'layered') &&
    ['draft', 'rendered', 'approved'].includes(String(value.status)) &&
    isPositiveInteger(value.canvas_width) &&
    isPositiveInteger(value.canvas_height) &&
    typeof value.background_rgba === 'string' &&
    /^#[0-9a-f]{8}$/u.test(value.background_rgba) &&
    ['owned', 'licensed', 'permissioned', 'public_domain'].includes(String(value.output_rights)) &&
    typeof value.framing_notes === 'string' &&
    typeof value.pose_notes === 'string' &&
    typeof value.action_notes === 'string' &&
    typeof value.lighting_notes === 'string' &&
    isStringOrNull(value.visible_speaker_entity_id) &&
    Array.isArray(value.layers) &&
    value.layers.length > 0 &&
    value.layers.every(isStartingFrameLayer) &&
    typeof value.fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.fingerprint) &&
    isUtcTimestamp(value.created_at) &&
    (rendered
      ? isNonEmptyString(value.rendered_asset_id) &&
        isPositiveInteger(value.rendered_asset_version) &&
        typeof value.rendered_sha256 === 'string' &&
        /^[0-9a-f]{64}$/u.test(value.rendered_sha256) &&
        isNonEmptyString(value.renderer_revision) &&
        isUtcTimestamp(value.rendered_at) &&
        isNonEmptyString(value.preview_url)
      : value.rendered_asset_id === null &&
        value.rendered_asset_version === null &&
        value.rendered_sha256 === null &&
        value.renderer_revision === null &&
        value.rendered_at === null &&
        value.preview_url === null) &&
    (value.status === 'approved' ? isUtcTimestamp(value.approved_at) : value.approved_at === null)
  )
}

function isStartingFrameCompositionList(value: unknown): value is StartingFrameCompositionList {
  return (
    isRecord(value) && Array.isArray(value.items) && value.items.every(isStartingFrameComposition)
  )
}

function isReferenceVideoSource(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.asset_id) &&
    isPositiveInteger(value.asset_version) &&
    typeof value.asset_sha256 === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.asset_sha256) &&
    isNonEmptyString(value.media_type) &&
    value.media_type.startsWith('video/') &&
    (value.scope === 'project' || value.scope === 'library') &&
    isNonEmptyString(value.inspector_revision) &&
    isPositiveInteger(value.duration_ms) &&
    isPositiveInteger(value.width) &&
    isPositiveInteger(value.height) &&
    isPositiveInteger(value.frame_rate_numerator) &&
    isPositiveInteger(value.frame_rate_denominator) &&
    isStringOrNull(value.library_entity_id) &&
    isStringOrNull(value.library_version_id) &&
    (value.library_version_fingerprint === null ||
      (typeof value.library_version_fingerprint === 'string' &&
        /^[0-9a-f]{64}$/u.test(value.library_version_fingerprint)))
  )
}

function isReferenceVideoGuidance(value: unknown): value is ReferenceVideoGuidance {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.project_id) &&
    isNonEmptyString(value.shot_id) &&
    isPositiveInteger(value.shot_version) &&
    isNonEmptyString(value.shot_binding_revision_id) &&
    isPositiveInteger(value.revision) &&
    ['motion_performance', 'shot_guidance', 'review_only'].includes(String(value.purpose)) &&
    isReferenceVideoSource(value.source) &&
    isNonNegativeInteger(value.trim_start_ms) &&
    isPositiveInteger(value.trim_end_ms) &&
    value.trim_end_ms > value.trim_start_ms &&
    typeof value.guidance_notes === 'string' &&
    (value.status === 'draft' || value.status === 'approved') &&
    typeof value.fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.fingerprint) &&
    isUtcTimestamp(value.created_at) &&
    (value.status === 'approved'
      ? isUtcTimestamp(value.approved_at)
      : value.approved_at === null) &&
    isNonEmptyString(value.preview_url)
  )
}

function isReferenceVideoGuidanceList(value: unknown): value is ReferenceVideoGuidanceList {
  return (
    isRecord(value) && Array.isArray(value.items) && value.items.every(isReferenceVideoGuidance)
  )
}

function isSha256(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{64}$/u.test(value)
}

function isImageGenerationProvider(value: unknown): value is ImageGenerationProvider {
  return (
    isRecord(value) &&
    isNonEmptyString(value.backend) &&
    isNonEmptyString(value.backend_revision) &&
    isNonEmptyString(value.model) &&
    isNonEmptyString(value.display_name) &&
    value.task === 'ti2v-5B' &&
    isPositiveInteger(value.area_width) &&
    isPositiveInteger(value.area_height) &&
    isPositiveInteger(value.frame_count) &&
    typeof value.enabled === 'boolean' &&
    isNonEmptyString(value.runtime_state) &&
    isStringOrNull(value.unavailable_reason) &&
    (value.enabled ? value.unavailable_reason === null : isNonEmptyString(value.unavailable_reason))
  )
}

function isControlledGenerationProvider(value: unknown): value is ControlledGenerationProvider {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.backend) &&
    isNonEmptyString(value.backend_revision) &&
    isNonEmptyString(value.model) &&
    isNonEmptyString(value.display_name) &&
    isNonEmptyString(value.task) &&
    ['vace_performance_transfer', 'animate_character', 'animate_replacement'].includes(
      String(value.operation),
    ) &&
    isPositiveInteger(value.area_width) &&
    isPositiveInteger(value.area_height) &&
    isPositiveInteger(value.frame_count) &&
    isPositiveInteger(value.maximum_guidance_ms) &&
    typeof value.preserves_starting_frame_environment === 'boolean' &&
    typeof value.enabled === 'boolean' &&
    isNonEmptyString(value.runtime_state) &&
    isStringOrNull(value.unavailable_reason) &&
    (value.enabled ? value.unavailable_reason === null : isNonEmptyString(value.unavailable_reason))
  )
}

function isControlledGenerationProviderList(
  value: unknown,
): value is ControlledGenerationProviderList {
  return (
    isRecord(value) &&
    Array.isArray(value.items) &&
    value.items.every(isControlledGenerationProvider)
  )
}

function isImageGenerationJob(value: unknown): value is ImageGenerationJob {
  if (!isRecord(value) || !isRecord(value.request) || !isRecord(value.conditioning)) return false
  const request = value.request
  const conditioning = value.conditioning
  const result = value.result
  const evidence = value.conditioning_evidence
  const failure = value.failure
  const reference = conditioning.reference_video
  const referenceValid =
    reference === null ||
    (isRecord(reference) &&
      isNonEmptyString(reference.guidance_id) &&
      isPositiveInteger(reference.guidance_revision) &&
      isSha256(reference.guidance_fingerprint) &&
      ['motion_performance', 'shot_guidance', 'review_only'].includes(String(reference.purpose)) &&
      isNonEmptyString(reference.source_asset_id) &&
      isPositiveInteger(reference.source_asset_version) &&
      isSha256(reference.source_asset_sha256) &&
      isNonNegativeInteger(reference.trim_start_ms) &&
      isPositiveInteger(reference.trim_end_ms) &&
      reference.trim_end_ms > reference.trim_start_ms &&
      ['vace_performance_transfer', 'animate_character', 'animate_replacement'].includes(
        String(reference.operation),
      ) &&
      typeof reference.preserve_environment === 'boolean' &&
      isSha256(reference.constraint_plan_fingerprint))
  return (
    isNonEmptyString(value.id) &&
    isJobStatus(value.status) &&
    isUtcTimestamp(value.created_at) &&
    isUtcTimestamp(value.updated_at) &&
    (value.started_at === null || isUtcTimestamp(value.started_at)) &&
    (value.completed_at === null || isUtcTimestamp(value.completed_at)) &&
    isNonEmptyString(value.idempotency_key) &&
    isNonEmptyString(request.prompt) &&
    isNonEmptyString(request.model) &&
    isPositiveInteger(request.area_width) &&
    isPositiveInteger(request.area_height) &&
    isPositiveInteger(request.frame_count) &&
    typeof request.seed === 'string' &&
    /^-?[0-9]+$/u.test(request.seed) &&
    isNonEmptyString(conditioning.project_id) &&
    isNonEmptyString(conditioning.shot_id) &&
    isPositiveInteger(conditioning.shot_version) &&
    isNonEmptyString(conditioning.composition_id) &&
    isPositiveInteger(conditioning.composition_revision) &&
    isSha256(conditioning.composition_fingerprint) &&
    isNonEmptyString(conditioning.source_asset_id) &&
    isPositiveInteger(conditioning.source_asset_version) &&
    isSha256(conditioning.source_asset_sha256) &&
    isPositiveInteger(conditioning.source_width) &&
    isPositiveInteger(conditioning.source_height) &&
    isSha256(conditioning.manifest_fingerprint) &&
    referenceValid &&
    isStringOrNull(value.backend) &&
    isStringOrNull(value.backend_revision) &&
    (value.progress === null || isProgress(value.progress)) &&
    (evidence === null ||
      (isRecord(evidence) &&
        isSha256(evidence.source_sha256) &&
        isSha256(evidence.derivative_sha256) &&
        isPositiveInteger(evidence.derivative_width) &&
        isPositiveInteger(evidence.derivative_height) &&
        (evidence.reference_source_sha256 === null || isSha256(evidence.reference_source_sha256)) &&
        (evidence.reference_derivative_sha256 === null ||
          isSha256(evidence.reference_derivative_sha256)) &&
        (evidence.control_fingerprint === null || isSha256(evidence.control_fingerprint)) &&
        ((reference === null &&
          evidence.reference_source_sha256 === null &&
          evidence.reference_derivative_sha256 === null &&
          evidence.control_fingerprint === null) ||
          (reference !== null &&
            isSha256(evidence.reference_source_sha256) &&
            isSha256(evidence.reference_derivative_sha256) &&
            isSha256(evidence.control_fingerprint))))) &&
    (result === null ||
      (isRecord(result) &&
        result.media_type === 'video/mp4' &&
        isNonEmptyString(result.download_url) &&
        isPositiveInteger(result.width) &&
        isPositiveInteger(result.height) &&
        result.frame_count === request.frame_count &&
        (result.duration_seconds === null ||
          (isFiniteNumber(result.duration_seconds) && result.duration_seconds > 0)) &&
        isPositiveInteger(result.size_bytes) &&
        isSha256(result.sha256) &&
        isUtcTimestamp(result.created_at))) &&
    (failure === null ||
      (isRecord(failure) &&
        isErrorCode(failure.code) &&
        isNonEmptyString(failure.message) &&
        typeof failure.retryable === 'boolean' &&
        isNonEmptyString(failure.correlation_id)))
  )
}

function isTimelineItem(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !['video', 'image', 'audio', 'title_card'].includes(String(value.kind)) ||
    !isNonNegativeInteger(value.start_ms) ||
    !isPositiveInteger(value.duration_ms) ||
    !isNonNegativeInteger(value.layer)
  ) {
    return false
  }
  return value.kind === 'title_card'
    ? value.asset_id === null && isNonEmptyString(value.text)
    : isNonEmptyString(value.asset_id) && value.text === null
}

function isCaption(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonNegativeInteger(value.start_ms) &&
    isPositiveInteger(value.end_ms) &&
    value.end_ms > value.start_ms &&
    isNonEmptyString(value.text)
  )
}

function isTimelineRevision(value: unknown): value is TimelineRevision {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.project_id) &&
    isPositiveInteger(value.revision) &&
    isPositiveInteger(value.duration_ms) &&
    Array.isArray(value.items) &&
    value.items.length > 0 &&
    value.items.every(isTimelineItem) &&
    Array.isArray(value.captions) &&
    value.captions.every(isCaption) &&
    typeof value.fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.fingerprint) &&
    isUtcTimestamp(value.created_at) &&
    (value.approved_at === null || isUtcTimestamp(value.approved_at))
  )
}

function isTimelineRevisionList(value: unknown): value is TimelineRevisionList {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isTimelineRevision)
}

const approvalStages = new Set([
  'character_references',
  'identity_workflow',
  'telugu_script',
  'pronunciation',
  'voice_performance',
  'storyboard',
  'visual_performance',
  'lip_sync',
  'adjacent_shot_continuity',
  'rough_cut',
  'dialogue_90_seconds',
  'sequence_180_seconds',
  'film_900_seconds',
  'final_sound_mix',
])

function isOptionalStringOrNull(value: unknown): boolean {
  return value === undefined || value === null || isNonEmptyString(value)
}

function isFilmSceneSave(value: unknown): value is FilmSceneSave {
  if (!isRecord(value) || !isRecord(value.continuity)) return false
  const continuity = value.continuity
  return (
    isOptionalStringOrNull(value.id) &&
    (value.expected_version === undefined ||
      value.expected_version === null ||
      isPositiveInteger(value.expected_version)) &&
    isNonNegativeInteger(value.position) &&
    isNonEmptyString(value.title) &&
    isPositiveInteger(value.target_duration_ms) &&
    isNonEmptyString(value.telugu_script) &&
    isNonEmptyString(value.pronunciation_notes) &&
    isNonEmptyString(continuity.location) &&
    isNonEmptyString(continuity.lighting) &&
    isNonEmptyString(continuity.wardrobe) &&
    isNonEmptyString(continuity.props) &&
    isNonEmptyString(continuity.physical_state) &&
    isNonEmptyString(continuity.character_positions)
  )
}

function isFilmScene(value: unknown): value is FilmScene {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isPositiveInteger(value.version) &&
    typeof value.content_fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.content_fingerprint) &&
    isUtcTimestamp(value.created_at) &&
    isUtcTimestamp(value.updated_at) &&
    isFilmSceneSave(value.draft)
  )
}

function isFilmShotSave(value: unknown): value is FilmShotSave {
  return (
    isRecord(value) &&
    isOptionalStringOrNull(value.id) &&
    (value.expected_version === undefined ||
      value.expected_version === null ||
      isPositiveInteger(value.expected_version)) &&
    isNonEmptyString(value.scene_id) &&
    isNonNegativeInteger(value.position) &&
    isPositiveInteger(value.target_duration_ms) &&
    isNonEmptyString(value.description) &&
    (value.reference_workflow === 'reference_generation' ||
      value.reference_workflow === 'approved_source_footage') &&
    Array.isArray(value.character_reference_asset_ids) &&
    value.character_reference_asset_ids.every(isNonEmptyString) &&
    (value.dialogue_workflow === 'tts' || value.dialogue_workflow === 'recorded') &&
    isNonEmptyString(value.storyboard_asset_id) &&
    isStringOrNull(value.source_footage_asset_id) &&
    isStringOrNull(value.recorded_dialogue_asset_id)
  )
}

function isFilmShot(value: unknown): value is FilmShot {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.scene_id) &&
    isPositiveInteger(value.version) &&
    typeof value.content_fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.content_fingerprint) &&
    isUtcTimestamp(value.created_at) &&
    isUtcTimestamp(value.updated_at) &&
    isFilmShotSave(value.draft)
  )
}

function isFilmApproval(value: unknown): value is FilmApproval {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    approvalStages.has(String(value.stage)) &&
    typeof value.subject_fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.subject_fingerprint) &&
    isUtcTimestamp(value.approved_at) &&
    isStringOrNull(value.scene_id) &&
    isStringOrNull(value.shot_id) &&
    isStringOrNull(value.evidence_asset_id)
  )
}

function isFilmWorkspace(value: unknown): value is FilmWorkspace {
  return (
    isRecord(value) &&
    Array.isArray(value.scenes) &&
    value.scenes.every(isFilmScene) &&
    Array.isArray(value.shots) &&
    value.shots.every(isFilmShot) &&
    Array.isArray(value.approvals) &&
    value.approvals.every(isFilmApproval)
  )
}

function isContinuityBoundary(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonNegativeInteger(value.position) &&
    isNonEmptyString(value.left_scene_id) &&
    isNonEmptyString(value.left_shot_id) &&
    isNonEmptyString(value.right_scene_id) &&
    isNonEmptyString(value.right_shot_id) &&
    typeof value.fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.fingerprint) &&
    typeof value.cross_scene === 'boolean' &&
    Array.isArray(value.changed_fields) &&
    value.changed_fields.every(isNonEmptyString)
  )
}

function isFilmReadinessRequirement(value: unknown): boolean {
  return (
    isRecord(value) &&
    approvalStages.has(String(value.stage)) &&
    isNonEmptyString(value.message) &&
    isStringOrNull(value.scene_id) &&
    isStringOrNull(value.shot_id)
  )
}

function isFilmReadiness(value: unknown): value is FilmReadiness {
  return (
    isRecord(value) &&
    typeof value.workspace_fingerprint === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.workspace_fingerprint) &&
    Array.isArray(value.continuity_boundaries) &&
    value.continuity_boundaries.every(isContinuityBoundary) &&
    Array.isArray(value.structural_blockers) &&
    value.structural_blockers.every(isNonEmptyString) &&
    Array.isArray(value.pending_approvals) &&
    value.pending_approvals.every(isFilmReadinessRequirement) &&
    typeof value.ready_for_rough_cut === 'boolean' &&
    typeof value.ready_for_final_footage === 'boolean' &&
    typeof value.ready_for_dialogue_90_seconds === 'boolean' &&
    typeof value.ready_for_sequence_180_seconds === 'boolean' &&
    typeof value.ready_for_film_900_seconds === 'boolean' &&
    typeof value.ready_for_final_sound === 'boolean' &&
    typeof value.accepted === 'boolean' &&
    (value.next_gate === null ||
      (typeof value.next_gate === 'string' && approvalStages.has(value.next_gate)))
  )
}

function isRoughCutProvider(value: unknown): value is RoughCutProvider {
  return (
    isRecord(value) &&
    isNonEmptyString(value.backend) &&
    isNonEmptyString(value.backend_revision) &&
    isNonEmptyString(value.display_name) &&
    typeof value.enabled === 'boolean' &&
    isNonEmptyString(value.runtime_state) &&
    isPositiveInteger(value.width) &&
    isPositiveInteger(value.height) &&
    isPositiveInteger(value.fps_numerator) &&
    isPositiveInteger(value.fps_denominator) &&
    isStringOrNull(value.unavailable_reason) &&
    (value.enabled ? value.unavailable_reason === null : isNonEmptyString(value.unavailable_reason))
  )
}

function isRoughCutJob(value: unknown): value is RoughCutJob {
  if (!isRecord(value)) return false
  const progress = value.progress
  const result = value.result
  const failure = value.failure
  return (
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.project_id) &&
    isJobStatus(value.status) &&
    isUtcTimestamp(value.created_at) &&
    isUtcTimestamp(value.updated_at) &&
    (value.started_at === null || isUtcTimestamp(value.started_at)) &&
    (value.completed_at === null || isUtcTimestamp(value.completed_at)) &&
    isNonEmptyString(value.idempotency_key) &&
    isStringOrNull(value.backend) &&
    isStringOrNull(value.backend_revision) &&
    isSha256(value.workspace_fingerprint) &&
    isSha256(value.manifest_fingerprint) &&
    isPositiveInteger(value.shot_count) &&
    isPositiveInteger(value.duration_ms) &&
    isPositiveInteger(value.width) &&
    isPositiveInteger(value.height) &&
    isPositiveInteger(value.fps_numerator) &&
    isPositiveInteger(value.fps_denominator) &&
    (progress === null || isProgress(progress)) &&
    (result === null ||
      (isRecord(result) &&
        result.media_type === 'video/mp4' &&
        isNonEmptyString(result.download_url) &&
        result.width === value.width &&
        result.height === value.height &&
        isPositiveInteger(result.frame_count) &&
        (result.duration_seconds === null ||
          (isFiniteNumber(result.duration_seconds) && result.duration_seconds > 0)) &&
        isPositiveInteger(result.size_bytes) &&
        isSha256(result.sha256) &&
        isUtcTimestamp(result.created_at))) &&
    (failure === null ||
      (isRecord(failure) &&
        isErrorCode(failure.code) &&
        isNonEmptyString(failure.message) &&
        typeof failure.retryable === 'boolean' &&
        isNonEmptyString(failure.correlation_id)))
  )
}

function isTimelineRenderProvider(value: unknown): value is TimelineRenderProvider {
  return (
    isRecord(value) &&
    isNonEmptyString(value.backend) &&
    isNonEmptyString(value.backend_revision) &&
    isNonEmptyString(value.display_name) &&
    typeof value.enabled === 'boolean' &&
    isNonEmptyString(value.runtime_state) &&
    isPositiveInteger(value.width) &&
    isPositiveInteger(value.height) &&
    isPositiveInteger(value.fps_numerator) &&
    isPositiveInteger(value.fps_denominator) &&
    isPositiveInteger(value.duration_ms) &&
    isStringOrNull(value.unavailable_reason) &&
    (value.enabled ? value.unavailable_reason === null : isNonEmptyString(value.unavailable_reason))
  )
}

function isTimelineRenderJob(value: unknown): value is TimelineRenderJob {
  if (!isRecord(value)) return false
  const progress = value.progress
  const result = value.result
  const failure = value.failure
  return (
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.project_id) &&
    isNonEmptyString(value.timeline_id) &&
    isPositiveInteger(value.timeline_revision) &&
    isJobStatus(value.status) &&
    isUtcTimestamp(value.created_at) &&
    isUtcTimestamp(value.updated_at) &&
    (value.started_at === null || isUtcTimestamp(value.started_at)) &&
    (value.completed_at === null || isUtcTimestamp(value.completed_at)) &&
    isNonEmptyString(value.idempotency_key) &&
    isStringOrNull(value.backend) &&
    isStringOrNull(value.backend_revision) &&
    isSha256(value.timeline_fingerprint) &&
    isSha256(value.manifest_fingerprint) &&
    isPositiveInteger(value.visual_item_count) &&
    isNonNegativeInteger(value.audio_item_count) &&
    isNonNegativeInteger(value.caption_count) &&
    isPositiveInteger(value.duration_ms) &&
    isPositiveInteger(value.width) &&
    isPositiveInteger(value.height) &&
    isPositiveInteger(value.fps_numerator) &&
    isPositiveInteger(value.fps_denominator) &&
    (progress === null || isProgress(progress)) &&
    (result === null ||
      (isRecord(result) &&
        result.media_type === 'video/mp4' &&
        isNonEmptyString(result.download_url) &&
        result.width === value.width &&
        result.height === value.height &&
        isPositiveInteger(result.frame_count) &&
        (result.duration_seconds === null ||
          (isFiniteNumber(result.duration_seconds) && result.duration_seconds > 0)) &&
        isPositiveInteger(result.size_bytes) &&
        isSha256(result.sha256) &&
        isUtcTimestamp(result.created_at))) &&
    (failure === null ||
      (isRecord(failure) &&
        isErrorCode(failure.code) &&
        isNonEmptyString(failure.message) &&
        typeof failure.retryable === 'boolean' &&
        isNonEmptyString(failure.correlation_id)))
  )
}

function isResolution(value: unknown): value is Resolution {
  return isRecord(value) && isPositiveInteger(value.width) && isPositiveInteger(value.height)
}

function isNormalizedRequest(value: unknown): value is NormalizedRequest {
  return (
    isRecord(value) &&
    isGenerationMode(value.mode) &&
    isNonEmptyString(value.prompt) &&
    isNonEmptyString(value.model) &&
    isPositiveInteger(value.width) &&
    isPositiveInteger(value.height) &&
    isPositiveInteger(value.frame_count) &&
    isInteger(value.seed)
  )
}

function isProgress(value: unknown): value is Progress {
  return (
    isRecord(value) &&
    isNonNegativeInteger(value.completed_units) &&
    isPositiveInteger(value.total_units) &&
    value.completed_units <= value.total_units &&
    isNonEmptyString(value.stage)
  )
}

function isExpectedDownloadUrl(value: unknown, jobId: string): value is string {
  if (typeof value !== 'string') {
    return false
  }
  const prefix = '/api/v1/jobs/'
  const suffix = '/output'
  if (!value.startsWith(prefix) || !value.endsWith(suffix)) {
    return false
  }
  const encodedJobId = value.slice(prefix.length, -suffix.length)
  if (encodedJobId.length === 0 || encodedJobId.includes('/')) {
    return false
  }
  try {
    return decodeURIComponent(encodedJobId) === jobId
  } catch {
    return false
  }
}

function isGenerationResult(
  value: unknown,
  jobId: string,
  request: NormalizedRequest,
): value is GenerationResult {
  return (
    isRecord(value) &&
    value.media_type === 'video/mp4' &&
    isExpectedDownloadUrl(value.download_url, jobId) &&
    value.width === request.width &&
    value.height === request.height &&
    value.frame_count === request.frame_count &&
    (value.duration_seconds === null ||
      (isFiniteNumber(value.duration_seconds) && value.duration_seconds > 0)) &&
    isPositiveInteger(value.size_bytes) &&
    typeof value.sha256 === 'string' &&
    /^[0-9a-f]{64}$/u.test(value.sha256) &&
    isUtcTimestamp(value.created_at)
  )
}

function isJobFailure(value: unknown, jobId: string): value is JobFailure {
  return (
    isRecord(value) &&
    isErrorCode(value.code) &&
    isNonEmptyString(value.message) &&
    typeof value.retryable === 'boolean' &&
    value.job_id === jobId &&
    isNonEmptyString(value.correlation_id)
  )
}

function hasExecutionIdentity(
  startedAt: string | null,
  backend: string | null,
  modelRevision: string | null,
): boolean {
  return startedAt !== null && isNonEmptyString(backend) && isNonEmptyString(modelRevision)
}

function hasNoExecutionIdentity(
  startedAt: string | null,
  backend: string | null,
  modelRevision: string | null,
): boolean {
  return startedAt === null && backend === null && modelRevision === null
}

function hasOptionalExecutionIdentity(
  startedAt: string | null,
  backend: string | null,
  modelRevision: string | null,
): boolean {
  return (
    hasNoExecutionIdentity(startedAt, backend, modelRevision) ||
    hasExecutionIdentity(startedAt, backend, modelRevision)
  )
}

function hasValidTimestampOrder(
  createdAt: string,
  updatedAt: string,
  startedAt: string | null,
  completedAt: string | null,
): boolean {
  const createdTime = Date.parse(createdAt)
  const updatedTime = Date.parse(updatedAt)
  if (updatedTime < createdTime) {
    return false
  }
  const startedTime = startedAt === null ? null : Date.parse(startedAt)
  if (startedTime !== null && (startedTime < createdTime || startedTime > updatedTime)) {
    return false
  }
  const completedTime = completedAt === null ? null : Date.parse(completedAt)
  if (completedTime !== null && (completedTime < createdTime || completedTime > updatedTime)) {
    return false
  }
  return startedTime === null || completedTime === null || completedTime >= startedTime
}

function hasValidJobState(
  status: JobStatus,
  startedAt: string | null,
  completedAt: string | null,
  backend: string | null,
  modelRevision: string | null,
  progress: Progress | null,
  result: GenerationResult | null,
  failure: JobFailure | null,
): boolean {
  if (status === 'queued') {
    return (
      startedAt === null &&
      completedAt === null &&
      backend === null &&
      modelRevision === null &&
      progress === null &&
      result === null &&
      failure === null
    )
  }
  if (status === 'running') {
    return (
      hasExecutionIdentity(startedAt, backend, modelRevision) &&
      completedAt === null &&
      result === null &&
      failure === null
    )
  }
  if (status === 'succeeded') {
    return (
      hasExecutionIdentity(startedAt, backend, modelRevision) &&
      completedAt !== null &&
      progress === null &&
      result !== null &&
      failure === null
    )
  }
  if (status === 'failed') {
    return (
      hasOptionalExecutionIdentity(startedAt, backend, modelRevision) &&
      completedAt !== null &&
      progress === null &&
      result === null &&
      failure !== null
    )
  }
  return (
    hasOptionalExecutionIdentity(startedAt, backend, modelRevision) &&
    completedAt !== null &&
    progress === null &&
    result === null &&
    failure === null
  )
}

function isJob(value: unknown): value is Job {
  if (!isRecord(value)) {
    return false
  }
  const {
    id,
    status,
    created_at: createdAt,
    updated_at: updatedAt,
    started_at: startedAt,
    completed_at: completedAt,
    request,
    backend,
    model_revision: modelRevision,
    progress,
    result,
    failure,
  } = value
  if (
    !isNonEmptyString(id) ||
    !isJobStatus(status) ||
    !isUtcTimestamp(createdAt) ||
    !isUtcTimestamp(updatedAt) ||
    (startedAt !== null && !isUtcTimestamp(startedAt)) ||
    (completedAt !== null && !isUtcTimestamp(completedAt)) ||
    !isNormalizedRequest(request) ||
    !isStringOrNull(backend) ||
    !isStringOrNull(modelRevision) ||
    (progress !== null && !isProgress(progress)) ||
    (result !== null && !isGenerationResult(result, id, request)) ||
    (failure !== null && !isJobFailure(failure, id))
  ) {
    return false
  }
  return (
    hasValidTimestampOrder(createdAt, updatedAt, startedAt, completedAt) &&
    hasValidJobState(
      status,
      startedAt,
      completedAt,
      backend,
      modelRevision,
      progress,
      result,
      failure,
    )
  )
}

function isJobPage(value: unknown): value is JobPage {
  return (
    isRecord(value) &&
    Array.isArray(value.items) &&
    value.items.every(isJob) &&
    isStringOrNull(value.next_cursor)
  )
}

function isModelCapability(value: unknown): value is ModelCapability {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.display_name) &&
    Array.isArray(value.modes) &&
    value.modes.length > 0 &&
    value.modes.every(isGenerationMode) &&
    Array.isArray(value.resolutions) &&
    value.resolutions.length > 0 &&
    value.resolutions.every(isResolution) &&
    Array.isArray(value.frame_counts) &&
    value.frame_counts.length > 0 &&
    value.frame_counts.every(isPositiveInteger) &&
    typeof value.enabled === 'boolean'
  )
}

function isModelList(value: unknown): value is ModelList {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isModelCapability)
}

function isHealth(value: unknown): value is Health {
  return isRecord(value) && value.status === 'ok'
}

function parseApiError(value: unknown): ApiError | null {
  if (!isRecord(value)) {
    return null
  }
  if (
    !isErrorCode(value.code) ||
    typeof value.message !== 'string' ||
    typeof value.retryable !== 'boolean' ||
    typeof value.correlation_id !== 'string' ||
    (value.job_id !== null && typeof value.job_id !== 'string') ||
    !Array.isArray(value.fields) ||
    !value.fields.every((field) => typeof field === 'string')
  ) {
    return null
  }
  return {
    code: value.code,
    message: value.message,
    retryable: value.retryable,
    correlation_id: value.correlation_id,
    job_id: value.job_id,
    fields: [...value.fields],
  }
}

export class ApiClientError extends Error {
  readonly kind: ApiClientErrorKind
  readonly status: number | null
  readonly code: ErrorCode
  readonly retryable: boolean
  readonly correlation_id: string | null
  readonly job_id: string | null
  readonly fields: string[]

  constructor(options: ApiClientErrorOptions) {
    super(options.message)
    this.name = 'ApiClientError'
    this.kind = options.kind
    this.status = options.status
    this.code = options.code
    this.retryable = options.retryable
    this.correlation_id = options.correlation_id ?? null
    this.job_id = options.job_id ?? null
    this.fields = options.fields === undefined ? [] : [...options.fields]
  }
}

export function isApiClientError(error: unknown): error is ApiClientError {
  return error instanceof ApiClientError
}

function invalidResponse(status: number): ApiClientError {
  return new ApiClientError({
    kind: 'invalid_response',
    status,
    code: 'INTERNAL_ERROR',
    message: 'The application returned an invalid response.',
    retryable: true,
  })
}

function networkFailure(): ApiClientError {
  return new ApiClientError({
    kind: 'network',
    status: null,
    code: 'INTERNAL_ERROR',
    message: 'Unable to reach the application.',
    retryable: true,
  })
}

function normalizedBaseUrl(baseUrl: string): string {
  return baseUrl === '/' ? '' : baseUrl.replace(/\/+$/u, '')
}

export class ApiClient {
  private readonly baseUrl: string
  private readonly configuredFetch: typeof globalThis.fetch | undefined

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = normalizedBaseUrl(options.baseUrl ?? '')
    this.configuredFetch = options.fetch
  }

  async submitJob(request: GenerationRequest, signal?: AbortSignal): Promise<Job> {
    return this.requestJson<Job>(
      '/api/v1/jobs',
      {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
        signal: signal ?? null,
      },
      isJob,
    )
  }

  async getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
    return this.requestJson<Job>(
      this.jobPath(jobId),
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal: signal ?? null,
      },
      isJob,
    )
  }

  async listJobs(options: ListJobsOptions = {}): Promise<JobPage> {
    const parameters = new URLSearchParams()
    if (options.limit !== undefined) {
      parameters.set('limit', String(options.limit))
    }
    if (options.cursor !== undefined) {
      parameters.set('cursor', options.cursor)
    }
    if (options.status !== undefined) {
      parameters.set('status', options.status)
    }
    const query = parameters.toString()
    const path = query.length === 0 ? '/api/v1/jobs' : `/api/v1/jobs?${query}`
    return this.requestJson<JobPage>(
      path,
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal: options.signal ?? null,
      },
      isJobPage,
    )
  }

  async cancelJob(jobId: string, signal?: AbortSignal): Promise<Job> {
    return this.requestJson<Job>(
      `${this.jobPath(jobId)}/cancel`,
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        signal: signal ?? null,
      },
      isJob,
    )
  }

  async listModels(signal?: AbortSignal): Promise<ModelList> {
    return this.requestJson<ModelList>(
      '/api/v1/models',
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal: signal ?? null,
      },
      isModelList,
    )
  }

  async health(signal?: AbortSignal): Promise<Health> {
    return this.requestJson<Health>(
      '/api/v1/health',
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal: signal ?? null,
      },
      isHealth,
    )
  }

  async createLibraryEntity(
    draft: LibraryEntityDraft,
    signal?: AbortSignal,
  ): Promise<LibraryEntity> {
    return this.requestJson<LibraryEntity>(
      '/api/v2/library/entities',
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
        signal: signal ?? null,
      },
      isLibraryEntity,
    )
  }

  async listLibraryEntities(
    kind?: LibraryEntityKind,
    query?: string,
    signal?: AbortSignal,
  ): Promise<LibraryEntityList> {
    const parameters = new URLSearchParams({ limit: '100' })
    if (kind !== undefined) parameters.set('kind', kind)
    if (query?.trim()) parameters.set('query', query.trim())
    return this.requestJson<LibraryEntityList>(
      `/api/v2/library/entities?${parameters.toString()}`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isLibraryEntityList,
    )
  }

  async updateLibraryEntity(
    entityId: string,
    displayName: string,
    aliases: string[],
    expectedVersion: number,
    signal?: AbortSignal,
  ): Promise<LibraryEntity> {
    return this.requestJson<LibraryEntity>(
      `/api/v2/library/entities/${encodeURIComponent(entityId)}`,
      {
        method: 'PUT',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_version: expectedVersion,
          display_name: displayName,
          aliases,
        }),
        signal: signal ?? null,
      },
      isLibraryEntity,
    )
  }

  async uploadLibraryAsset(
    file: File,
    kind: AssetKind,
    rights: RightsDeclaration,
    signal?: AbortSignal,
  ): Promise<MediaAsset> {
    const parameters = new URLSearchParams({ filename: file.name, kind, rights })
    return this.requestJson<MediaAsset>(
      `/api/v2/library/assets?${parameters.toString()}`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': file.type },
        body: file,
        signal: signal ?? null,
      },
      isMediaAsset,
    )
  }

  async listLibraryAssets(signal?: AbortSignal): Promise<MediaAssetList> {
    return this.requestJson<MediaAssetList>(
      '/api/v2/library/assets',
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isMediaAssetList,
    )
  }

  async inspectLibraryAsset(assetId: string, signal?: AbortSignal): Promise<MediaAsset> {
    return this.requestJson<MediaAsset>(
      `/api/v2/library/assets/${encodeURIComponent(assetId)}/inspect`,
      { method: 'POST', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isMediaAsset,
    )
  }

  async createLibraryVersion(
    entityId: string,
    draft: LibraryVersionDraft,
    signal?: AbortSignal,
  ): Promise<LibraryVersion> {
    return this.requestJson<LibraryVersion>(
      `/api/v2/library/entities/${encodeURIComponent(entityId)}/versions`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
        signal: signal ?? null,
      },
      isLibraryVersion,
    )
  }

  async listLibraryVersions(entityId: string, signal?: AbortSignal): Promise<LibraryVersionList> {
    return this.requestJson<LibraryVersionList>(
      `/api/v2/library/entities/${encodeURIComponent(entityId)}/versions`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isLibraryVersionList,
    )
  }

  async approveLibraryVersion(
    entityId: string,
    versionId: string,
    signal?: AbortSignal,
  ): Promise<LibraryVersion> {
    return this.requestJson<LibraryVersion>(
      `/api/v2/library/entities/${encodeURIComponent(entityId)}/versions/${encodeURIComponent(versionId)}/approve`,
      { method: 'POST', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isLibraryVersion,
    )
  }

  async createFilmBibleSnapshot(
    projectId: string,
    pins: FilmBiblePinSelection[],
    signal?: AbortSignal,
  ): Promise<FilmBibleSnapshot> {
    return this.requestJson<FilmBibleSnapshot>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film-bible/snapshots`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ pins }),
        signal: signal ?? null,
      },
      isFilmBibleSnapshot,
    )
  }

  async listFilmBibleSnapshots(
    projectId: string,
    signal?: AbortSignal,
  ): Promise<FilmBibleSnapshotList> {
    return this.requestJson<FilmBibleSnapshotList>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film-bible/snapshots`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isFilmBibleSnapshotList,
    )
  }

  async approveFilmBibleSnapshot(
    projectId: string,
    snapshotId: string,
    signal?: AbortSignal,
  ): Promise<FilmBibleSnapshot> {
    return this.requestJson<FilmBibleSnapshot>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film-bible/snapshots/${encodeURIComponent(snapshotId)}/approve`,
      { method: 'POST', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isFilmBibleSnapshot,
    )
  }

  async resolveFilmBibleName(
    projectId: string,
    snapshotId: string,
    mention: string,
    kind?: LibraryEntityKind,
    signal?: AbortSignal,
  ): Promise<FilmBibleNameResolution> {
    const parameters = new URLSearchParams({ mention })
    if (kind !== undefined) parameters.set('kind', kind)
    return this.requestJson<FilmBibleNameResolution>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film-bible/snapshots/${encodeURIComponent(snapshotId)}/resolve?${parameters.toString()}`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isFilmBibleNameResolution,
    )
  }

  async createShotBindingRevision(
    projectId: string,
    shotId: string,
    draft: ShotBindingRevisionDraft,
    signal?: AbortSignal,
  ): Promise<ShotBindingRevision> {
    return this.requestJson<ShotBindingRevision>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/bindings`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
        signal: signal ?? null,
      },
      isShotBindingRevision,
    )
  }

  async listShotBindingRevisions(
    projectId: string,
    shotId: string,
    signal?: AbortSignal,
  ): Promise<ShotBindingRevisionList> {
    return this.requestJson<ShotBindingRevisionList>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/bindings`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isShotBindingRevisionList,
    )
  }

  async listAffectedShots(
    projectId: string,
    entityId: string,
    versionId: string,
    signal?: AbortSignal,
  ): Promise<AffectedShotList> {
    const parameters = new URLSearchParams({ entity_id: entityId, version_id: versionId })
    return this.requestJson<AffectedShotList>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film-bible/affected-shots?${parameters.toString()}`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isAffectedShotList,
    )
  }

  async createStartingFrameComposition(
    projectId: string,
    shotId: string,
    draft: StartingFrameDraft,
    signal?: AbortSignal,
  ): Promise<StartingFrameComposition> {
    return this.requestJson<StartingFrameComposition>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/starting-frames`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
        signal: signal ?? null,
      },
      isStartingFrameComposition,
    )
  }

  async listStartingFrameCompositions(
    projectId: string,
    shotId: string,
    signal?: AbortSignal,
  ): Promise<StartingFrameCompositionList> {
    return this.requestJson<StartingFrameCompositionList>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/starting-frames`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isStartingFrameCompositionList,
    )
  }

  async renderStartingFrameComposition(
    projectId: string,
    shotId: string,
    compositionId: string,
    signal?: AbortSignal,
  ): Promise<StartingFrameComposition> {
    return this.requestJson<StartingFrameComposition>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/starting-frames/${encodeURIComponent(compositionId)}/render`,
      { method: 'POST', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isStartingFrameComposition,
    )
  }

  async approveStartingFrameComposition(
    projectId: string,
    shotId: string,
    compositionId: string,
    signal?: AbortSignal,
  ): Promise<StartingFrameComposition> {
    return this.requestJson<StartingFrameComposition>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/starting-frames/${encodeURIComponent(compositionId)}/approve`,
      { method: 'POST', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isStartingFrameComposition,
    )
  }

  async createReferenceVideoGuidance(
    projectId: string,
    shotId: string,
    draft: ReferenceVideoGuidanceDraft,
    signal?: AbortSignal,
  ): Promise<ReferenceVideoGuidance> {
    return this.requestJson<ReferenceVideoGuidance>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/reference-guidance`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
        signal: signal ?? null,
      },
      isReferenceVideoGuidance,
    )
  }

  async listReferenceVideoGuidance(
    projectId: string,
    shotId: string,
    signal?: AbortSignal,
  ): Promise<ReferenceVideoGuidanceList> {
    return this.requestJson<ReferenceVideoGuidanceList>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/reference-guidance`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isReferenceVideoGuidanceList,
    )
  }

  async approveReferenceVideoGuidance(
    projectId: string,
    shotId: string,
    guidanceId: string,
    signal?: AbortSignal,
  ): Promise<ReferenceVideoGuidance> {
    return this.requestJson<ReferenceVideoGuidance>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/reference-guidance/${encodeURIComponent(guidanceId)}/approve`,
      { method: 'POST', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isReferenceVideoGuidance,
    )
  }

  async getImageGenerationProvider(signal?: AbortSignal): Promise<ImageGenerationProvider> {
    return this.requestJson<ImageGenerationProvider>(
      '/api/v2/image-generation/provider',
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isImageGenerationProvider,
    )
  }

  async listControlledGenerationProviders(
    signal?: AbortSignal,
  ): Promise<ControlledGenerationProviderList> {
    return this.requestJson<ControlledGenerationProviderList>(
      '/api/v2/controlled-generation/providers',
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isControlledGenerationProviderList,
    )
  }

  async submitControlledGeneration(
    projectId: string,
    shotId: string,
    compositionId: string,
    guidanceId: string,
    draft: ControlledGenerationDraft,
    signal?: AbortSignal,
  ): Promise<ImageGenerationJob> {
    return this.requestJson<ImageGenerationJob>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/starting-frames/${encodeURIComponent(compositionId)}/reference-guidance/${encodeURIComponent(guidanceId)}/generations`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
        signal: signal ?? null,
      },
      isImageGenerationJob,
    )
  }

  async submitImageGeneration(
    projectId: string,
    shotId: string,
    compositionId: string,
    draft: ImageGenerationDraft,
    signal?: AbortSignal,
  ): Promise<ImageGenerationJob> {
    return this.requestJson<ImageGenerationJob>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/starting-frames/${encodeURIComponent(compositionId)}/generations`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
        signal: signal ?? null,
      },
      isImageGenerationJob,
    )
  }

  async getImageGeneration(
    projectId: string,
    shotId: string,
    jobId: string,
    signal?: AbortSignal,
  ): Promise<ImageGenerationJob> {
    return this.requestJson<ImageGenerationJob>(
      this.imageGenerationPath(projectId, shotId, jobId),
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isImageGenerationJob,
    )
  }

  async cancelImageGeneration(
    projectId: string,
    shotId: string,
    jobId: string,
    signal?: AbortSignal,
  ): Promise<ImageGenerationJob> {
    return this.requestJson<ImageGenerationJob>(
      `${this.imageGenerationPath(projectId, shotId, jobId)}/cancel`,
      { method: 'POST', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isImageGenerationJob,
    )
  }

  async createProject(request: ProjectDraft, signal?: AbortSignal): Promise<Project> {
    return this.requestJson<Project>(
      '/api/v2/projects',
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
        signal: signal ?? null,
      },
      isProject,
    )
  }

  async listProjects(limit = 50, signal?: AbortSignal): Promise<ProjectList> {
    return this.requestJson<ProjectList>(
      `/api/v2/projects?limit=${encodeURIComponent(String(limit))}`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isProjectList,
    )
  }

  async uploadProjectAsset(
    projectId: string,
    file: File,
    kind: AssetKind,
    rights: RightsDeclaration,
    signal?: AbortSignal,
  ): Promise<MediaAsset> {
    const parameters = new URLSearchParams({ filename: file.name, kind, rights })
    return this.requestJson<MediaAsset>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/assets?${parameters.toString()}`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': file.type },
        body: file,
        signal: signal ?? null,
      },
      isMediaAsset,
    )
  }

  async listProjectAssets(projectId: string, signal?: AbortSignal): Promise<MediaAssetList> {
    return this.requestJson<MediaAssetList>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/assets`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isMediaAssetList,
    )
  }

  async inspectProjectAsset(
    projectId: string,
    assetId: string,
    signal?: AbortSignal,
  ): Promise<MediaAsset> {
    return this.requestJson<MediaAsset>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/inspect`,
      { method: 'POST', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isMediaAsset,
    )
  }

  async createTimelineRevision(
    projectId: string,
    draft: TimelineDraft,
    signal?: AbortSignal,
  ): Promise<TimelineRevision> {
    return this.requestJson<TimelineRevision>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/timelines`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
        signal: signal ?? null,
      },
      isTimelineRevision,
    )
  }

  async listTimelineRevisions(
    projectId: string,
    signal?: AbortSignal,
  ): Promise<TimelineRevisionList> {
    return this.requestJson<TimelineRevisionList>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/timelines`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isTimelineRevisionList,
    )
  }

  async approveTimelineRevision(
    projectId: string,
    timelineId: string,
    expectedProjectVersion: number,
    signal?: AbortSignal,
  ): Promise<TimelineRevision> {
    return this.requestJson<TimelineRevision>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/timelines/${encodeURIComponent(timelineId)}/approve`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_project_version: expectedProjectVersion }),
        signal: signal ?? null,
      },
      isTimelineRevision,
    )
  }

  async getFilmWorkspace(projectId: string, signal?: AbortSignal): Promise<FilmWorkspace> {
    return this.requestJson<FilmWorkspace>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isFilmWorkspace,
    )
  }

  async saveFilmScene(
    projectId: string,
    draft: FilmSceneSave,
    signal?: AbortSignal,
  ): Promise<FilmScene> {
    return this.requestJson<FilmScene>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/scenes`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
        signal: signal ?? null,
      },
      isFilmScene,
    )
  }

  async saveFilmShot(
    projectId: string,
    draft: FilmShotSave,
    signal?: AbortSignal,
  ): Promise<FilmShot> {
    return this.requestJson<FilmShot>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
        signal: signal ?? null,
      },
      isFilmShot,
    )
  }

  async approveFilmSubject(
    projectId: string,
    request: FilmApprovalRequest,
    signal?: AbortSignal,
  ): Promise<FilmApproval> {
    return this.requestJson<FilmApproval>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/approvals`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
        signal: signal ?? null,
      },
      isFilmApproval,
    )
  }

  async getFilmReadiness(projectId: string, signal?: AbortSignal): Promise<FilmReadiness> {
    return this.requestJson<FilmReadiness>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/readiness`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isFilmReadiness,
    )
  }

  async getRoughCutProvider(projectId: string, signal?: AbortSignal): Promise<RoughCutProvider> {
    return this.requestJson<RoughCutProvider>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/rough-cuts/provider`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isRoughCutProvider,
    )
  }

  async submitRoughCut(
    projectId: string,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<RoughCutJob> {
    return this.requestJson<RoughCutJob>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/rough-cuts`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ idempotency_key: idempotencyKey }),
        signal: signal ?? null,
      },
      isRoughCutJob,
    )
  }

  async getRoughCut(projectId: string, jobId: string, signal?: AbortSignal): Promise<RoughCutJob> {
    return this.requestJson<RoughCutJob>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/rough-cuts/${encodeURIComponent(jobId)}`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isRoughCutJob,
    )
  }

  async cancelRoughCut(
    projectId: string,
    jobId: string,
    signal?: AbortSignal,
  ): Promise<RoughCutJob> {
    return this.requestJson<RoughCutJob>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/film/rough-cuts/${encodeURIComponent(jobId)}/cancel`,
      { method: 'POST', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isRoughCutJob,
    )
  }

  async getTimelineRenderProvider(
    projectId: string,
    signal?: AbortSignal,
  ): Promise<TimelineRenderProvider> {
    return this.requestJson<TimelineRenderProvider>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/timeline-renders/provider`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isTimelineRenderProvider,
    )
  }

  async submitTimelineRender(
    projectId: string,
    timelineId: string,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<TimelineRenderJob> {
    return this.requestJson<TimelineRenderJob>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/timelines/${encodeURIComponent(timelineId)}/renders`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ idempotency_key: idempotencyKey }),
        signal: signal ?? null,
      },
      isTimelineRenderJob,
    )
  }

  async getTimelineRender(
    projectId: string,
    timelineId: string,
    jobId: string,
    signal?: AbortSignal,
  ): Promise<TimelineRenderJob> {
    return this.requestJson<TimelineRenderJob>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/timelines/${encodeURIComponent(timelineId)}/renders/${encodeURIComponent(jobId)}`,
      { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isTimelineRenderJob,
    )
  }

  async cancelTimelineRender(
    projectId: string,
    timelineId: string,
    jobId: string,
    signal?: AbortSignal,
  ): Promise<TimelineRenderJob> {
    return this.requestJson<TimelineRenderJob>(
      `/api/v2/projects/${encodeURIComponent(projectId)}/timelines/${encodeURIComponent(timelineId)}/renders/${encodeURIComponent(jobId)}/cancel`,
      { method: 'POST', headers: { Accept: 'application/json' }, signal: signal ?? null },
      isTimelineRenderJob,
    )
  }

  async getOutput(jobId: string, signal?: AbortSignal): Promise<Blob> {
    const response = await this.request(`${this.jobPath(jobId)}/output`, {
      method: 'GET',
      headers: { Accept: 'video/mp4' },
      signal: signal ?? null,
    })
    if (!response.ok) {
      throw await this.errorFromResponse(response)
    }
    const mediaType = response.headers.get('content-type')?.split(';', 1)[0]?.trim()
    if (mediaType !== 'video/mp4') {
      throw invalidResponse(response.status)
    }
    return response.blob()
  }

  outputUrl(jobId: string): string {
    return this.url(`${this.jobPath(jobId)}/output`)
  }

  private jobPath(jobId: string): string {
    return `/api/v1/jobs/${encodeURIComponent(jobId)}`
  }

  private imageGenerationPath(projectId: string, shotId: string, jobId: string): string {
    return `/api/v2/projects/${encodeURIComponent(projectId)}/film/shots/${encodeURIComponent(shotId)}/generations/${encodeURIComponent(jobId)}`
  }

  private url(path: string): string {
    return `${this.baseUrl}${path}`
  }

  private async requestJson<T>(
    path: string,
    init: RequestInit,
    validate: (value: unknown) => value is T,
  ): Promise<T> {
    const response = await this.request(path, init)
    if (!response.ok) {
      throw await this.errorFromResponse(response)
    }
    try {
      const payload: unknown = await response.json()
      if (!validate(payload)) {
        throw invalidResponse(response.status)
      }
      return payload
    } catch {
      throw invalidResponse(response.status)
    }
  }

  private async request(path: string, init: RequestInit): Promise<Response> {
    const fetchImplementation = this.configuredFetch ?? globalThis.fetch
    if (typeof fetchImplementation !== 'function') {
      throw networkFailure()
    }
    try {
      return await fetchImplementation(this.url(path), init)
    } catch (error: unknown) {
      if (init.signal?.aborted) {
        throw error
      }
      throw networkFailure()
    }
  }

  private async errorFromResponse(response: Response): Promise<ApiClientError> {
    let payload: unknown
    try {
      payload = await response.json()
    } catch {
      return invalidResponse(response.status)
    }
    const apiError = parseApiError(payload)
    if (apiError === null) {
      return invalidResponse(response.status)
    }
    return new ApiClientError({
      kind: 'api',
      status: response.status,
      code: apiError.code,
      message: apiError.message,
      retryable: apiError.retryable,
      correlation_id: apiError.correlation_id,
      job_id: apiError.job_id,
      fields: apiError.fields,
    })
  }
}

export const videoApi = new ApiClient()
