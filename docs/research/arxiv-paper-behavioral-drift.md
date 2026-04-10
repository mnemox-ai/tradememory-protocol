# Behavioral Drift Detection for AI Trading Agents: A Statistical Process Control Approach

**Syuan Wei Peng**

Mnemox AI, Taiwan

johnson90207@gmail.com

---

## Abstract

AI trading agents operating autonomously in financial markets lack the ability to detect when their own behavior has degraded. Unlike market regime detection, which monitors external conditions, behavioral drift detection monitors the agent itself -- asking whether its current performance deviates from its established baseline. We formulate this as a Statistical Process Control (SPC) problem and apply the Cumulative Sum (CUSUM) control chart, originally developed for manufacturing quality control, to monitor agent win rate deviations and automatically reduce position sizes when drift is detected. We tested three approaches: Bayesian Online Changepoint Detection (BOCPD), a Decision Quality Score (DQS), and CUSUM with adaptive baseline. BOCPD failed on sparse binary trade sequences; DQS achieved zero separation between winning and losing trades. Only CUSUM succeeded. Across 200 strategy configurations on two cryptocurrency markets (BTCUSDT, ETHUSDT) with 3 years of data and walk-forward validation, CUSUM-based position adjustment achieved a 73.5% win rate on drawdown reduction versus no calibration ($d = 0.76$, $p \approx 0$), outperforming three naive behavioral baselines. However, a simple equity drawdown threshold (MaxDDStop) outperformed CUSUM in 93.5% of strategies, demonstrating that outcome-based monitoring is more effective than behavioral monitoring for pure risk reduction. We argue that CUSUM's value lies in behavioral diagnostics -- identifying *why* performance degrades -- rather than risk mitigation, and recommend combining both approaches. We report both positive and negative results as contributions to the nascent field of agent behavioral quality control.

---

## 1. Introduction

The proliferation of AI-driven trading agents has introduced a class of autonomous systems that execute financial decisions with minimal human oversight. These agents -- whether built on large language models (Li et al., 2024; Kim et al., 2025; Xiao et al., 2025), reinforcement learning (Yang et al., 2020), or rule-based strategies -- share a common vulnerability: they cannot detect when their own behavior has drifted from what historically works.

This is distinct from the well-studied problem of market regime detection. Market regime models ask "has the market changed?" Agent behavioral drift asks "am I performing differently than I should be?" The distinction matters because an agent can begin underperforming even when market conditions appear stable, due to subtle shifts in execution patterns, strategy parameter sensitivity, or data distribution drift (Gama et al., 2014). In the machine learning literature, this is related to concept drift -- the phenomenon where the statistical properties of the target variable change over time (Lu et al., 2018). However, concept drift research focuses primarily on classifier retraining, whereas our problem requires real-time monitoring with immediate risk management actions.

The consequences of undetected behavioral drift in autonomous trading are concrete and financially material. A strategy that maintained a 55% win rate during its in-sample calibration period may silently degrade to 40% over subsequent months. Without a detection mechanism, the agent continues trading at full position size, accumulating drawdown that a simple monitoring system could have mitigated. In institutional settings, undetected behavioral drift can trigger regulatory scrutiny: MiFID II requires algorithmic trading firms to have "effective systems and risk controls" (Article 17), and the EU AI Act classifies autonomous financial systems as high-risk, requiring ongoing monitoring of AI system performance post-deployment.

We propose framing agent behavioral drift as a Statistical Process Control (SPC) problem. SPC methods, developed for manufacturing quality assurance beginning with Page (1954) and systematized by Montgomery (2012), are designed for precisely this type of monitoring: detecting when a process that was "in control" has shifted. The key insight is that an agent's sequence of trade outcomes -- wins and losses -- is analogous to a production line's quality measurements. When the process mean shifts (win rate degrades), the control chart should signal. This framing is natural but, to our knowledge, unexplored: while SPC has been discussed in financial contexts (Woodall & Montgomery, 1999), it has not been applied to monitoring the behavioral consistency of autonomous trading agents.

Why SPC rather than machine learning or Bayesian inference? The answer is data density. A trading agent producing 100--500 trades over several months generates sparse, binary outcome sequences. This is far too little data for neural network approaches and, as we demonstrate, insufficient for Bayesian Online Changepoint Detection (Adams & MacKay, 2007), which requires dense continuous streams for reliable posterior inference. CUSUM, by contrast, was designed for exactly this regime: detecting mean shifts in sparse sequential data with known statistical guarantees on detection delay (Page, 1954). The practical implications are significant -- a monitoring system that requires thousands of observations before producing actionable signals is useless for a trading agent that executes 5--10 trades per week.

The position sizing response to detected drift is informed by the Kelly criterion literature (Kelly, 1956; Thorp, 2006). When an agent's win rate degrades, the Kelly-optimal bet size decreases. Our approach implements a simplified version: rather than continuously optimizing lot size via Kelly, we apply a binary reduction ($\times 0.5$) when CUSUM signals drift, and restore full size when the signal clears. This discrete approach sacrifices optimality for robustness and interpretability.

Our contributions are: (1) the first application of SPC to AI trading agent behavioral monitoring, formulated as a quality control problem rather than a prediction problem; (2) empirical validation across 200 strategies on two cryptocurrency markets showing CUSUM-based position adjustment outperforms three naive baselines on drawdown reduction with statistical significance; (3) honest negative results on BOCPD and DQS that narrow the design space for future agent monitoring systems; and (4) a discussion of the boundary between strategy-level and trade-level behavioral assessment.

---

## 2. Related Work

**AI trading agents with memory.** FinMem (Li et al., 2024) introduced a three-layer memory architecture (working, episodic, semantic) for LLM-based trading, demonstrating that structured memory improves decision quality. ATLAS (Kim et al., 2025) explored multi-agent frameworks with adaptive prompt optimization, where agents dynamically refine their prompts based on recent trading outcomes. TradingAgents (Xiao et al., 2025) modeled collaborative multi-agent trading with role-specialized agents sharing context. Yang et al. (2020) proposed ensemble deep reinforcement learning for stock trading with automated position management. None of these systems monitor the agent's own behavioral trajectory over time; all focus on improving market analysis or decision-making without a self-diagnostic capability. Our work is complementary: behavioral monitoring can be layered on top of any of these architectures to detect when the agent's learned behavior has degraded.

**Changepoint detection.** Adams and MacKay (2007) developed Bayesian Online Changepoint Detection (BOCPD), which maintains a posterior distribution over run lengths and has been widely applied to financial time series for regime detection. BOCPD uses conjugate prior models (Beta-Bernoulli for binary data, Normal-Inverse-Gamma for continuous) to perform exact online inference. The algorithm has strong theoretical properties but, as we show, requires data densities that trading agent outcome sequences rarely achieve. Page (1954) introduced the Cumulative Sum control chart for detecting small persistent shifts in process means, a cornerstone of Statistical Process Control. CUSUM has formal bounds on Average Run Length (ARL) under both null and alternative hypotheses (Montgomery, 2012), making it suitable for applications where false alarm rates must be controlled. Woodall and Montgomery (1999) surveyed SPC research directions, including applications beyond manufacturing, but did not consider autonomous agent monitoring.

**Concept drift in machine learning.** The broader machine learning community has extensively studied concept drift -- the phenomenon where the joint distribution $P(X, Y)$ changes over time (Gama et al., 2014; Lu et al., 2018). Concept drift detection methods include DDM (Drift Detection Method), EDDM, and ADWIN. However, these methods assume access to continuous prediction streams with ground truth labels arriving at each step. In trading, ground truth (whether a trade was profitable) arrives only when a position is closed, which may be hours or days after entry. This temporal sparsity makes standard concept drift detectors ill-suited for trading agent monitoring, motivating our use of SPC methods designed for sparse sequential data.

**Position sizing and risk management.** The Kelly criterion (Kelly, 1956; Thorp, 2006) provides the theoretically optimal bet size as a function of win rate and payoff ratio. Lopez de Prado (2018) discusses practical considerations for applying Kelly sizing in financial contexts, including the well-known problem of parameter estimation error leading to overbetting. Bailey and Lopez de Prado (2014) introduced the Deflated Sharpe Ratio to correct for multiple testing in strategy evaluation. Our approach can be viewed as a simplified adaptive Kelly system: when CUSUM detects that the win rate has shifted below baseline, the Kelly-optimal position size has decreased, and we respond with a discrete lot reduction.

**Behavioral monitoring in non-trading domains.** The concept of monitoring an agent's behavioral consistency has precedent in software reliability engineering, where CUSUM charts track defect rates in code releases, and in clinical trial monitoring, where sequential analysis methods (including CUSUM) track adverse event frequencies to enable early stopping decisions. Industrial SPC monitoring of process quality is a mature field with well-established methodology (Montgomery, 2012). To our knowledge, no prior work applies these methods to AI trading agent behavioral sequences -- a gap we attribute to the recency of autonomous AI trading agents as a practical deployment category.

**Memory and recall in RL.** Prioritized Experience Replay (Schaul et al., 2015) demonstrated that weighting experience by temporal-difference error improves learning efficiency. Our system uses Outcome-Weighted Memory (OWM), a five-factor multiplicative recall model that extends prioritized replay concepts to trading agent memory. OWM scores memories by outcome quality, context similarity, recency, confidence, and affective state, producing a ranked set of relevant past experiences. Behavioral monitoring is built on top of OWM: the agent's trade outcome sequence, stored in episodic memory, provides the data stream that CUSUM monitors.

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

**Omission of the allowance parameter.** The textbook CUSUM formulation includes a slack parameter $k$ (also called the allowance or reference value): $S_n = \max(0, S_{n-1} + (\mu_0 - x_n) - k)$, where $k$ typically equals half the shift magnitude one wishes to detect. We set $k = 0$ deliberately. For binary outcomes ($x_n \in \{0, 1\}$), the observation already takes only two values, and the "shift" is a change in the Bernoulli parameter $p$. Introducing $k > 0$ would suppress the CUSUM response to small-to-moderate drift, which is precisely what we want to detect early. With $k = 0$, the threshold $h$ alone controls sensitivity: a higher $h$ requires more cumulative evidence before triggering. We found $h = 4.0$ to be a reasonable default -- it requires roughly the equivalent of 4 consecutive unexpected losses to trigger, providing a balance between detection speed and false alarm rate. We acknowledge that this makes our CUSUM maximally sensitive, resulting in an approximately 41% alert rate across all OOS trades, and discuss the implications in Section 5.4.

**Warm-start protocol.** The adaptive baseline is critical. Rather than using a hardcoded $\mu_0 = 0.5$, we compute $\mu_0$ from the agent's IS trades. This addresses a failure mode discovered in early experiments: a hardcoded target produced 100% alert rates on 10 of 12 initial test configurations because most strategies' true win rates were far from 0.5.

**Adaptive baseline update.** After an initial burn-in of 20 OOS trades, the baseline $\mu_0$ is updated to the agent's observed OOS win rate. This adaptive mechanism serves two purposes. First, it handles cases where OOS conditions differ structurally from IS (e.g., the IS period contained a trending market that inflated win rates). Second, it anchors CUSUM to the agent's current steady-state performance rather than its historical peak, reducing alert fatigue. However, this introduces a limitation: if the agent enters OOS already in a degraded state, the adapted baseline will be low, and CUSUM will not fire until performance degrades further below the already-poor baseline. We consider this an acceptable tradeoff -- the alternative (fixed IS baseline) produces excessive false alarms that render the system unusable.

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

We generated strategies from a parameter grid over five dimensions: trend threshold (0.3, 0.7, 1.5), ATR percentile filter (30, 50, 70), stop-loss (1.0, 1.5, 2.5 ATR), take-profit (1.5, 3.0, 5.0 ATR), and maximum hold period (12, 36, 72 bars). We filtered to require take-profit strictly greater than stop-loss (positive expectancy structure) and a minimum of 30 IS trades. From the $3^5 = 243$ parameter combinations, this filtering produced approximately 150 valid strategies. For each symbol-timeframe pair, the first 50 qualifying strategies were used, yielding 200 total experiments across 4 market segments. This grid-based approach avoids cherry-picking: the 200 strategies span a range of characteristics from tight-stop scalpers ($\text{SL}=1.0$, hold $\leq 12$) to wide-stop swing traders ($\text{SL}=2.5$, hold $\leq 72$).

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
5. **SimpleWR** -- Rolling 20-trade win rate; reduces lot when WR drops more than 10% below IS baseline. Uses the same warm-start as CUSUM. The strongest behavioral baseline.
6. **MaxDDStop** -- Reduces lot when equity drawdown exceeds 15% of peak equity. This represents standard risk management practice: monitoring the equity curve rather than behavioral signals. Uses IS equity to establish the initial peak. The strongest outcome-based baseline.

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
| vs. MaxDDStop | **6.5%** | **-3,522.99** | 1.000 | **-0.76 (medium)** |

Bootstrap 95% CI for DD reduction vs. BaseAgent: [+3,180.69, +4,559.59]. The interval excludes zero.

CUSUM also improved PnL on average: mean PnL change of +2,181.23 versus BaseAgent, with CUSUM producing better PnL in 60% of strategies.

**The MaxDDStop result demands attention.** MaxDDStop -- a simple equity drawdown threshold with no behavioral intelligence -- achieves a 99.5% win rate against BaseAgent (mean DD reduction +7,363.01), dramatically outperforming CUSUM's 73.5%. In head-to-head comparison, MaxDDStop beats CUSUM in 93.5% of strategies ($d = 0.76$, $p < 10^{-6}$). This is arguably our most important result and is discussed in Section 6.2.

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

### 5.3 Robustness: Excluding the Dominant Segment

The BTCUSDT 1h segment shows a suspiciously perfect 100% win rate (50/50 strategies), raising the question of whether aggregate results are driven entirely by this segment. Table 3 reports statistics computed after excluding BTCUSDT 1h.

**Table 3.** CUSUM vs. baselines after excluding BTCUSDT 1h ($N = 150$).

| Comparison | Win Rate | Mean DD $\Delta$ | $p$-value | Cohen's $d$ |
|:-----------|:--------:|:----------------:|:---------:|:-----------:|
| vs. No calibration | 64.7% | +1,795.82 | $< 10^{-6}$ | 0.50 (medium) |
| vs. Simple WR | 57.3% | +151.13 | 0.179 | 0.08 (negligible) |

Bootstrap 95% CI for DD reduction vs. BaseAgent (without BTCUSDT 1h): [+1,255.96, +2,401.86]. The interval excludes zero.

This robustness check reveals an important nuance. CUSUM's advantage over BaseAgent remains statistically significant after excluding the dominant segment ($d = 0.50$, $p < 10^{-6}$), confirming that CUSUM provides genuine drawdown reduction beyond BTCUSDT 1h. However, the advantage over SimpleWR becomes statistically insignificant ($p = 0.179$, $d = 0.08$). This means that on the remaining three market segments (BTCUSDT 4h, ETHUSDT 1h, ETHUSDT 4h), SimpleWR achieves nearly identical drawdown reduction to CUSUM. The BTCUSDT 1h segment -- with its high trade count and large price moves -- is where CUSUM's cumulative evidence accumulation provides a measurable advantage over windowed approaches. On lower-frequency or lower-volatility segments, the simpler approach suffices.

### 5.4 Threshold Sensitivity

The CUSUM threshold $h$ controls the tradeoff between detection speed and false alarm rate. Table 4 reports results across five threshold values.

**Table 4.** CUSUM performance by threshold $h$ (vs. BaseAgent, all 200 strategies).

| $h$ | Win Rate | Mean DD $\Delta$ | Cohen's $d$ | Alert Rate |
|:---:|:--------:|:----------------:|:-----------:|:----------:|
| 2.0 | 86.5% | +5,412.38 | 0.88 (large) | 51.5% |
| 3.0 | 81.5% | +4,474.10 | 0.81 (large) | 39.0% |
| 4.0 | 73.0% | +3,754.08 | 0.78 (medium) | 30.5% |
| 5.0 | 64.0% | +2,789.88 | 0.64 (medium) | 24.4% |
| 6.0 | 58.0% | +2,157.39 | 0.57 (medium) | 19.1% |

All five threshold values achieve statistical significance ($p < 10^{-6}$ for all). The relationship between $h$ and performance is monotonic: lower thresholds detect drift faster, producing higher win rates and larger DD reductions, but at the cost of higher alert rates (more frequent lot reductions). At $h = 2.0$, CUSUM fires on 51.5% of OOS trades -- essentially trading at half lot most of the time -- while achieving the highest win rate (86.5%) and effect size ($d = 0.88$). At $h = 6.0$, CUSUM fires on only 19.1% of trades but still achieves a 58% win rate ($d = 0.57$).

The robustness of these results across all five threshold values is encouraging: the choice of $h = 4.0$ is not a lucky parameter pick. Any practitioner can choose $h$ based on their preferred tradeoff between detection sensitivity and intervention frequency. We note, however, that the strong performance of low-$h$ values (which fire very frequently) reinforces the concern raised in Section 5.1: much of CUSUM's drawdown reduction may come from the lot reduction itself rather than from the precision of drift detection timing.

### 5.5 Negative Results

**Table 5.** Approaches that failed. Included as contributions to the field.

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

5. **Strategy dependence.** The 200 strategies share the same underlying price series within each market segment. Strategies evaluated on the same BTCUSDT 1h data will exhibit correlated drawdowns -- a market crash produces simultaneous losses across all strategies. This violates the independence assumption of the paired $t$-test, potentially inflating statistical significance. Our bootstrap confidence intervals partially mitigate this (they capture variance in the DD reduction distribution) but do not fully account for the temporal correlation structure. The extremely small reported $p$-values ($< 10^{-6}$) should be interpreted with this caveat: the true effective sample size is smaller than 200 due to cross-strategy correlation. We note that the directional conclusions (CUSUM reduces DD more often than not) remain valid, as win rates are robust to dependence; it is the precision of $p$-values that is affected.

6. **Transaction costs.** Our simulation does not model transaction costs, slippage, or market impact. CUSUM reduces lot size on approximately 41% of OOS trades, which in practice means more frequent lot size changes. While this does not increase the number of trades (CUSUM never skips trades), varying lot sizes may incur additional costs on platforms that charge per-lot fees or have minimum lot requirements. The practical impact depends on the trading venue and instrument.

---

## 6. Discussion

### 6.1 Why SPC Works for This Problem

The success of CUSUM and failure of BOCPD can be understood through the lens of data requirements. BOCPD maintains a full posterior distribution over run lengths, requiring enough data within each run segment to distinguish signal from noise. A trading agent producing 100--500 binary outcomes over months does not meet this requirement. CUSUM, by contrast, was designed for exactly this data regime -- Page (1954) developed it for manufacturing settings where inspections might occur once per shift, producing sparse sequential observations.

The binary nature of trade outcomes (win/loss) further favors CUSUM. The CUSUM statistic for binary data has a simple, interpretable form: it accumulates the deviation of observed wins from expected wins. No distributional assumptions beyond stationarity under the null hypothesis are needed.

### 6.2 The MaxDDStop Result: Behavioral vs. Outcome Monitoring

The most important result in this paper is arguably a negative one: MaxDDStop -- a simple equity drawdown threshold -- outperforms CUSUM in 93.5% of strategies with the same effect size ($d = 0.76$) that CUSUM achieves against BaseAgent. This demands honest examination.

MaxDDStop monitors the **outcome** (equity drawdown) and responds when the symptom appears. CUSUM monitors the **behavior** (win rate) and responds when the cause is detected. In theory, behavioral monitoring should fire earlier, because win rate degrades before its effects accumulate into a measurable equity drawdown. In practice, our data shows the opposite: MaxDDStop's 15% equity threshold triggers more reliably and more effectively than CUSUM's behavioral signal.

Why? Three factors explain MaxDDStop's dominance:

1. **Direct measurement.** MaxDDStop measures exactly what we want to minimize (equity drawdown). CUSUM measures a proxy (win rate deviation) that is correlated but not identical. A strategy can have acceptable win rate but suffer large drawdowns from a few outsized losses that CUSUM does not detect.

2. **No warm-start sensitivity.** MaxDDStop tracks the equity curve directly and does not depend on an IS baseline that may not reflect OOS conditions. CUSUM's adaptive baseline introduces a 20-trade burn-in period during which degradation goes undetected.

3. **Higher alert coverage.** MaxDDStop fires on 99.5% of strategies because virtually all strategies experience at least one drawdown exceeding 15% during OOS. Its protection is nearly universal, while CUSUM's behavioral signal is more selective.

**Does this make CUSUM worthless?** Not entirely, but its role must be reframed. CUSUM's value is not in drawdown reduction -- MaxDDStop does that better. CUSUM's value is **diagnostic**: it answers *why* performance is degrading, not just *that* it is degrading. A MaxDDStop alert tells you "equity is down 15%." A CUSUM alert tells you "win rate has shifted below baseline." The latter is actionable for strategy development: it suggests the strategy's edge has eroded, prompting parameter re-optimization or strategy retirement. MaxDDStop provides no such insight.

In practice, we recommend combining both: MaxDDStop for immediate risk protection, CUSUM for behavioral diagnostics and audit trail. This combination is analogous to industrial practice, where control charts (CUSUM) coexist with alarm systems (MaxDDStop) -- the alarm stops the line, the chart tells you why it stopped.

### 6.3 The SimpleWR Question

Without BTCUSDT 1h, CUSUM's advantage over SimpleWR becomes statistically insignificant ($p = 0.179$, $d = 0.08$). SimpleWR -- a rolling 20-trade window -- achieves comparable drawdown reduction with zero algorithmic complexity. CUSUM's theoretical advantages (ARL bounds, cumulative evidence for gradual drift) do not manifest as practical advantages in our data.

This suggests that for behavioral monitoring specifically (as opposed to outcome monitoring via MaxDDStop), the choice between CUSUM and SimpleWR is a matter of preference, not performance. CUSUM offers formal statistical guarantees on detection delay; SimpleWR offers simplicity. In deployment contexts with regulatory requirements, CUSUM's formal properties may be preferred for audit and compliance purposes.

### 6.3 Connection to Adaptive Position Sizing

Our approach can be situated within the broader literature on adaptive position sizing. The Kelly criterion (Kelly, 1956) dictates that optimal bet size is a function of edge (win rate minus loss rate) and payoff ratio. When an agent's win rate degrades, the Kelly-optimal position decreases. CUSUM-based monitoring provides a mechanism to detect when this degradation has occurred, triggering a position reduction that approximates the directional adjustment Kelly would prescribe.

However, our implementation is deliberately simpler than full Kelly optimization. We use a binary $\times 0.5$ reduction rather than a continuously adjusted lot size. This design choice reflects a practical reality: estimating the precise Kelly fraction requires accurate estimates of both win rate and average win/loss ratio, which are noisy with sparse data. A binary reduction is more robust to estimation error, though it sacrifices optimality. Future work could explore graduated reduction schedules (e.g., CUSUM-proportional lot sizing) to bridge the gap between our discrete approach and continuous Kelly adjustment.

### 6.4 Limitations

Several limitations constrain generalizability:

- **Cryptocurrency only.** We tested on BTCUSDT and ETHUSDT. Cryptocurrency markets have distinct volatility characteristics (24/7 trading, high kurtosis, correlation with macro events). Performance on forex, equities, or fixed income is unknown.

- **Synthetic strategies.** All 200 strategies were generated from a parameter grid, not developed by human traders or trained ML models. Real-world strategies may exhibit different degradation patterns.

- **No live validation.** All results are from historical walk-forward simulation. Live trading introduces execution slippage, latency, and market impact that simulations do not capture.

- **Single reduction factor.** We used a fixed $\times 0.5$ lot reduction. The optimal reduction factor and CUSUM threshold ($h = 4.0$) were not optimized; they represent reasonable defaults that may not be optimal for all strategy types.

### 6.5 Broader Implications

As AI trading agents become more prevalent, the question of behavioral quality control will become unavoidable. Regulatory frameworks for autonomous trading (e.g., MiFID II algorithmic trading requirements, SEC Rule 15c3-5) increasingly require firms to demonstrate that their algorithms are operating within expected parameters. The EU AI Act classifies autonomous financial decision-making systems as high-risk, requiring continuous monitoring of AI system performance post-deployment. CUSUM-based behavioral monitoring provides a simple, interpretable, and statistically grounded mechanism for this purpose -- one that produces a clear audit trail of when drift was detected, what evidence triggered the detection (the CUSUM statistic value), and what action was taken (lot reduction). This audit trail is naturally compatible with compliance reporting requirements.

The negative results are equally important for the field. The failure of BOCPD on sparse binary sequences provides a clear guideline: when monitoring trading agent outcomes, use SPC methods designed for sparse data, not Bayesian changepoint detection methods that assume dense observation streams. The failure of trade-level DQS establishes that behavioral monitoring operates at the strategy level, not the individual trade level -- a boundary that future research should respect. Any feature that could predict individual trade outcomes would itself constitute a trading signal, not a monitoring statistic; this observation explains why trade-level quality scoring is fundamentally ill-posed as a monitoring problem.

We also note a broader implication for the AI agent safety community. The problem of detecting when an autonomous agent's behavior has drifted from its intended operating envelope is not unique to trading. Autonomous vehicles, industrial robots, and medical AI systems all face analogous challenges. SPC methods may be applicable to these domains as well, particularly when the agent's performance can be reduced to a binary or scalar quality signal observed sequentially over time.

---

## 7. Conclusion

We have presented the first application of Statistical Process Control to AI trading agent behavioral monitoring. The CUSUM control chart, with an adaptive baseline established from in-sample trades and updated after a 20-trade OOS burn-in, detects win rate degradation and reduces drawdown through automatic position sizing adjustment. Across 200 strategy configurations on BTCUSDT and ETHUSDT with 3 years of walk-forward validation, CUSUM achieved a 73.5% win rate on drawdown reduction versus no calibration ($d = 0.76$, $p < 10^{-6}$, bootstrap 95% CI [+3,180.69, +4,559.59]), and outperformed three naive behavioral baselines with statistical significance.

However, our most consequential finding is that MaxDDStop -- a simple equity drawdown threshold with no behavioral intelligence -- outperforms CUSUM on drawdown reduction in 93.5% of strategies ($d = 0.76$). This establishes that for pure risk mitigation, outcome-based monitoring (tracking the equity curve) is more effective than behavioral monitoring (tracking win rate deviation). CUSUM's value lies not in risk reduction but in behavioral diagnostics: identifying *why* performance has degraded, which informs strategy development and produces compliance-friendly audit trails.

We report three negative results as contributions: BOCPD fails on sparse binary sequences; trade-level DQS achieves zero separation; and CUSUM loses to equity-based monitoring on its primary metric. These results collectively narrow the design space for future agent monitoring systems and suggest that production deployments should combine outcome-based protection (MaxDDStop) with behavioral diagnostics (CUSUM) rather than relying on either alone.

Limitations include restriction to two cryptocurrency markets, grid-generated synthetic strategies, no live deployment validation, a fixed CUSUM threshold ($h = 4.0$), and strategy dependence that inflates reported $p$-values. The ETHUSDT 4h failure and the without-BTCUSDT-1h robustness check (where CUSUM vs. SimpleWR becomes insignificant at $p = 0.179$) establish practical boundaries on CUSUM's applicability.

Future work should extend validation to additional asset classes and timeframes, test on human-developed and ML-trained strategies, explore combined MaxDDStop + CUSUM systems, and most importantly, conduct live deployment studies. The question of whether CUSUM's diagnostic value translates to better long-term strategy management -- even when MaxDDStop handles short-term risk -- remains open and is the most promising direction for this research.

The broader message is that as AI agents assume greater autonomy in financial markets, we need both safety nets and diagnostic tools. MaxDDStop is the safety net; CUSUM is the diagnostic. Neither alone is sufficient. The agent is the process; its trade outcomes are the quality measurements; and a well-designed monitoring system uses multiple control mechanisms, each serving a distinct purpose.

---

## References

- Adams, R. P., & MacKay, D. J. C. (2007). Bayesian Online Changepoint Detection. *arXiv preprint arXiv:0710.3742*.
- Bailey, D. H., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality. *Journal of Portfolio Management*, 40(5), 94--107.
- Gama, J., Zliobaite, I., Bifet, A., Pechenizkiy, M., & Bouchachia, A. (2014). A Survey on Concept Drift Adaptation. *ACM Computing Surveys*, 46(4), 1--37.
- Kelly, J. L. (1956). A New Interpretation of Information Rate. *Bell System Technical Journal*, 35(4), 917--926.
- Kim, J., et al. (2025). ATLAS: Adaptive Trading with LLM AgentS Through Dynamic Prompt Optimization and Multi-Agent Coordination. *arXiv preprint arXiv:2510.15949*.
- Li, Y., Wang, Z., & Huang, W. (2024). FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design. In *Workshop on Financial Large Language Models, ICLR 2024*.
- Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
- Lu, J., Liu, A., Dong, F., Gu, F., Gama, J., & Zhang, G. (2018). Learning Under Concept Drift: A Review. *IEEE Transactions on Knowledge and Data Engineering*, 31(12), 2346--2363.
- Montgomery, D. C. (2012). *Introduction to Statistical Quality Control* (7th ed.). Wiley.
- Page, E. S. (1954). Continuous Inspection Schemes. *Biometrika*, 41(1/2), 100--115.
- Schaul, T., Quan, J., Antonoglou, I., & Silver, D. (2015). Prioritized Experience Replay. *arXiv preprint arXiv:1511.05952*.
- Shefrin, H., & Statman, M. (1985). The Disposition to Sell Winners Too Early and Ride Losers Too Long: Theory and Evidence. *Journal of Finance*, 40(3), 777--790.
- Thorp, E. O. (2006). The Kelly Criterion in Blackjack, Sports Betting and the Stock Market. In *Handbook of Asset and Liability Management* (pp. 385--428). North-Holland.
- Tulving, E. (1972). Episodic and Semantic Memory. In E. Tulving & W. Donaldson (Eds.), *Organization of Memory* (pp. 381--403). Academic Press.
- Woodall, W. H., & Montgomery, D. C. (1999). Research Issues and Ideas in Statistical Process Control. *Journal of Quality Technology*, 31(4), 376--386.
- Xiao, Y., et al. (2025). TradingAgents: Multi-Agents LLM Financial Trading Framework. *arXiv preprint arXiv:2412.20138*.
- Yang, H., Liu, X. Y., Zhong, S., & Walid, A. (2020). Deep Reinforcement Learning for Automated Stock Trading: An Ensemble Strategy. In *Proceedings of the First ACM International Conference on AI in Finance* (pp. 1--8).

---

*Code and data available at: https://github.com/mnemox-ai/tradememory-protocol*

*Preprint -- April 2026*
