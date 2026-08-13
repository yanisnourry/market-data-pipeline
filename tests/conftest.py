from datetime import datetime, timezone

import pytest

from ingestion.models import Candle


@pytest.fixture
def make_candle():
    """Factory to build a test Candle without repeating every field.

    Usage: make_candle(timestamp=..., close=Decimal("100")) — unspecified
    fields fall back to a neutral default value.
    """

    def _make(
        timestamp: datetime = datetime(2024, 1, 1, tzinfo=timezone.utc),
        symbol: str = "BTCUSDT",
        exchange: str = "binance",
        timeframe: str = "1h",
        open=100,
        high=101,
        low=99,
        close=100,
        volume=10,
        **overrides,
    ) -> Candle:
        return Candle(
            timestamp=timestamp,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
            **overrides,
        )

    return _make
