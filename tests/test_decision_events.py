"""Tests for decision_events instrumentation (v0.5.3).

Every pre-trade gate (legitimacy, DQS) and plan trigger must leave a
persisted event behind — this is the raw material for post-alert
behavior metrics. Persistence failures must never block the gate.
"""

import os
import tempfile

import pytest

_tmpdir = tempfile.mkdtemp()
_test_db = os.path.join(_tmpdir, "test_decision_events.db")


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch):
    """Use a fresh temp database for each test."""
    import tradememory.mcp_server as mod
    from tradememory.db import Database

    db = Database(db_path=_test_db)
    mod._db = db
    yield db
    mod._db = None
    if os.path.exists(_test_db):
        os.remove(_test_db)


# ---------------------------------------------------------------------------
# DB layer
# ---------------------------------------------------------------------------


def test_insert_and_query(_fresh_db):
    db = _fresh_db
    event_id = db.insert_decision_event(
        tool="compute_dqs",
        strategy="VolBreakout",
        symbol="XAUUSD",
        tier="caution",
        score=5.5,
        factors={"regime": "ranging"},
        recommendation="Reduce size",
    )
    assert event_id.startswith("de-")

    events = db.query_decision_events()
    assert len(events) == 1
    e = events[0]
    assert e["tool"] == "compute_dqs"
    assert e["tier"] == "caution"
    assert e["score"] == 5.5
    assert "ranging" in e["factors_json"]
    assert e["recommendation"] == "Reduce size"


def test_query_filters(_fresh_db):
    db = _fresh_db
    db.insert_decision_event(tool="compute_dqs")
    db.insert_decision_event(tool="check_trade_legitimacy")
    assert len(db.query_decision_events(tool="compute_dqs")) == 1
    assert len(db.query_decision_events()) == 2


def test_nullable_fields(_fresh_db):
    db = _fresh_db
    db.insert_decision_event(tool="plan_triggered")
    e = db.query_decision_events()[0]
    assert e["strategy"] is None
    assert e["score"] is None
    assert e["factors_json"] is None


# ---------------------------------------------------------------------------
# Gate tools persist events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legitimacy_gate_persists_event(_fresh_db):
    from tradememory.mcp_server import check_trade_legitimacy

    result = await check_trade_legitimacy(
        strategy_name="VolBreakout", symbol="XAUUSD"
    )
    assert "tier" in result

    events = _fresh_db.query_decision_events(tool="check_trade_legitimacy")
    assert len(events) == 1
    assert events[0]["strategy"] == "VolBreakout"
    assert events[0]["symbol"] == "XAUUSD"
    assert events[0]["tier"] == result["tier"]


@pytest.mark.asyncio
async def test_dqs_gate_persists_event(_fresh_db):
    from tradememory.mcp_server import compute_dqs

    result = await compute_dqs(
        symbol="xauusd",
        strategy_name="VolBreakout",
        direction="LONG",
        proposed_lot_size=0.2,
    )
    assert "tier" in result

    events = _fresh_db.query_decision_events(tool="compute_dqs")
    assert len(events) == 1
    assert events[0]["symbol"] == "XAUUSD"
    assert events[0]["tier"] == result["tier"]
    assert events[0]["score"] == result["dqs_score"]


@pytest.mark.asyncio
async def test_triggered_plan_persists_event(_fresh_db):
    from tradememory.mcp_server import check_active_plans, create_trading_plan

    created = await create_trading_plan(
        trigger_type="market_condition",
        trigger_condition='{"regime": "ranging"}',
        planned_action='{"type": "switch_strategy", "to": "MeanReversion"}',
        reasoning="Ranging regimes favor MR",
        priority=0.8,
    )
    assert "error" not in created, created

    result = await check_active_plans(context_regime="ranging")
    assert len(result["triggered"]) == 1

    events = _fresh_db.query_decision_events(tool="plan_triggered")
    assert len(events) == 1
    assert "switch_strategy" in (events[0]["recommendation"] or "")
    assert "ranging" in events[0]["factors_json"]


@pytest.mark.asyncio
async def test_triggered_plan_dedup_same_day(_fresh_db):
    """Polling check_active_plans must not re-log the same standing alert."""
    from tradememory.mcp_server import check_active_plans, create_trading_plan

    await create_trading_plan(
        trigger_type="market_condition",
        trigger_condition='{"regime": "ranging"}',
        planned_action='{"type": "switch_strategy"}',
        reasoning="dedup check",
        priority=0.5,
    )
    await check_active_plans(context_regime="ranging")
    await check_active_plans(context_regime="ranging")
    await check_active_plans(context_regime="ranging")

    events = _fresh_db.query_decision_events(tool="plan_triggered")
    assert len(events) == 1


@pytest.mark.asyncio
async def test_persistence_failure_never_blocks_gate(_fresh_db, monkeypatch):
    from tradememory.mcp_server import check_trade_legitimacy

    def _boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(_fresh_db, "insert_decision_event", _boom)
    result = await check_trade_legitimacy(strategy_name="VolBreakout")
    assert "tier" in result  # gate still answers
