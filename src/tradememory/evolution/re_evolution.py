"""Re-Evolution Pipeline — continuous strategy adaptation.

When decay is detected, re-evolve a new strategy on recent data:
1. Detect decay via RegimeDecayDetector
2. Grid search (or EvolutionEngine) on rolling IS window
3. Validate best candidate on OOS window
4. Apply DSR gate (statistical_gates) to filter noise
5. Deploy or go to cash position

This module is designed for the Grid WFO experiment (Exp 4a) and
future live re-evolution. No LLM dependency — grid search only.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from tradememory.data.models import OHLCV, OHLCVSeries
from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    EvolutionRun,
    ExitCondition,
    FitnessMetrics,
    RuleCondition,
)
from tradememory.evolution.statistical_gates import deflated_sharpe_ratio
from tradememory.evolution.strategy_registry import StrategyRegistry

logger = logging.getLogger(__name__)


@dataclass
class GridSearchSpace:
    """Defines the grid search parameter space."""

    hour_utc: List[int] = field(
        default_factory=lambda: list(range(24))
    )
    direction: List[str] = field(
        default_factory=lambda: ["long", "short"]
    )
    trend_12h_pct_threshold: List[float] = field(
        default_factory=lambda: [-0.5, -0.3, 0.0, 0.3, 0.5]
    )
    sl_atr: List[float] = field(
        default_factory=lambda: [0.5, 1.0, 1.5, 2.0]
    )
    tp_atr: List[float] = field(
        default_factory=lambda: [1.0, 1.5, 2.0, 3.0, 4.0]
    )
    max_holding_bars: List[int] = field(
        default_factory=lambda: [4, 6, 8, 12]
    )

    @property
    def total_combinations(self) -> int:
        return (
            len(self.hour_utc)
            * len(self.direction)
            * len(self.trend_12h_pct_threshold)
            * len(self.sl_atr)
            * len(self.tp_atr)
            * len(self.max_holding_bars)
        )


@dataclass
class GridCandidate:
    """A single grid search candidate with its parameters and fitness."""

    params: Dict[str, Any]
    pattern: CandidatePattern
    is_fitness: Optional[FitnessMetrics] = None
    oos_fitness: Optional[FitnessMetrics] = None


@dataclass
class ReEvolutionResult:
    """Result of one re-evolution cycle."""

    best_candidate: Optional[GridCandidate] = None
    num_tested: int = 0
    num_viable: int = 0  # IS Sharpe > 0
    dsr: Optional[float] = None
    dsr_pvalue: Optional[float] = None
    passed_dsr_gate: bool = False
    deployed: bool = False
    reason: str = ""


# --- Grid search helpers ---


def build_grid_pattern(
    hour_utc: int,
    direction: str,
    trend_threshold: float,
    sl_atr: float,
    tp_atr: float,
    max_holding_bars: int,
) -> CandidatePattern:
    """Build a CandidatePattern from grid search parameters."""
    # Direction determines trend filter direction
    if direction == "long":
        trend_op = ConditionOperator.GT
    else:
        trend_op = ConditionOperator.LT

    conditions = [
        RuleCondition(field="hour_utc", op=ConditionOperator.EQ, value=hour_utc),
        RuleCondition(field="trend_12h_pct", op=trend_op, value=trend_threshold),
    ]

    return CandidatePattern(
        pattern_id=f"GRID-H{hour_utc}-{direction[0].upper()}-T{trend_threshold}",
        name=f"Grid H{hour_utc} {direction} trend>{trend_threshold}",
        description=(
            f"{direction.upper()} at {hour_utc}:00 UTC when trend_12h "
            f"{'>' if direction == 'long' else '<'} {trend_threshold}%, "
            f"SL={sl_atr}xATR TP={tp_atr}xATR hold<={max_holding_bars}bars"
        ),
        entry_condition=EntryCondition(
            direction=direction,
            conditions=conditions,
        ),
        exit_condition=ExitCondition(
            stop_loss_atr=sl_atr,
            take_profit_atr=tp_atr,
            max_holding_bars=max_holding_bars,
        ),
        confidence=0.5,
        source="grid_search",
    )


def generate_grid(space: Optional[GridSearchSpace] = None) -> List[GridCandidate]:
    """Generate all grid candidates from the search space."""
    s = space or GridSearchSpace()
    candidates = []
    for hour in s.hour_utc:
        for direction in s.direction:
            for trend_th in s.trend_12h_pct_threshold:
                for sl in s.sl_atr:
                    for tp in s.tp_atr:
                        for hold in s.max_holding_bars:
                            pattern = build_grid_pattern(
                                hour, direction, trend_th, sl, tp, hold
                            )
                            candidates.append(
                                GridCandidate(
                                    params={
                                        "hour_utc": hour,
                                        "direction": direction,
                                        "trend_threshold": trend_th,
                                        "sl_atr": sl,
                                        "tp_atr": tp,
                                        "max_holding_bars": hold,
                                    },
                                    pattern=pattern,
                                )
                            )
    return candidates


# --- Re-Evolution Pipeline ---


BacktestFn = Callable[
    [List[OHLCV], list, list, CandidatePattern, str], FitnessMetrics
]
"""Type for the fast_backtest function signature:
   (bars, contexts, atrs, pattern, timeframe) -> FitnessMetrics
"""


@dataclass
class ReEvolutionConfig:
    """Configuration for the re-evolution pipeline."""

    min_is_trades: int = 10  # minimum trades in IS window
    min_is_sharpe: float = 0.0  # minimum IS Sharpe to be viable
    min_oos_trades: int = 5  # minimum trades in OOS window
    top_n_for_oos: int = 20  # how many IS survivors go to OOS
    dsr_alpha: float = 0.05  # DSR significance level
    timeframe: str = "1h"


class ReEvolutionPipeline:
    """Grid-based re-evolution pipeline.

    Usage:
        pipeline = ReEvolutionPipeline(backtest_fn=fast_backtest)
        result = pipeline.run(
            is_bars=bars_3mo, is_contexts=ctx_3mo, is_atrs=atr_3mo,
            oos_bars=bars_1mo, oos_contexts=ctx_1mo, oos_atrs=atr_1mo,
            registry=registry,
        )
    """

    def __init__(
        self,
        backtest_fn: BacktestFn,
        config: Optional[ReEvolutionConfig] = None,
        grid_space: Optional[GridSearchSpace] = None,
    ):
        self.backtest_fn = backtest_fn
        self.config = config or ReEvolutionConfig()
        self.grid_space = grid_space or GridSearchSpace()

    def run(
        self,
        is_bars: List[OHLCV],
        is_contexts: list,
        is_atrs: list,
        oos_bars: List[OHLCV],
        oos_contexts: list,
        oos_atrs: list,
        registry: Optional[StrategyRegistry] = None,
        version_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReEvolutionResult:
        """Run one re-evolution cycle: grid search IS → top N OOS → DSR gate.

        Args:
            is_bars/contexts/atrs: In-sample data (e.g. 3 months).
            oos_bars/contexts/atrs: Out-of-sample data (e.g. 1 month).
            registry: Optional StrategyRegistry to deploy to.
            version_id: Version ID for registry deployment.
            metadata: Extra metadata for registry.

        Returns:
            ReEvolutionResult with best candidate and gate outcomes.
        """
        cfg = self.config
        result = ReEvolutionResult()

        # Step 1: Generate grid
        candidates = generate_grid(self.grid_space)
        result.num_tested = len(candidates)
        logger.info(f"Grid search: {result.num_tested} candidates")

        # Always accumulate trials in registry (even if DSR fails or no viable candidates).
        # M must grow monotonically — you tested these combinations regardless of outcome.
        if registry is not None:
            registry.cumulative_trials += result.num_tested

        # Step 2: Backtest IS for all candidates
        for c in candidates:
            c.is_fitness = self.backtest_fn(
                is_bars, is_contexts, is_atrs, c.pattern, cfg.timeframe
            )

        # Step 3: Filter by IS viability
        viable = [
            c
            for c in candidates
            if c.is_fitness is not None
            and c.is_fitness.trade_count >= cfg.min_is_trades
            and c.is_fitness.sharpe_ratio > cfg.min_is_sharpe
        ]
        result.num_viable = len(viable)

        if not viable:
            result.reason = "No viable IS candidates"
            logger.warning(result.reason)
            return result

        # Step 4: Rank by IS Sharpe, take top N
        viable.sort(key=lambda c: c.is_fitness.sharpe_ratio, reverse=True)
        top_n = viable[: cfg.top_n_for_oos]

        # Step 5: Backtest OOS for top N
        for c in top_n:
            c.oos_fitness = self.backtest_fn(
                oos_bars, oos_contexts, oos_atrs, c.pattern, cfg.timeframe
            )

        # Step 6: Select best by OOS Sharpe (with min trade filter)
        oos_viable = [
            c
            for c in top_n
            if c.oos_fitness is not None
            and c.oos_fitness.trade_count >= cfg.min_oos_trades
            and c.oos_fitness.sharpe_ratio > 0
        ]

        if not oos_viable:
            result.reason = "No OOS-viable candidates"
            logger.warning(result.reason)
            return result

        best = max(oos_viable, key=lambda c: c.oos_fitness.sharpe_ratio)
        result.best_candidate = best

        # Step 7: DSR gate
        cumulative_trials = result.num_tested
        if registry is not None:
            cumulative_trials += registry.cumulative_trials

        dsr, p_value = deflated_sharpe_ratio(
            observed_sr=best.oos_fitness.sharpe_ratio,
            num_trials=max(cumulative_trials, 1),
            num_obs=best.oos_fitness.trade_count,
        )
        result.dsr = dsr
        result.dsr_pvalue = p_value
        result.passed_dsr_gate = dsr > 0

        if not result.passed_dsr_gate:
            result.reason = f"DSR gate failed: DSR={dsr:.4f}, p={p_value:.4f}"
            logger.info(result.reason)
            return result

        # Step 8: Deploy to registry if provided
        # Note: num_trials=0 here because cumulative_trials was already
        # incremented in Step 1 (before any early returns).
        if registry is not None and version_id is not None:
            registry.deploy(
                version_id=version_id,
                pattern=best.pattern.model_dump(),
                fitness=best.oos_fitness.model_dump(),
                reason=f"Grid re-evolution, DSR={dsr:.4f}",
                num_trials=0,
                dsr=dsr,
                metadata=metadata or {},
            )
            result.deployed = True

        result.reason = (
            f"Deployed {version_id}: OOS Sharpe={best.oos_fitness.sharpe_ratio:.4f}, "
            f"DSR={dsr:.4f}, p={p_value:.4f}"
            if result.deployed
            else f"DSR gate passed (DSR={dsr:.4f}) but no registry/version_id"
        )
        logger.info(result.reason)
        return result


# --- LLM-based Re-Evolution Pipeline ---


@dataclass
class LLMReEvolutionResult:
    """Result of one LLM re-evolution cycle."""

    evolution_run: Optional[EvolutionRun] = None
    best_pattern: Optional[CandidatePattern] = None
    oos_fitness: Optional[FitnessMetrics] = None
    num_hypotheses: int = 0  # M for DSR
    num_graduated: int = 0
    total_backtests: int = 0
    total_llm_tokens: int = 0
    dsr: Optional[float] = None
    dsr_pvalue: Optional[float] = None
    passed_dsr_gate: bool = False
    deployed: bool = False
    reason: str = ""
    # Structural novelty tracking
    all_fields_used: List[str] = field(default_factory=list)
    novel_fields: List[str] = field(default_factory=list)


GRID_ONLY_FIELDS = {"hour_utc", "trend_12h_pct"}


class LLMReEvolutionPipeline:
    """LLM-based re-evolution pipeline for Exp 4b.

    Uses EvolutionEngine for IS hypothesis generation/selection,
    then backtests the best graduated strategy on external OOS data.

    Usage:
        from tradememory.evolution.engine import EngineConfig, EvolutionEngine
        from tradememory.evolution.llm import AnthropicClient

        llm = AnthropicClient()
        engine_config = EngineConfig(...)
        pipeline = LLMReEvolutionPipeline(llm, engine_config, backtest_fn=fast_backtest)
        result = await pipeline.run(is_series, oos_bars, oos_contexts, oos_atrs, registry)
    """

    def __init__(
        self,
        llm: Any,  # LLMClient protocol
        engine_config: Any,  # EngineConfig
        backtest_fn: BacktestFn,
        min_oos_trades: int = 3,
        dsr_alpha: float = 0.05,
        timeframe: str = "1h",
    ):
        self.llm = llm
        self.engine_config = engine_config
        self.backtest_fn = backtest_fn
        self.min_oos_trades = min_oos_trades
        self.dsr_alpha = dsr_alpha
        self.timeframe = timeframe

    async def run(
        self,
        is_series: OHLCVSeries,
        oos_bars: List[OHLCV],
        oos_contexts: list,
        oos_atrs: list,
        registry: Optional[StrategyRegistry] = None,
        version_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LLMReEvolutionResult:
        """Run one LLM re-evolution cycle.

        Args:
            is_series: In-sample OHLCVSeries (engine splits internally for IS/OOS).
            oos_bars/contexts/atrs: External OOS data for deployment validation.
            registry: Optional StrategyRegistry for M tracking and deployment.
            version_id: Version ID for registry deployment.
            metadata: Extra metadata.

        Returns:
            LLMReEvolutionResult with best candidate and gate outcomes.
        """
        from tradememory.evolution.engine import EvolutionEngine

        result = LLMReEvolutionResult()

        # Step 1: Run EvolutionEngine on IS data
        engine = EvolutionEngine(self.llm, self.engine_config)
        run = await engine.evolve(is_series)
        result.evolution_run = run
        result.num_hypotheses = len(run.hypotheses)
        result.num_graduated = len(run.graduated)
        result.total_backtests = run.total_backtests
        result.total_llm_tokens = run.total_llm_tokens

        # Always accumulate M in registry
        if registry is not None:
            registry.cumulative_trials += result.num_hypotheses

        # Track structural novelty
        all_fields = set()
        for h in run.hypotheses:
            for cond in h.pattern.entry_condition.conditions:
                all_fields.add(cond.field)
        result.all_fields_used = sorted(all_fields)
        result.novel_fields = sorted(all_fields - GRID_ONLY_FIELDS)

        logger.info(
            f"LLM evolution: {result.num_hypotheses} hypotheses, "
            f"{result.num_graduated} graduated, "
            f"{run.total_llm_tokens} tokens"
        )

        # Step 2: If no graduated strategies, return (cash position)
        if not run.graduated:
            result.reason = "No graduated strategies from LLM evolution"
            logger.warning(result.reason)
            return result

        # Step 3: Backtest best graduated strategy on external OOS
        # Pick best by IS Sharpe among graduated
        best_graduated = max(
            run.graduated,
            key=lambda h: h.fitness_is.sharpe_ratio if h.fitness_is else 0,
        )
        result.best_pattern = best_graduated.pattern

        oos_fitness = self.backtest_fn(
            oos_bars, oos_contexts, oos_atrs,
            best_graduated.pattern, self.timeframe,
        )
        result.oos_fitness = oos_fitness
        result.total_backtests += 1

        if oos_fitness.trade_count < self.min_oos_trades or oos_fitness.sharpe_ratio <= 0:
            result.reason = (
                f"OOS not viable: Sharpe={oos_fitness.sharpe_ratio:.4f}, "
                f"trades={oos_fitness.trade_count}"
            )
            logger.info(result.reason)
            return result

        # Step 4: DSR gate
        cumulative_trials = result.num_hypotheses
        if registry is not None:
            cumulative_trials = registry.cumulative_trials

        dsr, p_value = deflated_sharpe_ratio(
            observed_sr=oos_fitness.sharpe_ratio,
            num_trials=max(cumulative_trials, 1),
            num_obs=oos_fitness.trade_count,
        )
        result.dsr = dsr
        result.dsr_pvalue = p_value
        result.passed_dsr_gate = dsr > 0

        if not result.passed_dsr_gate:
            result.reason = f"DSR gate failed: DSR={dsr:.4f}, p={p_value:.4f}"
            logger.info(result.reason)
            return result

        # Step 5: Deploy if registry provided
        if registry is not None and version_id is not None:
            registry.deploy(
                version_id=version_id,
                pattern=best_graduated.pattern.model_dump(),
                fitness=oos_fitness.model_dump(),
                reason=f"LLM re-evolution, DSR={dsr:.4f}",
                num_trials=0,  # already accumulated in Step 1
                dsr=dsr,
                metadata=metadata or {},
            )
            result.deployed = True

        result.reason = (
            f"Deployed {version_id}: OOS Sharpe={oos_fitness.sharpe_ratio:.4f}, "
            f"DSR={dsr:.4f}, p={p_value:.4f}"
            if result.deployed
            else f"DSR gate passed (DSR={dsr:.4f}) but no registry/version_id"
        )
        logger.info(result.reason)
        return result
