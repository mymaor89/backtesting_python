import pytest
import pandas as pd
import numpy as np
from fast_trade.run_analysis import apply_logic_to_df

def _make_ohlcv_df(data):
    # Use the length of one of the data lists (e.g., 'close') for periods
    n = len(data["close"])
    dates = pd.date_range("2024-01-01", periods=n, freq="1D")
    df = pd.DataFrame(data, index=dates)
    return df

def test_slippage_on_entry():
    # Price is 100. Slippage is 1%. Expected entry price = 101.
    data = {
        "open": [100.0, 100.0],
        "high": [105.0, 105.0],
        "low": [95.0, 95.0],
        "close": [100.0, 100.0],
        "volume": [1000, 1000],
        "action": ["e", "h"]
    }
    df = _make_ohlcv_df(data)
    backtest = {
        "base_balance": 1000,
        "comission": 0.0,
        "lot_size_perc": 1.0,
        "slippage": 1.0,  # 1% slippage
        "execution_at": "close"
    }
    
    result = apply_logic_to_df(df, backtest)
    
    # 1000 / (100 * 1.01) = 1000 / 101 = 9.90099009...
    expected_aux = round(1000 / 101.0, 8)
    assert result["aux"].iloc[0] == expected_aux
    # account_value at index 0 should be 0 because we spent 1000
    assert result["account_value"].iloc[0] == 0.0

def test_slippage_on_exit():
    # Price is 100. Slippage is 1%. Expected exit price = 99.
    data = {
        "open": [100.0, 100.0, 100.0],
        "high": [105.0, 105.0, 105.0],
        "low": [95.0, 95.0, 95.0],
        "close": [100.0, 100.0, 100.0],
        "volume": [1000, 1000, 1000],
        "action": ["e", "h", "x"]
    }
    df = _make_ohlcv_df(data)
    backtest = {
        "base_balance": 1000,
        "comission": 0.0,
        "lot_size_perc": 1.0,
        "slippage": 1.0,  # 1% slippage
        "execution_at": "close"
    }
    
    result = apply_logic_to_df(df, backtest)
    
    # Entry at 101: units = 9.9009901 (round to 8)
    units = round(1000 / 101.0, 8)
    # Exit at 99: cash = units * 99 = 9.9009901 * 99 = 980.1980199
    expected_cash = round(units * 99.0, 8)
    assert result["account_value"].iloc[2] == expected_cash

def test_execution_at_next_open():
    # Signal at close of bar 0. Execution at open of bar 1.
    # Bar 0: close=100. Bar 1: open=110.
    data = {
        "open": [100.0, 110.0, 110.0],
        "high": [105.0, 115.0, 115.0],
        "low": [95.0, 105.0, 105.0],
        "close": [100.0, 110.0, 110.0],
        "volume": [1000, 1000, 1000],
        "action": ["e", "h", "x"]
    }
    df = _make_ohlcv_df(data)
    backtest = {
        "base_balance": 1000,
        "comission": 0.0,
        "lot_size_perc": 1.0,
        "slippage": 0.0,
        "execution_at": "next_open"
    }
    
    result = apply_logic_to_df(df, backtest)
    
    # Signal at bar 0. Execution at bar 1 open = 110.
    # units = 1000 / 110 = 9.09090909
    expected_aux = round(1000 / 110.0, 8)
    assert result["aux"].iloc[0] == expected_aux
    
    # Exit signal at bar 2. Execution at bar 2 open? 
    # Current implementation for next_open on exit at bar i looks at open[i+1].
    # But if it's the last bar, it uses close[i].
    # In this test, i=2 is not the last bar if we added one more.
    
def test_intra_candle_stop_loss():
    # Entry at 100. Stop loss 5% (threshold 95).
    # Bar 1: High=110, Low=94, Close=105.
    # Vectorized logic SHOULD trigger stop because Low=94 is below 95, 
    # even though Close=105 is above 95.
    data = {
        "open": [100.0, 105.0, 105.0],
        "high": [105.0, 110.0, 110.0],
        "low": [95.0, 94.0, 94.0],
        "close": [100.0, 105.0, 105.0],
        "volume": [1000, 1000, 1000],
        "action": ["e", "h", "h"]
    }
    df = _make_ohlcv_df(data)
    backtest = {
        "base_balance": 1000,
        "comission": 0.0,
        "lot_size_perc": 1.0,
        "stop_loss": 0.05,
        "execution_at": "close"
    }
    
    result = apply_logic_to_df(df, backtest)
    
    # Bar 1 low is 94 which is < 100*0.95=95.
    # Should exit on bar 1.
    assert result["in_trade"].iloc[1] == False
    assert result["action"].iloc[1] == "x"

def test_vectorized_confirmation_frames():
    # Condition: close > 100 for 3 bars.
    data = {
        "open": [100, 100, 100, 100, 100, 100],
        "high": [100, 100, 100, 100, 100, 100],
        "low": [100, 100, 100, 100, 100, 100],
        "close": [90, 110, 110, 90, 110, 110], # only 2 consecutive 110s at the end
        "volume": [1000] * 6,
        "action": ["h"] * 6
    }
    df = _make_ohlcv_df(data)
    backtest = {
        "base_balance": 1000,
        "comission": 0.0,
        "lot_size_perc": 1.0,
        "enter": [["close", ">", 100, 3]], # requires 3 bars
        "exit": []
    }
    
    # We need to use run_backtest or logic_utils functions to test this properly
    from fast_trade.run_backtest import process_logic_and_generate_actions
    
    result_df = process_logic_and_generate_actions(df.copy(), backtest)
    
    # No row has 3 consecutive closes > 100.
    assert "e" not in result_df["action"].values

    # Test with 3 consecutive
    data2 = {
        "close": [110, 110, 110, 100, 100],
        "open": [100]*5, "high": [100]*5, "low": [100]*5, "volume": [1000]*5, "action": ["h"]*5
    }
    df2 = _make_ohlcv_df(data2)
    result_df2 = process_logic_and_generate_actions(df2, backtest)
    
    # Bar 2 (3rd bar) should have "e"
    assert result_df2["action"].iloc[2] == "e"
    assert result_df2["action"].iloc[1] == "h"
