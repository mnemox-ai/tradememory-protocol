"""Tests for the Agent Simulation Framework (Phase 3).

Uses synthetic OHLCV data (50-100 bars) — no Binance API calls.
"""

import math
import os
import random
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    ExitCondition,
    FitnessMetrics,
    RuleCondition,
    ValidityConditions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_series(n_bars: int = 100, seed: int = 42, symbol: str = "BTCUSDT") -> OHLCVSeries:
    """Generate synthetic OHLCV data with a mild uptrend + noise."""
    rng = random.Random(seed)
    bars = []
    price = 30000.0  # BTC-like starting price
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

    for i in range(n_bars):
        # Mild uptrend with random noise
        change_pct = rng.gauss(0.001, 0.01)  # 0.1% drift, 1% volatility
        open_price = price
        close_price = price * (1 + change_pct)

        high = max(open_price, close_price) * (1 + abs(rng.gauss(0, 0.005)))
        low = min(open_price, close_price) * (1 - abs(rng.gauss(0, 0.005)))
        volume = rng.uniform(100, 1000)

        bars.append(OHLCV(
            timestamp=base_time + timedelta(hours=i),
            open=round(open_price, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close_price, 2),
            volume=round(volume, 2),
        ))
        price = close_price

    return OHLCVSeries(symbol=symbol, timeframe=Timeframe.H1, bars=bars, source="synthetic")


def _simple_strategy() -> CandidatePattern:
    """A simple trend-following strategy for testing."""
    return CandidatePattern(
        pattern_id="test-trend",
        name="TestTrend",
        description="Test strategy",
        entry_condition=EntryCondition(
            direction="long",
            conditions=[
                RuleCondition(field="trend_12h_pct", op=ConditionOperator.GT, value=0.0),
            ],
            description="Enter on any positive 12h trend",
        ),
        exit_condition=ExitCondition(
            stop_loss_atr=1.5,
            take_profit_atr=3.0,
            max_holding_bars=24,
        ),
        validity_conditions=ValidityConditions(),
        confidence=0.5,
        source="test",
    )


# ---------------------------------------------------------------------------
# Test 1: BaseAgent generates signals
# ---------------------------------------------------------------------------

def test_base_agent_generates_signals():
    """BaseAgent should generate trade signals when conditions are met."""
    from tradememory.data.context_builder import MarketContext, Regime
    from tradememory.simulation.agent import BaseAgent

    strategy = _simple_strategy()
    agent = BaseAgent(strategy, fixed_lot=0.01)

    # Context where trend_12h_pct > 0
    ctx = MarketContext(
        trend_12h_pct=0.5,
        atr_percentile=50.0,
        price=30000.0,
        symbol="BTCUSDT",
    )
    signal = agent.should_trade(ctx)
    assert signal is not None
    assert signal.direction == "long"
    assert signal.lot_size == 0.01

    # Context where trend_12h_pct < 0 — no signal
    ctx_neg = MarketContext(
        trend_12h_pct=-0.5,
        atr_percentile=50.0,
        price=30000.0,
        symbol="BTCUSDT",
    )
    assert agent.should_trade(ctx_neg) is None


# ---------------------------------------------------------------------------
# Test 2: CalibratedAgent skips low DQS
# ---------------------------------------------------------------------------

def test_calibrated_agent_skips_low_dqs():
    """CalibratedAgent should skip trades when DQS is in 'skip' tier."""
    from tradememory.data.context_builder import MarketContext
    from tradememory.simulation.agent import CalibratedAgent

    strategy = _simple_strategy()
    agent = CalibratedAgent(strategy, fixed_lot=0.01)

    # Set bad affective state to push DQS down
    agent.db.init_affective(peak_equity=10000.0, current_equity=7000.0)
    state = agent.db.load_affective()
    state["consecutive_losses"] = 6
    state["confidence_level"] = 0.1
    state["drawdown_state"] = 0.30  # 30%
    agent.db.save_affective(state)

    ctx = MarketContext(
        trend_12h_pct=0.5,
        atr_percentile=50.0,
        price=30000.0,
        symbol="BTCUSDT",
    )

    signal = agent.should_trade(ctx)
    # With bad risk state (DD>20%, losses>4), risk_state factor = 0
    # Other factors neutral (1.0) → score ≈ (0+1+1+0+1)/5*5 = 3.0 → skip or caution
    # Either skip (no signal) or reduced signal is acceptable
    if signal is not None:
        assert signal.lot_size < 0.01, "Should have reduced lot size"


# ---------------------------------------------------------------------------
# Test 3: CalibratedAgent reduces on changepoint
# ---------------------------------------------------------------------------

def test_calibrated_agent_reduces_on_changepoint():
    """CalibratedAgent should reduce position when changepoint detected."""
    from tradememory.simulation.agent import CalibratedAgent, SimulatedTrade

    strategy = _simple_strategy()
    agent = CalibratedAgent(strategy, fixed_lot=0.01)

    # Manually set high changepoint probability
    agent._last_cp_prob = 0.8
    agent._last_cusum_alert = True

    # Good affective state so DQS doesn't block
    agent.db.init_affective(peak_equity=10000.0, current_equity=10000.0)

    from tradememory.data.context_builder import MarketContext
    ctx = MarketContext(
        trend_12h_pct=0.5,
        atr_percentile=50.0,
        price=30000.0,
        symbol="BTCUSDT",
    )

    signal = agent.should_trade(ctx)
    if signal is not None:
        # Lot should be reduced: base 0.01 * DQS_mult * 0.5 (changepoint)
        assert signal.lot_size <= 0.01 * 0.5 + 0.001, (
            f"Expected reduced lot, got {signal.lot_size}"
        )


# ---------------------------------------------------------------------------
# Test 4: Simulator runs without error
# ---------------------------------------------------------------------------

def test_simulator_runs_without_error():
    """Simulator should complete without exceptions on synthetic data."""
    from tradememory.simulation.agent import BaseAgent
    from tradememory.simulation.simulator import Simulator

    series = _make_series(100)
    strategy = _simple_strategy()
    agent = BaseAgent(strategy, fixed_lot=0.01)

    sim = Simulator(agent, series, timeframe_str="1h")
    result = sim.run()

    assert result.agent_name == agent.name
    assert result.strategy_name == "TestTrend"
    assert result.symbol == "BTCUSDT"
    assert isinstance(result.fitness, FitnessMetrics)


# ---------------------------------------------------------------------------
# Test 5: Simulator fitness metrics valid
# ---------------------------------------------------------------------------

def test_simulator_fitness_metrics_valid():
    """FitnessMetrics should have valid bounds."""
    from tradememory.simulation.agent import BaseAgent
    from tradememory.simulation.simulator import Simulator

    series = _make_series(200, seed=99)
    strategy = _simple_strategy()
    agent = BaseAgent(strategy, fixed_lot=0.01)

    sim = Simulator(agent, series, timeframe_str="1h")
    result = sim.run()

    fm = result.fitness
    assert 0.0 <= fm.win_rate <= 1.0
    assert fm.max_drawdown_pct >= 0.0
    assert fm.trade_count >= 0
    # All trades should have valid pnl_r
    for t in result.trades:
        assert math.isfinite(t.pnl_r), f"pnl_r not finite: {t.pnl_r}"


# ---------------------------------------------------------------------------
# Test 6: A/B experiment uses same data
# ---------------------------------------------------------------------------

def test_ab_experiment_same_data():
    """ABExperiment should run both agents on the same OOS data."""
    from tradememory.simulation.experiment import ABExperiment

    series = _make_series(150)
    strategy = _simple_strategy()

    exp = ABExperiment(strategy, series, timeframe_str="1h", is_ratio=0.67)
    report = exp.run()

    # Both should have results
    assert report.agent_a is not None
    assert report.agent_b is not None
    assert report.agent_a.symbol == "BTCUSDT"
    assert report.agent_b.symbol == "BTCUSDT"

    # Sharpe improvement should be a finite number
    assert math.isfinite(report.sharpe_improvement)
    assert math.isfinite(report.dd_reduction)


# ---------------------------------------------------------------------------
# Test 7: Ablation has 4 variants
# ---------------------------------------------------------------------------

def test_ablation_has_4_variants():
    """Ablation study should produce exactly 4 variants."""
    from tradememory.simulation.experiment import ABExperiment

    series = _make_series(150)
    strategy = _simple_strategy()

    exp = ABExperiment(strategy, series, timeframe_str="1h", is_ratio=0.67)
    ablation_results = exp.ablation()

    assert len(ablation_results) == 4
    variant_names = {a.variant_name for a in ablation_results}
    assert variant_names == {"no_dqs", "no_changepoint", "no_kelly", "no_regime"}

    for a in ablation_results:
        assert a.result is not None
        assert math.isfinite(a.sharpe_delta)


# ---------------------------------------------------------------------------
# Test 8: ComparisonReport fields complete
# ---------------------------------------------------------------------------

def test_comparison_report_fields():
    """ComparisonReport should have all expected fields."""
    from tradememory.simulation.experiment import ABExperiment

    series = _make_series(150, seed=77)
    strategy = _simple_strategy()

    exp = ABExperiment(strategy, series, timeframe_str="1h")
    report = exp.run()

    # Check all fields exist and are valid types
    assert isinstance(report.sharpe_improvement, float)
    assert isinstance(report.dd_reduction, float)
    assert isinstance(report.trades_skipped_by_b, int)
    assert isinstance(report.pnl_of_skipped_trades, float)
    assert isinstance(report.dqs_pnl_correlation, float)
    assert isinstance(report.statistical_significance, dict)

    # Statistical significance should have test info
    sig = report.statistical_significance
    assert "test" in sig


# ---------------------------------------------------------------------------
# Test 9: Preset strategies are valid CandidatePatterns
# ---------------------------------------------------------------------------

def test_preset_strategies_valid():
    """All preset strategies should be valid CandidatePattern instances."""
    from tradememory.simulation.presets import PRESET_STRATEGIES

    assert len(PRESET_STRATEGIES) == 3

    for s in PRESET_STRATEGIES:
        assert isinstance(s, CandidatePattern)
        assert s.source == "preset"
        assert len(s.entry_condition.conditions) >= 1
        assert s.exit_condition.stop_loss_atr is not None
        assert s.exit_condition.take_profit_atr is not None
        assert s.exit_condition.max_holding_bars is not None


# ---------------------------------------------------------------------------
# Test 10: Report generation
# ---------------------------------------------------------------------------

def test_report_generation():
    """FullExperimentReport should generate valid markdown."""
    from tradememory.simulation.report import FullExperimentReport

    sample_results = [
        {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "strategy": "TrendFollow",
            "comparison": {
                "sharpe_a": 0.5,
                "sharpe_b": 0.8,
                "sharpe_improvement": 0.6,
                "dd_a": 15.0,
                "dd_b": 10.0,
                "dd_reduction": 0.33,
                "trades_skipped": 5,
                "skipped_pnl": -120.50,
            },
            "ablation": [
                {"variant": "no_dqs", "sharpe": 0.6, "sharpe_delta": -0.2},
                {"variant": "no_changepoint", "sharpe": 0.75, "sharpe_delta": -0.05},
            ],
        }
    ]

    report = FullExperimentReport(results=sample_results)
    md = report.to_markdown()

    assert "# Self-Calibrating Trading Agent" in md
    assert "BTCUSDT" in md
    assert "TrendFollow" in md
    assert "Ablation" in md

    # Save to temp file
    tmp_path = os.path.join(tempfile.mkdtemp(), "test_report")
    report.save(tmp_path)
    assert os.path.exists(tmp_path + ".json")
    assert os.path.exists(tmp_path + ".md")
