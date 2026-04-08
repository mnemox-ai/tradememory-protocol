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
from .owm.drift import compute_context_drift, compute_drift_summary
from .owm_helpers import (
    ensure_tz,
    update_affective_from_trade,
    update_procedural_from_trade,
    update_semantic_from_trade,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("tradememory-protocol")

# Shared instance — initialized on first use
_db: Optional[Database] = None


def _get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db



# ---------------------------------------------------------------------------
# Legacy tools removed in 2026-04-08 audit refactor:
#   - store_trade_memory → use remember_trade (writes all 5 memory layers)
#   - recall_similar_trades → use recall_memories (OWM scoring + drift)
# ---------------------------------------------------------------------------


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
    entry_timestamp: Optional[str] = None,
    exit_timestamp: Optional[str] = None,
) -> dict:
    """Store a trade into OWM multi-layer memory with automatic updates.

    Writes to episodic memory and automatically updates semantic (Bayesian),
    procedural (running averages + hold time + Kelly), and affective
    (EWMA confidence/streaks). Also writes to trade_records for backward
    compatibility.

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
        entry_timestamp: ISO format entry time. Used to compute hold duration.
        exit_timestamp: ISO format exit time. Used to compute hold duration.
    """
    db = _get_db()

    tid = trade_id or f"owm-{uuid.uuid4().hex[:12]}"
    ts = timestamp or datetime.now(timezone.utc).isoformat()

    direction_lower = direction.lower()
    if direction_lower not in ("long", "short"):
        return {"error": f"direction must be 'long' or 'short', got '{direction}'"}

    symbol_upper = symbol.upper()

    # Compute hold duration if timestamps provided
    hold_seconds = None
    if entry_timestamp and exit_timestamp:
        try:
            entry_dt = datetime.fromisoformat(entry_timestamp)
            exit_dt = datetime.fromisoformat(exit_timestamp)
            hold_seconds = int((exit_dt - entry_dt).total_seconds())
            if hold_seconds < 0:
                hold_seconds = None
        except (ValueError, TypeError):
            hold_seconds = None

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
        "hold_duration_seconds": hold_seconds,
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
    update_semantic_from_trade(db, symbol_upper, strategy_name, pnl, pnl_r, context_regime, tid)
    update_procedural_from_trade(
        db, symbol_upper, strategy_name, pnl,
        hold_duration_seconds=episodic_data.get("hold_duration_seconds"),
        pnl_r=pnl_r,
    )
    update_affective_from_trade(db, pnl, confidence)

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
                "timestamp": ensure_tz(ep.get("timestamp")),
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
            # Check drift_flag — discount confidence if recent performance diverges
            vc = sem.get("validity_conditions") or {}
            drift_flag = vc.get("drift_flag", False) if isinstance(vc, dict) else False
            confidence = sem.get("confidence", 0.5)
            if drift_flag:
                confidence *= 0.7  # 30% discount on drifting beliefs

            candidates.append({
                "id": sem["id"],
                "memory_type": "semantic",
                "timestamp": ensure_tz(sem.get("updated_at") or sem.get("created_at")),
                "confidence": confidence,
                "context": {
                    "symbol": sem.get("symbol"),
                    "regime": sem.get("regime"),
                    "volatility_regime": sem.get("volatility_regime"),
                },
                "proposition": sem.get("proposition"),
                "alpha": sem.get("alpha"),
                "beta": sem.get("beta"),
                "sample_size": sem.get("sample_size"),
                "drift_flag": drift_flag,
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
    drift_results = []
    for sm in scored:
        # Build memory context string for drift comparison
        mem_ctx = sm.data.get("context", {})
        if sm.memory_type == "semantic":
            # Semantic memories store context differently
            mem_ctx = {
                "symbol": sm.data.get("context", {}).get("symbol"),
                "regime": sm.data.get("context", {}).get("regime"),
                "volatility_regime": sm.data.get("context", {}).get("volatility_regime"),
            }
        mem_ctx_str = (
            json.dumps(mem_ctx) if isinstance(mem_ctx, dict) else str(mem_ctx)
        )
        drift = compute_context_drift(mem_ctx_str, market_context)
        drift_results.append(drift)

        entry: Dict[str, Any] = {
            "memory_id": sm.memory_id,
            "memory_type": sm.memory_type,
            "score": round(sm.score, 6),
            "components": {k: round(v, 6) for k, v in sm.components.items()},
            "context_drift": drift,
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
        "drift_summary": compute_drift_summary(drift_results),
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


# =====================================================================
# Audit tools — Trading Decision Records (Phase 2)
# =====================================================================

@mcp.tool()
async def export_audit_trail(
    trade_id: Optional[str] = None,
    strategy: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """Export Trading Decision Records for audit and compliance review.

    Provides a complete, tamper-evident record of trading decisions including
    the memory context (similar trades, beliefs) that informed each decision.

    Args:
        trade_id: Get a single TDR by trade ID (e.g., "MT5-7047640363").
            If provided, other filters are ignored.
        strategy: Filter by strategy name (e.g., "VolBreakout").
        start: Start date (ISO format, inclusive). E.g., "2026-03-01".
        end: End date (ISO format, exclusive). E.g., "2026-04-01".
        limit: Maximum records to return (default 50).

    Returns:
        dict with 'records' (list of TDR dicts) and 'count'.
        Each record includes data_hash for tamper verification.
    """
    import json as _json
    from .domain.tdr import TradingDecisionRecord, MemoryContext

    database = _get_db()

    if trade_id:
        trade = database.get_trade(trade_id)
        if not trade:
            return {"error": f"Trade {trade_id} not found", "records": [], "count": 0}
        records = [trade]
    else:
        records = database.query_trades(strategy=strategy, limit=limit)
        if start or end:
            filtered = []
            for t in records:
                ts = t.get("timestamp", "")
                if start and ts < start:
                    continue
                if end and ts >= end:
                    continue
                filtered.append(t)
            records = filtered

    tdrs = []
    for trade in records:
        refs = trade.get("references", [])
        if isinstance(refs, str):
            refs = _json.loads(refs)

        beliefs = []
        try:
            sem = database.query_semantic(strategy=trade.get("strategy"), limit=5)
            beliefs = [
                f"{b.get('proposition', '')} (conf={b.get('confidence', 0):.2f})"
                for b in sem
            ]
        except Exception:
            pass

        mem = MemoryContext(
            similar_trades=refs,
            relevant_beliefs=beliefs,
            anti_resonance_applied=len(refs) > 0,
            recall_count=len(refs),
        )
        tdr = TradingDecisionRecord.from_trade_record(trade, memory_ctx=mem)
        tdrs.append(tdr.model_dump(mode="json"))

    return {"records": tdrs, "count": len(tdrs)}


@mcp.tool()
async def verify_audit_hash(trade_id: str) -> dict:
    """Verify the integrity of a Trading Decision Record.

    Recomputes the SHA256 data_hash from stored inputs and compares with
    the hash computed at decision time. A mismatch indicates tampering.

    Args:
        trade_id: Trade ID to verify (e.g., "MT5-7047640363").

    Returns:
        dict with 'verified' (bool), 'stored_hash', 'recomputed_hash'.
    """
    import json as _json
    from .domain.tdr import TradingDecisionRecord

    database = _get_db()
    trade = database.get_trade(trade_id)
    if not trade:
        return {"error": f"Trade {trade_id} not found", "verified": False}

    market_context = trade.get("market_context", {})
    if isinstance(market_context, str):
        market_context = _json.loads(market_context)

    recomputed = TradingDecisionRecord.compute_hash(
        trade_id=trade.get("id", ""),
        timestamp=trade.get("timestamp", ""),
        symbol=trade.get("symbol", ""),
        direction=trade.get("direction", ""),
        strategy=trade.get("strategy", ""),
        confidence=trade.get("confidence", 0.0),
        reasoning=trade.get("reasoning", ""),
        market_context=market_context,
    )

    # Build TDR from stored trade to get the stored hash
    # This mirrors the REST /audit/verify endpoint logic
    refs = trade.get("references", [])
    if isinstance(refs, str):
        refs = _json.loads(refs)

    beliefs = []
    try:
        sem = database.query_semantic(strategy=trade.get("strategy"), limit=5)
        beliefs = [
            f"{b.get('proposition', '')} (conf={b.get('confidence', 0):.2f})"
            for b in sem
        ]
    except Exception:
        pass

    from .domain.tdr import MemoryContext
    mem = MemoryContext(
        similar_trades=refs,
        relevant_beliefs=beliefs,
        anti_resonance_applied=len(refs) > 0,
        negative_ratio=None,
        recall_count=len(refs),
    )
    tdr = TradingDecisionRecord.from_trade_record(trade, memory_ctx=mem)
    stored = tdr.data_hash

    return {
        "trade_id": trade_id,
        "stored_hash": stored,
        "recomputed_hash": recomputed,
        "verified": stored == recomputed,
    }


# ---------------------------------------------------------------------------
# Strategy Validation
# ---------------------------------------------------------------------------


@mcp.tool()
async def validate_strategy(
    file_path: str,
    format: str = "quantconnect",
    strategy_name: str = "",
    num_strategies: int = 1,
) -> dict:
    """Validate a trading strategy using statistical tests (DSR + Walk-Forward + Regime + CPCV).

    For educational and research purposes only. Not financial advice.

    Upload a trade log CSV (QuantConnect format) or daily returns CSV.
    The tool runs four statistical tests:
    1. Deflated Sharpe Ratio (DSR) — detects overfitting from multiple testing
    2. Walk-Forward Validation — checks out-of-sample consistency
    3. Regime Analysis — performance across bull/bear/crisis markets
    4. CPCV — cross-validated Sharpe stability across time periods

    Args:
        file_path: Absolute path to the CSV file on your local machine.
        format: CSV format — "quantconnect" for trade logs (columns: Entry Time, Exit Time,
                Direction, Entry Price, Exit Price, Quantity, P&L, Fees, IsWin) or
                "returns" for daily returns (columns: date,return or single column of returns).
        strategy_name: Name of the strategy (for the report).
        num_strategies: How many strategies you tested before picking this one.
                        Higher M = stricter DSR threshold (corrects for selection bias).

    Returns:
        Complete validation report with per-test verdicts and overall PASS/CAUTION/FAIL.
    """
    from .strategy_validator import validate_from_trades, validate_from_returns

    try:
        if format == "returns":
            return validate_from_returns(
                file_path=file_path,
                strategy_name=strategy_name,
                num_strategies=num_strategies,
            )
        else:
            return validate_from_trades(
                file_path=file_path,
                format=format,
                strategy_name=strategy_name,
                num_strategies=num_strategies,
            )
    except FileNotFoundError as e:
        return {"error": str(e), "hint": "Provide the full absolute path to your CSV file."}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.error("validate_strategy failed: %s", e)
        return {"error": f"Validation failed: {e}"}


# ---------------------------------------------------------------------------
# Decision Legitimacy Gate
# ---------------------------------------------------------------------------


@mcp.tool()
async def check_trade_legitimacy(
    strategy_name: str,
    symbol: str = "XAUUSD",
    current_regime: Optional[str] = None,
    current_atr_d1: Optional[float] = None,
) -> dict:
    """Check if the agent has sufficient data and confidence to trade.

    Call this before making any trade decision. Evaluates sample size,
    memory quality, regime experience, streak state, and drawdown to
    determine whether the agent has earned the right to trade at full size.

    Args:
        strategy_name: Strategy to evaluate (e.g. "VolBreakout").
        symbol: Trading instrument (default "XAUUSD").
        current_regime: Current market regime (trending_up/trending_down/ranging/volatile).
        current_atr_d1: Current ATR(14) on D1 in dollars (informational).

    Returns:
        Legitimacy assessment with score, tier (full/reduced/skip),
        factor breakdown, recommendation, and position_multiplier.
    """
    from .owm.legitimacy import compute_legitimacy_score

    db = _get_db()

    # 1. Total trades for this strategy
    trades = db.query_trades(strategy=strategy_name, symbol=symbol, limit=10000)
    memory_count = len(trades)

    # 2. Regime-specific trade count
    regime_trade_count = 0
    if current_regime:
        episodic = db.query_episodic(strategy=strategy_name, regime=current_regime, limit=10000)
        regime_trade_count = len(episodic)

    # 3. Win rate
    win_rate = None
    if memory_count > 0:
        wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
        win_rate = wins / memory_count

    # 4. Affective state (drawdown + streak)
    state = db.load_affective()
    if state is None:
        db.init_affective(peak_equity=10000.0, current_equity=10000.0)
        state = db.load_affective() or {}

    consecutive_losses = state.get("consecutive_losses", 0)
    drawdown_pct = state.get("drawdown_state", 0.0) * 100  # stored as 0-1, we need 0-100

    # 5. Average context drift — default 0.0 (no drift = good)
    # Drift computation requires ContextVector pairs; future enhancement.
    avg_context_drift = 0.0

    result = compute_legitimacy_score(
        strategy_name=strategy_name,
        current_regime=current_regime,
        memory_count=memory_count,
        avg_context_drift=avg_context_drift,
        win_rate=win_rate,
        consecutive_losses=consecutive_losses,
        drawdown_pct=drawdown_pct,
        regime_trade_count=regime_trade_count,
    )

    # Add context info
    result["context"] = {
        "symbol": symbol,
        "strategy": strategy_name,
        "regime": current_regime,
        "atr_d1": current_atr_d1,
        "total_trades": memory_count,
        "regime_trades": regime_trade_count,
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
        "consecutive_losses": consecutive_losses,
        "drawdown_pct": round(drawdown_pct, 2),
    }

    return result


def main():
    """Entry point for MCP server."""
    import sys
    from pathlib import Path
    _data_dir = Path.home() / ".tradememory"
    if not (_data_dir / ".setup_done").exists():
        print("First time? Run: tradememory setup", file=sys.stderr)
    mcp.run()
