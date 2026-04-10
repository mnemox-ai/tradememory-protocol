"""Tests for MixtureSPRT engine."""
from __future__ import annotations

import numpy as np
import pytest

from tradememory.ssrt.core import MixtureSPRT
from tradememory.ssrt.models import SSRTVerdict


class TestMixtureSPRT:
    """Test suite for mSPRT engine."""

    def test_burn_in_returns_inconclusive(self):
        """First 20 trades should always return INCONCLUSIVE."""
        m = MixtureSPRT(burn_in=20)
        for i in range(19):
            v = m.update(-5.0)  # extreme negative
            assert v.decision == "INCONCLUSIVE", f"Trade {i+1} should be INCONCLUSIVE"

    def test_matching_null_returns_continue(self):
        """Trades matching null_mean should not trigger RETIRE."""
        rng = np.random.default_rng(42)
        m = MixtureSPRT(null_mean=1.0, sigma=1.5)
        for _ in range(50):
            v = m.update(rng.normal(1.0, 1.5))
        assert v.decision == "CONTINUE"

    def test_always_negative_returns_retire(self):
        """50 very negative trades should eventually trigger RETIRE."""
        rng = np.random.default_rng(42)
        m = MixtureSPRT(null_mean=0.0, sigma=1.0, tau=1.0)
        retired = False
        for _ in range(50):
            v = m.update(rng.normal(-2.0, 1.0))
            if v.decision == "RETIRE":
                retired = True
                break
        assert retired, "Should retire with consistently negative trades"

    def test_p_value_always_valid(self):
        """p_value should always be in [0, 1] after each update."""
        rng = np.random.default_rng(42)
        m = MixtureSPRT()
        for _ in range(100):
            v = m.update(rng.normal(0.0, 1.5))
            assert 0 <= v.p_value <= 1.0, f"p_value {v.p_value} out of range"

    def test_serialization_roundtrip(self):
        """get_state -> from_state should produce identical results."""
        rng = np.random.default_rng(42)
        m1 = MixtureSPRT(alpha=0.05, tau=1.0, sigma=1.5)
        for _ in range(10):
            m1.update(rng.normal(0.3, 1.0))

        state = m1.get_state()
        m2 = MixtureSPRT.from_state(state)

        # Next update should give identical results
        obs = 0.7
        v1 = m1.update(obs)
        v2 = m2.update(obs)
        assert v1.p_value == pytest.approx(v2.p_value)
        assert v1.lambda_n == pytest.approx(v2.lambda_n)

    def test_reset_clears_state(self):
        """After reset, should behave like fresh instance."""
        m = MixtureSPRT(null_mean=0.5, sigma=1.5)
        for _ in range(30):
            m.update(0.1)

        m.reset(null_mean=0.0, sigma=1.5)
        assert m.n == 0
        assert m.sum_z == 0.0

        v = m.update(0.5)

        m2 = MixtureSPRT(null_mean=0.0, sigma=1.5)
        v2 = m2.update(0.5)
        assert v.p_value == pytest.approx(v2.p_value)

    def test_type_i_error_control(self):
        """Under H0, RETIRE rate should be <= alpha + tolerance."""
        n_sims = 500
        alpha = 0.05
        n_trades = 100
        retires = 0

        for seed in range(n_sims):
            rng = np.random.default_rng(seed)
            m = MixtureSPRT(alpha=alpha, tau=1.0, sigma=1.0, null_mean=0.0)
            for _ in range(n_trades):
                v = m.update(rng.normal(0.0, 1.0))
                if v.decision == "RETIRE":
                    retires += 1
                    break

        error_rate = retires / n_sims
        assert error_rate <= 0.08, f"Type I error rate {error_rate:.3f} exceeds tolerance 0.08"

    def test_shift_null_preserves_count(self):
        """shift_null should NOT reset trade count."""
        m = MixtureSPRT(null_mean=0.0)
        for _ in range(30):
            m.update(0.5)
        assert m.n == 30
        m.shift_null(new_null_mean=0.3)
        assert m.n == 30  # count preserved

    def test_shift_null_equivalent_to_reprocess(self):
        """Shifting null should give same z_bar as reprocessing from scratch."""
        observations = [0.3, -0.1, 0.5, 0.8, -0.2, 0.4, 0.1, -0.3, 0.6, 0.2]

        # Method 1: Process with null=0.0, then shift to null=0.3
        m1 = MixtureSPRT(null_mean=0.0, sigma=1.0, burn_in=0)
        for obs in observations:
            m1.update(obs)
        m1.shift_null(new_null_mean=0.3)

        # Method 2: Process from scratch with null=0.3
        m2 = MixtureSPRT(null_mean=0.3, sigma=1.0, burn_in=0)
        for obs in observations:
            m2.update(obs)

        # z_bar should be identical
        z_bar_1 = m1.sum_z / m1.n
        z_bar_2 = m2.sum_z / m2.n
        assert abs(z_bar_1 - z_bar_2) < 1e-10

        # log_lambda should be identical (same sigma)
        assert abs(m1._log_lambda - m2._log_lambda) < 1e-10

    def test_shift_null_no_observations(self):
        """shift_null with no data should just update parameters."""
        m = MixtureSPRT(null_mean=0.0, sigma=1.5)
        m.shift_null(new_null_mean=0.5, new_sigma=2.0)
        assert m.null_mean == 0.5
        assert m.sigma == 2.0
        assert m.n == 0

    def test_shift_null_improves_regime_detection(self):
        """Regime-aware with shift_null should beat regime-aware with reset
        on regime_specific_decay scenario (the Phase 1 failure case).

        Uses frequent regime switches (every 10 trades) to amplify
        the evidence-preservation advantage of shift over reset.
        """
        from tradememory.ssrt.simulator import DecaySimulator
        from tradememory.ssrt.regime import RegimeAwareNull

        n_sims = 200
        shift_detections = 0
        reset_detections = 0

        # Frequent regime switches: reset loses evidence at each switch,
        # shift preserves it — making detection faster after burn-in
        regime_schedule = [
            (i, "trending_up" if (i // 10) % 2 == 0 else "ranging")
            for i in range(0, 200, 10)
        ]

        for seed in range(n_sims):
            trades = DecaySimulator.regime_specific_decay(
                n_trades=200, decay_at=50, seed=seed,
                regime_schedule=regime_schedule,
            )

            # Run with shift_null (Option B)
            msprt_shift = MixtureSPRT(alpha=0.05, tau=1.0, sigma=1.5, null_mean=0.5, burn_in=20)
            regime_null_shift = RegimeAwareNull(min_trades_per_regime=10)
            prev_regime = None
            shift_detected = False
            for trade in trades:
                regime_null_shift.update(trade)
                rn_mean, rn_sigma = regime_null_shift.get_null(trade.regime)
                if trade.regime != prev_regime and prev_regime is not None:
                    msprt_shift.shift_null(new_null_mean=rn_mean, new_sigma=rn_sigma)
                prev_regime = trade.regime
                v = msprt_shift.update(trade.pnl_r)
                if v.decision == "RETIRE":
                    shift_detected = True
                    break
            if shift_detected:
                shift_detections += 1

            # Run with reset (Option A — Phase 1 approach)
            msprt_reset = MixtureSPRT(alpha=0.05, tau=1.0, sigma=1.5, null_mean=0.5, burn_in=20)
            regime_null_reset = RegimeAwareNull(min_trades_per_regime=10)
            prev_regime = None
            reset_detected = False
            for trade in trades:
                regime_null_reset.update(trade)
                rn_mean, rn_sigma = regime_null_reset.get_null(trade.regime)
                if trade.regime != prev_regime and prev_regime is not None:
                    msprt_reset.reset(null_mean=rn_mean, sigma=rn_sigma)
                prev_regime = trade.regime
                v = msprt_reset.update(trade.pnl_r)
                if v.decision == "RETIRE":
                    reset_detected = True
                    break
            if reset_detected:
                reset_detections += 1

        # shift_null should detect MORE than reset (higher power)
        assert shift_detections > reset_detections, (
            f"shift_null ({shift_detections}) should beat reset ({reset_detections})"
        )

    def test_invalid_params_raise(self):
        """Invalid constructor params should raise ValueError."""
        with pytest.raises(ValueError):
            MixtureSPRT(alpha=0.0)
        with pytest.raises(ValueError):
            MixtureSPRT(alpha=1.0)
        with pytest.raises(ValueError):
            MixtureSPRT(tau=-1.0)
        with pytest.raises(ValueError):
            MixtureSPRT(sigma=0.0)
