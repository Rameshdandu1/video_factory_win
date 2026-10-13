import { useEffect, useState } from 'react'

import { isApiClientError, videoApi } from '../api/client'
import type { RoughCutJob, RoughCutProvider } from '../api/contracts'

interface RoughCutPanelProps {
  projectId: string
}

export function RoughCutPanel({ projectId }: RoughCutPanelProps) {
  const [provider, setProvider] = useState<RoughCutProvider | null>(null)
  const [job, setJob] = useState<RoughCutJob | null>(null)
  const [idempotencyKey, setIdempotencyKey] = useState('')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void videoApi
      .getRoughCutProvider(projectId, controller.signal)
      .then(setProvider)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(isApiClientError(error) ? error.message : 'Unable to load the renderer state.')
        }
      })
    return () => controller.abort()
  }, [projectId])

  useEffect(() => {
    if (job === null || (job.status !== 'queued' && job.status !== 'running')) return
    const controller = new AbortController()
    const timer = window.setInterval(() => {
      void videoApi
        .getRoughCut(projectId, job.id, controller.signal)
        .then(setJob)
        .catch((error: unknown) => {
          if (!controller.signal.aborted) {
            setMessage(isApiClientError(error) ? error.message : 'Unable to refresh the rough cut.')
          }
        })
    }, 2000)
    return () => {
      controller.abort()
      window.clearInterval(timer)
    }
  }, [job, projectId])

  async function submit() {
    setPending(true)
    setMessage(null)
    try {
      const submitted = await videoApi.submitRoughCut(projectId, idempotencyKey)
      setJob(submitted)
      setMessage('Rough cut queued with an immutable approved-media manifest.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to queue the rough cut.')
    } finally {
      setPending(false)
    }
  }

  async function cancel() {
    if (job === null) return
    setPending(true)
    try {
      setJob(await videoApi.cancelRoughCut(projectId, job.id))
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to cancel the rough cut.')
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="rough-cut-panel" aria-labelledby="rough-cut-heading">
      <div>
        <p className="eyebrow">Phase 7A</p>
        <h4 id="rough-cut-heading">Approved audio + storyboard rough cut</h4>
        <p>
          This creates one 900-second review film from current approved storyboard images and
          recorded Telugu dialogue. It does not generate final footage or imply film acceptance.
        </p>
      </div>
      {provider === null ? (
        <p>Checking renderer qualification…</p>
      ) : (
        <div className="film-gate-summary">
          <span>{provider.display_name}</span>
          <span>{`${String(provider.width)}×${String(provider.height)}`}</span>
          <span>{`${String(provider.fps_numerator)}/${String(provider.fps_denominator)} fps`}</span>
          <span>{provider.enabled ? 'Qualified' : 'Disabled'}</span>
        </div>
      )}
      {provider?.unavailable_reason === null ||
      provider?.unavailable_reason === undefined ? null : (
        <p className="film-warning">{provider.unavailable_reason}</p>
      )}
      <label className="field">
        <span>Idempotency key</span>
        <input
          value={idempotencyKey}
          maxLength={200}
          onChange={(event) => setIdempotencyKey(event.target.value)}
        />
      </label>
      <div className="rough-cut-actions">
        <button
          type="button"
          className="button button--primary"
          disabled={
            pending ||
            provider?.enabled !== true ||
            idempotencyKey.trim() === '' ||
            job?.status === 'running'
          }
          onClick={() => void submit()}
        >
          {pending ? 'Working…' : 'Render approved rough cut'}
        </button>
        {job?.status === 'queued' || job?.status === 'running' ? (
          <button
            type="button"
            className="button button--secondary"
            disabled={pending}
            onClick={() => void cancel()}
          >
            Cancel render
          </button>
        ) : null}
      </div>
      {job === null ? null : (
        <div className="rough-cut-status" aria-live="polite">
          <strong>{job.status}</strong>
          <span>{`${String(job.shot_count)} approved shots · ${String(job.duration_ms / 1000)} seconds`}</span>
          {job.progress === null ? (
            <span>{job.status === 'running' ? 'Rendering…' : 'Waiting for the renderer.'}</span>
          ) : (
            <progress value={job.progress.completed_units} max={job.progress.total_units}>
              {job.progress.completed_units}/{job.progress.total_units}
            </progress>
          )}
          {job.result === null ? null : (
            <a href={job.result.download_url}>Download rough-cut MP4</a>
          )}
          {job.failure === null ? null : <span>{job.failure.message}</span>}
        </div>
      )}
      {message === null ? null : <p role="status">{message}</p>}
    </section>
  )
}
