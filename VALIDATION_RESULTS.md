# Phase 13: Statistical Validation Results

> Validates that the Evolution Engine discovers strategies with genuine edge,
> not just random noise. Each step adds a layer of statistical rigor.

---

## Step 1: Random Baseline

### Method

Generate N random strategies on the same OHLCV data used by the Evolution Engine.
Compute Sharpe ratio for each. A real strategy must rank above the 95th percentile
of the random distribution to be considered non-random.

### Data

- **Symbol**: BTCUSDT 1H (Binance spot)
- **Period**: 2024-06-01 to 2026-03-17 (15,693 bars)
- **Random strategies**: 1,000 (seed=42)
- **Execution time**: precompute=44s, 1000 backtests=13s, total=58s

### Baseline Distribution

| Metric | Value |
|--------|-------|
| Mean Sharpe | -0.0354 |
| Std Sharpe | 2.2147 |
| P5 | -3.3704 |
| P25 | -1.7777 |
| P50 (median) | -0.0116 |
| P75 | 1.4518 |
| P95 | 3.2708 |

### Strategy Results

| Strategy | Sharpe | Percentile | Trades | Win Rate | PF | Pass? |
|----------|--------|------------|--------|----------|----|-------|
| Strategy C (full) | 3.4003 | 96.9% | 336 | 37.2% | 1.12 | PASS |
| Strategy E (full) | 4.4188 | 100.0% | 321 | 41.1% | 1.15 | PASS |
| Strategy C (no trend) | -0.4349 | 38.0% | 654 | 37.6% | 0.99 | FAIL |
| Strategy E (no trend) | 1.3527 | 68.6% | 653 | 39.1% | 1.04 | FAIL |

### Ablation: Trend Filter Contribution

| Strategy | Full | No Trend | Delta |
|----------|------|----------|-------|
| C | 96.9% | 38.0% | +58.9 pctile pts |
| E | 100.0% | 68.6% | +31.4 pctile pts |

The 12h trend filter is the primary alpha source. Without it, both strategies fall to noise-level performance.

### Verdict

**PASS** -- Both Strategy C and E beat the 95th percentile of 1,000 random strategies.

### Next

Proceed to Step 2 (Walk-Forward) to test out-of-sample stability.

---

## Step 2: Walk-Forward (TODO)

TODO

---

## Step 3: Time Bias Test (TODO)

TODO

---

## Step 4: Extended OOS (TODO)

TODO
