"""
Unit tests for ReflectionEngine module.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, date, timezone

from src.tradememory.reflection import ReflectionEngine
from src.tradememory.journal import TradeJournal
from src.tradememory.db import Database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(str(db_path))
        yield db


@pytest.fixture
def journal(temp_db):
    """Create a TradeJournal with temp database"""
    return TradeJournal(db=temp_db)


@pytest.fixture
def reflection(journal):
    """Create a ReflectionEngine with temp journal"""
    return ReflectionEngine(journal=journal)


def test_daily_summary_no_trades(reflection):
    """Test daily summary when no trades exist"""
    target = date(2026, 2, 23)
    summary = reflection.generate_daily_summary(target_date=target)
    
    assert "2026-02-23" in summary
    assert "No trades today" in summary


def test_daily_summary_with_trades(reflection, journal):
    """Test daily summary with real trades"""
    # Create some test trades for today (UTC)
    today = datetime.now(timezone.utc).date()
    
    # Winner
    journal.record_decision(
        trade_id="T-2026-WIN-001",
        symbol="XAUUSD",
        direction="long",
        lot_size=0.05,
        strategy="VolBreakout",
        confidence=0.85,
        reasoning="Strong breakout",
        market_context={"price": 2900.00}
    )
    journal.record_outcome(
        trade_id="T-2026-WIN-001",
        exit_price=2910.00,
        pnl=50.00,
        pnl_r=2.0,
        exit_reasoning="Hit target"
    )
    
    # Loser
    journal.record_decision(
        trade_id="T-2026-LOSS-001",
        symbol="XAUUSD",
        direction="short",
        lot_size=0.05,
        strategy="Pullback",
        confidence=0.65,
        reasoning="Pullback setup",
        market_context={"price": 2905.00}
    )
    journal.record_outcome(
        trade_id="T-2026-LOSS-001",
        exit_price=2910.00,
        pnl=-25.00,
        pnl_r=-1.0,
        exit_reasoning="Stop hit"
    )
    
    # Generate summary
    summary = reflection.generate_daily_summary(target_date=today)
    
    assert today.isoformat() in summary
    assert "Trades: 2" in summary
    assert "Winners: 1" in summary
    assert "Losers: 1" in summary
    assert "Win Rate: 50.0%" in summary
    assert "Net P&L: $25.00" in summary


def test_daily_summary_insufficient_data(reflection, journal):
    """Test summary with <3 trades shows warning"""
    today = datetime.now(timezone.utc).date()
    
    # Only 1 trade
    journal.record_decision(
        trade_id="T-2026-SINGLE-001",
        symbol="XAUUSD",
        direction="long",
        lot_size=0.05,
        strategy="Test",
        confidence=0.7,
        reasoning="Test",
        market_context={"price": 2900.00}
    )
    
    summary = reflection.generate_daily_summary(target_date=today)
    
    assert "Insufficient data for pattern analysis" in summary


def test_metrics_calculation(reflection, journal):
    """Test performance metrics calculation"""
    today = datetime.now(timezone.utc).date()
    
    # Create 5 trades: 3 winners, 2 losers
    for i in range(5):
        is_winner = i < 3
        trade_id = f"T-2026-METRICS-{i:03d}"
        
        journal.record_decision(
            trade_id=trade_id,
            symbol="XAUUSD",
            direction="long",
            lot_size=0.05,
            strategy="Test",
            confidence=0.7 + (i * 0.05),
            reasoning="Test",
            market_context={"price": 2900.00}
        )
        
        journal.record_outcome(
            trade_id=trade_id,
            exit_price=2910.00 if is_winner else 2895.00,
            pnl=50.00 if is_winner else -25.00,
            pnl_r=2.0 if is_winner else -1.0,
            exit_reasoning="Test"
        )
    
    # Get trades and calculate metrics
    trades = reflection._get_trades_for_date(today)
    metrics = reflection._calculate_daily_metrics(trades)
    
    assert metrics['total'] == 5
    assert metrics['winners'] == 3
    assert metrics['losers'] == 2
    assert metrics['win_rate'] == 60.0
    assert metrics['total_pnl'] == 100.0  # (3*50) - (2*25)
    assert metrics['avg_r'] == pytest.approx(0.8, abs=0.1)  # (3*2 - 2*1) / 5


def test_high_confidence_mistakes_detected(reflection, journal):
    """Test that high-confidence losers are flagged as mistakes"""
    today = datetime.now(timezone.utc).date()
    
    # High confidence loser
    journal.record_decision(
        trade_id="T-2026-MISTAKE-001",
        symbol="XAUUSD",
        direction="long",
        lot_size=0.1,
        strategy="VolBreakout",
        confidence=0.90,  # Very high confidence
        reasoning="Strong setup",
        market_context={"price": 2900.00}
    )
    journal.record_outcome(
        trade_id="T-2026-MISTAKE-001",
        exit_price=2880.00,
        pnl=-100.00,  # Big loss
        pnl_r=-2.0,
        exit_reasoning="Stop hit"
    )
    
    summary = reflection.generate_daily_summary(target_date=today)
    
    assert "MISTAKES" in summary or "High confidence" in summary
