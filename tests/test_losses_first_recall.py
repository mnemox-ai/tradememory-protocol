"""Pre-trade recall that puts losses first, and position size on stored trades.

Before these changes the server told agents that "losses in similar
conditions surface first", while recall ranked winners first and kept losses
only through a 20% floor. remember_trade also stored every position size as 0,
so sizing up after a losing streak could never be seen.
"""

import asyncio
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from tradememory.hybrid_recall import hybrid_recall
from tradememory.owm.context import ContextVector
from tradememory.owm.recall import (
    compute_loss_salience,
    outcome_weighted_recall,
    typical_abs_pnl,
)

_tmpdir = tempfile.mkdtemp()
_test_db = os.path.join(_tmpdir, "test_losses_first.db")


@pytest.fixture(autouse=True)
def _fresh_db():
    import tradememory.mcp_server as mod
    from tradememory.db import Database

    mod._db = Database(db_path=_test_db)
    yield
    mod._db = None
    if os.path.exists(_test_db):
        os.remove(_test_db)


def _ts(days_ago: float = 1.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _memory(mid: str, pnl_r=None, pnl=None, confidence=0.5, days_ago=1.0, **extra):
    m = {
        "id": mid,
        "memory_type": "episodic",
        "timestamp": _ts(days_ago),
        "confidence": confidence,
        "context": {"symbol": "XAUUSD", "regime": "trending_up"},
        "pnl_r": pnl_r,
        "pnl": pnl,
    }
    m.update(extra)
    return m


QUERY = ContextVector(symbol="XAUUSD", regime="trending_up")


# -- the loss weight --


def test_loss_salience_mirrors_outcome_quality():
    assert compute_loss_salience({"pnl_r": -2.0}) > 0.5 > compute_loss_salience({"pnl_r": 2.0})
    assert compute_loss_salience({"pnl_r": 0.0}) == pytest.approx(0.5)
    assert compute_loss_salience({}) == 0.5


def test_loss_salience_uses_pnl_when_there_is_no_r():
    # An imported fill history has no stop, so no R; pnl is measured against
    # the typical trade instead.
    assert compute_loss_salience({"pnl": -300.0}, pnl_scale=100.0) > 0.9
    assert compute_loss_salience({"pnl": 300.0}, pnl_scale=100.0) < 0.1
    assert compute_loss_salience({"pnl": -300.0}, pnl_scale=None) == 0.5


def test_typical_abs_pnl_is_the_median():
    assert typical_abs_pnl([{"pnl": -10.0}, {"pnl": 30.0}, {"pnl": 20.0}]) == 20.0
    assert typical_abs_pnl([{"pnl": -10.0}, {"pnl": 30.0}]) == 20.0
    assert typical_abs_pnl([{"pnl": None}, {}]) is None


# -- ranking --


def _book():
    return [
        _memory("win-big", pnl_r=2.5),
        _memory("win-small", pnl_r=0.8),
        _memory("loss-small", pnl_r=-0.7),
        _memory("loss-big", pnl_r=-2.2),
    ]


def test_default_order_still_ranks_winners_first():
    ranked = outcome_weighted_recall(QUERY, _book(), limit=4)
    assert ranked[0].memory_id == "win-big"
    assert "Q" in ranked[0].components


def test_losses_first_ranks_the_worst_loss_first():
    ranked = outcome_weighted_recall(QUERY, _book(), limit=4, order="losses_first")
    assert [r.memory_id for r in ranked[:2]] == ["loss-big", "loss-small"]
    assert ranked[-1].memory_id == "win-big"
    assert "Loss" in ranked[0].components


def test_losses_first_is_not_hidden_by_a_losing_streak():
    # In the default order a losing streak pushes loss memories down (Aff < 1).
    streak = {"consecutive_losses": 5, "drawdown_state": 0.0}
    default = {r.memory_id: r for r in outcome_weighted_recall(QUERY, _book(), affective_state=streak, limit=4)}
    assert default["loss-big"].components["Aff"] < 1.0
    ranked = outcome_weighted_recall(QUERY, _book(), affective_state=streak, limit=4, order="losses_first")
    assert ranked[0].memory_id == "loss-big"
    assert all(r.components["Aff"] == 1.0 for r in ranked)


def test_losses_first_ranks_pnl_only_history():
    book = [_memory("w", pnl=250.0), _memory("l", pnl=-400.0), _memory("w2", pnl=90.0)]
    ranked = outcome_weighted_recall(QUERY, book, limit=3, order="losses_first")
    assert ranked[0].memory_id == "l"


def test_unknown_order_is_rejected():
    with pytest.raises(ValueError):
        outcome_weighted_recall(QUERY, _book(), order="winners_first")


def test_hybrid_losses_first_skips_the_negative_floor_and_keeps_order():
    book = _book()
    for m in book:
        m["embedding"] = [1.0, 0.0]
    ranked = hybrid_recall(QUERY, [1.0, 0.0], book, limit=2, order="losses_first")
    assert [r.memory_id for r in ranked] == ["loss-big", "loss-small"]
    default = hybrid_recall(QUERY, [1.0, 0.0], book, limit=2)
    assert default[0].memory_id == "win-big"


# -- MCP tools --


async def _store(remember_trade, pnl, pnl_r, lot=None):
    return await remember_trade(
        symbol="XAUUSD",
        direction="long",
        entry_price=2650.0,
        exit_price=2650.0 + pnl / 10,
        pnl=pnl,
        pnl_r=pnl_r,
        strategy_name="VolBreakout",
        market_context="London breakout, trending up",
        context_regime="trending_up",
        lot_size=lot,
    )


@pytest.mark.asyncio
async def test_recall_memories_losses_first_end_to_end():
    from tradememory.mcp_server import recall_memories, remember_trade

    for pnl, r in [(300.0, 3.0), (120.0, 1.2), (-90.0, -0.9), (-250.0, -2.5)]:
        await _store(remember_trade, pnl, r)

    default = await recall_memories(
        symbol="XAUUSD", market_context="London breakout", context_regime="trending_up",
        memory_types=["episodic"], limit=4, use_hybrid=False,
    )
    assert default["order"] == "outcome"
    assert default["memories"][0]["pnl"] > 0

    first = await recall_memories(
        symbol="XAUUSD", market_context="London breakout", context_regime="trending_up",
        memory_types=["episodic"], limit=4, use_hybrid=False, order="losses_first",
    )
    assert first["order"] == "losses_first"
    assert first["memories"][0]["pnl"] == -250.0
    assert first["memories"][1]["pnl"] == -90.0


@pytest.mark.asyncio
async def test_recall_memories_rejects_unknown_order():
    from tradememory.mcp_server import recall_memories

    result = await recall_memories(symbol="XAUUSD", market_context="x", order="best")
    assert "error" in result


@pytest.mark.asyncio
async def test_remember_trade_stores_position_size():
    import tradememory.mcp_server as mod
    from tradememory.mcp_server import remember_trade

    stored = await _store(remember_trade, -120.0, -1.2, lot=0.35)
    tid = stored["memory_id"]
    assert mod._db.get_trade(tid)["lot_size"] == pytest.approx(0.35)
    episodic = [e for e in mod._db.query_episodic(limit=10) if e["id"] == tid]
    assert episodic and episodic[0]["lot_size"] == pytest.approx(0.35)


@pytest.mark.asyncio
async def test_remember_trade_without_size_keeps_working():
    import tradememory.mcp_server as mod
    from tradememory.mcp_server import remember_trade

    stored = await _store(remember_trade, 80.0, 0.8)
    assert stored["status"] == "stored"
    assert mod._db.get_trade(stored["memory_id"])["lot_size"] == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [-1.0, math.nan, math.inf])
async def test_remember_trade_rejects_bad_position_size(bad):
    from tradememory.mcp_server import remember_trade

    result = await _store(remember_trade, 80.0, 0.8, lot=bad)
    assert "error" in result


@pytest.mark.asyncio
async def test_recall_finds_a_symbol_buried_under_other_symbols():
    # Before the SQL symbol filter, recall read the 50 most recent memories of
    # ANY symbol and filtered afterwards, so an imported history of other
    # coins pushed this symbol's trades out of reach.
    import tradememory.mcp_server as mod
    from tradememory.mcp_server import recall_memories, remember_trade

    await remember_trade(
        symbol="XAUUSD", direction="long", entry_price=2650.0, exit_price=2620.0,
        pnl=-300.0, pnl_r=-1.5, strategy_name="VolBreakout",
        market_context="London breakout", timestamp=_ts(days_ago=20),
    )
    for i in range(60):
        mod._db.insert_episodic({
            "id": f"btc-{i}", "timestamp": _ts(days_ago=1), "context_json": {"symbol": "BTC"},
            "context_regime": None, "context_volatility_regime": None, "context_session": None,
            "context_atr_d1": None, "context_atr_h1": None, "strategy": "VolBreakout",
            "direction": "long", "entry_price": 100.0, "lot_size": 1.0, "exit_price": 101.0,
            "pnl": 1.0, "pnl_r": None, "hold_duration_seconds": None, "max_adverse_excursion": None,
            "reflection": None, "confidence": 0.5, "tags": [], "retrieval_strength": 1.0,
            "retrieval_count": 0, "last_retrieved": None,
        })
    result = await recall_memories(
        symbol="XAUUSD", market_context="London breakout", memory_types=["episodic"],
        limit=10, use_hybrid=False, order="losses_first",
    )
    assert [m["pnl"] for m in result["memories"]] == [-300.0]
