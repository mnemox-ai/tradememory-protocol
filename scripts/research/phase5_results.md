# Phase 5: Rigorous Changepoint Validation

Generated: 2026-04-09 14:52 UTC
Runtime: 2541s (42.4 min)

## 1. Research Question

Does BOCPD-based position adjustment reduce drawdown compared to:
- a) No adjustment (BaseAgent)
- b) Periodic reduction (PeriodicReduceAgent)
- c) Random skip (RandomSkipAgent)
- d) Simple win-rate threshold (SimpleWRAgent)

## 2. Methodology

- **Strategies**: Parameter grid (100 passed IS filter of 30+ trades)
- **Symbols**: BTCUSDT, ETHUSDT
- **Timeframes**: 1h
- **Walk-forward**: 67% IS / 33% OOS
- **Warm-start**: CalibratedAgent seeded with IS trades + adaptive DQS thresholds
- **Bootstrap**: 1000 resamples, 95% CI
- **DSR validation**: On CalibratedAgent OOS Sharpe

## 3. Results

### 3.1 Aggregate: CalibratedAgent vs BaseAgent

- Experiments total: 100
- Win rate (Calibrated has lower DD): 100/100 = 100.0%
- Mean DD reduction: 0.9819
- 95% CI: [0.9743, 0.9888]
- Bootstrap p-value: 0.0000

### 3.2 vs Naive Baselines

| Comparison | Win Rate | Mean DD delta | 95% CI | p-value | N |
|------------|----------|--------------|--------|---------|---|
| Calibrated vs No calibration | 100.0% | 0.0000 | [0.9743, 0.9888] | 0.0000 | 0 |
| Calibrated vs Periodic reduce | 100.0% | 9831.2590 | [8016.4710, 11636.3140] | 0.0000 | 100 |
| Calibrated vs Random skip | 100.0% | 9225.4884 | [7525.5322, 10962.3840] | 0.0000 | 100 |
| Calibrated vs Simple WR | 100.0% | 6892.9322 | [5613.0634, 8285.2119] | 0.0000 | 100 |

### 3.3 Sensitivity: hazard_rate

| hazard_rate | Mean DD reduction | Strategies improved | Robust? |
|-------------|------------------|--------------------|---------| 
| 20 | 0.9883 | 5/5 | Yes |
| 30 | 0.9883 | 5/5 | Yes |
| 40 | 0.9883 | 5/5 | Yes |
| 50 | 0.9883 | 5/5 | Yes |
| 75 | 0.9883 | 5/5 | Yes |
| 100 | 0.9883 | 5/5 | Yes |
| 150 | 0.9883 | 5/5 | Yes |
| 200 | 0.9883 | 5/5 | Yes |
| 300 | 0.9883 | 5/5 | Yes |
| 500 | 0.9883 | 5/5 | Yes |

### 3.4 DSR Pass Rate

- 0/100 experiments pass DSR (Agent B Sharpe is statistically real)

### 3.5 Trade Activity (Critical)

- BaseAgent mean trades: 136.6
- CalibratedAgent mean trades: 4.4
- CalibratedAgent mean skipped signals: 660.4
- CalibratedAgent with 0 OOS trades: 48/100

**WARNING**: CalibratedAgent executes very few trades. DD reduction is largely from
NOT TRADING rather than intelligent calibration. DQS skip tier is too aggressive
on cold-start / small DB, causing near-total trade rejection in OOS.
This invalidates the DD reduction as a measure of changepoint value.

## 4. Per-Market Breakdown

| Symbol | TF | Strategies | Cal wins | Cal mean DD | Base mean DD |
|--------|-----|------------|----------|-------------|-------------|
| BTCUSDT | 1h | 50 | 50/50 | 539.46 | 21432.91 |
| ETHUSDT | 1h | 50 | 50/50 | 11.98 | 983.98 |

## 5. Conclusion

**Verdict: INVALID -- CalibratedAgent reduces DD by NOT TRADING (48% zero-trade experiments, trade ratio 3.2%). DQS skip tier too aggressive. BOCPD changepoint effect unmeasurable.**

- Is BOCPD better than naive? YES (p=0.0)
- Is it robust to parameter choice? 10/10 hazard_rates show improvement
- Is it cross-market? Tested on 2 symbols
