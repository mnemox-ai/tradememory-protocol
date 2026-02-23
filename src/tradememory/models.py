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
        None, ge=0.0, le=1.0, description="0.0 - 1.0 score"
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
