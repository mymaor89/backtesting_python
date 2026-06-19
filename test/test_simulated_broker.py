"""
Tests for the 5s high-fidelity SimulatedBroker — focused on the OCA fill matcher
and, above all, the STOP-LIMIT BUFFER BREACH → naked-position → bar-close RESCUE
path that the real-data replay does not happen to force on the calm sample window.

PnL convention: MNQ = $2.00 / point / contract (the broker's default point_value).
"""
from collections import namedtuple

import pytest

from fast_trade.simulated_broker import SimulatedBroker
from shared_strategies.broker import Side

# minimal 5s sub-bar shape the broker reads (.open/.high/.low/.close)
SB = namedtuple("SB", "open high low close")


def _broker(realistic=True, last=100.0):
    closed = []
    b = SimulatedBroker(realistic=realistic,
                        position_closed_cb=lambda *a: closed.append(a))
    b.set_last_price(last)
    b._closed_calls = closed
    return b


# ── take-profit ──────────────────────────────────────────────────────────────
def test_tp_fills_at_limit_and_closes_long():
    b = _broker(last=100.0)
    h = b.submit_oca_bracket(Side.LONG, 2, sl_trigger=95.0, sl_limit=85.0, tp_price=110.0)
    b.on_sub_bar(SB(101, 111, 100, 110), ts=1)        # high sweeps the TP
    assert b.get_current_position().side is None        # flat
    assert b.n_tp == 1 and b.n_sl == 0
    assert b.total_pnl == pytest.approx((110 - 100) * 2 * 2)  # +$40
    assert not b.is_order_live(h.sl_id)                 # OCA sibling cancelled


# ── clean stop graze vs full band sweep ───────────────────────────────────────
def test_sl_graze_fills_at_trigger():
    b = _broker(last=100.0)
    b.submit_oca_bracket(Side.LONG, 2, sl_trigger=95.0, sl_limit=85.0, tp_price=120.0)
    b.on_sub_bar(SB(99, 99, 94, 96), ts=1)             # dips to 94: past stop, above limit
    assert b.total_pnl == pytest.approx((95 - 100) * 2 * 2)   # filled at 95 → -$20


def test_realistic_band_sweep_slips_to_limit():
    b = _broker(realistic=True, last=100.0)
    b.submit_oca_bracket(Side.LONG, 2, sl_trigger=95.0, sl_limit=85.0, tp_price=120.0)
    b.on_sub_bar(SB(99, 99, 84, 86), ts=1)             # sweeps through the whole band
    assert b.total_pnl == pytest.approx((85 - 100) * 2 * 2)   # filled at limit 85 → -$60


def test_optimistic_ignores_the_sweep():
    b = _broker(realistic=False, last=100.0)
    b.submit_oca_bracket(Side.LONG, 2, sl_trigger=95.0, sl_limit=85.0, tp_price=120.0)
    b.on_sub_bar(SB(99, 99, 84, 86), ts=1)             # same bar...
    assert b.total_pnl == pytest.approx((95 - 100) * 2 * 2)   # ...but fills at trigger 95 → -$20
    assert b.n_breaches == 0


# ── THE HEADLINE MECHANIC: buffer breach → naked → rescue ─────────────────────
def test_long_buffer_breach_is_a_nonfill():
    b = _broker(realistic=True, last=100.0)
    h = b.submit_oca_bracket(Side.LONG, 2, sl_trigger=95.0, sl_limit=85.0, tp_price=120.0)
    b.on_sub_bar(SB(80, 82, 78, 79), ts=1)             # 5s bar OPENS at 80, below the 85 limit floor
    assert b.n_breaches == 1
    assert b.get_current_position().side is Side.LONG  # STILL OPEN — the SL did not fill
    assert b.get_current_position().qty == 2
    assert not b.is_order_live(h.sl_id)                # rejected, cannot refill


def test_breach_then_bar_close_rescue():
    b = _broker(realistic=True, last=100.0)
    b.submit_oca_bracket(Side.LONG, 2, sl_trigger=95.0, sl_limit=85.0, tp_price=120.0)
    b.on_sub_bar(SB(80, 82, 78, 79), ts=1)             # breach: naked below the stop
    assert b.n_rescues == 0 and b.total_pnl == 0.0     # nothing realized yet
    # the strategy's EMA50 bar-close check fires next bar → flatten(ema_stop)
    b.flatten_position(reason="ema_stop", price=79.0)
    assert b.n_rescues == 1
    assert b.get_current_position().side is None
    assert b.total_pnl == pytest.approx((79 - 100) * 2 * 2)   # rescued at 79 → -$84
    # ...far worse than the -$30 the optimistic engine assumed (fill at the 95 stop)
    assert b.total_pnl < (95 - 100) * 2 * 2
    assert b._closed_calls and b._closed_calls[-1][0] == "LONG"


def test_short_buffer_breach_mirror():
    b = _broker(realistic=True, last=100.0)
    b.submit_oca_bracket(Side.SHORT, 2, sl_trigger=105.0, sl_limit=115.0, tp_price=90.0)
    b.on_sub_bar(SB(120, 122, 119, 121), ts=1)         # opens at 120, above the 115 ceiling
    assert b.n_breaches == 1
    assert b.get_current_position().side is Side.SHORT  # naked
    b.flatten_position(reason="ema_stop", price=121.0)
    assert b.n_rescues == 1
    assert b.total_pnl == pytest.approx((100 - 121) * 2 * 2)  # short rescued at 121 → -$84


# ── OCA same-bar resolution: nearest level to the open fills first ─────────────
def test_nearest_level_to_open_wins():
    # SHORT whose stop sits BELOW entry (degenerate EMA50 placement). Price falls
    # through the TP (nearer) before the stop-limit (farther) → TP must win, not
    # a fantasy stop fill.
    b = _broker(realistic=True, last=100.0)
    b.submit_oca_bracket(Side.SHORT, 2, sl_trigger=70.0, sl_limit=72.0, tp_price=97.0)
    b.on_sub_bar(SB(99, 99, 69, 71), ts=1)             # both touchable; TP at 97 nearer the open
    assert b.n_tp == 1 and b.n_sl == 0
    assert b.total_pnl == pytest.approx((100 - 97) * 2 * 2)   # +$12 at the TP


# ── partial reduce + leg resize ───────────────────────────────────────────────
def test_reduce_then_modify_legs():
    b = _broker(last=100.0)
    h = b.submit_oca_bracket(Side.SHORT, 10, sl_trigger=110.0, sl_limit=120.0, tp_price=90.0)
    b.set_last_price(96.0)
    assert b.reduce_position(7, reason="runner peel") is True
    pos = b.get_current_position()
    assert pos.side is Side.SHORT and pos.qty == 3
    assert b.total_pnl == pytest.approx((100 - 96) * 7 * 2)   # +$56 on the 7 lots
    assert b.modify_order(h.sl_id, total_qty=3) is True       # resize the resting SL
    assert b.modify_order(999999, total_qty=3) is False       # dead order → benign False


def test_flatten_is_idempotent_when_flat():
    b = _broker(last=100.0)
    b.flatten_position(reason="manual")                # no position
    assert b.get_current_position().side is None
    assert b.total_pnl == 0.0
