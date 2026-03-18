"""Shared strategy definitions for backtesting and live execution scripts."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    ExitCondition,
    RuleCondition,
)


def build_strategy_e() -> CandidatePattern:
    """Strategy E: Afternoon Engine — LONG at 14:00 UTC when 12h trend UP."""
    return CandidatePattern(
        pattern_id="STRAT-E",
        name="Strategy E (Afternoon Engine)",
        description="LONG at 14:00 UTC when 12h trend is positive",
        entry_condition=EntryCondition(
            direction="long",
            conditions=[
                RuleCondition(field="hour_utc", op=ConditionOperator.EQ, value=14),
                RuleCondition(field="trend_12h_pct", op=ConditionOperator.GT, value=0),
            ],
        ),
        exit_condition=ExitCondition(
            stop_loss_atr=1.0,
            take_profit_atr=2.0,
            max_holding_bars=6,
        ),
        confidence=0.8,
        source="evolution_engine",
    )
