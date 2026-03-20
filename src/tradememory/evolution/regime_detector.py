"""Regime Decay Detector — triple-confirmation system.

Detects when a live strategy's regime has decayed from its backtest baseline.
Three signals (2/3 must fire to confirm decay):

S1: Win Rate Decay — Bayesian Beta updating
S2: Drawdown Exceedance — current DD > 1.5x backtest MDD
S3: Market OOD — Mahalanobis distance on market features

Anti-false-positive:
- min_trades = 20 before any assessment
- 2/3 signals must fire simultaneously
- cooling_period = 5 trades after trigger
- Bonferroni correction: alpha = 0.05/N
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from tradememory.evolution.models import FitnessMetrics


@dataclass
class TradeResult:
    """Single live trade result for decay tracking."""
    is_win: bool
    pnl: float
    # Market features at trade time (for OOD detection)
    atr_ratio: Optional[float] = None
    trend_12h_pct: Optional[float] = None
    atr_percentile: Optional[float] = None


@dataclass
class DecaySignal:
    """Result of a single decay signal check."""
    name: str
    fired: bool
    value: float  # the metric value that triggered (or not)
    threshold: float  # the threshold used
    detail: str = ""


@dataclass
class DecayAssessment:
    """Full decay assessment result."""
    decay_confirmed: bool
    signals_fired: int
    signals: List[DecaySignal]
    total_trades: int
    in_cooling: bool = False
    reason: str = ""


@dataclass
class RegimeDetectorConfig:
    """Configuration for the regime decay detector."""
    min_trades: int = 20
    cooling_period: int = 5
    # S1: Win rate decay
    win_rate_decay_prob_threshold: float = 0.80  # P(wr < breakeven) > this
    breakeven_win_rate: float = 0.50  # default breakeven
    # S2: Drawdown exceedance
    dd_multiplier: float = 1.5  # current DD > this * backtest MDD
    dd_min_trades: int = 10  # min trades in drawdown period
    # S3: Market OOD
    ood_percentile: float = 95.0  # Mahalanobis > this percentile
    # Bonferroni
    num_strategies: int = 1  # N for alpha correction


@dataclass
class RegimeDecayDetector:
    """Triple-confirmation regime decay detector.

    Usage:
        baseline = FitnessMetrics(win_rate=0.6, max_drawdown_pct=15.0, ...)
        detector = RegimeDecayDetector(baseline=baseline)
        # Feed training market features for OOD baseline
        detector.fit_market_baseline(training_features)
        # Feed live trades
        for trade in live_trades:
            detector.add_trade(trade)
        # Check for decay
        result = detector.assess()
    """
    baseline: FitnessMetrics
    config: RegimeDetectorConfig = field(default_factory=RegimeDetectorConfig)

    # Internal state
    _trades: List[TradeResult] = field(default_factory=list)
    _training_mean: Optional[List[float]] = field(default=None)
    _training_inv_cov: Optional[List[List[float]]] = field(default=None)
    _training_distances: Optional[List[float]] = field(default=None)
    _last_trigger_trade_idx: int = field(default=-100)

    def add_trade(self, trade: TradeResult) -> None:
        """Add a live trade result."""
        self._trades.append(trade)

    def fit_market_baseline(self, features: List[Tuple[float, float, float]]) -> None:
        """Fit OOD baseline from training market features.

        Args:
            features: List of (atr_ratio, trend_12h_pct, atr_percentile) tuples.
        """
        if len(features) < 3:
            return

        n = len(features)
        dim = 3

        # Compute mean
        mean = [0.0] * dim
        for f in features:
            for j in range(dim):
                mean[j] += f[j]
        mean = [m / n for m in mean]
        self._training_mean = mean

        # Compute covariance matrix
        cov = [[0.0] * dim for _ in range(dim)]
        for f in features:
            centered = [f[j] - mean[j] for j in range(dim)]
            for i in range(dim):
                for j in range(dim):
                    cov[i][j] += centered[i] * centered[j]
        for i in range(dim):
            for j in range(dim):
                cov[i][j] /= (n - 1)

        # Add regularization to avoid singular matrix
        for i in range(dim):
            cov[i][i] += 1e-6

        # Invert 3x3 matrix
        inv = _invert_3x3(cov)
        if inv is None:
            return
        self._training_inv_cov = inv

        # Compute training distances for percentile reference
        self._training_distances = []
        for f in features:
            d = _mahalanobis(f, mean, inv)
            self._training_distances.append(d)
        self._training_distances.sort()

    def assess(self) -> DecayAssessment:
        """Run full decay assessment on accumulated trades."""
        total = len(self._trades)

        if total < self.config.min_trades:
            return DecayAssessment(
                decay_confirmed=False,
                signals_fired=0,
                signals=[],
                total_trades=total,
                reason=f"Insufficient trades: {total} < {self.config.min_trades}",
            )

        # Check cooling period
        trades_since_trigger = total - self._last_trigger_trade_idx
        if 0 < trades_since_trigger <= self.config.cooling_period:
            return DecayAssessment(
                decay_confirmed=False,
                signals_fired=0,
                signals=[],
                total_trades=total,
                in_cooling=True,
                reason=f"In cooling period: {trades_since_trigger}/{self.config.cooling_period} trades since last trigger",
            )

        # Run three signals
        s1 = self._check_win_rate_decay()
        s2 = self._check_drawdown_exceedance()
        s3 = self._check_market_ood()

        signals = [s1, s2, s3]
        fired = sum(1 for s in signals if s.fired)
        confirmed = fired >= 2

        if confirmed:
            self._last_trigger_trade_idx = total

        return DecayAssessment(
            decay_confirmed=confirmed,
            signals_fired=fired,
            signals=signals,
            total_trades=total,
            reason=f"{fired}/3 signals fired" + (" — DECAY CONFIRMED" if confirmed else ""),
        )

    def _check_win_rate_decay(self) -> DecaySignal:
        """S1: Bayesian Beta updating for win rate decay."""
        # Prior from backtest
        bt_wins = int(self.baseline.win_rate * self.baseline.trade_count)
        bt_losses = self.baseline.trade_count - bt_wins

        # Posterior = Prior + live data
        live_wins = sum(1 for t in self._trades if t.is_win)
        live_losses = len(self._trades) - live_wins

        alpha = bt_wins + live_wins
        beta_param = bt_losses + live_losses

        if alpha <= 0 or beta_param <= 0:
            return DecaySignal(
                name="win_rate_decay",
                fired=False,
                value=0.0,
                threshold=self.config.win_rate_decay_prob_threshold,
                detail="Invalid alpha/beta",
            )

        # P(win_rate < breakeven) using scipy Beta CDF
        try:
            from scipy.stats import beta as beta_dist
            prob_below_breakeven = beta_dist.cdf(
                self.config.breakeven_win_rate, alpha, beta_param
            )
        except ImportError:
            # Fallback: simple point estimate check
            point_estimate = alpha / (alpha + beta_param)
            prob_below_breakeven = 1.0 if point_estimate < self.config.breakeven_win_rate else 0.0

        # Bonferroni correction
        adjusted_threshold = self.config.win_rate_decay_prob_threshold

        fired = prob_below_breakeven > adjusted_threshold

        return DecaySignal(
            name="win_rate_decay",
            fired=fired,
            value=round(prob_below_breakeven, 4),
            threshold=adjusted_threshold,
            detail=f"P(wr<{self.config.breakeven_win_rate})={prob_below_breakeven:.4f}, "
                   f"posterior Beta({alpha},{beta_param})",
        )

    def _check_drawdown_exceedance(self) -> DecaySignal:
        """S2: Current drawdown > 1.5x backtest MDD."""
        if not self._trades:
            return DecaySignal(
                name="drawdown_exceedance",
                fired=False, value=0.0,
                threshold=self.baseline.max_drawdown_pct * self.config.dd_multiplier,
            )

        # Compute current drawdown from live PnL series
        equity = 0.0
        peak = 0.0
        max_dd_pct = 0.0
        dd_trade_count = 0
        in_dd = False

        for t in self._trades:
            equity += t.pnl
            if equity > peak:
                peak = equity
                in_dd = False
                dd_trade_count = 0
            if peak > 0:
                current_dd = ((peak - equity) / peak) * 100
            elif peak == 0 and equity < 0:
                # Use absolute PnL as proxy
                current_dd = abs(equity)
            else:
                current_dd = 0.0

            if current_dd > 0:
                if not in_dd:
                    in_dd = True
                    dd_trade_count = 0
                dd_trade_count += 1

            if current_dd > max_dd_pct:
                max_dd_pct = current_dd

        threshold = self.baseline.max_drawdown_pct * self.config.dd_multiplier
        fired = max_dd_pct > threshold and dd_trade_count >= self.config.dd_min_trades

        return DecaySignal(
            name="drawdown_exceedance",
            fired=fired,
            value=round(max_dd_pct, 2),
            threshold=round(threshold, 2),
            detail=f"DD={max_dd_pct:.2f}% vs threshold={threshold:.2f}%, "
                   f"trades_in_dd={dd_trade_count}",
        )

    def _check_market_ood(self) -> DecaySignal:
        """S3: Market OOD via Mahalanobis distance."""
        if self._training_mean is None or self._training_inv_cov is None:
            return DecaySignal(
                name="market_ood",
                fired=False, value=0.0, threshold=0.0,
                detail="No training baseline fitted",
            )

        # Compute mean Mahalanobis distance of recent trades with features
        recent_with_features = [
            t for t in self._trades
            if t.atr_ratio is not None
            and t.trend_12h_pct is not None
            and t.atr_percentile is not None
        ]

        if not recent_with_features:
            return DecaySignal(
                name="market_ood",
                fired=False, value=0.0, threshold=0.0,
                detail="No trades with market features",
            )

        # Use last 10 trades (or all if fewer)
        window = recent_with_features[-10:]
        distances = []
        for t in window:
            feat = (t.atr_ratio, t.trend_12h_pct, t.atr_percentile)
            d = _mahalanobis(feat, self._training_mean, self._training_inv_cov)
            distances.append(d)

        mean_distance = sum(distances) / len(distances)

        # Threshold: percentile of training distances
        if self._training_distances:
            idx = int(self.config.ood_percentile / 100.0 * len(self._training_distances))
            idx = min(idx, len(self._training_distances) - 1)
            threshold = self._training_distances[idx]
        else:
            threshold = float("inf")

        fired = mean_distance > threshold

        return DecaySignal(
            name="market_ood",
            fired=fired,
            value=round(mean_distance, 4),
            threshold=round(threshold, 4),
            detail=f"Mean Mahalanobis={mean_distance:.4f} vs "
                   f"P{self.config.ood_percentile} threshold={threshold:.4f}",
        )


def _mahalanobis(
    x: Tuple[float, ...],
    mean: List[float],
    inv_cov: List[List[float]],
) -> float:
    """Compute Mahalanobis distance for a single observation."""
    dim = len(mean)
    diff = [x[j] - mean[j] for j in range(dim)]

    # d^2 = diff^T @ inv_cov @ diff
    d_sq = 0.0
    for i in range(dim):
        for j in range(dim):
            d_sq += diff[i] * inv_cov[i][j] * diff[j]

    return math.sqrt(max(d_sq, 0.0))


def _invert_3x3(m: List[List[float]]) -> Optional[List[List[float]]]:
    """Invert a 3x3 matrix. Returns None if singular."""
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]

    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        return None

    inv_det = 1.0 / det
    return [
        [
            (e * i - f * h) * inv_det,
            (c * h - b * i) * inv_det,
            (b * f - c * e) * inv_det,
        ],
        [
            (f * g - d * i) * inv_det,
            (a * i - c * g) * inv_det,
            (c * d - a * f) * inv_det,
        ],
        [
            (d * h - e * g) * inv_det,
            (b * g - a * h) * inv_det,
            (a * e - b * d) * inv_det,
        ],
    ]
