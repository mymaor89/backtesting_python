"""
Data Ingestor Service.

Fetches OHLCV bars from yfinance (equities / ETFs / crypto via Yahoo Finance)
and writes them to:
  1. TimescaleDB  — `ohlcv` hypertable (primary source of truth)
  2. Bronze lake  — Parquet files at $ARCHIVE_PATH/<exchange>/<symbol>.parquet
                    (keeps compatibility with the existing fast-trade archive)

Run modes
---------
  One-shot   : python -m fast_trade.services.ingestor --once
  Daemon     : python -m fast_trade.services.ingestor          (polls every POLL_INTERVAL_S)

Called programmatically by update_archive_task() in tasks.py:
  from fast_trade.services.ingestor import fetch_and_store_yfinance
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Optional

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ingestor] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", "/data/lake/bronze")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://fasttrade:fasttrade_dev@timescaledb:5432/fasttrade",
)
POLL_INTERVAL_S = int(os.getenv("INGESTOR_POLL_INTERVAL", "300"))  # 5 min default

# Symbols to ingest: "EXCHANGE:SYMBOL:YFINANCE_TICKER:INTERVAL"
# Override via INGEST_SYMBOLS env var (comma-separated same format)
_DEFAULT_SYMBOLS = [
    "yfinance:BTCUSD:BTC-USD:1h",
    "yfinance:ETHUSD:ETH-USD:1h",
    "yfinance:SPY:SPY:1d",
    "yfinance:QQQ:QQQ:1d",
]


def _parse_symbols() -> list[dict]:
    raw = os.getenv("INGEST_SYMBOLS", ",".join(_DEFAULT_SYMBOLS))
    result = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) < 4:
            log.warning("Skipping malformed INGEST_SYMBOLS entry: %r", entry)
            continue
        result.append(
            {
                "exchange": parts[0],
                "symbol": parts[1],
                "ticker": parts[2],
                "interval": parts[3],
            }
        )
    return result


# ── yfinance fetch ─────────────────────────────────────────────────────────────

def _yf_interval_to_period(interval: str) -> str:
    """Map a yfinance interval string to an appropriate default period."""
    mapping = {
        "1m": "7d",
        "2m": "60d",
        "5m": "60d",
        "15m": "60d",
        "30m": "60d",
        "60m": "730d",
        "1h": "730d",
        "90m": "60d",
        "1d": "max",
        "5d": "max",
        "1wk": "max",
        "1mo": "max",
        "3mo": "max",
    }
    return mapping.get(interval, "max")


def fetch_ohlcv_yfinance(
    ticker: str,
    interval: str = "1h",
    period: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch OHLCV data from Yahoo Finance via yfinance.

    Returns a DataFrame indexed by UTC timestamp with columns:
      open, high, low, close, volume
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance is not installed. Add it to the Dockerfile.")

    if period is None and start is None:
        period = _yf_interval_to_period(interval)

    yf_kwargs: dict = {"interval": interval, "auto_adjust": True, "progress": False}
    if start:
        yf_kwargs["start"] = start
    if end:
        yf_kwargs["end"] = end
    if period and not start:
        yf_kwargs["period"] = period

    raw = yf.download(ticker, **yf_kwargs)

    if raw.empty:
        log.warning("yfinance returned no data for ticker=%r interval=%r", ticker, interval)
        return pd.DataFrame()

    # Flatten MultiIndex columns produced by yfinance ≥ 0.2
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw.columns = [c.lower() for c in raw.columns]

    # Keep only OHLCV
    ohlcv_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in raw.columns]
    df = raw[ohlcv_cols].copy()

    # Ensure UTC-aware index
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "date"

    # Drop rows with NaN close
    df = df.dropna(subset=["close"])

    return df


# ── TimescaleDB write ─────────────────────────────────────────────────────────

def _write_to_timescaledb(
    df: pd.DataFrame,
    symbol: str,
    exchange: str,
    engine,
) -> int:
    """
    Upsert OHLCV rows into the TimescaleDB `ohlcv` hypertable.
    Returns the number of rows written.
    """
    from sqlalchemy import text

    if df.empty:
        return 0

    rows = []
    for ts, row in df.iterrows():
        rows.append(
            {
                "ts": ts,
                "symbol": symbol,
                "exchange": exchange,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0) or 0),
            }
        )

    # Batch upsert
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO ohlcv (ts, symbol, exchange, open, high, low, close, volume)
                VALUES (:ts, :symbol, :exchange, :open, :high, :low, :close, :volume)
                ON CONFLICT (ts, symbol, exchange) DO UPDATE
                    SET open   = EXCLUDED.open,
                        high   = EXCLUDED.high,
                        low    = EXCLUDED.low,
                        close  = EXCLUDED.close,
                        volume = EXCLUDED.volume
            """),
            rows,
        )

    return len(rows)


# ── Parquet (bronze lake) write ───────────────────────────────────────────────

def _write_to_parquet(df: pd.DataFrame, symbol: str, exchange: str) -> str:
    """
    Write / merge OHLCV data into the bronze lake parquet file.
    Returns the parquet file path.
    """
    from fast_trade.archive.db_helpers import update_klines_to_db

    # update_klines_to_db expects a naive-index DataFrame
    df_naive = df.copy()
    if df_naive.index.tzinfo is not None:
        df_naive.index = df_naive.index.tz_localize(None)

    path = update_klines_to_db(df_naive, symbol, exchange)
    return path


# ── Public entry point (called by update_archive_task) ───────────────────────

def fetch_and_store_yfinance(symbols: Optional[list[dict]] = None) -> dict:
    """
    Fetch latest bars for all configured symbols and persist them.

    Returns a status dict: { "EXCHANGE:SYMBOL": "ok" | "error: ..." }
    """
    from fast_trade.services.db import get_worker_engine

    engine = get_worker_engine()
    if symbols is None:
        symbols = _parse_symbols()

    status: dict[str, str] = {}

    for cfg in symbols:
        key = f"{cfg['exchange']}:{cfg['symbol']}"
        try:
            df = fetch_ohlcv_yfinance(cfg["ticker"], interval=cfg["interval"])
            if df.empty:
                status[key] = "no_data"
                continue

            n = _write_to_timescaledb(df, cfg["symbol"], cfg["exchange"], engine)
            _write_to_parquet(df, cfg["symbol"], cfg["exchange"])
            log.info("Fetched %d bars for %s", n, key)
            status[key] = "ok"
        except Exception as exc:
            log.exception("Failed to ingest %s", key)
            status[key] = f"error: {exc}"

    return status


# ── Daemon / one-shot entrypoint ──────────────────────────────────────────────

def main(once: bool = False) -> None:
    symbols = _parse_symbols()

    log.info(
        "Ingestor starting | archive=%s | db=%s | symbols=%d | interval=%ds",
        ARCHIVE_PATH,
        DATABASE_URL.split("@")[-1],  # hide credentials
        len(symbols),
        POLL_INTERVAL_S,
    )

    while True:
        try:
            results = fetch_and_store_yfinance(symbols)
            for key, status in results.items():
                log.info("  %-30s  %s", key, status)
        except Exception:
            log.exception("Ingestor cycle failed")

        if once:
            break

        log.info("Sleeping %ds until next fetch …", POLL_INTERVAL_S)
        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast-Trade OHLCV ingestor")
    parser.add_argument(
        "--once", action="store_true", help="Fetch once and exit (no daemon loop)"
    )
    args = parser.parse_args()
    main(once=args.once)
