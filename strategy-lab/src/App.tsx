import { useState } from 'react'
import { StrategyEditor } from './components/StrategyEditor'
import { EquityChart } from './components/EquityChart'
import { TradesTable } from './components/TradesTable'
import { SummaryCards } from './components/SummaryCards'
import { OptimizePanel } from './components/OptimizePanel'
import { Leaderboard } from './components/Leaderboard'
import { useBacktest } from './hooks/useBacktest'
import { useHealthCheck } from './hooks/useHealthCheck'

type Tab = 'backtest' | 'optimize' | 'leaderboard'
type ResultTab = 'chart' | 'trades'

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('backtest')
  const [resultTab, setResultTab] = useState<ResultTab>('chart')
  const [username, setUsername] = useState('')
  const { loading, result, error, runBacktest } = useBacktest()
  const apiHealth = useHealthCheck()
  const isAdmin = username.trim().toLowerCase() === 'admin'

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-mono">
      {/* Header */}
      <header className="border-b border-slate-800 px-2 sm:px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-cyan-400 text-xl font-bold">⚡ Strategy Lab</span>
          <span className="text-slate-600 text-sm">fast-trade v2</span>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="text"
            value={username}
            onChange={e => setUsername(e.target.value)}
            placeholder="username"
            className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-cyan-600 w-28"
          />
          <span
            className={`inline-block w-2.5 h-2.5 rounded-full ${
              apiHealth === 'healthy'
                ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]'
                : apiHealth === 'unhealthy'
                ? 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.5)]'
                : 'bg-slate-500 animate-pulse'
            }`}
            title={`API: ${apiHealth}`}
          />
          <span className={`text-xs ${
            apiHealth === 'healthy' ? 'text-emerald-400' : apiHealth === 'unhealthy' ? 'text-red-400' : 'text-slate-500'
          }`}>
            {apiHealth === 'healthy' ? 'API' : apiHealth === 'unhealthy' ? 'Offline' : '...'}
          </span>
        </div>

        <nav className="flex gap-1">
          {(['backtest', 'optimize', 'leaderboard'] as Tab[]).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 rounded text-sm transition-colors ${
                activeTab === tab
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {tab === 'backtest' ? 'Strategy Lab' : tab === 'optimize' ? 'Optimizer' : 'Leaderboard'}
            </button>
          ))}
        </nav>
      </header>

      <main className="p-2 sm:p-6 w-full">
        {activeTab === 'backtest' ? (
          <div className="space-y-6">
            {/* Editor + Summary side-by-side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <StrategyEditor onRun={runBacktest} loading={loading} />
              <SummaryCards
                summary={result?.summary ?? null}
                runId={result?.run_id ?? null}
                cached={result?.cached ?? false}
              />
            </div>

            {/* API error */}
            {error && (
              <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 text-red-400 text-sm">
                {error}
              </div>
            )}

            {/* Equity chart + trade log */}
            {result && (
              <div className="bg-slate-900 rounded-xl border border-slate-800">
                <div className="flex gap-1 p-3 border-b border-slate-800">
                  {(['chart', 'trades'] as ResultTab[]).map(t => (
                    <button
                      key={t}
                      onClick={() => setResultTab(t)}
                      className={`px-3 py-1 rounded text-sm transition-colors ${
                        resultTab === t
                          ? 'bg-slate-700 text-slate-100'
                          : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      {t === 'chart' ? 'Equity Curve' : 'Trade Log'}
                    </button>
                  ))}
                  {result.cached && (
                    <span className="ml-auto self-center text-xs text-amber-500">
                      Cached result — equity curve not available. Re-run with use_cache: false for full data.
                    </span>
                  )}
                </div>
                <div className="p-4">
                  {resultTab === 'chart' ? (
                    <EquityChart data={result.equity_curve} />
                  ) : (
                    <TradesTable trades={result.trades} />
                  )}
                </div>
              </div>
            )}
          </div>
        ) : activeTab === 'optimize' ? (
          <OptimizePanel />
        ) : (
          <Leaderboard isAdmin={isAdmin} />
        )}
      </main>
    </div>
  )
}
