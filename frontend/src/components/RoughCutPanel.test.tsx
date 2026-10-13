import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { videoApi } from '../api/client'
import type { RoughCutJob, RoughCutProvider } from '../api/contracts'
import { RoughCutPanel } from './RoughCutPanel'

const provider: RoughCutProvider = {
  backend: 'ffmpeg-rough-cut',
  backend_revision: 'ffmpeg-rough-cut-v1',
  display_name: 'Approved storyboard rough cut',
  enabled: true,
  runtime_state: 'qualified',
  width: 1280,
  height: 720,
  fps_numerator: 24,
  fps_denominator: 1,
  unavailable_reason: null,
}

const queued: RoughCutJob = {
  id: 'job_rough',
  project_id: 'project_one',
  status: 'queued',
  created_at: '2026-10-13T00:00:00Z',
  updated_at: '2026-10-13T00:00:00Z',
  started_at: null,
  completed_at: null,
  idempotency_key: 'rough-cut-test',
  backend: null,
  backend_revision: null,
  workspace_fingerprint: 'a'.repeat(64),
  manifest_fingerprint: 'b'.repeat(64),
  shot_count: 12,
  duration_ms: 900_000,
  width: 1280,
  height: 720,
  fps_numerator: 24,
  fps_denominator: 1,
  progress: null,
  result: null,
  failure: null,
}

describe('RoughCutPanel', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows qualification honestly and submits one idempotent render', async () => {
    vi.spyOn(videoApi, 'getRoughCutProvider').mockResolvedValue(provider)
    const submit = vi.spyOn(videoApi, 'submitRoughCut').mockResolvedValue(queued)
    vi.spyOn(videoApi, 'getRoughCut').mockResolvedValue(queued)

    render(<RoughCutPanel projectId="project_one" />)

    expect(await screen.findByText('Qualified')).toBeInTheDocument()
    const key = screen.getByLabelText('Idempotency key')
    fireEvent.change(key, { target: { value: 'rough-cut-test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Render approved rough cut' }))

    await waitFor(() => expect(submit).toHaveBeenCalledWith('project_one', 'rough-cut-test'))
    expect(await screen.findByText('queued')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel render' })).toBeEnabled()
  })

  it('keeps submission disabled when the runtime is unqualified', async () => {
    vi.spyOn(videoApi, 'getRoughCutProvider').mockResolvedValue({
      ...provider,
      enabled: false,
      runtime_state: 'not_configured',
      unavailable_reason: 'Qualification required.',
    })

    render(<RoughCutPanel projectId="project_one" />)

    expect(await screen.findByText('Qualification required.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Render approved rough cut' })).toBeDisabled()
  })
})
