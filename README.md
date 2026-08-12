# Market Data Pipeline

A production-grade market data ingestion pipeline built in Python. Fetches OHLCV candlestick data from Binance, stores it in TimescaleDB, exposes it via a REST/WebSocket API, and visualizes it in a Streamlit dashboard.

---

## Architecture

```
Binance REST API
      │
      ▼
┌─────────────┐
│  Fetcher    │  async HTTP (aiohttp), pagination, retry backoff
│  Normalizer │  raw → Pydantic Candle model
│  Validator  │  gap / outlier / OHLCV inconsistency detection
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│  TimescaleDB (hypertable)   │  NUMERIC prices, TIMESTAMPTZ, upsert idempotent
│  Redis (last price cache)   │  TTL-based, per symbol
└──────┬──────────────────────┘
       │
       ▼
┌─────────────┐
│  FastAPI    │  REST + WebSocket
│  APScheduler│  periodic fetch per timeframe
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Streamlit  │  candlestick chart + data quality metrics
└─────────────┘
```

---

## Stack

| Component | Technology |
|---|---|
| Language | Python 3.11 |
| Time-series DB | TimescaleDB (PostgreSQL 16) |
| Cache | Redis 7 |
| API | FastAPI + SQLAlchemy 2.0 async |
| Scheduler | APScheduler 3 |
| Dashboard | Streamlit + Plotly |
| Data source | Binance REST API (`/api/v3/klines`) |

---

## Getting started

### Prerequisites

- Docker + Docker Compose

### 1. Clone and configure

```bash
git clone <repo-url>
cd market-data-pipeline
cp .env.example .env
```

The `.env` file only needs your secrets (`DB_PASSWORD`). All other defaults work out of the box.

### 2. Start the full stack

```bash
docker-compose up -d
```

This starts all five services in the correct order:

| Service | URL | Description |
|---|---|---|
| `timescaledb` | `localhost:5432` | Time-series database |
| `redis` | `localhost:6379` | Last price cache |
| `init` | — | Initializes DB schema (runs once) |
| `api` | `http://localhost:8000` | REST + WebSocket API |
| `dashboard` | `http://localhost:8501` | Streamlit dashboard |

The `init` service creates the `candles` hypertable before the API starts. If you need to re-run it manually:

```bash
docker-compose run --rm init
```

### 3. Verify

```bash
# API health check
curl http://localhost:8000/health

# Swagger UI
open http://localhost:8000/docs

# Dashboard
open http://localhost:8501
```

---

## Local development (without Docker for the app)

If you want to run the API and dashboard locally while keeping the infra in Docker:

```bash
# Start only infra
docker-compose up -d timescaledb redis

# Install dependencies
pip install -r requirements.txt

# Initialize DB
python init_db.py

# Start API
uvicorn api.main:app --reload

# Start dashboard (separate terminal)
streamlit run dashboard/app.py
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service status (DB + Redis) |
| GET | `/health/data-quality` | Anomaly counts (gaps, outliers, inconsistencies) |
| GET | `/symbols` | Available trading pairs |
| GET | `/timeframes` | Configured timeframes |
| GET | `/ohlcv/{symbol}/{timeframe}` | Historical OHLCV data |
| GET | `/ohlcv/{symbol}/{timeframe}/latest` | Latest candle |
| WS  | `/ws/prices` | Live last price stream |

### Query parameters for `/ohlcv`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `start` | datetime (ISO 8601) | — | Start of range (UTC) |
| `end` | datetime (ISO 8601) | — | End of range (UTC) |
| `limit` | int [1–1000] | 100 | Max candles returned |
| `offset` | int | 0 | Pagination offset |

---

## Data validation

The validator flags anomalies without discarding data:

| Anomaly | Detection rule | Flag |
|---|---|---|
| Gap | `delta > 1 × timeframe_duration` | `has_gap = True` |
| Price outlier | `\|close[i] - close[i-1]\| / close[i-1] > 20%` | `is_outlier = True` |
| Volume outlier | `volume > mean(last 24 candles) × 10` | `is_outlier = True` |
| OHLCV inconsistency | `high < max(open, close)` or `low > min(open, close)` | `is_inconsistency = True` |
| Duplicate | `(timestamp, symbol, exchange, timeframe)` conflict | Ignored silently (upsert) |

Anomaly counts are exposed at `GET /health/data-quality`.

---

## Environment variables

Copy `.env.example` to `.env`. All defaults work with the provided `docker-compose.yml`.

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=market_data
DB_USER=postgres
DB_PASSWORD=postgres

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_TTL_SECONDS=60

# Binance
BINANCE_BASE_URL=https://api.binance.com

# App
LOG_LEVEL=INFO
ENVIRONMENT=development
```

---

## Project structure

```
market-data-pipeline/
├── docker-compose.yml
├── .env.example
├── init_db.py
│
├── ingestion/
│   ├── models.py        Pydantic Candle schema
│   ├── fetcher.py       async Binance fetch, pagination, retry
│   ├── normalizer.py    raw list → Candle
│   └── validator.py     gap / outlier / inconsistency detection
│
├── storage/
│   ├── models.py        SQLAlchemy CandleModel + init_db()
│   ├── repository.py    insert_candles, get_candles, get_latest_candle
│   └── cache.py         Redis last price (set / get / delete)
│
├── api/
│   ├── main.py          FastAPI app, lifespan, APScheduler setup
│   ├── schemas.py       CandleResponse (Pydantic)
│   ├── utils.py         shared DB queries
│   └── routes/
│       ├── health.py    /health, /health/data-quality
│       ├── symbols.py   /symbols, /timeframes
│       ├── ohlcv.py     /ohlcv/{symbol}/{timeframe}
│       └── ws.py        /ws/prices WebSocket
│
├── scheduler/
│   ├── config.py        SYMBOLS, TIMEFRAMES, TIMEFRAME_SCHEDULE
│   └── jobs.py          fetch_and_store() job definition
│
├── dashboard/
│   └── app.py           Streamlit: candlestick + data quality
│
└── docs/
    └── architecture.md  Technical decisions
```
