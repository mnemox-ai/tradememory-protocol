"""Selection & Elimination — IS/OOS hypothesis filtering.

Pipeline:
1. Rank hypotheses by IS fitness (Sharpe ratio)
2. Top N proceed to OOS validation
3. OOS survivors → graduated (ready for semantic memory)
4. Failed hypotheses → Strategy Graveyard (for LLM learning)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from tradememory.evolution.models import (
    FitnessMetrics,
    Hypothesis,
    HypothesisStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class SelectionConfig:
    """Thresholds for IS ranking and OOS validation."""

    # IS selection: how many top hypotheses proceed to OOS
    top_n: int = 10

    # IS minimum thresholds (pre-filter before ranking)
    min_is_trade_count: int = 10
    min_is_sharpe: float = 0.0  # at least break-even

    # OOS validation thresholds
    min_oos_sharpe: float = 1.0
    min_oos_trade_count: int = 30
    max_oos_drawdown_pct: float = 20.0
    min_oos_profit_factor: float = 1.2
    min_oos_win_rate: float = 0.4

    # Ranking metric
    rank_by: str = "sharpe_ratio"  # sharpe_ratio, profit_factor, expectancy


@dataclass
class SelectionResult:
    """Result of the selection & elimination process."""

    graduated: List[Hypothesis] = field(default_factory=list)
    eliminated: List[Hypothesis] = field(default_factory=list)
    graveyard_entries: List[dict] = field(default_factory=list)

    @property
    def graduated_count(self) -> int:
        return len(self.graduated)

    @property
    def eliminated_count(self) -> int:
        return len(self.eliminated)


def rank_by_is_fitness(
    hypotheses: List[Hypothesis],
    config: Optional[SelectionConfig] = None,
) -> List[Hypothesis]:
    """Rank hypotheses by IS fitness, filter out weak ones.

    Args:
        hypotheses: Hypotheses with fitness_is populated.
        config: Selection thresholds.

    Returns:
        Top N hypotheses sorted by ranking metric (descending).
    """
    cfg = config or SelectionConfig()

    # Filter: must have IS fitness
    with_fitness = [h for h in hypotheses if h.fitness_is is not None]

    # Apply IS minimum thresholds
    viable = []
    for h in with_fitness:
        f = h.fitness_is
        if f.trade_count < cfg.min_is_trade_count:
            continue
        if f.sharpe_ratio < cfg.min_is_sharpe:
            continue
        viable.append(h)

    # Sort by ranking metric (descending)
    def sort_key(h: Hypothesis) -> float:
        f = h.fitness_is
        return getattr(f, cfg.rank_by, f.sharpe_ratio)

    viable.sort(key=sort_key, reverse=True)

    return viable[:cfg.top_n]


def validate_oos(
    hypothesis: Hypothesis,
    config: Optional[SelectionConfig] = None,
) -> tuple[bool, str]:
    """Validate a hypothesis against OOS thresholds.

    Args:
        hypothesis: Must have fitness_oos populated.
        config: OOS thresholds.

    Returns:
        (passed, reason) — reason is empty string if passed,
        elimination reason if failed.
    """
    cfg = config or SelectionConfig()
    f = hypothesis.fitness_oos

    if f is None:
        return False, "no OOS fitness data"

    if f.trade_count < cfg.min_oos_trade_count:
        return False, f"OOS trade_count={f.trade_count} < {cfg.min_oos_trade_count}"

    if f.sharpe_ratio < cfg.min_oos_sharpe:
        return False, f"OOS Sharpe={f.sharpe_ratio:.2f} < {cfg.min_oos_sharpe}"

    if f.max_drawdown_pct > cfg.max_oos_drawdown_pct:
        return False, f"OOS max_dd={f.max_drawdown_pct:.1f}% > {cfg.max_oos_drawdown_pct}%"

    if f.profit_factor < cfg.min_oos_profit_factor:
        return False, f"OOS PF={f.profit_factor:.2f} < {cfg.min_oos_profit_factor}"

    if f.win_rate < cfg.min_oos_win_rate:
        return False, f"OOS win_rate={f.win_rate:.2f} < {cfg.min_oos_win_rate}"

    return True, ""


def select_and_eliminate(
    hypotheses: List[Hypothesis],
    config: Optional[SelectionConfig] = None,
) -> SelectionResult:
    """Run full selection & elimination pipeline.

    Expects hypotheses to have both fitness_is and fitness_oos populated.

    Pipeline:
    1. Rank by IS fitness → top N
    2. Validate OOS for top N
    3. Survivors → GRADUATED
    4. Failed → ELIMINATED + graveyard

    Args:
        hypotheses: All hypotheses from a generation.
        config: Selection/elimination thresholds.

    Returns:
        SelectionResult with graduated, eliminated, and graveyard entries.
    """
    cfg = config or SelectionConfig()
    result = SelectionResult()

    # Step 1: Rank by IS
    ranked = rank_by_is_fitness(hypotheses, cfg)

    # Step 2: Mark those not in top N as eliminated (IS stage)
    ranked_ids = {h.hypothesis_id for h in ranked}
    for h in hypotheses:
        if h.hypothesis_id not in ranked_ids and h.fitness_is is not None:
            h.status = HypothesisStatus.ELIMINATED
            reason = _is_elimination_reason(h, cfg)
            h.elimination_reason = reason
            result.eliminated.append(h)
            result.graveyard_entries.append(h.to_graveyard_entry())

    # Step 3: OOS validation for top N
    for h in ranked:
        passed, reason = validate_oos(h, cfg)
        if passed:
            h.status = HypothesisStatus.GRADUATED
            result.graduated.append(h)
            logger.info(
                f"GRADUATED: {h.pattern.name} "
                f"(IS Sharpe={h.fitness_is.sharpe_ratio:.2f}, "
                f"OOS Sharpe={h.fitness_oos.sharpe_ratio:.2f})"
            )
        else:
            h.status = HypothesisStatus.ELIMINATED
            h.elimination_reason = reason
            result.eliminated.append(h)
            result.graveyard_entries.append(h.to_graveyard_entry())
            logger.info(f"ELIMINATED: {h.pattern.name} — {reason}")

    return result


def _is_elimination_reason(h: Hypothesis, cfg: SelectionConfig) -> str:
    """Generate elimination reason for IS-stage failures."""
    f = h.fitness_is
    if f is None:
        return "no IS fitness data"
    reasons = []
    if f.trade_count < cfg.min_is_trade_count:
        reasons.append(f"trade_count={f.trade_count}")
    if f.sharpe_ratio < cfg.min_is_sharpe:
        reasons.append(f"Sharpe={f.sharpe_ratio:.2f}")
    if not reasons:
        reasons.append("ranked below top N")
    return "IS filter: " + ", ".join(reasons)
