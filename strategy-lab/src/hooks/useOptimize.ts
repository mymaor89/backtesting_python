import { useState, useCallback, useRef } from 'react'
import type { TaskStatus } from '../types/api'

const API_BASE = '/api'
const POLL_INTERVAL_MS = 3000

export function useOptimize() {
  const [submitting, setSubmitting] = useState(false)
  const [polling, setPolling] = useState(false)
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    setPolling(false)
  }, [])

  const startPolling = useCallback(
    (taskId: string) => {
      setPolling(true)
      intervalRef.current = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/optimize/${taskId}`)
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          const data: TaskStatus = await res.json()
          setTaskStatus(data)
          if (data.status === 'done' || data.status === 'failed' || data.status === 'cancelled') {
            stopPolling()
          }
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e))
          stopPolling()
        }
      }, POLL_INTERVAL_MS)
    },
    [stopPolling],
  )

  const submit = useCallback(
    async (baseStrategy: Record<string, unknown>, evolverConfig: Record<string, unknown>) => {
      setSubmitting(true)
      setError(null)
      setTaskStatus(null)
      stopPolling()
      try {
        const res = await fetch(`${API_BASE}/optimize`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ base_strategy: baseStrategy, evolver_config: evolverConfig }),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data: TaskStatus = await res.json()
        setTaskStatus(data)
        startPolling(data.task_id)
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setSubmitting(false)
      }
    },
    [startPolling, stopPolling],
  )

  return { submitting, polling, taskStatus, error, submit }
}
