import type { GenerationJob, JobStatus } from '../api/contracts'
import { compactIdentifier, formatSeed, formatTimestamp } from '../lib/format'
import { StatusBadge } from './StatusBadge'

interface JobQueueProps {
  jobs: GenerationJob[]
  selectedJobId: string | null
  statusFilter: JobStatus | ''
  nextCursor: string | null
  isLoading: boolean
  isRefreshing: boolean
  isLoadingMore: boolean
  onSelect: (job: GenerationJob) => Promise<void>
  onLoadMore: () => Promise<void>
  onStatusFilterChange: (status: JobStatus | '') => void
}

const STATUS_OPTIONS: readonly { value: JobStatus | ''; label: string }[] = [
  { value: '', label: 'All jobs' },
  { value: 'queued', label: 'Queued' },
  { value: 'running', label: 'Running' },
  { value: 'succeeded', label: 'Ready' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
]

export function JobQueue({
  jobs,
  selectedJobId,
  statusFilter,
  nextCursor,
  isLoading,
  isRefreshing,
  isLoadingMore,
  onSelect,
  onLoadMore,
  onStatusFilterChange,
}: JobQueueProps) {
  return (
    <aside className="job-queue" aria-labelledby="queue-title">
      <header className="job-queue__header">
        <div>
          <p className="eyebrow">History</p>
          <h2 id="queue-title">Recent jobs</h2>
        </div>
        {isRefreshing ? <span className="queue-refreshing">Refreshing…</span> : null}
      </header>

      <div className="queue-filter">
        <label htmlFor="job-status-filter">Filter jobs</label>
        <select
          id="job-status-filter"
          value={statusFilter}
          onChange={(event) => onStatusFilterChange(event.target.value as JobStatus | '')}
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value || 'all'} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="job-queue__content" aria-live="polite">
        {isLoading ? (
          <div className="queue-loading" role="status">
            <span className="queue-loading__line" />
            <span className="queue-loading__line" />
            <span className="queue-loading__line" />
            <span className="sr-only">Loading recent jobs</span>
          </div>
        ) : jobs.length === 0 ? (
          <div className="queue-empty">
            <strong>No generations yet</strong>
            <span>
              {statusFilter === ''
                ? 'Your next job will appear here.'
                : 'No jobs match this status.'}
            </span>
          </div>
        ) : (
          <ol className="job-list">
            {jobs.map((job) => (
              <li key={job.id}>
                <button
                  className="job-row"
                  data-selected={job.id === selectedJobId}
                  type="button"
                  aria-label={`Open generation ${job.id}`}
                  aria-current={job.id === selectedJobId ? 'true' : undefined}
                  onClick={() => void onSelect(job)}
                >
                  <span className="job-row__topline">
                    <StatusBadge status={job.status} />
                    <time dateTime={job.created_at}>{formatTimestamp(job.created_at)}</time>
                  </span>
                  <strong>{job.request.prompt}</strong>
                  <span className="job-row__meta">
                    {job.request.model} · {job.request.width} × {job.request.height} ·{' '}
                    {job.request.frame_count} frames · seed {formatSeed(job.request.seed)}
                  </span>
                  <time
                    className="job-row__terminal-time"
                    dateTime={job.completed_at ?? job.created_at}
                  >
                    {job.completed_at === null ? 'Created' : 'Completed'}{' '}
                    {formatTimestamp(job.completed_at ?? job.created_at)}
                  </time>
                  <span className="job-row__id">{compactIdentifier(job.id)}</span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>

      {nextCursor === null ? null : (
        <button
          className="button button--quiet queue-load-more"
          type="button"
          disabled={isLoadingMore}
          onClick={() => void onLoadMore()}
        >
          {isLoadingMore ? 'Loading…' : 'Load older jobs'}
        </button>
      )}
    </aside>
  )
}
