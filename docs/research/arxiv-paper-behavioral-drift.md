# Behavioral Drift Detection for AI Trading Agents: A Statistical Process Control Approach

**Syuan Wei Peng**

Mnemox AI, Taiwan

syuanwei@mnemox.ai

---

## Abstract

AI trading agents operating autonomously in financial markets lack the ability to detect when their own behavior has degraded. Unlike market regime detection, which monitors external conditions, behavioral drift detection monitors the agent itself -- asking whether its current performance deviates from its established baseline. We formulate this as a Statistical Process Control (SPC) problem and apply the Cumulative Sum (CUSUM) control chart, originally developed for manufacturing quality control, to monitor agent win rate deviations and automatically reduce position sizes when drift is detected. We tested three approaches: Bayesian Online Changepoint Detection (BOCPD), a Decision Quality Score (DQS), and CUSUM with adaptive baseline. BOCPD failed on sparse binary trade sequences; DQS achieved zero separation between winning and losing trades. Only CUSUM succeeded. Across 200 strategy configurations on two cryptocurrency markets (BTCUSDT, ETHUSDT) with 3 years of data and walk-forward validation, CUSUM-based position adjustment achieved a 73.5% win rate on drawdown reduction versus no calibration ($d = 0.76$, $p \approx 0$), and outperformed all three naive baselines with statistical significance. We report both positive and negative results as contributions to the nascent field of agent behavioral quality control.

---

## 1. Introduction

The proliferation of AI-driven trading agents has introduced a class of autonomous systems that execute financial decisions with minimal human oversight. These agents -- whether built on large language models, reinforcement learning, or rule-based strategies -- share a common vulnerability: they cannot detect when their own behavior has drifted from what historically works.

This is distinct from the well-studied problem of market regime detection. Market regime models ask "has the market changed?" Agent behavioral drift asks "am I performing differently than I should be?" The distinction matters because an agent can begin underperforming even when market conditions appear stable, due to subtle shifts in execution patterns, strategy parameter sensitivity, or data distribution drift.

The consequences of undetected behavioral drift in autonomous trading are concrete. A strategy that maintained a 55% win rate during its in-sample calibration period may silently degrade to 40% over subsequent months. Without a detection mechanism, the agent continues trading at full position size, accumulating drawdown that a simple monitoring system could have mitigated.

We propose framing agent behavioral drift as a Statistical Process Control problem. SPC methods, developed for manufacturing quality assurance beginning with Page (1954), are designed for precisely this type of monitoring: detecting when a process that was in control has shifted. The key insight is that an agent's sequence of trade outcomes -- wins and losses -- is analogous to a production line's quality measurements. When the process mean shifts (win rate degrades), the control chart should signal.

Why SPC rather than machine learning or Bayesian inference? The answer is data density. A trading agent producing 100-500 trades over several months generates sparse, binary outcome sequences. This is far too little data for neural network approaches and, as we demonstrate, insufficient for Bayesian Online Changepoint Detection, which requires dense continuous streams for reliable posterior inference. CUSUM, by contrast, was designed for exactly this regime: detecting mean shifts in sparse sequential data with known statistical guarantees on detection delay.

Our contributions are: (1) the first application of SPC to AI trading agent behavioral monitoring, formulated as a quality control problem; (2) empirical validation across 200 strategies on two markets showing CUSUM outperforms three naive baselines; and (3) honest negative results on BOCPD and DQS that inform future research directions.

---

## 2. Related Work

**AI trading agents with memory.** FinMem (Li et al., 2024) introduced a three-layer memory architecture for LLM-based trading, demonstrating that structured memory improves decision quality. ATLAS (2026) explored multi-agent frameworks with adaptive prompt optimization for trading decisions. TradingAgents (Xiao et al., 2025) modeled collaborative multi-agent trading with shared context. None of these systems monitor the agent's own behavioral trajectory; all focus on improving market analysis or decision-making without a self-diagnostic capability.

**Changepoint detection.** Adams and MacKay (2007) developed Bayesian Online Changepoint Detection (BOCPD), which maintains a posterior distribution over run lengths and has been widely applied to financial time series for regime detection. BOCPD uses conjugate prior models (Beta-Bernoulli for binary data, Normal-Inverse-Gamma for continuous) to perform exact online inference. The algorithm has strong theoretical properties but, as we show, requires data densities that trading agent outcome sequences rarely achieve. Page (1954) introduced the Cumulative Sum control chart for detecting small persistent shifts in process means, a cornerstone of Statistical Process Control. CUSUM has formal bounds on Average Run Length (ARL) under both null and alternative hypotheses, making it suitable for applications where false alarm rates must be controlled.

**Behavioral monitoring in non-trading domains.** The concept of monitoring an agent's behavioral consistency has precedent in software reliability engineering and clinical trial monitoring, where CUSUM charts track error rates and adverse event frequencies respectively. To our knowledge, no prior work applies these methods to AI trading agent behavioral sequences.

**Memory and recall in RL.** Prioritized Experience Replay (Schaul et al., 2015) demonstrated that weighting experience by temporal-difference error improves learning efficiency. Our system uses Outcome-Weighted Memory (OWM), a five-factor multiplicative recall model that extends prioritized replay concepts to trading agent memory, as the foundation on which behavioral monitoring is built.

---

## 3. Method

### 3.1 Problem Formulation

Let an agent execute a sequence of trades $\{t_1, t_2, \ldots, t_n\}$ where each trade produces a binary outcome $x_i \in \{0, 1\}$ (loss or win). The agent's baseline win rate $\mu_0$ is established from an in-sample (IS) calibration period. Behavioral drift occurs when the true win rate shifts to $\mu_1 < \mu_0$ during the out-of-sample (OOS) period.

We seek a monitoring statistic $S_n$ that (a) triggers an alert when sufficient evidence of drift accumulates, (b) does not trigger during normal variance, and (c) resets when performance recovers. This is the standard one-sided SPC formulation for detecting downward process mean shifts.

### 3.2 CUSUM with Adaptive Baseline

The CUSUM statistic tracks cumulative deviation from the baseline win rate:

$$S_n = \max\left(0, \ S_{n-1} + (\mu_0 - x_n)\right)$$

where $\mu_0$ is the baseline win rate from IS data, and $x_n = 1$ if trade $n$ is a win, $0$ otherwise. The statistic $S_n$ increases by $\mu_0$ on each loss and decreases by $(1 - \mu_0)$ on each win. The $\max(0, \cdot)$ operator resets the accumulator when performance recovers, preventing historical good performance from masking current degradation.

An alert fires when $S_n > h$ where $h = 4.0$ is the detection threshold. During an alert, the agent reduces its position size:

$$\text{lot}_n = \begin{cases} \text{lot}_{\text{base}} \times 0.5 & \text{if } S_n > h \\ \text{lot}_{\text{base}} & \text{otherwise} \end{cases}$$

The alert clears when $S_n$ returns to 0, indicating the win rate has recovered to baseline.

**Warm-start protocol.** The adaptive baseline is critical. Rather than using a hardcoded $\mu_0 = 0.5$, we compute $\mu_0$ from the agent's IS trades. This addresses a failure mode discovered in early experiments: a hardcoded target produced 100% alert rates on 10 of 12 initial test configurations because most strategies' true win rates were far from 0.5.

### 3.3 BOCPD: Why We Tested It and Why It Failed

Bayesian Online Changepoint Detection (Adams and MacKay, 2007) maintains a posterior distribution over the run length $r_t$ -- the number of observations since the last changepoint. We implemented BOCPD with two conjugate models: Beta-Bernoulli for win/loss sequences and Normal-Inverse-Gamma for P&L distributions.

BOCPD failed for three reasons:

1. **Insufficient data density.** BOCPD requires enough observations within each run segment to update the posterior meaningfully. A trading agent producing 100 OOS trades does not generate enough data for the posterior to converge before the next drift event. In our Level 0 synthetic tests, BOCPD changepoint probability never exceeded 0.21 even on a dramatic 65% to 25% win rate shift (with hazard rate $\lambda = 50$).

2. **Warm-start boundary artifact.** After warm-starting with 200+ IS trades, BOCPD detected the IS-to-OOS boundary as a permanent changepoint and never recovered. The posterior became stuck at run length $r = 1$ indefinitely.

3. **Binary data limitation.** BOCPD was designed for dense continuous streams (e.g., sensor readings at 1 Hz). A binary win/loss sequence with gaps between trades provides far less information per observation than a continuous signal.

CUSUM, by contrast, was specifically designed for sparse binary sequences in manufacturing quality control. This explains its success where BOCPD failed.

### 3.4 DQS: Trade-Level Scoring and Why It Failed

We also developed a Decision Quality Score (DQS) -- a five-factor pre-trade scoring system intended to predict individual trade quality based on regime match, position sizing, process adherence, risk state, and historical pattern match.

DQS failed completely at the trade level. In diagnostic testing across three strategies, DQS produced identical scores for winning and losing trades:

| Strategy | DQS (Winners) | DQS (Losers) | Separation |
|----------|---------------|--------------|------------|
| TrendFollow | 4.90 | 4.90 | 0.000 |
| Breakout | 6.16 | 6.16 | 0.000 |
| MeanReversion | 5.67 | 5.67 | 0.000 |

**Root cause.** All DQS factors use session-level information (overall strategy win rate, overall Kelly fraction, overall drawdown). Every trade from the same strategy in the same session sees the same historical context and therefore receives the same score. DQS distinguishes between strategies but cannot distinguish between trades within a strategy. This is a fundamental limitation: any feature that predicts individual trade outcomes is itself a trading signal, not a monitoring statistic.

This negative result is important because it establishes a boundary: behavioral monitoring operates at the strategy level, not the trade level.

---

## 4. Experimental Setup

### 4.1 Strategy Generation

We generated 200 strategies from a parameter grid over four dimensions: trend threshold (0.3), ATR filter (30--70), stop-loss (1.0--3.0 ATR), take-profit (1.5--4.5 ATR), and hold period (12--36 bars). Strategies were filtered to require a minimum of 30 IS trades. This grid-based approach avoids cherry-picking: the 200 strategies span a range of characteristics from tight-stop scalpers to wide-stop swing traders.

### 4.2 Market Data

- **Symbols**: BTCUSDT, ETHUSDT
- **Timeframes**: 1h, 4h
- **Data period**: 1,095 days (3.0 years) of Binance OHLCV data
- **Walk-forward split**: 67% in-sample / 33% out-of-sample

Each symbol-timeframe combination runs 50 strategies, producing 200 total experiments.

### 4.3 Agents

Five agents execute identical trades on each strategy. All agents receive the same entry and exit signals; they differ only in position sizing logic:

1. **BaseAgent** -- Fixed lot size, no calibration. The null hypothesis.
2. **CUSUMOnly** -- CUSUM with adaptive baseline from IS trades. Lot $\times 0.5$ when alert fires. Never skips trades.
3. **PeriodicReduce** -- Every 50 trades, reduces lot for 10 trades. No market intelligence.
4. **RandomSkip** -- Randomly reduces lot on 30% of trades (seed = 42 for reproducibility). Tests whether CUSUM's timing is better than chance.
5. **SimpleWR** -- Rolling 20-trade win rate; reduces lot when WR drops more than 10% below IS baseline. Uses the same warm-start as CUSUM. The strongest naive baseline.

All agents apply the same $\times 0.5$ lot reduction factor when triggered, isolating the detection mechanism as the only variable.

### 4.4 Metrics

- **Equity-adjusted max drawdown**: Maximum peak-to-trough decline in lot-weighted equity, measured in dollars. This accounts for position sizing differences.
- **DD reduction**: $\text{DD}_{\text{baseline}} - \text{DD}_{\text{CUSUM}}$, positive values indicate CUSUM improvement.
- **Paired $t$-test**: One-sided test on the 200-element vector of DD differences ($H_0$: mean difference $\leq 0$).
- **Bootstrap 95% CI**: 5,000 bootstrap resamples of the mean DD reduction.
- **Cohen's $d$**: Standardized effect size.

---

## 5. Results

### 5.1 CUSUM vs. Baselines

Table 1 shows CUSUM's pairwise performance against each baseline on drawdown reduction across all 200 strategies.

**Table 1.** CUSUM vs. baselines on equity-adjusted max drawdown reduction (positive = CUSUM better). All $p$-values from one-sided paired $t$-tests.

| Comparison | Win Rate | Mean DD $\Delta$ | $p$-value | Cohen's $d$ |
|:-----------|:--------:|:----------------:|:---------:|:-----------:|
| vs. No calibration | 73.5% | +3,840.02 | $< 10^{-6}$ | 0.76 (medium) |
| vs. Periodic | 63.0% | +2,650.13 | $< 10^{-6}$ | 0.59 (medium) |
| vs. Random | 57.5% | +1,546.95 | $< 10^{-6}$ | 0.39 (small) |
| vs. Simple WR | 66.5% | +1,532.53 | $< 10^{-6}$ | 0.45 (small) |

Bootstrap 95% CI for DD reduction vs. BaseAgent: [+3,180.69, +4,559.59]. The interval excludes zero.

CUSUM also improved PnL on average: mean PnL change of +2,181.23 versus BaseAgent, with CUSUM producing better PnL in 60% of strategies.

### 5.2 Per-Market Breakdown

Table 2 shows CUSUM performance broken down by symbol and timeframe.

**Table 2.** CUSUM vs. BaseAgent by market segment.

| Segment | $N$ | Mean DD $\Delta$ | Win Rate | $p$-value |
|:--------|:---:|:----------------:|:--------:|:---------:|
| BTCUSDT 1h | 50 | +9,972.60 | 100% | $< 10^{-4}$ |
| BTCUSDT 4h | 50 | +4,978.75 | 76% | $< 10^{-4}$ |
| ETHUSDT 1h | 50 | +399.11 | 98% | $< 10^{-4}$ |
| ETHUSDT 4h | 50 | +9.61 | 20% | 0.2527 |

The results reveal a clear pattern: CUSUM's effectiveness scales with trade frequency and price volatility. BTCUSDT 1h (highest trade count, largest price moves) shows the strongest effect. ETHUSDT 4h (fewest trades, smallest moves) shows no significant effect.

### 5.3 Negative Results

**Table 3.** Approaches that failed. Included as contributions to the field.

| Approach | Failure Mode | Root Cause |
|:---------|:-------------|:-----------|
| BOCPD (Beta-Bernoulli) | Max $P(\text{changepoint}) = 0.21$ on 65%$\to$25% WR shift | Data too sparse for posterior convergence |
| BOCPD (warm-start) | Stuck at run length = 1 after IS boundary | IS$\to$OOS transition detected as permanent changepoint |
| DQS (trade-level) | Separation = 0.000 across all strategies | Session-level features cannot distinguish individual trades |
| CalibratedAgent (Phase 5) | Skipped 97% of trades, 48/100 zero-trade experiments | DQS skip tier too aggressive on cold-start |

### 5.4 Caveats

We flag four limitations that qualify the positive results:

1. **ETHUSDT 4h failure.** CUSUM achieves only 20% win rate on this segment ($p = 0.25$). On low-frequency data, strategies produce too few OOS trades for CUSUM to accumulate sufficient evidence before resetting. This establishes a minimum trade-count requirement for CUSUM applicability.

2. **BTC dominance.** BTCUSDT accounts for the majority of absolute DD reduction (\$9,973 + \$4,979 vs. \$399 + \$10 for ETHUSDT). BTC's larger price moves create larger absolute drawdowns, giving CUSUM more room to help. The effect may be partially an artifact of absolute dollar measurement.

3. **CUSUM reduction rate.** Across all experiments, CUSUM reduced lot size on approximately 41% of OOS trades. This is aggressive. On high-frequency data with many trades, the cumulative protection is substantial. On low-frequency data, CUSUM fires and resets without accumulating meaningful signal.

4. **SimpleWR gap is small.** While CUSUM beats SimpleWR with statistical significance ($p < 10^{-6}$), the practical effect size is modest ($d = 0.45$). SimpleWR achieves approximately 80% of CUSUM's drawdown reduction with zero algorithmic complexity. Section 6 discusses whether CUSUM's statistical rigor justifies its additional complexity.

---

## 6. Discussion

### 6.1 Why SPC Works for This Problem

The success of CUSUM and failure of BOCPD can be understood through the lens of data requirements. BOCPD maintains a full posterior distribution over run lengths, requiring enough data within each run segment to distinguish signal from noise. A trading agent producing 100--500 binary outcomes over months does not meet this requirement. CUSUM, by contrast, was designed for exactly this data regime -- Page (1954) developed it for manufacturing settings where inspections might occur once per shift, producing sparse sequential observations.

The binary nature of trade outcomes (win/loss) further favors CUSUM. The CUSUM statistic for binary data has a simple, interpretable form: it accumulates the deviation of observed wins from expected wins. No distributional assumptions beyond stationarity under the null hypothesis are needed.

### 6.2 The SimpleWR Question

The most challenging result for CUSUM's value proposition is its modest advantage over SimpleWR ($d = 0.45$). SimpleWR -- a rolling 20-trade window with a 10% threshold -- is trivial to implement and achieves comparable drawdown reduction.

However, CUSUM offers two formal advantages:

1. **Detection delay bounds.** CUSUM has well-characterized Average Run Length (ARL) properties. For a given threshold $h$ and shift magnitude $\delta$, the expected number of observations until detection is bounded. SimpleWR has no such guarantee; its detection speed depends on the arbitrary choice of window size and threshold.

2. **Cumulative evidence.** CUSUM accumulates evidence across all observations since the last reset. A gradual drift from 55% to 45% win rate will eventually trigger CUSUM even if no 20-trade window falls below threshold. SimpleWR can miss gradual shifts entirely if no individual window captures enough degradation. This distinction becomes important for slow regime changes that unfold over 50--100 trades.

Whether these theoretical advantages justify CUSUM's additional complexity depends on the deployment context. For a production system with regulatory requirements (e.g., reporting detection delay bounds), CUSUM is clearly preferable. For a solo trader seeking simple risk reduction, SimpleWR may suffice.

### 6.3 Limitations

Several limitations constrain generalizability:

- **Cryptocurrency only.** We tested on BTCUSDT and ETHUSDT. Cryptocurrency markets have distinct volatility characteristics (24/7 trading, high kurtosis, correlation with macro events). Performance on forex, equities, or fixed income is unknown.

- **Synthetic strategies.** All 200 strategies were generated from a parameter grid, not developed by human traders or trained ML models. Real-world strategies may exhibit different degradation patterns.

- **No live validation.** All results are from historical walk-forward simulation. Live trading introduces execution slippage, latency, and market impact that simulations do not capture.

- **Single reduction factor.** We used a fixed $\times 0.5$ lot reduction. The optimal reduction factor and CUSUM threshold ($h = 4.0$) were not optimized; they represent reasonable defaults that may not be optimal for all strategy types.

### 6.4 Broader Implications

As AI trading agents become more prevalent, the question of behavioral quality control will become unavoidable. Regulatory frameworks for autonomous trading (e.g., MiFID II algorithmic trading requirements, SEC Rule 15c3-5) increasingly require firms to demonstrate that their algorithms are operating within expected parameters. CUSUM-based behavioral monitoring provides a simple, interpretable, and statistically grounded mechanism for this purpose -- one that produces a clear audit trail of when drift was detected and what action was taken.

The negative results are equally important for the field. The failure of BOCPD on sparse binary sequences provides a clear guideline: when monitoring trading agent outcomes, use SPC methods, not Bayesian changepoint detection. The failure of trade-level DQS establishes that behavioral monitoring operates at the strategy level, not the individual trade level -- a boundary that future research should respect.

---

## 7. Conclusion

We have presented the first application of Statistical Process Control to AI trading agent behavioral monitoring. The CUSUM control chart, with an adaptive baseline established from in-sample trades, successfully detects win rate degradation and reduces drawdown through automatic position sizing adjustment. Across 200 strategy configurations on BTCUSDT and ETHUSDT with 3 years of walk-forward validation, CUSUM achieved a 73.5% win rate on drawdown reduction versus no calibration ($d = 0.76$, $p < 10^{-6}$, bootstrap 95% CI [+3,180.69, +4,559.59]), and outperformed all three naive baselines with statistical significance.

We also report two negative results that we consider contributions: BOCPD fails on sparse binary trade sequences due to insufficient data density for posterior convergence, and trade-level quality scoring achieves zero separation between winning and losing trades when using session-level features. These results narrow the design space for future agent monitoring systems.

Limitations include restriction to cryptocurrency markets, synthetic strategies, and lack of live validation. Future work should extend validation to additional asset classes, test on strategies developed by human traders or ML systems, optimize the CUSUM threshold and lot reduction parameters, and conduct live deployment studies. The ETHUSDT 4h failure suggests that minimum trade-count requirements should be established before deploying CUSUM-based monitoring.

The broader message is that as AI agents assume greater autonomy in financial markets, we need quality control systems for the agents themselves -- not just for the markets they trade. SPC, a 70-year-old methodology from manufacturing, turns out to be well-suited for this purpose.

---

## References

- Adams, R. P., & MacKay, D. J. C. (2007). Bayesian Online Changepoint Detection. *arXiv preprint arXiv:0710.3742*.
- Bailey, D. H., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality. *Journal of Portfolio Management*, 40(5), 94--107.
- Li, Y., Wang, Z., & Huang, W. (2024). FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design. In *Workshop on Financial Large Language Models, ICLR 2024*.
- Page, E. S. (1954). Continuous Inspection Schemes. *Biometrika*, 41(1/2), 100--115.
- Schaul, T., Quan, J., Antonoglou, I., & Silver, D. (2015). Prioritized Experience Replay. *arXiv preprint arXiv:1511.05952*.
- Shefrin, H., & Statman, M. (1985). The Disposition to Sell Winners Too Early and Ride Losers Too Long: Theory and Evidence. *Journal of Finance*, 40(3), 777--790.
- Tulving, E. (1972). Episodic and Semantic Memory. In E. Tulving & W. Donaldson (Eds.), *Organization of Memory* (pp. 381--403). Academic Press.
- Xiao, Y., et al. (2025). TradingAgents: Multi-Agents LLM Financial Trading Framework. *arXiv preprint arXiv:2412.20138*.

---

*Code and data available at: https://github.com/mnemox-ai/tradememory-protocol*

*Preprint -- April 2026*
