import React from 'react'
import { useLeaderboard, type LeaderboardEntry } from '../hooks/useLeaderboard'

const cls = {
  container: 'bg-slate-900 rounded-xl border border-slate-800 overflow-hidden',
  header: 'px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50',
  title: 'text-sm font-bold text-slate-200 uppercase tracking-wider',
  table: 'w-full text-left border-collapse',
  th: 'px-4 py-3 text-[10px] font-bold text-slate-500 uppercase tracking-widest border-b border-slate-800 whitespace-nowrap',
  td: 'px-4 py-4 text-xs text-slate-300 border-b border-slate-800/50 whitespace-nowrap',
  row: 'hover:bg-slate-800/30 transition-colors',
  rank: 'text-cyan-500/50 font-mono font-bold text-[10px]',
  refreshBtn: 'text-xs text-cyan-400 hover:text-cyan-300 transition-colors flex items-center gap-1.5'
}

function Metric({ value, format }: { value: number, format: (v: number) => string }) {
  const color = value > 0 ? 'text-emerald-400' : value < 0 ? 'text-red-400' : 'text-slate-400'
  return <span className={color}>{format(value)}</span>
}

function formatPeriod(start: string | null, end: string | null): string {
  const fmt = (d: string) => {
    const date = new Date(d)
    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  }
  if (start && end) return `${fmt(start)} – ${fmt(end)}`
  if (start) return `${fmt(start)} – now`
  return '—'
}

export function Leaderboard() {
  const { entries, loading, refresh } = useLeaderboard()

  return (
    <div className={cls.container}>
      <div className={cls.header}>
        <div className="flex items-center gap-3">
          <h2 className={cls.title}>Performance Leaderboard</h2>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-900/30 text-cyan-500 font-bold border border-cyan-800/50">Top 50</span>
        </div>
        <button onClick={refresh} disabled={loading} className={cls.refreshBtn}>
          {loading ? 'Refreshing...' : '↻ Refresh'}
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className={cls.table}>
          <thead>
            <tr>
              <th className={cls.th}>Rank</th>
              <th className={cls.th}>Strategy</th>
              <th className={cls.th}>Symbol</th>
              <th className={cls.th}>Freq</th>
              <th className={cls.th}>User</th>
              <th className={cls.th}>Period</th>
              <th className={cls.th}>Return</th>
              <th className={cls.th}>B&H</th>
              <th className={cls.th}>Sharpe</th>
              <th className={cls.th}>Win Rate</th>
              <th className={cls.th}>Max DD</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && !loading && (
              <tr>
                <td colSpan={11} className="px-6 py-12 text-center text-slate-500 italic">
                  No backtest results found yet. Run some strategies to see them here!
                </td>
              </tr>
            )}
            {entries.map((e, idx) => (
              <tr key={e.run_id} className={cls.row}>
                <td className={cls.td}><span className={cls.rank}>#{idx + 1}</span></td>
                <td className={cls.td}>
                  <span className="font-bold text-slate-200">{e.strategy_name}</span>
                </td>
                <td className={cls.td}>
                  <span className="font-mono font-bold text-slate-300">{e.symbol || '—'}</span>
                </td>
                <td className={cls.td}>
                  <span className="text-[10px] text-slate-400 bg-slate-800/50 px-1.5 py-0.5 rounded border border-slate-700">{e.freq || '—'}</span>
                </td>
                <td className={cls.td}>
                  <span className="text-[10px] text-cyan-500/70 font-mono">{e.username ? `@${e.username}` : '—'}</span>
                </td>
                <td className={cls.td}>
                  <span className="text-[10px] text-slate-400 font-mono">{formatPeriod(e.start_date, e.end_date)}</span>
                </td>
                <td className={cls.td + " font-mono font-bold"}>
                  <Metric value={e.return_perc} format={v => `${v > 0 ? '+' : ''}${v.toFixed(2)}%`} />
                </td>
                <td className={cls.td + " font-mono"}>
                  <Metric value={e.buy_and_hold_perc} format={v => `${v > 0 ? '+' : ''}${v.toFixed(2)}%`} />
                </td>
                <td className={cls.td + " font-mono"}>{e.sharpe_ratio.toFixed(2)}</td>
                <td className={cls.td + " font-mono"}>{e.win_rate.toFixed(1)}%</td>
                <td className={cls.td + " font-mono text-red-500/70"}>
                  {e.max_drawdown <= 0 ? e.max_drawdown.toFixed(2) : `-${e.max_drawdown.toFixed(2)}`}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
