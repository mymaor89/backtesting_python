FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY fast_trade/ ./fast_trade/

# Install the package + all service dependencies in one layer
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir \
        jupyterlab \
        celery[redis] \
        sqlalchemy \
        psycopg2-binary \
        yfinance \
        redis \
        finta \
        backtesting \
        mplfinance

# Create persistent storage directories
RUN mkdir -p /data/results /data/archive /data/notebooks /data/lake/bronze /data/lake/silver

EXPOSE 8888

CMD ["jupyter", "lab", \
    "--ip=0.0.0.0", \
    "--port=8888", \
    "--no-browser", \
    "--allow-root", \
    "--notebook-dir=/data/notebooks", \
    "--ServerApp.token=''", \
    "--ServerApp.password=''"]
