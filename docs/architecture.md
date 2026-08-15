# Architecture — Market Data Pipeline

## Overview

This document covers the technical decisions made during the design and implementation of the pipeline. It is intended as a reference for understanding *why* things are built the way they are.

---

## Data flow

```
Binance /api/v3/klines
        │
        │  raw list[list]
        ▼
   fetcher.py          — async HTTP, pagination, retry
        │
        │  raw list[list]
        ▼
  normalizer.py        — raw → Pydantic Candle (typed, immutable)
        │
        │  list[Candle]
        ▼
   validator.py        — flags: has_gap, is_outlier, is_inconsistency
        │
        │  list[Candle] (with flags)
        ▼
  repository.py        — INSERT ... ON CONFLICT DO NOTHING
        │
        ├──► TimescaleDB  (persistent, time-series optimized)
        └──► Redis cache  (last price, TTL 60s)
```

---

## Key decisions

### TimescaleDB over plain PostgreSQL

TimescaleDB partitions the `candles` table automatically by time (hypertable). This gives:
- Faster range queries on `timestamp` without manual partitioning
- Native time-series functions (`time_bucket`, `first`, `last`) available for future use
- Drop-in PostgreSQL compatibility — no ORM changes needed

### NUMERIC for all prices, never FLOAT

`FLOAT` is binary-precision (IEEE 754). For financial data, `0.1 + 0.2 != 0.3`. All price and volume columns use `NUMERIC(20, 8)`, which guarantees exact decimal arithmetic. Python's `Decimal` type is used throughout for the same reason.

### TIMESTAMPTZ — always UTC, never naive

All timestamps are stored as `TIMESTAMPTZ` (timezone-aware). Python datetimes are always constructed with `tz=timezone.utc`. This prevents silent timezone conversion bugs when the server locale changes.

### Immutable Candle model (`frozen=True`)

The `Candle` Pydantic model uses `frozen=True`. Validator flags are applied via `model_copy(update=flags)` which creates a new instance instead of mutating in place. This makes the validation pipeline predictable and testable: a candle at any stage of the pipeline is a complete, valid object.

### Upsert idempotence (`ON CONFLICT DO UPDATE ... WHERE`)

The primary key is `(timestamp, symbol, exchange, timeframe)`. If the scheduler re-fetches a range that was already stored (restart, overlap), the row is only rewritten when at least one OHLCV column actually differs (`IS DISTINCT FROM` on `open`/`high`/`low`/`close`/`volume` in the `WHERE` clause) — an unchanged duplicate is a no-op update, not a fresh write. This also lets a re-fetch correct a candle that Binance revised after the fact (e.g. a late trade updating the close of the current, still-forming candle), instead of permanently keeping the first value seen. The pipeline can be re-run without producing inconsistent data.

### Async throughout (aiohttp + asyncpg + redis.asyncio)

The entire stack is async to avoid blocking the event loop during I/O. Key choices:
- `aiohttp.ClientSession` for outbound HTTP (Binance)
- `asyncpg` driver via SQLAlchemy 2.0 async for DB writes
- `redis.asyncio` for cache operations
- `asyncio.Semaphore(10)` to cap concurrent Binance requests

### Retry with exponential backoff

`_fetch_chunk` retries up to 3 times on any `aiohttp.ClientError` (covers both HTTP errors and network-level failures). Wait times: 1s → 2s → 4s. On the third failure, the exception propagates and is caught by the job-level `try/except` in `scheduler/jobs.py`.

### Scheduler: one job per timeframe

APScheduler runs one `fetch_and_store` job per configured timeframe (1m, 5m, 1h, 1d). Each job fetches only the last interval worth of candles (`end_ms - INTERVAL_MS[timeframe]` to `end_ms`). Jobs are independent and isolated: a failure in the 1m job does not affect the 1h job.

---

## Database schema

```sql
CREATE TABLE candles (
    timestamp         TIMESTAMPTZ     NOT NULL,
    symbol            VARCHAR(20)     NOT NULL,
    exchange          VARCHAR(20)     NOT NULL,
    timeframe         VARCHAR(5)      NOT NULL,
    open              NUMERIC(20, 8)  NOT NULL,
    high              NUMERIC(20, 8)  NOT NULL,
    low               NUMERIC(20, 8)  NOT NULL,
    close             NUMERIC(20, 8)  NOT NULL,
    volume            NUMERIC(30, 8)  NOT NULL,
    has_gap           BOOLEAN         NOT NULL,
    is_outlier        BOOLEAN         NOT NULL,
    is_inconsistency  BOOLEAN         NOT NULL,
    PRIMARY KEY (timestamp, symbol, exchange, timeframe)
);

SELECT create_hypertable('candles', 'timestamp', if_not_exists => TRUE);

CREATE INDEX ON candles (symbol, timeframe, timestamp DESC);
```

`create_hypertable` is only called from `init_db.py`, not from the test fixtures — CI and local tests run `candles` as a plain PostgreSQL table.

---

## Validation rules

| Anomaly | Rule | Notes |
|---|---|---|
| Gap | `delta_ms > INTERVAL_MS[timeframe]` | Flagged on candle[i], compared to candle[i-1] |
| Price outlier | `\|close[i] - close[i-1]\| / close[i-1] > 0.20` | Guard: `close[i-1] > 0` to avoid division by zero |
| Volume outlier | `volume > mean(window) × 10` | Window = last 24 candles |
| OHLCV inconsistency | `high < max(open, close)` or `low > min(open, close)` | Physically impossible candle |

Anomalies are flagged, not dropped. The decision to exclude flagged data is left to the consumer (API client or downstream project).

---

## API design

### Startup validation

On startup (FastAPI lifespan), the app verifies DB and Redis connectivity before accepting traffic. If either is unavailable, the process exits immediately with a logged error rather than starting in a degraded state.

### Two Pydantic models for ingestion vs API

- `ingestion.models.Candle` — immutable, used through the ingestion pipeline
- `api.schemas.CandleResponse` — inherits from `Candle`, adds `model_config` with `from_attributes=True` to deserialize SQLAlchemy row objects

This separation avoids coupling the API schema to the ingestion model.

### WebSocket `/ws/prices`

On connection, the handler queries the list of known symbols from DB, then enters a loop that reads each symbol's last price from Redis every second and streams them to the client. Redis acts as a write-through cache: every successful `insert_candles` call updates `last_price:{symbol}` with a 60-second TTL.

---

## Downstream projects

This pipeline is designed to feed two downstream projects:

- **Project 2 — Vectorized Backtester**: reads historical OHLCV via `storage.repository` directly
- **Project 3 — Risk Dashboard**: consumes data via the REST API

No strategy logic or signal computation belongs in this project.
