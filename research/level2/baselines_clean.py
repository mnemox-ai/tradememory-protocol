"""Clean naive baselines for Level 2 comparison.

All baselines:
- Never skip trades (only adjust lot)
- Have warm_start() method (even if no-op)
- Are drop-in replacements for CUSUMOnlyAgent in the experiment

If CUSUM can't beat these, it has no novel contribution.
"""

from __future__ import annotations

import random
from typing import List, Optional

from tradememory.data.context_builder import MarketContext
from tradememory.evolution.models import CandidatePattern
from tradememory.simulation.agent import BaseAgent, SimulatedTrade, TradeSignal


class PeriodicReduceAgent(BaseAgent):
    """Baseline 1: Every N trades, reduce lot for M trades.

    No intelligence — just periodic caution.
    """

    def __init__(
        self,
        strategy: CandidatePattern,
        fixed_lot: float = 0.01,
        period: int = 50,
        reduce_pct: float = 0.5,
        reduce_duration: int = 10,
    ):
        super().__init__(strategy, fixed_lot)
        self._period = period
        self._reduce_pct = reduce_pct
        self._reduce_duration = reduce_duration
        self._trade_count: int = 0
        self._reduce_countdown: int = 0
        self._reduced_count: int = 0

    @property
    def name(self) -> str:
        return f"PeriodicReduce({self.strategy.name})"

    def warm_start(self, is_trades: List[SimulatedTrade]):
        """No-op. Periodic doesn't use IS data."""
        pass

    def should_trade(self, context: MarketContext) -> Optional[TradeSignal]:
        signal = super().should_trade(context)
        if signal is None:
            return None
        self._trade_count += 1
        if self._trade_count % self._period == 0:
            self._reduce_countdown = self._reduce_duration
        if self._reduce_countdown > 0:
            self._reduce_countdown -= 1
            signal.lot_size *= self._reduce_pct
            self._reduced_count += 1
        return signal


class RandomReduceAgent(BaseAgent):
    """Baseline 2: Randomly reduce lot on X% of trades.

    If CUSUM's reduction pattern is no better than random, it has no value.
    """

    def __init__(
        self,
        strategy: CandidatePattern,
        fixed_lot: float = 0.01,
        reduce_rate: float = 0.3,
        reduce_pct: float = 0.5,
        seed: int = 42,
    ):
        super().__init__(strategy, fixed_lot)
        self._reduce_rate = reduce_rate
        self._reduce_pct = reduce_pct
        self._rng = random.Random(seed)
        self._reduced_count: int = 0

    @property
    def name(self) -> str:
        return f"RandomReduce({self.strategy.name})"

    def warm_start(self, is_trades: List[SimulatedTrade]):
        """No-op. Random doesn't use IS data."""
        pass

    def should_trade(self, context: MarketContext) -> Optional[TradeSignal]:
        signal = super().should_trade(context)
        if signal is None:
            return None
        if self._rng.random() < self._reduce_rate:
            signal.lot_size *= self._reduce_pct
            self._reduced_count += 1
        return signal


class SimpleWRAgent(BaseAgent):
    """Baseline 3: Rolling WR < baseline - delta -> reduce lot.

    Uses warm_start to set baseline (fair comparison with CUSUM).
    Simple moving average of outcomes — no Bayesian inference.
    """

    def __init__(
        self,
        strategy: CandidatePattern,
        fixed_lot: float = 0.01,
        window: int = 20,
        threshold_delta: float = 0.1,
        reduce_pct: float = 0.5,
    ):
        super().__init__(strategy, fixed_lot)
        self._window = window
        self._threshold_delta = threshold_delta
        self._reduce_pct = reduce_pct
        self._baseline_wr: float = 0.5
        self._outcomes: List[bool] = []
        self._reduced_count: int = 0

    @property
    def name(self) -> str:
        return f"SimpleWR({self.strategy.name})"

    def warm_start(self, is_trades: List[SimulatedTrade]):
        """Set baseline WR from IS trades (same as CUSUMOnlyAgent)."""
        if not is_trades:
            return
        wins = sum(1 for t in is_trades if t.pnl > 0)
        self._baseline_wr = wins / len(is_trades)

    def should_trade(self, context: MarketContext) -> Optional[TradeSignal]:
        signal = super().should_trade(context)
        if signal is None:
            return None
        if len(self._outcomes) >= self._window:
            recent_wr = sum(self._outcomes[-self._window:]) / self._window
            if recent_wr < self._baseline_wr - self._threshold_delta:
                signal.lot_size *= self._reduce_pct
                self._reduced_count += 1
        return signal

    def on_trade_complete(self, trade: SimulatedTrade):
        super().on_trade_complete(trade)
        self._outcomes.append(trade.pnl > 0)
