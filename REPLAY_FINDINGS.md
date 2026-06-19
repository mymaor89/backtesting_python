# 5s Replay Engine — Findings

Research-side execution environment for the engine-agnostic
`EmaRetestV134Strategy` (from the `algotrading-strategies` shared package),
built entirely inside `backtesting_python`.

## What was built

| Piece | File | Role |
|---|---|---|
| `SimulatedBroker` | `fast_trade/simulated_broker.py` | Implements `AbstractBroker`. 5-second high-fidelity OCA fill matcher: parent market entry, stop-limit SL + limit TP children, stop-limit **buffer-breach → non-fill**, partial reduce + leg resize. |
| Backtest glue | `fast_trade/backtest_glue.py` | Wires `StrategyContext(SimulatedBroker, FixedClock, CapturingTelemetry, OpenControl)`, defines the 1-minute strategy bar + 5s sub-bar shapes, resamples a 5s stream into per-minute groups. |
| Replay runner | `run_5s_replay.py` | Pulls `ohlcv_5s` from TimescaleDB, drives the strategy bar-by-bar, prints the optimistic-vs-realistic PnL report and a buffer-sensitivity sweep. |
| Tests | `test/test_simulated_broker.py` | 10 tests incl. the breach → naked → bar-close rescue path. |

Install: `pip install -e /mnt/projects/algotrading/algotrading-strategies` (done in
`.venv-replay`). Run: `python run_5s_replay.py`. Tests: `pytest test/test_simulated_broker.py`.

## Execution model

- **Strategy bars = 1 minute** (EMA20/50, 30-min retest window — a 1-minute strategy).
- **Fill matching = the twelve 5s sub-bars inside each minute.** For each minute the
  broker first matches resting OCA legs against that minute's 5s sub-bars (fills that
  physically happened intra-minute), *then* the strategy decides on the 1-minute close.
  A position opened at a bar's close is protected from the next bar (standard
  bar-backtest convention).
- A leg is **activated only if price actually reaches its level** (no fantasy fills).
  When both legs are touchable in one 5s bar, the level **nearest the bar open** fills
  first (price travels out from the open), stop wins an exact tie.
- **Realistic SL** fills at the trigger on a graze, **slips to the limit** when the 5s
  bar sweeps the whole buffer band, and **breaches (non-fill)** when the bar *opens*
  past the limit. A breached stop-limit is rejected; the strategy's EMA50 bar-close
  check then **rescues** the naked position at market.
- **Optimistic** is the rosy level-only baseline: every stop fills at its trigger,
  every TP at its level — no slippage, no gaps, no rescues.
- PnL: MNQ = **$2.00 / point / contract**.

## Result (MNQM6, 2026-06-08 → 2026-06-20, 116,991 5s bars → 9,750 1m bars)

```
                              OPTIMISTIC       REALISTIC
  Trades                              12              12
  TP fills                             9               9
  SL fills (at level)                  3               3
  SL buffer BREACHES                   0               0
  Bar-close RESCUES                    0               0
  Total PnL (USD)                 910.50          910.50
  OPTIMISM GAP (optimistic − realistic):  $0.00
```

**Honest headline: at the live default 15-point stop-limit buffer, the optimism gap on
this window is $0.** No 5s bar gapped past the 15-pt buffer, so there were zero breaches
and zero rescues — the level-only fills were accurate here. The previously-assumed
~$3,000 "optimism gap" does **not** reproduce on this sample under a physically-correct
5s matcher; that figure was an artifact of an over-pessimistic fill assumption
(filling every stop at its limit + a wrong-side "stop" booking a fantasy profit),
both of which this engine corrects.

### Where the mechanic *does* bite — buffer sensitivity

```
  buffer pts  breaches   rescues  SL slips    real PnL  gap vs opt
       15.00         0         0         0      910.50        0.00
       10.00         0         0         1      750.50      160.00
        6.00         1         0         0      970.50      -60.00
        2.00         1         0         2      894.50       16.00
        0.50         1         0         2      951.50      -41.00
```

Tightening the buffer toward 0 makes the stop-limit unable to absorb the 5s
move-through: breaches appear at ≤6 pts and SL fills start slipping to the limit. On
this *calm* window the dollar impact stays small and noisy (±$160) — the one breach
that occurs recovers into its take-profit rather than needing a rescue, so no rescue
fires on real bars here. The breach → naked → **rescue** path itself is exercised and
asserted directly in `test/test_simulated_broker.py` (synthetic gap bars): a LONG
rescued at 79 books −$84 vs the −$30 the optimistic engine assumes at the 95 stop.

## Takeaways

1. The engine is faithful and reusable: the *same* strategy class runs here through
   `SimulatedBroker` exactly as it runs live through `IbkrBroker`.
2. The OCA non-fill / bar-close-rescue mechanic is implemented and verified.
3. On real `ohlcv_5s`, the default 15-pt buffer is wide enough that the strategy's
   own trades never breach — so the optimism gap is ~$0 on this window. A larger
   gap requires either a tighter buffer or genuinely gappy sessions; it should be
   re-measured on volatile days (e.g. high-impact news) rather than assumed.
