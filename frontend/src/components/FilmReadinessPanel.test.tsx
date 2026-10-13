import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { videoApi } from '../api/client'
import type { FilmReadiness } from '../api/contracts'
import { FilmReadinessPanel } from './FilmReadinessPanel'

const readiness: FilmReadiness = {
  workspace_fingerprint: 'a'.repeat(64),
  continuity_boundaries: [
    {
      position: 0,
      left_scene_id: 'scene_house',
      left_shot_id: 'shot_house',
      right_scene_id: 'scene_temple',
      right_shot_id: 'shot_temple',
      fingerprint: 'b'.repeat(64),
      cross_scene: true,
      changed_fields: ['location', 'lighting', 'wardrobe'],
    },
  ],
  structural_blockers: [],
  pending_approvals: [
    {
      stage: 'rough_cut',
      message: 'Approve the current rough film.',
      scene_id: null,
      shot_id: null,
    },
  ],
  ready_for_rough_cut: true,
  ready_for_final_footage: false,
  ready_for_dialogue_90_seconds: false,
  ready_for_sequence_180_seconds: false,
  ready_for_film_900_seconds: false,
  ready_for_final_sound: false,
  accepted: false,
  next_gate: 'rough_cut',
}

describe('FilmReadinessPanel', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows authoritative gates and the house-to-temple continuity boundary', async () => {
    const getReadiness = vi.spyOn(videoApi, 'getFilmReadiness').mockResolvedValue(readiness)

    render(<FilmReadinessPanel projectId="project_one" refreshToken="revision-one" />)

    expect(await screen.findByText('Next gate: rough cut')).toBeInTheDocument()
    expect(screen.getByText('shot_house → shot_temple')).toBeInTheDocument()
    expect(screen.getByText('Review changes: location, lighting, wardrobe')).toBeInTheDocument()
    expect(screen.getByText('Acceptance incomplete')).toBeInTheDocument()
    expect(getReadiness).toHaveBeenCalledWith('project_one', expect.any(AbortSignal))
  })

  it('reloads derived readiness when persisted revisions change', async () => {
    const getReadiness = vi.spyOn(videoApi, 'getFilmReadiness').mockResolvedValue(readiness)
    const { rerender } = render(
      <FilmReadinessPanel projectId="project_one" refreshToken="revision-one" />,
    )
    await screen.findByText('Next gate: rough cut')

    rerender(<FilmReadinessPanel projectId="project_one" refreshToken="revision-two" />)

    await waitFor(() => expect(getReadiness).toHaveBeenCalledTimes(2))
  })
})
