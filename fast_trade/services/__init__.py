"""
fast_trade.services — production service layer.

  api.py         FastAPI application (Strategy Engine HTTP API)
  db.py          Shared SQLAlchemy engine + TimescaleDB helpers
  ingestor.py    OHLCV data fetcher (yfinance → TimescaleDB + parquet)
  serializers.py React-friendly JSON serialisers (equity curve, trades)
"""
