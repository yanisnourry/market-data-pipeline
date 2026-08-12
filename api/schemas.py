from pydantic import ConfigDict
from ingestion.models import Candle


class CandleResponse(Candle):
    model_config = ConfigDict(frozen=True, from_attributes=True)
