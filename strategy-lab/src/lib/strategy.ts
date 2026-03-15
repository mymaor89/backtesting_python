// ── Types ─────────────────────────────────────────────────────────────────────

export type Operator = '<' | '>' | '=' | '!=' | '>=' | '<='

export interface Datapoint {
  name: string
  transformer: string
  args: number[]
}

export interface Rule {
  left: string
  op: Operator
  right: string  // indicator name OR numeric string
}

export interface StrategyFormState {
  exchange: string
  symbol: string
  freq: string
  start: string
  stop: string
  base_balance: number
  comission: number
  datapoints: Datapoint[]
  enter: Rule[]
  exit: Rule[]
}

// ── Constants ─────────────────────────────────────────────────────────────────

export const EXCHANGES = ['coinbase', 'binanceus', 'binancecom'] as const

export const EXCHANGE_SYMBOLS: Record<string, string[]> = {
  coinbase:   ['BTC-USD', 'ETH-USD', 'SOL-USD', 'DOGE-USD', 'XRP-USD', 'ADA-USD', 'AVAX-USD', 'LINK-USD', 'MATIC-USD'],
  binanceus:  ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT', 'XRPUSDT', 'BNBUSDT', 'ADAUSDT', 'AVAXUSDT', 'MATICUSDT'],
  binancecom: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT', 'XRPUSDT', 'BNBUSDT', 'ADAUSDT', 'AVAXUSDT', 'MATICUSDT'],
}

export const FREQS = ['1Min', '5Min', '15Min', '30Min', '1h', '4h', '8h', '12h', '1D'] as const

export const OPERATORS: Operator[] = ['<', '>', '=', '!=', '>=', '<=']

export const OHLC_COLUMNS = ['close', 'open', 'high', 'low'] as const

export const TRANSFORMER_GROUPS = [
  {
    label: 'Moving Averages',
    options: ['dema', 'ema', 'evwma', 'hma', 'kama', 'sma', 'smm', 'smma', 'ssma', 'tema', 'trima', 'vama', 'vwap', 'wma', 'zlema'],
  },
  {
    label: 'Oscillators',
    options: ['adx', 'ao', 'cci', 'cmo', 'er', 'ift_rsi', 'macd', 'mi', 'mfi', 'mom', 'ppo', 'roc', 'rsi', 'stoch', 'stochd', 'stochrsi', 'tsi', 'uo', 'williams'],
  },
  {
    label: 'Volatility',
    options: ['apz', 'atr', 'bbands', 'bbwidth', 'do', 'kc', 'percent_b', 'sar', 'sqzmi', 'tr'],
  },
  {
    label: 'Volume',
    options: ['adl', 'chaikin', 'cfi', 'efi', 'emv', 'fve', 'msd', 'obv', 'pzo', 'vfi', 'vpt', 'vzo', 'wobv', 'wto'],
  },
  {
    label: 'Other',
    options: ['basp', 'baspn', 'chandelier', 'copp', 'dmi', 'ebbp', 'fish', 'ichimoku', 'kst', 'pivot', 'pivot_fib', 'qstick', 'rolling_max', 'rolling_min', 'tmf', 'tp', 'vortex'],
  },
] as const

// Sensible default args per transformer
const ARG_DEFAULTS: Record<string, number[]> = {
  sma: [20], ema: [14], dema: [14], tema: [14], zlema: [14], wma: [14],
  hma: [14], kama: [14], smma: [14], smm: [3], ssma: [3], trima: [20],
  vama: [20], evwma: [20], vwap: [],
  rsi: [14], ift_rsi: [14], mom: [10], roc: [10],
  macd: [12, 26, 9], ppo: [12, 26],
  stoch: [14], stochd: [3], stochrsi: [14],
  cci: [20], mfi: [14], williams: [14], adx: [14], dmi: [14],
  ao: [], mi: [9, 25], tsi: [25, 13], uo: [7, 14, 28],
  atr: [14], tr: [], sar: [2, 20], bbands: [20, 2], bbwidth: [20],
  percent_b: [20], kc: [20], do: [20], sqzmi: [20], apz: [21],
  adl: [], obv: [], wobv: [], vzo: [14], pzo: [14], efi: [13],
  chaikin: [3, 10], cfi: [14], emv: [], msd: [20],
  vfi: [130], vpt: [], fve: [22], wto: [8, 13],
}

export function defaultArgs(transformer: string): number[] {
  return ARG_DEFAULTS[transformer] ?? [14]
}

// ── Converters ────────────────────────────────────────────────────────────────

export function formToStrategy(f: StrategyFormState): Record<string, unknown> {
  return {
    symbol:        f.symbol,
    exchange:      f.exchange,
    freq:          f.freq,
    start:         f.start,
    stop:          f.stop,
    base_balance:  f.base_balance,
    comission:     f.comission,
    datapoints:    f.datapoints.map(dp => ({ name: dp.name, transformer: dp.transformer, args: dp.args })),
    enter:         f.enter.map(r => [r.left, r.op, isNaN(Number(r.right)) ? r.right : Number(r.right)]),
    exit:          f.exit.map(r  => [r.left, r.op, isNaN(Number(r.right)) ? r.right : Number(r.right)]),
  }
}

export function strategyToForm(s: Record<string, unknown>): StrategyFormState {
  const parseRule = (r: unknown[]): Rule => ({
    left:  String(r[0] ?? 'close'),
    op:    (r[1] ?? '<') as Operator,
    right: String(r[2] ?? '0'),
  })
  return {
    exchange:     String(s.exchange ?? 'coinbase'),
    symbol:       String(s.symbol ?? 'BTC-USD'),
    freq:         String((s.freq ?? s.chart_period) ?? '4h'),
    start:        String(s.start ?? '2026-03-01'),
    stop:         String(s.stop ?? '2026-03-14'),
    base_balance: Number(s.base_balance ?? 1000),
    comission:    Number(s.comission ?? 0.001),
    datapoints: ((s.datapoints as unknown[]) ?? []).map(dp => {
      const d = dp as Record<string, unknown>
      return {
        name:        String(d.name ?? ''),
        transformer: String(d.transformer ?? 'rsi'),
        args:        ((d.args as unknown[]) ?? [14]).map(Number),
      }
    }),
    enter: ((s.enter as unknown[][]) ?? []).map(parseRule),
    exit:  ((s.exit  as unknown[][]) ?? []).map(parseRule),
  }
}

// ── Validator ─────────────────────────────────────────────────────────────────

export interface ValidationResult {
  errors: string[]
  fieldErrors: Record<string, string>
}

export function validate(f: StrategyFormState): ValidationResult {
  const errors: string[] = []
  const fieldErrors: Record<string, string> = {}

  const addField = (key: string, msg: string) => {
    fieldErrors[key] = msg
    errors.push(msg)
  }

  // Exchange
  if (!f.exchange) addField('exchange', 'Exchange is required')

  // Symbol + exchange compatibility
  if (!f.symbol) {
    addField('symbol', 'Symbol is required')
  } else if (f.exchange === 'coinbase' && !f.symbol.includes('-')) {
    addField('symbol', 'Coinbase symbols use dash format — e.g. BTC-USD')
  } else if (['binanceus', 'binancecom'].includes(f.exchange) && f.symbol.includes('-')) {
    addField('symbol', 'Binance symbols must not contain a dash — e.g. BTCUSDT')
  }

  // Dates
  if (!f.start) addField('start', 'Start date required')
  if (!f.stop)  addField('stop', 'Stop date required')
  if (f.start && f.stop && f.start >= f.stop)
    addField('stop', 'Stop must be after start')

  // Balance / commission
  if (f.base_balance <= 0) addField('base_balance', 'Balance must be > 0')
  if (f.comission < 0 || f.comission > 1) addField('comission', 'Commission must be between 0 and 1')

  // Datapoints
  const names = new Set<string>()
  f.datapoints.forEach((dp, i) => {
    if (!dp.name.trim())
      addField(`dp_name_${i}`, 'Indicator name required')
    else if (names.has(dp.name))
      addField(`dp_name_${i}`, `Duplicate name "${dp.name}"`)
    else
      names.add(dp.name)
    if (!dp.transformer)
      addField(`dp_transformer_${i}`, 'Transformer required')
  })

  const validOperands = new Set([...OHLC_COLUMNS, ...names])

  const checkRules = (rules: Rule[], label: string, prefix: string) => {
    if (rules.length === 0) {
      errors.push(`At least one ${label.toLowerCase()} rule is required`)
      return
    }
    rules.forEach((r, i) => {
      if (!r.left) {
        addField(`${prefix}_left_${i}`, 'Required')
      } else if (!validOperands.has(r.left)) {
        addField(`${prefix}_left_${i}`, `"${r.left}" is not a defined indicator or OHLC column`)
      }
      if (r.right === '') {
        addField(`${prefix}_right_${i}`, 'Required')
      } else if (isNaN(Number(r.right)) && !validOperands.has(r.right)) {
        addField(`${prefix}_right_${i}`, `"${r.right}" must be a number or a known indicator`)
      }
    })
  }

  checkRules(f.enter, 'Enter', 'enter')
  checkRules(f.exit,  'Exit',  'exit')

  return { errors, fieldErrors }
}

// ── Default state ─────────────────────────────────────────────────────────────

export const DEFAULT_FORM_STATE: StrategyFormState = {
  exchange:     'coinbase',
  symbol:       'BTC-USD',
  freq:         '4h',
  start:        '2026-03-01',
  stop:         '2026-03-14',
  base_balance: 1000,
  comission:    0.001,
  datapoints: [
    { name: 'rsi',      transformer: 'rsi', args: [14] },
    { name: 'fast_ema', transformer: 'ema', args: [10] },
    { name: 'slow_ema', transformer: 'ema', args: [30] },
  ],
  enter: [{ left: 'rsi', op: '<', right: '30' }],
  exit:  [{ left: 'rsi', op: '>', right: '70' }],
}
