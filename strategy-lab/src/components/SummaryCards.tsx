import type { Summary } from '../types/api'

interface Props {
  summary: Summary | null
  runId: string | null
  cached: boolean
}

const fmt = (v: number | null | undefined, decimals = 2, suffix = '') =>
  v == null ? '—' : `${v.toFixed(decimals)}${suffix}`

interface MetricConfig {
  label: string
  key: string
  format: (v: number | null | undefined) => string
  greenWhenPositive?: boolean
}

const METRICS: MetricConfig[] = [
  { label: 'Total Return', key: 'return_perc', format: v => fmt(v, 2, '%'), greenWhenPositive: true },
  { label: 'Sharpe Ratio', key: 'sharpe_ratio', format: v => fmt(v, 3), greenWhenPositive: true },
  { label: 'Max Drawdown', key: 'max_drawdown', format: v => fmt(v, 2, '%'), greenWhenPositive: false },
  { label: 'Win Rate', key: 'win_rate', format: v => fmt(v, 1, '%'), greenWhenPositive: true },
  { label: 'Profit Factor', key: 'profit_factor', format: v => fmt(v, 2), greenWhenPositive: true },
  { label: 'Trades', key: 'num_trades', format: v => (v == null ? '—' : String(v)) },
  { label: 'Buy & Hold', key: 'buy_and_hold_perc', format: v => fmt(v, 2, '%'), greenWhenPositive: true },
  { label: 'Time in Market', key: 'time_in_market', format: v => fmt(v, 1, '%') },
  { label: 'Avg Trade', key: 'avg_trade_perc', format: v => fmt(v, 2, '%'), greenWhenPositive: true },
  { label: 'Total Fees', key: 'total_fees', format: v => v == null ? '—' : `$${v.toFixed(2)}` },
  { label: 'Fees %', key: 'total_fees_perc', format: v => fmt(v, 2, '%') },
  { label: 'Leverage', key: 'leverage', format: v => fmt(v, 1, 'x') },
  { label: 'Liquidations', key: 'num_liquidations', format: v => (v == null ? '—' : String(v)), greenWhenPositive: false },
]

function valueColor(metric: MetricConfig, value: number | null | undefined): string {
  if (value == null || metric.greenWhenPositive === undefined) return 'text-slate-200'
  const positive = value > 0
  if (metric.greenWhenPositive) return positive ? 'text-green-400' : 'text-red-400'
  return positive ? 'text-red-400' : 'text-green-400'
}

export function SummaryCards({ summary, runId, cached }: Props) {
  if (!summary) {
    return (
      <div className="bg-slate-900 rounded-xl border border-slate-800 flex items-center justify-center min-h-[200px]">
        <p className="text-slate-600 text-sm">Run a backtest to see results</p>
      </div>
    )
  }

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <span className="text-sm text-slate-400 font-semibold">Summary</span>
        <div className="flex items-center gap-2">
          {cached && (
            <span className="px-2 py-0.5 bg-amber-900/30 text-amber-400 border border-amber-700/30 rounded text-xs">
              cached
            </span>
          )}
          {runId && <span className="text-slate-600 text-xs font-mono">{runId.slice(0, 8)}…</span>}
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-6 gap-px bg-slate-800">
        {METRICS.map(m => {
          const val = (summary as Record<string, unknown>)[m.key] as number | null | undefined
          return (
            <div key={m.key} className="bg-slate-900 p-4">
              <p className="text-slate-500 text-xs mb-1">{m.label}</p>
              <p className={`text-lg font-semibold ${valueColor(m, val)}`}>{m.format(val)}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
