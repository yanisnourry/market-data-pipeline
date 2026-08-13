from datetime import datetime, timedelta, timezone

from ingestion.fetcher import INTERVAL_MS
from ingestion.validator import (
    _has_gaps,
    _has_outlier_price,
    _has_outlier_volume,
    _inconsistency_ohlcv,
)

ONE_HOUR = timedelta(milliseconds=INTERVAL_MS["1h"])
T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


# --- _has_gaps -----------------------------------------------------------

def test_has_gaps_nominal_spacing_is_not_a_gap(make_candle):
    c1 = make_candle(timestamp=T0)
    c2 = make_candle(timestamp=T0 + ONE_HOUR)
    assert _has_gaps((c1, c2), "1h") is False


def test_has_gaps_one_second_over_is_a_gap(make_candle):
    c1 = make_candle(timestamp=T0)
    c2 = make_candle(timestamp=T0 + ONE_HOUR + timedelta(seconds=1))
    assert _has_gaps((c1, c2), "1h") is True


def test_has_gaps_missing_candle_is_a_gap(make_candle):
    c1 = make_candle(timestamp=T0)
    c2 = make_candle(timestamp=T0 + 2 * ONE_HOUR)
    assert _has_gaps((c1, c2), "1h") is True


# --- _has_outlier_price ----------------------------------------------------

def test_has_outlier_price_nominal_move_is_not_outlier(make_candle):
    c1 = make_candle(close=100)
    c2 = make_candle(close=110)
    assert _has_outlier_price((c1, c2)) is False


def test_has_outlier_price_exactly_twenty_percent_is_not_outlier(make_candle):
    c1 = make_candle(close=100)
    c2 = make_candle(close=120)
    assert _has_outlier_price((c1, c2)) is False


def test_has_outlier_price_over_twenty_percent_is_outlier(make_candle):
    c1 = make_candle(close=100)
    c2 = make_candle(close=121)
    assert _has_outlier_price((c1, c2)) is True


# --- _has_outlier_volume ---------------------------------------------------

def test_has_outlier_volume_nominal_is_not_outlier(make_candle):
    range_candle = [make_candle(volume=10) for _ in range(24)]
    candle = make_candle(volume=50)
    assert _has_outlier_volume(candle, range_candle) is False


def test_has_outlier_volume_exactly_ten_times_mean_is_not_outlier(make_candle):
    range_candle = [make_candle(volume=10) for _ in range(24)]
    candle = make_candle(volume=100)
    assert _has_outlier_volume(candle, range_candle) is False


def test_has_outlier_volume_over_ten_times_mean_is_outlier(make_candle):
    range_candle = [make_candle(volume=10) for _ in range(24)]
    candle = make_candle(volume=101)
    assert _has_outlier_volume(candle, range_candle) is True


# --- _inconsistency_ohlcv ---------------------------------------------------

def test_inconsistency_ohlcv_consistent_candle_is_valid(make_candle):
    candle = make_candle(open=100, close=100, high=101, low=99)
    assert _inconsistency_ohlcv(candle) is False


def test_inconsistency_ohlcv_high_below_body_is_inconsistent(make_candle):
    candle = make_candle(open=100, close=100, high=99, low=99)
    assert _inconsistency_ohlcv(candle) is True


def test_inconsistency_ohlcv_low_above_body_is_inconsistent(make_candle):
    candle = make_candle(open=100, close=100, high=101, low=101)
    assert _inconsistency_ohlcv(candle) is True
