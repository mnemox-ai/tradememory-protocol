"""Property-based tests for OWM core functions using Hypothesis.

These tests verify mathematical invariants that must hold for ALL inputs,
not just hand-picked examples. Each test generates thousands of random
inputs to catch edge cases.
"""

import math

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from tradememory.owm.recall import (
    compute_outcome_quality,
    compute_recency,
    compute_confidence_factor,
    compute_affective_modulation,
    sigmoid,
)


# ---------------------------------------------------------------------------
# Strategies for generating valid inputs
# ---------------------------------------------------------------------------

pnl_r_strategy = st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False)
sigma_r_strategy = st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False)
confidence_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
tau_strategy = st.floats(min_value=1.0, max_value=365.0, allow_nan=False, allow_infinity=False)
d_strategy = st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False)
drawdown_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Property: sigmoid is always in (0, 1) and monotonically increasing
# ---------------------------------------------------------------------------

@given(x=st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False))
def test_sigmoid_bounded(x):
    """Sigmoid must always be in [0, 1] (float64 rounds to boundaries at extremes)."""
    result = sigmoid(x)
    assert 0.0 <= result <= 1.0, f"sigmoid({x}) = {result}, expected [0, 1]"


@given(
    x1=st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False),
    x2=st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False),
)
def test_sigmoid_monotonic(x1, x2):
    """Sigmoid must be monotonically increasing: x1 < x2 => sigmoid(x1) <= sigmoid(x2)."""
    if x1 < x2:
        assert sigmoid(x1) <= sigmoid(x2)


# ---------------------------------------------------------------------------
# Property: outcome quality is always in [0, 1]
# ---------------------------------------------------------------------------

@given(pnl_r=pnl_r_strategy, sigma_r=sigma_r_strategy)
def test_outcome_quality_bounded(pnl_r, sigma_r):
    """OWM outcome quality must always be in [0, 1] when pnl_r is provided."""
    memory = {"pnl_r": pnl_r}
    q = compute_outcome_quality(memory, sigma_r=sigma_r)
    assert 0.0 <= q <= 1.0, f"Q({pnl_r}, sigma={sigma_r}) = {q}"


@given(confidence=confidence_strategy)
def test_outcome_quality_fallback(confidence):
    """When pnl_r is None, outcome quality returns confidence."""
    memory = {"confidence": confidence}
    q = compute_outcome_quality(memory)
    assert q == confidence


@given(
    pnl_r1=pnl_r_strategy,
    pnl_r2=pnl_r_strategy,
    sigma_r=sigma_r_strategy,
)
def test_outcome_quality_monotonic(pnl_r1, pnl_r2, sigma_r):
    """Higher pnl_r should produce higher outcome quality."""
    assume(pnl_r1 < pnl_r2)
    q1 = compute_outcome_quality({"pnl_r": pnl_r1}, sigma_r=sigma_r)
    q2 = compute_outcome_quality({"pnl_r": pnl_r2}, sigma_r=sigma_r)
    assert q1 <= q2, f"Q({pnl_r1})={q1} > Q({pnl_r2})={q2}"


# ---------------------------------------------------------------------------
# Property: recency is monotonically decreasing with age
# ---------------------------------------------------------------------------

@given(tau=tau_strategy, d=d_strategy)
def test_recency_at_zero_age(tau, d):
    """A memory from right now should have recency ~1.0."""
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    rec = compute_recency(now_iso, tau=tau, d=d)
    assert 0.99 <= rec <= 1.0, f"Recency at age=0: {rec}"


@given(
    tau=tau_strategy,
    d=d_strategy,
)
def test_recency_decreases_with_age(tau, d):
    """Older memories must score lower recency than newer ones."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=1)).isoformat()
    old = (now - timedelta(days=30)).isoformat()

    rec_recent = compute_recency(recent, tau=tau, d=d)
    rec_old = compute_recency(old, tau=tau, d=d)
    assert rec_recent >= rec_old, f"Recent({rec_recent}) < Old({rec_old})"


@given(tau=tau_strategy, d=d_strategy)
def test_recency_always_positive(tau, d):
    """Recency must always be > 0 (power-law never reaches zero)."""
    from datetime import datetime, timezone, timedelta
    ancient = (datetime.now(timezone.utc) - timedelta(days=3650)).isoformat()
    rec = compute_recency(ancient, tau=tau, d=d)
    assert rec > 0, f"Recency at 10yr age: {rec}"


# ---------------------------------------------------------------------------
# Property: confidence factor maps [0,1] to [0.5, 1.0]
# ---------------------------------------------------------------------------

@given(confidence=confidence_strategy)
def test_confidence_factor_range(confidence):
    """Confidence factor must be in [0.5, 1.0]."""
    cf = compute_confidence_factor(confidence)
    assert 0.5 <= cf <= 1.0, f"Conf({confidence}) = {cf}"


@given(
    c1=confidence_strategy,
    c2=confidence_strategy,
)
def test_confidence_factor_monotonic(c1, c2):
    """Higher confidence should produce higher confidence factor."""
    assume(c1 < c2)
    assert compute_confidence_factor(c1) <= compute_confidence_factor(c2)


# ---------------------------------------------------------------------------
# Property: affective modulation is always in [0.7, 1.3]
# ---------------------------------------------------------------------------

@given(
    pnl_r=pnl_r_strategy,
    drawdown=drawdown_strategy,
    consec_losses=st.integers(min_value=0, max_value=20),
)
def test_affective_modulation_bounded(pnl_r, drawdown, consec_losses):
    """Affective modulation must always be in [0.7, 1.3]."""
    memory = {"pnl_r": pnl_r}
    aff = compute_affective_modulation(
        memory, drawdown_state=drawdown, consecutive_losses=consec_losses,
    )
    assert 0.7 <= aff <= 1.3, f"Aff({pnl_r}, dd={drawdown}, cl={consec_losses}) = {aff}"


# ---------------------------------------------------------------------------
# Property: OWM ranking is deterministic
# ---------------------------------------------------------------------------

@given(st.data())
@settings(max_examples=50)
def test_owm_ranking_deterministic(data):
    """Two calls with identical inputs must produce identical rankings."""
    from tradememory.owm import outcome_weighted_recall, ContextVector

    n = data.draw(st.integers(min_value=2, max_value=10))
    memories = []
    for i in range(n):
        pnl_r = data.draw(st.floats(min_value=-5, max_value=5, allow_nan=False, allow_infinity=False))
        conf = data.draw(st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False))
        from datetime import datetime, timezone, timedelta
        age = data.draw(st.integers(min_value=0, max_value=365))
        ts = (datetime.now(timezone.utc) - timedelta(days=age)).isoformat()
        memories.append({
            "id": f"mem-{i}",
            "memory_type": "episodic",
            "timestamp": ts,
            "confidence": conf,
            "context": {"symbol": "XAUUSD"},
            "pnl_r": pnl_r,
        })

    ctx = ContextVector(symbol="XAUUSD")
    r1 = outcome_weighted_recall(ctx, memories, limit=n)
    r2 = outcome_weighted_recall(ctx, memories, limit=n)

    ids1 = [m.memory_id for m in r1]
    ids2 = [m.memory_id for m in r2]
    assert ids1 == ids2, f"Non-deterministic ranking: {ids1} vs {ids2}"
