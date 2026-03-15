import {
  EXCHANGES, EXCHANGE_SYMBOLS, FREQS, OPERATORS, OHLC_COLUMNS,
  TRANSFORMER_GROUPS, defaultArgs,
  type StrategyFormState, type Datapoint, type Rule, type Operator,
  validate,
} from '../lib/strategy'

// ── Shared input style helpers ────────────────────────────────────────────────

const cls = {
  input:  'bg-slate-800 border border-slate-700 text-slate-200 rounded px-2 py-1.5 text-sm w-full focus:outline-none focus:border-cyan-600 transition-colors',
  error:  'bg-slate-800 border border-red-500 text-slate-200 rounded px-2 py-1.5 text-sm w-full focus:outline-none focus:border-red-400 transition-colors',
  select: 'bg-slate-800 border border-slate-700 text-slate-200 rounded px-2 py-1.5 text-sm w-full focus:outline-none focus:border-cyan-600 transition-colors appearance-none cursor-pointer',
  label:  'block text-xs text-slate-500 mb-1',
  section:'text-xs text-slate-500 uppercase tracking-wider font-semibold mb-3',
  addBtn: 'text-xs text-cyan-400 hover:text-cyan-300 transition-colors flex items-center gap-1',
  delBtn: 'text-slate-600 hover:text-red-400 transition-colors text-lg leading-none px-1',
}

function fieldCls(hasError: boolean) {
  return hasError ? cls.error : cls.input
}

// ── Sub-components ────────────────────────────────────────────────────────────

function FieldError({ msg }: { msg?: string }) {
  if (!msg) return null
  return <p className="text-xs text-red-400 mt-1">{msg}</p>
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return <p className={cls.section}>{children}</p>
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  state: StrategyFormState
  onChange: (s: StrategyFormState) => void
}

// ── Main component ────────────────────────────────────────────────────────────

export function StrategyForm({ state, onChange }: Props) {
  const { fieldErrors } = validate(state)

  const set = <K extends keyof StrategyFormState>(key: K, value: StrategyFormState[K]) =>
    onChange({ ...state, [key]: value })

  // When exchange changes, auto-correct symbol if format is incompatible
  const onExchangeChange = (exchange: string) => {
    let symbol = state.symbol
    const needsDash    = exchange === 'coinbase'
    const hasDash      = symbol.includes('-')
    if (needsDash && !hasDash) symbol = EXCHANGE_SYMBOLS[exchange][0]
    if (!needsDash && hasDash) symbol = EXCHANGE_SYMBOLS[exchange][0]
    onChange({ ...state, exchange, symbol })
  }

  // ── Datapoints ─────────────────────────────────────────────────────────────

  const updateDp = (i: number, patch: Partial<Datapoint>) => {
    const next = state.datapoints.map((dp, idx) => idx === i ? { ...dp, ...patch } : dp)
    set('datapoints', next)
  }

  const onTransformerChange = (i: number, transformer: string) => {
    updateDp(i, { transformer, args: defaultArgs(transformer) })
  }

  const addDp = () =>
    set('datapoints', [...state.datapoints, { name: '', transformer: 'rsi', args: [14] }])

  const removeDp = (i: number) =>
    set('datapoints', state.datapoints.filter((_, idx) => idx !== i))

  const updateArg = (dpIdx: number, argIdx: number, val: string) => {
    const args = [...state.datapoints[dpIdx].args]
    args[argIdx] = Number(val)
    updateDp(dpIdx, { args })
  }

  const addArg    = (i: number) => updateDp(i, { args: [...state.datapoints[i].args, 1] })
  const removeArg = (i: number, argIdx: number) =>
    updateDp(i, { args: state.datapoints[i].args.filter((_, idx) => idx !== argIdx) })

  // ── Rules ──────────────────────────────────────────────────────────────────

  const dpNames      = state.datapoints.map(d => d.name).filter(Boolean)
  const allOperands  = [...OHLC_COLUMNS, ...dpNames]

  const updateRule = (side: 'enter' | 'exit', i: number, patch: Partial<Rule>) => {
    const next = state[side].map((r, idx) => idx === i ? { ...r, ...patch } : r)
    set(side, next)
  }

  const addRule = (side: 'enter' | 'exit') =>
    set(side, [...state[side], { left: dpNames[0] ?? 'close', op: '<', right: '0' }])

  const removeRule = (side: 'enter' | 'exit', i: number) =>
    set(side, state[side].filter((_, idx) => idx !== i))

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="p-4 space-y-6 overflow-y-auto max-h-[620px]">

      {/* ── Configuration ───────────────────────────────────────────────── */}
      <div>
        <SectionHeader>Configuration</SectionHeader>
        <div className="grid grid-cols-2 gap-3">

          {/* Exchange */}
          <div>
            <label className={cls.label}>Exchange</label>
            <select
              value={state.exchange}
              onChange={e => onExchangeChange(e.target.value)}
              className={fieldErrors.exchange ? cls.error : cls.select}
            >
              {EXCHANGES.map(ex => <option key={ex} value={ex}>{ex}</option>)}
            </select>
            <FieldError msg={fieldErrors.exchange} />
          </div>

          {/* Symbol */}
          <div>
            <label className={cls.label}>Symbol</label>
            <input
              list="symbol-suggestions"
              value={state.symbol}
              onChange={e => set('symbol', e.target.value.toUpperCase())}
              className={fieldCls(!!fieldErrors.symbol)}
              placeholder={state.exchange === 'coinbase' ? 'BTC-USD' : 'BTCUSDT'}
            />
            <datalist id="symbol-suggestions">
              {(EXCHANGE_SYMBOLS[state.exchange] ?? []).map(s => <option key={s} value={s} />)}
            </datalist>
            <FieldError msg={fieldErrors.symbol} />
          </div>

          {/* Frequency */}
          <div>
            <label className={cls.label}>Frequency</label>
            <select
              value={state.freq}
              onChange={e => set('freq', e.target.value)}
              className={cls.select}
            >
              {FREQS.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>

          {/* Base balance */}
          <div>
            <label className={cls.label}>Base Balance ($)</label>
            <input
              type="number" min="1" step="100"
              value={state.base_balance}
              onChange={e => set('base_balance', Number(e.target.value))}
              className={fieldCls(!!fieldErrors.base_balance)}
            />
            <FieldError msg={fieldErrors.base_balance} />
          </div>

          {/* Start */}
          <div>
            <label className={cls.label}>Start Date</label>
            <input
              type="date"
              value={state.start}
              onChange={e => set('start', e.target.value)}
              className={fieldCls(!!fieldErrors.start)}
            />
            <FieldError msg={fieldErrors.start} />
          </div>

          {/* Stop */}
          <div>
            <label className={cls.label}>Stop Date</label>
            <input
              type="date"
              value={state.stop}
              onChange={e => set('stop', e.target.value)}
              className={fieldCls(!!fieldErrors.stop)}
            />
            <FieldError msg={fieldErrors.stop} />
          </div>

          {/* Commission */}
          <div className="col-span-2 sm:col-span-1">
            <label className={cls.label}>Commission (0–1, e.g. 0.001 = 0.1%)</label>
            <input
              type="number" min="0" max="1" step="0.0001"
              value={state.comission}
              onChange={e => set('comission', Number(e.target.value))}
              className={fieldCls(!!fieldErrors.comission)}
            />
            <FieldError msg={fieldErrors.comission} />
          </div>

        </div>
      </div>

      {/* ── Indicators ──────────────────────────────────────────────────── */}
      <div>
        <SectionHeader>Indicators</SectionHeader>

        <div className="space-y-2">
          {state.datapoints.map((dp, i) => (
            <div key={i} className="bg-slate-800/50 rounded-lg p-3 space-y-2">
              <div className="flex items-start gap-2">

                {/* Name */}
                <div className="flex-1 min-w-0">
                  <label className={cls.label}>Name</label>
                  <input
                    value={dp.name}
                    onChange={e => updateDp(i, { name: e.target.value.replace(/\s/g, '_') })}
                    placeholder="e.g. my_rsi"
                    className={fieldCls(!!fieldErrors[`dp_name_${i}`])}
                  />
                  <FieldError msg={fieldErrors[`dp_name_${i}`]} />
                </div>

                {/* Transformer */}
                <div className="flex-1 min-w-0">
                  <label className={cls.label}>Transformer</label>
                  <select
                    value={dp.transformer}
                    onChange={e => onTransformerChange(i, e.target.value)}
                    className={fieldErrors[`dp_transformer_${i}`] ? cls.error : cls.select}
                  >
                    {TRANSFORMER_GROUPS.map(g => (
                      <optgroup key={g.label} label={g.label}>
                        {g.options.map(t => <option key={t} value={t}>{t}</option>)}
                      </optgroup>
                    ))}
                  </select>
                </div>

                {/* Delete indicator */}
                <div className="pt-5">
                  <button
                    onClick={() => removeDp(i)}
                    className={cls.delBtn}
                    title="Remove indicator"
                  >×</button>
                </div>
              </div>

              {/* Args */}
              <div>
                <label className={cls.label}>
                  Args
                  <span className="text-slate-600 ml-1">(period, std dev, etc.)</span>
                </label>
                <div className="flex flex-wrap items-center gap-1.5">
                  {dp.args.map((arg, ai) => (
                    <div key={ai} className="flex items-center gap-0.5">
                      <input
                        type="number"
                        value={arg}
                        onChange={e => updateArg(i, ai, e.target.value)}
                        className="w-16 bg-slate-800 border border-slate-700 text-slate-200 rounded px-2 py-1 text-xs focus:outline-none focus:border-cyan-600"
                      />
                      {dp.args.length > 1 && (
                        <button
                          onClick={() => removeArg(i, ai)}
                          className="text-slate-600 hover:text-red-400 text-xs px-0.5"
                          title="Remove arg"
                        >×</button>
                      )}
                    </div>
                  ))}
                  <button
                    onClick={() => addArg(i)}
                    className="text-xs text-slate-500 hover:text-cyan-400 border border-slate-700 hover:border-cyan-600 rounded px-2 py-1 transition-colors"
                    title="Add arg"
                  >+ arg</button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <button onClick={addDp} className={`${cls.addBtn} mt-2`}>
          <span>+</span> Add Indicator
        </button>
      </div>

      {/* ── Rule builder ────────────────────────────────────────────────── */}
      {(['enter', 'exit'] as const).map(side => (
        <div key={side}>
          <SectionHeader>
            {side === 'enter' ? '▶ Enter Rules' : '◀ Exit Rules'}
            <span className="normal-case font-normal text-slate-600 ml-1">(all must be true)</span>
          </SectionHeader>

          <div className="space-y-2">
            {state[side].map((rule, i) => (
              <div key={i} className="flex items-start gap-2">

                {/* Left operand */}
                <div className="flex-1 min-w-0">
                  {i === 0 && <label className={cls.label}>Left</label>}
                  <select
                    value={rule.left}
                    onChange={e => updateRule(side, i, { left: e.target.value })}
                    className={fieldErrors[`${side}_left_${i}`] ? cls.error : cls.select}
                  >
                    <optgroup label="OHLC">
                      {OHLC_COLUMNS.map(c => <option key={c} value={c}>{c}</option>)}
                    </optgroup>
                    {dpNames.length > 0 && (
                      <optgroup label="Indicators">
                        {dpNames.map(n => <option key={n} value={n}>{n}</option>)}
                      </optgroup>
                    )}
                  </select>
                  <FieldError msg={fieldErrors[`${side}_left_${i}`]} />
                </div>

                {/* Operator */}
                <div className="w-20 shrink-0">
                  {i === 0 && <label className={cls.label}>Op</label>}
                  <select
                    value={rule.op}
                    onChange={e => updateRule(side, i, { op: e.target.value as Operator })}
                    className={cls.select}
                  >
                    {OPERATORS.map(op => <option key={op} value={op}>{op}</option>)}
                  </select>
                </div>

                {/* Right operand — indicator or numeric value */}
                <div className="flex-1 min-w-0">
                  {i === 0 && <label className={cls.label}>Right (value or indicator)</label>}
                  <input
                    list={`right-${side}-${i}`}
                    value={rule.right}
                    onChange={e => updateRule(side, i, { right: e.target.value })}
                    placeholder="30 or indicator name"
                    className={fieldCls(!!fieldErrors[`${side}_right_${i}`])}
                  />
                  <datalist id={`right-${side}-${i}`}>
                    {allOperands.map(n => <option key={n} value={n} />)}
                    {['0', '10', '20', '30', '50', '70', '80', '100'].map(v =>
                      <option key={v} value={v} />
                    )}
                  </datalist>
                  <FieldError msg={fieldErrors[`${side}_right_${i}`]} />
                </div>

                {/* Delete rule */}
                <div className={i === 0 ? 'pt-5' : 'pt-0'}>
                  <button
                    onClick={() => removeRule(side, i)}
                    className={cls.delBtn}
                    title="Remove rule"
                  >×</button>
                </div>
              </div>
            ))}
          </div>

          <button onClick={() => addRule(side)} className={`${cls.addBtn} mt-2`}>
            <span>+</span> Add Rule
          </button>
        </div>
      ))}

    </div>
  )
}
