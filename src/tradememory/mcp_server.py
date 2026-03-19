"""
TradeMemory MCP Server — Memory system for AI trading agents.

Exposes trade memory operations as MCP tools via FastMCP.
Runs alongside the existing FastAPI server (separate entry point).
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from .db import Database
from .embedding import embed_trade_context
from .hybrid_recall import hybrid_recall
from .owm import ContextVector, outcome_weighted_recall

logger = logging.getLogger(__name__)

mcp = FastMCP("tradememory-protocol")

# Shared instance — initialized on first use
_db: Optional[Database] = None


def _get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


def _ensure_tz(ts: Optional[str]) -> str:
    """Ensure a timestamp string is timezone-aware (UTC).

    db.py uses datetime.now(timezone.utc) which produces timezone-aware timestamps.
    OWM compute_recency needs aware timestamps for subtraction.
    """
    if ts is None:
        return datetime.now(timezone.utc).isoformat()
    if "+" not in ts and "Z" not in ts and ts.count("-") <= 2:
        return ts + "+00:00"
    return ts


# ---------------------------------------------------------------------------
# OWM Helper functions
# ---------------------------------------------------------------------------


def _update_semantic_from_trade(
    db: Database,
    symbol: str,
    strategy_name: str,
    pnl: float,
    pnl_r: Optional[float],
    context_regime: Optional[str],
    trade_id: str,
) -> None:
    """Update semantic memories with Bayesian evidence from a new trade.

    Finds existing semantic memories for the same strategy+symbol.
    If none exist, creates one. Then applies Bayesian update:
    pnl > 0 → alpha += weight, pnl <= 0 → beta += weight.
    weight = min(2, abs(pnl_r)) if pnl_r available, else 1.0.
    """
    existing = db.query_semantic(strategy=strategy_name, symbol=symbol, limit=10)

    weight = min(2.0, abs(pnl_r)) if pnl_r is not None else 1.0
    confirmed = pnl > 0

    if existing:
        for mem in existing:
            db.update_semantic_bayesian(
                memory_id=mem["id"],
                confirmed=confirmed,
                weight=weight,
                evidence_id=trade_id,
            )
    else:
        sem_id = f"sem-{strategy_name.lower()}-{symbol.lower()}-{uuid.uuid4().hex[:8]}"
        alpha = 1.0 + (weight if confirmed else 0.0)
        beta = 1.0 + (0.0 if confirmed else weight)
        db.insert_semantic({
            "id": sem_id,
            "proposition": f"{strategy_name} on {symbol} tends to be profitable",
            "alpha": alpha,
            "beta": beta,
            "sample_size": 1,
            "strategy": strategy_name,
            "symbol": symbol,
            "regime": context_regime,
            "volatility_regime": None,
            "validity_conditions": {"symbol": symbol, "strategy": strategy_name},
            "last_confirmed": trade_id if confirmed else None,
            "last_contradicted": None if confirmed else trade_id,
            "source": "remember_trade",
            "retrieval_strength": 1.0,
        })


def _update_procedural_from_trade(
    db: Database,
    symbol: str,
    strategy_name: str,
    pnl: float,
    lot_size: float = 0.0,
) -> None:
    """Update procedural memory with running averages from a new trade."""
    proc_id = f"proc-{strategy_name.lower()}-{symbol.lower()}"
    existing = db.query_procedural(strategy=strategy_name, symbol=symbol, limit=1)

    if existing:
        rec = existing[0]
        n = rec.get("sample_size", 0)
        new_n = n + 1

        old_mean = rec.get("actual_lot_mean") or 0.0
        new_mean = old_mean + (lot_size - old_mean) / new_n if new_n > 0 else lot_size

        db.upsert_procedural({
            "id": proc_id,
            "strategy": strategy_name,
            "symbol": symbol,
            "behavior_type": "trade_execution",
            "sample_size": new_n,
            "avg_hold_winners": rec.get("avg_hold_winners") or 0.0,
            "avg_hold_losers": rec.get("avg_hold_losers") or 0.0,
            "disposition_ratio": rec.get("disposition_ratio"),
            "actual_lot_mean": new_mean,
            "actual_lot_variance": rec.get("actual_lot_variance") or 0.0,
            "kelly_fraction_suggested": rec.get("kelly_fraction_suggested"),
            "lot_vs_kelly_ratio": rec.get("lot_vs_kelly_ratio"),
        })
    else:
        db.upsert_procedural({
            "id": proc_id,
            "strategy": strategy_name,
            "symbol": symbol,
            "behavior_type": "trade_execution",
            "sample_size": 1,
            "avg_hold_winners": 0.0,
            "avg_hold_losers": 0.0,
            "disposition_ratio": None,
            "actual_lot_mean": lot_size,
            "actual_lot_variance": 0.0,
            "kelly_fraction_suggested": None,
            "lot_vs_kelly_ratio": None,
        })


def _update_affective_from_trade(
    db: Database,
    pnl: float,
    confidence: float,
) -> None:
    """Update affective state: EWMA confidence, streaks, equity/drawdown."""
    state = db.load_affective()

    ewma_alpha = 0.3

    if state is None:
        db.init_affective(peak_equity=10000.0, current_equity=10000.0)
        state = db.load_affective()
        if state is None:
            return

    old_conf = state.get("confidence_level", 0.5)
    new_conf = ewma_alpha * confidence + (1 - ewma_alpha) * old_conf
    new_conf = max(0.0, min(1.0, new_conf))

    if pnl > 0:
        consec_wins = state.get("consecutive_wins", 0) + 1
        consec_losses = 0
    else:
        consec_wins = 0
        consec_losses = state.get("consecutive_losses", 0) + 1

    current_equity = state.get("current_equity", 10000.0) + pnl
    peak_equity = max(state.get("peak_equity", current_equity), current_equity)
    drawdown_state = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0.0

    db.save_affective({
        "confidence_level": new_conf,
        "risk_appetite": state.get("risk_appetite", 1.0),
        "momentum_bias": state.get("momentum_bias", 0.0),
        "peak_equity": peak_equity,
        "current_equity": current_equity,
        "drawdown_state": drawdown_state,
        "max_acceptable_drawdown": state.get("max_acceptable_drawdown", 0.20),
        "consecutive_wins": consec_wins,
        "consecutive_losses": consec_losses,
        "history_json": state.get("history_json", []),
    })


# ---------------------------------------------------------------------------
# Original tools (backward compatible)
# ---------------------------------------------------------------------------


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
    Uses OWM scoring when episodic memories exist, falls back to keyword matching.

    Args:
        symbol: Trading instrument to filter by (e.g. "XAUUSD")
        market_context: Current market conditions to match against
        strategy_name: Optional strategy filter
        limit: Max number of results (default 5)
    """
    db = _get_db()
    symbol_upper = symbol.upper()

    # Check if episodic memory has data — use OWM if available
    episodic_check = db.query_episodic(strategy=strategy_name, limit=1)
    if episodic_check:
        # Parse session hint from market_context text
        _mc = (market_context or "").lower()
        _session = None
        if "london" in _mc:
            _session = "london"
        elif "asian" in _mc or "asia" in _mc:
            _session = "asian"
        elif "newyork" in _mc or "new york" in _mc:
            _session = "newyork"
        query_context = ContextVector(symbol=symbol_upper, session=_session)
        all_episodic = db.query_episodic(strategy=strategy_name, limit=limit * 5)

        candidates = []
        for ep in all_episodic:
            ctx = ep.get("context_json") or {}
            ep_symbol = ctx.get("symbol")
            if ep_symbol and ep_symbol != symbol_upper:
                continue
            candidates.append({
                "id": ep["id"],
                "memory_type": "episodic",
                "timestamp": _ensure_tz(ep.get("timestamp")),
                "confidence": ep.get("confidence", 0.5),
                "context": ctx,
                "pnl_r": ep.get("pnl_r"),
                "pnl": ep.get("pnl"),
                "strategy": ep.get("strategy"),
                "direction": ep.get("direction"),
                "reflection": ep.get("reflection"),
            })

        affective = db.load_affective()
        aff_state = None
        if affective:
            aff_state = {
                "drawdown_state": affective.get("drawdown_state", 0.0),
                "consecutive_losses": affective.get("consecutive_losses", 0),
            }

        scored = outcome_weighted_recall(
            query_context=query_context,
            memories=candidates,
            affective_state=aff_state,
            limit=limit,
        )

        results = []
        for sm in scored:
            results.append({
                "trade_id": sm.memory_id,
                "symbol": sm.data.get("context", {}).get("symbol", symbol_upper),
                "direction": sm.data.get("direction"),
                "strategy": sm.data.get("strategy"),
                "entry_context": sm.data.get("context", {}),
                "pnl": sm.data.get("pnl"),
                "exit_reasoning": sm.data.get("reflection"),
                "lessons": sm.data.get("reflection"),
                "grade": None,
                "relevance_score": sm.score,
                "owm_components": sm.components,
                "timestamp": sm.data.get("timestamp"),
            })

        return {
            "query_symbol": symbol_upper,
            "query_context": market_context,
            "matches_found": len(results),
            "recall_method": "owm",
            "trades": results,
        }

    # Fallback: original keyword matching on trade_records
    trades = db.query_trades(strategy=strategy_name, symbol=symbol_upper, limit=limit * 3)

    keywords = set(market_context.lower().split())
    scored_kw = []
    for t in trades:
        ctx = t.get("market_context", {})
        ctx_text = ""
        if isinstance(ctx, dict):
            ctx_text = ctx.get("description", str(ctx))
        elif isinstance(ctx, str):
            ctx_text = ctx
        ctx_words = set(ctx_text.lower().split())
        overlap = len(keywords & ctx_words)
        scored_kw.append((overlap, t))

    scored_kw.sort(key=lambda x: x[0], reverse=True)
    top = scored_kw[:limit]

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
        "query_symbol": symbol_upper,
        "query_context": market_context,
        "matches_found": len(results),
        "recall_method": "keyword",
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


# ---------------------------------------------------------------------------
# New OWM-powered tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def remember_trade(
    symbol: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    pnl: float,
    strategy_name: str,
    market_context: str,
    pnl_r: Optional[float] = None,
    context_regime: Optional[str] = None,
    context_atr_d1: Optional[float] = None,
    confidence: float = 0.5,
    reflection: Optional[str] = None,
    max_adverse_excursion: Optional[float] = None,
    trade_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> dict:
    """Store a trade into OWM multi-layer memory with automatic updates.

    Writes to episodic memory and automatically updates semantic (Bayesian),
    procedural (running averages), and affective (EWMA confidence/streaks).
    Also writes to trade_records for backward compatibility.

    Args:
        symbol: Trading instrument (e.g. "XAUUSD")
        direction: "long" or "short"
        entry_price: Entry price of the trade
        exit_price: Exit price of the trade
        pnl: Profit/loss in account currency
        strategy_name: Strategy used (e.g. "VolBreakout")
        market_context: Description of market conditions
        pnl_r: P&L as R-multiple (risk units). Improves OWM scoring quality.
        context_regime: Market regime (trending_up/trending_down/ranging/volatile)
        context_atr_d1: ATR(14) on D1 in dollars
        confidence: Agent confidence level 0-1 (default 0.5)
        reflection: Lessons learned from this trade
        max_adverse_excursion: Maximum adverse excursion during the trade
        trade_id: Optional custom ID. Auto-generated if omitted.
        timestamp: ISO format timestamp. Defaults to now (UTC).
    """
    db = _get_db()

    tid = trade_id or f"owm-{uuid.uuid4().hex[:12]}"
    ts = timestamp or datetime.now(timezone.utc).isoformat()

    direction_lower = direction.lower()
    if direction_lower not in ("long", "short"):
        return {"error": f"direction must be 'long' or 'short', got '{direction}'"}

    symbol_upper = symbol.upper()

    # Build context dict for episodic memory
    context_dict = {
        "symbol": symbol_upper,
        "price": entry_price,
        "regime": context_regime,
        "atr_d1": context_atr_d1,
        "description": market_context,
    }

    # 1) Insert into episodic_memory
    episodic_data = {
        "id": tid,
        "timestamp": ts,
        "context_json": context_dict,
        "context_regime": context_regime,
        "context_volatility_regime": None,
        "context_session": None,
        "context_atr_d1": context_atr_d1,
        "context_atr_h1": None,
        "strategy": strategy_name,
        "direction": direction_lower,
        "entry_price": entry_price,
        "lot_size": 0.0,
        "exit_price": exit_price,
        "pnl": pnl,
        "pnl_r": pnl_r,
        "hold_duration_seconds": None,
        "max_adverse_excursion": max_adverse_excursion,
        "reflection": reflection,
        "confidence": confidence,
        "tags": [],
        "retrieval_strength": 1.0,
        "retrieval_count": 0,
        "last_retrieved": None,
    }
    db.insert_episodic(episodic_data)

    # 2) Update semantic (Bayesian), procedural (running avg), affective (EWMA)
    _update_semantic_from_trade(db, symbol_upper, strategy_name, pnl, pnl_r, context_regime, tid)
    _update_procedural_from_trade(db, symbol_upper, strategy_name, pnl)
    _update_affective_from_trade(db, pnl, confidence)

    # 3) Backward compatibility: also store in trade_records
    trade_data = {
        "id": tid,
        "timestamp": ts,
        "symbol": symbol_upper,
        "direction": direction_lower,
        "lot_size": 0.0,
        "strategy": strategy_name,
        "confidence": confidence,
        "reasoning": market_context,
        "market_context": {"description": market_context, "entry_price": entry_price},
        "references": [],
        "exit_timestamp": None,
        "exit_price": exit_price,
        "pnl": pnl,
        "pnl_r": pnl_r,
        "hold_duration": None,
        "exit_reasoning": reflection,
        "slippage": None,
        "execution_quality": None,
        "lessons": reflection,
        "tags": [],
        "grade": None,
    }
    db.insert_trade(trade_data)

    # 4) Auto-generate embedding for hybrid recall (best-effort)
    try:
        embed_input = {
            "strategy": strategy_name,
            "direction": direction_lower,
            "context_regime": context_regime,
            "reflection": reflection,
        }
        embedding = embed_trade_context(embed_input)
        if embedding is not None:
            db.update_episodic_embedding(tid, embedding)
            logger.info(f"Embedding stored for trade {tid} (dim={len(embedding)})")
    except Exception as e:
        logger.warning(f"Embedding generation skipped for trade {tid}: {e}")

    return {
        "memory_id": tid,
        "symbol": symbol_upper,
        "direction": direction_lower,
        "strategy": strategy_name,
        "stored_at": ts,
        "memory_layers": ["episodic", "semantic", "procedural", "affective", "trade_records"],
        "status": "stored",
    }


@mcp.tool()
async def recall_memories(
    symbol: str,
    market_context: str,
    context_regime: Optional[str] = None,
    context_atr_d1: Optional[float] = None,
    strategy_name: Optional[str] = None,
    memory_types: Optional[List[str]] = None,
    limit: int = 10,
) -> dict:
    """Recall memories using OWM outcome-weighted scoring.

    Queries episodic and semantic memories, scores them by outcome quality,
    context similarity, recency, confidence, and affective modulation.
    Returns ranked memories with score breakdown.

    Args:
        symbol: Trading instrument (e.g. "XAUUSD")
        market_context: Current market conditions to match against
        context_regime: Current market regime (trending_up/trending_down/ranging/volatile)
        context_atr_d1: Current ATR(14) on D1 in dollars
        strategy_name: Optional strategy filter
        memory_types: Types to query (default: ["episodic", "semantic"])
        limit: Max results (default 10)
    """
    db = _get_db()
    symbol_upper = symbol.upper()

    if memory_types is None:
        memory_types = ["episodic", "semantic"]

    # Parse session hint from market_context text
    _mc = (market_context or "").lower()
    _session = None
    if "london" in _mc:
        _session = "london"
    elif "asian" in _mc or "asia" in _mc:
        _session = "asian"
    elif "newyork" in _mc or "new york" in _mc:
        _session = "newyork"

    query_context = ContextVector(
        symbol=symbol_upper,
        regime=context_regime,
        atr_d1=context_atr_d1,
        session=_session,
    )

    candidates: List[Dict[str, Any]] = []

    if "episodic" in memory_types:
        # Don't filter by regime at DB level — let OWM similarity scoring rank by context
        episodic = db.query_episodic(strategy=strategy_name, limit=limit * 5)
        for ep in episodic:
            ctx = ep.get("context_json") or {}
            ep_symbol = ctx.get("symbol")
            if ep_symbol and ep_symbol != symbol_upper:
                continue
            candidates.append({
                "id": ep["id"],
                "memory_type": "episodic",
                "timestamp": _ensure_tz(ep.get("timestamp")),
                "confidence": ep.get("confidence", 0.5),
                "context": ctx,
                "pnl_r": ep.get("pnl_r"),
                "pnl": ep.get("pnl"),
                "strategy": ep.get("strategy"),
                "direction": ep.get("direction"),
                "reflection": ep.get("reflection"),
            })

    if "semantic" in memory_types:
        semantic = db.query_semantic(strategy=strategy_name, symbol=symbol_upper, limit=limit * 3)
        for sem in semantic:
            candidates.append({
                "id": sem["id"],
                "memory_type": "semantic",
                "timestamp": _ensure_tz(sem.get("updated_at") or sem.get("created_at")),
                "confidence": sem.get("confidence", 0.5),
                "context": {
                    "symbol": sem.get("symbol"),
                    "regime": sem.get("regime"),
                    "volatility_regime": sem.get("volatility_regime"),
                },
                "proposition": sem.get("proposition"),
                "alpha": sem.get("alpha"),
                "beta": sem.get("beta"),
                "sample_size": sem.get("sample_size"),
            })

    affective = db.load_affective()
    affective_state = None
    if affective:
        affective_state = {
            "drawdown_state": affective.get("drawdown_state", 0.0),
            "consecutive_losses": affective.get("consecutive_losses", 0),
        }

    scored = hybrid_recall(
        query_context=query_context,
        query_embedding=None,  # No embedding yet — falls back to pure OWM
        memories=candidates,
        affective_state=affective_state,
        limit=limit,
    )

    results = []
    for sm in scored:
        entry: Dict[str, Any] = {
            "memory_id": sm.memory_id,
            "memory_type": sm.memory_type,
            "score": round(sm.score, 6),
            "components": {k: round(v, 6) for k, v in sm.components.items()},
        }
        if sm.memory_type == "episodic":
            entry["strategy"] = sm.data.get("strategy")
            entry["direction"] = sm.data.get("direction")
            entry["pnl"] = sm.data.get("pnl")
            entry["pnl_r"] = sm.data.get("pnl_r")
            entry["reflection"] = sm.data.get("reflection")
        elif sm.memory_type == "semantic":
            entry["proposition"] = sm.data.get("proposition")
            entry["confidence"] = sm.data.get("confidence")
            entry["sample_size"] = sm.data.get("sample_size")
        results.append(entry)

    # Side effect: log recall event (handler layer, not in hybrid_recall)
    try:
        avg_score = (
            sum(r["score"] for r in results) / len(results) if results else 0.0
        )
        conn = db._get_connection()
        try:
            conn.execute(
                """INSERT INTO recall_events
                   (timestamp, query_symbol, query_context, query_regime,
                    num_candidates, num_returned, avg_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    symbol_upper,
                    market_context,
                    context_regime,
                    len(candidates),
                    len(results),
                    round(avg_score, 6),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        # Side effect failure must not affect recall response
        logger.debug(f"recall_events logging skipped: {e}")

    return {
        "query_symbol": symbol_upper,
        "query_context": market_context,
        "query_regime": context_regime,
        "memory_types_queried": memory_types,
        "matches_found": len(results),
        "affective_state": affective_state,
        "memories": results,
    }


@mcp.tool()
async def get_behavioral_analysis(
    strategy_name: Optional[str] = None,
    symbol: Optional[str] = None,
) -> dict:
    """Get behavioral analysis from procedural memory.

    Returns aggregate trading behavior stats: hold times, disposition ratio,
    lot sizing variance, and Kelly criterion comparison.

    Args:
        strategy_name: Filter by strategy name. Returns all if omitted.
        symbol: Filter by symbol. Returns all if omitted.
    """
    db = _get_db()
    records = db.query_procedural(
        strategy=strategy_name,
        symbol=symbol.upper() if symbol else None,
        limit=100,
    )

    if not records:
        return {"status": "no_data", "message": "No behavioral data yet"}

    results = []
    for rec in records:
        results.append({
            "strategy": rec.get("strategy"),
            "symbol": rec.get("symbol"),
            "avg_hold_winners": rec.get("avg_hold_winners"),
            "avg_hold_losers": rec.get("avg_hold_losers"),
            "disposition_ratio": rec.get("disposition_ratio"),
            "lot_sizing_variance": rec.get("actual_lot_variance"),
            "kelly_fraction_suggested": rec.get("kelly_fraction_suggested"),
            "lot_vs_kelly_ratio": rec.get("lot_vs_kelly_ratio"),
            "sample_size": rec.get("sample_size", 0),
        })

    return {
        "status": "ok",
        "count": len(results),
        "behaviors": results,
    }


@mcp.tool()
async def get_agent_state() -> dict:
    """Get the current agent affective state (confidence, risk, drawdown).

    Returns confidence level, risk appetite, drawdown percentage,
    win/loss streaks, equity tracking, and a recommended action
    based on current drawdown severity.
    """
    db = _get_db()
    state = db.load_affective()

    if state is None:
        db.init_affective(peak_equity=10000.0, current_equity=10000.0)
        state = db.load_affective()
        if state is None:
            return {"status": "error", "message": "Failed to initialize affective state"}

    drawdown_pct = state.get("drawdown_state", 0.0)

    if drawdown_pct > 0.6:
        recommended_action = "stop_trading"
    elif drawdown_pct > 0.3:
        recommended_action = "reduce_size"
    else:
        recommended_action = "normal"

    return {
        "status": "ok",
        "confidence_level": state.get("confidence_level", 0.5),
        "risk_appetite": state.get("risk_appetite", 1.0),
        "drawdown_pct": drawdown_pct,
        "consecutive_wins": state.get("consecutive_wins", 0),
        "consecutive_losses": state.get("consecutive_losses", 0),
        "current_equity": state.get("current_equity", 0.0),
        "peak_equity": state.get("peak_equity", 0.0),
        "recommended_action": recommended_action,
    }


@mcp.tool()
async def create_trading_plan(
    trigger_type: str,
    trigger_condition: str,
    planned_action: str,
    reasoning: str,
    expiry_days: int = 30,
    priority: float = 0.5,
) -> dict:
    """Create a prospective trading plan that activates when conditions are met.

    Stores a rule-based plan in prospective memory. The plan stays active
    until triggered, expired, or manually cancelled.

    Args:
        trigger_type: Type of trigger (e.g. "market_condition", "drawdown", "time_based")
        trigger_condition: JSON string describing when to trigger (e.g. '{"regime": "ranging"}')
        planned_action: JSON string describing what to do (e.g. '{"type": "skip_trade"}')
        reasoning: Why this plan was created
        expiry_days: Days until plan expires (default 30)
        priority: Priority 0-1, higher = checked first (default 0.5)
    """
    db = _get_db()

    plan_id = f"plan-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    expiry = (now + timedelta(days=expiry_days)).isoformat()

    # Parse JSON strings to validate them, store as dicts
    try:
        trigger_cond_parsed = json.loads(trigger_condition)
    except (json.JSONDecodeError, TypeError):
        return {"error": f"trigger_condition must be valid JSON, got: {trigger_condition}"}

    try:
        planned_act_parsed = json.loads(planned_action)
    except (json.JSONDecodeError, TypeError):
        return {"error": f"planned_action must be valid JSON, got: {planned_action}"}

    data = {
        "id": plan_id,
        "trigger_type": trigger_type,
        "trigger_condition": trigger_cond_parsed,
        "planned_action": planned_act_parsed,
        "action_type": planned_act_parsed.get("type", trigger_type),
        "status": "active",
        "priority": priority,
        "expiry": expiry,
        "source_episodic_ids": [],
        "source_semantic_ids": [],
        "reasoning": reasoning,
        "triggered_at": None,
        "outcome_pnl_r": None,
        "outcome_reflection": None,
    }
    success = db.insert_prospective(data)

    if not success:
        return {"error": "Failed to insert prospective plan"}

    return {
        "plan_id": plan_id,
        "status": "active",
        "expiry": expiry,
        "message": f"Trading plan created: {trigger_type} → {planned_act_parsed.get('type', 'action')}",
    }


@mcp.tool()
async def check_active_plans(
    context_regime: Optional[str] = None,
    context_atr_d1: Optional[float] = None,
) -> dict:
    """Check active trading plans against current market context.

    Queries all active prospective plans, expires any past their expiry date,
    and matches remaining plans against the provided context.

    Args:
        context_regime: Current market regime (trending_up/trending_down/ranging/volatile)
        context_atr_d1: Current ATR(14) on D1 in dollars
    """
    db = _get_db()
    plans = db.query_prospective(status="active", limit=1000)

    now = datetime.now(timezone.utc)
    triggered = []
    pending = []

    for plan in plans:
        # Check expiry
        expiry_str = plan.get("expiry")
        if expiry_str:
            try:
                expiry_dt = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                if expiry_dt.tzinfo is None:
                    expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                if now > expiry_dt:
                    db.update_prospective_status(plan["id"], "expired")
                    continue
            except (ValueError, TypeError):
                pass

        # Check trigger_condition against context
        trigger_cond = plan.get("trigger_condition", {})
        if isinstance(trigger_cond, str):
            try:
                trigger_cond = json.loads(trigger_cond)
            except (json.JSONDecodeError, TypeError):
                trigger_cond = {}

        matches = True
        if trigger_cond:
            cond_regime = trigger_cond.get("regime")
            if cond_regime and context_regime and cond_regime != context_regime:
                matches = False

            cond_atr_min = trigger_cond.get("atr_d1_min")
            if cond_atr_min is not None and context_atr_d1 is not None:
                if context_atr_d1 < cond_atr_min:
                    matches = False

            cond_atr_max = trigger_cond.get("atr_d1_max")
            if cond_atr_max is not None and context_atr_d1 is not None:
                if context_atr_d1 > cond_atr_max:
                    matches = False

            # If no context provided and condition has requirements, don't match
            if cond_regime and context_regime is None:
                matches = False
            if (cond_atr_min is not None or cond_atr_max is not None) and context_atr_d1 is None:
                matches = False

        plan_summary = {
            "plan_id": plan["id"],
            "trigger_type": plan.get("trigger_type"),
            "trigger_condition": trigger_cond,
            "planned_action": plan.get("planned_action"),
            "priority": plan.get("priority"),
            "reasoning": plan.get("reasoning"),
            "expiry": plan.get("expiry"),
        }

        if matches:
            triggered.append(plan_summary)
        else:
            pending.append(plan_summary)

    return {
        "active_count": len(triggered) + len(pending),
        "triggered": triggered,
        "pending": pending,
    }


# ---------------------------------------------------------------------------
# Evolution Engine tools (Phase 11 — P2)
# ---------------------------------------------------------------------------


@mcp.tool()
async def evolution_fetch_market_data(
    symbol: str,
    timeframe: str = "1h",
    days: int = 90,
) -> dict:
    """Fetch OHLCV market data from Binance for evolution analysis.

    Downloads historical price bars for backtesting and pattern discovery.
    Use this before discover_patterns or run_backtest to get data.

    Args:
        symbol: Trading pair (e.g. "BTCUSDT", "ETHUSDT")
        timeframe: Bar timeframe — "5m", "15m", "1h", "4h", "1d"
        days: Number of days of history to fetch (default 90)
    """
    from .evolution.mcp_tools import fetch_market_data

    result = await fetch_market_data(symbol, timeframe, days)
    # Strip OHLCVSeries from response (not JSON-serializable)
    result_copy = {k: v for k, v in result.items() if k != "series"}
    return result_copy


@mcp.tool()
async def evolution_discover_patterns(
    symbol: str,
    timeframe: str = "1h",
    count: int = 5,
    temperature: float = 0.7,
    days: int = 90,
) -> dict:
    """Discover trading patterns from market data using LLM analysis.

    Uses Claude to analyze OHLCV data and generate candidate trading patterns
    with entry/exit conditions. Each pattern can be backtested afterward.

    Args:
        symbol: Trading pair (e.g. "BTCUSDT")
        timeframe: Bar timeframe — "5m", "15m", "1h", "4h", "1d"
        count: Number of patterns to generate (default 5)
        temperature: LLM creativity 0-1 (default 0.7, higher = more diverse)
        days: Days of history to analyze (default 90)
    """
    from .evolution.llm import AnthropicClient
    from .evolution.mcp_tools import discover_patterns

    llm = AnthropicClient()
    return await discover_patterns(
        symbol, timeframe, count, temperature,
        llm=llm, days=days,
    )


@mcp.tool()
async def evolution_run_backtest(
    pattern_dict: dict,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    days: int = 90,
) -> dict:
    """Backtest a candidate pattern against historical OHLCV data.

    Takes a pattern dict (from discover_patterns) and runs a vectorized
    backtest. Returns fitness metrics: Sharpe ratio, win rate, trade count,
    max drawdown, total PnL.

    Args:
        pattern_dict: CandidatePattern as dict (from discover_patterns output)
        symbol: Trading pair (e.g. "BTCUSDT")
        timeframe: Bar timeframe — "5m", "15m", "1h", "4h", "1d"
        days: Days of history to backtest against (default 90)
    """
    from .evolution.mcp_tools import run_backtest

    return await run_backtest(pattern_dict, symbol, timeframe, days)


@mcp.tool()
async def evolution_evolve_strategy(
    symbol: str,
    timeframe: str = "1h",
    generations: int = 3,
    population_size: int = 10,
    days: int = 90,
) -> dict:
    """Run full evolution loop — generate, backtest, select, eliminate.

    Multi-generation strategy evolution: generates candidate patterns via LLM,
    backtests on in-sample data, validates survivors on out-of-sample data,
    eliminates weak hypotheses. Returns graduated strategies and graveyard.

    Args:
        symbol: Trading pair (e.g. "BTCUSDT")
        timeframe: Bar timeframe — "5m", "15m", "1h", "4h", "1d"
        generations: Number of evolution generations (default 3)
        population_size: Hypotheses per generation (default 10)
        days: Days of history to use (default 90)
    """
    from .evolution.llm import AnthropicClient
    from .evolution.mcp_tools import evolve_strategy

    llm = AnthropicClient()
    return await evolve_strategy(
        symbol, timeframe, generations, population_size,
        llm=llm, days=days,
    )


@mcp.tool()
async def evolution_get_log() -> dict:
    """Get the log of past evolution runs from this session.

    Returns a list of all evolution runs with their results, including
    graduated strategies, graveyard, token usage, and backtest counts.
    Data is in-memory (resets on server restart).
    """
    from .evolution.mcp_tools import get_evolution_log

    return get_evolution_log()


def main():
    """Entry point for MCP server."""
    mcp.run()
