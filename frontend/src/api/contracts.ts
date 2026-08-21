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
