"""End-to-end integration tests for TradeMemory.

No mocks — tests the full pipeline from MCP tool calls through to database
and back. Uses a temporary SQLite database for isolation.
"""

import asyncio
import os
import tempfile

import pytest


_tmpdir = tempfile.mkdtemp()
_test_db = os.path.join(_tmpdir, "test_integration.db")


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch):
    """Use a fresh temp database for each test."""
    import tradememory.mcp_server as mod
    from tradememory.db import Database

    db = Database(db_path=_test_db)
    mod._db = db
    yield
    mod._db = None
    if os.path.exists(_test_db):
        os.remove(_test_db)


@pytest.mark.asyncio
async def test_full_trade_lifecycle():
    """End-to-end: remember_trade → recall_memories → get_agent_state → audit.

    Verifies the complete pipeline without mocks:
    1. Store a trade with full context
    2. Recall it and verify OWM scoring works
    3. Check agent state reflects the trade
    4. Export audit trail and verify hash
    """
    from tradememory.mcp_server import (
        remember_trade,
        recall_memories,
        get_agent_state,
        export_audit_trail,
        verify_audit_hash,
    )

    # 1. Remember a winning trade
    result = await remember_trade(
        symbol="XAUUSD",
        direction="long",
        entry_price=2650.0,
        exit_price=2680.0,
        pnl=300.0,
        pnl_r=1.5,
        strategy_name="VolBreakout",
        market_context="London open breakout, high ATR, clear trend",
        context_regime="trending_up",
        confidence=0.8,
        reflection="Good setup, waited for confirmation",
        trade_id="integ-001",
        entry_timestamp="2026-04-07T08:00:00+00:00",
        exit_timestamp="2026-04-07T12:00:00+00:00",
    )

    assert result["status"] == "stored"
    assert result["memory_id"] == "integ-001"
    assert "episodic" in result["memory_layers"]
    assert "semantic" in result["memory_layers"]
    assert "procedural" in result["memory_layers"]
    assert "affective" in result["memory_layers"]

    # 2. Recall memories for same context
    recall = await recall_memories(
        symbol="XAUUSD",
        market_context="London session breakout with ATR expansion",
        context_regime="trending_up",
        strategy_name="VolBreakout",
    )

    assert recall["matches_found"] >= 1
    top_memory = recall["memories"][0]
    assert top_memory["memory_id"] == "integ-001"
    assert top_memory["score"] > 0
    assert "components" in top_memory

    # 3. Check agent state reflects the trade
    state = await get_agent_state()
    assert state["status"] == "ok"
    assert state["confidence_level"] > 0
    # Winning trade should have 0 consecutive losses
    assert state["consecutive_losses"] == 0
    assert state["consecutive_wins"] >= 1

    # 4. Export audit trail
    audit = await export_audit_trail(strategy="VolBreakout")
    assert audit["count"] >= 1
    # Find our trade in the audit (TDR uses record_id field)
    our_record = None
    for record in audit["records"]:
        if record.get("record_id") == "integ-001":
            our_record = record
            break
    assert our_record is not None, f"Trade not found in audit trail. Keys: {audit['records'][0].keys() if audit['records'] else 'empty'}"

    # 5. Verify audit hash
    verification = await verify_audit_hash(trade_id="integ-001")
    assert verification["verified"] is True


@pytest.mark.asyncio
async def test_multi_trade_recall_ranking():
    """Store 3 trades with different outcomes, verify OWM ranks them correctly.

    A big winner should rank higher than a small winner or loser
    when context similarity is equal.
    """
    from tradememory.mcp_server import remember_trade, recall_memories

    # Trade 1: Big winner
    await remember_trade(
        symbol="XAUUSD", direction="long", entry_price=2650.0,
        exit_price=2700.0, pnl=500.0, pnl_r=2.5,
        strategy_name="VolBreakout", market_context="breakout high ATR",
        trade_id="rank-001",
    )
    # Trade 2: Small winner
    await remember_trade(
        symbol="XAUUSD", direction="long", entry_price=2650.0,
        exit_price=2655.0, pnl=50.0, pnl_r=0.25,
        strategy_name="VolBreakout", market_context="breakout moderate ATR",
        trade_id="rank-002",
    )
    # Trade 3: Loser
    await remember_trade(
        symbol="XAUUSD", direction="long", entry_price=2650.0,
        exit_price=2630.0, pnl=-200.0, pnl_r=-1.0,
        strategy_name="VolBreakout", market_context="breakout low ATR",
        trade_id="rank-003",
    )

    recall = await recall_memories(
        symbol="XAUUSD",
        market_context="breakout high ATR",
        strategy_name="VolBreakout",
    )

    assert recall["matches_found"] >= 3  # 3 episodic + semantic memories
    # Big winner should rank first among episodic (highest outcome quality + context match)
    episodic_memories = [m for m in recall["memories"] if m["memory_type"] == "episodic"]
    assert episodic_memories[0]["memory_id"] == "rank-001"


@pytest.mark.asyncio
async def test_semantic_drift_detection():
    """Verify that semantic drift flag is set when recent trades diverge.

    Store 12 big wins (pnl_r=3.0 → Bayesian weight=2.0), then 12 small losses
    (pnl_r=-0.5 → weight=0.5). The Bayesian belief stays high (weighted by R),
    but the recent 20 episodic show 8 wins / 20 = 40% win rate.
    Delta > 15% → drift detected.
    """
    from tradememory.mcp_server import remember_trade, _get_db

    # 12 big winners — builds strong Bayesian belief (weight=2.0 each)
    for i in range(12):
        await remember_trade(
            symbol="XAUUSD", direction="long", entry_price=2650.0,
            exit_price=2670.0, pnl=300.0, pnl_r=3.0,
            strategy_name="DriftTest", market_context="test",
            trade_id=f"drift-win-{i:03d}",
        )

    # 12 small losers — Bayesian stays optimistic due to heavy win weights,
    # but recent episodic win rate drops
    for i in range(12):
        await remember_trade(
            symbol="XAUUSD", direction="long", entry_price=2650.0,
            exit_price=2645.0, pnl=-50.0, pnl_r=-0.5,
            strategy_name="DriftTest", market_context="test",
            trade_id=f"drift-lose-{i:03d}",
        )

    # Check semantic memory has drift flag
    db = _get_db()
    semantic = db.query_semantic(strategy="DriftTest", symbol="XAUUSD", limit=1)
    assert len(semantic) > 0

    vc = semantic[0].get("validity_conditions") or {}
    assert vc.get("drift_flag") is True, f"Expected drift_flag=True, got: {vc}"
    drift_info = vc.get("drift_info", {})
    assert drift_info.get("delta", 0) > 0.15, f"Delta too small: {drift_info}"


@pytest.mark.asyncio
async def test_procedural_kelly_computation():
    """Verify Kelly fraction is computed after sufficient trades."""
    from tradememory.mcp_server import remember_trade, _get_db

    # Store 12 trades (10+ needed for Kelly) — 8 wins, 4 losses
    for i in range(8):
        await remember_trade(
            symbol="XAUUSD", direction="long", entry_price=2650.0,
            exit_price=2670.0, pnl=200.0, pnl_r=1.5,
            strategy_name="KellyTest", market_context="test",
            trade_id=f"kelly-win-{i:03d}",
        )
    for i in range(4):
        await remember_trade(
            symbol="XAUUSD", direction="long", entry_price=2650.0,
            exit_price=2630.0, pnl=-200.0, pnl_r=-1.0,
            strategy_name="KellyTest", market_context="test",
            trade_id=f"kelly-lose-{i:03d}",
        )

    db = _get_db()
    proc = db.query_procedural(strategy="KellyTest", symbol="XAUUSD", limit=1)
    assert len(proc) > 0

    record = proc[0]
    assert record["sample_size"] == 12
    assert record["kelly_fraction_suggested"] is not None
    assert 0.0 < record["kelly_fraction_suggested"] <= 0.5
    # With 67% win rate and 1.5R avg win / 1.0R avg loss, Kelly should be positive
    assert record["kelly_fraction_suggested"] > 0.01


@pytest.mark.asyncio
async def test_hold_duration_tracking():
    """Verify hold duration is computed from entry/exit timestamps."""
    from tradememory.mcp_server import remember_trade, _get_db

    await remember_trade(
        symbol="XAUUSD", direction="long", entry_price=2650.0,
        exit_price=2670.0, pnl=200.0,
        strategy_name="HoldTest", market_context="test",
        trade_id="hold-001",
        entry_timestamp="2026-04-07T08:00:00+00:00",
        exit_timestamp="2026-04-07T12:00:00+00:00",
    )

    db = _get_db()
    episodic = db.query_episodic(strategy="HoldTest", limit=1)
    assert len(episodic) > 0
    assert episodic[0]["hold_duration_seconds"] == 4 * 3600  # 4 hours

    proc = db.query_procedural(strategy="HoldTest", symbol="XAUUSD", limit=1)
    assert len(proc) > 0
    # Winner, so avg_hold_winners should be set
    assert proc[0]["avg_hold_winners"] == 4 * 3600.0
