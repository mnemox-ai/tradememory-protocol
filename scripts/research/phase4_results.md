# Self-Calibrating Trading Agent: Experiment Report
> Generated: 2026-04-08 20:57 UTC | TradeMemory Protocol v0.5.1

## 1. Executive Summary

Across 12 A/B experiments (2 symbols x 3 timeframes x 3 strategies), Agent B (self-calibrating) showed an average Sharpe improvement of -8.3% and average drawdown reduction of +8.3% compared to Agent A (baseline). Agent B skipped 560 trades total with a skip precision of 10.5% (proportion of skipped trades that were losers). Statistical significance (p < 0.05): 0/12 experiments showed Agent B significantly better, 0/12 showed Agent A better, 12/12 showed no significant difference.

## 2. Methodology

- **IS/OOS split**: 67% in-sample (training) / 33% out-of-sample (evaluation)
- **Walk-forward design**: Agent B learns on IS period, evaluated purely on OOS
- **Agent A (Baseline)**: Mechanical strategy execution, fixed lot size, no learning
- **Agent B (Calibrated)**: Same base strategy + DQS gate + BOCPD changepoint + Kelly sizing + regime filter
- **3 preset strategies**:
  - TrendFollow: Enter on 12h uptrend + moderate ATR, SL=1.5 ATR, TP=3.0 ATR
  - Breakout: Enter on high ATR expansion + strong trend, SL=2.0 ATR, TP=4.0 ATR
  - MeanReversion: Enter on low ATR range-bound, SL=1.0 ATR, TP=1.5 ATR
- **Calibration components**:
  - DQS (Decision Quality Score): 5-factor continuous scoring (0-10), 4 tiers (go/proceed/caution/skip)
  - BOCPD (Bayesian Online Changepoint Detection): Adams & MacKay 2007, Beta-Bernoulli + NIG conjugate models
  - CUSUM: Complementary cumulative sum detector for rapid shifts
  - Kelly sizing: From procedural memory's kelly_fraction
- **Statistical tests**: Welch's t-test on trade PnLs, DSR (Deflated Sharpe Ratio), Pearson correlation
- **Data**: 3 years of Binance spot OHLCV, no slippage, no transaction costs

## 3. Main Results -- A/B Comparison

### 3.1 Full Results Table

| Symbol | TF | Strategy | Sharpe A | Sharpe B | £G Sharpe | DD A | DD B | £G DD | Trades A | Trades B | Skipped | Skip PnL | DQS-PnL r | p-value | Sig? |
|--------|-----|----------|----------|----------|---------|------|------|------|----------|----------|---------|----------|-----------|---------|------|
| BTCUSDT | 1h | TrendFollow | -2.8608 | -2.8608 | +0.0% | 27942.9% | 27942.9% | +0.0% | 348 | 348 | 0 | 0.00 | -0.0218 | 1.000 | no |
| BTCUSDT | 1h | Breakout | -1.4367 | -1.4367 | +0.0% | 121134.1% | 121134.1% | +0.0% | 139 | 139 | 0 | 0.00 | 0.0105 | 1.000 | no |
| BTCUSDT | 1h | MeanReversion | -3.9900 | -3.9900 | +0.0% | 42019.4% | 42019.4% | +0.0% | 325 | 325 | 0 | 0.00 | -0.0041 | 1.000 | no |
| BTCUSDT | 4h | TrendFollow | 0.8889 | 0.0000 | -100.0% | 8267.8% | 0.0% | +100.0% | 91 | 0 | 560 | 5533.20 | 0.0000 | 1.000 | no |
| BTCUSDT | 4h | Breakout | -8.2926 | -8.2926 | +0.0% | 17695.9% | 17695.9% | +0.0% | 29 | 29 | 0 | 0.00 | -0.3461 | 1.000 | no |
| BTCUSDT | 4h | MeanReversion | 5.6754 | 5.6754 | +0.0% | 50624.4% | 50624.4% | +0.0% | 50 | 50 | 0 | 0.00 | -0.1028 | 1.000 | no |
| ETHUSDT | 1h | TrendFollow | 3.0695 | 3.0695 | +0.0% | 21168.4% | 21168.4% | +0.0% | 362 | 362 | 0 | 0.00 | 0.0405 | 1.000 | no |
| ETHUSDT | 1h | Breakout | 2.5144 | 2.5144 | +0.0% | 10930.4% | 10930.4% | +0.0% | 164 | 164 | 0 | 0.00 | -0.0776 | 1.000 | no |
| ETHUSDT | 1h | MeanReversion | -9.7465 | -9.7465 | +0.0% | 174078.7% | 174078.7% | +0.0% | 270 | 270 | 0 | 0.00 | -0.0768 | 1.000 | no |
| ETHUSDT | 4h | TrendFollow | 7.3853 | 7.3853 | +0.0% | 3748.8% | 3748.8% | +0.0% | 87 | 87 | 0 | 0.00 | -0.1306 | 1.000 | no |
| ETHUSDT | 4h | Breakout | 6.1578 | 6.1578 | +0.0% | 5622.3% | 5622.3% | +0.0% | 35 | 35 | 0 | 0.00 | 0.1716 | 1.000 | no |
| ETHUSDT | 4h | MeanReversion | 9.9051 | 9.9051 | +0.0% | 102899.8% | 102899.8% | +0.0% | 46 | 46 | 0 | 0.00 | 0.3156 | 1.000 | no |

### 3.2 Per-Timeframe Analysis

| Timeframe | N | Avg Sharpe A | Avg Sharpe B | Avg £G Sharpe | Avg £G DD | Skipped | Avg DQS-PnL r | Sig Count |
|---------------------------|---|--------------|--------------|-------------|--------|---------|---------------|-----------|
| 1h | 6 | -2.0750 | -2.0750 | +0.0% | +0.0% | 0 | -0.0215 | 0/6 |
| 4h | 6 | 3.6200 | 3.4718 | -16.7% | +16.7% | 560 | -0.0154 | 0/6 |

Calibration shows strongest improvement on **1h** (+0.0% avg Sharpe improvement).

### 3.3 Per-Symbol Analysis

| Symbol | N | Avg Sharpe A | Avg Sharpe B | Avg £G Sharpe | Avg £G DD | Skipped | Avg DQS-PnL r | Sig Count |
|------------------|---|--------------|--------------|-------------|--------|---------|---------------|-----------|
| BTCUSDT | 6 | -1.6693 | -1.8175 | -16.7% | +16.7% | 560 | -0.0774 | 0/6 |
| ETHUSDT | 6 | 3.2143 | 3.2143 | +0.0% | +0.0% | 0 | 0.0404 | 0/6 |

Cross-market spread in improvement: 16.7%. Divergent across symbols.

### 3.4 Per-Strategy Analysis

| Strategy | N | Avg Sharpe A | Avg Sharpe B | Avg £G Sharpe | Avg £G DD | Skipped | Avg DQS-PnL r | Sig Count |
|------------------------|---|--------------|--------------|-------------|--------|---------|---------------|-----------|
| Breakout | 4 | -0.2643 | -0.2643 | +0.0% | +0.0% | 0 | -0.0604 | 0/4 |
| MeanReversion | 4 | 0.4610 | 0.4610 | +0.0% | +0.0% | 0 | 0.0330 | 0/4 |
| TrendFollow | 4 | 2.1207 | 1.8985 | -25.0% | +25.0% | 560 | -0.0280 | 0/4 |

Calibration is most effective for **Breakout** (+0.0%).

## 4. Ablation Study

### 4.1 Ablation Table

| Symbol | TF | Strategy | Full B | No DQS | No CP | No Kelly | No Regime | Most Important |
|--------|-----|----------|--------|--------|-------|----------|-----------|----------------|
| BTCUSDT | 1h | TrendFollow | -2.8608 | -2.8608 | -2.8608 | -2.8608 | -2.8608 | no_dqs |
| BTCUSDT | 1h | Breakout | -1.4367 | -1.4367 | -1.4367 | -1.4367 | -1.4367 | no_dqs |
| BTCUSDT | 1h | MeanReversion | -3.9900 | -3.9900 | -3.9900 | -3.9900 | -3.9900 | no_dqs |
| BTCUSDT | 4h | TrendFollow | 0.0000 | 0.8889 | 0.0000 | 0.0000 | 0.0000 | no_changepoint |
| BTCUSDT | 4h | Breakout | -8.2926 | -8.2926 | -8.2926 | -8.2926 | -8.2926 | no_dqs |
| BTCUSDT | 4h | MeanReversion | 5.6754 | 5.6754 | 5.6754 | 5.6754 | 5.6754 | no_dqs |
| ETHUSDT | 1h | TrendFollow | 3.0695 | 3.0695 | 3.0695 | 3.0695 | 3.0695 | no_dqs |
| ETHUSDT | 1h | Breakout | 2.5144 | 2.5144 | 2.5144 | 2.5144 | 2.5144 | no_dqs |
| ETHUSDT | 1h | MeanReversion | -9.7465 | -9.7465 | -9.7465 | -9.7465 | -9.7465 | no_dqs |
| ETHUSDT | 4h | TrendFollow | 7.3853 | 7.3853 | 7.3853 | 7.3853 | 7.3853 | no_dqs |
| ETHUSDT | 4h | Breakout | 6.1578 | 6.1578 | 6.1578 | 6.1578 | 6.1578 | no_dqs |
| ETHUSDT | 4h | MeanReversion | 9.9051 | 9.9051 | 9.9051 | 9.9051 | 9.9051 | no_dqs |

### 4.2 Component Importance Ranking

| Component | Avg Sharpe £G | Std | N | Importance |
|-----------|-------------|-----|---|------------|
| no_changepoint | +0.0000 | 0.0000 | 12 | minimal |
| no_kelly | +0.0000 | 0.0000 | 12 | minimal |
| no_regime | +0.0000 | 0.0000 | 12 | minimal |
| no_dqs | +0.0741 | 0.2566 | 12 | minimal |

Most important component: **no_changepoint** (removing it causes avg Sharpe delta of +0.0000). Importance: minimal.

## 5. Statistical Validation

### 5.1 Deflated Sharpe Ratio (DSR)

| Symbol | TF | Strategy | Sharpe (OOS) | DSR | p-value | Verdict |
|--------|-----|----------|-------------|-----|---------|---------|
| BTCUSDT | 1h | TrendFollow | -2.8608 | -23.6159 | 1.0000 | FAIL |
| BTCUSDT | 1h | Breakout | -1.4367 | -11.8396 | 1.0000 | FAIL |
| BTCUSDT | 1h | MeanReversion | -3.9900 | -23.9933 | 1.0000 | FAIL |
| BTCUSDT | 4h | TrendFollow | 0.0000 | 0.0000 | 1.0000 | INSUFFICIENT_DATA |
| BTCUSDT | 4h | Breakout | -8.2926 | 0.0000 | 1.0000 | INSUFFICIENT_DATA |
| BTCUSDT | 4h | MeanReversion | 5.6754 | 9.6058 | 0.0000 | PASS |
| ETHUSDT | 1h | TrendFollow | 3.0695 | 24.4044 | 0.0000 | PASS |
| ETHUSDT | 1h | Breakout | 2.5144 | 15.7371 | 0.0000 | PASS |
| ETHUSDT | 1h | MeanReversion | -9.7465 | -22.9544 | 1.0000 | FAIL |
| ETHUSDT | 4h | TrendFollow | 7.3853 | 12.8808 | 0.0000 | PASS |
| ETHUSDT | 4h | Breakout | 6.1578 | 8.0370 | 0.0000 | PASS |
| ETHUSDT | 4h | MeanReversion | 9.9051 | 9.3916 | 0.0000 | PASS |

DSR results: 6 PASS, 4 FAIL, 2 INSUFFICIENT_DATA out of 12 experiments.

### 5.2 DQS-PnL Correlation

- Aggregate mean DQS-PnL Pearson r: **-0.0185**
- Range: [-0.3461, 0.3156]
- Positive r indicates DQS score is predictive of trade outcome

### 5.3 Significance Summary

- 0/12 experiments: Agent B significantly better (p < 0.05)
- 12/12 experiments: no significant difference
- 0/12 experiments: Agent A better (calibration harmful)

## 6. Behavioral Analysis

### 6.1 Changepoint Detection

- Total BOCPD alerts (cp_prob > 0.5): 317
- Total CUSUM alerts: 1804
- Avg max changepoint probability: 0.9072
- Experiments with at least one alert: 11/12

### 6.2 DQS Distribution

- Grand mean DQS score: 5.5402
- Grand median DQS score: 5.5808
- Total DQS-scored trades: 2415

**Tier distribution:**

| Tier | Count | Avg PnL |
|------|-------|---------|
| go | 29 | 7.2511 |
| proceed | 1596 | -18.2420 |
| caution | 230 | -20.7612 |
| skip | 560 | 0.0000 |

### 6.3 Skipped Trade Analysis

- Total trades skipped by Agent B: 560
- Of those, losers in Agent A: 59
- Skip precision: **10.5%** (higher = DQS more accurate)
- Total PnL of skipped trades (Agent A): 5533.1995

## 7. Limitations & Risks

- No slippage model: real-world execution would degrade results
- No transaction costs: spreads and commissions not modeled
- Crypto-only: results on BTCUSDT/ETHUSDT may not generalize to forex/stocks
- IS/OOS split is time-based (correct for financial data, but only one split point)
- Small strategy universe: only 3 preset strategies tested
- DQS calibration uses in-sample data: potential look-ahead bias in weight learning
- Changepoint detector hazard rate (1/50) is a fixed hyperparameter, not optimized
- Single fixed lot size for Agent A: does not account for position sizing edge

## 8. Conclusion

### Phase 5 Decision: **NO-GO**

**Evidence against (risks):**
- Average Sharpe improvement negative (-8.3%)
- <30% experiments show significant improvement (0/12)
- Skip precision <= 50% (10.5%)
- DQS-PnL correlation non-positive (-0.0185)

**Claims with data support:**
- Calibration reduces average drawdown by +8.3%

**Claims WITHOUT sufficient data support:**
- DQS as a standalone predictor (correlation too weak)
- Universal improvement (only 0/12 statistically significant)

---
*Report generated by TradeMemory Protocol v0.5.1 Simulation Framework*