import { useEffect, useState } from 'react'

import { isApiClientError, videoApi } from '../api/client'
import type { TimelineRenderJob, TimelineRenderProvider } from '../api/contracts'

interface TimelineRenderPanelProps {
  projectId: string
  timelineId: string
}

export function TimelineRenderPanel({ projectId, timelineId }: TimelineRenderPanelProps) {
  const [provider, setProvider] = useState<TimelineRenderProvider | null>(null)
  const [job, setJob] = useState<TimelineRenderJob | null>(null)
  const [idempotencyKey, setIdempotencyKey] = useState('')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void videoApi
      .getTimelineRenderProvider(projectId, controller.signal)
      .then(setProvider)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(
            isApiClientError(error) ? error.message : 'Unable to load final renderer state.',
          )
        }
      })
    return () => controller.abort()
  }, [projectId])

  useEffect(() => {
    if (job === null || (job.status !== 'queued' && job.status !== 'running')) return
    const controller = new AbortController()
    const timer = window.setInterval(() => {
      void videoApi
        .getTimelineRender(projectId, timelineId, job.id, controller.signal)
        .then(setJob)
        .catch((error: unknown) => {
          if (!controller.signal.aborted) {
            setMessage(
              isApiClientError(error) ? error.message : 'Unable to refresh the timeline render.',
            )
          }
        })
    }, 2000)
    return () => {
      controller.abort()
      window.clearInterval(timer)
    }
  }, [job, projectId, timelineId])

  async function submit() {
    setPending(true)
    setMessage(null)
    try {
      setJob(await videoApi.submitTimelineRender(projectId, timelineId, idempotencyKey))
      setMessage('Final render queued from the immutable approved timeline.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to queue the timeline render.')
    } finally {
      setPending(false)
    }
  }

  async function cancel() {
    if (job === null) return
    setPending(true)
    try {
      setJob(await videoApi.cancelTimelineRender(projectId, timelineId, job.id))
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to cancel the timeline render.')
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="rough-cut-panel" aria-labelledby="timeline-render-heading">
      <div>
        <p className="eyebrow">Final timeline export</p>
        <h4 id="timeline-render-heading">Render approved timeline</h4>
        <p>
          Produces a measured MP4 from the exact approved visual, audio, title, and caption assets.
          A matching duration alone does not establish film-quality acceptance.
        </p>
      </div>
      {provider === null ? (
        <p>Checking renderer qualification…</p>
      ) : (
        <div className="film-gate-summary">
          <span>{provider.display_name}</span>
          <span>{`${String(provider.width)}×${String(provider.height)}`}</span>
          <span>{`${String(provider.duration_ms / 1000)} seconds`}</span>
          <span>{provider.enabled ? 'Qualified' : 'Disabled'}</span>
        </div>
      )}
      {provider?.unavailable_reason === null ||
      provider?.unavailable_reason === undefined ? null : (
        <p className="film-warning">{provider.unavailable_reason}</p>
      )}
      <label className="field">
        <span>Final-render idempotency key</span>
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
          {pending ? 'Working…' : 'Render approved timeline'}
        </button>
        {job?.status === 'queued' || job?.status === 'running' ? (
          <button
            type="button"
            className="button button--secondary"
            disabled={pending}
            onClick={() => void cancel()}
          >
            Cancel final render
          </button>
        ) : null}
      </div>
      {job === null ? null : (
        <div className="rough-cut-status" aria-live="polite">
          <strong>{job.status}</strong>
          <span>
            {`${String(job.visual_item_count)} visuals · ${String(job.audio_item_count)} audio tracks · ${String(job.caption_count)} captions`}
          </span>
          {job.progress === null ? (
            <span>{job.status === 'running' ? 'Rendering…' : 'Waiting for the renderer.'}</span>
          ) : (
            <progress value={job.progress.completed_units} max={job.progress.total_units}>
              {job.progress.completed_units}/{job.progress.total_units}
            </progress>
          )}
          {job.result === null ? null : (
            <a href={job.result.download_url}>Download approved-timeline MP4</a>
          )}
          {job.failure === null ? null : <span>{job.failure.message}</span>}
        </div>
      )}
      {message === null ? null : <p role="status">{message}</p>}
    </section>
  )
}
