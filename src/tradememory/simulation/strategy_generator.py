"""Generate diverse strategies from parameter grid.

Instead of 3 hand-picked presets, systematically generate 150+ strategies
by varying: trend threshold, ATR threshold, SL/TP multiples, max holding period.
This ensures results are not cherry-picked.
"""

from __future__ import annotations

from itertools import product
from typing import List

from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    ExitCondition,
    RuleCondition,
    ValidityConditions,
)


def generate_strategy_grid() -> List[CandidatePattern]:
    """Generate strategies from parameter combinations.

    Grid:
    - trend_threshold: [0.3, 0.7, 1.5]  (weak/medium/strong trend)
    - atr_threshold: [30, 50, 70]  (low/mid/high volatility)
    - sl_atr: [1.0, 1.5, 2.5]  (tight/normal/wide stop)
    - tp_atr: [1.5, 3.0, 5.0]  (low/mid/high target)
    - max_hold: [12, 36, 72]  (short/medium/long hold)

    Filter: only keep tp > sl (positive expectancy structure).
    Generates 3x3x3x3x3 = 243 combos, filtered to ~150+ valid strategies.
    """
    strategies: List[CandidatePattern] = []
    idx = 0

    for trend_th, atr_th, sl, tp, hold in product(
        [0.3, 0.7, 1.5],
        [30, 50, 70],
        [1.0, 1.5, 2.5],
        [1.5, 3.0, 5.0],
        [12, 36, 72],
    ):
        if tp <= sl:
            continue

        idx += 1
        name = f"Grid_t{trend_th}_a{atr_th}_sl{sl}_tp{tp}_h{hold}"

        strategies.append(CandidatePattern(
            pattern_id=f"grid-{idx:04d}",
            name=name,
            description=(
                f"Trend>{trend_th}%, ATR>{atr_th}pct, "
                f"SL={sl}ATR, TP={tp}ATR, Hold<={hold}bars"
            ),
            entry_condition=EntryCondition(
                direction="long",
                conditions=[
                    RuleCondition(
                        field="trend_12h_pct",
                        op=ConditionOperator.GT,
                        value=trend_th,
                    ),
                    RuleCondition(
                        field="atr_percentile",
                        op=ConditionOperator.GT,
                        value=atr_th,
                    ),
                ],
                description=f"Trend>{trend_th}, ATR>{atr_th}pct",
            ),
            exit_condition=ExitCondition(
                stop_loss_atr=sl,
                take_profit_atr=tp,
                max_holding_bars=hold,
            ),
            validity_conditions=ValidityConditions(),
            confidence=0.5,
            source="grid",
        ))

    return strategies
