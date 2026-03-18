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
  start_date: string | null
  end_date: string | null
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
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
      setEntries(await res.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const deleteEntry = useCallback(async (runId: string) => {
    const res = await fetch(`${API_BASE}/runs/${runId}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
    setEntries(prev => prev.filter(e => e.run_id !== runId))
  }, [])

  useEffect(() => {
    fetchLeaderboard()
  }, [fetchLeaderboard])

  return { entries, loading, error, refresh: fetchLeaderboard, deleteEntry }
}
