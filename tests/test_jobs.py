from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from ingestion.fetcher import INTERVAL_MS
from scheduler.config import INITIAL_BACKFILL_MS
from scheduler.jobs import fetch_and_store
from storage.models import CandleModel
from storage.repository import insert_candles

TF = "1h"
STEP_MS = INTERVAL_MS[TF]
# Mid-hour, so the latest Binance kline is still in progress, as in production.
NOW = datetime(2024, 6, 1, 12, 30, tzinfo=timezone.utc)
NOW_MS = int(NOW.timestamp() * 1000)
CURRENT_OPEN = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


class FakeBinance:
    """Stands in for fetch_candles: records each requested window and returns
    one kline per interval whose open time is >= start_ms (Binance semantics)."""

    def __init__(self, close="100"):
        self.close = close
        self.calls = []

    async def __call__(self, session, symbol, timeframe, start_ms, end_ms):
        self.calls.append((start_ms, end_ms))
        first_open = -(-start_ms // STEP_MS) * STEP_MS  # ceil to the interval grid
        return [
            [open_ms, "100", "201", "99", self.close, "10"]
            for open_ms in range(first_open, end_ms + 1, STEP_MS)
        ]


@pytest.fixture
def fake_binance():
    fake = FakeBinance()
    with patch("scheduler.jobs.fetch_candles", new=fake), \
            patch("scheduler.jobs.SYMBOLS", ["BTCUSDT"]), \
            patch("scheduler.jobs.time.time", return_value=NOW.timestamp()), \
            patch("scheduler.jobs.set_last_price", new_callable=AsyncMock):
        yield fake


async def _run(db_sessionmaker):
    await fetch_and_store(session_maker=db_sessionmaker, redis_client=AsyncMock(), timeframe=TF)


async def _stored(db_sessionmaker) -> list[CandleModel]:
    async with db_sessionmaker() as session:
        result = await session.execute(select(CandleModel).order_by(CandleModel.timestamp))
        return list(result.scalars().all())


async def _seed(db_sessionmaker, make_candle, timestamps, **fields):
    async with db_sessionmaker() as session:
        await insert_candles(session, [
            make_candle(timestamp=ts, exchange="BINANCE", timeframe=TF, **fields) for ts in timestamps
        ])


async def test_empty_db_fetches_initial_backfill(db_sessionmaker, fake_binance):
    await _run(db_sessionmaker)

    assert fake_binance.calls == [(NOW_MS - INITIAL_BACKFILL_MS[TF], NOW_MS)]
    stored = await _stored(db_sessionmaker)
    assert len(stored) == INITIAL_BACKFILL_MS[TF] // STEP_MS


async def test_recent_latest_resumes_at_latest_candle(db_sessionmaker, make_candle, fake_binance):
    await _seed(db_sessionmaker, make_candle, [CURRENT_OPEN])

    await _run(db_sessionmaker)

    # Starts AT the latest candle (not +1 interval) so the open candle gets refetched.
    assert fake_binance.calls == [(_ms(CURRENT_OPEN), NOW_MS)]


async def test_multi_day_gap_is_filled_exactly(db_sessionmaker, make_candle, fake_binance):
    last_before_outage = CURRENT_OPEN - timedelta(days=3)
    await _seed(db_sessionmaker, make_candle, [last_before_outage - timedelta(hours=1), last_before_outage])

    await _run(db_sessionmaker)

    assert fake_binance.calls == [(_ms(last_before_outage), NOW_MS)]
    stored = [c.timestamp for c in await _stored(db_sessionmaker)]
    expected = [last_before_outage - timedelta(hours=1) + i * timedelta(hours=1) for i in range(3 * 24 + 2)]
    assert stored == expected  # contiguous, no hole, nothing beyond the current candle


async def test_gap_beyond_horizon_is_capped(db_sessionmaker, make_candle, fake_binance):
    too_old = NOW - timedelta(milliseconds=INITIAL_BACKFILL_MS[TF]) - timedelta(days=10)
    await _seed(db_sessionmaker, make_candle, [too_old.replace(minute=0)])

    await _run(db_sessionmaker)

    assert fake_binance.calls == [(NOW_MS - INITIAL_BACKFILL_MS[TF], NOW_MS)]


async def test_in_progress_candle_is_overwritten_with_final_values(db_sessionmaker, make_candle, fake_binance):
    await _seed(db_sessionmaker, make_candle, [CURRENT_OPEN], close=100)
    fake_binance.close = "200"

    await _run(db_sessionmaker)

    stored = {c.timestamp: c for c in await _stored(db_sessionmaker)}
    assert stored[CURRENT_OPEN].close == 200


async def test_rerun_on_up_to_date_data_creates_no_duplicate(db_sessionmaker, make_candle, fake_binance):
    await _seed(db_sessionmaker, make_candle, [CURRENT_OPEN - timedelta(hours=5)])

    await _run(db_sessionmaker)
    first = len(await _stored(db_sessionmaker))
    await _run(db_sessionmaker)

    assert len(await _stored(db_sessionmaker)) == first == 6
