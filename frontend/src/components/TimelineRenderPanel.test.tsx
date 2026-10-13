import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { videoApi } from '../api/client'
import type { TimelineRenderJob, TimelineRenderProvider } from '../api/contracts'
import { TimelineRenderPanel } from './TimelineRenderPanel'

const provider: TimelineRenderProvider = {
  backend: 'ffmpeg-timeline-render',
  backend_revision: 'ffmpeg-timeline-render-v1',
  display_name: 'Approved final timeline render',
  enabled: true,
  runtime_state: 'qualified',
  width: 1280,
  height: 720,
  fps_numerator: 24,
  fps_denominator: 1,
  duration_ms: 900_000,
  unavailable_reason: null,
}

const queued: TimelineRenderJob = {
  id: 'job_final',
  project_id: 'project_one',
  timeline_id: 'timeline_one',
  timeline_revision: 2,
  status: 'queued',
  created_at: '2026-10-13T00:00:00Z',
  updated_at: '2026-10-13T00:00:00Z',
  started_at: null,
  completed_at: null,
  idempotency_key: 'final-test',
  backend: null,
  backend_revision: null,
  timeline_fingerprint: 'a'.repeat(64),
  manifest_fingerprint: 'b'.repeat(64),
  visual_item_count: 12,
  audio_item_count: 4,
  caption_count: 8,
  duration_ms: 900_000,
  width: 1280,
  height: 720,
  fps_numerator: 24,
  fps_denominator: 1,
  progress: null,
  result: null,
  failure: null,
}

describe('TimelineRenderPanel', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows qualification and queues the exact approved timeline', async () => {
    vi.spyOn(videoApi, 'getTimelineRenderProvider').mockResolvedValue(provider)
    const submit = vi.spyOn(videoApi, 'submitTimelineRender').mockResolvedValue(queued)
    vi.spyOn(videoApi, 'getTimelineRender').mockResolvedValue(queued)

    render(<TimelineRenderPanel projectId="project_one" timelineId="timeline_one" />)

    expect(await screen.findByText('Qualified')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Final-render idempotency key'), {
      target: { value: 'final-test' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Render approved timeline' }))

    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith('project_one', 'timeline_one', 'final-test'),
    )
    expect(await screen.findByText('queued')).toBeInTheDocument()
    expect(screen.getByText(/matching duration alone/u)).toBeInTheDocument()
  })

  it('keeps rendering disabled without qualification', async () => {
    vi.spyOn(videoApi, 'getTimelineRenderProvider').mockResolvedValue({
      ...provider,
      enabled: false,
      runtime_state: 'not_configured',
      unavailable_reason: 'Qualification required.',
    })

    render(<TimelineRenderPanel projectId="project_one" timelineId="timeline_one" />)

    expect(await screen.findByText('Qualification required.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Render approved timeline' })).toBeDisabled()
  })
})
