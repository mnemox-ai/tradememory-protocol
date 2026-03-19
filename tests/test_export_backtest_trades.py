"""Tests for scripts/research/export_backtest_trades.py."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

# Import functions under test
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "research"))

from tradememory.data.models import OHLCV, OHLCVSeries
from tradememory.evolution.backtester import Trade
from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    ExitCondition,
    FitnessMetrics,
    RuleCondition,
)

from export_backtest_trades import (
    fast_backtest_with_trades,
    precompute_atrs,
    precompute_contexts,
    trade_to_dict,
)
from strategy_definitions import build_strategy_e


def _make_bar(ts_hour: int, o: float, h: float, l: float, c: float, vol: float = 100.0) -> OHLCV:
    """Helper to create an OHLCV bar at a specific UTC hour on 2025-01-01."""
    return OHLCV(
        timestamp=datetime(2025, 1, 1, ts_hour, 0, 0, tzinfo=timezone.utc),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=vol,
    )


def _make_series(n: int = 30) -> OHLCVSeries:
    """Create a simple series with n bars for testing."""
    bars = []
    base = 50000.0
    for i in range(n):
        # Slight uptrend
        price = base + i * 10
        bars.append(
            OHLCV(
                timestamp=datetime(2025, 1, 1 + i // 24, i % 24, 0, 0, tzinfo=timezone.utc),
                open=price,
                high=price + 50,
                low=price - 50,
                close=price + 5,
                volume=100.0,
            )
        )
    return OHLCVSeries(symbol="BTCUSDT", timeframe="1h", bars=bars)


class TestBuildStrategyE:
    def test_returns_candidate_pattern(self):
        s = build_strategy_e()
        assert isinstance(s, CandidatePattern)
        assert s.pattern_id == "STRAT-E"
        assert s.entry_condition.direction == "long"
        assert len(s.entry_condition.conditions) == 2
        assert s.exit_condition.stop_loss_atr == 1.0
        assert s.exit_condition.take_profit_atr == 2.0
        assert s.exit_condition.max_holding_bars == 6


class TestPrecomputeAtrs:
    def test_first_entries_are_none(self):
        series = _make_series(30)
        atrs = precompute_atrs(series.bars, atr_period=14)
        assert len(atrs) == 30
        for i in range(15):
            assert atrs[i] is None

    def test_later_entries_have_values(self):
        series = _make_series(30)
        atrs = precompute_atrs(series.bars, atr_period=14)
        for i in range(16, 30):
            assert atrs[i] is not None
            assert atrs[i] > 0


class TestFastBacktestWithTrades:
    def test_empty_bars(self):
        fitness, trades = fast_backtest_with_trades([], [], [], build_strategy_e())
        assert isinstance(fitness, FitnessMetrics)
        assert fitness.trade_count == 0
        assert trades == []

    def test_short_bars(self):
        series = _make_series(5)
        fitness, trades = fast_backtest_with_trades(
            series.bars, [None] * 5, [None] * 5, build_strategy_e()
        )
        assert fitness.trade_count == 0
        assert trades == []

    def test_returns_tuple(self):
        series = _make_series(30)
        contexts = [None] * 30
        atrs = [None] * 30
        result = fast_backtest_with_trades(
            series.bars, contexts, atrs, build_strategy_e()
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        fitness, trades = result
        assert isinstance(fitness, FitnessMetrics)
        assert isinstance(trades, list)


class TestTradeToDict:
    def test_output_fields(self):
        bars = [
            OHLCV(
                timestamp=datetime(2025, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
                open=50000.0, high=50100.0, low=49900.0, close=50050.0, volume=100.0,
            ),
            OHLCV(
                timestamp=datetime(2025, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
                open=50050.0, high=50200.0, low=50000.0, close=50150.0, volume=100.0,
            ),
        ]

        # Mock context with trend_12h_pct
        ctx = MagicMock()
        ctx.trend_12h_pct = 0.5
        contexts = [ctx, None]
        atrs = [500.0, 500.0]

        trade = Trade(
            entry_bar=0,
            exit_bar=1,
            direction="long",
            entry_price=50000.0,
            exit_price=50150.0,
            pnl=150.0,
            exit_reason="tp",
            holding_bars=1,
        )

        d = trade_to_dict(trade, bars, contexts, atrs, strategy_id="STRAT-E", symbol="BTCUSDT")

        assert d["strategy_id"] == "STRAT-E"
        assert d["symbol"] == "BTCUSDT"
        assert d["direction"] == "long"
        assert d["entry_price"] == 50000.0
        assert d["exit_price"] == 50150.0
        assert d["entry_time"] == "2025-01-01T14:00:00+00:00"
        assert d["exit_time"] == "2025-01-01T15:00:00+00:00"
        assert d["exit_reason"] == "tp"
        assert d["holding_bars"] == 1
        assert d["atr_at_entry"] == 500.0
        assert d["trend_12h_pct"] == 0.5
        assert d["trade_type"] == "backtest"
        # pnl_pct = 150 / 50000 * 100 = 0.3
        assert d["pnl_pct"] == 0.3
        # pnl_r = 150 / 500 = 0.3
        assert d["pnl_r"] == 0.3

    def test_none_context(self):
        bars = [
            OHLCV(
                timestamp=datetime(2025, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
                open=50000.0, high=50100.0, low=49900.0, close=50050.0, volume=100.0,
            ),
            OHLCV(
                timestamp=datetime(2025, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
                open=50050.0, high=50200.0, low=50000.0, close=50150.0, volume=100.0,
            ),
        ]
        contexts = [None, None]
        atrs = [None, None]

        trade = Trade(
            entry_bar=0, exit_bar=1, direction="long",
            entry_price=50000.0, exit_price=50150.0, pnl=150.0,
            exit_reason="tp", holding_bars=1,
        )

        d = trade_to_dict(trade, bars, contexts, atrs)
        assert d["atr_at_entry"] is None
        assert d["trend_12h_pct"] is None
        assert d["pnl_r"] is None
