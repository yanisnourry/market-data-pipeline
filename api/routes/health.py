from fastapi import APIRouter, Request
from sqlalchemy import select, func
from storage.models import CandleModel

router = APIRouter()

@router.get("/health")
async def health(request: Request):
    try:
        async with request.app.state.db.connect() as conn:
            await conn.execute(select(1))
        db_status = "ok"
    except Exception:
        db_status = "unhealthy"

    redis_status = "ok" if await request.app.state.redis.ping() else "unhealthy"
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

    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e)
        }