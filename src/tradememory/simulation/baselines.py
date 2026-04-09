"""Naive baseline agents for rigorous comparison.

Three dumb strategies that require zero intelligence:
- PeriodicReduceAgent: Every N trades, reduce lot for M trades
- RandomSkipAgent: Randomly skip X% of trades
- SimpleWRAgent: If rolling win rate < threshold, reduce lot

If CalibratedAgent (BOCPD + DQS) can't beat these, it has no novel contribution.
"""

from __future__ import annotations

import random
from typing import List, Optional

from tradememory.data.context_builder import MarketContext
from tradememory.evolution.models import CandidatePattern
from tradememory.simulation.agent import BaseAgent, SimulatedTrade, TradeSignal


class PeriodicReduceAgent(BaseAgent):
    """Baseline 1: Every N trades, reduce lot by X% for next M trades.

    No intelligence -- just periodic caution.
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
        self._trade_count = 0
        self._reduce_countdown = 0

    @property
    def name(self) -> str:
        return f"PeriodicReduce({self.strategy.name})"

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
        return signal


class RandomSkipAgent(BaseAgent):
    """Baseline 2: Randomly skip X% of trades.

    If changepoint's skip pattern is no better than random, it has no value.
    """

    def __init__(
        self,
        strategy: CandidatePattern,
        fixed_lot: float = 0.01,
        skip_rate: float = 0.3,
        seed: int = 42,
    ):
        super().__init__(strategy, fixed_lot)
        self._skip_rate = skip_rate
        self._rng = random.Random(seed)
        self.skipped_signals: int = 0

    @property
    def name(self) -> str:
        return f"RandomSkip({self.strategy.name})"

    def should_trade(self, context: MarketContext) -> Optional[TradeSignal]:
        signal = super().should_trade(context)
        if signal is None:
            return None
        if self._rng.random() < self._skip_rate:
            self.skipped_signals += 1
            return None
        return signal


class SimpleWRAgent(BaseAgent):
    """Baseline 3: If rolling win rate < threshold, reduce lot by 50%.

    Simple moving-average-of-outcomes. No Bayesian inference. No conjugate models.
    If BOCPD can't beat this, it has no added value over a moving average.
    """

    def __init__(
        self,
        strategy: CandidatePattern,
        fixed_lot: float = 0.01,
        window: int = 20,
        wr_threshold: float = 0.4,
        reduce_pct: float = 0.5,
    ):
        super().__init__(strategy, fixed_lot)
        self._window = window
        self._wr_threshold = wr_threshold
        self._reduce_pct = reduce_pct
        self._outcomes: List[bool] = []

    @property
    def name(self) -> str:
        return f"SimpleWR({self.strategy.name})"

    def should_trade(self, context: MarketContext) -> Optional[TradeSignal]:
        signal = super().should_trade(context)
        if signal is None:
            return None
        if len(self._outcomes) >= self._window:
            recent_wr = sum(self._outcomes[-self._window:]) / self._window
            if recent_wr < self._wr_threshold:
                signal.lot_size *= self._reduce_pct
        return signal

    def on_trade_complete(self, trade: SimulatedTrade):
        super().on_trade_complete(trade)
        self._outcomes.append(trade.pnl > 0)
