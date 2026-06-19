"""
SimulatedBroker — research-side execution venue for the engine-agnostic
strategies in the `algotrading-strategies` package.

It implements the SAME `AbstractBroker` contract the live `IbkrBroker` does, so
`EmaRetestV134Strategy` runs here unchanged. The whole point of this module is
the *fill realism*: a naive bar backtest assumes every protective leg fills at
its level, which quietly overstates PnL. This broker instead matches the OCA
bracket legs against the **5-second sub-bars** that make up each strategy bar and
reproduces the one failure mode that costs real money on MNQ:

    STOP-LIMIT BUFFER BREACH
    ------------------------
    The strategy's stop loss is a STOP-LIMIT (stop = EMA50, limit = stop ∓
    SL_LIMIT_BUFFER). If price gaps clean through the limit floor inside a 5s
    sub-bar, a stop-limit CANNOT fill (you would have to trade outside the limit)
    → the leg is REJECTED / NON-FILL and the position is left naked. On the next
    strategy-bar close the strategy's EMA50 check calls flatten_position() — the
    BAR-CLOSE MARKET RESCUE — closing at a materially worse price than the stop.

Run the broker in two fidelities to quantify the cost of that mechanic:

    realistic=False  (OPTIMISTIC)  every SL fills at its stop trigger, TP at its
                                   limit. No slippage, no gaps, no rescues. This
                                   is the rosy number a level-only backtest prints.
    realistic=True   (HIGH-FIDELITY) SL slips to the limit on a normal through-
                                   trade, BREACHES (non-fill) on a gap, and the
                                   strategy's bar-close rescue cleans up. This is
                                   what the account actually experiences.

The gap between the two totals is the "optimism gap".

Contract notes honoured (see AbstractBroker):
  * methods are side-effect-honest — a claimed fill updates get_current_position()
  * the parent is a MARKET order: it fills immediately at last_price on submit
  * children are inactive until the parent fills (here: the parent fills on
    submit, so children go live the same instant and are matched from the NEXT
    sub-bar fed in — standard bar-backtest convention, documented in the runner)
  * modify_order never raises on a dead leg; it returns False
  * a fill of any protective leg cancels its OCA sibling
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from shared_strategies.broker import (
    AbstractBroker,
    AccountState,
    BracketHandle,
    Position,
    Side,
)

log = logging.getLogger("fast_trade.simulated_broker")

# MNQ (Micro E-mini Nasdaq-100) is $2.00 per index point per contract.
MNQ_POINT_VALUE = 2.0


@dataclass
class _Leg:
    """A resting OCA child (protective stop-limit SL or limit TP)."""
    order_id: int
    kind: str               # "SL" | "TP"
    action: str             # "SELL" (protect a LONG) | "BUY" (protect a SHORT)
    qty: int
    limit: float            # SL: the stop-limit floor/ceiling; TP: the limit price
    stop: Optional[float] = None   # SL only: the stop trigger
    live: bool = True
    breached: bool = False  # SL only: triggered but gapped past the limit (working, unfilled)


@dataclass
class FillRecord:
    """One execution, for the PnL ledger / report."""
    ts: Any
    kind: str               # ENTRY | TP | SL | RESCUE | REDUCE | FLATTEN | SESSION_END
    side: str               # LONG | SHORT (the position's direction)
    action: str             # BUY | SELL (this execution's direction)
    qty: int
    price: float
    pnl: float              # realized USD on this execution (0 for an entry)
    note: str = ""
    breach: bool = False


class SimulatedBroker(AbstractBroker):
    """5s high-fidelity OCA fill simulator. Implements AbstractBroker."""

    def __init__(
        self,
        *,
        realistic: bool = True,
        point_value: float = MNQ_POINT_VALUE,
        position_closed_cb: Optional[Callable[[str, float, float, int], None]] = None,
    ) -> None:
        self.realistic = realistic
        self.point_value = point_value
        # Wired by the runner to strategy.on_position_closed so the strategy's
        # local bookkeeping (st.side) is cleared when the BROKER closes a position
        # out from under it (an OCA leg filling between strategy bars). This is the
        # backtest stand-in for the live engine's fill callbacks.
        self.position_closed_cb = position_closed_cb

        # ── position state (broker-authoritative) ─────────────────────────
        self._side: Optional[Side] = None
        self._qty: int = 0
        self._avg: Optional[float] = None

        # ── resting OCA legs ──────────────────────────────────────────────
        self._legs: List[_Leg] = []
        self._oca_group: Optional[str] = None
        self._ids = itertools.count(1)

        # ── market / account ──────────────────────────────────────────────
        self._last_price: Optional[float] = None
        self._daily_pnl: float = 0.0
        self._daily_trades: int = 0
        self._cur_day = None

        # ── reporting ledgers ─────────────────────────────────────────────
        self.fills: List[FillRecord] = []
        self.total_pnl: float = 0.0
        self.n_entries: int = 0
        self.n_tp: int = 0
        self.n_sl: int = 0
        self.n_breaches: int = 0
        self.n_rescues: int = 0

    # ════════════════════════════════════════════════════════════════════
    #  Runner-facing hooks (NOT part of AbstractBroker)
    # ════════════════════════════════════════════════════════════════════
    def roll_day(self, day) -> None:
        """Reset per-day risk counters at the first bar of a new ET day."""
        if self._cur_day != day:
            self._cur_day = day
            self._daily_pnl = 0.0
            self._daily_trades = 0

    def set_last_price(self, price: float) -> None:
        self._last_price = price

    def on_sub_bar(self, sub: Any, ts: Any) -> None:
        """Match resting OCA legs against ONE incoming 5s sub-bar.

        `sub` is any object exposing .open/.high/.low/.close. Called by the runner
        for every 5s bar inside a strategy bar, BEFORE the strategy sees that
        strategy bar — so an OCA fill that physically happened mid-minute is
        reflected (and the strategy's bar-close rescue only fires when it truly
        did not fill).

        Resolution is physically grounded:
          • a leg is ACTIVATED only if the bar's price range actually reaches its
            level (no fantasy fills on levels price never touched);
          • when BOTH legs are touchable in the same 5s bar, the one whose level
            is nearest the bar's OPEN fills first (price travels out from the
            open), with the stop winning an exact tie (conservative);
          • the realistic SL slips to its limit ONLY when the bar genuinely sweeps
            through the buffer band, and BREACHES (non-fill → reject → bar-close
            rescue) only when the bar OPENS past the limit (a true gap-through).
        """
        self._last_price = sub.close
        if self._side is None:
            return
        sl = next((l for l in self._legs if l.kind == "SL" and l.live), None)
        tp = next((l for l in self._legs if l.kind == "TP" and l.live), None)

        cands = []  # (dist_to_open, is_sl, leg, fill_price_or_None_for_breach, note)
        if sl is not None:
            act = self._eval_sl(sl, sub)
            if act is not None:
                fill, note = act
                cands.append((abs(sl.stop - sub.open), True, sl, fill, note))
        if tp is not None:
            t = tp.limit
            touched = sub.high >= t if self._side is Side.LONG else sub.low <= t
            if touched:
                cands.append((abs(t - sub.open), False, tp, t, ""))

        if not cands:
            return
        # nearest level to the open fills first; stop wins an exact-distance tie
        cands.sort(key=lambda c: (c[0], not c[1]))
        _, is_sl, leg, fill, note = cands[0]
        if is_sl and fill is None:
            # buffer breach: stop-limit rejected, position left naked. The
            # strategy's EMA50 bar-close check will RESCUE it next bar.
            self._mark_breach(leg, sub, ts)
            # if the TP was ALSO swept in this same bar (price ran clean through
            # both), it still fills — the naked window simply didn't last.
            if tp is not None and tp.live:
                t = tp.limit
                if (sub.high >= t if self._side is Side.LONG else sub.low <= t):
                    self._fill_leg(tp, t, "TP", ts)
            return
        self._fill_leg(leg, fill, "SL" if is_sl else "TP", ts, note=note)

    def _eval_sl(self, sl: _Leg, sub: Any):
        """Return (fill_price, note) if the SL is activated by this sub-bar, or
        (None, ...) for a realistic breach, or None if not activated.

        Optimistic (realistic=False) is the rosy level-only baseline: a triggered
        stop always fills at its trigger, ignoring gaps. Realistic is data-driven:
        it fills at the trigger on a graze, slips to the limit when the bar sweeps
        the whole band, and cannot fill (breach) when the bar opens past the limit.
        """
        S, L = sl.stop, sl.limit
        if self._side is Side.LONG:                 # SELL stop-limit, L < S
            if sub.low > S:
                return None                         # stop not reached
            if not self.realistic:
                return (S, "")
            if sub.open <= L:
                return (None, "")                   # gapped open below limit → breach
            if sub.low <= L:
                return (L, "swept band → fill at limit")
            return (S, "")                          # grazed the stop only
        else:                                       # SHORT: BUY stop-limit, L > S
            if sub.high < S:
                return None
            if not self.realistic:
                return (S, "")
            if sub.open >= L:
                return (None, "")                   # gapped open above limit → breach
            if sub.high >= L:
                return (L, "swept band → fill at limit")
            return (S, "")

    def _mark_breach(self, sl: _Leg, sub: Any, ts: Any) -> None:
        # Reject the stop-limit (live=False) but keep it in the book so flatten()
        # can see it was breached and classify the close as a RESCUE. A rejected
        # leg cannot refill — the bar-close rescue is the only way out.
        if not sl.breached:
            sl.breached = True
            sl.live = False
            self.n_breaches += 1
            log.warning(f"SL BUFFER BREACH stop={sl.stop} limit={sl.limit} "
                        f"open={sub.open} side={self._side.value} — NON-FILL, naked")

    # ════════════════════════════════════════════════════════════════════
    #  AbstractBroker — connection / market
    # ════════════════════════════════════════════════════════════════════
    def is_connected(self) -> bool:
        return True

    @property
    def last_price(self) -> Optional[float]:
        return self._last_price

    # ════════════════════════════════════════════════════════════════════
    #  AbstractBroker — execution
    # ════════════════════════════════════════════════════════════════════
    def submit_oca_bracket(self, side: Side, qty: int, sl_trigger: float,
                           sl_limit: float, tp_price: Optional[float] = None) -> BracketHandle:
        # Parent is MARKET → fills immediately at the current price.
        fill = self._last_price
        if fill is None:
            raise RuntimeError("submit_oca_bracket before any price was seen")
        self._side = side
        self._qty = qty
        self._avg = fill
        self._daily_trades += 1
        self.n_entries += 1

        parent_id = next(self._ids)
        self._oca_group = f"SIM_OCA_{parent_id}"
        sl_action = side.exit_action

        sl_leg = _Leg(order_id=next(self._ids), kind="SL", action=sl_action,
                      qty=qty, limit=sl_limit, stop=sl_trigger)
        self._legs = [sl_leg]
        tp_id: Optional[int] = None
        if tp_price is not None:
            tp_leg = _Leg(order_id=next(self._ids), kind="TP", action=sl_action,
                          qty=qty, limit=tp_price)
            self._legs.append(tp_leg)
            tp_id = tp_leg.order_id

        self.fills.append(FillRecord(ts=None, kind="ENTRY", side=side.value,
                                     action=side.entry_action, qty=qty, price=fill,
                                     pnl=0.0, note=f"sl_stop={sl_trigger} sl_limit={sl_limit} tp={tp_price}"))
        log.info(f"SIM ENTRY {side.value} qty={qty} @ {fill} sl={sl_trigger}/{sl_limit} tp={tp_price}")
        return BracketHandle(oca_group=self._oca_group, parent_id=parent_id,
                             sl_id=sl_leg.order_id, tp_id=tp_id)

    def modify_order(self, order_id: int, *, total_qty: Optional[int] = None,
                     limit_price: Optional[float] = None,
                     stop_price: Optional[float] = None) -> bool:
        leg = next((l for l in self._legs if l.order_id == order_id and l.live), None)
        if leg is None:
            return False                            # dead leg — benign per contract
        if total_qty is not None:
            leg.qty = total_qty
        if limit_price is not None:
            leg.limit = limit_price
        if stop_price is not None:
            leg.stop = stop_price
        return True

    def reduce_position(self, qty: int, reason: str = "") -> bool:
        """Standalone MARKET partial close (the runner/peel). OUTSIDE the OCA
        group — the caller resizes the resting legs via modify_order()."""
        if self._side is None or qty <= 0:
            return False
        qty = min(qty, self._qty)
        price = self._last_price
        pnl = self._realized(price, qty)
        self.fills.append(FillRecord(ts=None, kind="REDUCE", side=self._side.value,
                                     action=self._side.exit_action, qty=qty, price=price,
                                     pnl=pnl, note=reason))
        self._qty -= qty
        self._book(pnl)
        if self._qty <= 0:
            self._go_flat(price, "REDUCE", reason)
        return True

    def flatten_position(self, reason: str = "manual", price: Optional[float] = None) -> None:
        """Cancel every resting leg, then close the whole position at market.
        Idempotent when flat. This is where the BAR-CLOSE RESCUE lands."""
        if self._side is None:
            return
        px = price if price is not None else self._last_price
        qty = self._qty
        pnl = self._realized(px, qty)
        breached = any(l.kind == "SL" and l.breached for l in self._legs)
        kind = "RESCUE" if (reason == "ema_stop" and breached) else (
            "SESSION_END" if reason == "session_end" else "FLATTEN")
        if kind == "RESCUE":
            self.n_rescues += 1
        self.fills.append(FillRecord(ts=None, kind=kind, side=self._side.value,
                                     action=self._side.exit_action, qty=qty, price=px,
                                     pnl=pnl, note=reason, breach=breached))
        self._book(pnl)
        log.info(f"SIM {kind} {self._side.value} qty={qty} @ {px} pnl={pnl:.2f} reason={reason}")
        self._go_flat(px, kind, reason)

    def is_order_live(self, order_id: int) -> bool:
        return any(l.order_id == order_id and l.live for l in self._legs)

    # ════════════════════════════════════════════════════════════════════
    #  AbstractBroker — state
    # ════════════════════════════════════════════════════════════════════
    def get_current_position(self) -> Position:
        return Position(side=self._side, qty=max(self._qty, 0), avg_price=self._avg)

    def get_account_state(self) -> AccountState:
        open_orders = sum(1 for l in self._legs if l.live)
        return AccountState(daily_pnl=self._daily_pnl, daily_trades=self._daily_trades,
                            open_orders=open_orders, last_price=self._last_price)

    # ════════════════════════════════════════════════════════════════════
    #  internals
    # ════════════════════════════════════════════════════════════════════
    def _fill_leg(self, leg: _Leg, price: float, kind: str, ts: Any, note: str = "") -> None:
        """A protective leg filled → close that qty and cancel the OCA sibling."""
        qty = min(leg.qty, self._qty)
        pnl = self._realized(price, qty)
        self.fills.append(FillRecord(ts=ts, kind=kind, side=self._side.value,
                                     action=leg.action, qty=qty, price=price,
                                     pnl=pnl, note=note))
        if kind == "TP":
            self.n_tp += 1
        elif kind == "SL":
            self.n_sl += 1
        self._book(pnl)
        log.info(f"SIM {kind} {self._side.value} qty={qty} @ {price} pnl={pnl:.2f} {note}")
        self._qty -= qty
        leg.live = False
        if self._qty <= 0:
            self._go_flat(price, kind, note)

    def _realized(self, exit_price: float, qty: int) -> float:
        if self._avg is None or self._side is None:
            return 0.0
        diff = exit_price - self._avg
        if self._side is Side.SHORT:
            diff = -diff
        return diff * qty * self.point_value

    def _book(self, pnl: float) -> None:
        self._daily_pnl += pnl
        self.total_pnl += pnl

    def _go_flat(self, price: float, kind: str, reason: str) -> None:
        side = self._side.value if self._side else None
        # cancel all resting legs (OCA teardown)
        for l in self._legs:
            l.live = False
        self._legs = []
        self._oca_group = None
        self._side = None
        self._qty = 0
        self._avg = None
        if self.position_closed_cb is not None and side is not None:
            # notify the strategy so its local st.side is cleared (live-engine
            # fill-callback stand-in). pnl arg unused by the strategy.
            self.position_closed_cb(side, price, 0.0, 0)
