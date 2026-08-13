"""Bloc B — Data correctness: UTC timestamps everywhere, Decimal everywhere.

These tests prove the property end-to-end (insert -> DB -> read back),
not just at the Pydantic model level.
"""
from datetime import datetime, timezone
from decimal import Decimal

from storage.repository import get_candles, insert_candles

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


async def test_stored_timestamp_round_trips_as_utc_aware(db_session, make_candle):
    await insert_candles(db_session, [make_candle(timestamp=T0)])

    result = await get_candles(
        db_session, symbol="BTCUSDT", timeframe="1h", start=None, end=None, limit=10, offset=0
    )

    assert len(result) == 1
    assert result[0].timestamp.tzinfo is not None
    assert result[0].timestamp == T0


async def test_stored_prices_are_decimal_not_float(db_session, make_candle):
    await insert_candles(
        db_session,
        [make_candle(timestamp=T0, open="27123.45678901", close="27200.00000001")],
    )

    result = await get_candles(
        db_session, symbol="BTCUSDT", timeframe="1h", start=None, end=None, limit=10, offset=0
    )

    candle = result[0]
    assert isinstance(candle.open, Decimal)
    assert isinstance(candle.close, Decimal)
    assert isinstance(candle.volume, Decimal)
    # zero IEEE-754 binary rounding error: the exact value must survive the round-trip
    assert candle.open == Decimal("27123.45678901")
