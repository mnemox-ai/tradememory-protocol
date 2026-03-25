"""
TradeMemory MCP Server - FastAPI implementation.
Implements MCP tools from Blueprint Section 3.1.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .adaptive_risk import AdaptiveRisk
from .db import Database
from .journal import TradeJournal
from .models import SessionState, TradeDirection, TradeProposal
from .mt5_connector import MT5Connector
from .owm import ContextVector, outcome_weighted_recall
from .owm.migration import (
    initialize_affective,
    migrate_patterns_to_semantic,
    migrate_trades_to_episodic,
)
from .reflection import ReflectionEngine
from .state import StateManager

app = FastAPI(
    title="TradeMemory Protocol",
    description="AI Agent Trading Memory & Adaptive Decision Layer",
    version="0.5.0"
)

# CORS middleware — allow dashboard dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dashboard API router
from .dashboard_api import dashboard_router  # noqa: E402

app.include_router(dashboard_router)

# Initialize modules
journal = TradeJournal()
state_manager = StateManager()
reflection_engine = ReflectionEngine(journal=journal)
mt5_connector = MT5Connector(journal=journal, state_manager=state_manager)
adaptive_risk = AdaptiveRisk(journal=journal, state_manager=state_manager)


# ========== MCP Tool Request/Response Models ==========

class RecordDecisionRequest(BaseModel):
    """Request for trade.record_decision"""
    trade_id: str
    symbol: str
    direction: str
    lot_size: float
    strategy: str
    confidence: float
    reasoning: str
    market_context: Dict[str, Any]
    references: Optional[List[str]] = None


class RecordOutcomeRequest(BaseModel):
    """Request for trade.record_outcome"""
    trade_id: str
    exit_price: float
    pnl: float
    exit_reasoning: str
    pnl_r: Optional[float] = None
    hold_duration: Optional[int] = None
    slippage: Optional[float] = None
    execution_quality: Optional[float] = None
    lessons: Optional[str] = None


class QueryHistoryRequest(BaseModel):
    """Request for trade.query_history"""
    strategy: Optional[str] = None
    symbol: Optional[str] = None
    limit: int = 100


class LoadStateRequest(BaseModel):
    """Request for state.load"""
    agent_id: str


class SaveStateRequest(BaseModel):
    """Request for state.save"""
    state: Dict[str, Any]


# ========== MCP Tool Endpoints ==========

@app.post("/trade/record_decision")
async def trade_record_decision(req: RecordDecisionRequest):
    """
    MCP Tool: trade.record_decision
    Log a trade decision with reasoning and context.
    """
    try:
        trade = journal.record_decision(
            trade_id=req.trade_id,
            symbol=req.symbol,
            direction=req.direction,
            lot_size=req.lot_size,
            strategy=req.strategy,
            confidence=req.confidence,
            reasoning=req.reasoning,
            market_context=req.market_context,
            references=req.references
        )

        return {
            "success": True,
            "trade_id": trade.id,
            "timestamp": trade.timestamp.isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/trade/record_outcome")
async def trade_record_outcome(req: RecordOutcomeRequest):
    """
    MCP Tool: trade.record_outcome
    Log trade result after position closes.
    """
    try:
        success = journal.record_outcome(
            trade_id=req.trade_id,
            exit_price=req.exit_price,
            pnl=req.pnl,
            exit_reasoning=req.exit_reasoning,
            pnl_r=req.pnl_r,
            hold_duration=req.hold_duration,
            slippage=req.slippage,
            execution_quality=req.execution_quality,
            lessons=req.lessons
        )

        return {
            "success": success,
            "trade_id": req.trade_id
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/trade/query_history")
async def trade_query_history(req: QueryHistoryRequest):
    """
    MCP Tool: trade.query_history
    Search past trades by strategy/date/result.
    """
    try:
        trades = journal.query_history(
            strategy=req.strategy,
            symbol=req.symbol,
            limit=req.limit
        )

        return {
            "success": True,
            "count": len(trades),
            "trades": [t.model_dump() for t in trades]
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/trade/get_active")
async def trade_get_active():
    """
    MCP Tool: trade.get_active
    Get current open positions with context.
    """
    try:
        active_trades = journal.get_active_trades()

        return {
            "success": True,
            "count": len(active_trades),
            "trades": [t.model_dump() for t in active_trades]
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/state/load")
async def state_load(req: LoadStateRequest):
    """
    MCP Tool: state.load
    Load agent state at session start.
    """
    try:
        state = state_manager.load_state(req.agent_id)

        return {
            "success": True,
            "state": state.model_dump()
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/state/save")
async def state_save(req: SaveStateRequest):
    """
    MCP Tool: state.save
    Persist current state.
    """
    try:
        # Convert dict to SessionState model
        state = SessionState(**req.state)
        success = state_manager.save_state(state)

        return {
            "success": success,
            "agent_id": state.agent_id
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reflect/run_daily")
async def reflect_run_daily(date: Optional[str] = None):
    """
    MCP Tool: reflect.run_daily
    Generate daily reflection summary.

    Args:
        date: Optional YYYY-MM-DD string (default: today)
    """
    try:
        from datetime import date as date_type

        target_date = None
        if date:
            target_date = date_type.fromisoformat(date)

        summary = reflection_engine.generate_daily_summary(target_date=target_date)

        return {
            "success": True,
            "date": (target_date or date_type.today()).isoformat(),
            "summary": summary
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reflect/run_weekly")
async def reflect_run_weekly(week_ending: Optional[str] = None):
    """
    MCP Tool: reflect.run_weekly
    Generate weekly reflection summary.

    Args:
        week_ending: Optional YYYY-MM-DD string (default: last Sunday)
    """
    try:
        from datetime import date as date_type

        target = None
        if week_ending:
            target = date_type.fromisoformat(week_ending)

        summary = reflection_engine.generate_weekly_summary(week_ending=target)

        return {
            "success": True,
            "week_ending": (target or date_type.today()).isoformat(),
            "summary": summary,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reflect/run_monthly")
async def reflect_run_monthly(year: Optional[int] = None, month: Optional[int] = None):
    """
    MCP Tool: reflect.run_monthly
    Generate monthly reflection summary.

    Args:
        year: Optional year (default: current)
        month: Optional month (default: current)
    """
    try:
        from datetime import date as date_type

        summary = reflection_engine.generate_monthly_summary(year=year, month=month)

        effective_year = year or date_type.today().year
        effective_month = month or date_type.today().month

        return {
            "success": True,
            "year": effective_year,
            "month": effective_month,
            "summary": summary,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/mt5/sync")
async def mt5_sync(agent_id: str = "ng-gold-agent"):
    """
    MCP Tool: mt5.sync
    Sync MT5 demo trades to TradeJournal.

    Args:
        agent_id: Agent identifier for state tracking
    """
    try:
        stats = mt5_connector.sync_trades(agent_id=agent_id)

        return {
            "success": True,
            "agent_id": agent_id,
            "stats": stats
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class MT5ConnectRequest(BaseModel):
    """Request for mt5.connect"""
    login: int
    password: str
    server: str
    path: Optional[str] = None


@app.post("/mt5/connect")
async def mt5_connect(req: MT5ConnectRequest):
    """
    MCP Tool: mt5.connect
    Connect to MT5 demo account.
    """
    try:
        success = mt5_connector.connect(
            login=req.login,
            password=req.password,
            server=req.server,
            path=req.path
        )

        return {
            "success": success,
            "message": "Connected to MT5" if success else "Connection failed"
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== Risk Endpoints ==========

class GetConstraintsRequest(BaseModel):
    """Request for risk.get_constraints"""
    agent_id: str
    symbol: Optional[str] = None
    strategy: Optional[str] = None
    recalculate: bool = False


class CheckTradeRequest(BaseModel):
    """Request for risk.check_trade"""
    agent_id: str
    symbol: str
    direction: str
    lot_size: float
    strategy: str
    confidence: float
    session: Optional[str] = None


@app.post("/risk/get_constraints")
async def risk_get_constraints(req: GetConstraintsRequest):
    """
    MCP Tool: risk.get_constraints
    Get current dynamic risk constraints for an agent.
    """
    try:
        if req.recalculate:
            constraints = adaptive_risk.calculate_constraints(
                agent_id=req.agent_id,
                symbol=req.symbol,
                strategy=req.strategy,
            )
        else:
            constraints = adaptive_risk.get_constraints(req.agent_id)

        return {
            "success": True,
            "agent_id": req.agent_id,
            "constraints": constraints.model_dump(mode="json"),
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/risk/check_trade")
async def risk_check_trade(req: CheckTradeRequest):
    """
    MCP Tool: risk.check_trade
    Check a proposed trade against current risk constraints.
    """
    try:
        proposal = TradeProposal(
            symbol=req.symbol,
            direction=TradeDirection(req.direction),
            lot_size=req.lot_size,
            strategy=req.strategy,
            confidence=req.confidence,
            session=req.session,
        )
        result = adaptive_risk.check_trade(
            agent_id=req.agent_id,
            proposal=proposal,
        )

        return {
            "success": True,
            "approved": result.approved,
            "adjusted_lot_size": result.adjusted_lot_size,
            "reasons": result.reasons,
            "constraints": result.constraints_applied.model_dump(mode="json"),
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== Pattern Discovery Endpoints ==========

class DiscoverPatternsRequest(BaseModel):
    """Request for reflect.discover_patterns"""
    db_path: Optional[str] = None
    starting_balance: float = 10000.0


class QueryPatternsRequest(BaseModel):
    """Request for patterns.query"""
    strategy: Optional[str] = None
    symbol: Optional[str] = None
    pattern_type: Optional[str] = None


@app.post("/reflect/discover_patterns")
async def reflect_discover_patterns(req: DiscoverPatternsRequest):
    """
    Trigger L2 pattern discovery from backtest data.

    Args:
        db_path: Path to backtest database (default: tradememory.db)
        starting_balance: Baseline for PnL% calculation
    """
    try:
        db = Database(req.db_path) if req.db_path else None
        patterns = reflection_engine.discover_patterns_from_backtest(
            db=db, starting_balance=req.starting_balance
        )
        return {
            "success": True,
            "patterns_discovered": len(patterns),
            "patterns": patterns,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/patterns/query")
async def query_patterns(req: QueryPatternsRequest):
    """
    Query stored L2 patterns.

    Args:
        strategy: Filter by strategy name
        symbol: Filter by symbol
        pattern_type: Filter by detector type
    """
    try:
        patterns = journal.db.query_patterns(
            strategy=req.strategy,
            symbol=req.symbol,
            pattern_type=req.pattern_type,
        )
        return {
            "success": True,
            "count": len(patterns),
            "patterns": patterns,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== L3 Strategy Adjustment Endpoints ==========

class GenerateAdjustmentsRequest(BaseModel):
    """Request for reflect.generate_adjustments"""
    db_path: Optional[str] = None


class QueryAdjustmentsRequest(BaseModel):
    """Request for adjustments.query"""
    status: Optional[str] = None
    adjustment_type: Optional[str] = None


class UpdateAdjustmentStatusRequest(BaseModel):
    """Request for adjustments.update_status"""
    adjustment_id: str
    status: str
    applied_at: Optional[str] = None


@app.post("/reflect/generate_adjustments")
async def reflect_generate_adjustments(req: GenerateAdjustmentsRequest):
    """
    Generate L3 strategy adjustments from L2 patterns.

    Reads backtest_auto patterns and applies 5 deterministic rules
    to produce adjustment proposals (status='proposed').

    Args:
        db_path: Path to database (default: tradememory.db)
    """
    try:
        db = Database(req.db_path) if req.db_path else None
        adjustments = reflection_engine.generate_l3_adjustments(db=db)
        return {
            "success": True,
            "adjustments_generated": len(adjustments),
            "adjustments": adjustments,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/adjustments/query")
async def query_adjustments(
    status: Optional[str] = None,
    adjustment_type: Optional[str] = None,
):
    """
    Query stored L3 strategy adjustments.

    Args:
        status: Filter by status (proposed, approved, applied, rejected)
        adjustment_type: Filter by type (strategy_disable, strategy_prefer, etc.)
    """
    try:
        adjustments = journal.db.query_adjustments(
            status=status,
            adjustment_type=adjustment_type,
        )
        return {
            "success": True,
            "count": len(adjustments),
            "adjustments": adjustments,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/adjustments/update_status")
async def update_adjustment_status(req: UpdateAdjustmentStatusRequest):
    """
    Update the status of a strategy adjustment.

    Args:
        adjustment_id: Adjustment identifier
        status: New status (proposed, approved, applied, rejected)
        applied_at: ISO timestamp when applied (optional)
    """
    try:
        success = journal.db.update_adjustment_status(
            adjustment_id=req.adjustment_id,
            status=req.status,
            applied_at=req.applied_at,
        )
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Adjustment '{req.adjustment_id}' not found",
            )
        return {
            "success": True,
            "adjustment_id": req.adjustment_id,
            "status": req.status,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "TradeMemory Protocol",
        "version": "0.5.0"
    }


# ========== OWM (Outcome-Weighted Memory) Endpoints ==========

def _ensure_tz(ts: Optional[str]) -> str:
    """Ensure a timestamp string is timezone-aware (UTC)."""
    if ts is None:
        return datetime.now(timezone.utc).isoformat()
    if "+" not in ts and "Z" not in ts and ts.count("-") <= 2:
        return ts + "+00:00"
    return ts


def _update_semantic_from_trade(
    db: Database,
    symbol: str,
    strategy_name: str,
    pnl: float,
    pnl_r: Optional[float],
    context_regime: Optional[str],
    trade_id: str,
) -> None:
    """Update semantic memories with Bayesian evidence from a new trade."""
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


class RememberTradeRequest(BaseModel):
    """Request for POST /owm/remember"""
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    pnl: float
    strategy_name: str
    market_context: str
    pnl_r: Optional[float] = None
    context_regime: Optional[str] = None
    context_atr_d1: Optional[float] = None
    confidence: float = 0.5
    reflection: Optional[str] = None
    max_adverse_excursion: Optional[float] = None
    trade_id: Optional[str] = None
    timestamp: Optional[str] = None


class RecallMemoriesRequest(BaseModel):
    """Request for POST /owm/recall"""
    symbol: str
    market_context: str
    context_regime: Optional[str] = None
    context_atr_d1: Optional[float] = None
    strategy_name: Optional[str] = None
    memory_types: Optional[List[str]] = None
    limit: int = 10


class CreatePlanRequest(BaseModel):
    """Request for POST /owm/plan"""
    trigger_type: str
    trigger_condition: str
    planned_action: str
    reasoning: str
    expiry_days: int = 30
    priority: float = 0.5


@app.post("/owm/remember")
async def owm_remember(req: RememberTradeRequest):
    """Store a trade into OWM multi-layer memory with automatic updates."""
    try:
        db = journal.db
        tid = req.trade_id or f"owm-{uuid.uuid4().hex[:12]}"
        ts = req.timestamp or datetime.now(timezone.utc).isoformat()
        direction_lower = req.direction.lower()
        if direction_lower not in ("long", "short"):
            raise HTTPException(status_code=400, detail=f"direction must be 'long' or 'short', got '{req.direction}'")
        symbol_upper = req.symbol.upper()

        context_dict = {
            "symbol": symbol_upper,
            "price": req.entry_price,
            "regime": req.context_regime,
            "atr_d1": req.context_atr_d1,
            "description": req.market_context,
        }

        episodic_data = {
            "id": tid,
            "timestamp": ts,
            "context_json": context_dict,
            "context_regime": req.context_regime,
            "context_volatility_regime": None,
            "context_session": None,
            "context_atr_d1": req.context_atr_d1,
            "context_atr_h1": None,
            "strategy": req.strategy_name,
            "direction": direction_lower,
            "entry_price": req.entry_price,
            "lot_size": 0.0,
            "exit_price": req.exit_price,
            "pnl": req.pnl,
            "pnl_r": req.pnl_r,
            "hold_duration_seconds": None,
            "max_adverse_excursion": req.max_adverse_excursion,
            "reflection": req.reflection,
            "confidence": req.confidence,
            "tags": [],
            "retrieval_strength": 1.0,
            "retrieval_count": 0,
            "last_retrieved": None,
        }
        db.insert_episodic(episodic_data)

        _update_semantic_from_trade(db, symbol_upper, req.strategy_name, req.pnl, req.pnl_r, req.context_regime, tid)
        _update_procedural_from_trade(db, symbol_upper, req.strategy_name, req.pnl)
        _update_affective_from_trade(db, req.pnl, req.confidence)

        trade_data = {
            "id": tid,
            "timestamp": ts,
            "symbol": symbol_upper,
            "direction": direction_lower,
            "lot_size": 0.0,
            "strategy": req.strategy_name,
            "confidence": req.confidence,
            "reasoning": req.market_context,
            "market_context": {"description": req.market_context, "entry_price": req.entry_price},
            "references": [],
            "exit_timestamp": None,
            "exit_price": req.exit_price,
            "pnl": req.pnl,
            "pnl_r": req.pnl_r,
            "hold_duration": None,
            "exit_reasoning": req.reflection,
            "slippage": None,
            "execution_quality": None,
            "lessons": req.reflection,
            "tags": [],
            "grade": None,
        }
        db.insert_trade(trade_data)

        return {
            "memory_id": tid,
            "symbol": symbol_upper,
            "direction": direction_lower,
            "strategy": req.strategy_name,
            "stored_at": ts,
            "memory_layers": ["episodic", "semantic", "procedural", "affective", "trade_records"],
            "status": "stored",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/owm/recall")
async def owm_recall(req: RecallMemoriesRequest):
    """Recall memories using OWM outcome-weighted scoring."""
    try:
        db = journal.db
        symbol_upper = req.symbol.upper()
        memory_types = req.memory_types or ["episodic", "semantic"]

        # Parse session hint from market_context text
        _mc = (req.market_context or "").lower()
        _session = None
        if "london" in _mc:
            _session = "london"
        elif "asian" in _mc or "asia" in _mc:
            _session = "asian"
        elif "newyork" in _mc or "new york" in _mc:
            _session = "newyork"

        query_context = ContextVector(
            symbol=symbol_upper,
            regime=req.context_regime,
            atr_d1=req.context_atr_d1,
            session=_session,
        )

        candidates: List[Dict[str, Any]] = []

        if "episodic" in memory_types:
            episodic = db.query_episodic(strategy=req.strategy_name, limit=req.limit * 5)
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
            semantic = db.query_semantic(strategy=req.strategy_name, symbol=symbol_upper, limit=req.limit * 3)
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

        scored = outcome_weighted_recall(
            query_context=query_context,
            memories=candidates,
            affective_state=affective_state,
            limit=req.limit,
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

        response = {
            "query_symbol": symbol_upper,
            "query_context": req.market_context,
            "query_regime": req.context_regime,
            "memory_types_queried": memory_types,
            "matches_found": len(results),
            "affective_state": affective_state,
            "memories": results,
        }

        # Log recall event to PostgreSQL for Intelligence page (side effect)
        try:

            from sqlalchemy import text as sa_text

            from .database import get_async_session

            if results:
                components_list = [r.get("components", {}) for r in results]
                avg_total = sum(r.get("score", 0) for r in results) / len(results)
                avg_q = sum(c.get("Q", 0) for c in components_list) / len(components_list)
                avg_sim = sum(c.get("Sim", 0) for c in components_list) / len(components_list)
                avg_rec = sum(c.get("Rec", 0) for c in components_list) / len(components_list)
                avg_conf = sum(c.get("Conf", 0) for c in components_list) / len(components_list)
                avg_aff = sum(c.get("Aff", 0) for c in components_list) / len(components_list)
                neg_count = sum(1 for r in results if (r.get("pnl_r") or 0) < 0)
                negative_ratio = neg_count / len(results)

                async with get_async_session() as session:
                    await session.execute(sa_text("""
                        INSERT INTO recall_events
                        (timestamp, query_symbol, query_context, query_regime,
                         result_count, avg_total, avg_q, avg_sim, avg_rec, avg_conf, avg_aff,
                         negative_ratio)
                        VALUES (NOW(), :symbol, :context, :regime,
                                :result_count, :avg_total, :avg_q, :avg_sim, :avg_rec, :avg_conf, :avg_aff,
                                :negative_ratio)
                    """), {
                        "symbol": symbol_upper,
                        "context": req.market_context,
                        "regime": req.context_regime,
                        "result_count": len(results),
                        "avg_total": avg_total,
                        "avg_q": avg_q,
                        "avg_sim": avg_sim,
                        "avg_rec": avg_rec,
                        "avg_conf": avg_conf,
                        "avg_aff": avg_aff,
                        "negative_ratio": negative_ratio,
                    })
        except Exception:
            pass  # PG unavailable — silently skip, recall still works

        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/owm/behavioral")
async def owm_behavioral(
    strategy: Optional[str] = None,
    symbol: Optional[str] = None,
):
    """Get behavioral analysis from procedural memory."""
    try:
        db = journal.db
        records = db.query_procedural(
            strategy=strategy,
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/owm/state")
async def owm_state():
    """Get the current agent affective state."""
    try:
        db = journal.db
        state = db.load_affective()

        if state is None:
            db.init_affective(peak_equity=10000.0, current_equity=10000.0)
            state = db.load_affective()
            if state is None:
                raise HTTPException(status_code=500, detail="Failed to initialize affective state")

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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/owm/plan")
async def owm_plan(req: CreatePlanRequest):
    """Create a prospective trading plan."""
    try:
        db = journal.db
        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(days=req.expiry_days)).isoformat()

        try:
            trigger_cond_parsed = json.loads(req.trigger_condition)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=400, detail=f"trigger_condition must be valid JSON, got: {req.trigger_condition}")

        try:
            planned_act_parsed = json.loads(req.planned_action)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=400, detail=f"planned_action must be valid JSON, got: {req.planned_action}")

        data = {
            "id": plan_id,
            "trigger_type": req.trigger_type,
            "trigger_condition": trigger_cond_parsed,
            "planned_action": planned_act_parsed,
            "action_type": planned_act_parsed.get("type", req.trigger_type),
            "status": "active",
            "priority": req.priority,
            "expiry": expiry,
            "source_episodic_ids": [],
            "source_semantic_ids": [],
            "reasoning": req.reasoning,
            "triggered_at": None,
            "outcome_pnl_r": None,
            "outcome_reflection": None,
        }
        success = db.insert_prospective(data)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to insert prospective plan")

        return {
            "plan_id": plan_id,
            "status": "active",
            "expiry": expiry,
            "message": f"Trading plan created: {req.trigger_type} → {planned_act_parsed.get('type', 'action')}",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/owm/plans")
async def owm_plans(
    regime: Optional[str] = None,
    atr_d1: Optional[float] = None,
):
    """Check active trading plans against current market context."""
    try:
        db = journal.db
        plans = db.query_prospective(status="active", limit=1000)

        now = datetime.now(timezone.utc)
        triggered = []
        pending = []

        for plan in plans:
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

            trigger_cond = plan.get("trigger_condition", {})
            if isinstance(trigger_cond, str):
                try:
                    trigger_cond = json.loads(trigger_cond)
                except (json.JSONDecodeError, TypeError):
                    trigger_cond = {}

            matches = True
            if trigger_cond:
                cond_regime = trigger_cond.get("regime")
                if cond_regime and regime and cond_regime != regime:
                    matches = False
                cond_atr_min = trigger_cond.get("atr_d1_min")
                if cond_atr_min is not None and atr_d1 is not None:
                    if atr_d1 < cond_atr_min:
                        matches = False
                cond_atr_max = trigger_cond.get("atr_d1_max")
                if cond_atr_max is not None and atr_d1 is not None:
                    if atr_d1 > cond_atr_max:
                        matches = False
                if cond_regime and regime is None:
                    matches = False
                if (cond_atr_min is not None or cond_atr_max is not None) and atr_d1 is None:
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/owm/migrate")
async def owm_migrate():
    """Trigger OWM migration: trades→episodic, patterns→semantic, initialize affective."""
    try:
        db = journal.db
        episodic_count = migrate_trades_to_episodic(db)
        semantic_count = migrate_patterns_to_semantic(db)
        affective_ok = initialize_affective(db)

        return {
            "success": True,
            "episodic_migrated": episodic_count,
            "semantic_migrated": semantic_count,
            "affective_initialized": affective_ok,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== Evolution Engine Endpoints (Phase 11 — P2) ==========


class EvolutionDiscoverRequest(BaseModel):
    """Request for POST /evolution/discover"""
    symbol: str
    timeframe: str = "1h"
    count: int = 5
    temperature: float = 0.7
    days: int = 90


class EvolutionBacktestRequest(BaseModel):
    """Request for POST /evolution/backtest"""
    pattern_dict: Dict[str, Any]
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    days: int = 90


class EvolutionEvolveRequest(BaseModel):
    """Request for POST /evolution/evolve"""
    symbol: str
    timeframe: str = "1h"
    generations: int = 3
    population_size: int = 10
    days: int = 90


@app.post("/evolution/discover")
async def evolution_discover(req: EvolutionDiscoverRequest):
    """Discover trading patterns from market data using LLM analysis."""
    try:
        from .evolution.llm import AnthropicClient
        from .evolution.mcp_tools import discover_patterns

        llm = AnthropicClient()
        return await discover_patterns(
            req.symbol, req.timeframe, req.count, req.temperature,
            llm=llm, days=req.days,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/evolution/backtest")
async def evolution_backtest(req: EvolutionBacktestRequest):
    """Backtest a candidate pattern against historical OHLCV data."""
    try:
        from .evolution.mcp_tools import run_backtest

        return await run_backtest(
            req.pattern_dict, req.symbol, req.timeframe, req.days,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/evolution/evolve")
async def evolution_evolve(req: EvolutionEvolveRequest):
    """Run full evolution loop — generate, backtest, select, eliminate."""
    try:
        from .evolution.llm import AnthropicClient
        from .evolution.mcp_tools import evolve_strategy

        llm = AnthropicClient()
        return await evolve_strategy(
            req.symbol, req.timeframe, req.generations, req.population_size,
            llm=llm, days=req.days,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/evolution/log")
async def evolution_log():
    """Get the log of past evolution runs from this session."""
    try:
        from .evolution.mcp_tools import get_evolution_log

        return get_evolution_log()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =====================================================================
# Audit API — Trading Decision Records (Phase 2)
# =====================================================================

from .domain.tdr import TradingDecisionRecord, MemoryContext


def _build_tdr(trade: Dict[str, Any], database=None) -> TradingDecisionRecord:
    """Build a TDR from a trade_records row, enriching with memory context."""
    if database is None:
        database = journal.db

    # Try to get memory context from the trade's references
    refs = trade.get("references", [])
    if isinstance(refs, str):
        refs = json.loads(refs)

    # Query semantic beliefs for the strategy
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
        anti_resonance_applied=len(refs) > 0,  # if recall was used, AR was applied
        negative_ratio=None,
        recall_count=len(refs),
    )
    return TradingDecisionRecord.from_trade_record(trade, memory_ctx=mem)


@app.get("/audit/decision-record/{trade_id}")
async def audit_get_decision_record(trade_id: str):
    """Get a complete Trading Decision Record for a single trade.

    Returns the full audit trail including decision context, memory state,
    risk parameters, outcome, and tamper-detection hash.
    """
    db = journal.db
    trade = db.get_trade(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    tdr = _build_tdr(trade, db)
    return tdr.model_dump(mode="json")


@app.get("/audit/export")
async def audit_export(
    start: Optional[str] = None,
    end: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 1000,
):
    """Export Trading Decision Records as JSON array.

    Query params:
        start: ISO date string (inclusive), e.g. 2026-03-01
        end: ISO date string (exclusive), e.g. 2026-04-01
        strategy: Filter by strategy name
        limit: Max records (default 1000)

    Returns JSON array of TDRs. For JSON Lines, use /audit/export-jsonl.
    """
    db = journal.db
    trades = db.query_trades(strategy=strategy, limit=limit)

    # Date range filter
    if start or end:
        filtered = []
        for t in trades:
            ts = t.get("timestamp", "")
            if start and ts < start:
                continue
            if end and ts >= end:
                continue
            filtered.append(t)
        trades = filtered

    return [_build_tdr(t, db).model_dump(mode="json") for t in trades]


@app.get("/audit/export-jsonl")
async def audit_export_jsonl(
    start: Optional[str] = None,
    end: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 1000,
):
    """Export Trading Decision Records as JSON Lines (one JSON object per line).

    Same parameters as /audit/export but returns text/plain with JSONL format.
    """
    from fastapi.responses import PlainTextResponse

    db = journal.db
    trades = db.query_trades(strategy=strategy, limit=limit)

    if start or end:
        filtered = []
        for t in trades:
            ts = t.get("timestamp", "")
            if start and ts < start:
                continue
            if end and ts >= end:
                continue
            filtered.append(t)
        trades = filtered

    lines = []
    for t in trades:
        tdr = _build_tdr(t, db)
        lines.append(tdr.model_dump_json())

    return PlainTextResponse(
        content="\n".join(lines) + ("\n" if lines else ""),
        media_type="application/x-ndjson",
    )


@app.get("/audit/verify/{trade_id}")
async def audit_verify(trade_id: str):
    """Verify integrity of a Trading Decision Record.

    Recomputes the data_hash from stored inputs and compares with
    the hash that was computed at decision time.
    """
    db = journal.db
    trade = db.get_trade(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    market_context = trade.get("market_context", {})
    if isinstance(market_context, str):
        market_context = json.loads(market_context)

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

    tdr = _build_tdr(trade, db)
    return {
        "trade_id": trade_id,
        "stored_hash": tdr.data_hash,
        "recomputed_hash": recomputed,
        "verified": tdr.data_hash == recomputed,
    }


# --- Dashboard static file serving ---
_logger = logging.getLogger(__name__)
_dashboard_dist = Path(__file__).parent.parent.parent / "dashboard" / "dist"

# API prefixes that must NOT be caught by the SPA catch-all
_API_PREFIXES = (
    "audit/", "dashboard/", "trade/", "state/", "reflect/", "mt5/", "risk/",
    "patterns/", "adjustments/", "owm/", "evolution/", "health",
)

if _dashboard_dist.exists():
    _assets_dir = _dashboard_dist / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="dashboard-assets")
    _logger.info("Dashboard static files mounted from %s", _dashboard_dist)

    @app.get("/{full_path:path}")
    async def _serve_spa(full_path: str):
        """Catch-all: serve SPA index.html for client-side routing."""
        if full_path.startswith(_API_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")
        # Serve static files (e.g. vite.svg) if they exist on disk
        static_file = _dashboard_dist / full_path
        if full_path and static_file.exists() and static_file.is_file():
            return FileResponse(str(static_file))
        return FileResponse(str(_dashboard_dist / "index.html"))


def main():
    """Entry point for `tradememory` CLI command."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)  # nosec B104 — server deployment


if __name__ == "__main__":
    main()
