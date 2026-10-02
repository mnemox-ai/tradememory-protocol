---
name: tradememory
slug: tradememory
version: 0.5.6
description: >-
  Memory and a brake for AI trading agents. 20 MCP tools: outcome-weighted
  recall, behavioral drift alerts, tamper-evident audit chain. Optional proxy
  that sits between your agent and your broker's MCP server (Alpaca today) and
  refuses orders outside a policy you own.
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
        ANTHROPIC_API_KEY: "Optional. Enables LLM reflections and the Evolution Engine; rule-based fallback without it."
        TRADEMEMORY_DB: "Optional. Path of the SQLite database, defaults to ~/.tradememory/tradememory.db"
    os: ["linux", "darwin", "win32"]
    homepage: https://github.com/mnemox-ai/tradememory-protocol
---

# TradeMemory Protocol

Two things for an agent that trades:

1. **Memory.** Record every trade with one call, recall past trades weighted by
   how they turned out, and get told when you are tilting: losing streaks,
   oversized positions after a loss, drawdown past your own line. Every
   record is SHA-256 chained and anchored daily to an RFC 3161 timestamp
   authority, so a changed record is detectable without trusting our clock.
2. **A brake (preview).** Run the proxy between your agent and your broker's
   MCP server. Orders are evaluated against your policy before they reach the
   broker; refusals, approvals and replays are all recorded. Alpaca is the
   first broker. See "Brake" below.

Local-first: SQLite on your machine, no telemetry, no hosted account needed.
MIT licensed, 1,500+ tests, CI on Python 3.10 to 3.12.

## Installation

```bash
pip install tradememory-protocol
# brake preview (Python 3.12+):
pip install "tradememory-protocol[proxy]"
```

Verify: `tradememory doctor`.

## Setup

### Claude Desktop

```json
{
  "mcpServers": {
    "tradememory": { "command": "uvx", "args": ["tradememory-protocol"] }
  }
}
```

### Claude Code

```bash
claude mcp add tradememory -- uvx tradememory-protocol
```

### OpenClaw

Use this skill; the server command is `uvx tradememory-protocol` (stdio).

## Brake: put it in front of Alpaca

```bash
tradememory proxy init --account-id <alpaca account id> --symbols AAPL,MSFT
tradememory proxy doctor --env-file ~/.secrets/alpaca-paper.env   # checks tool names and the account id
tradememory proxy config                                           # the MCP entry that replaces the direct Alpaca one
```

Then point the agent at `tradememory proxy run --policy ... --env-file ...`
instead of `uvx alpaca-mcp-server`. The agent sees all of Alpaca's tools plus
`recall_memories`, `get_behavioral_analysis`, `get_agent_state`, `brake_status`.

Refused by default: symbols outside your list, orders above your notional or
position limits, entries without a bracket stop, new orders after your daily
loss or drawdown limit, and everything after `tradememory proxy halt FULL_HALT`.
Never blocked: closing a position. Orders at or above `approval_notional`
wait for `tradememory proxy approve <intent_id>`; the agent retries with the
same `client_order_id` and the proxy forwards it exactly once. Anything the
brake cannot evaluate is refused, not passed through. Full walkthrough with
real outputs: `docs/recipes/alpaca-brake.md`.

## MCP tools (20)

| Group | Tools |
|---|---|
| Memory | `remember_trade`, `recall_memories`, `get_trade_reflection`, `get_strategy_performance` |
| State and behaviour | `get_agent_state`, `get_behavioral_analysis`, `check_trade_legitimacy`, `compute_dqs` |
| Plans | `create_trading_plan`, `check_active_plans` |
| Audit | `export_audit_trail`, `verify_audit_hash`, `verify_audit_chain`, `get_daily_root` |
| Validation | `validate_strategy` (deflated Sharpe, walk-forward, regime, CPCV) |
| Evolution (research-stage) | `evolution_fetch_market_data`, `evolution_discover_patterns`, `evolution_run_backtest`, `evolution_evolve_strategy`, `evolution_get_log` |

The Evolution Engine and the DQS gate are research-stage: see
`LIMITATIONS.md` for what has and has not survived validation before you trust
either for a trading decision.

## Things to say to your agent

> "Record my AAPL long at 195, earnings beat, high confidence."

> "Before I buy AAPL again: what happened last time in this condition?"

> "Am I on tilt? Check my state and my sizing after losses."

> "Verify the audit chain."

> "What does the brake refuse right now?" (`brake_status`, proxy only)

## Security and permissions

- **Network at runtime:** the MCP server runs on stdio with no outbound calls
  except the daily RFC 3161 timestamp request (configurable) and, if you set
  `ANTHROPIC_API_KEY`, reflection calls to the Anthropic API. The Evolution
  Engine fetches OHLCV from Binance's public API when you use it.
- **Broker keys:** the brake reads the env file you name and passes it only
  to the broker process it starts (`uvx alpaca-mcp-server`). It never writes
  keys to disk or to the database.
- **Files:** one SQLite database (`TRADEMEMORY_DB`), a policy file and a small
  state file under `~/.tradememory/`.
- **No implicit permissions:** no dependency auto-install, no system files,
  no elevation.

## Links

- GitHub: https://github.com/mnemox-ai/tradememory-protocol
- PyPI: https://pypi.org/project/tradememory-protocol/
- Brake recipe: https://github.com/mnemox-ai/tradememory-protocol/blob/master/docs/recipes/alpaca-brake.md
- Limitations: https://github.com/mnemox-ai/tradememory-protocol/blob/master/LIMITATIONS.md
- Help putting it in front of your broker: https://github.com/mnemox-ai/tradememory-protocol/issues/new?template=brake_integration.yml

## Related skills

| Skill | Path | Description |
|-------|------|-------------|
| Strategy Validator | `.skills/strategy-validator/SKILL.md` | Validate a backtest for overfitting with four statistical tests. Use when the user says "validate my strategy" or "is this overfitting?". |
