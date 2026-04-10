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
