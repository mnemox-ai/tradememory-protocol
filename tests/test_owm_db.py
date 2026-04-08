"""
Unit tests for OWM (Outcome-Weighted Memory) database tables and CRUD methods.
Tests all 5 tables: episodic, semantic, procedural, affective, prospective.
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone

from tradememory.db import Database
from tradememory.exceptions import TradeMemoryDBError


# ========== Fixtures ==========

@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_owm.db"
        yield Database(str(db_path))


def _make_episodic(id="E-001", strategy="VolBreakout", direction="long",
                   entry_price=5175.0, pnl=100.0, pnl_r=1.5,
                   regime="trending_up", session="london"):
    return {
        "id": id,
        "timestamp": "2026-03-02T10:00:00",
        "context_json": {"price": 5175.0, "atr_d1": 150.0},
        "context_regime": regime,
        "context_volatility_regime": "high",
        "context_session": session,
        "context_atr_d1": 150.0,
        "context_atr_h1": 35.0,
        "strategy": strategy,
        "direction": direction,
        "entry_price": entry_price,
        "lot_size": 0.03,
        "exit_price": 5275.0 if pnl > 0 else 5075.0,
        "pnl": pnl,
        "pnl_r": pnl_r,
        "hold_duration_seconds": 3600,
        "max_adverse_excursion": -50.0,
        "reflection": "Good breakout trade",
        "confidence": 0.7,
        "tags": ["london", "breakout"],
        "retrieval_strength": 1.0,
        "retrieval_count": 0,
        "last_retrieved": None,
    }


# ========== Episodic Memory Tests ==========

class TestEpisodicMemory:

    def test_insert_and_query(self, db):
        data = _make_episodic()
        assert db.insert_episodic(data) is True
        results = db.query_episodic()
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "E-001"
        assert r["strategy"] == "VolBreakout"
        assert r["pnl_r"] == 1.5
        assert r["context_json"]["price"] == 5175.0
        assert r["tags"] == ["london", "breakout"]

    def test_query_filter_strategy(self, db):
        db.insert_episodic(_make_episodic(id="E-001", strategy="VolBreakout"))
        db.insert_episodic(_make_episodic(id="E-002", strategy="IntradayMomentum"))
        results = db.query_episodic(strategy="VolBreakout")
        assert len(results) == 1
        assert results[0]["strategy"] == "VolBreakout"

    def test_query_filter_regime(self, db):
        db.insert_episodic(_make_episodic(id="E-001", regime="trending_up"))
        db.insert_episodic(_make_episodic(id="E-002", regime="ranging"))
        results = db.query_episodic(regime="ranging")
        assert len(results) == 1
        assert results[0]["context_regime"] == "ranging"

    def test_query_filter_direction(self, db):
        db.insert_episodic(_make_episodic(id="E-001", direction="long"))
        db.insert_episodic(_make_episodic(id="E-002", direction="short"))
        results = db.query_episodic(direction="short")
        assert len(results) == 1
        assert results[0]["direction"] == "short"

    def test_update_retrieval(self, db):
        db.insert_episodic(_make_episodic())
        assert db.update_episodic_retrieval("E-001") is True
        results = db.query_episodic()
        assert results[0]["retrieval_count"] == 1
        assert results[0]["last_retrieved"] is not None
        # Second retrieval
        db.update_episodic_retrieval("E-001")
        results = db.query_episodic()
        assert results[0]["retrieval_count"] == 2

    def test_update_retrieval_nonexistent(self, db):
        assert db.update_episodic_retrieval("NOPE") is False

    def test_insert_duplicate_fails(self, db):
        db.insert_episodic(_make_episodic())
        with pytest.raises(TradeMemoryDBError):
            db.insert_episodic(_make_episodic())

    def test_context_json_dict_serialization(self, db):
        data = _make_episodic()
        data["context_json"] = {"custom": True, "nested": {"a": 1}}
        db.insert_episodic(data)
        results = db.query_episodic()
        assert results[0]["context_json"]["nested"]["a"] == 1

    def test_query_limit(self, db):
        for i in range(5):
            db.insert_episodic(_make_episodic(id=f"E-{i:03d}"))
        results = db.query_episodic(limit=3)
        assert len(results) == 3


# ========== Semantic Memory Tests ==========

class TestSemanticMemory:

    def _make_semantic(self, id="S-001", proposition="VB works in trending markets",
                       strategy="VolBreakout", source="induced"):
        return {
            "id": id,
            "proposition": proposition,
            "alpha": 1.0,
            "beta": 1.0,
            "sample_size": 0,
            "strategy": strategy,
            "symbol": "XAUUSD",
            "regime": "trending_up",
            "volatility_regime": "high",
            "validity_conditions": {"atr_d1_min": 100.0},
            "last_confirmed": None,
            "last_contradicted": None,
            "source": source,
        }

    def test_insert_and_query(self, db):
        data = self._make_semantic()
        assert db.insert_semantic(data) is True
        results = db.query_semantic()
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "S-001"
        assert r["proposition"] == "VB works in trending markets"
        # Computed fields
        assert r["confidence"] == pytest.approx(0.5)  # alpha=1, beta=1
        assert r["uncertainty"] > 0

    def test_query_filter_strategy(self, db):
        db.insert_semantic(self._make_semantic(id="S-001", strategy="VB"))
        db.insert_semantic(self._make_semantic(id="S-002", strategy="IM"))
        results = db.query_semantic(strategy="IM")
        assert len(results) == 1
        assert results[0]["strategy"] == "IM"

    def test_query_filter_regime(self, db):
        s1 = self._make_semantic(id="S-001")
        s1["regime"] = "trending_up"
        s2 = self._make_semantic(id="S-002")
        s2["regime"] = "ranging"
        db.insert_semantic(s1)
        db.insert_semantic(s2)
        results = db.query_semantic(regime="ranging")
        assert len(results) == 1

    def test_bayesian_update_confirmed(self, db):
        db.insert_semantic(self._make_semantic())
        assert db.update_semantic_bayesian("S-001", confirmed=True, weight=1.0) is True
        results = db.query_semantic()
        r = results[0]
        assert r["alpha"] == 2.0
        assert r["beta"] == 1.0
        assert r["sample_size"] == 1
        assert r["confidence"] == pytest.approx(2.0 / 3.0)
        assert r["last_confirmed"] is not None

    def test_bayesian_update_contradicted(self, db):
        db.insert_semantic(self._make_semantic())
        db.update_semantic_bayesian("S-001", confirmed=False, weight=2.0)
        results = db.query_semantic()
        r = results[0]
        assert r["alpha"] == 1.0
        assert r["beta"] == 3.0
        assert r["sample_size"] == 1
        assert r["confidence"] == pytest.approx(0.25)
        assert r["last_contradicted"] is not None

    def test_bayesian_update_nonexistent(self, db):
        assert db.update_semantic_bayesian("NOPE", confirmed=True) is False

    def test_bayesian_update_with_evidence_id(self, db):
        db.insert_semantic(self._make_semantic())
        db.update_semantic_bayesian("S-001", confirmed=True, evidence_id="E-042")
        results = db.query_semantic()
        assert results[0]["last_confirmed"] == "E-042"

    def test_validity_conditions_json(self, db):
        data = self._make_semantic()
        data["validity_conditions"] = {"atr_d1_min": 100, "session": "london"}
        db.insert_semantic(data)
        results = db.query_semantic()
        vc = results[0]["validity_conditions"]
        assert vc["atr_d1_min"] == 100
        assert vc["session"] == "london"

    def test_confidence_uncertainty_math(self, db):
        data = self._make_semantic()
        data["alpha"] = 8.0
        data["beta"] = 4.0
        db.insert_semantic(data)
        results = db.query_semantic()
        r = results[0]
        assert r["confidence"] == pytest.approx(8.0 / 12.0)
        expected_unc = (8.0 * 4.0) / (12.0 ** 2 * 13.0)
        assert r["uncertainty"] == pytest.approx(expected_unc)


# ========== Procedural Memory Tests ==========

class TestProceduralMemory:

    def _make_procedural(self, id="P-001", strategy="VolBreakout",
                         symbol="XAUUSD", behavior_type="execution"):
        return {
            "id": id,
            "strategy": strategy,
            "symbol": symbol,
            "behavior_type": behavior_type,
            "sample_size": 50,
            "avg_hold_winners": 3600.0,
            "avg_hold_losers": 7200.0,
            "disposition_ratio": 2.0,
            "actual_lot_mean": 0.05,
            "actual_lot_variance": 0.001,
            "kelly_fraction_suggested": 0.08,
            "lot_vs_kelly_ratio": 0.625,
        }

    def test_upsert_and_query(self, db):
        data = self._make_procedural()
        assert db.upsert_procedural(data) is True
        results = db.query_procedural()
        assert len(results) == 1
        r = results[0]
        assert r["strategy"] == "VolBreakout"
        assert r["disposition_ratio"] == 2.0
        assert r["kelly_fraction_suggested"] == 0.08

    def test_upsert_replaces(self, db):
        data = self._make_procedural()
        db.upsert_procedural(data)
        data["sample_size"] = 100
        data["disposition_ratio"] = 1.5
        db.upsert_procedural(data)
        results = db.query_procedural()
        assert len(results) == 1
        assert results[0]["sample_size"] == 100
        assert results[0]["disposition_ratio"] == 1.5

    def test_query_filter_strategy(self, db):
        db.upsert_procedural(self._make_procedural(id="P-001", strategy="VB"))
        db.upsert_procedural(self._make_procedural(id="P-002", strategy="IM"))
        results = db.query_procedural(strategy="IM")
        assert len(results) == 1
        assert results[0]["strategy"] == "IM"

    def test_query_filter_symbol(self, db):
        db.upsert_procedural(self._make_procedural(id="P-001", symbol="XAUUSD"))
        db.upsert_procedural(self._make_procedural(id="P-002", symbol="EURUSD"))
        results = db.query_procedural(symbol="EURUSD")
        assert len(results) == 1
        assert results[0]["symbol"] == "EURUSD"

    def test_updated_at_changes(self, db):
        data = self._make_procedural()
        db.upsert_procedural(data)
        first = db.query_procedural()[0]["updated_at"]
        data["sample_size"] = 60
        db.upsert_procedural(data)
        second = db.query_procedural()[0]["updated_at"]
        assert second >= first


# ========== Affective State Tests ==========

class TestAffectiveState:

    def test_init_and_load(self, db):
        assert db.init_affective(10000.0, 10000.0) is True
        state = db.load_affective()
        assert state is not None
        assert state["confidence_level"] == 0.5
        assert state["risk_appetite"] == 1.0
        assert state["peak_equity"] == 10000.0
        assert state["current_equity"] == 10000.0
        assert state["consecutive_wins"] == 0
        assert state["history_json"] == []

    def test_init_idempotent(self, db):
        assert db.init_affective(10000.0, 10000.0) is True
        assert db.init_affective(20000.0, 20000.0) is False  # already exists
        state = db.load_affective()
        assert state["peak_equity"] == 10000.0  # unchanged

    def test_load_empty(self, db):
        assert db.load_affective() is None

    def test_save_and_load(self, db):
        db.init_affective(10000.0, 10000.0)
        state = db.load_affective()
        state["confidence_level"] = 0.8
        state["risk_appetite"] = 0.6
        state["consecutive_wins"] = 3
        state["current_equity"] = 9500.0
        state["drawdown_state"] = 0.25
        state["history_json"] = [{"t": "2026-03-02", "eq": 9500}]
        assert db.save_affective(state) is True
        loaded = db.load_affective()
        assert loaded["confidence_level"] == 0.8
        assert loaded["risk_appetite"] == 0.6
        assert loaded["consecutive_wins"] == 3
        assert loaded["current_equity"] == 9500.0
        assert len(loaded["history_json"]) == 1

    def test_save_overwrites(self, db):
        db.init_affective(10000.0, 10000.0)
        db.save_affective({
            "confidence_level": 0.9,
            "risk_appetite": 0.3,
            "momentum_bias": -0.5,
            "peak_equity": 12000.0,
            "current_equity": 8000.0,
            "drawdown_state": 0.5,
            "max_acceptable_drawdown": 0.25,
            "consecutive_wins": 0,
            "consecutive_losses": 5,
            "history_json": [],
        })
        state = db.load_affective()
        assert state["peak_equity"] == 12000.0
        assert state["consecutive_losses"] == 5
        assert state["momentum_bias"] == -0.5


# ========== Prospective Memory Tests ==========

class TestProspectiveMemory:

    def _make_prospective(self, id="F-001", trigger_type="market_condition",
                          action_type="skip_trade", status="active"):
        return {
            "id": id,
            "trigger_type": trigger_type,
            "trigger_condition": {"regime": "ranging", "strategy": "VolBreakout"},
            "planned_action": {"type": "skip_trade", "reason": "low edge in ranging"},
            "action_type": action_type,
            "status": status,
            "priority": 0.8,
            "expiry": "2026-04-01T00:00:00",
            "source_episodic_ids": ["E-001", "E-002"],
            "source_semantic_ids": ["S-001"],
            "reasoning": "VB has poor performance in ranging markets",
            "triggered_at": None,
            "outcome_pnl_r": None,
            "outcome_reflection": None,
        }

    def test_insert_and_query(self, db):
        data = self._make_prospective()
        assert db.insert_prospective(data) is True
        results = db.query_prospective()
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "F-001"
        assert r["trigger_condition"]["regime"] == "ranging"
        assert r["planned_action"]["type"] == "skip_trade"
        assert r["source_episodic_ids"] == ["E-001", "E-002"]
        assert r["priority"] == 0.8

    def test_query_filter_status(self, db):
        db.insert_prospective(self._make_prospective(id="F-001", status="active"))
        db.insert_prospective(self._make_prospective(id="F-002", status="triggered"))
        results = db.query_prospective(status="active")
        assert len(results) == 1
        assert results[0]["id"] == "F-001"

    def test_query_filter_trigger_type(self, db):
        db.insert_prospective(self._make_prospective(id="F-001", trigger_type="market_condition"))
        db.insert_prospective(self._make_prospective(id="F-002", trigger_type="time"))
        results = db.query_prospective(trigger_type="time")
        assert len(results) == 1
        assert results[0]["trigger_type"] == "time"

    def test_update_status_triggered(self, db):
        db.insert_prospective(self._make_prospective())
        now = datetime.now(timezone.utc).isoformat()
        assert db.update_prospective_status(
            "F-001", "triggered", triggered_at=now,
            outcome_pnl_r=2.5, outcome_reflection="Avoided a bad trade"
        ) is True
        results = db.query_prospective(status="triggered")
        assert len(results) == 1
        r = results[0]
        assert r["triggered_at"] == now
        assert r["outcome_pnl_r"] == 2.5
        assert r["outcome_reflection"] == "Avoided a bad trade"

    def test_update_status_expired(self, db):
        db.insert_prospective(self._make_prospective())
        assert db.update_prospective_status("F-001", "expired") is True
        results = db.query_prospective(status="expired")
        assert len(results) == 1

    def test_update_status_nonexistent(self, db):
        assert db.update_prospective_status("NOPE", "triggered") is False

    def test_insert_duplicate_fails(self, db):
        db.insert_prospective(self._make_prospective())
        with pytest.raises(TradeMemoryDBError):
            db.insert_prospective(self._make_prospective())

    def test_query_ordered_by_priority(self, db):
        p1 = self._make_prospective(id="F-001")
        p1["priority"] = 0.3
        p2 = self._make_prospective(id="F-002")
        p2["priority"] = 0.9
        db.insert_prospective(p1)
        db.insert_prospective(p2)
        results = db.query_prospective()
        assert results[0]["id"] == "F-002"  # higher priority first


# ========== Cross-table: existing tables unaffected ==========

class TestExistingTablesUnaffected:
    """Verify that creating OWM tables doesn't break existing L1/L2/L3 tables."""

    def test_trade_records_still_work(self, db):
        trade = {
            "id": "T-001",
            "timestamp": "2026-03-02T10:00:00",
            "symbol": "XAUUSD",
            "direction": "long",
            "lot_size": 0.1,
            "strategy": "VolBreakout",
            "confidence": 0.8,
            "reasoning": "Test",
            "market_context": {},
            "references": [],
            "exit_timestamp": None,
            "exit_price": None,
            "pnl": None,
            "pnl_r": None,
            "hold_duration": None,
            "exit_reasoning": None,
            "slippage": None,
            "execution_quality": None,
            "lessons": None,
            "tags": [],
            "grade": None,
        }
        assert db.insert_trade(trade) is True
        result = db.get_trade("T-001")
        assert result["symbol"] == "XAUUSD"

    def test_patterns_still_work(self, db):
        pattern = {
            "pattern_id": "PAT-001",
            "pattern_type": "win_rate",
            "description": "Test pattern",
            "confidence": 0.7,
            "sample_size": 50,
            "date_range": "2025-01 to 2026-02",
            "strategy": "VolBreakout",
            "symbol": "XAUUSD",
            "metrics": {"pf": 1.17},
            "source": "backtest_auto",
            "validation_status": "IN_SAMPLE",
            "discovered_at": "2026-03-02T10:00:00",
        }
        assert db.insert_pattern(pattern) is True
        result = db.get_pattern("PAT-001")
        assert result["description"] == "Test pattern"

    def test_adjustments_still_work(self, db):
        adj = {
            "adjustment_id": "ADJ-001",
            "adjustment_type": "parameter",
            "parameter": "RR",
            "old_value": "2.5",
            "new_value": "3.5",
            "reason": "Test",
            "source_pattern_id": None,
            "confidence": 0.8,
            "status": "proposed",
            "created_at": "2026-03-02T10:00:00",
            "applied_at": None,
        }
        assert db.insert_adjustment(adj) is True
        results = db.query_adjustments(status="proposed")
        assert len(results) == 1
