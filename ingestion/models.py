from decimal import Decimal
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class Candle(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp: datetime
    symbol: str
    exchange: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    has_gap: bool = False
    is_outlier: bool = False
    is_inconsistency: bool = False