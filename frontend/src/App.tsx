import { useState } from 'react'

import type { JobStatus } from './api/contracts'
import { GenerationForm } from './components/GenerationForm'
import { JobDetail } from './components/JobDetail'
import { JobQueue } from './components/JobQueue'
import { useGenerationWorkspace } from './hooks/useGenerationWorkspace'

export function App() {
  const [statusFilter, setStatusFilter] = useState<JobStatus | ''>('')
  const workspace = useGenerationWorkspace(statusFilter)

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace">
        Skip to workspace
      </a>

      <header className="app-header">
        <div className="brand-lockup" aria-label="Video Factory">
          <span className="brand-mark" aria-hidden="true">
            <span />
          </span>
          <div>
            <strong>Video Factory</strong>
            <span>Wan2.1 generation console</span>
          </div>
        </div>

        <div className="header-actions">
          <div className="connection-state" role="status" aria-live="polite">
            <span className="connection-state__dot" data-state={workspace.connection} />
            <span>
              {workspace.connection === 'online'
                ? 'API connected'
                : workspace.connection === 'connecting'
                  ? 'Connecting to API'
                  : 'API unavailable'}
            </span>
          </div>
          <button
            className="button button--quiet header-refresh"
            type="button"
            disabled={workspace.isRefreshing}
            onClick={() => void workspace.refresh()}
          >
            {workspace.isRefreshing ? 'Refreshing…' : 'Refresh jobs'}
          </button>
        </div>
      </header>

      {workspace.notice === null ? null : (
        <div className="notice" role="alert">
          <div>
            <span className="notice__code">{workspace.notice.code}</span>
            <strong>{workspace.notice.message}</strong>
            {workspace.notice.correlationId === null ? null : (
              <span>Reference {workspace.notice.correlationId}</span>
            )}
          </div>
          <div className="notice__actions">
            {workspace.notice.source !== 'action' && workspace.notice.retryable ? (
              <button
                className="button button--quiet"
                type="button"
                onClick={() => void workspace.retryConnection()}
              >
                Retry connection
              </button>
            ) : null}
            <button
              className="icon-button"
              type="button"
              aria-label="Dismiss message"
              onClick={workspace.dismissNotice}
            >
              <span aria-hidden="true">×</span>
            </button>
          </div>
        </div>
      )}

      <main id="workspace" className="workspace-grid">
        <GenerationForm
          models={workspace.models}
          isLoadingModels={workspace.isLoadingModels}
          isSubmitting={workspace.isSubmitting}
          onSubmit={workspace.submitJob}
        />
        <JobDetail
          job={workspace.selectedJob}
          isCancelling={workspace.cancellingJobId === workspace.selectedJob?.id}
          cancellationPending={
            workspace.selectedJob === null
              ? false
              : workspace.cancellationPendingIds.has(workspace.selectedJob.id)
          }
          onCancel={workspace.cancelJob}
        />
        <JobQueue
          jobs={workspace.jobs}
          selectedJobId={workspace.selectedJob?.id ?? null}
          statusFilter={statusFilter}
          nextCursor={workspace.nextCursor}
          isLoading={workspace.isLoadingJobs}
          isRefreshing={workspace.isRefreshing}
          isLoadingMore={workspace.isLoadingMore}
          onSelect={workspace.selectJob}
          onLoadMore={workspace.loadMore}
          onStatusFilterChange={setStatusFilter}
        />
      </main>
    </div>
  )
}

export default App
