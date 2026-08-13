import os
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ingestion.models import Candle
from storage.models import Base

load_dotenv()


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


def _db_url() -> str:
    return (
        f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )


@pytest.fixture
async def db_engine():
    """Engine connected to the real TimescaleDB (docker-compose).

    Cleans up the `candles` table after each test to keep tests independent.
    """
    engine = create_async_engine(_db_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE candles"))
    await engine.dispose()


@pytest.fixture
def db_sessionmaker(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def db_session(db_sessionmaker):
    async with db_sessionmaker() as session:
        yield session
