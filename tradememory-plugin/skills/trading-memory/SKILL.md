---
name: trading-memory
description: Domain knowledge for AI trading memory — Outcome-Weighted Memory (OWM) architecture, 5 memory types, recall scoring, and behavioral analysis. Use when recording trades, recalling similar contexts, analyzing performance, or checking behavioral drift. Triggers on "record trade", "remember trade", "recall", "similar trades", "performance", "behavioral", "disposition", "affective state", "confidence".
---

# Trading Memory

## Overview

TradeMemory implements a cognitive memory architecture for trading agents. Every trade is stored with full context (market conditions, strategy, reasoning, confidence) and recalled using Outcome-Weighted Memory (OWM) — a scoring system that surfaces winning trades in similar contexts first.

This is not a trade journal. It's a memory system that learns which past experiences are most relevant to current decisions.

## Architecture: 3-Layer Pipeline

```
L1: Raw Trades → L2: Pattern Discovery → L3: Strategy Adjustments
```

- **L1 (Episodic)**: Every trade stored as-is with full context. The ground truth.
- **L2 (Patterns)**: Behavioral patterns discovered from L1 data. Disposition effect, session biases, strategy correlations.
- **L3 (Adjustments)**: Concrete strategy adjustments derived from L2 patterns. Parameter changes, rule modifications, strategy retirement.

## Outcome-Weighted Memory (OWM) — 5 Memory Types

### 1. Episodic Memory
Raw trade events. Each record contains: symbol, direction, entry/exit, P&L, strategy, market context, reflection, timestamp.

**When to write**: After every completed trade.
**When to read**: When recalling past trades for decision-making.

### 2. Semantic Memory
Strategy knowledge base. Aggregated understanding of what works: "VolBreakout performs best in London session with ATR > $40" is semantic memory.

**When to write**: Automatically updated when trades are stored via `remember_trade`.
**When to read**: When evaluating whether a strategy fits current conditions.

### 3. Procedural Memory
Behavioral baselines. Tracks execution patterns: average hold times per strategy, lot sizing consistency, stop loss adherence, entry timing precision.

**When to write**: Automatically computed from trade history.
**When to read**: During behavioral analysis and daily reviews.

### 4. Affective Memory
Emotional/confidence state. Tracks: current confidence level (0-1), drawdown percentage, win/loss streaks, risk appetite, tilt indicators.

**When to write**: Updated after every trade and during daily reviews.
**When to read**: Before entering trades (am I on tilt?), during risk checks.

### 5. Prospective Memory
Active trading plans. Future-oriented: "If XAUUSD breaks above 5200 with ATR confirmation, go long." Plans have entry conditions, exit conditions, risk parameters, and expiry dates.

**When to write**: When creating trading plans.
**When to read**: When checking if current market conditions match any active plans.

## OWM Recall Scoring

When you query `recall_memories`, results are scored by:

| Factor | Weight | Description |
|--------|--------|-------------|
| P&L Outcome | 40% | Profitable trades score higher. Magnitude matters. |
| Context Similarity | 30% | How closely the recalled context matches the query context |
| Recency | 20% | Recent trades weighted more (exponential decay) |
| Confidence Calibration | 10% | Trades where confidence matched outcome score higher |

**Why outcome-weighted?** Traditional trade journals treat all trades equally. OWM amplifies signal from successful decisions in similar contexts. If you've profited 5 times trading London session breakouts, those memories surface strongly when you're evaluating the next London session breakout.

## MCP Tools Reference

### Core Memory (2 tools)

| Tool | Use Case |
|------|----------|
| `get_strategy_performance` | Aggregate stats: win rate, PF, P&L per strategy |
| `get_trade_reflection` | Deep-dive into a specific trade's reasoning |

### OWM Cognitive Memory (6 tools)

| Tool | Use Case |
|------|----------|
| `remember_trade` | Full OWM store: writes to all 5 memory layers |
| `recall_memories` | OWM recall: scored by outcome, similarity, recency, calibration |
| `get_behavioral_analysis` | Procedural memory: disposition ratio, hold times, Kelly criterion |
| `get_agent_state` | Affective state: confidence, drawdown, streaks, risk appetite |
| `create_trading_plan` | Prospective memory: entry/exit conditions, risk parameters |
| `check_active_plans` | Evaluate active plans against current market conditions |

## Best Practices

### When to Record
- **Always** record after a trade closes, not while it's open
- Include the full market context — session, volatility, trend state
- Write an honest reflection — why you entered, what you expected, what happened
- Set confidence before seeing the result (not after)

### When to Recall
- **Before entering a trade**: "Have I been in this situation before? What happened?"
- **During daily review**: "What patterns emerge from this week's trades?"
- **After a loss**: "Have I seen this failure mode before?"

### When NOT to Recall
- Don't recall mid-trade to justify holding a loser
- Don't recall to confirm a decision you've already made (confirmation bias)
- Don't over-query — if you're recalling 20 times a day, you're procrastinating, not trading

## Common Mistakes

| Mistake | Why It's Bad | Fix |
|---------|-------------|-----|
| Recording without context | Useless for recall — can't match future situations | Always include session, volatility, trend state |
| Setting confidence after seeing P&L | Destroys calibration scoring | Set confidence at entry, before outcome is known |
| Ignoring affective state | Trading on tilt leads to revenge trades | Check `get_agent_state` before every session |
| Never running daily reviews | Behavioral drift goes undetected | Run `/daily-review` at end of each trading day |
| Storing paper trades as real trades | Pollutes performance metrics | Tag paper trades separately or use a different database |

## Data Flow

```
Trade Closes
    ↓
remember_trade() → Episodic (raw event)
                  → Semantic (strategy knowledge update)
                  → Procedural (behavioral baseline update)
                  → Affective (confidence/streak update)
                  → Prospective (check active plans)
    ↓
recall_memories() ← OWM scoring
    ↓
Next Trading Decision
```
