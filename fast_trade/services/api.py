"""
FastAPI Strategy Engine Service.

Endpoints
---------
GET  /health                  Liveness probe for Docker / Go backend
POST /backtest                Run a backtest synchronously; returns full JSON result
POST /optimize                Submit an async GA optimisation run; returns task_id
GET  /optimize/{task_id}      Poll optimisation status / retrieve results
GET  /runs/{run_id}           Retrieve a previously stored backtest run by ID
"""
from __future__ import annotations

import uuid
import logging
from typing import Any, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from fast_trade.services.db import (
    get_engine,
    hash_data,
    hash_strategy,
    get_cached_backtest,
    save_backtest_run,
    save_trades,
    upsert_strategy,
    list_presets,
    create_preset,
    update_preset,
    delete_preset,
    list_leaderboard,
)
from fast_trade.services.serializers import backtest_response, summary_to_json
from fast_trade.run_backtest import run_backtest

app = FastAPI(
    title="Fast-Trade Strategy Engine",
    version="2.0.0",
    description=(
        "Backtesting and optimisation service. "
        "Accepts strategy definitions (YAML-as-JSON) from the Go backend, "
        "returns metrics and equity-curve data consumable by the React frontend."
    ),
)

logger = logging.getLogger("fast_trade.api")

# Allow the Go backend and React dev server to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Lazy DB engine (created once per worker process) ─────────────────────────

_engine = None


def _db():
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine


# ── Request / Response models ─────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    strategy: dict = Field(
        ...,
        description=(
            "Strategy definition. Required keys: datapoints, enter, exit. "
            "Optional: symbol, exchange, freq, start, stop, base_balance, comission."
        ),
        examples=[
            {
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "freq": "4h",
                "start": "2023-01-01",
                "stop": "2024-01-01",
                "base_balance": 1000,
                "comission": 0.001,
                "datapoints": [{"name": "rsi", "transformer": "rsi", "args": [14]}],
                "enter": [["rsi", "<", 30]],
                "exit": [["rsi", ">", 70]],
            }
        ],
    )
    use_cache: bool = Field(
        True,
        description="Return a cached result when a completed run with matching hashes exists.",
    )


class OptimizeRequest(BaseModel):
    base_strategy: dict = Field(..., description="Base strategy dict to optimise.")
    evolver_config: dict = Field(
        default_factory=dict,
        description=(
            "PyGAD / evolver configuration overrides. "
            "Keys: num_generations, sol_per_pop, gene_space, fitness_func_name, etc."
        ),
    )


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str                 # pending | running | done | failed | cancelled
    result: Optional[Any] = None


class RunSummaryResponse(BaseModel):
    run_id: str
    strategy_hash: str
    data_hash: str
    status: str
    summary: Optional[dict] = None


class PresetRequest(BaseModel):
    name: str = Field(..., description="Preset display name")
    tag: str = Field("", description="Short label (e.g. Trend, Scalp)")
    category: str = Field("Custom", description="Category grouping")
    description: str = Field("", description="Strategy description")
    state: dict = Field(..., description="StrategyFormState object")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
def health():
    """Liveness probe — always returns 200 when the service is up."""
    return {"status": "ok", "service": "fast-trade-api", "version": "2.0.0"}


@app.post("/backtest", tags=["backtest"])
def run_backtest_endpoint(req: BacktestRequest) -> dict:
    """
    Run a backtest synchronously and return results.

    If `use_cache=true` (default) and a completed run with matching
    strategy + data hashes already exists in TimescaleDB, the cached
    summary is returned immediately (equity_curve and trades will be empty
    in that case — use GET /runs/{run_id} for the full trade log).

    The response shape is designed for direct consumption by the React frontend:
    ```json
    {
      "run_id":       "uuid",
      "cached":       false,
      "summary":      { "return_perc": 12.4, "sharpe_ratio": 1.3, ... },
      "equity_curve": [ { "ts": "...", "equity": 1042.5, "adj_equity": 1038.2, "action": "h" } ],
      "trades":       [ { "date": "...", "adj_account_value_change_perc": 4.25, ... } ]
    }
    ```
    """
    strategy = req.strategy
    engine = _db()

    # Deterministic hashes for cache lookup
    s_hash = hash_strategy(strategy)
    d_hash = hash_data(
        symbol=str(strategy.get("symbol", "")),
        exchange=str(strategy.get("exchange", "")),
        start=str(strategy.get("start", "")),
        end=str(strategy.get("stop", strategy.get("end", ""))),
        freq=str(strategy.get("freq", strategy.get("chart_period", ""))),
    )

    # Cache hit — return without re-running
    if req.use_cache:
        try:
            cached = get_cached_backtest(engine, s_hash, d_hash)
            if cached:
                return {
                    "run_id": cached["run_id"],
                    "cached": True,
                    "summary": summary_to_json(cached["summary"]),
                    "equity_curve": [],
                    "trades": [],
                }
        except Exception:
            pass  # DB unavailable — fall through to live run

    # Run the backtest
    try:
        result = run_backtest(strategy)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    summary: dict = result.get("summary", {})
    df: pd.DataFrame = result.get("df", pd.DataFrame())
    trade_log: pd.DataFrame = result.get("trade_df", result.get("trade_log", pd.DataFrame()))

    run_id = str(uuid.uuid4())

    # Persist to TimescaleDB (best-effort — never fails the HTTP response)
    try:
        clean_summary = summary_to_json(summary)
        clean_strategy = summary_to_json(strategy)
        strategy_id = upsert_strategy(
            engine, strategy.get("name", "unnamed"), clean_strategy
        )
        save_backtest_run(engine, run_id, strategy_id, s_hash, d_hash, clean_summary, clean_strategy)
        save_trades(engine, run_id, trade_log)
    except Exception as exc:
        logger.error(f"Failed to persist backtest {run_id}: {exc}", exc_info=True)

    return backtest_response(run_id, summary, df, trade_log, cached=False)


@app.post("/optimize", response_model=TaskStatusResponse, tags=["optimization"])
def trigger_optimization(req: OptimizeRequest) -> TaskStatusResponse:
    """
    Submit an async genetic-algorithm optimisation run.

    Returns a `task_id` immediately. Poll `GET /optimize/{task_id}` until
    `status == "done"`, then read the `result` field for the best strategy.
    """
    from fast_trade.tasks import app as celery_app

    task = celery_app.send_task(
        "fast_trade.tasks.run_optimization_task",
        kwargs={
            "base_strategy": req.base_strategy,
            "evolver_config": req.evolver_config,
        },
        queue="optimize",
    )
    return TaskStatusResponse(task_id=task.id, status="pending")


@app.get("/optimize/{task_id}", response_model=TaskStatusResponse, tags=["optimization"])
def get_optimization_status(task_id: str) -> TaskStatusResponse:
    """
    Poll the status of a submitted optimisation task.

    Possible statuses: pending | running | done | failed | cancelled
    When `status == "done"`, `result` contains the best strategy dict.
    When `status == "failed"`, `result` contains `{"error": "..."}`.
    """
    from celery.result import AsyncResult
    from fast_trade.tasks import app as celery_app

    ar = AsyncResult(task_id, app=celery_app)
    state_map = {
        "PENDING": "pending",
        "STARTED": "running",
        "SUCCESS": "done",
        "FAILURE": "failed",
        "REVOKED": "cancelled",
    }
    status = state_map.get(ar.state, ar.state.lower())
    payload: Optional[Any] = None
    if ar.state == "SUCCESS":
        payload = ar.result
    elif ar.state == "FAILURE":
        payload = {"error": str(ar.result)}

    return TaskStatusResponse(task_id=task_id, status=status, result=payload)


@app.get("/runs/{run_id}", tags=["backtest"])
def get_run(run_id: str) -> dict:
    """
    Retrieve a stored backtest run by its UUID.

    Returns the summary stored in TimescaleDB.
    (The full equity curve is not re-stored; re-run with use_cache=false to get it.)
    """
    from sqlalchemy import text

    engine = _db()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT r.id, s.name AS strategy_name, r.strategy_hash, r.data_hash,
                       r.started_at, r.finished_at, r.status, r.summary
                FROM backtest_runs r
                LEFT JOIN strategies s ON r.strategy_id = s.id
                WHERE r.id = :run_id
            """),
            {"run_id": run_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    return {
        "run_id": row.id,
        "strategy_name": row.strategy_name,
        "strategy_hash": row.strategy_hash,
        "data_hash": row.data_hash,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "status": row.status,
        "summary": summary_to_json(row.summary or {}),
    }


# ── Presets CRUD ─────────────────────────────────────────────────────────────

@app.get("/presets", tags=["presets"])
def get_presets() -> list[dict]:
    """List all user-saved presets."""
    try:
        return list_presets(_db())
    except Exception:
        return []


@app.get("/leaderboard", tags=["backtest"])
@app.get("/api-strategy/leaderboard", tags=["backtest"])
def get_leaderboard(limit: int = 50) -> list[dict]:
    """Retrieve top-performing backtest runs from TimescaleDB."""
    try:
        return list_leaderboard(_db(), limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/presets", tags=["presets"], status_code=201)
def create_preset_endpoint(req: PresetRequest) -> dict:
    """Create a new preset."""
    try:
        return create_preset(_db(), req.name, req.tag, req.category, req.description, req.state)
    except Exception as exc:
        if "presets_name_idx" in str(exc) or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail=f"Preset named {req.name!r} already exists")
        raise HTTPException(status_code=500, detail=str(exc))


@app.put("/presets/{preset_id}", tags=["presets"])
def update_preset_endpoint(preset_id: int, req: PresetRequest) -> dict:
    """Update an existing preset."""
    result = update_preset(_db(), preset_id, req.name, req.tag, req.category, req.description, req.state)
    if not result:
        raise HTTPException(status_code=404, detail=f"Preset {preset_id} not found")
    return result


@app.delete("/presets/{preset_id}", tags=["presets"])
def delete_preset_endpoint(preset_id: int) -> dict:
    """Delete a preset."""
    if not delete_preset(_db(), preset_id):
        raise HTTPException(status_code=404, detail=f"Preset {preset_id} not found")
    return {"deleted": True}
