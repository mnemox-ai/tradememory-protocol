"""
TradeMemory MCP Server - FastAPI implementation.
Implements MCP tools from Blueprint Section 3.1.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

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
