"""
Fast-Trade Streamlit Dashboard
Reads from TimescaleDB — no direct coupling to fast-trade internals.
"""
import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text

DB_URL = os.environ["DATABASE_URL"]
engine = create_engine(DB_URL)

st.set_page_config(page_title="Fast-Trade", layout="wide")
st.title("Fast-Trade Research Dashboard")

# ── Recent Backtest Runs ──────────────────────────────────
st.subheader("Recent Backtest Runs")
with engine.connect() as conn:
    runs = pd.read_sql("""
        SELECT r.id, s.name AS strategy, r.started_at, r.status,
               r.summary->>'return_perc'   AS return_pct,
               r.summary->>'sharpe_ratio'  AS sharpe,
               r.summary->>'max_drawdown'  AS max_dd,
               r.summary->>'num_trades'    AS trades
        FROM backtest_runs r
        LEFT JOIN strategies s ON r.strategy_id = s.id
        ORDER BY r.started_at DESC
        LIMIT 50
    """, conn)

if runs.empty:
    st.info("No backtest runs yet.")
else:
    st.dataframe(runs, use_container_width=True)

# ── OHLCV Chart ───────────────────────────────────────────
st.subheader("Market Data")

with engine.connect() as conn:
    symbols = pd.read_sql(
        "SELECT DISTINCT symbol, exchange FROM ohlcv ORDER BY symbol", conn
    )

if symbols.empty:
    st.info("No OHLCV data yet. Run the ingestor first.")
else:
    with st.sidebar:
        st.header("Data")
        symbol = st.selectbox("Symbol", symbols["symbol"].tolist())
        exchange = st.selectbox(
            "Exchange",
            symbols[symbols["symbol"] == symbol]["exchange"].tolist()
        )
        timeframe = st.selectbox("Timeframe", ["1min", "5min", "1H", "1D"], index=2)
        days = st.slider("Days of history", 7, 365, 90)

    st.subheader(f"{symbol} / {exchange} — {timeframe}")

    query = text("""
        SELECT
            time_bucket(:bucket, ts) AS t,
            first(open,  ts) AS open,
            max(high)        AS high,
            min(low)         AS low,
            last(close, ts)  AS close,
            sum(volume)      AS volume
        FROM ohlcv
        WHERE symbol = :symbol
          AND exchange = :exchange
          AND ts >= NOW() - INTERVAL '1 day' * :days
        GROUP BY t
        ORDER BY t
    """)

    bucket_map = {"1min": "1 minute", "5min": "5 minutes", "1H": "1 hour", "1D": "1 day"}

    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={
            "bucket": bucket_map[timeframe],
            "symbol": symbol,
            "exchange": exchange,
            "days": days
        })

    if df.empty:
        st.info("No data for this selection.")
    else:
        fig = go.Figure(go.Candlestick(
            x=df["t"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"]
        ))
        fig.update_layout(xaxis_rangeslider_visible=False, height=450)
        st.plotly_chart(fig, use_container_width=True)

# ── Portfolio State ───────────────────────────────────────
st.subheader("Paper Portfolios")
with engine.connect() as conn:
    ports = pd.read_sql(
        "SELECT * FROM portfolio_state ORDER BY updated_at DESC", conn
    )

if not ports.empty:
    st.dataframe(ports, use_container_width=True)
