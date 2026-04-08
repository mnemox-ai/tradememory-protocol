"""Tests for MCP server tools."""

import asyncio
import os
import tempfile

import pytest

# Patch DB path before importing anything
_tmpdir = tempfile.mkdtemp()
_test_db = os.path.join(_tmpdir, "test_tradememory.db")


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch):
    """Use a fresh temp database for each test."""
    import tradememory.mcp_server as mod

    from tradememory.db import Database

    db = Database(db_path=_test_db)
    mod._db = db
    yield
    mod._db = None
    # Clean up DB file
    if os.path.exists(_test_db):
        os.remove(_test_db)


# -- store_trade_memory and recall_similar_trades removed in 2026-04-08 audit --
# Use remember_trade and recall_memories instead.


# -- get_strategy_performance --


@pytest.mark.asyncio
async def test_get_strategy_performance_empty():
    from tradememory.mcp_server import get_strategy_performance

    result = await get_strategy_performance()
    assert result["trade_count"] == 0


@pytest.mark.asyncio
async def test_get_strategy_performance_with_trades():
    from tradememory.mcp_server import get_strategy_performance, remember_trade

    # Store closed trades via remember_trade (writes to trade_records + episodic)
    await remember_trade(
        symbol="XAUUSD", direction="long", entry_price=2650.0,
        exit_price=2670.0, pnl=200.0, strategy_name="VolBreakout",
        market_context="test",
    )
    await remember_trade(
        symbol="XAUUSD", direction="long", entry_price=2640.0,
        exit_price=2630.0, pnl=-100.0, strategy_name="VolBreakout",
        market_context="test",
    )
    await remember_trade(
        symbol="XAUUSD", direction="short", entry_price=2700.0,
        exit_price=2680.0, pnl=200.0, strategy_name="IntradayMomentum",
        market_context="test",
    )

    result = await get_strategy_performance()
    assert result["total_closed_trades"] == 3
    assert "VolBreakout" in result["strategies"]
    assert "IntradayMomentum" in result["strategies"]

    vb = result["strategies"]["VolBreakout"]
    assert vb["trade_count"] == 2
    assert vb["win_rate"] == 50.0
    assert vb["total_pnl"] == 100.0

    im = result["strategies"]["IntradayMomentum"]
    assert im["trade_count"] == 1
    assert im["win_rate"] == 100.0


@pytest.mark.asyncio
async def test_get_strategy_performance_filtered():
    from tradememory.mcp_server import get_strategy_performance, remember_trade

    await remember_trade(
        symbol="XAUUSD", direction="long", entry_price=2650.0,
        exit_price=2670.0, pnl=200.0, strategy_name="VolBreakout",
        market_context="test",
    )
    await remember_trade(
        symbol="EURUSD", direction="long", entry_price=1.08,
        exit_price=1.09, pnl=100.0, strategy_name="VolBreakout",
        market_context="test",
    )

    result = await get_strategy_performance(symbol="XAUUSD")
    assert result["total_closed_trades"] == 1
    assert result["symbol"] == "XAUUSD"


# -- get_trade_reflection --


@pytest.mark.asyncio
async def test_get_trade_reflection_not_found():
    from tradememory.mcp_server import get_trade_reflection

    result = await get_trade_reflection(trade_id="nonexistent")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_trade_reflection_found():
    from tradememory.mcp_server import get_trade_reflection, remember_trade

    stored = await remember_trade(
        symbol="XAUUSD",
        direction="long",
        entry_price=2650.0,
        exit_price=2670.0,
        pnl=200.0,
        strategy_name="VolBreakout",
        market_context="Breakout above resistance",
        reflection="Perfect setup, good patience",
        trade_id="test-reflect-001",
    )

    result = await get_trade_reflection(trade_id="test-reflect-001")
    assert result["trade_id"] == "test-reflect-001"
    assert result["symbol"] == "XAUUSD"
    assert result["pnl"] == 200.0
    assert result["lessons"] == "Perfect setup, good patience"
