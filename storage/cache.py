import os
from decimal import Decimal
from redis.asyncio import Redis


async def set_last_price(client: Redis, symbol: str, price: Decimal) -> None:
    await client.setex(f"last_price:{symbol}", int(os.getenv('REDIS_TTL_SECONDS', 60)), str(price))

async def get_last_price(client: Redis, symbol: str) -> Decimal | None:
    value = await client.get(f"last_price:{symbol}")
    return Decimal(value.decode()) if value else None

async def delete_last_price(client: Redis, symbol: str) -> None:
    await client.getdel(f"last_price:{symbol}")