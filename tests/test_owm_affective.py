"""Tests for OWM affective module: EWMA confidence and risk appetite."""

import pytest

from tradememory.owm.affective import ewma_confidence, risk_appetite


# --- ewma_confidence ---


class TestEwmaConfidence:
    def test_empty_outcomes_returns_neutral(self):
        assert ewma_confidence([]) == 0.5

    def test_all_positive_outcomes_above_neutral(self):
        result = ewma_confidence([100.0, 200.0, 150.0])
        assert result > 0.5

    def test_all_negative_outcomes_below_neutral(self):
        result = ewma_confidence([-100.0, -200.0, -150.0])
        assert result < 0.5

    def test_convergence_with_many_wins(self):
        """Long winning streak should push confidence toward 1.0."""
        outcomes = [100.0] * 50
        result = ewma_confidence(outcomes)
        assert result > 0.7

    def test_convergence_with_many_losses(self):
        """Long losing streak should push confidence toward 0.0."""
        outcomes = [-100.0] * 50
        result = ewma_confidence(outcomes)
        assert result < 0.3

    def test_recent_outcomes_weighted_more(self):
        """With low lambda, recent outcomes dominate."""
        # Wins then big loss — low lambda should track the loss
        mostly_wins = [100.0] * 10 + [-500.0]
        result_low_lam = ewma_confidence(mostly_wins, lam=0.3)
        result_high_lam = ewma_confidence(mostly_wins, lam=0.95)
        # Low lambda reacts more to recent loss
        assert result_low_lam < result_high_lam

    def test_output_bounded_zero_one(self):
        for outcomes in [[1e6], [-1e6], [0.0], [100, -100, 50, -50]]:
            result = ewma_confidence(outcomes)
            assert 0.0 <= result <= 1.0

    def test_single_outcome(self):
        pos = ewma_confidence([500.0])
        neg = ewma_confidence([-500.0])
        assert pos > 0.5
        assert neg < 0.5

    def test_invalid_lambda_raises(self):
        with pytest.raises(ValueError):
            ewma_confidence([1.0], lam=0.0)
        with pytest.raises(ValueError):
            ewma_confidence([1.0], lam=1.0)
        with pytest.raises(ValueError):
            ewma_confidence([1.0], lam=-0.5)

    def test_symmetric_around_neutral(self):
        """Equal magnitude positive and negative should be near 0.5."""
        result = ewma_confidence([100.0, -100.0, 100.0, -100.0])
        assert 0.45 < result < 0.55


# --- risk_appetite ---


class TestRiskAppetite:
    def test_zero_drawdown_full_appetite(self):
        assert risk_appetite(0.0, 20.0) == 1.0

    def test_max_drawdown_minimum_appetite(self):
        assert risk_appetite(20.0, 20.0) == 0.1

    def test_beyond_max_drawdown_clamps_to_minimum(self):
        result = risk_appetite(30.0, 20.0)
        assert result == 0.1

    def test_half_drawdown(self):
        # 1 - (10/20)^2 = 1 - 0.25 = 0.75
        result = risk_appetite(10.0, 20.0)
        assert abs(result - 0.75) < 1e-9

    def test_quadratic_shape(self):
        """Appetite should drop slowly at first, then faster."""
        a1 = risk_appetite(5.0, 20.0)   # 1 - (0.25)^2 = 0.9375
        a2 = risk_appetite(10.0, 20.0)  # 1 - (0.5)^2  = 0.75
        a3 = risk_appetite(15.0, 20.0)  # 1 - (0.75)^2 = 0.4375
        # Drop from 5→10 < drop from 10→15
        drop_1 = a1 - a2
        drop_2 = a2 - a3
        assert drop_2 > drop_1

    def test_invalid_max_dd_raises(self):
        with pytest.raises(ValueError):
            risk_appetite(5.0, 0.0)
        with pytest.raises(ValueError):
            risk_appetite(5.0, -10.0)

    def test_negative_drawdown_raises(self):
        with pytest.raises(ValueError):
            risk_appetite(-5.0, 20.0)

    def test_output_always_at_least_minimum(self):
        """Even extreme drawdowns can't go below 0.1."""
        for dd in [50, 100, 1000]:
            assert risk_appetite(float(dd), 20.0) >= 0.1
