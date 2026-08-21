import type { JobStatus } from '../api/contracts'

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

const numberFormatter = new Intl.NumberFormat()

const STATUS_LABELS: Readonly<Record<JobStatus, string>> = {
  queued: 'Queued',
  running: 'Running',
  succeeded: 'Ready',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

export function formatTimestamp(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? 'Unknown time' : dateFormatter.format(parsed)
}

export function formatBytes(value: number): string {
  if (value < 1_024) {
    return `${numberFormatter.format(value)} B`
  }
  if (value < 1_024 ** 2) {
    return `${(value / 1_024).toFixed(1)} KB`
  }
  if (value < 1_024 ** 3) {
    return `${(value / 1_024 ** 2).toFixed(1)} MB`
  }
  return `${(value / 1_024 ** 3).toFixed(1)} GB`
}

export function formatDuration(value: number | null): string {
  if (value === null) {
    return 'Not reported'
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} sec`
}

export function formatStatus(status: JobStatus): string {
  return STATUS_LABELS[status]
}

export function compactIdentifier(value: string): string {
  if (value.length <= 18) {
    return value
  }
  return `${value.slice(0, 10)}…${value.slice(-5)}`
}

export function formatNumber(value: number): string {
  return numberFormatter.format(value)
}

export function formatSeed(value: number): string {
  return Number.isSafeInteger(value) ? String(value) : 'Stored by server'
}
