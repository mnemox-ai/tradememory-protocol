"""Evolution MCP tool functions — pure async, not yet registered on MCP server.

Five tools:
1. fetch_market_data — fetch OHLCV via BinanceDataSource
2. discover_patterns — LLM pattern discovery from market data
3. run_backtest — backtest a pattern dict against OHLCV data
4. evolve_strategy — full evolution loop with trajectory
5. get_evolution_log — list of past evolution runs (in-memory)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional

from tradememory.data.binance import BinanceDataSource
from tradememory.data.models import OHLCVSeries, Timeframe
from tradememory.evolution.backtester import backtest
from tradememory.evolution.engine import EngineConfig, EvolutionEngine
from tradememory.evolution.generator import GenerationConfig, HypothesisGenerator
from tradememory.evolution.llm import LLMClient
from tradememory.evolution.models import (
    CandidatePattern,
    EntryCondition,
    EvolutionConfig,
    EvolutionRun,
    ExitCondition,
)

logger = logging.getLogger(__name__)

# Module-level evolution log (in-memory, not DB — per spec)
_evolution_log: List[dict[str, Any]] = []

# Timeframe string → Timeframe enum mapping
_TIMEFRAME_MAP = {tf.value: tf for tf in Timeframe}


def _resolve_timeframe(tf_str: str) -> Timeframe:
    """Resolve timeframe string to enum, raise ValueError if invalid."""
    tf = _TIMEFRAME_MAP.get(tf_str)
    if tf is None:
        valid = ", ".join(_TIMEFRAME_MAP.keys())
        raise ValueError(f"Invalid timeframe '{tf_str}'. Valid: {valid}")
    return tf


async def fetch_market_data(
    symbol: str,
    timeframe: str = "1h",
    days: int = 90,
    *,
    data_source: Optional[BinanceDataSource] = None,
) -> dict[str, Any]:
    """Fetch OHLCV market data via BinanceDataSource.

    Args:
        symbol: Trading pair (e.g. "BTCUSDT")
        timeframe: Bar timeframe (e.g. "1h", "4h", "1d")
        days: Number of days of history to fetch
        data_source: Optional injected data source (for testing)

    Returns:
        dict with bars_count, start_date, end_date, symbol, timeframe, series
    """
    try:
        tf = _resolve_timeframe(timeframe)
    except ValueError as e:
        return {
            "error": str(e),
            "symbol": symbol,
            "timeframe": timeframe,
            "bars_count": 0,
            "start_date": None,
            "end_date": None,
            "series": None,
        }

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    own_source = data_source is None
    if own_source:
        data_source = BinanceDataSource()

    try:
        series = await data_source.fetch_ohlcv(
            symbol=symbol,
            timeframe=tf,
            start=start,
            end=end,
        )
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars_count": series.count,
            "start_date": series.start.isoformat() if series.start else None,
            "end_date": series.end.isoformat() if series.end else None,
            "series": series,
        }
    except Exception as e:
        logger.error("fetch_market_data failed: %s", e)
        return {
            "error": str(e),
            "symbol": symbol,
            "timeframe": timeframe,
            "bars_count": 0,
            "start_date": None,
            "end_date": None,
            "series": None,
        }
    finally:
        if own_source:
            await data_source.close()


async def discover_patterns(
    symbol: str,
    timeframe: str = "1h",
    count: int = 5,
    temperature: float = 0.7,
    *,
    llm: LLMClient,
    series: Optional[OHLCVSeries] = None,
    data_source: Optional[BinanceDataSource] = None,
    days: int = 90,
) -> dict[str, Any]:
    """Discover trading patterns from market data using LLM.

    Args:
        symbol: Trading pair
        timeframe: Bar timeframe
        count: Number of patterns to generate
        temperature: LLM sampling temperature
        llm: LLM client (required)
        series: Pre-fetched OHLCVSeries (skips fetch if provided)
        data_source: Optional injected data source
        days: Days of history if fetching

    Returns:
        dict with patterns list, tokens_used, count, errors
    """
    # Get data
    if series is None:
        result = await fetch_market_data(
            symbol, timeframe, days, data_source=data_source,
        )
        if result.get("error"):
            return {
                "error": result["error"],
                "patterns": [],
                "tokens_used": 0,
                "count": 0,
            }
        series = result["series"]

    config = GenerationConfig(
        patterns_per_batch=count,
        discovery_temperature=temperature,
    )
    generator = HypothesisGenerator(llm=llm, config=config)

    try:
        gen_result = await generator.generate(series=series, temperature=temperature, count=count)
        patterns = []
        for hyp in gen_result.hypotheses:
            patterns.append(hyp.pattern.model_dump(mode="json"))

        return {
            "patterns": patterns,
            "tokens_used": gen_result.total_tokens,
            "count": len(patterns),
            "errors": gen_result.errors,
        }
    except Exception as e:
        logger.error("discover_patterns failed: %s", e)
        return {
            "error": str(e),
            "patterns": [],
            "tokens_used": 0,
            "count": 0,
        }


def _pattern_from_dict(pattern_dict: dict) -> CandidatePattern:
    """Build CandidatePattern from a dict (handles nested models)."""
    return CandidatePattern.model_validate(pattern_dict)


async def run_backtest(
    pattern_dict: dict[str, Any],
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    days: int = 90,
    *,
    series: Optional[OHLCVSeries] = None,
    data_source: Optional[BinanceDataSource] = None,
) -> dict[str, Any]:
    """Backtest a pattern against OHLCV data.

    Args:
        pattern_dict: CandidatePattern as dict
        symbol: Trading pair
        timeframe: Bar timeframe
        days: Days of history if fetching
        series: Pre-fetched OHLCVSeries (skips fetch if provided)
        data_source: Optional injected data source

    Returns:
        dict with fitness metrics (sharpe_ratio, win_rate, etc.)
    """
    tf_str = timeframe

    # Parse pattern
    try:
        pattern = _pattern_from_dict(pattern_dict)
    except Exception as e:
        logger.error("Invalid pattern_dict: %s", e)
        return {"error": f"Invalid pattern: {e}"}

    # Get data
    if series is None:
        result = await fetch_market_data(
            symbol, tf_str, days, data_source=data_source,
        )
        if result.get("error"):
            return {"error": result["error"]}
        series = result["series"]

    # Run backtest
    try:
        fitness = backtest(series=series, pattern=pattern, timeframe=tf_str)
        return {
            "pattern_id": pattern.pattern_id,
            "pattern_name": pattern.name,
            **fitness.model_dump(),
        }
    except Exception as e:
        logger.error("run_backtest failed: %s", e)
        return {"error": f"Backtest failed: {e}"}


async def evolve_strategy(
    symbol: str,
    timeframe: str = "1h",
    generations: int = 3,
    population_size: int = 10,
    *,
    llm: LLMClient,
    series: Optional[OHLCVSeries] = None,
    data_source: Optional[BinanceDataSource] = None,
    days: int = 90,
) -> dict[str, Any]:
    """Run full evolution loop — generate, backtest, select, eliminate.

    Args:
        symbol: Trading pair (e.g. "BTCUSDT")
        timeframe: Bar timeframe (e.g. "1h", "4h")
        generations: Number of evolution generations
        population_size: Hypotheses per generation
        llm: LLM client (required)
        series: Pre-fetched OHLCVSeries (skips fetch if provided)
        data_source: Optional injected data source
        days: Days of history if fetching

    Returns:
        dict with run_id, per-generation results, graduated list,
        graveyard with elimination reasons, total tokens/backtests.
    """
    # Validate timeframe
    try:
        tf = _resolve_timeframe(timeframe)
    except ValueError as e:
        return {"error": str(e)}

    # Get data
    if series is None:
        result = await fetch_market_data(
            symbol, timeframe, days, data_source=data_source,
        )
        if result.get("error"):
            return {"error": result["error"]}
        series = result["series"]

    # Configure and run engine
    evo_config = EvolutionConfig(
        symbol=symbol,
        timeframe=timeframe,
        generations=generations,
        population_size=population_size,
    )
    engine_config = EngineConfig(evolution=evo_config)
    engine = EvolutionEngine(llm=llm, config=engine_config)

    try:
        run: EvolutionRun = await engine.evolve(series)
    except Exception as e:
        logger.error("evolve_strategy failed: %s", e)
        return {"error": f"Evolution failed: {e}"}

    # Build per-generation summary
    gen_results: list[dict] = []
    for gen_idx in range(generations):
        gen_hyps = [h for h in run.hypotheses if h.generation == gen_idx]
        gen_grad = [h for h in run.graduated if h.generation == gen_idx]
        gen_elim = [h for h in run.graveyard if h.generation == gen_idx]
        gen_results.append({
            "generation": gen_idx,
            "hypotheses_count": len(gen_hyps),
            "graduated_count": len(gen_grad),
            "eliminated_count": len(gen_elim),
        })

    # Build graduated list
    graduated = []
    for h in run.graduated:
        entry = {
            "hypothesis_id": h.hypothesis_id,
            "pattern_name": h.pattern.name,
            "generation": h.generation,
        }
        if h.fitness_is:
            entry["fitness_is"] = h.fitness_is.model_dump()
        if h.fitness_oos:
            entry["fitness_oos"] = h.fitness_oos.model_dump()
        graduated.append(entry)

    # Build graveyard list
    graveyard = []
    for h in run.graveyard:
        entry = {
            "hypothesis_id": h.hypothesis_id,
            "pattern_name": h.pattern.name,
            "generation": h.generation,
            "elimination_reason": h.elimination_reason,
        }
        if h.fitness_is:
            entry["fitness_is"] = h.fitness_is.model_dump()
        if h.fitness_oos:
            entry["fitness_oos"] = h.fitness_oos.model_dump()
        graveyard.append(entry)

    response = {
        "run_id": run.run_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "generations": generations,
        "population_size": population_size,
        "per_generation": gen_results,
        "graduated": graduated,
        "graveyard": graveyard,
        "total_graduated": len(graduated),
        "total_graveyard": len(graveyard),
        "total_tokens": run.total_llm_tokens,
        "total_backtests": run.total_backtests,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }

    # Store in module-level log
    _evolution_log.append(response)

    return response


def get_evolution_log() -> dict[str, Any]:
    """Return list of past evolution runs (in-memory).

    Returns:
        dict with runs list and total_runs count.
    """
    return {
        "runs": list(_evolution_log),
        "total_runs": len(_evolution_log),
    }
