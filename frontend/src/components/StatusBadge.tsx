import type { JobStatus } from '../api/contracts'
import { formatStatus } from '../lib/format'

interface StatusBadgeProps {
  status: JobStatus
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span className="status-badge" data-status={status}>
      <span className="status-badge__dot" aria-hidden="true" />
      {formatStatus(status)}
    </span>
  )
}
