import { useEffect, useMemo, useState } from 'react'

import { isApiClientError, videoApi } from '../api/client'
import type {
  ControlledGenerationProvider,
  FilmShot,
  ImageGenerationJob,
  MediaAsset,
  ReferenceVideoGuidance as Guidance,
  ReferenceVideoPurpose,
  ShotBindingRevision,
  StartingFrameComposition,
} from '../api/contracts'

interface ReferenceVideoGuidanceProps {
  projectId: string
  shots: FilmShot[]
}

const purposes: ReferenceVideoPurpose[] = ['motion_performance', 'shot_guidance', 'review_only']

export function ReferenceVideoGuidance({ projectId, shots }: ReferenceVideoGuidanceProps) {
  const [shotId, setShotId] = useState('')
  const [projectAssets, setProjectAssets] = useState<MediaAsset[]>([])
  const [libraryAssets, setLibraryAssets] = useState<MediaAsset[]>([])
  const [bindings, setBindings] = useState<ShotBindingRevision[]>([])
  const [guidance, setGuidance] = useState<Guidance[]>([])
  const [compositions, setCompositions] = useState<StartingFrameComposition[]>([])
  const [providers, setProviders] = useState<ControlledGenerationProvider[]>([])
  const [bindingId, setBindingId] = useState('')
  const [assetId, setAssetId] = useState('')
  const [purpose, setPurpose] = useState<ReferenceVideoPurpose>('motion_performance')
  const [trimStart, setTrimStart] = useState(0)
  const [trimEnd, setTrimEnd] = useState(3_000)
  const [libraryEntityId, setLibraryEntityId] = useState('')
  const [libraryVersionId, setLibraryVersionId] = useState('')
  const [notes, setNotes] = useState('')
  const [compositionId, setCompositionId] = useState('')
  const [providerId, setProviderId] = useState('')
  const [preserveEnvironment, setPreserveEnvironment] = useState(true)
  const [generationPrompt, setGenerationPrompt] = useState('')
  const [idempotencyKey, setIdempotencyKey] = useState('')
  const [seed, setSeed] = useState('')
  const [generationJob, setGenerationJob] = useState<ImageGenerationJob | null>(null)
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const selectedShot = shots.find((shot) => shot.id === shotId) ?? null
  const sources = useMemo(
    () =>
      [...projectAssets, ...libraryAssets].filter(
        (asset) => asset.kind === 'video' && asset.state === 'inspected',
      ),
    [libraryAssets, projectAssets],
  )
  const selectedAsset = sources.find((asset) => asset.id === assetId) ?? null

  useEffect(() => {
    const controller = new AbortController()
    void Promise.all([
      videoApi.listProjectAssets(projectId, controller.signal),
      videoApi.listLibraryAssets(controller.signal),
      videoApi.listControlledGenerationProviders(controller.signal),
    ])
      .then(([projectPage, libraryPage, providerPage]) => {
        if (controller.signal.aborted) return
        setProjectAssets(projectPage.items)
        setLibraryAssets(libraryPage.items)
        setProviders(providerPage.items)
        const firstEnabled = providerPage.items.find((provider) => provider.enabled)
        setProviderId(firstEnabled?.id ?? providerPage.items[0]?.id ?? '')
        setPreserveEnvironment(firstEnabled?.preserves_starting_frame_environment ?? true)
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(isApiClientError(error) ? error.message : 'Unable to load video sources.')
        }
      })
    return () => controller.abort()
  }, [projectId])

  async function chooseShot(nextShotId: string) {
    setShotId(nextShotId)
    setBindingId('')
    setCompositionId('')
    setGuidance([])
    setCompositions([])
    setGenerationJob(null)
    if (nextShotId === '') return
    setPending(true)
    setMessage(null)
    try {
      const [bindingPage, guidancePage, compositionPage] = await Promise.all([
        videoApi.listShotBindingRevisions(projectId, nextShotId),
        videoApi.listReferenceVideoGuidance(projectId, nextShotId),
        videoApi.listStartingFrameCompositions(projectId, nextShotId),
      ])
      setBindings(bindingPage.items)
      setBindingId(bindingPage.items[0]?.id ?? '')
      setGuidance(guidancePage.items)
      setCompositions(compositionPage.items)
      setCompositionId(
        compositionPage.items.find((composition) => composition.status === 'approved')?.id ?? '',
      )
    } catch (error: unknown) {
      setMessage(
        isApiClientError(error) ? error.message : 'Unable to load reference-video guidance.',
      )
    } finally {
      setPending(false)
    }
  }

  async function saveGuidance() {
    if (selectedShot === null || selectedAsset === null || bindingId === '') return
    setPending(true)
    setMessage(null)
    try {
      const created = await videoApi.createReferenceVideoGuidance(projectId, selectedShot.id, {
        shot_version: selectedShot.version,
        shot_binding_revision_id: bindingId,
        purpose,
        source: {
          asset_id: selectedAsset.id,
          library_entity_id:
            selectedAsset.scope === 'library' ? libraryEntityId.trim() || null : null,
          library_version_id:
            selectedAsset.scope === 'library' ? libraryVersionId.trim() || null : null,
        },
        trim_start_ms: trimStart,
        trim_end_ms: trimEnd,
        guidance_notes: notes,
      })
      setGuidance((current) => [created, ...current])
      setMessage(
        'Draft saved. Review the exact range below, then approve it separately for this shot.',
      )
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to save reference guidance.')
    } finally {
      setPending(false)
    }
  }

  async function approve(item: Guidance) {
    setPending(true)
    setMessage(null)
    try {
      const approved = await videoApi.approveReferenceVideoGuidance(
        projectId,
        item.shot_id,
        item.id,
      )
      setGuidance((current) =>
        current.map((candidate) => (candidate.id === approved.id ? approved : candidate)),
      )
      setMessage('Exact source, trim, purpose, and fingerprint approved for this shot revision.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to approve reference guidance.')
    } finally {
      setPending(false)
    }
  }

  function chooseProvider(nextProviderId: string) {
    setProviderId(nextProviderId)
    const provider = providers.find((candidate) => candidate.id === nextProviderId)
    setPreserveEnvironment(provider?.preserves_starting_frame_environment ?? false)
  }

  async function generate(item: Guidance) {
    if (compositionId === '' || providerId === '') return
    setPending(true)
    setMessage(null)
    try {
      const job = await videoApi.submitControlledGeneration(
        projectId,
        item.shot_id,
        compositionId,
        item.id,
        {
          provider_id: providerId,
          preserve_environment: preserveEnvironment,
          prompt: generationPrompt,
          idempotency_key: idempotencyKey,
          seed: seed.trim() === '' ? null : seed.trim(),
        },
      )
      setGenerationJob(job)
      setMessage(
        'Controlled generation queued with the approved starting frame, reference range, and constraint plan frozen.',
      )
    } catch (error: unknown) {
      setMessage(
        isApiClientError(error)
          ? error.message
          : 'Unable to submit controlled reference-video generation.',
      )
    } finally {
      setPending(false)
    }
  }

  const selectedProvider = providers.find((provider) => provider.id === providerId) ?? null
  const selectedComposition =
    compositions.find((composition) => composition.id === compositionId) ?? null

  return (
    <section className="starting-frame-composer" aria-labelledby="reference-guidance-title">
      <h3 id="reference-guidance-title">Reference-video guidance</h3>
      <p>
        Pin an inspected source and a 250 ms–30 s range. Purpose is guidance only; it does not prove
        identity preservation or reliable emotional acting.
      </p>
      {message === null ? null : <p role="status">{message}</p>}
      <div className="form-grid">
        <label className="field">
          <span>Shot revision</span>
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
          <span>Exact shot binding</span>
          <select value={bindingId} onChange={(event) => setBindingId(event.target.value)}>
            <option value="">Select a binding</option>
            {bindings.map((binding) => (
              <option key={binding.id} value={binding.id}>
                Revision {binding.revision} · shot v{binding.shot_version}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Inspected video source</span>
          <select value={assetId} onChange={(event) => setAssetId(event.target.value)}>
            <option value="">Select a verified video</option>
            {sources.map((asset) => (
              <option key={asset.id} value={asset.id}>
                {asset.scope} · {asset.original_filename} · {String(asset.metadata?.duration_ms)} ms
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Purpose</span>
          <select
            value={purpose}
            onChange={(event) => setPurpose(event.target.value as ReferenceVideoPurpose)}
          >
            {purposes.map((item) => (
              <option key={item} value={item}>
                {item.replaceAll('_', ' ')}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Trim start (ms)</span>
          <input
            type="number"
            min={0}
            value={trimStart}
            onChange={(event) => setTrimStart(Number(event.target.value))}
          />
        </label>
        <label className="field">
          <span>Trim end, exclusive (ms)</span>
          <input
            type="number"
            min={250}
            value={trimEnd}
            onChange={(event) => setTrimEnd(Number(event.target.value))}
          />
        </label>
      </div>
      {selectedAsset?.scope === 'library' ? (
        <div className="form-grid">
          <label className="field">
            <span>Pinned library entity ID</span>
            <input
              value={libraryEntityId}
              onChange={(event) => setLibraryEntityId(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Pinned approved version ID</span>
            <input
              value={libraryVersionId}
              onChange={(event) => setLibraryVersionId(event.target.value)}
            />
          </label>
        </div>
      ) : null}
      <label className="field">
        <span>Guidance notes</span>
        <textarea
          maxLength={2_000}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
        />
      </label>
      <button
        type="button"
        className="button button--primary"
        disabled={pending || selectedShot === null || selectedAsset === null || bindingId === ''}
        onClick={() => void saveGuidance()}
      >
        Save immutable guidance revision
      </button>

      <fieldset className="controlled-generation-panel">
        <legend>Opt in to controlled video generation</legend>
        <p>
          This submits one approved shot only. VACE preserves the approved starting-frame set;
          Animate character/replacement uses the source-video environment and rejects separately
          pinned location or prop constraints.
        </p>
        <div className="form-grid">
          <label className="field">
            <span>Approved starting frame</span>
            <select
              value={compositionId}
              onChange={(event) => setCompositionId(event.target.value)}
            >
              <option value="">Select an approved frame</option>
              {compositions
                .filter((composition) => composition.status === 'approved')
                .map((composition) => (
                  <option key={composition.id} value={composition.id}>
                    Revision {composition.revision} · {composition.canvas_width}×
                    {composition.canvas_height}
                  </option>
                ))}
            </select>
          </label>
          <label className="field">
            <span>Qualified provider and operation</span>
            <select value={providerId} onChange={(event) => chooseProvider(event.target.value)}>
              <option value="">Select a provider</option>
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id} disabled={!provider.enabled}>
                  {provider.display_name} · {provider.operation.replaceAll('_', ' ')} ·{' '}
                  {provider.enabled ? 'qualified' : provider.runtime_state}
                </option>
              ))}
            </select>
          </label>
          <label className="field field--wide">
            <span>Shot prompt</span>
            <textarea
              maxLength={2_000}
              value={generationPrompt}
              onChange={(event) => setGenerationPrompt(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Idempotency key</span>
            <input
              maxLength={200}
              value={idempotencyKey}
              onChange={(event) => setIdempotencyKey(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Seed (optional)</span>
            <input value={seed} onChange={(event) => setSeed(event.target.value)} />
          </label>
        </div>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={preserveEnvironment}
            disabled={selectedProvider?.operation !== 'vace_performance_transfer'}
            onChange={(event) => setPreserveEnvironment(event.target.checked)}
          />
          Preserve the approved starting-frame environment
        </label>
        {selectedProvider === null ? null : (
          <p>
            {selectedProvider.preserves_starting_frame_environment
              ? 'This operation consumes both the approved frame and motion reference while retaining the approved set.'
              : 'This operation cannot promise the approved set. Select it only when the source-video environment is intended.'}{' '}
            Maximum reference range: {selectedProvider.maximum_guidance_ms} ms.
            {selectedProvider.unavailable_reason === null
              ? ''
              : ` Unavailable: ${selectedProvider.unavailable_reason}`}
          </p>
        )}
        {selectedComposition === null ? (
          <p>No approved starting frame is selected.</p>
        ) : (
          <p>
            Frozen frame revision {selectedComposition.revision}; visible character:{' '}
            {selectedComposition.visible_speaker_entity_id ?? 'not associated'}.
          </p>
        )}
        {generationJob === null ? null : (
          <p role="status">
            Job {generationJob.id} · {generationJob.status} ·{' '}
            {generationJob.conditioning.reference_video?.operation.replaceAll('_', ' ')}
          </p>
        )}
      </fieldset>

      <div className="starting-frame-grid">
        {guidance.map((item) => {
          const start = item.trim_start_ms / 1000
          const end = item.trim_end_ms / 1000
          return (
            <article key={item.id} className="starting-frame-card">
              <strong>
                Revision {item.revision} · {item.purpose.replaceAll('_', ' ')} · {item.status}
              </strong>
              <span>
                {item.trim_start_ms}–{item.trim_end_ms} ms · source v{item.source.asset_version}
              </span>
              <video
                controls
                preload="metadata"
                src={`${item.preview_url}#t=${String(start)},${String(end)}`}
                onTimeUpdate={(event) => {
                  if (event.currentTarget.currentTime >= end) event.currentTarget.pause()
                }}
              >
                Reference-video preview is unavailable in this browser.
              </video>
              <code>{item.fingerprint}</code>
              {item.guidance_notes === '' ? null : <p>{item.guidance_notes}</p>}
              {item.status === 'draft' ? (
                <button
                  type="button"
                  className="button button--secondary"
                  disabled={pending}
                  onClick={() => void approve(item)}
                >
                  Approve reviewed range
                </button>
              ) : (
                <>
                  <span>Approved independently</span>
                  <button
                    type="button"
                    className="button button--primary"
                    disabled={
                      pending ||
                      selectedProvider?.enabled !== true ||
                      selectedComposition === null ||
                      generationPrompt.trim() === '' ||
                      idempotencyKey.trim() === '' ||
                      item.purpose !== 'motion_performance' ||
                      item.trim_end_ms - item.trim_start_ms > selectedProvider.maximum_guidance_ms
                    }
                    onClick={() => void generate(item)}
                  >
                    Generate this approved shot
                  </button>
                </>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
