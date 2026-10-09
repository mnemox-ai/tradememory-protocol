# FinRL integration probe — frozen before execution

Date: 2026-10-10 (Asia/Taipei). Scope: local research; no orders, production databases, external messages, paid model APIs or changes to existing strategies. This is a reuse/integration measurement, not a new trading method or a test of novelty.

## Questions and prior art

1. Can the actual upstream accounting preserve cash, charge costs, and keep observations causal? Can it generate reusable policy trajectories?
2. Does an unchanged Stable-Baselines3 PPO baseline justify adding this stack to our experiments, relative to cash, full exposure and a fixed 20-day moving-average rule?
3. Can current TradeMemory retrieve those observed trajectories with correct temporal eligibility and explicit outcome/loss ordering? This measures integration, NOT whether an LLM makes better decisions after recall.

Reuse: upstream FinRL `PortfolioOptimizationEnv`, FinRL-X `BacktestEngine`, `bt`, SB3 PPO and existing TradeMemory recall functions. Only import/Gym adapters, data normalization, experiment orchestration and independent arithmetic controls are new. No custom RL, backtest engine, vector store or memory ranking.

Prior art consulted before design: FinMem (https://github.com/pipiku915/FinMem-LLM-StockTrading), FinAgent (https://arxiv.org/html/2402.18485v2), META (https://arxiv.org/html/2609.28771v1), SB3 evaluation guidance (https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html). Existing TradeMemory replay already supports LLM prompt memory; AS1 tested another selector definition on reused FX history. Do not repeat AS1 or replace its verdict. LLM memory ablations belong in existing replay and require a named model and equal-information controls; a hand-written veto over losses-first recall is NOT a valid substitute.

## Frozen market probe

- Assets fixed before fetching: SPY, QQQ, GLD. Public Yahoo Finance adjusted OHLC. Fixed download interval 2015-01-01 through 2026-10-01 (exclusive). Snapshot CSV + SHA-256; any missing asset fails that asset, never substitute a winner.
- Training: dates before 2023-01-01. Evaluation: 2023-01-01 to 2024-12-31 and 2025-01-01 to 2026-09-30. Two reporting windows of the same frozen model, not independent training trials. They are held out from this run's training, NOT a claim that Sean/the world never saw this history.
- Long-only, one ETF + cash per environment. Target ETF weight in [0,1]; cash=1-weight. This isolates cash semantics and avoids survivorship in selected stocks. Fractional portfolios; no MT5 leverage/lot/spread/swap claim.
- FinRL `trf` cost model, 10 bps per side. Observations: 20-day window of close/high/low ratios using only completed prices; actions decide close_t to close_(t+1). Same-close execution is an idealized research convention, not executable fills.
- PPO: SB3 implementation, seeds [11,23,37,51,71], 32,768 requested timesteps, n_steps=512, batch_size=64, n_epochs=5, learning_rate=0.0003, gamma=0.99, policy=[32,32], reward_scaling=100, CPU, one thread. No sweep, early stopping, model selection or test-window tuning. Actual timestep count and package versions recorded.
- Baselines on identical upstream environment/time/costs: cash; 100% ETF target each day; close >= trailing SMA20 => ETF, else cash. They are targets/rebalances, not uncosted price-return proxies.
- Outputs: net return, maximum drawdown, daily Sharpe (descriptive), mean ETF target exposure, trading turnover, both windows and all seeds. Report each asset and seed, including failures. Never take best-of-N.

## Instrument gates / stop conditions

Before market results: known arithmetic tests for cash, half/full exposure, flat-price entry and liquidation costs, round-trip costs, terminal transitions/reward duplication, future-data perturbation, future-memory exclusion, historical replay clock, upstream Gym adapter equivalence. Positive/negative controls must detect a deliberately broken full-investment normalization and future-memory inclusion. Failed paths are quarantined, not silently patched or used to produce efficacy claims.

FinRL-X and FinRL have different paths; failures in the generic BacktestEngine do not condemn adaptive_rotation. Test it separately where feasible. Original upstream sources remain unchanged. Narrow adapter omissions must be documented and compared step-for-step to original nonterminal accounting.

## Decision rules

- Recommend a component for reuse only if its required accounting/causality controls pass and actual run artifacts reproduce. Failed controls block that particular integration, irrespective of attractive returns.
- Market baseline performance is exploratory suitability evidence. This budget is insufficient to declare that RL cannot work, and seed variation is not an independent sample of market histories. No statistical alpha/promote/deploy conclusion from this probe.
- TradeMemory recall output is an intentionally selected sample; never interpret a losses-first recalled mean as an unbiased expected-return estimate. Existing API runtime recency must use an explicit replay clock in research and results show whether that changes ranks.
- A credible memory efficacy conclusion remains pending unless the same actual decision-maker is tested with no memory, equal-information simple memory, TradeMemory, and negative controls. Report this limit instead of claiming the engineering integration proved efficacy.

## Durable value even for negative results

Pinned upstream sources, data and package versions; arithmetic and causal checks; reproducible trajectories; measured adaptation costs and specific interfaces suitable for later existing-replay experiments. No reopening of closed alpha-factory batches.

## Instrument-calibration amendment v1.1 (before any market run)

The original portfolio environment failed first-entry cost and terminal-reward controls. The FinRL-X generic engine failed half-cash and trajectory controls. Both paths are quarantined; original `controls.json` is preserved as `portfolio_controls.json`.

Test upstream `StockTradingEnv` as the alternative, with its native integer shares, cash and per-side buy/sell costs. Capital remains $10,000; report residual cash/integer share effects. A thin adapter maps target weights to integer share deltas, normalizes causal trailing OHLC ratios, and supplies log-return reward x100 (the original frozen reward definition); all fills/cash/costs come from upstream. It ends on the last real price transition instead of the original extra terminal call that repeats the last reward. Verify step-by-step accounting equality before training. These are explicit interface adaptations, not repairs of the quarantined accounting engines. Markets, splits, seeds, budget, costs, baselines and decision rules remain frozen.
