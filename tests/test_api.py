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


async def test_data_quality_does_not_leak_exception_text(caplog):
    secret = "password authentication failed for user postgres@10.0.0.5"

    def broken_sessionmaker():
        raise RuntimeError(secret)

    app = FastAPI()
    app.include_router(health_router)
    app.state.session = broken_sessionmaker

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/data-quality")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert secret not in response.text
    assert secret in caplog.text


async def test_data_quality_zero_when_no_data(api_client, db_session):
    async with api_client as client:
        response = await client.get("/health/data-quality")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["has_gap"] == 0
    assert body["data"]["is_outlier"] == 0
    assert body["data"]["is_inconsistency"] == 0


class _FakeConn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        return None


class _FakeEngine:
    """Stands in for app.state.db: connect() either works or raises."""

    def __init__(self, up: bool):
        self.up = up

    def connect(self):
        if not self.up:
            raise ConnectionRefusedError("db down")
        return _FakeConn()


class _FakeRedis:
    """Stands in for app.state.redis: ping() raises when down, like redis-py."""

    def __init__(self, up: bool):
        self.up = up

    async def ping(self):
        if not self.up:
            raise ConnectionError("redis down")
        return True


async def _get_health(db_up: bool, redis_up: bool):
    app = FastAPI()
    app.include_router(health_router)
    app.state.db = _FakeEngine(db_up)
    app.state.redis = _FakeRedis(redis_up)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/health")


async def test_health_ok_when_all_dependencies_up():
    response = await _get_health(db_up=True, redis_up=True)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "redis": "ok"}


async def test_health_503_when_db_down():
    response = await _get_health(db_up=False, redis_up=True)

    assert response.status_code == 503
    assert response.json()["db"] == "unhealthy"


async def test_health_degraded_but_200_when_redis_down():
    response = await _get_health(db_up=True, redis_up=False)

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "db": "ok", "redis": "unhealthy"}

