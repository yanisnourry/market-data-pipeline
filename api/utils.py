from sqlalchemy import select
from storage.models import CandleModel


async def fetch_symbol(session) -> list[str]:
    stmt = select(CandleModel.symbol).distinct()
    result = await session.execute(stmt)
    return result.scalars().all()