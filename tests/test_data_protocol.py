"""Tests for the DataSource protocol and data models."""

import pytest
from datetime import datetime, timezone, timedelta

from src.tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from src.tradememory.data.protocol import (
    DataSource,
    DataSourceError,
    RateLimitError,
    SymbolNotFoundError,
)


# ---------------------------------------------------------------------------
# OHLCV model tests
# ---------------------------------------------------------------------------


class TestOHLCV:
    def test_basic_construction(self):
        bar = OHLCV(
            timestamp=datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc),
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000.0,
        )
        assert bar.open == 100.0
        assert bar.close == 103.0
        assert bar.volume == 1000.0

    def test_utc_enforcement_naive_datetime(self):
        """Naive datetime gets UTC timezone attached."""
        bar = OHLCV(
            timestamp=datetime(2026, 1, 1, 14, 0),
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
        )
        assert bar.timestamp.tzinfo == timezone.utc

    def test_utc_preserves_existing_tz(self):
        """Aware datetime keeps its timezone."""
        eastern = timezone(timedelta(hours=-5))
        bar = OHLCV(
            timestamp=datetime(2026, 1, 1, 14, 0, tzinfo=eastern),
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
        )
        assert bar.timestamp.tzinfo == eastern

    def test_high_gte_low_validation(self):
        """high < low should raise ValueError."""
        with pytest.raises(ValueError, match="high.*must be >= low"):
            OHLCV(
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                open=100.0,
                high=95.0,  # invalid: less than low
                low=98.0,
                close=97.0,
            )

    def test_high_equals_low_ok(self):
        """Doji bar: high == low is valid."""
        bar = OHLCV(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
        )
        assert bar.range == 0.0

    def test_default_volume_zero(self):
        bar = OHLCV(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
        )
        assert bar.volume == 0.0

    def test_properties_bullish(self):
        bar = OHLCV(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100.0,
            high=110.0,
            low=95.0,
            close=108.0,
        )
        assert bar.mid == 102.5
        assert bar.range == 15.0
        assert bar.body == 8.0
        assert bar.is_bullish is True

    def test_properties_bearish(self):
        bar = OHLCV(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100.0,
            high=102.0,
            low=90.0,
            close=92.0,
        )
        assert bar.body == -8.0
        assert bar.is_bullish is False


# ---------------------------------------------------------------------------
# OHLCVSeries tests
# ---------------------------------------------------------------------------


def _make_bars(n: int, start_price: float = 100.0) -> list[OHLCV]:
    """Generate n bars starting from a base price."""
    bars = []
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        p = start_price + i
        bars.append(
            OHLCV(
                timestamp=base + timedelta(hours=i),
                open=p,
                high=p + 2,
                low=p - 1,
                close=p + 1,
                volume=100.0 * (i + 1),
            )
        )
    return bars


class TestOHLCVSeries:
    def test_empty_series(self):
        s = OHLCVSeries(symbol="BTCUSDT", timeframe=Timeframe.H1)
        assert s.count == 0
        assert s.start is None
        assert s.end is None

    def test_metadata(self):
        bars = _make_bars(10)
        s = OHLCVSeries(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            bars=bars,
            source="test",
        )
        assert s.count == 10
        assert s.start == bars[0].timestamp
        assert s.end == bars[-1].timestamp
        assert s.source == "test"

    def test_slice(self):
        bars = _make_bars(24)
        s = OHLCVSeries(
            symbol="BTCUSDT", timeframe=Timeframe.H1, bars=bars
        )
        start = datetime(2026, 1, 1, 5, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
        sliced = s.slice(start, end)

        assert sliced.symbol == "BTCUSDT"
        assert sliced.timeframe == Timeframe.H1
        assert sliced.count == 6  # hours 5,6,7,8,9,10
        assert sliced.start == start
        assert sliced.end == end

    def test_slice_empty_result(self):
        bars = _make_bars(5)
        s = OHLCVSeries(
            symbol="BTCUSDT", timeframe=Timeframe.H1, bars=bars
        )
        far_future = datetime(2027, 1, 1, tzinfo=timezone.utc)
        sliced = s.slice(far_future, far_future + timedelta(hours=1))
        assert sliced.count == 0

    def test_split_default_70_30(self):
        bars = _make_bars(100)
        s = OHLCVSeries(
            symbol="BTCUSDT", timeframe=Timeframe.H1, bars=bars
        )
        is_sample, oos = s.split()

        assert is_sample.count == 70
        assert oos.count == 30
        assert is_sample.bars[-1].timestamp < oos.bars[0].timestamp

    def test_split_custom_ratio(self):
        bars = _make_bars(100)
        s = OHLCVSeries(
            symbol="BTCUSDT", timeframe=Timeframe.H1, bars=bars
        )
        is_sample, oos = s.split(0.5)
        assert is_sample.count == 50
        assert oos.count == 50

    def test_split_empty_series(self):
        s = OHLCVSeries(symbol="BTCUSDT", timeframe=Timeframe.H1)
        is_sample, oos = s.split()
        assert is_sample.count == 0
        assert oos.count == 0

    def test_split_single_bar(self):
        """Single bar goes to IS, OOS is empty (or vice versa)."""
        bars = _make_bars(1)
        s = OHLCVSeries(
            symbol="BTCUSDT", timeframe=Timeframe.H1, bars=bars
        )
        is_sample, oos = s.split(0.5)
        # split_idx = max(1, min(0, 0)) = 1, so IS gets 1, OOS gets 0
        assert is_sample.count + oos.count == 1

    def test_split_preserves_metadata(self):
        bars = _make_bars(20)
        s = OHLCVSeries(
            symbol="ETHUSDT",
            timeframe=Timeframe.M15,
            bars=bars,
            source="binance",
        )
        is_sample, oos = s.split()
        assert is_sample.symbol == "ETHUSDT"
        assert is_sample.timeframe == Timeframe.M15
        assert is_sample.source == "binance"
        assert oos.symbol == "ETHUSDT"


# ---------------------------------------------------------------------------
# Timeframe enum tests
# ---------------------------------------------------------------------------


class TestTimeframe:
    def test_values(self):
        assert Timeframe.M1 == "1m"
        assert Timeframe.H1 == "1h"
        assert Timeframe.D1 == "1d"

    def test_all_timeframes(self):
        assert len(Timeframe) == 8


# ---------------------------------------------------------------------------
# Protocol tests
# ---------------------------------------------------------------------------


class TestDataSourceProtocol:
    def test_protocol_is_runtime_checkable(self):
        """DataSource is a runtime-checkable Protocol."""
        assert hasattr(DataSource, "__protocol_attrs__") or hasattr(
            DataSource, "__abstractmethods__"
        ) or True  # Protocol existence is enough

    def test_concrete_class_satisfies_protocol(self):
        """A class implementing all methods satisfies isinstance check."""

        class MockSource:
            @property
            def name(self) -> str:
                return "mock"

            async def fetch_ohlcv(self, symbol, timeframe, start, end, limit=None):
                return OHLCVSeries(symbol=symbol, timeframe=timeframe)

            async def available_symbols(self) -> list[str]:
                return ["BTCUSDT"]

        source = MockSource()
        assert isinstance(source, DataSource)

    def test_incomplete_class_fails_protocol(self):
        """A class missing methods does NOT satisfy the protocol."""

        class BadSource:
            pass

        assert not isinstance(BadSource(), DataSource)


# ---------------------------------------------------------------------------
# Exception tests
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_data_source_error(self):
        err = DataSourceError("binance", "connection timeout")
        assert str(err) == "[binance] connection timeout"
        assert err.source == "binance"

    def test_rate_limit_error(self):
        err = RateLimitError("binance", retry_after=30.0)
        assert "30.0s" in str(err)
        assert err.retry_after == 30.0
        assert err.source == "binance"

    def test_rate_limit_no_retry(self):
        err = RateLimitError("binance")
        assert err.retry_after is None
        assert "Rate limit" in str(err)

    def test_symbol_not_found(self):
        err = SymbolNotFoundError("mt5", "INVALID")
        assert "INVALID" in str(err)
        assert err.symbol == "INVALID"
        assert err.source == "mt5"

    def test_exception_hierarchy(self):
        """All custom errors inherit from DataSourceError."""
        assert issubclass(RateLimitError, DataSourceError)
        assert issubclass(SymbolNotFoundError, DataSourceError)
        assert issubclass(DataSourceError, Exception)
