"""
Celery Task Definitions — Phase 2 stub.

Workers: backtest-worker, scheduler
Queue:   backtests, optimize

Currently: defines the Celery app and a placeholder task.
Next steps: implement run_backtest_task(), run_optimization_task().
"""
import os
from celery import Celery
from celery.schedules import crontab

broker = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")
backend = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2")

app = Celery("fast_trade", broker=broker, backend=backend)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "fast_trade.tasks.run_backtest_task": {"queue": "backtests"},
        "fast_trade.tasks.run_optimization_task": {"queue": "optimize"},
    },
    beat_schedule={
        # Nightly archive update at 01:00 UTC
        "update-archive-nightly": {
            "task": "fast_trade.tasks.update_archive_task",
            "schedule": crontab(hour=1, minute=0),
        },
    },
)


@app.task(name="fast_trade.tasks.run_backtest_task", bind=True)
def run_backtest_task(self, strategy: dict) -> dict:
    """
    Run a backtest from a strategy dict.
    Saves results to TimescaleDB backtest_runs table.
    """
    from fast_trade.run_backtest import run_backtest
    result = run_backtest(strategy)
    return result.get("summary", {})


@app.task(name="fast_trade.tasks.run_optimization_task", bind=True)
def run_optimization_task(self, evolver_config: dict) -> dict:
    """Genetic algorithm optimization — placeholder."""
    raise NotImplementedError("Optimization task not yet implemented")


@app.task(name="fast_trade.tasks.update_archive_task")
def update_archive_task():
    """Nightly scheduled archive update — placeholder."""
    import logging
    logging.getLogger(__name__).info("update_archive_task triggered (stub)")
