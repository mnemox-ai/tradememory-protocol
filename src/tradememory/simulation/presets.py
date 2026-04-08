"""Preset trading strategies for simulation experiments.

Three baseline strategies that don't require LLM generation:
- TrendFollow: Enter on uptrend + moderate volatility
- Breakout: Enter on high-ATR volatility expansion
- MeanReversion: Enter on low-ATR range-bound conditions
"""

from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    ExitCondition,
    RuleCondition,
    ValidityConditions,
)

PRESET_STRATEGIES = [
    CandidatePattern(
        pattern_id="preset-trend-follow",
        name="TrendFollow",
        description="Enter long when 12h trend positive + ATR above median",
        entry_condition=EntryCondition(
            direction="long",
            conditions=[
                RuleCondition(field="trend_12h_pct", op=ConditionOperator.GT, value=0.5),
                RuleCondition(field="atr_percentile", op=ConditionOperator.GT, value=40),
            ],
            description="Uptrend with moderate volatility",
        ),
        exit_condition=ExitCondition(
            stop_loss_atr=1.5,
            take_profit_atr=3.0,
            max_holding_bars=48,
        ),
        validity_conditions=ValidityConditions(),
        confidence=0.5,
        source="preset",
    ),
    CandidatePattern(
        pattern_id="preset-breakout",
        name="Breakout",
        description="Enter long on high ATR breakout",
        entry_condition=EntryCondition(
            direction="long",
            conditions=[
                RuleCondition(field="atr_percentile", op=ConditionOperator.GT, value=70),
                RuleCondition(field="trend_12h_pct", op=ConditionOperator.GT, value=1.0),
            ],
            description="Volatility expansion breakout",
        ),
        exit_condition=ExitCondition(
            stop_loss_atr=2.0,
            take_profit_atr=4.0,
            max_holding_bars=24,
        ),
        validity_conditions=ValidityConditions(),
        confidence=0.5,
        source="preset",
    ),
    CandidatePattern(
        pattern_id="preset-mean-reversion",
        name="MeanReversion",
        description="Enter long on low ATR in ranging market",
        entry_condition=EntryCondition(
            direction="long",
            conditions=[
                RuleCondition(field="atr_percentile", op=ConditionOperator.LT, value=30),
                RuleCondition(field="trend_12h_pct", op=ConditionOperator.GT, value=-0.5),
                RuleCondition(field="trend_12h_pct", op=ConditionOperator.LT, value=0.5),
            ],
            description="Low volatility range-bound",
        ),
        exit_condition=ExitCondition(
            stop_loss_atr=1.0,
            take_profit_atr=1.5,
            max_holding_bars=12,
        ),
        validity_conditions=ValidityConditions(),
        confidence=0.5,
        source="preset",
    ),
]
