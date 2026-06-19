"""
api_server.py — lightweight FastAPI microservice that exposes the 5s replay
engine to the OpenAlgo React UI.

The backtest is CPU-heavy (pandas-style bar crunching + a synchronous psycopg2
pull), so the actual run is dispatched to a worker thread via asyncio.to_thread —
the ASGI event loop stays responsive and this service stays decoupled from the
live trading engine's CPU (it is a standalone process).

Run:
    uvicorn api_server:app --host 0.0.0.0 --port 8001
    # or: python api_server.py

Then from the Vite/React UI (http://localhost:5173):
    POST http://localhost:8001/api/v1/backtest/run
    { "strategy_name": "ema_retest_v134", "start_time": "2026-06-08", "end_time": "2026-06-20" }
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from run_5s_replay import SUPPORTED_STRATEGIES, run_replay

log = logging.getLogger("api_server")

app = FastAPI(
    title="Backtest 5s Replay Service",
    version="1.0.0",
    description="Standalone microservice wrapping the engine-agnostic 5s replay "
                "engine (SimulatedBroker + StrategyContext) for the OpenAlgo UI.",
)

# Allow the typical Vite/React dev origins so the OpenAlgo UI can call us.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# One backtest at a time per worker keeps CPU bounded and predictable; the await
# yields the event loop so health checks / other requests are still served.
_run_lock = asyncio.Lock()


# ── schemas ──────────────────────────────────────────────────────────────────
class BacktestRequest(BaseModel):
    strategy_name: str = Field("ema_retest_v134", examples=["ema_retest_v134"])
    start_time: Optional[str] = Field(None, description="ISO date/time, inclusive (default: full window)")
    end_time: Optional[str] = Field(None, description="ISO date/time, exclusive (default: full window)")
    symbol: Optional[str] = Field(None, description="Contract symbol (default: MNQM6)")


class TradeRow(BaseModel):
    entry_time: Optional[str]
    side: str
    entry_price: float
    qty: int
    exit_time: Optional[str]
    exit_price: Optional[float]
    exits: List[str]
    realized_pnl: float
    breach: bool
    rescue: bool


class Metrics(BaseModel):
    total_pnl: float
    optimistic_pnl: float
    optimism_gap: float
    trades_count: int
    wins: int
    losses: int
    win_rate: float
    tp_fills: int
    sl_fills: int
    buffer_breaches: int
    bar_close_rescues: int
    sub_bars_5s: int
    strategy_bars_1m: int


class BacktestResponse(BaseModel):
    strategy_name: str
    symbol: str
    start: str
    end: str
    metrics: Metrics
    trades: List[TradeRow]


# ── routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "strategies": sorted(SUPPORTED_STRATEGIES)}


@app.post("/api/v1/backtest/run", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest) -> Any:
    if req.strategy_name not in SUPPORTED_STRATEGIES:
        raise HTTPException(
            status_code=422,
            detail=f"unknown strategy '{req.strategy_name}'; "
                   f"supported: {sorted(SUPPORTED_STRATEGIES)}",
        )
    async with _run_lock:
        try:
            # Off-load the blocking/CPU-heavy run so the event loop stays free.
            result = await asyncio.to_thread(
                run_replay,
                strategy_name=req.strategy_name,
                symbol=req.symbol,
                start=req.start_time,
                end=req.end_time,
            )
        except ValueError as e:                       # bad strategy / empty data
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:                         # DB down, etc.
            log.exception("backtest run failed")
            raise HTTPException(status_code=500, detail=f"backtest failed: {e}")
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8001, reload=False)
