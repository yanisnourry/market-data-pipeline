from fastapi import APIRouter, Request, Query
from fastapi import HTTPException
from api.schemas import CandleResponse, UTCDatetime
from storage.repository import get_latest_candle, get_candles

router = APIRouter()

@router.get("/ohlcv/{symbol}/{timeframe}/latest", response_model=CandleResponse)
async def get_ohlcv_latest(request: Request, symbol: str, timeframe: str):
    async with request.app.state.session() as session:
        result = await get_latest_candle(session=session, symbol=symbol, timeframe=timeframe)
        if not result:
            raise HTTPException(status_code=404, detail="Candle not found")

        return result

@router.get("/ohlcv/{symbol}/{timeframe}", response_model=list[CandleResponse])
async def get_ohlcv(
        request: Request,
        symbol: str,
        timeframe: str,
        start: UTCDatetime = None,
        end: UTCDatetime = None,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0)
    ):
    async with request.app.state.session() as session:
        result = await get_candles(
            session=session,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            limit=limit,
            offset=offset
        )
        return result
