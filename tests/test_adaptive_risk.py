"""Tests for the AdaptiveRisk module."""

import pytest
from datetime import datetime, timezone, timedelta

from src.tradememory.db import Database
from src.tradememory.journal import TradeJournal
from src.tradememory.state import StateManager
from src.tradememory.adaptive_risk import AdaptiveRisk
from src.tradememory.models import (
    RiskStatus, RiskConstraints, TradeProposal, TradeCheckResult, TradeDirection,
)


# ==================== Fixtures ====================

@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary SQLite database."""
    return Database(str(tmp_path / "test_risk.db"))


@pytest.fixture
def journal(temp_db):
    return TradeJournal(db=temp_db)


@pytest.fixture
def state_manager(temp_db):
    return StateManager(db=temp_db)


@pytest.fixture
def risk(journal, state_manager):
    """AdaptiveRisk with lowered thresholds for easy testing."""
    return AdaptiveRisk(
        journal=journal,
        state_manager=state_manager,
        consecutive_loss_limit=3,
        daily_loss_limit=200.0,
        max_lot_size=0.1,
    )


# ==================== Helpers ====================

def _create_trade(
    journal: TradeJournal,
    idx: int,
    pnl: float,
    *,
    session: str = "london",
    strategy: str = "VolBreakout",
    symbol: str = "XAUUSD",
    confidence: float = 0.7,
    days_ago: int = 0,
) -> None:
    """Quick helper to record a decision + outcome."""
    trade_id = f"T-2026-{idx:04d}"
    journal.record_decision(
        trade_id=trade_id,
        symbol=symbol,
        direction="long",
        lot_size=0.05,
        strategy=strategy,
        confidence=confidence,
        reasoning=f"Test trade {idx}",
        market_context={"price": 2900.0, "session": session},
    )
    journal.record_outcome(
        trade_id=trade_id,
        exit_price=2900.0 + pnl,
        pnl=pnl,
        exit_reasoning="Test exit",
    )


# ==================== Safe Defaults ====================

class TestSafeDefaults:
    """Tests for safe defaults when data is insufficient."""

    def test_zero_trades_returns_defaults(self, risk):
        """No trades -> safe defaults with ACTIVE status."""
        c = risk.calculate_constraints("agent-001")
        assert c.status == RiskStatus.ACTIVE
        assert c.scale_factor == 1.0
        assert "insufficient" in c.reason.lower() or "default" in c.reason.lower()

    def test_fewer_than_min_trades(self, risk, journal):
        """< 5 closed trades -> safe defaults."""
        for i in range(1, 4):
            _create_trade(journal, i, pnl=50.0)
        c = risk.calculate_constraints("agent-002")
        assert c.status == RiskStatus.ACTIVE
        assert c.kelly_fraction == 0.0

    def test_get_constraints_no_state(self, risk):
        """get_constraints for unknown agent returns defaults."""
        c = risk.get_constraints("unknown-agent")
        assert c.status == RiskStatus.ACTIVE
        assert c.max_lot_size == 0.1


# ==================== Kelly Criterion ====================

class TestKellyCriterion:
    """Tests for Quarter-Kelly calculation."""

    def test_kelly_with_edge(self, risk, journal):
        """Positive edge -> positive kelly fraction."""
        # 7 wins, 3 losses -> p=0.7, good edge
        for i in range(1, 8):
            _create_trade(journal, i, pnl=100.0)
        for i in range(8, 11):
            _create_trade(journal, i, pnl=-50.0)

        c = risk.calculate_constraints("agent-kelly")
        assert c.kelly_fraction > 0
        assert c.kelly_fraction <= 0.25

    def test_kelly_no_edge(self, risk, journal):
        """No edge -> kelly 0."""
        # 3 wins $10, 7 losses $-50 -> negative expectancy
        for i in range(1, 4):
            _create_trade(journal, i, pnl=10.0)
        for i in range(4, 11):
            _create_trade(journal, i, pnl=-50.0)

        c = risk.calculate_constraints("agent-no-edge")
        assert c.kelly_fraction == 0.0

    def test_kelly_insufficient_wins_or_losses(self, risk, journal):
        """< 2 wins or < 2 losses -> kelly 0."""
        # All wins, 0 losses
        for i in range(1, 8):
            _create_trade(journal, i, pnl=50.0)

        c = risk.calculate_constraints("agent-all-win")
        assert c.kelly_fraction == 0.0


# ==================== Drawdown Scaling ====================

class TestDrawdownScaling:
    """Tests for drawdown-based scaling."""

    def test_no_drawdown(self, risk, journal):
        """All profitable -> scale 1.0."""
        # Interleave small losses with wins so consecutive streak doesn't trigger
        for i in range(1, 6):
            _create_trade(journal, i, pnl=100.0)
        _create_trade(journal, 6, pnl=-10.0)
        _create_trade(journal, 7, pnl=100.0)
        _create_trade(journal, 8, pnl=-10.0)
        _create_trade(journal, 9, pnl=100.0)

        c = risk.calculate_constraints("agent-no-dd")
        assert c.scale_factor >= 0.75  # small losses, no significant DD

    def test_moderate_drawdown(self, risk, journal):
        """5-10% drawdown -> scale 0.75."""
        # Start with profit, then sustained losses ~6% of $10k equity
        for i in range(1, 4):
            _create_trade(journal, i, pnl=100.0)
        for i in range(4, 11):
            _create_trade(journal, i, pnl=-120.0)

        c = risk.calculate_constraints("agent-mod-dd")
        assert c.scale_factor <= 0.75

    def test_severe_drawdown(self, risk, journal):
        """>10% drawdown -> scale 0.5."""
        # Heavy losses totaling >$1000 on $10k base
        for i in range(1, 3):
            _create_trade(journal, i, pnl=50.0)
        for i in range(3, 13):
            _create_trade(journal, i, pnl=-150.0)

        c = risk.calculate_constraints("agent-severe-dd")
        assert c.scale_factor <= 0.5


# ==================== Session Adjustments ====================

class TestSessionAdjustments:
    """Tests for per-session win rate adjustments."""

    def test_low_session_win_rate(self, risk, journal):
        """Session with < 40% win rate -> 0.5x multiplier."""
        # Asian: 1 win, 4 losses (20% WR)
        _create_trade(journal, 1, pnl=50.0, session="asian")
        for i in range(2, 6):
            _create_trade(journal, i, pnl=-30.0, session="asian")

        # London: enough to pass MIN_TRADES
        for i in range(6, 11):
            _create_trade(journal, i, pnl=50.0, session="london")

        c = risk.calculate_constraints("agent-session")
        assert c.session_adjustments["asian"] == 0.5

    def test_insufficient_session_data(self, risk, journal):
        """< 3 trades in a session -> conservative 0.75."""
        # Only 2 asian trades + 8 london trades
        for i in range(1, 3):
            _create_trade(journal, i, pnl=50.0, session="asian")
        for i in range(3, 11):
            _create_trade(journal, i, pnl=50.0, session="london")

        c = risk.calculate_constraints("agent-sess-insuf")
        assert c.session_adjustments["asian"] == 0.75


# ==================== Consecutive Losses ====================

class TestConsecutiveLosses:
    """Tests for consecutive loss streak detection."""

    def test_consecutive_losses_stopped(self, risk, journal):
        """
        >= consecutive_loss_limit (3) consecutive losses -> STOPPED.
        We need >= 5 total closed trades to pass MIN_TRADES.
        """
        # 2 wins first, then 3 consecutive losses
        for i in range(1, 3):
            _create_trade(journal, i, pnl=50.0)
        for i in range(3, 6):
            _create_trade(journal, i, pnl=-30.0)

        c = risk.calculate_constraints("agent-consec-stop")
        assert c.status == RiskStatus.STOPPED

    def test_consecutive_losses_reduced(self, risk, journal):
        """
        >= limit-1 (2) consecutive losses -> REDUCED.
        """
        # 3 wins, then 2 consecutive losses
        for i in range(1, 4):
            _create_trade(journal, i, pnl=50.0)
        for i in range(4, 6):
            _create_trade(journal, i, pnl=-30.0)

        c = risk.calculate_constraints("agent-consec-red")
        assert c.status == RiskStatus.REDUCED

    def test_win_resets_streak(self, risk, journal):
        """A win after losses resets the streak."""
        # 2 losses, then 1 win at the end
        for i in range(1, 3):
            _create_trade(journal, i, pnl=50.0)
        for i in range(3, 5):
            _create_trade(journal, i, pnl=-30.0)
        _create_trade(journal, 5, pnl=50.0)

        c = risk.calculate_constraints("agent-reset")
        assert c.status == RiskStatus.ACTIVE


# ==================== Daily Loss Limit ====================

class TestDailyLossLimit:
    """Tests for daily loss limit detection."""

    def test_daily_loss_exceeded(self, risk, journal):
        """Today's loss > limit -> STOPPED."""
        # All trades are today (days_ago=0 is default)
        # daily_loss_limit = 200.0; total losses = 5 * -50 = -250
        for i in range(1, 4):
            _create_trade(journal, i, pnl=50.0)
        for i in range(4, 9):
            _create_trade(journal, i, pnl=-50.0)

        c = risk.calculate_constraints("agent-daily-stop")
        assert c.status == RiskStatus.STOPPED

    def test_daily_loss_warning(self, risk, journal):
        """Today's loss > 80% limit -> REDUCED."""
        # daily_loss_limit = 200; need losses = 160-199
        for i in range(1, 4):
            _create_trade(journal, i, pnl=50.0)
        # 3 losses * -60 = -180 > 160 (80% of 200)
        for i in range(4, 7):
            _create_trade(journal, i, pnl=-60.0)

        c = risk.calculate_constraints("agent-daily-warn")
        assert c.status in (RiskStatus.REDUCED, RiskStatus.STOPPED)


# ==================== check_trade ====================

class TestCheckTrade:
    """Tests for trade proposal validation."""

    def test_approved_trade(self, risk, state_manager):
        """Normal trade within constraints is approved."""
        # Store default constraints
        defaults = RiskConstraints()
        state_manager.update_risk_constraints(
            "agent-check", defaults.model_dump(mode="json")
        )

        proposal = TradeProposal(
            symbol="XAUUSD",
            direction=TradeDirection.LONG,
            lot_size=0.05,
            strategy="VolBreakout",
            confidence=0.7,
        )
        result = risk.check_trade("agent-check", proposal)
        assert result.approved is True
        assert result.adjusted_lot_size == 0.05

    def test_lot_capped(self, risk, state_manager):
        """Lot exceeding max_lot_size is capped."""
        constraints = RiskConstraints(max_lot_size=0.05)
        state_manager.update_risk_constraints(
            "agent-cap", constraints.model_dump(mode="json")
        )

        proposal = TradeProposal(
            symbol="XAUUSD",
            direction=TradeDirection.LONG,
            lot_size=0.10,
            strategy="VolBreakout",
            confidence=0.7,
        )
        result = risk.check_trade("agent-cap", proposal)
        assert result.approved is True
        assert result.adjusted_lot_size == 0.05
        assert any("capped" in r.lower() for r in result.reasons)

    def test_stopped_rejection(self, risk, state_manager):
        """STOPPED status rejects the trade."""
        constraints = RiskConstraints(
            status=RiskStatus.STOPPED,
            reason="Daily loss limit exceeded",
        )
        state_manager.update_risk_constraints(
            "agent-stop", constraints.model_dump(mode="json")
        )

        proposal = TradeProposal(
            symbol="XAUUSD",
            direction=TradeDirection.LONG,
            lot_size=0.05,
            strategy="VolBreakout",
            confidence=0.7,
        )
        result = risk.check_trade("agent-stop", proposal)
        assert result.approved is False
        assert result.adjusted_lot_size == 0.0

    def test_session_adjustment_applied(self, risk, state_manager):
        """Session adjustment reduces lot size."""
        constraints = RiskConstraints(
            session_adjustments={"asian": 0.5, "london": 1.0, "newyork": 1.0},
        )
        state_manager.update_risk_constraints(
            "agent-sess", constraints.model_dump(mode="json")
        )

        proposal = TradeProposal(
            symbol="XAUUSD",
            direction=TradeDirection.LONG,
            lot_size=0.10,
            strategy="VolBreakout",
            confidence=0.7,
            session="asian",
        )
        result = risk.check_trade("agent-sess", proposal)
        assert result.approved is True
        assert result.adjusted_lot_size == 0.05
        assert any("asian" in r.lower() for r in result.reasons)

    def test_floor_applied(self, risk, state_manager):
        """Lot scaled below 0.01 is floored to 0.01."""
        constraints = RiskConstraints(
            max_lot_size=0.02,
            scale_factor=0.1,
        )
        state_manager.update_risk_constraints(
            "agent-floor", constraints.model_dump(mode="json")
        )

        proposal = TradeProposal(
            symbol="XAUUSD",
            direction=TradeDirection.LONG,
            lot_size=0.05,
            strategy="VolBreakout",
            confidence=0.7,
        )
        result = risk.check_trade("agent-floor", proposal)
        assert result.approved is True
        assert result.adjusted_lot_size == 0.01


# ==================== End-to-End ====================

class TestEndToEnd:
    """Integration: calculate -> persist -> get."""

    def test_calculate_persist_get(self, risk, journal):
        """calculate_constraints persists and get_constraints retrieves."""
        # Create enough trades
        for i in range(1, 8):
            _create_trade(journal, i, pnl=100.0)
        for i in range(8, 11):
            _create_trade(journal, i, pnl=-50.0)

        agent = "agent-e2e"
        calc = risk.calculate_constraints(agent)
        got = risk.get_constraints(agent)

        assert got.status == calc.status
        assert got.kelly_fraction == calc.kelly_fraction
        assert got.scale_factor == calc.scale_factor

    def test_calculate_then_check(self, risk, journal):
        """Full flow: calculate constraints then check a proposal."""
        # Interleave wins/losses so consecutive limit doesn't trigger STOPPED
        for i in range(1, 6):
            _create_trade(journal, i, pnl=100.0)
        _create_trade(journal, 6, pnl=-50.0)
        _create_trade(journal, 7, pnl=100.0)
        _create_trade(journal, 8, pnl=-50.0)
        _create_trade(journal, 9, pnl=100.0)
        _create_trade(journal, 10, pnl=-50.0)

        agent = "agent-flow"
        risk.calculate_constraints(agent)

        proposal = TradeProposal(
            symbol="XAUUSD",
            direction=TradeDirection.LONG,
            lot_size=0.05,
            strategy="VolBreakout",
            confidence=0.7,
        )
        result = risk.check_trade(agent, proposal)
        assert result.approved is True
        assert result.adjusted_lot_size > 0
