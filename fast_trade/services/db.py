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

def _derive_strategy_name(config: dict) -> str:
    """Derive a tactic-descriptive name from strategy config when no explicit name is given."""
    datapoints = config.get("datapoints", [])
    enter_rules = config.get("enter", [])

    # Group datapoints by transformer type
    by_type: dict = {}
    for dp in datapoints:
        t = dp.get("transformer", "").lower()
        by_type.setdefault(t, []).append(dp)

    def _args(t):
        return [dp.get("args", []) for dp in by_type.get(t, [])]

    # Breakout via Donchian channels
    if "rolling_max" in by_type or "rolling_min" in by_type:
        dps = by_type.get("rolling_max") or by_type.get("rolling_min")
        period = (dps[0].get("args") or [20])[0]
        return f"Donchian {period} Breakout"

    # RSI-based — inspect entry threshold to distinguish trend filter vs mean-reversion
    if "rsi" in by_type:
        all_periods = [(dp.get("args") or [14])[0] for dp in by_type["rsi"]]
        # Find the RSI used in the entry condition
        entry_rsi_period = None
        entry_threshold = None
        entry_op = None
        for rule in enter_rules:
            if isinstance(rule, (list, tuple)) and len(rule) >= 3:
                left, op, right = str(rule[0]), rule[1], rule[2]
                if "rsi" in left.lower():
                    # Try to pull period from matching datapoint name
                    for dp in by_type["rsi"]:
                        if dp.get("name") == left:
                            entry_rsi_period = (dp.get("args") or [14])[0]
                    entry_threshold = right
                    entry_op = op
                    break
        period = entry_rsi_period or min(all_periods)
        if entry_op == "<" and entry_threshold is not None:
            label = "Mean Rev" if period <= 5 else "Oversold"
            return f"RSI({period}) {label} <{entry_threshold}"
        if entry_op == ">" and entry_threshold is not None:
            return f"RSI({period}) Overbought >{entry_threshold}"
        if len(all_periods) >= 3:
            # Multi-RSI hybrid
            extra = [k.upper() for k in ("macd", "atr", "ema", "sma") if k in by_type]
            suffix = " + " + "/".join(extra[:2]) if extra else ""
            return f"RSI Multi{suffix}"
        return f"RSI({period}) Strategy"

    # Triple EMA stack
    if len(by_type.get("ema", [])) >= 3:
        periods = sorted((dp.get("args") or [20])[0] for dp in by_type["ema"])
        return f"Triple EMA {'/'.join(str(p) for p in periods)}"

    # EMA vs SMA crossover
    if by_type.get("ema") and by_type.get("sma"):
        ep = (by_type["ema"][0].get("args") or [20])[0]
        sp = (by_type["sma"][0].get("args") or [200])[0]
        return f"EMA {ep}/SMA {sp} Crossover"

    # Dual EMA crossover
    if len(by_type.get("ema", [])) == 2:
        periods = sorted((dp.get("args") or [20])[0] for dp in by_type["ema"])
        return f"EMA {periods[0]}/{periods[1]} Crossover"

    # Dual SMA crossover (Golden/Death Cross)
    if len(by_type.get("sma", [])) >= 2:
        periods = sorted((dp.get("args") or [200])[0] for dp in by_type["sma"])
        return f"SMA {periods[0]}/{periods[1]} Crossover"

    # MACD-based
    if "macd" in by_type:
        extras = [k.upper() for k in ("rsi", "ema", "sma", "atr") if k in by_type]
        suffix = " + " + "/".join(extras[:2]) if extras else ""
        return f"MACD{suffix}"

    # Bollinger Bands
    if "bbands" in by_type or "bollinger" in by_type:
        return "Bollinger Bands Mean Rev"

    # Generic fallback using present indicator names
    priority = ["macd", "atr", "stoch", "cci", "adx", "ema", "sma", "vwap"]
    found = [k.upper() for k in priority if k in by_type]
    if found:
        return " + ".join(found[:3]) + " Strategy"

    return "Custom Strategy"


def upsert_strategy(engine: sa.Engine, name: str, config: dict) -> Optional[int]:
    """Insert a strategy row (by name) and return its id."""
    if not name or name.strip().lower() == "unnamed":
        name = _derive_strategy_name(config)
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

    # Fallback: if params is missing essential fields (conditions), try to restore from summary.strategy
    params = dict(row.params) if row.params else {}
    summary = row.summary or {}
    
    # Check if any condition key is non-empty
    has_conditions = any(params.get(k) for k in ["enter", "exit", "rules", "enter_short", "exit_short"])
    
    if not has_conditions and isinstance(summary, dict) and "strategy" in summary:
        s_params = summary["strategy"]
        if isinstance(s_params, dict):
            # If the summary strategy has conditions, it's a better source than empty params
            has_summary_conditions = any(s_params.get(k) for k in ["enter", "exit", "rules"])
            if has_summary_conditions:
                # Merge: take everything from summary strategy, but keep original params if they have useful data
                # Actually, summary strategy is usually the 'complete' one used for the backtest
                params = s_params
    
    # Ensure leverage exists
    if params and "leverage" not in params:
        # Check if row has leverage (if we were to add it to the SELECT, but it's not there yet)
        # We can default to 1.0 or try to find it in summary
        params["leverage"] = summary.get("leverage", 1.0)

    return {
        "run_id": row.id,
        "strategy_name": row.strategy_name,
        "strategy_hash": row.strategy_hash,
        "data_hash": row.data_hash,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "status": row.status,
        "summary": row.summary or {},
        "params": params,
    }


def list_presets(engine: sa.Engine) -> list[dict]:
    """Return all user-saved presets, ordered by updated_at desc."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, name, tag, category, description, explanation, state, created_at, updated_at FROM presets ORDER BY updated_at DESC")
        ).fetchall()
    return [
        {
            "id": r.id,
            "name": r.name,
            "tag": r.tag,
            "category": r.category,
            "description": r.description,
            "explanation": r.explanation,
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


def _clean_preset_state(state: dict) -> dict:
    """General cleanup of the strategy state:
    1. Remove indicators from `datapoints` that are NOT used in `enter` or `exit`.
    2. Ensure basic fields like `risk_enabled` exist (for frontend consistency).
    3. Coerce numeric types.
    """
    if not isinstance(state, dict):
        return state

    # Extract all unique indicator names used in rules
    used_names = {"close", "open", "high", "low", "volume"}  # Built-ins
    
    def walk_rules(rules):
        if not isinstance(rules, list):
            return
        for rule in rules:
            if not rule: 
                continue
            if isinstance(rule, dict):
                if "or" in rule:
                    walk_rules(rule["or"])
                elif "and" in rule:
                    walk_rules(rule["and"])
                elif "left" in rule:
                    # Support dictionary rule format: {"left": "rsi", "op": ">", "right": 70}
                    if isinstance(rule.get("left"), str):
                        used_names.add(rule.get("left"))
                    right = rule.get("right")
                    if isinstance(right, str) and not right.isdigit():
                        try:
                            float(right)
                        except (ValueError, TypeError):
                            used_names.add(right)
            elif isinstance(rule, (list, tuple)) and len(rule) >= 3:
                # Standard format: ["rsi", ">", 70]
                if isinstance(rule[0], str):
                    used_names.add(rule[0])
                if isinstance(rule[2], str) and not rule[2].isdigit():
                    try:
                        float(rule[2])
                    except (ValueError, TypeError):
                        used_names.add(rule[2])

    walk_rules(state.get("enter", []))
    walk_rules(state.get("exit", []))
    walk_rules(state.get("enter_short", []))
    walk_rules(state.get("exit_short", []))

    # 1. Filter datapoints
    datapoints = state.get("datapoints")
    if isinstance(datapoints, list):
        # Only keep datapoints that are actually referenced in the rules
        # OR are special 'built-in' names that the user might want to keep
        state["datapoints"] = [
            dp for dp in datapoints 
            if dp.get("name") in used_names or dp.get("name") in ["close", "open", "high", "low", "volume"]
        ]

    # 2. Risk fields consistency
    # Convert stop loss / take profit from decimal to percentage if they are > 0 and < 1
    # Actually most of the time the state is StrategyFormState (stored from the frontend),
    # where these are already percentages (e.g. 1.5 for 1.5%).
    # We leave them as is unless there's a clear mistake.

    # 3. Handle deprecated fields
    if "chart_period" in state and "freq" not in state:
        state["freq"] = state.pop("chart_period")
    if "chart_start" in state and "start" not in state:
        state["start"] = state.pop("chart_start")
    if "chart_stop" in state and "stop" not in state:
        state["stop"] = state.pop("chart_stop")

    return state


def clean_all_presets(engine: sa.Engine) -> int:
    """Iterate through all presets and apply cleanup logic. Returns count of affected rows."""
    presets = list_presets(engine)
    count = 0
    for p in presets:
        original_json = json.dumps(p["state"], sort_keys=True)
        # Deep copy to avoid in-place modification before comparison
        state_copy = copy.deepcopy(p["state"])
        cleaned = _clean_preset_state(state_copy)
        
        # Also remove presets that have NO conditions and NO name
        is_empty = (not cleaned.get("enter") and not cleaned.get("exit") and not cleaned.get("rules"))
        if is_empty and (not p["name"] or p["name"] == "Unnamed"):
            # Delete useless preset
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM presets WHERE id = :id"), {"id": p["id"]})
                conn.commit()
            count += 1
            continue

        if json.dumps(cleaned, sort_keys=True) != original_json:
            update_preset(engine, p["id"], p["name"], p["tag"], p["category"], p["description"], p.get("explanation", ""), cleaned)
            count += 1
    return count


def list_leaderboard(engine: sa.Engine, limit: int = 50) -> list[dict]:
    """Return top backtest runs ranked by efficiency_score (calculated from return, risk, and time).
    
    To find the 'smartest' strategies, we fetch a larger candidate set (500) sorted by raw return,
    calculate normalized efficiency scores, and then sort the final result by that score.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    r.id,
                    COALESCE(NULLIF(s.name, 'Unnamed'), r.params->>'name') as strategy_name,
                    r.params as raw_params,
                    r.strategy_hash, r.data_hash,
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
                    COALESCE(r.leverage, (r.summary->>'leverage')::float, 1.0) as leverage,
                    r.params->>'explanation' as explanation
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
        # Derive tactic name from params if not set, or if name looks like a generic "SYMBOL FREQ" label
        sname = (r.strategy_name or "").strip()
        _looks_generic = bool(
            not sname
            or __import__("re").fullmatch(r"[A-Z0-9\-]+ \d+[Dhm]", sname)
        )
        if _looks_generic:
            params = r.raw_params if isinstance(r.raw_params, dict) else {}
            sname = _derive_strategy_name(params)
        raw_s = _calc_raw_efficiency(
            r.return_perc or 0,
            r.max_drawdown or 0,
            r.time_in_market or 0,
        )
        all_data.append({"row": r, "raw_score": raw_s, "strategy_name": sname})

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
            "strategy_name": d["strategy_name"],
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
            "explanation": d["row"].explanation,
        }
        for d in top_entries
    ]


def create_preset(engine: sa.Engine, name: str, tag: str, category: str, description: str, explanation: str, state: dict) -> dict:
    """Insert a new preset and return it."""
    state = _clean_preset_state(state)
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO presets (name, tag, category, description, explanation, state)
                VALUES (:name, :tag, :category, :description, :explanation, CAST(:state AS jsonb))
                RETURNING id, created_at, updated_at
            """),
            {"name": name, "tag": tag, "category": category, "description": description, "explanation": explanation, "state": json.dumps(state)},
        ).fetchone()
    return {
        "id": row.id,
        "name": name,
        "tag": tag,
        "category": category,
        "description": description,
        "explanation": explanation,
        "state": state,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def update_preset(engine: sa.Engine, preset_id: int, name: str, tag: str, category: str, description: str, explanation: str, state: dict) -> Optional[dict]:
    """Update an existing preset by id. Returns updated preset or None if not found."""
    state = _clean_preset_state(state)
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                UPDATE presets
                SET name = :name, tag = :tag, category = :category,
                    description = :description, explanation = :explanation,
                    state = CAST(:state AS jsonb), updated_at = NOW()
                WHERE id = :id
                RETURNING id, created_at, updated_at
            """),
            {"id": preset_id, "name": name, "tag": tag, "category": category, "description": description, "explanation": explanation, "state": json.dumps(state)},
        ).fetchone()
    if not row:
        return None
    return {
        "id": row.id,
        "name": name,
        "tag": tag,
        "category": category,
        "description": description,
        "explanation": explanation,
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
def delete_run(engine: sa.Engine, run_id: str) -> bool:
    """Delete a single backtest run and its trades. Returns True if deleted."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM trades WHERE run_id = :id"), {"id": run_id})
        result = conn.execute(text("DELETE FROM backtest_runs WHERE id = :id"), {"id": run_id})
    return result.rowcount > 0


def clear_all_runs(engine: sa.Engine) -> int:
    """Clear all backtest runs and related trade data. Returns count of removed runs."""
    with engine.begin() as conn:
        # Get count before deletion
        res = conn.execute(text("SELECT count(*) FROM backtest_runs")).fetchone()
        count = res[0] if res else 0
        
        # Truncate tables correctly for timescale hypertables or standard SQL
        # CASCADE ensures trades and portfolio_state are also cleaned up if they have FKs
        conn.execute(text("TRUNCATE backtest_runs CASCADE"))
        
    return count
