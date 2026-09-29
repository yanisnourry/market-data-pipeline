import logging

from fastapi import APIRouter, Request, Response
from sqlalchemy import select, func
from storage.models import CandleModel

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/health")
async def health(request: Request, response: Response):
    try:
        async with request.app.state.db.connect() as conn:
            await conn.execute(select(1))
        db_status = "ok"
    except Exception:
        db_status = "unhealthy"

    # ping() raises on a lost connection instead of returning False: without
    # the try, a Redis outage would turn this endpoint into a 500.
    try:
        redis_status = "ok" if await request.app.state.redis.ping() else "unhealthy"
    except Exception:
        redis_status = "unhealthy"

    # Without the DB nothing can be served: 503 lets the readiness probe pull
    # the pod out of the Service. A Redis outage only degrades cache and
    # WebSocket (/ohlcv still reads the DB), so the pod stays in rotation.
    if db_status != "ok":
        response.status_code = 503

    status_list = [db_status, redis_status]
    status = "ok" if all(s == "ok" for s in status_list) else "degraded"
    return {"status": status, "db": db_status, "redis": redis_status}

@router.get("/health/data-quality")
async def data_quality(request: Request):
    try:
        async with request.app.state.session() as session:
            stmt = select(
                func.count().filter(CandleModel.has_gap.is_(True)).label("has_gap"),
                func.count().filter(CandleModel.is_outlier.is_(True)).label("is_outlier"),
                func.count().filter(CandleModel.is_inconsistency.is_(True)).label("is_inconsistency"),
            ).select_from(CandleModel)
            result = await session.execute(stmt)
            stats = result.mappings().one()

        return {
            "status": "ok",
            "data": stats
        }

    except Exception:
        # Full traceback stays in server logs; the public response must not
        # leak driver messages (host, user, SQL, schema details).
        logger.exception("data-quality query failed")
        return {
            "status": "degraded",
            "error": "data quality stats unavailable"
        }