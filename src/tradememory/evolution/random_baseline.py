"""Random baseline generator for Evolution Engine.

Generates random strategies to establish a null-hypothesis baseline.
Any real pattern must beat the 95th percentile of random strategies
to be considered statistically significant.
"""

from __future__ import annotations

import bisect
import random
import statistics
from typing import Dict, List

from pydantic import BaseModel

from tradememory.data.models import OHLCVSeries
from tradememory.evolution.backtester import backtest
from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    ExitCondition,
    RuleCondition,
)


class BaselineResult(BaseModel):
    """Summary statistics from a random strategy baseline run."""

    n_strategies: int
    sharpe_distribution: List[float]  # sorted ascending
    mean_sharpe: float
    std_sharpe: float
    percentile_95: float  # Sharpe value at 95th percentile


class RandomStrategyGenerator:
    """Generate random trading strategies for baseline comparison.

    Each strategy has a random hour-of-day entry, random direction,
    and fixed exit rules. Used to establish a null distribution of
    Sharpe ratios against which real patterns are tested.
    """

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    def generate(self, n: int = 1000) -> List[CandidatePattern]:
        """Generate n random candidate patterns."""
        patterns: List[CandidatePattern] = []
        for i in range(n):
            hour = self._rng.randint(0, 23)
            direction = self._rng.choice(["long", "short"])

            pattern = CandidatePattern(
                pattern_id=f"RANDOM-{i + 1:03d}",
                name=f"RANDOM-{i + 1:03d}",
                description=f"Random baseline: {direction} at hour {hour} UTC",
                entry_condition=EntryCondition(
                    direction=direction,
                    conditions=[
                        RuleCondition(
                            field="hour_utc",
                            op=ConditionOperator.EQ,
                            value=hour,
                        )
                    ],
                    description=f"Enter {direction} when hour_utc == {hour}",
                ),
                exit_condition=ExitCondition(
                    stop_loss_atr=1.0,
                    take_profit_atr=2.0,
                    max_holding_bars=6,
                ),
                confidence=0.0,
                source="random_baseline",
            )
            patterns.append(pattern)
        return patterns


def run_baseline(
    series: OHLCVSeries,
    n_strategies: int = 1000,
    seed: int = 42,
    timeframe: str = "1h",
) -> BaselineResult:
    """Generate N random strategies and backtest each to build a null distribution.

    Args:
        series: OHLCV data to backtest against.
        n_strategies: Number of random strategies to generate.
        seed: Random seed for reproducibility.
        timeframe: Bar timeframe for Sharpe annualization.

    Returns:
        BaselineResult with sorted Sharpe distribution and summary stats.
    """
    if not series.bars or len(series.bars) < 30:
        return BaselineResult(
            n_strategies=0,
            sharpe_distribution=[],
            mean_sharpe=0.0,
            std_sharpe=0.0,
            percentile_95=0.0,
        )

    generator = RandomStrategyGenerator(seed=seed)
    patterns = generator.generate(n_strategies)

    sharpes: List[float] = []
    for pattern in patterns:
        metrics = backtest(series, pattern, timeframe=timeframe)
        sharpes.append(metrics.sharpe_ratio)

    sharpes.sort()

    mean_s = statistics.mean(sharpes) if sharpes else 0.0
    std_s = statistics.stdev(sharpes) if len(sharpes) >= 2 else 0.0

    # 95th percentile
    if sharpes:
        idx_95 = int(len(sharpes) * 0.95)
        idx_95 = min(idx_95, len(sharpes) - 1)
        p95 = sharpes[idx_95]
    else:
        p95 = 0.0

    return BaselineResult(
        n_strategies=n_strategies,
        sharpe_distribution=sharpes,
        mean_sharpe=round(mean_s, 4),
        std_sharpe=round(std_s, 4),
        percentile_95=round(p95, 4),
    )


def compute_percentile_rank(sharpe: float, distribution: List[float]) -> float:
    """Compute percentile rank (0-100) of a Sharpe ratio within a distribution.

    Uses bisect on a sorted distribution. Empty distribution returns 0.0.
    """
    if not distribution:
        return 0.0
    rank = bisect.bisect_left(distribution, sharpe)
    return round((rank / len(distribution)) * 100, 2)


def rank_strategies(
    strategies: Dict[str, float],
    result: BaselineResult,
) -> Dict[str, dict]:
    """Rank named strategies against the baseline distribution.

    Args:
        strategies: {name: sharpe_value} dict.
        result: BaselineResult from run_baseline().

    Returns:
        {name: {"sharpe": float, "percentile": float, "passes_5pct": bool}}
    """
    ranked: Dict[str, dict] = {}
    for name, sharpe in strategies.items():
        pct = compute_percentile_rank(sharpe, result.sharpe_distribution)
        ranked[name] = {
            "sharpe": sharpe,
            "percentile": pct,
            "passes_5pct": pct >= 95.0,
        }
    return ranked
