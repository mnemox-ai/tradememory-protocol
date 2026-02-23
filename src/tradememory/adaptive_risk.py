"""
AdaptiveRisk - Dynamic position sizing based on trade memory.
Implements Blueprint Section 2.1 AdaptiveRisk functionality.

Pure rule-based (no LLM dependency). Reads TradeJournal history,
calculates performance metrics, outputs dynamic risk constraints.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from .models import (
    TradeRecord, RiskStatus, RiskConstraints,
    TradeProposal, TradeCheckResult,
)
from .journal import TradeJournal
from .state import StateManager


# Default safe constraints for new agents or insufficient data
_SAFE_DEFAULTS = RiskConstraints(
    max_lot_size=0.1,
    risk_per_trade_pct=2.0,
    daily_loss_limit=500.0,
    scale_factor=1.0,
    session_adjustments={"asian": 1.0, "london": 1.0, "newyork": 1.0},
    consecutive_loss_limit=5,
    kelly_fraction=0.0,
    status=RiskStatus.ACTIVE,
    reason="Default constraints - insufficient trade history",
)


class AdaptiveRisk:
    """
    Dynamic risk management engine.

    Reads closed trades from TradeJournal, runs 5 risk algorithms,
    and produces RiskConstraints that a trading agent queries before
    opening a position.
    """

    MIN_TRADES = 5          # Minimum closed trades to calculate
    LOOKBACK_DAYS = 30      # Window for trade history

    def __init__(
        self,
        journal: Optional[TradeJournal] = None,
        state_manager: Optional[StateManager] = None,
        *,
        consecutive_loss_limit: int = 5,
        daily_loss_limit: float = 500.0,
        max_lot_size: float = 0.1,
    ):
        self.journal = journal or TradeJournal()
        self.state_manager = state_manager or StateManager()
        self._consecutive_loss_limit = consecutive_loss_limit
        self._daily_loss_limit = daily_loss_limit
        self._max_lot_size = max_lot_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_constraints(
        self,
        agent_id: str,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> RiskConstraints:
        """
        (Re)calculate risk constraints from trade history.

        Returns safe defaults if < MIN_TRADES closed trades.
        Persists result to StateManager.
        """
        closed = self._get_closed_trades(symbol=symbol, strategy=strategy)

        if len(closed) < self.MIN_TRADES:
            constraints = _SAFE_DEFAULTS.model_copy()
            constraints.max_lot_size = self._max_lot_size
            constraints.daily_loss_limit = self._daily_loss_limit
            constraints.consecutive_loss_limit = self._consecutive_loss_limit
            constraints.updated_at = datetime.now(timezone.utc)
            self._persist(agent_id, constraints)
            return constraints

        constraints = self._combine_constraints(closed)
        self._persist(agent_id, constraints)
        return constraints

    def get_constraints(self, agent_id: str) -> RiskConstraints:
        """
        Return stored constraints. Falls back to safe defaults
        if nothing persisted yet.
        """
        state = self.state_manager.load_state(agent_id)
        raw = state.risk_constraints

        if not raw:
            return _SAFE_DEFAULTS.model_copy()

        return RiskConstraints(**raw)

    def check_trade(
        self,
        agent_id: str,
        proposal: TradeProposal,
    ) -> TradeCheckResult:
        """
        Validate a trade proposal against current constraints.

        Only *reduces* lot size — never increases.
        Floor: 0.01 (minimum tradeable lot).
        """
        constraints = self.get_constraints(agent_id)
        lot = proposal.lot_size
        reasons: List[str] = []

        # 1. Status gate
        if constraints.status == RiskStatus.STOPPED:
            return TradeCheckResult(
                approved=False,
                adjusted_lot_size=0.0,
                reasons=[f"Trading stopped: {constraints.reason}"],
                constraints_applied=constraints,
            )

        # 2. Cap to max_lot_size
        if lot > constraints.max_lot_size:
            reasons.append(
                f"Lot capped from {lot} to {constraints.max_lot_size} (max_lot_size)"
            )
            lot = constraints.max_lot_size

        # 3. Apply global scale_factor
        if constraints.scale_factor < 1.0:
            new_lot = round(lot * constraints.scale_factor, 2)
            if new_lot < lot:
                reasons.append(
                    f"Scaled {lot} -> {new_lot} (scale_factor={constraints.scale_factor})"
                )
                lot = new_lot

        # 4. Apply session adjustment
        session = proposal.session
        if session and session in constraints.session_adjustments:
            adj = constraints.session_adjustments[session]
            if adj < 1.0:
                new_lot = round(lot * adj, 2)
                if new_lot < lot:
                    reasons.append(
                        f"Session '{session}' adjustment: {lot} -> {new_lot} (x{adj})"
                    )
                    lot = new_lot

        # 5. Floor
        if lot < 0.01:
            lot = 0.01
            reasons.append("Floor applied: minimum lot 0.01")

        return TradeCheckResult(
            approved=True,
            adjusted_lot_size=lot,
            reasons=reasons,
            constraints_applied=constraints,
        )

    # ------------------------------------------------------------------
    # Private: Risk algorithms
    # ------------------------------------------------------------------

    def _get_closed_trades(
        self,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> List[TradeRecord]:
        """Get closed trades within lookback window."""
        trades = self.journal.query_history(
            symbol=symbol, strategy=strategy, limit=1000
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.LOOKBACK_DAYS)
        closed = []
        for t in trades:
            if t.pnl is None:
                continue
            ts = t.timestamp
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                closed.append(t)
        return closed

    def _calculate_kelly(self, trades: List[TradeRecord]) -> float:
        """
        Quarter-Kelly criterion.

        f* = (p*b - q) / b  where p=win_rate, b=avg_win/avg_loss, q=1-p
        Returns 0.0 if no edge or insufficient data. Max 0.25.
        """
        wins = [t for t in trades if t.pnl is not None and t.pnl > 0]
        losses = [t for t in trades if t.pnl is not None and t.pnl < 0]

        if len(wins) < 2 or len(losses) < 2:
            return 0.0

        p = len(wins) / len(trades)
        q = 1 - p
        avg_win = sum(t.pnl for t in wins) / len(wins)  # type: ignore[arg-type]
        avg_loss = abs(sum(t.pnl for t in losses) / len(losses))  # type: ignore[arg-type]

        if avg_loss == 0:
            return 0.0

        b = avg_win / avg_loss
        kelly = (p * b - q) / b

        if kelly <= 0:
            return 0.0

        # Quarter-Kelly, capped at 25%
        return min(kelly / 4, 0.25)

    def _calculate_drawdown_scale(self, trades: List[TradeRecord]) -> float:
        """
        Scale factor based on running drawdown.

        DD > 10% -> 0.5x, DD > 5% -> 0.75x, else 1.0x.
        Uses cumulative PnL as proxy equity curve.
        """
        if not trades:
            return 1.0

        cumulative = 0.0
        peak = 0.0
        max_dd_pct = 0.0

        # Assume $10,000 starting equity for DD% calculation
        equity_base = 10000.0

        for t in trades:
            cumulative += (t.pnl or 0.0)
            equity = equity_base + cumulative
            if equity > peak:
                peak = equity
            if peak > 0:
                dd_pct = (peak - equity) / peak
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct

        if max_dd_pct > 0.10:
            return 0.5
        if max_dd_pct > 0.05:
            return 0.75
        return 1.0

    def _calculate_session_adjustments(
        self, trades: List[TradeRecord]
    ) -> Dict[str, float]:
        """
        Per-session lot multiplier based on win rate.

        Win rate < 40% -> 0.5x, < 50% -> 0.75x, else 1.0.
        Insufficient data (< 3 trades) -> 0.75 (conservative).
        """
        session_map: Dict[str, List[TradeRecord]] = {
            "asian": [], "london": [], "newyork": [],
        }

        for t in trades:
            session = None
            if t.market_context and t.market_context.session:
                session = t.market_context.session.lower()
            if session in session_map:
                session_map[session].append(t)

        adjustments: Dict[str, float] = {}
        for session, session_trades in session_map.items():
            if len(session_trades) < 3:
                adjustments[session] = 0.75
                continue
            wins = sum(
                1 for st in session_trades
                if st.pnl is not None and st.pnl > 0
            )
            wr = wins / len(session_trades)
            if wr < 0.40:
                adjustments[session] = 0.5
            elif wr < 0.50:
                adjustments[session] = 0.75
            else:
                adjustments[session] = 1.0

        return adjustments

    def _check_consecutive_losses(
        self, trades: List[TradeRecord]
    ) -> RiskStatus:
        """
        Check consecutive loss streak.

        >= limit -> STOPPED, >= limit-1 -> REDUCED, else ACTIVE.
        Trades sorted newest-first; streak resets on any win.
        """
        # Sort by timestamp descending (most recent first)
        sorted_trades = sorted(
            trades,
            key=lambda t: t.timestamp if isinstance(t.timestamp, str) else t.timestamp.isoformat(),
            reverse=True,
        )

        streak = 0
        for t in sorted_trades:
            if t.pnl is not None and t.pnl < 0:
                streak += 1
            else:
                break

        if streak >= self._consecutive_loss_limit:
            return RiskStatus.STOPPED
        if streak >= self._consecutive_loss_limit - 1:
            return RiskStatus.REDUCED
        return RiskStatus.ACTIVE

    def _check_daily_loss(self, trades: List[TradeRecord]) -> RiskStatus:
        """
        Check if today's realised loss exceeds daily limit.

        Exceeded -> STOPPED, >= 80% -> REDUCED, else ACTIVE.
        """
        today = datetime.now(timezone.utc).date()
        daily_loss = 0.0

        for t in trades:
            ts = t.timestamp
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts.date() == today and t.pnl is not None and t.pnl < 0:
                daily_loss += abs(t.pnl)

        if daily_loss >= self._daily_loss_limit:
            return RiskStatus.STOPPED
        if daily_loss >= self._daily_loss_limit * 0.8:
            return RiskStatus.REDUCED
        return RiskStatus.ACTIVE

    # ------------------------------------------------------------------
    # Private: Combine & persist
    # ------------------------------------------------------------------

    def _combine_constraints(
        self, trades: List[TradeRecord]
    ) -> RiskConstraints:
        """
        Run all 5 algorithms and merge into a single RiskConstraints.

        Worst-status-wins; REDUCED applies extra 0.5x scale.
        Kelly -> risk_per_trade_pct (0.5%-5% range).
        """
        kelly = self._calculate_kelly(trades)
        dd_scale = self._calculate_drawdown_scale(trades)
        session_adj = self._calculate_session_adjustments(trades)
        consec_status = self._check_consecutive_losses(trades)
        daily_status = self._check_daily_loss(trades)

        # Worst status wins
        status_priority = {
            RiskStatus.ACTIVE: 0,
            RiskStatus.REDUCED: 1,
            RiskStatus.STOPPED: 2,
        }
        worst = max(
            [consec_status, daily_status],
            key=lambda s: status_priority[s],
        )

        # Build reason string
        reasons = []
        if worst == RiskStatus.STOPPED:
            if consec_status == RiskStatus.STOPPED:
                reasons.append(
                    f"Consecutive loss limit ({self._consecutive_loss_limit}) reached"
                )
            if daily_status == RiskStatus.STOPPED:
                reasons.append(
                    f"Daily loss limit (${self._daily_loss_limit}) exceeded"
                )
        elif worst == RiskStatus.REDUCED:
            if consec_status == RiskStatus.REDUCED:
                reasons.append("Approaching consecutive loss limit")
            if daily_status == RiskStatus.REDUCED:
                reasons.append("Approaching daily loss limit (>80%)")

        # Scale factor
        scale = dd_scale
        if worst == RiskStatus.REDUCED:
            scale = round(scale * 0.5, 2)

        # Kelly -> risk_per_trade_pct  (0.5% – 5%)
        if kelly > 0:
            risk_pct = round(max(0.5, min(kelly * 100, 5.0)), 2)
        else:
            risk_pct = 2.0  # default when no edge detected

        reason_text = "; ".join(reasons) if reasons else "Calculated from trade history"

        return RiskConstraints(
            max_lot_size=self._max_lot_size,
            risk_per_trade_pct=risk_pct,
            daily_loss_limit=self._daily_loss_limit,
            scale_factor=scale,
            session_adjustments=session_adj,
            consecutive_loss_limit=self._consecutive_loss_limit,
            kelly_fraction=round(kelly, 4),
            status=worst,
            reason=reason_text,
            updated_at=datetime.now(timezone.utc),
        )

    def _persist(self, agent_id: str, constraints: RiskConstraints) -> None:
        """Save constraints to StateManager."""
        self.state_manager.update_risk_constraints(
            agent_id, constraints.model_dump(mode="json")
        )
