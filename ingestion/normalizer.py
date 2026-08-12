import logging
from datetime import timezone, datetime
from ingestion.models import Candle

logger = logging.getLogger(__name__)


def _normalize(raw: list, symbol: str, exchange: str, timeframe: str) -> Candle | None:
    try:
        dt = datetime.fromtimestamp(raw[0] / 1000, tz=timezone.utc)
        return Candle(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            open=raw[1],
            high=raw[2],
            low=raw[3],
            close=raw[4],
            volume=raw[5],
            timestamp=dt,
        )
    except Exception as e:
        logger.warning(f"Failed to normalize candle for {symbol} {timeframe}: {e} — raw={raw[:6]}")
        return None


def normalize_all(data: list, symbol: str, exchange: str, timeframe: str) -> list[Candle]:
    candles = [_normalize(raw, symbol, exchange, timeframe) for raw in data]
    return [c for c in candles if c is not None]
