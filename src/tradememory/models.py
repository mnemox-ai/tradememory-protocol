"""
Data models for TradeMemory Protocol.
Based on Blueprint Section 5: Trade Journal Data Schema
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum


class TradeDirection(str, Enum):
    """Trade direction"""
    LONG = "long"
    SHORT = "short"


class TradeGrade(str, Enum):
    """Quality grade for trade decision (not result)"""
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class MarketContext(BaseModel):
    """Market context at decision time"""
    price: float
    atr: Optional[float] = None
    session: Optional[str] = None  # asian/london/newyork
    indicators: Dict[str, Any] = Field(default_factory=dict)
    news_sentiment: Optional[float] = None  # -1.0 to 1.0


class TradeRecord(BaseModel):
    """
    Complete trade record with decision context and outcome.
    Matches Blueprint Section 5 schema exactly.
    """
    
    # Core identification
    id: str = Field(..., description="Unique trade ID (T-YYYY-NNNN)")
    timestamp: datetime = Field(..., description="Decision timestamp (UTC)")
    symbol: str = Field(..., description="Trading instrument (XAUUSD, BTCUSDT, etc.)")
    direction: TradeDirection
    lot_size: float
    strategy: str = Field(..., description="Strategy tag (VolBreakout, Pullback, etc.)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Agent confidence score")
    
    # Decision context
    reasoning: str = Field(..., description="Natural language explanation of WHY")
    market_context: MarketContext
    references: List[str] = Field(
        default_factory=list,
        description="References to past trades that informed decision"
    )
    
    # Outcome (filled after trade closes)
    exit_timestamp: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None  # Realized P&L in account currency
    pnl_r: Optional[float] = None  # P&L in R-multiples
    hold_duration: Optional[int] = None  # Minutes held
    exit_reasoning: Optional[str] = None
    slippage: Optional[float] = None  # Entry slippage in pips
    execution_quality: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="0.0 - 1.0 score"
    )
    
    # Post-trade reflection (filled by ReflectionEngine)
    lessons: Optional[str] = None
    tags: List[str] = Field(default_factory=list, description="Auto-generated pattern tags")
    grade: Optional[TradeGrade] = None  # Quality of decision, not result
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "T-2026-0001",
            "timestamp": "2026-02-23T10:30:00Z",
            "symbol": "XAUUSD",
            "direction": "long",
            "lot_size": 0.05,
            "strategy": "VolBreakout",
            "confidence": 0.72,
            "reasoning": "London session open with strong momentum above 20-period high",
            "market_context": {
                "price": 2891.50,
                "atr": 28.3,
                "session": "london"
            },
            "references": []
        }
    })


class SessionState(BaseModel):
    """Agent session state for cross-session persistence"""
    agent_id: str
    last_active: datetime
    warm_memory: Dict[str, Any] = Field(
        default_factory=dict,
        description="L2 curated insights and patterns"
    )
    active_positions: List[str] = Field(
        default_factory=list,
        description="List of open trade IDs"
    )
    risk_constraints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Current dynamic risk parameters"
    )


# ========== Adaptive Risk Models ==========

class RiskStatus(str, Enum):
    """Risk management status level"""
    ACTIVE = "active"
    REDUCED = "reduced"
    STOPPED = "stopped"


class RiskConstraints(BaseModel):
    """Dynamic risk parameters calculated from trade history"""
    max_lot_size: float = Field(default=0.1, description="Maximum allowed lot size")
    risk_per_trade_pct: float = Field(default=2.0, ge=0.5, le=5.0, description="Risk per trade as % of equity")
    daily_loss_limit: float = Field(default=500.0, description="Maximum daily loss in account currency")
    scale_factor: float = Field(default=1.0, ge=0.0, le=1.0, description="Global position scale factor")
    session_adjustments: Dict[str, float] = Field(
        default_factory=lambda: {"asian": 1.0, "london": 1.0, "newyork": 1.0},
        description="Per-session lot multipliers"
    )
    consecutive_loss_limit: int = Field(default=5, description="Max consecutive losses before stop")
    kelly_fraction: float = Field(default=0.0, ge=0.0, le=0.25, description="Quarter-Kelly fraction")
    status: RiskStatus = Field(default=RiskStatus.ACTIVE)
    reason: str = Field(default="Default constraints - insufficient trade history")
    updated_at: datetime = Field(default_factory=lambda: datetime.now())


class TradeProposal(BaseModel):
    """A proposed trade to be checked against risk constraints"""
    symbol: str
    direction: TradeDirection
    lot_size: float = Field(gt=0)
    strategy: str
    confidence: float = Field(ge=0.0, le=1.0)
    session: Optional[str] = None  # asian/london/newyork


class TradeCheckResult(BaseModel):
    """Result of checking a trade proposal against risk constraints"""
    approved: bool
    adjusted_lot_size: float
    reasons: List[str] = Field(default_factory=list)
    constraints_applied: RiskConstraints
