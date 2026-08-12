import asyncio

import aiohttp
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ingestion.fetcher import fetch_candles
from ingestion.normalizer import normalize_all
from ingestion.validator import validator
from storage.repository import insert_candles
from dotenv import load_dotenv
import os

load_dotenv()
db_url = f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

async def main():
  base_url = "https://api.binance.com"
  async with aiohttp.ClientSession(base_url) as session:
      data = await fetch_candles(session, "BTCUSDT", "1h",
                                 start_ms=1775030400 * 1000,  # un timestamp quelconque
                                 end_ms=1775062800 * 1000,
                                 )
      candles = normalize_all(data=data, symbol="BTCUSDT", exchange="BINANCE", timeframe="1h")
      candles = validator(candles=candles, interval="1h")

  engine = create_async_engine(
      db_url,
      echo=True
  )
  SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
  async with SessionLocal() as session:
      await insert_candles(session, candles)

if __name__ == "__main__":
    asyncio.run(main())