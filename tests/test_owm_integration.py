"""End-to-end integration tests for OWM REST endpoints."""

import json

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed — OWM integration tests skipped")

from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def owm_client(tmp_path):
    """Create a test client with a real DB wired into the FastAPI server."""
    db_path = str(tmp_path / "owm_test.db")

    from tradememory.db import Database
    from tradememory.journal import TradeJournal
    from tradememory.state import StateManager
    from tradememory.reflection import ReflectionEngine
    from tradememory.adaptive_risk import AdaptiveRisk

    db = Database(db_path)
    journal = TradeJournal(db=db)
    state_mgr = StateManager(db=db)
    reflection = ReflectionEngine(journal=journal)
    risk = AdaptiveRisk(journal=journal, state_manager=state_mgr)

    with patch("tradememory.server.journal", journal), \
         patch("tradememory.server.state_manager", state_mgr), \
         patch("tradememory.server.reflection_engine", reflection), \
         patch("tradememory.server.adaptive_risk", risk):

        from tradememory.server import app
        yield TestClient(app)


# ---------------------------------------------------------------------------
# Trade data fixtures
# ---------------------------------------------------------------------------

TRADE_1_WIN = {
    "symbol": "XAUUSD",
    "direction": "long",
    "entry_price": 5100.0,
    "exit_price": 5200.0,
    "pnl": 500.0,
    "strategy_name": "VolBreakout",
    "market_context": "London breakout, strong momentum",
    "pnl_r": 2.0,
    "context_regime": "trending_up",
    "context_atr_d1": 150.0,
    "confidence": 0.8,
    "reflection": "Clean breakout, held to target",
    "trade_id": "owm-test-001",
}

TRADE_2_LOSS = {
    "symbol": "XAUUSD",
    "direction": "short",
    "entry_price": 5200.0,
    "exit_price": 5250.0,
    "pnl": -300.0,
    "strategy_name": "MeanReversion",
    "market_context": "Tried to fade rally, stopped out",
    "pnl_r": -1.0,
    "context_regime": "trending_up",
    "context_atr_d1": 155.0,
    "confidence": 0.4,
    "reflection": "Fading trends is painful",
    "trade_id": "owm-test-002",
}

TRADE_3_WIN = {
    "symbol": "XAUUSD",
    "direction": "long",
    "entry_price": 5150.0,
    "exit_price": 5300.0,
    "pnl": 750.0,
    "strategy_name": "IntradayMomentum",
    "market_context": "NY session momentum continuation",
    "pnl_r": 3.5,
    "context_regime": "trending_up",
    "context_atr_d1": 160.0,
    "confidence": 0.9,
    "reflection": "Momentum trades in trend work well",
    "trade_id": "owm-test-003",
}


class TestOWMRemember:
    """Test POST /owm/remember stores trades correctly."""

    def test_remember_single_trade(self, owm_client):
        resp = owm_client.post("/owm/remember", json=TRADE_1_WIN)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stored"
        assert data["memory_id"] == "owm-test-001"
        assert data["symbol"] == "XAUUSD"
        assert data["direction"] == "long"
        assert data["strategy"] == "VolBreakout"
        assert "episodic" in data["memory_layers"]
        assert "semantic" in data["memory_layers"]
        assert "procedural" in data["memory_layers"]
        assert "affective" in data["memory_layers"]

    def test_remember_invalid_direction(self, owm_client):
        bad = {**TRADE_1_WIN, "direction": "sideways", "trade_id": "owm-bad-dir"}
        resp = owm_client.post("/owm/remember", json=bad)
        assert resp.status_code == 400

    def test_remember_three_trades(self, owm_client):
        for trade in [TRADE_1_WIN, TRADE_2_LOSS, TRADE_3_WIN]:
            resp = owm_client.post("/owm/remember", json=trade)
            assert resp.status_code == 200
            assert resp.json()["status"] == "stored"

    def test_remembered_trade_is_reflectable(self, owm_client):
        """Trades stored via /owm/remember must parse as TradeRecord —
        market_context needs a 'price' field or the reflection engine 400s."""
        resp = owm_client.post("/owm/remember", json=TRADE_1_WIN)
        assert resp.status_code == 200
        resp = owm_client.post("/reflect/run_daily")
        assert resp.status_code == 200, resp.json()
        assert resp.json()["success"] is True


class TestOWMRecall:
    """Test POST /owm/recall returns correctly scored memories."""

    def _store_three_trades(self, client):
        for trade in [TRADE_1_WIN, TRADE_2_LOSS, TRADE_3_WIN]:
            resp = client.post("/owm/remember", json=trade)
            assert resp.status_code == 200

    def test_recall_after_storing(self, owm_client):
        self._store_three_trades(owm_client)

        resp = owm_client.post("/owm/recall", json={
            "symbol": "XAUUSD",
            "market_context": "Trending gold market",
            "context_regime": "trending_up",
            "context_atr_d1": 155.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["query_symbol"] == "XAUUSD"
        assert data["matches_found"] > 0

        memories = data["memories"]
        assert len(memories) > 0

        # Check score components exist
        first = memories[0]
        assert "score" in first
        assert "components" in first
        assert first["score"] > 0

    def test_recall_scoring_order(self, owm_client):
        """Winners with context match should rank higher than losers."""
        self._store_three_trades(owm_client)

        resp = owm_client.post("/owm/recall", json={
            "symbol": "XAUUSD",
            "market_context": "Trending market",
            "context_regime": "trending_up",
            "context_atr_d1": 155.0,
            "memory_types": ["episodic"],
        })
        assert resp.status_code == 200
        data = resp.json()
        episodic_memories = [m for m in data["memories"] if m["memory_type"] == "episodic"]

        if len(episodic_memories) >= 2:
            # Winners should score higher overall
            scores = [m["score"] for m in episodic_memories]
            assert scores == sorted(scores, reverse=True), "Memories should be sorted by score descending"

            # The losing trade should score lower than the best winner
            winner_scores = [m["score"] for m in episodic_memories if m.get("pnl", 0) > 0]
            loser_scores = [m["score"] for m in episodic_memories if m.get("pnl", 0) < 0]
            if winner_scores and loser_scores:
                assert max(winner_scores) > max(loser_scores)

    def test_recall_empty_db(self, owm_client):
        resp = owm_client.post("/owm/recall", json={
            "symbol": "XAUUSD",
            "market_context": "Empty market",
        })
        assert resp.status_code == 200
        assert resp.json()["matches_found"] == 0


class TestOWMBehavioral:
    """Test GET /owm/behavioral returns procedural data."""

    def _store_three_trades(self, client):
        for trade in [TRADE_1_WIN, TRADE_2_LOSS, TRADE_3_WIN]:
            resp = client.post("/owm/remember", json=trade)
            assert resp.status_code == 200

    def test_behavioral_with_data(self, owm_client):
        self._store_three_trades(owm_client)

        resp = owm_client.get("/owm/behavioral")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["count"] > 0

        # Should have entries for strategies that had trades
        strategies = {b["strategy"] for b in data["behaviors"]}
        assert "VolBreakout" in strategies or "IntradayMomentum" in strategies

    def test_behavioral_filter_by_strategy(self, owm_client):
        self._store_three_trades(owm_client)

        resp = owm_client.get("/owm/behavioral", params={"strategy": "VolBreakout"})
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] == "ok":
            for b in data["behaviors"]:
                assert b["strategy"] == "VolBreakout"

    def test_behavioral_no_data(self, owm_client):
        resp = owm_client.get("/owm/behavioral")
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_data"


class TestOWMState:
    """Test GET /owm/state returns affective state correctly."""

    def _store_three_trades(self, client):
        for trade in [TRADE_1_WIN, TRADE_2_LOSS, TRADE_3_WIN]:
            resp = client.post("/owm/remember", json=trade)
            assert resp.status_code == 200

    def test_state_initial(self, owm_client):
        """Fresh DB should auto-initialize affective state."""
        resp = owm_client.get("/owm/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "confidence_level" in data
        assert "recommended_action" in data

    def test_state_after_trades(self, owm_client):
        """After 3 trades (W, L, W), affective state should be updated."""
        self._store_three_trades(owm_client)

        resp = owm_client.get("/owm/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

        # Net P&L = +500 -300 +750 = +950, so current_equity > 10000
        assert data["current_equity"] > 10000.0

        # Last trade was a win, so consecutive_wins >= 1
        assert data["consecutive_wins"] >= 1
        assert data["consecutive_losses"] == 0

        # Positive equity → drawdown should be 0 or near 0
        assert data["drawdown_pct"] < 0.01
        assert data["recommended_action"] == "normal"


class TestOWMPlan:
    """Test POST /owm/plan and GET /owm/plans."""

    def test_create_plan(self, owm_client):
        resp = owm_client.post("/owm/plan", json={
            "trigger_type": "market_condition",
            "trigger_condition": '{"regime": "ranging"}',
            "planned_action": '{"type": "skip_trade", "reason": "Low edge in ranging market"}',
            "reasoning": "Historical data shows MR only strategy with edge in ranging",
            "expiry_days": 14,
            "priority": 0.8,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["plan_id"].startswith("plan-")
        assert "expiry" in data

    def test_create_plan_invalid_json(self, owm_client):
        resp = owm_client.post("/owm/plan", json={
            "trigger_type": "test",
            "trigger_condition": "not json",
            "planned_action": '{"type": "skip"}',
            "reasoning": "test",
        })
        assert resp.status_code == 400

    def test_check_plans_triggered(self, owm_client):
        """Create a plan with regime=ranging, then check with regime=ranging → triggered."""
        owm_client.post("/owm/plan", json={
            "trigger_type": "market_condition",
            "trigger_condition": '{"regime": "ranging"}',
            "planned_action": '{"type": "skip_trade"}',
            "reasoning": "Test plan",
        })

        resp = owm_client.get("/owm/plans", params={"regime": "ranging"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_count"] >= 1
        assert len(data["triggered"]) >= 1
        assert data["triggered"][0]["trigger_condition"]["regime"] == "ranging"

    def test_check_plans_pending(self, owm_client):
        """Create a plan with regime=ranging, check with regime=trending_up → pending."""
        owm_client.post("/owm/plan", json={
            "trigger_type": "market_condition",
            "trigger_condition": '{"regime": "ranging"}',
            "planned_action": '{"type": "skip_trade"}',
            "reasoning": "Test plan",
        })

        resp = owm_client.get("/owm/plans", params={"regime": "trending_up"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["pending"]) >= 1


class TestOWMMigrate:
    """Test POST /owm/migrate."""

    def test_migrate_empty_db(self, owm_client):
        resp = owm_client.post("/owm/migrate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["episodic_migrated"] == 0
        assert data["semantic_migrated"] == 0
        assert data["affective_initialized"] is True


class TestOWMFullPipeline:
    """End-to-end pipeline: remember → recall → behavioral → state → plan → plans."""

    def test_full_pipeline(self, owm_client):
        # Step 1: Store 3 trades
        for trade in [TRADE_1_WIN, TRADE_2_LOSS, TRADE_3_WIN]:
            resp = owm_client.post("/owm/remember", json=trade)
            assert resp.status_code == 200
            assert resp.json()["status"] == "stored"

        # Step 2: Recall memories — OWM scoring
        resp = owm_client.post("/owm/recall", json={
            "symbol": "XAUUSD",
            "market_context": "Trending gold, ATR rising",
            "context_regime": "trending_up",
            "context_atr_d1": 155.0,
        })
        assert resp.status_code == 200
        recall_data = resp.json()
        assert recall_data["matches_found"] > 0
        # Scores should be in descending order
        scores = [m["score"] for m in recall_data["memories"]]
        assert scores == sorted(scores, reverse=True)

        # Step 3: Behavioral analysis
        resp = owm_client.get("/owm/behavioral")
        assert resp.status_code == 200
        behavioral_data = resp.json()
        assert behavioral_data["status"] == "ok"
        assert behavioral_data["count"] > 0

        # Step 4: Agent state — should reflect 3 trades
        resp = owm_client.get("/owm/state")
        assert resp.status_code == 200
        state_data = resp.json()
        assert state_data["status"] == "ok"
        # Net PnL = +500 -300 +750 = +950
        assert state_data["current_equity"] > 10000.0
        assert state_data["consecutive_wins"] >= 1

        # Step 5: Create a trading plan
        resp = owm_client.post("/owm/plan", json={
            "trigger_type": "market_condition",
            "trigger_condition": '{"regime": "ranging"}',
            "planned_action": '{"type": "reduce_size", "factor": 0.5}',
            "reasoning": "Reduce position size when market enters ranging regime",
            "expiry_days": 7,
            "priority": 0.7,
        })
        assert resp.status_code == 200
        plan_data = resp.json()
        assert plan_data["status"] == "active"
        plan_id = plan_data["plan_id"]

        # Step 6: Check active plans — should be pending (current regime trending_up)
        resp = owm_client.get("/owm/plans", params={"regime": "trending_up"})
        assert resp.status_code == 200
        plans_data = resp.json()
        assert plans_data["active_count"] >= 1
        # Plan has regime=ranging, query is trending_up → should be pending
        pending_ids = [p["plan_id"] for p in plans_data["pending"]]
        assert plan_id in pending_ids

        # Check with matching regime → triggered
        resp = owm_client.get("/owm/plans", params={"regime": "ranging"})
        assert resp.status_code == 200
        plans_data = resp.json()
        triggered_ids = [p["plan_id"] for p in plans_data["triggered"]]
        assert plan_id in triggered_ids
