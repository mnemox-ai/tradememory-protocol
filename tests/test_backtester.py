"""Tests for vectorized backtester (Task 10.2).

Uses synthetic data with known outcomes — no randomness.
"""

import math
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from tradememory.data.context_builder import (
    ContextConfig,
    MarketContext,
    Regime,
    Session,
    VolatilityRegime,
)
from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.backtester import (
    Trade,
    _compute_fitness,
    _compute_max_drawdown,
    _max_consecutive_losses,
    backtest,
    check_entry,
    evaluate_condition,
)
from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    ExitCondition,
    FitnessMetrics,
    RuleCondition,
    ValidityConditions,
)


# --- Helpers ---


def make_bars(
    count: int = 100,
    start: datetime = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
    base: float = 42000.0,
    trend: float = 0.0,
    volatility: float = 100.0,
) -> List[OHLCV]:
    bars = []
    price = base
    for i in range(count):
        ts = start + timedelta(hours=i)
        o = price
        c = price + trend
        h = max(o, c) + volatility
        l = min(o, c) - volatility
        bars.append(OHLCV(timestamp=ts, open=o, high=h, low=l, close=c, volume=1000))
        price = c
    return bars


def make_series(bars: List[OHLCV] = None, count: int = 100, **kwargs) -> OHLCVSeries:
    if bars is None:
        bars = make_bars(count, **kwargs)
    return OHLCVSeries(symbol="BTCUSDT", timeframe=Timeframe.H1, bars=bars, source="test")


def make_pattern(
    direction: str = "long",
    conditions: List[RuleCondition] = None,
    sl_atr: float = 1.0,
    tp_atr: float = 2.0,
    max_bars: int = 10,
    validity: ValidityConditions = None,
) -> CandidatePattern:
    if conditions is None:
        # Default: always enter (any hour)
        conditions = [
            RuleCondition(field="hour_utc", op=ConditionOperator.GTE, value=0),
        ]
    return CandidatePattern(
        name="Test Pattern",
        description="For testing",
        entry_condition=EntryCondition(
            direction=direction,
            conditions=conditions,
        ),
        exit_condition=ExitCondition(
            stop_loss_atr=sl_atr,
            take_profit_atr=tp_atr,
            max_holding_bars=max_bars,
        ),
        validity_conditions=validity or ValidityConditions(),
    )


# --- Condition Evaluation ---


class TestEvaluateCondition:
    def test_gt(self):
        ctx = MarketContext(hour_utc=14)
        assert evaluate_condition(
            RuleCondition(field="hour_utc", op=ConditionOperator.GT, value=10), ctx
        ) is True
        assert evaluate_condition(
            RuleCondition(field="hour_utc", op=ConditionOperator.GT, value=14), ctx
        ) is False

    def test_eq(self):
        ctx = MarketContext(hour_utc=16)
        assert evaluate_condition(
            RuleCondition(field="hour_utc", op=ConditionOperator.EQ, value=16), ctx
        ) is True
        assert evaluate_condition(
            RuleCondition(field="hour_utc", op=ConditionOperator.EQ, value=14), ctx
        ) is False

    def test_between(self):
        ctx = MarketContext(atr_percentile=50.0)
        assert evaluate_condition(
            RuleCondition(field="atr_percentile", op=ConditionOperator.BETWEEN, value=[25, 75]), ctx
        ) is True
        assert evaluate_condition(
            RuleCondition(field="atr_percentile", op=ConditionOperator.BETWEEN, value=[60, 90]), ctx
        ) is False

    def test_in(self):
        ctx = MarketContext(session=Session.OVERLAP)
        assert evaluate_condition(
            RuleCondition(field="session", op=ConditionOperator.IN, value=["overlap", "newyork"]), ctx
        ) is True

    def test_neq(self):
        ctx = MarketContext(volatility_regime=VolatilityRegime.EXTREME)
        assert evaluate_condition(
            RuleCondition(field="volatility_regime", op=ConditionOperator.NEQ, value="extreme"), ctx
        ) is False

    def test_none_field(self):
        ctx = MarketContext()
        assert evaluate_condition(
            RuleCondition(field="trend_12h_pct", op=ConditionOperator.GT, value=0), ctx
        ) is False

    def test_enum_to_string(self):
        """Enum values should be compared as strings."""
        ctx = MarketContext(regime=Regime.TRENDING_UP)
        assert evaluate_condition(
            RuleCondition(field="regime", op=ConditionOperator.EQ, value="trending_up"), ctx
        ) is True


# --- Check Entry ---


class TestCheckEntry:
    def test_all_conditions_met(self):
        ctx = MarketContext(hour_utc=14, trend_12h_pct=1.5)
        pattern = make_pattern(conditions=[
            RuleCondition(field="hour_utc", op=ConditionOperator.EQ, value=14),
            RuleCondition(field="trend_12h_pct", op=ConditionOperator.GT, value=0.5),
        ])
        assert check_entry(pattern, ctx) is True

    def test_one_condition_failed(self):
        ctx = MarketContext(hour_utc=14, trend_12h_pct=-0.5)
        pattern = make_pattern(conditions=[
            RuleCondition(field="hour_utc", op=ConditionOperator.EQ, value=14),
            RuleCondition(field="trend_12h_pct", op=ConditionOperator.GT, value=0.5),
        ])
        assert check_entry(pattern, ctx) is False

    def test_no_conditions(self):
        """Empty conditions = never enter (safety)."""
        ctx = MarketContext(hour_utc=14)
        pattern = make_pattern(conditions=[])
        assert check_entry(pattern, ctx) is False

    def test_validity_regime_filter(self):
        ctx = MarketContext(hour_utc=14, regime=Regime.RANGING)
        pattern = make_pattern(
            conditions=[RuleCondition(field="hour_utc", op=ConditionOperator.GTE, value=0)],
            validity=ValidityConditions(regime="trending_up"),
        )
        assert check_entry(pattern, ctx) is False


# --- Backtest ---


class TestBacktest:
    def test_basic_long_uptrend(self):
        """Long in uptrend should produce positive PnL."""
        series = make_series(count=100, trend=10.0, volatility=50.0)
        pattern = make_pattern(direction="long", sl_atr=1.5, tp_atr=3.0, max_bars=10)
        fitness = backtest(series, pattern)
        assert fitness.trade_count > 0
        assert fitness.total_pnl > 0  # should profit in uptrend

    def test_basic_short_downtrend(self):
        """Short in downtrend should produce positive PnL."""
        series = make_series(count=100, trend=-10.0, volatility=50.0, base=50000.0)
        pattern = make_pattern(direction="short", sl_atr=1.5, tp_atr=3.0, max_bars=10)
        fitness = backtest(series, pattern)
        assert fitness.trade_count > 0
        assert fitness.total_pnl > 0

    def test_long_in_downtrend_loses(self):
        """Long in downtrend should lose."""
        series = make_series(count=100, trend=-15.0, volatility=50.0, base=50000.0)
        pattern = make_pattern(direction="long", sl_atr=1.0, tp_atr=3.0, max_bars=20)
        fitness = backtest(series, pattern)
        assert fitness.trade_count > 0
        assert fitness.total_pnl < 0

    def test_empty_series(self):
        series = make_series(count=0)
        pattern = make_pattern()
        fitness = backtest(series, pattern)
        assert fitness.trade_count == 0

    def test_too_few_bars(self):
        series = make_series(count=10)
        pattern = make_pattern()
        fitness = backtest(series, pattern)
        assert fitness.trade_count == 0  # not enough for ATR computation

    def test_time_based_exit(self):
        """max_holding_bars forces exit."""
        series = make_series(count=100, trend=0.0, volatility=1.0)  # tiny volatility
        pattern = make_pattern(
            sl_atr=100.0,  # far SL
            tp_atr=100.0,  # far TP
            max_bars=3,
        )
        fitness = backtest(series, pattern)
        # All trades should exit by time
        assert fitness.trade_count > 0
        assert fitness.avg_holding_bars <= 3

    def test_no_entry_conditions_no_trades(self):
        """Pattern with empty conditions never enters."""
        series = make_series(count=100)
        pattern = make_pattern(conditions=[])
        fitness = backtest(series, pattern)
        assert fitness.trade_count == 0

    def test_specific_hour_filter(self):
        """Only enter at specific UTC hour."""
        # Create bars that cycle through 24 hours
        series = make_series(count=100, trend=5.0, volatility=50.0)
        pattern = make_pattern(
            conditions=[
                RuleCondition(field="hour_utc", op=ConditionOperator.EQ, value=14),
            ],
            max_bars=5,
        )
        fitness = backtest(series, pattern)
        # Should have fewer trades than the "always enter" version
        all_entry = backtest(series, make_pattern(max_bars=5))
        assert fitness.trade_count < all_entry.trade_count


# --- Fitness computation ---


class TestComputeFitness:
    def test_all_wins(self):
        trades = [
            Trade(entry_bar=0, exit_bar=5, direction="long", entry_price=100, exit_price=110, pnl=10, holding_bars=5),
            Trade(entry_bar=10, exit_bar=15, direction="long", entry_price=110, exit_price=120, pnl=10, holding_bars=5),
        ]
        f = _compute_fitness(trades)
        assert f.win_rate == 1.0
        assert f.total_pnl == 20.0
        assert f.trade_count == 2
        assert f.profit_factor == 999.0  # capped inf

    def test_mixed_results(self):
        trades = [
            Trade(entry_bar=0, exit_bar=5, direction="long", entry_price=100, exit_price=110, pnl=10, holding_bars=5),
            Trade(entry_bar=10, exit_bar=15, direction="long", entry_price=110, exit_price=105, pnl=-5, holding_bars=5),
            Trade(entry_bar=20, exit_bar=25, direction="long", entry_price=105, exit_price=115, pnl=10, holding_bars=5),
        ]
        f = _compute_fitness(trades)
        assert f.trade_count == 3
        assert f.win_rate == pytest.approx(2 / 3, abs=0.01)
        assert f.total_pnl == 15.0
        assert f.profit_factor == pytest.approx(20.0 / 5.0, abs=0.01)

    def test_empty_trades(self):
        f = _compute_fitness([])
        assert f.trade_count == 0
        assert f.sharpe_ratio == 0

    def test_single_trade(self):
        trades = [Trade(entry_bar=0, exit_bar=5, direction="long", entry_price=100, exit_price=110, pnl=10, holding_bars=5)]
        f = _compute_fitness(trades)
        assert f.trade_count == 1
        assert f.total_pnl == 10.0

    def test_avg_holding(self):
        trades = [
            Trade(entry_bar=0, exit_bar=3, direction="long", entry_price=100, exit_price=110, pnl=10, holding_bars=3),
            Trade(entry_bar=10, exit_bar=17, direction="long", entry_price=100, exit_price=110, pnl=10, holding_bars=7),
        ]
        f = _compute_fitness(trades)
        assert f.avg_holding_bars == 5.0


class TestMaxDrawdown:
    def test_no_drawdown(self):
        assert _compute_max_drawdown([10, 10, 10]) == 0

    def test_simple_drawdown(self):
        # Peak at 20, drops to 10 = 50% DD
        dd = _compute_max_drawdown([10, 10, -10])
        assert dd == pytest.approx(50.0, abs=1.0)

    def test_empty(self):
        assert _compute_max_drawdown([]) == 0

    def test_all_losses(self):
        dd = _compute_max_drawdown([-10, -10, -10])
        assert dd == 0  # never had a peak > 0


class TestMaxConsecutiveLosses:
    def test_basic(self):
        assert _max_consecutive_losses([10, -5, -5, -5, 10]) == 3

    def test_no_losses(self):
        assert _max_consecutive_losses([10, 10, 10]) == 0

    def test_all_losses(self):
        assert _max_consecutive_losses([-5, -5, -5]) == 3

    def test_empty(self):
        assert _max_consecutive_losses([]) == 0
