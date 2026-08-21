import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import App from './App'

type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

interface JobFixture {
  id: string
  status: JobStatus
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
  request: {
    mode: 'text_to_video'
    prompt: string
    model: string
    width: number
    height: number
    frame_count: number
    seed: number
  }
  backend: string | null
  model_revision: string | null
  progress: {
    completed_units: number
    total_units: number
    stage: string
  } | null
  result: {
    media_type: 'video/mp4'
    download_url: string
    width: number
    height: number
    frame_count: number
    duration_seconds: number | null
    size_bytes: number
    sha256: string
    created_at: string
  } | null
  failure: {
    code: string
    message: string
    retryable: boolean
    job_id: string
    correlation_id: string
  } | null
}

const NOW = '2026-08-21T10:00:00Z'
const MODEL_RESPONSE = {
  items: [
    {
      id: 'wan21-t2v',
      display_name: 'Wan2.1 Text to Video',
      modes: ['text_to_video'],
      resolutions: [
        { width: 832, height: 480 },
        { width: 1280, height: 720 },
      ],
      frame_counts: [81, 121],
      enabled: true,
    },
  ],
}

function makeJob(status: JobStatus = 'queued', id = `job-${status}`): JobFixture {
  const terminal = status === 'succeeded' || status === 'failed' || status === 'cancelled'
  return {
    id,
    status,
    created_at: NOW,
    updated_at: NOW,
    started_at: status === 'queued' ? null : NOW,
    completed_at: terminal ? NOW : null,
    request: {
      mode: 'text_to_video',
      prompt: `${status} cinematic prompt`,
      model: 'wan21-t2v',
      width: 832,
      height: 480,
      frame_count: 81,
      seed: 42,
    },
    backend: status === 'queued' ? null : 'wan21',
    model_revision: status === 'queued' ? null : 'wan21-revision',
    progress: null,
    result:
      status === 'succeeded'
        ? {
            media_type: 'video/mp4',
            download_url: `/api/v1/jobs/${id}/output`,
            width: 832,
            height: 480,
            frame_count: 81,
            duration_seconds: 5,
            size_bytes: 123_456,
            sha256: 'a'.repeat(64),
            created_at: NOW,
          }
        : null,
    failure:
      status === 'failed'
        ? {
            code: 'GENERATION_FAILED',
            message: 'Video generation failed.',
            retryable: true,
            job_id: id,
            correlation_id: 'correlation-safe',
          }
        : null,
  }
}

interface ListReply {
  status?: number
  body: unknown
}

interface ApiScenario {
  jobs?: JobFixture[]
  listReplies?: ListReply[]
  listHandler?: (url: URL, requestIndex: number) => Promise<Response>
  healthReply?: ListReply
  getJobs?: Readonly<Record<string, JobFixture>>
  getJobHandler?: (jobId: string, requestIndex: number) => Promise<Response>
  submittedJob?: JobFixture
  cancelledJob?: JobFixture
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function requestUrl(input: RequestInfo | URL): URL {
  if (typeof input === 'string') {
    return new URL(input, window.location.origin)
  }
  if (input instanceof URL) {
    return input
  }
  return new URL(input.url, window.location.origin)
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) {
    return init.method.toUpperCase()
  }
  return typeof input === 'object' && 'method' in input ? input.method.toUpperCase() : 'GET'
}

function installApi(scenario: ApiScenario = {}): ReturnType<typeof vi.fn> {
  let jobs = [...(scenario.jobs ?? [])]
  let listReplyIndex = 0
  let listRequestIndex = 0
  let getJobRequestIndex = 0
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = requestUrl(input)
    const method = requestMethod(input, init)

    if (method === 'GET' && url.pathname === '/api/v1/models') {
      return Promise.resolve(jsonResponse(MODEL_RESPONSE))
    }
    if (method === 'GET' && url.pathname === '/api/v1/health') {
      const reply = scenario.healthReply
      return Promise.resolve(
        reply === undefined
          ? jsonResponse({ status: 'ok' })
          : jsonResponse(reply.body, reply.status ?? 200),
      )
    }
    if (method === 'GET' && url.pathname === '/api/v1/jobs') {
      if (scenario.listHandler !== undefined) {
        const requestIndex = listRequestIndex
        listRequestIndex += 1
        return scenario.listHandler(url, requestIndex)
      }
      const replies = scenario.listReplies
      if (replies && replies.length > 0) {
        const reply = replies[Math.min(listReplyIndex, replies.length - 1)]
        if (reply === undefined) {
          throw new Error('List reply fixture is missing.')
        }
        listReplyIndex += 1
        return Promise.resolve(jsonResponse(reply.body, reply.status ?? 200))
      }
      return Promise.resolve(jsonResponse({ items: jobs, next_cursor: null }))
    }
    const jobMatch = /^\/api\/v1\/jobs\/([^/]+)$/.exec(url.pathname)
    if (method === 'GET' && jobMatch) {
      const encodedJobId = jobMatch[1]
      if (encodedJobId === undefined) {
        throw new Error('Job request fixture is missing an identifier.')
      }
      const jobId = decodeURIComponent(encodedJobId)
      if (scenario.getJobHandler !== undefined) {
        const requestIndex = getJobRequestIndex
        getJobRequestIndex += 1
        return scenario.getJobHandler(jobId, requestIndex)
      }
      const job = scenario.getJobs?.[jobId]
      if (job === undefined) {
        throw new Error(`Unexpected job request: ${jobId}`)
      }
      return Promise.resolve(jsonResponse(job))
    }
    if (method === 'POST' && url.pathname === '/api/v1/jobs') {
      const submitted = scenario.submittedJob ?? makeJob('queued', 'job-submitted')
      jobs = [submitted, ...jobs]
      return Promise.resolve(jsonResponse(submitted, 202))
    }
    const cancelMatch = /^\/api\/v1\/jobs\/([^/]+)\/cancel$/.exec(url.pathname)
    if (method === 'POST' && cancelMatch) {
      const cancelled = scenario.cancelledJob ?? makeJob('cancelled', cancelMatch[1])
      jobs = jobs.map((job) => (job.id === cancelled.id ? cancelled : job))
      return Promise.resolve(jsonResponse(cancelled))
    }

    throw new Error(`Unexpected API request: ${method} ${url.pathname}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function matchingCall(
  fetchMock: ReturnType<typeof vi.fn>,
  method: string,
  pathname: string,
): [RequestInfo | URL, RequestInit | undefined] | undefined {
  return fetchMock.mock.calls.find(([input, init]) => {
    const typedInput = input as RequestInfo | URL
    const typedInit = init as RequestInit | undefined
    return (
      requestMethod(typedInput, typedInit) === method &&
      requestUrl(typedInput).pathname === pathname
    )
  }) as [RequestInfo | URL, RequestInit | undefined] | undefined
}

function matchingCalls(
  fetchMock: ReturnType<typeof vi.fn>,
  method: string,
  pathname: string,
): [RequestInfo | URL, RequestInit | undefined][] {
  return fetchMock.mock.calls.filter(([input, init]) => {
    const typedInput = input as RequestInfo | URL
    const typedInit = init as RequestInit | undefined
    return (
      requestMethod(typedInput, typedInit) === method &&
      requestUrl(typedInput).pathname === pathname
    )
  }) as [RequestInfo | URL, RequestInit | undefined][]
}

describe('App', () => {
  it('builds generation settings from the discovered model capabilities', async () => {
    const user = userEvent.setup()
    installApi()
    render(<App />)

    const model = await screen.findByLabelText('Model')
    const resolution = screen.getByLabelText('Resolution')
    const frames = screen.getByLabelText('Frames')

    await waitFor(() => expect(model).toHaveTextContent('Wan2.1 Text to Video'))
    expect(resolution).toBeDisabled()
    expect(frames).toBeDisabled()

    await user.selectOptions(model, 'wan21-t2v')

    expect(resolution).toHaveTextContent(/832\s*[×x]\s*480/)
    expect(resolution).toHaveTextContent(/1280\s*[×x]\s*720/)
    expect(frames).toHaveTextContent('81')
    expect(frames).toHaveTextContent('121')
    expect(screen.getByLabelText('Seed (optional)')).toHaveValue('')
  })

  it('keeps the latest job selection when an earlier detail request resolves last', async () => {
    const user = userEvent.setup()
    const first = makeJob('failed', 'job-first-selection')
    const second = makeJob('failed', 'job-second-selection')
    let settleSecond: ((response: Response) => void) | undefined
    installApi({
      jobs: [first, second],
      getJobHandler: (jobId) => {
        if (jobId === second.id) {
          return new Promise((resolve) => {
            settleSecond = resolve
          })
        }
        return Promise.resolve(jsonResponse(first))
      },
    })
    render(<App />)

    const firstRow = await screen.findByRole('button', {
      name: `Open generation ${first.id}`,
    })
    const secondRow = screen.getByRole('button', {
      name: `Open generation ${second.id}`,
    })
    await user.click(secondRow)
    await waitFor(() => expect(settleSecond).toBeDefined())
    expect(secondRow).toHaveAttribute('aria-current', 'true')

    await user.click(firstRow)
    expect(firstRow).toHaveAttribute('aria-current', 'true')

    const settle = settleSecond
    if (settle === undefined) {
      throw new Error('Deferred second-job response did not start.')
    }
    await act(async () => {
      settle(jsonResponse(second))
      await Promise.resolve()
    })

    expect(firstRow).toHaveAttribute('aria-current', 'true')
    expect(secondRow).not.toHaveAttribute('aria-current')
  })

  it('submits the normalized form and renders the accepted queued job', async () => {
    const user = userEvent.setup()
    const submitted = makeJob('queued', 'job-new')
    submitted.request.prompt = 'A quiet moonlit lake'
    submitted.request.seed = 73
    const fetchMock = installApi({ submittedJob: submitted })
    render(<App />)

    const prompt = await screen.findByLabelText('Prompt')
    await user.type(prompt, 'A quiet moonlit lake')
    await user.selectOptions(screen.getByLabelText('Model'), 'wan21-t2v')
    await user.selectOptions(screen.getByLabelText('Resolution'), '832x480')
    await user.selectOptions(screen.getByLabelText('Frames'), '81')
    await user.type(screen.getByLabelText('Seed (optional)'), '73')
    await user.click(screen.getByRole('button', { name: 'Generate video' }))

    await waitFor(() => {
      expect(matchingCall(fetchMock, 'POST', '/api/v1/jobs')).toBeDefined()
    })
    const call = matchingCall(fetchMock, 'POST', '/api/v1/jobs')
    expect(call).toBeDefined()
    const body = call?.[1]?.body
    if (typeof body !== 'string') {
      throw new Error('Submit request fixture did not receive a JSON body.')
    }
    const payload = JSON.parse(body) as Record<string, unknown>
    expect(payload).toMatchObject({
      mode: 'text_to_video',
      prompt: 'A quiet moonlit lake',
      model: 'wan21-t2v',
      width: 832,
      height: 480,
      frame_count: 81,
      seed: 73,
    })
    expect((await screen.findAllByText(/queued/i)).length).toBeGreaterThan(0)
  })

  it('blocks an unsafe manual seed without sending a request and focuses the seed field', async () => {
    const user = userEvent.setup()
    const fetchMock = installApi()
    render(<App />)

    await user.type(await screen.findByLabelText('Prompt'), 'A precise orbital camera move')
    await user.selectOptions(screen.getByLabelText('Model'), 'wan21-t2v')
    await user.selectOptions(screen.getByLabelText('Resolution'), '832x480')
    await user.selectOptions(screen.getByLabelText('Frames'), '81')
    const seed = screen.getByLabelText('Seed (optional)')
    await user.type(seed, String(Number.MAX_SAFE_INTEGER + 1))
    await user.click(screen.getByRole('button', { name: 'Generate video' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Seed must be a safe whole number or left blank.',
    )
    await waitFor(() => expect(seed).toHaveFocus())
    expect(matchingCall(fetchMock, 'POST', '/api/v1/jobs')).toBeUndefined()
  })

  it('does not display an imprecise server seed outside JavaScript safe integers', async () => {
    const succeeded = makeJob('succeeded', 'job-server-seed')
    succeeded.request.seed = Number.MAX_SAFE_INTEGER + 1
    installApi({ jobs: [succeeded] })
    render(<App />)

    expect((await screen.findAllByText('Stored by server')).length).toBeGreaterThan(0)
    expect(screen.queryByText(String(Number.MAX_SAFE_INTEGER + 1))).not.toBeInTheDocument()
  })

  it.each(['queued', 'running'] as const)(
    'shows %s work as indeterminate when the API has no reliable progress',
    async (status) => {
      installApi({ jobs: [makeJob(status)] })
      render(<App />)

      const progress = await screen.findByRole('progressbar', {
        name: 'Generation progress',
      })
      expect(progress).not.toHaveAttribute('aria-valuenow')
      expect(screen.queryByText(/estimated|remaining|% complete/i)).not.toBeInTheDocument()
    },
  )

  it('exposes reliable backend progress units and stage through progressbar semantics', async () => {
    const running = makeJob('running', 'job-progress')
    running.progress = {
      completed_units: 12,
      total_units: 40,
      stage: 'diffusion',
    }
    installApi({ jobs: [running] })
    render(<App />)

    const progress = await screen.findByRole('progressbar', {
      name: 'Generation progress',
    })
    expect(progress).toHaveAttribute('aria-valuenow', '12')
    expect(progress).toHaveAttribute('aria-valuemax', '40')
    expect(progress).toHaveAttribute('aria-valuetext', expect.stringMatching(/30%.*diffusion/i))
    expect(screen.getByText(/diffusion.*12.*40/i)).toBeInTheDocument()
  })

  it('shows a safe recoverable API error and retries without exposing internals', async () => {
    const user = userEvent.setup()
    installApi({
      listReplies: [
        {
          status: 503,
          body: {
            code: 'INTERNAL_ERROR',
            message: 'The application is temporarily unavailable.',
            retryable: true,
            correlation_id: 'correlation-safe',
            job_id: null,
            fields: [],
          },
        },
        { body: { items: [], next_cursor: null } },
      ],
    })
    render(<App />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The application is temporarily unavailable.')
    expect(alert).not.toHaveTextContent(/C:\\|checkpoint|traceback|private prompt/i)

    await user.click(screen.getByRole('button', { name: 'Retry connection' }))
    expect(await screen.findByText(/no (generations|jobs)/i)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps capability-driven controls usable when the independent health check fails', async () => {
    installApi({
      healthReply: {
        status: 503,
        body: {
          code: 'INTERNAL_ERROR',
          message: 'The application is temporarily unavailable.',
          retryable: true,
          correlation_id: 'correlation-health',
          job_id: null,
          fields: [],
        },
      },
    })
    render(<App />)

    const model = await screen.findByLabelText('Model')
    await waitFor(() => expect(model).toBeEnabled())
    expect(model).toHaveTextContent('Wan2.1 Text to Video')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The application is temporarily unavailable.',
    )
  })

  it('requests cancellation for the selected running job and renders the terminal response', async () => {
    const user = userEvent.setup()
    const running = makeJob('running', 'job-cancel-me')
    const cancelled = makeJob('cancelled', running.id)
    const fetchMock = installApi({ jobs: [running], cancelledJob: cancelled })
    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'Cancel generation' }))

    await waitFor(() => {
      expect(matchingCall(fetchMock, 'POST', '/api/v1/jobs/job-cancel-me/cancel')).toBeDefined()
    })
    expect((await screen.findAllByText(/cancelled/i)).length).toBeGreaterThan(0)
  })

  it('shows cooperative cleanup when a running cancellation response remains running', async () => {
    const user = userEvent.setup()
    const running = makeJob('running', 'job-cleaning-up')
    const stillRunning = makeJob('running', running.id)
    installApi({ jobs: [running], cancelledJob: stillRunning })
    render(<App />)

    await screen.findByRole('progressbar', { name: 'Generation progress' })
    await user.click(screen.getByRole('button', { name: 'Cancel generation' }))

    expect(
      await screen.findByText('Cancellation requested. The worker is cleaning up safely.'),
    ).toHaveAttribute('role', 'status')
    expect(screen.getByRole('button', { name: 'Cancel generation' })).toBeDisabled()
    expect(screen.queryByText(/^Cancelled$/, { selector: '.status-badge' })).not.toBeInTheDocument()
  })

  it('offers an application-served preview and download for a successful job', async () => {
    const succeeded = makeJob('succeeded', 'job-ready')
    installApi({ jobs: [succeeded] })
    render(<App />)

    const preview = await screen.findByLabelText('Generated video preview')
    const download = screen.getByRole('link', { name: 'Download video' })
    expect(preview).toHaveAttribute('src', '/api/v1/jobs/job-ready/output')
    expect(download).toHaveAttribute('href', '/api/v1/jobs/job-ready/output')
    expect(download).toHaveAttribute('download')
  })

  it('recovers an unavailable output after a refreshed snapshot or successful media load', async () => {
    const user = userEvent.setup()
    installApi({ jobs: [makeJob('succeeded', 'job-missing-output')] })
    render(<App />)

    let preview = await screen.findByLabelText('Generated video preview')
    fireEvent.error(preview)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This video output is currently unavailable.',
    )

    const failedPreview = preview
    await user.click(screen.getByRole('button', { name: 'Refresh jobs' }))
    await waitFor(() => {
      expect(
        screen.queryByText('This video output is currently unavailable.', { exact: false }),
      ).not.toBeInTheDocument()
    })

    preview = screen.getByLabelText('Generated video preview')
    expect(preview).not.toBe(failedPreview)
    fireEvent.error(preview)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This video output is currently unavailable.',
    )
    fireEvent.loadedData(preview)
    expect(
      screen.queryByText('This video output is currently unavailable.', { exact: false }),
    ).not.toBeInTheDocument()
  })

  it('renders an empty recent-jobs state with a manual refresh action', async () => {
    installApi()
    render(<App />)

    expect(await screen.findByText(/no (generations|jobs)/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh jobs' })).toBeEnabled()
  })

  it('sends the exact status filter and merges cursor pages without duplicate jobs', async () => {
    const user = userEvent.setup()
    const first = makeJob('failed', 'job-failed-newer')
    const older = makeJob('failed', 'job-failed-older')
    const fetchMock = installApi({
      listReplies: [
        { body: { items: [], next_cursor: null } },
        { body: { items: [first], next_cursor: 'opaque+/cursor' } },
        { body: { items: [first, older], next_cursor: null } },
      ],
    })
    render(<App />)

    await screen.findByText('No generations yet')
    await user.selectOptions(screen.getByLabelText('Filter jobs'), 'failed')
    await screen.findByRole('button', { name: `Open generation ${first.id}` })
    await user.click(screen.getByRole('button', { name: 'Load older jobs' }))
    await screen.findByRole('button', { name: `Open generation ${older.id}` })

    const listUrls = matchingCalls(fetchMock, 'GET', '/api/v1/jobs').map(([input]) =>
      requestUrl(input),
    )
    expect(
      listUrls.some(
        (url) => url.searchParams.get('status') === 'failed' && !url.searchParams.has('cursor'),
      ),
    ).toBe(true)
    expect(
      listUrls.some(
        (url) =>
          url.searchParams.get('status') === 'failed' &&
          url.searchParams.get('cursor') === 'opaque+/cursor',
      ),
    ).toBe(true)
    expect(screen.getAllByRole('button', { name: `Open generation ${first.id}` })).toHaveLength(1)
  })

  it('discards an old cursor page when the status filter changes during loading', async () => {
    const user = userEvent.setup()
    const first = makeJob('succeeded', 'job-ready-newer')
    const staleOlder = makeJob('succeeded', 'job-ready-stale-older')
    const filtered = makeJob('failed', 'job-filtered-failure')
    let settleOlder: ((response: Response) => void) | undefined
    let settleFiltered: ((response: Response) => void) | undefined
    installApi({
      listHandler: (url) => {
        if (url.searchParams.get('cursor') === 'older-ready-jobs') {
          return new Promise((resolve) => {
            settleOlder = resolve
          })
        }
        if (url.searchParams.get('status') === 'failed') {
          return new Promise((resolve) => {
            settleFiltered = resolve
          })
        }
        return Promise.resolve(jsonResponse({ items: [first], next_cursor: 'older-ready-jobs' }))
      },
    })
    render(<App />)

    await screen.findByRole('button', { name: `Open generation ${first.id}` })
    await user.click(screen.getByRole('button', { name: 'Load older jobs' }))
    await waitFor(() => expect(settleOlder).toBeDefined())

    await user.selectOptions(screen.getByLabelText('Filter jobs'), 'failed')
    await waitFor(() => expect(settleFiltered).toBeDefined())
    expect(screen.getByRole('button', { name: 'Refreshing…' })).toBeDisabled()

    const finishOlder = settleOlder
    if (finishOlder === undefined) {
      throw new Error('Deferred cursor response did not start.')
    }
    await act(async () => {
      finishOlder(jsonResponse({ items: [staleOlder], next_cursor: 'stale-cursor' }))
      await Promise.resolve()
    })
    expect(screen.getByRole('button', { name: 'Refreshing…' })).toBeDisabled()
    expect(
      screen.queryByRole('button', { name: `Open generation ${staleOlder.id}` }),
    ).not.toBeInTheDocument()

    const finishFiltered = settleFiltered
    if (finishFiltered === undefined) {
      throw new Error('Deferred filtered response did not start.')
    }
    await act(async () => {
      finishFiltered(jsonResponse({ items: [filtered], next_cursor: null }))
      await Promise.resolve()
    })

    expect(
      await screen.findByRole('button', { name: `Open generation ${filtered.id}` }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: `Open generation ${staleOlder.id}` }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load older jobs' })).not.toBeInTheDocument()
  })

  it('clears active-job polling when the application unmounts', async () => {
    const intervalId = 73
    const setInterval = vi.spyOn(window, 'setInterval').mockReturnValue(intervalId)
    const clearInterval = vi.spyOn(window, 'clearInterval')
    installApi({ jobs: [makeJob('running')] })

    const view = render(<App />)
    await screen.findByRole('heading', { name: 'Generation details' })
    await waitFor(() => expect(setInterval).toHaveBeenCalled())

    view.unmount()
    expect(clearInterval).toHaveBeenCalledWith(intervalId)
  })

  it('refreshes an active selected job outside the filtered page without overlapping polls', async () => {
    const user = userEvent.setup()
    const active = makeJob('running', 'job-selected-active')
    const refreshedActive = makeJob('running', active.id)
    refreshedActive.request.prompt = 'refreshed selected prompt'
    const filtered = makeJob('failed', 'job-filter-match')
    let settleScheduledList: ((response: Response) => void) | undefined
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    const setInterval = vi.spyOn(window, 'setInterval').mockReturnValue(91)
    const fetchMock = installApi({
      getJobs: { [active.id]: refreshedActive },
      listHandler: (_url, requestIndex) => {
        if (requestIndex === 0) {
          return Promise.resolve(jsonResponse({ items: [active], next_cursor: null }))
        }
        if (requestIndex === 1) {
          return Promise.resolve(jsonResponse({ items: [filtered], next_cursor: null }))
        }
        return new Promise((resolve) => {
          settleScheduledList = resolve
        })
      },
    })
    render(<App />)

    await screen.findByRole('progressbar', { name: 'Generation progress' })
    const pollRegistrations = () =>
      setInterval.mock.calls.filter(([, timeout]) => timeout === 2_500)
    await waitFor(() => expect(pollRegistrations().length).toBeGreaterThan(0))
    const registrationsBeforeFilter = pollRegistrations().length
    await user.selectOptions(screen.getByLabelText('Filter jobs'), 'failed')
    expect(await screen.findByText('refreshed selected prompt')).toBeInTheDocument()
    expect(matchingCall(fetchMock, 'GET', '/api/v1/jobs/job-selected-active')).toBeDefined()
    await waitFor(() => {
      expect(pollRegistrations().length).toBeGreaterThan(registrationsBeforeFilter)
    })
    await waitFor(() => {
      expect(
        screen
          .getAllByRole('button', { name: 'Refresh jobs' })
          .every((button) => !button.hasAttribute('disabled')),
      ).toBe(true)
    })

    const intervalRegistration = pollRegistrations().at(-1)
    const scheduledPoll = intervalRegistration?.[0] as (() => void) | undefined
    if (typeof scheduledPoll !== 'function') {
      throw new Error('Active-job polling fixture was not registered.')
    }
    expect(document.visibilityState).toBe('visible')
    scheduledPoll()
    scheduledPoll()
    await waitFor(() => {
      expect(matchingCalls(fetchMock, 'GET', '/api/v1/jobs')).toHaveLength(3)
    })

    const settle = settleScheduledList
    if (settle === undefined) {
      throw new Error('Scheduled list fixture did not start.')
    }
    await act(async () => {
      settle(jsonResponse({ items: [filtered], next_cursor: null }))
      await Promise.resolve()
    })
    expect(matchingCalls(fetchMock, 'GET', '/api/v1/jobs')).toHaveLength(3)
  })

  it('re-lists a filter when the selected active job transitions into it', async () => {
    const user = userEvent.setup()
    const running = makeJob('running', 'job-enters-failed-filter')
    const failed = makeJob('failed', running.id)
    let failedListRequests = 0
    let selectedRefreshes = 0
    const setInterval = vi.spyOn(window, 'setInterval').mockReturnValue(127)
    installApi({
      listHandler: (url) => {
        if (url.searchParams.get('status') !== 'failed') {
          return Promise.resolve(jsonResponse({ items: [running], next_cursor: null }))
        }
        failedListRequests += 1
        return Promise.resolve(
          jsonResponse({
            items: failedListRequests >= 3 ? [failed] : [],
            next_cursor: null,
          }),
        )
      },
      getJobHandler: () => {
        selectedRefreshes += 1
        return Promise.resolve(jsonResponse(selectedRefreshes >= 2 ? failed : running))
      },
    })
    render(<App />)

    await screen.findByRole('progressbar', { name: 'Generation progress' })
    await user.selectOptions(screen.getByLabelText('Filter jobs'), 'failed')
    await waitFor(() => expect(selectedRefreshes).toBe(1))
    expect(screen.getByText('No jobs match this status.')).toBeInTheDocument()

    const pollRegistrations = setInterval.mock.calls.filter(([, timeout]) => timeout === 2_500)
    const scheduledPoll = pollRegistrations.at(-1)?.[0] as (() => void) | undefined
    if (typeof scheduledPoll !== 'function') {
      throw new Error('Active-job polling fixture was not registered.')
    }
    scheduledPoll()

    expect(
      await screen.findByRole('button', { name: `Open generation ${failed.id}` }),
    ).toBeInTheDocument()
    expect(failedListRequests).toBe(3)
    expect((await screen.findAllByText('Failed')).length).toBeGreaterThan(0)
  })
})
