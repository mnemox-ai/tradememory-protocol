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
    import src.tradememory.mcp_server as mod

    from src.tradememory.db import Database

    db = Database(db_path=_test_db)
    mod._db = db
    yield
    mod._db = None
    # Clean up DB file
    if os.path.exists(_test_db):
        os.remove(_test_db)


# -- store_trade_memory --


@pytest.mark.asyncio
async def test_store_trade_memory_basic():
    from src.tradememory.mcp_server import store_trade_memory

    result = await store_trade_memory(
        symbol="XAUUSD",
        direction="long",
        entry_price=2650.0,
        strategy_name="VolBreakout",
        market_context="Asian session breakout with high ATR",
    )
    assert result["status"] == "stored"
    assert result["symbol"] == "XAUUSD"
    assert result["direction"] == "long"
    assert result["has_outcome"] is False
    assert "memory_id" in result


@pytest.mark.asyncio
async def test_store_trade_memory_with_outcome():
    from src.tradememory.mcp_server import store_trade_memory

    result = await store_trade_memory(
        symbol="XAUUSD",
        direction="short",
        entry_price=2700.0,
        exit_price=2680.0,
        pnl=200.0,
        strategy_name="IntradayMomentum",
        market_context="London open strong bearish momentum",
        reflection="Good entry, held through pullback",
    )
    assert result["status"] == "stored"
    assert result["has_outcome"] is True
    assert result["direction"] == "short"


@pytest.mark.asyncio
async def test_store_trade_memory_invalid_direction():
    from src.tradememory.mcp_server import store_trade_memory

    result = await store_trade_memory(
        symbol="XAUUSD",
        direction="sideways",
        entry_price=2650.0,
        strategy_name="VolBreakout",
        market_context="test",
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_store_trade_memory_custom_id():
    from src.tradememory.mcp_server import store_trade_memory

    result = await store_trade_memory(
        symbol="XAUUSD",
        direction="long",
        entry_price=2650.0,
        strategy_name="Pullback",
        market_context="test",
        trade_id="my-custom-id",
    )
    assert result["memory_id"] == "my-custom-id"


# -- recall_similar_trades --


@pytest.mark.asyncio
async def test_recall_similar_trades_empty():
    from src.tradememory.mcp_server import recall_similar_trades

    result = await recall_similar_trades(
        symbol="XAUUSD",
        market_context="breakout with high volume",
    )
    assert result["matches_found"] == 0
    assert result["trades"] == []


@pytest.mark.asyncio
async def test_recall_similar_trades_with_data():
    from src.tradememory.mcp_server import recall_similar_trades, store_trade_memory

    # Store some trades first
    await store_trade_memory(
        symbol="XAUUSD",
        direction="long",
        entry_price=2650.0,
        exit_price=2670.0,
        pnl=200.0,
        strategy_name="VolBreakout",
        market_context="Asian session breakout high ATR strong momentum",
        reflection="Great breakout trade",
    )
    await store_trade_memory(
        symbol="XAUUSD",
        direction="long",
        entry_price=2640.0,
        exit_price=2630.0,
        pnl=-100.0,
        strategy_name="VolBreakout",
        market_context="Quiet range no clear direction",
        reflection="Should not have entered",
    )

    result = await recall_similar_trades(
        symbol="XAUUSD",
        market_context="Asian session breakout momentum",
    )
    assert result["matches_found"] == 2
    # The first trade should be more relevant (more keyword overlap)
    assert result["trades"][0]["relevance_score"] >= result["trades"][1]["relevance_score"]


@pytest.mark.asyncio
async def test_recall_similar_trades_with_strategy_filter():
    from src.tradememory.mcp_server import recall_similar_trades, store_trade_memory

    await store_trade_memory(
        symbol="XAUUSD", direction="long", entry_price=2650.0,
        strategy_name="VolBreakout", market_context="test breakout",
    )
    await store_trade_memory(
        symbol="XAUUSD", direction="long", entry_price=2640.0,
        strategy_name="Pullback", market_context="test pullback",
    )

    result = await recall_similar_trades(
        symbol="XAUUSD",
        market_context="test",
        strategy_name="VolBreakout",
    )
    assert result["matches_found"] == 1
    assert result["trades"][0]["strategy"] == "VolBreakout"


# -- get_strategy_performance --


@pytest.mark.asyncio
async def test_get_strategy_performance_empty():
    from src.tradememory.mcp_server import get_strategy_performance

    result = await get_strategy_performance()
    assert result["trade_count"] == 0


@pytest.mark.asyncio
async def test_get_strategy_performance_with_trades():
    from src.tradememory.mcp_server import get_strategy_performance, store_trade_memory

    # Store closed trades
    await store_trade_memory(
        symbol="XAUUSD", direction="long", entry_price=2650.0,
        exit_price=2670.0, pnl=200.0, strategy_name="VolBreakout",
        market_context="test",
    )
    await store_trade_memory(
        symbol="XAUUSD", direction="long", entry_price=2640.0,
        exit_price=2630.0, pnl=-100.0, strategy_name="VolBreakout",
        market_context="test",
    )
    await store_trade_memory(
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
    from src.tradememory.mcp_server import get_strategy_performance, store_trade_memory

    await store_trade_memory(
        symbol="XAUUSD", direction="long", entry_price=2650.0,
        exit_price=2670.0, pnl=200.0, strategy_name="VolBreakout",
        market_context="test",
    )
    await store_trade_memory(
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
    from src.tradememory.mcp_server import get_trade_reflection

    result = await get_trade_reflection(trade_id="nonexistent")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_trade_reflection_found():
    from src.tradememory.mcp_server import get_trade_reflection, store_trade_memory

    stored = await store_trade_memory(
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
