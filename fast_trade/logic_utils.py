import itertools
from typing import List

import pandas as pd


def max_last_frames(backtest: dict) -> int:
    logics = [
        backtest.get("enter", []),
        backtest.get("exit", []),
        backtest.get("any_exit", []),
        backtest.get("any_enter", []),
    ]
    flat = list(itertools.chain(*logics))
    max_frames = 0
    for logic in flat:
        if isinstance(logic, dict) and "or" in logic:
            for sub in logic["or"]:
                if len(sub) > 3 and sub[3] > max_frames:
                    max_frames = sub[3]
        elif not isinstance(logic, dict) and len(logic) > 3 and logic[3] > max_frames:
            max_frames = logic[3]
    return max_frames


def can_vectorize_logic(df: pd.DataFrame, backtest: dict) -> bool:
    def check_rule(logic) -> bool:
        if isinstance(logic, dict) and "or" in logic:
            return all(check_rule(sub) for sub in logic["or"])
        return (
            isinstance(logic[0], str)
            and logic[0] in df.columns
            and (
                isinstance(logic[2], (int, float))
                or (isinstance(logic[2], str) and logic[2] in df.columns)
            )
        )

    for logic_group in [
        backtest.get("enter", []),
        backtest.get("exit", []),
        backtest.get("any_enter", []),
        backtest.get("any_exit", []),
    ]:
        for logic in logic_group:
            if not check_rule(logic):
                return False
    return True


def _single_condition(df: pd.DataFrame, logic) -> pd.Series:
    op = logic[1]
    left = df[logic[0]]
    right = df[logic[2]] if isinstance(logic[2], str) and logic[2] in df.columns else logic[2]
    ops = {
        ">": left > right, "<": left < right, "=": left == right,
        "!=": left != right, ">=": left >= right, "<=": left <= right,
    }
    return ops.get(op, pd.Series(False, index=df.index))


def build_mask(df: pd.DataFrame, logic_list: List, combine_any: bool) -> pd.Series:
    if not logic_list:
        return pd.Series(False, index=df.index)
    mask = pd.Series(not combine_any, index=df.index)
    for logic in logic_list:
        if isinstance(logic, dict) and "or" in logic:
            condition = build_mask(df, logic["or"], combine_any=True)
        else:
            condition = _single_condition(df, logic)
        mask = mask | condition if combine_any else mask & condition
    return mask


def vectorized_actions(df: pd.DataFrame, backtest: dict) -> pd.Series:
    df_actions = pd.Series("h", index=df.index)
    exit_mask = build_mask(df, backtest.get("exit", []), combine_any=False)
    any_exit_mask = build_mask(df, backtest.get("any_exit", []), combine_any=True)
    enter_mask = build_mask(df, backtest.get("enter", []), combine_any=False)
    any_enter_mask = build_mask(df, backtest.get("any_enter", []), combine_any=True)

    tsl_mask = pd.Series(False, index=df.index)
    if backtest.get("trailing_stop_loss"):
        tsl_mask = df["close"] <= df["trailing_stop_loss"]

    df_actions.loc[tsl_mask] = "tsl"
    df_actions.loc[~tsl_mask & exit_mask] = "x"
    df_actions.loc[~tsl_mask & ~exit_mask & any_exit_mask] = "ax"
    df_actions.loc[~tsl_mask & ~exit_mask & ~any_exit_mask & enter_mask] = "e"
    df_actions.loc[
        ~tsl_mask & ~exit_mask & ~any_exit_mask & ~enter_mask & any_enter_mask
    ] = "ae"

    return df_actions
