from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from storage.models import CandleModel
from storage.repository import insert_candles

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
ONE_HOUR = timedelta(hours=1)


async def _count(db_session, symbol="BTCUSDT") -> int:
    result = await db_session.execute(
        select(func.count()).select_from(CandleModel).where(CandleModel.symbol == symbol)
    )
    return result.scalar_one()


async def test_insert_candles_is_idempotent_on_exact_refetch(db_session, make_candle):
    candles = [
        make_candle(timestamp=T0 + i * ONE_HOUR)
        for i in range(5)
    ]

    await insert_candles(db_session, candles)
    await insert_candles(db_session, candles)  # identical refetch

    assert await _count(db_session) == 5


async def test_insert_candles_no_duplicate_on_overlapping_refetch(db_session, make_candle):
    first_batch = [make_candle(timestamp=T0 + i * ONE_HOUR) for i in range(3)]  # h0, h1, h2
    second_batch = [make_candle(timestamp=T0 + i * ONE_HOUR) for i in range(1, 4)]  # h1, h2, h3

    await insert_candles(db_session, first_batch)
    await insert_candles(db_session, second_batch)

    assert await _count(db_session) == 4  # h0, h1, h2, h3 — no duplicate on h1/h2


async def test_insert_candles_empty_list_is_a_noop(db_session):
    await insert_candles(db_session, [])
    assert await _count(db_session) == 0
