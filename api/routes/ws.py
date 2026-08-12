import asyncio

from fastapi import APIRouter
from fastapi import WebSocket
from fastapi import WebSocketDisconnect

from api.utils import fetch_symbol
from storage.cache import get_last_price

router = APIRouter()

@router.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket):
    await websocket.accept()
    try:
        async with websocket.app.state.session() as session:
            symbols = await fetch_symbol(session)
        while True:
            redis = websocket.app.state.redis
            for symbol in symbols:
                last_price = await get_last_price(redis, symbol)
                await websocket.send_json({"symbol": symbol, "price": str(last_price)})
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass