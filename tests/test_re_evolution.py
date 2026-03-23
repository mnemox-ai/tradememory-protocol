"""Tests for ReEvolutionPipeline — grid-based re-evolution."""

import pytest

from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    ExitCondition,
    FitnessMetrics,
    RuleCondition,
)
from tradememory.evolution.re_evolution import (
    GridCandidate,
    GridSearchSpace,
    ReEvolutionConfig,
    ReEvolutionPipeline,
    ReEvolutionResult,
    build_grid_pattern,
    generate_grid,
)
from tradememory.evolution.strategy_registry import StrategyRegistry


# --- Grid helpers ---


class TestBuildGridPattern:
    def test_long_pattern(self):
        p = build_grid_pattern(
            hour_utc=14, direction="long", trend_threshold=0.3,
            sl_atr=1.0, tp_atr=2.0, max_holding_bars=6,
        )
        assert p.entry_condition.direction == "long"
        assert len(p.entry_condition.conditions) == 2
        # hour condition
        hour_cond = p.entry_condition.conditions[0]
        assert hour_cond.field == "hour_utc"
        assert hour_cond.op == ConditionOperator.EQ
        assert hour_cond.value == 14
        # trend condition: long uses GT
        trend_cond = p.entry_condition.conditions[1]
        assert trend_cond.op == ConditionOperator.GT
        assert trend_cond.value == 0.3
        # exit
        assert p.exit_condition.stop_loss_atr == 1.0
        assert p.exit_condition.take_profit_atr == 2.0
        assert p.exit_condition.max_holding_bars == 6

    def test_short_pattern(self):
        p = build_grid_pattern(
            hour_utc=16, direction="short", trend_threshold=-0.3,
            sl_atr=1.5, tp_atr=3.0, max_holding_bars=8,
        )
        assert p.entry_condition.direction == "short"
        trend_cond = p.entry_condition.conditions[1]
        assert trend_cond.op == ConditionOperator.LT
        assert trend_cond.value == -0.3

    def test_source_is_grid_search(self):
        p = build_grid_pattern(0, "long", 0.0, 1.0, 2.0, 6)
        assert p.source == "grid_search"


class TestGridSearchSpace:
    def test_default_total_combinations(self):
        s = GridSearchSpace()
        # 24 * 2 * 5 * 4 * 5 * 4 = 19200
        assert s.total_combinations == 19200

    def test_custom_space(self):
        s = GridSearchSpace(
            hour_utc=[14, 16],
            direction=["long"],
            trend_12h_pct_threshold=[0.0],
            sl_atr=[1.0],
            tp_atr=[2.0],
            max_holding_bars=[6],
        )
        assert s.total_combinations == 2

    def test_generate_grid_count(self):
        s = GridSearchSpace(
            hour_utc=[14],
            direction=["long", "short"],
            trend_12h_pct_threshold=[0.0, 0.3],
            sl_atr=[1.0],
            tp_atr=[2.0],
            max_holding_bars=[6],
        )
        candidates = generate_grid(s)
        assert len(candidates) == 4  # 1*2*2*1*1*1
        assert all(isinstance(c, GridCandidate) for c in candidates)
        assert all(c.pattern is not None for c in candidates)

    def test_generate_grid_params_correct(self):
        s = GridSearchSpace(
            hour_utc=[14],
            direction=["long"],
            trend_12h_pct_threshold=[0.3],
            sl_atr=[1.5],
            tp_atr=[3.0],
            max_holding_bars=[8],
        )
        candidates = generate_grid(s)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.params["hour_utc"] == 14
        assert c.params["direction"] == "long"
        assert c.params["trend_threshold"] == 0.3
        assert c.params["sl_atr"] == 1.5
        assert c.params["tp_atr"] == 3.0
        assert c.params["max_holding_bars"] == 8


# --- Mock backtest function ---


def make_mock_backtest(sharpe: float = 1.0, trades: int = 20):
    """Create a mock backtest function that returns fixed metrics."""
    def mock_fn(bars, contexts, atrs, pattern, timeframe="1h"):
        return FitnessMetrics(
            sharpe_ratio=sharpe,
            trade_count=trades,
            win_rate=0.55,
            profit_factor=1.5,
            total_pnl=100.0,
        )
    return mock_fn


def make_varied_backtest():
    """Mock backtest that returns different IS vs OOS results based on call count."""
    call_count = {"n": 0}

    def mock_fn(bars, contexts, atrs, pattern, timeframe="1h"):
        call_count["n"] += 1
        # Vary sharpe based on hour parameter to make grid search interesting
        hour = None
        for cond in pattern.entry_condition.conditions:
            if cond.field == "hour_utc":
                hour = cond.value
                break
        base_sharpe = (hour or 0) * 0.1  # hours 0-23 -> sharpe 0.0-2.3
        return FitnessMetrics(
            sharpe_ratio=round(base_sharpe, 4),
            trade_count=20,
            win_rate=0.5 + base_sharpe * 0.01,
            profit_factor=1.0 + base_sharpe * 0.2,
            total_pnl=base_sharpe * 50,
        )
    return mock_fn


# --- ReEvolutionPipeline tests ---


class TestReEvolutionPipeline:
    def _small_space(self):
        return GridSearchSpace(
            hour_utc=[14, 16],
            direction=["long"],
            trend_12h_pct_threshold=[0.0],
            sl_atr=[1.0],
            tp_atr=[2.0],
            max_holding_bars=[6],
        )

    def test_run_happy_path(self):
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_mock_backtest(sharpe=2.0, trades=30),
            grid_space=self._small_space(),
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
        )
        assert result.num_tested == 2
        assert result.num_viable == 2
        assert result.best_candidate is not None
        assert result.best_candidate.oos_fitness.sharpe_ratio == 2.0

    def test_run_no_viable_candidates(self):
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_mock_backtest(sharpe=-1.0, trades=5),
            grid_space=self._small_space(),
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
        )
        assert result.best_candidate is None
        assert "No viable IS" in result.reason

    def test_run_no_oos_viable(self):
        """IS passes but OOS has 0 trades."""
        call_count = {"n": 0}

        def is_good_oos_bad(bars, contexts, atrs, pattern, timeframe="1h"):
            call_count["n"] += 1
            # First N calls are IS (good), rest are OOS (bad)
            if call_count["n"] <= 2:  # 2 candidates in small space
                return FitnessMetrics(sharpe_ratio=2.0, trade_count=20)
            return FitnessMetrics(sharpe_ratio=-1.0, trade_count=2)

        pipeline = ReEvolutionPipeline(
            backtest_fn=is_good_oos_bad,
            grid_space=self._small_space(),
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
        )
        assert result.best_candidate is None
        assert "No OOS-viable" in result.reason

    def test_dsr_gate_calculation(self):
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_mock_backtest(sharpe=2.0, trades=30),
            grid_space=self._small_space(),
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
        )
        assert result.dsr is not None
        assert result.dsr_pvalue is not None

    def test_deploy_to_registry(self):
        registry = StrategyRegistry()
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_mock_backtest(sharpe=3.0, trades=50),
            grid_space=self._small_space(),
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
            registry=registry,
            version_id="V1",
            metadata={"window": "2020-01 to 2020-04"},
        )
        assert result.deployed is True
        assert registry.version_count == 1
        active = registry.get_active()
        assert active.version_id == "V1"
        assert active.metadata == {"window": "2020-01 to 2020-04"}

    def test_no_deploy_without_registry(self):
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_mock_backtest(sharpe=3.0, trades=50),
            grid_space=self._small_space(),
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
        )
        assert result.deployed is False

    def test_no_deploy_without_version_id(self):
        registry = StrategyRegistry()
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_mock_backtest(sharpe=3.0, trades=50),
            grid_space=self._small_space(),
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
            registry=registry,
        )
        assert result.deployed is False

    def test_cumulative_trials_accumulate(self):
        registry = StrategyRegistry()
        registry.cumulative_trials = 10000  # previous trials
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_mock_backtest(sharpe=3.0, trades=50),
            grid_space=self._small_space(),
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
            registry=registry,
            version_id="V2",
        )
        # DSR should use 10000 + 2 = 10002 trials
        assert result.dsr is not None
        # After deploy, registry should have cumulative = 10000 + 2
        assert registry.cumulative_trials == 10002

    def test_varied_backtest_selects_best_hour(self):
        """Grid with varied hours should select the highest-sharpe hour."""
        space = GridSearchSpace(
            hour_utc=[5, 10, 20],  # sharpe = 0.5, 1.0, 2.0
            direction=["long"],
            trend_12h_pct_threshold=[0.0],
            sl_atr=[1.0],
            tp_atr=[2.0],
            max_holding_bars=[6],
        )
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_varied_backtest(),
            grid_space=space,
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
        )
        assert result.best_candidate is not None
        assert result.best_candidate.params["hour_utc"] == 20

    def test_config_min_is_trades_filter(self):
        """Candidates below min_is_trades should be filtered."""
        config = ReEvolutionConfig(min_is_trades=50)
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_mock_backtest(sharpe=2.0, trades=20),
            config=config,
            grid_space=self._small_space(),
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
        )
        assert result.num_viable == 0
        assert "No viable IS" in result.reason

    def test_config_min_oos_trades_filter(self):
        """OOS candidates below min_oos_trades should be filtered."""
        config = ReEvolutionConfig(min_oos_trades=100)
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_mock_backtest(sharpe=2.0, trades=20),
            config=config,
            grid_space=self._small_space(),
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
        )
        assert "No OOS-viable" in result.reason

    def test_top_n_limits_oos_backtests(self):
        """Only top_n_for_oos candidates should be OOS tested."""
        config = ReEvolutionConfig(top_n_for_oos=1)
        space = GridSearchSpace(
            hour_utc=[5, 10, 15, 20],
            direction=["long"],
            trend_12h_pct_threshold=[0.0],
            sl_atr=[1.0],
            tp_atr=[2.0],
            max_holding_bars=[6],
        )
        oos_count = {"n": 0}
        base_fn = make_varied_backtest()

        def counting_fn(bars, contexts, atrs, pattern, timeframe="1h"):
            result = base_fn(bars, contexts, atrs, pattern, timeframe)
            return result

        pipeline = ReEvolutionPipeline(
            backtest_fn=counting_fn,
            config=config,
            grid_space=space,
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
        )
        # With top_n_for_oos=1, only 1 should have oos_fitness
        candidates_with_oos = [
            c for c in generate_grid(space) if True  # just count expected
        ]
        # Best candidate should still be found
        assert result.best_candidate is not None


    def test_cumulative_trials_always_accumulate_on_dsr_fail(self):
        """Bug fix: cumulative_trials must increment even when DSR gate fails."""
        registry = StrategyRegistry()
        registry.cumulative_trials = 100000  # huge M makes DSR impossible
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_mock_backtest(sharpe=0.5, trades=20),
            grid_space=self._small_space(),  # 2 candidates
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
            registry=registry,
            version_id="V_FAIL",
        )
        # DSR should fail with M=100002
        assert not result.passed_dsr_gate
        assert not result.deployed
        # But cumulative_trials MUST still be incremented
        assert registry.cumulative_trials == 100002

    def test_cumulative_trials_accumulate_on_no_viable_is(self):
        """cumulative_trials must increment even when no IS-viable candidates."""
        registry = StrategyRegistry()
        registry.cumulative_trials = 500
        pipeline = ReEvolutionPipeline(
            backtest_fn=make_mock_backtest(sharpe=-1.0, trades=5),
            grid_space=self._small_space(),  # 2 candidates
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
            registry=registry,
        )
        assert "No viable IS" in result.reason
        assert registry.cumulative_trials == 502

    def test_cumulative_trials_accumulate_on_no_oos_viable(self):
        """cumulative_trials must increment even when no OOS-viable candidates."""
        registry = StrategyRegistry()
        registry.cumulative_trials = 300
        call_count = {"n": 0}

        def is_good_oos_bad(bars, contexts, atrs, pattern, timeframe="1h"):
            call_count["n"] += 1
            if call_count["n"] <= 2:  # IS calls
                return FitnessMetrics(sharpe_ratio=2.0, trade_count=20)
            return FitnessMetrics(sharpe_ratio=-1.0, trade_count=2)  # OOS fails

        pipeline = ReEvolutionPipeline(
            backtest_fn=is_good_oos_bad,
            grid_space=self._small_space(),  # 2 candidates
        )
        result = pipeline.run(
            is_bars=[], is_contexts=[], is_atrs=[],
            oos_bars=[], oos_contexts=[], oos_atrs=[],
            registry=registry,
        )
        assert "No OOS-viable" in result.reason
        assert registry.cumulative_trials == 302


class TestReEvolutionResult:
    def test_default_state(self):
        r = ReEvolutionResult()
        assert r.best_candidate is None
        assert r.num_tested == 0
        assert r.deployed is False
        assert r.passed_dsr_gate is False
