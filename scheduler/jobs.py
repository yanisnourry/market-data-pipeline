import logging
import time
import aiohttp
from ingestion.fetcher import INTERVAL_MS, fetch_candles
from ingestion.normalizer import normalize_all
from ingestion.validator import validator
from scheduler.config import SYMBOLS
from dotenv import load_dotenv
import os

from storage.cache import set_last_price
from storage.repository import insert_candles

load_dotenv()
BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL")
EXCHANGE_LIST = [BINANCE_BASE_URL]
EXCHANGE_MAP = {
    BINANCE_BASE_URL: "BINANCE",
}

logger = logging.getLogger(__name__)


async def fetch_and_store(session_maker, redis_client, timeframe):
    for exchange in EXCHANGE_LIST:
        async with aiohttp.ClientSession(base_url=exchange) as client_session:
            for symbol in SYMBOLS:
                try:
                    end_ms = int(time.time() * 1000)
                    start_ms = end_ms - INTERVAL_MS[timeframe]
                    raw = await fetch_candles(
                        session=client_session,
                        symbol=symbol,
                        timeframe=timeframe,
                        start_ms=start_ms,
                        end_ms=end_ms,
                    )
                    candles = normalize_all(data=raw, symbol=symbol, exchange=EXCHANGE_MAP[exchange], timeframe=timeframe)
                    candles = validator(candles=candles, timeframe=timeframe)

                    if not candles:
                        logger.warning(f"No candles fetched for {symbol} {timeframe}")
                        continue

                    async with session_maker() as async_session:
                        await insert_candles(session=async_session, candles=candles)

                    await set_last_price(client=redis_client, symbol=symbol, price=candles[-1].close)
                    logger.info(f"Stored {len(candles)} candles for {symbol} {timeframe}")

                except Exception as e:
                    logger.error(f"fetch_and_store failed for {symbol} {timeframe}: {e}")
