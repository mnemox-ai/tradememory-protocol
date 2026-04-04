"""Tests for ΔS Context Drift Monitor."""

import json

import pytest

from tradememory.owm.drift import (
    compute_context_drift,
    compute_drift_summary,
)


class TestComputeContextDrift:
    """Tests for compute_context_drift function."""

    def test_same_context_returns_zero_drift(self):
        """Identical contexts should produce delta_s ≈ 0, zone = safe."""
        ctx = "XAUUSD trending_up london session atr 45.2"
        result = compute_context_drift(ctx, ctx)
        assert result["delta_s"] == 0.0
        assert result["zone"] == "safe"
        assert result["warning"] is None

    def test_similar_context_low_drift(self):
        """Very similar contexts should be in safe zone."""
        mem = "XAUUSD trending_up london session volatility high atr 45.2"
        cur = "XAUUSD trending_up london session volatility high atr 44.8"
        result = compute_context_drift(mem, cur)
        assert result["delta_s"] < 0.35
        assert result["zone"] == "safe"

    def test_different_regime_transit_or_risk(self):
        """Different regime should push delta_s above safe threshold."""
        mem = "XAUUSD trending_up london session high volatility"
        cur = "XAUUSD ranging newyork session low volatility"
        result = compute_context_drift(mem, cur)
        assert result["delta_s"] > 0.35
        assert result["zone"] in ("transit", "risk", "danger")
        # Should detect regime difference
        assert result["warning"] is not None
        assert "trending_up" in result["warning"]
        assert "ranging" in result["warning"]

    def test_completely_different_contexts(self):
        """Totally unrelated contexts should be in danger zone."""
        mem = "BTCUSDT ranging asia low volatility consolidation"
        cur = "EURUSD trending_down london high impact NFP breakout"
        result = compute_context_drift(mem, cur)
        assert result["delta_s"] > 0.75
        assert result["zone"] == "danger"

    def test_json_market_context_parsing(self):
        """JSON market_context should be parsed and compared correctly."""
        mem_json = json.dumps({
            "regime": "trending_up",
            "atr_d1": 42.5,
            "symbol": "XAUUSD",
            "session": "london",
        })
        cur_json = json.dumps({
            "regime": "trending_up",
            "atr_d1": 42.5,
            "symbol": "XAUUSD",
            "session": "london",
        })
        result = compute_context_drift(mem_json, cur_json)
        assert result["delta_s"] == 0.0
        assert result["zone"] == "safe"

    def test_json_slightly_different_atr(self):
        """JSON contexts with only ATR difference should be low drift."""
        mem_json = json.dumps({
            "regime": "trending_up",
            "atr_d1": 42.5,
            "symbol": "XAUUSD",
            "session": "london",
        })
        cur_json = json.dumps({
            "regime": "trending_up",
            "atr_d1": 43.0,
            "symbol": "XAUUSD",
            "session": "london",
        })
        result = compute_context_drift(mem_json, cur_json)
        # Most tokens overlap, minor ATR difference adds a couple tokens
        assert result["delta_s"] < 0.55  # At most transit zone
        assert result["zone"] in ("safe", "transit")

    def test_json_vs_text_context(self):
        """JSON context compared with text context should still work."""
        mem_json = json.dumps({
            "regime": "trending_up",
            "symbol": "XAUUSD",
            "session": "london",
        })
        cur_text = "XAUUSD trending_up london session"
        result = compute_context_drift(mem_json, cur_text)
        # Should find some overlap (xauusd, trending_up, london)
        assert result["delta_s"] < 0.75

    def test_json_different_regime_warning(self):
        """JSON contexts with different regimes should produce warning."""
        mem_json = json.dumps({"regime": "trending_up", "symbol": "XAUUSD"})
        cur_json = json.dumps({"regime": "ranging", "symbol": "XAUUSD"})
        result = compute_context_drift(mem_json, cur_json)
        assert result["warning"] is not None
        assert "trending_up" in result["warning"]
        assert "ranging" in result["warning"]

    def test_empty_both_contexts(self):
        """Both empty contexts should return safe with zero drift."""
        result = compute_context_drift("", "")
        assert result["delta_s"] == 0.0
        assert result["zone"] == "safe"
        assert result["warning"] is None

    def test_empty_memory_context(self):
        """Empty memory context should return danger zone."""
        result = compute_context_drift("", "XAUUSD trending_up")
        assert result["delta_s"] == 1.0
        assert result["zone"] == "danger"
        assert result["warning"] is not None

    def test_empty_current_context(self):
        """Empty current context should return danger zone."""
        result = compute_context_drift("XAUUSD trending_up", "")
        assert result["delta_s"] == 1.0
        assert result["zone"] == "danger"

    def test_none_contexts(self):
        """None contexts should be handled gracefully."""
        result = compute_context_drift(None, None)
        assert result["delta_s"] == 0.0
        assert result["zone"] == "safe"

    def test_none_memory_context(self):
        result = compute_context_drift(None, "some context")
        assert result["delta_s"] == 1.0
        assert result["zone"] == "danger"

    def test_delta_s_range(self):
        """delta_s should always be in [0, 1]."""
        pairs = [
            ("a b c", "a b c"),
            ("a b c", "d e f"),
            ("x", "y"),
            ("hello world foo bar", "hello world baz qux"),
        ]
        for mem, cur in pairs:
            result = compute_context_drift(mem, cur)
            assert 0.0 <= result["delta_s"] <= 1.0, f"Failed for ({mem}, {cur})"

    def test_zone_values(self):
        """Zone should always be one of the valid values."""
        valid_zones = {"safe", "transit", "risk", "danger"}
        pairs = [
            ("same", "same"),
            ("a b c d e", "a b c x y"),
            ("completely", "different"),
        ]
        for mem, cur in pairs:
            result = compute_context_drift(mem, cur)
            assert result["zone"] in valid_zones

    def test_regime_warning_only_when_different(self):
        """No warning when regimes match."""
        mem = "XAUUSD trending_up london"
        cur = "XAUUSD trending_up newyork"
        result = compute_context_drift(mem, cur)
        assert result["warning"] is None  # Same regime, no warning


class TestComputeDriftSummary:
    """Tests for compute_drift_summary function."""

    def test_empty_list(self):
        result = compute_drift_summary([])
        assert result["avg_delta_s"] == 0.0
        assert result["usable_count"] == 0
        assert result["risky_count"] == 0

    def test_all_safe(self):
        drifts = [
            {"delta_s": 0.1, "zone": "safe", "warning": None},
            {"delta_s": 0.2, "zone": "safe", "warning": None},
        ]
        result = compute_drift_summary(drifts)
        assert result["avg_delta_s"] == 0.15
        assert result["usable_count"] == 2
        assert result["risky_count"] == 0

    def test_mixed_zones(self):
        drifts = [
            {"delta_s": 0.1, "zone": "safe", "warning": None},
            {"delta_s": 0.4, "zone": "transit", "warning": None},
            {"delta_s": 0.6, "zone": "risk", "warning": "Regime differs"},
            {"delta_s": 0.9, "zone": "danger", "warning": "Regime differs"},
        ]
        result = compute_drift_summary(drifts)
        assert result["avg_delta_s"] == 0.5
        assert result["usable_count"] == 2  # safe + transit
        assert result["risky_count"] == 2   # risk + danger

    def test_all_danger(self):
        drifts = [
            {"delta_s": 0.8, "zone": "danger", "warning": "x"},
            {"delta_s": 0.9, "zone": "danger", "warning": "y"},
        ]
        result = compute_drift_summary(drifts)
        assert result["usable_count"] == 0
        assert result["risky_count"] == 2
