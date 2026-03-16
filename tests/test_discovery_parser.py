"""Tests for pattern parser condition normalization in discovery.py.

Covers standard format, Haiku shorthand format, malformed conditions,
and mixed formats.
"""

import logging
import pytest

from tradememory.evolution.discovery import _normalize_condition, _parse_single_pattern
from tradememory.evolution.models import CandidatePattern


# --- _normalize_condition tests ---


class TestNormalizeCondition:
    """Tests for the _normalize_condition helper."""

    def test_standard_format(self):
        """Standard {"field", "op", "value"} passes through."""
        cond = {"field": "hour_utc", "op": "eq", "value": 4}
        result = _normalize_condition(cond)
        assert result == {"field": "hour_utc", "op": "eq", "value": 4}

    def test_haiku_format_eq(self):
        """Haiku shorthand {"field": "x", "eq": 4} is normalized."""
        cond = {"field": "hour_utc", "eq": 4}
        result = _normalize_condition(cond)
        assert result == {"field": "hour_utc", "op": "eq", "value": 4}

    def test_haiku_format_gt(self):
        cond = {"field": "atr_percentile", "gt": 50}
        result = _normalize_condition(cond)
        assert result == {"field": "atr_percentile", "op": "gt", "value": 50}

    def test_haiku_format_lt(self):
        cond = {"field": "trend_12h_pct", "lt": -0.5}
        result = _normalize_condition(cond)
        assert result == {"field": "trend_12h_pct", "op": "lt", "value": -0.5}

    def test_haiku_format_gte(self):
        cond = {"field": "volume", "gte": 1000}
        result = _normalize_condition(cond)
        assert result == {"field": "volume", "op": "gte", "value": 1000}

    def test_haiku_format_lte(self):
        cond = {"field": "spread", "lte": 30}
        result = _normalize_condition(cond)
        assert result == {"field": "spread", "op": "lte", "value": 30}

    def test_haiku_format_neq(self):
        cond = {"field": "regime", "neq": "ranging"}
        result = _normalize_condition(cond)
        assert result == {"field": "regime", "op": "neq", "value": "ranging"}

    def test_haiku_format_between(self):
        cond = {"field": "hour_utc", "between": [8, 16]}
        result = _normalize_condition(cond)
        assert result == {"field": "hour_utc", "op": "between", "value": [8, 16]}

    def test_haiku_format_in(self):
        cond = {"field": "session", "in": ["london", "newyork"]}
        result = _normalize_condition(cond)
        assert result == {"field": "session", "op": "in", "value": ["london", "newyork"]}

    def test_missing_field_returns_none(self, caplog):
        """Condition without 'field' key is skipped with warning."""
        cond = {"op": "eq", "value": 4}
        with caplog.at_level(logging.WARNING):
            result = _normalize_condition(cond)
        assert result is None
        assert "missing 'field'" in caplog.text

    def test_no_operator_returns_none(self, caplog):
        """Condition with field but no recognizable operator is skipped."""
        cond = {"field": "hour_utc", "something": 4}
        with caplog.at_level(logging.WARNING):
            result = _normalize_condition(cond)
        assert result is None
        assert "no recognizable operator" in caplog.text

    def test_empty_dict_returns_none(self, caplog):
        cond = {}
        with caplog.at_level(logging.WARNING):
            result = _normalize_condition(cond)
        assert result is None

    def test_standard_format_extra_keys_ignored(self):
        """Extra keys in standard format don't break anything."""
        cond = {"field": "x", "op": "eq", "value": 1, "description": "test"}
        result = _normalize_condition(cond)
        assert result == {"field": "x", "op": "eq", "value": 1}


# --- _parse_single_pattern tests ---


def _make_pattern_raw(conditions):
    """Helper to build a minimal valid pattern dict with given conditions."""
    return {
        "name": "TestPattern",
        "description": "A test pattern",
        "entry_condition": {
            "direction": "long",
            "conditions": conditions,
            "description": "entry desc",
        },
        "exit_condition": {
            "stop_loss_atr": 1.5,
            "take_profit_atr": 3.0,
        },
        "validity_conditions": {},
        "confidence": 0.7,
        "sample_count": 100,
    }


class TestParseSinglePattern:
    """Tests for _parse_single_pattern with condition normalization."""

    def test_standard_conditions(self):
        """Standard format conditions parse correctly."""
        raw = _make_pattern_raw([
            {"field": "hour_utc", "op": "eq", "value": 16},
            {"field": "trend_12h_pct", "op": "gt", "value": 0},
        ])
        pattern = _parse_single_pattern(raw)
        assert isinstance(pattern, CandidatePattern)
        assert len(pattern.entry_condition.conditions) == 2
        assert pattern.entry_condition.conditions[0].field == "hour_utc"
        assert pattern.entry_condition.conditions[0].op == "eq"
        assert pattern.entry_condition.conditions[0].value == 16

    def test_haiku_conditions(self):
        """Haiku shorthand conditions parse correctly."""
        raw = _make_pattern_raw([
            {"field": "hour_utc", "eq": 4},
            {"field": "atr_percentile", "gt": 50},
        ])
        pattern = _parse_single_pattern(raw)
        assert len(pattern.entry_condition.conditions) == 2
        assert pattern.entry_condition.conditions[0].op == "eq"
        assert pattern.entry_condition.conditions[0].value == 4
        assert pattern.entry_condition.conditions[1].op == "gt"
        assert pattern.entry_condition.conditions[1].value == 50

    def test_mixed_formats(self):
        """Mix of standard and Haiku formats in one pattern."""
        raw = _make_pattern_raw([
            {"field": "hour_utc", "op": "eq", "value": 16},
            {"field": "trend_12h_pct", "lt": -0.3},
            {"field": "atr_percentile", "op": "between", "value": [25, 75]},
        ])
        pattern = _parse_single_pattern(raw)
        assert len(pattern.entry_condition.conditions) == 3
        assert pattern.entry_condition.conditions[0].op == "eq"
        assert pattern.entry_condition.conditions[1].op == "lt"
        assert pattern.entry_condition.conditions[1].value == -0.3
        assert pattern.entry_condition.conditions[2].op == "between"

    def test_malformed_condition_skipped(self, caplog):
        """Malformed condition is skipped; valid ones still parse."""
        raw = _make_pattern_raw([
            {"field": "hour_utc", "eq": 4},
            {"op": "gt", "value": 50},  # missing field
            {"field": "trend_12h_pct", "lt": 0},
        ])
        with caplog.at_level(logging.WARNING):
            pattern = _parse_single_pattern(raw)
        assert len(pattern.entry_condition.conditions) == 2
        assert pattern.entry_condition.conditions[0].field == "hour_utc"
        assert pattern.entry_condition.conditions[1].field == "trend_12h_pct"

    def test_all_conditions_malformed(self, caplog):
        """If all conditions are malformed, pattern still parses with empty conditions."""
        raw = _make_pattern_raw([
            {"op": "gt", "value": 50},
            {"garbage": True},
        ])
        with caplog.at_level(logging.WARNING):
            pattern = _parse_single_pattern(raw)
        assert len(pattern.entry_condition.conditions) == 0
        assert pattern.name == "TestPattern"

    def test_real_haiku_response(self):
        """Real Haiku response format from live test that failed.

        Haiku returned conditions like:
        {"field": "hour_utc", "eq": 4}
        {"field": "atr_percentile", "between": [30, 70]}
        """
        raw = {
            "name": "Asian_Session_Reversal",
            "description": "Mean reversion during low-volatility Asian session",
            "entry_condition": {
                "direction": "long",
                "conditions": [
                    {"field": "hour_utc", "eq": 4},
                    {"field": "atr_percentile", "between": [30, 70]},
                    {"field": "trend_12h_pct", "lt": -0.2},
                ],
                "description": "Enter long during Asian session on pullback",
            },
            "exit_condition": {
                "stop_loss_atr": 1.2,
                "take_profit_atr": 2.5,
                "max_holding_bars": 12,
            },
            "validity_conditions": {
                "regime": "ranging",
                "session": "asian",
            },
            "confidence": 0.65,
            "sample_count": 45,
        }
        pattern = _parse_single_pattern(raw)
        assert pattern.name == "Asian_Session_Reversal"
        assert len(pattern.entry_condition.conditions) == 3
        assert pattern.entry_condition.conditions[0].op == "eq"
        assert pattern.entry_condition.conditions[0].value == 4
        assert pattern.entry_condition.conditions[1].op == "between"
        assert pattern.entry_condition.conditions[1].value == [30, 70]
        assert pattern.entry_condition.conditions[2].op == "lt"
        assert pattern.entry_condition.conditions[2].value == -0.2
        assert pattern.exit_condition.stop_loss_atr == 1.2
        assert pattern.validity_conditions.regime == "ranging"
