import { useState, useEffect, useRef, useCallback } from 'react'

type HealthStatus = 'checking' | 'healthy' | 'unhealthy'

const POLL_INTERVAL = 15_000 // 15 seconds

export function useHealthCheck() {
  const [status, setStatus] = useState<HealthStatus>('checking')
  const timerRef = useRef<ReturnType<typeof setInterval>>()

  const check = useCallback(async () => {
    try {
      const res = await fetch('/api/health', { signal: AbortSignal.timeout(5000) })
      setStatus(res.ok ? 'healthy' : 'unhealthy')
    } catch {
      setStatus('unhealthy')
    }
  }, [])

  useEffect(() => {
    check()
    timerRef.current = setInterval(check, POLL_INTERVAL)
    return () => clearInterval(timerRef.current)
  }, [check])

  return status
}
