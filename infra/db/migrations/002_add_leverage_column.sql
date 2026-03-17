-- Migration: Add leverage column to backtest_runs for efficient filtering
-- Run this manually if the database was already initialized before this feature

ALTER TABLE backtest_runs
    ADD COLUMN IF NOT EXISTS leverage DOUBLE PRECISION NOT NULL DEFAULT 1.0;

-- Backfill from existing summary JSONB
UPDATE backtest_runs
SET leverage = COALESCE((summary->>'leverage')::float, 1.0)
WHERE leverage = 1.0;

CREATE INDEX IF NOT EXISTS backtest_runs_leverage_idx ON backtest_runs (leverage);
