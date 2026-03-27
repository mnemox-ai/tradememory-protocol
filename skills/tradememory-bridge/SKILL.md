---
name: tradememory-bridge
description: |
  Bridge between Binance trading events and TradeMemory Protocol.
  Automatically journals trades, recalls similar past setups, detects behavioral biases,
  and provides outcome-weighted recall for AI trading agents.
  Use this skill after executing Binance spot trades to build persistent memory.
metadata:
  version: "1.0"
  author: mnemox-ai
license: MIT
---

# TradeMemory Bridge for Binance

Store Binance spot trades into persistent memory. Recall similar past trades before entering new positions. Detect behavioral biases (overtrading, revenge trading). Track strategy performance across sessions.

**Requires**: [TradeMemory Protocol](https://github.com/mnemox-ai/tradememory-protocol) MCP server running.

## Setup

Install and start the TradeMemory MCP server:

```bash
pip install tradememory-protocol
python -m tradememory
```

Or add to Claude Desktop / Claude Code MCP config:

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

## Workflow

After executing a Binance spot trade using the Binance Spot skill:

1. **Store the trade** using `remember_trade` MCP tool
2. **Before next trade**, recall similar past trades using `recall_memories` MCP tool
3. **Check agent state** using `get_agent_state` to see if drawdown or confidence suggests pausing
4. **Review behaviors** using `get_behavioral_analysis` to detect biases

## MCP Tools Reference

### remember_trade

Store a completed trade into memory. Automatically updates all memory layers.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| symbol | string | Yes | Trading pair (e.g. "BTCUSDT", "ETHUSDT") |
| direction | string | Yes | "long" or "short" |
| entry_price | number | Yes | Entry price |
| exit_price | number | Yes | Exit price |
| pnl | number | Yes | Profit/loss in account currency |
| strategy_name | string | Yes | Strategy name (e.g. "GridBreakout", "MeanReversion") |
| market_context | string | Yes | Natural language description of market conditions |
| pnl_r | number | No | P&L as R-multiple (risk units) |
| context_regime | string | No | Market regime: trending_up, trending_down, ranging, volatile |
| confidence | number | No | Confidence level 0-1 (default 0.5) |
| reflection | string | No | Lessons learned from this trade |

**Example — after a Binance spot BUY→SELL cycle:**

```
Call remember_trade with:
  symbol: "BTCUSDT"
  direction: "long"
  entry_price: 87500.00
  exit_price: 89200.00
  pnl: 170.00
  strategy_name: "BreakoutEntry"
  market_context: "BTC broke above 87000 resistance with volume spike. Funding rate positive. 4H RSI was 62."
  context_regime: "trending_up"
  confidence: 0.7
  reflection: "Entry timing was good. Could have held longer — exited at first pullback."
```

### recall_memories

Before entering a new trade, recall past trades in similar market conditions. Returns scored results ranked by outcome quality and context similarity.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| symbol | string | Yes | Trading pair to filter by |
| market_context | string | Yes | Current market conditions (natural language) |
| context_regime | string | No | Current regime: trending_up, trending_down, ranging, volatile |
| strategy_name | string | No | Filter by strategy |
| limit | number | No | Max results (default 10) |

**Example — before entering a new BTC trade:**

```
Call recall_memories with:
  symbol: "BTCUSDT"
  market_context: "BTC consolidating near 90000 after rally. Volume declining. Funding rate turning negative."
  context_regime: "ranging"
  strategy_name: "BreakoutEntry"
  limit: 5
```

Returns past trades ranked by relevance to current conditions, with per-trade scores.

### get_agent_state

Check current trading state: confidence, risk appetite, drawdown, win/loss streaks.

**No parameters required.**

Returns a recommended action: `normal`, `reduce_size`, or `stop_trading` based on drawdown severity.

### get_behavioral_analysis

Detect trading biases from historical behavior patterns.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| strategy_name | string | No | Filter by strategy |
| symbol | string | No | Filter by symbol |

Detects: overtrading, revenge trading (re-entry after loss), disposition effect (cutting winners too early, holding losers too long), lot sizing inconsistency.

### get_strategy_performance

Get win rate, profit factor, and aggregate stats per strategy.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| strategy_name | string | No | Filter by strategy |
| symbol | string | No | Filter by symbol |

### create_trading_plan

Set conditional plans that trigger on specific market conditions.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| trigger_type | string | Yes | "market_condition", "drawdown", or "time_based" |
| trigger_condition | string | Yes | JSON describing when to trigger |
| planned_action | string | Yes | JSON describing what to do |
| reasoning | string | Yes | Why this plan was created |

**Example:**

```
Call create_trading_plan with:
  trigger_type: "market_condition"
  trigger_condition: '{"regime": "volatile", "symbol": "BTCUSDT"}'
  planned_action: '{"type": "reduce_size", "factor": 0.5}'
  reasoning: "Historical data shows BreakoutEntry underperforms in volatile BTC regimes"
```

### check_active_plans

Check if any active plans match current market conditions.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| context_regime | string | No | Current market regime |

## Agent Behavior

1. **After every Binance spot trade execution**, call `remember_trade` with full context. Include market conditions, not just price data.
2. **Before entering a new position**, call `recall_memories` to check what happened in similar past conditions.
3. **At session start**, call `get_agent_state` to check if drawdown or losing streaks suggest reducing size.
4. **Periodically**, call `get_behavioral_analysis` to detect emerging biases.
5. **Never skip journaling**. Memory quality depends on consistent recording.
6. **Use natural language** for `market_context`. The richer the description, the better the recall matching.

## Supported Exchanges

TradeMemory Protocol is exchange-agnostic. While this skill documents the Binance bridge workflow, the same MCP tools work with any trading data source — just pass the correct symbol format for your exchange.

## Notes

1. All timestamps are UTC (ISO 8601 format).
2. `pnl_r` (R-multiple) is optional but significantly improves recall quality.
3. The `context_regime` field enables regime-filtered recall — strongly recommended.
4. TradeMemory stores data locally by default (SQLite). No data is sent to external servers unless you configure a hosted endpoint.
5. All 17 MCP tools are free and open source under MIT license.
