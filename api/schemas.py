from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, ConfigDict
from ingestion.models import Candle


class CandleResponse(Candle):
    model_config = ConfigDict(frozen=True, from_attributes=True)


def _ensure_utc_aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        raise ValueError("must include a timezone offset, e.g. 2024-01-01T00:00:00Z")
    return dt


# Query param datetime: rejects naive datetimes (422) instead of letting them
# flow through to the SQL query, where their interpretation would depend on the server timezone.
UTCDatetime = Annotated[datetime | None, AfterValidator(_ensure_utc_aware)]
