"""
Data Ingestor Service — Phase 2 stub.

Fetches market data from yfinance / Binance / Coinbase,
normalizes it, and writes to TimescaleDB + bronze lake.

Currently: keeps the container alive and logs a startup message.
Next steps: implement fetch_yfinance(), fetch_binance(), write_to_db().
"""
import logging
import os
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ingestor] %(message)s")
log = logging.getLogger(__name__)


def main():
    db_url = os.getenv("DATABASE_URL", "not set")
    redis_url = os.getenv("REDIS_URL", "not set")
    archive = os.getenv("ARCHIVE_PATH", "not set")

    log.info("Data ingestor starting")
    log.info(f"  DATABASE_URL  = {db_url}")
    log.info(f"  REDIS_URL     = {redis_url}")
    log.info(f"  ARCHIVE_PATH  = {archive}")
    log.info("Ingestor stub running — implement fetch logic here.")

    while True:
        log.info("Ingestor heartbeat (no fetch logic yet)")
        time.sleep(60)


if __name__ == "__main__":
    main()
