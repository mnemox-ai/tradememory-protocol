<!-- mcp-name: io.github.mnemox-ai/tradememory-protocol -->

<p align="center">
  <img src="assets/header.png" alt="TradeMemory Protocol" width="600">
</p>

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/tradememory-protocol?style=flat-square&color=blue)](https://pypi.org/project/tradememory-protocol/)
[![Tests](https://img.shields.io/badge/tests-1%2C087_passed-brightgreen?style=flat-square)](https://github.com/mnemox-ai/tradememory-protocol/actions)
[![MCP Tools](https://img.shields.io/badge/MCP_tools-15-blueviolet?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
[![Smithery](https://img.shields.io/badge/Smithery-listed-orange?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)

[Tutorial](docs/TUTORIAL.md) | [API Reference](docs/API.md) | [OWM Framework](docs/OWM_FRAMEWORK.md) | [中文版](docs/README_ZH.md)

</div>

---

TradeMemory Protocol is an MCP server that gives AI trading agents persistent memory across sessions. Instead of forgetting every trade after each conversation, your agent stores decisions, discovers patterns, and adjusts strategy automatically — using a three-layer architecture inspired by ACT-R cognitive science.

**When to use this:** You're building an AI agent that trades forex, crypto, or equities via MT5, Binance, Alpaca, or any platform — and you want it to remember what worked, what didn't, and why.

## How it works

1. **Store** — Your agent records trades with context (strategy, confidence, market regime) via MCP tools
2. **Recall** — Before the next trade, the agent retrieves similar past trades weighted by outcome (Outcome-Weighted Memory)
3. **Evolve** — The Evolution Engine discovers patterns across trades and generates new strategy hypotheses, validated with Deflated Sharpe Ratio

## When to use TradeMemory vs alternatives

| | TradeMemory | Raw Mem0/Qdrant | LangChain Memory | Custom SQLite |
|---|---|---|---|---|
| **Trade-specific schema** | ✅ L1→L2→L3 pipeline | ❌ Generic vectors | ❌ Chat-oriented | ❌ DIY everything |
| **Outcome weighting** | ✅ Kelly + ACT-R | ❌ Cosine only | ❌ Recency only | ❌ Manual |
| **Strategy evolution** | ✅ Built-in engine | ❌ Not included | ❌ Not included | ❌ Not included |
| **MCP native** | ✅ 15 tools | ❌ Custom wrapper | ❌ Custom wrapper | ❌ Custom wrapper |
| **Statistical validation** | ✅ DSR + walk-forward | ❌ None | ❌ None | ❌ None |

## News

- [2026-03] **Onboarding CLI** — `tradememory setup` wizard, `doctor` health check, 8-platform config generator
- [2026-03] **v0.5.0** — Evolution Engine + OWM 5 memory types. 1,087 tests. [Release Notes](https://github.com/mnemox-ai/tradememory-protocol/releases/tag/v0.5.0)
- [2026-03] **Statistical Validation** — Strategy E passes P100% random baseline, Sharpe 3.24 walk-forward
- [2026-03] **Live Paper Trading** — Strategy E running on Binance via GitHub Actions (hourly)
- [2026-02] **v0.4.0** — OWM Framework, 15 MCP tools, Smithery + Glama listed

## Architecture

<p align="center">
  <img src="assets/schema.png" alt="Architecture" width="900">
</p>

## Three-Layer Memory

<p align="center">
  <img src="assets/memory-pipeline.png" alt="L1 L2 L3 Memory Pipeline" width="900">
</p>

## Quick Start

```bash
pip install tradememory-protocol
```

Add to `claude_desktop_config.json`:

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

Then tell Claude: *"Record my BTCUSDT long at 71,000 — momentum breakout, high confidence."*

<details>
<summary>Claude Code / Cursor / Docker</summary>

```bash
# Claude Code
claude mcp add tradememory -- uvx tradememory-protocol

# From source
git clone https://github.com/mnemox-ai/tradememory-protocol.git
cd tradememory-protocol && pip install -e . && python -m tradememory

# Docker
docker compose up -d
```

</details>

## Setup & Configuration

First-time guided setup:

```bash
tradememory setup
```

This walks you through:
1. **Terms acceptance** — trading disclaimer and data storage policy
2. **Platform detection** — auto-detects Claude Desktop, Claude Code, Cursor, Windsurf, Cline
3. **Config generation** — prints the exact JSON snippet for your platform
4. **Health check** — verifies database, MCP tools, and core functionality

### Platform Configs

Generate config for any supported platform:

```bash
tradememory config              # interactive menu
tradememory config claude_code  # direct: auto-installs via CLI
tradememory config cursor       # prints .cursor/mcp.json snippet
tradememory config windsurf     # prints Windsurf config
tradememory config raw_json     # generic MCP JSON
```

Supported: Claude Desktop · Claude Code · Cursor · Windsurf · Cline · Smithery · Docker

### Health Check

```bash
tradememory doctor        # core checks (~3s)
tradememory doctor --full # + REST API, MT5, Anthropic API
```

## MCP Tools (15)

| Category | Tools |
|----------|-------|
| **Core Memory** | `store_trade_memory` · `recall_similar_trades` · `get_strategy_performance` · `get_trade_reflection` |
| **OWM Cognitive** | `remember_trade` · `recall_memories` · `get_behavioral_analysis` · `get_agent_state` · `create_trading_plan` · `check_active_plans` |
| **Evolution** | `evolution_run` · `evolution_status` · `evolution_results` · `evolution_compare` · `evolution_config` |

<details>
<summary>REST API (30+ endpoints)</summary>

Trade recording, outcome logging, history, reflections, risk constraints, MT5 sync, OWM, evolution.

Full reference: [docs/API.md](docs/API.md)

</details>

## OWM — Outcome-Weighted Memory

<p align="center">
  <img src="assets/owm-factors.png" alt="OWM 5 Factors" width="900">
</p>

> Full theoretical foundation: [OWM Framework](docs/OWM_FRAMEWORK.md)

## Evolution Engine

<p align="center">
  <img src="assets/evolution.png" alt="Evolution Engine" width="900">
</p>

> Methodology & data: [Research Log](docs/RESEARCH_LOG.md)

## Documentation

| Doc | Description |
|-----|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design & layer separation |
| [OWM Framework](docs/OWM_FRAMEWORK.md) | Full theoretical foundation |
| [Tutorial](docs/TUTORIAL.md) | Install → first trade → memory recall |
| [API Reference](docs/API.md) | All REST endpoints |
| [MT5 Setup](docs/MT5_SYNC_SETUP.md) | MetaTrader 5 integration |
| [Research Log](docs/RESEARCH_LOG.md) | 11 evolution experiments |
| [Roadmap](docs/ROADMAP.md) | Development roadmap |
| [中文版](docs/README_ZH.md) | Traditional Chinese |

## Contributing

See [Contributing Guide](.github/CONTRIBUTING.md) · [Security Policy](.github/SECURITY.md)

<a href="https://star-history.com/#mnemox-ai/tradememory-protocol&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=mnemox-ai/tradememory-protocol&type=Date&theme=dark" />
   <img alt="Star History" src="https://api.star-history.com/svg?repos=mnemox-ai/tradememory-protocol&type=Date" width="600" />
 </picture>
</a>

---

MIT — see [LICENSE](LICENSE). For educational/research purposes only. Not financial advice.

<div align="center">Built by <a href="https://mnemox.ai">Mnemox</a></div>
