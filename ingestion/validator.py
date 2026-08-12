from statistics import mean
from ingestion.fetcher import INTERVAL_MS
from ingestion.models import Candle


def _has_gaps(candles_pair: tuple, interval: str) -> bool:
    c1, c2 = candles_pair
    delta = c2.timestamp - c1.timestamp
    delta_ms = delta.total_seconds() * 1000
    return delta_ms > INTERVAL_MS[interval]

def _has_outlier_price(candles_pair: tuple) -> bool:
    c1, c2 = candles_pair
    return abs(c2.close - c1.close) / c1.close > 0.20

def _has_outlier_volume(candle: Candle, range_candle: list[Candle]) -> bool:
    volume_list = [candle.volume for candle in range_candle]
    mean_volume = mean(volume_list)
    volume = candle.volume
    return volume > mean_volume * 10

def _inconsistency_ohlcv(candle: Candle):
    return candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close)

def _get_range(candles: list[Candle], index) -> list[Candle]:
    min_index = max(0, index-24)
    ranges = candles[min_index:index]
    return ranges

def validator(candles: list[Candle], timeframe: str) -> list[Candle]:
    result = []
    for index, candle in enumerate(candles):
        flags = {}
        if index > 0:
            prev_candle = candles[index - 1]
            candles_pair = prev_candle, candle
            if _has_gaps(candles_pair, timeframe):
                flags["has_gap"] = True
            if prev_candle.close > 0 and _has_outlier_price(candles_pair):
                flags["is_outlier"] = True

        range_candle = _get_range(candles, index)
        if len(range_candle) > 0 and _has_outlier_volume(candle, range_candle):
            flags["is_outlier"] = True
        if _inconsistency_ohlcv(candle):
            flags["is_inconsistency"] = True
        if flags:
            candle = candle.model_copy(update=flags)
        result.append(candle)

    return result
