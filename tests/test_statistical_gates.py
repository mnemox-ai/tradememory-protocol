"""Tests for Statistical Gates — DSR, MinBTL, BH-FDR."""

import math

import pytest

from tradememory.evolution.statistical_gates import (
    benjamini_hochberg,
    deflated_sharpe_ratio,
    min_backtest_length,
    _norm_cdf,
)


# --- Test: Deflated Sharpe Ratio ---


class TestDeflatedSharpeRatio:
    def test_single_trial_strong_sharpe(self):
        """M=1, SR=2.0, T=100 → DSR > 0 (no selection bias)."""
        dsr, p = deflated_sharpe_ratio(
            observed_sr=2.0, num_trials=1, num_obs=100,
        )
        assert dsr > 0, f"DSR should be > 0 for single trial strong SR, got {dsr}"
        assert p < 0.05

    def test_many_trials_weak_sharpe(self):
        """M=10000, SR=0.3, T=50 → DSR < 0 (heavy selection bias, weak SR)."""
        dsr, p = deflated_sharpe_ratio(
            observed_sr=0.3, num_trials=10000, num_obs=50,
        )
        assert dsr < 0, f"DSR should be < 0 for 10K trials with SR=0.3, T=50, got {dsr}"
        assert p > 0.5

    def test_m1000_sr2_t100_positive(self):
        """M=1000, SR=2.0, T=100 → DSR > 0 (verification criterion)."""
        dsr, p = deflated_sharpe_ratio(
            observed_sr=2.0, num_trials=1000, num_obs=100,
        )
        assert dsr > 0, f"DSR(M=1000, SR=2.0, T=100) should be > 0, got {dsr}"

    def test_higher_trials_lower_dsr(self):
        """More trials → lower DSR (more selection bias)."""
        dsr_10, _ = deflated_sharpe_ratio(2.0, num_trials=10, num_obs=200)
        dsr_1000, _ = deflated_sharpe_ratio(2.0, num_trials=1000, num_obs=200)
        assert dsr_10 > dsr_1000

    def test_longer_track_record_higher_dsr(self):
        """More observations → higher DSR (more precise estimate)."""
        dsr_50, _ = deflated_sharpe_ratio(1.5, num_trials=100, num_obs=50)
        dsr_500, _ = deflated_sharpe_ratio(1.5, num_trials=100, num_obs=500)
        # Both positive since SR=1.5 easily beats the null max for M=100
        assert dsr_500 > dsr_50

    def test_zero_sr(self):
        """SR=0 with many trials → DSR << 0."""
        dsr, p = deflated_sharpe_ratio(0.0, num_trials=100, num_obs=100)
        assert dsr < 0
        assert p > 0.5

    def test_negative_sr(self):
        """Negative SR → DSR < 0."""
        dsr, p = deflated_sharpe_ratio(-1.0, num_trials=1, num_obs=100)
        assert dsr < 0

    def test_skewness_effect(self):
        """Negative skew increases SE → lowers DSR."""
        dsr_normal, _ = deflated_sharpe_ratio(1.5, 100, 200, skewness=0)
        dsr_negskew, _ = deflated_sharpe_ratio(1.5, 100, 200, skewness=-2)
        # Negative skew with positive SR actually decreases SE numerator,
        # but the formula is (1 - skew*SR + ...), so -skew*SR = +2*1.5 = +3
        # which increases SE → lowers DSR
        assert dsr_negskew < dsr_normal

    def test_fat_tails_effect(self):
        """Higher kurtosis → higher SE → lower DSR."""
        dsr_normal, _ = deflated_sharpe_ratio(1.5, 100, 200, kurtosis=3)
        dsr_fat, _ = deflated_sharpe_ratio(1.5, 100, 200, kurtosis=6)
        assert dsr_fat < dsr_normal

    def test_edge_case_invalid_inputs(self):
        """Invalid inputs return safe defaults."""
        dsr, p = deflated_sharpe_ratio(1.0, num_trials=0, num_obs=100)
        assert dsr == 0.0 and p == 1.0

        dsr, p = deflated_sharpe_ratio(1.0, num_trials=1, num_obs=1)
        assert dsr == 0.0 and p == 1.0


# --- Test: Minimum Backtest Length ---


class TestMinBacktestLength:
    def test_many_trials_moderate_sr(self):
        """M=1000, SR*=1.5 → needs observations to be significant."""
        t = min_backtest_length(target_sr=1.5, num_trials=1000)
        assert t >= 2, f"Should need at least 2 observations, got {t}"

    def test_single_trial_strong_sr(self):
        """M=1, SR*=2.0 → very few observations needed."""
        t = min_backtest_length(target_sr=2.0, num_trials=1)
        assert 2 <= t <= 20, f"Expected 2-20, got {t}"

    def test_more_trials_need_more_obs(self):
        """More trials → longer backtest needed."""
        t_10 = min_backtest_length(1.5, num_trials=10)
        t_1000 = min_backtest_length(1.5, num_trials=1000)
        assert t_1000 >= t_10

    def test_higher_sr_needs_fewer_obs(self):
        """Higher target SR → fewer observations needed."""
        t_low = min_backtest_length(1.0, num_trials=100)
        t_high = min_backtest_length(3.0, num_trials=100)
        assert t_high <= t_low

    def test_zero_sr(self):
        t = min_backtest_length(0.0, num_trials=100)
        assert t == 0

    def test_negative_sr(self):
        t = min_backtest_length(-1.0, num_trials=100)
        assert t == 0


# --- Test: Benjamini-Hochberg ---


class TestBenjaminiHochberg:
    def test_known_rejections(self):
        """Classic BH example with known results."""
        # 5 p-values, alpha=0.05
        p_values = [0.001, 0.008, 0.039, 0.041, 0.45]
        results = benjamini_hochberg(p_values, alpha=0.05)

        assert len(results) == 5
        # p=0.001 → rank 1 → threshold 0.01 → sig
        assert results[0][2] is True  # idx 0, p=0.001
        # p=0.008 → rank 2 → threshold 0.02 → sig
        assert results[1][2] is True  # idx 1, p=0.008
        # p=0.039 → rank 3 → threshold 0.03 → NOT sig (0.039 > 0.03)
        # But BH is step-up: largest k where p_(k) <= k/m*alpha
        # Sorted: 0.001, 0.008, 0.039, 0.041, 0.45
        # k=1: 0.001 <= 0.01 ✓
        # k=2: 0.008 <= 0.02 ✓
        # k=3: 0.039 <= 0.03 ✗
        # So max k=2, first 2 are significant
        assert results[2][2] is False  # idx 2, p=0.039
        assert results[4][2] is False  # idx 4, p=0.45

    def test_all_significant(self):
        """All p-values very small → all significant."""
        p_values = [0.001, 0.002, 0.003]
        results = benjamini_hochberg(p_values, alpha=0.05)
        assert all(r[2] for r in results)

    def test_none_significant(self):
        """All p-values large → none significant."""
        p_values = [0.5, 0.6, 0.7, 0.8]
        results = benjamini_hochberg(p_values, alpha=0.05)
        assert not any(r[2] for r in results)

    def test_empty_input(self):
        assert benjamini_hochberg([]) == []

    def test_single_value_significant(self):
        results = benjamini_hochberg([0.01], alpha=0.05)
        assert len(results) == 1
        assert results[0][2] is True

    def test_single_value_not_significant(self):
        results = benjamini_hochberg([0.1], alpha=0.05)
        assert len(results) == 1
        assert results[0][2] is False

    def test_preserves_original_order(self):
        """Results should be in original index order."""
        p_values = [0.5, 0.001, 0.3]
        results = benjamini_hochberg(p_values, alpha=0.05)
        assert results[0][0] == 0  # original idx 0
        assert results[1][0] == 1
        assert results[2][0] == 2
        # Only idx 1 (p=0.001) is significant
        assert results[1][2] is True
        assert results[0][2] is False

    def test_higher_alpha_more_rejections(self):
        p_values = [0.01, 0.03, 0.06, 0.10]
        strict = benjamini_hochberg(p_values, alpha=0.01)
        lenient = benjamini_hochberg(p_values, alpha=0.10)
        n_strict = sum(1 for r in strict if r[2])
        n_lenient = sum(1 for r in lenient if r[2])
        assert n_lenient >= n_strict


# --- Test: norm_cdf helper ---


class TestNormCDF:
    def test_zero(self):
        assert abs(_norm_cdf(0) - 0.5) < 1e-10

    def test_large_positive(self):
        assert _norm_cdf(5.0) > 0.999

    def test_large_negative(self):
        assert _norm_cdf(-5.0) < 0.001

    def test_symmetry(self):
        assert abs(_norm_cdf(1.0) + _norm_cdf(-1.0) - 1.0) < 1e-10
