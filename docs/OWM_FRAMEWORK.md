# Outcome-Weighted Memory (OWM): A Cognitive Memory Architecture for AI Trading Agents

**Author:** Sean (Mnemox AI) + AI co-design
**Version:** 1.0.0-draft
**Date:** 2026-03-04
**Status:** Theoretical framework — pending implementation and empirical validation

> This document is the intellectual foundation of TradeMemory's competitive moat.
> It defines a complete, implementable memory theory for AI trading agents,
> grounded in cognitive science, reinforcement learning, and quantitative finance.

---

## Table of Contents

1. [Why L1/L2/L3 Is Fundamentally Flawed](#1-why-l1l2l3-is-fundamentally-flawed)
2. [The OWM Framework — Fully Specified](#2-the-owm-framework--fully-specified)
3. [The Core Innovation: Outcome-Weighted Recall](#3-the-core-innovation-outcome-weighted-recall)
4. [Mathematical Validation](#4-mathematical-validation)
5. [Financial Validation](#5-financial-validation)
6. [Comparison: L1/L2/L3 vs OWM](#6-comparison-l1l2l3-vs-owm)
7. [Implementation Specification](#7-implementation-specification)
8. [Validation Plan Using Real Data](#8-validation-plan-using-real-data)

---

## 1. Why L1/L2/L3 Is Fundamentally Flawed

### 1.1 The Layer Metaphor Is a Data Pipeline, Not a Memory System

The L1/L2/L3 architecture borrows from data engineering (raw → transformed → aggregated), not from how learning actually works. It implies a unidirectional flow:

```
L1 (Raw Trades) → L2 (Patterns) → L3 (Adjustments)
```

This is a **batch ETL pipeline**. It has three fundamental problems:

**Problem 1: No feedback loop.** L3 adjustments do not modify how L1 data is stored or how L2 patterns are discovered. A real memory system has bidirectional influence — what you know changes what you notice, which changes what you remember. A trader who has learned that "Friday NFP causes violent gold reversals" will encode future Friday trades differently. L1/L2/L3 cannot represent this.

**Problem 2: No decay or forgetting.** Every L1 record has equal weight forever. A trade from 2022 when gold was $1,800 and a trade from 2026 when gold is $5,175 sit in the same table with the same retrieval priority. Human traders (and any effective learning system) naturally down-weight stale information. The L1/L2/L3 model has no mechanism for this — you either delete old data (losing information) or keep it all (diluting signal).

**Problem 3: No context-dependent recall.** L2 pattern discovery is a batch process: scan all trades, find statistical patterns, store them. But real trading memory is context-triggered. When a trader sees a specific chart formation during London open with rising yields, they don't search "all patterns" — they recall specific memories that feel similar. The recall path matters more than the storage path.

### 1.2 What L1/L2/L3 Cannot Capture

| Phenomenon | Real Trading | L1/L2/L3 Representation |
|------------|-------------|------------------------|
| "I've seen this exact setup before" | Vivid episodic recall, emotionally tagged | Keyword overlap on `market_context` text field |
| "Breakout strategies work in trending markets" | Semantic knowledge, refined over years | A pattern row in L2 with a confidence number |
| "I always cut winners too early" | Procedural habit, often unconscious | Not representable at all |
| "I'm scared after three consecutive losses" | Affective state affecting all decisions | Not representable at all |
| "If NFP beats expectations, I'll buy the dip" | Prospective intention, conditional plan | Not representable at all |
| "Last month's edge has disappeared" | Regime awareness, time-varying | L2 patterns are static once discovered |

### 1.3 Specific Failure Modes

**Failure Mode 1: Regime Blindness.** L2 discovers "VolBreakout has 45% win rate and PF 1.17." This is a single number covering 2024-2026 — a period where gold went from $2,000 to $5,175. The pattern is regime-blind. It does not know that VB performed differently during the $2,000-$3,000 range vs the $4,000-$5,000 range. Without temporal context in the pattern itself, L3 adjustments are based on averaged-out, potentially misleading statistics.

**Failure Mode 2: Cold Memory.** L3 generates an adjustment like "increase RR from 2.5 to 3.5." This adjustment has no memory of why it was proposed, what market conditions prompted it, or whether those conditions still hold. If the market regime changes, the adjustment persists until a human manually reverts it or another L2 scan overrides it. There is no automatic "this adjustment was proposed during high-volatility conditions and we're now in low-volatility" awareness.

**Failure Mode 3: The Aggregation Trap.** L2 computes aggregate statistics: win rate, profit factor, average PnL. But aggregates destroy the most valuable information — the specific conditions under which a strategy excels or fails. "IM has 94% profitable variants" hides the fact that IM_XAUUSD_BUY_RR3.5_TH0.45 returned +166% while IM_XAUUSD_SELL_RR1.5_TH0.65 returned -12%. The L1/L2/L3 architecture pushes toward aggregation because that's what layers do. OWM pushes toward specific, context-tagged, outcome-weighted memories.

### 1.4 The Deeper Issue: L1/L2/L3 Has No Theory of Learning

The most damning criticism is philosophical. L1/L2/L3 describes data storage and transformation. It does not describe **learning**. Learning requires:

1. **Encoding** — selectively storing information based on what matters (not storing everything equally)
2. **Consolidation** — strengthening useful memories and weakening useless ones over time
3. **Retrieval** — finding the right memory at the right time based on current context
4. **Reconsolidation** — updating existing memories when new evidence arrives
5. **Forgetting** — actively discarding information that is no longer useful

L1/L2/L3 has encoding (store a trade) and a crude form of consolidation (aggregate into patterns). It has no retrieval theory (keyword matching is not a theory), no reconsolidation (patterns are immutable once created), and no forgetting mechanism.

OWM provides all five.

---

## 2. The OWM Framework — Fully Specified

### 2.0 Foundational Principles

OWM is built on three axioms:

**Axiom 1 (Outcome Authority):** The financial outcome of a decision is the ultimate arbiter of memory value. A memory that led to a profitable decision in similar conditions deserves stronger recall than one that did not. This is not the same as "only remember winners" — losing trades in specific conditions are extremely valuable warnings.

**Axiom 2 (Context Is Everything):** A memory's value is not intrinsic — it depends on how similar the current context is to the context in which the memory was formed. A breakout pattern memory formed during a trending market is highly relevant when the current market is trending, and nearly worthless when the market is ranging.

**Axiom 3 (Memories Are Living):** Memories are not static records. They have retrieval strength that changes over time. They get reinforced when similar experiences confirm them and weakened when contradictory evidence appears. They can be merged, split, or retired.

These three axioms directly map to Tulving's memory theory (1972, 1985) and to the Prioritized Experience Replay framework from DeepMind (Schaul et al., 2015), adapted from game-playing to financial decision-making.

### 2.1 Episodic Memory (Event Memory)

#### Cognitive Analogue
Tulving's episodic memory — autonoetic consciousness, "mental time travel" to a specific past experience. A trader remembering "that one trade on March 2nd where VB caught the London breakout for +$1,175."

#### Mathematical Definition

An episodic memory is a tuple:

```
E = (id, t, C, a, o, r, conf, tags)
```

Where:
- `id` : unique identifier (string)
- `t` : timestamp (UTC ISO 8601)
- `C` : context vector (see Section 2.6)
- `a` : action taken = (strategy, direction, entry_price, lot_size)
- `o` : outcome = (exit_price, pnl, pnl_r, hold_duration, max_adverse_excursion)
- `r` : reflection (natural language — agent's own analysis post-trade)
- `conf` : confidence at time of decision, in [0, 1]
- `tags` : set of categorical labels

#### Data Schema (SQLite)

```sql
CREATE TABLE episodic_memory (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    -- Context vector (stored as JSON for flexibility, indexed fields extracted)
    context_json TEXT NOT NULL,
    context_regime TEXT,           -- 'trending_up', 'trending_down', 'ranging', 'volatile'
    context_volatility_regime TEXT, -- 'low', 'normal', 'high', 'extreme'
    context_session TEXT,          -- 'asia', 'london', 'newyork', 'overlap'
    context_atr_d1 REAL,
    context_atr_h1 REAL,
    -- Action
    strategy TEXT NOT NULL,
    direction TEXT NOT NULL,       -- 'long' or 'short'
    entry_price REAL NOT NULL,
    lot_size REAL,
    -- Outcome (NULL if trade still open)
    exit_price REAL,
    pnl REAL,
    pnl_r REAL,                    -- PnL in R-multiples (risk-normalized)
    hold_duration_seconds INTEGER,
    max_adverse_excursion REAL,    -- worst unrealized loss during trade
    -- Meta
    reflection TEXT,
    confidence REAL DEFAULT 0.5,
    tags TEXT,                     -- JSON array
    -- Memory dynamics
    retrieval_strength REAL DEFAULT 1.0,
    retrieval_count INTEGER DEFAULT 0,
    last_retrieved TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_episodic_regime ON episodic_memory(context_regime);
CREATE INDEX idx_episodic_strategy ON episodic_memory(strategy);
CREATE INDEX idx_episodic_timestamp ON episodic_memory(timestamp DESC);
CREATE INDEX idx_episodic_pnl_r ON episodic_memory(pnl_r);
```

#### Write Operation

An episodic memory is created when:
1. A trade is **closed** (has exit price and PnL), OR
2. A significant **non-trade event** occurs (e.g., agent decides NOT to trade — a deliberate inaction that should also be remembered)

The context vector `C` is computed at write time from current market data:

```python
def compute_context(symbol: str, mt5_data: dict) -> dict:
    """Compute context vector from current market state."""
    return {
        "symbol": symbol,
        "price": mt5_data["bid"],
        "atr_d1": mt5_data["atr_d1"],         # ATR(14) on D1
        "atr_h1": mt5_data["atr_h1"],         # ATR(14) on H1
        "atr_m5": mt5_data["atr_m5"],         # ATR(14) on M5
        "spread_points": mt5_data["spread"],
        "hour_utc": datetime.utcnow().hour,
        "day_of_week": datetime.utcnow().weekday(),
        "session": classify_session(datetime.utcnow()),  # asia/london/ny/overlap
        "regime": classify_regime(mt5_data),   # trending_up/down/ranging/volatile
        "volatility_regime": classify_volatility(mt5_data),  # low/normal/high/extreme
        "recent_drawdown_pct": compute_recent_drawdown(mt5_data),
        "consecutive_losses": count_consecutive_losses(),
    }
```

#### Read Operation (Recall)

Episodic memories are recalled using the Outcome-Weighted Recall function (Section 3). The key insight: episodic recall is **cue-dependent**. The current context acts as a cue, and memories whose stored context is similar to the cue are retrieved with higher priority.

#### Decay Function

Retrieval strength decays following a **power law** (matching ACT-R cognitive architecture and empirical memory research):

```
S_retrieval(t) = S_0 * (1 + t/tau)^(-d) * boost(n_retrievals)
```

Where:
- `S_0` = initial strength (1.0 for a new memory)
- `t` = time since memory creation (in days)
- `tau` = time constant (default: 30 days — one month is the natural trading cycle)
- `d` = decay exponent (default: 0.5 — power law, not exponential, per Wixted & Ebbesen 1991)
- `boost(n)` = 1 + 0.1 * ln(1 + n) — each retrieval slightly strengthens the memory (testing effect)

Why power law instead of exponential? Exponential decay (`e^(-t/tau)`) drops too fast — after 3*tau (90 days), a memory would retain only 5% strength. Power law decay is empirically more accurate for human memory and more useful for trading: a trade from 6 months ago in the exact same regime should still be retrievable, just with reduced weight.

#### Financial Grounding

Episodic memory maps to **trade journaling** — the most recommended practice in behavioral finance for improving trading performance. Research by Odean (1998) and Barber & Odean (2000) demonstrates that traders who systematically review past trades make better decisions. OWM automates and enhances this: instead of a human reviewing a journal, the AI agent has structured, searchable, outcome-weighted access to every past decision.

---

### 2.2 Semantic Memory (Knowledge Memory)

#### Cognitive Analogue
Tulving's semantic memory — noetic consciousness, context-free general knowledge. "Breakout strategies work better in trending markets." "Gold correlates with US dollar weakness." "High ATR means wider stops."

#### Mathematical Definition

A semantic memory is a tuple:

```
K = (id, proposition, evidence_set, confidence, domain, validity_conditions)
```

Where:
- `id` : unique identifier
- `proposition` : natural language statement of the knowledge
- `evidence_set` : {E_1, E_2, ..., E_n} — set of episodic memories that support or contradict this knowledge
- `confidence` : Bayesian posterior probability, in [0, 1]
- `domain` : (strategy, symbol, regime) — the conditions under which this knowledge applies
- `validity_conditions` : constraints that must hold for this knowledge to be applicable

#### Confidence as Bayesian Posterior

Semantic confidence is updated using Bayes' theorem. Start with a prior (Beta distribution is the conjugate prior for binomial outcomes):

```
confidence ~ Beta(alpha, beta)
```

Initially: `alpha = 1, beta = 1` (uniform prior — no opinion).

After observing a trade outcome that tests this knowledge:
- If the knowledge predicted correctly: `alpha += w` where `w` = outcome weight (see Section 3)
- If the knowledge predicted incorrectly: `beta += w`

The posterior mean:

```
confidence = alpha / (alpha + beta)
```

The posterior variance (uncertainty):

```
uncertainty = (alpha * beta) / ((alpha + beta)^2 * (alpha + beta + 1))
```

This gives us not just a confidence value but a **confidence in our confidence** — crucial for distinguishing "I'm 70% sure based on 3 trades" from "I'm 70% sure based on 300 trades."

#### Data Schema

```sql
CREATE TABLE semantic_memory (
    id TEXT PRIMARY KEY,
    proposition TEXT NOT NULL,
    -- Bayesian parameters
    alpha REAL NOT NULL DEFAULT 1.0,
    beta REAL NOT NULL DEFAULT 1.0,
    confidence REAL GENERATED ALWAYS AS (alpha / (alpha + beta)) STORED,
    uncertainty REAL GENERATED ALWAYS AS (
        (alpha * beta) / ((alpha + beta) * (alpha + beta) * (alpha + beta + 1.0))
    ) STORED,
    sample_size INTEGER NOT NULL DEFAULT 0,
    -- Domain applicability
    strategy TEXT,
    symbol TEXT,
    regime TEXT,                    -- NULL = applies to all regimes
    volatility_regime TEXT,         -- NULL = applies to all vol regimes
    -- Validity
    validity_conditions TEXT,       -- JSON: conditions under which this holds
    last_confirmed TEXT,            -- last episodic memory that confirmed this
    last_contradicted TEXT,         -- last episodic memory that contradicted this
    -- Meta
    source TEXT NOT NULL,           -- 'induced' (from episodic) or 'seeded' (manual)
    retrieval_strength REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

#### Write Operation

Semantic memories are created in two ways:

1. **Induction from episodic memories:** After accumulating N (default: 10) episodic memories with a shared pattern, a semantic memory is proposed. Example: 10 episodic memories of VolBreakout during London session, 7 profitable, 3 not → induce "VolBreakout during London session has ~70% success rate" with alpha=8, beta=4 (7+1 successes, 3+1 failures, adding prior).

2. **Seeding by user:** A trader can inject prior knowledge: "Gold is inversely correlated with USD." This starts with alpha=2, beta=1 (mild prior belief) and gets updated by evidence.

**Critical constraint:** A semantic memory MUST have `validity_conditions`. "VolBreakout works" is not allowed. "VolBreakout works during trending-up regime with ATR(D1) > $100" is allowed. This prevents the aggregation trap of L2.

#### Read Operation

Semantic memories are retrieved when the current context matches their `domain` and `validity_conditions`. Confidence acts as a natural priority: high-confidence knowledge is recalled first. But uncertainty also matters — the agent should preferentially test uncertain knowledge to reduce uncertainty (exploration vs exploitation).

#### Decay Function

Semantic memories decay much slower than episodic memories (knowledge persists longer than specific events):

```
S_semantic(t) = S_0 * (1 + t/tau_s)^(-d_s) * regime_match_factor
```

Where:
- `tau_s` = 180 days (6 months — knowledge should be stable)
- `d_s` = 0.3 (slower decay than episodic)
- `regime_match_factor` = 1.0 if current regime matches the memory's domain, 0.3 if not

The `regime_match_factor` is the key innovation: semantic knowledge formed in a bull market rapidly loses retrieval strength when the market transitions to a bear market, even if the raw confidence is high. This prevents the agent from rigidly applying bull-market knowledge in a regime change.

#### Financial Grounding

Semantic memory maps to **statistical edge** — the accumulated knowledge of what works and what doesn't. In quantitative finance, this is equivalent to a strategy's expected edge, but with crucial additions: domain restrictions (when does the edge exist?) and Bayesian uncertainty (how confident are we?). This directly addresses the problem identified by Marcos Lopez de Prado (2018) in "Advances in Financial Machine Learning" — that backtested edges are often overfit and lack proper out-of-sample validation. The Bayesian framework naturally handles this by starting with wide uncertainty and narrowing it only with genuine confirming evidence.

---

### 2.3 Procedural Memory (Habit Memory)

#### Cognitive Analogue
Tulving/Squire's procedural memory — anoetic consciousness, unconscious skills and habits. A trader who "always" places stop-losses 1.5 ATR away, or who "always" takes partial profits at 1R, or who "always" hesitates before shorting.

#### Mathematical Definition

A procedural memory tracks what the agent **actually does repeatedly**, not what it's supposed to do:

```
P = (id, behavior_pattern, frequency, context_distribution, outcome_distribution, drift_detector)
```

Where:
- `behavior_pattern` : description of the repeated behavior
- `frequency` : how often this behavior occurs (count and rate)
- `context_distribution` : in what contexts this behavior appears
- `outcome_distribution` : what outcomes result from this behavior
- `drift_detector` : detects if this behavior is changing over time

This is where OWM fundamentally differs from L1/L2/L3. L1/L2/L3 cannot represent "what the agent actually does" because it only stores individual trades (L1) and aggregate patterns (L2). Procedural memory tracks **behavioral tendencies** — the difference between the strategy's theoretical behavior and the agent's actual behavior.

#### Key Procedural Metrics

For each strategy the agent runs, procedural memory tracks:

```python
@dataclass
class ProceduralRecord:
    strategy: str
    symbol: str
    # What the agent actually does (rolling window, last N trades)
    actual_win_rate: float           # empirical
    actual_avg_pnl_r: float          # in R-multiples
    actual_avg_hold_duration: float  # seconds
    actual_entry_timing_bias: float  # early (-1) to late (+1) relative to signal
    actual_exit_timing_bias: float   # early (-1) to late (+1) relative to target
    # Position sizing behavior
    actual_avg_lot_fraction: float   # actual lots / Kelly-optimal lots
    actual_lot_variance: float       # consistency of sizing
    # Behavioral biases detected
    disposition_effect_score: float  # tendency to cut winners early / hold losers
    loss_aversion_score: float       # asymmetry in behavior after wins vs losses
    recency_bias_score: float        # over-weighting of recent outcomes
    # Stability
    behavior_stability: float        # 0 (erratic) to 1 (consistent)
    drift_detected: bool             # is behavior changing significantly?
```

#### Data Schema

```sql
CREATE TABLE procedural_memory (
    id TEXT PRIMARY KEY,
    strategy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    -- Rolling behavioral statistics
    window_size INTEGER NOT NULL DEFAULT 50,    -- trades in window
    actual_win_rate REAL,
    actual_avg_pnl_r REAL,
    actual_avg_hold_seconds REAL,
    actual_lot_fraction_vs_kelly REAL,
    -- Bias detection
    disposition_effect REAL DEFAULT 0.0,
    loss_aversion REAL DEFAULT 0.0,
    recency_bias REAL DEFAULT 0.0,
    behavior_stability REAL DEFAULT 0.5,
    -- Optimal benchmarks (from semantic memory / theory)
    kelly_fraction REAL,
    expected_win_rate REAL,
    expected_avg_pnl_r REAL,
    -- Drift detection
    drift_detected INTEGER DEFAULT 0,
    drift_direction TEXT,           -- 'improving', 'degrading', 'shifting'
    drift_magnitude REAL DEFAULT 0.0,
    -- Time
    last_updated TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

#### Write Operation

Procedural memory is updated after every closed trade. It is a **rolling computation**, not a one-time store:

```python
def update_procedural(strategy: str, symbol: str, new_trade: EpisodicMemory):
    """Update procedural memory with latest trade."""
    recent = get_recent_episodic(strategy, symbol, limit=WINDOW_SIZE)

    # Compute actual statistics
    pnls_r = [e.pnl_r for e in recent if e.pnl_r is not None]
    wins = [p for p in pnls_r if p > 0]

    record = get_or_create_procedural(strategy, symbol)
    record.actual_win_rate = len(wins) / len(pnls_r) if pnls_r else 0
    record.actual_avg_pnl_r = mean(pnls_r) if pnls_r else 0

    # Disposition effect: compare hold duration of winners vs losers
    winner_durations = [e.hold_duration for e in recent if e.pnl_r and e.pnl_r > 0]
    loser_durations = [e.hold_duration for e in recent if e.pnl_r and e.pnl_r <= 0]
    if winner_durations and loser_durations:
        record.disposition_effect = (
            mean(loser_durations) / mean(winner_durations) - 1.0
        )
        # Positive = holding losers longer than winners (classic disposition effect)

    # Kelly fraction comparison
    if record.expected_win_rate and record.expected_avg_pnl_r:
        kelly_f = compute_kelly(record.expected_win_rate, record.expected_avg_pnl_r)
        if kelly_f > 0:
            actual_lots = [e.lot_size for e in recent]
            # This requires account equity to compute fraction — simplified
            record.actual_lot_fraction_vs_kelly = mean(actual_lots) / kelly_f

    # Drift detection (CUSUM or Page-Hinkley test)
    record.drift_detected = detect_drift(pnls_r)

    save_procedural(record)
```

#### Decay Function

Procedural memory does not decay in the traditional sense — it is **continuously recomputed** from the rolling window. However, the window itself implements implicit decay: only the last N trades contribute. The window size adapts:

```
N_window = max(20, min(100, round(50 * (1 + behavior_stability))))
```

Stable behavior → larger window (more data, smoother estimates). Erratic behavior → smaller window (more responsive to recent changes).

#### Financial Grounding

Procedural memory maps to **position sizing and execution quality** — the practical mechanics of trading that separate a theoretical edge from realized profits. The connection to the Kelly Criterion is direct:

The Kelly optimal fraction is:

```
f* = (p * b - q) / b
```

Where `p` = win probability, `q` = 1 - p, `b` = win/loss ratio. This is the theoretically optimal bet size. Procedural memory tracks how close the agent's actual sizing is to Kelly optimal, and whether this ratio drifts over time.

The disposition effect metric connects to the seminal work of Shefrin & Statman (1985), who documented that investors systematically sell winners too soon and hold losers too long. By tracking this automatically, OWM enables the agent to detect and correct its own behavioral biases.

---

### 2.4 Affective Memory (Confidence/State Memory)

#### Cognitive Analogue
The emotional and confidence state that colors all other memory operations. Not literal emotions (an AI doesn't feel fear), but the computational analogue: a **confidence multiplier** that reflects recent performance and adjusts risk appetite, memory retrieval bias, and decision thresholds.

#### Mathematical Definition

Affective state is a real-time vector, not a stored record:

```
A(t) = (confidence_level, risk_appetite, momentum_bias, drawdown_state)
```

Where:
- `confidence_level` : in [0, 1] — how "confident" the agent is in its overall performance
- `risk_appetite` : in [0, 1] — willingness to take risk (modulates position sizing)
- `momentum_bias` : in [-1, 1] — tendency to follow recent direction (-1 = contrarian, +1 = momentum)
- `drawdown_state` : in [0, 1] — 0 = at equity high, 1 = at max drawdown threshold

#### Confidence Level Dynamics

Confidence updates via an exponentially-weighted moving average of recent risk-adjusted outcomes:

```
confidence(t) = lambda * confidence(t-1) + (1 - lambda) * signal(latest_trade)
```

Where:
- `lambda` = 0.9 (slow-moving — confidence doesn't jump on a single trade)
- `signal(trade)` = sigmoid(pnl_r / expected_pnl_r) — maps R-multiple outcome to [0, 1]

After a +3R winner: signal ≈ 0.95 → confidence nudges up
After a -1R loser: signal ≈ 0.27 → confidence nudges down
After a 0R scratch: signal ≈ 0.50 → confidence stays neutral

#### Risk Appetite as Function of Drawdown

Risk appetite is NOT a sentiment — it is a mathematically justified response to drawdown, grounded in the theory of optimal drawdown control (Grossman & Zhou, 1993):

```
risk_appetite(t) = max(0.1, 1.0 - (current_drawdown / max_acceptable_drawdown)^2)
```

Where:
- `current_drawdown` = (peak_equity - current_equity) / peak_equity
- `max_acceptable_drawdown` = configurable (default: 0.20 = 20%)

Properties:
- At equity high (DD = 0%): risk_appetite = 1.0 (full risk)
- At 10% DD: risk_appetite = 1.0 - (0.10/0.20)^2 = 0.75
- At 15% DD: risk_appetite = 1.0 - (0.75)^2 = 0.4375
- At 20% DD: risk_appetite = max(0.1, 1.0 - 1.0) = 0.1 (minimum risk)

This creates a **concave** risk reduction — the agent reduces risk slowly at first, then aggressively as drawdown deepens. This is consistent with the practical trading wisdom of "fractional Kelly" (betting less than the Kelly optimal amount to reduce ruin probability) and with the academic finding that geometric growth is maximized by reducing position size during drawdowns (Vince, 1990).

#### Drawdown-Aware Memory Retrieval

Here is where affective memory interacts with the recall system. During drawdowns, memory retrieval is biased:

```
retrieval_bias(memory) = {
    if memory.pnl_r > 0 and drawdown_state > 0.5:
        boost = 1.3   # Surface winning memories during deep drawdown (stabilize)
    elif memory.pnl_r < -2 and drawdown_state > 0.3:
        boost = 1.5   # Surface large-loss memories as warnings (prevent compounding)
    else:
        boost = 1.0   # Normal retrieval
}
```

This models the empirical finding in behavioral finance that losses loom larger than gains (Kahneman & Tversky, 1979). But instead of treating this as a bias to correct, OWM uses it constructively: during drawdowns, the agent should indeed pay more attention to memories of past losses (as warnings) and past recoveries (as stabilizers).

#### Data Schema

```sql
CREATE TABLE affective_state (
    id TEXT PRIMARY KEY DEFAULT 'current',
    confidence_level REAL NOT NULL DEFAULT 0.5,
    risk_appetite REAL NOT NULL DEFAULT 1.0,
    momentum_bias REAL NOT NULL DEFAULT 0.0,
    -- Drawdown tracking
    peak_equity REAL NOT NULL,
    current_equity REAL NOT NULL,
    current_drawdown_pct REAL GENERATED ALWAYS AS (
        CASE WHEN peak_equity > 0
        THEN (peak_equity - current_equity) / peak_equity
        ELSE 0.0 END
    ) STORED,
    drawdown_state REAL NOT NULL DEFAULT 0.0,
    max_acceptable_drawdown REAL NOT NULL DEFAULT 0.20,
    -- Streak tracking
    consecutive_wins INTEGER NOT NULL DEFAULT 0,
    consecutive_losses INTEGER NOT NULL DEFAULT 0,
    -- History (for analysis)
    last_updated TEXT NOT NULL,
    history_json TEXT DEFAULT '[]'  -- Array of {timestamp, confidence, risk_appetite, equity}
);
```

#### Write Operation

Affective state is updated after every trade close and periodically (every hour) even without trades:

```python
def update_affective(trade: Optional[EpisodicMemory] = None, equity: float = None):
    state = load_affective_state()

    if trade:
        # Update confidence via EWMA
        signal = sigmoid(trade.pnl_r / expected_pnl_r_for_strategy(trade.strategy))
        state.confidence_level = 0.9 * state.confidence_level + 0.1 * signal

        # Update streaks
        if trade.pnl_r > 0:
            state.consecutive_wins += 1
            state.consecutive_losses = 0
        else:
            state.consecutive_losses += 1
            state.consecutive_wins = 0

    if equity:
        state.current_equity = equity
        if equity > state.peak_equity:
            state.peak_equity = equity

        dd_pct = (state.peak_equity - equity) / state.peak_equity
        state.risk_appetite = max(0.1, 1.0 - (dd_pct / state.max_acceptable_drawdown) ** 2)
        state.drawdown_state = min(1.0, dd_pct / state.max_acceptable_drawdown)

    save_affective_state(state)
```

#### Decay Function

Affective state does not decay — it is continuously recomputed. But `confidence_level` has inherent momentum via the EWMA lambda, which means it takes approximately `1/(1-lambda)` = 10 trades to substantially shift confidence.

#### Financial Grounding

Affective memory maps to **risk management and drawdown theory**. The mathematical framework draws from:

- **Optimal Growth Theory** (Kelly, 1956): Position sizing should reflect edge confidence
- **Drawdown Constraints** (Grossman & Zhou, 1993): Optimal policy under maximum drawdown constraint is to reduce exposure as DD increases
- **Behavioral Finance** (Kahneman & Tversky, 1979): Loss aversion is ~2x — the affective state formalizes this asymmetry
- **Fractional Kelly** (Thorp, 2006): Practical trading uses f*/2 or f*/4 to reduce variance, which maps directly to risk_appetite < 1.0

---

### 2.5 Prospective Memory (Intent Memory)

#### Cognitive Analogue
The ability to remember to do something in the future when a specific condition is met. "If NFP comes in above 200K on Friday, I will buy the dip on gold." "If VB hasn't triggered by Wednesday, increase the breakout buffer."

#### Mathematical Definition

A prospective memory is a conditional plan:

```
F = (id, trigger_condition, planned_action, expiry, priority, source_memories)
```

Where:
- `trigger_condition` : a computable predicate on the context vector C(t)
- `planned_action` : what to do when triggered
- `expiry` : when this plan becomes invalid (time-based or condition-based)
- `priority` : how important this plan is relative to others
- `source_memories` : which episodic/semantic memories motivated this plan

#### Why This Matters for Trading Agents

Without prospective memory, an AI trading agent is purely reactive — it responds to the current moment without any forward planning. But effective trading requires anticipation:

- "If the Fed raises rates next week, my current long gold position is at risk — set a tighter stop"
- "The last three VolBreakout signals in this regime were false breakouts — wait for confirmation before entering the next one"
- "I'm in drawdown — reduce lot size on the next trade regardless of signal strength"

Prospective memory turns the agent from **reactive** to **anticipatory**.

#### Data Schema

```sql
CREATE TABLE prospective_memory (
    id TEXT PRIMARY KEY,
    -- Trigger
    trigger_type TEXT NOT NULL,       -- 'market_condition', 'time', 'event', 'state'
    trigger_condition TEXT NOT NULL,   -- JSON: computable condition
    -- Action
    planned_action TEXT NOT NULL,     -- JSON: what to do
    action_type TEXT NOT NULL,        -- 'adjust_param', 'skip_trade', 'force_exit', 'alert'
    -- Lifecycle
    status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'triggered', 'expired', 'cancelled'
    priority REAL NOT NULL DEFAULT 0.5,
    expiry TEXT,                      -- ISO timestamp or NULL (no expiry)
    -- Provenance
    source_episodic_ids TEXT,        -- JSON array of episodic memory IDs
    source_semantic_ids TEXT,        -- JSON array of semantic memory IDs
    reasoning TEXT NOT NULL,          -- Why this plan was formed
    -- Outcome tracking (after trigger)
    triggered_at TEXT,
    outcome_pnl_r REAL,             -- Did following this plan help?
    outcome_reflection TEXT,
    -- Meta
    created_at TEXT NOT NULL
);

CREATE INDEX idx_prospective_status ON prospective_memory(status);
CREATE INDEX idx_prospective_trigger ON prospective_memory(trigger_type);
```

#### Write Operation

Prospective memories are created:

1. **After a reflection** — The agent analyzes recent trades and forms a plan: "The last 3 IM trades during low-volatility regime lost money → create prospective: IF regime=low_vol AND strategy=IM THEN skip_trade"

2. **From semantic knowledge** — A semantic memory with high confidence generates a standing plan: "VolBreakout works in trending markets → IF regime=trending AND VB_signal THEN confidence_boost=0.2"

3. **From affective state** — Drawdown triggers defensive plans: "Drawdown > 15% → IF any_signal THEN lot_size *= 0.5"

```python
def create_prospective_from_reflection(reflection_result: dict):
    """Create a prospective memory from post-trade reflection."""
    if reflection_result.get("pattern_detected"):
        pattern = reflection_result["pattern_detected"]

        return ProspectiveMemory(
            trigger_condition={
                "regime": pattern["regime"],
                "strategy": pattern["strategy"],
                "type": "market_condition"
            },
            planned_action={
                "type": pattern["recommended_action"],
                "magnitude": pattern["suggested_magnitude"]
            },
            priority=pattern["confidence"],
            expiry=datetime.utcnow() + timedelta(days=30),  # Plans expire
            source_episodic_ids=pattern["supporting_trade_ids"],
            reasoning=pattern["explanation"]
        )
```

#### Trigger Evaluation

Every tick (or at each decision point), active prospective memories are evaluated:

```python
def evaluate_prospective_memories(current_context: dict) -> List[ProspectiveAction]:
    """Check all active prospective memories against current context."""
    active = query_prospective(status='active')
    actions = []

    for pm in active:
        # Check expiry
        if pm.expiry and datetime.utcnow() > pm.expiry:
            update_status(pm.id, 'expired')
            continue

        # Evaluate trigger condition
        if matches_trigger(pm.trigger_condition, current_context):
            actions.append(ProspectiveAction(
                memory_id=pm.id,
                action=pm.planned_action,
                priority=pm.priority,
                reasoning=pm.reasoning
            ))

    return sorted(actions, key=lambda a: a.priority, reverse=True)
```

#### Decay and Expiry

Prospective memories have explicit expiry (default: 30 days). After triggering, they are retained for outcome tracking but moved to 'triggered' status. This prevents plan accumulation — a common failure mode where a system accumulates so many conditional rules that they conflict.

#### Financial Grounding

Prospective memory maps to **regime switching models** and **conditional order management** in quantitative finance. The mathematical underpinning draws from:

- **Hidden Markov Models** for regime detection (Hamilton, 1989): The trigger conditions in prospective memory are essentially HMM state transitions expressed as computable predicates
- **Stop-loss and take-profit orders**: These are the simplest form of prospective memory — "if price reaches X, do Y"
- **Dynamic Strategy Allocation** (Ang & Bekaert, 2002): The idea that portfolio weights should change with regime is exactly what prospective memory implements at the strategy level

---

### 2.6 The Context Vector — Shared Language Across Memory Types

All five memory types reference a **context vector** `C(t)` that describes the market state at time `t`. This is the shared language that enables cross-memory recall:

```python
@dataclass
class ContextVector:
    """Market context at a point in time."""
    # Price
    symbol: str
    price: float

    # Volatility (multi-timeframe)
    atr_d1: float          # ATR(14) on D1 in dollars
    atr_h1: float          # ATR(14) on H1 in dollars
    atr_m5: float          # ATR(14) on M5 in dollars
    atr_ratio_h1_d1: float # H1/D1 ratio (intraday vol relative to daily)

    # Regime classification
    regime: str            # 'trending_up', 'trending_down', 'ranging', 'volatile'
    volatility_regime: str # 'low', 'normal', 'high', 'extreme'

    # Session
    session: str           # 'asia', 'london', 'newyork', 'overlap'
    hour_utc: int
    day_of_week: int       # 0=Mon, 4=Fri

    # Spread
    spread_points: float
    spread_as_atr_pct: float  # spread / ATR(M5) — normalized spread cost

    # Agent state (from affective memory)
    drawdown_pct: float
    consecutive_losses: int
    confidence: float
```

**Context Similarity** is computed as a weighted combination of categorical and numerical matches:

```python
def context_similarity(C1: ContextVector, C2: ContextVector) -> float:
    """Compute similarity between two context vectors. Returns [0, 1]."""
    score = 0.0
    total_weight = 0.0

    # Categorical matches (exact)
    categorical = [
        ('regime', 0.25),
        ('volatility_regime', 0.15),
        ('session', 0.10),
    ]
    for field, weight in categorical:
        total_weight += weight
        if getattr(C1, field) == getattr(C2, field):
            score += weight

    # Numerical similarity (Gaussian kernel)
    numerical = [
        ('atr_d1', 0.15, 0.3),   # (field, weight, bandwidth as fraction)
        ('atr_h1', 0.10, 0.3),
        ('spread_as_atr_pct', 0.05, 0.5),
        ('drawdown_pct', 0.10, 0.1),
        ('price', 0.10, 0.2),     # price level matters for gold
    ]
    for field, weight, bandwidth in numerical:
        total_weight += weight
        v1 = getattr(C1, field)
        v2 = getattr(C2, field)
        if v1 is not None and v2 is not None and v1 != 0:
            # Gaussian kernel: exp(-0.5 * ((v1-v2)/(bandwidth*v1))^2)
            ratio = (v1 - v2) / (bandwidth * abs(v1))
            similarity = math.exp(-0.5 * ratio * ratio)
            score += weight * similarity

    return score / total_weight if total_weight > 0 else 0.0
```

The weights are configurable and themselves can be learned (a meta-learning problem for future work). The Gaussian kernel for numerical fields ensures that "close" values score near 1.0 while "far" values score near 0.0, with the `bandwidth` parameter controlling how "close" needs to be.

---

## 3. The Core Innovation: Outcome-Weighted Recall

### 3.1 The Problem with Uniform Recall

Current AI memory systems (Mem0, Zep, LangChain Memory) use either:
1. **Recency-based recall** — return the most recent memories
2. **Embedding similarity** — return memories whose text embedding is closest to the query
3. **Keyword matching** — return memories containing the same keywords (TradeMemory's current approach)

None of these are appropriate for financial decision-making because they ignore the most important signal: **did this memory lead to a good outcome?**

An agent that recalls "the last time I saw this pattern, I bought and lost 3R" should weight that memory very differently than "the last time I saw this pattern, I bought and made 5R" — even if both memories have identical context similarity scores.

### 3.2 The OWM Recall Formula

When an agent faces a decision and queries its memory, the **recall score** for each candidate memory `m` given current context `C_now` is:

```
Score(m, C_now) = Q(m) * Sim(m, C_now) * Rec(m) * Conf(m) * Aff(m)
```

Where:

#### Q(m) — Outcome Quality

```
Q(m) = sigmoid(k * pnl_r(m) / sigma_r)
```

- `pnl_r(m)` = the R-multiple outcome of the trade associated with memory `m`
- `sigma_r` = rolling standard deviation of R-multiples (normalizes across volatility regimes)
- `k` = sensitivity parameter (default: 2.0)
- `sigmoid(x) = 1 / (1 + e^(-x))`

Properties:
- A +3R winner with sigma_r = 1.5: Q = sigmoid(2 * 3/1.5) = sigmoid(4) = 0.982
- A +0.5R winner with sigma_r = 1.5: Q = sigmoid(2 * 0.5/1.5) = sigmoid(0.67) = 0.661
- A -1R loser: Q = sigmoid(2 * (-1)/1.5) = sigmoid(-1.33) = 0.209
- A -3R loser: Q = sigmoid(2 * (-3)/1.5) = sigmoid(-4) = 0.018

**Important:** Q(m) is in (0, 1), not {0, 1}. Losing trades still have nonzero recall scores — they are recalled as **warnings**. The sigmoid ensures extremely bad outcomes are still retrievable (Q never reaches exactly 0), which is crucial for risk management.

**For memories without direct outcomes** (semantic, prospective):
- Semantic: Q(K) = K.confidence (the Bayesian posterior)
- Prospective: Q(F) = F.priority * mean(Q(source_memories))

#### Sim(m, C_now) — Context Similarity

```
Sim(m, C_now) = context_similarity(m.context, C_now)
```

As defined in Section 2.6. Returns [0, 1].

#### Rec(m) — Recency

```
Rec(m) = (1 + age_days / tau)^(-d)
```

Following the power-law decay from Section 2.1:
- `age_days` = (now - m.timestamp).days
- `tau` = 30 (for episodic), 180 (for semantic), N/A (for procedural/affective)
- `d` = 0.5 (episodic), 0.3 (semantic)

Properties:
- 1 day old: Rec = (1 + 1/30)^(-0.5) = 0.983
- 7 days old: Rec = (1 + 7/30)^(-0.5) = 0.893
- 30 days old: Rec = 2^(-0.5) = 0.707
- 90 days old: Rec = 4^(-0.5) = 0.500
- 365 days old: Rec = 13.2^(-0.5) = 0.275

Note: Power law decay is much gentler than exponential. A 1-year-old memory retains 27.5% of its recency score, compared to ~0% under exponential decay with tau=30. This is intentional — old memories in the same regime should still be recallable.

#### Conf(m) — Confidence at Formation

```
Conf(m) = 0.5 + 0.5 * m.confidence
```

This maps the agent's confidence at the time of memory formation from [0, 1] to [0.5, 1.0]. The floor of 0.5 ensures that low-confidence memories are not completely suppressed — they might still contain useful information.

Rationale: Memories formed when the agent was confident represent higher-quality decision-making. But the floor prevents the degenerate case where all early memories (formed with default confidence 0.5) are ignored.

#### Aff(m) — Affective Modulation

```
Aff(m) = 1.0 + alpha * relevance_to_current_state(m, A(t))
```

Where `alpha` = 0.3 (mild modulation) and:

```python
def relevance_to_current_state(m, affective_state):
    """How relevant is this memory given current affective state?"""
    if affective_state.drawdown_state > 0.5:
        # In significant drawdown
        if m.pnl_r is not None and m.pnl_r < -1.5:
            return 0.5   # Boost large-loss memories (warnings)
        elif m.pnl_r is not None and m.pnl_r > 2.0:
            return 0.3   # Boost large-win memories (confidence restoration)
        else:
            return 0.0
    elif affective_state.consecutive_losses >= 3:
        # Losing streak
        if m.pnl_r is not None and m.pnl_r > 0:
            return 0.3   # Surface winners to counter recency bias
        else:
            return -0.2  # Slightly suppress additional loss memories
    else:
        return 0.0  # Neutral state — no affective modulation
```

This is the most novel component. It creates **state-dependent recall**, mirroring how human traders' memory access patterns change based on their emotional state — but in a controlled, mathematically bounded way.

### 3.3 Complete Recall Algorithm

```python
def outcome_weighted_recall(
    query_context: ContextVector,
    memory_types: List[str] = ['episodic', 'semantic'],
    strategy_filter: Optional[str] = None,
    symbol_filter: Optional[str] = None,
    limit: int = 10,
) -> List[ScoredMemory]:
    """
    The core OWM recall function.

    Returns memories ranked by Score(m, C_now) = Q * Sim * Rec * Conf * Aff.
    """
    affective = load_affective_state()
    candidates = []

    for mem_type in memory_types:
        if mem_type == 'episodic':
            raw = query_episodic(
                symbol=symbol_filter,
                strategy=strategy_filter,
                limit=limit * 5,  # Over-fetch, then re-rank
            )
        elif mem_type == 'semantic':
            raw = query_semantic(
                symbol=symbol_filter,
                strategy=strategy_filter,
                regime=query_context.regime,
                limit=limit * 3,
            )
        elif mem_type == 'prospective':
            raw = query_prospective(status='active')
        else:
            continue

        for m in raw:
            # Compute each component
            q = compute_outcome_quality(m)
            sim = context_similarity(m.context, query_context)
            rec = compute_recency(m, mem_type)
            conf = 0.5 + 0.5 * getattr(m, 'confidence', 0.5)
            aff = 1.0 + 0.3 * relevance_to_current_state(m, affective)

            score = q * sim * rec * conf * aff

            candidates.append(ScoredMemory(
                memory=m,
                score=score,
                components={'Q': q, 'Sim': sim, 'Rec': rec, 'Conf': conf, 'Aff': aff},
                memory_type=mem_type,
            ))

    # Sort by score, return top-k
    candidates.sort(key=lambda x: x.score, reverse=True)
    return candidates[:limit]
```

### 3.4 Connection to Kelly Criterion

The Kelly Criterion tells us the optimal fraction of capital to risk:

```
f* = p/a - q/b
```

Where `p` = P(win), `q` = P(loss) = 1-p, `a` = loss amount, `b` = win amount.

In OWM, the Kelly inputs come from memory:

```python
def kelly_from_memory(
    strategy: str,
    symbol: str,
    current_context: ContextVector,
) -> float:
    """Compute Kelly fraction using outcome-weighted memory."""

    # Recall relevant episodic memories
    memories = outcome_weighted_recall(
        query_context=current_context,
        memory_types=['episodic'],
        strategy_filter=strategy,
        symbol_filter=symbol,
        limit=50,
    )

    if len(memories) < 10:
        return 0.0  # Insufficient data — don't bet

    # Weight each memory's outcome by its recall score
    total_weight = sum(m.score for m in memories)

    weighted_wins = sum(
        m.score * m.memory.pnl_r
        for m in memories if m.memory.pnl_r and m.memory.pnl_r > 0
    )
    weighted_losses = sum(
        m.score * abs(m.memory.pnl_r)
        for m in memories if m.memory.pnl_r and m.memory.pnl_r <= 0
    )

    win_count = sum(m.score for m in memories if m.memory.pnl_r and m.memory.pnl_r > 0)
    loss_count = sum(m.score for m in memories if m.memory.pnl_r and m.memory.pnl_r <= 0)

    if loss_count == 0 or win_count == 0:
        return 0.0  # Can't compute Kelly without both wins and losses

    p = win_count / total_weight
    q = 1 - p
    b = weighted_wins / win_count      # Average weighted win
    a = weighted_losses / loss_count   # Average weighted loss

    kelly_f = p / a - q / b

    # Apply fractional Kelly and affective modulation
    affective = load_affective_state()
    fractional = 0.25  # Quarter Kelly for safety (Thorp recommendation)

    return max(0.0, kelly_f * fractional * affective.risk_appetite)
```

The key innovation: this is not the standard Kelly computation over all historical trades. It is Kelly computed over **outcome-weighted, context-similar, recency-adjusted** memories. The result is a Kelly fraction that adapts to the current market regime without explicit regime detection — the memory system implicitly filters for regime-relevant data.

### 3.5 Bayesian Updating of Semantic Knowledge

When a new episodic memory is formed, it may confirm or contradict existing semantic knowledge. The update rule:

```python
def bayesian_update_semantic(
    episodic: EpisodicMemory,
    semantic: SemanticMemory,
) -> None:
    """Update semantic knowledge based on new episodic evidence."""

    # Check if this episodic memory is relevant to this semantic knowledge
    if not domain_matches(episodic, semantic):
        return

    # Determine if the outcome confirms or contradicts the proposition
    confirmed = evaluate_proposition(semantic.proposition, episodic)

    # Weight the update by outcome magnitude (larger outcomes = stronger evidence)
    weight = min(2.0, abs(episodic.pnl_r) if episodic.pnl_r else 0.5)

    if confirmed:
        semantic.alpha += weight
    else:
        semantic.beta += weight

    semantic.sample_size += 1
    semantic.updated_at = datetime.utcnow().isoformat()

    if confirmed:
        semantic.last_confirmed = episodic.id
    else:
        semantic.last_contradicted = episodic.id

    save_semantic(semantic)
```

Properties of this update:
- **Outcome-weighted evidence**: A trade that confirms "VB works in trending markets" with a +5R result updates more strongly than one with +0.5R. This is principled — stronger evidence from larger outcomes.
- **Symmetric updates**: Both confirmations and contradictions are weighted by outcome magnitude. A -3R contradiction is strong evidence against the proposition.
- **Natural convergence**: The Beta distribution posterior converges as sample_size grows. With 50+ data points, the posterior is tight and resistant to single-trade perturbation.
- **Prior sensitivity**: With few trades, the prior (alpha=1, beta=1) has significant influence. With many trades, the prior washes out. This is exactly the cold-start behavior we want.

### 3.6 Sharpe-Ratio Weighted Memory Periods

Not all periods of trading are equally informative. A period with Sharpe > 2.0 represents a genuine, consistent edge. A period with Sharpe near 0 is noise. Memories from high-Sharpe periods should be preferentially recalled.

```python
def compute_period_sharpe_weight(memory: EpisodicMemory, window_days: int = 30) -> float:
    """Weight a memory by the Sharpe ratio of its surrounding period."""

    # Get all trades in the window around this memory
    window_start = memory.timestamp - timedelta(days=window_days/2)
    window_end = memory.timestamp + timedelta(days=window_days/2)
    period_trades = query_episodic_by_timerange(window_start, window_end)

    if len(period_trades) < 5:
        return 1.0  # Not enough data — neutral weight

    pnl_rs = [t.pnl_r for t in period_trades if t.pnl_r is not None]
    if not pnl_rs or std(pnl_rs) == 0:
        return 1.0

    sharpe = mean(pnl_rs) / std(pnl_rs) * sqrt(252 / window_days)

    # Map Sharpe to weight: Sharpe=0 → 0.5, Sharpe=1 → 1.0, Sharpe=2 → 1.5, Sharpe=3+ → 2.0
    weight = 0.5 + 0.5 * min(3.0, max(0.0, sharpe))

    return weight
```

This weight can be incorporated as an optional multiplier in the recall formula:

```
Score_extended(m, C_now) = Q(m) * Sim(m, C_now) * Rec(m) * Conf(m) * Aff(m) * Sharpe_w(m)
```

The justification is that memories formed during periods of genuine edge (high Sharpe) contain more information about what works than memories formed during noise periods (low Sharpe). This is related to the concept of "Information Ratio" in portfolio management.

---

## 4. Mathematical Validation

### 4.1 Full Recall Scoring Function

Restating formally:

```
Score(m, C) = Q(m) * Sim(m.C, C) * Rec(m, t_now) * Conf(m) * Aff(m, A(t_now))
```

Where each component is bounded:

| Component | Range | Neutral Value | Behavior |
|-----------|-------|---------------|----------|
| Q(m) | (0, 1) | 0.5 (break-even) | Higher for profitable trades |
| Sim | [0, 1] | varies | Higher for context match |
| Rec | (0, 1] | 0.707 (30d old) | Higher for recent memories |
| Conf | [0.5, 1.0] | 0.75 (conf=0.5) | Higher for confident decisions |
| Aff | [0.7, 1.3] | 1.0 (neutral state) | Modulated by drawdown/streaks |

### 4.2 Boundedness Proof

**Claim:** The recall score is bounded: `Score(m, C) in (0, 1.3)`.

**Proof:**
- Q in (0, 1) — sigmoid is strictly bounded by 0 and 1, never reaches either
- Sim in [0, 1] — weighted average of [0,1] components
- Rec in (0, 1] — power law with positive exponent, approaches 0 but never reaches it
- Conf in [0.5, 1.0] — affine transformation of [0,1] to [0.5, 1.0]
- Aff in [0.7, 1.3] — 1.0 + 0.3 * [-1, 1]

Maximum: Q=0.999 * Sim=1.0 * Rec=1.0 * Conf=1.0 * Aff=1.3 ≈ 1.30
Minimum: approaches 0 as any of Q, Sim, Rec approach 0

The score never explodes and never collapses to exactly zero. This is crucial for numerical stability.

### 4.3 Convergence Analysis

**Question:** Does the memory system converge to useful behavior, or does it oscillate or degenerate?

**Claim:** OWM converges to preferentially recalling high-quality, context-relevant memories, with convergence rate proportional to sqrt(N) where N is the number of stored memories.

**Argument:**

Consider the Bayesian updating of semantic memory. The posterior Beta(alpha, beta) concentrates around the true probability p* as alpha + beta grows:

```
Var(posterior) = alpha*beta / ((alpha+beta)^2 * (alpha+beta+1))
            ≈ p*(1-p*) / (alpha+beta+1)
```

With N observations of weight ~1 each, alpha + beta ≈ N + 2, so Var ≈ p*(1-p*)/N. The standard deviation decreases as 1/sqrt(N), which is the standard Bayesian convergence rate.

For the recall function, consider what happens as memories accumulate:
1. More memories → better estimation of Q(m) distribution → more informative recall
2. More memories per context → better Sim(m, C) discrimination → context matching improves
3. Bayesian semantic updates → confidence narrows → knowledge becomes actionable
4. Procedural tracking → behavioral biases become detectable → self-correction possible

**Degenerate case analysis:**

*What if all memories are winners?* Q(m) ≈ 1 for all, so the discriminating factors become Sim and Rec. The system still works — it returns the most context-similar recent memories. This is actually the correct behavior during a strong bull market.

*What if all memories are losers?* Q(m) ≈ 0.1-0.3 for all. The agent's Kelly fraction goes to 0, risk_appetite drops via affective memory, and the agent effectively stops trading until conditions change. This is correct — it should not trade when all evidence says the strategy is losing.

*What if memories are 50/50?* Q(m) distributes around 0.5. Sim and Rec dominate the ranking. The system retrieves contextually relevant, recent memories — which is exactly the right behavior in the absence of a clear directional edge.

### 4.4 Edge Cases

**Cold Start (0 trades):**
- Episodic: empty → recall returns nothing → Kelly fraction = 0 → no trading
- Semantic: can be seeded with prior knowledge (alpha=2, beta=1 for positive belief)
- Procedural: initialized with defaults
- Affective: confidence = 0.5 (neutral), risk_appetite = 1.0 (no drawdown)
- Prospective: empty or seeded with basic rules

The system gracefully handles cold start by defaulting to "do nothing" and allowing user-seeded priors. As data accumulates, OWM takes over.

**Conflicting Memories:**
When episodic memories give conflicting signals (some winners, some losers in similar context), the recall function naturally handles this — both are returned, with winners having higher Q scores. The agent sees both the winning and losing memories and must weigh them. This is actually more informative than a single aggregated statistic, because the agent can examine the differences between the winning and losing memories' contexts.

**Regime Change:**
This is where OWM most clearly outperforms L1/L2/L3. When the regime changes:
1. **Sim drops** — old memories' context no longer matches current context, so they are naturally de-prioritized
2. **Affective state adjusts** — if the regime change causes losses, drawdown increases, risk_appetite drops
3. **Prospective memories trigger** — "if regime changes, reduce exposure" plans activate
4. **Semantic knowledge decays selectively** — the `regime_match_factor` in semantic decay reduces the retrieval strength of knowledge from the old regime
5. **New episodic memories form** — the first trades in the new regime become high-priority (few competitors for Sim)

The system adapts without any explicit "regime change detected" signal — it emerges from the memory dynamics.

### 4.5 Computational Complexity

For a query with N total memories:
- Context similarity computation: O(N) (each is O(1) — fixed-size vector)
- Recall scoring: O(N) (each score is O(1))
- Sorting: O(N log N)
- Total: O(N log N)

With N = 10,000 memories (Sean's current dataset), this takes < 50ms on any modern machine. For N = 100,000+, pre-filtering by symbol and strategy reduces the candidate set to O(1000), keeping the system responsive.

SQLite indexes on `symbol`, `strategy`, `regime`, `timestamp` ensure that pre-filtering is O(log N).

---

## 5. Financial Validation

### 5.1 Position Sizing → Kelly Criterion → Procedural Memory

| Financial Concept | OWM Component | Mathematical Connection |
|-------------------|---------------|------------------------|
| Optimal position size | Procedural Memory tracks actual sizing | `kelly_from_memory()` computes f* from outcome-weighted recall |
| Fractional Kelly | Affective Memory modulates risk_appetite | `f_actual = f* * fractional * risk_appetite` |
| Position sizing consistency | Procedural `actual_lot_variance` | Low variance = disciplined execution |
| Sizing relative to edge | `actual_lot_fraction_vs_kelly` | Ratio < 1 = under-betting, > 1 = over-betting |

**Reference:** Kelly (1956), "A New Interpretation of Information Rate." Thorp (2006), "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market." The Bayesian Kelly framework by Browne (1996) at Columbia University connects Bayesian posterior updating to optimal Kelly sizing — exactly what OWM does when computing Kelly fractions from outcome-weighted memory recall.

### 5.2 Pattern Recognition → Statistical Edge → Semantic Memory

| Financial Concept | OWM Component | Mathematical Connection |
|-------------------|---------------|------------------------|
| Edge estimation | Semantic Memory confidence = Beta posterior | P(edge exists) = alpha / (alpha + beta) |
| Edge uncertainty | Semantic Memory `uncertainty` field | Var = alpha*beta / ((a+b)^2*(a+b+1)) |
| Edge decay | `regime_match_factor` in semantic decay | Edge is conditional on market regime |
| Overfitting detection | `sample_size` + `uncertainty` | Low n + high confidence = suspicious |
| Out-of-sample test | Prospective Memory → track future performance | Create plan: "test this edge on next 10 trades" |

**Reference:** Lopez de Prado (2018), "Advances in Financial Machine Learning" — Chapters 8-11 on backtest overfitting, combinatorial purged cross-validation. The Bayesian framework in OWM semantic memory naturally penalizes small-sample patterns by maintaining wide posteriors, addressing the overfitting problem that Lopez de Prado identifies as the #1 issue in quantitative finance.

### 5.3 Risk Management → Drawdown Theory → Affective Memory

| Financial Concept | OWM Component | Mathematical Connection |
|-------------------|---------------|------------------------|
| Maximum drawdown constraint | `max_acceptable_drawdown` | Modulates risk_appetite quadratically |
| Drawdown recovery | `confidence_level` EWMA | Slow restoration after recovery |
| Risk of ruin | Kelly fraction * risk_appetite | Combined never exceeds safe threshold |
| Volatility targeting | ATR in context vector | Memories from similar volatility are prioritized |
| Loss aversion (2x) | Affective `retrieval_bias` | Losses boost retrieval by 1.5x in drawdown |

**Reference:** Grossman & Zhou (1993), "Optimal Investment Strategies for Controlling Drawdowns." Kahneman & Tversky (1979), "Prospect Theory: An Analysis of Decision under Risk." The quadratic drawdown-to-risk mapping in affective memory implements the theoretical result from Grossman & Zhou that optimal exposure decreases convexly with drawdown depth.

### 5.4 Market Regime Detection → Regime Switching Models → Prospective Memory

| Financial Concept | OWM Component | Mathematical Connection |
|-------------------|---------------|------------------------|
| Regime identification | Context vector `regime` classification | Categorical variable in Sim() |
| Regime transitions | Prospective Memory trigger conditions | "IF regime changes, THEN adjust" |
| Hidden Markov Models | Context similarity across memories | Implicit: memories cluster by regime |
| Regime-dependent parameters | Semantic knowledge with regime domain | "VB works in trending_up" is regime-specific |
| Transition probabilities | Not explicit — emergent from memory access | Frequency of regime labels in recent memories |

**Reference:** Hamilton (1989), "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle." Ang & Bekaert (2002), "International Asset Allocation With Regime Shifts." OWM does not require an explicit HMM — regime-dependent behavior emerges from the context similarity function. This is simpler to implement, more interpretable, and avoids the parameter estimation challenges of HMMs with limited data.

### 5.5 Trade Journaling → Behavioral Finance → Episodic Memory

| Financial Concept | OWM Component | Mathematical Connection |
|-------------------|---------------|------------------------|
| Trade journal | Episodic memory store | Structured, searchable, weighted |
| Post-trade review | `reflection` field + Bayesian update | Review triggers knowledge consolidation |
| Disposition effect | Procedural `disposition_effect` metric | Measured as hold-time ratio |
| Recency bias | Affective modulation | Counter-balanced during streaks |
| Overconfidence | Procedural `actual_lot_fraction_vs_kelly` | Over-betting after wins detected |

**Reference:** Shefrin & Statman (1985), "The Disposition to Sell Winners Too Early and Ride Losers Too Long: Theory and Evidence." Odean (1998), "Are Investors Reluctant to Realize Their Losses?" Barber & Odean (2000), "Trading Is Hazardous to Your Wealth." OWM's procedural memory provides automatic detection of these well-documented behavioral biases, which is precisely what trade journaling is supposed to achieve but rarely does in practice due to inconsistent human self-reporting.

---

## 6. Comparison: L1/L2/L3 vs OWM

| Dimension | L1/L2/L3 | OWM | Winner |
|-----------|----------|-----|--------|
| **Information Captured** | Trades (L1), aggregate patterns (L2), parameter changes (L3) | 5 memory types: episodic events, semantic knowledge, procedural habits, affective state, prospective plans | **OWM** — captures behavioral, emotional, and planning dimensions |
| **Recall Mechanism** | Keyword matching on text (O(n) scan, no ranking theory) | Outcome-weighted, context-similar, recency-adjusted, confidence-modulated, affect-aware (O(n log n), principled formula) | **OWM** — mathematically grounded retrieval |
| **Adaptation Speed** | Batch: L2 scans L1 periodically, L3 generates adjustments | Real-time: every trade updates episodic, semantic (Bayesian), procedural, and affective memories | **OWM** — continuous learning vs batch processing |
| **Regime Change Handling** | None — L2 patterns are regime-blind, manually invalidated | Automatic — context similarity drops for old-regime memories, affective state adjusts, prospective plans trigger | **OWM** — emergent regime adaptation |
| **Explainability** | Low — "pattern XYZ has 70% confidence" with no context | High — "I'm recalling this memory because it had a +3R outcome (Q=0.98) in a very similar context (Sim=0.91), is fairly recent (Rec=0.85), was made with high confidence (Conf=0.95)" | **OWM** — every recall decision is decomposable |
| **Cold Start** | Requires N trades before L2 can find patterns | Works from 0: seeded semantic + default procedural + neutral affective; improves continuously | **OWM** — graceful degradation |
| **Behavioral Bias Detection** | Not possible | Built-in: procedural memory tracks disposition effect, loss aversion, recency bias | **OWM** — unique capability |
| **Forward Planning** | Not possible | Prospective memory: conditional plans with trigger evaluation | **OWM** — unique capability |
| **Implementation Complexity** | Low — 3 SQL tables, 4 MCP tools | Medium — 5+ SQL tables, 6+ MCP tools, real-time updates | **L1/L2/L3** — simpler |
| **Competitive Moat** | Low — trivially reproducible (it's just tables + SQL) | High — the recall formula, decay functions, and Bayesian updating are original theory | **OWM** — defensible IP |
| **Academic Grounding** | None — ad hoc data engineering | Tulving's memory taxonomy, ACT-R decay model, Kelly Criterion, Bayesian updating, Prioritized Experience Replay | **OWM** — publishable |

### Why OWM Is Not Just "A Better L2"

The most common objection will be: "Isn't OWM just L1/L2/L3 with better recall?" No. The differences are structural:

1. **L1/L2/L3 is unidirectional; OWM is a cycle.** In OWM, recall influences storage (what gets encoded depends on what's already known), and outcome updates flow backward to all memory types simultaneously.

2. **L1/L2/L3 separates storage and retrieval; OWM unifies them.** In L1/L2/L3, you store at one time and retrieve at another, and the retrieval mechanism is completely independent of how data was stored. In OWM, every memory has a retrieval strength that changes over time based on usage, outcomes, and context.

3. **L1/L2/L3 has no theory of the agent; OWM models the agent's internal state.** Affective and procedural memories are about the agent itself, not about the market. This enables self-awareness and self-correction.

4. **L1/L2/L3 is retrospective; OWM is also prospective.** Prospective memory enables forward planning — a capability that does not exist in any current AI memory system (Mem0, Zep, LangChain Memory are all retrospective).

---

## 7. Implementation Specification

### 7.1 Mapping to Existing TradeMemory Tools

| Current MCP Tool | OWM Mapping | Changes Needed |
|------------------|-------------|----------------|
| `store_trade_memory` | Write to episodic memory + update procedural + update semantic (Bayesian) + update affective | Replaced by `remember_trade` |
| `recall_similar_trades` | `outcome_weighted_recall()` on episodic + semantic | Replaced by `recall_memories` |
| `get_strategy_performance` | Query procedural memory for behavioral stats + aggregate episodic | Return procedural metrics alongside aggregate stats |
| `get_trade_reflection` | Retrieve episodic memory + connected semantic knowledge + relevant prospective plans | Enrich response with cross-memory links |

### 7.2 New MCP Tools Needed

```python
# 1. Store with full context (replaced store_trade_memory)
@mcp.tool()
async def remember_trade(
    symbol: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    pnl: float,
    pnl_r: float,           # NEW: R-multiple
    strategy_name: str,
    market_context: str,     # Natural language (agent's description)
    context_regime: str,     # NEW: classified regime
    context_atr_d1: float,   # NEW: ATR on D1
    confidence: float,       # NEW: agent's confidence at decision time
    reflection: str = None,
    max_adverse_excursion: float = None,  # NEW: worst unrealized loss
) -> dict:
    """Store a trade as episodic memory and trigger cross-memory updates."""
    ...

# 2. Outcome-weighted recall (replaced recall_similar_trades)
@mcp.tool()
async def recall_memories(
    symbol: str,
    market_context: str,
    context_regime: str = None,
    context_atr_d1: float = None,
    strategy_name: str = None,
    memory_types: List[str] = ['episodic', 'semantic'],
    limit: int = 10,
) -> dict:
    """Recall memories using outcome-weighted, context-aware scoring."""
    ...

# 3. Query behavioral patterns (NEW)
@mcp.tool()
async def get_behavioral_analysis(
    strategy_name: str = None,
    symbol: str = None,
) -> dict:
    """Get procedural memory analysis: biases, habits, Kelly comparison."""
    ...

# 4. Get agent state (NEW)
@mcp.tool()
async def get_agent_state() -> dict:
    """Return current affective state: confidence, risk appetite, drawdown."""
    ...

# 5. Create a plan (NEW)
@mcp.tool()
async def create_trading_plan(
    trigger_condition: dict,
    planned_action: dict,
    reasoning: str,
    expiry_days: int = 30,
) -> dict:
    """Create a prospective memory: IF condition THEN action."""
    ...

# 6. Check active plans (NEW)
@mcp.tool()
async def check_active_plans(
    current_context: dict = None,
) -> dict:
    """Evaluate all active prospective memories against current context."""
    ...
```

### 7.3 Schema Migration

The migration from L1/L2/L3 to OWM can be done incrementally:

**Phase 1: Add OWM tables alongside existing tables**
```sql
-- New tables (Section 2 schemas)
CREATE TABLE episodic_memory (...);
CREATE TABLE semantic_memory (...);
CREATE TABLE procedural_memory (...);
CREATE TABLE affective_state (...);
CREATE TABLE prospective_memory (...);
```

**Phase 2: Migrate existing data**
```python
def migrate_trades_to_episodic():
    """Convert existing trade_records to episodic_memory."""
    trades = db.query_trades(limit=100000)
    for t in trades:
        episodic = {
            'id': t['id'],
            'timestamp': t['timestamp'],
            'context_json': t.get('market_context', '{}'),
            'context_regime': infer_regime(t),  # Heuristic from existing data
            'strategy': t['strategy'],
            'direction': t['direction'],
            'entry_price': extract_entry_price(t),
            'pnl': t.get('pnl'),
            'pnl_r': compute_pnl_r(t),  # Requires SL info
            'reflection': t.get('lessons') or t.get('exit_reasoning'),
            'confidence': t.get('confidence', 0.5),
            'retrieval_strength': 1.0,
            'created_at': t['timestamp'],
        }
        insert_episodic(episodic)

def migrate_patterns_to_semantic():
    """Convert existing patterns to semantic_memory."""
    patterns = db.query_patterns(limit=1000)
    for p in patterns:
        semantic = {
            'id': p['pattern_id'],
            'proposition': p['description'],
            'alpha': 1.0 + p['confidence'] * p['sample_size'],
            'beta': 1.0 + (1 - p['confidence']) * p['sample_size'],
            'sample_size': p['sample_size'],
            'strategy': p.get('strategy'),
            'symbol': p.get('symbol'),
            'source': p['source'],
            'created_at': p['discovered_at'],
            'updated_at': p['discovered_at'],
        }
        insert_semantic(semantic)
```

**Phase 3: Replace MCP tools with OWM versions**

This is backward-compatible — the new tools accept the same inputs but return richer outputs.

### 7.4 Core Recall Algorithm — Python Implementation

```python
import math
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ScoredMemory:
    memory_id: str
    memory_type: str  # 'episodic', 'semantic', 'prospective'
    score: float
    components: dict  # {'Q': float, 'Sim': float, 'Rec': float, 'Conf': float, 'Aff': float}
    data: dict        # The actual memory content


def sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    else:
        z = math.exp(x)
        return z / (1.0 + z)


def compute_outcome_quality(memory: dict, sigma_r: float = 1.5, k: float = 2.0) -> float:
    """Q(m) — outcome quality score."""
    pnl_r = memory.get('pnl_r')
    if pnl_r is None:
        return 0.5  # No outcome yet — neutral

    if sigma_r <= 0:
        sigma_r = 1.5  # Fallback

    return sigmoid(k * pnl_r / sigma_r)


def compute_context_similarity(ctx1: dict, ctx2: dict) -> float:
    """Sim(C1, C2) — context similarity in [0, 1]."""
    score = 0.0
    total_weight = 0.0

    # Categorical matches
    categoricals = [
        ('context_regime', 0.25),
        ('context_volatility_regime', 0.15),
        ('context_session', 0.10),
    ]
    for field, weight in categoricals:
        total_weight += weight
        v1 = ctx1.get(field)
        v2 = ctx2.get(field)
        if v1 and v2 and v1 == v2:
            score += weight

    # Numerical similarity (Gaussian kernel)
    numericals = [
        ('context_atr_d1', 0.15, 0.3),
        ('context_atr_h1', 0.10, 0.3),
        ('price', 0.10, 0.2),
        ('drawdown_pct', 0.10, 0.1),
    ]
    for field, weight, bandwidth in numericals:
        total_weight += weight
        v1 = ctx1.get(field)
        v2 = ctx2.get(field)
        if v1 is not None and v2 is not None and v1 != 0:
            ratio = (v1 - v2) / (bandwidth * abs(v1))
            sim = math.exp(-0.5 * ratio * ratio)
            score += weight * sim

    return score / total_weight if total_weight > 0 else 0.0


def compute_recency(timestamp_iso: str, tau: float = 30.0, d: float = 0.5) -> float:
    """Rec(m) — power-law recency decay."""
    try:
        mem_time = datetime.fromisoformat(timestamp_iso.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        age_days = max(0, (now - mem_time).total_seconds() / 86400)
    except (ValueError, TypeError):
        return 0.5  # Fallback for unparseable timestamps

    return (1.0 + age_days / tau) ** (-d)


def compute_confidence_factor(confidence: Optional[float]) -> float:
    """Conf(m) — confidence at formation, mapped to [0.5, 1.0]."""
    c = confidence if confidence is not None else 0.5
    return 0.5 + 0.5 * max(0.0, min(1.0, c))


def compute_affective_modulation(
    memory: dict,
    drawdown_state: float = 0.0,
    consecutive_losses: int = 0,
    alpha: float = 0.3,
) -> float:
    """Aff(m) — state-dependent retrieval modulation."""
    pnl_r = memory.get('pnl_r')
    relevance = 0.0

    if drawdown_state > 0.5:
        if pnl_r is not None and pnl_r < -1.5:
            relevance = 0.5   # Boost large-loss warnings
        elif pnl_r is not None and pnl_r > 2.0:
            relevance = 0.3   # Boost recovery memories
    elif consecutive_losses >= 3:
        if pnl_r is not None and pnl_r > 0:
            relevance = 0.3   # Counter losing streak recency bias
        elif pnl_r is not None and pnl_r < 0:
            relevance = -0.2  # Slightly suppress loss piling

    return 1.0 + alpha * relevance


def outcome_weighted_recall(
    query_context: dict,
    memories: List[dict],
    affective_state: dict,
    limit: int = 10,
) -> List[ScoredMemory]:
    """
    Core OWM recall function.

    Args:
        query_context: Current market context dict
        memories: List of candidate memory dicts
        affective_state: Current affective state dict
        limit: Max memories to return

    Returns:
        List of ScoredMemory, sorted by score descending
    """
    # Compute sigma_r from available data
    pnl_rs = [m.get('pnl_r', 0) for m in memories if m.get('pnl_r') is not None]
    sigma_r = (sum(x*x for x in pnl_rs) / len(pnl_rs)) ** 0.5 if pnl_rs else 1.5
    sigma_r = max(0.5, sigma_r)  # Floor to prevent division issues

    dd_state = affective_state.get('drawdown_state', 0.0)
    consec_losses = affective_state.get('consecutive_losses', 0)

    scored = []
    for m in memories:
        q = compute_outcome_quality(m, sigma_r=sigma_r)
        sim = compute_context_similarity(m, query_context)
        rec = compute_recency(
            m.get('timestamp', ''),
            tau=30.0 if m.get('_type') == 'episodic' else 180.0,
            d=0.5 if m.get('_type') == 'episodic' else 0.3,
        )
        conf = compute_confidence_factor(m.get('confidence'))
        aff = compute_affective_modulation(m, dd_state, consec_losses)

        total_score = q * sim * rec * conf * aff

        scored.append(ScoredMemory(
            memory_id=m.get('id', ''),
            memory_type=m.get('_type', 'episodic'),
            score=total_score,
            components={'Q': round(q, 4), 'Sim': round(sim, 4),
                       'Rec': round(rec, 4), 'Conf': round(conf, 4),
                       'Aff': round(aff, 4)},
            data=m,
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:limit]
```

---

## 8. Validation Plan Using Real Data

### 8.1 Available Data

Sean has:
- **10,169 backtest trades** across 97 parameter variants (4 strategies, 2024.01-2026.02)
- **~15 live demo trades** from Shadow Mode (2026.02-03)
- **Context data**: ATR values, regimes, sessions (partially reconstructed from timestamps)

### 8.2 Backtest Methodology

**Step 1: Convert existing data to OWM format**

Migrate 10,169 trades from `backtest_v1.db` into episodic memory, computing:
- `pnl_r`: from PnL and estimated SL distance (strategy-specific)
- `context_regime`: from price trajectory in the trade's time window
- `context_atr_d1`: from historical ATR data (reconstruct from OHLC)
- `confidence`: set to 0.5 for backtest trades (no real confidence data)

**Step 2: Split data temporally**

- **Training period**: 2024.01 - 2025.06 (18 months)
- **Validation period**: 2025.07 - 2026.02 (8 months)

This is a strict out-of-sample split. No information from the validation period is used during training.

**Step 3: Simulate OWM agent on validation period**

For each trade in the validation period:
1. Compute current context from the trade's timestamp
2. Run `outcome_weighted_recall()` using only training period memories
3. Compute Kelly fraction from recalled memories
4. Simulate position sizing: `lot_size = f_kelly * equity / (SL * tick_value)`
5. Compute hypothetical PnL with OWM sizing vs original fixed-lot sizing
6. Update all memory types (episodic, semantic, procedural, affective) with the trade

**Step 4: Compare strategies**

- **Baseline**: Fixed lot (0.10) as in original backtest
- **OWM**: Outcome-weighted Kelly sizing
- **Simple Kelly**: Standard Kelly from aggregate win rate (no context weighting)
- **Recency-only**: Kelly from last 50 trades (no outcome weighting)

### 8.3 Metrics to Measure

**Financial Performance:**
- Net PnL ($)
- Profit Factor
- Sharpe Ratio (annualized)
- Maximum Drawdown (%)
- GHPR (Geometric Holding Period Return)
- Calmar Ratio (return / max DD)

**Decision Quality:**
- **Recall Precision**: Of the top-5 recalled memories, how many had the same direction outcome as the current trade? (Higher = better context matching)
- **Kelly Accuracy**: Correlation between OWM-computed Kelly fraction and actual trade outcome
- **Regime Adaptation**: Rolling 30-day Sharpe ratio — does OWM maintain Sharpe more consistently across regime changes?

**Adaptation Speed:**
- **Regime Detection Lag**: After a regime change, how many trades until OWM's behavior changes? Compare with L1/L2/L3 (which requires manual re-scan)
- **Drawdown Recovery**: Time (in trades) to recover to previous equity high under OWM vs fixed sizing

**Behavioral Quality:**
- **Disposition Effect**: Does OWM reduce the hold-time asymmetry between winners and losers?
- **Sizing Consistency**: Variance of lot sizes relative to Kelly optimal
- **Over-trading Prevention**: Does OWM reduce trade frequency during unfavorable regimes?

### 8.4 A/B Comparison Framework

```python
def run_owm_validation(
    training_trades: List[dict],
    validation_trades: List[dict],
    initial_equity: float = 10000.0,
) -> dict:
    """
    Run OWM vs baselines on validation data.

    Returns comparison metrics for each approach.
    """
    approaches = {
        'fixed_lot': FixedLotSimulator(lot_size=0.10),
        'simple_kelly': SimpleKellySimulator(training_trades),
        'recency_kelly': RecencyKellySimulator(window=50),
        'owm': OWMSimulator(training_trades),
    }

    results = {}
    for name, sim in approaches.items():
        equity_curve = [initial_equity]

        for trade in sorted(validation_trades, key=lambda t: t['timestamp']):
            lot_size = sim.compute_lot_size(trade, equity_curve[-1])
            actual_pnl = trade['pnl_r'] * lot_size * SL_DOLLARS  # Scale by lot
            equity_curve.append(equity_curve[-1] + actual_pnl)
            sim.update(trade)

        results[name] = compute_metrics(equity_curve, validation_trades)

    return results
```

### 8.5 Expected Outcomes

Based on the theory:

1. **OWM should outperform fixed lot** during validation because it reduces sizing during adverse regimes (affective memory) and increases sizing during favorable regimes (high Kelly from context-similar winners).

2. **OWM should outperform simple Kelly** because simple Kelly uses aggregate statistics that include irrelevant regime data. OWM filters for context-similar memories.

3. **OWM should have lower maximum drawdown** because the affective memory's risk_appetite reduction kicks in during drawdowns, while fixed lot and simple Kelly are drawdown-oblivious.

4. **The biggest improvement should be in Calmar ratio** (return/maxDD), because OWM simultaneously increases return (better sizing) and decreases drawdown (risk modulation).

5. **The biggest risk is overfitting the recall formula's parameters** (k, tau, d, alpha, etc.). To mitigate: keep parameters at their theoretically justified defaults and do not tune them on validation data. The parameters in Section 3 are derived from cognitive science (ACT-R) and finance theory (Kelly, Grossman-Zhou), not from curve-fitting.

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **R-multiple** | Trade PnL divided by initial risk (SL distance). A +2R trade means you made 2x your risk. |
| **Kelly fraction** | Optimal fraction of capital to risk, maximizing log-growth. |
| **GHPR** | Geometric Holding Period Return — the compounded per-trade return. |
| **Profit Factor** | Gross wins / Gross losses. PF > 1 = profitable. |
| **Sharpe Ratio** | Mean return / Std(return), annualized. Sharpe > 1 = good. |
| **Calmar Ratio** | Annualized return / Maximum drawdown. Higher = better risk-adjusted. |
| **ATR** | Average True Range — a measure of volatility in price units. |
| **Regime** | Market state: trending up, trending down, ranging, volatile. |
| **Power law decay** | f(t) = (1 + t/tau)^(-d). Slower than exponential, matches human memory research. |
| **Beta distribution** | Bayesian conjugate prior for binomial probability. Beta(a,b) has mean a/(a+b). |
| **Disposition effect** | Behavioral bias: selling winners too early, holding losers too long. |

## Appendix B: References

### Cognitive Science
- Tulving, E. (1972). "Episodic and semantic memory." Organization of Memory.
- Tulving, E. (1985). "Memory and consciousness." Canadian Psychology, 26(1), 1-12.
- Anderson, J.R. (2007). "How Can the Human Mind Occur in the Physical Universe?" (ACT-R theory)
- Wixted, J.T. & Ebbesen, E.B. (1991). "On the form of forgetting." Psychological Science.
- Bjork, R.A. & Bjork, E.L. (1992). "A new theory of disuse and an old theory of stimulus fluctuation."

### Reinforcement Learning
- Schaul, T., et al. (2015). "Prioritized Experience Replay." arXiv:1511.05952.
- Peters, J. & Schaal, S. (2007). "Reinforcement learning by reward-weighted regression for operational space control."
- Peng, X.B., et al. (2019). "Advantage-Weighted Regression: Simple and Scalable Off-Policy Reinforcement Learning."

### Quantitative Finance
- Kelly, J.L. (1956). "A New Interpretation of Information Rate." Bell System Technical Journal.
- Browne, S. (1996). "Portfolio Choice and the Bayesian Kelly Criterion." Columbia Business School.
- Thorp, E.O. (2006). "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market."
- Vince, R. (1990). "Portfolio Management Formulas."
- Grossman, S. & Zhou, Z. (1993). "Optimal Investment Strategies for Controlling Drawdowns."
- Lopez de Prado, M. (2018). "Advances in Financial Machine Learning." Wiley.
- Hamilton, J.D. (1989). "A New Approach to the Economic Analysis of Nonstationary Time Series."
- Ang, A. & Bekaert, G. (2002). "International Asset Allocation With Regime Shifts."

### Behavioral Finance
- Kahneman, D. & Tversky, A. (1979). "Prospect Theory: An Analysis of Decision under Risk."
- Shefrin, H. & Statman, M. (1985). "The Disposition to Sell Winners Too Early and Ride Losers Too Long."
- Odean, T. (1998). "Are Investors Reluctant to Realize Their Losses?"
- Barber, B. & Odean, T. (2000). "Trading Is Hazardous to Your Wealth."

### AI Memory Systems
- Chhablani, G., et al. (2025). "Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory." arXiv:2504.19413.
- Sumers, T.R., et al. (2023). "Cognitive Architectures for Language Agents." arXiv:2309.02427.
- LangChain LangMem SDK (2025). Semantic, Procedural, Episodic memory for agents.

---

## Appendix C: Competitive Moat Analysis

### What Can Be Copied
- The 5 memory types (concepts from cognitive science are not patentable)
- The SQL schema
- The basic recall formula structure

### What Cannot Be Easily Copied
1. **The specific parameter choices** (tau=30, d=0.5, k=2.0, etc.) — derived from cross-disciplinary synthesis of cognitive science + finance theory. A competitor would need to reproduce the research.
2. **The Bayesian semantic update rule** weighted by outcome magnitude — this is a novel contribution.
3. **The Kelly-from-memory computation** — using outcome-weighted recall to compute context-dependent Kelly fractions is, to our knowledge, original.
4. **The affective modulation** — state-dependent recall that models drawdown-aware memory access has no precedent in AI memory systems.
5. **The validation dataset** — 10,169 trades with strategy labels, regime classifications, and outcome data. This grows with usage.
6. **The integration** — OWM is designed for MCP protocol. The combination of memory theory + MCP tooling + trading domain creates a narrow but defensible niche.

### The Real Moat: Data Network Effect

The deepest moat is not the algorithm — it is the **data flywheel**:
1. Agent trades → episodic memories accumulate
2. More memories → better recall → better decisions
3. Better decisions → more profits → more users
4. More users → more aggregate data → better semantic knowledge
5. Better knowledge → better cold-start experience → even more users

This flywheel does not exist in L1/L2/L3 because L1/L2/L3 has no quality signal in its recall mechanism. OWM's outcome-weighting means that more data genuinely makes the system better, creating a compounding advantage.

---

*This document represents the theoretical foundation of TradeMemory v2.0. Implementation should proceed in phases: (1) schema migration, (2) recall algorithm, (3) Bayesian updating, (4) affective/procedural modules, (5) prospective memory. Each phase can be independently tested and validated against the existing 10,169-trade dataset.*
