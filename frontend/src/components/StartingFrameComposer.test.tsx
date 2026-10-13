import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { videoApi } from '../api/client'
import type {
  FilmShot,
  ImageGenerationJob,
  ImageGenerationProvider,
  ShotBindingRevision,
  StartingFrameComposition,
  StartingFrameDraft,
} from '../api/contracts'
import { StartingFrameComposer } from './StartingFrameComposer'

const now = '2026-10-13T00:00:00Z'
const shot: FilmShot = {
  id: 'shot_one',
  scene_id: 'scene_one',
  version: 2,
  content_fingerprint: 'a'.repeat(64),
  created_at: now,
  updated_at: now,
  draft: {
    scene_id: 'scene_one',
    position: 0,
    target_duration_ms: 5000,
    description: 'Arjun approaches the house',
    reference_workflow: 'reference_generation',
    character_reference_asset_ids: ['asset_arjun'],
    dialogue_workflow: 'tts',
    storyboard_asset_id: 'asset_storyboard',
    source_footage_asset_id: null,
    recorded_dialogue_asset_id: null,
  },
}
const binding: ShotBindingRevision = {
  id: 'binding_one',
  project_id: 'project_one',
  shot_id: shot.id,
  shot_version: shot.version,
  revision: 1,
  film_bible_snapshot_id: 'bible_one',
  bindings: [
    {
      entity_id: 'library_arjun',
      library_version_id: 'version_arjun',
      library_version_number: 1,
      version_kind: 'identity',
      version_fingerprint: 'b'.repeat(64),
      role: 'character_identity',
    },
    {
      entity_id: 'library_house',
      library_version_id: 'version_house',
      library_version_number: 1,
      version_kind: 'location_view',
      version_fingerprint: '9'.repeat(64),
      role: 'location_view',
    },
  ],
  fingerprint: 'c'.repeat(64),
  created_at: now,
}
const draft: StartingFrameDraft = {
  shot_version: shot.version,
  shot_binding_revision_id: binding.id,
  mode: 'layered',
  canvas_width: 832,
  canvas_height: 480,
  background_rgba: '#00000000',
  output_rights: 'owned',
  framing_notes: 'Medium shot',
  pose_notes: 'Arjun faces camera',
  action_notes: 'Arjun stops',
  lighting_notes: 'Day exterior',
  visible_speaker_entity_id: 'library_arjun',
  layers: [
    {
      role: 'background',
      source: {
        asset_id: 'asset_house',
        library_entity_id: 'library_house',
        library_version_id: 'version_house',
      },
      transform: {
        x: 0,
        y: 0,
        width: 832,
        height: 480,
        rotation_millidegrees: 0,
        opacity_basis_points: 10000,
        fit: 'contain',
        crop: null,
      },
      mask: null,
    },
  ],
}
const composition: StartingFrameComposition = {
  ...draft,
  id: 'composition_one',
  project_id: 'project_one',
  shot_id: shot.id,
  revision: 1,
  status: 'draft',
  layers: [
    {
      role: 'background',
      source: {
        asset_id: 'asset_house',
        library_entity_id: 'library_house',
        library_version_id: 'version_house',
        asset_version: 1,
        asset_sha256: 'd'.repeat(64),
        scope: 'library',
        library_version_fingerprint: '9'.repeat(64),
      },
      transform: {
        x: 0,
        y: 0,
        width: 832,
        height: 480,
        rotation_millidegrees: 0,
        opacity_basis_points: 10000,
        fit: 'contain',
        crop: null,
      },
      mask: null,
    },
  ],
  fingerprint: 'e'.repeat(64),
  created_at: now,
  rendered_asset_id: null,
  rendered_asset_version: null,
  rendered_sha256: null,
  renderer_revision: null,
  rendered_at: null,
  approved_at: null,
  preview_url: null,
}
const imageProvider: ImageGenerationProvider = {
  backend: 'wan22-ti2v',
  backend_revision: 'wan2.2@code;task=ti2v-5B;model@model',
  model: 'wan22-ti2v-5b',
  display_name: 'Wan2.2 TI2V 5B',
  task: 'ti2v-5B',
  area_width: 1280,
  area_height: 704,
  frame_count: 81,
  enabled: true,
  runtime_state: 'qualified',
  unavailable_reason: null,
}

afterEach(() => vi.restoreAllMocks())

describe('StartingFrameComposer', () => {
  it('creates, server-renders, previews, and separately approves one immutable revision', async () => {
    vi.spyOn(videoApi, 'getImageGenerationProvider').mockResolvedValue(imageProvider)
    vi.spyOn(videoApi, 'listProjectAssets').mockResolvedValue({ items: [] })
    vi.spyOn(videoApi, 'listShotBindingRevisions').mockResolvedValue({ items: [binding] })
    vi.spyOn(videoApi, 'listStartingFrameCompositions').mockResolvedValue({ items: [] })
    const create = vi
      .spyOn(videoApi, 'createStartingFrameComposition')
      .mockResolvedValue(composition)
    const rendered = {
      ...composition,
      status: 'rendered' as const,
      rendered_asset_id: 'asset_rendered',
      rendered_asset_version: 1,
      rendered_sha256: 'f'.repeat(64),
      renderer_revision: 'pillow-11.3.0/composition-v1',
      rendered_at: now,
      preview_url:
        '/api/v2/projects/project_one/film/shots/shot_one/starting-frames/composition_one/preview',
    }
    const renderPreview = vi
      .spyOn(videoApi, 'renderStartingFrameComposition')
      .mockResolvedValue(rendered)
    const approve = vi
      .spyOn(videoApi, 'approveStartingFrameComposition')
      .mockResolvedValue({ ...rendered, status: 'approved', approved_at: now })
    const user = userEvent.setup()
    render(<StartingFrameComposer projectId="project_one" shots={[shot]} />)

    await user.selectOptions(screen.getByLabelText('Shot'), shot.id)
    await waitFor(() =>
      expect(screen.getByLabelText('Exact shot-binding revision')).toHaveValue(binding.id),
    )
    fireEvent.change(screen.getByLabelText(/Composition JSON/), {
      target: { value: JSON.stringify(draft) },
    })
    await user.click(screen.getByRole('button', { name: 'Save composition revision' }))

    await waitFor(() => expect(create).toHaveBeenCalledWith('project_one', shot.id, draft))
    await user.click(screen.getByRole('button', { name: 'Render server preview' }))
    await waitFor(() =>
      expect(renderPreview).toHaveBeenCalledWith('project_one', shot.id, composition.id),
    )
    expect(
      await screen.findByRole('img', { name: /server-rendered starting frame/i }),
    ).toHaveAttribute('src', expect.stringContaining(`sha=${rendered.rendered_sha256}`))
    await user.click(screen.getByRole('button', { name: 'Approve exact preview' }))
    await waitFor(() =>
      expect(approve).toHaveBeenCalledWith('project_one', shot.id, composition.id),
    )
    expect(screen.getByText(/does not claim automatic harmonization/i)).toBeInTheDocument()
  })

  it('queues only an approved composition with string seed and stable idempotency', async () => {
    const approved = {
      ...composition,
      status: 'approved' as const,
      rendered_asset_id: 'asset_rendered',
      rendered_asset_version: 1,
      rendered_sha256: 'f'.repeat(64),
      renderer_revision: 'pillow-11.3.0/composition-v1',
      rendered_at: now,
      approved_at: now,
      preview_url:
        '/api/v2/projects/project_one/film/shots/shot_one/starting-frames/composition_one/preview',
    }
    const job: ImageGenerationJob = {
      id: 'job_i2v',
      status: 'queued',
      created_at: now,
      updated_at: now,
      started_at: null,
      completed_at: null,
      idempotency_key: `${approved.id}:${approved.fingerprint.slice(0, 16)}`,
      request: {
        prompt: 'Arjun turns toward camera',
        model: imageProvider.model,
        area_width: 1280,
        area_height: 704,
        frame_count: 81,
        seed: '-7',
      },
      conditioning: {
        project_id: 'project_one',
        shot_id: shot.id,
        shot_version: shot.version,
        composition_id: approved.id,
        composition_revision: approved.revision,
        composition_fingerprint: approved.fingerprint,
        source_asset_id: 'asset_rendered',
        source_asset_version: 1,
        source_asset_sha256: 'f'.repeat(64),
        source_width: 832,
        source_height: 480,
        manifest_fingerprint: '1'.repeat(64),
        reference_video: null,
      },
      backend: null,
      backend_revision: null,
      progress: null,
      conditioning_evidence: null,
      result: null,
      failure: null,
    }
    vi.spyOn(videoApi, 'getImageGenerationProvider').mockResolvedValue(imageProvider)
    vi.spyOn(videoApi, 'listProjectAssets').mockResolvedValue({ items: [] })
    vi.spyOn(videoApi, 'listShotBindingRevisions').mockResolvedValue({ items: [binding] })
    vi.spyOn(videoApi, 'listStartingFrameCompositions').mockResolvedValue({ items: [approved] })
    const submit = vi.spyOn(videoApi, 'submitImageGeneration').mockResolvedValue(job)
    const user = userEvent.setup()
    render(<StartingFrameComposer projectId="project_one" shots={[shot]} />)

    await user.selectOptions(screen.getByLabelText('Shot'), shot.id)
    await user.type(
      await screen.findByLabelText('Generation prompt revision 1'),
      job.request.prompt,
    )
    await user.type(screen.getByLabelText('Generation seed revision 1'), '-7')
    await user.click(screen.getByRole('button', { name: 'Queue image-conditioned shot' }))

    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith('project_one', shot.id, approved.id, {
        prompt: job.request.prompt,
        seed: '-7',
        idempotency_key: job.idempotency_key,
      }),
    )
    expect(screen.getByText('Status: queued')).toBeInTheDocument()
    expect(screen.getByText(/reliable emotional acting are not claimed/i)).toBeInTheDocument()
  })
})
