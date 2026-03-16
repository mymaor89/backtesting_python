import { useState } from 'react'
import {
  EXCHANGES, EXCHANGE_SYMBOLS, FREQS, OPERATORS, OHLC_COLUMNS,
  TRANSFORMER_GROUPS, defaultArgs,
  type StrategyFormState, type Datapoint, type Rule, type Operator,
  type OrGroup, type RuleItem,
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
  tooltipTrigger: 'inline-flex items-center justify-center w-3.5 h-3.5 ml-1.5 rounded-full bg-slate-700 text-slate-400 text-[10px] cursor-help hover:bg-cyan-900/50 hover:text-cyan-400 transition-all font-bold italic',
  tooltipContent: 'absolute z-50 invisible group-hover:visible bg-slate-900 border border-slate-700 text-slate-300 text-[10px] p-2 rounded shadow-2xl w-48 -left-2 top-6 leading-relaxed pointer-events-none'
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

function Tooltip({ text }: { text: string }) {
  return (
    <span className="relative group inline-block">
      <span className={cls.tooltipTrigger}>i</span>
      <span className={cls.tooltipContent}>{text}</span>
    </span>
  )
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  state: StrategyFormState
  onChange: (s: StrategyFormState) => void
}

// ── Main component ────────────────────────────────────────────────────────────

export function StrategyForm({ state, onChange }: Props) {
  const { fieldErrors } = validate(state)

  const applyPreset = (preset: string) => {
    const end = new Date()
    const stop = end.toLocaleDateString('en-CA')
    let begin = new Date()

    switch (preset) {
      case '1mo': begin.setMonth(end.getMonth() - 1); break
      case '3mo': begin.setMonth(end.getMonth() - 3); break
      case '6mo': begin.setMonth(end.getMonth() - 6); break
      case '1y':  begin.setFullYear(end.getFullYear() - 1); break
      case 'Ytd': begin = new Date(end.getFullYear(), 0, 1); break
      case '2y':  begin.setFullYear(end.getFullYear() - 2); break
      case '5y':  begin.setFullYear(end.getFullYear() - 5); break
    }
    const start = begin.toLocaleDateString('en-CA')
    onChange({ ...state, start, stop })
  }

  const set = <K extends keyof StrategyFormState>(key: K, value: StrategyFormState[K]) =>
    onChange({ ...state, [key]: value })

  // When exchange changes, auto-correct symbol if format is incompatible
  const onExchangeChange = (exchange: string) => {
    let symbol = state.symbol
    const needsDash = exchange === 'coinbase'
    const hasDash   = symbol.includes('-')
    const isCrypto  = ['coinbase', 'binanceus', 'binancecom'].includes(exchange)
    // Reset to a known-good symbol when switching between crypto and yfinance
    if (!isCrypto || (needsDash && !hasDash) || (!needsDash && hasDash))
      symbol = EXCHANGE_SYMBOLS[exchange][0]
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
  const allOperands  = [...new Set([...OHLC_COLUMNS, ...dpNames])]

  const updateRule = (side: 'enter' | 'exit', i: number, patch: Partial<Rule>) => {
    const next = state[side].map((r, idx) => idx === i ? { ...r, ...patch } : r)
    set(side, next)
  }

  const addRule = (side: 'enter' | 'exit') =>
    set(side, [...state[side], { left: dpNames[0] ?? 'close', op: '<' as Operator, right: '0' }])

  const removeRule = (side: 'enter' | 'exit', i: number) =>
    set(side, state[side].filter((_, idx) => idx !== i))

  const updateOrSubRule = (side: 'enter' | 'exit', i: number, j: number, patch: Partial<Rule>) => {
    const next = state[side].map((item, idx): RuleItem => {
      if (idx !== i || !('or' in item)) return item
      return { or: item.or.map((sub, si) => si === j ? { ...sub, ...patch } : sub) }
    })
    set(side, next)
  }

  const addOrGroup = (side: 'enter' | 'exit') =>
    set(side, [...state[side], { or: [{ left: dpNames[0] ?? 'close', op: '<' as Operator, right: '0' }] }])

  const addOrSubRule = (side: 'enter' | 'exit', i: number) => {
    const next = state[side].map((item, idx): RuleItem => {
      if (idx !== i || !('or' in item)) return item
      return { or: [...item.or, { left: dpNames[0] ?? 'close', op: '<' as Operator, right: '0' }] }
    })
    set(side, next)
  }

  const removeOrSubRule = (side: 'enter' | 'exit', i: number, j: number) => {
    const next = state[side].map((item, idx): RuleItem => {
      if (idx !== i || !('or' in item)) return item
      return { or: item.or.filter((_, si) => si !== j) }
    })
    set(side, next)
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="p-2 sm:p-4 space-y-6 overflow-y-auto max-h-[85vh]">

      {/* ── Configuration ───────────────────────────────────────────────── */}
      <div>
        <SectionHeader>Configuration</SectionHeader>
        <div className="grid grid-cols-2 gap-3">

          {/* Exchange */}
          <div>
            <label className={cls.label}>
              Exchange
              <Tooltip text="The source of historical market data. yfinance is for stocks/ETFs, others for Crypto." />
            </label>
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
            <label className={cls.label}>
              Symbol
              <Tooltip text="The asset ticker. Use dash for Coinbase (BTC-USD) and no dash for Binance (BTCUSDT)." />
            </label>
            <input
              list="symbol-suggestions"
              value={state.symbol}
              onChange={e => set('symbol', e.target.value.toUpperCase())}
              className={fieldCls(!!fieldErrors.symbol)}
              placeholder={state.exchange === 'coinbase' ? 'BTC-USD' : state.exchange === 'yfinance' ? 'SPY' : 'BTCUSDT'}
            />
            <datalist id="symbol-suggestions">
              {(EXCHANGE_SYMBOLS[state.exchange] ?? []).map(s => <option key={s} value={s} />)}
            </datalist>
            <FieldError msg={fieldErrors.symbol} />
          </div>

          {/* Frequency */}
          <div>
            <label className={cls.label}>
              Frequency
              <Tooltip text="The interval of each candle. Lower timeframes provide more noise, higher provide more signal." />
            </label>
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
            <label className={cls.label}>
              Base Balance ($)
              <Tooltip text="Your starting theoretical capital in USD for this backtest." />
            </label>
            <input
              type="number" min="1" step="100"
              value={state.base_balance}
              onChange={e => set('base_balance', Number(e.target.value))}
              className={fieldCls(!!fieldErrors.base_balance)}
            />
            <FieldError msg={fieldErrors.base_balance} />
          </div>

          {/* Presets */}
          <div className="col-span-2 flex items-center gap-2 -mb-1">
            <span className={cls.label + " mb-0"}>
              Date Presets:
              <Tooltip text="Quickly select common historical timeframes." />
            </span>
            <div className="flex flex-wrap gap-1.5">
              {['1mo', '3mo', '6mo', '1y', 'Ytd', '2y', '5y'].map(p => (
                <button
                  key={p}
                  type="button"
                  onClick={() => applyPreset(p)}
                  className="px-2 py-0.5 text-[10px] bg-slate-700 hover:bg-slate-600 active:bg-cyan-900 text-slate-300 rounded border border-slate-600 transition-colors"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Start */}
          <div>
            <label className={cls.label}>
              Start Date
              <Tooltip text="When to begin the historical simulation." />
            </label>
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
            <label className={cls.label}>
              Stop Date
              <Tooltip text="When to end the historical simulation." />
            </label>
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
            <label className={cls.label}>
              Commission (0–1, e.g. 0.001 = 0.1%)
              <Tooltip text="Fee paid to the exchange for every executed buy and sell order." />
            </label>
            <input
              type="number" min="0" max="1" step="0.0001"
              value={state.comission}
              onChange={e => set('comission', Number(e.target.value))}
              className={fieldCls(!!fieldErrors.comission)}
            />
            <FieldError msg={fieldErrors.comission} />
          </div>

          <div className="lg:col-span-2">
            <label className="flex items-center gap-2 cursor-pointer group">
              <input
                type="checkbox"
                className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-cyan-600 focus:ring-cyan-600 focus:ring-offset-slate-900"
                checked={state.risk_enabled}
                onChange={e => set('risk_enabled', e.target.checked)}
              />
              <span className="text-xs font-semibold text-slate-400 group-hover:text-slate-200 transition-colors uppercase tracking-wider">
                Enable Risk Management (SL / TP)
              </span>
              <Tooltip text="Safeguard your account with automated exit strategies based on percentage loss or gain." />
            </label>
          </div>

          {state.risk_enabled && (
            <>
              {/* Stop Loss */}
              <div>
                <label className={cls.label}>
                  Stop Loss %
                  <Tooltip text="Close position if price drops this % below entry to prevent further losses." />
                </label>
                <input
                  type="number" min="0" max="100" step="1"
                  value={state.stop_loss}
                  onChange={e => set('stop_loss', Number(e.target.value))}
                  className={fieldCls(!!fieldErrors.stop_loss)}
                  placeholder="0"
                />
                <FieldError msg={fieldErrors.stop_loss} />
              </div>

              {/* Take Profit */}
              <div>
                <label className={cls.label}>
                  Take Profit %
                  <Tooltip text="Close position once profit reaches this % to lock in gains." />
                </label>
                <input
                  type="number" min="0" max="1000" step="1"
                  value={state.take_profit}
                  onChange={e => set('take_profit', Number(e.target.value))}
                  className={fieldCls(!!fieldErrors.take_profit)}
                  placeholder="0"
                />
                <FieldError msg={fieldErrors.take_profit} />
              </div>

              {/* Trailing Stop Loss */}
              <div>
                <label className={cls.label}>
                  Trailing Stop %
                  <Tooltip text="A floating stop loss that follows price upwards but never moves down. Great for trend following." />
                </label>
                <input
                  type="number" min="0" max="100" step="1"
                  value={state.trailing_stop_loss}
                  onChange={e => set('trailing_stop_loss', Number(e.target.value))}
                  className={fieldCls(!!fieldErrors.trailing_stop_loss)}
                  placeholder="0"
                />
                <FieldError msg={fieldErrors.trailing_stop_loss} />
              </div>
            </>
          )}
          
          {/* Leverage */}
          <div>
            <label className={cls.label}>
              Leverage (1–100x)
              <Tooltip text="Magnifies position size by borrowing funds. Higher leverage increases profit potential but raises liquidation risk." />
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range" min="1" max="50" step="1"
                value={state.leverage}
                onChange={e => set('leverage', Number(e.target.value))}
                className="flex-1 accent-cyan-600 h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer"
              />
              <input
                type="number" min="1" max="100"
                value={state.leverage}
                onChange={e => set('leverage', Number(e.target.value))}
                className="w-16 bg-slate-800 border border-slate-700 text-slate-200 rounded px-2 py-1 text-xs focus:outline-none focus:border-cyan-600"
              />
            </div>
            <FieldError msg={fieldErrors.leverage} />
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
                  <label className={cls.label}>
                    Name
                    <Tooltip text="Unique identifier for this indicator to use in your rules." />
                  </label>
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
                  <label className={cls.label}>
                    Transformer
                    <Tooltip text="The technical analysis formula used to process price data (e.g. RSI, EMA, BBands)." />
                  </label>
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
            <Tooltip text={side === 'enter' ? "Conditions that trigger buying a long position or opening a short." : "Conditions that trigger selling a long or closing a short."} />
          </SectionHeader>

          <div className="space-y-2">
            {state[side].map((item, i) => (
              'or' in item ? (
                // ── OR group ──────────────────────────────────────────
                <div key={i} className="border border-amber-900/50 rounded-lg p-3 space-y-2 bg-amber-950/10">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-amber-500 px-1.5 py-0.5 rounded bg-amber-900/30">OR</span>
                    <button onClick={() => removeRule(side, i)} className={cls.delBtn} title="Remove OR group">×</button>
                  </div>
                  {item.or.map((sub, j) => (
                    <div key={j} className="flex items-start gap-2 pl-2">
                      {/* Left */}
                      <div className="flex-1 min-w-0">
                        <select
                          value={sub.left}
                          onChange={e => updateOrSubRule(side, i, j, { left: e.target.value })}
                          className={fieldErrors[`${side}_or${i}_left_${j}`] ? cls.error : cls.select}
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
                        <FieldError msg={fieldErrors[`${side}_or${i}_left_${j}`]} />
                      </div>
                      {/* Op */}
                      <div className="w-20 shrink-0">
                        <select value={sub.op} onChange={e => updateOrSubRule(side, i, j, { op: e.target.value as Operator })} className={cls.select}>
                          {OPERATORS.map(op => <option key={op} value={op}>{op}</option>)}
                        </select>
                      </div>
                      {/* Right */}
                      <div className="flex-1 min-w-0">
                        <input
                          list={`right-${side}-or${i}-${j}`}
                          value={sub.right}
                          onChange={e => updateOrSubRule(side, i, j, { right: e.target.value })}
                          placeholder="value or indicator"
                          className={fieldCls(!!fieldErrors[`${side}_or${i}_right_${j}`])}
                        />
                        <datalist id={`right-${side}-or${i}-${j}`}>
                          {allOperands.map(n => <option key={n} value={n} />)}
                          {['0','10','20','30','50','70','80','100'].map(v => <option key={v} value={v} />)}
                        </datalist>
                        <FieldError msg={fieldErrors[`${side}_or${i}_right_${j}`]} />
                      </div>
                      {/* Delete sub-rule */}
                      <button onClick={() => removeOrSubRule(side, i, j)} className={cls.delBtn} title="Remove condition">×</button>
                    </div>
                  ))}
                  <button onClick={() => addOrSubRule(side, i)} className={`${cls.addBtn} pl-2 text-amber-500 hover:text-amber-400`}>
                    <span>+</span> Add condition
                  </button>
                </div>
              ) : (
                // ── Plain rule ────────────────────────────────────────
                <div key={i} className="flex items-start gap-2">
                  {/* Left operand */}
                  <div className="flex-1 min-w-0">
                    {i === 0 && <label className={cls.label}>Left</label>}
                    <select
                      value={item.left}
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
                      value={item.op}
                      onChange={e => updateRule(side, i, { op: e.target.value as Operator })}
                      className={cls.select}
                    >
                      {OPERATORS.map(op => <option key={op} value={op}>{op}</option>)}
                    </select>
                  </div>
                  {/* Right operand */}
                  <div className="flex-1 min-w-0">
                    {i === 0 && <label className={cls.label}>Right (value or indicator)</label>}
                    <input
                      list={`right-${side}-${i}`}
                      value={item.right}
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
                    <button onClick={() => removeRule(side, i)} className={cls.delBtn} title="Remove rule">×</button>
                  </div>
                </div>
              )
            ))}
          </div>

          <div className="flex gap-3 mt-2">
            <button onClick={() => addRule(side)} className={cls.addBtn}>
              <span>+</span> Add Rule
            </button>
            <button onClick={() => addOrGroup(side)} className={`${cls.addBtn} text-amber-500 hover:text-amber-400`}>
              <span>+</span> Add OR Group
            </button>
          </div>
        </div>
      ))}

    </div>
  )
}
