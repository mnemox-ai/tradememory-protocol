"""CUSUMOnlyAgent — BaseAgent + CUSUM adaptive position sizing.

No DQS. No BOCPD. No DB writes.
Simplest possible calibration: track rolling CUSUM deviation from baseline WR,
reduce lot when CUSUM fires, restore when it resets.

From Level 1 findings: CUSUM is the only component that works.
"""

from __future__ import annotations

from typing import List, Optional

from tradememory.data.context_builder import MarketContext
from tradememory.evolution.models import CandidatePattern
from tradememory.simulation.agent import BaseAgent, SimulatedTrade, TradeSignal


class CUSUMOnlyAgent(BaseAgent):
    """BaseAgent + CUSUM adaptive position sizing. No DQS. No BOCPD.

    Mechanism:
    1. Warm-start: build baseline WR from IS trades
    2. OOS: track rolling CUSUM deviation from baseline
    3. When CUSUM > threshold: lot * 0.5
    4. When CUSUM resets to 0: lot back to normal

    That's it. The simplest possible calibration.
    """

    def __init__(
        self,
        strategy: CandidatePattern,
        fixed_lot: float = 0.01,
        cusum_threshold: float = 4.0,
    ):
        super().__init__(strategy, fixed_lot)
        self._outcomes: List[bool] = []
        self._baseline_wr: float = 0.5  # updated by warm_start
        self._cusum_s: float = 0.0
        self._cusum_threshold: float = cusum_threshold
        self._cusum_alert: bool = False
        self._reduced_count: int = 0

    @property
    def name(self) -> str:
        return f"CUSUMOnly({self.strategy.name})"

    def warm_start(self, is_trades: List[SimulatedTrade]):
        """Establish baseline WR from IS trades. Does NOT accumulate CUSUM."""
        if not is_trades:
            return
        wins = sum(1 for t in is_trades if t.pnl > 0)
        self._baseline_wr = wins / len(is_trades)
        # Don't touch _cusum_s — warm-start only sets baseline

    def should_trade(self, context: MarketContext) -> Optional[TradeSignal]:
        """Entry logic from BaseAgent + lot adjustment from CUSUM. Never skips."""
        signal = super().should_trade(context)
        if signal is None:
            return None

        # Only adjust lot — NEVER skip
        if self._cusum_alert:
            signal.lot_size *= 0.5
            self._reduced_count += 1

        return signal

    def on_trade_complete(self, trade: SimulatedTrade):
        """Record + update CUSUM."""
        super().on_trade_complete(trade)
        won = trade.pnl > 0
        self._outcomes.append(won)

        # CUSUM: accumulate deviation from baseline
        cusum_x = 1.0 if won else 0.0
        self._cusum_s = max(0.0, self._cusum_s + (self._baseline_wr - cusum_x))
        self._cusum_alert = self._cusum_s > self._cusum_threshold

        # Reset when performance recovers
        if self._cusum_s == 0.0:
            self._cusum_alert = False
