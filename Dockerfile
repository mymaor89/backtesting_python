# ============================================================
# Fast-Trade — multi-mode container image
#
# Runtime modes (selected via `command:` in docker-compose.yml):
#   api        uvicorn fast_trade.services.api:app   (port 8000)  ← default
#   worker     celery worker — backtests + optimize queues
#   scheduler  celery beat   — nightly archive updates
#   ingestor   OHLCV fetcher daemon
#   jupyter    JupyterLab research environment       (port 8888)
# ============================================================

FROM python:3.11-slim

WORKDIR /app

# ── System build deps ─────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Layer 1: install declared package dependencies ────────────────────────────
# Copy only the manifest + a minimal stub so setuptools can resolve deps
# without needing the real source tree.  This layer is rebuilt only when
# pyproject.toml changes — not on every code edit.
COPY pyproject.toml ./

# Create a minimal stub package so `pip install -e .` (or `pip install .`)
# can resolve and install all declared dependencies from pyproject.toml
# without requiring the real fast_trade/ directory to exist yet.
RUN mkdir -p fast_trade/archive fast_trade/summary fast_trade/ml fast_trade/services && \
    touch fast_trade/__init__.py \
          fast_trade/archive/__init__.py \
          fast_trade/summary/__init__.py \
          fast_trade/ml/__init__.py \
          fast_trade/services/__init__.py

# Install package deps (from pyproject.toml) — cached as long as toml doesn't change
RUN pip install --no-cache-dir --timeout 120 --retries 5 .

# ── Layer 2: install service-layer extras ────────────────────────────────────
# These are not in pyproject.toml (they are infra-only); kept in a separate
# RUN so they cache independently of the core deps above.
RUN pip install --no-cache-dir --timeout 120 --retries 5 \
        fastapi \
        "uvicorn[standard]" \
        "celery[redis]" \
        redis \
        sqlalchemy \
        psycopg2-binary \
        yfinance \
        jupyterlab \
        finta \
        mplfinance \
        pytest

# ── Layer 3: copy real application code ──────────────────────────────────────
# Overwrites the stubs.  Rebuilt on every source change, but deps are cached.
COPY fast_trade/ ./fast_trade/

# Reinstall just the package (no deps download, very fast)
RUN pip install --no-cache-dir --no-deps --timeout 120 .

# ── Persistent storage layout ─────────────────────────────────────────────────
RUN mkdir -p \
        /data/results \
        /data/archive \
        /data/notebooks \
        /data/lake/bronze \
        /data/lake/silver \
        /data/models

# ── Ports ─────────────────────────────────────────────────────────────────────
EXPOSE 8000 8888

# ── Default: run the FastAPI service ─────────────────────────────────────────
# Override CMD in docker-compose.yml for worker / scheduler / jupyter modes.
CMD ["uvicorn", "fast_trade.services.api:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
