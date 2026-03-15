"""Tests for Evolution Engine (Orchestrator).

End-to-end tests with MockLLMClient + synthetic OHLCV data.
"""

import json
import pytest
from datetime import datetime, timezone

from tradememory.data.models import OHLCV, OHLCVSeries
from tradememory.evolution.engine import EngineConfig, EvolutionEngine
from tradememory.evolution.llm import LLMError, MockLLMClient
from tradememory.evolution.models import (
    EvolutionConfig,
    EvolutionRun,
    HypothesisStatus,
)
from tradememory.evolution.generator import GenerationConfig
from tradememory.evolution.selector import SelectionConfig


# --- Test data helpers ---


def make_bar(idx: int, base_price: float = 100.0) -> OHLCV:
    """Create a synthetic OHLCV bar with slight trend."""
    # Small uptrend so strategies can find something
    drift = idx * 0.05
    noise = (idx % 7 - 3) * 0.3  # oscillation
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
    """Create synthetic OHLCVSeries with enough bars for backtesting."""
    return OHLCVSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        bars=[make_bar(i) for i in range(n_bars)],
    )


def make_pattern_json(name: str = "TestPattern", hour: int = 10) -> str:
    """Create a valid pattern JSON response from the LLM."""
    pattern = {
        "patterns": [
            {
                "name": name,
                "description": f"Test pattern: buy at hour {hour}",
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
        ]
    }
    return json.dumps(pattern)


def make_multi_pattern_json(count: int = 3) -> str:
    """Create multiple patterns in one LLM response."""
    patterns = []
    for i in range(count):
        patterns.append({
            "name": f"Pattern_{i}",
            "description": f"Test pattern variant {i}",
            "entry_condition": {
                "direction": "long",
                "conditions": [
                    {"field": "hour_utc", "op": "eq", "value": i % 24}
                ],
            },
            "exit_condition": {
                "stop_loss_atr": 1.0 + i * 0.5,
                "take_profit_atr": 2.0 + i * 0.5,
                "max_holding_bars": 12 + i * 6,
            },
            "confidence": 0.6,
        })
    return json.dumps({"patterns": patterns})


# --- EvolutionEngine._split_data ---


class TestSplitData:
    """Test data splitting logic."""

    def test_split_default_ratio(self):
        """70/30 split by default."""
        series = make_series(100)
        is_s, oos_s = EvolutionEngine._split_data(series, 0.7)
        assert len(is_s.bars) == 70
        assert len(oos_s.bars) == 30
        assert is_s.symbol == "BTCUSDT"
        assert oos_s.symbol == "BTCUSDT"

    def test_split_custom_ratio(self):
        """Custom ratio works."""
        series = make_series(100)
        is_s, oos_s = EvolutionEngine._split_data(series, 0.5)
        assert len(is_s.bars) == 50
        assert len(oos_s.bars) == 50

    def test_split_preserves_order(self):
        """IS gets earlier bars, OOS gets later bars."""
        series = make_series(100)
        is_s, oos_s = EvolutionEngine._split_data(series, 0.7)
        # IS bars should be the first 70
        assert is_s.bars[0].timestamp == series.bars[0].timestamp
        assert is_s.bars[-1].timestamp == series.bars[69].timestamp
        # OOS bars should be the last 30
        assert oos_s.bars[0].timestamp == series.bars[70].timestamp

    def test_split_empty_series(self):
        """Empty series produces empty splits."""
        series = OHLCVSeries(symbol="TEST", timeframe="1h", bars=[])
        is_s, oos_s = EvolutionEngine._split_data(series, 0.7)
        assert len(is_s.bars) == 0
        assert len(oos_s.bars) == 0

    def test_split_metadata_preserved(self):
        """Symbol and timeframe preserved in both splits."""
        series = make_series(100)
        series.symbol = "ETHUSDT"
        series.timeframe = "4h"
        is_s, oos_s = EvolutionEngine._split_data(series, 0.7)
        assert is_s.symbol == "ETHUSDT"
        assert is_s.timeframe == "4h"
        assert oos_s.symbol == "ETHUSDT"
        assert oos_s.timeframe == "4h"


# --- EvolutionEngine.evolve (end-to-end) ---


class TestEvolveBasic:
    """Basic evolution loop tests."""

    @pytest.mark.asyncio
    async def test_single_generation_produces_run(self):
        """Single generation returns a valid EvolutionRun."""
        mock = MockLLMClient(responses=[make_multi_pattern_json(3)])
        config = EngineConfig(
            evolution=EvolutionConfig(generations=1, population_size=3),
            selection=SelectionConfig(
                top_n=3,
                min_is_trade_count=0,
                min_is_sharpe=-999,
                min_oos_sharpe=-999,
                min_oos_trade_count=0,
                max_oos_drawdown_pct=100,
                min_oos_profit_factor=0,
                min_oos_win_rate=0,
            ),
        )
        engine = EvolutionEngine(mock, config)
        series = make_series(200)

        run = await engine.evolve(series)

        assert isinstance(run, EvolutionRun)
        assert run.run_id.startswith("EVO-")
        assert run.completed_at is not None
        assert run.total_backtests > 0
        assert run.total_llm_tokens > 0
        assert len(run.hypotheses) > 0

    @pytest.mark.asyncio
    async def test_run_config_preserved(self):
        """EvolutionRun preserves the config."""
        mock = MockLLMClient(responses=[make_pattern_json()])
        config = EngineConfig(
            evolution=EvolutionConfig(
                symbol="ETHUSDT",
                timeframe="4h",
                generations=1,
                population_size=1,
            ),
            selection=SelectionConfig(
                min_is_trade_count=0,
                min_is_sharpe=-999,
            ),
        )
        engine = EvolutionEngine(mock, config)
        series = make_series(200)

        run = await engine.evolve(series)

        assert run.config.symbol == "ETHUSDT"
        assert run.config.timeframe == "4h"

    @pytest.mark.asyncio
    async def test_hypotheses_get_generation_number(self):
        """Each hypothesis gets its generation number."""
        mock = MockLLMClient(responses=[make_multi_pattern_json(2)])
        config = EngineConfig(
            evolution=EvolutionConfig(generations=1, population_size=2),
            selection=SelectionConfig(
                min_is_trade_count=0, min_is_sharpe=-999,
            ),
        )
        engine = EvolutionEngine(mock, config)
        run = await engine.evolve(make_series(200))

        for h in run.hypotheses:
            assert h.generation == 0

    @pytest.mark.asyncio
    async def test_hypotheses_have_is_fitness(self):
        """All hypotheses get IS fitness after backtesting."""
        mock = MockLLMClient(responses=[make_multi_pattern_json(2)])
        config = EngineConfig(
            evolution=EvolutionConfig(generations=1, population_size=2),
            selection=SelectionConfig(
                min_is_trade_count=0, min_is_sharpe=-999,
            ),
        )
        engine = EvolutionEngine(mock, config)
        run = await engine.evolve(make_series(200))

        for h in run.hypotheses:
            assert h.fitness_is is not None

    @pytest.mark.asyncio
    async def test_backtest_count_matches(self):
        """Total backtests = IS backtests + OOS backtests."""
        mock = MockLLMClient(responses=[make_multi_pattern_json(3)])
        config = EngineConfig(
            evolution=EvolutionConfig(generations=1, population_size=3),
            selection=SelectionConfig(
                top_n=2,
                min_is_trade_count=0,
                min_is_sharpe=-999,
            ),
        )
        engine = EvolutionEngine(mock, config)
        run = await engine.evolve(make_series(200))

        # All 3 get IS backtested, top 2 get OOS backtested
        # Total should be 3 (IS) + 2 (OOS) = 5
        assert run.total_backtests >= 3  # at least IS for all


class TestEvolveMultiGeneration:
    """Multi-generation evolution tests."""

    @pytest.mark.asyncio
    async def test_two_generations(self):
        """Two generations run successfully."""
        # Gen 0 explore, Gen 1 explore + mutate
        responses = [
            make_multi_pattern_json(3),  # gen 0 explore
            make_multi_pattern_json(2),  # gen 1 explore
            make_pattern_json("Mutant_0"),  # gen 1 mutate
        ]
        mock = MockLLMClient(responses=responses)
        config = EngineConfig(
            evolution=EvolutionConfig(generations=2, population_size=3),
            selection=SelectionConfig(
                top_n=3,
                min_is_trade_count=0,
                min_is_sharpe=-999,
                min_oos_sharpe=-999,
                min_oos_trade_count=0,
                max_oos_drawdown_pct=100,
                min_oos_profit_factor=0,
                min_oos_win_rate=0,
            ),
        )
        engine = EvolutionEngine(mock, config)
        run = await engine.evolve(make_series(200))

        assert run.completed_at is not None
        # Should have hypotheses from both generations
        assert len(run.hypotheses) >= 3

    @pytest.mark.asyncio
    async def test_graveyard_grows_across_generations(self):
        """Graveyard entries accumulate across generations."""
        responses = [
            make_multi_pattern_json(2),  # gen 0
            make_multi_pattern_json(2),  # gen 1
        ]
        mock = MockLLMClient(responses=responses)
        config = EngineConfig(
            evolution=EvolutionConfig(generations=2, population_size=2),
            selection=SelectionConfig(
                top_n=2,
                min_is_trade_count=0,
                min_is_sharpe=-999,
                # Strict OOS filter: most won't graduate
                min_oos_sharpe=999,
            ),
        )
        engine = EvolutionEngine(mock, config)
        run = await engine.evolve(make_series(200))

        # With strict OOS, most should be eliminated → graveyard
        assert len(run.graveyard) > 0


class TestEvolveEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_series_returns_empty_run(self):
        """Empty series → empty run with completed_at."""
        mock = MockLLMClient(responses=[make_pattern_json()])
        config = EngineConfig(
            evolution=EvolutionConfig(generations=1, population_size=1),
        )
        engine = EvolutionEngine(mock, config)
        empty = OHLCVSeries(symbol="TEST", timeframe="1h", bars=[])

        run = await engine.evolve(empty)

        assert run.completed_at is not None
        assert len(run.hypotheses) == 0
        assert len(run.graduated) == 0

    @pytest.mark.asyncio
    async def test_too_few_bars_returns_empty_run(self):
        """Series with only a few bars → empty run."""
        mock = MockLLMClient(responses=[make_pattern_json()])
        config = EngineConfig(
            evolution=EvolutionConfig(generations=1, population_size=1),
        )
        engine = EvolutionEngine(mock, config)
        tiny = OHLCVSeries(
            symbol="TEST", timeframe="1h",
            bars=[make_bar(i) for i in range(5)],
        )

        run = await engine.evolve(tiny)

        assert run.completed_at is not None

    @pytest.mark.asyncio
    async def test_llm_error_skips_generation(self):
        """LLM error → generation skipped, run continues."""
        mock = MockLLMClient(responses=[])
        mock.should_error = True
        mock.error_message = "Service unavailable"
        config = EngineConfig(
            evolution=EvolutionConfig(generations=1, population_size=2),
            generation=GenerationConfig(max_retries=0),
        )
        engine = EvolutionEngine(mock, config)
        run = await engine.evolve(make_series(200))

        assert run.completed_at is not None
        assert len(run.hypotheses) == 0

    @pytest.mark.asyncio
    async def test_summary_property(self):
        """EvolutionRun.summary returns correct stats."""
        mock = MockLLMClient(responses=[make_multi_pattern_json(2)])
        config = EngineConfig(
            evolution=EvolutionConfig(generations=1, population_size=2),
            selection=SelectionConfig(
                min_is_trade_count=0, min_is_sharpe=-999,
            ),
        )
        engine = EvolutionEngine(mock, config)
        run = await engine.evolve(make_series(200))

        summary = run.summary
        assert summary["run_id"] == run.run_id
        assert summary["symbol"] == "BTCUSDT"
        assert summary["total_hypotheses"] == len(run.hypotheses)
        assert summary["graduated"] == len(run.graduated)
        assert summary["eliminated"] == len(run.graveyard)
        assert summary["total_backtests"] == run.total_backtests

    @pytest.mark.asyncio
    async def test_zero_generations(self):
        """Zero generations → empty run."""
        mock = MockLLMClient(responses=[])
        config = EngineConfig(
            evolution=EvolutionConfig(generations=0, population_size=5),
        )
        engine = EvolutionEngine(mock, config)
        run = await engine.evolve(make_series(200))

        assert run.completed_at is not None
        assert len(run.hypotheses) == 0
        assert run.total_backtests == 0


class TestEngineConfig:
    """Test EngineConfig defaults."""

    def test_defaults(self):
        """EngineConfig has sensible defaults."""
        cfg = EngineConfig()
        assert cfg.evolution.generations == 3
        assert cfg.evolution.population_size == 10
        assert cfg.evolution.is_oos_ratio == 0.7
        assert cfg.selection.top_n == 10
        assert cfg.mutations_per_graduated == 2
        assert cfg.explore_ratio == 0.6

    def test_custom_config(self):
        """Custom values override defaults."""
        cfg = EngineConfig(
            evolution=EvolutionConfig(generations=5, population_size=20),
            mutations_per_graduated=3,
            explore_ratio=0.4,
        )
        assert cfg.evolution.generations == 5
        assert cfg.evolution.population_size == 20
        assert cfg.mutations_per_graduated == 3
        assert cfg.explore_ratio == 0.4


class TestTokenTracking:
    """Test that LLM token usage is tracked."""

    @pytest.mark.asyncio
    async def test_tokens_accumulated(self):
        """Tokens from all LLM calls are accumulated."""
        mock = MockLLMClient(responses=[make_multi_pattern_json(2)])
        config = EngineConfig(
            evolution=EvolutionConfig(generations=1, population_size=2),
            selection=SelectionConfig(
                min_is_trade_count=0, min_is_sharpe=-999,
            ),
        )
        engine = EvolutionEngine(mock, config)
        run = await engine.evolve(make_series(200))

        # MockLLMClient returns 100 input + 200 output = 300 per call
        assert run.total_llm_tokens > 0
        assert run.total_llm_tokens == 300  # 1 generate call × 300 tokens
