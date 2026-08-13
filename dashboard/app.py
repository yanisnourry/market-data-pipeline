import os
import streamlit as st
import requests
import plotly.graph_objects as go

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

st.set_page_config(
    page_title="Market Data Pipeline",
    page_icon="📈",
    layout="wide"
)

@st.cache_data(ttl=60)  # Re-fetch every 60 seconds
def fetch_symbols() -> list[str]:
    response = requests.get(f"{API_BASE}/symbols", timeout=5)
    response.raise_for_status()
    return response.json()

@st.cache_data(ttl=60)
def fetch_timeframes() -> list[str]:
    response = requests.get(f"{API_BASE}/timeframes", timeout=5)
    response.raise_for_status()
    return response.json()

@st.cache_data(ttl=60)
def fetch_ohlcv(symbol, timeframe) -> list[dict]:
    response = requests.get(f"{API_BASE}/ohlcv/{symbol}/{timeframe}?limit=500", timeout=5)
    response.raise_for_status()
    return response.json()

st.title("📊 MARKET DATA PIPELINE")
# --- Sidebar: selectors ---
with st.sidebar:
    st.header("⚙️ Configuration")
    try:
        symbols = fetch_symbols()
        timeframes = fetch_timeframes()
    except requests.exceptions.RequestException as e:
        st.error(f"API inaccessible : {e}")
        st.stop()

    symbol = st.selectbox(
        "Symbols",
        symbols
    )
    timeframe = st.selectbox(
        "Timeframe",
        timeframes
    )

# --- Section 1: Candlestick ---
st.header("Candlestick")
try:
    ohlcv = fetch_ohlcv(symbol, timeframe)
except requests.exceptions.RequestException as e:
    st.error(f"API inaccessible : {e}")
    st.stop()

if not ohlcv:
    st.warning("Aucune donnée disponible");
    st.stop()

timestamps = [c["timestamp"] for c in ohlcv]
opens      = [c["open"] for c in ohlcv]
highs      = [c["high"] for c in ohlcv]
lows       = [c["low"] for c in ohlcv]
closes     = [c["close"] for c in ohlcv]

fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=timestamps,
    open=opens,
    high=highs,
    low=lows,
    close=closes,
    name=symbol
))
fig.update_layout(
    title=f"{symbol} — {timeframe}",
    xaxis_title="Date",
    yaxis_title="Prix (USDT)",
    xaxis_rangeslider_visible=False,
    height=600
)

st.plotly_chart(fig, use_container_width=True)

# --- Section 2: Data Quality ---
st.header("Data Quality")
try:
  response = requests.get(f"{API_BASE}/health/data-quality", timeout=5)
  response.raise_for_status()
  payload = response.json()
  if payload["status"] != "ok":
      st.error(f"Data quality indisponible : {payload.get('error')}")
      st.stop()
  data = payload["data"]
except requests.exceptions.RequestException as e:
  st.error(f"API inaccessible : {e}")
  st.stop()

col1, col2, col3 = st.columns(3)

col1.metric("Gaps", data["has_gap"])
col2.metric("Outliers", data["is_outlier"])
col3.metric("Inconsistencies", data["is_inconsistency"])