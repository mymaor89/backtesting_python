export interface EquityPoint {
  ts: string
  equity: number | null
  adj_equity: number | null
  action: string
  in_trade?: boolean
  close?: number | null
  open?: number | null
  high?: number | null
  low?: number | null
  [key: string]: unknown   // indicator columns (rsi, fast_ema, …)
}

export interface Trade {
  [key: string]: unknown
}

export interface Summary {
  return_perc?: number | null
  sharpe_ratio?: number | null
  max_drawdown?: number | null
  num_trades?: number | null
  win_rate?: number | null
  profit_factor?: number | null
  buy_and_hold_perc?: number | null
  time_in_market?: number | null
  avg_trade_perc?: number | null
  leverage?: number | null
  num_liquidations?: number | null
  [key: string]: unknown
}

export interface BacktestResponse {
  run_id: string
  cached: boolean
  summary: Summary
  equity_curve: EquityPoint[]
  trades: Trade[]
}

export interface OptimizeResult {
  best_strategy: Record<string, unknown>
  best_fitness: number
  generations_run: number
}

export interface TaskStatus {
  task_id: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
  result: OptimizeResult | { error: string } | null
}
