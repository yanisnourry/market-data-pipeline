import asyncio
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine
from storage.models import init_db
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


async def main():
    db_url = (
        f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
    engine = create_async_engine(db_url)
    try:
        await init_db(engine)
        logger.info("Database initialized successfully")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
