"""
Tests for Bayesian Online Changepoint Detection (Phase 1).

8 tests: unit + property-based covering stable series, mean shifts,
pnl shifts, hold time shifts, serialization, hazard sensitivity,
and probability bounds.
"""

import json
import random

import pytest

from tradememory.owm.changepoint import BayesianChangepoint, ChangePointResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_series(detector, observations):
    """Feed a list of observation dicts, return list of ChangePointResults."""
    results = []
    for obs in observations:
        results.append(detector.update(obs))
    return results


def _make_obs(won: bool, pnl_r: float, hold_seconds=None, lot_vs_kelly=None):
    obs = {"won": won, "pnl_r": pnl_r}
    if hold_seconds is not None:
        obs["hold_seconds"] = hold_seconds
    if lot_vs_kelly is not None:
        obs["lot_vs_kelly"] = lot_vs_kelly
    return obs


# ---------------------------------------------------------------------------
# Test 1: Stable series — no changepoint
# ---------------------------------------------------------------------------

def test_no_changepoint_stable_series():
    """50 trades at ~60% win rate should NOT trigger a changepoint."""
    rng = random.Random(42)
    detector = BayesianChangepoint(hazard_lambda=50.0)

    results = []
    for _ in range(50):
        won = rng.random() < 0.6
        pnl_r = rng.gauss(0.5, 0.3) if won else rng.gauss(-0.3, 0.2)
        r = detector.update(_make_obs(won, pnl_r))
        results.append(r)

    # After stabilizing, the last 10 should all have low cp_prob
    for r in results[-10:]:
        assert r.changepoint_probability < 0.5, (
            f"Stable series should not trigger changepoint, got cp_prob={r.changepoint_probability:.3f}"
        )


# ---------------------------------------------------------------------------
# Test 2: Detect mean shift in win rate
# ---------------------------------------------------------------------------

def test_detect_mean_shift():
    """30 trades at 70% win rate → 30 trades at 30% should detect a changepoint."""
    rng = random.Random(123)
    detector = BayesianChangepoint(hazard_lambda=30.0)

    # Phase 1: high win rate
    for _ in range(30):
        won = rng.random() < 0.7
        pnl_r = rng.gauss(1.0, 0.3) if won else rng.gauss(-0.5, 0.2)
        detector.update(_make_obs(won, pnl_r))

    # Phase 2: low win rate — should detect changepoint
    max_cp_prob = 0.0
    for _ in range(30):
        won = rng.random() < 0.3
        pnl_r = rng.gauss(-0.5, 0.3) if not won else rng.gauss(0.3, 0.2)
        r = detector.update(_make_obs(won, pnl_r))
        max_cp_prob = max(max_cp_prob, r.changepoint_probability)

    # cp_prob should be meaningfully above the base hazard rate (1/30 ≈ 0.033)
    assert max_cp_prob > 0.05, (
        f"Should detect mean shift, max cp_prob was only {max_cp_prob:.3f}"
    )


# ---------------------------------------------------------------------------
# Test 3: Detect PnL shift
# ---------------------------------------------------------------------------

def test_detect_pnl_shift():
    """pnl_r from avg 1.5 to avg -0.5 should trigger changepoint."""
    rng = random.Random(456)
    detector = BayesianChangepoint(hazard_lambda=30.0)

    # Phase 1: profitable
    for _ in range(30):
        pnl_r = rng.gauss(1.5, 0.3)
        detector.update(_make_obs(won=True, pnl_r=pnl_r))

    # Phase 2: losing
    max_cp_prob = 0.0
    for _ in range(30):
        pnl_r = rng.gauss(-0.5, 0.3)
        r = detector.update(_make_obs(won=False, pnl_r=pnl_r))
        max_cp_prob = max(max_cp_prob, r.changepoint_probability)

    assert max_cp_prob > 0.3, (
        f"Should detect pnl shift, max cp_prob was only {max_cp_prob:.3f}"
    )


# ---------------------------------------------------------------------------
# Test 4: Detect hold time shift
# ---------------------------------------------------------------------------

def test_detect_hold_time_shift():
    """Hold time from 4hr (14400s) to 15min (900s) should be detectable."""
    rng = random.Random(789)
    detector = BayesianChangepoint(hazard_lambda=30.0)

    # Phase 1: long holds
    for _ in range(30):
        won = rng.random() < 0.5
        pnl_r = rng.gauss(0.5, 0.5)
        hold = int(rng.gauss(14400, 1000))
        detector.update(_make_obs(won, pnl_r, hold_seconds=max(60, hold)))

    # Phase 2: short holds
    max_cp_prob = 0.0
    for _ in range(30):
        won = rng.random() < 0.5
        pnl_r = rng.gauss(0.5, 0.5)
        hold = int(rng.gauss(900, 200))
        r = detector.update(_make_obs(won, pnl_r, hold_seconds=max(60, hold)))
        max_cp_prob = max(max_cp_prob, r.changepoint_probability)

    assert max_cp_prob > 0.3, (
        f"Should detect hold time shift, max cp_prob was only {max_cp_prob:.3f}"
    )


# ---------------------------------------------------------------------------
# Test 5: Serialization roundtrip
# ---------------------------------------------------------------------------

def test_serialization_roundtrip():
    """get_state → from_state should produce identical results on next update."""
    rng = random.Random(101)
    detector = BayesianChangepoint(hazard_lambda=40.0)

    # Feed 20 observations
    for _ in range(20):
        won = rng.random() < 0.6
        pnl_r = rng.gauss(0.5, 0.5)
        detector.update(_make_obs(won, pnl_r))

    # Serialize and restore
    state = detector.get_state()
    state_json = json.dumps(state)
    restored = BayesianChangepoint.from_state(json.loads(state_json))

    # Both should give same result on next observation
    obs = _make_obs(won=True, pnl_r=1.2)

    r1 = detector.update(obs)
    r2 = restored.update(obs)

    assert abs(r1.changepoint_probability - r2.changepoint_probability) < 1e-10, (
        f"Roundtrip mismatch: {r1.changepoint_probability} vs {r2.changepoint_probability}"
    )
    assert r1.observation_count == r2.observation_count


# ---------------------------------------------------------------------------
# Test 6: Hazard rate sensitivity
# ---------------------------------------------------------------------------

def test_hazard_rate_sensitivity():
    """Lower hazard_lambda (more frequent CPs expected) should produce
    higher changepoint probability on the same shift."""
    rng_a = random.Random(202)
    rng_b = random.Random(202)  # same seed

    detector_fast = BayesianChangepoint(hazard_lambda=10.0)  # expects frequent CPs
    detector_slow = BayesianChangepoint(hazard_lambda=100.0)  # expects rare CPs

    # Phase 1
    for _ in range(20):
        won = rng_a.random() < 0.7
        pnl_r = rng_a.gauss(1.0, 0.3) if won else rng_a.gauss(-0.3, 0.2)
        obs = _make_obs(won, pnl_r)
        detector_fast.update(obs)

        won = rng_b.random() < 0.7
        pnl_r = rng_b.gauss(1.0, 0.3) if won else rng_b.gauss(-0.3, 0.2)
        detector_slow.update(_make_obs(won, pnl_r))

    # Phase 2: shift
    max_fast = 0.0
    max_slow = 0.0
    for _ in range(20):
        won = rng_a.random() < 0.3
        pnl_r = rng_a.gauss(-0.5, 0.3)
        r = detector_fast.update(_make_obs(won, pnl_r))
        max_fast = max(max_fast, r.changepoint_probability)

        won = rng_b.random() < 0.3
        pnl_r = rng_b.gauss(-0.5, 0.3)
        r = detector_slow.update(_make_obs(won, pnl_r))
        max_slow = max(max_slow, r.changepoint_probability)

    # Fast detector should be more sensitive
    assert max_fast > max_slow, (
        f"Fast detector ({max_fast:.3f}) should be more sensitive than slow ({max_slow:.3f})"
    )


# ---------------------------------------------------------------------------
# Test 7: Property — cp_probability always in [0, 1]
# ---------------------------------------------------------------------------

def test_property_cp_probability_bounded():
    """Changepoint probability should always be in [0, 1], regardless of input."""
    rng = random.Random(303)
    detector = BayesianChangepoint(hazard_lambda=50.0)

    for _ in range(200):
        won = rng.random() < 0.5
        pnl_r = rng.gauss(0, 5.0)  # wide variance
        hold = max(1, int(rng.gauss(3600, 5000)))
        lot = max(0.01, rng.gauss(1.0, 2.0))

        r = detector.update(_make_obs(won, pnl_r, hold_seconds=hold, lot_vs_kelly=lot))

        assert 0.0 <= r.changepoint_probability <= 1.0, (
            f"cp_prob out of bounds: {r.changepoint_probability}"
        )
        assert r.observation_count > 0
        assert r.max_run_length >= 0


# ---------------------------------------------------------------------------
# Test 8: Property — larger shift → higher cp_prob
# ---------------------------------------------------------------------------

def test_property_monotonic_shift():
    """A bigger behavioral shift should produce a higher max cp_prob
    than a smaller shift, on average."""

    def run_with_shift(wr_before, wr_after, seed):
        rng = random.Random(seed)
        detector = BayesianChangepoint(hazard_lambda=30.0)

        for _ in range(30):
            won = rng.random() < wr_before
            pnl_r = rng.gauss(0.5, 0.3) if won else rng.gauss(-0.3, 0.2)
            detector.update(_make_obs(won, pnl_r))

        max_cp = 0.0
        for _ in range(30):
            won = rng.random() < wr_after
            pnl_r = rng.gauss(0.5, 0.3) if won else rng.gauss(-0.3, 0.2)
            r = detector.update(_make_obs(won, pnl_r))
            max_cp = max(max_cp, r.changepoint_probability)
        return max_cp

    # Run multiple seeds and average
    big_shift_scores = []
    small_shift_scores = []
    for seed in range(10):
        big_shift_scores.append(run_with_shift(0.7, 0.2, seed))    # large shift
        small_shift_scores.append(run_with_shift(0.7, 0.55, seed))  # small shift

    avg_big = sum(big_shift_scores) / len(big_shift_scores)
    avg_small = sum(small_shift_scores) / len(small_shift_scores)

    assert avg_big > avg_small, (
        f"Bigger shift avg cp_prob ({avg_big:.3f}) should exceed smaller shift ({avg_small:.3f})"
    )
