# Bot API Guide: Strategy Testing, Tweaking & Creation

This guide instructs AI bots (Claude, etc.) on how to interact with the Fast-Trade API
to test strategies, tweak parameters, create new ones, and manage presets.

## Base URL

All endpoints are accessible at `http://localhost:9000/api/` (via the Go proxy)
or directly at `http://localhost:8000/` (FastAPI).

---

## 1. Running a Backtest

**Endpoint:** `POST /api/backtest`

### Request Body
```json
{
  "strategy": {
    "symbol": "BTC-USD",
    "exchange": "coinbase",
    "freq": "4h",
    "start": "2026-01-01",
    "stop": "2026-03-15",
    "base_balance": 10000,
    "comission": 0.001,
    "datapoints": [
      { "name": "rsi", "transformer": "rsi", "args": [14] },
      { "name": "fast_ema", "transformer": "ema", "args": [10] },
      { "name": "slow_ema", "transformer": "ema", "args": [30] }
    ],
    "enter": [
      ["rsi", "<", 30],
      ["fast_ema", ">", "slow_ema"]
    ],
    "exit": [
      ["rsi", ">", 70]
    ]
  },
  "use_cache": false
}
```

### Key Fields
- **symbol**: Asset ticker. Coinbase uses dash format (`BTC-USD`), Binance uses no dash (`BTCUSDT`), yfinance uses standard tickers (`SPY`, `AAPL`)
- **exchange**: `coinbase`, `binanceus`, `binancecom`, `yfinance`
- **freq**: Candle interval: `1min`, `5min`, `15min`, `30min`, `1h`, `4h`, `8h`, `12h`, `1D`
- **start/stop**: Date range (ISO format: `YYYY-MM-DD`)
- **base_balance**: Starting capital in USD
- **comission**: Trading fee as decimal (0.001 = 0.1%)
- **datapoints**: Technical indicators to compute (see Indicators section below)
- **enter**: Array of entry conditions (ALL must be true, AND logic)
- **exit**: Array of exit conditions (ALL must be true, AND logic)
- **use_cache**: Set `false` to force re-run and get full equity curve

### OR Logic (Alternative Conditions)
To use OR logic within enter/exit rules, wrap conditions in an `or` object:
```json
{
  "enter": [
    ["fast_ema", ">", "slow_ema"],
    { "or": [
      ["rsi", "<", 30],
      ["rsi", "<", 20]
    ]}
  ]
}
```

### Response
```json
{
  "run_id": "uuid",
  "cached": false,
  "summary": {
    "return_perc": 12.4,
    "sharpe_ratio": 1.3,
    "max_drawdown": -8.2,
    "num_trades": 42,
    "win_rate": 0.58,
    "profit_factor": 1.8,
    "buy_and_hold_perc": 5.1,
    "avg_trade_perc": 0.29,
    "time_in_market": 0.65
  },
  "equity_curve": [...],
  "trades": [...]
}
```

### Key Metrics to Evaluate
| Metric | Good Value | Description |
|--------|-----------|-------------|
| `return_perc` | > 0 | Total return percentage |
| `sharpe_ratio` | > 1.0 | Risk-adjusted return |
| `max_drawdown` | > -20% | Worst peak-to-trough decline |
| `win_rate` | > 0.5 | Percentage of winning trades |
| `profit_factor` | > 1.5 | Gross profit / gross loss |
| `num_trades` | > 10 | Enough trades for statistical significance |
| `buy_and_hold_perc` | compare | Benchmark: what holding would return |

---

## 2. Available Technical Indicators

### Moving Averages
| Transformer | Args | Description |
|------------|------|-------------|
| `sma` | [period] | Simple Moving Average |
| `ema` | [period] | Exponential Moving Average |
| `dema` | [period] | Double EMA |
| `tema` | [period] | Triple EMA |
| `wma` | [period] | Weighted Moving Average |
| `hma` | [period] | Hull Moving Average |
| `kama` | [period] | Kaufman Adaptive MA |
| `zlema` | [period] | Zero-Lag EMA |
| `vwap` | [] | Volume-Weighted Average Price |

### Oscillators
| Transformer | Args | Description |
|------------|------|-------------|
| `rsi` | [period] | Relative Strength Index (0-100) |
| `macd` | [fast, slow, signal] | MACD line value |
| `stoch` | [period] | Stochastic %K (0-100) |
| `stochd` | [period] | Stochastic %D |
| `stochrsi` | [period] | Stochastic RSI |
| `cci` | [period] | Commodity Channel Index |
| `mfi` | [period] | Money Flow Index |
| `williams` | [period] | Williams %R |
| `adx` | [period] | Average Directional Index |
| `roc` | [period] | Rate of Change |
| `mom` | [period] | Momentum |
| `tsi` | [long, short] | True Strength Index |
| `uo` | [s, m, l] | Ultimate Oscillator |

### Volatility
| Transformer | Args | Description |
|------------|------|-------------|
| `atr` | [period] | Average True Range |
| `bbands` | [period, std_dev] | Bollinger Bands (middle) |
| `percent_b` | [period] | Bollinger %B (0-1) |
| `kc` | [period] | Keltner Channel |
| `sar` | [af, max_af] | Parabolic SAR |
| `tr` | [] | True Range |

### Volume
| Transformer | Args | Description |
|------------|------|-------------|
| `obv` | [] | On-Balance Volume |
| `adl` | [] | Accumulation/Distribution Line |
| `chaikin` | [fast, slow] | Chaikin Oscillator |
| `efi` | [period] | Elder Force Index |
| `vfi` | [period] | Volume Force Index |

### Other
| Transformer | Args | Description |
|------------|------|-------------|
| `vortex` | [period] | Vortex Indicator |
| `ichimoku` | [t, k, s] | Ichimoku Cloud |
| `fish` | [period] | Fisher Transform |
| `rolling_max` | [period] | Rolling Maximum |
| `rolling_min` | [period] | Rolling Minimum |

### Rule Operands
Rules can reference:
- Any defined datapoint name (e.g. `rsi`, `fast_ema`)
- OHLC columns: `close`, `open`, `high`, `low`
- Numeric literals: `30`, `0.5`, `70`

### Operators
`<`, `>`, `=`, `!=`, `>=`, `<=`

---

## 3. Strategy Tweaking Workflow

### Step 1: Run Baseline
```json
POST /api/backtest
{ "strategy": { ... baseline ... }, "use_cache": false }
```

### Step 2: Evaluate Results
Check `summary.return_perc`, `summary.sharpe_ratio`, `summary.max_drawdown`, `summary.win_rate`.

### Step 3: Tweak Parameters
Common tweaks to try:
- **RSI thresholds**: Try 25/75 instead of 30/70
- **Moving average periods**: Try faster (8, 13) or slower (50, 200)
- **Timeframe**: Switch from `4h` to `1h` or `1D`
- **Add filters**: Add a trend filter (e.g. price > SMA-200)
- **Adjust commission**: 0.001 for stocks, 0.002 for crypto
- **Extend date range**: Longer backtest = more robust results

### Step 4: Compare
Run multiple variants and compare Sharpe ratio and max drawdown.

### Step 5: Save Best as Preset
```json
POST /api/presets
{
  "name": "My Optimized RSI",
  "tag": "Mean Rev",
  "category": "Mean Reversion",
  "description": "RSI 25/75 with SMA-200 filter, optimized for BTC 4h",
  "state": {
    "exchange": "coinbase",
    "symbol": "BTC-USD",
    "freq": "4h",
    "start": "2026-01-01",
    "stop": "2026-03-15",
    "base_balance": 10000,
    "comission": 0.001,
    "datapoints": [
      { "name": "rsi", "transformer": "rsi", "args": [14] },
      { "name": "sma_200", "transformer": "sma", "args": [200] }
    ],
    "enter": [
      { "left": "rsi", "op": "<", "right": "25" },
      { "left": "close", "op": ">", "right": "sma_200" }
    ],
    "exit": [
      { "left": "rsi", "op": ">", "right": "75" }
    ]
  }
}
```

---

## 4. Presets CRUD API

### List All Presets
```
GET /api/presets
```
Returns array of saved presets.

### Create Preset
```
POST /api/presets
Content-Type: application/json

{
  "name": "My Strategy",
  "tag": "Trend",
  "category": "Trend Following",
  "description": "Description of what the strategy does",
  "state": { ... StrategyFormState ... }
}
```

**Note:** The `state` field uses the **form state format** (objects with `left`, `op`, `right` for rules), not the raw strategy format (arrays). Example:

Form state format (for presets):
```json
{
  "enter": [{ "left": "rsi", "op": "<", "right": "30" }],
  "exit": [{ "left": "rsi", "op": ">", "right": "70" }]
}
```

Raw strategy format (for backtests):
```json
{
  "enter": [["rsi", "<", 30]],
  "exit": [["rsi", ">", 70]]
}
```

### Update Preset
```
PUT /api/presets/{id}
Content-Type: application/json

{ "name": "Updated Name", "tag": "...", "category": "...", "description": "...", "state": { ... } }
```

### Delete Preset
```
DELETE /api/presets/{id}
```

---

## 5. Optimization (Genetic Algorithm)

### Start Optimization
```
POST /api/optimize
{
  "base_strategy": { ... strategy dict ... },
  "evolver_config": {
    "num_generations": 50,
    "sol_per_pop": 20
  }
}
```

### Poll Status
```
GET /api/optimize/{task_id}
```
Poll every 2-3 seconds until `status == "done"`.

### Response when done
```json
{
  "task_id": "...",
  "status": "done",
  "result": {
    "best_strategy": { ... },
    "best_fitness": 0.95,
    "generations_run": 50
  }
}
```

---

## 6. Common Strategy Templates

### Simple RSI Mean Reversion
```json
{
  "symbol": "BTC-USD", "exchange": "coinbase", "freq": "4h",
  "start": "2026-01-01", "stop": "2026-03-15",
  "base_balance": 10000, "comission": 0.001,
  "datapoints": [{ "name": "rsi", "transformer": "rsi", "args": [14] }],
  "enter": [["rsi", "<", 30]],
  "exit": [["rsi", ">", 70]]
}
```

### EMA Crossover Trend Following
```json
{
  "symbol": "SPY", "exchange": "yfinance", "freq": "1D",
  "start": "2024-01-01", "stop": "2026-03-15",
  "base_balance": 10000, "comission": 0.001,
  "datapoints": [
    { "name": "fast", "transformer": "ema", "args": [12] },
    { "name": "slow", "transformer": "ema", "args": [26] }
  ],
  "enter": [["fast", ">", "slow"]],
  "exit": [["fast", "<", "slow"]]
}
```

### Multi-Indicator with Trend Filter
```json
{
  "symbol": "ETH-USD", "exchange": "coinbase", "freq": "1h",
  "start": "2025-06-01", "stop": "2026-03-15",
  "base_balance": 5000, "comission": 0.002,
  "datapoints": [
    { "name": "rsi", "transformer": "rsi", "args": [14] },
    { "name": "macd", "transformer": "macd", "args": [12, 26, 9] },
    { "name": "sma_200", "transformer": "sma", "args": [200] }
  ],
  "enter": [
    ["close", ">", "sma_200"],
    ["rsi", "<", 35],
    ["macd", ">", 0]
  ],
  "exit": [
    ["rsi", ">", 75]
  ]
}
```

### Bollinger Band Squeeze
```json
{
  "symbol": "NVDA", "exchange": "yfinance", "freq": "1D",
  "start": "2024-01-01", "stop": "2026-03-15",
  "base_balance": 10000, "comission": 0.001,
  "datapoints": [
    { "name": "pct_b", "transformer": "percent_b", "args": [20] },
    { "name": "rsi", "transformer": "rsi", "args": [14] }
  ],
  "enter": [["pct_b", "<", 0.2], ["rsi", ">", 40]],
  "exit": [["pct_b", ">", 0.8]]
}
```

---

## 7. Health Check

```
GET /api/health
```
Response: `{ "status": "ok", "service": "fast-trade-api", "version": "2.0.0" }`

Use this to verify the API is running before sending backtest requests.

---

## 8. Leaderboard

### Get Leaderboard
```
GET /api/leaderboard?limit=50
```
Returns top-performing backtest runs ranked by return percentage.

**Response:**
```json
[
  {
    "run_id": "uuid",
    "strategy_name": "My Strategy",
    "symbol": "SPY",
    "freq": "1D",
    "username": "maor_the_dev",
    "start_date": "2024-01-01",
    "end_date": "2026-03-15",
    "return_perc": 14.86,
    "sharpe_ratio": 1.888,
    "win_rate": 0.85,
    "total_trades": 14,
    "buy_and_hold_perc": 24.89,
    "max_drawdown": -6.07,
    "time_in_market": 37.98,
    "leverage": 1.0,
    "efficiency_score": 82.5,
    "finished_at": "2026-03-16T22:33:12.416930+00:00"
  }
]
```

**New fields:**
| Field | Description |
|-------|-------------|
| `start_date` / `end_date` | Backtest date range from params |
| `time_in_market` | Percentage of bars the strategy held a position |
| `leverage` | Leverage used (only runs with `leverage <= 1.0` appear on leaderboard) |
| `efficiency_score` | 0–100 score: `return_perc / (\|max_drawdown\|^1.5 × time_in_market)`, normalized across the returned rows. Higher = better risk-adjusted efficiency. |

---

## 9. Username Tracking

When running backtests, you can include a `username` field to track who ran each strategy. This is displayed on the leaderboard.

### Example with Username
```json
POST /api/backtest
{
  "strategy": { ... },
  "use_cache": false,
  "username": "maor_the_dev"
}
```

---

## 10. Tips for Bot Interaction

1. **Always set `use_cache: false`** when testing new strategies to get full equity curves
2. **Check health first** before running backtests
3. **Use sufficient date ranges** - at least 3 months for hourly data, 1 year for daily
4. **Compare against buy-and-hold** - check `summary.buy_and_hold_perc` vs `summary.return_perc`
5. **Watch for overfitting** - if a strategy only works on one narrow date range, it's likely overfit
6. **Save good strategies as presets** so they can be reused and refined later
7. **The `state` format differs from `strategy` format** - presets use form state (objects), backtests use raw arrays
8. **Track your runs** - include `username` to see your strategies on the leaderboard
