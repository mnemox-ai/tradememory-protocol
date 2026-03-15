"""Tests for pattern discovery + LLM abstraction (Task 10.1).

Unit tests use MockLLMClient — no real API calls.
Integration test uses real Anthropic API (requires ANTHROPIC_API_KEY).
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from src.tradememory.data.context_builder import MarketContext, Regime, Session, VolatilityRegime
from src.tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from src.tradememory.evolution.discovery import (
    build_discovery_prompt,
    compute_hourly_stats,
    discover_patterns,
    format_graveyard,
    mutate_pattern,
    parse_patterns_response,
)
from src.tradememory.evolution.llm import (
    LLMClient,
    LLMError,
    LLMMessage,
    LLMResponse,
    MockLLMClient,
    AnthropicClient,
)
from src.tradememory.evolution.models import (
    CandidatePattern,
    EntryCondition,
    ExitCondition,
    FitnessMetrics,
    Hypothesis,
    HypothesisStatus,
    RuleCondition,
)


# --- Fixtures ---


def make_bars(count=50, start=None, trend=0.5, base=42000.0):
    start = start or datetime(2024, 6, 1, tzinfo=timezone.utc)
    bars = []
    price = base
    for i in range(count):
        ts = start + timedelta(hours=i)
        o = price
        c = price + trend
        h = max(o, c) + 100
        l = min(o, c) - 100
        bars.append(OHLCV(timestamp=ts, open=o, high=h, low=l, close=c, volume=1000))
        price = c
    return bars


def make_series(count=50):
    return OHLCVSeries(
        symbol="BTCUSDT",
        timeframe=Timeframe.H1,
        bars=make_bars(count),
        source="test",
    )


MOCK_DISCOVERY_RESPONSE = json.dumps([
    {
        "name": "Afternoon Engine",
        "description": "Long at 14:00 UTC when 12H trend is positive. Exploits post-London momentum.",
        "entry_condition": {
            "direction": "long",
            "conditions": [
                {"field": "hour_utc", "op": "eq", "value": 14},
                {"field": "trend_12h_pct", "op": "gt", "value": 0.5},
            ],
            "description": "Long at 14:00 UTC in uptrend",
        },
        "exit_condition": {
            "stop_loss_atr": 1.5,
            "take_profit_atr": 4.0,
            "max_holding_bars": 6,
        },
        "validity_conditions": {
            "regime": "trending_up",
            "volatility_regime": "normal",
        },
        "confidence": 0.7,
        "sample_count": 45,
    },
    {
        "name": "US Session Drain",
        "description": "Short at 16:00 UTC when 12H trend is negative.",
        "entry_condition": {
            "direction": "short",
            "conditions": [
                {"field": "hour_utc", "op": "eq", "value": 16},
                {"field": "trend_12h_pct", "op": "lt", "value": -0.3},
            ],
            "description": "Short at NY open in downtrend",
        },
        "exit_condition": {
            "stop_loss_atr": 1.0,
            "take_profit_atr": 2.5,
            "max_holding_bars": 8,
        },
        "validity_conditions": {
            "regime": "trending_down",
        },
        "confidence": 0.65,
        "sample_count": 38,
    },
])


MOCK_MUTATION_RESPONSE = json.dumps([
    {
        "name": "Afternoon Engine v2",
        "description": "Tighter entry: require stronger trend filter",
        "entry_condition": {
            "direction": "long",
            "conditions": [
                {"field": "hour_utc", "op": "eq", "value": 14},
                {"field": "trend_12h_pct", "op": "gt", "value": 1.0},
                {"field": "volatility_regime", "op": "neq", "value": "extreme"},
            ],
            "description": "Long at 14:00 with strong uptrend, no extreme vol",
        },
        "exit_condition": {
            "stop_loss_atr": 1.2,
            "take_profit_atr": 3.5,
            "max_holding_bars": 5,
        },
        "confidence": 0.6,
        "sample_count": 30,
    }
])


# --- LLM Protocol ---


class TestLLMProtocol:
    def test_mock_is_llm_client(self):
        assert isinstance(MockLLMClient(), LLMClient)

    def test_anthropic_is_llm_client(self):
        assert isinstance(AnthropicClient(), LLMClient)

    def test_mock_name(self):
        assert MockLLMClient().name == "mock"

    def test_anthropic_name(self):
        assert AnthropicClient().name == "anthropic"


# --- MockLLMClient ---


class TestMockLLMClient:
    @pytest.mark.asyncio
    async def test_basic_response(self):
        mock = MockLLMClient(responses=["hello world"])
        resp = await mock.complete([LLMMessage(role="user", content="test")])
        assert resp.content == "hello world"
        assert resp.input_tokens == 100
        assert resp.output_tokens == 200

    @pytest.mark.asyncio
    async def test_multiple_responses(self):
        mock = MockLLMClient(responses=["first", "second"])
        r1 = await mock.complete([LLMMessage(role="user", content="1")])
        r2 = await mock.complete([LLMMessage(role="user", content="2")])
        assert r1.content == "first"
        assert r2.content == "second"

    @pytest.mark.asyncio
    async def test_records_calls(self):
        mock = MockLLMClient(responses=["ok"])
        await mock.complete(
            [LLMMessage(role="user", content="test")],
            system="sys",
            temperature=0.3,
        )
        assert len(mock.calls) == 1
        assert mock.calls[0]["system"] == "sys"
        assert mock.calls[0]["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_fallback_response(self):
        mock = MockLLMClient()  # no pre-configured responses
        resp = await mock.complete([LLMMessage(role="user", content="test")])
        assert resp.content == '{"patterns": []}'

    @pytest.mark.asyncio
    async def test_close(self):
        mock = MockLLMClient()
        await mock.close()  # should not raise


# --- LLMResponse ---


class TestLLMResponse:
    def test_parse_json_raw(self):
        resp = LLMResponse(content='[{"a": 1}]')
        assert resp.parse_json() == [{"a": 1}]

    def test_parse_json_markdown(self):
        resp = LLMResponse(content='Some text\n```json\n[{"a": 1}]\n```\nMore text')
        assert resp.parse_json() == [{"a": 1}]

    def test_parse_json_invalid(self):
        resp = LLMResponse(content="This is not JSON at all")
        with pytest.raises(ValueError):
            resp.parse_json()

    def test_parse_json_markdown_no_lang(self):
        resp = LLMResponse(content='```\n{"key": "value"}\n```')
        assert resp.parse_json() == {"key": "value"}


# --- Prompt Building ---


class TestBuildDiscoveryPrompt:
    def test_basic_prompt(self):
        series = make_series(50)
        prompt = build_discovery_prompt(series, count=3)
        assert "BTCUSDT" in prompt
        assert "1h" in prompt
        assert "3" in prompt
        assert "Hourly Statistics" in prompt

    def test_with_graveyard(self):
        series = make_series(50)
        graveyard = [
            {"pattern_name": "Bad Strategy", "elimination_reason": "Negative Sharpe"},
        ]
        prompt = build_discovery_prompt(series, graveyard=graveyard)
        assert "Bad Strategy" in prompt
        assert "Negative Sharpe" in prompt

    def test_empty_series_raises(self):
        series = OHLCVSeries(symbol="TEST", timeframe=Timeframe.H1, bars=[])
        with pytest.raises(ValueError):
            build_discovery_prompt(series)


class TestComputeHourlyStats:
    def test_basic(self):
        bars = make_bars(48)  # 2 days
        stats = compute_hourly_stats(bars)
        assert "00:00 UTC" in stats
        assert "avg_range" in stats

    def test_empty(self):
        assert "no data" in compute_hourly_stats([])


class TestFormatGraveyard:
    def test_empty(self):
        result = format_graveyard([])
        assert "none" in result

    def test_with_entries(self):
        entries = [{"pattern_name": "X", "elimination_reason": "bad"}]
        result = format_graveyard(entries)
        assert "X" in result


# --- Response Parsing ---


class TestParsePatterns:
    def test_parse_valid_response(self):
        resp = LLMResponse(content=MOCK_DISCOVERY_RESPONSE)
        patterns = parse_patterns_response(resp)
        assert len(patterns) == 2
        assert patterns[0].name == "Afternoon Engine"
        assert patterns[0].entry_condition.direction == "long"
        assert len(patterns[0].entry_condition.conditions) == 2
        assert patterns[0].exit_condition.stop_loss_atr == 1.5
        assert patterns[1].name == "US Session Drain"

    def test_parse_wrapped_json(self):
        data = {"patterns": [{"name": "Test", "description": "d", "entry_condition": {"direction": "long", "conditions": []}}]}
        resp = LLMResponse(content=json.dumps(data))
        patterns = parse_patterns_response(resp)
        assert len(patterns) == 1

    def test_parse_invalid_json(self):
        resp = LLMResponse(content="This is not JSON")
        patterns = parse_patterns_response(resp)
        assert patterns == []

    def test_parse_partial_invalid(self):
        """Skip invalid items, keep valid ones."""
        data = [
            {"name": "Good", "description": "ok", "entry_condition": {"direction": "long", "conditions": []}},
            {"entry_condition": {"conditions": [{"field": "x", "op": "INVALID_OP", "value": 1}]}},
        ]
        resp = LLMResponse(content=json.dumps(data))
        patterns = parse_patterns_response(resp)
        assert len(patterns) == 1
        assert patterns[0].name == "Good"

    def test_pattern_fields(self):
        resp = LLMResponse(content=MOCK_DISCOVERY_RESPONSE)
        patterns = parse_patterns_response(resp)
        p = patterns[0]
        assert p.source == "llm_discovery"
        assert p.confidence == 0.7
        assert p.sample_count == 45
        assert p.exit_condition.take_profit_atr == 4.0
        assert p.exit_condition.max_holding_bars == 6
        assert p.validity_conditions.regime == "trending_up"


# --- Discovery ---


class TestDiscoverPatterns:
    @pytest.mark.asyncio
    async def test_discover(self):
        mock = MockLLMClient(responses=[MOCK_DISCOVERY_RESPONSE])
        series = make_series(50)
        patterns, response = await discover_patterns(mock, series, count=2)
        assert len(patterns) == 2
        assert patterns[0].name == "Afternoon Engine"
        # Verify LLM was called with right params
        assert len(mock.calls) == 1
        assert mock.calls[0]["system"] is not None

    @pytest.mark.asyncio
    async def test_discover_with_graveyard(self):
        mock = MockLLMClient(responses=[MOCK_DISCOVERY_RESPONSE])
        series = make_series(50)
        graveyard = [{"pattern_name": "Old Bad", "elimination_reason": "neg sharpe"}]
        patterns, _ = await discover_patterns(mock, series, graveyard=graveyard)
        # Verify graveyard was in the prompt
        prompt_content = mock.calls[0]["messages"][0].content
        assert "Old Bad" in prompt_content

    @pytest.mark.asyncio
    async def test_discover_empty_response(self):
        mock = MockLLMClient(responses=['[]'])
        series = make_series(50)
        patterns, _ = await discover_patterns(mock, series)
        assert patterns == []


# --- Mutation ---


class TestMutatePattern:
    @pytest.mark.asyncio
    async def test_mutate(self):
        mock = MockLLMClient(responses=[MOCK_MUTATION_RESPONSE])
        hypothesis = Hypothesis(
            pattern=CandidatePattern(
                name="Afternoon Engine",
                description="Long at 14:00",
                entry_condition=EntryCondition(direction="long"),
            ),
            fitness_is=FitnessMetrics(
                sharpe_ratio=1.5,
                win_rate=0.55,
                profit_factor=1.8,
                trade_count=45,
                max_drawdown_pct=12.0,
            ),
        )
        mutations, resp = await mutate_pattern(mock, hypothesis, count=1)
        assert len(mutations) == 1
        assert mutations[0].source == "mutation"
        assert "v2" in mutations[0].name

    @pytest.mark.asyncio
    async def test_mutate_no_fitness_raises(self):
        mock = MockLLMClient()
        hypothesis = Hypothesis(
            pattern=CandidatePattern(name="Test", description="", entry_condition=EntryCondition()),
        )
        with pytest.raises(ValueError, match="fitness"):
            await mutate_pattern(mock, hypothesis)


# --- Integration Test (real API) ---


@pytest.mark.integration
class TestDiscoverPatternsIntegration:
    """Integration tests that call real Anthropic API.

    Run with: pytest -m integration --run-integration
    Requires ANTHROPIC_API_KEY in environment.
    """

    @pytest.mark.asyncio
    async def test_real_discovery(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY not set")

        client = AnthropicClient(api_key=api_key)
        try:
            series = make_series(100)
            patterns, response = await discover_patterns(
                client, series, count=2, temperature=0.5
            )

            # Should get parseable patterns
            assert len(patterns) > 0
            assert response.input_tokens > 0
            assert response.output_tokens > 0

            # Each pattern should have valid structure
            for p in patterns:
                assert p.name
                assert p.entry_condition.direction in ("long", "short")
                assert len(p.entry_condition.conditions) > 0
        finally:
            await client.close()
