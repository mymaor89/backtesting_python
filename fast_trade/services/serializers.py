"""
React-friendly JSON serializers for backtest results.

Converts pandas DataFrames (equity curve, trade log) into plain JSON arrays
suitable for direct consumption by Recharts, Lightweight Charts, Victory, etc.

All NaN / Inf values are replaced with None so the JSON is always valid.
Numpy scalar types are coerced to Python primitives.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd


# ── Primitive helpers ─────────────────────────────────────────────────────────

def _safe_float(v) -> Optional[float]:
    """Return a clean Python float, or None for NaN / Inf."""
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 6)
    except (TypeError, ValueError):
        return None


def _clean_value(v) -> Any:
    """Recursively sanitise a value for JSON serialisation."""
    if isinstance(v, dict):
        return {k: _clean_value(vv) for k, vv in v.items()}
    if isinstance(v, list):
        return [_clean_value(i) for i in v]
    if hasattr(v, "isoformat"):          # datetime / Timestamp
        return v.isoformat()
    if hasattr(v, "item"):               # numpy scalar → Python primitive
        return _clean_value(v.item())
    if isinstance(v, float):
        return _safe_float(v)
    if isinstance(v, bool):
        return v
    return v


# ── Public serialisers ────────────────────────────────────────────────────────

_SYSTEM_COLS = frozenset([
    "account_value", "adj_account_value", "in_trade", "fee", "aux",
    "adj_account_value_change_perc", "adj_account_value_change",
    "open", "high", "low", "close", "volume", "action",
])

_ACTION_LABELS: dict[str, str] = {
    "e":   "Enter",
    "ae":  "Enter",
    "x":   "Exit",
    "ax":  "Exit",
    "tsl": "Exit (TSL)",
    "h":   "Hold",
}


def equity_curve_to_json(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Convert the backtest DataFrame to an equity-curve JSON array.

    Each point includes price (OHLC), account values, action, and all
    indicator columns so the frontend can render price charts with overlays.

      {
        "ts":         "2024-01-15T04:00:00",
        "equity":     1042.5,
        "adj_equity": 1038.2,
        "action":     "h",
        "close":      45200.0,
        "open":       44800.0,
        "high":       45500.0,
        "low":        44700.0,
        "rsi":        28.4,        // any indicator columns follow
        "fast_ema":   45100.0,
        ...
      }
    """
    if "account_value" not in df.columns:
        return []

    indicator_cols = [c for c in df.columns if c not in _SYSTEM_COLS]

    df = df.copy()
    df.index = pd.to_datetime(df.index)

    records: list[dict] = []
    for ts, row in df.iterrows():
        point: dict[str, Any] = {
            "ts":         ts.isoformat(),
            "equity":     _safe_float(row.get("account_value")),
            "adj_equity": _safe_float(row.get("adj_account_value")),
            "action":     str(row.get("action", "h")),
            "in_trade":   bool(row.get("in_trade", False)),
            "close":      _safe_float(row.get("close")),
            "open":       _safe_float(row.get("open")),
            "high":       _safe_float(row.get("high")),
            "low":        _safe_float(row.get("low")),
        }
        for col in indicator_cols:
            point[col] = _safe_float(row.get(col))
        records.append(point)
    return records


def trade_log_to_json(trade_log_df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Convert the trade log DataFrame to a JSON array.

    Each element represents one completed round-trip trade:
      {
        "date":                          "2024-01-15T04:00:00",
        "close":                         45200.0,
        "adj_account_value":             1042.5,
        "adj_account_value_change":      42.5,
        "adj_account_value_change_perc": 4.25,
        "in_trade":                      false,
        ...
      }
    """
    if trade_log_df is None or (hasattr(trade_log_df, "empty") and trade_log_df.empty):
        return []

    records: list[dict] = []
    for idx, row in trade_log_df.iterrows():
        record: dict[str, Any] = {
            "date": pd.Timestamp(idx).isoformat() if idx is not None else None
        }
        for col in trade_log_df.columns:
            if col == "action":
                raw = str(row[col])
                record[col] = _ACTION_LABELS.get(raw, raw)
            else:
                record[col] = _clean_value(row[col])
        records.append(record)

    return records


def summary_to_json(summary: dict) -> dict[str, Any]:
    """Recursively sanitise a summary dict so it is safe to serialise as JSON."""
    return {k: _clean_value(v) for k, v in summary.items()}


def backtest_response(
    run_id: str,
    summary: dict,
    df: pd.DataFrame,
    trade_log_df: pd.DataFrame,
    cached: bool = False,
) -> dict[str, Any]:
    """
    Assemble the full FastAPI response for a backtest run.

    Shape consumed by the Go backend / React frontend:
    {
      "run_id":       "550e8400-e29b-41d4-a716-446655440000",
      "cached":       false,
      "summary": {
        "return_perc": 12.4,
        "sharpe_ratio": 1.3,
        "max_drawdown": -8.2,
        "num_trades": 47,
        ...
      },
      "equity_curve": [
        { "ts": "2024-01-01T00:00:00", "equity": 1000.0, "adj_equity": 1000.0, "action": "h" },
        ...
      ],
      "trades": [
        { "date": "2024-01-15T04:00:00", "adj_account_value_change_perc": 4.25, ... },
        ...
      ]
    }
    """
    return {
        "run_id": run_id,
        "cached": cached,
        "summary": summary_to_json(summary),
        "equity_curve": equity_curve_to_json(df),
        "trades": trade_log_to_json(trade_log_df),
    }
