import logging
import time
import aiohttp
from ingestion.fetcher import fetch_candles
from ingestion.normalizer import normalize_all
from ingestion.validator import validator
from scheduler.config import INITIAL_BACKFILL_MS, SYMBOLS
from dotenv import load_dotenv
import os

from storage.cache import set_last_price
from storage.repository import get_latest_candle, insert_candles

load_dotenv()
BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL")
EXCHANGE_LIST = [BINANCE_BASE_URL]
EXCHANGE_MAP = {
    BINANCE_BASE_URL: "BINANCE",
}

logger = logging.getLogger(__name__)


async def _compute_start_ms(session_maker, symbol: str, timeframe: str, end_ms: int) -> int:
    """Resume from the latest stored candle, or backfill if the series is empty.

    Starts AT the latest candle, not one interval after it: that candle was most
    likely stored while still open (Binance returns the in-progress kline), and
    refetching it lets the upsert overwrite it with its final OHLCV.
    Never reaches further back than INITIAL_BACKFILL_MS, so a long outage costs
    at most one initial backfill per tick instead of an unbounded request burst.
    """
    horizon_ms = end_ms - INITIAL_BACKFILL_MS[timeframe]
    async with session_maker() as async_session:
        latest = await get_latest_candle(session=async_session, symbol=symbol, timeframe=timeframe)
    if latest is None:
        return horizon_ms
    latest_ms = int(latest.timestamp.timestamp() * 1000)
    if latest_ms < horizon_ms:
        logger.warning(
            f"Gap for {symbol} {timeframe} exceeds backfill horizon; "
            f"candles before {horizon_ms} will not be recovered"
        )
        return horizon_ms
    return latest_ms


async def fetch_and_store(session_maker, redis_client, timeframe):
    for exchange in EXCHANGE_LIST:
        async with aiohttp.ClientSession(base_url=exchange) as client_session:
            for symbol in SYMBOLS:
                try:
                    end_ms = int(time.time() * 1000)
                    start_ms = await _compute_start_ms(session_maker, symbol, timeframe, end_ms)
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
