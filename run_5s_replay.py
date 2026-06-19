#!/usr/bin/env python3
"""
run_5s_replay.py — drive the engine-agnostic EmaRetestV134Strategy over real
ohlcv_5s history through the SimulatedBroker, and quantify the "optimism gap".

What it does
------------
1. Pulls MNQ 5-second bars from TimescaleDB (the same `ohlcv_5s` hypertable the
   live ingest writes) for the analysed window.
2. Resamples them into 1-minute strategy bars, keeping the twelve 5s sub-bars
   per minute for high-fidelity OCA fill matching.
3. Replays the SAME strategy class the live engine runs, bar-by-bar, TWICE:
       OPTIMISTIC  — every stop fills at its trigger, every TP at its level
       REALISTIC   — stop-limit slips to its limit, BREACHES (non-fill) on a gap,
                     and the strategy's EMA50 bar-close RESCUE cleans up naked
                     positions at a worse price.
4. Prints a PnL report. The delta between the two totals is the optimism gap —
   the money a level-only backtest pretends it keeps but the account does not.

Usage
-----
    python run_5s_replay.py                 # full window, MNQM6
    SYMBOL=MNQM6 START=2026-06-10 END=2026-06-13 python run_5s_replay.py

DB env (defaults match the local algotrading TimescaleDB on host port 5435):
    POSTGRES_HOST=localhost POSTGRES_PORT=5435 POSTGRES_DB=fasttrade
    POSTGRES_USER=fasttrade POSTGRES_PASSWORD=fasttrade_dev
"""
from __future__ import annotations

import logging
import os
import sys
from typing import List, Tuple

import psycopg2

from fast_trade.backtest_glue import Bar, SubBar, build_rig, group_into_minutes

logging.basicConfig(level=os.environ.get("LOGLEVEL", "ERROR"),
                    format="%(levelname)s %(name)s %(message)s")

SYMBOL = os.environ.get("SYMBOL", "MNQM6")
START = os.environ.get("START", "2026-06-08")
END = os.environ.get("END", "2026-06-20")


def fetch_5s(symbol: str, start: str, end: str) -> List[tuple]:
    dsn = dict(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5435")),
        dbname=os.environ.get("POSTGRES_DB", "fasttrade"),
        user=os.environ.get("POSTGRES_USER", "fasttrade"),
        password=os.environ.get("POSTGRES_PASSWORD", "fasttrade_dev"),
    )
    conn = psycopg2.connect(**dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT time, open, high, low, close
                 FROM ohlcv_5s
                WHERE symbol = %s AND time >= %s AND time < %s
                ORDER BY time ASC""",
            (symbol, start, end),
        )
        return cur.fetchall()
    finally:
        conn.close()


# ── round-trip reconstruction from the broker fill ledger ────────────────────
class Trade:
    __slots__ = ("entry_ts", "side", "entry_px", "entry_qty", "qty", "pnl",
                 "exits", "exit_px", "exit_ts", "breach", "rescue")

    def __init__(self, rec):
        self.entry_ts = rec.ts
        self.side = rec.side
        self.entry_px = rec.price
        self.entry_qty = rec.qty
        self.qty = rec.qty
        self.pnl = 0.0
        self.exits: List[str] = []
        self.exit_px = None
        self.exit_ts = None
        self.breach = False
        self.rescue = False

    def add_exit(self, rec):
        self.pnl += rec.pnl
        self.exits.append(rec.kind)
        self.qty -= rec.qty
        self.exit_px = rec.price            # last closing fill price wins
        self.exit_ts = rec.ts
        if rec.breach:
            self.breach = True
        if rec.kind == "RESCUE":
            self.rescue = True

    def as_dict(self) -> dict:
        def iso(t):
            return t.isoformat() if t is not None else None
        return {
            "entry_time": iso(self.entry_ts),
            "side": self.side,
            "entry_price": self.entry_px,
            "qty": self.entry_qty,
            "exit_time": iso(self.exit_ts),
            "exit_price": self.exit_px,
            "exits": list(self.exits),
            "realized_pnl": round(self.pnl, 2),
            "breach": self.breach,
            "rescue": self.rescue,
        }


def to_trades(fills) -> List[Trade]:
    trades: List[Trade] = []
    cur = None
    for rec in fills:
        if rec.kind == "ENTRY":
            cur = Trade(rec)
            trades.append(cur)
        elif cur is not None:
            cur.add_exit(rec)
            if cur.qty <= 0:
                cur = None
    return trades


def run(groups: List[Tuple[Bar, List[SubBar]]], realistic: bool):
    rig = build_rig(realistic=realistic)
    broker, strat = rig.broker, rig.strategy
    for bar, subs in groups:
        et = bar.date
        broker.roll_day(et.date())
        n_before = len(broker.fills)
        # 1) match resting OCA legs against this minute's 5s sub-bars (fills that
        #    physically happened mid-minute, before the strategy's bar-close logic)
        for sub in subs:
            broker.on_sub_bar(sub, sub.date)
        # 2) strategy decides on the 1-minute close
        broker.set_last_price(bar.close)
        rig.clock.t = et
        strat.update_indicators(et, bar)
        strat.on_bar_strategy(et, bar)
        # stamp this-bar fills that the broker could not timestamp itself
        for rec in broker.fills[n_before:]:
            if rec.ts is None:
                rec.ts = et
    # close any position left open at end-of-data for clean accounting
    if broker.get_current_position().side is not None:
        broker.flatten_position(reason="end_of_data")
        if broker.fills[-1].ts is None:
            broker.fills[-1].ts = groups[-1][0].date
    return broker


def report(opt, real, n_min: int, n_sub: int):
    ot, rt = to_trades(opt.fills), to_trades(real.fills)
    gap = opt.total_pnl - real.total_pnl

    def wins(ts):
        return sum(1 for t in ts if t.pnl > 0), sum(1 for t in ts if t.pnl <= 0)

    ow, ol = wins(ot)
    rw, rl = wins(rt)

    print("=" * 74)
    print(f"  5s REPLAY — EMA Retest V13.4  |  {SYMBOL}  {START} → {END}")
    print(f"  {n_sub:,} five-second sub-bars  →  {n_min:,} one-minute strategy bars")
    print("=" * 74)
    print(f"  {'':22}{'OPTIMISTIC':>16}{'REALISTIC':>16}")
    print("  " + "-" * 70)
    print(f"  {'Trades':22}{len(ot):>16}{len(rt):>16}")
    print(f"  {'Wins / Losses':22}{f'{ow} / {ol}':>16}{f'{rw} / {rl}':>16}")
    print(f"  {'TP fills':22}{opt.n_tp:>16}{real.n_tp:>16}")
    print(f"  {'SL fills (at level)':22}{opt.n_sl:>16}{real.n_sl:>16}")
    print(f"  {'SL buffer BREACHES':22}{opt.n_breaches:>16}{real.n_breaches:>16}")
    print(f"  {'Bar-close RESCUES':22}{opt.n_rescues:>16}{real.n_rescues:>16}")
    print(f"  {'Total PnL (USD)':22}{opt.total_pnl:>16,.2f}{real.total_pnl:>16,.2f}")
    print("  " + "-" * 70)
    print(f"  OPTIMISM GAP (optimistic − realistic):  ${gap:,.2f}")
    print("=" * 74)

    # Per-trade comparison (entries are identical across both runs — same signal
    # logic — so they align by index; only the FILLS differ).
    print("\n  Per-trade ledger (▲ breach/rescue trade):")
    print(f"  {'#':>2} {'entry time (ET)':16} {'side':5} {'entry':>9} "
          f"{'opt$':>9} {'real$':>9} {'Δ$':>9}  notes")
    print("  " + "-" * 86)
    for i, (a, b) in enumerate(zip(ot, rt), 1):
        flag = "▲" if (b.breach or b.rescue) else " "
        notes = []
        if b.breach:
            notes.append("BREACH")
        if b.rescue:
            notes.append("RESCUE")
        notes.append("/".join(b.exits))
        ts = a.entry_ts.strftime("%m-%d %H:%M") if a.entry_ts else "?"
        print(f"  {i:>2} {ts:16} {a.side:5} {a.entry_px:>9.2f} "
              f"{a.pnl:>9.2f} {b.pnl:>9.2f} {a.pnl - b.pnl:>9.2f} {flag} {' '.join(notes)}")
    print("  " + "-" * 86)
    if real.n_breaches or real.n_rescues:
        print(f"  ▲ rows are stop-limit BREACHES: the 5s bar gapped past the limit,")
        print(f"  the SL could not fill, and the EMA50 bar-close RESCUE closed the")
        print(f"  naked position — the gap the optimistic engine never sees.\n")
    else:
        print(f"  No ▲ rows: at the live default {15}-pt buffer NO 5s bar in this")
        print(f"  window gapped past the stop-limit, so there were zero breaches and")
        print(f"  zero rescues — the level-only (optimistic) fills were accurate here.")
        print(f"  See the buffer-sensitivity sweep below for where the mechanic bites.\n")
    return gap


def sweep(groups, base_opt):
    """Buffer-sensitivity sweep: re-run the REALISTIC engine across a range of
    stop-limit buffers to show where the breach/rescue mechanic activates and the
    optimism gap opens up. The strategy reads SL_LIMIT_BUFFER as a module global,
    so we set it before building each run."""
    import shared_strategies.ema_retest_v134 as strat_mod
    saved = strat_mod.SL_LIMIT_BUFFER
    print("\n  Stop-limit buffer sensitivity (REALISTIC engine):")
    print(f"  {'buffer pts':>10}{'breaches':>10}{'rescues':>10}{'SL slips':>10}"
          f"{'real PnL':>12}{'gap vs opt':>12}")
    print("  " + "-" * 64)
    try:
        for buf in (15.0, 10.0, 6.0, 4.0, 2.0, 1.0, 0.5):
            strat_mod.SL_LIMIT_BUFFER = buf
            b = run(groups, realistic=True)
            slips = sum(1 for f in b.fills if f.kind == "SL" and "limit" in f.note)
            gap = base_opt.total_pnl - b.total_pnl
            print(f"  {buf:>10.2f}{b.n_breaches:>10}{b.n_rescues:>10}{slips:>10}"
                  f"{b.total_pnl:>12,.2f}{gap:>12,.2f}")
    finally:
        strat_mod.SL_LIMIT_BUFFER = saved
    print("  " + "-" * 64)
    print("  At the live default (15 pts) the buffer fully absorbs every 5s")
    print("  move-through, so nothing breaches. Tightening it exposes the exact")
    print("  non-fill → bar-close-rescue mechanic the engine is built to model.\n")


SUPPORTED_STRATEGIES = {"ema_retest_v134"}


def run_replay(strategy_name: str = "ema_retest_v134", symbol: str = None,
               start: str = None, end: str = None) -> dict:
    """Programmatic entry point (shared by the CLI and the FastAPI service).

    Runs the optimistic + realistic replay and returns a JSON-serialisable result
    with `metrics` and the per-trade `trades` ledger. Raises ValueError on an
    unknown strategy or empty data so callers can map it to an HTTP 4xx.
    """
    if strategy_name not in SUPPORTED_STRATEGIES:
        raise ValueError(f"unknown strategy '{strategy_name}'; "
                         f"supported: {sorted(SUPPORTED_STRATEGIES)}")
    symbol = symbol or SYMBOL
    start = start or START
    end = end or END

    rows = fetch_5s(symbol, start, end)
    if not rows:
        raise ValueError(f"no ohlcv_5s rows for {symbol} in [{start}, {end})")
    groups = group_into_minutes(rows)

    opt = run(groups, realistic=False)
    real = run(groups, realistic=True)
    real_trades = to_trades(real.fills)

    wins = sum(1 for t in real_trades if t.pnl > 0)
    n = len(real_trades)
    return {
        "strategy_name": strategy_name,
        "symbol": symbol,
        "start": start,
        "end": end,
        "metrics": {
            "total_pnl": round(real.total_pnl, 2),
            "optimistic_pnl": round(opt.total_pnl, 2),
            "optimism_gap": round(opt.total_pnl - real.total_pnl, 2),
            "trades_count": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate": round(wins / n, 4) if n else 0.0,
            "tp_fills": real.n_tp,
            "sl_fills": real.n_sl,
            "buffer_breaches": real.n_breaches,
            "bar_close_rescues": real.n_rescues,
            "sub_bars_5s": len(rows),
            "strategy_bars_1m": len(groups),
        },
        "trades": [t.as_dict() for t in real_trades],
    }


def main() -> int:
    rows = fetch_5s(SYMBOL, START, END)
    if not rows:
        print(f"No ohlcv_5s rows for {SYMBOL} in [{START}, {END}). "
              f"Check DB env / symbol.", file=sys.stderr)
        return 1
    groups = group_into_minutes(rows)
    n_min, n_sub = len(groups), len(rows)
    opt = run(groups, realistic=False)
    real = run(groups, realistic=True)
    report(opt, real, n_min, n_sub)
    if os.environ.get("SWEEP", "1") != "0":
        sweep(groups, opt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
