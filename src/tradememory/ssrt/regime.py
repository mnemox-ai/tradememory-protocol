"""Regime-aware null hypothesis for sequential testing."""

from __future__ import annotations

from typing import Any

from tradememory.ssrt.models import RegimeBaseline, TradeResult


class RegimeAwareNull:
    """Maintain per-regime performance baselines for null hypothesis.

    Uses Welford's online algorithm for running mean/variance per regime.
    When a regime has sufficient data (>= min_trades_per_regime), its mean
    is used as the null hypothesis. Otherwise falls back to default_null.

    Args:
        min_trades_per_regime: Minimum trades before using regime-specific null.
        default_null: Fallback null mean when insufficient regime data.
    """

    VALID_REGIMES = {"trending_up", "trending_down", "ranging", "volatile"}

    def __init__(self, min_trades_per_regime: int = 10, default_null: float = 0.0):
        self.min_trades_per_regime = min_trades_per_regime
        self.default_null = default_null

        # Per-regime Welford accumulators: {regime: {"n": int, "mean": float, "m2": float}}
        self._accumulators: dict[str, dict[str, float]] = {}
        # Track last update time per regime
        self._last_updated: dict[str, str] = {}

    def _validate_regime(self, regime: str) -> None:
        """Raise ValueError if regime is not valid."""
        if regime not in self.VALID_REGIMES:
            raise ValueError(
                f"Unknown regime '{regime}'. Valid: {sorted(self.VALID_REGIMES)}"
            )

    def update(self, trade: TradeResult) -> None:
        """Update regime baseline with new trade.

        Uses Welford's online algorithm for numerically stable running
        mean and variance computation.

        Args:
            trade: Trade result with regime and pnl_r fields.
        """
        self._validate_regime(trade.regime)

        regime = trade.regime
        if regime not in self._accumulators:
            self._accumulators[regime] = {"n": 0.0, "mean": 0.0, "m2": 0.0}

        acc = self._accumulators[regime]
        acc["n"] += 1
        n = acc["n"]
        delta = trade.pnl_r - acc["mean"]
        acc["mean"] += delta / n
        delta2 = trade.pnl_r - acc["mean"]
        acc["m2"] += delta * delta2

        self._last_updated[regime] = trade.timestamp

    def get_null(self, regime: str) -> tuple[float, float]:
        """Return (null_mean, sigma) for given regime.

        Falls back to default_null and pooled sigma if insufficient
        regime-specific data.

        Args:
            regime: Market regime string.

        Returns:
            Tuple of (null_mean, sigma).
        """
        self._validate_regime(regime)

        acc = self._accumulators.get(regime)

        if acc is None or acc["n"] < self.min_trades_per_regime:
            # Insufficient data — use defaults
            # Try pooled sigma from all regimes
            pooled_sigma = self._pooled_sigma()
            return (self.default_null, pooled_sigma if pooled_sigma > 0 else 1.5)

        n = acc["n"]
        mean = acc["mean"]
        variance = acc["m2"] / n if n > 1 else 0.0
        sigma = variance ** 0.5 if variance > 0 else 1.5

        return (mean, sigma)

    def _pooled_sigma(self) -> float:
        """Compute pooled standard deviation across all regimes."""
        total_n = 0.0
        total_m2 = 0.0
        for acc in self._accumulators.values():
            total_n += acc["n"]
            total_m2 += acc["m2"]
        if total_n <= 1:
            return 0.0
        return (total_m2 / total_n) ** 0.5

    def get_baselines(self) -> dict[str, RegimeBaseline]:
        """Return all regime baselines."""
        baselines = {}
        for regime, acc in self._accumulators.items():
            n = int(acc["n"])
            mean = acc["mean"]
            variance = acc["m2"] / n if n > 1 else 0.0
            sigma = variance ** 0.5 if variance > 0 else 0.0
            baselines[regime] = RegimeBaseline(
                regime=regime,
                mean_pnl_r=mean,
                std_pnl_r=sigma,
                trade_count=n,
                last_updated=self._last_updated.get(regime, ""),
            )
        return baselines

    def get_state(self) -> dict[str, Any]:
        """Serialize for persistence."""
        return {
            "min_trades_per_regime": self.min_trades_per_regime,
            "default_null": self.default_null,
            "accumulators": dict(self._accumulators),
            "last_updated": dict(self._last_updated),
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> RegimeAwareNull:
        """Restore from serialized state."""
        obj = cls(
            min_trades_per_regime=state["min_trades_per_regime"],
            default_null=state["default_null"],
        )
        obj._accumulators = {k: dict(v) for k, v in state["accumulators"].items()}
        obj._last_updated = dict(state["last_updated"])
        return obj
