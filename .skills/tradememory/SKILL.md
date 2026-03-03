---
name: tradememory
slug: tradememory
version: 1.0.0
description: >-
  AI trading memory for MT5/forex traders. Record every trade, discover patterns,
  and get AI-powered reflections with automatic strategy adjustments.
  The only trading memory system with 3-layer architecture (raw trades -> patterns -> strategy).
metadata:
  openclaw:
    emoji: "📊"
    category: "finance"
    requires:
      bins: ["python3", "pip"]
      env:
        - name: MT5_LOGIN
          description: "MetaTrader 5 account number for trade sync"
          optional: true
        - name: MT5_PASSWORD
          description: "MetaTrader 5 account password for trade sync"
          optional: true
        - name: MT5_SERVER
          description: "MT5 broker server name (e.g. ForexTimeFXTM-Demo01)"
          optional: true
        - name: ANTHROPIC_API_KEY
          description: "Enables LLM-powered reflections via Claude. Without it, reflections use rule-based analysis."
          optional: true
        - name: TRADEMEMORY_API
          description: "API endpoint URL, defaults to http://localhost:8000"
          optional: true
    os: ["linux", "darwin", "win32"]
    homepage: https://github.com/mnemox-ai/tradememory-protocol
---

# TradeMemory Protocol

Give your AI agent persistent trading memory. TradeMemory records every trade decision, discovers patterns across sessions, uses AI to reflect on your trading behavior, and automatically adjusts risk recommendations. It works with MT5, Binance, Alpaca, or any platform that outputs trade data.

Built on MCP (Model Context Protocol). 203 tests passing. MIT licensed.

## Installation

```bash
pip install tradememory-protocol
```

Verify installation:

```bash
python -c "import tradememory; print('TradeMemory ready')"
```

## Setup for MT5 Users

If you trade on MetaTrader 5, TradeMemory can auto-sync your closed trades every 60 seconds — zero modifications to your EA.

```bash
# 1. Install MT5 Python API
pip install MetaTrader5 python-dotenv requests

# 2. Clone repo for sync scripts
git clone https://github.com/mnemox-ai/tradememory-protocol.git
cd tradememory-protocol

# 3. Configure credentials
cp .env.example .env
# Edit .env with your MT5 login, password, server

# 4. Start the TradeMemory server
python -m src.tradememory.server
# Runs on http://localhost:8000

# 5. Start MT5 sync (in a second terminal)
python scripts/mt5_sync.py
# Polls MT5 every 60 seconds for closed trades
```

See [MT5_SYNC_SETUP.md](https://github.com/mnemox-ai/tradememory-protocol/blob/master/docs/MT5_SYNC_SETUP.md) for the full setup guide, auto-start configuration, and troubleshooting.

## Security & Permissions

**Network access:** Local only by default. The TradeMemory server runs on `localhost:8000` and does not make outbound network requests unless you configure the optional hosted API endpoint.

**Environment variables:** All environment variables listed above are optional. MT5 credentials (`MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`) are only needed if you use the MT5 sync feature. They are never logged, transmitted externally, or stored outside your local `.env` file.

**File system access:** TradeMemory writes to a single SQLite database file (`tradememory.db`) in the project directory. No other files are created or modified outside the project.

**No implicit permissions:** This skill does not auto-install dependencies, modify system files, or require elevated privileges. All setup steps are explicit and documented below.

## Available Commands

Tell your agent these things in natural language. TradeMemory will handle the rest.

### Record a Trade

> "Record my trade: XAUUSD long 0.05 lots, entry 2847, exit 2855, profit $40"

Calls `store_trade_memory`. Stores the trade in L1 (raw trade layer) with full context. You can add market conditions and reflections:

> "Record my XAUUSD short trade, entry 5180, exit 5165, profit $75. London session breakout, high volume. I noticed the pullback confirmed before entry."

### Check Performance

> "Show my trading performance this week"

Calls `get_strategy_performance`. Returns per-strategy stats: win rate, profit factor, average winner/loser, max drawdown, best and worst trades.

> "Compare my VolBreakout vs Pullback strategy performance"

### Recall Past Trades

> "Show my XAUUSD trades from last month"

Calls `recall_similar_trades` with symbol and date filter. Returns trades with their context, outcomes, and lessons.

> "What were my last 5 losing trades? What went wrong?"

### Run AI Reflection

> "Run a reflection on my last 20 trades"

Calls the reflection engine to analyze patterns across your trades. Discovers session-based edges (London vs Asian), strategy performance gaps, confidence-outcome correlations, and drawdown sequences.

> "What patterns have you found in my London session trades?"

### Compare Time Periods

> "How am I doing compared to last week?"

Calls `get_strategy_performance` for both periods and compares. Shows whether your win rate, profit factor, and risk management are improving or declining.

### Deep-Dive a Specific Trade

> "Tell me about trade MT5-2350547759"

Calls `get_trade_reflection`. Returns the full context: entry reasoning, market conditions, exit reasoning, P&L, lessons learned, and grade.

## MCP Tools Reference

| Tool | Purpose |
|------|---------|
| `store_trade_memory` | Store a trade decision with full context (symbol, direction, price, strategy, market context, reflection) |
| `recall_similar_trades` | Find past trades with similar market context for pattern matching |
| `get_strategy_performance` | Aggregate stats per strategy: win rate, PnL, profit factor, best/worst trades |
| `get_trade_reflection` | Deep-dive into a specific trade's reasoning and lessons |

## 3-Layer Memory Architecture

TradeMemory organizes your trading data into three layers:

**L1 — Raw Trades (Hot)**
Every trade recorded with: symbol, direction, lot size, entry/exit price, P&L, timestamps, strategy name, confidence score, reasoning, market context, and post-trade reflection.

**L2 — Discovered Patterns (Warm)**
The reflection engine runs daily and discovers patterns from L1 data:
- Session performance (London 78% WR vs Asian 31% WR)
- Strategy edges (VolBreakout PF 1.89 vs MeanReversion PF 0.72)
- Confidence correlation (high confidence trades: 85% WR, low confidence: 20% WR)
- Drawdown sequences and recovery patterns

**L3 — Strategy Adjustments (Cold)**
Rule-based tuning generated from L2 patterns:
- Disable losing strategies automatically
- Increase lot size for proven edges
- Restrict direction in trending markets
- Adjust confidence thresholds based on historical correlation

## Daily Reflection Setup

Set up a cron job so your agent sends you a daily trading summary:

```bash
# OpenClaw cron: run reflection every day at 23:55
openclaw cron add --name "Daily Trade Reflection" \
  --cron "55 23 * * *" \
  --session isolated \
  --message "Run a reflection on today's trades and send me a summary" \
  --announce
```

Weekly and monthly reflections are also supported:

```bash
# Weekly reflection (every Sunday at 23:55)
openclaw cron add --name "Weekly Trade Reflection" \
  --cron "55 23 * * 0" \
  --session isolated \
  --message "Run a weekly reflection on my trading performance and compare to last week" \
  --announce

# Monthly reflection (1st of each month at 00:00)
openclaw cron add --name "Monthly Trade Reflection" \
  --cron "0 0 1 * *" \
  --session isolated \
  --message "Run a monthly reflection on my trading. Summarize wins, losses, pattern changes, and strategy adjustments." \
  --announce
```

> **Note:** Add `--channel whatsapp` or `--channel slack` to the `--announce` flag to route notifications to a specific channel. Channel availability depends on your OpenClaw configuration.

## Hosted API (Coming Soon)

The current version runs locally on your machine. A hosted version at **mcp.mnemox.ai** is planned, which will include:

- Cloud-based reflection engine (no local API key needed)
- Cross-session pattern analysis with persistent storage
- Multi-account monitoring (run multiple EAs, one memory)
- Webhook alerts when the system detects behavioral drift

Free tier: local install (this version). Pro tier: hosted API with cloud reflections and multi-account support. Pricing TBD.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | No | Enables LLM-powered reflections (Claude). Without it, reflections use rule-based analysis. |
| `MT5_LOGIN` | MT5 only | MetaTrader 5 account number |
| `MT5_PASSWORD` | MT5 only | MetaTrader 5 password |
| `MT5_SERVER` | MT5 only | Broker server name (e.g. "ForexTimeFXTM-Demo01") |
| `TRADEMEMORY_API` | No | API endpoint, defaults to `http://localhost:8000` |
| `SYNC_INTERVAL` | No | MT5 sync polling interval in seconds, defaults to `60` |

## Links

- GitHub: https://github.com/mnemox-ai/tradememory-protocol
- PyPI: https://pypi.org/project/tradememory-protocol/
- Documentation: https://github.com/mnemox-ai/tradememory-protocol/blob/master/docs/TUTORIAL.md
- Demo: `python scripts/demo.py` (30 simulated trades, no API key needed)
