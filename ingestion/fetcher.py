import logging
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

BINANCE_MAX_CANDLES = 1000
INTERVAL_MS = {
    "1m":  60_000,
    "3m":  180_000,
    "5m":  300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h":  3_600_000,
    "2h":  7_200_000,
    "4h":  14_400_000,
    "6h":  21_600_000,
    "8h":  28_800_000,
    "12h": 43_200_000,
    "1d":  86_400_000,
    "3d":  259_200_000,
    "1w":  604_800_000,
    "1M":  2_592_000_000,
}


def compute_start_ms(interval: str, start_ms: int, end_ms: int) -> list[int]:
    current_ms = start_ms
    all_start_ms = []
    while current_ms < end_ms:
        all_start_ms.append(current_ms)
        current_ms += BINANCE_MAX_CANDLES * INTERVAL_MS[interval]
    return all_start_ms


async def _fetch_chunk(
        session: aiohttp.ClientSession,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        sem: asyncio.Semaphore,
) -> list[list]:
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": BINANCE_MAX_CANDLES,
    }
    async with sem:
        for attempt in range(3):
            try:
                async with session.get("/api/v3/klines", params=params) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    return data
            except aiohttp.ClientError as e:
                if attempt == 2:
                    logger.error(f"Fetch failed after 3 attempts for {symbol} {interval}: {e}")
                    raise
                wait = 2 ** attempt
                logger.warning(f"Fetch attempt {attempt + 1} failed for {symbol} {interval}: {e} — retrying in {wait}s")
                await asyncio.sleep(wait)
    raise RuntimeError("unreachable")


async def fetch_candles(
        session: aiohttp.ClientSession,
        symbol: str,
        timeframe: str,
        start_ms: int,
        end_ms: int,
) -> list[list]:
    all_start_ms = compute_start_ms(timeframe, start_ms, end_ms)
    sem = asyncio.Semaphore(10)
    coroutines = [
        _fetch_chunk(
            session=session,
            symbol=symbol,
            interval=timeframe,
            start_ms=new_start_ms,
            end_ms=min(new_start_ms + BINANCE_MAX_CANDLES * INTERVAL_MS[timeframe], end_ms),
            sem=sem,
        )
        for new_start_ms in all_start_ms
    ]
    data = await asyncio.gather(*coroutines)
    return [c for chunk in data for c in chunk]
