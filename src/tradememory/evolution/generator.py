"""Hypothesis Generator — LLM-powered batch hypothesis creation.

Wraps discovery.py into a higher-level API:
- Batch generation with configurable temperature (explore/exploit)
- Creates Hypothesis objects with PENDING status
- Retry / error recovery
- Graveyard-aware (avoids reinventing eliminated strategies)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from src.tradememory.data.models import OHLCVSeries
from src.tradememory.evolution.discovery import (
    discover_patterns,
    mutate_pattern,
)
from src.tradememory.evolution.llm import LLMClient, LLMError
from src.tradememory.evolution.models import (
    CandidatePattern,
    Hypothesis,
    HypothesisStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class GenerationConfig:
    """Configuration for hypothesis generation."""

    # Discovery settings
    patterns_per_batch: int = 5
    discovery_temperature: float = 0.7
    mutation_temperature: float = 0.8
    mutations_per_parent: int = 3

    # Retry settings
    max_retries: int = 2
    min_patterns_per_batch: int = 1  # fail if fewer than this

    # Model override (None = use client default)
    model: Optional[str] = None


@dataclass
class GenerationResult:
    """Result of a generation batch."""

    hypotheses: List[Hypothesis] = field(default_factory=list)
    total_tokens: int = 0
    errors: List[str] = field(default_factory=list)
    retries: int = 0

    @property
    def count(self) -> int:
        return len(self.hypotheses)

    @property
    def success(self) -> bool:
        return self.count > 0


class HypothesisGenerator:
    """Generates trading hypotheses from market data using LLM.

    Usage:
        gen = HypothesisGenerator(llm_client)
        result = await gen.generate(series)
        # result.hypotheses = [Hypothesis(status=PENDING), ...]

        # Or mutate existing winners:
        result = await gen.mutate(parent_hypothesis)
    """

    def __init__(
        self,
        llm: LLMClient,
        config: Optional[GenerationConfig] = None,
    ):
        self.llm = llm
        self.config = config or GenerationConfig()
        self._graveyard: List[dict] = []

    def set_graveyard(self, graveyard: List[dict]) -> None:
        """Set eliminated strategies to avoid reinventing them."""
        self._graveyard = graveyard

    async def generate(
        self,
        series: OHLCVSeries,
        temperature: Optional[float] = None,
        count: Optional[int] = None,
    ) -> GenerationResult:
        """Generate new hypotheses from OHLCV data.

        Args:
            series: Market data to analyze.
            temperature: Override discovery temperature.
            count: Override patterns_per_batch.

        Returns:
            GenerationResult with hypotheses in PENDING status.
        """
        temp = temperature or self.config.discovery_temperature
        batch_size = count or self.config.patterns_per_batch
        result = GenerationResult()

        for attempt in range(1 + self.config.max_retries):
            try:
                patterns, response = await discover_patterns(
                    llm=self.llm,
                    series=series,
                    count=batch_size,
                    graveyard=self._graveyard,
                    temperature=temp,
                    model=self.config.model,
                )
                result.total_tokens += response.input_tokens + response.output_tokens

                if patterns:
                    for p in patterns:
                        h = _create_hypothesis(p)
                        result.hypotheses.append(h)
                    break  # success

                # No patterns parsed — retry with higher temperature
                if attempt < self.config.max_retries:
                    temp = min(temp + 0.1, 1.0)
                    result.retries += 1
                    logger.warning(
                        f"No patterns parsed (attempt {attempt + 1}), "
                        f"retrying with temperature={temp:.1f}"
                    )
                else:
                    result.errors.append(
                        f"No valid patterns after {attempt + 1} attempts"
                    )

            except LLMError as e:
                result.errors.append(str(e))
                if attempt < self.config.max_retries:
                    result.retries += 1
                    logger.warning(
                        f"LLM error (attempt {attempt + 1}): {e}, retrying"
                    )
                else:
                    logger.error(f"LLM error after {attempt + 1} attempts: {e}")
                    break

        if result.count < self.config.min_patterns_per_batch and not result.hypotheses:
            logger.warning(
                f"Generation produced {result.count} hypotheses "
                f"(min={self.config.min_patterns_per_batch})"
            )

        return result

    async def mutate(
        self,
        parent: Hypothesis,
        temperature: Optional[float] = None,
        count: Optional[int] = None,
    ) -> GenerationResult:
        """Generate mutations of an existing hypothesis.

        Args:
            parent: Source hypothesis with fitness data.
            temperature: Override mutation temperature.
            count: Override mutations_per_parent.

        Returns:
            GenerationResult with mutated hypotheses.
        """
        temp = temperature or self.config.mutation_temperature
        n = count or self.config.mutations_per_parent
        result = GenerationResult()

        try:
            patterns, response = await mutate_pattern(
                llm=self.llm,
                hypothesis=parent,
                count=n,
                temperature=temp,
                model=self.config.model,
            )
            result.total_tokens = response.input_tokens + response.output_tokens

            for p in patterns:
                h = _create_hypothesis(p)
                result.hypotheses.append(h)

        except LLMError as e:
            result.errors.append(str(e))
            logger.error(f"Mutation failed for {parent.pattern.name}: {e}")
        except ValueError as e:
            result.errors.append(str(e))
            logger.error(f"Mutation invalid for {parent.pattern.name}: {e}")

        return result

    async def explore(
        self,
        series: OHLCVSeries,
        count: int = 5,
    ) -> GenerationResult:
        """High-temperature discovery for exploration.

        Uses temperature=0.9 for maximum diversity.
        """
        return await self.generate(series, temperature=0.9, count=count)

    async def exploit(
        self,
        series: OHLCVSeries,
        count: int = 5,
    ) -> GenerationResult:
        """Low-temperature discovery for exploitation.

        Uses temperature=0.3 for focused, conservative patterns.
        """
        return await self.generate(series, temperature=0.3, count=count)


def _create_hypothesis(
    pattern: CandidatePattern,
) -> Hypothesis:
    """Create a Hypothesis from a CandidatePattern."""
    return Hypothesis(
        pattern=pattern,
        status=HypothesisStatus.PENDING,
    )
