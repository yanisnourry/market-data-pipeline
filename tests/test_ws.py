import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import api.routes.ws as ws_module


class _FakeResult:
    def scalars(self):
        return self

    def all(self):
        return ["BTCUSDT"]


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        return _FakeResult()


class _FakeRedis:
    def __init__(self, fail: bool = False):
        self.fail = fail

    async def get(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        return b"100"


def _make_app(redis_fail: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(ws_module.router)
    app.state.session = _FakeSession
    app.state.redis = _FakeRedis(fail=redis_fail)
    app.state.ws_connections = 0
    return app


def test_ws_streams_prices_and_releases_slot_on_disconnect():
    app = _make_app()
    with TestClient(app).websocket_connect("/ws/prices") as ws:
        assert ws.receive_json() == {"symbol": "BTCUSDT", "price": "100"}
        assert app.state.ws_connections == 1

    assert app.state.ws_connections == 0


def test_ws_rejects_with_1013_when_cap_reached(monkeypatch):
    monkeypatch.setattr(ws_module, "WS_MAX_CONNECTIONS", 1)
    app = _make_app()
    app.state.ws_connections = 1  # the only slot is already taken

    with TestClient(app).websocket_connect("/ws/prices") as ws:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()

    assert exc_info.value.code == 1013
    assert app.state.ws_connections == 1  # the rejected client never took a slot


def test_ws_releases_slot_when_handler_crashes():
    # A Redis error is not a WebSocketDisconnect: only the finally block
    # can give the slot back.
    app = _make_app(redis_fail=True)
    with pytest.raises(ConnectionError):
        with TestClient(app).websocket_connect("/ws/prices") as ws:
            ws.receive_json()

    assert app.state.ws_connections == 0
