"""
Shared database connection pool for the FastAPI service and Celery workers.

Provides:
  - SQLAlchemy engine factory (pooled for API, NullPool for workers)
  - Deterministic hashing for cache lookups
  - CRUD helpers: cache read, backtest run save, strategy upsert, trade bulk-insert
"""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.pool import NullPool

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://fasttrade:fasttrade_dev@timescaledb:5432/fasttrade",
)


# ── Engine factories ──────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_engine(pool_size: int = 5) -> sa.Engine:
    """Pooled engine — for use in the FastAPI process only."""
    return sa.create_engine(
        _DATABASE_URL,
        pool_size=pool_size,
        max_overflow=10,
        pool_pre_ping=True,
    )


def get_worker_engine() -> sa.Engine:
    """NullPool engine — safe for Celery forked worker processes."""
    return sa.create_engine(_DATABASE_URL, poolclass=NullPool, pool_pre_ping=True)


# ── Hashing helpers ───────────────────────────────────────────────────────────

def hash_strategy(strategy: dict) -> str:
    """SHA-256 of the canonically serialised strategy definition."""
    canonical = json.dumps(strategy, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def hash_data(symbol: str, exchange: str, start: str, end: str, freq: str) -> str:
    """SHA-256 of the data-slice parameters."""
    key = f"{symbol}:{exchange}:{start}:{end}:{freq}"
    return hashlib.sha256(key.encode()).hexdigest()


# ── Cache read ────────────────────────────────────────────────────────────────

def get_cached_backtest(
    engine: sa.Engine,
    strategy_hash: str,
    data_hash: str,
) -> Optional[dict]:
    """
    Return a previously completed run whose strategy + data hashes match.
    Returns None when no cache hit is found.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, summary
                FROM backtest_runs
                WHERE strategy_hash = :sh
                  AND data_hash     = :dh
                  AND status        = 'done'
                ORDER BY finished_at DESC
                LIMIT 1
            """),
            {"sh": strategy_hash, "dh": data_hash},
        ).fetchone()

    if row and row.summary:
        return {"run_id": row.id, "summary": row.summary, "cached": True}
    return None


# ── Write helpers ─────────────────────────────────────────────────────────────

def upsert_strategy(engine: sa.Engine, name: str, config: dict) -> Optional[int]:
    """Insert a strategy row (by name) and return its id."""
    if not name or name.strip().lower() == "unnamed":
        name = "Unnamed"
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO strategies (name, config)
                VALUES (:name, CAST(:config AS JSONB))
                ON CONFLICT DO NOTHING
                RETURNING id
            """),
            {"name": name, "config": json.dumps(config)},
        ).fetchone()
        if row:
            return row.id
        # Row already existed — fetch it
        row = conn.execute(
            text("SELECT id FROM strategies WHERE name = :name ORDER BY id DESC LIMIT 1"),
            {"name": name},
        ).fetchone()
        return row.id if row else None


def save_backtest_run(
    engine: sa.Engine,
    run_id: str,
    strategy_id: Optional[int],
    strategy_hash: str,
    data_hash: str,
    summary: dict,
    params: dict,
    username: Optional[str] = None,
) -> None:
    """Persist a completed backtest run to TimescaleDB."""
    symbol = params.get("symbol") or summary.get("symbol")
    freq = params.get("freq") or params.get("chart_period") or summary.get("freq")
    leverage = float(summary.get("leverage") or params.get("leverage") or 1.0)

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO backtest_runs
                    (id, strategy_id, strategy_hash, data_hash,
                     started_at, finished_at, status, summary, params,
                     symbol, timeframe, username, leverage)
                VALUES
                    (:id, :sid, :sh, :dh,
                     NOW(), NOW(), 'done', CAST(:summary AS JSONB), CAST(:params AS JSONB),
                     :symbol, :timeframe, :username, :leverage)
                ON CONFLICT (id) DO UPDATE
                    SET finished_at = NOW(),
                        status      = 'done',
                        summary     = CAST(:summary AS JSONB),
                        symbol      = :symbol,
                        timeframe   = :timeframe,
                        username    = :username,
                        leverage    = :leverage
            """),
            {
                "id": run_id,
                "sid": strategy_id,
                "sh": strategy_hash,
                "dh": data_hash,
                "summary": json.dumps(summary, default=str),
                "params": json.dumps(params, default=str),
                "symbol": symbol,
                "timeframe": freq,
                "username": username,
                "leverage": leverage,
            },
        )


# ── Preset CRUD ──────────────────────────────────────────────────────────────

def get_run(engine: sa.Engine, run_id: str) -> Optional[dict]:
    """Return a single backtest run by its ID."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT r.id, s.name AS strategy_name, r.strategy_hash, r.data_hash,
                       r.started_at, r.finished_at, r.status, r.summary, r.params
                FROM backtest_runs r
                LEFT JOIN strategies s ON r.strategy_id = s.id
                WHERE r.id = :run_id
            """),
            {"run_id": run_id},
        ).fetchone()

    if not row:
        return None

    return {
        "run_id": row.id,
        "strategy_name": row.strategy_name,
        "strategy_hash": row.strategy_hash,
        "data_hash": row.data_hash,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "status": row.status,
        "summary": row.summary or {},
        "params": row.params or {},
    }


def list_presets(engine: sa.Engine) -> list[dict]:
    """Return all user-saved presets, ordered by updated_at desc."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, name, tag, category, description, state, created_at, updated_at FROM presets ORDER BY updated_at DESC")
        ).fetchall()
    return [
        {
            "id": r.id,
            "name": r.name,
            "tag": r.tag,
            "category": r.category,
            "description": r.description,
            "state": r.state,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


def _calc_raw_efficiency(return_perc: float, max_drawdown: float, time_in_market: float) -> float:
    """Raw efficiency score: return / (|drawdown|^1.5 * time_in_market).

    Non-linear drawdown penalty makes high-drawdown strategies score much worse.
    Uses a floor of 0.1 for drawdown and 0.01 for time_in_market to avoid div/0.
    """
    dd = max(abs(max_drawdown), 0.1)
    tim = max(time_in_market, 0.01)
    return return_perc / (dd ** 1.5 * tim)


def list_leaderboard(engine: sa.Engine, limit: int = 50) -> list[dict]:
    """Return top backtest runs ranked by efficiency_score (calculated from return, risk, and time).
    
    To find the 'smartest' strategies, we fetch a larger candidate set (500) sorted by raw return,
    calculate normalized efficiency scores, and then sort the final result by that score.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    r.id, s.name as strategy_name, r.strategy_hash, r.data_hash,
                    r.finished_at, COALESCE(r.symbol, r.params->>'symbol') as symbol,
                    COALESCE(r.timeframe, r.params->>'freq', r.params->>'chart_period') as freq,
                    r.username,
                    r.params->>'start' as start_date,
                    r.params->>'stop' as end_date,
                    (r.summary->>'return_perc')::float as return_perc,
                    (r.summary->>'sharpe_ratio')::float as sharpe_ratio,
                    (r.summary->>'win_rate')::float as win_rate,
                    (r.summary->>'total_trades')::int as total_trades,
                    (r.summary->>'buy_and_hold_perc')::float as buy_and_hold_perc,
                    COALESCE((r.summary->'drawdown_metrics'->>'max_drawdown_pct')::float, (r.summary->>'max_drawdown')::float) as max_drawdown,
                    COALESCE((r.summary->>'time_in_market')::float, (r.summary->>'market_exposure_perc')::float, 0) as time_in_market,
                    COALESCE(r.leverage, (r.summary->>'leverage')::float, 1.0) as leverage
                FROM backtest_runs r
                LEFT JOIN strategies s ON r.strategy_id = s.id
                WHERE r.status = 'done'
                  AND r.summary ? 'return_perc'
                  AND COALESCE(r.leverage, (r.summary->>'leverage')::float, 1.0) <= 1.0
                ORDER BY (r.summary->>'return_perc')::float DESC
                LIMIT :candidate_limit
            """),
            {"candidate_limit": 500}
        ).fetchall()

    if not rows:
        return []

    # Compute raw efficiency scores for all rows
    all_data = []
    for r in rows:
        raw_s = _calc_raw_efficiency(
            r.return_perc or 0,
            r.max_drawdown or 0,
            r.time_in_market or 0,
        )
        all_data.append({"row": r, "raw_score": raw_s})

    # Normalize to 0-100 using global min-max within this candidate set
    raw_scores = [d["raw_score"] for d in all_data]
    min_s, max_s = min(raw_scores), max(raw_scores)
    span = max_s - min_s
    
    for d in all_data:
        if span > 0:
            d["normalized"] = round((d["raw_score"] - min_s) / span * 100, 2)
        else:
            d["normalized"] = 100.0

    # Sort final set by the efficiency score instead of raw return
    all_data.sort(key=lambda x: x["normalized"], reverse=True)
    
    # Take the top 'limit' requested
    top_entries = all_data[:limit]

    return [
        {
            "run_id": d["row"].id,
            "strategy_name": d["row"].strategy_name or "Unnamed",
            "symbol": d["row"].symbol,
            "freq": d["row"].freq,
            "username": d["row"].username,
            "start_date": d["row"].start_date,
            "end_date": d["row"].end_date,
            "return_perc": round(d["row"].return_perc, 2) if d["row"].return_perc is not None else 0,
            "sharpe_ratio": round(d["row"].sharpe_ratio, 3) if d["row"].sharpe_ratio is not None else 0,
            "win_rate": round(d["row"].win_rate, 2) if d["row"].win_rate is not None else 0,
            "total_trades": d["row"].total_trades or 0,
            "buy_and_hold_perc": round(d["row"].buy_and_hold_perc, 2) if d["row"].buy_and_hold_perc is not None else 0,
            "max_drawdown": round(d["row"].max_drawdown, 2) if d["row"].max_drawdown is not None else 0,
            "time_in_market": round(d["row"].time_in_market, 2) if d["row"].time_in_market is not None else 0,
            "leverage": round(d["row"].leverage, 2) if d["row"].leverage is not None else 1.0,
            "efficiency_score": d["normalized"],
            "finished_at": d["row"].finished_at.isoformat() if d["row"].finished_at else None,
        }
        for d in top_entries
    ]


def create_preset(engine: sa.Engine, name: str, tag: str, category: str, description: str, state: dict) -> dict:
    """Insert a new preset and return it."""
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO presets (name, tag, category, description, state)
                VALUES (:name, :tag, :category, :description, CAST(:state AS jsonb))
                RETURNING id, created_at, updated_at
            """),
            {"name": name, "tag": tag, "category": category, "description": description, "state": json.dumps(state)},
        ).fetchone()
    return {
        "id": row.id,
        "name": name,
        "tag": tag,
        "category": category,
        "description": description,
        "state": state,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def update_preset(engine: sa.Engine, preset_id: int, name: str, tag: str, category: str, description: str, state: dict) -> Optional[dict]:
    """Update an existing preset by id. Returns updated preset or None if not found."""
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                UPDATE presets
                SET name = :name, tag = :tag, category = :category,
                    description = :description, state = CAST(:state AS jsonb),
                    updated_at = NOW()
                WHERE id = :id
                RETURNING id, created_at, updated_at
            """),
            {"id": preset_id, "name": name, "tag": tag, "category": category, "description": description, "state": json.dumps(state)},
        ).fetchone()
    if not row:
        return None
    return {
        "id": row.id,
        "name": name,
        "tag": tag,
        "category": category,
        "description": description,
        "state": state,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def delete_preset(engine: sa.Engine, preset_id: int) -> bool:
    """Delete a preset by id. Returns True if deleted."""
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM presets WHERE id = :id"),
            {"id": preset_id},
        )
    return result.rowcount > 0


def save_trades(engine: sa.Engine, run_id: str, trade_log_df) -> None:
    """Bulk-insert a trade log DataFrame into the trades hypertable."""
    import pandas as pd

    if trade_log_df is None or (hasattr(trade_log_df, "empty") and trade_log_df.empty):
        return

    rows = []
    for idx, t in trade_log_df.iterrows():
        ts = idx if hasattr(idx, "isoformat") else pd.Timestamp(idx)
        rows.append(
            {
                "ts": ts,
                "run_id": run_id,
                "symbol": str(t.get("symbol", "")),
                "exchange": str(t.get("exchange", "")),
                "action": "trade",
                "price": float(t.get("close", t.get("exit_price", 0)) or 0),
                "qty": float(t.get("quantity", 0) or 0),
                "pnl_perc": float(t.get("adj_account_value_change_perc", 0) or 0),
                "pnl_abs": float(t.get("adj_account_value_change", 0) or 0),
                "hold_bars": int(t.get("hold_time", 0) or 0),
            }
        )

    if not rows:
        return

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO trades
                    (ts, run_id, symbol, exchange, action,
                     price, qty, pnl_perc, pnl_abs, hold_bars)
                VALUES
                    (:ts, :run_id, :symbol, :exchange, :action,
                     :price, :qty, :pnl_perc, :pnl_abs, :hold_bars)
                ON CONFLICT DO NOTHING
            """),
            rows,
        )
