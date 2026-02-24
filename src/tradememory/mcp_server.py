"""
TradeMemory MCP Server — Memory system for AI trading agents.

Exposes trade memory operations as MCP tools via FastMCP.
Runs alongside the existing FastAPI server (separate entry point).
"""

from datetime import datetime, timezone
from typing import Optional
import uuid

from fastmcp import FastMCP

from .db import Database

mcp = FastMCP("tradememory-protocol")

# Shared instance — initialized on first use
_db: Optional[Database] = None


def _get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


@mcp.tool()
async def store_trade_memory(
    symbol: str,
    direction: str,
    entry_price: float,
    strategy_name: str,
    market_context: str,
    exit_price: Optional[float] = None,
    pnl: Optional[float] = None,
    reflection: Optional[str] = None,
    trade_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> dict:
    """Store a trade decision with full context into memory.

    Call this after executing a trade to build your memory bank.
    Include market_context and reflection for better recall later.

    Args:
        symbol: Trading instrument (e.g. "XAUUSD")
        direction: "long" or "short"
        entry_price: Entry price of the trade
        strategy_name: Name of the strategy used (e.g. "VolBreakout")
        market_context: Description of market conditions when trade was taken
        exit_price: Exit price (if trade is closed)
        pnl: Profit/loss in account currency (if trade is closed)
        reflection: What you learned from this trade
        trade_id: Optional custom ID. Auto-generated if omitted.
        timestamp: ISO format timestamp. Defaults to now (UTC).
    """
    db = _get_db()

    tid = trade_id or f"mcp-{uuid.uuid4().hex[:12]}"
    ts = timestamp or datetime.now(timezone.utc).isoformat()

    direction_lower = direction.lower()
    if direction_lower not in ("long", "short"):
        return {"error": f"direction must be 'long' or 'short', got '{direction}'"}

    # Insert directly to DB (bypasses Pydantic MarketContext validation)
    trade_data = {
        "id": tid,
        "timestamp": ts,
        "symbol": symbol.upper(),
        "direction": direction_lower,
        "lot_size": 0.0,
        "strategy": strategy_name,
        "confidence": 0.0,
        "reasoning": market_context,
        "market_context": {"description": market_context, "entry_price": entry_price},
        "references": [],
        "exit_timestamp": None,
        "exit_price": exit_price,
        "pnl": pnl,
        "pnl_r": None,
        "hold_duration": None,
        "exit_reasoning": reflection or None,
        "slippage": None,
        "execution_quality": None,
        "lessons": reflection or None,
        "tags": [],
        "grade": None,
    }
    db.insert_trade(trade_data)

    return {
        "memory_id": tid,
        "symbol": symbol.upper(),
        "direction": direction_lower,
        "strategy": strategy_name,
        "stored_at": ts,
        "has_outcome": exit_price is not None,
        "status": "stored",
    }


@mcp.tool()
async def recall_similar_trades(
    symbol: str,
    market_context: str,
    strategy_name: Optional[str] = None,
    limit: int = 5,
) -> dict:
    """Find past trades with similar market context.

    Use this before making a trade to learn from past experience.
    Returns trades with their reflections and outcomes.

    Args:
        symbol: Trading instrument to filter by (e.g. "XAUUSD")
        market_context: Current market conditions to match against
        strategy_name: Optional strategy filter
        limit: Max number of results (default 5)
    """
    db = _get_db()
    trades = db.query_trades(strategy=strategy_name, symbol=symbol.upper(), limit=limit * 3)

    # Simple keyword matching for context similarity
    keywords = set(market_context.lower().split())
    scored = []
    for t in trades:
        ctx = t.get("market_context", {})
        ctx_text = ""
        if isinstance(ctx, dict):
            ctx_text = ctx.get("description", str(ctx))
        elif isinstance(ctx, str):
            ctx_text = ctx
        ctx_words = set(ctx_text.lower().split())
        overlap = len(keywords & ctx_words)
        scored.append((overlap, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:limit]

    results = []
    for score, t in top:
        results.append({
            "trade_id": t["id"],
            "symbol": t["symbol"],
            "direction": t["direction"],
            "strategy": t["strategy"],
            "entry_context": t.get("market_context", {}),
            "pnl": t.get("pnl"),
            "exit_reasoning": t.get("exit_reasoning"),
            "lessons": t.get("lessons"),
            "grade": t.get("grade"),
            "relevance_score": score,
            "timestamp": t.get("timestamp"),
        })

    return {
        "query_symbol": symbol.upper(),
        "query_context": market_context,
        "matches_found": len(results),
        "trades": results,
    }


@mcp.tool()
async def get_strategy_performance(
    strategy_name: Optional[str] = None,
    symbol: Optional[str] = None,
) -> dict:
    """Get aggregate performance stats per strategy.

    Use this to evaluate which strategies are working and which need adjustment.

    Args:
        strategy_name: Filter by strategy name. Returns all strategies if omitted.
        symbol: Filter by symbol. Returns all symbols if omitted.
    """
    db = _get_db()
    trades = db.query_trades(
        strategy=strategy_name,
        symbol=symbol.upper() if symbol else None,
        limit=10000,
    )

    # Only count closed trades (have pnl)
    closed = [t for t in trades if t.get("pnl") is not None]

    if not closed:
        return {
            "strategy": strategy_name or "all",
            "symbol": symbol or "all",
            "trade_count": 0,
            "message": "No closed trades found",
        }

    # Group by strategy
    by_strategy: dict[str, list] = {}
    for t in closed:
        s = t["strategy"]
        by_strategy.setdefault(s, []).append(t)

    strategies = {}
    for strat, strat_trades in by_strategy.items():
        pnls = [t["pnl"] for t in strat_trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]
        total_pnl = sum(pnls)

        best = max(strat_trades, key=lambda t: t["pnl"])
        worst = min(strat_trades, key=lambda t: t["pnl"])

        strategies[strat] = {
            "trade_count": len(strat_trades),
            "win_rate": round(len(winners) / len(strat_trades) * 100, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / len(strat_trades), 2),
            "avg_winner": round(sum(winners) / len(winners), 2) if winners else 0,
            "avg_loser": round(sum(losers) / len(losers), 2) if losers else 0,
            "best_trade": {"id": best["id"], "pnl": best["pnl"]},
            "worst_trade": {"id": worst["id"], "pnl": worst["pnl"]},
            "profit_factor": round(
                sum(winners) / abs(sum(losers)), 2
            ) if losers and sum(losers) != 0 else float("inf"),
        }

    return {
        "symbol": symbol or "all",
        "total_closed_trades": len(closed),
        "strategies": strategies,
    }


@mcp.tool()
async def get_trade_reflection(
    trade_id: str,
) -> dict:
    """Get the full context and reflection for a specific trade.

    Use this to deep-dive into a particular trade's reasoning and lessons.

    Args:
        trade_id: The trade ID to look up
    """
    db = _get_db()
    trade = db.get_trade(trade_id)

    if not trade:
        return {"error": f"Trade '{trade_id}' not found"}

    return {
        "trade_id": trade["id"],
        "symbol": trade["symbol"],
        "direction": trade["direction"],
        "strategy": trade["strategy"],
        "timestamp": trade["timestamp"],
        "market_context": trade.get("market_context", {}),
        "reasoning": trade.get("reasoning"),
        "exit_price": trade.get("exit_price"),
        "pnl": trade.get("pnl"),
        "exit_reasoning": trade.get("exit_reasoning"),
        "lessons": trade.get("lessons"),
        "grade": trade.get("grade"),
        "tags": trade.get("tags", []),
    }


def main():
    """Entry point for MCP server."""
    mcp.run()
