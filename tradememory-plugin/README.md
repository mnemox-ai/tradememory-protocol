# TradeMemory Plugin

Persistent memory + autonomous strategy evolution for AI traders. 200+ trading MCP servers execute. None remember. TradeMemory does.

## Installation

### From GitHub (recommended)

```bash
git clone https://github.com/mnemox-ai/tradememory-plugin.git
claude --plugin-dir ./tradememory-plugin
```

### Manual

Copy the plugin directory into your project or pass it directly:

```bash
claude --plugin-dir /path/to/tradememory-plugin
```

### MCP Server (standalone, no plugin needed)

```bash
pip install tradememory-protocol
claude mcp add tradememory -- uvx tradememory-protocol
```

## Commands

| Command | Description |
|---------|-------------|
| `/record-trade [details]` | Record a completed trade into all 5 OWM memory layers |
| `/recall [context]` | Recall similar past trades, ranked by outcome-weighted score |
| `/performance [strategy]` | Generate strategy performance report with behavioral analysis |
| `/evolve [symbol] [tf] [gens]` | Discover new trading strategies from raw OHLCV data |
| `/daily-review [date]` | AI-powered daily reflection on trades and behavioral patterns |

## Skills

### Trading Memory
| Skill | Description |
|-------|-------------|
| **trading-memory** | OWM architecture, 5 memory types, recall scoring, behavioral baselines |
| **evolution-engine** | LLM-powered strategy discovery, vectorized backtesting, OOS validation |
| **risk-management** | Affective state monitoring, tilt detection, position sizing, behavioral guardrails |

## MCP Tools (17 total)

### Core Memory (2)
- `get_strategy_performance` — Aggregate stats per strategy
- `get_trade_reflection` — Deep-dive into a trade's reasoning

### OWM Cognitive Memory (6)
- `remember_trade` — Store across all 5 OWM memory layers
- `recall_memories` — Outcome-weighted recall
- `get_behavioral_analysis` — Disposition ratio, hold times, Kelly criterion
- `get_agent_state` — Confidence, drawdown, streaks, risk appetite
- `create_trading_plan` — Prospective trading plans
- `check_active_plans` — Evaluate plans against current conditions

### Evolution Engine (5)
- `evolution_fetch_market_data` — Fetch OHLCV from Binance
- `evolution_discover_patterns` — LLM-powered pattern discovery
- `evolution_run_backtest` — Vectorized backtesting
- `evolution_evolve_strategy` — Full evolution loop
- `evolution_get_log` — Evolution history and graveyard

### Decision Audit Trail (2)
- `export_audit_trail` — Export decision records with SHA-256 tamper detection
- `verify_audit_hash` — Verify integrity of a decision record

## Example Workflows

### Record and Learn
```
/record-trade XAUUSD long 5180 5210 +$150

# Stores trade, updates all memory layers, shows similar past trades
```

### Pre-Trade Check
```
/recall London session breakout, high volatility, XAUUSD trending up

# Returns past trades in similar conditions, ranked by P&L outcome
```

### Strategy Evolution
```
/evolve BTCUSDT 1h 3

# Discovers patterns → backtests → selects → mutates × 3 generations
# Validates out-of-sample → graduates survivors
```

### End of Day
```
/daily-review today

# Analyzes today's trades, checks behavioral drift, updates affective state
```

## Requirements

- Python 3.10+
- `pip install tradememory-protocol`
- Optional: `ANTHROPIC_API_KEY` for LLM reflections and Evolution Engine

## Links

- [Plugin repo](https://github.com/mnemox-ai/tradememory-plugin)
- [Core protocol](https://github.com/mnemox-ai/tradememory-protocol)
- [PyPI](https://pypi.org/project/tradememory-protocol/)
- [Tutorial](https://github.com/mnemox-ai/tradememory-protocol/blob/master/docs/TUTORIAL.md)
