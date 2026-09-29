SYMBOLS = ["BTCUSDT", "ETHUSDT", "BTCUSDC"]
TIMEFRAMES = ["1m", "5m", "15m", "1h", "1d"]
TIMEFRAME_SCHEDULE = {
    "1m": {"minutes": 1},
    "5m": {"minutes": 5},
    "15m": {"minutes": 15},
    "1h": {"hours": 1},
    "1d": {"hours": 24},
}
# How far back to fetch the first time a (symbol, timeframe) series is seen,
# sized to ~10k candles per series (9 to 11 Binance requests) rather than a
# uniform number of days: 90 days of 1m alone would be ~130k candles. The 1h
# horizon covers backtester-service's 30-day lookback plus SMA warmup with room
# to spare. Also caps how far a single tick reaches back after a long outage.
_DAY_MS = 86_400_000
INITIAL_BACKFILL_MS = {
    "1m": 7 * _DAY_MS,
    "5m": 30 * _DAY_MS,
    "15m": 90 * _DAY_MS,
    "1h": 365 * _DAY_MS,
    "1d": 5 * 365 * _DAY_MS,
}
