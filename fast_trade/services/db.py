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
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO strategies (name, config)
                VALUES (:name, :config::jsonb)
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
) -> None:
    """Persist a completed backtest run to TimescaleDB."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO backtest_runs
                    (id, strategy_id, strategy_hash, data_hash,
                     started_at, finished_at, status, summary, params)
                VALUES
                    (:id, :sid, :sh, :dh,
                     NOW(), NOW(), 'done', :summary::jsonb, :params::jsonb)
                ON CONFLICT (id) DO UPDATE
                    SET finished_at = NOW(),
                        status      = 'done',
                        summary     = :summary::jsonb
            """),
            {
                "id": run_id,
                "sid": strategy_id,
                "sh": strategy_hash,
                "dh": data_hash,
                "summary": json.dumps(summary, default=str),
                "params": json.dumps(params, default=str),
            },
        )


# ── Preset CRUD ──────────────────────────────────────────────────────────────

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
