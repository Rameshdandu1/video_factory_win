import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { videoApi } from '../api/client'
import type {
  ControlledGenerationProvider,
  FilmShot,
  ImageGenerationJob,
  MediaAsset,
  ReferenceVideoGuidance as Guidance,
  ShotBindingRevision,
  StartingFrameComposition,
} from '../api/contracts'
import { ReferenceVideoGuidance } from './ReferenceVideoGuidance'

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
    target_duration_ms: 5_000,
    description: 'Performance reference',
    reference_workflow: 'reference_generation',
    character_reference_asset_ids: ['identity_one'],
    dialogue_workflow: 'tts',
    storyboard_asset_id: 'storyboard_one',
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
      entity_id: 'character_one',
      library_version_id: 'version_one',
      library_version_number: 1,
      version_kind: 'identity',
      version_fingerprint: 'b'.repeat(64),
      role: 'character_identity',
    },
  ],
  fingerprint: 'c'.repeat(64),
  created_at: now,
}
const asset: MediaAsset = {
  id: 'video_one',
  project_id: 'project_one',
  scope: 'project',
  version: 2,
  kind: 'video',
  state: 'inspected',
  original_filename: 'walk.mp4',
  media_type: 'video/mp4',
  size_bytes: 1000,
  sha256: 'd'.repeat(64),
  rights: 'permissioned',
  created_at: now,
  metadata: {
    format_name: 'mov,mp4',
    duration_ms: 12_000,
    width: 1280,
    height: 720,
    frame_rate_numerator: 24,
    frame_rate_denominator: 1,
    sample_rate: null,
    channels: null,
    sample_count: null,
  },
  inspector_revision: 'ffprobe:test',
  inspected_at: now,
}
const draftGuidance: Guidance = {
  id: 'guidance_one',
  project_id: 'project_one',
  shot_id: shot.id,
  shot_version: shot.version,
  shot_binding_revision_id: binding.id,
  revision: 1,
  purpose: 'motion_performance',
  source: {
    asset_id: asset.id,
    asset_version: asset.version,
    asset_sha256: asset.sha256,
    media_type: asset.media_type,
    scope: asset.scope,
    inspector_revision: asset.inspector_revision ?? '',
    duration_ms: asset.metadata?.duration_ms ?? 0,
    width: asset.metadata?.width ?? 0,
    height: asset.metadata?.height ?? 0,
    frame_rate_numerator: asset.metadata?.frame_rate_numerator ?? 0,
    frame_rate_denominator: asset.metadata?.frame_rate_denominator ?? 0,
    library_entity_id: null,
    library_version_id: null,
    library_version_fingerprint: null,
  },
  trim_start_ms: 1_000,
  trim_end_ms: 4_000,
  guidance_notes: '',
  status: 'draft',
  fingerprint: 'e'.repeat(64),
  created_at: now,
  approved_at: null,
  preview_url:
    '/api/v2/projects/project_one/film/shots/shot_one/reference-guidance/guidance_one/preview',
}
const approvedComposition: StartingFrameComposition = {
  id: 'composition_one',
  project_id: 'project_one',
  shot_id: shot.id,
  shot_version: shot.version,
  shot_binding_revision_id: binding.id,
  revision: 1,
  mode: 'composed_upload',
  status: 'approved',
  canvas_width: 832,
  canvas_height: 480,
  background_rgba: '#000000ff',
  output_rights: 'owned',
  framing_notes: 'Medium shot',
  pose_notes: 'Actor faces camera',
  action_notes: 'Actor speaks',
  lighting_notes: 'Day interior',
  visible_speaker_entity_id: 'character_one',
  layers: [
    {
      role: 'starting_frame',
      source: {
        asset_id: 'image_one',
        library_entity_id: null,
        library_version_id: null,
        asset_version: 1,
        asset_sha256: 'f'.repeat(64),
        scope: 'project',
        library_version_fingerprint: null,
      },
      transform: {
        x: 0,
        y: 0,
        width: 832,
        height: 480,
        rotation_millidegrees: 0,
        opacity_basis_points: 10_000,
        fit: 'contain',
        crop: null,
      },
      mask: null,
    },
  ],
  fingerprint: '1'.repeat(64),
  created_at: now,
  rendered_asset_id: 'rendered_one',
  rendered_asset_version: 1,
  rendered_sha256: '2'.repeat(64),
  renderer_revision: 'pillow-11.3.0/composition-v1',
  rendered_at: now,
  approved_at: now,
  preview_url: '/preview/composition_one',
}
const controlledProvider: ControlledGenerationProvider = {
  id: 'vace-performance-transfer',
  backend: 'vace-wan21',
  backend_revision: 'vace@code;task=animate_anything:salientbboxtrack;model@model',
  model: 'vace-wan21-1.3b-performance',
  display_name: 'VACE performance transfer',
  task: 'animate_anything:salientbboxtrack',
  operation: 'vace_performance_transfer',
  area_width: 832,
  area_height: 480,
  frame_count: 81,
  maximum_guidance_ms: 5_063,
  preserves_starting_frame_environment: true,
  enabled: true,
  runtime_state: 'qualified',
  unavailable_reason: null,
}

afterEach(() => vi.restoreAllMocks())

describe('ReferenceVideoGuidance', () => {
  it('creates, previews the exact trim, and separately approves a revision', async () => {
    vi.spyOn(videoApi, 'listProjectAssets').mockResolvedValue({ items: [asset] })
    vi.spyOn(videoApi, 'listLibraryAssets').mockResolvedValue({ items: [] })
    vi.spyOn(videoApi, 'listControlledGenerationProviders').mockResolvedValue({ items: [] })
    vi.spyOn(videoApi, 'listShotBindingRevisions').mockResolvedValue({ items: [binding] })
    vi.spyOn(videoApi, 'listReferenceVideoGuidance').mockResolvedValue({ items: [] })
    vi.spyOn(videoApi, 'listStartingFrameCompositions').mockResolvedValue({ items: [] })
    const create = vi
      .spyOn(videoApi, 'createReferenceVideoGuidance')
      .mockResolvedValue(draftGuidance)
    const approve = vi
      .spyOn(videoApi, 'approveReferenceVideoGuidance')
      .mockResolvedValue({ ...draftGuidance, status: 'approved', approved_at: now })
    const user = userEvent.setup()
    render(<ReferenceVideoGuidance projectId="project_one" shots={[shot]} />)

    await user.selectOptions(screen.getByLabelText('Shot revision'), shot.id)
    await waitFor(() => expect(screen.getByLabelText('Exact shot binding')).toHaveValue(binding.id))
    await user.selectOptions(screen.getByLabelText('Inspected video source'), asset.id)
    await user.clear(screen.getByLabelText('Trim start (ms)'))
    await user.type(screen.getByLabelText('Trim start (ms)'), '1000')
    await user.clear(screen.getByLabelText('Trim end, exclusive (ms)'))
    await user.type(screen.getByLabelText('Trim end, exclusive (ms)'), '4000')
    await user.click(screen.getByRole('button', { name: 'Save immutable guidance revision' }))

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith('project_one', shot.id, {
        shot_version: shot.version,
        shot_binding_revision_id: binding.id,
        purpose: 'motion_performance',
        source: {
          asset_id: asset.id,
          library_entity_id: null,
          library_version_id: null,
        },
        trim_start_ms: 1_000,
        trim_end_ms: 4_000,
        guidance_notes: '',
      }),
    )
    const preview = screen
      .getByText('Reference-video preview is unavailable in this browser.')
      .closest('video')
    expect(preview).toHaveAttribute('src', expect.stringContaining('#t=1,4'))
    await user.click(screen.getByRole('button', { name: 'Approve reviewed range' }))
    await waitFor(() =>
      expect(approve).toHaveBeenCalledWith('project_one', shot.id, draftGuidance.id),
    )
    expect(screen.getByText(/does not prove identity preservation/i)).toBeInTheDocument()
  })

  it('opts into a qualified provider with exact approved frame and guidance revisions', async () => {
    const approvedGuidance: Guidance = {
      ...draftGuidance,
      status: 'approved',
      approved_at: now,
    }
    const job: ImageGenerationJob = {
      id: 'controlled_job_one',
      status: 'queued',
      created_at: now,
      updated_at: now,
      started_at: null,
      completed_at: null,
      idempotency_key: 'shot-one-vace-1',
      request: {
        prompt: 'Natural Telugu dialogue performance',
        model: controlledProvider.model,
        area_width: controlledProvider.area_width,
        area_height: controlledProvider.area_height,
        frame_count: controlledProvider.frame_count,
        seed: '17',
      },
      conditioning: {
        project_id: 'project_one',
        shot_id: shot.id,
        shot_version: shot.version,
        composition_id: approvedComposition.id,
        composition_revision: approvedComposition.revision,
        composition_fingerprint: approvedComposition.fingerprint,
        source_asset_id: approvedComposition.rendered_asset_id ?? '',
        source_asset_version: approvedComposition.rendered_asset_version ?? 1,
        source_asset_sha256: approvedComposition.rendered_sha256 ?? '',
        source_width: approvedComposition.canvas_width,
        source_height: approvedComposition.canvas_height,
        manifest_fingerprint: '3'.repeat(64),
        reference_video: {
          guidance_id: approvedGuidance.id,
          guidance_revision: approvedGuidance.revision,
          guidance_fingerprint: approvedGuidance.fingerprint,
          purpose: approvedGuidance.purpose,
          source_asset_id: asset.id,
          source_asset_version: asset.version,
          source_asset_sha256: asset.sha256,
          trim_start_ms: approvedGuidance.trim_start_ms,
          trim_end_ms: approvedGuidance.trim_end_ms,
          operation: controlledProvider.operation,
          preserve_environment: true,
          constraint_plan_fingerprint: '4'.repeat(64),
        },
      },
      backend: null,
      backend_revision: null,
      progress: null,
      conditioning_evidence: null,
      result: null,
      failure: null,
    }
    vi.spyOn(videoApi, 'listProjectAssets').mockResolvedValue({ items: [asset] })
    vi.spyOn(videoApi, 'listLibraryAssets').mockResolvedValue({ items: [] })
    vi.spyOn(videoApi, 'listControlledGenerationProviders').mockResolvedValue({
      items: [controlledProvider],
    })
    vi.spyOn(videoApi, 'listShotBindingRevisions').mockResolvedValue({ items: [binding] })
    vi.spyOn(videoApi, 'listReferenceVideoGuidance').mockResolvedValue({
      items: [approvedGuidance],
    })
    vi.spyOn(videoApi, 'listStartingFrameCompositions').mockResolvedValue({
      items: [approvedComposition],
    })
    const submit = vi.spyOn(videoApi, 'submitControlledGeneration').mockResolvedValue(job)
    const user = userEvent.setup()
    render(<ReferenceVideoGuidance projectId="project_one" shots={[shot]} />)

    await user.selectOptions(screen.getByLabelText('Shot revision'), shot.id)
    await waitFor(() =>
      expect(screen.getByLabelText('Qualified provider and operation')).toHaveValue(
        controlledProvider.id,
      ),
    )
    await user.type(screen.getByLabelText('Shot prompt'), job.request.prompt)
    await user.type(screen.getByLabelText('Idempotency key'), job.idempotency_key)
    await user.type(screen.getByLabelText('Seed (optional)'), '17')
    await user.click(screen.getByRole('button', { name: 'Generate this approved shot' }))

    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith(
        'project_one',
        shot.id,
        approvedComposition.id,
        approvedGuidance.id,
        {
          provider_id: controlledProvider.id,
          preserve_environment: true,
          prompt: job.request.prompt,
          idempotency_key: job.idempotency_key,
          seed: '17',
        },
      ),
    )
    expect(screen.getByText(/controlled_job_one · queued/i)).toBeInTheDocument()
  })
})
