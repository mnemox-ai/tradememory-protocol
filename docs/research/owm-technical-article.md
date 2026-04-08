# Outcome-Weighted Memory: A Cognitive Architecture for Trading Agent Recall

**Sean Peng** (Mnemox AI)  
Draft v1.0 -- April 2026

---

## Abstract

We present Outcome-Weighted Memory (OWM), a cognitive memory architecture for AI trading agents that replaces uniform recall with a five-factor multiplicative scoring model grounded in Tulving's memory taxonomy. OWM organizes agent experience into five memory layers -- episodic, semantic, procedural, affective, and prospective -- and retrieves memories using a product of outcome quality, context similarity, recency, confidence, and affective modulation. The architecture requires no training data and functions from the first trade. We describe the mathematical formulation, discuss our implementation as an open-source MCP server with 19 tools and 1293 tests, and report honest preliminary results from a small empirical deployment (n=40 trades, XAUUSD, 3 strategies). OWM is deployed in production and available at [tradememory-protocol](https://github.com/mnemox-ai/tradememory-protocol).

---

## 1. Motivation: The Amnesia Problem in AI Trading Agents

The current generation of LLM-based trading systems suffers from a fundamental limitation: they cannot learn from their own experience. An agent executing trades today has no structured access to the outcomes of trades it executed last week. Each decision is made in a context vacuum -- the agent may have access to market data and a strategy specification, but it has no memory of what happened the last time it encountered similar conditions.

This is not merely a data storage problem. Most trading systems log trades to a database. The issue is **recall** -- the ability to surface the right past experience at the right moment. A traditional trade log returns records filtered by date range or strategy name. It cannot answer the question that matters most at decision time: "What happened the last time I saw this exact market setup?"

Existing approaches to AI agent memory fall short in the financial domain for several reasons. General-purpose memory systems like Mem0 and Zep provide embedding-based retrieval that ignores outcome quality entirely. A memory of a catastrophic -3R loss and a +5R win have equal retrieval priority if their text embeddings are equidistant from the query. Recency-based approaches (the default in most LLM conversation histories) surface whatever happened most recently, regardless of relevance to current conditions.

The financial domain introduces requirements that generic memory architectures were not designed for. First, outcome matters: a memory's value is inseparable from the financial result it produced. Second, context is regime-dependent: a pattern that generated profits in a trending market may be destructive in a ranging market. Third, the agent's own performance state -- its drawdown, confidence, and recent win/loss streak -- should influence which memories surface. A trader in a deep drawdown benefits from recalling past recovery patterns differently than a trader at equity highs.

We formalize these requirements into a coherent architecture that borrows from cognitive science, reinforcement learning, and quantitative finance. The result is a system that works from trade number one (no training phase), produces fully interpretable recall scores, and runs as pure arithmetic without GPU inference.

---

## 2. Related Work

The intersection of memory systems and trading agents has received increasing attention. We position OWM relative to four categories of prior work.

**FinMem (Li et al., 2024)** introduced a tiered memory system for LLM-based financial trading, with working, episodic, and semantic layers inspired by cognitive science. Published at the FinLLM workshop and accumulating significant community interest, FinMem demonstrated that structured memory improves LLM trading decisions over memoryless baselines. However, FinMem's recall mechanism relies on text embedding similarity, treating all memories as equally valuable regardless of outcome. OWM extends this direction by making outcome quality the primary recall signal and adding three additional memory types -- procedural, affective, and prospective -- that FinMem does not address.

**TradingAgents (Xiao et al., 2025)** takes a multi-agent approach to financial trading, modeling analyst, researcher, and trader personas with shared memory. The framework has attracted substantial open-source adoption. Its strength lies in the collaborative architecture, but its memory system is primarily a shared context buffer rather than a structured recall mechanism. OWM's contribution is orthogonal: it provides the recall algorithm that any agent architecture (single or multi-agent) can use to retrieve relevant past experience.

**TradingGPT (Li et al., 2023)** explored LLMs as trading agents with layered memory, employing short-term and long-term memory components. While pioneering in connecting LLM agents to financial decision-making, TradingGPT's memory does not incorporate outcome-weighting or affective modulation.

**Traditional trade journaling tools** -- TraderSync, Edgewonk, Tradervue -- represent decades of practical wisdom about the value of trade review. These tools provide manual logging, tagging, and statistical dashboards. OWM automates the core insight behind trade journaling (systematic review of past decisions improves future decisions, per Odean 1998) while adding outcome-weighted retrieval that no manual journal can provide. A human reviewing a journal applies implicit outcome weighting through their own memory biases; OWM makes this process explicit and mathematically specified.

**Prioritized Experience Replay (Schaul et al., 2015)** from the reinforcement learning literature is the closest algorithmic ancestor. PER demonstrated that weighting experience replay by temporal-difference error magnitude improves learning efficiency in game-playing agents. OWM adapts this principle from TD-error to financial outcome quality, and extends it from a single priority score to a five-factor model that incorporates context, recency, confidence, and affective state.

---

## 3. Architecture: Five Memory Layers

OWM organizes agent memory into five types, following Tulving's (1972, 1985) taxonomy of human memory systems. Each type captures a distinct aspect of trading experience.

**Episodic Memory** stores individual trade events with full context. Each record is a tuple $E = (id, t, C, a, o, r, conf)$ where $C$ is a context vector capturing market regime, volatility, session, spread, and agent state at the time of the trade; $a$ is the action taken (strategy, direction, entry); $o$ is the outcome (exit, PnL, R-multiple, max adverse excursion); and $r$ is a natural-language reflection. This maps directly to the trade journaling practice recommended in behavioral finance. Retrieval strength follows power-law decay: $S(t) = (1 + t/\tau)^{-d}$, chosen over exponential decay because empirical memory research (Wixted & Ebbesen, 1991) shows power-law better models human forgetting -- and because a trade from six months ago in the exact same regime should still be retrievable.

**Semantic Memory** stores accumulated knowledge with Bayesian confidence. A semantic memory $K$ contains a proposition (e.g., "VolBreakout during London session in trending-up regime has positive expectancy"), a Beta-distributed confidence parameter ($\alpha, \beta$), and strict validity conditions. The posterior $\text{confidence} = \alpha / (\alpha + \beta)$ updates incrementally as new episodic evidence arrives. The requirement for explicit validity conditions prevents the aggregation trap where a single averaged statistic obscures regime-dependent behavior.

**Procedural Memory** tracks what the agent actually does, not what it should do. For each strategy, it maintains rolling statistics: actual win rate, average hold duration, lot sizing relative to Kelly optimal, and behavioral bias scores including disposition effect (Shefrin & Statman, 1985) and loss aversion. This layer is continuously recomputed from a sliding window of recent episodic memories.

**Affective Memory** maintains the agent's performance state: confidence level via EWMA of recent outcomes, risk appetite as a function of drawdown ($\text{appetite} = \max(0.1, 1 - (dd/dd_{max})^2)$), and win/loss streak counters. This is not an attempt to simulate emotions but a mathematically grounded risk management mechanism drawing from optimal drawdown control theory (Grossman & Zhou, 1993).

**Prospective Memory** stores conditional future plans: "If regime shifts to ranging and strategy is VolBreakout, reduce confidence threshold." Plans have explicit expiry dates (default 30 days) to prevent rule accumulation. This transforms the agent from purely reactive to anticipatory, mapping to regime-switching models (Hamilton, 1989) and dynamic strategy allocation (Ang & Bekaert, 2002).

---

## 4. Five-Factor Scoring: The Recall Formula

When the agent queries memory, each candidate memory $m$ is scored against the current context $C_{now}$ using:

$$\text{Score}(m, C_{now}) = Q(m) \times \text{Sim}(m, C_{now}) \times \text{Rec}(m) \times \text{Conf}(m) \times \text{Aff}(m)$$

The multiplicative form is a deliberate architectural choice (documented in ADR-001). The key property is **zero-on-any-dimension collapse**: a memory with near-zero outcome quality does not surface regardless of how recent or contextually similar it is. Additive scoring cannot enforce this -- a high recency score would rescue a catastrophic trade. The multiplicative model mirrors Tulving's encoding specificity principle: retrieval depends on the match across multiple independent dimensions simultaneously.

**Factor 1: Outcome Quality** $Q(m)$. For episodic memories with a recorded R-multiple:

$$Q(m) = \sigma\!\left(\frac{k \cdot \text{pnl\_r}(m)}{\sigma_r}\right)$$

where $\sigma$ is the sigmoid function, $k = 2.0$ is a sensitivity parameter, and $\sigma_r = 1.5$ is a normalizing scale. This maps a +3R win to $Q \approx 0.98$ and a -3R loss to $Q \approx 0.02$. Critically, $Q$ is never exactly zero -- losing trades remain retrievable as warnings, which is essential for risk management. For semantic memories without direct outcomes, $Q$ defaults to the Bayesian confidence.

**Factor 2: Context Similarity** $\text{Sim}(m, C_{now})$. A weighted combination of categorical exact-match (regime: 0.25, volatility regime: 0.15, session: 0.10) and numerical Gaussian kernel comparisons (ATR: 0.15/0.10, drawdown: 0.10, price: 0.10, spread: 0.05):

$$\text{Sim} = \frac{\sum_i w_i \cdot s_i}{\sum_i w_i}$$

where $s_i = \mathbb{1}[v_1 = v_2]$ for categorical fields and $s_i = \exp\!\left(-\frac{1}{2}\left(\frac{v_1 - v_2}{h \cdot |v_1|}\right)^2\right)$ for numerical fields with bandwidth $h$. When context data is sparse (missing fields), the similarity defaults to 0.5 rather than 0.0, preventing recall collapse in data-sparse conditions.

**Factor 3: Recency** $\text{Rec}(m)$. Power-law temporal decay:

$$\text{Rec}(m) = \left(1 + \frac{\text{age\_days}}{\tau}\right)^{-d}$$

with $\tau = 30, d = 0.5$ for episodic memories and $\tau = 180, d = 0.3$ for semantic. A 30-day-old episodic memory retains $2^{-0.5} \approx 0.71$ of its recency score; a one-year-old memory retains 0.28. This is substantially gentler than exponential decay, consistent with empirical memory research.

**Factor 4: Confidence at Formation** $\text{Conf}(m)$. Maps the agent's decision-time confidence from $[0, 1]$ to $[0.5, 1.0]$:

$$\text{Conf}(m) = 0.5 + 0.5 \cdot c_m$$

The floor of 0.5 ensures early memories (formed with default confidence) are not discarded, while higher-confidence memories receive a retrieval advantage.

**Factor 5: Affective Modulation** $\text{Aff}(m)$. Bounded to $[0.7, 1.3]$, this factor biases retrieval based on the agent's current performance state. During deep drawdown ($dd > 50\%$), large-loss memories are boosted as warnings ($+0.5$) and large-win memories are boosted as recovery references ($+0.3$). During losing streaks ($\geq 3$ consecutive), winning memories are surfaced ($+0.3$) while additional loss memories are mildly suppressed ($-0.2$). The modulation coefficient $\alpha = 0.3$ keeps the effect bounded. This is the most novel component: it creates state-dependent recall analogous to how human traders' memory access patterns shift with emotional state, but in a controlled and auditable manner.

---

## 5. Empirical Setup

OWM is implemented as a Python MCP (Model Context Protocol) server, deployed and used in production for live trading assistance. The current deployment comprises:

- **19 MCP tools** covering memory storage, recall, strategy performance, trade reflection, strategy validation, context drift monitoring, and decision legitimacy checks.
- **1293 passing tests** across the full codebase, including 60 dedicated strategy validator tests and 11 legitimacy gate tests.
- **Trade data**: 40 closed trades on XAUUSD across 3 strategies (VolBreakout, IntradayMomentum, Pullback), collected from a MetaTrader 5 demo account over approximately 6 weeks.
- **Recall pipeline**: Episodic and semantic memories are scored and ranked using the five-factor formula. Recall events are logged for audit. A context drift monitor (Jaccard-based) flags when recalled memories come from significantly different market conditions.
- **Deflated Sharpe Ratio (DSR)** validation (Bailey & Lopez de Prado, 2014) is integrated to test whether reported strategy performance exceeds what would be expected from multiple testing.

The system runs on SQLite with no external dependencies beyond standard Python. No GPU is required. The entire recall computation is deterministic arithmetic -- no stochastic inference.

---

## 6. Current Results

We state plainly: $n = 40$ is insufficient for rigorous statistical claims. The results below are preliminary observations, not validated findings.

**DSR Validation.** We applied the Deflated Sharpe Ratio test to all three strategies. At $n = 40$, no strategy achieved statistical significance at $p < 0.05$ after adjusting for the number of strategies tested. This is the expected result for a small sample and is itself a validation that the statistical machinery works correctly -- it refuses to certify an edge from insufficient data.

**Qualitative Observations.** The primary measurable benefit so far is pre-trade discipline. When the agent recalls 3-5 past trades in similar conditions before making a decision, the decision context includes explicit references to prior outcomes. In user testing, this recall step prevented at least two planned entries where the recalled memories showed consistent losses in the matching regime. This is anecdotal, not statistical.

**What $n \geq 100$ Would Enable.** With 100+ trades per strategy, we could compute regime-conditional statistics with meaningful confidence intervals, validate whether OWM recall actually improves decision quality versus a recency-only baseline, and test parameter sensitivity of the five factors. We estimate reaching this threshold within 3-4 months of continued demo trading.

**Context Drift Monitor.** The Jaccard-based $\Delta S$ drift detector correctly identified regime transitions in the trade history, flagging recalled memories from trending-up periods when the current regime had shifted to ranging. While not a performance metric, this confirms the context similarity machinery functions as designed.

---

## 7. Future Work

Several directions remain open. **Parameter sensitivity analysis**: systematic evaluation of the five factor weights and their interaction effects, potentially via grid search over historical data once $n > 200$. **Hybrid recall with embeddings**: the architecture supports an optional vector similarity component (pgvector) that would combine embedding-based retrieval with OWM scoring; the current implementation falls back to pure OWM when embeddings are unavailable. **Walk-forward validation**: applying the recall algorithm in a strict walk-forward framework to measure whether outcome-weighted recall genuinely improves out-of-sample decision quality. **Larger empirical study**: expanding beyond single-instrument (XAUUSD) to multi-asset and higher-frequency strategies, with the goal of publishing statistically rigorous results. We welcome collaboration from researchers with access to larger trade datasets.

---

## References

- Ang, A., & Bekaert, G. (2002). International Asset Allocation with Regime Shifts. *Review of Financial Studies*, 15(4), 1137-1187.
- Bailey, D. H., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality. *Journal of Portfolio Management*, 40(5), 94-107.
- Grossman, S. J., & Zhou, Z. (1993). Optimal Investment Strategies for Controlling Drawdowns. *Mathematical Finance*, 3(3), 241-276.
- Hamilton, J. D. (1989). A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle. *Econometrica*, 57(2), 357-384.
- Kelly, J. L. (1956). A New Interpretation of Information Rate. *Bell System Technical Journal*, 35(4), 917-926.
- Li, Y., Wang, Z., & Huang, W. (2024). FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design. In *Workshop on Financial Large Language Models, ICLR 2024*.
- Li, Z., et al. (2023). TradingGPT: Multi-Agent System with Layered Memory and Distinct Characters for Enhanced Financial Trading Performance. *arXiv preprint arXiv:2309.03736*.
- Odean, T. (1998). Are Investors Reluctant to Realize Their Losses? *Journal of Finance*, 53(5), 1775-1798.
- Schaul, T., Quan, J., Antonoglou, I., & Silver, D. (2015). Prioritized Experience Replay. *arXiv preprint arXiv:1511.05952*.
- Shefrin, H., & Statman, M. (1985). The Disposition to Sell Winners Too Early and Ride Losers Too Long: Theory and Evidence. *Journal of Finance*, 40(3), 777-790.
- Tulving, E. (1972). Episodic and Semantic Memory. In E. Tulving & W. Donaldson (Eds.), *Organization of Memory* (pp. 381-403). Academic Press.
- Tulving, E. (1985). Memory and Consciousness. *Canadian Psychology*, 26(1), 1-12.
- Wixted, J. T., & Ebbesen, E. B. (1991). On the Form of Forgetting. *Psychological Science*, 2(6), 409-415.
- Xiao, Y., et al. (2025). TradingAgents: Multi-Agents LLM Financial Trading Framework. *arXiv preprint arXiv:2412.20138*.
