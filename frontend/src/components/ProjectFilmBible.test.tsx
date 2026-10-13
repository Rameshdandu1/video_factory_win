import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { videoApi } from '../api/client'
import type { FilmBibleSnapshot, LibraryEntity, LibraryVersion } from '../api/contracts'
import { ProjectFilmBible } from './ProjectFilmBible'

const now = '2026-10-13T00:00:00Z'
const entity: LibraryEntity = {
  id: 'library_arjun',
  kind: 'character',
  metadata_version: 1,
  display_name: 'Arjun',
  aliases: ['అర్జున్'],
  created_at: now,
  updated_at: now,
}
const version: LibraryVersion = {
  id: 'version_arjun_1',
  entity_id: entity.id,
  version_number: 1,
  kind: 'identity',
  status: 'approved',
  label: 'Approved identity',
  notes: '',
  invariants: 'Face and hair',
  state_notes: '',
  voice_profile_id: null,
  rights_statement: 'Permission recorded',
  assets: [
    {
      asset_id: 'asset_arjun',
      asset_version: 1,
      asset_sha256: 'a'.repeat(64),
      role: 'identity_appearance',
      view_label: 'front',
    },
  ],
  fingerprint: 'b'.repeat(64),
  created_at: now,
  approved_at: now,
}
const draftSnapshot: FilmBibleSnapshot = {
  id: 'bible_one',
  project_id: 'project_one',
  revision: 1,
  status: 'draft',
  pins: [
    {
      entity_id: entity.id,
      library_version_id: version.id,
      library_version_number: 1,
      version_kind: 'identity',
      version_fingerprint: version.fingerprint,
      role: 'character_identity',
    },
  ],
  fingerprint: 'c'.repeat(64),
  created_at: now,
  approved_at: null,
}

afterEach(() => vi.restoreAllMocks())

describe('ProjectFilmBible', () => {
  it('saves and approves exact project pins without claiming visual identity', async () => {
    vi.spyOn(videoApi, 'listLibraryEntities').mockResolvedValue({ items: [entity] })
    vi.spyOn(videoApi, 'listLibraryVersions').mockResolvedValue({ items: [version] })
    vi.spyOn(videoApi, 'listFilmBibleSnapshots').mockResolvedValue({ items: [] })
    const create = vi.spyOn(videoApi, 'createFilmBibleSnapshot').mockResolvedValue(draftSnapshot)
    const approve = vi.spyOn(videoApi, 'approveFilmBibleSnapshot').mockResolvedValue({
      ...draftSnapshot,
      status: 'approved',
      approved_at: now,
    })
    const user = userEvent.setup()
    render(<ProjectFilmBible projectId="project_one" shots={[]} />)

    await user.selectOptions(await screen.findByLabelText('Library entity'), entity.id)
    await user.selectOptions(screen.getByLabelText('Approved version'), version.id)
    await user.click(screen.getByRole('button', { name: 'Add or replace pin' }))
    await user.click(screen.getByRole('button', { name: 'Save Film Bible revision' }))

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith('project_one', [
        {
          entity_id: entity.id,
          version_id: version.id,
          role: 'character_identity',
        },
      ]),
    )
    await user.click(await screen.findByRole('button', { name: 'Approve snapshot' }))
    await waitFor(() => expect(approve).toHaveBeenCalledWith('project_one', draftSnapshot.id))
    expect(screen.getByText(/not a visual-consistency guarantee/i)).toBeInTheDocument()
  })

  it('shows ambiguous mention results instead of silently choosing a character', async () => {
    const approved = { ...draftSnapshot, status: 'approved' as const, approved_at: now }
    vi.spyOn(videoApi, 'listLibraryEntities').mockResolvedValue({ items: [entity] })
    vi.spyOn(videoApi, 'listLibraryVersions').mockResolvedValue({ items: [version] })
    vi.spyOn(videoApi, 'listFilmBibleSnapshots').mockResolvedValue({ items: [approved] })
    vi.spyOn(videoApi, 'resolveFilmBibleName').mockResolvedValue({
      mention: '@అర్జున్',
      status: 'ambiguous',
      candidates: [
        {
          entity_id: entity.id,
          display_name: 'Arjun',
          entity_kind: 'character',
          pins: approved.pins,
        },
        {
          entity_id: 'library_other',
          display_name: 'Arjun Two',
          entity_kind: 'character',
          pins: [],
        },
      ],
    })
    const user = userEvent.setup()
    render(<ProjectFilmBible projectId="project_one" shots={[]} />)

    const input = await screen.findByLabelText('Exact name or alias')
    await user.clear(input)
    await user.type(input, '@అర్జున్')
    await user.click(screen.getByRole('button', { name: 'Resolve mention' }))

    expect(await screen.findByText(/ambiguous: Arjun, Arjun Two/)).toBeInTheDocument()
  })
})
