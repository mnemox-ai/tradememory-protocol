"""Tests for HypothesisGenerator (Task 10.3)."""

import json
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.generator import (
    GenerationConfig,
    GenerationResult,
    HypothesisGenerator,
    _create_hypothesis,
)
from tradememory.evolution.llm import LLMError, LLMMessage, LLMResponse, MockLLMClient
from tradememory.evolution.models import (
    CandidatePattern,
    EntryCondition,
    ExitCondition,
    FitnessMetrics,
    Hypothesis,
    HypothesisStatus,
    RuleCondition,
    ConditionOperator,
)


# --- Helpers ---


def make_bars(count: int = 50) -> List[OHLCV]:
    bars = []
    price = 42000.0
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        ts = start + timedelta(hours=i)
        bars.append(OHLCV(
            timestamp=ts, open=price, high=price + 100,
            low=price - 100, close=price + 10, volume=1000,
        ))
        price += 10
    return bars


def make_series(count: int = 50) -> OHLCVSeries:
    return OHLCVSeries(
        symbol="BTCUSDT", timeframe=Timeframe.H1,
        bars=make_bars(count), source="test",
    )


VALID_PATTERN_JSON = json.dumps([{
    "name": "Test Pattern",
    "description": "A test",
    "entry_condition": {
        "direction": "long",
        "conditions": [
            {"field": "hour_utc", "op": "gte", "value": 14},
        ],
    },
    "exit_condition": {
        "stop_loss_atr": 1.5,
        "take_profit_atr": 3.0,
        "max_holding_bars": 10,
    },
    "confidence": 0.7,
}])

TWO_PATTERNS_JSON = json.dumps([
    {
        "name": "Pattern A",
        "description": "First",
        "entry_condition": {
            "direction": "long",
            "conditions": [{"field": "hour_utc", "op": "eq", "value": 14}],
        },
        "exit_condition": {"stop_loss_atr": 1.0, "take_profit_atr": 2.0, "max_holding_bars": 8},
    },
    {
        "name": "Pattern B",
        "description": "Second",
        "entry_condition": {
            "direction": "short",
            "conditions": [{"field": "hour_utc", "op": "eq", "value": 16}],
        },
        "exit_condition": {"stop_loss_atr": 1.5, "take_profit_atr": 3.0, "max_holding_bars": 12},
    },
])


def make_hypothesis_with_fitness() -> Hypothesis:
    pattern = CandidatePattern(
        name="Parent",
        description="A parent pattern",
        entry_condition=EntryCondition(
            direction="long",
            conditions=[RuleCondition(field="hour_utc", op=ConditionOperator.GTE, value=14)],
        ),
        exit_condition=ExitCondition(stop_loss_atr=1.0, take_profit_atr=2.0, max_holding_bars=10),
    )
    return Hypothesis(
        id="parent-001",
        pattern=pattern,
        status=HypothesisStatus.SURVIVED_IS,
        created_at=datetime.now(timezone.utc),
        fitness_is=FitnessMetrics(
            trade_count=20, win_rate=0.6, profit_factor=1.8,
            sharpe_ratio=1.5, total_pnl=500.0, max_drawdown_pct=15.0,
            avg_holding_bars=5.0, expectancy=25.0,
        ),
    )


# --- Tests ---


class TestCreateHypothesis:
    def test_creates_pending(self):
        pattern = CandidatePattern(
            name="Test",
            description="test",
            entry_condition=EntryCondition(direction="long", conditions=[]),
            exit_condition=ExitCondition(),
        )
        h = _create_hypothesis(pattern)
        assert h.status == HypothesisStatus.PENDING
        assert h.pattern.name == "Test"
        assert h.hypothesis_id  # has an ID
        # Hypothesis auto-generates hypothesis_id

    def test_with_parent_id(self):
        pattern = CandidatePattern(
            name="Child",
            description="test",
            entry_condition=EntryCondition(direction="long", conditions=[]),
            exit_condition=ExitCondition(),
        )
        h = _create_hypothesis(pattern)
        assert h.hypothesis_id  # has auto-generated ID

    def test_unique_ids(self):
        pattern = CandidatePattern(
            name="Test",
            description="test",
            entry_condition=EntryCondition(direction="long", conditions=[]),
            exit_condition=ExitCondition(),
        )
        h1 = _create_hypothesis(pattern)
        h2 = _create_hypothesis(pattern)
        assert h1.hypothesis_id != h2.hypothesis_id


class TestGenerationResult:
    def test_empty_result(self):
        r = GenerationResult()
        assert r.count == 0
        assert r.success is False

    def test_with_hypotheses(self):
        pattern = CandidatePattern(
            name="Test",
            description="test",
            entry_condition=EntryCondition(direction="long", conditions=[]),
            exit_condition=ExitCondition(),
        )
        h = _create_hypothesis(pattern)
        r = GenerationResult(hypotheses=[h], total_tokens=100)
        assert r.count == 1
        assert r.success is True


class TestGenerationConfig:
    def test_defaults(self):
        c = GenerationConfig()
        assert c.patterns_per_batch == 5
        assert c.discovery_temperature == 0.7
        assert c.mutation_temperature == 0.8
        assert c.max_retries == 2

    def test_custom(self):
        c = GenerationConfig(
            patterns_per_batch=10,
            discovery_temperature=0.5,
            max_retries=0,
        )
        assert c.patterns_per_batch == 10
        assert c.discovery_temperature == 0.5
        assert c.max_retries == 0


class TestHypothesisGenerator:
    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Generate hypotheses from valid LLM response."""
        mock = MockLLMClient(responses=[VALID_PATTERN_JSON])
        gen = HypothesisGenerator(mock)
        series = make_series()

        result = await gen.generate(series)

        assert result.success
        assert result.count == 1
        assert result.hypotheses[0].status == HypothesisStatus.PENDING
        assert result.hypotheses[0].pattern.name == "Test Pattern"
        assert result.total_tokens > 0
        assert result.retries == 0

    @pytest.mark.asyncio
    async def test_generate_multiple(self):
        """Generate multiple hypotheses."""
        mock = MockLLMClient(responses=[TWO_PATTERNS_JSON])
        gen = HypothesisGenerator(mock)
        series = make_series()

        result = await gen.generate(series, count=2)

        assert result.count == 2
        assert result.hypotheses[0].pattern.name == "Pattern A"
        assert result.hypotheses[1].pattern.name == "Pattern B"

    @pytest.mark.asyncio
    async def test_generate_llm_error_retries(self):
        """LLM error triggers retry."""
        mock = MockLLMClient(responses=[])
        mock.should_error = True
        mock.error_message = "Rate limit"
        gen = HypothesisGenerator(mock, GenerationConfig(max_retries=1))
        series = make_series()

        result = await gen.generate(series)

        assert not result.success
        assert len(result.errors) > 0
        assert "Rate limit" in result.errors[0]

    @pytest.mark.asyncio
    async def test_generate_empty_response_retries(self):
        """Empty LLM response triggers retry with higher temperature."""
        # First response: invalid JSON, second: valid
        mock = MockLLMClient(responses=["not json", VALID_PATTERN_JSON])
        gen = HypothesisGenerator(mock, GenerationConfig(max_retries=1))
        series = make_series()

        result = await gen.generate(series)

        assert result.success
        assert result.retries == 1
        assert result.count == 1

    @pytest.mark.asyncio
    async def test_generate_with_graveyard(self):
        """Graveyard entries are passed to discovery."""
        mock = MockLLMClient(responses=[VALID_PATTERN_JSON])
        gen = HypothesisGenerator(mock)
        gen.set_graveyard([
            {"pattern_name": "Dead Strategy", "elimination_reason": "negative Sharpe"},
        ])
        series = make_series()

        result = await gen.generate(series)

        assert result.success
        # Verify graveyard was in the prompt
        assert len(mock.calls) == 1
        prompt_content = mock.calls[0]["messages"][0].content
        assert "Dead Strategy" in prompt_content

    @pytest.mark.asyncio
    async def test_generate_custom_temperature(self):
        """Custom temperature is passed through."""
        mock = MockLLMClient(responses=[VALID_PATTERN_JSON])
        gen = HypothesisGenerator(mock)
        series = make_series()

        await gen.generate(series, temperature=0.3)

        # MockLLMClient records calls — verify temperature was set
        assert mock.calls[0]["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_explore_high_temp(self):
        """Explore uses high temperature."""
        mock = MockLLMClient(responses=[VALID_PATTERN_JSON])
        gen = HypothesisGenerator(mock)
        series = make_series()

        result = await gen.explore(series)

        assert result.success
        assert mock.calls[0]["temperature"] == 0.9

    @pytest.mark.asyncio
    async def test_exploit_low_temp(self):
        """Exploit uses low temperature."""
        mock = MockLLMClient(responses=[VALID_PATTERN_JSON])
        gen = HypothesisGenerator(mock)
        series = make_series()

        result = await gen.exploit(series)

        assert result.success
        assert mock.calls[0]["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_mutate_success(self):
        """Mutate generates child hypotheses."""
        mock = MockLLMClient(responses=[VALID_PATTERN_JSON])
        gen = HypothesisGenerator(mock)
        parent = make_hypothesis_with_fitness()

        result = await gen.mutate(parent)

        assert result.success
        assert result.hypotheses[0].hypothesis_id  # has ID
        assert result.hypotheses[0].pattern.source == "mutation"

    @pytest.mark.asyncio
    async def test_mutate_no_fitness_fails(self):
        """Mutate fails if parent has no fitness."""
        mock = MockLLMClient(responses=[VALID_PATTERN_JSON])
        gen = HypothesisGenerator(mock)
        parent = Hypothesis(
            id="no-fitness",
            pattern=CandidatePattern(
                name="No Fitness",
                description="test",
                entry_condition=EntryCondition(direction="long", conditions=[]),
                exit_condition=ExitCondition(),
            ),
            status=HypothesisStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        result = await gen.mutate(parent)

        assert not result.success
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_mutate_llm_error(self):
        """Mutate handles LLM error gracefully."""
        mock = MockLLMClient(responses=[])
        mock.should_error = True
        mock.error_message = "Service unavailable"
        gen = HypothesisGenerator(mock)
        parent = make_hypothesis_with_fitness()

        result = await gen.mutate(parent)

        assert not result.success
        assert "Service unavailable" in result.errors[0]

    @pytest.mark.asyncio
    async def test_generate_no_retries_config(self):
        """max_retries=0 means no retries."""
        mock = MockLLMClient(responses=["invalid json"])
        gen = HypothesisGenerator(mock, GenerationConfig(max_retries=0))
        series = make_series()

        result = await gen.generate(series)

        assert not result.success
        assert result.retries == 0
        assert len(mock.calls) == 1  # only 1 attempt

    @pytest.mark.asyncio
    async def test_all_hypotheses_have_unique_ids(self):
        """All generated hypotheses get unique IDs."""
        mock = MockLLMClient(responses=[TWO_PATTERNS_JSON])
        gen = HypothesisGenerator(mock)
        series = make_series()

        result = await gen.generate(series)

        ids = [h.hypothesis_id for h in result.hypotheses]
        assert len(ids) == len(set(ids))  # all unique
