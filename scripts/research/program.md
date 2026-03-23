# Research Program: Memory-Enhanced Trading

## Objective
Determine whether injecting historical trade memories into Strategy E's
decision process can improve risk-adjusted returns (Sharpe ratio).

## Constraints
- Fixed backtest window: BTCUSDT 1H, 2025-06-01 to 2026-03-21
  - Training: 2025-06-01 to 2025-11-30 (memory generation)
  - Test: 2025-12-01 to 2026-03-21 (evaluation)
- Baseline: Strategy E unmodified (LONG at H14 UTC when trend_12h > 0)
- Each iteration = one backtest run (~seconds)
- Agent decides what to modify, runs it, evaluates, keeps or discards

## Search Space (what the agent can modify)
1. **Memory filter threshold**: similarity_cutoff (0.3 - 0.9)
2. **Negative outcome threshold**: skip if avg_r < X (-2.0 to 0.0)
3. **Context dimensions**: which features matter for similarity
   - hour_utc weight (0.0 - 1.0)
   - trend_direction weight (0.0 - 1.0)
   - trend_magnitude weight (0.0 - 1.0)
   - regime weight (0.0 - 1.0)
   - atr_similarity weight (0.0 - 1.0)
4. **Top-K recall**: how many memories to consider (1 - 20)
5. **Skip logic**: skip on negative avg, or skip on majority negative, or confidence-weighted

## Evaluation Metric
Primary: Sharpe ratio improvement over baseline
Secondary: Profit factor, win rate, max drawdown

## Success Criteria
Memory injection is validated if:
- Sharpe improves by ≥ 0.5 over baseline in test period
- Win rate does not decrease by > 5pp
- Correctly filters more losers than winners (skipped_losers > skipped_winners)
