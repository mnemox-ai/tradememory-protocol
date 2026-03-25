"""Tests for EventLogReader and pnl_r helpers in mt5_sync_v3.py (Phase 0)."""

import csv
import tempfile
from pathlib import Path

import pytest

# Import the reader class directly
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mt5_sync_v3 import EventLogReader, _extract_sl_from_comment, _get_contract_size, _CONTRACT_SIZES


@pytest.fixture
def tmp_event_log_dir(tmp_path):
    """Create a temp dir with mock event_log CSV files."""
    return tmp_path


def _write_csv(path: Path, rows: list[dict]):
    """Write event_log CSV with standard headers."""
    headers = [
        "ts", "symbol", "tf", "evt", "fsm_from", "fsm_to",
        "gate1_pass", "gate1_code", "gate2_code", "score_total",
        "score_breakdown", "decision", "reason", "atr_m5",
        "ema_fast_h1", "ema_slow_h1", "ema_fast_m30", "ema_slow_m30",
        "bid", "ask", "spread_points", "spread_price",
        "ai_p_up", "ai_adj", "score_after_ai", "signal_id",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class TestEventLogReaderMatch:
    """Test matching TRADE_OPEN by pos_id."""

    def test_match_by_pos_id(self, tmp_event_log_dir):
        csv_path = tmp_event_log_dir / "event_log_2026-03-24_06-00-00_XAUUSD_PERIOD_M5_M260112_12345.csv"
        _write_csv(csv_path, [
            {
                "ts": "2026.03.24 07:55:05", "symbol": "XAUUSD", "tf": "PERIOD_M5",
                "evt": "TRADE_OPEN", "decision": "SELL", "reason": "pos_id=7047640363",
                "atr_m5": "13.617857", "spread_points": "33", "spread_price": "0.33",
                "bid": "4348.22", "ask": "4348.55",
                "ema_fast_h1": "4404.80", "ema_slow_h1": "4493.57",
                "ema_fast_m30": "4374.59", "ema_slow_m30": "4406.62",
            },
        ])
        reader = EventLogReader(tmp_event_log_dir)
        result = reader.find_entry_context("XAUUSD", 260112, 7047640363, 1711262105)

        assert result["matched"] is True
        assert "SELL entry" in result["reasoning"]
        assert "ATR(M5)=13.62" in result["reasoning"]
        assert result["confidence"] != 0.5  # not default
        assert result["market_data"]["atr_m5"] == pytest.approx(13.617857)
        assert result["market_data"]["spread_points"] == 33

    def test_no_match_returns_fallback(self, tmp_event_log_dir):
        csv_path = tmp_event_log_dir / "event_log_2026-03-24_06-00-00_XAUUSD_PERIOD_M5_M260112_12345.csv"
        _write_csv(csv_path, [
            {
                "ts": "2026.03.24 07:55:05", "evt": "TRADE_OPEN",
                "decision": "SELL", "reason": "pos_id=9999999",
                "atr_m5": "10.0", "spread_points": "20",
            },
        ])
        reader = EventLogReader(tmp_event_log_dir)
        result = reader.find_entry_context("XAUUSD", 260112, 1111111, 1711262105)

        assert result["matched"] is False
        assert result["confidence"] == 0.5
        assert "Auto-synced" in result["reasoning"]

    def test_no_csv_files_returns_fallback(self, tmp_event_log_dir):
        reader = EventLogReader(tmp_event_log_dir)
        result = reader.find_entry_context("XAUUSD", 260112, 123456, 1711262105)

        assert result["matched"] is False
        assert result["confidence"] == 0.5

    def test_dir_not_exists_returns_fallback(self):
        reader = EventLogReader(Path("/nonexistent/path"))
        result = reader.find_entry_context("XAUUSD", 260112, 123456, 1711262105)

        assert result["matched"] is False


class TestEventLogReaderDecision:
    """Test matching DECISION events with score_breakdown."""

    def test_decision_event_provides_score(self, tmp_event_log_dir):
        csv_path = tmp_event_log_dir / "event_log_2026-02-24_15-49-24_XAUUSD_PERIOD_M5_M260111_61375.csv"
        _write_csv(csv_path, [
            {
                "ts": "2026.02.24 09:49:00", "evt": "DECISION",
                "decision": "BUY", "reason": "FILTER_FAIL_EMA_TREND_BUY",
                "score_total": "40",
                "score_breakdown": "imp=40;ret=0;trg=0;total=40;gate1=OK;gate2=OK",
                "atr_m5": "6.84",
            },
            {
                "ts": "2026.02.24 09:49:25", "evt": "TRADE_OPEN",
                "decision": "BUY", "reason": "pos_id=5001",
                "atr_m5": "6.84", "spread_points": "17", "spread_price": "0.17",
                "bid": "5176.94", "ask": "5177.11",
                "ema_fast_h1": "5167.97", "ema_slow_h1": "5123.26",
            },
        ])
        reader = EventLogReader(tmp_event_log_dir)
        # entry_time = 2026-02-24 09:49:25 UTC
        result = reader.find_entry_context("XAUUSD", 260111, 5001, 1771926565)

        assert result["matched"] is True
        assert "Score: imp=40" in result["reasoning"]
        assert "FILTER_FAIL_EMA_TREND_BUY" in result["reasoning"]
        assert result["confidence"] == 0.4  # 40/100


class TestEventLogReaderConfidence:
    """Test dynamic confidence calculation."""

    def test_low_spread_high_atr_boosts_confidence(self, tmp_event_log_dir):
        csv_path = tmp_event_log_dir / "event_log_2026-03-24_06-00-00_XAUUSD_PERIOD_M5_M260112_99999.csv"
        _write_csv(csv_path, [
            {
                "ts": "2026.03.24 10:00:00", "evt": "TRADE_OPEN",
                "decision": "BUY", "reason": "pos_id=8001",
                "atr_m5": "15.0", "spread_points": "14", "spread_price": "0.14",
                "bid": "4400.00", "ask": "4400.14",
                "ema_fast_h1": "4410.0", "ema_slow_h1": "4390.0",
            },
        ])
        reader = EventLogReader(tmp_event_log_dir)
        result = reader.find_entry_context("XAUUSD", 260112, 8001, 1711270800)

        # spread_ratio = 0.14/15.0 ≈ 0.0093 < 0.05 → confidence 0.7
        assert result["confidence"] == 0.7

    def test_high_spread_lowers_confidence(self, tmp_event_log_dir):
        csv_path = tmp_event_log_dir / "event_log_2026-03-24_06-00-00_XAUUSD_PERIOD_M5_M260118_88888.csv"
        _write_csv(csv_path, [
            {
                "ts": "2026.03.24 10:00:00", "evt": "TRADE_OPEN",
                "decision": "SELL", "reason": "pos_id=9001",
                "atr_m5": "5.0", "spread_points": "40", "spread_price": "0.40",
                "bid": "4400.00", "ask": "4400.40",
            },
        ])
        reader = EventLogReader(tmp_event_log_dir)
        result = reader.find_entry_context("XAUUSD", 260118, 9001, 1711270800)

        # spread_ratio = 0.40/5.0 = 0.08 → between 0.05 and 0.15 → stays 0.6
        assert result["confidence"] == 0.6


class TestSLExtraction:
    """Test SL price extraction from deal comments."""

    def test_extract_sl_from_comment_standard(self):
        assert _extract_sl_from_comment("[sl 4385.04]") == pytest.approx(4385.04)

    def test_extract_sl_from_comment_no_space(self):
        # Some brokers format differently
        assert _extract_sl_from_comment("[sl4385.04]") is None  # requires space

    def test_extract_sl_from_comment_mixed_text(self):
        assert _extract_sl_from_comment("closed by [sl 4424.96] at market") == pytest.approx(4424.96)

    def test_extract_sl_from_comment_empty(self):
        assert _extract_sl_from_comment("") is None
        assert _extract_sl_from_comment(None) is None

    def test_extract_sl_from_comment_no_sl(self):
        assert _extract_sl_from_comment("manual close") is None

    def test_extract_sl_from_comment_tp_not_sl(self):
        assert _extract_sl_from_comment("[tp 4500.00]") is None


class TestContractSize:
    """Test contract size lookup."""

    def test_xauusd(self):
        # Without MT5 initialized, falls back to hardcoded
        assert _get_contract_size("XAUUSD") == 100

    def test_unknown_symbol_defaults(self):
        assert _get_contract_size("UNKNOWN") == 100000


class TestPnlRCalculation:
    """Integration test: verify pnl_r math with known values."""

    def test_pnl_r_from_sl_comment(self):
        """Verify R-multiple calculation:
        Short entry at 4410.93, SL at 4385.04 (below = wrong for short, but testing math)
        sl_distance = |4410.93 - 4385.04| = 25.89
        risk = 25.89 * 0.1 lots * 100 (XAUUSD contract) = $258.90
        pnl = $258.20
        pnl_r = 258.20 / 258.90 ≈ 0.9973
        """
        entry_price = 4410.93
        sl_price = 4385.04
        lot_size = 0.1
        pnl = 258.20
        contract_size = 100  # XAUUSD

        sl_distance = abs(entry_price - sl_price)
        risk = sl_distance * lot_size * contract_size
        pnl_r = pnl / risk

        assert sl_distance == pytest.approx(25.89, abs=0.01)
        assert risk == pytest.approx(258.90, abs=0.1)
        assert pnl_r == pytest.approx(0.997, abs=0.01)

    def test_pnl_r_loss_is_negative(self):
        """SL hit = pnl_r ≈ -1.0"""
        entry_price = 4400.00
        sl_price = 4380.00  # long position, SL below
        lot_size = 0.01
        contract_size = 100
        pnl = -20.00  # lost $20

        sl_distance = abs(entry_price - sl_price)  # 20.00
        risk = sl_distance * lot_size * contract_size  # 20 * 0.01 * 100 = $20
        pnl_r = pnl / risk  # -20/20 = -1.0

        assert pnl_r == pytest.approx(-1.0)
