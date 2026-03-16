"""Tests for stop loss and trailing stop loss features.

These features are applied during the simulation phase (_simulate_account_path),
not during action determination. They track per-trade entry price and high water
mark to trigger exits when price drops below configured thresholds.
"""

import numpy as np
import pandas as pd
import pytest
from fast_trade.run_analysis import (
    _encode_actions,
    _simulate_account_path,
    apply_logic_to_df,
    ACTION_HOLD,
    ACTION_ENTER,
    ACTION_EXIT,
)


# ---------------------------------------------------------------------------
# Helper to build a simple dataframe for apply_logic_to_df tests
# ---------------------------------------------------------------------------
def _make_df(close_prices, high_prices=None, actions=None):
    """Build a minimal OHLCV dataframe with the given prices."""
    n = len(close_prices)
    if high_prices is None:
        high_prices = close_prices
    if actions is None:
        actions = ["h"] * n
    dates = pd.date_range("2024-01-01", periods=n, freq="1D")
    df = pd.DataFrame(
        {
            "close": close_prices,
            "open": close_prices,
            "high": high_prices,
            "low": close_prices,
            "volume": [1000] * n,
            "action": actions,
        },
        index=dates,
    )
    return df


# ===========================================================================
# _encode_actions
# ===========================================================================
class TestEncodeActions:
    def test_basic_encoding(self):
        actions = np.array(["e", "h", "x", "ae", "ax", "tsl", "h"])
        codes = _encode_actions(actions)
        expected = np.array(
            [ACTION_ENTER, ACTION_HOLD, ACTION_EXIT, ACTION_ENTER, ACTION_EXIT, ACTION_EXIT, ACTION_HOLD],
            dtype=np.int8,
        )
        np.testing.assert_array_equal(codes, expected)

    def test_all_holds(self):
        actions = np.array(["h", "h", "h"])
        codes = _encode_actions(actions)
        np.testing.assert_array_equal(codes, np.zeros(3, dtype=np.int8))


# ===========================================================================
# Fixed stop loss — _simulate_account_path
# ===========================================================================
class TestFixedStopLoss:
    def test_stop_loss_triggers_exit(self):
        """Price enters at 100, drops to 90 (10% drop). With 5% stop loss, should exit."""
        action_codes = np.array([ACTION_ENTER, ACTION_HOLD, ACTION_HOLD], dtype=np.int8)
        close_prices = np.array([100.0, 96.0, 90.0])
        high_prices = np.array([100.0, 96.0, 90.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.05,  # 5% stop loss
        )

        # Should exit on bar index 1 (96 <= 100 * 0.95 = 95? No, 96 > 95)
        # Should exit on bar index 2 (90 <= 100 * 0.95 = 95? Yes)
        assert result["final_actions"][0] == ACTION_ENTER
        assert result["final_actions"][1] == ACTION_HOLD  # 96 > 95, hold
        assert result["final_actions"][2] == ACTION_EXIT  # 90 <= 95, exit
        assert not result["in_trade"][2]

    def test_stop_loss_does_not_trigger_above_threshold(self):
        """Price stays above stop loss threshold — no forced exit."""
        action_codes = np.array([ACTION_ENTER, ACTION_HOLD, ACTION_EXIT], dtype=np.int8)
        close_prices = np.array([100.0, 98.0, 96.0])
        high_prices = np.array([100.0, 98.0, 96.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.05,  # 5% — threshold is 95
        )

        # Bar 1: 98 > 95, no stop
        # Bar 2: 96 > 95, no stop — exits via normal exit action
        assert result["final_actions"][1] == ACTION_HOLD
        assert result["final_actions"][2] == ACTION_EXIT
        assert result["in_trade"][1]
        assert not result["in_trade"][2]

    def test_stop_loss_zero_means_disabled(self):
        """With stop_loss=0, it should never trigger forced exit."""
        action_codes = np.array([ACTION_ENTER, ACTION_HOLD, ACTION_EXIT], dtype=np.int8)
        close_prices = np.array([100.0, 50.0, 30.0])  # huge drop
        high_prices = np.array([100.0, 50.0, 30.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.0,
        )

        # No stop loss — should stay in trade until bar 2 (normal exit)
        assert result["in_trade"][0]
        assert result["in_trade"][1]
        assert not result["in_trade"][2]

    def test_stop_loss_only_applies_when_in_trade(self):
        """Stop loss should not affect bars where we're not in a trade."""
        action_codes = np.array(
            [ACTION_HOLD, ACTION_HOLD, ACTION_ENTER, ACTION_HOLD], dtype=np.int8
        )
        close_prices = np.array([100.0, 50.0, 100.0, 94.0])
        high_prices = np.array([100.0, 50.0, 100.0, 94.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.05,
        )

        # Bars 0-1: not in trade, stop loss irrelevant
        assert not result["in_trade"][0]
        assert not result["in_trade"][1]
        # Bar 2: enter at 100
        assert result["in_trade"][2]
        # Bar 3: 94 <= 100 * 0.95 = 95, stop loss triggers
        assert result["final_actions"][3] == ACTION_EXIT
        assert not result["in_trade"][3]


# ===========================================================================
# Trailing stop loss — _simulate_account_path
# ===========================================================================
class TestTrailingStopLoss:
    def test_trailing_stop_triggers_after_rally(self):
        """Enter at 100, price rallies to 120, then drops to 108.
        With 10% trailing stop, threshold = 120 * 0.9 = 108.
        Close at 108 <= 108, should exit."""
        action_codes = np.array(
            [ACTION_ENTER, ACTION_HOLD, ACTION_HOLD, ACTION_HOLD], dtype=np.int8
        )
        close_prices = np.array([100.0, 110.0, 120.0, 108.0])
        high_prices = np.array([100.0, 115.0, 120.0, 112.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            trailing_stop_loss=0.10,
        )

        # High water mark progression: 100 -> 115 -> 120 -> 120 (112 < 120)
        # Bar 3: 108 <= 120 * 0.9 = 108 → exit
        assert result["final_actions"][3] == ACTION_EXIT
        assert not result["in_trade"][3]

    def test_trailing_stop_uses_high_not_close(self):
        """High water mark should track bar highs, not just close prices."""
        action_codes = np.array(
            [ACTION_ENTER, ACTION_HOLD, ACTION_HOLD], dtype=np.int8
        )
        # Close never goes above 100, but high hits 120
        close_prices = np.array([100.0, 95.0, 90.0])
        high_prices = np.array([100.0, 120.0, 92.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            trailing_stop_loss=0.10,
        )

        # High water mark: 100 -> 120 -> 120
        # Bar 1: 95 <= 120 * 0.9 = 108? Yes → exit
        assert result["final_actions"][1] == ACTION_EXIT
        assert not result["in_trade"][1]

    def test_trailing_stop_resets_between_trades(self):
        """After exiting and re-entering, high water mark should reset to new entry price."""
        action_codes = np.array(
            [ACTION_ENTER, ACTION_HOLD, ACTION_EXIT, ACTION_ENTER, ACTION_HOLD],
            dtype=np.int8,
        )
        close_prices = np.array([100.0, 120.0, 115.0, 50.0, 44.0])
        high_prices = np.array([100.0, 125.0, 115.0, 50.0, 46.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            trailing_stop_loss=0.10,
        )

        # Trade 1: enter at 100, HWM goes to 125, exit at 115 (normal exit, 115 > 125*0.9=112.5)
        assert result["in_trade"][0]
        assert result["in_trade"][1]
        assert not result["in_trade"][2]

        # Trade 2: enter at 50, HWM = 50
        # Bar 4: high=46 < 50 so HWM stays 50. close=44 <= 50*0.9=45 → exit
        assert result["in_trade"][3]
        assert result["final_actions"][4] == ACTION_EXIT
        assert not result["in_trade"][4]

    def test_trailing_stop_zero_means_disabled(self):
        """With trailing_stop_loss=0, no trailing stop should trigger."""
        action_codes = np.array(
            [ACTION_ENTER, ACTION_HOLD, ACTION_EXIT], dtype=np.int8
        )
        close_prices = np.array([100.0, 120.0, 50.0])
        high_prices = np.array([100.0, 130.0, 50.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            trailing_stop_loss=0.0,
        )

        # Should not trigger trailing stop despite 130 -> 50 drop
        assert result["in_trade"][0]
        assert result["in_trade"][1]
        assert not result["in_trade"][2]  # normal exit


# ===========================================================================
# Combined stop loss + trailing stop loss
# ===========================================================================
class TestCombinedStopLoss:
    def test_fixed_stop_triggers_before_trailing(self):
        """Fixed stop at 5% triggers on a straight drop, even if trailing (10%) wouldn't."""
        action_codes = np.array(
            [ACTION_ENTER, ACTION_HOLD], dtype=np.int8
        )
        close_prices = np.array([100.0, 94.0])
        high_prices = np.array([100.0, 96.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.05,  # threshold: 95
            trailing_stop_loss=0.10,  # threshold: 100*0.9=90
        )

        # 94 <= 95 (fixed stop triggers), 94 > 90 (trailing would NOT trigger)
        assert result["final_actions"][1] == ACTION_EXIT
        assert not result["in_trade"][1]

    def test_trailing_triggers_before_fixed(self):
        """After a rally, trailing stop can trigger before fixed stop would."""
        action_codes = np.array(
            [ACTION_ENTER, ACTION_HOLD, ACTION_HOLD], dtype=np.int8
        )
        close_prices = np.array([100.0, 150.0, 130.0])
        high_prices = np.array([100.0, 155.0, 135.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.50,  # 50% — threshold: 50, won't trigger
            trailing_stop_loss=0.10,  # HWM=155, threshold: 139.5
        )

        # Bar 2: 130 <= 155*0.9=139.5 (trailing triggers), 130 > 50 (fixed wouldn't)
        assert result["final_actions"][2] == ACTION_EXIT
        assert not result["in_trade"][2]


# ===========================================================================
# Account value correctness with stop losses
# ===========================================================================
class TestAccountValueWithStopLoss:
    def test_account_value_after_stop_loss_exit(self):
        """Verify account value is correctly updated after a stop-loss exit."""
        action_codes = np.array([ACTION_ENTER, ACTION_HOLD], dtype=np.int8)
        close_prices = np.array([100.0, 90.0])
        high_prices = np.array([100.0, 92.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.05,
        )

        # Enter at 100 with 1000 balance → buy 10 units
        # Stop triggers at 90, sell 10 units at 90 = 900
        assert result["final_actions"][1] == ACTION_EXIT
        assert result["account_value"][1] == 900.0
        assert not result["in_trade"][1]

    def test_account_value_with_commission_and_stop_loss(self):
        """Verify fees are applied on both entry and stop-loss exit."""
        action_codes = np.array([ACTION_ENTER, ACTION_HOLD], dtype=np.int8)
        close_prices = np.array([100.0, 90.0])
        high_prices = np.array([100.0, 92.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=1.0,  # 1% commission
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.05,
        )

        # Entry: buy 1000/100 = 10 units, fee = $10.0 (1% of 1000), net aux = 9.9
        assert result["fee"][0] == 10.0
        # Exit at 90: sell 9.9 * 90 = 891, fee = 891 * 0.01 = 8.91
        assert result["final_actions"][1] == ACTION_EXIT
        assert result["fee"][1] == pytest.approx(8.91, rel=1e-6)
        expected_cash = 0.0 + 891.0 - 8.91  # cash_value after entry is 0
        assert result["account_value"][1] == pytest.approx(expected_cash, rel=1e-6)

    def test_can_reenter_after_stop_loss(self):
        """After a stop-loss exit, should be able to enter a new trade."""
        action_codes = np.array(
            [ACTION_ENTER, ACTION_HOLD, ACTION_HOLD, ACTION_ENTER, ACTION_EXIT],
            dtype=np.int8,
        )
        close_prices = np.array([100.0, 90.0, 95.0, 95.0, 100.0])
        high_prices = np.array([100.0, 92.0, 95.0, 95.0, 100.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.05,
        )

        # Trade 1: enter at 100, stop at 90 → account = 900
        assert not result["in_trade"][1]
        assert result["account_value"][1] == 900.0
        # Bar 2: hold (not in trade), bar 3: re-enter at 95
        assert result["in_trade"][3]
        # Bar 4: exit at 100 → 900/95 ≈ 9.47368421 units * 100 = 947.368...
        assert not result["in_trade"][4]
        assert result["account_value"][4] > 900.0  # profit on second trade


# ===========================================================================
# Integration: apply_logic_to_df with stop losses
# ===========================================================================
class TestApplyLogicWithStopLoss:
    def test_apply_logic_with_fixed_stop_loss(self):
        """End-to-end: apply_logic_to_df with a fixed stop loss."""
        close = [100.0, 110.0, 105.0, 90.0, 95.0]
        high = [102.0, 115.0, 108.0, 92.0, 97.0]
        actions = ["e", "h", "h", "h", "x"]
        df = _make_df(close, high, actions)

        backtest = {
            "base_balance": 1000,
            "comission": 0.0,
            "lot_size_perc": 1.0,
            "max_lot_size": 0,
            "exit_on_end": False,
            "stop_loss": 0.10,  # 10% stop loss
            "trailing_stop_loss": 0,
        }

        result = apply_logic_to_df(df, backtest)

        # Enter at 100, stop threshold = 90
        # Bar 3: close=90, 90 <= 100*0.9=90 → stop triggers
        assert list(result["in_trade"]) == [True, True, True, False, False]
        # After stop, action should be updated to "x"
        assert result["action"].iloc[3] == "x"

    def test_apply_logic_with_trailing_stop_loss(self):
        """End-to-end: apply_logic_to_df with trailing stop loss."""
        close = [100.0, 110.0, 120.0, 105.0, 95.0]
        high = [105.0, 115.0, 125.0, 110.0, 98.0]
        actions = ["e", "h", "h", "h", "x"]
        df = _make_df(close, high, actions)

        backtest = {
            "base_balance": 1000,
            "comission": 0.0,
            "lot_size_perc": 1.0,
            "max_lot_size": 0,
            "exit_on_end": False,
            "stop_loss": 0,
            "trailing_stop_loss": 0.10,  # 10% trailing
        }

        result = apply_logic_to_df(df, backtest)

        # HWM: 105 → 115 → 125 → 125 (110<125)
        # Bar 3: threshold = 125*0.9 = 112.5, close=105 <= 112.5 → exit
        assert result["in_trade"].iloc[0] is True or result["in_trade"].iloc[0] == True
        assert result["in_trade"].iloc[2] is True or result["in_trade"].iloc[2] == True
        assert result["in_trade"].iloc[3] == False
        assert result["action"].iloc[3] == "x"

    def test_apply_logic_no_stop_loss_holds_through_dip(self):
        """Without stop loss, position holds through dips until normal exit."""
        close = [100.0, 50.0, 30.0, 200.0]
        high = [100.0, 50.0, 30.0, 200.0]
        actions = ["e", "h", "h", "x"]
        df = _make_df(close, high, actions)

        backtest = {
            "base_balance": 1000,
            "comission": 0.0,
            "lot_size_perc": 1.0,
            "max_lot_size": 0,
            "exit_on_end": False,
            "stop_loss": 0,
            "trailing_stop_loss": 0,
        }

        result = apply_logic_to_df(df, backtest)

        # Should hold through entire dip
        assert list(result["in_trade"]) == [True, True, True, False]
        # Final account value should reflect the profit (sold at 200)
        assert result["account_value"].iloc[3] == 2000.0

    def test_apply_logic_exit_on_end_with_stop_loss(self):
        """exit_on_end should work correctly even when stop loss is configured."""
        close = [100.0, 110.0, 120.0]
        high = [100.0, 110.0, 120.0]
        actions = ["e", "h", "h"]
        df = _make_df(close, high, actions)

        backtest = {
            "base_balance": 1000,
            "comission": 0.0,
            "lot_size_perc": 1.0,
            "max_lot_size": 0,
            "exit_on_end": True,
            "stop_loss": 0.50,  # won't trigger (price is going up)
            "trailing_stop_loss": 0,
        }

        result = apply_logic_to_df(df, backtest)

        # Price only goes up, so no stop triggers. exit_on_end adds a final exit row.
        assert result["in_trade"].iloc[-1] == False
        # Should have 4 rows (3 original + 1 exit_on_end)
        assert len(result) == 4


# ===========================================================================
# Edge cases
# ===========================================================================
class TestStopLossEdgeCases:
    def test_stop_loss_exact_threshold(self):
        """Price hits exactly the stop loss threshold."""
        action_codes = np.array([ACTION_ENTER, ACTION_HOLD], dtype=np.int8)
        close_prices = np.array([100.0, 95.0])  # exactly 5% drop
        high_prices = np.array([100.0, 96.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.05,
        )

        # 95 <= 100 * 0.95 = 95.0 → should trigger (<=)
        assert result["final_actions"][1] == ACTION_EXIT

    def test_stop_loss_on_entry_bar_does_not_trigger(self):
        """Stop loss should not trigger on the same bar as entry."""
        action_codes = np.array([ACTION_ENTER, ACTION_HOLD], dtype=np.int8)
        close_prices = np.array([100.0, 99.0])
        high_prices = np.array([100.0, 99.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.05,
        )

        # Entry bar: not yet in trade when stop is checked (check happens before entry logic)
        # Bar 1: 99 > 95, no stop
        assert result["in_trade"][0]
        assert result["in_trade"][1]

    def test_multiple_entries_and_stops(self):
        """Multiple enter-stop-reenter cycles."""
        action_codes = np.array(
            [ACTION_ENTER, ACTION_HOLD, ACTION_HOLD, ACTION_ENTER, ACTION_HOLD, ACTION_EXIT],
            dtype=np.int8,
        )
        close_prices = np.array([100.0, 80.0, 85.0, 85.0, 70.0, 90.0])
        high_prices = np.array([100.0, 82.0, 85.0, 85.0, 72.0, 90.0])

        result = _simulate_account_path(
            action_codes=action_codes,
            open_prices=close_prices,
            low_prices=close_prices,
            close_prices=close_prices,
            high_prices=high_prices,
            base_balance=1000.0,
            comission=0.0,
            lot_size=1.0,
            max_lot_size=0,
            stop_loss=0.10,
        )

        # Trade 1: enter at 100, bar 1: 80 <= 90 → stop
        assert result["final_actions"][1] == ACTION_EXIT
        assert not result["in_trade"][1]
        # Trade 2: enter at 85, bar 4: 70 <= 76.5 → stop
        assert result["final_actions"][4] == ACTION_EXIT
        assert not result["in_trade"][4]
        # Bar 5: no trade to exit
        assert not result["in_trade"][5]
