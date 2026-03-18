-- Fast-Trade TimescaleDB Schema
-- Run once on first startup via docker-entrypoint-initdb.d

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ──────────────────────────────────────────────
-- OHLCV time-series: the single source of truth
-- for all market data (crypto, ETFs, indices)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ohlcv (
    ts        TIMESTAMPTZ     NOT NULL,
    symbol    TEXT            NOT NULL,
    exchange  TEXT            NOT NULL,
    open      DOUBLE PRECISION NOT NULL,
    high      DOUBLE PRECISION NOT NULL,
    low       DOUBLE PRECISION NOT NULL,
    close     DOUBLE PRECISION NOT NULL,
    volume    DOUBLE PRECISION NOT NULL
);

SELECT create_hypertable('ohlcv', 'ts', if_not_exists => TRUE);

-- Compress chunks older than 7 days (saves ~90% disk)
ALTER TABLE ohlcv SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, exchange',
    timescaledb.compress_orderby = 'ts DESC'
);

SELECT add_compression_policy('ohlcv', INTERVAL '7 days', if_not_exists => TRUE);

CREATE UNIQUE INDEX IF NOT EXISTS ohlcv_unique
    ON ohlcv (ts, symbol, exchange);

-- ──────────────────────────────────────────────
-- STRATEGIES: versioned strategy definitions
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS strategies (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    config      JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    tags        TEXT[] DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS strategies_name_idx ON strategies (name, version);

-- ──────────────────────────────────────────────
-- BACKTEST RUNS: experiment registry
-- Every run is reproducible via this record
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS backtest_runs (
    id              TEXT PRIMARY KEY,           -- UUID
    strategy_id     INTEGER REFERENCES strategies(id),
    strategy_hash   TEXT NOT NULL,              -- sha256 of config
    data_hash       TEXT NOT NULL,              -- sha256 of input data slice
    git_sha         TEXT,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          TEXT DEFAULT 'pending',     -- pending, running, done, failed
    summary         JSONB,
    params          JSONB,                      -- any CLI mods / overrides
    symbol          TEXT,
    timeframe       TEXT,
    username        TEXT
);

CREATE INDEX IF NOT EXISTS backtest_runs_strategy_idx ON backtest_runs (strategy_id);
CREATE INDEX IF NOT EXISTS backtest_runs_status_idx ON backtest_runs (status);

-- ──────────────────────────────────────────────
-- TRADES: all executed trades (backtest + paper)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    ts              TIMESTAMPTZ NOT NULL,
    run_id          TEXT,                       -- NULL for paper trades
    portfolio_name  TEXT,
    symbol          TEXT NOT NULL,
    exchange        TEXT NOT NULL,
    action          TEXT NOT NULL,              -- enter, exit, tsl
    price           DOUBLE PRECISION NOT NULL,
    qty             DOUBLE PRECISION NOT NULL,
    pnl_perc        DOUBLE PRECISION,
    pnl_abs         DOUBLE PRECISION,
    hold_bars       INTEGER
);

SELECT create_hypertable('trades', 'ts', if_not_exists => TRUE);

-- ──────────────────────────────────────────────
-- PORTFOLIO STATE: one row per portfolio
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS portfolio_state (
    name            TEXT PRIMARY KEY,
    symbol          TEXT NOT NULL,
    exchange        TEXT NOT NULL,
    cash            DOUBLE PRECISION NOT NULL,
    position_qty    DOUBLE PRECISION NOT NULL DEFAULT 0,
    avg_price       DOUBLE PRECISION NOT NULL DEFAULT 0,
    equity          DOUBLE PRECISION NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    strategy_id     INTEGER REFERENCES strategies(id)
);

-- ──────────────────────────────────────────────
-- PRESETS: user-saved strategy presets
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS presets (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    tag         TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT 'Custom',
    description TEXT NOT NULL DEFAULT '',
    explanation TEXT NOT NULL DEFAULT '',
    state       JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS presets_name_idx ON presets (name);

-- ──────────────────────────────────────────────
-- REGIME LABELS: output of HMM regime detection
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS regime_labels (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT NOT NULL,
    exchange        TEXT NOT NULL,
    regime_label    TEXT NOT NULL,
    regime_conf     DOUBLE PRECISION NOT NULL,
    model_version   TEXT
);

SELECT create_hypertable('regime_labels', 'ts', if_not_exists => TRUE);

CREATE UNIQUE INDEX IF NOT EXISTS regime_labels_unique
    ON regime_labels (ts, symbol, exchange, model_version);
