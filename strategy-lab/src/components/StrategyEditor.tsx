import { useState } from 'react'
import { StrategyForm } from './StrategyForm'
import {
  DEFAULT_FORM_STATE, PRESET_STRATEGIES, formToStrategy, strategyToForm, validate,
  type StrategyFormState, type Preset,
} from '../lib/strategy'
import { usePresets, type SavedPreset, type PresetPayload } from '../hooks/usePresets'

const DEFAULT_JSON = JSON.stringify(formToStrategy(DEFAULT_FORM_STATE), null, 2)

type Mode = 'json' | 'form'

interface Props {
  onRun: (strategy: Record<string, unknown>) => void
  loading: boolean
}

// Convert a SavedPreset (from DB) to the same shape as a built-in Preset
function savedToPreset(s: SavedPreset): Preset & { savedId: number } {
  return {
    savedId: s.id,
    name: s.name,
    tag: s.tag,
    category: s.category,
    description: s.description,
    state: strategyToForm(s.state),
  }
}

export function StrategyEditor({ onRun, loading }: Props) {
  const [mode, setMode]           = useState<Mode>('form')
  const [json, setJson]           = useState(DEFAULT_JSON)
  const [formState, setFormState] = useState<StrategyFormState>(DEFAULT_FORM_STATE)
  const [switchError, setSwitchError] = useState<string | null>(null)

  const { presets: savedPresets, savePreset, updatePreset, deletePreset } = usePresets()

  // ── Save preset modal state ─────────────────────────────────────────────────

  const [showSaveModal, setShowSaveModal] = useState(false)
  const [editingPreset, setEditingPreset] = useState<(SavedPreset & { savedId?: number }) | null>(null)
  const [saveForm, setSaveForm] = useState({ name: '', tag: '', category: 'Custom', description: '' })
  const [saveError, setSaveError] = useState<string | null>(null)
  const [activePresetId, setActivePresetId] = useState<number | null>(null)
  const [showSaveMenu, setShowSaveMenu] = useState(false)

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

  // ── Current form state helper ─────────────────────────────────────────────

  const getCurrentState = (): StrategyFormState => {
    if (mode === 'json') {
      try { return strategyToForm(JSON.parse(json)) } catch { return formState }
    }
    return formState
  }

  // ── Preset loader ───────────────────────────────────────────────────────────

  const [showPresets, setShowPresets] = useState(false)

  // Merge built-in and saved presets
  const builtInPresets = PRESET_STRATEGIES.map(p => ({ ...p, savedId: undefined as number | undefined }))
  const dbPresets = savedPresets.map(savedToPreset)
  const allPresets = [...dbPresets, ...builtInPresets]
  const categories = [...new Set(allPresets.map(p => p.category))]

  const applyPreset = (preset: Preset & { savedId?: number }) => {
    setFormState(preset.state)
    setJson(JSON.stringify(formToStrategy(preset.state), null, 2))
    setSwitchError(null)
    setShowPresets(false)
    setActivePresetId(preset.savedId ?? null)
  }

  // ── Save / Edit / Delete ──────────────────────────────────────────────────

  const activePreset = activePresetId != null ? savedPresets.find(p => p.id === activePresetId) : null

  const openSaveNew = () => {
    setEditingPreset(null)
    setSaveForm({ name: '', tag: '', category: 'Custom', description: '' })
    setSaveError(null)
    setShowSaveModal(true)
    setShowSaveMenu(false)
  }

  const handleSaveToExisting = async () => {
    if (!activePreset) return
    setShowSaveMenu(false)
    const currentState = getCurrentState()
    const payload: PresetPayload = {
      name: activePreset.name,
      tag: activePreset.tag,
      category: activePreset.category,
      description: activePreset.description,
      state: formToStrategy(currentState) as Record<string, unknown>,
    }
    const result = await updatePreset(activePreset.id, payload)
    if (!result) {
      setSwitchError('Failed to update preset')
    }
  }

  const openEditPreset = (p: SavedPreset & { savedId?: number }, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingPreset(p)
    setSaveForm({ name: p.name, tag: p.tag, category: p.category, description: p.description })
    setSaveError(null)
    setShowSaveModal(true)
  }

  const handleSave = async () => {
    if (!saveForm.name.trim()) {
      setSaveError('Name is required')
      return
    }
    const currentState = getCurrentState()
    const payload: PresetPayload = {
      ...saveForm,
      state: formToStrategy(currentState) as Record<string, unknown>,
    }
    let result
    if (editingPreset) {
      result = await updatePreset(editingPreset.id, payload)
    } else {
      result = await savePreset(payload)
    }
    if (result) {
      setShowSaveModal(false)
      setSaveError(null)
    } else {
      setSaveError('Failed to save. Name may already exist.')
    }
  }

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete this preset?')) return
    await deletePreset(id)
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
                {m === 'json' ? '{ } JSON' : '\u229E Form'}
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
              <span>Presets</span>
              <span className={`text-[10px] transition-transform ${showPresets ? 'rotate-180' : ''}`}>{'\u25BC'}</span>
            </button>

            {showPresets && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setShowPresets(false)} />
                <div className="absolute left-0 mt-2 w-[520px] bg-slate-800 border border-slate-700 rounded-lg shadow-2xl z-20 overflow-hidden max-h-[500px] flex flex-col">
                  {/* Preset panel content */}
                  <div className="flex flex-1 overflow-hidden">
                    {/* Left Sidebar: Categories */}
                    <div className="w-1/3 bg-slate-900/50 border-r border-slate-700 p-2 space-y-1 overflow-y-auto">
                      <p className="px-2 py-1 text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-1">Categories</p>
                      {categories.map(cat => (
                        <div key={cat} className="group">
                          <p className="px-2 py-1.5 text-xs text-slate-400 font-medium">{cat}</p>
                          <div className="pl-2 space-y-0.5 mt-0.5">
                            {allPresets.filter(p => p.category === cat).map(p => (
                              <button
                                key={p.savedId ? `db-${p.savedId}` : `builtin-${p.name}`}
                                onClick={() => applyPreset(p)}
                                className="w-full text-left px-2 py-1 rounded text-[11px] text-slate-500 hover:text-cyan-400 hover:bg-slate-700/50 transition-colors truncate"
                              >
                                {p.savedId != null && <span className="text-emerald-500 mr-1">*</span>}
                                {p.name}
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
                            {allPresets.filter(p => p.category === cat).map(p => (
                              <button
                                key={p.savedId ? `db-${p.savedId}` : `builtin-${p.name}`}
                                onClick={() => applyPreset(p)}
                                className="group text-left p-2.5 rounded-lg border border-slate-700 hover:border-cyan-500/50 hover:bg-slate-700/30 transition-all relative"
                              >
                                <div className="flex items-center justify-between mb-1">
                                  <div className="flex items-center gap-1.5">
                                    {p.savedId != null && <span className="text-[9px] px-1 py-0.5 rounded bg-emerald-900/40 text-emerald-400 font-mono leading-none">saved</span>}
                                    <span className="text-xs font-bold text-slate-200 group-hover:text-cyan-400 tracking-tight transition-colors">{p.name}</span>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-900 text-slate-500 font-mono leading-none group-hover:text-slate-300 transition-colors">{p.tag}</span>
                                    {p.savedId != null && (
                                      <>
                                        <span
                                          onClick={(e) => {
                                            const sp = savedPresets.find(s => s.id === p.savedId)
                                            if (sp) openEditPreset(sp as SavedPreset & { savedId?: number }, e)
                                          }}
                                          className="text-[10px] text-slate-600 hover:text-cyan-400 cursor-pointer px-1"
                                          title="Edit preset"
                                        >edit</span>
                                        <span
                                          onClick={(e) => handleDelete(p.savedId!, e)}
                                          className="text-[10px] text-slate-600 hover:text-red-400 cursor-pointer px-1"
                                          title="Delete preset"
                                        >del</span>
                                      </>
                                    )}
                                  </div>
                                </div>
                                <p className="text-[10px] text-slate-500 leading-normal line-clamp-2 italic">{p.description}</p>
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Bottom bar */}
                  <div className="border-t border-slate-700 px-3 py-2 flex items-center justify-between bg-slate-900/30">
                    <span className="text-[10px] text-slate-600">
                      {savedPresets.length} saved / {PRESET_STRATEGIES.length} built-in
                    </span>
                    <button
                      onClick={() => { setShowPresets(false); openSaveNew() }}
                      className="text-xs text-cyan-400 hover:text-cyan-300 font-medium transition-colors"
                    >
                      + Save Current as Preset
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Save button in header */}
          <div className="relative">
            {activePreset ? (
              <>
                <button
                  onClick={() => setShowSaveMenu(!showSaveMenu)}
                  className="px-3 py-1 rounded text-xs font-medium text-slate-400 border border-slate-700 hover:border-emerald-600 hover:text-emerald-400 transition-colors flex items-center gap-1.5"
                >
                  <span>Save Preset</span>
                  <span className={`text-[10px] transition-transform ${showSaveMenu ? 'rotate-180' : ''}`}>{'\u25BC'}</span>
                </button>
                {showSaveMenu && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setShowSaveMenu(false)} />
                    <div className="absolute left-0 mt-1 w-[200px] bg-slate-800 border border-slate-700 rounded-lg shadow-2xl z-20 overflow-hidden">
                      <button
                        onClick={handleSaveToExisting}
                        className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 hover:text-emerald-400 transition-colors"
                      >
                        Save to "{activePreset.name}"
                      </button>
                      <button
                        onClick={openSaveNew}
                        className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 hover:text-cyan-400 transition-colors border-t border-slate-700"
                      >
                        Save as New Preset
                      </button>
                    </div>
                  </>
                )}
              </>
            ) : (
              <button
                onClick={openSaveNew}
                className="px-3 py-1 rounded text-xs font-medium text-slate-400 border border-slate-700 hover:border-emerald-600 hover:text-emerald-400 transition-colors"
              >
                Save Preset
              </button>
            )}
          </div>
        </div>

        <button
          onClick={handleRun}
          disabled={loading || (mode === 'form' && formErrors.length > 0)}
          className="px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm font-medium transition-colors text-white"
        >
          {loading ? 'Running\u2026' : '\u25B6 Run Backtest'}
        </button>
      </div>

      {/* Content */}
      {mode === 'json' ? (
        <textarea
          value={json}
          onChange={e => setJson(e.target.value)}
          className="flex-1 bg-transparent text-slate-300 text-xs p-4 resize-none outline-none min-h-[60vh] font-mono leading-relaxed"
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
            <p key={i} className="text-xs text-amber-400">{'\u26A0'} {e}</p>
          ))}
        </div>
      )}

      {/* Save / Edit Preset Modal */}
      {showSaveModal && (
        <>
          <div className="fixed inset-0 bg-black/50 z-30" onClick={() => setShowSaveModal(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-40 w-[420px] bg-slate-800 border border-slate-700 rounded-xl shadow-2xl p-5 space-y-4">
            <h3 className="text-sm font-bold text-slate-200">
              {editingPreset ? 'Edit Preset' : 'Save as Preset'}
            </h3>

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Name *</label>
                <input
                  value={saveForm.name}
                  onChange={e => setSaveForm({ ...saveForm, name: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-700 text-slate-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-600"
                  placeholder="e.g. My RSI Strategy"
                  autoFocus
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-500 mb-1">Tag</label>
                  <input
                    value={saveForm.tag}
                    onChange={e => setSaveForm({ ...saveForm, tag: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 text-slate-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-600"
                    placeholder="e.g. Trend"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">Category</label>
                  <input
                    value={saveForm.category}
                    onChange={e => setSaveForm({ ...saveForm, category: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 text-slate-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-600"
                    placeholder="e.g. Mean Reversion"
                    list="category-suggestions"
                  />
                  <datalist id="category-suggestions">
                    {['Trend Following', 'Mean Reversion', 'Volatility', 'Momentum', 'Breakout', 'Scalping', 'Advanced', 'Custom'].map(c =>
                      <option key={c} value={c} />
                    )}
                  </datalist>
                </div>
              </div>

              <div>
                <label className="block text-xs text-slate-500 mb-1">Description</label>
                <textarea
                  value={saveForm.description}
                  onChange={e => setSaveForm({ ...saveForm, description: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-700 text-slate-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-600 resize-none h-16"
                  placeholder="Brief description of the strategy..."
                />
              </div>
            </div>

            {!editingPreset && (
              <p className="text-[10px] text-slate-600">
                The current strategy configuration will be saved with this preset.
              </p>
            )}

            {saveError && <p className="text-xs text-red-400">{saveError}</p>}

            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowSaveModal(false)}
                className="px-4 py-1.5 text-sm text-slate-400 hover:text-slate-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded transition-colors"
              >
                {editingPreset ? 'Update' : 'Save'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
