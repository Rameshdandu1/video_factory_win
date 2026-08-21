import {
  ERROR_CODES,
  type ApiError,
  type ErrorCode,
  type GenerationMode,
  type GenerationRequest,
  type GenerationResult,
  type Health,
  type Job,
  type JobFailure,
  type JobPage,
  type JobStatus,
  type ModelCapability,
  type ModelList,
  type NormalizedRequest,
  type Progress,
  type Resolution,
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
