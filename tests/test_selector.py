"""Tests for Selection & Elimination (Task 10.4)."""

from datetime import datetime, timezone

import pytest

from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    ExitCondition,
    FitnessMetrics,
    Hypothesis,
    HypothesisStatus,
    RuleCondition,
)
from tradememory.evolution.selector import (
    SelectionConfig,
    SelectionResult,
    rank_by_is_fitness,
    select_and_eliminate,
    validate_oos,
)


# --- Helpers ---


def make_fitness(
    sharpe: float = 1.5,
    trade_count: int = 50,
    win_rate: float = 0.55,
    profit_factor: float = 1.5,
    max_dd: float = 10.0,
    total_pnl: float = 1000.0,
) -> FitnessMetrics:
    return FitnessMetrics(
        sharpe_ratio=sharpe,
        trade_count=trade_count,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown_pct=max_dd,
        total_pnl=total_pnl,
        avg_holding_bars=5.0,
        expectancy=total_pnl / trade_count if trade_count > 0 else 0,
    )


def make_hypothesis(
    name: str = "Test",
    is_fitness: FitnessMetrics = None,
    oos_fitness: FitnessMetrics = None,
) -> Hypothesis:
    pattern = CandidatePattern(
        name=name,
        description=f"{name} pattern",
        entry_condition=EntryCondition(
            direction="long",
            conditions=[RuleCondition(field="hour_utc", op=ConditionOperator.GTE, value=14)],
        ),
        exit_condition=ExitCondition(stop_loss_atr=1.0, take_profit_atr=2.0, max_holding_bars=10),
    )
    return Hypothesis(
        pattern=pattern,
        fitness_is=is_fitness,
        fitness_oos=oos_fitness,
    )


# --- Tests ---


class TestSelectionConfig:
    def test_defaults(self):
        c = SelectionConfig()
        assert c.top_n == 10
        assert c.min_oos_sharpe == 1.0
        assert c.min_oos_trade_count == 30
        assert c.max_oos_drawdown_pct == 20.0

    def test_custom(self):
        c = SelectionConfig(top_n=5, min_oos_sharpe=2.0)
        assert c.top_n == 5
        assert c.min_oos_sharpe == 2.0


class TestSelectionResult:
    def test_empty(self):
        r = SelectionResult()
        assert r.graduated_count == 0
        assert r.eliminated_count == 0


class TestRankByISFitness:
    def test_ranks_by_sharpe(self):
        h1 = make_hypothesis("Low", is_fitness=make_fitness(sharpe=0.5, trade_count=20))
        h2 = make_hypothesis("High", is_fitness=make_fitness(sharpe=2.0, trade_count=20))
        h3 = make_hypothesis("Mid", is_fitness=make_fitness(sharpe=1.2, trade_count=20))

        ranked = rank_by_is_fitness([h1, h2, h3])

        assert ranked[0].pattern.name == "High"
        assert ranked[1].pattern.name == "Mid"
        assert ranked[2].pattern.name == "Low"

    def test_filters_low_trade_count(self):
        h1 = make_hypothesis("Good", is_fitness=make_fitness(sharpe=2.0, trade_count=20))
        h2 = make_hypothesis("Few Trades", is_fitness=make_fitness(sharpe=3.0, trade_count=5))

        ranked = rank_by_is_fitness([h1, h2])

        assert len(ranked) == 1
        assert ranked[0].pattern.name == "Good"

    def test_filters_negative_sharpe(self):
        h1 = make_hypothesis("Winner", is_fitness=make_fitness(sharpe=1.0, trade_count=20))
        h2 = make_hypothesis("Loser", is_fitness=make_fitness(sharpe=-0.5, trade_count=20))

        ranked = rank_by_is_fitness([h1, h2])

        assert len(ranked) == 1
        assert ranked[0].pattern.name == "Winner"

    def test_top_n_limit(self):
        hypotheses = [
            make_hypothesis(f"H{i}", is_fitness=make_fitness(sharpe=float(i), trade_count=20))
            for i in range(20)
        ]
        config = SelectionConfig(top_n=3)

        ranked = rank_by_is_fitness(hypotheses, config)

        assert len(ranked) == 3
        assert ranked[0].pattern.name == "H19"  # highest sharpe

    def test_no_fitness_skipped(self):
        h1 = make_hypothesis("Has Fitness", is_fitness=make_fitness(trade_count=20))
        h2 = make_hypothesis("No Fitness")

        ranked = rank_by_is_fitness([h1, h2])

        assert len(ranked) == 1

    def test_empty_input(self):
        assert rank_by_is_fitness([]) == []

    def test_rank_by_profit_factor(self):
        h1 = make_hypothesis("Low PF", is_fitness=make_fitness(sharpe=2.0, profit_factor=1.2, trade_count=20))
        h2 = make_hypothesis("High PF", is_fitness=make_fitness(sharpe=1.0, profit_factor=3.0, trade_count=20))

        config = SelectionConfig(rank_by="profit_factor")
        ranked = rank_by_is_fitness([h1, h2], config)

        assert ranked[0].pattern.name == "High PF"


class TestValidateOOS:
    def test_passes_all_thresholds(self):
        h = make_hypothesis(
            oos_fitness=make_fitness(sharpe=1.5, trade_count=50, win_rate=0.55, profit_factor=1.8, max_dd=10.0),
        )
        passed, reason = validate_oos(h)
        assert passed is True
        assert reason == ""

    def test_fails_sharpe(self):
        h = make_hypothesis(
            oos_fitness=make_fitness(sharpe=0.5, trade_count=50),
        )
        passed, reason = validate_oos(h)
        assert passed is False
        assert "Sharpe" in reason

    def test_fails_trade_count(self):
        h = make_hypothesis(
            oos_fitness=make_fitness(trade_count=10),
        )
        passed, reason = validate_oos(h)
        assert passed is False
        assert "trade_count" in reason

    def test_fails_drawdown(self):
        h = make_hypothesis(
            oos_fitness=make_fitness(max_dd=25.0, trade_count=50),
        )
        passed, reason = validate_oos(h)
        assert passed is False
        assert "max_dd" in reason

    def test_fails_profit_factor(self):
        h = make_hypothesis(
            oos_fitness=make_fitness(profit_factor=0.9, trade_count=50),
        )
        passed, reason = validate_oos(h)
        assert passed is False
        assert "PF" in reason

    def test_fails_win_rate(self):
        h = make_hypothesis(
            oos_fitness=make_fitness(win_rate=0.3, trade_count=50),
        )
        passed, reason = validate_oos(h)
        assert passed is False
        assert "win_rate" in reason

    def test_no_oos_fitness(self):
        h = make_hypothesis()
        passed, reason = validate_oos(h)
        assert passed is False
        assert "no OOS" in reason

    def test_custom_thresholds(self):
        h = make_hypothesis(
            oos_fitness=make_fitness(sharpe=1.8, trade_count=50),
        )
        config = SelectionConfig(min_oos_sharpe=2.0)
        passed, reason = validate_oos(h, config)
        assert passed is False

    def test_borderline_passes(self):
        """Exactly at thresholds should pass."""
        h = make_hypothesis(
            oos_fitness=make_fitness(
                sharpe=1.0, trade_count=30, win_rate=0.4,
                profit_factor=1.2, max_dd=20.0,
            ),
        )
        passed, _ = validate_oos(h)
        assert passed is True


class TestSelectAndEliminate:
    def test_full_pipeline(self):
        """Good strategies graduate, bad ones get eliminated."""
        good = make_hypothesis(
            "Winner",
            is_fitness=make_fitness(sharpe=2.0, trade_count=50),
            oos_fitness=make_fitness(sharpe=1.5, trade_count=40, profit_factor=1.8),
        )
        bad_oos = make_hypothesis(
            "Bad OOS",
            is_fitness=make_fitness(sharpe=1.5, trade_count=50),
            oos_fitness=make_fitness(sharpe=0.3, trade_count=40),
        )
        bad_is = make_hypothesis(
            "Bad IS",
            is_fitness=make_fitness(sharpe=-1.0, trade_count=50),
            oos_fitness=make_fitness(sharpe=2.0, trade_count=40),
        )

        result = select_and_eliminate([good, bad_oos, bad_is])

        assert result.graduated_count == 1
        assert result.graduated[0].pattern.name == "Winner"
        assert result.graduated[0].status == HypothesisStatus.GRADUATED

        # bad_oos eliminated in OOS, bad_is eliminated in IS
        assert result.eliminated_count == 2
        eliminated_names = {h.pattern.name for h in result.eliminated}
        assert "Bad OOS" in eliminated_names
        assert "Bad IS" in eliminated_names

    def test_graveyard_entries(self):
        """Eliminated hypotheses produce graveyard entries."""
        h = make_hypothesis(
            "Loser",
            is_fitness=make_fitness(sharpe=1.0, trade_count=50),
            oos_fitness=make_fitness(sharpe=0.2, trade_count=40),
        )

        result = select_and_eliminate([h])

        assert len(result.graveyard_entries) == 1
        entry = result.graveyard_entries[0]
        assert entry["pattern_name"] == "Loser"
        assert "elimination_reason" in entry

    def test_empty_input(self):
        result = select_and_eliminate([])
        assert result.graduated_count == 0
        assert result.eliminated_count == 0

    def test_all_graduate(self):
        """All hypotheses can graduate if they pass."""
        hypotheses = [
            make_hypothesis(
                f"H{i}",
                is_fitness=make_fitness(sharpe=2.0 + i * 0.1, trade_count=50),
                oos_fitness=make_fitness(sharpe=1.5 + i * 0.1, trade_count=40, profit_factor=1.8),
            )
            for i in range(3)
        ]

        result = select_and_eliminate(hypotheses)
        assert result.graduated_count == 3

    def test_all_eliminated(self):
        """All hypotheses can be eliminated."""
        hypotheses = [
            make_hypothesis(
                f"H{i}",
                is_fitness=make_fitness(sharpe=0.5 + i * 0.1, trade_count=50),
                oos_fitness=make_fitness(sharpe=0.1, trade_count=10),
            )
            for i in range(3)
        ]

        result = select_and_eliminate(hypotheses)
        assert result.graduated_count == 0
        assert result.eliminated_count == 3

    def test_status_updated(self):
        """Hypothesis status is updated in place."""
        h = make_hypothesis(
            "Test",
            is_fitness=make_fitness(sharpe=2.0, trade_count=50),
            oos_fitness=make_fitness(sharpe=1.5, trade_count=40, profit_factor=1.8),
        )
        assert h.status == HypothesisStatus.PENDING

        select_and_eliminate([h])
        assert h.status == HypothesisStatus.GRADUATED

    def test_elimination_reason_set(self):
        """Eliminated hypotheses have elimination_reason."""
        h = make_hypothesis(
            "Test",
            is_fitness=make_fitness(sharpe=1.0, trade_count=50),
            oos_fitness=make_fitness(sharpe=0.2, trade_count=40),
        )

        select_and_eliminate([h])
        assert h.elimination_reason is not None
        assert "Sharpe" in h.elimination_reason
