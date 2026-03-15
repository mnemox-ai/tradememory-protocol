"""Tests for OWM memory decay functions."""

import math

import pytest

from tradememory.owm.decay import episodic_decay, regime_match_factor, semantic_decay


# --- episodic_decay ---


class TestEpisodicDecay:
    def test_fresh_memory_is_one(self):
        assert episodic_decay(0) == 1.0

    def test_30_day_below_threshold(self):
        """At 30 days (t=tau), strength should be < 0.71 (2^-0.5 ≈ 0.707)."""
        strength = episodic_decay(30)
        assert strength < 0.71

    def test_monotonically_decreasing(self):
        """Strength should decrease as age increases."""
        values = [episodic_decay(d) for d in [0, 7, 30, 90, 365]]
        for i in range(len(values) - 1):
            assert values[i] > values[i + 1]

    def test_never_reaches_zero(self):
        """Power-law decay never hits zero (unlike exponential)."""
        assert episodic_decay(10_000) > 0

    def test_rehearsal_boost(self):
        """Rehearsal should increase strength."""
        base = episodic_decay(30, rehearsal_count=0)
        boosted = episodic_decay(30, rehearsal_count=3)
        assert boosted > base

    def test_rehearsal_boost_formula(self):
        """Verify rehearsal boost matches 1 + 0.3*ln(1+n)."""
        age = 30
        n = 5
        base = episodic_decay(age, rehearsal_count=0)
        boosted = episodic_decay(age, rehearsal_count=n)
        expected_ratio = 1 + 0.3 * math.log(1 + n)
        assert abs(boosted / base - expected_ratio) < 1e-10

    def test_zero_rehearsal_no_boost(self):
        """rehearsal_count=0 should give boost factor of exactly 1.0."""
        assert episodic_decay(0, rehearsal_count=0) == 1.0

    def test_custom_tau_and_d(self):
        """Custom parameters should work correctly."""
        s = episodic_decay(60, tau=60, d=1.0)
        expected = (1 + 60 / 60) ** (-1.0)  # 0.5
        assert abs(s - expected) < 1e-10

    def test_negative_age_raises(self):
        with pytest.raises(ValueError, match="age_days"):
            episodic_decay(-1)

    def test_negative_rehearsal_raises(self):
        with pytest.raises(ValueError, match="rehearsal_count"):
            episodic_decay(10, rehearsal_count=-1)

    def test_zero_tau_raises(self):
        with pytest.raises(ValueError, match="tau"):
            episodic_decay(10, tau=0)


# --- semantic_decay ---


class TestSemanticDecay:
    def test_fresh_memory_is_one(self):
        assert semantic_decay(0) == 1.0

    def test_slower_than_episodic(self):
        """Semantic decay should be slower than episodic at same age."""
        age = 90
        assert semantic_decay(age) > episodic_decay(age)

    def test_180_day_value(self):
        """At tau=180, d=0.3, check reasonable retention."""
        s = semantic_decay(180)
        expected = 2 ** (-0.3)  # (1+1)^(-0.3)
        assert abs(s - expected) < 1e-10

    def test_negative_age_raises(self):
        with pytest.raises(ValueError, match="age_days"):
            semantic_decay(-5)


# --- regime_match_factor ---


class TestRegimeMatchFactor:
    def test_exact_match(self):
        assert regime_match_factor("trending", "trending") == 1.0

    def test_mismatch(self):
        assert regime_match_factor("trending", "ranging") == 0.3

    def test_memory_regime_none(self):
        assert regime_match_factor(None, "trending") == 0.6

    def test_current_regime_none(self):
        assert regime_match_factor("trending", None) == 0.6

    def test_both_none(self):
        assert regime_match_factor(None, None) == 0.6
