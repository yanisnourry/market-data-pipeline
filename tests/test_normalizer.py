import logging
from datetime import datetime, timezone
from decimal import Decimal

from ingestion.normalizer import _normalize, normalize_all

# Real Binance kline format (/api/v3/klines):
# [open_time, open, high, low, close, volume, close_time, ...(ignored)]
VALID_RAW = [
    1499040000000,
    "0.01634790",
    "0.80000000",
    "0.01575800",
    "0.01577100",
    "148976.11427815",
    1499644799999,
    "2434.19055334",
    308,
    "1756.87402397",
    "28.46694368",
    "17928899.62484339",
]


def test_normalize_valid_raw_returns_candle():
    candle = _normalize(VALID_RAW, symbol="BTCUSDT", exchange="binance", timeframe="1h")

    assert candle is not None
    assert candle.symbol == "BTCUSDT"
    assert candle.exchange == "binance"
    assert candle.timeframe == "1h"
    assert candle.open == Decimal("0.01634790")
    assert candle.high == Decimal("0.80000000")
    assert candle.low == Decimal("0.01575800")
    assert candle.close == Decimal("0.01577100")
    assert candle.volume == Decimal("148976.11427815")


def test_normalize_converts_open_time_ms_to_utc_datetime():
    candle = _normalize(VALID_RAW, symbol="BTCUSDT", exchange="binance", timeframe="1h")

    assert candle.timestamp == datetime(2017, 7, 3, 0, 0, tzinfo=timezone.utc)
    assert candle.timestamp.tzinfo is timezone.utc


def test_normalize_returns_none_on_missing_fields(caplog):
    raw = [1499040000000, "0.01"]  # missing high/low/close/volume

    with caplog.at_level(logging.WARNING):
        candle = _normalize(raw, symbol="BTCUSDT", exchange="binance", timeframe="1h")

    assert candle is None
    assert "BTCUSDT" in caplog.text


def test_normalize_returns_none_on_non_numeric_price():
    raw = list(VALID_RAW)
    raw[1] = "not-a-number"  # invalid open

    candle = _normalize(raw, symbol="BTCUSDT", exchange="binance", timeframe="1h")

    assert candle is None


def test_normalize_all_filters_out_invalid_entries():
    invalid_raw = [1499040000000, "0.01"]
    data = [VALID_RAW, invalid_raw, VALID_RAW]

    candles = normalize_all(data, symbol="BTCUSDT", exchange="binance", timeframe="1h")

    assert len(candles) == 2
    assert all(c is not None for c in candles)


def test_normalize_all_empty_data_returns_empty_list():
    assert normalize_all([], symbol="BTCUSDT", exchange="binance", timeframe="1h") == []
