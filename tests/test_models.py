"""
Unit tests for data models.
"""

import pytest
from datetime import datetime, timezone
from src.tradememory.models import (
    TradeRecord,
    MarketContext,
    SessionState,
    TradeDirection,
    TradeGrade
)


def test_market_context_creation():
    """Test MarketContext model"""
    ctx = MarketContext(
        price=2891.50,
        atr=28.3,
        session="london"
    )
    
    assert ctx.price == 2891.50
    assert ctx.atr == 28.3
    assert ctx.session == "london"


def test_trade_record_minimal():
    """Test TradeRecord with minimal required fields"""
    trade = TradeRecord(
        id="T-2026-0001",
        timestamp=datetime.now(timezone.utc),
        symbol="XAUUSD",
        direction=TradeDirection.LONG,
        lot_size=0.05,
        strategy="VolBreakout",
        confidence=0.72,
        reasoning="Test trade",
        market_context=MarketContext(price=2891.50)
    )
    
    assert trade.id == "T-2026-0001"
    assert trade.symbol == "XAUUSD"
    assert trade.direction == TradeDirection.LONG
    assert trade.lot_size == 0.05
    assert trade.confidence == 0.72
    assert trade.exit_timestamp is None  # Not closed yet


def test_trade_record_with_outcome():
    """Test TradeRecord with outcome data"""
    trade = TradeRecord(
        id="T-2026-0002",
        timestamp=datetime.now(timezone.utc),
        symbol="XAUUSD",
        direction=TradeDirection.SHORT,
        lot_size=0.1,
        strategy="Pullback",
        confidence=0.85,
        reasoning="Strong pullback setup",
        market_context=MarketContext(price=2900.00, atr=30.0),
        exit_timestamp=datetime.now(timezone.utc),
        exit_price=2895.00,
        pnl=25.00,
        pnl_r=1.5,
        lessons="Good entry, could trail stop better"
    )
    
    assert trade.exit_price == 2895.00
    assert trade.pnl == 25.00
    assert trade.pnl_r == 1.5
    assert trade.lessons is not None


def test_trade_record_confidence_validation():
    """Test confidence score validation"""
    with pytest.raises(ValueError):
        TradeRecord(
            id="T-2026-0003",
            timestamp=datetime.now(timezone.utc),
            symbol="XAUUSD",
            direction=TradeDirection.LONG,
            lot_size=0.05,
            strategy="Test",
            confidence=1.5,  # Invalid: > 1.0
            reasoning="Test",
            market_context=MarketContext(price=2891.50)
        )


def test_session_state_creation():
    """Test SessionState model"""
    state = SessionState(
        agent_id="ng-gold-agent",
        last_active=datetime.now(timezone.utc),
        warm_memory={"last_strategy": "VolBreakout"},
        active_positions=["T-2026-0001"],
        risk_constraints={"max_lot": 0.1}
    )
    
    assert state.agent_id == "ng-gold-agent"
    assert "last_strategy" in state.warm_memory
    assert len(state.active_positions) == 1
    assert state.risk_constraints["max_lot"] == 0.1


def test_session_state_defaults():
    """Test SessionState with defaults"""
    state = SessionState(
        agent_id="test-agent",
        last_active=datetime.now(timezone.utc)
    )
    
    assert state.warm_memory == {}
    assert state.active_positions == []
    assert state.risk_constraints == {}
