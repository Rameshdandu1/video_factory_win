import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { isApiClientError, videoApi } from '../api/client'
import type { GenerationJob, GenerationRequest, JobStatus, ModelCapability } from '../api/contracts'

const POLL_INTERVAL_MS = 2_500
const PAGE_SIZE = 20

type ConnectionState = 'connecting' | 'online' | 'offline'

export interface UiNotice {
  source: 'health' | 'models' | 'connection' | 'action'
  code: string
  message: string
  retryable: boolean
  correlationId: string | null
}

interface WorkspaceState {
  models: ModelCapability[]
  jobs: GenerationJob[]
  selectedJob: GenerationJob | null
  nextCursor: string | null
  connection: ConnectionState
  notice: UiNotice | null
  isLoadingModels: boolean
  isLoadingJobs: boolean
  isRefreshing: boolean
  isLoadingMore: boolean
  isSubmitting: boolean
  cancellingJobId: string | null
  cancellationPendingIds: ReadonlySet<string>
  selectJob: (job: GenerationJob) => Promise<void>
  submitJob: (request: GenerationRequest) => Promise<void>
  cancelJob: (jobId: string) => Promise<void>
  refresh: () => Promise<void>
  loadMore: () => Promise<void>
  retryConnection: () => Promise<void>
  dismissNotice: () => void
}

function noticeFromError(error: unknown, source: UiNotice['source']): UiNotice {
  if (isApiClientError(error)) {
    return {
      source,
      code: error.code,
      message: error.message,
      retryable: error.retryable,
      correlationId: error.correlation_id,
    }
  }
  return {
    source,
    code: 'INTERNAL_ERROR',
    message: 'The application could not complete the request.',
    retryable: true,
    correlationId: null,
  }
}

function isActive(job: GenerationJob): boolean {
  return job.status === 'queued' || job.status === 'running'
}

function requestWasStopped(controller: AbortController): boolean {
  return controller.signal.aborted
}

function mergeJob(items: GenerationJob[], incoming: GenerationJob): GenerationJob[] {
  const existingIndex = items.findIndex((item) => item.id === incoming.id)
  if (existingIndex === -1) {
    return [incoming, ...items]
  }
  return items.map((item) => (item.id === incoming.id ? incoming : item))
}

export function useGenerationWorkspace(statusFilter: JobStatus | ''): WorkspaceState {
  const [models, setModels] = useState<ModelCapability[]>([])
  const [jobs, setJobs] = useState<GenerationJob[]>([])
  const [selectedJob, setSelectedJob] = useState<GenerationJob | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [connection, setConnection] = useState<ConnectionState>('connecting')
  const [notice, setNotice] = useState<UiNotice | null>(null)
  const [isLoadingModels, setIsLoadingModels] = useState(true)
  const [isLoadingJobs, setIsLoadingJobs] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [cancellingJobId, setCancellingJobId] = useState<string | null>(null)
  const [cancellationPendingIds, setCancellationPendingIds] = useState<Set<string>>(() => new Set())

  const mountedRef = useRef(true)
  const selectedJobRef = useRef<GenerationJob | null>(null)
  const controllersRef = useRef(new Set<AbortController>())
  const listControllerRef = useRef<AbortController | null>(null)
  const selectionControllerRef = useRef<AbortController | null>(null)

  const trackedController = useCallback((): AbortController => {
    const controller = new AbortController()
    controllersRef.current.add(controller)
    return controller
  }, [])

  const releaseController = useCallback((controller: AbortController): void => {
    controllersRef.current.delete(controller)
  }, [])

  useEffect(() => {
    const controllers = controllersRef.current
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      for (const controller of controllers) {
        controller.abort()
      }
      controllers.clear()
    }
  }, [])

  const commitSelectedJob = useCallback((job: GenerationJob | null): void => {
    selectedJobRef.current = job
    setSelectedJob(job)
  }, [])

  const loadCapabilities = useCallback(async (): Promise<void> => {
    const controller = trackedController()
    setIsLoadingModels(true)
    setConnection('connecting')
    try {
      const checkHealth = async (): Promise<void> => {
        try {
          await videoApi.health(controller.signal)
          if (mountedRef.current && !requestWasStopped(controller)) {
            setConnection('online')
            setNotice((current) => (current?.source === 'health' ? null : current))
          }
        } catch (error: unknown) {
          if (!controller.signal.aborted && mountedRef.current) {
            setConnection('offline')
            setNotice(noticeFromError(error, 'health'))
          }
        }
      }

      const loadModels = async (): Promise<void> => {
        try {
          const modelList = await videoApi.listModels(controller.signal)
          if (mountedRef.current && !requestWasStopped(controller)) {
            setModels(modelList.items)
            setNotice((current) => (current?.source === 'models' ? null : current))
          }
        } catch (error: unknown) {
          if (!controller.signal.aborted && mountedRef.current) {
            setNotice(noticeFromError(error, 'models'))
          }
        }
      }

      await Promise.all([checkHealth(), loadModels()])
    } finally {
      releaseController(controller)
      if (mountedRef.current) {
        setIsLoadingModels(false)
      }
    }
  }, [releaseController, trackedController])

  const refreshJobs = useCallback(
    async (background = false, cancelExisting = true): Promise<void> => {
      if (listControllerRef.current !== null && !cancelExisting) {
        return
      }
      if (cancelExisting) {
        listControllerRef.current?.abort()
        setIsLoadingMore(false)
      }

      const controller = trackedController()
      listControllerRef.current = controller
      if (!background) {
        setIsRefreshing(true)
      }
      try {
        const options = {
          limit: PAGE_SIZE,
          signal: controller.signal,
          ...(statusFilter === '' ? {} : { status: statusFilter }),
        }
        let page = await videoApi.listJobs(options)
        controller.signal.throwIfAborted()
        if (!mountedRef.current) {
          return
        }
        const selectedAtStart = selectedJobRef.current
        const selectedFromPage =
          selectedAtStart === null
            ? null
            : (page.items.find((item) => item.id === selectedAtStart.id) ?? null)
        const refreshedSelected =
          selectedAtStart !== null && isActive(selectedAtStart) && selectedFromPage === null
            ? await videoApi.getJob(selectedAtStart.id, controller.signal)
            : selectedFromPage
        controller.signal.throwIfAborted()

        const selectedEnteredFilter =
          statusFilter !== '' &&
          selectedAtStart !== null &&
          refreshedSelected !== null &&
          selectedAtStart.status !== refreshedSelected.status &&
          refreshedSelected.status === statusFilter &&
          !page.items.some((item) => item.id === refreshedSelected.id)
        if (selectedEnteredFilter) {
          page = await videoApi.listJobs(options)
          controller.signal.throwIfAborted()
        }

        setJobs(page.items)
        setNextCursor(page.next_cursor)
        const currentSelected = selectedJobRef.current
        if (currentSelected === null) {
          commitSelectedJob(page.items[0] ?? null)
        } else if (refreshedSelected?.id === currentSelected.id) {
          commitSelectedJob(
            page.items.find((item) => item.id === currentSelected.id) ?? refreshedSelected,
          )
        } else {
          commitSelectedJob(
            page.items.find((item) => item.id === currentSelected.id) ?? currentSelected,
          )
        }
        setCancellationPendingIds((current) => {
          const next = new Set(current)
          for (const job of page.items) {
            if (!isActive(job)) {
              next.delete(job.id)
            }
          }
          if (refreshedSelected !== null && !isActive(refreshedSelected)) {
            next.delete(refreshedSelected.id)
          }
          return next
        })
        setConnection('online')
        setNotice((current) => (current?.source === 'connection' ? null : current))
      } catch (error: unknown) {
        if (!controller.signal.aborted && mountedRef.current) {
          setConnection('offline')
          setNotice(noticeFromError(error, 'connection'))
        }
      } finally {
        if (listControllerRef.current === controller) {
          listControllerRef.current = null
          if (mountedRef.current && !background) {
            setIsRefreshing(false)
          }
        }
        releaseController(controller)
      }
    },
    [commitSelectedJob, releaseController, statusFilter, trackedController],
  )

  useEffect(() => {
    const timer = window.setTimeout(() => void loadCapabilities(), 0)
    return () => window.clearTimeout(timer)
  }, [loadCapabilities])

  useEffect(() => {
    let disposed = false
    const timer = window.setTimeout(() => {
      setIsLoadingJobs(true)
      void refreshJobs(false, true).finally(() => {
        if (!disposed && mountedRef.current) {
          setIsLoadingJobs(false)
        }
      })
    }, 0)
    return () => {
      disposed = true
      window.clearTimeout(timer)
    }
  }, [refreshJobs])

  const hasActiveJobs = useMemo(
    () => jobs.some(isActive) || (selectedJob !== null && isActive(selectedJob)),
    [jobs, selectedJob],
  )

  useEffect(() => {
    if (!hasActiveJobs) {
      return undefined
    }
    const interval = window.setInterval(() => {
      if (document.visibilityState === 'hidden') {
        return
      }
      void refreshJobs(true, false)
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [hasActiveJobs, refreshJobs])

  const selectJob = useCallback(
    async (job: GenerationJob): Promise<void> => {
      selectionControllerRef.current?.abort()
      commitSelectedJob(job)
      const controller = trackedController()
      selectionControllerRef.current = controller
      try {
        const current = await videoApi.getJob(job.id, controller.signal)
        if (
          !mountedRef.current ||
          controller.signal.aborted ||
          selectionControllerRef.current !== controller ||
          selectedJobRef.current?.id !== job.id
        ) {
          return
        }
        commitSelectedJob(current)
        setJobs((items) => mergeJob(items, current))
        if (!isActive(current)) {
          setCancellationPendingIds((items) => {
            const next = new Set(items)
            next.delete(current.id)
            return next
          })
        }
      } catch (error: unknown) {
        if (!controller.signal.aborted && mountedRef.current) {
          setNotice(noticeFromError(error, 'action'))
        }
      } finally {
        if (selectionControllerRef.current === controller) {
          selectionControllerRef.current = null
        }
        releaseController(controller)
      }
    },
    [commitSelectedJob, releaseController, trackedController],
  )

  const submitJob = useCallback(
    async (request: GenerationRequest): Promise<void> => {
      const controller = trackedController()
      setIsSubmitting(true)
      try {
        const submitted = await videoApi.submitJob(request, controller.signal)
        if (!mountedRef.current || controller.signal.aborted) {
          return
        }
        commitSelectedJob(submitted)
        if (statusFilter === '' || statusFilter === submitted.status) {
          setJobs((items) => mergeJob(items, submitted))
        }
        setNotice(null)
        setConnection('online')
      } catch (error: unknown) {
        if (!controller.signal.aborted && mountedRef.current) {
          setNotice(noticeFromError(error, 'action'))
        }
      } finally {
        releaseController(controller)
        if (mountedRef.current) {
          setIsSubmitting(false)
        }
      }
    },
    [commitSelectedJob, releaseController, statusFilter, trackedController],
  )

  const cancelJob = useCallback(
    async (jobId: string): Promise<void> => {
      const controller = trackedController()
      setCancellingJobId(jobId)
      try {
        const cancelled = await videoApi.cancelJob(jobId, controller.signal)
        if (!mountedRef.current || controller.signal.aborted) {
          return
        }
        if (selectedJobRef.current?.id === cancelled.id) {
          commitSelectedJob(cancelled)
        }
        setJobs((items) => mergeJob(items, cancelled))
        setCancellationPendingIds((current) => {
          const next = new Set(current)
          if (cancelled.status === 'running') {
            next.add(cancelled.id)
          } else {
            next.delete(cancelled.id)
          }
          return next
        })
        setNotice(null)
      } catch (error: unknown) {
        if (!controller.signal.aborted && mountedRef.current) {
          setNotice(noticeFromError(error, 'action'))
        }
      } finally {
        releaseController(controller)
        if (mountedRef.current) {
          setCancellingJobId(null)
        }
      }
    },
    [commitSelectedJob, releaseController, trackedController],
  )

  const loadMore = useCallback(async (): Promise<void> => {
    if (nextCursor === null || listControllerRef.current !== null) {
      return
    }
    const controller = trackedController()
    listControllerRef.current = controller
    setIsLoadingMore(true)
    try {
      const options = {
        limit: PAGE_SIZE,
        cursor: nextCursor,
        signal: controller.signal,
        ...(statusFilter === '' ? {} : { status: statusFilter }),
      }
      const page = await videoApi.listJobs(options)
      if (
        !mountedRef.current ||
        controller.signal.aborted ||
        listControllerRef.current !== controller
      ) {
        return
      }
      setJobs((current) => {
        const knownIds = new Set(current.map((item) => item.id))
        return [...current, ...page.items.filter((item) => !knownIds.has(item.id))]
      })
      setNextCursor(page.next_cursor)
    } catch (error: unknown) {
      if (!controller.signal.aborted && mountedRef.current) {
        setNotice(noticeFromError(error, 'connection'))
      }
    } finally {
      if (listControllerRef.current === controller) {
        listControllerRef.current = null
        if (mountedRef.current) {
          setIsLoadingMore(false)
        }
      }
      releaseController(controller)
    }
  }, [nextCursor, releaseController, statusFilter, trackedController])

  const retryConnection = useCallback(async (): Promise<void> => {
    await Promise.all([loadCapabilities(), refreshJobs(false, true)])
  }, [loadCapabilities, refreshJobs])

  return {
    models,
    jobs,
    selectedJob,
    nextCursor,
    connection,
    notice,
    isLoadingModels,
    isLoadingJobs,
    isRefreshing,
    isLoadingMore,
    isSubmitting,
    cancellingJobId,
    cancellationPendingIds,
    selectJob,
    submitJob,
    cancelJob,
    refresh: () => refreshJobs(false, true),
    loadMore,
    retryConnection,
    dismissNotice: () => setNotice(null),
  }
}
