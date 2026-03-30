# TradeMemory Protocol — Complete Tutorial

**Time required:** ~10 minutes
**Prerequisites:** Python 3.10+, git
**API key needed:** No (demo uses simulated data)

---

## What You'll Build

A Claude-powered trading assistant that **remembers every trade, discovers patterns, and evolves its strategy over time**.

By the end of this tutorial, you'll see an AI agent go from "stateless calculator" to "trader with memory" — all in under 10 minutes.

---

## Step 1: Install (2 minutes)

### Option A: One-line install

```bash
curl -sSL https://raw.githubusercontent.com/mnemox-ai/tradememory-protocol/master/scripts/platform/install.sh | bash
cd tradememory-protocol
```

### Option B: Manual install

```bash
git clone https://github.com/mnemox-ai/tradememory-protocol.git
cd tradememory-protocol

python -m venv venv
source venv/bin/activate    # Linux/Mac
# venv\Scripts\activate     # Windows

pip install -r requirements.txt
cp .env.example .env
```

Verify installation:

```bash
python -m pytest tests/ -q
# Expected: 1,233 passed
```

---

## Step 2: Run the Demo (2 minutes)

```bash
python scripts/demo.py
```

This runs 30 simulated XAUUSD trades through the full pipeline. No API key needed.

**What you'll see:**

1. **L1 — Trade Recording**: 30 trades logged with session, strategy, confidence, P&L
2. **L2 — Pattern Discovery**: The reflection engine finds patterns like:
   - London session: ~100% win rate (HIGH EDGE)
   - Asian session: ~10% win rate (WEAK)
   - High confidence trades vastly outperform low confidence
3. **L3 — Strategy Adjustments**: Auto-generated rules:
   - Asian lot size reduced 50% (poor performance)
   - London lot size increased 60% (strong track record)
   - Minimum confidence threshold raised

---

## Step 3: Understand the 3-Layer Memory

TradeMemory uses a three-layer architecture:

| Layer | Name | What It Stores | Example |
|-------|------|---------------|---------|
| **L1** | Hot Memory | Active trades, current session | "XAUUSD long @ 2847, conf 0.78" |
| **L2** | Warm Memory | Discovered patterns, insights | "London VolBreakout: 73% win rate" |
| **L3** | Cold Memory | Full trade history (SQLite) | All 30 trades with complete context |

**Key insight:** Most AI agents only have L1 (current context). TradeMemory adds L2 and L3, so the agent builds knowledge over time.

---

## Step 4: OWM Cognitive Memory

TradeMemory v0.5 adds **OWM (Outcome-Weighted Memory)** — five memory layers that work like a trader's brain:

| Layer | What It Does |
|-------|-------------|
| **Episodic** | Stores each trade with full context (price, regime, reflection) |
| **Semantic** | Bayesian beliefs updated after every trade ("VolBreakout in trending markets: 72% edge") |
| **Procedural** | Running averages per strategy — what actually works |
| **Affective** | EWMA confidence tracking, win/loss streaks, drawdown state |
| **Prospective** | Trading plans with entry/exit criteria and expiry |

### Store a trade via MCP

Ask your Claude agent:

> "Remember my XAUUSD long trade: entered at 5180, exited at 5210, made $90 using VolBreakout. Market was trending up with strong London momentum. ATR was $155. I was 0.8 confident."

This calls `remember_trade` under the hood, which writes to all five memory layers simultaneously.

### Recall memories via MCP

Before entering a trade, ask:

> "What do my memories say about trading XAUUSD in a trending market? I'm looking at VolBreakout."

This calls `recall_memories` with outcome-weighted scoring — trades with better outcomes, matching context, and higher confidence rank higher.

### Other OWM tools

- `get_behavioral_analysis` — "Show me my behavioral patterns" → win rates by regime, overtrading detection, confidence calibration
- `get_agent_state` — "What's my current state?" → affective state, drawdown, streak info
- `create_trading_plan` — "Create a plan to buy XAUUSD at 5150 if price pulls back to the 20 EMA"
- `check_active_plans` — "Do I have any active trading plans?"

---

## Step 5: Evolution Engine

The Evolution Engine uses Claude to **discover trading strategies from raw price data**, then backtests and selects survivors across generations.

### Run a full evolution

Ask your Claude agent:

> "Run evolution on BTCUSDT 1h data for 3 generations with 10 candidates each."

This calls `evolution_evolve_strategy`, which:
1. Fetches OHLCV data from Binance
2. Uses Claude to generate candidate trading patterns
3. Backtests each pattern (vectorized, no API calls)
4. Eliminates weak hypotheses (Sharpe < threshold)
5. Repeats for N generations
6. Validates survivors on out-of-sample data

### Step-by-step approach

You can also run each step individually:

```
# 1. Fetch data
> "Fetch 90 days of BTCUSDT 1h data for evolution"
# Calls: evolution_fetch_market_data

# 2. Discover patterns
> "Discover 5 trading patterns from the BTCUSDT data"
# Calls: evolution_discover_patterns

# 3. Backtest a pattern
> "Backtest the first pattern against the data"
# Calls: evolution_run_backtest

# 4. Check the log
> "Show me the evolution log"
# Calls: evolution_get_log
```

**Requires:** `ANTHROPIC_API_KEY` in `.env` (Claude generates the pattern hypotheses).

---

## Step 6: Record Your Own Trade (1 minute)

Start the MCP server:

```bash
python -m tradememory
# Server runs on http://localhost:8000
```

In another terminal, record a trade:

```bash
curl -X POST http://localhost:8000/trade/record_decision \
  -H "Content-Type: application/json" \
  -d '{
    "trade_id": "MY-001",
    "symbol": "XAUUSD",
    "direction": "long",
    "lot_size": 0.05,
    "strategy": "VolBreakout",
    "confidence": 0.75,
    "reasoning": "London open, strong momentum above 2850"
  }'
```

Record the outcome:

```bash
curl -X POST http://localhost:8000/trade/record_outcome \
  -H "Content-Type: application/json" \
  -d '{
    "trade_id": "MY-001",
    "exit_price": 2858.50,
    "pnl": 42.50,
    "pnl_r": 2.1,
    "exit_reasoning": "Hit 2R target"
  }'
```

---

## Step 7: Run Reflection (2 minutes)

After recording several trades, trigger the reflection engine:

```bash
python -m src.daily_reflection
```

**Without API key (rule-based):** Calculates win rates, session patterns, strategy performance.

**With Claude API key:** Add to `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

Then reflection uses Claude to generate deeper insights like:
- "Your entries on London VolBreakout are well-timed, but exits are premature — consider trailing stops"
- "Asian session losses correlate with low-volume periods before 02:00 UTC"

---

## Step 8: Use Memory in Your Next Trade

The next time the agent starts, it loads its state:

```python
from tradememory.state import StateManager
from tradememory.db import Database

db = Database("data/tradememory.db")
state = StateManager(db=db)

agent_state = state.load_state("my-agent")
print(agent_state.warm_memory)    # Learned patterns
print(agent_state.risk_constraints)  # Adjusted risk params
```

The agent now knows:
- Which sessions perform best
- Which strategies have edge
- What confidence threshold to use
- How to size positions based on track record

---

## What Just Happened?

Your AI went from **"stateless calculator"** to **"trader with memory."**

| Before | After |
|--------|-------|
| Every session starts fresh | Agent loads learned patterns |
| Same mistakes repeated | Patterns detected, behavior adjusted |
| No idea about win rate | Knows win rate by session, strategy, time |
| Fixed position sizing | Dynamic sizing based on performance |
| No context between sessions | Full cross-session persistence |

---

## MCP Tools Reference

TradeMemory exposes 17 MCP tools across four categories:

### Core Memory (4 tools)

| Tool | Description |
|------|-------------|
| `store_trade_memory` | Record a trade decision with strategy, confidence, reasoning |
| `recall_similar_trades` | Find past trades matching symbol, strategy, or context |
| `get_strategy_performance` | Win rate, avg PnL, trade count per strategy |
| `get_trade_reflection` | Get AI-generated reflection on recent trades |

### OWM Cognitive Memory (6 tools)

| Tool | Description |
|------|-------------|
| `remember_trade` | Store trade into all 5 OWM layers (episodic → semantic → procedural → affective) |
| `recall_memories` | Outcome-weighted recall with context matching and recency scoring |
| `get_behavioral_analysis` | Win rates by regime, overtrading detection, confidence calibration |
| `get_agent_state` | Current affective state — confidence, drawdown, streak |
| `create_trading_plan` | Create a prospective plan with entry/exit criteria and expiry |
| `check_active_plans` | List active plans, check if any triggered |

### Evolution Engine (5 tools)

| Tool | Description |
|------|-------------|
| `evolution_fetch_market_data` | Fetch OHLCV data from Binance for backtesting |
| `evolution_discover_patterns` | LLM-powered pattern generation from price data |
| `evolution_run_backtest` | Vectorized backtest of a candidate pattern |
| `evolution_evolve_strategy` | Full evolution loop — generate, backtest, select, repeat |
| `evolution_get_log` | View past evolution runs and graduated strategies |

### Decision Audit Trail (2 tools)

| Tool | Description |
|------|-------------|
| `export_audit_trail` | Export trading decision records with SHA-256 tamper detection |
| `verify_audit_hash` | Verify integrity of a decision record by recomputing its hash |

---

## Next Steps

- **Connect to MT5**: See [MT5 Setup Guide](../MT5_SYNC_SETUP.md) to sync real trades
- **Set up daily reflection**: See [Daily Reflection Setup](../DAILY_REFLECTION_SETUP.md)
- **Read the architecture**: See [Architecture Overview](ARCHITECTURE.md)
- **API reference**: See [API Documentation](API.md)

---

## Troubleshooting

**Tests fail?**
```bash
python -m pytest tests/ -v  # See which test fails
```

**Server won't start?**
```bash
pip install -r requirements.txt  # Ensure all deps installed
```

**demo.py shows encoding errors?**
```bash
# On Windows, ensure UTF-8:
set PYTHONIOENCODING=utf-8
python scripts/demo.py
```

---

**Questions?** Open an issue: [GitHub Issues](https://github.com/mnemox-ai/tradememory-protocol/issues)

Built with care by [Mnemox](https://mnemox.ai) — AI memory infrastructure.
