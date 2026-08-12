from fastapi import APIRouter, Request
from api.utils import fetch_symbol
from scheduler.config import TIMEFRAMES

router = APIRouter()

@router.get("/symbols")
async def get_symbols(request: Request):
    async with request.app.state.session() as session:
        symbols = await fetch_symbol(session)
        return symbols

@router.get("/timeframes")
async def get_timeframes(request: Request):
    return TIMEFRAMES

