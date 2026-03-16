import { useState, useCallback } from 'react'
import type { BacktestResponse } from '../types/api'

const API_BASE = '/api'

export function useBacktest() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<BacktestResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const runBacktest = useCallback(async (strategy: Record<string, unknown>) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy, use_cache: false }),
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`HTTP ${res.status}: ${text}`)
      }
      const data: BacktestResponse = await res.json()
      setResult(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  return { loading, result, error, runBacktest }
}
