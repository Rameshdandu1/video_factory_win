import { describe, expect, it, vi } from 'vitest'

import { ApiClient } from './client'
import type { Project, ProjectDraft } from './contracts'

const draft: ProjectDraft = {
  title: 'Customer and mechanic',
  language: 'te',
  mode: 'short',
  target_duration_ms: 30_000,
  aspect_ratio: '9:16',
  export_settings: { width: 720, height: 1280, fps_numerator: 30, fps_denominator: 1 },
  providers: { video: 'wan21', speech: 'uploaded', lip_sync: null, caption_alignment: null },
  budget_policy: {
    max_compute_seconds: null,
    max_cost_micros: null,
    automatic_expensive_retries: 0,
  },
  preset: 'standard',
  titles_and_credits_within_target: true,
}

const project: Project = {
  ...draft,
  id: 'project_one',
  version: 1,
  state: 'draft',
  approved_timeline_revision_id: null,
  created_at: '2026-10-12T00:00:00Z',
  updated_at: '2026-10-12T00:00:00Z',
}

describe('project API v2', () => {
  it('submits the typed project draft without changing v1', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(JSON.stringify(project), {
        status: 201,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const client = new ApiClient({ fetch })

    await expect(client.createProject(draft)).resolves.toEqual(project)
    expect(fetch).toHaveBeenCalledWith(
      '/api/v2/projects',
      expect.objectContaining({ method: 'POST', body: JSON.stringify(draft) }),
    )
  })

  it('streams an asset body and validates the safe metadata response', async () => {
    const asset = {
      id: 'asset_one',
      project_id: project.id,
      scope: 'project' as const,
      version: 1 as const,
      kind: 'audio' as const,
      state: 'ready' as const,
      original_filename: 'voice.wav',
      media_type: 'audio/wav',
      size_bytes: 12,
      sha256: 'a'.repeat(64),
      rights: 'permissioned' as const,
      created_at: '2026-10-12T00:00:00Z',
      metadata: null,
      inspector_revision: null,
      inspected_at: null,
    }
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(JSON.stringify(asset), {
        status: 201,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const client = new ApiClient({ fetch })
    const file = new File(['RIFFxxxxWAVE'], 'voice.wav', { type: 'audio/wav' })

    await expect(
      client.uploadProjectAsset(project.id, file, 'audio', 'permissioned'),
    ).resolves.toEqual(asset)
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining(`/api/v2/projects/${project.id}/assets?`),
      expect.objectContaining({ method: 'POST', body: file }),
    )
  })

  it('creates an immutable timeline revision with captions', async () => {
    const draft = {
      duration_ms: 30_000,
      items: [
        {
          kind: 'title_card' as const,
          start_ms: 0,
          duration_ms: 30_000,
          layer: 0,
          asset_id: null,
          text: 'Customer and mechanic',
        },
      ],
      captions: [{ start_ms: 0, end_ms: 2_000, text: 'Hello' }],
    }
    const timeline = {
      ...draft,
      id: 'timeline_one',
      project_id: project.id,
      revision: 1,
      fingerprint: 'b'.repeat(64),
      created_at: '2026-10-12T00:00:00Z',
      approved_at: null,
    }
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(JSON.stringify(timeline), {
        status: 201,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const client = new ApiClient({ fetch })

    await expect(client.createTimelineRevision(project.id, draft)).resolves.toEqual(timeline)
    expect(fetch).toHaveBeenCalledWith(
      `/api/v2/projects/${project.id}/timelines`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(draft) }),
    )
  })

  it('rejects a malformed project success response', async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(
        new Response(JSON.stringify({ items: [{ ...project, version: 0 }] }), { status: 200 }),
      )
    const client = new ApiClient({ fetch })

    await expect(client.listProjects()).rejects.toMatchObject({ kind: 'invalid_response' })
  })

  it('loads the derived film-readiness contract without inventing browser state', async () => {
    const readiness = {
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
          changed_fields: ['location'],
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
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(JSON.stringify(readiness), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const client = new ApiClient({ fetch })

    await expect(client.getFilmReadiness(project.id)).resolves.toEqual(readiness)
    expect(fetch).toHaveBeenCalledWith(
      `/api/v2/projects/${project.id}/film/readiness`,
      expect.objectContaining({ method: 'GET' }),
    )
  })
})
