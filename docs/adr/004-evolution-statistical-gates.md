# ADR 004: Evolution Engine Statistical Gates

**Status:** Accepted  
**Date:** 2026-01-20  
**Authors:** Sean Peng  
**Supersedes:** None

## Context

The Evolution Engine uses LLM-based pattern discovery to generate candidate trading strategies from historical OHLCV data. Each candidate is backtested and assigned fitness metrics (Sharpe ratio, win rate, max drawdown, trade count).

The critical question: what threshold must a generated strategy pass before being promoted to production use?

This is fundamentally a multiple-testing problem. When you generate 150 strategy candidates and pick the one with the highest Sharpe ratio, you are almost certainly selecting noise, not signal. The probability of finding at least one candidate with Sharpe > 1.0 by pure chance increases with the number of candidates tested -- this is the multiple comparisons problem applied to quantitative finance.

We needed statistical gates rigorous enough to reject false discoveries while still allowing genuinely robust strategies through.

## Decision

Four-layer statistical gate, applied sequentially. A strategy must pass ALL layers to graduate.

### Layer 1: Deflated Sharpe Ratio (DSR)

Based on Bailey and Lopez de Prado (2014). The DSR adjusts a strategy's observed Sharpe ratio for:

- **Number of trials** (how many strategies were tested)
- **Skewness** of the return distribution
- **Kurtosis** of the return distribution
- **Track record length** (number of trades)

A strategy with Sharpe = 1.5 tested alongside 150 other candidates has a DSR that accounts for the selection bias. The DSR answers: "What is the probability that this Sharpe ratio would have been observed even if the true Sharpe were zero, given that we tested N strategies?"

Gate: DSR p-value < 0.05 (strategy's Sharpe is statistically significant after multiple-testing correction).

### Layer 2: Walk-Forward Validation

Split historical data into in-sample (training) and out-of-sample (validation) periods.

- In-sample: strategy is discovered and optimized
- Out-of-sample: strategy is evaluated on unseen data

Gate: Out-of-sample Sharpe must be positive AND within 50% of in-sample Sharpe. A strategy with in-sample Sharpe = 2.0 and out-of-sample Sharpe = 0.3 is rejected as overfit.

### Layer 3: Regime Stability

Uses Mahalanobis distance for out-of-distribution (OOD) detection and Bayesian regime confidence scoring.

- Computes feature vectors for the market regime during the backtest period
- Measures how far the current regime is from the training regime
- Requires minimum Bayesian confidence that the strategy's assumptions still hold

Gate: Mahalanobis distance below threshold AND regime confidence > 0.6. A trend-following strategy discovered during a strong uptrend is flagged if the current regime is ranging.

### Layer 4: CPCV (Combinatorial Purged Cross-Validation)

Advanced cross-validation specifically designed for time-series financial data (Lopez de Prado, 2018).

- Generates all combinatorial train/test splits
- Purges overlapping observations at split boundaries (prevents leakage)
- Applies embargo periods to prevent information bleeding across folds

Gate: Median Sharpe across all CPCV folds must be positive. This is the hardest gate to pass -- it requires the strategy to work across many different time periods, not just the one it was discovered in.

## Results (Post-Mortem)

| Metric | Value |
|--------|-------|
| Total strategies generated | 150+ |
| Strategies passing DSR gate | 0 |
| Strategies passing walk-forward | 0 |
| Strategies graduating (all 4 gates) | 0 |
| Phase 15 batch: 23 candidates | 0 passed DSR |

**Zero strategies have graduated.** Every LLM-generated strategy that appeared profitable in-sample was rejected by the DSR gate as statistically indistinguishable from random chance after multiple-testing correction.

### Root Cause Analysis

LLM-generated strategies suffer from a specific failure mode: the LLM identifies patterns that are visually salient in price charts (double bottoms, momentum breakouts, mean-reversion setups) but lack genuine statistical edge. These patterns "work" in-sample because the LLM unconsciously fits to the specific noise realization of the training data. The DSR gate correctly identifies this as selection bias.

This is not a failure of the statistical gates. It is the gates working exactly as designed. The alternative -- promoting strategies that look good in-sample -- would lead to real capital losses.

## Consequences

### Positive

- **Zero false positive strategies promoted.** No user has been exposed to a strategy that passed through luck rather than edge.
- **Statistical gates are independently valuable.** The DSR calculator, regime detector, and CPCV validator are exposed as the `validate_strategy` MCP tool. Users can validate their own (human-designed) strategies against these same gates.
- **Intellectual honesty.** The zero-graduation result, documented transparently, builds credibility with sophisticated users who understand multiple-testing problems.
- **Research contribution.** Demonstrates empirically that pure LLM strategy generation (without domain constraints) does not survive rigorous statistical validation. This is a useful negative result for the quantitative finance + AI community.

### Negative

- **User experience friction.** Users who expect the Evolution Engine to produce ready-to-trade strategies are disappointed. Zero output after running 3 generations of 10 strategies feels like the feature is broken.
- **Computational cost without output.** Each evolution run consumes LLM tokens (pattern discovery), compute (backtesting), and time (minutes to hours). Zero graduation means zero ROI on that compute.
- **Perception risk.** "Your strategy generator has never produced a viable strategy" is a difficult marketing message, regardless of how technically correct the reasoning is.

### Mitigations and Future Direction

1. **Documentation clarity.** Evolution Engine is labeled "research phase" in all user-facing docs. The feature description emphasizes the statistical validation tools, not the strategy generation.

2. **Standalone validation tools.** The statistical gates (DSR, regime detection, CPCV) are exported independently. A user with a human-designed strategy can validate it through the same rigorous pipeline. This is where the real value lies today.

3. **Hybrid generation (future).** Instead of asking the LLM to generate strategies from scratch, provide human-designed strategy skeletons (e.g., "trend-following with ATR-based stops") and let the LLM optimize parameters. This constrains the search space to strategies with known structural edge, potentially improving graduation rates.

4. **Higher-frequency data (future).** Current backtests use 1h/4h/1d bars. Microstructure effects (order flow, bid-ask dynamics) may provide edge that is detectable at higher frequencies. This requires tick data access and more sophisticated backtesting infrastructure.

5. **Relaxed gates for research mode.** A "research" flag that reports gate results without enforcing pass/fail, allowing users to study near-misses and understand what would need to change for graduation.

## References

- Bailey, D.H. and Lopez de Prado, M. (2014). "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and the Skewness/Kurtosis of Returns." *Journal of Portfolio Management*.
- Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley. Chapter 12: CPCV.
- Tulving, E. (1973). "Encoding Specificity and Retrieval Processes in Episodic Memory." Referenced in ADR-001 for OWM scoring context.
