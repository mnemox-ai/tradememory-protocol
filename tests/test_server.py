"""Tests for the FastAPI MCP server endpoints."""

import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient


@pytest.fixture
def real_client(tmp_path):
    """Create a test client with real database for integration tests."""
    db_path = str(tmp_path / "test.db")

    from src.tradememory.db import Database
    from src.tradememory.journal import TradeJournal
    from src.tradememory.state import StateManager
    from src.tradememory.reflection import ReflectionEngine
    from src.tradememory.adaptive_risk import AdaptiveRisk

    db = Database(db_path)
    journal = TradeJournal(db=db)
    state_mgr = StateManager(db=db)
    reflection = ReflectionEngine(journal=journal)
    risk = AdaptiveRisk(journal=journal, state_manager=state_mgr)

    with patch("src.tradememory.server.journal", journal), \
         patch("src.tradememory.server.state_manager", state_mgr), \
         patch("src.tradememory.server.reflection_engine", reflection), \
         patch("src.tradememory.server.adaptive_risk", risk):

        from src.tradememory.server import app
        yield TestClient(app)


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_check(self, real_client):
        """Health endpoint returns status, service name, and version."""
        resp = real_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "TradeMemory Protocol"
        assert data["version"] == "0.1.0"


class TestTradeEndpoints:
    """Tests for /trade/* endpoints."""

    def test_record_decision(self, real_client):
        """POST /trade/record_decision creates a trade and returns its ID."""
        resp = real_client.post("/trade/record_decision", json={
            "trade_id": "T-2026-0001",
            "symbol": "XAUUSD",
            "direction": "long",
            "lot_size": 0.05,
            "strategy": "VolBreakout",
            "confidence": 0.72,
            "reasoning": "London breakout",
            "market_context": {"price": 2890.0, "session": "london"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["trade_id"] == "T-2026-0001"
        assert "timestamp" in data

    def test_record_decision_invalid_confidence(self, real_client):
        """POST /trade/record_decision with confidence > 1.0 returns 400."""
        resp = real_client.post("/trade/record_decision", json={
            "trade_id": "T-2026-0002",
            "symbol": "XAUUSD",
            "direction": "long",
            "lot_size": 0.05,
            "strategy": "VolBreakout",
            "confidence": 1.5,
            "reasoning": "Bad confidence",
            "market_context": {"price": 2890.0},
        })
        assert resp.status_code == 400

    def test_record_outcome(self, real_client):
        """POST /trade/record_outcome updates trade with exit data."""
        # First create a trade
        real_client.post("/trade/record_decision", json={
            "trade_id": "T-2026-0010",
            "symbol": "XAUUSD",
            "direction": "long",
            "lot_size": 0.05,
            "strategy": "VolBreakout",
            "confidence": 0.72,
            "reasoning": "Test trade",
            "market_context": {"price": 2890.0},
        })

        # Record outcome
        resp = real_client.post("/trade/record_outcome", json={
            "trade_id": "T-2026-0010",
            "exit_price": 2900.0,
            "pnl": 50.0,
            "exit_reasoning": "Hit target",
            "pnl_r": 2.5,
            "hold_duration": 45,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["trade_id"] == "T-2026-0010"

    def test_query_history(self, real_client):
        """POST /trade/query_history returns filtered trades."""
        # Create two trades with different strategies
        for i, strategy in enumerate(["VolBreakout", "Pullback"], 1):
            real_client.post("/trade/record_decision", json={
                "trade_id": f"T-2026-00{i}0",
                "symbol": "XAUUSD",
                "direction": "long",
                "lot_size": 0.05,
                "strategy": strategy,
                "confidence": 0.7,
                "reasoning": f"Test {strategy}",
                "market_context": {"price": 2890.0},
            })

        resp = real_client.post("/trade/query_history", json={
            "strategy": "VolBreakout",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1
        assert data["trades"][0]["strategy"] == "VolBreakout"

    def test_query_history_empty(self, real_client):
        """POST /trade/query_history with no matches returns empty list."""
        resp = real_client.post("/trade/query_history", json={
            "strategy": "NonExistent",
        })
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_get_active(self, real_client):
        """GET /trade/get_active returns trades without recorded outcome."""
        # Create a trade but don't close it
        real_client.post("/trade/record_decision", json={
            "trade_id": "T-2026-0099",
            "symbol": "XAUUSD",
            "direction": "short",
            "lot_size": 0.03,
            "strategy": "Pullback",
            "confidence": 0.65,
            "reasoning": "Open trade",
            "market_context": {"price": 2910.0},
        })

        resp = real_client.get("/trade/get_active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] >= 1


class TestStateEndpoints:
    """Tests for /state/* endpoints."""

    def test_state_load_new(self, real_client):
        """POST /state/load creates new state for unknown agent."""
        resp = real_client.post("/state/load", json={
            "agent_id": "test-agent-001"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["state"]["agent_id"] == "test-agent-001"
        assert data["state"]["warm_memory"] == {}
        assert data["state"]["active_positions"] == []

    def test_state_save_and_load(self, real_client):
        """POST /state/save persists state, POST /state/load retrieves it."""
        # Save
        resp = real_client.post("/state/save", json={
            "state": {
                "agent_id": "test-agent-002",
                "last_active": "2026-02-23T12:00:00+00:00",
                "warm_memory": {"insight": "london is good"},
                "active_positions": ["T-2026-0001"],
                "risk_constraints": {"max_lot": 0.08},
            }
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Load
        resp = real_client.post("/state/load", json={
            "agent_id": "test-agent-002"
        })
        state = resp.json()["state"]
        assert state["warm_memory"]["insight"] == "london is good"
        assert state["risk_constraints"]["max_lot"] == 0.08


class TestReflectionEndpoint:
    """Tests for /reflect/* endpoints."""

    def test_run_daily_no_trades(self, real_client):
        """POST /reflect/run_daily with no trades returns summary text."""
        resp = real_client.post("/reflect/run_daily")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "date" in data
        assert isinstance(data["summary"], str)

    def test_run_daily_specific_date(self, real_client):
        """POST /reflect/run_daily with date parameter uses that date."""
        resp = real_client.post("/reflect/run_daily?date=2026-02-20")
        assert resp.status_code == 200
        assert resp.json()["date"] == "2026-02-20"

    def test_run_weekly_no_trades(self, real_client):
        """POST /reflect/run_weekly with no trades returns weekly summary."""
        resp = real_client.post("/reflect/run_weekly?week_ending=2026-02-16")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "WEEKLY SUMMARY" in data["summary"]
        assert "No trades this week" in data["summary"]

    def test_run_monthly_no_trades(self, real_client):
        """POST /reflect/run_monthly with no trades returns monthly summary."""
        resp = real_client.post("/reflect/run_monthly?year=2026&month=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["year"] == 2026
        assert data["month"] == 1
        assert "MONTHLY SUMMARY" in data["summary"]
        assert "No trades this month" in data["summary"]


class TestRiskEndpoints:
    """Tests for /risk/* endpoints."""

    def test_get_constraints_default(self, real_client):
        """POST /risk/get_constraints for new agent returns defaults."""
        resp = real_client.post("/risk/get_constraints", json={
            "agent_id": "test-risk-agent",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["constraints"]["status"] == "active"

    def test_get_constraints_recalculate(self, real_client):
        """POST /risk/get_constraints with recalculate=True runs calculation."""
        resp = real_client.post("/risk/get_constraints", json={
            "agent_id": "test-risk-recalc",
            "recalculate": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "constraints" in data

    def test_check_trade_approved(self, real_client):
        """POST /risk/check_trade approves normal trade."""
        resp = real_client.post("/risk/check_trade", json={
            "agent_id": "test-risk-check",
            "symbol": "XAUUSD",
            "direction": "long",
            "lot_size": 0.05,
            "strategy": "VolBreakout",
            "confidence": 0.7,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["approved"] is True
        assert data["adjusted_lot_size"] == 0.05
