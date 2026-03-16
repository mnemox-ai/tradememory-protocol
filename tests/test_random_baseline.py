"""Comprehensive tests for random baseline validation module."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.models import RuleCondition
from tradememory.evolution.random_baseline import (
    BaselineResult,
    RandomStrategyGenerator,
    compute_percentile_rank,
    rank_strategies,
    run_baseline,
)


# --- Helper ---


def make_random_walk_series(
    n_bars: int = 500,
    start_price: float = 30000.0,
    step: float = 100.0,
    start_dt: datetime = datetime(2024, 1, 1, tzinfo=timezone.utc),
    seed: int = 99,
) -> OHLCVSeries:
    """Generate a random-walk OHLCV series for testing."""
    rng = random.Random(seed)
    bars: list[OHLCV] = []
    price = start_price
    for i in range(n_bars):
        ts = start_dt + timedelta(hours=i)
        change = rng.uniform(-step, step)
        open_ = price
        close = price + change
        high = max(open_, close) + rng.uniform(0, step * 0.5)
        low = min(open_, close) - rng.uniform(0, step * 0.5)
        volume = rng.uniform(100, 1000)
        bars.append(
            OHLCV(
                timestamp=ts,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
        price = close
    return OHLCVSeries(
        symbol="BTCUSDT",
        timeframe=Timeframe.H1,
        bars=bars,
        source="test",
    )


# --- Generator Tests ---


class TestRandomStrategyGenerator:
    def test_generator_count(self):
        """generate(100) returns exactly 100 patterns."""
        gen = RandomStrategyGenerator(seed=42)
        patterns = gen.generate(100)
        assert len(patterns) == 100

    def test_generator_has_hour_condition(self):
        """Each pattern has exactly 1 RuleCondition with field='hour_utc'."""
        gen = RandomStrategyGenerator(seed=42)
        patterns = gen.generate(50)
        for p in patterns:
            conditions = p.entry_condition.conditions
            assert len(conditions) == 1
            assert isinstance(conditions[0], RuleCondition)
            assert conditions[0].field == "hour_utc"

    def test_generator_mixed_directions(self):
        """100 patterns have both 'long' and 'short' directions."""
        gen = RandomStrategyGenerator(seed=42)
        patterns = gen.generate(100)
        directions = {p.entry_condition.direction for p in patterns}
        assert "long" in directions
        assert "short" in directions

    def test_generator_seed_reproducibility(self):
        """Same seed produces identical patterns."""
        gen1 = RandomStrategyGenerator(seed=123)
        gen2 = RandomStrategyGenerator(seed=123)
        p1 = gen1.generate(50)
        p2 = gen2.generate(50)
        for a, b in zip(p1, p2):
            assert a.pattern_id == b.pattern_id
            assert a.entry_condition.direction == b.entry_condition.direction
            assert (
                a.entry_condition.conditions[0].value
                == b.entry_condition.conditions[0].value
            )

    def test_generator_fixed_exits(self):
        """All patterns have SL=1.0, TP=2.0, max_hold=6."""
        gen = RandomStrategyGenerator(seed=42)
        patterns = gen.generate(100)
        for p in patterns:
            assert p.exit_condition.stop_loss_atr == 1.0
            assert p.exit_condition.take_profit_atr == 2.0
            assert p.exit_condition.max_holding_bars == 6


# --- run_baseline Tests ---


class TestRunBaseline:
    def test_run_baseline_with_synthetic_data(self):
        """Run baseline with 500-bar synthetic data, verify structure."""
        series = make_random_walk_series(n_bars=500)
        result = run_baseline(series, n_strategies=50, seed=42)

        assert result.n_strategies == 50
        assert len(result.sharpe_distribution) == 50
        # Distribution must be sorted ascending
        for i in range(len(result.sharpe_distribution) - 1):
            assert result.sharpe_distribution[i] <= result.sharpe_distribution[i + 1]

    def test_run_baseline_empty_series(self):
        """Series with <30 bars returns n_strategies=0."""
        series = make_random_walk_series(n_bars=20)
        result = run_baseline(series, n_strategies=50, seed=42)

        assert result.n_strategies == 0
        assert len(result.sharpe_distribution) == 0
        assert result.mean_sharpe == 0.0
        assert result.std_sharpe == 0.0
        assert result.percentile_95 == 0.0


# --- compute_percentile_rank Tests ---


class TestComputePercentileRank:
    def test_percentile_rank_median(self):
        """distribution=[1,2,3,4,5], sharpe=3 -> ~50-60."""
        pct = compute_percentile_rank(3, [1, 2, 3, 4, 5])
        assert 40.0 <= pct <= 60.0

    def test_percentile_rank_above_max(self):
        """distribution=[1,2,3], sharpe=10 -> 100.0."""
        pct = compute_percentile_rank(10, [1, 2, 3])
        assert pct == 100.0

    def test_percentile_rank_below_min(self):
        """distribution=[1,2,3], sharpe=0 -> 0.0."""
        pct = compute_percentile_rank(0, [1, 2, 3])
        assert pct == 0.0


# --- rank_strategies Tests ---


class TestRankStrategies:
    def test_rank_strategies_structure(self):
        """Verify output structure and passes_5pct logic."""
        baseline = BaselineResult(
            n_strategies=100,
            sharpe_distribution=list(range(100)),  # 0..99
            mean_sharpe=49.5,
            std_sharpe=29.0,
            percentile_95=95.0,
        )

        strategies = {
            "GoodStrategy": 98.0,  # should pass 5%
            "BadStrategy": 10.0,   # should not pass 5%
        }

        ranked = rank_strategies(strategies, baseline)

        # Structure check
        assert "GoodStrategy" in ranked
        assert "BadStrategy" in ranked
        for name, info in ranked.items():
            assert "sharpe" in info
            assert "percentile" in info
            assert "passes_5pct" in info

        # GoodStrategy: sharpe=98 in [0..99] -> percentile >= 95
        assert ranked["GoodStrategy"]["passes_5pct"] is True
        # BadStrategy: sharpe=10 in [0..99] -> percentile ~10
        assert ranked["BadStrategy"]["passes_5pct"] is False
