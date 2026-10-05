# TradeMemory

TradeMemory remembers what it cost. It is a local-first memory and brake for AI trading agents: it keeps the trades you record or sync, puts your losing trades from similar conditions in front of the agent before the next order, finds where your own history loses money, and lets you approve rules that a broker brake then enforces.

This plugin adds the TradeMemory MCP server and the skills and commands that use it. The server runs on your machine; your trades are stored in a local SQLite database.

## What it runs, sends and fetches

- **Starts** `uvx tradememory-protocol==0.6.0`, which downloads that exact version of the open-source [tradememory-protocol](https://pypi.org/project/tradememory-protocol/) package from PyPI and runs it as a local stdio MCP server. Source: https://github.com/mnemox-ai/tradememory-protocol (MIT).
- **Stores** everything in `~/.tradememory/` on your machine. Nothing is sent to Mnemox; there is no telemetry.
- **Network calls the server can make**, each only when you use the matching tool:
  - `get_daily_root` sends one 32-byte daily hash of your audit records to the timestamp authority at `https://freetsa.org/tsr` (set `TRADEMEMORY_TSA=off` to stop it, or `TRADEMEMORY_TSA_URL` to use another). No trade data is sent.
  - `evolution_fetch_market_data` fetches public price candles from `https://api.binance.com`.
  - The `evolution_*` pattern discovery and LLM reflections call Anthropic or DeepSeek only if you have set your own `ANTHROPIC_API_KEY` or `DEEPSEEK_API_KEY` in your environment.
- **Command line, not the plugin**: `tradememory sync hyperliquid` reads public fills from `https://api.hyperliquid.xyz/info`; `tradememory sync alpaca` and the brake call Alpaca's API with keys you keep in a local file.

## Commands

| Command | What it does |
|---|---|
| `/recall [symbol] [conditions]` | Recalls your losing trades from similar conditions first, before an order |
| `/sync-history [hyperliquid <address> \| alpaca]` | Pulls a venue's fills into memory and reads back where the history loses money |
| `/record-trade [details]` | Records a finished trade in memory |
| `/performance [strategy]` | Performance per strategy from recorded trades |
| `/daily-review [date]` | Reflection on recent trades |
| `/evolve [symbol] [timeframe] [generations]` | Strategy discovery from price candles (needs an LLM key) |

## Skills

- **history-and-rules**: sync, the "sizing up after losses" check, rules you approve, and the broker brake.
- **trading-memory**: how memories are stored and recalled.
- **risk-management**: agent state, drawdown and streaks.
- **evolution-engine**: the strategy discovery loop.

## Rules and the brake

When a sync finds that you size up right after two losses in a row more often than you usually do, and those trades lost money, it proposes a rule. The rule does nothing until you run `tradememory rules approve <id>` yourself. The brake (`pip install "tradememory-protocol[proxy]"`, Python 3.12+, preview) then holds new orders at or above that size after two losses in a row, before they reach Alpaca. Details: [README](https://github.com/mnemox-ai/tradememory-protocol#rules-from-your-own-history).

Everything TradeMemory reports is descriptive statistics of your own past trades, not investment advice.

## Requirements

- [uv](https://docs.astral.sh/uv/) for `uvx`, and Python 3.10+ (3.12+ for the brake)
- Claude Code for the command line steps (`/sync-history`, rules, brake)
