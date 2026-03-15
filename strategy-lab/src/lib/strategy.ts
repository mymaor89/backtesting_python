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

export interface OrGroup { or: Rule[] }
export type RuleItem = Rule | OrGroup

export interface StrategyFormState {
  exchange: string
  symbol: string
  freq: string
  start: string
  stop: string
  base_balance: number
  comission: number
  datapoints: Datapoint[]
  enter: RuleItem[]
  exit: RuleItem[]
}

// ── Constants ─────────────────────────────────────────────────────────────────

export const EXCHANGES = ['coinbase', 'binanceus', 'binancecom', 'yfinance'] as const

export const EXCHANGE_SYMBOLS: Record<string, string[]> = {
  coinbase:   ['BTC-USD', 'ETH-USD', 'SOL-USD', 'DOGE-USD', 'XRP-USD', 'ADA-USD', 'AVAX-USD', 'LINK-USD', 'MATIC-USD'],
  binanceus:  ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT', 'XRPUSDT', 'BNBUSDT', 'ADAUSDT', 'AVAXUSDT', 'MATICUSDT'],
  binancecom: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT', 'XRPUSDT', 'BNBUSDT', 'ADAUSDT', 'AVAXUSDT', 'MATICUSDT'],
  yfinance:   ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'GOOGL', 'META', 'GLD', 'TLT', 'IWM'],
}

export const FREQS = ['1min', '5min', '15min', '30min', '1h', '4h', '8h', '12h', '1D'] as const

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
  const convertItem = (r: RuleItem): unknown => {
    if ('or' in r) {
      return { or: r.or.map(sub => [sub.left, sub.op, isNaN(Number(sub.right)) ? sub.right : Number(sub.right)]) }
    }
    return [r.left, r.op, isNaN(Number(r.right)) ? r.right : Number(r.right)]
  }
  return {
    symbol:        f.symbol,
    exchange:      f.exchange,
    freq:          f.freq,
    start:         f.start,
    stop:          f.stop,
    base_balance:  f.base_balance,
    comission:     f.comission,
    datapoints:    f.datapoints.map(dp => ({ name: dp.name, transformer: dp.transformer, args: dp.args })),
    enter:         f.enter.map(convertItem),
    exit:          f.exit.map(convertItem),
  }
}

export function strategyToForm(s: Record<string, unknown>): StrategyFormState {
  const parseRule = (r: unknown[]): Rule => ({
    left:  String(r[0] ?? 'close'),
    op:    (r[1] ?? '<') as Operator,
    right: String(r[2] ?? '0'),
  })
  const parseItem = (r: unknown): RuleItem => {
    if (r && typeof r === 'object' && !Array.isArray(r) && 'or' in (r as object)) {
      const orArr = ((r as Record<string, unknown>).or as unknown[]) ?? []
      return { or: orArr.map(sub => parseRule(sub as unknown[])) }
    }
    return parseRule(r as unknown[])
  }
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
    enter: ((s.enter as unknown[]) ?? []).map(parseItem),
    exit:  ((s.exit  as unknown[]) ?? []).map(parseItem),
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
  // yfinance accepts any ticker format (SPY, AAPL, BTC-USD, etc.)

  // Dates
  if (!f.start) addField('start', 'Start date required')
  if (!f.stop)  addField('stop', 'Stop date required')
  if (f.start && f.stop && f.start > f.stop)
    addField('stop', 'Stop must be on or after start')

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

  const checkRules = (rules: RuleItem[], label: string, prefix: string) => {
    if (rules.length === 0) {
      errors.push(`At least one ${label.toLowerCase()} rule is required`)
      return
    }
    rules.forEach((item, i) => {
      if ('or' in item) {
        if (item.or.length === 0) {
          errors.push(`OR group in ${label} must have at least one condition`)
        }
        item.or.forEach((sub, j) => {
          if (!sub.left) {
            addField(`${prefix}_or${i}_left_${j}`, 'Required')
          } else if (!validOperands.has(sub.left)) {
            addField(`${prefix}_or${i}_left_${j}`, `"${sub.left}" is not a known indicator or OHLC column`)
          }
          if (sub.right === '') {
            addField(`${prefix}_or${i}_right_${j}`, 'Required')
          } else if (isNaN(Number(sub.right)) && !validOperands.has(sub.right)) {
            addField(`${prefix}_or${i}_right_${j}`, `"${sub.right}" must be a number or known indicator`)
          }
        })
      } else {
        if (!item.left) {
          addField(`${prefix}_left_${i}`, 'Required')
        } else if (!validOperands.has(item.left)) {
          addField(`${prefix}_left_${i}`, `"${item.left}" is not a defined indicator or OHLC column`)
        }
        if (item.right === '') {
          addField(`${prefix}_right_${i}`, 'Required')
        } else if (isNaN(Number(item.right)) && !validOperands.has(item.right)) {
          addField(`${prefix}_right_${i}`, `"${item.right}" must be a number or a known indicator`)
        }
      }
    })
  }

  checkRules(f.enter, 'Enter', 'enter')
  checkRules(f.exit,  'Exit',  'exit')

  return { errors, fieldErrors }
}

// ── Preset strategies ─────────────────────────────────────────────────────────

export interface Preset {
  name: string
  tag: string        // short label shown in the pill
  description: string
  state: StrategyFormState
}

export const PRESET_STRATEGIES: Preset[] = [
  {
    name: 'Golden Cross',
    tag: 'Trend',
    description: 'Buy when SMA-50 crosses above SMA-200 (price above SMA-50). Exit on death-cross. Classic trend-following on SPY.',
    state: {
      exchange: 'yfinance', symbol: 'SPY', freq: '1D',
      start: '2020-01-01', stop: '2024-12-31',
      base_balance: 10000, comission: 0.001,
      datapoints: [
        { name: 'sma_50',  transformer: 'sma', args: [50] },
        { name: 'sma_200', transformer: 'sma', args: [200] },
      ],
      enter: [
        { left: 'sma_50', op: '>', right: 'sma_200' },
        { left: 'close',  op: '>', right: 'sma_50'  },
      ],
      exit: [
        { left: 'sma_50', op: '<', right: 'sma_200' },
      ],
    },
  },
  {
    name: 'Turtle Breakout',
    tag: 'Donchian',
    description: 'Enter when price hits a new 20-day high (Donchian breakout). Exit on a new 20-day low. Tested on Gold (GLD).',
    state: {
      exchange: 'yfinance', symbol: 'GLD', freq: '1D',
      start: '2018-01-01', stop: '2024-12-31',
      base_balance: 10000, comission: 0.001,
      datapoints: [
        { name: 'high_20', transformer: 'rolling_max', args: [20] },
        { name: 'low_20',  transformer: 'rolling_min', args: [20] },
      ],
      enter: [{ left: 'close', op: '>=', right: 'high_20' }],
      exit:  [{ left: 'close', op: '<=', right: 'low_20'  }],
    },
  },
  {
    name: 'RSI Mean Reversion',
    tag: 'Mean Rev',
    description: 'Buy dips in an uptrend: RSI oversold (<30) while price is above SMA-200. Exit when RSI recovers above 65.',
    state: {
      exchange: 'yfinance', symbol: 'AAPL', freq: '1D',
      start: '2018-01-01', stop: '2024-12-31',
      base_balance: 10000, comission: 0.001,
      datapoints: [
        { name: 'rsi',     transformer: 'rsi', args: [14]  },
        { name: 'sma_200', transformer: 'sma', args: [200] },
      ],
      enter: [
        { left: 'rsi',   op: '<', right: '30'      },
        { left: 'close', op: '>', right: 'sma_200' },
      ],
      exit: [{ left: 'rsi', op: '>', right: '65' }],
    },
  },
  {
    name: 'Bollinger Reversion',
    tag: 'Mean Rev',
    description: 'Enter when price falls below the lower Bollinger Band (%B < 0.1) and RSI is weak. Exit when price reaches the upper band. Uses recent 60 days (yfinance intraday limit).',
    state: {
      exchange: 'yfinance', symbol: 'BTC-USD', freq: '1h',
      start: '2026-01-15', stop: '2026-03-15',
      base_balance: 10000, comission: 0.001,
      datapoints: [
        { name: 'pct_b', transformer: 'percent_b', args: [20] },
        { name: 'rsi',   transformer: 'rsi',       args: [14] },
      ],
      enter: [
        { left: 'pct_b', op: '<', right: '0.1' },
        { left: 'rsi',   op: '<', right: '40'  },
      ],
      exit: [{ left: 'pct_b', op: '>', right: '0.9' }],
    },
  },
  {
    name: 'Momentum ROC',
    tag: 'Momentum',
    description: 'Ride positive momentum: enter when 6-month rate-of-change is positive and price is above SMA-50. Exit on momentum loss.',
    state: {
      exchange: 'yfinance', symbol: 'QQQ', freq: '1D',
      start: '2018-01-01', stop: '2024-12-31',
      base_balance: 10000, comission: 0.001,
      datapoints: [
        { name: 'roc',    transformer: 'roc', args: [126] },
        { name: 'sma_50', transformer: 'sma', args: [50]  },
      ],
      enter: [
        { left: 'roc',   op: '>', right: '0'      },
        { left: 'close', op: '>', right: 'sma_50' },
      ],
      exit: [{ left: 'roc', op: '<', right: '0' }],
    },
  },
]

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
