"""
backtest_glue — the thin adapter that lets the engine-agnostic
`EmaRetestV134Strategy` run inside this research repo.

It builds a `StrategyContext` wired to:
  • SimulatedBroker     — the 5s high-fidelity OCA fill venue (this repo)
  • FixedClock          — set to the current strategy bar's timestamp each bar
  • CapturingTelemetry  — records the strategy's events for the report / parity
  • OpenControl         — always live, never halted/disarmed (the backtest default)

It also defines the minimal bar shapes the strategy reads (`.date/.high/.low/
.close`) and the 5s sub-bar shape the broker matches against, plus a helper that
resamples a raw 5s stream into (strategy_bar, [sub_bars]) minute groups.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Tuple

from shared_strategies import registry
from shared_strategies.context import (
    CapturingTelemetry,
    FixedClock,
    OpenControl,
    StrategyContext,
)

from .simulated_broker import SimulatedBroker


@dataclass(frozen=True)
class Bar:
    """Strategy-timeframe bar (1 minute). `date` is tz-aware ET (so .hour gives
    the ET hour the strategy's session checks expect, and .timestamp() the epoch)."""
    date: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class SubBar:
    """A 5-second sub-bar the SimulatedBroker matches OCA legs against."""
    date: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class BacktestRig:
    """Everything one replay run needs, constructed together so the broker's
    fill-callback is wired back into the strategy's reconciliation hook.
    `strategy` is whatever engine-agnostic class the registry resolved — the rig
    is strategy-agnostic; only the registry knows the concrete type."""
    strategy: object
    broker: SimulatedBroker
    clock: FixedClock
    telemetry: CapturingTelemetry
    ctx: StrategyContext


def build_rig(realistic: bool, strategy_name: str = "ema_retest_v134") -> BacktestRig:
    """Assemble strategy + broker + context for one fidelity setting.

    The strategy is resolved from the `shared_strategies` registry by name (id or
    alias) and built via its factory — so any engine-agnostic strategy registered
    there is backtestable with no change here. Raises ValueError on an unknown
    name (the registry message lists what is supported).

    `realistic=False` → OPTIMISTIC (level-only fills, no breaches/rescues).
    `realistic=True`  → HIGH-FIDELITY (stop-limit buffer breach + bar-close rescue).
    """
    spec = registry.get(strategy_name)
    broker = SimulatedBroker(realistic=realistic)
    telemetry = CapturingTelemetry()
    clock = FixedClock(t=datetime(1970, 1, 1))
    control = OpenControl()
    ctx = StrategyContext(broker=broker, telemetry=telemetry, clock=clock, control=control)
    strategy = spec.factory(ctx)
    # Wire the broker's between-bar fills back to the strategy so its local
    # position bookkeeping is reconciled (stand-in for live fill callbacks).
    broker.position_closed_cb = strategy.on_position_closed
    return BacktestRig(strategy=strategy, broker=broker, clock=clock,
                       telemetry=telemetry, ctx=ctx)


def group_into_minutes(rows: Iterable[tuple]) -> List[Tuple[Bar, List[SubBar]]]:
    """Resample an ordered 5s stream into per-minute (Bar, [SubBar]) groups.

    `rows` are (time, open, high, low, close) tuples with tz-aware ET `time`,
    sorted ascending. Each output minute carries the 1-minute OHLC the strategy
    trades on plus the ordered 5s sub-bars the broker fills against.
    """
    groups: List[Tuple[Bar, List[SubBar]]] = []
    cur_key = None
    subs: List[SubBar] = []
    o = h = l = c = None
    minute_dt = None

    def flush():
        if minute_dt is None:
            return
        groups.append((Bar(date=minute_dt, open=o, high=h, low=l, close=c), subs))

    for t, op, hi, lo, cl in rows:
        key = t.replace(second=0, microsecond=0)
        if key != cur_key:
            flush()
            cur_key = key
            minute_dt = key
            subs = []
            o, h, l, c = op, hi, lo, cl
        else:
            h = max(h, hi)
            l = min(l, lo)
            c = cl
        subs.append(SubBar(date=t, open=op, high=hi, low=lo, close=cl))
    flush()
    return groups
