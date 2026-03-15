import { useState } from 'react'
import { StrategyForm } from './StrategyForm'
import {
  DEFAULT_FORM_STATE, PRESET_STRATEGIES, formToStrategy, strategyToForm, validate,
  type StrategyFormState,
} from '../lib/strategy'

const DEFAULT_JSON = JSON.stringify(formToStrategy(DEFAULT_FORM_STATE), null, 2)

type Mode = 'json' | 'form'

interface Props {
  onRun: (strategy: Record<string, unknown>) => void
  loading: boolean
}

export function StrategyEditor({ onRun, loading }: Props) {
  const [mode, setMode]           = useState<Mode>('json')
  const [json, setJson]           = useState(DEFAULT_JSON)
  const [formState, setFormState] = useState<StrategyFormState>(DEFAULT_FORM_STATE)
  const [switchError, setSwitchError] = useState<string | null>(null)

  // ── Mode switching ──────────────────────────────────────────────────────────

  const switchToForm = () => {
    try {
      setFormState(strategyToForm(JSON.parse(json)))
      setSwitchError(null)
      setMode('form')
    } catch {
      setSwitchError('Fix JSON errors before switching to form mode')
    }
  }

  const switchToJson = () => {
    setJson(JSON.stringify(formToStrategy(formState), null, 2))
    setSwitchError(null)
    setMode('json')
  }

  const handleModeClick = (next: Mode) => {
    if (next === mode) return
    next === 'form' ? switchToForm() : switchToJson()
  }

  // ── Preset loader ───────────────────────────────────────────────────────────

  const [showPresets, setShowPresets] = useState(false)

  const applyPreset = (name: string) => {
    const preset = PRESET_STRATEGIES.find(p => p.name === name)
    if (!preset) return
    setFormState(preset.state)
    setJson(JSON.stringify(formToStrategy(preset.state), null, 2))
    setSwitchError(null)
    setShowPresets(false)
  }

  const categories = [...new Set(PRESET_STRATEGIES.map(p => p.category))]

  // ── Run ─────────────────────────────────────────────────────────────────────

  const handleRun = () => {
    if (mode === 'json') {
      try {
        onRun(JSON.parse(json))
        setSwitchError(null)
      } catch (e) {
        setSwitchError(`Invalid JSON: ${e instanceof Error ? e.message : String(e)}`)
      }
    } else {
      const { errors } = validate(formState)
      if (errors.length > 0) {
        setSwitchError(`Fix ${errors.length} validation error${errors.length > 1 ? 's' : ''} before running`)
        return
      }
      onRun(formToStrategy(formState))
      setSwitchError(null)
    }
  }

  // ── Validation summary (form mode only) ────────────────────────────────────

  const { errors: formErrors } = mode === 'form' ? validate(formState) : { errors: [] }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800 flex flex-col relative">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex gap-1">
            {(['json', 'form'] as Mode[]).map(m => (
              <button
                key={m}
                onClick={() => handleModeClick(m)}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                  mode === m
                    ? 'bg-slate-700 text-slate-100'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {m === 'json' ? '{ } JSON' : '⊞ Form'}
              </button>
            ))}
          </div>

          <div className="relative">
            <button
              onClick={() => setShowPresets(!showPresets)}
              className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium border transition-colors ${
                showPresets
                  ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30'
                  : 'text-slate-400 border-slate-700 hover:border-slate-600 hover:text-slate-200'
              }`}
            >
              <span>📁 View Presets</span>
              <span className={`text-[10px] transition-transform ${showPresets ? 'rotate-180' : ''}`}>▼</span>
            </button>

            {showPresets && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setShowPresets(false)} />
                <div className="absolute left-0 mt-2 w-[480px] bg-slate-800 border border-slate-700 rounded-lg shadow-2xl z-20 overflow-hidden max-h-[500px] flex">
                  {/* Left Sidebar: Categories */}
                  <div className="w-1/3 bg-slate-900/50 border-r border-slate-700 p-2 space-y-1 overflow-y-auto">
                    <p className="px-2 py-1 text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-1">Categories</p>
                    {categories.map(cat => (
                      <div key={cat} className="group">
                        <p className="px-2 py-1.5 text-xs text-slate-400 font-medium">{cat}</p>
                        <div className="pl-2 space-y-0.5 mt-0.5">
                          {PRESET_STRATEGIES.filter(p => p.category === cat).map(p => (
                            <button
                              key={p.name}
                              onClick={() => applyPreset(p.name)}
                              className="w-full text-left px-2 py-1 round text-[11px] text-slate-500 hover:text-cyan-400 hover:bg-slate-700/50 transition-colors truncate"
                            >
                              • {p.name}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Right: Detailed List */}
                  <div className="flex-1 p-3 overflow-y-auto space-y-4">
                    {categories.map(cat => (
                      <div key={cat} className="space-y-2">
                        <h4 className="text-[10px] uppercase tracking-widest text-cyan-500 font-bold px-1 border-b border-cyan-500/20 pb-1">{cat}</h4>
                        <div className="grid grid-cols-1 gap-2">
                          {PRESET_STRATEGIES.filter(p => p.category === cat).map(p => (
                            <button
                              key={p.name}
                              onClick={() => applyPreset(p.name)}
                              className="group text-left p-2.5 rounded-lg border border-slate-700 hover:border-cyan-500/50 hover:bg-slate-700/30 transition-all"
                            >
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-xs font-bold text-slate-200 group-hover:text-cyan-400 tracking-tight transition-colors">{p.name}</span>
                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-900 text-slate-500 font-mono leading-none group-hover:text-slate-300 transition-colors">{p.tag}</span>
                              </div>
                              <p className="text-[10px] text-slate-500 leading-normal line-clamp-2 italic">{p.description}</p>
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        <button
          onClick={handleRun}
          disabled={loading || (mode === 'form' && formErrors.length > 0)}
          className="px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm font-medium transition-colors text-white"
        >
          {loading ? 'Running…' : '▶ Run Backtest'}
        </button>
      </div>

      {/* Content */}
      {mode === 'json' ? (
        <textarea
          value={json}
          onChange={e => setJson(e.target.value)}
          className="flex-1 bg-transparent text-slate-300 text-xs p-4 resize-none outline-none min-h-[380px] font-mono leading-relaxed"
          spellCheck={false}
        />
      ) : (
        <StrategyForm state={formState} onChange={setFormState} />
      )}

      {/* Error / validation footer */}
      {(switchError || (mode === 'form' && formErrors.length > 0)) && (
        <div className="border-t border-slate-800 px-4 py-2 space-y-1 shrink-0">
          {switchError && (
            <p className="text-xs text-red-400">{switchError}</p>
          )}
          {mode === 'form' && formErrors.map((e, i) => (
            <p key={i} className="text-xs text-amber-400">⚠ {e}</p>
          ))}
        </div>
      )}
    </div>
  )
}
