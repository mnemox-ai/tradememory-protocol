"""Tests for evolution_demo.py — E2E demo with mock LLM."""

import pytest

# Import from scripts (add scripts to path)
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from evolution_demo import generate_mock_btc_1h, build_mock_responses, run_demo


class TestMockDataGeneration:
    """Test the mock OHLCV data generator."""

    def test_generates_correct_bar_count(self):
        series = generate_mock_btc_1h(bars=100)
        assert series.count == 100

    def test_generates_default_500_bars(self):
        series = generate_mock_btc_1h()
        assert series.count == 500

    def test_symbol_and_timeframe(self):
        series = generate_mock_btc_1h()
        assert series.symbol == "BTCUSDT"
        assert series.timeframe.value == "1h"

    def test_prices_are_realistic(self):
        series = generate_mock_btc_1h(start_price=65000.0)
        closes = [b.close for b in series.bars]
        # Should stay within reasonable range (not crash to 0 or moon to 1M)
        assert min(closes) > 30000
        assert max(closes) < 200000

    def test_high_gte_low(self):
        series = generate_mock_btc_1h()
        for bar in series.bars:
            assert bar.high >= bar.low

    def test_deterministic_with_seed(self):
        s1 = generate_mock_btc_1h(seed=42)
        s2 = generate_mock_btc_1h(seed=42)
        assert s1.bars[0].close == s2.bars[0].close
        assert s1.bars[-1].close == s2.bars[-1].close

    def test_different_seed_different_data(self):
        s1 = generate_mock_btc_1h(seed=42)
        s2 = generate_mock_btc_1h(seed=99)
        assert s1.bars[-1].close != s2.bars[-1].close


class TestMockResponses:
    """Test mock LLM response construction."""

    def test_build_mock_responses_returns_list(self):
        responses = build_mock_responses()
        assert isinstance(responses, list)
        assert len(responses) >= 6  # at least gen0 + gen1 explore + gen1 mutate + gen2

    def test_responses_are_valid_json(self):
        import json
        for r in build_mock_responses():
            parsed = json.loads(r)
            assert "patterns" in parsed
            assert len(parsed["patterns"]) > 0


class TestEvolutionDemo:
    """E2E test: run the full demo and verify no errors."""

    @pytest.mark.asyncio
    async def test_run_demo_no_errors(self):
        """Full demo runs without exceptions and returns valid summary."""
        summary = await run_demo(seed=42)

        assert isinstance(summary, dict)
        assert summary["symbol"] == "BTCUSDT"
        assert summary["generations"] == 3
        assert summary["total_hypotheses"] > 0
        assert summary["total_backtests"] > 0
        assert summary["total_llm_tokens"] > 0

    @pytest.mark.asyncio
    async def test_demo_produces_hypotheses(self):
        """Demo should produce at least some hypotheses."""
        summary = await run_demo(seed=42)
        # With 3 generations × 3 population, expect ~9 hypotheses
        assert summary["total_hypotheses"] >= 3

    @pytest.mark.asyncio
    async def test_demo_has_graduated_or_eliminated(self):
        """All hypotheses should end up graduated or eliminated."""
        summary = await run_demo(seed=42)
        total = summary["graduated"] + summary["eliminated"]
        assert total == summary["total_hypotheses"]
