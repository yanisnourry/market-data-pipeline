import asyncio
import os

from fastapi import APIRouter
from fastapi import WebSocket
from fastapi import WebSocketDisconnect

from api.utils import fetch_symbol
from storage.cache import get_last_price

router = APIRouter()

# Each connection polls Redis every second for as long as it stays open:
# the cap bounds that load no matter how many clients show up.
WS_MAX_CONNECTIONS = int(os.getenv("WS_MAX_CONNECTIONS", 50))
# RFC 6455 close code "Try Again Later": the server is overloaded, not broken.
WS_CLOSE_TRY_AGAIN_LATER = 1013

@router.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket):
    state = websocket.app.state
    # Accept before closing so the client receives the close code; closing
    # before accept only yields a bare HTTP 403 handshake failure.
    await websocket.accept()
    # No await between the check and the increment: the event loop cannot
    # switch coroutines in between, so no lock is needed.
    if state.ws_connections >= WS_MAX_CONNECTIONS:
        await websocket.close(code=WS_CLOSE_TRY_AGAIN_LATER)
        return
    state.ws_connections += 1
    try:
        async with state.session() as session:
            symbols = await fetch_symbol(session)
        while True:
            redis = state.redis
            for symbol in symbols:
                last_price = await get_last_price(redis, symbol)
                await websocket.send_json({"symbol": symbol, "price": str(last_price)})
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        # finally, not only the except: any other error (DB, Redis, a send on
        # a dead socket) must release the slot too, or the cap leaks.
        state.ws_connections -= 1