"""Pattern Discovery — LLM-powered strategy hypothesis generation.

Input: OHLCVSeries + MarketContext series
Output: List[CandidatePattern]

Uses Phase 9 data layer for input, LLM Protocol for generation.
"""

from __future__ import annotations

import json
import logging
from datetime import timezone
from typing import List, Optional, Sequence

from tradememory.data.context_builder import MarketContext, build_context, ContextConfig
from tradememory.data.models import OHLCV, OHLCVSeries
from tradememory.evolution.llm import LLMClient, LLMError, LLMMessage, LLMResponse
from tradememory.evolution.models import (
    CandidatePattern,
    EntryCondition,
    ExitCondition,
    Hypothesis,
    RuleCondition,
    ValidityConditions,
)
from tradememory.evolution.prompts import (
    DISCOVERY_PROMPT,
    MUTATION_PROMPT,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

# Known operators for condition normalization (Haiku format handling)
_KNOWN_OPS = {"eq", "gt", "lt", "gte", "lte", "neq", "between", "in"}


def _normalize_condition(cond: dict) -> Optional[dict]:
    """Normalize a condition dict to {"field", "op", "value"} format.

    Handles two formats:
    - Standard: {"field": "x", "op": "eq", "value": 4}
    - Haiku shorthand: {"field": "x", "eq": 4}

    Returns None if normalization fails (missing field or no recognizable operator).
    """
    if "field" not in cond:
        logger.warning(f"Condition missing 'field' key, skipping: {cond}")
        return None

    # Standard format — already has op + value
    if "op" in cond and "value" in cond:
        return {"field": cond["field"], "op": cond["op"], "value": cond["value"]}

    # Haiku shorthand — operator is a top-level key
    for key in cond:
        if key in _KNOWN_OPS:
            return {"field": cond["field"], "op": key, "value": cond[key]}

    logger.warning(f"Condition has no recognizable operator, skipping: {cond}")
    return None


def compute_hourly_stats(bars: Sequence[OHLCV]) -> str:
    """Compute average range and direction by hour (UTC).

    Returns a formatted string for the LLM prompt.
    """
    hourly: dict[int, list[tuple[float, float]]] = {}  # hour → [(range, body)]

    for bar in bars:
        ts = bar.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hour = ts.hour
        hourly.setdefault(hour, []).append((bar.range, bar.body))

    lines = []
    for hour in sorted(hourly.keys()):
        data = hourly[hour]
        avg_range = sum(r for r, _ in data) / len(data)
        avg_body = sum(b for _, b in data) / len(data)
        direction = "bullish" if avg_body > 0 else "bearish"
        count = len(data)
        lines.append(
            f"  {hour:02d}:00 UTC — avg_range={avg_range:.2f}, "
            f"bias={direction} ({avg_body:+.2f}), n={count}"
        )

    return "\n".join(lines) if lines else "  (no data)"


def format_graveyard(graveyard: List[dict]) -> str:
    """Format graveyard entries for the prompt."""
    if not graveyard:
        return "  (none — this is the first evolution run)"

    lines = []
    for entry in graveyard[:10]:  # limit to avoid prompt bloat
        name = entry.get("pattern_name", "Unknown")
        reason = entry.get("elimination_reason", "unknown")
        lines.append(f"  - {name}: {reason}")

    return "\n".join(lines)


def build_discovery_prompt(
    series: OHLCVSeries,
    context: Optional[MarketContext] = None,
    count: int = 5,
    graveyard: Optional[List[dict]] = None,
) -> str:
    """Build the discovery prompt from data.

    Args:
        series: OHLCV data to analyze.
        context: Current MarketContext (computed if not provided).
        count: Number of patterns to discover.
        graveyard: Previously eliminated strategies.

    Returns:
        Formatted prompt string.
    """
    if not series.bars:
        raise ValueError("Cannot discover patterns from empty series")

    # Compute context if not provided
    if context is None:
        context = build_context(series)

    # Basic stats
    closes = [b.close for b in series.bars]
    ranges = [b.range for b in series.bars]

    return DISCOVERY_PROMPT.format(
        timeframe=series.timeframe.value,
        symbol=series.symbol,
        count=count,
        start_date=series.start.strftime("%Y-%m-%d") if series.start else "?",
        end_date=series.end.strftime("%Y-%m-%d") if series.end else "?",
        bar_count=series.count,
        price_low=min(closes),
        price_high=max(closes),
        avg_range=sum(ranges) / len(ranges),
        atr=context.atr_h1 or 0,
        hourly_stats=compute_hourly_stats(series.bars),
        trend_12h=context.trend_12h_pct or 0,
        trend_24h=context.trend_24h_pct or 0,
        regime=context.regime.value if context.regime else "unknown",
        volatility_regime=context.volatility_regime.value if context.volatility_regime else "unknown",
        graveyard_summary=format_graveyard(graveyard or []),
    )


def parse_patterns_response(response: LLMResponse) -> List[CandidatePattern]:
    """Parse LLM response into CandidatePattern list.

    Handles malformed responses gracefully — skips invalid patterns.
    """
    try:
        raw = response.parse_json()
    except ValueError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        return []

    if not isinstance(raw, list):
        # Sometimes LLM wraps in {"patterns": [...]}
        if isinstance(raw, dict) and "patterns" in raw:
            raw = raw["patterns"]
        else:
            logger.warning(f"Expected list, got {type(raw).__name__}")
            return []

    patterns = []
    for i, item in enumerate(raw):
        try:
            pattern = _parse_single_pattern(item)
            patterns.append(pattern)
        except Exception as e:
            logger.warning(f"Skipping pattern {i}: {e}")
            continue

    return patterns


def _parse_single_pattern(raw: dict) -> CandidatePattern:
    """Parse a single pattern dict into CandidatePattern."""
    # Entry condition
    entry_raw = raw.get("entry_condition", {})
    entry_conditions = []
    for cond in entry_raw.get("conditions", []):
        normalized = _normalize_condition(cond)
        if normalized is None:
            continue
        entry_conditions.append(RuleCondition(
            field=normalized["field"],
            op=normalized["op"],
            value=normalized["value"],
        ))
    entry = EntryCondition(
        direction=entry_raw.get("direction", "long"),
        conditions=entry_conditions,
        description=entry_raw.get("description", ""),
    )

    # Exit condition
    exit_raw = raw.get("exit_condition", {})
    exit_cond = ExitCondition(
        stop_loss_atr=exit_raw.get("stop_loss_atr"),
        take_profit_atr=exit_raw.get("take_profit_atr"),
        max_holding_bars=exit_raw.get("max_holding_bars"),
        trailing_stop_atr=exit_raw.get("trailing_stop_atr"),
    )

    # Validity conditions
    validity_raw = raw.get("validity_conditions", {})
    validity = ValidityConditions(
        regime=validity_raw.get("regime"),
        volatility_regime=validity_raw.get("volatility_regime"),
        session=validity_raw.get("session"),
        min_atr_d1=validity_raw.get("min_atr_d1"),
        max_atr_d1=validity_raw.get("max_atr_d1"),
        min_trend_12h_pct=validity_raw.get("min_trend_12h_pct"),
        max_trend_12h_pct=validity_raw.get("max_trend_12h_pct"),
    )

    return CandidatePattern(
        name=raw.get("name", "Unnamed Pattern"),
        description=raw.get("description", ""),
        entry_condition=entry,
        exit_condition=exit_cond,
        validity_conditions=validity,
        confidence=float(raw.get("confidence", 0.5)),
        sample_count=int(raw.get("sample_count", 0)),
        source="llm_discovery",
    )


async def discover_patterns(
    llm: LLMClient,
    series: OHLCVSeries,
    count: int = 5,
    graveyard: Optional[List[dict]] = None,
    temperature: float = 0.7,
    model: Optional[str] = None,
) -> tuple[List[CandidatePattern], LLMResponse]:
    """Run LLM pattern discovery on OHLCV data.

    Args:
        llm: LLM client (Anthropic, Mock, etc.)
        series: OHLCV data to analyze.
        count: Number of patterns to discover.
        graveyard: Previously eliminated strategies (avoid reinventing).
        temperature: LLM sampling temperature.
        model: LLM model override.

    Returns:
        (patterns, raw_response) tuple.
    """
    prompt = build_discovery_prompt(series, count=count, graveyard=graveyard)

    response = await llm.complete(
        messages=[LLMMessage(role="user", content=prompt)],
        system=SYSTEM_PROMPT,
        temperature=temperature,
        model=model,
        max_tokens=4096,
    )

    patterns = parse_patterns_response(response)
    logger.info(
        f"Discovered {len(patterns)}/{count} patterns for {series.symbol} "
        f"({response.input_tokens + response.output_tokens} tokens)"
    )

    return patterns, response


async def mutate_pattern(
    llm: LLMClient,
    hypothesis: Hypothesis,
    count: int = 3,
    temperature: float = 0.8,
    model: Optional[str] = None,
) -> tuple[List[CandidatePattern], LLMResponse]:
    """Generate mutations of an existing hypothesis.

    Args:
        llm: LLM client.
        hypothesis: Source hypothesis to mutate.
        count: Number of mutations to generate.
        temperature: Higher = more exploration.
        model: LLM model override.

    Returns:
        (mutated_patterns, raw_response) tuple.
    """
    fitness = hypothesis.fitness_is or hypothesis.fitness_oos
    if fitness is None:
        raise ValueError("Cannot mutate hypothesis without fitness data")

    prompt = MUTATION_PROMPT.format(
        pattern_json=hypothesis.pattern.model_dump_json(indent=2),
        sharpe=fitness.sharpe_ratio,
        win_rate=fitness.win_rate,
        profit_factor=fitness.profit_factor,
        trade_count=fitness.trade_count,
        max_dd=fitness.max_drawdown_pct,
        count=count,
    )

    response = await llm.complete(
        messages=[LLMMessage(role="user", content=prompt)],
        system=SYSTEM_PROMPT,
        temperature=temperature,
        model=model,
        max_tokens=4096,
    )

    patterns = parse_patterns_response(response)
    # Mark source as mutation
    for p in patterns:
        p.source = "mutation"

    logger.info(
        f"Generated {len(patterns)}/{count} mutations from {hypothesis.pattern.name}"
    )

    return patterns, response
