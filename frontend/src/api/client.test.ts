import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClient, ApiClientError, isApiClientError, videoApi } from './client'
import type {
  ApiError,
  GenerationRequest,
  GenerationResult,
  Health,
  Job,
  JobFailure,
  ModelCapability,
  ModelList,
} from './contracts'

const request: GenerationRequest = {
  mode: 'text_to_video',
  prompt: 'private prompt that belongs only in the request body',
  model: 'wan21-t2v',
  width: 832,
  height: 480,
  frame_count: 81,
  seed: null,
}

const queuedJob: Job = {
  id: 'job-1',
  status: 'queued',
  created_at: '2026-08-21T10:00:00Z',
  updated_at: '2026-08-21T10:00:00Z',
  started_at: null,
  completed_at: null,
  request: {
    ...request,
    seed: 42,
  },
  backend: null,
  model_revision: null,
  progress: null,
  result: null,
  failure: null,
}

const startedAt = '2026-08-21T10:01:00Z'
const completedAt = '2026-08-21T10:05:00Z'

const runningJob: Job = {
  ...queuedJob,
  status: 'running',
  updated_at: startedAt,
  started_at: startedAt,
  backend: 'fake',
  model_revision: 'fake-v1',
  progress: {
    completed_units: 1,
    total_units: 2,
    stage: 'generation',
  },
}

const successfulResult: GenerationResult = {
  media_type: 'video/mp4',
  download_url: '/api/v1/jobs/job-1/output',
  width: 832,
  height: 480,
  frame_count: 81,
  duration_seconds: null,
  size_bytes: 1_024,
  sha256: 'a'.repeat(64),
  created_at: completedAt,
}

const succeededJob: Job = {
  ...runningJob,
  status: 'succeeded',
  updated_at: completedAt,
  completed_at: completedAt,
  progress: null,
  result: successfulResult,
}

const generationFailure: JobFailure = {
  code: 'GENERATION_FAILED',
  message: 'Video generation failed.',
  retryable: true,
  job_id: 'job-1',
  correlation_id: 'correlation-1',
}

const failedJob: Job = {
  ...runningJob,
  status: 'failed',
  updated_at: completedAt,
  completed_at: completedAt,
  progress: null,
  failure: generationFailure,
}

const cancelledJob: Job = {
  ...runningJob,
  status: 'cancelled',
  updated_at: completedAt,
  completed_at: completedAt,
  progress: null,
}

const modelCapability: ModelCapability = {
  id: 'wan21-t2v',
  display_name: 'Wan2.1 Text to Video',
  modes: ['text_to_video'],
  resolutions: [{ width: 832, height: 480 }],
  frame_counts: [81],
  enabled: true,
}

const modelList: ModelList = {
  items: [modelCapability],
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function expectInvalidJobResponse(payload: unknown): Promise<void> {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(payload))
  const client = new ApiClient({ fetch: fetchMock })

  const caught: unknown = await client.getJob('job-1').catch((error: unknown) => error)

  expect(caught).toBeInstanceOf(ApiClientError)
  expect(caught).toMatchObject({
    kind: 'invalid_response',
    status: 200,
    code: 'INTERNAL_ERROR',
    message: 'The application returned an invalid response.',
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ApiClient', () => {
  it('submits the exact snake_case request body without putting the prompt in the URL', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(queuedJob, 202))
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const controller = new AbortController()
    const client = new ApiClient({
      baseUrl: 'https://video.example/',
      fetch: fetchMock,
    })

    await expect(client.submitJob(request, controller.signal)).resolves.toEqual(queuedJob)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const call = fetchMock.mock.calls[0]
    if (call === undefined) {
      throw new Error('expected fetch to be called')
    }
    const [input, init] = call
    if (typeof input !== 'string') {
      throw new Error('expected the client to call fetch with a URL string')
    }
    expect(input).toBe('https://video.example/api/v1/jobs')
    expect(input).not.toContain(request.prompt)
    expect(init).toMatchObject({
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      signal: controller.signal,
    })
    if (typeof init?.body !== 'string') {
      throw new Error('expected a JSON request body')
    }
    expect(JSON.parse(init.body)).toEqual(request)
    expect(log).not.toHaveBeenCalled()
    expect(warn).not.toHaveBeenCalled()
    expect(error).not.toHaveBeenCalled()
  })

  it('encodes cursor and status filters with the API query names', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({
        items: [queuedJob],
        next_cursor: 'next opaque cursor',
      }),
    )
    const client = new ApiClient({ baseUrl: 'https://video.example', fetch: fetchMock })

    await client.listJobs({
      limit: 25,
      cursor: 'opaque +/=?& cursor',
      status: 'running',
    })

    const call = fetchMock.mock.calls[0]
    if (call === undefined) {
      throw new Error('expected fetch to be called')
    }
    const [input, init] = call
    if (typeof input !== 'string') {
      throw new Error('expected the client to call fetch with a URL string')
    }
    const url = new URL(input)
    expect(url.pathname).toBe('/api/v1/jobs')
    expect(url.searchParams.get('limit')).toBe('25')
    expect(url.searchParams.get('cursor')).toBe('opaque +/=?& cursor')
    expect(url.searchParams.get('status')).toBe('running')
    expect(init?.method).toBe('GET')
  })

  it('URL-encodes opaque job IDs for get, cancel, and output operations', async () => {
    const video = new Uint8Array([0, 0, 0, 8, 102, 116, 121, 112])
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(queuedJob))
      .mockResolvedValueOnce(jsonResponse(cancelledJob))
      .mockResolvedValueOnce(
        new Response(video, {
          status: 200,
          headers: { 'Content-Type': 'video/mp4' },
        }),
      )
    const client = new ApiClient({ baseUrl: 'https://video.example/', fetch: fetchMock })
    const jobId = 'job/with spaces?#'
    const encoded = 'job%2Fwith%20spaces%3F%23'

    await client.getJob(jobId)
    await client.cancelJob(jobId)
    const blob = await client.getOutput(jobId)

    expect(fetchMock.mock.calls[0]?.[0]).toBe(`https://video.example/api/v1/jobs/${encoded}`)
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`https://video.example/api/v1/jobs/${encoded}/cancel`)
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe('POST')
    expect(fetchMock.mock.calls[2]?.[0]).toBe(`https://video.example/api/v1/jobs/${encoded}/output`)
    expect(client.outputUrl(jobId)).toBe(`https://video.example/api/v1/jobs/${encoded}/output`)
    expect(blob.type).toBe('video/mp4')
    expect(blob.size).toBe(video.byteLength)
  })

  it('accepts documented progress, result, and failure job envelopes', async () => {
    const jobs: [Job, Job, Job] = [runningJob, succeededJob, failedJob]
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(jobs[0]))
      .mockResolvedValueOnce(jsonResponse(jobs[1]))
      .mockResolvedValueOnce(jsonResponse(jobs[2]))
    const client = new ApiClient({ fetch: fetchMock })

    await expect(client.getJob('running')).resolves.toEqual(jobs[0])
    await expect(client.getJob('succeeded')).resolves.toEqual(jobs[1])
    await expect(client.getJob('failed')).resolves.toEqual(jobs[2])
  })

  it('accepts the API serializer encoding for an opaque result job ID', async () => {
    const opaqueId = "job!'()*"
    const serializedJob: Job = {
      ...succeededJob,
      id: opaqueId,
      result: {
        ...successfulResult,
        download_url: '/api/v1/jobs/job%21%27%28%29%2A/output',
      },
    }
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(serializedJob))

    await expect(new ApiClient({ fetch: fetchMock }).getJob(opaqueId)).resolves.toEqual(
      serializedJob,
    )
  })

  it('maps model discovery and health without changing their JSON fields', async () => {
    const health: Health = { status: 'ok' }
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(modelList))
      .mockResolvedValueOnce(jsonResponse(health))
    const client = new ApiClient({ fetch: fetchMock })

    await expect(client.listModels()).resolves.toEqual(modelList)
    await expect(client.health()).resolves.toEqual(health)

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/models')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/health')
    expect(videoApi).toBeInstanceOf(ApiClient)
  })

  it.each([
    {
      name: 'health status',
      payload: { status: 'degraded' },
      invoke: (client: ApiClient) => client.health(),
    },
    {
      name: 'model resolution',
      payload: {
        items: [
          {
            ...modelCapability,
            resolutions: [{ width: '832', height: 480 }],
          },
        ],
      },
      invoke: (client: ApiClient) => client.listModels(),
    },
    {
      name: 'whitespace-only model display identifier',
      payload: {
        items: [{ ...modelCapability, display_name: '   ' }],
      },
      invoke: (client: ApiClient) => client.listModels(),
    },
    {
      name: 'normalized request',
      payload: {
        ...queuedJob,
        request: { ...queuedJob.request, seed: null },
      },
      invoke: (client: ApiClient) => client.getJob('job-1'),
    },
    {
      name: 'whitespace-only normalized prompt',
      payload: {
        ...queuedJob,
        request: { ...queuedJob.request, prompt: '   ' },
      },
      invoke: (client: ApiClient) => client.getJob('job-1'),
    },
    {
      name: 'progress',
      payload: {
        ...runningJob,
        progress: {
          completed_units: 3,
          total_units: 2,
          stage: 'diffusion',
        },
      },
      invoke: (client: ApiClient) => client.getJob('job-1'),
    },
    {
      name: 'whitespace-only progress stage',
      payload: {
        ...runningJob,
        progress: { ...runningJob.progress, stage: '   ' },
      },
      invoke: (client: ApiClient) => client.getJob('job-1'),
    },
    {
      name: 'result',
      payload: {
        ...succeededJob,
        result: {
          ...successfulResult,
          sha256: 'not-a-sha256',
        },
      },
      invoke: (client: ApiClient) => client.getJob('job-1'),
    },
    {
      name: 'zero result duration',
      payload: {
        ...succeededJob,
        result: { ...successfulResult, duration_seconds: 0 },
      },
      invoke: (client: ApiClient) => client.getJob('job-1'),
    },
    {
      name: 'absolute result download URL',
      payload: {
        ...succeededJob,
        result: {
          ...successfulResult,
          download_url: 'https://untrusted.example/video.mp4',
        },
      },
      invoke: (client: ApiClient) => client.getJob('job-1'),
    },
    {
      name: 'whitespace-only failure message',
      payload: {
        ...failedJob,
        failure: { ...generationFailure, message: '   ' },
      },
      invoke: (client: ApiClient) => client.getJob('job-1'),
    },
    {
      name: 'failure',
      payload: {
        ...queuedJob,
        status: 'failed',
        completed_at: '2026-08-21T10:05:00Z',
        failure: {
          code: 'RAW_BACKEND_ERROR',
          message: 'Video generation failed.',
          retryable: true,
          job_id: 'job-1',
          correlation_id: 'correlation-1',
        },
      },
      invoke: (client: ApiClient) => client.getJob('job-1'),
    },
    {
      name: 'job page cursor',
      payload: { items: [queuedJob], next_cursor: 42 },
      invoke: (client: ApiClient) => client.listJobs(),
    },
  ])('fails closed for a malformed $name success envelope', async ({ payload, invoke }) => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(payload))
    const client = new ApiClient({ fetch: fetchMock })

    const caught: unknown = await invoke(client).catch((error: unknown) => error)

    expect(caught).toBeInstanceOf(ApiClientError)
    expect(caught).toMatchObject({
      kind: 'invalid_response',
      status: 200,
      code: 'INTERNAL_ERROR',
      message: 'The application returned an invalid response.',
    })
  })

  it.each([
    {
      name: 'queued job with execution identity',
      payload: {
        ...queuedJob,
        updated_at: startedAt,
        started_at: startedAt,
        backend: 'fake',
        model_revision: 'fake-v1',
      },
    },
    {
      name: 'queued job with a result',
      payload: { ...queuedJob, result: successfulResult },
    },
    {
      name: 'running job with completion data',
      payload: { ...runningJob, updated_at: completedAt, completed_at: completedAt },
    },
    {
      name: 'succeeded job without a result',
      payload: { ...succeededJob, result: null },
    },
    {
      name: 'succeeded job with a failure',
      payload: { ...succeededJob, failure: generationFailure },
    },
    {
      name: 'succeeded job retaining progress',
      payload: { ...succeededJob, progress: runningJob.progress },
    },
    {
      name: 'failed job without a failure',
      payload: { ...failedJob, failure: null },
    },
    {
      name: 'failed job with a result',
      payload: { ...failedJob, result: successfulResult },
    },
    {
      name: 'failed job retaining progress',
      payload: { ...failedJob, progress: runningJob.progress },
    },
    {
      name: 'failed job with partial execution identity',
      payload: { ...failedJob, backend: null },
    },
    {
      name: 'cancelled job without completion',
      payload: { ...cancelledJob, completed_at: null },
    },
    {
      name: 'cancelled job with a terminal payload',
      payload: { ...cancelledJob, failure: generationFailure },
    },
    {
      name: 'cancelled job retaining progress',
      payload: { ...cancelledJob, progress: runningJob.progress },
    },
    {
      name: 'cancelled job with partial execution identity',
      payload: { ...cancelledJob, model_revision: null },
    },
  ])('fails closed for an impossible $name', async ({ payload }) => {
    await expectInvalidJobResponse(payload)
  })

  it.each([
    {
      name: 'updated_at before created_at',
      payload: { ...queuedJob, updated_at: '2026-08-21T09:59:00Z' },
    },
    {
      name: 'started_at before created_at',
      payload: { ...runningJob, started_at: '2026-08-21T09:59:00Z' },
    },
    {
      name: 'started_at after updated_at',
      payload: { ...runningJob, started_at: '2026-08-21T10:02:00Z' },
    },
    {
      name: 'completed_at before started_at',
      payload: { ...succeededJob, completed_at: '2026-08-21T10:00:30Z' },
    },
    {
      name: 'completed_at after updated_at',
      payload: { ...succeededJob, completed_at: '2026-08-21T10:06:00Z' },
    },
  ])('fails closed when $name', async ({ payload }) => {
    await expectInvalidJobResponse(payload)
  })

  it('fails closed when failure.job_id does not match its job', async () => {
    await expectInvalidJobResponse({
      ...failedJob,
      failure: { ...generationFailure, job_id: 'different-job' },
    })
  })

  it.each([
    { name: 'width', result: { ...successfulResult, width: 1_280 } },
    { name: 'height', result: { ...successfulResult, height: 720 } },
    { name: 'frame count', result: { ...successfulResult, frame_count: 121 } },
  ])('fails closed when result $name differs from the normalized request', async ({ result }) => {
    await expectInvalidJobResponse({ ...succeededJob, result })
  })

  it('throws a typed error containing only the API safe error envelope', async () => {
    const payload: ApiError = {
      code: 'INVALID_REQUEST',
      message: 'Request validation failed.',
      retryable: false,
      correlation_id: 'correlation-1',
      job_id: null,
      fields: ['width'],
    }
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(payload, 422))
    const client = new ApiClient({ fetch: fetchMock })

    const caught: unknown = await client.submitJob(request).catch((error: unknown) => error)

    expect(isApiClientError(caught)).toBe(true)
    if (!isApiClientError(caught)) {
      throw new Error('expected ApiClientError')
    }
    expect(caught).toMatchObject({
      name: 'ApiClientError',
      kind: 'api',
      status: 422,
      code: 'INVALID_REQUEST',
      message: 'Request validation failed.',
      retryable: false,
      correlation_id: 'correlation-1',
      job_id: null,
      fields: ['width'],
    })
  })

  it('does not expose malformed response bodies or network exception text', async () => {
    const privateText = 'private prompt at C:/secret/checkpoint'
    const malformedFetch = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(privateText, { status: 500 }))
    const networkFetch = vi.fn<typeof fetch>().mockRejectedValue(new Error(privateText))

    const malformed: unknown = await new ApiClient({ fetch: malformedFetch })
      .health()
      .catch((error: unknown) => error)
    const network: unknown = await new ApiClient({ fetch: networkFetch })
      .health()
      .catch((error: unknown) => error)

    expect(malformed).toBeInstanceOf(ApiClientError)
    expect(network).toBeInstanceOf(ApiClientError)
    expect(String(malformed)).toContain('invalid response')
    expect(String(network)).toContain('Unable to reach')
    expect(String(malformed)).not.toContain(privateText)
    expect(String(network)).not.toContain(privateText)
  })

  it('passes AbortSignal through and preserves the platform abort rejection', async () => {
    const abortError = new Error('abort sentinel')
    const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(abortError)
    const controller = new AbortController()
    controller.abort()
    const client = new ApiClient({ fetch: fetchMock })

    await expect(client.health(controller.signal)).rejects.toBe(abortError)
    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBe(controller.signal)
  })
})
