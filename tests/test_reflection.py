"""
Unit tests for ReflectionEngine module.
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, date, timezone, timedelta

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


# ========== Helper for date-controlled trade insertion ==========

def _insert_trade_with_date(
    db: Database,
    idx: int,
    trade_date: date,
    pnl: float,
    session: str = "london",
    strategy: str = "VolBreakout",
    pnl_r: float = 1.0,
):
    """Insert a trade directly into DB with a specific date."""
    trade_id = f"T-DATE-{trade_date.isoformat()}-{idx:03d}"
    ts = f"{trade_date.isoformat()}T10:00:00+00:00"
    trade_data = {
        "id": trade_id,
        "timestamp": ts,
        "symbol": "XAUUSD",
        "direction": "long",
        "lot_size": 0.05,
        "strategy": strategy,
        "confidence": 0.7,
        "reasoning": "Test trade",
        "market_context": json.dumps({"price": 2900.0, "session": session}),
        "trade_references": json.dumps([]),
        "exit_timestamp": ts,
        "exit_price": 2910.0 if pnl > 0 else 2890.0,
        "pnl": pnl,
        "pnl_r": pnl_r,
        "hold_duration": 30,
        "exit_reasoning": "Test",
        "slippage": None,
        "execution_quality": None,
        "lessons": None,
        "tags": json.dumps([]),
        "grade": None,
    }
    conn = db._get_connection()
    try:
        conn.execute(
            """INSERT INTO trade_records VALUES (
                :id, :timestamp, :symbol, :direction, :lot_size, :strategy,
                :confidence, :reasoning, :market_context, :trade_references,
                :exit_timestamp, :exit_price, :pnl, :pnl_r, :hold_duration,
                :exit_reasoning, :slippage, :execution_quality, :lessons,
                :tags, :grade
            )""",
            trade_data,
        )
        conn.commit()
    finally:
        conn.close()


# ========== Date Range Helper Tests ==========

def test_get_trades_for_date_range(reflection, temp_db):
    """Test _get_trades_for_date_range returns trades within range."""
    d1 = date(2026, 2, 10)
    d2 = date(2026, 2, 12)
    d3 = date(2026, 2, 15)

    _insert_trade_with_date(temp_db, 1, d1, 50.0)
    _insert_trade_with_date(temp_db, 2, d2, -20.0)
    _insert_trade_with_date(temp_db, 3, d3, 30.0)

    trades = reflection._get_trades_for_date_range(d1, d2)
    assert len(trades) == 2

    trades_all = reflection._get_trades_for_date_range(d1, d3)
    assert len(trades_all) == 3


# ========== Weekly Tests ==========

def test_weekly_no_trades(reflection):
    """Weekly summary with no trades shows appropriate message."""
    we = date(2026, 2, 16)  # Sunday
    summary = reflection.generate_weekly_summary(week_ending=we)

    assert "WEEKLY SUMMARY" in summary
    assert "No trades this week" in summary
    assert "2026-02-10" in summary  # week start
    assert "2026-02-16" in summary  # week end


def test_weekly_with_trades(reflection, temp_db):
    """Weekly summary with trades shows performance data."""
    we = date(2026, 2, 16)
    ws = we - timedelta(days=6)

    for i in range(6):
        pnl = 50.0 if i < 4 else -25.0
        _insert_trade_with_date(temp_db, i, ws + timedelta(days=i), pnl)

    summary = reflection.generate_weekly_summary(week_ending=we)

    assert "WEEKLY SUMMARY" in summary
    assert "Trades: 6" in summary
    assert "Winners: 4" in summary
    assert "Win Rate:" in summary
    assert "Profit Factor:" in summary


def test_weekly_insufficient_data(reflection, temp_db):
    """Weekly summary with <5 trades shows warning."""
    we = date(2026, 2, 16)
    _insert_trade_with_date(temp_db, 1, date(2026, 2, 11), 50.0)
    _insert_trade_with_date(temp_db, 2, date(2026, 2, 12), -20.0)

    summary = reflection.generate_weekly_summary(week_ending=we)

    assert "Insufficient data for weekly pattern analysis" in summary


def test_weekly_strategy_breakdown(reflection, temp_db):
    """Weekly summary includes strategy breakdown."""
    we = date(2026, 2, 16)
    ws = we - timedelta(days=6)

    _insert_trade_with_date(temp_db, 1, ws, 50.0, strategy="VolBreakout")
    _insert_trade_with_date(temp_db, 2, ws + timedelta(days=1), -20.0, strategy="Pullback")
    _insert_trade_with_date(temp_db, 3, ws + timedelta(days=2), 30.0, strategy="VolBreakout")

    summary = reflection.generate_weekly_summary(week_ending=we)

    assert "STRATEGY BREAKDOWN:" in summary
    assert "VolBreakout" in summary
    assert "Pullback" in summary


def test_weekly_session_patterns(reflection, temp_db):
    """Weekly summary includes session patterns."""
    we = date(2026, 2, 16)
    ws = we - timedelta(days=6)

    _insert_trade_with_date(temp_db, 1, ws, 50.0, session="asian")
    _insert_trade_with_date(temp_db, 2, ws + timedelta(days=1), -20.0, session="london")
    _insert_trade_with_date(temp_db, 3, ws + timedelta(days=2), 30.0, session="newyork")

    summary = reflection.generate_weekly_summary(week_ending=we)

    assert "SESSION PATTERNS:" in summary
    assert "asian" in summary
    assert "london" in summary
    assert "newyork" in summary


def test_weekly_day_of_week(reflection, temp_db):
    """Weekly summary includes best/worst day."""
    we = date(2026, 2, 16)  # Sunday
    # Feb 10 = Monday, Feb 11 = Tuesday
    _insert_trade_with_date(temp_db, 1, date(2026, 2, 10), 100.0)
    _insert_trade_with_date(temp_db, 2, date(2026, 2, 11), -80.0)

    summary = reflection.generate_weekly_summary(week_ending=we)

    assert "DAY OF WEEK:" in summary
    assert "Best:" in summary
    assert "Worst:" in summary


def test_weekly_streak_analysis(reflection, temp_db):
    """Weekly metrics include streak data."""
    we = date(2026, 2, 16)
    ws = we - timedelta(days=6)

    # W W W L L → win streak 3, loss streak 2
    pnls = [50.0, 30.0, 20.0, -10.0, -15.0]
    for i, pnl in enumerate(pnls):
        _insert_trade_with_date(temp_db, i, ws + timedelta(days=i), pnl)

    summary = reflection.generate_weekly_summary(week_ending=we)

    assert "STREAKS:" in summary
    assert "Max win streak: 3" in summary
    assert "Max loss streak: 2" in summary


def test_weekly_profit_factor(reflection, temp_db):
    """Weekly metrics calculate correct profit factor."""
    we = date(2026, 2, 16)
    ws = we - timedelta(days=6)

    # 2 wins @ 50 = 100 gross, 1 loss @ -25 = 25 gross → PF = 4.0
    _insert_trade_with_date(temp_db, 1, ws, 50.0)
    _insert_trade_with_date(temp_db, 2, ws + timedelta(days=1), 50.0)
    _insert_trade_with_date(temp_db, 3, ws + timedelta(days=2), -25.0)

    trades = reflection._get_trades_for_date_range(ws, we)
    metrics = reflection._calculate_weekly_metrics(trades, ws, we)

    assert metrics["profit_factor"] == pytest.approx(4.0)


def test_weekly_llm_fallback_on_invalid(reflection, temp_db):
    """Weekly LLM output that fails validation falls back to rule-based."""
    we = date(2026, 2, 16)
    _insert_trade_with_date(temp_db, 1, date(2026, 2, 11), 50.0)
    _insert_trade_with_date(temp_db, 2, date(2026, 2, 12), -20.0)

    def bad_llm(model, prompt):
        return "garbage output"

    summary = reflection.generate_weekly_summary(week_ending=we, llm_provider=bad_llm)

    assert "WEEKLY SUMMARY" in summary
    assert "rule-based fallback" in summary


def test_weekly_validate_valid_output(reflection):
    """Valid weekly LLM output passes validation."""
    we = date(2026, 2, 16)
    ws = we - timedelta(days=6)

    valid = f"""=== WEEKLY SUMMARY: {ws.isoformat()} to {we.isoformat()} ===

PERFORMANCE:
Trades: 10 | Winners: 6 | Losers: 4
Net P&L: $200.00 | Win Rate: 60.0%

STRATEGY BREAKDOWN:
- VolBreakout: 6 trades, WR 66.7%

SESSION PATTERNS:
- london: 5 trades, WR 60.0%

KEY OBSERVATIONS:
- Good week overall.

NEXT WEEK:
- Continue current approach."""

    assert reflection._validate_weekly_llm_output(valid, we) is True


# ========== Monthly Tests ==========

def test_monthly_no_trades(reflection):
    """Monthly summary with no trades shows appropriate message."""
    summary = reflection.generate_monthly_summary(year=2026, month=1)

    assert "MONTHLY SUMMARY: 2026-01" in summary
    assert "No trades this month" in summary


def test_monthly_with_trades(reflection, temp_db):
    """Monthly summary with trades shows full performance data."""
    # Insert trades across February
    for i in range(10):
        d = date(2026, 2, 1 + i)
        pnl = 50.0 if i < 6 else -30.0
        _insert_trade_with_date(temp_db, i, d, pnl, strategy="VolBreakout")

    summary = reflection.generate_monthly_summary(year=2026, month=2)

    assert "MONTHLY SUMMARY: 2026-02" in summary
    assert "Trades: 10" in summary
    assert "Winners: 6" in summary
    assert "Win Rate:" in summary
    assert "Trading Days:" in summary
    assert "Avg Trades/Day:" in summary


def test_monthly_weekly_trends(reflection, temp_db):
    """Monthly metrics include weekly trend data."""
    # Spread trades across 3 weeks of Feb
    for i in range(9):
        d = date(2026, 2, 1 + i * 3)
        pnl = 50.0 if i % 2 == 0 else -20.0
        _insert_trade_with_date(temp_db, i, d, pnl)

    summary = reflection.generate_monthly_summary(year=2026, month=2)

    assert "WEEKLY TRENDS:" in summary
    assert "Trend:" in summary


def test_monthly_strategy_evolution(reflection, temp_db):
    """Monthly metrics track strategy evolution (first half vs second half)."""
    # First half: strategy A poor (1 win, 2 loss)
    _insert_trade_with_date(temp_db, 1, date(2026, 2, 2), -30.0, strategy="StratA")
    _insert_trade_with_date(temp_db, 2, date(2026, 2, 5), -20.0, strategy="StratA")
    _insert_trade_with_date(temp_db, 3, date(2026, 2, 8), 10.0, strategy="StratA")

    # Second half: strategy A improved (2 win, 1 loss)
    _insert_trade_with_date(temp_db, 4, date(2026, 2, 18), 50.0, strategy="StratA")
    _insert_trade_with_date(temp_db, 5, date(2026, 2, 20), 40.0, strategy="StratA")
    _insert_trade_with_date(temp_db, 6, date(2026, 2, 22), -10.0, strategy="StratA")

    start = date(2026, 2, 1)
    end = date(2026, 2, 28)
    trades = reflection._get_trades_for_date_range(start, end)
    metrics = reflection._calculate_monthly_metrics(trades, start, end)

    evo = metrics["strategy_evolution"]["StratA"]
    assert evo["first_half_wr"] == pytest.approx(33.3, abs=0.5)
    assert evo["second_half_wr"] == pytest.approx(66.7, abs=0.5)
    assert evo["direction"] == "improving"


def test_monthly_llm_fallback_on_invalid(reflection, temp_db):
    """Monthly LLM output that fails validation falls back to rule-based."""
    _insert_trade_with_date(temp_db, 1, date(2026, 2, 5), 50.0)

    def bad_llm(model, prompt):
        return "invalid"

    summary = reflection.generate_monthly_summary(
        year=2026, month=2, llm_provider=bad_llm
    )

    assert "MONTHLY SUMMARY: 2026-02" in summary
    assert "rule-based fallback" in summary
