"""Baseline retirement methods for comparison with mSPRT."""

from __future__ import annotations

from collections import deque
from typing import Optional

from tradememory.ssrt.models import TradeResult


class MaxDDBaseline:
    """Stop when max drawdown in R-multiples exceeds threshold.

    For R-multiple space, threshold is absolute (e.g., 5.0 means
    retire when cumulative R drops 5R from peak).
    """

    def __init__(self, threshold_r: float = 5.0):
        self.threshold_r = threshold_r
        self.peak: float = 0.0
        self.equity: float = 0.0

    def update(self, trade: TradeResult) -> str:
        self.equity += trade.pnl_r
        if self.equity > self.peak:
            self.peak = self.equity
        dd = self.peak - self.equity
        if dd >= self.threshold_r:
            return "RETIRE"
        return "CONTINUE"

    def reset(self):
        self.peak = 0.0
        self.equity = 0.0


class RollingSharpeBaseline:
    """Stop when N-trade rolling Sharpe stays below 0."""

    def __init__(self, window: int = 30, consecutive: int = 3):
        self.window = window
        self.consecutive = consecutive
        self._returns: deque = deque(maxlen=window)
        self._below_count: int = 0

    def update(self, trade: TradeResult) -> str:
        self._returns.append(trade.pnl_r)
        if len(self._returns) < self.window:
            return "CONTINUE"

        mean = sum(self._returns) / len(self._returns)
        var = sum((x - mean) ** 2 for x in self._returns) / len(self._returns)
        std = var ** 0.5 if var > 0 else 0.0
        sharpe = mean / std if std > 0 else 0.0

        if sharpe < 0:
            self._below_count += 1
        else:
            self._below_count = 0

        if self._below_count >= self.consecutive:
            return "RETIRE"
        return "CONTINUE"

    def reset(self):
        self._returns.clear()
        self._below_count = 0


class CUSUMBaseline:
    """CUSUM drift detection baseline.

    Uses one-sided CUSUM on binary win/loss outcomes to detect
    performance degradation (win rate dropping below target).
    """

    def __init__(self, threshold: float = 4.0, target_wr: float = 0.5):
        self.threshold = threshold
        self.target_wr = target_wr
        self._outcomes: list[float] = []
        self._cusum: float = 0.0

    def update(self, trade: TradeResult) -> str:
        # Binary outcome: 1 if win, 0 if loss
        outcome = 1.0 if trade.pnl_r > 0 else 0.0
        # Detect DOWNWARD drift: accumulate deviation below target
        self._cusum = max(0.0, self._cusum + (self.target_wr - outcome))

        if self._cusum >= self.threshold:
            return "RETIRE"
        return "CONTINUE"

    def reset(self):
        self._outcomes = []
        self._cusum = 0.0
