import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from ingestion.models import Candle
from storage.models import CandleModel

logger = logging.getLogger(__name__)


async def insert_candles(session: AsyncSession, candles: list[Candle]) -> None:
    if not candles:
        return
    rows = [candle.model_dump() for candle in candles]
    stmt = insert(CandleModel).values(rows)
    stmt = stmt.on_conflict_do_nothing()
    result = await session.execute(stmt)
    await session.commit()
    inserted = result.rowcount if result.rowcount >= 0 else len(rows)
    skipped = len(rows) - inserted
    logger.debug(f"Inserted {inserted} candles, skipped {skipped} duplicates")


async def get_candles(session: AsyncSession, symbol, timeframe, start, end, limit, offset) -> Sequence[CandleModel]:
    stmt = select(CandleModel).where(
        CandleModel.symbol == symbol,
        CandleModel.timeframe == timeframe,
    )
    if start:
        stmt = stmt.where(CandleModel.timestamp >= start)
    if end:
        stmt = stmt.where(CandleModel.timestamp <= end)
    stmt = stmt.order_by(CandleModel.timestamp.asc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_latest_candle(session: AsyncSession, symbol, timeframe) -> CandleModel | None:
    stmt = select(CandleModel).where(
        CandleModel.symbol == symbol,
        CandleModel.timeframe == timeframe,
    ).order_by(CandleModel.timestamp.desc()).limit(1)
    result = await session.execute(stmt)
    return result.scalars().first()
