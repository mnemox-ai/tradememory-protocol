"""Tests for Evolution Engine models (Task 10.1)."""

import json
from datetime import datetime, timezone

import pytest

from src.tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    EvolutionConfig,
    EvolutionRun,
    ExitCondition,
    FitnessMetrics,
    Hypothesis,
    HypothesisStatus,
    RuleCondition,
    ValidityConditions,
)


# --- CandidatePattern ---


class TestCandidatePattern:
    def test_create_with_defaults(self):
        p = CandidatePattern(
            name="Test Pattern",
            description="A test",
            entry_condition=EntryCondition(direction="long"),
        )
        assert p.name == "Test Pattern"
        assert p.pattern_id.startswith("PAT-")
        assert p.confidence == 0.5
        assert p.source == "llm_discovery"
        assert p.created_at.tzinfo == timezone.utc

    def test_full_pattern(self):
        p = CandidatePattern(
            name="US Session Drain",
            description="Short at 16:00 UTC when 12H trend is negative",
            entry_condition=EntryCondition(
                direction="short",
                conditions=[
                    RuleCondition(field="hour_utc", op=ConditionOperator.EQ, value=16),
                    RuleCondition(field="trend_12h_pct", op=ConditionOperator.LT, value=0),
                ],
                description="Short at US session open in downtrend",
            ),
            exit_condition=ExitCondition(
                stop_loss_atr=1.5,
                take_profit_atr=3.0,
                max_holding_bars=8,
            ),
            validity_conditions=ValidityConditions(
                regime="trending_down",
                volatility_regime="normal",
            ),
            confidence=0.7,
            sample_count=43,
        )
        assert p.entry_condition.direction == "short"
        assert len(p.entry_condition.conditions) == 2
        assert p.exit_condition.stop_loss_atr == 1.5

    def test_to_semantic_memory(self):
        p = CandidatePattern(
            name="Test",
            description="desc",
            entry_condition=EntryCondition(direction="long"),
            confidence=0.8,
        )
        mem = p.to_semantic_memory()
        assert mem["pattern_id"] == p.pattern_id
        assert mem["confidence"] == 0.8
        assert "entry_rules" in mem
        assert "exit_rules" in mem
        assert "validity" in mem

    def test_json_serializable(self):
        p = CandidatePattern(
            name="Test",
            description="desc",
            entry_condition=EntryCondition(direction="long"),
        )
        data = json.loads(p.model_dump_json())
        assert data["name"] == "Test"

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            CandidatePattern(
                name="Bad",
                description="",
                entry_condition=EntryCondition(),
                confidence=1.5,
            )

    def test_utc_enforcement(self):
        p = CandidatePattern(
            name="Test",
            description="",
            entry_condition=EntryCondition(),
            created_at=datetime(2024, 1, 1),  # naive
        )
        assert p.created_at.tzinfo == timezone.utc


# --- RuleCondition ---


class TestRuleCondition:
    def test_all_operators(self):
        for op in ConditionOperator:
            c = RuleCondition(field="test", op=op, value=1)
            assert c.op == op

    def test_between_value(self):
        c = RuleCondition(field="atr_percentile", op=ConditionOperator.BETWEEN, value=[25, 75])
        assert c.value == [25, 75]

    def test_in_value(self):
        c = RuleCondition(field="session", op=ConditionOperator.IN, value=["asia", "london"])
        assert c.value == ["asia", "london"]


# --- FitnessMetrics ---


class TestFitnessMetrics:
    def test_viable(self):
        f = FitnessMetrics(sharpe_ratio=1.5, trade_count=50)
        assert f.is_viable is True

    def test_not_viable_low_trades(self):
        f = FitnessMetrics(sharpe_ratio=2.0, trade_count=10)
        assert f.is_viable is False

    def test_not_viable_negative_sharpe(self):
        f = FitnessMetrics(sharpe_ratio=-0.5, trade_count=100)
        assert f.is_viable is False

    def test_passes_oos(self):
        f = FitnessMetrics(sharpe_ratio=1.5, trade_count=50, max_drawdown_pct=10)
        assert f.passes_oos_filter is True

    def test_fails_oos_sharpe(self):
        f = FitnessMetrics(sharpe_ratio=0.8, trade_count=50, max_drawdown_pct=10)
        assert f.passes_oos_filter is False

    def test_fails_oos_drawdown(self):
        f = FitnessMetrics(sharpe_ratio=2.0, trade_count=50, max_drawdown_pct=25)
        assert f.passes_oos_filter is False


# --- Hypothesis ---


class TestHypothesis:
    def test_lifecycle(self):
        h = Hypothesis(
            pattern=CandidatePattern(name="Test", description="", entry_condition=EntryCondition()),
            generation=1,
        )
        assert h.status == HypothesisStatus.PENDING
        assert h.hypothesis_id.startswith("HYP-")

    def test_graveyard_entry(self):
        h = Hypothesis(
            pattern=CandidatePattern(name="Failed Strategy", description="Did not work", entry_condition=EntryCondition()),
            fitness_is=FitnessMetrics(sharpe_ratio=-0.5, trade_count=20),
            elimination_reason="Negative Sharpe in IS",
            status=HypothesisStatus.ELIMINATED,
        )
        entry = h.to_graveyard_entry()
        assert entry["pattern_name"] == "Failed Strategy"
        assert entry["elimination_reason"] == "Negative Sharpe in IS"
        assert entry["fitness_is"]["sharpe_ratio"] == -0.5


# --- EvolutionRun ---


class TestEvolutionRun:
    def test_create(self):
        run = EvolutionRun(config=EvolutionConfig())
        assert run.run_id.startswith("EVO-")
        assert run.config.symbol == "BTCUSDT"

    def test_summary(self):
        run = EvolutionRun(config=EvolutionConfig(symbol="ETHUSDT", generations=5))
        assert run.summary["symbol"] == "ETHUSDT"
        assert run.summary["generations"] == 5
        assert run.summary["graduated"] == 0
