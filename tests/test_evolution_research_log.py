"""Tests for evolution research log auto-writer."""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from tradememory.evolution.models import (
    CandidatePattern,
    EntryCondition,
    EvolutionConfig,
    EvolutionRun,
    ExitCondition,
    FitnessMetrics,
    Hypothesis,
    HypothesisStatus,
    RuleCondition,
)
from tradememory.evolution.research_log import (
    _next_experiment_id,
    format_experiment_log,
    write_experiment_log,
)


# --- Helpers ---


def _make_pattern(name: str = "TestPattern") -> CandidatePattern:
    return CandidatePattern(
        name=name,
        description=f"Test pattern: {name}",
        entry_condition=EntryCondition(
            direction="long",
            conditions=[RuleCondition(field="hour_utc", op="eq", value=10)],
        ),
        exit_condition=ExitCondition(stop_loss_atr=1.5, take_profit_atr=3.0),
    )


def _make_fitness(sharpe: float = 1.5, wr: float = 0.55, trades: int = 50) -> FitnessMetrics:
    return FitnessMetrics(
        sharpe_ratio=sharpe,
        win_rate=wr,
        profit_factor=1.4,
        total_pnl=2000.0,
        max_drawdown_pct=8.0,
        trade_count=trades,
    )


def _make_run() -> EvolutionRun:
    """Create a minimal EvolutionRun with 2 graduated + 1 graveyard."""
    config = EvolutionConfig(symbol="BTCUSDT", timeframe="1h", generations=2)
    run = EvolutionRun(
        run_id="EVO-TEST01",
        config=config,
        started_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 3, 16, 12, 15, tzinfo=timezone.utc),
    )

    # Graduated
    h1 = Hypothesis(
        hypothesis_id="HYP-G01",
        pattern=_make_pattern("Winner A"),
        generation=0,
        status=HypothesisStatus.GRADUATED,
        fitness_is=_make_fitness(sharpe=2.1, wr=0.58),
        fitness_oos=_make_fitness(sharpe=1.6, wr=0.54),
    )
    h2 = Hypothesis(
        hypothesis_id="HYP-G02",
        pattern=_make_pattern("Winner B"),
        generation=1,
        status=HypothesisStatus.GRADUATED,
        fitness_is=_make_fitness(sharpe=1.8, wr=0.60),
        fitness_oos=_make_fitness(sharpe=1.3, wr=0.52),
    )
    run.graduated = [h1, h2]

    # Graveyard
    h3 = Hypothesis(
        hypothesis_id="HYP-E01",
        pattern=_make_pattern("Loser A"),
        generation=0,
        status=HypothesisStatus.ELIMINATED,
        fitness_is=_make_fitness(sharpe=-0.3, wr=0.42),
        elimination_reason="Negative Sharpe in IS",
    )
    run.graveyard = [h3]

    run.total_llm_tokens = 12000
    run.total_backtests = 15

    return run


# --- Tests ---


class TestNextExperimentId:
    def test_new_file(self, tmp_path):
        path = str(tmp_path / "log.md")
        assert _next_experiment_id(path) == "EXP-001"

    def test_increments_from_existing(self, tmp_path):
        path = tmp_path / "log.md"
        path.write_text(
            "# Log\n\n## EXP-001: test\n\nstuff\n\n## EXP-002: test2\n\nmore\n",
            encoding="utf-8",
        )
        assert _next_experiment_id(str(path)) == "EXP-003"


class TestFormatExperimentLog:
    def test_contains_experiment_id(self):
        run = _make_run()
        md = format_experiment_log(run, experiment_id="EXP-007")
        assert "## EXP-007:" in md

    def test_contains_config(self):
        run = _make_run()
        md = format_experiment_log(run)
        assert "BTCUSDT" in md
        assert "1h" in md
        assert "2 generations" in md or "Generations**: 2" in md

    def test_contains_results_table(self):
        run = _make_run()
        md = format_experiment_log(run)
        assert "Winner A" in md
        assert "Winner B" in md
        assert "Loser A" in md
        assert "Sharpe IS" in md

    def test_contains_graveyard_summary(self):
        run = _make_run()
        md = format_experiment_log(run)
        assert "Graduated**: 2" in md
        assert "Eliminated**: 1" in md
        assert "Negative Sharpe in IS" in md


class TestWriteExperimentLog:
    def test_creates_new_file(self, tmp_path):
        run = _make_run()
        log_path = str(tmp_path / "research_log.md")
        exp_id = write_experiment_log(run, log_path)

        assert exp_id == "EXP-001"
        content = (tmp_path / "research_log.md").read_text(encoding="utf-8")
        assert "# Evolution Research Log" in content
        assert "## EXP-001:" in content
        assert "Winner A" in content

    def test_appends_to_existing(self, tmp_path):
        log_path = str(tmp_path / "research_log.md")

        run1 = _make_run()
        run1.run_id = "EVO-RUN1"
        write_experiment_log(run1, log_path)

        run2 = _make_run()
        run2.run_id = "EVO-RUN2"
        exp_id = write_experiment_log(run2, log_path)

        assert exp_id == "EXP-002"
        content = (tmp_path / "research_log.md").read_text(encoding="utf-8")
        assert "## EXP-001:" in content
        assert "## EXP-002:" in content

    def test_creates_parent_dirs(self, tmp_path):
        run = _make_run()
        log_path = str(tmp_path / "sub" / "dir" / "log.md")
        exp_id = write_experiment_log(run, log_path)
        assert exp_id == "EXP-001"
        assert os.path.exists(log_path)
