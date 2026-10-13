import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { videoApi } from '../api/client'
import type { Project } from '../api/contracts'
import { ProjectsView } from './ProjectsView'

const project: Project = {
  id: 'project_one',
  version: 1,
  state: 'draft',
  title: 'Customer and mechanic',
  language: 'te',
  mode: 'short',
  target_duration_ms: 30_000,
  aspect_ratio: '16:9',
  export_settings: { width: 1280, height: 720, fps_numerator: 30, fps_denominator: 1 },
  providers: { video: 'wan21', speech: 'uploaded', lip_sync: null, caption_alignment: null },
  budget_policy: {
    max_compute_seconds: null,
    max_cost_micros: null,
    automatic_expensive_retries: 0,
  },
  preset: 'standard',
  titles_and_credits_within_target: true,
  approved_timeline_revision_id: null,
  created_at: '2026-10-12T00:00:00Z',
  updated_at: '2026-10-12T00:00:00Z',
}

afterEach(() => vi.restoreAllMocks())

describe('ProjectsView', () => {
  it('creates a server-authoritative project with the selected workflow settings', async () => {
    vi.spyOn(videoApi, 'listProjects').mockResolvedValue({ items: [] })
    const create = vi.spyOn(videoApi, 'createProject').mockResolvedValue(project)
    const user = userEvent.setup()
    render(<ProjectsView />)

    await user.type(screen.getByLabelText('Project title'), 'Customer and mechanic')
    await user.selectOptions(screen.getByLabelText('Language'), 'te')
    await user.click(screen.getByRole('button', { name: 'Create project' }))

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    expect(create.mock.calls[0]?.[0]).toMatchObject({
      title: 'Customer and mechanic',
      language: 'te',
      target_duration_ms: 30_000,
    })
    expect(await screen.findByText('Customer and mechanic')).toBeInTheDocument()
    expect(screen.getByText('Self-hosted; infrastructure costs apply.')).toBeInTheDocument()
  })

  it('creates the locked 900-second Telugu film preset with configurable credits timing', async () => {
    vi.spyOn(videoApi, 'listProjects').mockResolvedValue({ items: [] })
    const create = vi.spyOn(videoApi, 'createProject').mockResolvedValue({
      ...project,
      mode: 'long',
      target_duration_ms: 900_000,
      preset: 'telugu_short_film_900',
      titles_and_credits_within_target: false,
      export_settings: { width: 1280, height: 720, fps_numerator: 24, fps_denominator: 1 },
    })
    const user = userEvent.setup()
    render(<ProjectsView />)

    await user.type(screen.getByLabelText('Project title'), 'తెలుగు కథ')
    await user.selectOptions(screen.getByLabelText('Preset'), 'telugu_short_film_900')
    await user.click(screen.getByLabelText('Count titles and credits within the 900-second target'))
    await user.click(screen.getByRole('button', { name: 'Create project' }))

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    expect(create.mock.calls[0]?.[0]).toMatchObject({
      language: 'te',
      mode: 'long',
      target_duration_ms: 900_000,
      preset: 'telugu_short_film_900',
      titles_and_credits_within_target: false,
    })
  })
})
