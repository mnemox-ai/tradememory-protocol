# SSRT Phase 1 Results — mSPRT vs Baselines

> Generated: 2026-04-10
> 500 Monte Carlo simulations per cell, 5 scenarios x 6 methods = 15,000 runs

## Summary Table

```
Scenario             | Method          |  Type I | Type II |  Med Delay | Mean PnL Saved | Det Rate
----------------------------------------------------------------------------------------------------
linear_decay         | CUSUM           |     --- |   0.044 |         79 |         -13.84 |    0.956
linear_decay         | MaxDD_5R        |     --- |   0.000 |          1 |          -2.83 |    1.000
linear_decay         | MaxDD_8R        |     --- |   0.004 |         58 |         -13.25 |    0.996
linear_decay         | RollingSharpe   |     --- |   0.002 |         61 |         -16.01 |    0.998
linear_decay         | mSPRT           |     --- |   0.324 |        119 |          -5.83 |    0.676
linear_decay         | mSPRT_regime    |     --- |   0.324 |        119 |          -5.83 |    0.676
----------------------------------------------------------------------------------------------------
no_decay             | CUSUM           |   0.236 |     --- |        --- |         +10.54 |    0.236
no_decay             | MaxDD_5R        |   0.936 |     --- |        --- |         +65.84 |    0.936
no_decay             | MaxDD_8R        |   0.478 |     --- |        --- |         +25.44 |    0.478
no_decay             | RollingSharpe   |   0.342 |     --- |        --- |         +15.31 |    0.342
no_decay             | mSPRT           |   0.012 |     --- |        --- |          +0.67 |    0.012
no_decay             | mSPRT_regime    |   0.012 |     --- |        --- |          +0.67 |    0.012
----------------------------------------------------------------------------------------------------
regime_specific      | CUSUM           |     --- |   0.048 |         22 |          +4.96 |    0.952
regime_specific      | MaxDD_5R        |     --- |   0.000 |         -9 |          +6.95 |    1.000
regime_specific      | MaxDD_8R        |     --- |   0.002 |         11 |          +5.05 |    0.998
regime_specific      | RollingSharpe   |     --- |   0.000 |         17 |          +5.00 |    1.000
regime_specific      | mSPRT           |     --- |   0.248 |         71 |          +3.90 |    0.752
regime_specific      | mSPRT_regime    |     --- |   0.430 |         20 |          +4.09 |    0.570
----------------------------------------------------------------------------------------------------
sudden_death_100     | CUSUM           |     --- |   0.024 |         23 |         -18.75 |    0.976
sudden_death_100     | MaxDD_5R        |     --- |   0.000 |        -49 |          -6.11 |    1.000
sudden_death_100     | MaxDD_8R        |     --- |   0.002 |         10 |         -18.55 |    0.998
sudden_death_100     | RollingSharpe   |     --- |   0.000 |         19 |         -20.60 |    1.000
sudden_death_100     | mSPRT           |     --- |   0.322 |         69 |          -6.14 |    0.678
sudden_death_100     | mSPRT_regime    |     --- |   0.322 |         69 |          -6.14 |    0.678
----------------------------------------------------------------------------------------------------
sudden_death_50      | CUSUM           |     --- |   0.004 |         26 |         -34.10 |    0.996
sudden_death_50      | MaxDD_5R        |     --- |   0.000 |          1 |         -35.82 |    1.000
sudden_death_50      | MaxDD_8R        |     --- |   0.000 |         14 |         -37.42 |    1.000
sudden_death_50      | RollingSharpe   |     --- |   0.000 |         21 |         -37.44 |    1.000
sudden_death_50      | mSPRT           |     --- |   0.010 |         64 |         -24.08 |    0.990
sudden_death_50      | mSPRT_regime    |     --- |   0.010 |         64 |         -24.08 |    0.990
```

## Key Questions Answered

### 1. Does mSPRT control Type I error at alpha=0.05?

**YES.** mSPRT Type I = 0.012, well below alpha=0.05.

This is the ONLY method that properly controls false positives:
- MaxDD_5R: 0.936 (catastrophic)
- MaxDD_8R: 0.478 (unacceptable)
- RollingSharpe: 0.342 (unacceptable)
- CUSUM: 0.236 (unacceptable)
- **mSPRT: 0.012** (controlled)

All baselines retire healthy strategies at alarming rates. This means their "detection" rates on decay scenarios are meaningless — they fire on everything.

### 2. Does mSPRT detect decay faster than MaxDD/CUSUM?

**NO — but the comparison is unfair.**

Raw detection speed:
- MaxDD_5R detects fastest (median delay often <0, meaning it fires before decay even starts)
- CUSUM: median delay 22-79 trades
- RollingSharpe: median delay 17-61 trades
- mSPRT: median delay 64-119 trades

But MaxDD_5R, RollingSharpe, and CUSUM have astronomical false positive rates. Their speed is meaningless because they fire on non-decaying strategies too. It's like a smoke detector that goes off every time you cook — yes it's "fast" at detecting fires, but it's useless.

**Fair comparison at matched Type I rate**: Only mSPRT achieves Type I < 0.05. No baseline comes close. To get baselines to Type I < 0.05, you'd need thresholds so high they'd never detect anything.

### 3. Does regime-aware null improve detection on regime_specific scenario?

**NO — it's actually WORSE.**

- mSPRT (fixed null): Type II = 0.248, detection rate = 75.2%
- mSPRT_regime: Type II = 0.430, detection rate = 57.0%

The regime-aware variant loses evidence on every regime switch (reset). In this setup with 25-trade regime blocks, that's frequent resets destroying accumulated evidence. The fixed-null mSPRT that doesn't reset accumulates evidence across both regimes and catches the overall performance drop faster.

**Why**: Phase 1 chose Option A (reset on regime change) for statistical purity. The cost is real — 18 percentage points worse detection. Phase 2 could explore Option B (adjust shift, keep evidence) or only reset after N consecutive trades in new regime.

### 4. Economic value (P&L saved)?

Mixed. Mean PnL saved is often NEGATIVE because:
1. mSPRT triggers late (64-119 trades after decay), so you eat losses before retiring
2. Negative PnL saved means "you would have been better off running the full sequence" — but that's with hindsight

The real economic value is in NOT retiring healthy strategies:
- MaxDD_5R retires 93.6% of healthy strategies → massive opportunity cost
- mSPRT retires 1.2% of healthy strategies → minimal opportunity cost

## Honest Assessment

### What mSPRT does well
- **Statistical rigor**: Only method with controlled Type I error
- **Always-valid p-values**: Can peek after every trade without inflation
- **Theoretical foundation**: Based on Johari et al. 2017 (well-established)

### What mSPRT does poorly
- **Detection speed**: Significantly slower than heuristic methods
- **Power against gradual decay**: 67.6% detection on linear_decay (vs 99.6%+ for baselines, but baselines cheat with high false positives)
- **Regime-aware variant**: Currently worse than fixed null due to evidence loss on reset

### The fundamental trade-off
All baselines achieve high detection rates by being trigger-happy. mSPRT achieves low false positives by being conservative. **There is no free lunch.** The question is: which error is more expensive?

- If false retirement costs more (stopping a profitable strategy): **mSPRT wins**
- If late detection costs more (hemorrhaging capital): **heuristics with careful threshold tuning might be better**

For systematic trading where you have many strategies, false retirements are very expensive (you lose your edge). mSPRT is the right choice.

### Publishability

This is a **negative result** for the regime-aware null hypothesis (the paper's claimed novelty). The regime-aware variant is strictly worse than fixed-null mSPRT in these experiments. However:

1. The experimental setup (25-trade regime blocks) may not be representative
2. Option B (adjust without reset) wasn't tested
3. The Type I control result IS strong and publishable
4. The comparison showing all common heuristics have terrible Type I rates is valuable

**Recommendation**: Reframe as "mSPRT for strategy retirement with Type I guarantees" rather than "regime-aware SSRT." The regime story needs more work.

## Parameters Used

| Method | Parameters |
|--------|-----------|
| mSPRT | alpha=0.05, tau=1.0, sigma=1.5, null_mean=0.5, burn_in=20 |
| mSPRT_regime | Same + RegimeAwareNull(min_trades=10), reset on regime change |
| MaxDD_5R | threshold_r=5.0 (retire at 5R drawdown) |
| MaxDD_8R | threshold_r=8.0 (retire at 8R drawdown) |
| RollingSharpe | window=30, consecutive=3 |
| CUSUM | threshold=4.0, target_wr=0.5 |

## Simulation Design

| Scenario | Trades | Pre-mean | Post-mean | Decay at | Std |
|----------|--------|----------|-----------|----------|-----|
| no_decay | 200 | 0.5 | — | — | 1.5 |
| sudden_death_50 | 200 | 0.5 | -0.3 | 50 | 1.5 |
| sudden_death_100 | 200 | 0.5 | -0.3 | 100 | 1.5 |
| linear_decay | 200 | 0.5 | -0.3 | 50-150 | 1.5 |
| regime_specific | 200 | 0.5 | -0.3 | 50 | 1.5 |

## Next Steps (Phase 2)

1. **Tau sensitivity sweep**: tau ∈ {0.3, 0.5, 1.0, 2.0, 3.0} — smaller tau should improve detection of the 0.8R mean shift
2. **Option B regime handling**: Adjust observation shift without resetting accumulated evidence
3. **Adaptive sigma**: Estimate sigma from data instead of fixing at 1.5
4. **Larger mean shift**: Test with post_mean=-1.0 (larger effect size)
5. **Real data validation**: Apply to NG_Gold trades with known regime periods
