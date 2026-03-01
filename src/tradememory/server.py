"""
TradeMemory MCP Server - FastAPI implementation.
Implements MCP tools from Blueprint Section 3.1.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from .db import Database
from .journal import TradeJournal
from .state import StateManager
from .reflection import ReflectionEngine
from .mt5_connector import MT5Connector
from .adaptive_risk import AdaptiveRisk
from .models import SessionState, TradeProposal, TradeDirection


app = FastAPI(
    title="TradeMemory Protocol",
    description="AI Agent Trading Memory & Adaptive Decision Layer",
    version="0.1.0"
)

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
        "version": "0.1.0"
    }


def main():
    """Entry point for `tradememory` CLI command."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
