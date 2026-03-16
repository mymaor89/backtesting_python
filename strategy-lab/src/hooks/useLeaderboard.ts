import { useState, useEffect, useCallback } from 'react'

const API_BASE = '/api-strategy'

export interface LeaderboardEntry {
  run_id: string
  strategy_name: string
  symbol: string
  freq: string
  return_perc: number
  sharpe_ratio: number
  win_rate: number
  total_trades: number
  max_drawdown: number
  buy_and_hold_perc: number
  username: string | null
  finished_at: string
}

export function useLeaderboard() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchLeaderboard = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/leaderboard`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`)
      }
      const data = await res.json()
      setEntries(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchLeaderboard()
  }, [fetchLeaderboard])

  return { entries, loading, error, refresh: fetchLeaderboard }
}
