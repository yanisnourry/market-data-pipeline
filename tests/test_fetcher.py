import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from ingestion.fetcher import (
    BINANCE_MAX_CANDLES,
    INTERVAL_MS,
    _fetch_chunk,
    compute_start_ms,
    fetch_candles,
)


class FakeResponse:
    """Test double for a `session.get(...)` used as `async with`."""

    def __init__(self, payload=None, status_error=None, connect_error=None):
        self._payload = payload
        self._status_error = status_error
        self._connect_error = connect_error

    async def __aenter__(self):
        if self._connect_error is not None:
            raise self._connect_error
        return self

    async def __aexit__(self, *exc_info):
        return False

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    async def json(self):
        return self._payload


class FakeSession:
    """Returns the given FakeResponse instances in order, one `.get()` call = one response."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.call_count = 0

    def get(self, url, params=None):
        response = self._responses[self.call_count]
        self.call_count += 1
        return response


def too_many_requests():
    request_info = SimpleNamespace(real_url="https://api.binance.com/api/v3/klines")
    return aiohttp.ClientResponseError(request_info, (), status=429, message="Too Many Requests")


def timeout():
    return aiohttp.ServerTimeoutError("simulated timeout")


async def _run_fetch(responses):
    session = FakeSession(responses)
    sem = asyncio.Semaphore(1)
    with patch("ingestion.fetcher.asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
        result = await _fetch_chunk(session, "BTCUSDT", "1h", 0, 1000, sem)
    return result, sleep_mock, session


async def test_fetch_chunk_succeeds_first_try_no_retry():
    payload = [[1, 2, 3, 4, 5, 6]]
    result, sleep_mock, session = await _run_fetch([FakeResponse(payload=payload)])

    assert result == payload
    assert session.call_count == 1
    sleep_mock.assert_not_called()


async def test_fetch_chunk_retries_on_429_then_succeeds():
    payload = [[1, 2, 3, 4, 5, 6]]
    responses = [
        FakeResponse(status_error=too_many_requests()),
        FakeResponse(payload=payload),
    ]
    result, sleep_mock, session = await _run_fetch(responses)

    assert result == payload
    assert session.call_count == 2
    sleep_mock.assert_awaited_once_with(1)  # 2**0


async def test_fetch_chunk_retries_on_timeout_then_succeeds():
    payload = [[1, 2, 3, 4, 5, 6]]
    responses = [
        FakeResponse(connect_error=timeout()),
        FakeResponse(payload=payload),
    ]
    result, sleep_mock, session = await _run_fetch(responses)

    assert result == payload
    assert session.call_count == 2
    sleep_mock.assert_awaited_once_with(1)


async def test_fetch_chunk_backoff_is_exponential():
    payload = [[1, 2, 3, 4, 5, 6]]
    responses = [
        FakeResponse(status_error=too_many_requests()),
        FakeResponse(connect_error=timeout()),
        FakeResponse(payload=payload),
    ]
    result, sleep_mock, session = await _run_fetch(responses)

    assert result == payload
    assert session.call_count == 3
    assert sleep_mock.await_args_list == [((1,),), ((2,),)]  # 2**0, 2**1


async def test_fetch_chunk_raises_after_three_failed_attempts():
    responses = [
        FakeResponse(status_error=too_many_requests()),
        FakeResponse(connect_error=timeout()),
        FakeResponse(status_error=too_many_requests()),
    ]
    session = FakeSession(responses)
    sem = asyncio.Semaphore(1)

    with patch("ingestion.fetcher.asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
        with pytest.raises(aiohttp.ClientResponseError):
            await _fetch_chunk(session, "BTCUSDT", "1h", 0, 1000, sem)

    assert session.call_count == 3
    # no sleep after the 3rd failure, the exception propagates immediately
    assert sleep_mock.await_count == 2


# --- pagination -------------------------------------------------------------

CHUNK_MS_1H = BINANCE_MAX_CANDLES * INTERVAL_MS["1h"]  # size of one page, in ms
TWO_YEARS_MS = 2 * 365 * 24 * INTERVAL_MS["1h"]


def test_compute_start_ms_range_smaller_than_one_chunk_returns_single_start():
    starts = compute_start_ms("1h", 0, CHUNK_MS_1H - 1)
    assert starts == [0]


def test_compute_start_ms_empty_range_returns_nothing():
    starts = compute_start_ms("1h", 1000, 1000)
    assert starts == []


def test_compute_start_ms_two_years_1h_is_contiguous_and_covers_range():
    start_ms = 0
    end_ms = TWO_YEARS_MS
    starts = compute_start_ms("1h", start_ms, end_ms)

    assert starts[0] == start_ms
    # contiguous pages: each page starts exactly where the previous one's coverage ends
    for s1, s2 in zip(starts, starts[1:]):
        assert s2 - s1 == CHUNK_MS_1H
    # the last page starts before the end, and covers it entirely
    assert starts[-1] < end_ms <= starts[-1] + CHUNK_MS_1H
    assert len(starts) == len(set(starts))  # no duplicate


async def test_fetch_candles_two_year_range_has_no_gap_or_overlap():
    start_ms = 0
    end_ms = TWO_YEARS_MS

    with patch("ingestion.fetcher._fetch_chunk", new_callable=AsyncMock) as fetch_chunk_mock:
        fetch_chunk_mock.return_value = []
        await fetch_candles(None, "BTCUSDT", "1h", start_ms, end_ms)

    windows = [
        (call.kwargs["start_ms"], call.kwargs["end_ms"])
        for call in fetch_chunk_mock.call_args_list
    ]

    assert windows[0][0] == start_ms
    assert windows[-1][1] == end_ms
    for (_, e1), (s2, _) in zip(windows, windows[1:]):
        assert e1 == s2  # the next page starts exactly where the previous one ends
