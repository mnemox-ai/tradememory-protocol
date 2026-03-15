"""Tests for OWM prospective module: trigger evaluation and outcome recording."""

import pytest

from tradememory.owm.prospective import evaluate_trigger, record_outcome


# --- evaluate_trigger ---


class TestEvaluateTrigger:
    def test_single_gt_condition_met(self):
        plan = {"conditions": [{"field": "price", "op": "gt", "value": 5000}]}
        ctx = {"price": 5100}
        assert evaluate_trigger(plan, ctx) is True

    def test_single_gt_condition_not_met(self):
        plan = {"conditions": [{"field": "price", "op": "gt", "value": 5000}]}
        ctx = {"price": 4900}
        assert evaluate_trigger(plan, ctx) is False

    def test_multiple_conditions_all_met(self):
        plan = {
            "conditions": [
                {"field": "price", "op": "gt", "value": 5000},
                {"field": "atr", "op": "lt", "value": 50},
            ]
        }
        ctx = {"price": 5100, "atr": 30}
        assert evaluate_trigger(plan, ctx) is True

    def test_multiple_conditions_partial_fail(self):
        plan = {
            "conditions": [
                {"field": "price", "op": "gt", "value": 5000},
                {"field": "atr", "op": "lt", "value": 50},
            ]
        }
        ctx = {"price": 5100, "atr": 60}
        assert evaluate_trigger(plan, ctx) is False

    def test_missing_field_in_context_returns_false(self):
        plan = {"conditions": [{"field": "volatility", "op": "gt", "value": 10}]}
        ctx = {"price": 5100}
        assert evaluate_trigger(plan, ctx) is False

    def test_empty_conditions_returns_false(self):
        plan = {"conditions": []}
        assert evaluate_trigger(plan, {}) is False

    def test_no_conditions_key_returns_false(self):
        plan = {"strategy": "VolBreakout"}
        assert evaluate_trigger(plan, {"price": 5000}) is False

    def test_all_operators(self):
        ops_and_values = [
            ("gt", 10, 11, True),
            ("gt", 10, 10, False),
            ("lt", 10, 9, True),
            ("lt", 10, 10, False),
            ("gte", 10, 10, True),
            ("gte", 10, 9, False),
            ("lte", 10, 10, True),
            ("lte", 10, 11, False),
            ("eq", 10, 10, True),
            ("eq", 10, 11, False),
        ]
        for op, threshold, actual, expected in ops_and_values:
            plan = {"conditions": [{"field": "x", "op": op, "value": threshold}]}
            assert evaluate_trigger(plan, {"x": actual}) is expected, f"Failed: {op} {actual} {threshold}"

    def test_unknown_operator_raises(self):
        plan = {"conditions": [{"field": "x", "op": "neq", "value": 10}]}
        with pytest.raises(ValueError, match="Unknown operator"):
            evaluate_trigger(plan, {"x": 10})

    def test_incomplete_condition_returns_false(self):
        plan = {"conditions": [{"field": "x", "op": "gt"}]}  # missing value
        assert evaluate_trigger(plan, {"x": 10}) is False


# --- record_outcome ---


class TestRecordOutcome:
    def test_adds_outcome_fields(self):
        plan = {"strategy": "VolBreakout", "conditions": []}
        result = record_outcome(plan, 150.0)
        assert result["outcome"]["pnl"] == 150.0
        assert result["outcome"]["profitable"] is True
        assert "recorded_at" in result["outcome"]
        assert result["status"] == "completed"

    def test_negative_pnl_not_profitable(self):
        result = record_outcome({"strategy": "test"}, -50.0)
        assert result["outcome"]["profitable"] is False

    def test_zero_pnl_not_profitable(self):
        result = record_outcome({"strategy": "test"}, 0.0)
        assert result["outcome"]["profitable"] is False

    def test_does_not_mutate_original(self):
        original = {"strategy": "VolBreakout"}
        _ = record_outcome(original, 100.0)
        assert "outcome" not in original
        assert "status" not in original

    def test_preserves_original_fields(self):
        plan = {"strategy": "IM", "timeframe": "H1", "conditions": [{"field": "x", "op": "gt", "value": 1}]}
        result = record_outcome(plan, 200.0)
        assert result["strategy"] == "IM"
        assert result["timeframe"] == "H1"
        assert result["conditions"] == plan["conditions"]

    def test_recorded_at_is_utc_iso(self):
        result = record_outcome({"strategy": "test"}, 10.0)
        ts = result["outcome"]["recorded_at"]
        assert "+00:00" in ts or "Z" in ts
