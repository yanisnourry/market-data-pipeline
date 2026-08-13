from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routes.health import router as health_router
from storage.repository import insert_candles

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
ONE_HOUR = timedelta(hours=1)


@pytest.fixture
def api_client(db_sessionmaker):
    """Minimal FastAPI app: just the health router, no Redis/scheduler.

    We don't want to depend on the full api/main.py lifespan to test
    a route that only touches the DB.
    """
    app = FastAPI()
    app.include_router(health_router)
    app.state.session = db_sessionmaker
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_data_quality_reflects_real_counts(api_client, db_session, make_candle):
    candles = [
        make_candle(timestamp=T0, has_gap=True),
        make_candle(timestamp=T0 + ONE_HOUR, is_outlier=True),
        make_candle(timestamp=T0 + 2 * ONE_HOUR, is_inconsistency=True),
        make_candle(timestamp=T0 + 3 * ONE_HOUR),  # clean candle, no flag
    ]
    await insert_candles(db_session, candles)

    async with api_client as client:
        response = await client.get("/health/data-quality")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["has_gap"] == 1
    assert body["data"]["is_outlier"] == 1
    assert body["data"]["is_inconsistency"] == 1


async def test_data_quality_zero_when_no_data(api_client, db_session):
    async with api_client as client:
        response = await client.get("/health/data-quality")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["has_gap"] == 0
    assert body["data"]["is_outlier"] == 0
    assert body["data"]["is_inconsistency"] == 0
