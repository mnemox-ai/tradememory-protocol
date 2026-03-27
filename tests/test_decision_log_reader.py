"""Tests for DecisionLogReader in mt5_sync_v3.py — reads JSONL decision events."""

import json
from pathlib import Path

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mt5_sync_v3 import DecisionLogReader


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


def _write_jsonl(path: Path, events: list[dict]):
    """Write decision_log JSONL file."""
    with open(path, "w", encoding="utf-8") as f:
        for evt in events:
            f.write(json.dumps(evt) + "\n")


SAMPLE_EXECUTED = {
    "ts": "2026-03-27 08:35:05",
    "strategy": "VolBreakout",
    "timeframe": "M5",
    "bar_open": 3050.10,
    "bar_high": 3051.20,
    "bar_low": 3049.80,
    "bar_close": 3050.90,
    "spread_points": 28,
    "decision": "EXECUTED",
    "signal_triggered": True,
    "signal_direction": "LONG",
    "signal_strength": 0.7500,
    "conditions_json": {"conditions": ["breakout_confirmed", "volume_above_avg"]},
    "filters_json": {"filters": ["spread_ok", "risk_ok", "portfolio_ok"]},
    "indicators_json": {"atr_d1": 176.5, "atr_m5": 4.2, "ema_fast_h1": 3055.0, "ema_slow_h1": 3048.0},
    "exec_ticket": 12345678,
    "exec_price": 3050.90,
    "exec_slippage": 2.0,
    "exec_lot": 0.01,
    "exec_error_code": 0,
    "exec_error_msg": "",
    "exec_latency_ms": 45,
    "account_balance": 5945.00,
    "account_equity": 5930.00,
    "open_positions": 1,
    "daily_pnl": -15.00,
    "regime": "TRENDING",
    "regime_ratio": 0.350,
    "regime_would_block": False,
    "consec_losses": 2,
    "cooldown_active": False,
    "risk_daily_pct": -0.252,
}

SAMPLE_NO_SIGNAL = {
    "ts": "2026-03-27 08:30:00",
    "strategy": "VolBreakout",
    "timeframe": "M5",
    "bar_close": 3049.50,
    "spread_points": 30,
    "decision": "NO_SIGNAL",
    "signal_triggered": False,
    "signal_direction": "NONE",
    "signal_strength": None,
}


class TestDecisionLogReaderMatch:
    """Test matching EXECUTED events by ticket and timestamp."""

    def test_match_by_exec_ticket(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_NO_SIGNAL, SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,  # 2026-03-27 08:35:05 UTC
            exec_ticket=12345678,
        )

        assert result is not None
        assert result["matched"] is True
        assert "LONG EXECUTED" in result["reasoning"]
        assert "breakout_confirmed" in result["reasoning"]
        assert result["confidence"] == 0.75

    def test_match_by_timestamp_proximity(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        # No ticket match, but timestamp is within 5 min
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,  # exactly matching
            exec_ticket=0,  # no ticket
        )

        assert result is not None
        assert result["matched"] is True

    def test_no_match_wrong_strategy(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="Pullback",  # event is VolBreakout
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        # Pullback != VolBreakout
        assert result is None

    def test_no_match_time_too_far(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505 + 600,  # 10 min away (> 5 min threshold)
            exec_ticket=0,
        )
        assert result is None

    def test_skips_no_signal_events(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_NO_SIGNAL])  # only NO_SIGNAL

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1743065400,
        )
        assert result is None


class TestDecisionLogReaderContext:
    """Test rich context extraction from JSONL events."""

    def test_reasoning_contains_conditions(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert "breakout_confirmed" in result["reasoning"]
        assert "volume_above_avg" in result["reasoning"]

    def test_reasoning_contains_filters(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert "spread_ok" in result["reasoning"]
        assert "risk_ok" in result["reasoning"]

    def test_reasoning_contains_indicators(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert "atr_d1=176.5" in result["reasoning"]
        assert "ema_fast_h1=3055.0" in result["reasoning"]

    def test_reasoning_contains_execution_details(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert "latency=45ms" in result["reasoning"]
        assert "slippage=2.0pts" in result["reasoning"]

    def test_reasoning_contains_regime(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert "TRENDING" in result["reasoning"]
        assert "0.350" in result["reasoning"]

    def test_reasoning_contains_risk_state(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert "consec_losses=2" in result["reasoning"]
        assert "daily_risk=" in result["reasoning"]

    def test_decision_raw_preserved(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert result["decision_raw"]["exec_ticket"] == 12345678
        assert result["decision_raw"]["regime"] == "TRENDING"

    def test_market_data_includes_indicators(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [SAMPLE_EXECUTED])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert result["market_data"]["indicators"]["atr_d1"] == 176.5
        assert result["market_data"]["spread_points"] == 28


class TestDecisionLogReaderEdgeCases:
    """Edge cases and robustness."""

    def test_empty_dir(self, tmp_dir):
        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade("VolBreakout", 1774600505)
        assert result is None

    def test_dir_not_exists(self):
        reader = DecisionLogReader(Path("/nonexistent/path"))
        result = reader.find_decision_for_trade("VolBreakout", 1774600505)
        assert result is None

    def test_malformed_json_line_skipped(self, tmp_dir):
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        with open(jsonl_path, "w") as f:
            f.write("this is not json\n")
            f.write(json.dumps(SAMPLE_EXECUTED) + "\n")

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert result is not None
        assert result["matched"] is True

    def test_unknown_strategy_returns_none(self, tmp_dir):
        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade("UnknownStrategy", 1774600505)
        assert result is None

    def test_pullback_strategy_match(self, tmp_dir):
        pb_event = {**SAMPLE_EXECUTED, "strategy": "Pullback"}
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [pb_event])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="Pullback",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert result is not None
        assert result["matched"] is True

    def test_im_strategy_direct_match(self, tmp_dir):
        im_event = {**SAMPLE_EXECUTED, "strategy": "IntradayMomentum"}
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [im_event])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="IntradayMomentum",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert result is not None

    def test_confidence_from_signal_strength(self, tmp_dir):
        evt = {**SAMPLE_EXECUTED, "signal_strength": 0.85}
        jsonl_path = tmp_dir / "decision_log_20260327.jsonl"
        _write_jsonl(jsonl_path, [evt])

        reader = DecisionLogReader(tmp_dir)
        result = reader.find_decision_for_trade(
            strategy="VolBreakout",
            entry_time=1774600505,
            exec_ticket=12345678,
        )
        assert result["confidence"] == 0.85
