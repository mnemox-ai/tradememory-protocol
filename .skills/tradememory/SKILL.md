---
name: tradememory
slug: tradememory
version: 0.5.1
description: >-
  AI trading memory with outcome-weighted recall and autonomous strategy evolution.
  17 MCP tools, 1,233 tests, works with any trading platform.
source: https://github.com/mnemox-ai/tradememory-protocol
repository: https://github.com/mnemox-ai/tradememory-protocol
homepage: https://github.com/mnemox-ai/tradememory-protocol
metadata:
  openclaw:
    emoji: "📊"
    category: "finance"
    requires:
      bins: ["python3", "pip"]
      env:
        ANTHROPIC_API_KEY: "Required for LLM reflections and Evolution Engine (optional, rule-based fallback without it)"
        TRADEMEMORY_API: "API endpoint, defaults to http://localhost:8000 (optional)"
    os: ["linux", "darwin", "win32"]
    homepage: https://github.com/mnemox-ai/tradememory-protocol
---

# TradeMemory Protocol

Give your AI agent persistent trading memory. TradeMemory records every trade, recalls past decisions weighted by outcome quality, discovers behavioral patterns, and autonomously evolves new strategies from raw price data.

**Outcome-Weighted Memory (OWM)** — 5 memory types (episodic, semantic, procedural, affective, prospective) that score recall by P&L outcome, context similarity, recency, and confidence. Winning trades surface first.

**Evolution Engine** — LLM-powered strategy discovery. Feed it OHLCV data from any exchange, it generates candidate patterns, backtests them vectorized, validates out-of-sample, and graduates survivors. No manual rule writing.

**Platform-agnostic** — works with MT5, Binance, Alpaca, or any broker that outputs trade data. 1,233 tests passing. MIT licensed.

## Installation

```bash
pip install tradememory-protocol
```

Verify:

```bash
python -c "import tradememory; print('TradeMemory ready')"
```

## Setup

### Claude Desktop (via uvx)

Add to your Claude Desktop MCP config:

```json
{
  "mcpServers": {
    "tradememory": {
      "command": "uvx",
      "args": ["tradememory-protocol"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add tradememory -- uvx tradememory-protocol
```

### Manual (local server)

```bash
python -m tradememory
```

Runs the MCP server on stdio. For the REST API server:

```bash
python -m tradememory.server
# Runs on http://localhost:8000
```

## MCP Tools Reference

### Core Memory (4 tools)

| Tool | Purpose |
|------|---------|
| `store_trade_memory` | Store a trade with full context (symbol, direction, price, strategy, market context, reflection) |
| `recall_similar_trades` | Find past trades matching current market context for pattern recognition |
| `get_strategy_performance` | Aggregate stats per strategy: win rate, PnL, profit factor, best/worst trades |
| `get_trade_reflection` | Deep-dive into a specific trade's reasoning and lessons learned |

### OWM Cognitive Memory (6 tools)

| Tool | Purpose |
|------|---------|
| `remember_trade` | Store a trade into all 5 OWM memory layers with automatic behavioral updates |
| `recall_memories` | Outcome-weighted recall — scores memories by P&L, context similarity, recency, confidence |
| `get_behavioral_analysis` | Procedural memory stats: hold times, disposition ratio, lot variance, Kelly criterion |
| `get_agent_state` | Current affective state: confidence level, drawdown %, win/loss streaks, risk appetite |
| `create_trading_plan` | Create a prospective trading plan with entry/exit conditions and risk parameters |
| `check_active_plans` | Check status of active trading plans, evaluate against current market conditions |

### Evolution Engine (5 tools)

| Tool | Purpose |
|------|---------|
| `evolution_fetch_market_data` | Fetch OHLCV data from Binance for backtesting and pattern discovery |
| `evolution_discover_patterns` | LLM-powered pattern discovery from price data — generates candidate trading rules |
| `evolution_run_backtest` | Vectorized backtest of a candidate pattern — returns Sharpe, win rate, max drawdown |
| `evolution_evolve_strategy` | Full evolution loop: generate → backtest → select → eliminate across generations |
| `evolution_get_log` | Get log of past evolution runs with graduated strategies and graveyard |

### Decision Audit Trail (2 tools)

| Tool | Purpose |
|------|---------|
| `export_audit_trail` | Export trading decision records with SHA-256 tamper detection for compliance review |
| `verify_audit_hash` | Verify integrity of a trading decision record by recomputing its SHA-256 hash |

## Available Commands

Tell your agent these things in natural language.

### Record a Trade

> "Record my trade: XAUUSD long 0.05 lots, entry 5180, exit 5210, profit $150"

> "Remember my XAUUSD short trade, entry 5200, exit 5165, profit $175. London session breakout, high volume, confidence 0.8."

### Recall with OWM

> "What trades have I taken in similar market conditions? Current context: ranging market, low volatility, Asian session."

Returns memories ranked by outcome-weighted score — winning trades in similar contexts surface first.

### Check Performance

> "Show my trading performance this week"

> "Compare my VolBreakout vs IntradayMomentum strategy performance"

### Behavioral Analysis

> "Show my behavioral analysis — am I cutting winners short?"

Returns disposition ratio, hold time asymmetry, lot sizing variance vs Kelly criterion.

### Agent State

> "What's my current confidence level and drawdown?"

> "Am I on tilt? Check my affective state."

### Trading Plans

> "Create a trading plan for XAUUSD long if price breaks above 5200 with ATR confirmation"

> "Check my active trading plans against current market conditions"

### Evolution Engine

> "Evolve a strategy for BTCUSDT on the 1h timeframe — 3 generations, 10 candidates each"

> "Discover 5 trading patterns from ETHUSDT 4h data over the last 90 days"

> "Backtest this pattern against BTCUSDT 1h data"

> "Show me the evolution log — which strategies graduated?"

### AI Reflection

> "Run a reflection on my last 20 trades"

> "What patterns have you found in my London session trades?"

## Security & Permissions

**Network access during install:** `pip install` downloads from PyPI. Standard Python package installation.

**Network access at runtime:** The MCP server runs on stdio by default — no network access. The REST server runs on `localhost:8000` and does not make outbound requests. If `ANTHROPIC_API_KEY` is set, the reflection engine and Evolution Engine send data to the Claude API. Evolution Engine fetches OHLCV data from the Binance public API.

**Environment variables:** All environment variables are optional. They are stored in your local `.env` file and never logged or sent to external services (except `ANTHROPIC_API_KEY` which authenticates with the Anthropic API).

**File system access:** TradeMemory writes to a single SQLite database file (`tradememory.db`) in the project directory. No files are created or modified outside the project.

**No implicit permissions:** This skill does not auto-install dependencies, modify system files, or require elevated privileges.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | No | Enables LLM reflections and Evolution Engine. Without it, reflections use rule-based analysis; Evolution is unavailable. |
| `TRADEMEMORY_API` | No | REST API endpoint, defaults to `http://localhost:8000` |

## Links

- GitHub: https://github.com/mnemox-ai/tradememory-protocol
- PyPI: https://pypi.org/project/tradememory-protocol/
- Tutorial: https://github.com/mnemox-ai/tradememory-protocol/blob/master/docs/TUTORIAL.md
- Demo: `python scripts/demo.py` (30 simulated trades, full L1→L2→L3 pipeline)

## Related Skills

| Skill | Path | Description |
|-------|------|-------------|
| Strategy Validator | `.skills/strategy-validator/SKILL.md` | Validate trading strategies for overfitting using 4 statistical tests (DSR, Walk-Forward, Regime, CPCV). Use when the user says "validate my strategy", "check my backtest", or "is this overfitting?". |
