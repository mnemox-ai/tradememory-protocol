# SSRT Phase 2 Spec — Fix Regime-Aware Null + Tau Sweep

> Phase 1 結果：mSPRT Type I=0.012（唯一控制），但 regime-aware null 比 fixed null 差（Option A reset 丟證據）。
> Phase 2 目標：改 Option B（shift null, keep evidence）+ tau sensitivity sweep

## What Changed (Option A → Option B)

Phase 1 Option A: regime change → `msprt.reset()` → 清除所有累積證據 → 從零開始
Phase 2 Option B: regime change → `msprt.shift_null()` → 調整統計量，保留累積證據

### Math for shift_null()

Current state after n observations with old null mu_old:
- sum_z = sum(x_i - mu_old)
- sum_z_sq = sum((x_i - mu_old)^2)

When null shifts to mu_new (delta = mu_old - mu_new):
- z_i_new = (x_i - mu_new) = (x_i - mu_old) + delta = z_i_old + delta
- sum_z_new = sum_z_old + n * delta
- sum_z_sq_new = sum_z_sq_old + 2 * delta * sum_z_old + n * delta^2
- z_bar_new = sum_z_new / n

Then recalculate log_lambda from z_bar_new using the standard formula.

This is O(1) — no need to store individual observations.

**Sigma handling**: When regime changes, sigma may also change. Accept optional new sigma parameter. Note: changing sigma mid-stream makes the likelihood ratio approximate (formula assumes constant sigma), but empirically this is far better than resetting.

---

## Task 1: Add shift_null() to core.py + tests

### Changes to `src/tradememory/ssrt/core.py`

Add method to MixtureSPRT class:

```python
def shift_null(self, new_null_mean: float, new_sigma: float | None = None) -> None:
    """Adjust null hypothesis without resetting accumulated evidence.

    Shifts the running statistics to account for a new baseline mean.
    This preserves accumulated evidence (n, sum_z, log_lambda) while
    adjusting for the regime-dependent null.

    Option B approach: when regime changes, we don't lose evidence.

    Args:
        new_null_mean: New baseline mean for null hypothesis.
        new_sigma: New observation std (if None, keep current).
    """
    if self.n == 0:
        # No evidence to preserve — just update parameters
        self.null_mean = new_null_mean
        if new_sigma is not None:
            if new_sigma <= 0:
                raise ValueError("sigma must be positive")
            self.sigma = new_sigma
        return

    delta = self.null_mean - new_null_mean  # old - new
    
    # Adjust running statistics
    self.sum_z_sq += 2.0 * delta * self.sum_z + self.n * delta * delta
    self.sum_z += self.n * delta
    
    # Update null
    self.null_mean = new_null_mean
    if new_sigma is not None:
        if new_sigma <= 0:
            raise ValueError("sigma must be positive")
        self.sigma = new_sigma

    # Recalculate log_lambda from adjusted statistics
    z_bar = self.sum_z / self.n
    sigma_sq = self.sigma ** 2
    tau_sq = self.tau ** 2
    n = self.n
    ratio = n * tau_sq / sigma_sq
    self._log_lambda = (
        -0.5 * math.log(1.0 + ratio)
        + (n * n * tau_sq * z_bar * z_bar)
        / (2.0 * sigma_sq * (sigma_sq + n * tau_sq))
    )
```

### New tests in `tests/test_ssrt_core.py`

Add these test functions:

```python
def test_shift_null_preserves_count():
    """shift_null should NOT reset trade count."""
    m = MixtureSPRT(null_mean=0.0)
    for _ in range(30):
        m.update(0.5)
    assert m.n == 30
    m.shift_null(new_null_mean=0.3)
    assert m.n == 30  # count preserved

def test_shift_null_equivalent_to_reprocess():
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

def test_shift_null_no_observations():
    """shift_null with no data should just update parameters."""
    m = MixtureSPRT(null_mean=0.0, sigma=1.5)
    m.shift_null(new_null_mean=0.5, new_sigma=2.0)
    assert m.null_mean == 0.5
    assert m.sigma == 2.0
    assert m.n == 0

def test_shift_null_improves_regime_detection():
    """Regime-aware with shift_null should beat regime-aware with reset
    on regime_specific_decay scenario (the Phase 1 failure case).
    """
    from tradememory.ssrt.simulator import DecaySimulator
    from tradememory.ssrt.regime import RegimeAwareNull
    import numpy as np
    
    n_sims = 200
    shift_detections = 0
    reset_detections = 0
    
    for seed in range(n_sims):
        trades = DecaySimulator.regime_specific_decay(
            n_trades=200, decay_at=50, seed=seed
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
```

---

## Task 2: Update experiment runner

### Changes to `scripts/research/ssrt_experiments.py`

1. Add `run_msprt_shift()` function — same as `run_msprt()` but uses `shift_null()` instead of `reset()`:

```python
def run_msprt_shift(
    trades: list[TradeResult],
    null_mean: float = 0.0,
    sigma: float = 1.5,
    tau: float = 1.0,
) -> tuple[bool, int | None, float]:
    """Run regime-aware mSPRT with shift_null (Option B)."""
    msprt = MixtureSPRT(alpha=0.05, tau=tau, sigma=sigma, null_mean=null_mean, burn_in=20)
    regime_null = RegimeAwareNull(min_trades_per_regime=10)
    
    cum_pnl = 0.0
    prev_regime = None
    
    for i, trade in enumerate(trades):
        cum_pnl += trade.pnl_r
        regime_null.update(trade)
        rn_mean, rn_sigma = regime_null.get_null(trade.regime)
        
        if trade.regime != prev_regime and prev_regime is not None:
            msprt.shift_null(new_null_mean=rn_mean, new_sigma=rn_sigma)
        prev_regime = trade.regime
        
        verdict = msprt.update(trade.pnl_r)
        if verdict.decision == "RETIRE":
            return True, i + 1, cum_pnl
    
    return False, None, cum_pnl
```

2. Update METHODS dict — replace `mSPRT_regime` with two variants + add tau sweep:

```python
methods = {
    "mSPRT":              lambda trades, pm=pre_mean, s=std: run_msprt(trades, use_regime=False, null_mean=pm, sigma=s, tau=1.0),
    "mSPRT_t05":          lambda trades, pm=pre_mean, s=std: run_msprt(trades, use_regime=False, null_mean=pm, sigma=s, tau=0.5),
    "mSPRT_t03":          lambda trades, pm=pre_mean, s=std: run_msprt(trades, use_regime=False, null_mean=pm, sigma=s, tau=0.3),
    "mSPRT_regime_reset": lambda trades, pm=pre_mean, s=std: run_msprt(trades, use_regime=True, null_mean=pm, sigma=s, tau=1.0),
    "mSPRT_regime_shift": lambda trades, pm=pre_mean, s=std: run_msprt_shift(trades, null_mean=pm, sigma=s, tau=1.0),
    "MaxDD_5R":           lambda trades: run_baseline(trades, MaxDDBaseline(threshold_r=5.0)),
    "MaxDD_8R":           lambda trades: run_baseline(trades, MaxDDBaseline(threshold_r=8.0)),
    "RollingSharpe":      lambda trades: run_baseline(trades, RollingSharpeBaseline(window=30, consecutive=3)),
    "CUSUM":              lambda trades: run_baseline(trades, CUSUMBaseline(threshold=4.0, target_wr=0.5)),
}
```

3. Update print header and total count accordingly (5 scenarios x 9 methods = 45 cells).

---

## Task 3: Run experiments + analyze

Run: `python scripts/research/ssrt_experiments.py`

Write `validation/ssrt/phase2_results.md` answering:

1. Does shift_null beat reset on regime_specific scenario? (expect YES)
2. Does shift_null maintain Type I control? (must be YES — otherwise shift_null breaks the test)
3. What tau value gives best power/Type I tradeoff?
4. Updated summary table comparing all methods
5. Side-by-side Phase 1 vs Phase 2 for mSPRT_regime

---

## Task 4: Run full tests + commit

```bash
python -m pytest tests/ -v --tb=short
```

All tests must pass. Then:

```bash
git add -A
git commit -m "feat: SSRT Phase 2 — shift_null (Option B) + tau sweep. Regime-aware null now preserves evidence on regime change."
git push
```

Update CLAUDE.md Recent Changes.
