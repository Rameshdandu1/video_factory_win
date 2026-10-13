import { useEffect, useState } from 'react'

import { isApiClientError, videoApi } from '../api/client'
import type {
  FilmShot,
  ImageGenerationJob,
  ImageGenerationProvider,
  MediaAsset,
  ShotBindingRevision,
  StartingFrameComposition,
  StartingFrameDraft,
} from '../api/contracts'

interface StartingFrameComposerProps {
  projectId: string
  shots: FilmShot[]
}

function defaultDraft(shot: FilmShot | null, binding: ShotBindingRevision | null): string {
  return JSON.stringify(
    {
      shot_version: shot?.version ?? 1,
      shot_binding_revision_id: binding?.id ?? '',
      mode: 'layered',
      canvas_width: 832,
      canvas_height: 480,
      background_rgba: '#00000000',
      output_rights: 'owned',
      framing_notes: '',
      pose_notes: '',
      action_notes: '',
      lighting_notes: '',
      visible_speaker_entity_id: null,
      layers: [
        {
          role: 'background',
          source: {
            asset_id: 'replace-with-approved-library-image-id',
            library_entity_id: 'replace-with-pinned-location-entity-id',
            library_version_id: 'replace-with-pinned-location-version-id',
          },
          transform: {
            x: 0,
            y: 0,
            width: 832,
            height: 480,
            rotation_millidegrees: 0,
            opacity_basis_points: 10000,
            fit: 'cover',
            crop: null,
          },
          mask: null,
        },
      ],
    } satisfies StartingFrameDraft,
    null,
    2,
  )
}

export function StartingFrameComposer({ projectId, shots }: StartingFrameComposerProps) {
  const [shotId, setShotId] = useState('')
  const [bindings, setBindings] = useState<ShotBindingRevision[]>([])
  const [bindingId, setBindingId] = useState('')
  const [compositions, setCompositions] = useState<StartingFrameComposition[]>([])
  const [assets, setAssets] = useState<MediaAsset[]>([])
  const [draftJson, setDraftJson] = useState(defaultDraft(null, null))
  const [provider, setProvider] = useState<ImageGenerationProvider | null>(null)
  const [generationJobs, setGenerationJobs] = useState<Record<string, ImageGenerationJob>>({})
  const [generationPrompts, setGenerationPrompts] = useState<Record<string, string>>({})
  const [generationSeeds, setGenerationSeeds] = useState<Record<string, string>>({})
  const [idempotencyKeys, setIdempotencyKeys] = useState<Record<string, string>>({})
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void videoApi
      .listProjectAssets(projectId, controller.signal)
      .then((page) => {
        if (!controller.signal.aborted)
          setAssets(page.items.filter((asset) => asset.kind === 'image'))
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(isApiClientError(error) ? error.message : 'Unable to load project images.')
        }
      })
    return () => controller.abort()
  }, [projectId])

  useEffect(() => {
    const controller = new AbortController()
    void videoApi
      .getImageGenerationProvider(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setProvider(value)
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(
            isApiClientError(error) ? error.message : 'Unable to discover image generation.',
          )
        }
      })
    return () => controller.abort()
  }, [])

  async function chooseShot(nextShotId: string) {
    setShotId(nextShotId)
    setMessage(null)
    if (nextShotId === '') {
      setBindings([])
      setCompositions([])
      setBindingId('')
      return
    }
    setPending(true)
    try {
      const [bindingPage, compositionPage] = await Promise.all([
        videoApi.listShotBindingRevisions(projectId, nextShotId),
        videoApi.listStartingFrameCompositions(projectId, nextShotId),
      ])
      const binding = bindingPage.items[0] ?? null
      const shot = shots.find((item) => item.id === nextShotId) ?? null
      setBindings(bindingPage.items)
      setCompositions(compositionPage.items)
      setBindingId(binding?.id ?? '')
      setDraftJson(defaultDraft(shot, binding))
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to load starting frames.')
    } finally {
      setPending(false)
    }
  }

  function chooseBinding(nextBindingId: string) {
    setBindingId(nextBindingId)
    const shot = shots.find((item) => item.id === shotId) ?? null
    const binding = bindings.find((item) => item.id === nextBindingId) ?? null
    setDraftJson(defaultDraft(shot, binding))
  }

  async function createComposition() {
    if (shotId === '' || bindingId === '') return
    setPending(true)
    setMessage(null)
    try {
      const parsed = JSON.parse(draftJson) as StartingFrameDraft
      const shot = shots.find((item) => item.id === shotId)
      if (shot === undefined) throw new Error('Select a current shot.')
      const created = await videoApi.createStartingFrameComposition(projectId, shotId, {
        ...parsed,
        shot_version: shot.version,
        shot_binding_revision_id: bindingId,
      })
      setCompositions((current) => [created, ...current])
      setMessage('Composition draft saved. Render the server preview before approval.')
    } catch (error: unknown) {
      setMessage(
        isApiClientError(error)
          ? error.message
          : error instanceof Error
            ? error.message
            : 'Unable to create the composition.',
      )
    } finally {
      setPending(false)
    }
  }

  async function renderComposition(composition: StartingFrameComposition) {
    setPending(true)
    setMessage(null)
    try {
      const rendered = await videoApi.renderStartingFrameComposition(
        projectId,
        composition.shot_id,
        composition.id,
      )
      setCompositions((current) =>
        current.map((item) => (item.id === rendered.id ? rendered : item)),
      )
      setMessage('Authoritative server preview rendered. Review crop and letterboxing.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to render the composition.')
    } finally {
      setPending(false)
    }
  }

  async function approveComposition(composition: StartingFrameComposition) {
    setPending(true)
    setMessage(null)
    try {
      const approved = await videoApi.approveStartingFrameComposition(
        projectId,
        composition.shot_id,
        composition.id,
      )
      setCompositions((current) =>
        current.map((item) => (item.id === approved.id ? approved : item)),
      )
      setMessage('Starting frame approved with its exact output hash and source revisions.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to approve the composition.')
    } finally {
      setPending(false)
    }
  }

  async function generateFromComposition(composition: StartingFrameComposition) {
    const prompt = generationPrompts[composition.id]?.trim() ?? ''
    const seed = generationSeeds[composition.id]?.trim() ?? ''
    const idempotencyKey =
      idempotencyKeys[composition.id]?.trim() ??
      `${composition.id}:${composition.fingerprint.slice(0, 16)}`
    if (prompt === '') {
      setMessage('Add a generation prompt for the approved starting frame.')
      return
    }
    if (seed !== '' && !/^-?[0-9]+$/u.test(seed)) {
      setMessage('Seed must be a signed decimal integer.')
      return
    }
    setPending(true)
    setMessage(null)
    try {
      const job = await videoApi.submitImageGeneration(
        projectId,
        composition.shot_id,
        composition.id,
        { prompt, seed: seed === '' ? null : seed, idempotency_key: idempotencyKey },
      )
      setGenerationJobs((current) => ({ ...current, [composition.id]: job }))
      setIdempotencyKeys((current) => ({ ...current, [composition.id]: idempotencyKey }))
      setMessage('Image-conditioned shot queued with the approved source hash pinned.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to queue image generation.')
    } finally {
      setPending(false)
    }
  }

  async function refreshGeneration(composition: StartingFrameComposition) {
    const existing = generationJobs[composition.id]
    if (existing === undefined) return
    setPending(true)
    try {
      const job = await videoApi.getImageGeneration(projectId, composition.shot_id, existing.id)
      setGenerationJobs((current) => ({ ...current, [composition.id]: job }))
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to refresh generation status.')
    } finally {
      setPending(false)
    }
  }

  async function cancelGeneration(composition: StartingFrameComposition) {
    const existing = generationJobs[composition.id]
    if (existing === undefined) return
    setPending(true)
    try {
      const job = await videoApi.cancelImageGeneration(projectId, composition.shot_id, existing.id)
      setGenerationJobs((current) => ({ ...current, [composition.id]: job }))
      setMessage('Cancellation requested for this shot only.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to cancel generation.')
    } finally {
      setPending(false)
    }
  }

  function generationStatus(composition: StartingFrameComposition) {
    const job = generationJobs[composition.id]
    if (job === undefined) return null
    const result = job.result
    return (
      <div className="generation-status" aria-live="polite">
        <strong>Status: {job.status}</strong>
        <code>{job.conditioning.manifest_fingerprint.slice(0, 16)}</code>
        <div className="button-row">
          <button
            type="button"
            className="button button--secondary"
            disabled={pending}
            onClick={() => void refreshGeneration(composition)}
          >
            Refresh shot status
          </button>
          {['queued', 'running'].includes(job.status) ? (
            <button
              type="button"
              className="button button--secondary"
              disabled={pending}
              onClick={() => void cancelGeneration(composition)}
            >
              Cancel this shot
            </button>
          ) : null}
        </div>
        {result === null ? null : <a href={result.download_url}>Download generated shot</a>}
      </div>
    )
  }

  return (
    <section className="starting-frame-composer" aria-labelledby="starting-frame-title">
      <h3 id="starting-frame-title">Starting-frame composer</h3>
      <p>
        Layer approved sources or select one composed upload. Preview pixels come from the server
        renderer; manual layering does not claim automatic harmonization or photorealism.
      </p>
      {message === null ? null : <p role="status">{message}</p>}
      <div className="form-grid">
        <label className="field">
          <span>Shot</span>
          <select value={shotId} onChange={(event) => void chooseShot(event.target.value)}>
            <option value="">Select a shot</option>
            {shots.map((shot) => (
              <option key={shot.id} value={shot.id}>
                Shot {shot.draft.position + 1} · revision {shot.version}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Exact shot-binding revision</span>
          <select value={bindingId} onChange={(event) => chooseBinding(event.target.value)}>
            <option value="">Select a binding</option>
            {bindings.map((binding) => (
              <option key={binding.id} value={binding.id}>
                Revision {binding.revision} · {binding.bindings.length} pins
              </option>
            ))}
          </select>
        </label>
      </div>
      <details>
        <summary>Available project image IDs</summary>
        <ul className="asset-list">
          {assets.map((asset) => (
            <li key={asset.id}>
              <strong>{asset.original_filename}</strong>
              <code>{asset.id}</code>
              <span>{asset.sha256.slice(0, 16)}</span>
            </li>
          ))}
        </ul>
      </details>
      <label className="field">
        <span>Composition JSON · ordered back to front</span>
        <textarea
          rows={24}
          value={draftJson}
          onChange={(event) => setDraftJson(event.target.value)}
        />
      </label>
      <button
        type="button"
        className="button button--primary"
        disabled={pending || shotId === '' || bindingId === ''}
        onClick={() => void createComposition()}
      >
        Save composition revision
      </button>

      <h4>Saved composition revisions</h4>
      <div className="starting-frame-grid">
        {compositions.map((composition) => (
          <article key={composition.id} className="starting-frame-card">
            <strong>
              Revision {composition.revision} · {composition.status}
            </strong>
            <span>
              {composition.canvas_width} × {composition.canvas_height} · {composition.layers.length}{' '}
              layers
            </span>
            <code>{composition.fingerprint.slice(0, 16)}</code>
            {composition.preview_url === null ? null : (
              <img
                src={`${composition.preview_url}?sha=${composition.rendered_sha256 ?? ''}`}
                alt={`Server-rendered starting frame revision ${String(composition.revision)}`}
              />
            )}
            {composition.rendered_sha256 === null ? null : (
              <small>Output SHA-256: {composition.rendered_sha256}</small>
            )}
            {composition.status === 'draft' ? (
              <button
                type="button"
                className="button button--secondary"
                disabled={pending}
                onClick={() => void renderComposition(composition)}
              >
                Render server preview
              </button>
            ) : null}
            {composition.status === 'rendered' ? (
              <button
                type="button"
                className="button button--primary"
                disabled={pending}
                onClick={() => void approveComposition(composition)}
              >
                Approve exact preview
              </button>
            ) : null}
            {composition.status === 'approved' ? (
              <div className="starting-frame-generation">
                <strong>Generate this shot independently</strong>
                <small>
                  {provider?.enabled === true
                    ? `${provider.display_name} · ${String(provider.frame_count)} frames`
                    : (provider?.unavailable_reason ?? 'Checking qualified provider…')}
                </small>
                <label className="field">
                  <span>Generation prompt</span>
                  <textarea
                    aria-label={`Generation prompt revision ${String(composition.revision)}`}
                    rows={4}
                    value={generationPrompts[composition.id] ?? ''}
                    onChange={(event) =>
                      setGenerationPrompts((current) => ({
                        ...current,
                        [composition.id]: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="field">
                  <span>Seed · optional signed 64-bit decimal</span>
                  <input
                    aria-label={`Generation seed revision ${String(composition.revision)}`}
                    value={generationSeeds[composition.id] ?? ''}
                    onChange={(event) =>
                      setGenerationSeeds((current) => ({
                        ...current,
                        [composition.id]: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="field">
                  <span>Idempotency key</span>
                  <input
                    aria-label={`Idempotency key revision ${String(composition.revision)}`}
                    value={
                      idempotencyKeys[composition.id] ??
                      `${composition.id}:${composition.fingerprint.slice(0, 16)}`
                    }
                    onChange={(event) =>
                      setIdempotencyKeys((current) => ({
                        ...current,
                        [composition.id]: event.target.value,
                      }))
                    }
                  />
                </label>
                <button
                  type="button"
                  className="button button--primary"
                  disabled={pending || provider?.enabled !== true}
                  onClick={() => void generateFromComposition(composition)}
                >
                  Queue image-conditioned shot
                </button>
                {generationStatus(composition)}
              </div>
            ) : null}
          </article>
        ))}
      </div>
      <p className="film-warning">
        I2V is available only for approved starting-frame revisions and a qualified pinned runtime.
        Segmentation, relighting, harmonization, and reliable emotional acting are not claimed.
      </p>
    </section>
  )
}
