"""
Celery Task Definitions — Fast-Trade Strategy Engine.

Workers
-------
  backtest-worker  — queue: backtests, optimize
  scheduler        — Celery Beat, runs update_archive_task nightly

Queues
------
  backtests  — synchronous backtest runs triggered from the API
  optimize   — long-running GA optimisation jobs
"""
from __future__ import annotations

import logging
import os
import uuid

from celery import Celery
from celery.schedules import crontab

log = logging.getLogger(__name__)

# ── Celery app ────────────────────────────────────────────────────────────────

broker = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")
backend = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2")

app = Celery("fast_trade", broker=broker, backend=backend)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Route tasks to the correct queues
    task_routes={
        "fast_trade.tasks.run_backtest_task": {"queue": "backtests"},
        "fast_trade.tasks.run_optimization_task": {"queue": "optimize"},
        "fast_trade.tasks.update_archive_task": {"queue": "backtests"},
    },
    # Celery Beat schedule
    beat_schedule={
        "update-archive-nightly": {
            "task": "fast_trade.tasks.update_archive_task",
            "schedule": crontab(hour=1, minute=0),
        },
    },
    # Prevent result expiry for optimisation jobs (they can run for minutes)
    result_expires=86400,  # 24 h
)


# ── Task: run_backtest_task ───────────────────────────────────────────────────

@app.task(
    name="fast_trade.tasks.run_backtest_task",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def run_backtest_task(self, strategy: dict) -> dict:
    """
    Run a backtest from a strategy dict, persist results to TimescaleDB,
    and return the summary.

    Parameters
    ----------
    strategy : dict
        Full strategy definition (same shape as POST /backtest).

    Returns
    -------
    dict
        {"run_id": str, "summary": dict}
    """
    from fast_trade.run_backtest import run_backtest
    from fast_trade.services.db import (
        get_worker_engine,
        hash_strategy,
        hash_data,
        get_cached_backtest,
        save_backtest_run,
        save_trades,
        upsert_strategy,
    )

    engine = get_worker_engine()

    s_hash = hash_strategy(strategy)
    d_hash = hash_data(
        symbol=str(strategy.get("symbol", "")),
        exchange=str(strategy.get("exchange", "")),
        start=str(strategy.get("start", "")),
        end=str(strategy.get("stop", strategy.get("end", ""))),
        freq=str(strategy.get("freq", strategy.get("chart_period", ""))),
    )

    # Check cache first — workers honour the same cache as the API
    cached = get_cached_backtest(engine, s_hash, d_hash)
    if cached:
        log.info("Cache hit for strategy_hash=%s", s_hash[:12])
        return {"run_id": cached["run_id"], "summary": cached["summary"], "cached": True}

    try:
        result = run_backtest(strategy)
    except Exception as exc:
        log.exception("Backtest failed: %s", exc)
        raise self.retry(exc=exc)

    summary: dict = result.get("summary", {})
    trade_log = result.get("trade_log")

    run_id = str(uuid.uuid4())

    try:
        strategy_id = upsert_strategy(engine, strategy.get("name", "unnamed"), strategy)
        save_backtest_run(engine, run_id, strategy_id, s_hash, d_hash, summary, strategy)
        save_trades(engine, run_id, trade_log)
    except Exception:
        log.exception("Failed to persist backtest run %s to TimescaleDB", run_id)

    return {"run_id": run_id, "summary": summary, "cached": False}


# ── Task: run_optimization_task ───────────────────────────────────────────────

@app.task(
    name="fast_trade.tasks.run_optimization_task",
    bind=True,
    # Optimisations can run for several minutes — no auto-retry
    time_limit=1800,
    soft_time_limit=1700,
)
def run_optimization_task(self, base_strategy: dict, evolver_config: dict) -> dict:
    """
    Run a genetic-algorithm optimisation over a base strategy.

    Parameters
    ----------
    base_strategy : dict
        Strategy definition used as the optimisation template.
    evolver_config : dict
        Overrides passed to ml/evolver.py::optimize_strategy().
        Common keys: num_generations, sol_per_pop, gene_space, target_metric.

    Returns
    -------
    dict
        {"best_strategy": dict, "best_fitness": float, "generations_run": int}
    """
    from fast_trade.ml.evolver import optimize_strategy

    log.info(
        "Starting GA optimisation: generations=%s, pop=%s",
        evolver_config.get("num_generations", "default"),
        evolver_config.get("sol_per_pop", "default"),
    )

    # Build genes list from gene_space: [(name, {low, high, ...}), ...]
    # gene_space dict values can be a range dict or a discrete list.
    gene_space = evolver_config.get("gene_space", {})
    genes = [(name, space) for name, space in gene_space.items()]

    best_strategy, best_fitness = optimize_strategy(
        base_strategy,
        genes,
        num_generations=evolver_config.get("num_generations", 50),
        sol_per_pop=evolver_config.get("sol_per_pop", 20),
    )

    log.info("GA optimisation complete. Best fitness: %s", best_fitness)

    return {
        "best_strategy": best_strategy,
        "best_fitness": float(best_fitness) if best_fitness is not None else None,
        "generations_run": evolver_config.get("num_generations", 50),
    }


# ── Task: update_archive_task ─────────────────────────────────────────────────

@app.task(name="fast_trade.tasks.update_archive_task")
def update_archive_task() -> dict:
    """
    Nightly scheduled task: fetch new OHLCV bars from all configured
    sources (yfinance, Binance, Coinbase) and write them to TimescaleDB
    and the bronze data-lake parquet files.
    """
    import importlib
    import traceback

    results: dict[str, str] = {}

    sources = [
        ("yfinance", "fast_trade.services.ingestor", "fetch_and_store_yfinance"),
        ("binance", "fast_trade.archive.binance_api", "update_binance_archive"),
        ("coinbase", "fast_trade.archive.coinbase_api", "update_coinbase_archive"),
    ]

    for name, module_path, func_name in sources:
        try:
            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name, None)
            if fn is None:
                results[name] = "not_implemented"
                continue
            fn()
            results[name] = "ok"
        except Exception:
            log.exception("Archive update failed for source: %s", name)
            results[name] = f"error: {traceback.format_exc(limit=1)}"

    log.info("Archive update complete: %s", results)
    return results
