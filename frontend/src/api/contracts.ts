export const ERROR_CODES = [
  'INVALID_REQUEST',
  'UNSUPPORTED_MODEL',
  'UNSUPPORTED_PARAMETERS',
  'QUEUE_FULL',
  'MODEL_UNAVAILABLE',
  'INSUFFICIENT_RESOURCES',
  'GENERATION_FAILED',
  'OUTPUT_WRITE_FAILED',
  'JOB_NOT_FOUND',
  'JOB_NOT_CANCELLABLE',
  'PROJECT_NOT_FOUND',
  'REVISION_CONFLICT',
  'ASSET_INVALID',
  'ASSET_TOO_LARGE',
  'ASSET_NOT_FOUND',
  'MEDIA_INSPECTION_FAILED',
  'MEDIA_INSPECTION_UNAVAILABLE',
  'TIMELINE_NOT_FOUND',
  'FILM_SUBJECT_NOT_FOUND',
  'LIBRARY_ENTITY_NOT_FOUND',
  'LIBRARY_VERSION_NOT_FOUND',
  'LIBRARY_REVISION_CONFLICT',
  'FILM_BIBLE_NOT_FOUND',
  'STARTING_FRAME_NOT_FOUND',
  'STARTING_FRAME_RENDER_FAILED',
  'REFERENCE_GUIDANCE_NOT_FOUND',
  'IMAGE_GENERATION_NOT_FOUND',
  'IMAGE_GENERATION_UNAVAILABLE',
  'CONSTRAINT_CONFLICT',
  'ROUGH_CUT_NOT_FOUND',
  'TIMELINE_RENDER_NOT_FOUND',
  'MEDIA_RENDER_UNAVAILABLE',
  'MEDIA_RENDER_FAILED',
  'IDEMPOTENCY_CONFLICT',
  'INTERNAL_ERROR',
] as const

export type ErrorCode = (typeof ERROR_CODES)[number]

export type GenerationMode = 'text_to_video'

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export type UtcTimestamp = string

export interface GenerationRequest {
  mode: GenerationMode
  prompt: string
  model: string
  width: number
  height: number
  frame_count: number
  seed?: number | null
}

export interface NormalizedRequest {
  mode: GenerationMode
  prompt: string
  model: string
  width: number
  height: number
  frame_count: number
  seed: number
}

export interface Progress {
  completed_units: number
  total_units: number
  stage: string
}

export interface GenerationResult {
  media_type: 'video/mp4'
  download_url: string
  width: number
  height: number
  frame_count: number
  duration_seconds: number | null
  size_bytes: number
  sha256: string
  created_at: UtcTimestamp
}

export interface JobFailure {
  code: ErrorCode
  message: string
  retryable: boolean
  job_id: string
  correlation_id: string
}

export interface Job {
  id: string
  status: JobStatus
  created_at: UtcTimestamp
  updated_at: UtcTimestamp
  started_at: UtcTimestamp | null
  completed_at: UtcTimestamp | null
  request: NormalizedRequest
  backend: string | null
  model_revision: string | null
  progress: Progress | null
  result: GenerationResult | null
  failure: JobFailure | null
}

export type GenerationJob = Job

export interface JobPage {
  items: Job[]
  next_cursor: string | null
}

export interface Resolution {
  width: number
  height: number
}

export interface ModelCapability {
  id: string
  display_name: string
  modes: GenerationMode[]
  resolutions: Resolution[]
  frame_counts: number[]
  enabled: boolean
}

export interface ModelList {
  items: ModelCapability[]
}

export interface Health {
  status: 'ok'
}

export interface ApiError {
  code: ErrorCode
  message: string
  retryable: boolean
  correlation_id: string
  job_id: string | null
  fields: string[]
}

export type ProjectMode = 'short' | 'long'
export type ProjectState = 'draft' | 'active' | 'paused' | 'archived'
export type AspectRatio = '9:16' | '16:9' | '1:1'
export type ProjectPreset = 'standard' | 'telugu_short_film_900'

export interface ExportSettings {
  width: number
  height: number
  fps_numerator: number
  fps_denominator: number
}

export interface ProviderSelections {
  video: string
  speech: string | null
  lip_sync: string | null
  caption_alignment: string | null
}

export interface BudgetPolicy {
  max_compute_seconds: number | null
  max_cost_micros: number | null
  automatic_expensive_retries: number
}

export interface ProjectDraft {
  title: string
  language: string
  mode: ProjectMode
  target_duration_ms: number
  aspect_ratio: AspectRatio
  export_settings: ExportSettings
  providers: ProviderSelections
  budget_policy: BudgetPolicy
  preset: ProjectPreset
  titles_and_credits_within_target: boolean
}

export interface Project extends ProjectDraft {
  id: string
  version: number
  state: ProjectState
  approved_timeline_revision_id: string | null
  created_at: UtcTimestamp
  updated_at: UtcTimestamp
}

export interface ProjectList {
  items: Project[]
}

export type AssetKind = 'image' | 'audio' | 'video'
export type RightsDeclaration = 'owned' | 'licensed' | 'permissioned' | 'public_domain'

export interface MediaAsset {
  id: string
  project_id: string | null
  scope: 'project' | 'library'
  version: number
  kind: AssetKind
  state: 'ready' | 'inspected'
  original_filename: string
  media_type: string
  size_bytes: number
  sha256: string
  rights: RightsDeclaration
  created_at: UtcTimestamp
  metadata: MediaMetadata | null
  inspector_revision: string | null
  inspected_at: UtcTimestamp | null
}

export interface MediaMetadata {
  format_name: string
  duration_ms: number
  width: number | null
  height: number | null
  frame_rate_numerator: number | null
  frame_rate_denominator: number | null
  sample_rate: number | null
  channels: number | null
  sample_count: number | null
}

export interface MediaAssetList {
  items: MediaAsset[]
}

export type LibraryEntityKind = 'character' | 'location' | 'prop' | 'shot_reference'

export interface LibraryEntityDraft {
  kind: LibraryEntityKind
  display_name: string
  aliases: string[]
}

export interface LibraryEntity extends LibraryEntityDraft {
  id: string
  metadata_version: number
  created_at: UtcTimestamp
  updated_at: UtcTimestamp
}

export interface LibraryEntityList {
  items: LibraryEntity[]
}

export type LibraryVersionKind =
  | 'identity'
  | 'wardrobe'
  | 'location_view'
  | 'lighting_variant'
  | 'prop_variant'
  | 'prop_state'
  | 'shot_reference'

export type ReferenceRole =
  | 'identity_appearance'
  | 'location_or_prop'
  | 'source_layer'
  | 'starting_frame'
  | 'motion_performance'
  | 'shot_guidance'
  | 'review_only'

export interface LibraryAssetSelection {
  asset_id: string
  role: ReferenceRole
  view_label: string | null
}

export interface LibraryVersionDraft {
  kind: LibraryVersionKind
  label: string
  notes: string
  invariants: string
  state_notes: string
  voice_profile_id: string | null
  rights_statement: string
  assets: LibraryAssetSelection[]
}

export interface LibraryAssetBinding extends LibraryAssetSelection {
  asset_version: number
  asset_sha256: string
}

export interface LibraryVersion extends Omit<LibraryVersionDraft, 'assets'> {
  id: string
  entity_id: string
  version_number: number
  status: 'draft' | 'approved' | 'archived'
  assets: LibraryAssetBinding[]
  fingerprint: string
  created_at: UtcTimestamp
  approved_at: UtcTimestamp | null
}

export interface LibraryVersionList {
  items: LibraryVersion[]
}

export type FilmBiblePinRole =
  | 'character_identity'
  | 'character_wardrobe'
  | 'location_view'
  | 'location_lighting'
  | 'prop_variant'
  | 'prop_state'
  | 'shot_reference'

export interface FilmBiblePinSelection {
  entity_id: string
  version_id: string
  role: FilmBiblePinRole
}

export interface FilmBiblePin {
  entity_id: string
  library_version_id: string
  library_version_number: number
  version_kind: LibraryVersionKind
  version_fingerprint: string
  role: FilmBiblePinRole
}

export interface FilmBibleSnapshot {
  id: string
  project_id: string
  revision: number
  status: 'draft' | 'approved'
  pins: FilmBiblePin[]
  fingerprint: string
  created_at: UtcTimestamp
  approved_at: UtcTimestamp | null
}

export interface FilmBibleSnapshotList {
  items: FilmBibleSnapshot[]
}

export type NameResolutionStatus = 'resolved' | 'ambiguous' | 'unresolved'

export interface FilmBibleResolutionCandidate {
  entity_id: string
  display_name: string
  entity_kind: LibraryEntityKind
  pins: FilmBiblePin[]
}

export interface FilmBibleNameResolution {
  mention: string
  status: NameResolutionStatus
  candidates: FilmBibleResolutionCandidate[]
}

export interface ShotBindingRevisionDraft {
  shot_version: number
  film_bible_snapshot_id: string
  bindings: FilmBiblePinSelection[]
}

export interface ShotBindingRevision {
  id: string
  project_id: string
  shot_id: string
  shot_version: number
  revision: number
  film_bible_snapshot_id: string
  bindings: FilmBiblePin[]
  fingerprint: string
  created_at: UtcTimestamp
}

export interface ShotBindingRevisionList {
  items: ShotBindingRevision[]
}

export interface AffectedShotList {
  entity_id: string
  library_version_id: string
  shot_ids: string[]
}

export type StartingFrameMode = 'composed_upload' | 'layered'
export type StartingFrameStatus = 'draft' | 'rendered' | 'approved'
export type CompositionLayerRole =
  'starting_frame' | 'background' | 'character' | 'prop' | 'overlay'
export type CompositionFit = 'contain' | 'cover' | 'stretch'

export interface CompositionAssetSelection {
  asset_id: string
  library_entity_id: string | null
  library_version_id: string | null
}

export interface SourceCrop {
  x: number
  y: number
  width: number
  height: number
}

export interface LayerTransform {
  x: number
  y: number
  width: number
  height: number
  rotation_millidegrees: number
  opacity_basis_points: number
  fit: CompositionFit
  crop: SourceCrop | null
}

export interface StartingFrameLayerDraft {
  role: CompositionLayerRole
  source: CompositionAssetSelection
  transform: LayerTransform
  mask: CompositionAssetSelection | null
}

export interface StartingFrameDraft {
  shot_version: number
  shot_binding_revision_id: string
  mode: StartingFrameMode
  canvas_width: number
  canvas_height: number
  background_rgba: string
  output_rights: RightsDeclaration
  framing_notes: string
  pose_notes: string
  action_notes: string
  lighting_notes: string
  visible_speaker_entity_id: string | null
  layers: StartingFrameLayerDraft[]
}

export interface CompositionAssetSnapshot extends CompositionAssetSelection {
  asset_version: number
  asset_sha256: string
  scope: 'project' | 'library'
  library_version_fingerprint: string | null
}

export interface StartingFrameLayer extends Omit<StartingFrameLayerDraft, 'source' | 'mask'> {
  source: CompositionAssetSnapshot
  mask: CompositionAssetSnapshot | null
}

export interface StartingFrameComposition extends Omit<StartingFrameDraft, 'layers'> {
  id: string
  project_id: string
  shot_id: string
  revision: number
  status: StartingFrameStatus
  layers: StartingFrameLayer[]
  fingerprint: string
  created_at: UtcTimestamp
  rendered_asset_id: string | null
  rendered_asset_version: number | null
  rendered_sha256: string | null
  renderer_revision: string | null
  rendered_at: UtcTimestamp | null
  approved_at: UtcTimestamp | null
  preview_url: string | null
}

export interface StartingFrameCompositionList {
  items: StartingFrameComposition[]
}

export type ReferenceVideoPurpose = 'motion_performance' | 'shot_guidance' | 'review_only'
export type ReferenceGuidanceStatus = 'draft' | 'approved'

export interface ReferenceVideoSelection {
  asset_id: string
  library_entity_id: string | null
  library_version_id: string | null
}

export interface ReferenceVideoGuidanceDraft {
  shot_version: number
  shot_binding_revision_id: string
  purpose: ReferenceVideoPurpose
  source: ReferenceVideoSelection
  trim_start_ms: number
  trim_end_ms: number
  guidance_notes: string
}

export interface ReferenceVideoSourceSnapshot extends ReferenceVideoSelection {
  asset_version: number
  asset_sha256: string
  media_type: string
  scope: 'project' | 'library'
  inspector_revision: string
  duration_ms: number
  width: number
  height: number
  frame_rate_numerator: number
  frame_rate_denominator: number
  library_version_fingerprint: string | null
}

export interface ReferenceVideoGuidance extends Omit<ReferenceVideoGuidanceDraft, 'source'> {
  id: string
  project_id: string
  shot_id: string
  revision: number
  source: ReferenceVideoSourceSnapshot
  status: ReferenceGuidanceStatus
  fingerprint: string
  created_at: UtcTimestamp
  approved_at: UtcTimestamp | null
  preview_url: string
}

export interface ReferenceVideoGuidanceList {
  items: ReferenceVideoGuidance[]
}

export type ControlledVideoOperation =
  'vace_performance_transfer' | 'animate_character' | 'animate_replacement'

export interface ControlledGenerationProvider {
  id: string
  backend: string
  backend_revision: string
  model: string
  display_name: string
  task: string
  operation: ControlledVideoOperation
  area_width: number
  area_height: number
  frame_count: number
  maximum_guidance_ms: number
  preserves_starting_frame_environment: boolean
  enabled: boolean
  runtime_state: string
  unavailable_reason: string | null
}

export interface ControlledGenerationProviderList {
  items: ControlledGenerationProvider[]
}

export interface ImageGenerationProvider {
  backend: string
  backend_revision: string
  model: string
  display_name: string
  task: string
  area_width: number
  area_height: number
  frame_count: number
  enabled: boolean
  runtime_state: string
  unavailable_reason: string | null
}

export interface ImageGenerationDraft {
  prompt: string
  idempotency_key: string
  seed: string | null
}

export interface ControlledGenerationDraft extends ImageGenerationDraft {
  provider_id: string
  preserve_environment: boolean
}

export interface ImageConditioning {
  project_id: string
  shot_id: string
  shot_version: number
  composition_id: string
  composition_revision: number
  composition_fingerprint: string
  source_asset_id: string
  source_asset_version: number
  source_asset_sha256: string
  source_width: number
  source_height: number
  manifest_fingerprint: string
  reference_video: ReferenceVideoConditioning | null
}

export interface ReferenceVideoConditioning {
  guidance_id: string
  guidance_revision: number
  guidance_fingerprint: string
  purpose: ReferenceVideoPurpose
  source_asset_id: string
  source_asset_version: number
  source_asset_sha256: string
  trim_start_ms: number
  trim_end_ms: number
  operation: ControlledVideoOperation
  preserve_environment: boolean
  constraint_plan_fingerprint: string
}

export interface ConditioningEvidence {
  source_sha256: string
  derivative_sha256: string
  derivative_width: number
  derivative_height: number
  reference_source_sha256: string | null
  reference_derivative_sha256: string | null
  control_fingerprint: string | null
}

export interface ImageGenerationJob {
  id: string
  status: JobStatus
  created_at: UtcTimestamp
  updated_at: UtcTimestamp
  started_at: UtcTimestamp | null
  completed_at: UtcTimestamp | null
  idempotency_key: string
  request: {
    prompt: string
    model: string
    area_width: number
    area_height: number
    frame_count: number
    seed: string
  }
  conditioning: ImageConditioning
  backend: string | null
  backend_revision: string | null
  progress: Progress | null
  conditioning_evidence: ConditioningEvidence | null
  result: GenerationResult | null
  failure: Omit<JobFailure, 'job_id'> | null
}

export type TimelineItemKind = 'video' | 'image' | 'audio' | 'title_card'

export interface TimelineItem {
  kind: TimelineItemKind
  start_ms: number
  duration_ms: number
  layer: number
  asset_id: string | null
  text: string | null
}

export interface CaptionSegment {
  start_ms: number
  end_ms: number
  text: string
}

export interface TimelineDraft {
  duration_ms: number
  items: TimelineItem[]
  captions: CaptionSegment[]
}

export interface TimelineRevision extends TimelineDraft {
  id: string
  project_id: string
  revision: number
  fingerprint: string
  created_at: UtcTimestamp
  approved_at: UtcTimestamp | null
}

export interface TimelineRevisionList {
  items: TimelineRevision[]
}

export interface SceneContinuity {
  location: string
  lighting: string
  wardrobe: string
  props: string
  physical_state: string
  character_positions: string
}

export interface FilmSceneSave {
  id?: string | null
  expected_version?: number | null
  position: number
  title: string
  target_duration_ms: number
  telugu_script: string
  pronunciation_notes: string
  continuity: SceneContinuity
}

export interface FilmScene {
  id: string
  version: number
  content_fingerprint: string
  created_at: UtcTimestamp
  updated_at: UtcTimestamp
  draft: FilmSceneSave
}

export type ReferenceWorkflow = 'reference_generation' | 'approved_source_footage'
export type DialogueWorkflow = 'tts' | 'recorded'

export interface FilmShotSave {
  id?: string | null
  expected_version?: number | null
  scene_id: string
  position: number
  target_duration_ms: number
  description: string
  reference_workflow: ReferenceWorkflow
  character_reference_asset_ids: string[]
  dialogue_workflow: DialogueWorkflow
  storyboard_asset_id: string
  source_footage_asset_id: string | null
  recorded_dialogue_asset_id: string | null
}

export interface FilmShot {
  id: string
  scene_id: string
  version: number
  content_fingerprint: string
  created_at: UtcTimestamp
  updated_at: UtcTimestamp
  draft: FilmShotSave
}

export type ApprovalStage =
  | 'character_references'
  | 'identity_workflow'
  | 'telugu_script'
  | 'pronunciation'
  | 'voice_performance'
  | 'storyboard'
  | 'visual_performance'
  | 'lip_sync'
  | 'adjacent_shot_continuity'
  | 'rough_cut'
  | 'dialogue_90_seconds'
  | 'sequence_180_seconds'
  | 'film_900_seconds'
  | 'final_sound_mix'

export interface FilmApprovalRequest {
  stage: ApprovalStage
  scene_id: string | null
  shot_id: string | null
  evidence_asset_id: string | null
}

export interface FilmApproval extends FilmApprovalRequest {
  id: string
  subject_fingerprint: string
  approved_at: UtcTimestamp
}

export interface FilmWorkspace {
  scenes: FilmScene[]
  shots: FilmShot[]
  approvals: FilmApproval[]
}

export interface ContinuityBoundary {
  position: number
  left_scene_id: string
  left_shot_id: string
  right_scene_id: string
  right_shot_id: string
  fingerprint: string
  cross_scene: boolean
  changed_fields: string[]
}

export interface FilmReadinessRequirement {
  stage: ApprovalStage
  message: string
  scene_id: string | null
  shot_id: string | null
}

export interface FilmReadiness {
  workspace_fingerprint: string
  continuity_boundaries: ContinuityBoundary[]
  structural_blockers: string[]
  pending_approvals: FilmReadinessRequirement[]
  ready_for_rough_cut: boolean
  ready_for_final_footage: boolean
  ready_for_dialogue_90_seconds: boolean
  ready_for_sequence_180_seconds: boolean
  ready_for_film_900_seconds: boolean
  ready_for_final_sound: boolean
  accepted: boolean
  next_gate: ApprovalStage | null
}

export interface RoughCutProvider {
  backend: string
  backend_revision: string
  display_name: string
  enabled: boolean
  runtime_state: string
  width: number
  height: number
  fps_numerator: number
  fps_denominator: number
  unavailable_reason: string | null
}

export interface RoughCutProgress {
  completed_units: number
  total_units: number
  stage: string
}

export interface RoughCutResult {
  media_type: 'video/mp4'
  download_url: string
  width: number
  height: number
  frame_count: number
  duration_seconds: number | null
  size_bytes: number
  sha256: string
  created_at: UtcTimestamp
}

export interface RoughCutJob {
  id: string
  project_id: string
  status: JobStatus
  created_at: UtcTimestamp
  updated_at: UtcTimestamp
  started_at: UtcTimestamp | null
  completed_at: UtcTimestamp | null
  idempotency_key: string
  backend: string | null
  backend_revision: string | null
  workspace_fingerprint: string
  manifest_fingerprint: string
  shot_count: number
  duration_ms: number
  width: number
  height: number
  fps_numerator: number
  fps_denominator: number
  progress: RoughCutProgress | null
  result: RoughCutResult | null
  failure: Omit<JobFailure, 'job_id'> | null
}

export interface TimelineRenderProvider {
  backend: string
  backend_revision: string
  display_name: string
  enabled: boolean
  runtime_state: string
  width: number
  height: number
  fps_numerator: number
  fps_denominator: number
  duration_ms: number
  unavailable_reason: string | null
}

export interface TimelineRenderJob {
  id: string
  project_id: string
  timeline_id: string
  timeline_revision: number
  status: JobStatus
  created_at: UtcTimestamp
  updated_at: UtcTimestamp
  started_at: UtcTimestamp | null
  completed_at: UtcTimestamp | null
  idempotency_key: string
  backend: string | null
  backend_revision: string | null
  timeline_fingerprint: string
  manifest_fingerprint: string
  visual_item_count: number
  audio_item_count: number
  caption_count: number
  duration_ms: number
  width: number
  height: number
  fps_numerator: number
  fps_denominator: number
  progress: Progress | null
  result: RoughCutResult | null
  failure: Omit<JobFailure, 'job_id'> | null
}
