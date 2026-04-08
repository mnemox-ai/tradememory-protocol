<!-- mcp-name: io.github.mnemox-ai/tradememory-protocol -->

<p align="center">
  <img src="assets/header.png" alt="TradeMemory Protocol" width="600">
</p>

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/tradememory-protocol?style=flat-square&color=blue)](https://pypi.org/project/tradememory-protocol/)
[![Tests](https://img.shields.io/badge/tests-1%2C324_passed-brightgreen?style=flat-square)](https://github.com/mnemox-ai/tradememory-protocol/actions)
[![MCP Tools](https://img.shields.io/badge/MCP_tools-17-blueviolet?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
[![Smithery](https://img.shields.io/badge/Smithery-listed-orange?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)

[Getting Started](docs/GETTING_STARTED.md) | [Use Cases](docs/USE_CASES.md) | [API Reference](docs/API.md) | [OWM Framework](docs/OWM_FRAMEWORK.md) | [中文版](docs/README_ZH.md)

</div>

---

**Your trading AI has amnesia. And regulators are starting to notice.**

It makes the same mistakes every session. It can't explain why it traded. It forgets everything when the context window ends. Meanwhile, MiFID II is raising the bar for algorithmic decision documentation ([Article 17](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32014L0065)). The EU AI Act demands systematic logging of AI actions ([Article 14](https://eur-lex.europa.eu/eli/reg/2024/1689)). Your competitors' agents are learning from every trade.

The AI trading stack is missing a layer. Every MCP server handles execution — placing orders, fetching prices, reading charts. **None handle memory.**

Your agent can buy 100 shares of AAPL but can't answer: *"What happened last time I bought AAPL in this condition?"*

**TradeMemory is the memory layer.** One `pip install`, and your AI agent remembers every trade, every outcome, every mistake — with SHA-256 tamper-proof audit trail.

Used in production by traders running pre-flight checklists before every position, and by EA systems logging thousands of decisions daily.

## What it does

- **Before trading:** ask your memory — what happened last time in this market condition? How did it end?
- **After trading:** one call records everything — five memory layers update automatically
- **Safety rails:** confidence tracking, drawdown alerts, losing streak detection — the system tells you when to stop

Works with any market (stocks, forex, crypto, futures), any broker, any AI platform. TradeMemory doesn't execute trades or touch your money — it only records and recalls.

## Quick Start

```bash
pip install tradememory-protocol
```

Add to Claude Desktop (`claude_desktop_config.json`):

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

Then tell Claude: *"Record my AAPL long at $195 — earnings beat, institutional buying, high confidence."*

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

**Full walkthrough:** [Getting Started](docs/GETTING_STARTED.md) (Trader Track + Developer Track)

## Who uses TradeMemory

| | US Equity Trader | Forex EA System | Compliance Team |
|---|---|---|---|
| **Market** | Stocks (AAPL, TSLA, ...) | XAUUSD (Gold) | Multi-asset |
| **How** | Pre-flight checklist before every trade | Automated sync from MT5 | Full decision audit trail |
| **Key value** | Discipline system — memory before every decision | Record why signals were blocked, not just executed | SHA-256 tamper-proof records for regulators |
| **Details** | [Read more →](docs/USE_CASES.md#case-1-us-equity-trader--pre-flight-workflow) | [Read more →](docs/USE_CASES.md#case-2-forex-ea-system--automated-memory-loop) | [Read more →](docs/USE_CASES.md#case-3-compliance-first-fund--audit-trail) |

## How it works

<p align="center">
  <img src="assets/owm-factors.png" alt="OWM 5 Factors" width="900">
</p>

1. **Recall** — Before trading, retrieve past trades weighted by outcome quality, context similarity, recency, confidence, and emotional state ([OWM Framework](docs/OWM_FRAMEWORK.md))
2. **Record** — After trading, one call to `remember_trade` writes to five memory layers: episodic, semantic, procedural, affective, and trade records
3. **Reflect** — Daily/weekly/monthly reviews detect behavioral drift, strategy decay, and trading mistakes
4. **Audit** — Every decision is SHA-256 hashed at creation. Export anytime for review or regulatory submission

### MCP Tools

| Category | Tools | Description |
|----------|-------|-------------|
| **Memory** | `remember_trade` · `recall_memories` | Record and recall trades with outcome-weighted scoring |
| **State** | `get_agent_state` · `get_behavioral_analysis` | Confidence, drawdown, streaks, behavioral patterns |
| **Planning** | `create_trading_plan` · `check_active_plans` | Prospective plans with conditional triggers |
| **Risk** | `check_trade_legitimacy` | 5-factor pre-trade gate (full / reduced / skip) |
| **Audit** | `export_audit_trail` · `verify_audit_hash` | SHA-256 tamper detection + bulk export |

<details>
<summary>All 17 MCP tools + REST API</summary>

| Category | Tools |
|----------|-------|
| **Core Memory** | `get_strategy_performance` · `get_trade_reflection` |
| **OWM Cognitive** | `remember_trade` · `recall_memories` · `get_behavioral_analysis` · `get_agent_state` · `create_trading_plan` · `check_active_plans` |
| **Risk & Governance** | `check_trade_legitimacy` · `validate_strategy` |
| **Evolution** | `evolution_fetch_market_data` · `evolution_discover_patterns` · `evolution_run_backtest` · `evolution_evolve_strategy` · `evolution_get_log` |
| **Audit** | `export_audit_trail` · `verify_audit_hash` |

**REST API:** 35+ endpoints for trade recording, reflections, risk, MT5 sync, OWM, evolution, and audit. [Full reference →](docs/API.md)

</details>

## Pricing

| | Community | Pro | Enterprise |
|---|---|---|---|
| **Price** | **Free** | **$29/mo** (Coming Soon) | **Contact Us** |
| MCP tools | 17 tools | 17 tools | 17 tools |
| Storage | SQLite, self-hosted | Hosted API | Private deployment |
| Dashboard | — | Web dashboard | Custom dashboard |
| Compliance | Audit trail included | Audit trail included | Compliance reports + SLA |
| Support | GitHub Issues | Priority support | Dedicated support |
| | [Get Started →](docs/GETTING_STARTED.md) | *Coming soon* | [dev@mnemox.ai](mailto:dev@mnemox.ai) |

### Need Help Integrating?

Building a trading AI agent and want battle-tested memory architecture?

**Free 30-min strategy call** — we'll map your agent's memory needs and design guardrails for your specific workflow.

[dev@mnemox.ai](mailto:dev@mnemox.ai) | [Book a call](https://calendly.com/johnson90207/30min)

> *We've helped traders build pre-flight checklists, connect MT5/Binance, and design custom guardrails for forex, equities, and crypto.*

## Enterprise & Compliance

Every trading decision your agent makes — including decisions **not** to trade — is recorded as a Trading Decision Record (TDR), SHA-256 hashed at creation for tamper detection.

| Regulation | Requirement | TradeMemory Coverage |
|------------|-------------|---------------------|
| MiFID II Article 17 | Record every algorithmic trading decision factor | Full decision chain: conditions, filters, indicators, execution |
| EU AI Act Article 14 | Human oversight of high-risk AI systems | Explainable reasoning + memory context for every decision |
| EU AI Act Logging | Systematic logging of every AI action | Automatic per-decision TDR with structured JSON |

```bash
# Verify any record hasn't been tampered with
GET /audit/verify/{trade_id}
# → {"verified": true, "stored_hash": "a3f8c9...", "computed_hash": "a3f8c9..."}

# Bulk export for regulatory submission
GET /audit/export?strategy=VolBreakout&start=2026-03-01&format=jsonl
```

**Need a custom deployment for your fund?** → [dev@mnemox.ai](mailto:dev@mnemox.ai)

## Security

- **Never touches API keys.** TradeMemory does not execute trades, move funds, or access wallets.
- **Read and record only.** Your agent passes decision context to TradeMemory. It stores it. That's it.
- **No external network calls.** The server runs locally. No data is sent to third parties.
- **SHA-256 tamper detection.** Every record is hashed at creation. Verify integrity anytime.
- **1,324 tests passing.** Full test suite with CI.

## Research Status

TradeMemory's OWM framework is grounded in cognitive science (Tulving 1972)
and reinforcement learning (Schaul et al. 2015). Current status:

- **OWM five-factor scoring:** implemented, tested (1,300+ tests)
- **Statistical validation:** DSR, MBL implemented (Bailey-de Prado 2014)
- **Audit trail:** SHA-256 tamper-proof TDR
- **Evolution engine:** research phase (strategy generation works, statistical gate pass rate under optimization)
- **Hybrid recall:** OWM-only mode active, vector fusion available when embeddings configured
- **Empirical validation:** ongoing (n=40 trades, target n>=100 for statistical significance)

## Documentation

| Doc | Description |
|-----|-------------|
| [Getting Started](docs/GETTING_STARTED.md) | Install → first trade → pre-flight checklist |
| [Use Cases](docs/USE_CASES.md) | 3 real-world production scenarios |
| [API Reference](docs/API.md) | All REST endpoints |
| [OWM Framework](docs/OWM_FRAMEWORK.md) | Outcome-Weighted Memory theory |
| [Architecture](docs/ARCHITECTURE.md) | System design & layer separation |
| [Tutorial](docs/TUTORIAL.md) | Detailed walkthrough |
| [MT5 Setup](docs/MT5_SYNC_SETUP.md) | MetaTrader 5 integration |
| [Research Log](docs/RESEARCH_LOG.md) | Evolution experiments & data |
| [Failure Taxonomy](docs/trading-ai-failure-taxonomy.md) | 11 trading AI failure modes |
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
