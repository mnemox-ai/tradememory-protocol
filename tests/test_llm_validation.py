"""
Unit tests for LLM output validation (DEC-010).
"""

import pytest
from datetime import date

from src.tradememory.reflection import ReflectionEngine


@pytest.fixture
def reflection():
    """Create a ReflectionEngine instance"""
    return ReflectionEngine()


def test_validate_valid_llm_output(reflection):
    """Test validation passes for correctly formatted LLM output"""
    target_date = date(2026, 2, 23)
    
    valid_output = """=== DAILY SUMMARY: 2026-02-23 ===

PERFORMANCE:
Trades: 5 | Winners: 3 | Losers: 2
Net P&L: $125.00 | Win Rate: 60.0% | Avg R: 1.2

KEY OBSERVATIONS:
- High win rate indicates edge is present
- London session trades outperformed Asian session

MISTAKES:
- T-2026-001: Entered too early before confirmation

TOMORROW:
- Wait for stronger confirmation signals
"""
    
    assert reflection._validate_llm_output(valid_output, target_date) is True


def test_validate_missing_header(reflection):
    """Test validation fails when header is missing"""
    target_date = date(2026, 2, 23)
    
    invalid_output = """PERFORMANCE:
Trades: 5 | Winners: 3 | Losers: 2
Win Rate: 60.0%

KEY OBSERVATIONS:
- Some observations here
"""
    
    assert reflection._validate_llm_output(invalid_output, target_date) is False


def test_validate_wrong_date(reflection):
    """Test validation fails when date doesn't match"""
    target_date = date(2026, 2, 23)
    
    wrong_date_output = """=== DAILY SUMMARY: 2026-02-22 ===

PERFORMANCE:
Trades: 5 | Winners: 3 | Losers: 2
Net P&L: $125.00 | Win Rate: 60.0% | Avg R: 1.2

KEY OBSERVATIONS:
- Some observations
"""
    
    assert reflection._validate_llm_output(wrong_date_output, target_date) is False


def test_validate_missing_performance(reflection):
    """Test validation fails when PERFORMANCE section is missing"""
    target_date = date(2026, 2, 23)
    
    no_performance = """=== DAILY SUMMARY: 2026-02-23 ===

KEY OBSERVATIONS:
- Some observations here

TOMORROW:
- Some advice
"""
    
    assert reflection._validate_llm_output(no_performance, target_date) is False


def test_validate_missing_required_fields(reflection):
    """Test validation fails when required fields are missing"""
    target_date = date(2026, 2, 23)
    
    # Missing "Trades:" field
    missing_trades = """=== DAILY SUMMARY: 2026-02-23 ===

PERFORMANCE:
Winners: 3 | Losers: 2
Net P&L: $125.00 | Win Rate: 60.0%
"""
    
    assert reflection._validate_llm_output(missing_trades, target_date) is False
    
    # Missing "Win Rate:" field
    missing_wr = """=== DAILY SUMMARY: 2026-02-23 ===

PERFORMANCE:
Trades: 5 | Winners: 3 | Losers: 2
Net P&L: $125.00
"""
    
    assert reflection._validate_llm_output(missing_wr, target_date) is False


def test_validate_too_few_sections(reflection):
    """Test validation fails when less than 2 optional sections present"""
    target_date = date(2026, 2, 23)
    
    # Only has PERFORMANCE (required) and one optional section
    one_section = """=== DAILY SUMMARY: 2026-02-23 ===

PERFORMANCE:
Trades: 5 | Winners: 3 | Losers: 2
Net P&L: $125.00 | Win Rate: 60.0% | Avg R: 1.2

KEY OBSERVATIONS:
- Only one optional section
"""
    
    assert reflection._validate_llm_output(one_section, target_date) is False


def test_validate_minimal_valid_output(reflection):
    """Test validation passes for minimal but valid output"""
    target_date = date(2026, 2, 23)
    
    # Has required sections + exactly 2 optional sections
    minimal_valid = """=== DAILY SUMMARY: 2026-02-23 ===

PERFORMANCE:
Trades: 1 | Winners: 1 | Losers: 0
Net P&L: $50.00 | Win Rate: 100.0% | Avg R: 2.0

KEY OBSERVATIONS:
- Insufficient data for pattern analysis.

TOMORROW:
- Continue monitoring.
"""
    
    assert reflection._validate_llm_output(minimal_valid, target_date) is True


def test_validate_empty_or_short_output(reflection):
    """Test validation fails for empty or very short output"""
    target_date = date(2026, 2, 23)
    
    assert reflection._validate_llm_output("", target_date) is False
    assert reflection._validate_llm_output("short", target_date) is False
    assert reflection._validate_llm_output(None, target_date) is False


def test_llm_fallback_on_invalid_output(reflection):
    """Test that invalid LLM output triggers rule-based fallback"""
    from datetime import datetime
    from src.tradememory.journal import TradeJournal
    from src.tradememory.db import Database
    import tempfile
    from pathlib import Path
    
    # Setup
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test.db"
    db = Database(str(db_path))
    journal = TradeJournal(db=db)
    reflection = ReflectionEngine(journal=journal)
    
    # Create a test trade
    today = datetime.utcnow().date()
    journal.record_decision(
        trade_id="T-VALIDATION-001",
        symbol="XAUUSD",
        direction="long",
        lot_size=0.05,
        strategy="Test",
        confidence=0.7,
        reasoning="Test trade",
        market_context={"price": 2900.00}
    )
    journal.record_outcome(
        trade_id="T-VALIDATION-001",
        exit_price=2910.00,
        pnl=50.00,
        pnl_r=2.0,
        exit_reasoning="Test exit"
    )
    
    # Mock LLM that returns malformed output
    def malformed_llm(model, prompt):
        return "This is malformed output without proper structure."
    
    # Generate summary with malformed LLM
    summary = reflection.generate_daily_summary(target_date=today, llm_provider=malformed_llm)
    
    # Should fallback to rule-based
    assert "DAILY SUMMARY" in summary
    assert "PERFORMANCE" in summary
    assert "failed validation" in summary.lower()
    assert "rule-based fallback" in summary.lower()
