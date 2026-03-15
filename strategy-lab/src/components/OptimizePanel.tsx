import { useState } from 'react'
import { useOptimize } from '../hooks/useOptimize'
import type { OptimizeResult } from '../types/api'

const DEFAULT_STRATEGY = JSON.stringify(
  {
    symbol: 'BTC-USD',
    exchange: 'coinbase',
    freq: '4h',
    start: '2026-03-01',
    stop: '2026-03-14',
    base_balance: 1000,
    comission: 0.001,
    datapoints: [{ name: 'rsi', transformer: 'rsi', args: [14] }],
    enter: [['rsi', '<', 30]],
    exit: [['rsi', '>', 70]],
  },
  null,
  2,
)

const DEFAULT_EVOLVER = JSON.stringify(
  {
    num_generations: 20,
    sol_per_pop: 10,
    gene_space: {
      rsi_period: { low: 5, high: 50, step: 1 },
    },
  },
  null,
  2,
)

const STATUS_COLORS: Record<string, string> = {
  pending: 'text-amber-400',
  running: 'text-cyan-400',
  done: 'text-green-400',
  failed: 'text-red-400',
  cancelled: 'text-slate-400',
}

export function OptimizePanel() {
  const [strategy, setStrategy] = useState(DEFAULT_STRATEGY)
  const [evolver, setEvolver] = useState(DEFAULT_EVOLVER)
  const [parseError, setParseError] = useState<string | null>(null)
  const { submitting, polling, taskStatus, error, submit } = useOptimize()

  const handleSubmit = () => {
    try {
      const s = JSON.parse(strategy)
      const e = JSON.parse(evolver)
      setParseError(null)
      submit(s, e)
    } catch (err) {
      setParseError(`JSON parse error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  const optimizeResult = taskStatus?.status === 'done'
    ? (taskStatus.result as OptimizeResult | null)
    : null

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Base Strategy */}
        <div className="bg-slate-900 rounded-xl border border-slate-800 flex flex-col">
          <div className="px-4 py-3 border-b border-slate-800">
            <span className="text-sm text-slate-400 font-semibold">Base Strategy</span>
          </div>
          <textarea
            value={strategy}
            onChange={e => setStrategy(e.target.value)}
            className="flex-1 bg-transparent text-slate-300 text-xs p-4 resize-none outline-none min-h-[280px] font-mono leading-relaxed"
            spellCheck={false}
          />
        </div>

        {/* Evolver Config */}
        <div className="bg-slate-900 rounded-xl border border-slate-800 flex flex-col">
          <div className="px-4 py-3 border-b border-slate-800">
            <span className="text-sm text-slate-400 font-semibold">Evolver Config (PyGAD)</span>
          </div>
          <textarea
            value={evolver}
            onChange={e => setEvolver(e.target.value)}
            className="flex-1 bg-transparent text-slate-300 text-xs p-4 resize-none outline-none min-h-[280px] font-mono leading-relaxed"
            spellCheck={false}
          />
        </div>
      </div>

      {parseError && (
        <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 text-red-400 text-sm">
          {parseError}
        </div>
      )}

      <div className="flex items-center gap-4">
        <button
          onClick={handleSubmit}
          disabled={submitting || polling}
          className="px-6 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm font-medium transition-colors text-white"
        >
          {submitting ? 'Submitting…' : polling ? 'Optimizing…' : '⚡ Start Optimization'}
        </button>
        {polling && (
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
            <span className="text-slate-400 text-sm">GA running — polling every 3s</span>
          </div>
        )}
      </div>

      {(error || taskStatus) && (
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-6 space-y-4">
          {taskStatus && (
            <div className="flex items-center gap-3">
              <span className="text-slate-500 text-sm">Task:</span>
              <span className="text-slate-300 font-mono text-sm">{taskStatus.task_id}</span>
              <span className={`text-sm font-bold ${STATUS_COLORS[taskStatus.status] ?? 'text-slate-400'}`}>
                {taskStatus.status.toUpperCase()}
              </span>
            </div>
          )}

          {error && <div className="text-red-400 text-sm">{error}</div>}

          {optimizeResult && (
            <div className="space-y-4">
              <div className="flex items-center gap-8">
                <div>
                  <p className="text-slate-500 text-xs mb-1">Best Fitness</p>
                  <p className="text-green-400 text-2xl font-bold">
                    {optimizeResult.best_fitness?.toFixed(4) ?? '—'}
                  </p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">Generations Run</p>
                  <p className="text-slate-200 text-2xl font-bold">
                    {optimizeResult.generations_run ?? '—'}
                  </p>
                </div>
              </div>
              <div>
                <p className="text-slate-500 text-xs mb-2">Best Strategy (copy into Backtest tab to verify)</p>
                <pre className="bg-slate-800 rounded-lg p-4 text-xs text-slate-300 overflow-auto max-h-[300px] leading-relaxed">
                  {JSON.stringify(optimizeResult.best_strategy, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
