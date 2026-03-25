"""Tests for Phase 2: Audit endpoints + TDR schema + data_hash."""

import json

import pytest
from fastapi.testclient import TestClient

from tradememory.db import Database
from tradememory.domain.tdr import (
    TradingDecisionRecord,
    MemoryContext,
)


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test_audit.db"))


@pytest.fixture
def client(db):
    from tradememory.server import app, journal
    original_db = journal.db
    journal.db = db
    yield TestClient(app)
    journal.db = original_db


def _insert_trade(db, trade_id="TEST-001", strategy="VolBreakout", pnl=117.80):
    conn = db._get_connection()
    try:
        conn.execute("""
            INSERT INTO trade_records
            (id, timestamp, symbol, direction, lot_size, strategy, confidence,
             reasoning, market_context, trade_references, exit_timestamp,
             exit_price, pnl, pnl_r, hold_duration, exit_reasoning,
             slippage, execution_quality, lessons, tags, grade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id, "2026-03-25T10:00:00Z", "XAUUSD", "long", 0.01,
            strategy, 0.7,
            "VB SELL entry. ATR(M5)=13.62. Spread=33pts.",
            json.dumps({
                "price": 4348.22, "session": "london", "magic_number": 260112,
                "event_log": {"atr_m5": 13.62, "spread_points": 33},
                "regime": {"regime": "TRENDING", "atr_h1": 45.2, "atr_d1": 150.3},
            }),
            json.dumps(["T-2026-0001 (long pnl=50.00)", "T-2026-0005 (short pnl=-20.00)"]),
            "2026-03-25T14:00:00Z", 4360.00, pnl, 0.85, 240,
            "TP hit. Profit $+117.80. R=+0.85",
            None, None, None, json.dumps(["london"]), None,
        ))
        conn.commit()
    finally:
        conn.close()


# =====================================================================
# Task 2.1: TDR Schema
# =====================================================================

class TestTDRSchema:
    def test_create_tdr_from_dict(self):
        trade = {
            "id": "T-001", "timestamp": "2026-03-25T10:00:00Z",
            "symbol": "XAUUSD", "direction": "long", "strategy": "VolBreakout",
            "confidence": 0.7, "reasoning": "Test signal",
            "market_context": {"price": 4400.0, "session": "london"},
            "references": ["ref-1"], "lot_size": 0.01,
        }
        tdr = TradingDecisionRecord.from_trade_record(trade)
        assert tdr.record_id == "T-001"
        assert tdr.symbol == "XAUUSD"
        assert tdr.confidence_score == 0.7
        assert len(tdr.data_hash) == 64

    def test_data_hash_deterministic(self):
        h1 = TradingDecisionRecord.compute_hash("T-001", "2026", "XAUUSD", "long", "VB", 0.7, "test", {})
        h2 = TradingDecisionRecord.compute_hash("T-001", "2026", "XAUUSD", "long", "VB", 0.7, "test", {})
        assert h1 == h2

    def test_data_hash_changes_on_tamper(self):
        h1 = TradingDecisionRecord.compute_hash("T-001", "2026", "XAUUSD", "long", "VB", 0.7, "test", {})
        h2 = TradingDecisionRecord.compute_hash("T-001", "2026", "XAUUSD", "long", "VB", 0.8, "test", {})
        assert h1 != h2

    def test_memory_context_defaults(self):
        mem = MemoryContext()
        assert mem.similar_trades == []
        assert mem.anti_resonance_applied is False

    def test_tdr_with_full_memory_context(self):
        trade = {
            "id": "T-002", "timestamp": "2026-03-25T10:00:00Z",
            "symbol": "XAUUSD", "direction": "short", "strategy": "IM",
            "confidence": 0.6, "reasoning": "IM signal",
            "market_context": {}, "references": [],
        }
        mem = MemoryContext(
            similar_trades=["T-001", "T-003"],
            relevant_beliefs=["VB profitable in trending (conf=0.72)"],
            anti_resonance_applied=True, negative_ratio=0.25, recall_count=10,
        )
        tdr = TradingDecisionRecord.from_trade_record(trade, memory_ctx=mem)
        assert tdr.memory.anti_resonance_applied is True
        assert tdr.memory.negative_ratio == 0.25

    def test_tdr_serialization_roundtrip(self):
        trade = {
            "id": "T-003", "timestamp": "2026-03-25T10:00:00Z",
            "symbol": "XAUUSD", "direction": "long", "strategy": "VB",
            "confidence": 0.5, "reasoning": "test",
            "market_context": {"price": 4400}, "references": [],
            "pnl": 50.0, "pnl_r": 1.2,
        }
        tdr = TradingDecisionRecord.from_trade_record(trade)
        data = tdr.model_dump(mode="json")
        assert data["record_id"] == "T-003"
        assert data["data_hash"] != ""
        assert data["pnl"] == 50.0


# =====================================================================
# Task 2.2: /audit/decision-record/{trade_id}
# =====================================================================

class TestAuditEndpoint:
    def test_get_decision_record(self, client, db):
        _insert_trade(db)
        resp = client.get("/audit/decision-record/TEST-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["record_id"] == "TEST-001"
        assert data["symbol"] == "XAUUSD"
        assert data["strategy"] == "VolBreakout"
        assert data["confidence_score"] == 0.7
        assert data["pnl"] == 117.80
        assert data["pnl_r"] == 0.85
        assert len(data["data_hash"]) == 64
        assert len(data["memory"]["similar_trades"]) == 2
        assert data["market"]["session"] == "london"
        assert data["market"]["regime"] == "TRENDING"
        assert data["market"]["atr_m5"] == 13.62

    def test_get_decision_record_not_found(self, client):
        resp = client.get("/audit/decision-record/NONEXISTENT")
        assert resp.status_code == 404


# =====================================================================
# Task 2.3: /audit/export + /audit/export-jsonl
# =====================================================================

class TestAuditExport:
    def test_export_json(self, client, db):
        _insert_trade(db)
        resp = client.get("/audit/export")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_export_with_strategy_filter(self, client, db):
        _insert_trade(db, "T-VB", "VolBreakout")
        _insert_trade(db, "T-IM", "IntradayMomentum")
        resp = client.get("/audit/export?strategy=VolBreakout")
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["strategy"] == "VolBreakout" for r in data)

    def test_export_with_date_range(self, client, db):
        _insert_trade(db)
        resp = client.get("/audit/export?start=2026-03-25&end=2026-03-26")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_export_empty_range(self, client, db):
        _insert_trade(db)
        resp = client.get("/audit/export?start=2099-01-01")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_export_jsonl(self, client, db):
        _insert_trade(db)
        resp = client.get("/audit/export-jsonl")
        assert resp.status_code == 200
        assert "ndjson" in resp.headers.get("content-type", "")
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 1
        for line in lines:
            parsed = json.loads(line)
            assert "record_id" in parsed


# =====================================================================
# Task 2.6: data_hash verification
# =====================================================================

class TestAuditVerify:
    def test_verify_passes(self, client, db):
        _insert_trade(db)
        resp = client.get("/audit/verify/TEST-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is True
        assert len(data["stored_hash"]) == 64

    def test_verify_not_found(self, client):
        resp = client.get("/audit/verify/NONEXISTENT")
        assert resp.status_code == 404
