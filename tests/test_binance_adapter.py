"""Tests for Binance historical data adapter (Task 9.2).

All tests use mocked HTTP responses — no real API calls.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.tradememory.data.binance import (
    BASE_URL,
    KLINES_ENDPOINT,
    BinanceDataSource,
    TIMEFRAME_MAP,
)
from src.tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from src.tradememory.data.protocol import (
    DataSource,
    DataSourceError,
    RateLimitError,
    SymbolNotFoundError,
)


# --- Fixtures ---


def make_kline(open_time_ms: int, o=100.0, h=110.0, l=90.0, c=105.0, v=1000.0):
    """Create a single Binance kline array."""
    return [
        open_time_ms,  # 0: open time
        str(o),  # 1: open
        str(h),  # 2: high
        str(l),  # 3: low
        str(c),  # 4: close
        str(v),  # 5: volume
        open_time_ms + 3599999,  # 6: close time
        "10500.0",  # 7: quote asset volume
        50,  # 8: number of trades
        "500.0",  # 9: taker buy base
        "5250.0",  # 10: taker buy quote
        "0",  # 11: ignore
    ]


def make_klines(count: int, start_ms: int = 1704067200000, interval_ms: int = 3600000):
    """Create a list of mock klines."""
    return [
        make_kline(
            start_ms + i * interval_ms,
            o=100 + i,
            h=110 + i,
            l=90 + i,
            c=105 + i,
            v=1000 + i * 10,
        )
        for i in range(count)
    ]


@pytest.fixture
def tmp_cache(tmp_path):
    """Temporary cache directory."""
    return tmp_path / "cache"


@pytest.fixture
def mock_client():
    """Mock httpx.AsyncClient."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def source(tmp_cache, mock_client):
    """BinanceDataSource with mock client and temp cache."""
    return BinanceDataSource(
        cache_dir=tmp_cache,
        requests_per_minute=60000,  # effectively no rate limit in tests
        client=mock_client,
    )


# --- Protocol conformance ---


class TestProtocolConformance:
    def test_isinstance_check(self, source):
        """BinanceDataSource satisfies DataSource Protocol."""
        assert isinstance(source, DataSource)

    def test_name_property(self, source):
        assert source.name == "binance"


# --- Kline parsing ---


class TestKlineParsing:
    def test_parse_single_kline(self, source):
        raw = [make_kline(1704067200000, o=42000, h=42500, l=41800, c=42300, v=150)]
        bars = source._parse_klines(raw)
        assert len(bars) == 1
        bar = bars[0]
        assert bar.open == 42000.0
        assert bar.high == 42500.0
        assert bar.low == 41800.0
        assert bar.close == 42300.0
        assert bar.volume == 150.0
        assert bar.timestamp.tzinfo == timezone.utc
        assert bar.timestamp == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)

    def test_parse_multiple_klines(self, source):
        raw = make_klines(5)
        bars = source._parse_klines(raw)
        assert len(bars) == 5
        # Verify ascending order
        for i in range(1, len(bars)):
            assert bars[i].timestamp > bars[i - 1].timestamp

    def test_parse_empty(self, source):
        assert source._parse_klines([]) == []


# --- fetch_ohlcv ---


class TestFetchOHLCV:
    @pytest.mark.asyncio
    async def test_basic_fetch(self, source, mock_client):
        """Fetch small date range — single API call."""
        klines = make_klines(10)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = klines
        mock_client.get = AsyncMock(return_value=mock_resp)

        result = await source.fetch_ohlcv(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 10, tzinfo=timezone.utc),
        )

        assert isinstance(result, OHLCVSeries)
        assert result.symbol == "BTCUSDT"
        assert result.timeframe == Timeframe.H1
        assert result.source == "binance"
        assert result.count == 10

    @pytest.mark.asyncio
    async def test_fetch_with_limit(self, source, mock_client):
        """Limit parameter truncates results."""
        klines = make_klines(20)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = klines
        mock_client.get = AsyncMock(return_value=mock_resp)

        result = await source.fetch_ohlcv(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 2, tzinfo=timezone.utc),
            limit=5,
        )

        assert result.count == 5

    @pytest.mark.asyncio
    async def test_fetch_empty_response(self, source, mock_client):
        """Empty API response returns empty series."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_client.get = AsyncMock(return_value=mock_resp)

        result = await source.fetch_ohlcv(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
        )

        assert result.count == 0
        assert result.bars == []

    @pytest.mark.asyncio
    async def test_pagination(self, source, mock_client):
        """Large date range triggers multiple API calls."""
        # First call: 1000 bars (triggers pagination)
        first_batch = make_klines(1000, start_ms=1704067200000)
        # Second call: 500 bars (less than 1000 = done)
        second_start = 1704067200000 + 1000 * 3600000
        second_batch = make_klines(500, start_ms=second_start)

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            resp = MagicMock()
            resp.status_code = 200
            if call_count == 0:
                resp.json.return_value = first_batch
            else:
                resp.json.return_value = second_batch
            call_count += 1
            return resp

        mock_client.get = mock_get

        result = await source.fetch_ohlcv(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 3, 15, tzinfo=timezone.utc),
        )

        assert call_count == 2
        assert result.count == 1500


# --- Error handling ---


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_rate_limit_429(self, source, mock_client):
        """429 response raises RateLimitError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "30"}
        mock_client.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(RateLimitError) as exc_info:
            await source.fetch_ohlcv(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 1, 2, tzinfo=timezone.utc),
            )
        assert exc_info.value.retry_after == 30.0

    @pytest.mark.asyncio
    async def test_invalid_symbol_400(self, source, mock_client):
        """400 with 'Invalid symbol' raises SymbolNotFoundError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"msg": "Invalid symbol.", "code": -1121}
        mock_client.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(SymbolNotFoundError) as exc_info:
            await source.fetch_ohlcv(
                symbol="FAKECOIN",
                timeframe=Timeframe.H1,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 1, 2, tzinfo=timezone.utc),
            )
        assert exc_info.value.symbol == "FAKECOIN"

    @pytest.mark.asyncio
    async def test_other_400_error(self, source, mock_client):
        """400 with non-symbol error raises DataSourceError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"msg": "Mandatory parameter missing"}
        mock_client.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(DataSourceError):
            await source.fetch_ohlcv(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 1, 2, tzinfo=timezone.utc),
            )

    @pytest.mark.asyncio
    async def test_500_error(self, source, mock_client):
        """500 response raises DataSourceError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_client.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(DataSourceError):
            await source.fetch_ohlcv(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 1, 2, tzinfo=timezone.utc),
            )

    @pytest.mark.asyncio
    async def test_network_error(self, source, mock_client):
        """Network error raises DataSourceError."""
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        with pytest.raises(DataSourceError):
            await source.fetch_ohlcv(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 1, 2, tzinfo=timezone.utc),
            )


# --- Cache ---


class TestCache:
    @pytest.mark.asyncio
    async def test_cache_hit(self, source, mock_client, tmp_cache):
        """Second fetch uses cached data, no API call."""
        klines = make_klines(10)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = klines
        mock_client.get = AsyncMock(return_value=mock_resp)

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 10, tzinfo=timezone.utc)

        # First fetch — hits API, writes cache
        result1 = await source.fetch_ohlcv("BTCUSDT", Timeframe.H1, start, end)
        assert result1.count == 10
        assert mock_client.get.call_count == 1

        # Reset mock to verify no more calls
        mock_client.get.reset_mock()

        # Second fetch — should use cache
        result2 = await source.fetch_ohlcv("BTCUSDT", Timeframe.H1, start, end)
        assert result2.count == 10
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_different_params(self, source, mock_client, tmp_cache):
        """Different parameters miss cache."""
        klines = make_klines(10)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = klines
        mock_client.get = AsyncMock(return_value=mock_resp)

        start1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end1 = datetime(2024, 1, 1, 10, tzinfo=timezone.utc)
        start2 = datetime(2024, 2, 1, tzinfo=timezone.utc)
        end2 = datetime(2024, 2, 1, 10, tzinfo=timezone.utc)

        await source.fetch_ohlcv("BTCUSDT", Timeframe.H1, start1, end1)
        await source.fetch_ohlcv("BTCUSDT", Timeframe.H1, start2, end2)

        # Both should hit API
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_not_saved_with_limit(self, source, mock_client, tmp_cache):
        """Fetches with limit don't cache (partial data)."""
        klines = make_klines(20)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = klines
        mock_client.get = AsyncMock(return_value=mock_resp)

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 20, tzinfo=timezone.utc)

        await source.fetch_ohlcv("BTCUSDT", Timeframe.H1, start, end, limit=5)

        # Cache dir should have no parquet files
        parquets = list(tmp_cache.glob("*.parquet"))
        assert len(parquets) == 0

    def test_cache_key_format(self, source):
        """Cache key includes symbol, timeframe, date range."""
        path = source._cache_key(
            "BTCUSDT",
            Timeframe.H1,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 6, 30, tzinfo=timezone.utc),
        )
        assert "BTCUSDT" in path.name
        assert "1h" in path.name
        assert "20240101" in path.name
        assert "20240630" in path.name
        assert path.suffix == ".parquet"

    def test_load_nonexistent_cache(self, source):
        """Loading non-existent cache returns None."""
        result = source._load_cache(Path("/nonexistent/file.parquet"))
        assert result is None


# --- available_symbols ---


class TestAvailableSymbols:
    @pytest.mark.asyncio
    async def test_available_symbols(self, source, mock_client):
        """Returns list of trading symbols."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "symbols": [
                {"symbol": "BTCUSDT", "status": "TRADING"},
                {"symbol": "ETHUSDT", "status": "TRADING"},
                {"symbol": "OLDCOIN", "status": "BREAK"},  # not trading
            ]
        }
        mock_client.get = AsyncMock(return_value=mock_resp)

        symbols = await source.available_symbols()
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols
        assert "OLDCOIN" not in symbols

    @pytest.mark.asyncio
    async def test_available_symbols_error(self, source, mock_client):
        """API error raises DataSourceError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(DataSourceError):
            await source.available_symbols()


# --- Timeframe mapping ---


class TestTimeframeMapping:
    def test_all_timeframes_mapped(self):
        """All Timeframe enum values have Binance interval mapping."""
        for tf in Timeframe:
            assert tf in TIMEFRAME_MAP, f"Missing mapping for {tf}"

    def test_mapping_values(self):
        assert TIMEFRAME_MAP[Timeframe.M1] == "1m"
        assert TIMEFRAME_MAP[Timeframe.H1] == "1h"
        assert TIMEFRAME_MAP[Timeframe.D1] == "1d"


# --- Rate limiting ---


class TestRateLimiting:
    def test_default_rate(self):
        """Default rate is 600 req/min (conservative)."""
        src = BinanceDataSource()
        assert src._min_interval == 60.0 / 600

    def test_custom_rate(self):
        src = BinanceDataSource(requests_per_minute=1200)
        assert src._min_interval == 60.0 / 1200


# --- Close ---


class TestClose:
    @pytest.mark.asyncio
    async def test_close_owned_client(self, tmp_cache):
        """Close shuts down client we created."""
        source = BinanceDataSource(cache_dir=tmp_cache)
        # Force client creation
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        source._client = mock_client
        await source.close()
        mock_client.aclose.assert_called_once()
        assert source._client is None

    @pytest.mark.asyncio
    async def test_close_external_client(self, tmp_cache, mock_client):
        """Close does NOT shut down externally-provided client."""
        source = BinanceDataSource(cache_dir=tmp_cache, client=mock_client)
        await source.close()
        mock_client.aclose.assert_not_called()
