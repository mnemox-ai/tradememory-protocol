"""MaxDDStop baseline: reduce lot when equity drawdown exceeds threshold.

This is the standard risk management approach that the paper should compare against.
When equity DD exceeds X% of peak, reduce lot by 50%. Restore when DD recovers.

Usage: imported by compare_maxdd.py
"""
from __future__ import annotations

import sys
import os
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tradememory.simulation.agent import BaseAgent, SimulatedTrade, TradeSignal
from tradememory.data.context_builder import MarketContext
from tradememory.evolution.models import CandidatePattern

from typing import Optional


class MaxDDStopAgent(BaseAgent):
    """Reduce lot when equity drawdown exceeds threshold.

    Standard risk management approach: track equity curve,
    when DD from peak > dd_threshold, reduce lot by reduce_pct.
    """

    def __init__(
        self,
        strategy: CandidatePattern,
        fixed_lot: float = 0.01,
        dd_threshold: float = 0.15,  # 15% DD triggers reduction
        reduce_pct: float = 0.5,
    ):
        super().__init__(strategy, fixed_lot=fixed_lot)
        self._dd_threshold = dd_threshold
        self._reduce_pct = reduce_pct
        self._equity = 0.0
        self._peak_equity = 0.0
        self._reduced_count = 0
        self._trade_index = 0

    def warm_start(self, is_trades: List[SimulatedTrade]):
        """Compute IS equity to set initial peak."""
        for t in is_trades:
            self._equity += t.pnl
            self._peak_equity = max(self._peak_equity, self._equity)

    def _get_dd_adjusted_lot(self) -> float:
        """Compute lot size based on current equity drawdown."""
        if self._peak_equity > 0:
            dd_pct = (self._peak_equity - self._equity) / self._peak_equity
        else:
            dd_pct = 0.0

        if dd_pct > self._dd_threshold:
            self._reduced_count += 1
            return self.fixed_lot * self._reduce_pct
        return self.fixed_lot

    def should_trade(self, context: MarketContext) -> Optional[TradeSignal]:
        """Override to apply DD-adjusted lot sizing."""
        base_signal = super().should_trade(context)
        if base_signal is None:
            return None

        lot = self._get_dd_adjusted_lot()
        self._trade_index += 1

        return TradeSignal(
            direction=base_signal.direction,
            lot_size=lot,
            reason=f"MaxDDStop: lot={lot:.4f}",
        )

    def on_trade_complete(self, trade: SimulatedTrade):
        """Update equity tracking after trade completes."""
        self.trades.append(trade)
        self._equity += trade.pnl * (trade.lot_size / self.fixed_lot)
        self._peak_equity = max(self._peak_equity, self._equity)
