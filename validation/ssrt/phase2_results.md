# SSRT Phase 2 Results — shift_null vs reset + tau sweep

> Generated: 2026-04-10
> 500 Monte Carlo simulations per cell, 5 scenarios x 9 methods = 22,500 runs
> Runtime: 15.7s

## Phase 2 Additions (vs Phase 1)

- **mSPRT_regime_shift** (Option B): adjust null mean/sigma on regime change WITHOUT resetting accumulated evidence
- **mSPRT_t05**: tau=0.5 (tighter mixture prior — more sensitive to small shifts)
- **mSPRT_t03**: tau=0.3 (tightest mixture prior tested)

## Full Comparison Table

```
Scenario             | Method               |  Type I | Type II |  Med Delay | Mean PnL Saved | Det Rate
----------------------------------------------------------------------------------------------------------
no_decay             | mSPRT                |   0.012 |     --- |        --- |          +0.67 |    0.012
no_decay             | mSPRT_t05            |   0.010 |     --- |        --- |          +0.52 |    0.010
no_decay             | mSPRT_t03            |   0.008 |     --- |        --- |          +0.34 |    0.008
no_decay             | mSPRT_regime_reset   |   0.012 |     --- |        --- |          +0.67 |    0.012
no_decay             | mSPRT_regime_shift   |   0.012 |     --- |        --- |          +0.67 |    0.012
no_decay             | CUSUM                |   0.236 |     --- |        --- |         +10.54 |    0.236
no_decay             | MaxDD_5R             |   0.936 |     --- |        --- |         +65.84 |    0.936
no_decay             | MaxDD_8R             |   0.478 |     --- |        --- |         +25.44 |    0.478
no_decay             | RollingSharpe        |   0.342 |     --- |        --- |         +15.31 |    0.342
----------------------------------------------------------------------------------------------------------
sudden_death_50      | mSPRT                |     --- |   0.010 |         64 |         -24.08 |    0.990
sudden_death_50      | mSPRT_t05            |     --- |   0.010 |         60 |         -25.18 |    0.990
sudden_death_50      | mSPRT_t03            |     --- |   0.010 |         60 |         -24.96 |    0.990
sudden_death_50      | mSPRT_regime_reset   |     --- |   0.010 |         64 |         -24.08 |    0.990
sudden_death_50      | mSPRT_regime_shift   |     --- |   0.010 |         64 |         -24.08 |    0.990
sudden_death_50      | CUSUM                |     --- |   0.004 |         26 |         -34.10 |    0.996
sudden_death_50      | MaxDD_5R             |     --- |   0.000 |          1 |         -35.82 |    1.000
sudden_death_50      | MaxDD_8R             |     --- |   0.000 |         14 |         -37.42 |    1.000
sudden_death_50      | RollingSharpe        |     --- |   0.000 |         21 |         -37.44 |    1.000
----------------------------------------------------------------------------------------------------------
sudden_death_100     | mSPRT                |     --- |   0.322 |         69 |          -6.14 |    0.678
sudden_death_100     | mSPRT_t05            |     --- |   0.284 |         65 |          -7.18 |    0.716
sudden_death_100     | mSPRT_t03            |     --- |   0.270 |         65 |          -7.46 |    0.730
sudden_death_100     | mSPRT_regime_reset   |     --- |   0.322 |         69 |          -6.14 |    0.678
sudden_death_100     | mSPRT_regime_shift   |     --- |   0.322 |         69 |          -6.14 |    0.678
sudden_death_100     | CUSUM                |     --- |   0.024 |         23 |         -18.75 |    0.976
sudden_death_100     | MaxDD_5R             |     --- |   0.000 |        -49 |          -6.11 |    1.000
sudden_death_100     | MaxDD_8R             |     --- |   0.002 |         10 |         -18.55 |    0.998
sudden_death_100     | RollingSharpe        |     --- |   0.000 |         19 |         -20.60 |    1.000
----------------------------------------------------------------------------------------------------------
linear_decay         | mSPRT                |     --- |   0.324 |        119 |          -5.83 |    0.676
linear_decay         | mSPRT_t05            |     --- |   0.292 |        116 |          -6.79 |    0.708
linear_decay         | mSPRT_t03            |     --- |   0.276 |        115 |          -7.08 |    0.724
linear_decay         | mSPRT_regime_reset   |     --- |   0.324 |        119 |          -5.83 |    0.676
linear_decay         | mSPRT_regime_shift   |     --- |   0.324 |        119 |          -5.83 |    0.676
linear_decay         | CUSUM                |     --- |   0.044 |         79 |         -13.84 |    0.956
linear_decay         | MaxDD_5R             |     --- |   0.000 |          1 |          -2.83 |    1.000
linear_decay         | MaxDD_8R             |     --- |   0.004 |         58 |         -13.25 |    0.996
linear_decay         | RollingSharpe        |     --- |   0.002 |         61 |         -16.01 |    0.998
----------------------------------------------------------------------------------------------------------
regime_specific      | mSPRT                |     --- |   0.248 |         71 |          +3.90 |    0.752
regime_specific      | mSPRT_t05            |     --- |   0.200 |         69 |          +4.02 |    0.800
regime_specific      | mSPRT_t03            |     --- |   0.186 |         70 |          +4.22 |    0.814
regime_specific      | mSPRT_regime_reset   |     --- |   0.430 |         20 |          +4.09 |    0.570
regime_specific      | mSPRT_regime_shift   |     --- |   0.498 |         26 |          +3.17 |    0.502
regime_specific      | CUSUM                |     --- |   0.048 |         22 |          +4.96 |    0.952
regime_specific      | MaxDD_5R             |     --- |   0.000 |         -9 |          +6.95 |    1.000
regime_specific      | MaxDD_8R             |     --- |   0.002 |         11 |          +5.05 |    0.998
regime_specific      | RollingSharpe        |     --- |   0.000 |         17 |          +5.00 |    1.000
```

## Key Questions

### Q1: Does mSPRT_regime_shift beat mSPRT_regime_reset on regime_specific?

**NO. shift is WORSE than reset.**

| Method | Type II | Med Delay | Det Rate |
|--------|---------|-----------|----------|
| mSPRT (fixed null) | 0.248 | 71 | 75.2% |
| mSPRT_regime_reset | 0.430 | 20 | 57.0% |
| mSPRT_regime_shift | 0.498 | 26 | 50.2% |

Ranking: **fixed null > reset > shift** on detection rate.

Why shift is worst: `shift_null()` adjusts the null parameters without resetting, but the accumulated likelihood ratio was computed under the old null. The shifted null creates a mismatch — the test statistic now reflects a mixture of evidence under two different null hypotheses. This incoherence hurts power more than resetting does.

Why both regime variants lose to fixed null: The regime_specific scenario has 25-trade regime blocks. Both regime-aware methods disrupt the evidence accumulation (reset destroys it, shift corrupts it), while the fixed-null mSPRT simply accumulates evidence across all trades against a constant baseline. The overall performance drop (from pre_mean=0.5 to post_mean=-0.3) is strong enough that a single fixed null catches it even without regime decomposition.

### Q2: Does shift_null maintain Type I < 0.05?

**YES.** On no_decay scenario:

| Method | Type I |
|--------|--------|
| mSPRT | 0.012 |
| mSPRT_t05 | 0.010 |
| mSPRT_t03 | 0.008 |
| mSPRT_regime_reset | 0.012 |
| mSPRT_regime_shift | 0.012 |

All mSPRT variants maintain Type I well below 0.05. The shift_null approach doesn't break the false positive guarantee — it just has terrible power. (But note: the no_decay scenario has no regime switches, so shift_null behaves identically to the fixed null here. A proper Type I test for shift_null would need a no-decay scenario WITH regime switches.)

### Q3: Which tau gives best power while keeping Type I < 0.05?

**tau=0.3 is best across all scenarios.**

| Scenario | tau=1.0 | tau=0.5 | tau=0.3 | Winner |
|----------|---------|---------|---------|--------|
| no_decay (Type I) | 0.012 | 0.010 | 0.008 | tau=0.3 (lowest FP) |
| sudden_death_50 | 99.0% | 99.0% | 99.0% | Tie |
| sudden_death_100 | 67.8% | 71.6% | 73.0% | **tau=0.3** (+5.2pp) |
| linear_decay | 67.6% | 70.8% | 72.4% | **tau=0.3** (+4.8pp) |
| regime_specific | 75.2% | 80.0% | 81.4% | **tau=0.3** (+6.2pp) |

Smaller tau concentrates the mixture prior closer to the null, making the test more sensitive to small mean shifts (0.5 → -0.3 is a 0.8R shift against std=1.5, so effect size d ≈ 0.53). The improvement is consistent: ~5pp detection gain with BETTER Type I control (0.008 vs 0.012).

**tau=0.3 is the recommended default for SSRT.**

### Q4: Full Comparison — Regime-Specific Scenario

All 9 methods on the regime_specific scenario (the paper's target):

| Method | Det Rate | Type II | Med Delay | PnL Saved | Type I (no_decay) |
|--------|----------|---------|-----------|-----------|-------------------|
| MaxDD_5R | 100.0% | 0.000 | -9 | +6.95 | 0.936 |
| RollingSharpe | 100.0% | 0.000 | 17 | +5.00 | 0.342 |
| MaxDD_8R | 99.8% | 0.002 | 11 | +5.05 | 0.478 |
| CUSUM | 95.2% | 0.048 | 22 | +4.96 | 0.236 |
| **mSPRT_t03** | **81.4%** | **0.186** | **70** | **+4.22** | **0.008** |
| mSPRT_t05 | 80.0% | 0.200 | 69 | +4.02 | 0.010 |
| mSPRT | 75.2% | 0.248 | 71 | +3.90 | 0.012 |
| mSPRT_regime_reset | 57.0% | 0.430 | 20 | +4.09 | 0.012 |
| mSPRT_regime_shift | 50.2% | 0.498 | 26 | +3.17 | 0.012 |

The story is clear: **mSPRT_t03 is the best statistically-valid method** (Type I = 0.008 < 0.05) with 81.4% power. All higher-power methods have unacceptable false positive rates (23.6%–93.6%).

### Q5: Phase 1 vs Phase 2 — Regime Variant Side-by-Side

| Metric | Phase 1: mSPRT_regime (reset) | Phase 2: mSPRT_regime_shift | Phase 2: mSPRT_t03 (fixed null) |
|--------|-------------------------------|-----------------------------|---------------------------------|
| Type I (no_decay) | 0.012 | 0.012 | 0.008 |
| regime_specific Det Rate | 57.0% | 50.2% | 81.4% |
| regime_specific Med Delay | 20 | 26 | 70 |
| regime_specific Type II | 0.430 | 0.498 | 0.186 |
| regime_specific PnL Saved | +4.09 | +3.17 | +4.22 |
| sudden_death_50 Det Rate | 99.0% | 99.0% | 99.0% |
| linear_decay Det Rate | 67.6% | 67.6% | 72.4% |

**Verdict**: Phase 2's shift_null (Option B) made regime-aware mSPRT even WORSE (-7pp on regime_specific). The hypothesis that preserving evidence while shifting null would help was wrong — the statistical incoherence from mixing evidence under different nulls hurts more than resetting.

The real Phase 2 win: **tau tuning**. Dropping tau from 1.0 to 0.3 improved detection rate by 5-6pp across all scenarios while simultaneously lowering Type I from 0.012 to 0.008. This is a free lunch.

## Conclusions

1. **Regime-aware null is a dead end** — both Option A (reset) and Option B (shift) are worse than fixed-null mSPRT. The 25-trade regime blocks in our simulation are too short for regime-specific estimation to help.

2. **tau=0.3 is the recommended default** — consistent improvement in power (+5pp) with better Type I control (0.008 vs 0.012). No trade-off.

3. **mSPRT_t03 is the paper's best method** — 81.4% power on regime_specific, 0.8% false positive rate. The only method that controls Type I while maintaining reasonable power.

4. **The fundamental gap remains** — mSPRT_t03 detects at median delay 70 trades vs MaxDD's -9 to 11. For a trader who needs fast reaction, heuristic methods with careful threshold calibration (accepting higher false positives) may be preferable. The paper's contribution is giving traders a method with known, controlled error rates.

## Parameters

| Method | Parameters |
|--------|-----------|
| mSPRT | alpha=0.05, tau=1.0, sigma=1.5, null_mean=pre_mean, burn_in=20 |
| mSPRT_t05 | Same, tau=0.5 |
| mSPRT_t03 | Same, tau=0.3 |
| mSPRT_regime_reset | mSPRT + RegimeAwareNull(min_trades=10), reset on regime change |
| mSPRT_regime_shift | mSPRT + RegimeAwareNull(min_trades=10), shift_null on regime change |
| MaxDD_5R | threshold_r=5.0 |
| MaxDD_8R | threshold_r=8.0 |
| RollingSharpe | window=30, consecutive=3 |
| CUSUM | threshold=4.0, target_wr=0.5 |

## Next Steps (Phase 3 candidates)

1. **Adaptive sigma**: Estimate sigma from running data instead of fixing at 1.5
2. **Longer regime blocks**: Test with 50-100 trade regime blocks to give regime estimation more data
3. **Two-sided test**: Current mSPRT only tests for decay (one-sided). A strategy that improves should NOT be retired.
4. **Real data validation**: Apply mSPRT_t03 to NG_Gold trades
5. **Composite test**: Use mSPRT for statistical gate + MaxDD as emergency stop (best of both worlds)
