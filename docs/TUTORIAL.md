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
curl -sSL https://raw.githubusercontent.com/mnemox-ai/tradememory-protocol/master/install.sh | bash
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
# Expected: 36 passed
```

---

## Step 2: Run the Demo (2 minutes)

```bash
python demo.py
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

## Step 4: Record Your Own Trade (1 minute)

Start the MCP server:

```bash
python -m src.tradememory.server
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

## Step 5: Run Reflection (2 minutes)

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

## Step 6: Use Memory in Your Next Trade

The next time the agent starts, it loads its state:

```python
from src.tradememory.state import StateManager
from src.tradememory.db import Database

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
python demo.py
```

---

**Questions?** Open an issue: [GitHub Issues](https://github.com/mnemox-ai/tradememory-protocol/issues)

Built with care by [Mnemox](https://mnemox.ai) — AI memory infrastructure.
