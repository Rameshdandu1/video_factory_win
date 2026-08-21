import { useState } from 'react'

import type { GenerationJob } from '../api/contracts'
import { usePretextLayout } from '../hooks/usePretextLayout'
import {
  compactIdentifier,
  formatBytes,
  formatDuration,
  formatNumber,
  formatSeed,
  formatTimestamp,
} from '../lib/format'
import { StatusBadge } from './StatusBadge'

interface JobDetailProps {
  job: GenerationJob | null
  isCancelling: boolean
  cancellationPending: boolean
  onCancel: (jobId: string) => Promise<void>
}

interface OutputAvailabilityState {
  snapshot: GenerationJob | null
  unavailable: boolean
  attempt: number
}

function GenerationProgress({ job }: { job: GenerationJob }) {
  if (job.status !== 'queued' && job.status !== 'running') {
    return null
  }

  if (job.progress === null) {
    return (
      <div
        className="generation-progress generation-progress--indeterminate"
        role="progressbar"
        aria-label="Generation progress"
      >
        <span className="generation-progress__track" aria-hidden="true">
          <span className="generation-progress__pulse" />
        </span>
        <span className="generation-progress__label">
          {job.status === 'queued' ? 'Waiting for the worker' : 'Generating without an estimate'}
        </span>
      </div>
    )
  }

  const percent = Math.round((job.progress.completed_units / job.progress.total_units) * 100)
  return (
    <div
      className="generation-progress"
      role="progressbar"
      aria-label="Generation progress"
      aria-valuemin={0}
      aria-valuemax={job.progress.total_units}
      aria-valuenow={job.progress.completed_units}
      aria-valuetext={`${String(percent)}% — ${job.progress.stage}`}
    >
      <span className="generation-progress__track" aria-hidden="true">
        <span className="generation-progress__value" style={{ width: `${String(percent)}%` }} />
      </span>
      <span className="generation-progress__label">
        {job.progress.stage} · {formatNumber(job.progress.completed_units)} of{' '}
        {formatNumber(job.progress.total_units)}
      </span>
    </div>
  )
}

function EmptyDetail() {
  const message = 'Select a generation to inspect its settings, state, and output.'
  const messageRef = usePretextLayout<HTMLParagraphElement>(message)
  return (
    <section className="job-detail job-detail--empty" aria-labelledby="detail-title">
      <div className="preview-stage preview-stage--empty" aria-hidden="true">
        <span className="preview-stage__frame" />
        <span className="preview-stage__scanline" />
      </div>
      <div className="empty-detail-copy">
        <p className="eyebrow">Workspace</p>
        <h2 id="detail-title">Generation details</h2>
        <p ref={messageRef} className="pretext-copy">
          {message}
        </p>
      </div>
    </section>
  )
}

export function JobDetail({ job, isCancelling, cancellationPending, onCancel }: JobDetailProps) {
  const promptRef = usePretextLayout<HTMLParagraphElement>(job?.request.prompt ?? '')
  const [outputAvailability, setOutputAvailability] = useState<OutputAvailabilityState>(() => ({
    snapshot: job,
    unavailable: false,
    attempt: 0,
  }))

  if (outputAvailability.snapshot !== job) {
    setOutputAvailability({
      snapshot: job,
      unavailable: false,
      attempt: outputAvailability.unavailable
        ? outputAvailability.attempt + 1
        : outputAvailability.attempt,
    })
  }

  if (job === null) {
    return <EmptyDetail />
  }

  const isActive = job.status === 'queued' || job.status === 'running'
  const result = job.result
  const outputUnavailable = outputAvailability.snapshot === job && outputAvailability.unavailable

  return (
    <section className="job-detail" aria-labelledby="detail-title">
      <header className="job-detail__header">
        <div>
          <p className="eyebrow">Selected job</p>
          <h2 id="detail-title">Generation details</h2>
        </div>
        <StatusBadge status={job.status} />
      </header>

      <div className="preview-stage">
        {result === null ? (
          <div className="preview-stage__waiting">
            <span className="preview-stage__aperture" aria-hidden="true" />
            <strong>
              {job.status === 'failed'
                ? 'Generation stopped'
                : job.status === 'cancelled'
                  ? 'Generation cancelled'
                  : 'Output pending'}
            </strong>
            <span>
              {job.request.width} × {job.request.height}
            </span>
          </div>
        ) : (
          <video
            key={`${job.id}:${String(outputAvailability.attempt)}`}
            className="preview-stage__video"
            src={result.download_url}
            controls
            preload="metadata"
            aria-label="Generated video preview"
            onError={() =>
              setOutputAvailability((current) =>
                current.snapshot === job ? { ...current, unavailable: true } : current,
              )
            }
            onLoadedData={() =>
              setOutputAvailability((current) =>
                current.snapshot === job ? { ...current, unavailable: false } : current,
              )
            }
          />
        )}
      </div>

      {outputUnavailable ? (
        <p className="output-unavailable" role="alert">
          This video output is currently unavailable. Refresh the job before trying again.
        </p>
      ) : null}

      <GenerationProgress job={job} />

      {cancellationPending && job.status === 'running' ? (
        <p className="pending-note" role="status">
          Cancellation requested. The worker is cleaning up safely.
        </p>
      ) : null}

      {job.failure === null ? null : (
        <div className="job-failure" role="alert">
          <div>
            <span className="job-failure__code">{job.failure.code}</span>
            <strong>{job.failure.message}</strong>
          </div>
          <p>
            {job.failure.retryable
              ? 'A new generation may succeed after the issue is resolved.'
              : 'Change the settings or runtime configuration before trying again.'}
          </p>
          <span>Reference {compactIdentifier(job.failure.correlation_id)}</span>
        </div>
      )}

      <div className="job-detail__body">
        <div className="prompt-block">
          <span>Prompt</span>
          <p ref={promptRef} className="pretext-copy">
            {job.request.prompt}
          </p>
        </div>

        <dl className="metadata-grid">
          <div>
            <dt>Model</dt>
            <dd>{job.request.model}</dd>
          </div>
          <div>
            <dt>Resolution</dt>
            <dd>
              {job.request.width} × {job.request.height}
            </dd>
          </div>
          <div>
            <dt>Frames</dt>
            <dd>{formatNumber(job.request.frame_count)}</dd>
          </div>
          <div>
            <dt>Seed</dt>
            <dd>{formatSeed(job.request.seed)}</dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>{formatTimestamp(job.created_at)}</dd>
          </div>
          <div>
            <dt>Runtime</dt>
            <dd>{job.backend ?? 'Not assigned'}</dd>
          </div>
        </dl>

        {result === null ? null : (
          <div className="output-summary">
            <div className="output-summary__heading">
              <div>
                <span className="eyebrow">Output</span>
                <strong>MP4 ready</strong>
              </div>
              <a className="button button--secondary" href={result.download_url} download>
                Download video
              </a>
            </div>
            <dl className="output-summary__metadata">
              <div>
                <dt>Size</dt>
                <dd>{formatBytes(result.size_bytes)}</dd>
              </div>
              <div>
                <dt>Duration</dt>
                <dd>{formatDuration(result.duration_seconds)}</dd>
              </div>
              <div>
                <dt>Checksum</dt>
                <dd title={result.sha256}>{compactIdentifier(result.sha256)}</dd>
              </div>
            </dl>
          </div>
        )}
      </div>

      <footer className="job-detail__footer">
        <span className="job-id" title={job.id}>
          ID {compactIdentifier(job.id)}
        </span>
        {isActive ? (
          <button
            className="button button--danger"
            type="button"
            disabled={isCancelling || cancellationPending}
            onClick={() => void onCancel(job.id)}
          >
            {isCancelling ? 'Requesting cancellation…' : 'Cancel generation'}
          </button>
        ) : null}
      </footer>
    </section>
  )
}
