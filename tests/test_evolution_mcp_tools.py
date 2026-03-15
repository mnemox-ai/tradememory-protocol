"""Tests for evolution MCP tool functions.

Uses MockLLMClient and synthetic OHLCV data — no real API calls.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.llm import MockLLMClient
from tradememory.evolution.mcp_tools import (
    fetch_market_data,
    discover_patterns,
    run_backtest,
    evolve_strategy,
    get_evolution_log,
    _resolve_timeframe,
    _pattern_from_dict,
    _evolution_log,
)


# --- Helpers ---


def make_bar(idx: int, base_price: float = 100.0) -> OHLCV:
    drift = idx * 0.05
    noise = (idx % 7 - 3) * 0.3
    price = base_price + drift + noise
    return OHLCV(
        timestamp=datetime(2025, 1, 1, idx % 24, tzinfo=timezone.utc),
        open=price,
        high=price + 1.5,
        low=price - 1.5,
        close=price + 0.2,
        volume=1000.0 + idx * 10,
    )


def make_series(n_bars: int = 200) -> OHLCVSeries:
    return OHLCVSeries(
        symbol="BTCUSDT",
        timeframe=Timeframe.H1,
        bars=[make_bar(i) for i in range(n_bars)],
        source="test",
    )


def make_pattern_dict(name: str = "TestPattern", hour: int = 10) -> dict:
    return {
        "name": name,
        "description": f"Buy at hour {hour}",
        "entry_condition": {
            "direction": "long",
            "conditions": [
                {"field": "hour_utc", "op": "eq", "value": hour}
            ],
        },
        "exit_condition": {
            "stop_loss_atr": 1.5,
            "take_profit_atr": 3.0,
            "max_holding_bars": 24,
        },
        "confidence": 0.7,
    }


VALID_LLM_RESPONSE = json.dumps({
    "patterns": [
        {
            "name": "LLM Pattern",
            "description": "Discovered pattern",
            "entry_condition": {
                "direction": "long",
                "conditions": [
                    {"field": "hour_utc", "op": "eq", "value": 10}
                ],
            },
            "exit_condition": {
                "stop_loss_atr": 1.5,
                "take_profit_atr": 3.0,
                "max_holding_bars": 24,
            },
            "confidence": 0.7,
        }
    ]
})


# --- _resolve_timeframe ---


class TestResolveTimeframe:
    def test_valid_timeframes(self):
        assert _resolve_timeframe("1h") == Timeframe.H1
        assert _resolve_timeframe("1d") == Timeframe.D1
        assert _resolve_timeframe("5m") == Timeframe.M5

    def test_invalid_timeframe(self):
        with pytest.raises(ValueError, match="Invalid timeframe"):
            _resolve_timeframe("2h")


# --- _pattern_from_dict ---


class TestPatternFromDict:
    def test_valid_dict(self):
        p = _pattern_from_dict(make_pattern_dict())
        assert p.name == "TestPattern"
        assert p.entry_condition.direction == "long"
        assert p.exit_condition.stop_loss_atr == 1.5

    def test_invalid_dict(self):
        with pytest.raises(Exception):
            _pattern_from_dict({"invalid": "data"})


# --- fetch_market_data ---


class TestFetchMarketData:
    @pytest.mark.asyncio
    async def test_with_injected_source(self):
        series = make_series(100)
        source = AsyncMock()
        source.fetch_ohlcv = AsyncMock(return_value=series)
        source.close = AsyncMock()

        result = await fetch_market_data(
            "BTCUSDT", "1h", 30, data_source=source,
        )

        assert result["bars_count"] == 100
        assert result["symbol"] == "BTCUSDT"
        assert result["timeframe"] == "1h"
        assert result["series"] is series
        assert result["start_date"] is not None
        assert result["end_date"] is not None
        # injected source — close NOT called by function
        source.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_timeframe(self):
        result = await fetch_market_data("BTCUSDT", "invalid", 30)
        assert "error" in result
        assert result["bars_count"] == 0

    @pytest.mark.asyncio
    async def test_source_error(self):
        source = AsyncMock()
        source.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("API down"))
        source.close = AsyncMock()

        result = await fetch_market_data(
            "BTCUSDT", "1h", 30, data_source=source,
        )

        assert "error" in result
        assert "API down" in result["error"]
        assert result["bars_count"] == 0


# --- discover_patterns ---


class TestDiscoverPatterns:
    @pytest.mark.asyncio
    async def test_with_series(self):
        llm = MockLLMClient(responses=[VALID_LLM_RESPONSE])
        series = make_series(200)

        result = await discover_patterns(
            "BTCUSDT", "1h", count=1, temperature=0.7,
            llm=llm, series=series,
        )

        assert result["count"] >= 1
        assert len(result["patterns"]) >= 1
        assert result["patterns"][0]["name"] == "LLM Pattern"
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_tokens_tracked(self):
        llm = MockLLMClient(responses=[VALID_LLM_RESPONSE])
        series = make_series(200)

        result = await discover_patterns(
            "BTCUSDT", "1h", count=1, temperature=0.5,
            llm=llm, series=series,
        )

        assert "tokens_used" in result
        assert isinstance(result["tokens_used"], int)

    @pytest.mark.asyncio
    async def test_fetch_error_propagated(self):
        llm = MockLLMClient(responses=[VALID_LLM_RESPONSE])
        source = AsyncMock()
        source.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("Binance down"))
        source.close = AsyncMock()

        result = await discover_patterns(
            "BTCUSDT", "1h", count=1, temperature=0.7,
            llm=llm, data_source=source,
        )

        assert "error" in result
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_llm_error_handled(self):
        llm = MockLLMClient()
        llm.should_error = True
        series = make_series(200)

        result = await discover_patterns(
            "BTCUSDT", "1h", count=1, temperature=0.7,
            llm=llm, series=series,
        )

        # Generator handles LLM errors internally — returns empty or error
        assert result["count"] == 0 or "error" in result


# --- run_backtest ---


class TestRunBacktest:
    @pytest.mark.asyncio
    async def test_basic_backtest(self):
        series = make_series(200)
        pattern = make_pattern_dict()

        result = await run_backtest(
            pattern, "BTCUSDT", "1h", series=series,
        )

        assert "error" not in result
        assert "sharpe_ratio" in result
        assert "win_rate" in result
        assert "trade_count" in result
        assert "total_pnl" in result
        assert "max_drawdown_pct" in result
        assert "pattern_name" in result
        assert result["pattern_name"] == "TestPattern"

    @pytest.mark.asyncio
    async def test_invalid_pattern(self):
        result = await run_backtest(
            {"not": "a pattern"}, "BTCUSDT", "1h", series=make_series(50),
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_different_timeframes(self):
        series = make_series(200)
        pattern = make_pattern_dict()

        for tf in ["1h", "4h", "1d"]:
            result = await run_backtest(
                pattern, "BTCUSDT", tf, series=series,
            )
            assert "error" not in result
            assert "sharpe_ratio" in result

    @pytest.mark.asyncio
    async def test_fetch_error(self):
        source = AsyncMock()
        source.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("offline"))
        source.close = AsyncMock()

        result = await run_backtest(
            make_pattern_dict(), "BTCUSDT", "1h",
            data_source=source,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_pattern_id_preserved(self):
        series = make_series(200)
        pattern = make_pattern_dict()
        pattern["pattern_id"] = "PAT-CUSTOM"

        result = await run_backtest(pattern, "BTCUSDT", "1h", series=series)

        assert result.get("pattern_id") == "PAT-CUSTOM"


# --- evolve_strategy ---


def _llm_responses(n: int) -> list[str]:
    """Generate n LLM responses, each with one pattern."""
    responses = []
    for i in range(n):
        responses.append(json.dumps({
            "patterns": [
                {
                    "name": f"Pattern_{i}",
                    "description": f"Test pattern {i}",
                    "entry_condition": {
                        "direction": "long",
                        "conditions": [
                            {"field": "hour_utc", "op": "eq", "value": 10 + (i % 12)}
                        ],
                    },
                    "exit_condition": {
                        "stop_loss_atr": 1.5,
                        "take_profit_atr": 3.0,
                        "max_holding_bars": 24,
                    },
                    "confidence": 0.7,
                }
            ]
        }))
    return responses


class TestEvolveStrategy:
    @pytest.fixture(autouse=True)
    def clear_log(self):
        """Clear the module-level evolution log before each test."""
        _evolution_log.clear()
        yield
        _evolution_log.clear()

    @pytest.mark.asyncio
    async def test_basic_evolution(self):
        """evolve_strategy returns correct top-level keys."""
        # Enough responses for 2 gens × 1 LLM call each
        llm = MockLLMClient(responses=_llm_responses(10))
        series = make_series(300)

        result = await evolve_strategy(
            "BTCUSDT", "1h", generations=2, population_size=3,
            llm=llm, series=series,
        )

        assert "error" not in result
        assert "run_id" in result
        assert result["run_id"].startswith("EVO-")
        assert result["symbol"] == "BTCUSDT"
        assert result["timeframe"] == "1h"
        assert result["generations"] == 2
        assert result["population_size"] == 3
        assert "per_generation" in result
        assert "graduated" in result
        assert "graveyard" in result
        assert "total_tokens" in result
        assert "total_backtests" in result
        assert result["total_backtests"] > 0
        assert result["started_at"] is not None
        assert result["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_response_has_graveyard(self):
        """Response must include graveyard with elimination reasons."""
        llm = MockLLMClient(responses=_llm_responses(10))
        series = make_series(300)

        result = await evolve_strategy(
            "BTCUSDT", "1h", generations=1, population_size=3,
            llm=llm, series=series,
        )

        assert "graveyard" in result
        assert isinstance(result["graveyard"], list)
        # With strict OOS thresholds, most patterns end up in graveyard
        total = result["total_graduated"] + result["total_graveyard"]
        assert total > 0, "Should have at least one graduated or eliminated"

    @pytest.mark.asyncio
    async def test_graveyard_has_elimination_reason(self):
        """Each graveyard entry must have elimination_reason."""
        llm = MockLLMClient(responses=_llm_responses(10))
        series = make_series(300)

        result = await evolve_strategy(
            "BTCUSDT", "1h", generations=1, population_size=5,
            llm=llm, series=series,
        )

        for entry in result["graveyard"]:
            assert "elimination_reason" in entry
            assert "hypothesis_id" in entry
            assert "pattern_name" in entry
            assert "generation" in entry

    @pytest.mark.asyncio
    async def test_graduated_has_fitness(self):
        """Each graduated entry must have fitness_is (fitness_oos may be None for edge cases)."""
        llm = MockLLMClient(responses=_llm_responses(10))
        series = make_series(300)

        result = await evolve_strategy(
            "BTCUSDT", "1h", generations=1, population_size=5,
            llm=llm, series=series,
        )

        for entry in result["graduated"]:
            assert "hypothesis_id" in entry
            assert "pattern_name" in entry
            assert "fitness_is" in entry

    @pytest.mark.asyncio
    async def test_per_generation_results(self):
        """per_generation list has one entry per generation."""
        llm = MockLLMClient(responses=_llm_responses(10))
        series = make_series(300)

        result = await evolve_strategy(
            "BTCUSDT", "1h", generations=3, population_size=2,
            llm=llm, series=series,
        )

        assert len(result["per_generation"]) == 3
        for gen in result["per_generation"]:
            assert "generation" in gen
            assert "hypotheses_count" in gen
            assert "graduated_count" in gen
            assert "eliminated_count" in gen

    @pytest.mark.asyncio
    async def test_invalid_timeframe(self):
        """Invalid timeframe returns error."""
        llm = MockLLMClient(responses=[])
        result = await evolve_strategy(
            "BTCUSDT", "invalid", generations=1, population_size=2,
            llm=llm, series=make_series(100),
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_stored_in_log(self):
        """evolve_strategy stores result in _evolution_log."""
        llm = MockLLMClient(responses=_llm_responses(10))
        series = make_series(300)

        assert len(_evolution_log) == 0
        await evolve_strategy(
            "BTCUSDT", "1h", generations=1, population_size=2,
            llm=llm, series=series,
        )
        assert len(_evolution_log) == 1
        assert _evolution_log[0]["run_id"].startswith("EVO-")

    @pytest.mark.asyncio
    async def test_survivors_in_response(self):
        """Response has both graduated (survivors) and graveyard."""
        llm = MockLLMClient(responses=_llm_responses(10))
        series = make_series(300)

        result = await evolve_strategy(
            "BTCUSDT", "1h", generations=1, population_size=5,
            llm=llm, series=series,
        )

        assert "graduated" in result
        assert "graveyard" in result
        assert isinstance(result["graduated"], list)
        assert isinstance(result["graveyard"], list)
        assert "total_graduated" in result
        assert "total_graveyard" in result


# --- get_evolution_log ---


class TestGetEvolutionLog:
    @pytest.fixture(autouse=True)
    def clear_log(self):
        _evolution_log.clear()
        yield
        _evolution_log.clear()

    def test_empty_log(self):
        result = get_evolution_log()
        assert result["runs"] == []
        assert result["total_runs"] == 0

    @pytest.mark.asyncio
    async def test_log_after_runs(self):
        """Log accumulates across multiple evolve_strategy calls."""
        llm = MockLLMClient(responses=_llm_responses(20))
        series = make_series(300)

        await evolve_strategy(
            "BTCUSDT", "1h", generations=1, population_size=2,
            llm=llm, series=series,
        )
        llm2 = MockLLMClient(responses=_llm_responses(20))
        await evolve_strategy(
            "ETHUSDT", "4h", generations=1, population_size=2,
            llm=llm2, series=series,
        )

        result = get_evolution_log()
        assert result["total_runs"] == 2
        assert len(result["runs"]) == 2
        assert result["runs"][0]["symbol"] == "BTCUSDT"
        assert result["runs"][1]["symbol"] == "ETHUSDT"
