# Getting Started with TradeMemory

Choose your path:

- **[Trader Track](#trader-track)** — I use Claude to help with trading decisions
- **[Developer Track](#developer-track)** — I'm building a trading bot or agent

---

## Trader Track

For traders using Claude Desktop or Claude Code. No coding required.

### 1. Install (30 seconds)

```bash
pip install tradememory-protocol
```

Add to your Claude Desktop config (`claude_desktop_config.json`):

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

Restart Claude Desktop. TradeMemory is now connected.

<details>
<summary>Other platforms (Claude Code, Cursor, Windsurf)</summary>

```bash
# Claude Code
claude mcp add tradememory -- uvx tradememory-protocol

# Cursor — add to .cursor/mcp.json
# Windsurf — add to Windsurf MCP config
# All platforms: run `tradememory config` for your exact snippet
```

</details>

### 2. Your First Trade Memory (2 minutes)

**Before trading** — ask what happened last time:

> "I'm thinking about buying AAPL. Have I traded AAPL before? What happened?"

Claude checks your memory and returns past trades in similar conditions — what you did, why, and whether it worked.

**Check your state:**

> "How's my trading state right now? Am I on a losing streak?"

Claude returns your confidence level, current drawdown, and a recommendation (normal / reduce size / stop trading).

**After a completed trade** — record it:

> "Record this trade: I bought 100 shares of AAPL at $195 and sold at $205 for a $1,000 profit. Reason: earnings beat expectations and institutional buying volume was high."

One call. Five memory layers update automatically:
- **Episodic** — the full event with context
- **Semantic** — updates your AAPL strategy win rate belief
- **Procedural** — updates average hold time and position sizing
- **Affective** — updates confidence, tracks the win streak
- **Audit** — SHA-256 hashed record of the decision

### 3. Your Pre-Flight Checklist

Based on how real users run TradeMemory in production:

```
Before every trade:
  1. "What happened in similar conditions?"
  2. "What's my current trading state?"
  3. "Should I take this trade?"
     → The system returns: full size / reduced size / skip

After every trade:
  4. "Record this trade with full context"

Daily:
  5. "Run my daily trading review"

Weekly:
  6. "Give me my weekly strategy breakdown"
```

<details>
<summary>Technical: which MCP tools power each step</summary>

| Step | MCP Tool / REST Endpoint |
|------|--------------------------|
| 1 | `recall_memories` |
| 2 | `get_agent_state` |
| 3 | `check_trade_legitimacy` |
| 4 | `remember_trade` |
| 5 | REST: `/reflect/run_daily` |
| 6 | REST: `/reflect/run_weekly` |

</details>

If any pre-flight check returns a red flag — high drawdown, bad streak, low legitimacy score — pause and review before trading.

### 4. Tips

- **Be specific with context.** "Bought AAPL because of earnings beat" is better than "Bought AAPL." The more context you give, the better recall works next time.
- **Record losses too.** The system learns more from losses than wins.
- **Check memory before trading, not after.** The biggest value is preventing repeat mistakes.

---

## Developer Track

For developers integrating TradeMemory into trading bots or AI agents.

### 1. Install + Configure

```bash
pip install tradememory-protocol

# Start MCP server
python -m tradememory

# Or via uvx (no install needed)
uvx tradememory-protocol
```

MCP SSE endpoint: `http://localhost:8001/sse`
REST API: `http://localhost:8000`

<details>
<summary>Docker</summary>

```bash
git clone https://github.com/mnemox-ai/tradememory-protocol.git
cd tradememory-protocol
docker compose up -d
```

</details>

### 2. Core Pattern (3 tools)

**Write — record a completed trade:**

```python
# MCP tool: remember_trade
{
  "symbol": "AAPL",
  "direction": "long",
  "entry_price": 195.0,
  "exit_price": 205.0,
  "pnl": 1000.0,
  "strategy_name": "EarningsBreakout",
  "market_context": "Post-earnings gap up, institutional volume spike, RSI 62"
}
# → Writes to all 5 memory layers automatically
```

**Read — recall similar past trades:**

```python
# MCP tool: recall_memories
{
  "symbol": "AAPL",
  "market_context": "Pre-earnings, IV rising, support at 190"
}
# → Returns ranked memories weighted by outcome quality + context similarity
```

**State — check agent health:**

```python
# MCP tool: get_agent_state
# → { "confidence": 0.72, "drawdown_pct": 3.2, "recommended_action": "normal" }
```

### 3. REST API Integration

```bash
# Record a trade decision
curl -X POST http://localhost:8000/trade/record_decision \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "direction": "long", "entry_price": 195.0, "strategy_name": "EarningsBreakout", "market_context": "Post-earnings gap up"}'

# Record outcome
curl -X POST http://localhost:8000/trade/record_outcome \
  -H "Content-Type: application/json" \
  -d '{"trade_id": "...", "exit_price": 205.0, "pnl": 1000.0}'

# Daily reflection
curl -X POST http://localhost:8000/reflect/run_daily

# Weekly reflection
curl -X POST http://localhost:8000/reflect/run_weekly
```

### 4. Full Reference

- [API Reference](API.md) — All 35+ REST endpoints
- [MCP Tools](../README.md#mcp-tools-19) — All 19 MCP tools
- [OWM Framework](OWM_FRAMEWORK.md) — Outcome-Weighted Memory theory
- [Architecture](ARCHITECTURE.md) — System design

---

[Back to README](../README.md) · [Use Cases](USE_CASES.md) · [API Reference](API.md)
