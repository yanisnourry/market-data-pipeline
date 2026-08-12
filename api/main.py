import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import redis.asyncio as redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from scheduler.config import TIMEFRAMES, TIMEFRAME_SCHEDULE
from scheduler.jobs import fetch_and_store
from api.routes.health import router as health_router
from api.routes.symbols import router as symbols_router
from api.routes.ohlcv import router as ohlcv_router
from api.routes.ws import router as ws_router
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

db_url = f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = create_async_engine(
        db_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
    )
    app.state.session = async_sessionmaker(
        bind=app.state.db,
        expire_on_commit=False,
    )
    app.state.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)

    # Validate DB connectivity at startup
    try:
        async with app.state.db.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection OK")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

    # Validate Redis connectivity at startup
    try:
        await app.state.redis.ping()
        logger.info("Redis connection OK")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise

    scheduler = AsyncIOScheduler()
    for timeframe in TIMEFRAMES:
        scheduler.add_job(
            fetch_and_store,
            "interval",
            **TIMEFRAME_SCHEDULE[timeframe],
            kwargs={
                "session_maker": app.state.session,
                "redis_client": app.state.redis,
                "timeframe": timeframe,
            },
        )
    scheduler.start()
    logger.info(f"Scheduler started with {len(TIMEFRAMES)} jobs: {TIMEFRAMES}")

    yield

    scheduler.shutdown()
    await app.state.db.dispose()
    await app.state.redis.aclose()
    logger.info("Shutdown complete")


app = FastAPI(lifespan=lifespan)

app.include_router(health_router)
app.include_router(symbols_router)
app.include_router(ohlcv_router)
app.include_router(ws_router)
