"""Tests for RegimeDecayDetector — triple-confirmation system."""

import pytest

from tradememory.evolution.models import FitnessMetrics
from tradememory.evolution.regime_detector import (
    DecayAssessment,
    RegimeDecayDetector,
    RegimeDetectorConfig,
    TradeResult,
    _invert_3x3,
    _mahalanobis,
)


# --- Fixtures ---


def make_baseline(win_rate=0.6, trade_count=100, max_drawdown_pct=15.0):
    return FitnessMetrics(
        win_rate=win_rate,
        trade_count=trade_count,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=1.5,
        profit_factor=1.8,
        total_pnl=1000.0,
        avg_trade_pnl=10.0,
    )


def make_trade(is_win: bool, pnl: float, atr_ratio=0.5, trend=0.1, atr_pct=50.0):
    return TradeResult(
        is_win=is_win,
        pnl=pnl,
        atr_ratio=atr_ratio,
        trend_12h_pct=trend,
        atr_percentile=atr_pct,
    )


def make_training_features(n=100, atr_ratio=0.5, trend=0.1, atr_pct=50.0, noise=0.05):
    """Generate training features with small noise around center."""
    import random
    random.seed(42)
    features = []
    for _ in range(n):
        features.append((
            atr_ratio + random.gauss(0, noise),
            trend + random.gauss(0, noise),
            atr_pct + random.gauss(0, noise * 100),
        ))
    return features


# --- Test: insufficient trades ---


class TestInsufficientTrades:
    def test_below_min_trades_no_assessment(self):
        detector = RegimeDecayDetector(baseline=make_baseline())
        for _ in range(19):
            detector.add_trade(make_trade(True, 10.0))
        result = detector.assess()
        assert not result.decay_confirmed
        assert result.total_trades == 19
        assert "Insufficient" in result.reason

    def test_zero_trades(self):
        detector = RegimeDecayDetector(baseline=make_baseline())
        result = detector.assess()
        assert not result.decay_confirmed
        assert result.total_trades == 0

    def test_exactly_min_trades_runs_assessment(self):
        detector = RegimeDecayDetector(baseline=make_baseline())
        for _ in range(20):
            detector.add_trade(make_trade(True, 10.0))
        result = detector.assess()
        # Should run assessment (not "Insufficient")
        assert "Insufficient" not in result.reason
        assert result.total_trades == 20


# --- Test: stable scenario (no decay) ---


class TestStableScenario:
    def test_stable_no_decay(self):
        """60% win rate continues live → no decay."""
        detector = RegimeDecayDetector(baseline=make_baseline(win_rate=0.6))
        detector.fit_market_baseline(make_training_features())

        # 60% win rate, small positive PnL
        for i in range(30):
            is_win = i % 5 < 3  # 3/5 = 60%
            detector.add_trade(make_trade(is_win, 10.0 if is_win else -8.0))

        result = detector.assess()
        assert not result.decay_confirmed
        assert result.signals_fired < 2

    def test_stable_with_features_no_ood(self):
        """Stable market features → OOD doesn't fire."""
        detector = RegimeDecayDetector(baseline=make_baseline())
        features = make_training_features(n=100)
        detector.fit_market_baseline(features)

        for i in range(25):
            is_win = i % 5 < 3
            detector.add_trade(make_trade(
                is_win, 10.0 if is_win else -8.0,
                atr_ratio=0.5, trend=0.1, atr_pct=50.0,
            ))

        result = detector.assess()
        ood_signal = next(s for s in result.signals if s.name == "market_ood")
        assert not ood_signal.fired


# --- Test: decay scenario ---


class TestDecayScenario:
    def test_win_rate_drops_to_30pct(self):
        """Win rate drops from 60% to 30% → decay detected."""
        detector = RegimeDecayDetector(baseline=make_baseline(win_rate=0.6, trade_count=50))
        detector.fit_market_baseline(make_training_features())

        # 30% win rate live (severe decay) + drawdown
        equity = 0.0
        for i in range(30):
            is_win = i % 10 < 3  # 30%
            pnl = 10.0 if is_win else -15.0
            equity += pnl
            # Also make market OOD
            detector.add_trade(make_trade(
                is_win, pnl,
                atr_ratio=1.5, trend=2.0, atr_pct=95.0,  # far from training
            ))

        result = detector.assess()
        assert result.decay_confirmed
        assert result.signals_fired >= 2

    def test_only_win_rate_decay_no_confirm_with_one_signal(self):
        """Only S1 fires → not enough for confirmation (need 2/3)."""
        detector = RegimeDecayDetector(
            baseline=make_baseline(win_rate=0.6, trade_count=20, max_drawdown_pct=99.0),
        )
        # No OOD baseline → S3 won't fire
        # Very high max_drawdown_pct baseline → S2 threshold = 148.5%, won't fire

        # 20% win rate, but tiny losses → no drawdown exceedance
        for i in range(25):
            is_win = i % 5 == 0  # 20% win rate
            detector.add_trade(make_trade(is_win, 5.0 if is_win else -1.0))

        result = detector.assess()
        wr_signal = next(s for s in result.signals if s.name == "win_rate_decay")
        # Win rate decay should fire (20% << 60% baseline with only 20 prior trades)
        assert wr_signal.fired
        # DD signal should NOT fire (tiny losses, massive baseline MDD)
        dd_signal = next(s for s in result.signals if s.name == "drawdown_exceedance")
        assert not dd_signal.fired
        # OOD should NOT fire (no baseline fitted)
        ood_signal = next(s for s in result.signals if s.name == "market_ood")
        assert not ood_signal.fired
        # Only 1 signal → no confirmation
        assert not result.decay_confirmed


# --- Test: OOD scenario ---


class TestOODScenario:
    def test_atr_suddenly_3x(self):
        """ATR jumps 3x from training → OOD signal fires."""
        detector = RegimeDecayDetector(baseline=make_baseline())
        features = make_training_features(n=200, atr_ratio=0.5, trend=0.1, atr_pct=50.0, noise=0.02)
        detector.fit_market_baseline(features)

        # Normal trades but extreme market features
        for i in range(25):
            detector.add_trade(make_trade(
                True, 10.0,
                atr_ratio=1.5,  # 3x normal
                trend=3.0,  # 30x normal
                atr_pct=98.0,  # near max
            ))

        result = detector.assess()
        ood_signal = next(s for s in result.signals if s.name == "market_ood")
        assert ood_signal.fired

    def test_no_features_no_ood(self):
        """Trades without features → OOD signal doesn't fire."""
        detector = RegimeDecayDetector(baseline=make_baseline())
        detector.fit_market_baseline(make_training_features())

        for i in range(25):
            detector.add_trade(TradeResult(is_win=True, pnl=10.0))

        result = detector.assess()
        ood_signal = next(s for s in result.signals if s.name == "market_ood")
        assert not ood_signal.fired


# --- Test: drawdown exceedance ---


class TestDrawdownExceedance:
    def test_large_drawdown_fires(self):
        """Drawdown > 1.5x baseline MDD → S2 fires."""
        baseline = make_baseline(max_drawdown_pct=10.0)
        detector = RegimeDecayDetector(baseline=baseline)

        # Build up equity then crash
        for _ in range(5):
            detector.add_trade(make_trade(True, 100.0))
        # Now lose a lot (>15% of peak = 500)
        for _ in range(15):
            detector.add_trade(make_trade(False, -50.0))

        result = detector.assess()
        dd_signal = next(s for s in result.signals if s.name == "drawdown_exceedance")
        assert dd_signal.fired


# --- Test: cooling period ---


class TestCoolingPeriod:
    def test_cooling_after_trigger(self):
        """After decay is confirmed, next 5 trades are in cooling."""
        detector = RegimeDecayDetector(
            baseline=make_baseline(win_rate=0.6, trade_count=20, max_drawdown_pct=5.0),
            config=RegimeDetectorConfig(cooling_period=5),
        )
        detector.fit_market_baseline(make_training_features())

        # Force decay: all losses + OOD
        for _ in range(25):
            detector.add_trade(make_trade(
                False, -20.0,
                atr_ratio=2.0, trend=5.0, atr_pct=99.0,
            ))

        # First assessment triggers
        r1 = detector.assess()
        assert r1.decay_confirmed

        # Add 3 more trades — should be in cooling
        for _ in range(3):
            detector.add_trade(make_trade(False, -10.0))

        r2 = detector.assess()
        assert r2.in_cooling
        assert not r2.decay_confirmed

        # Add 3 more to exit cooling (total 6 > 5)
        for _ in range(3):
            detector.add_trade(make_trade(False, -10.0))

        r3 = detector.assess()
        assert not r3.in_cooling


# --- Test: helper functions ---


class TestHelpers:
    def test_invert_3x3_identity(self):
        m = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        inv = _invert_3x3(m)
        assert inv is not None
        for i in range(3):
            for j in range(3):
                expected = 1.0 if i == j else 0.0
                assert abs(inv[i][j] - expected) < 1e-10

    def test_invert_3x3_singular(self):
        m = [[1, 2, 3], [2, 4, 6], [1, 2, 3]]
        assert _invert_3x3(m) is None

    def test_mahalanobis_identity_cov(self):
        mean = [0.0, 0.0, 0.0]
        inv_cov = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        d = _mahalanobis((3.0, 4.0, 0.0), mean, inv_cov)
        assert abs(d - 5.0) < 1e-10  # sqrt(9 + 16) = 5

    def test_mahalanobis_at_mean_is_zero(self):
        mean = [1.0, 2.0, 3.0]
        inv_cov = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        d = _mahalanobis((1.0, 2.0, 3.0), mean, inv_cov)
        assert abs(d) < 1e-10


# --- Test: edge cases ---


class TestEdgeCases:
    def test_no_training_baseline_ood_skip(self):
        """Without fit_market_baseline, OOD signal returns not-fired."""
        detector = RegimeDecayDetector(baseline=make_baseline())
        for _ in range(25):
            detector.add_trade(make_trade(True, 10.0))
        result = detector.assess()
        ood = next(s for s in result.signals if s.name == "market_ood")
        assert not ood.fired

    def test_custom_config(self):
        config = RegimeDetectorConfig(min_trades=10, cooling_period=3)
        detector = RegimeDecayDetector(baseline=make_baseline(), config=config)
        for _ in range(10):
            detector.add_trade(make_trade(True, 10.0))
        result = detector.assess()
        assert result.total_trades == 10
        assert "Insufficient" not in result.reason

    def test_all_winning_trades_no_decay(self):
        """100% win rate → no decay signals."""
        detector = RegimeDecayDetector(baseline=make_baseline(win_rate=0.6))
        for _ in range(30):
            detector.add_trade(make_trade(True, 10.0))
        result = detector.assess()
        assert not result.decay_confirmed
        wr = next(s for s in result.signals if s.name == "win_rate_decay")
        assert not wr.fired
