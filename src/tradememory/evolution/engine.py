"""Evolution Orchestrator — full evolution loop.

Pipeline per generation:
1. Generate hypotheses (explore gen 0, mutate+explore gen 1+)
2. Backtest IS for each hypothesis
3. Rank by IS fitness → top N
4. Backtest OOS for top N
5. Select & eliminate → graduated / graveyard
6. Feed graveyard back to generator for next generation

No side effects: returns EvolutionRun, caller decides what to persist.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from tradememory.data.models import OHLCVSeries
from tradememory.evolution.backtester import backtest
from tradememory.evolution.generator import (
    GenerationConfig,
    HypothesisGenerator,
)
from tradememory.evolution.llm import LLMClient
from tradememory.evolution.models import (
    EvolutionConfig,
    EvolutionRun,
    Hypothesis,
    HypothesisStatus,
)
from tradememory.evolution.selector import (
    SelectionConfig,
    rank_by_is_fitness,
    select_and_eliminate,
)

logger = logging.getLogger(__name__)


@dataclass
class EngineConfig:
    """Configuration for the evolution engine."""

    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    selection: SelectionConfig = field(default_factory=SelectionConfig)

    # Mutation settings
    mutations_per_graduated: int = 2
    mutation_temperature: float = 0.8

    # Exploration vs exploitation balance
    explore_ratio: float = 0.6  # fraction of population from exploration (vs mutation)

    # Data quality warning threshold
    min_bars_warn: int = 200


class EvolutionEngine:
    """Orchestrates the full evolution loop.

    Usage:
        engine = EvolutionEngine(llm_client, config)
        run = await engine.evolve(series)
        # run.graduated = strategies that passed IS + OOS
        # run.graveyard = eliminated strategies for learning
    """

    def __init__(
        self,
        llm: LLMClient,
        config: Optional[EngineConfig] = None,
    ):
        self.llm = llm
        self.config = config or EngineConfig()
        self._generator = HypothesisGenerator(
            llm,
            GenerationConfig(
                patterns_per_batch=self.config.evolution.population_size,
                discovery_temperature=self.config.evolution.temperature,
                mutation_temperature=self.config.mutation_temperature,
                mutations_per_parent=self.config.mutations_per_graduated,
                model=self.config.evolution.model,
            ),
        )

    async def evolve(self, series: OHLCVSeries) -> EvolutionRun:
        """Run the full evolution loop.

        Args:
            series: Full OHLCV data. Will be split into IS/OOS.

        Returns:
            EvolutionRun with all results.
        """
        cfg = self.config.evolution
        run = EvolutionRun(config=cfg)

        # Warn if dataset is small
        if len(series.bars) < self.config.min_bars_warn:
            logger.warning(
                f"Only {len(series.bars)} bars provided, "
                f"recommend >= {self.config.min_bars_warn} for meaningful results"
            )

        # Split data into IS / OOS
        is_series, oos_series = self._split_data(series, cfg.is_oos_ratio)
        if not is_series.bars or not oos_series.bars:
            logger.error("Not enough data to split into IS/OOS")
            run.completed_at = datetime.now(timezone.utc)
            return run

        logger.info(
            f"Evolution {run.run_id}: {cfg.generations} generations, "
            f"pop={cfg.population_size}, IS={len(is_series.bars)} bars, "
            f"OOS={len(oos_series.bars)} bars"
        )

        graveyard_entries: List[dict] = []

        for gen in range(cfg.generations):
            logger.info(f"--- Generation {gen} ---")

            # Step 1: Generate hypotheses
            hypotheses = await self._generate_hypotheses(
                is_series, gen, graveyard_entries, run
            )
            if not hypotheses:
                logger.warning(f"Generation {gen}: no hypotheses generated, skipping")
                continue

            # Step 2: Backtest IS
            tf = is_series.timeframe.value
            for h in hypotheses:
                h.generation = gen
                h.status = HypothesisStatus.BACKTESTING
                h.fitness_is = backtest(is_series, h.pattern, timeframe=tf)
                run.total_backtests += 1

            # Step 3: Rank by IS → top N proceed to OOS
            ranked = rank_by_is_fitness(hypotheses, self.config.selection)

            # Step 4: Backtest OOS for ranked hypotheses
            for h in ranked:
                h.status = HypothesisStatus.SURVIVED_IS
                h.fitness_oos = backtest(oos_series, h.pattern, timeframe=tf)
                run.total_backtests += 1

            # Step 5: Select & eliminate
            result = select_and_eliminate(hypotheses, self.config.selection)

            # Collect results
            run.hypotheses.extend(hypotheses)
            run.graduated.extend(result.graduated)
            run.graveyard.extend(result.eliminated)
            graveyard_entries.extend(result.graveyard_entries)

            logger.info(
                f"Generation {gen}: {len(hypotheses)} hypotheses, "
                f"{result.graduated_count} graduated, "
                f"{result.eliminated_count} eliminated"
            )

        # Done
        run.completed_at = datetime.now(timezone.utc)
        self._generator.set_graveyard([])  # clean up

        logger.info(
            f"Evolution {run.run_id} complete: "
            f"{len(run.graduated)} graduated, "
            f"{len(run.graveyard)} eliminated, "
            f"{run.total_backtests} backtests, "
            f"{run.total_llm_tokens} tokens"
        )

        return run

    async def _generate_hypotheses(
        self,
        is_series: OHLCVSeries,
        generation: int,
        graveyard_entries: List[dict],
        run: EvolutionRun,
    ) -> List[Hypothesis]:
        """Generate hypotheses for one generation.

        Gen 0: pure exploration.
        Gen 1+: mix of exploration + mutation of graduated strategies.
        """
        self._generator.set_graveyard(graveyard_entries)
        pop_size = self.config.evolution.population_size
        hypotheses: List[Hypothesis] = []

        if generation == 0 or not run.graduated:
            # Pure exploration
            result = await self._generator.generate(
                is_series,
                temperature=self.config.evolution.temperature,
                count=pop_size,
            )
            run.total_llm_tokens += result.total_tokens
            hypotheses.extend(result.hypotheses)
        else:
            # Mix: explore + mutate graduated
            explore_count = max(1, int(pop_size * self.config.explore_ratio))
            mutate_count = pop_size - explore_count

            # Exploration
            explore_result = await self._generator.generate(
                is_series,
                temperature=self.config.evolution.temperature,
                count=explore_count,
            )
            run.total_llm_tokens += explore_result.total_tokens
            hypotheses.extend(explore_result.hypotheses)

            # Mutation of graduated strategies
            if mutate_count > 0 and run.graduated:
                mutations_per = max(1, mutate_count // len(run.graduated))
                for parent in run.graduated:
                    mutate_result = await self._generator.mutate(
                        parent,
                        temperature=self.config.mutation_temperature,
                        count=mutations_per,
                    )
                    run.total_llm_tokens += mutate_result.total_tokens
                    hypotheses.extend(mutate_result.hypotheses)

                    if len(hypotheses) >= pop_size:
                        break

        # Trim to population size
        return hypotheses[:pop_size]

    @staticmethod
    def _split_data(
        series: OHLCVSeries, is_ratio: float
    ) -> tuple[OHLCVSeries, OHLCVSeries]:
        """Split OHLCVSeries into IS and OOS portions.

        Args:
            series: Full data.
            is_ratio: Fraction for in-sample (e.g. 0.7 = 70% IS, 30% OOS).

        Returns:
            (is_series, oos_series)
        """
        bars = series.bars
        split_idx = int(len(bars) * is_ratio)

        is_series = OHLCVSeries(
            symbol=series.symbol,
            timeframe=series.timeframe,
            bars=bars[:split_idx],
        )
        oos_series = OHLCVSeries(
            symbol=series.symbol,
            timeframe=series.timeframe,
            bars=bars[split_idx:],
        )
        return is_series, oos_series
