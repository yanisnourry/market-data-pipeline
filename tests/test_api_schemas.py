import pytest
from pydantic import BaseModel, ValidationError

from api.schemas import UTCDatetime


class _Params(BaseModel):
    start: UTCDatetime = None


def test_naive_datetime_is_rejected():
    with pytest.raises(ValidationError):
        _Params(start="2024-01-01T00:00:00")  # no offset -> naive


def test_utc_aware_datetime_is_accepted():
    params = _Params(start="2024-01-01T00:00:00Z")
    assert params.start.tzinfo is not None


def test_offset_aware_datetime_is_accepted():
    params = _Params(start="2024-01-01T00:00:00+02:00")
    assert params.start.tzinfo is not None


def test_none_is_accepted():
    params = _Params(start=None)
    assert params.start is None
