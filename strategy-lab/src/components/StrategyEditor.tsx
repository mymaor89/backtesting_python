import { useState } from 'react'
import { StrategyForm } from './StrategyForm'
import {
  DEFAULT_FORM_STATE, formToStrategy, strategyToForm, validate,
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
    <div className="bg-slate-900 rounded-xl border border-slate-800 flex flex-col">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 shrink-0">
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
