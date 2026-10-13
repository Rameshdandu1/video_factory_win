import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { videoApi } from '../api/client'
import type { LibraryEntity, LibraryVersion, MediaAsset } from '../api/contracts'
import { FilmLibraryView } from './FilmLibraryView'

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
const asset: MediaAsset = {
  id: 'asset_arjun_front',
  project_id: null,
  scope: 'library',
  version: 1,
  kind: 'image',
  state: 'ready',
  original_filename: 'arjun-front.png',
  media_type: 'image/png',
  size_bytes: 128,
  sha256: 'a'.repeat(64),
  rights: 'permissioned',
  created_at: now,
  metadata: null,
  inspector_revision: null,
  inspected_at: null,
}
const draftVersion: LibraryVersion = {
  id: 'version_arjun_1',
  entity_id: entity.id,
  version_number: 1,
  kind: 'identity',
  status: 'draft',
  label: 'Identity pack',
  notes: '',
  invariants: 'Hair and face',
  state_notes: 'Neutral',
  voice_profile_id: null,
  rights_statement: 'Permission recorded',
  assets: [
    {
      asset_id: asset.id,
      asset_version: asset.version,
      asset_sha256: asset.sha256,
      role: 'identity_appearance',
      view_label: 'front',
    },
  ],
  fingerprint: 'b'.repeat(64),
  created_at: now,
  approved_at: null,
}

afterEach(() => vi.restoreAllMocks())

function installLibrary(items: LibraryEntity[] = []) {
  vi.spyOn(videoApi, 'listLibraryEntities').mockResolvedValue({ items })
  vi.spyOn(videoApi, 'listLibraryAssets').mockResolvedValue({ items: [asset] })
  vi.spyOn(videoApi, 'listLibraryVersions').mockResolvedValue({ items: [] })
}

describe('FilmLibraryView', () => {
  it('creates a Unicode-named reusable character with explicit aliases', async () => {
    const user = userEvent.setup()
    installLibrary()
    const create = vi.spyOn(videoApi, 'createLibraryEntity').mockResolvedValue(entity)
    render(<FilmLibraryView />)

    await user.type(await screen.findByLabelText('Name'), 'Arjun')
    await user.type(screen.getByLabelText('Aliases (comma separated)'), 'అర్జున్, Arjun Rao')
    await user.click(screen.getByRole('button', { name: 'Create library item' }))

    expect(create).toHaveBeenCalledWith({
      kind: 'character',
      display_name: 'Arjun',
      aliases: ['అర్జున్', 'Arjun Rao'],
    })
    expect(await screen.findByText('Arjun')).toBeInTheDocument()
  })

  it('creates and approves an exact reference-role version', async () => {
    const user = userEvent.setup()
    installLibrary([entity])
    const createVersion = vi.spyOn(videoApi, 'createLibraryVersion').mockResolvedValue(draftVersion)
    const approveVersion = vi.spyOn(videoApi, 'approveLibraryVersion').mockResolvedValue({
      ...draftVersion,
      status: 'approved',
      approved_at: now,
    })
    render(<FilmLibraryView />)

    await user.click(await screen.findByRole('button', { name: /Arjun/ }))
    await user.type(screen.getByLabelText('Version label'), 'Identity pack')
    await user.type(
      screen.getByLabelText('Invariants (features that should remain stable)'),
      'Hair and face',
    )
    await user.click(screen.getByRole('checkbox', { name: /arjun-front\.png/ }))
    await user.type(screen.getByLabelText('View label (optional)'), 'front')
    await user.click(screen.getByRole('button', { name: 'Save immutable draft version' }))

    expect(createVersion).toHaveBeenCalledWith(
      entity.id,
      expect.objectContaining({
        kind: 'identity',
        assets: [
          expect.objectContaining({
            asset_id: asset.id,
            role: 'identity_appearance',
            view_label: 'front',
          }),
        ],
      }),
    )
    await user.click(await screen.findByRole('button', { name: 'Approve version' }))
    await waitFor(() => expect(approveVersion).toHaveBeenCalledWith(entity.id, draftVersion.id))
    expect(await screen.findByText(/Version approved/)).toBeInTheDocument()
  })
})
