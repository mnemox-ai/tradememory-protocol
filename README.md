<!-- mcp-name: io.github.mnemox-ai/tradememory-protocol -->

<p align="center">
  <img src="assets/header.png" alt="TradeMemory Protocol" width="600">
</p>

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/tradememory-protocol?style=flat-square&color=blue)](https://pypi.org/project/tradememory-protocol/)
[![Tests](https://img.shields.io/github/actions/workflow/status/mnemox-ai/tradememory-protocol/ci.yml?branch=master&style=flat-square&label=tests)](https://github.com/mnemox-ai/tradememory-protocol/actions/workflows/ci.yml)
[![MCP Tools](https://img.shields.io/badge/MCP_tools-20-blueviolet?style=flat-square)](https://smithery.ai/server/mnemox-ai/tradememory-protocol)
[![Smithery](https://img.shields.io/badge/Smithery-listed-orange?style=flat-square)](https://smithery.ai/server/mnemox-ai/tradememory-protocol)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)

[Getting Started](docs/GETTING_STARTED.md) | [Use Cases](docs/USE_CASES.md) | [API Reference](docs/API.md) | [OWM Framework](docs/OWM_FRAMEWORK.md) | [Limitations](LIMITATIONS.md) | [中文版](docs/README_ZH.md)

</div>

---

**TradeMemory remembers what it cost.** It is an open-source, local-first memory and brake for AI trading agents: it pulls in your fills, finds where your own history loses money, puts those losing trades in front of your agent before the next order, and can refuse an order that breaks rules you set, before it reaches the broker.

Brokers now let AI agents trade over MCP, with different guardrails: Webull and tastytrade set size or buying-power limits, Interactive Brokers only lets the agent draft an order for you to submit, and Robinhood and Public set no cap you can impose on an external agent ([StockBrokers, 2026-09-30](https://www.stockbrokers.com/guides/ai-agent-brokers)). The caps are fixed numbers. None of them looks at how your own past trades went.

## Start with your own history

```bash
pip install tradememory-protocol

# Hyperliquid: public fills, no key needed
tradememory sync hyperliquid --address 0xYourAddress

# Alpaca: read-only calls with your own keys, kept in a local file
tradememory sync alpaca --env-file ~/.secrets/alpaca.env
```

Each closed trade is stored in memory once; running it again stores only new trades. Then it prints where your history loses money. The format, with illustrative numbers:

```
After 2 losses in a row (20 trades):
  9 of them (45%) were 1.5x your usual size or more (across all your trades: 25%).
  That is more often than usual.
  All 20 won 50% and made -$1,500.
  The 9 sized-up trades won 22% and made -$2,100.

Median hold: winners 1.5h, losers 9.0h.

Suggested rule (does nothing until you approve it):
  After 2 losses in a row, orders that take a position to $1,500 or more are held for your approval.
  To turn it on: tradememory rules approve r-3f2a9c1e5b [--max-notional N] (the brake enforces it on its next order)
```

These are descriptive statistics of your own past trades, not advice about the next one. Hyperliquid's API serves only an address's recent fills, not its whole history, so the sooner it is synced, the more history is kept. Other venues: MT5 and Binance spot sync scripts are in `scripts/`, and any agent can record a trade with `remember_trade`.

## Rules from your own history

A sync suggests a rule only when your history calls for one: you size up right after two losses in a row more often than you size up at all (a one-sided binomial test against your own rate gives p ≤ 0.10, and the difference is at least 5 points), and those bigger trades lost money in total. The limit is the size the report calls "sized up", 1.5 times your median trade. Most histories do not call for one. On 2026-10-05, none of 18 high-volume Hyperliquid accounts we sampled did; among 70 smaller accounts (US$5k to 200k of monthly volume), 8 of the 51 with enough trades did, by 8 to 36 points.

A suggested rule does nothing until you approve it (`tradememory rules list`, then `tradememory rules approve <id>`, optionally with your own `--max-notional`). From then on the brake checks it on every new order that adds risk: when the account's two latest closed trades are losses and the position the order could leave is at or above the limit, the order waits for your approval like any other escalation, or is refused if you approved the rule with `--action deny`. Two small orders that add up to a big position are held like one big order. The closed trades come from the broker at that moment (its fill history, read through the same MCP server), so a stop that closed a minute ago counts without a sync; if that history cannot be read, an order big enough to trip the rule is refused. Reducing or closing a position is never held, a rule never lets through anything your policy refuses, and an approval you gave before a rule fired does not cover it. A rule edited by hand makes the brake refuse every order until you retire it with `tradememory rules retire <id>`; the check catches careless edits, it is not a signature.

## Before the next order

`recall_memories(order="losses_first")` puts every losing trade ahead of the rest, the bigger losses in similar conditions first, with their size and P&L. Besides the symbol's most recent trades, it searches the symbol's recent losing trades, so an older loss is not crowded out. The server tells connected agents to call it before proposing a trade. The default order ranks better outcomes higher (by R multiple, where one was recorded) and keeps at least 20% losses in the list.

## Connect your agent

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

## Put a brake in front of your broker (preview)

The `proxy` extra runs TradeMemory between your agent and your broker's MCP server (Alpaca today). Every tool is forwarded unchanged except the order-placing ones, which [Mnemox Control](https://github.com/mnemox-ai/mnemox-control) evaluates against a policy you own before they reach the broker. Every evaluation, allowed or refused, is recorded and chained into the audit log. An allowed order comes back with your losing trades from similar conditions first, and `tradememory sync alpaca` later fills in how each forwarded trade ended, in R when the entry carried a stop. The agent you already have keeps working; only one line of its MCP config changes.

```bash
pip install "tradememory-protocol[proxy]"   # Python 3.12+
tradememory proxy init --account-id <your Alpaca account id> --symbols AAPL,MSFT
tradememory proxy doctor --env-file ~/.secrets/alpaca-paper.env   # checks the live tool names and the account id
tradememory proxy config                                           # prints the MCP client entry that replaces the direct Alpaca one
```

Refused by default: symbols outside your list, orders above your notional and position limits, entries without a bracket stop, any new order after your daily-loss or drawdown limit, cancelling the protective stop of an open position, any tool the brake has not classified, and everything while you have run `tradememory proxy halt FULL_HALT`. Never blocked: closing a position. Orders at or above `approval_notional` wait for `tradememory proxy approve <intent_id> --terms <fingerprint>`, which approves exactly the terms you read; the agent retries with the same `client_order_id` and the same terms, and the proxy forwards it at most once. A rule you approved from your own history (see [Rules from your own history](#rules-from-your-own-history)) holds a new order the same way. `evaluate_order` returns the same decision without placing anything, for pre-checks and for advisory layers in other frameworks. Anything the brake cannot evaluate (a dead quote feed, an unknown asset, an order type the policy does not cover) is refused, not passed through.

Status: tested end-to-end against a stateful fake of Alpaca's MCP server (`tests/proxy/`), and run against a real Alpaca paper account on 2026-10-01: three refusals (symbol not on the list, entry without a stop, notional over the limit), one allowed one-share bracket order that reached the broker, and one retry with the same `client_order_id` that was answered from the record without a second order. Options, order replacement, stop-limit and trailing orders are refused rather than evaluated. Your broker keys go only to the broker process the proxy starts; TradeMemory never stores them.

Walkthrough with the real outputs: [docs/recipes/alpaca-brake.md](docs/recipes/alpaca-brake.md).

## Three ways it is used

| | US equity trader | Forex EA system | Audit trail (illustrative) |
|---|---|---|---|
| **Market** | Stocks (AAPL, TSLA, ...) | XAUUSD (Gold) | Multi-asset |
| **How** | Pre-flight checklist before every trade | Automated sync from MT5 | Decision records with a hash chain |
| **Who** | One independent user (March 2026) | The maintainer's own MT5 account | An example, not a customer |
| **Details** | [Read more](docs/USE_CASES.md#case-1-us-equity-trader--pre-flight-workflow) | [Read more](docs/USE_CASES.md#case-2-forex-ea-system--automated-memory-loop) | [Read more](docs/USE_CASES.md#case-3-compliance-first-fund--audit-trail) |

## How it works

<p align="center">
  <img src="assets/owm-factors.png" alt="OWM 5 Factors" width="900">
</p>

1. **Recall** — Before trading, retrieve past trades weighted by outcome quality, context similarity, recency, confidence, and emotional state ([OWM Framework](docs/OWM_FRAMEWORK.md))
2. **Record** — After trading, one call to `remember_trade` writes to five memory layers: episodic, semantic, procedural, affective, and trade records
3. **Reflect** — Daily/weekly/monthly reviews detect behavioral drift, strategy decay, and trading mistakes
4. **Audit** — Every decision is SHA-256 hashed at creation and chained to the one before. Export anytime for review

### MCP Tools

| Category | Tools | Description |
|----------|-------|-------------|
| **Memory** | `remember_trade` · `recall_memories` | Record and recall trades with outcome-weighted scoring |
| **State** | `get_agent_state` · `get_behavioral_analysis` | Confidence, drawdown, streaks, behavioral patterns |
| **Planning** | `create_trading_plan` · `check_active_plans` | Prospective plans with conditional triggers |
| **Risk** | `check_trade_legitimacy` | 5-factor pre-trade gate (full / reduced / skip) |
| **Audit** | `export_audit_trail` · `verify_audit_hash` | SHA-256 tamper detection + bulk export |

<details>
<summary>All 20 MCP tools + REST API</summary>

| Category | Tools |
|----------|-------|
| **Core Memory** | `get_strategy_performance` · `get_trade_reflection` |
| **OWM Cognitive** | `remember_trade` · `recall_memories` · `get_behavioral_analysis` · `get_agent_state` · `create_trading_plan` · `check_active_plans` |
| **Risk & Governance** | `check_trade_legitimacy` · `validate_strategy` · `compute_dqs` |
| **Evolution** | `evolution_fetch_market_data` · `evolution_discover_patterns` · `evolution_run_backtest` · `evolution_evolve_strategy` · `evolution_get_log` |
| **Audit** | `export_audit_trail` · `verify_audit_hash` · `verify_audit_chain` · `get_daily_root` |

**REST API:** 35+ endpoints for trade recording, reflections, risk, MT5 sync, OWM, evolution, and audit. [Full reference →](docs/API.md)

</details>

## Get help connecting

Running an agent against a broker, or want your history synced and read? [Open a brake-integration issue](https://github.com/mnemox-ai/tradememory-protocol/issues/new?template=brake_integration.yml) or [book 30 minutes](https://calendly.com/johnson90207/30min). Setup help is free, and the people who use it decide what gets built next.

## Audit trail

Every trading decision your agent makes — including decisions **not** to trade — is recorded as a Trading Decision Record (TDR). Per-record SHA-256 content hashes are linked into a forward-chained audit ledger; every UTC day is summarised by a Merkle root which itself chains across days. Tampering with any historical record invalidates every subsequent link.

Rules that require decision records bind investment firms, not retail users. Under the EU AI Act, the Annex III high-risk logging obligations were postponed to 2 December 2027, and ESMA's February 2026 supervisory briefing on algorithmic trading states that AI-based algorithmic trading is currently excluded from the high-risk scope. The table shows which TradeMemory features map to those texts if and when they apply to you. It is not a compliance claim.

| Regulation | Requirement | TradeMemory Coverage |
|------------|-------------|---------------------|
| MiFID II Article 17 | Record every algorithmic trading decision factor | Full decision chain: conditions, filters, indicators, execution |
| EU AI Act Article 14 | Human oversight of high-risk AI systems | Explainable reasoning + memory context for every decision |
| EU AI Act Article 12 | Automatic, tamper-resistant logs over system lifetime | Linked SHA-256 chain + daily Merkle roots (RFC 3161 TSA anchoring, on by default since 0.5.3) |

```bash
# Verify a single record hasn't been tampered with
verify_audit_hash(trade_id="MT5-7047640363")
# → {"verified": true, "chain_entry": {"sequence_num": 42, ...}}

# Walk the entire chain (or a slice) end-to-end
verify_audit_chain(from_seq=1, to_seq=None)
# → {"verified": true, "checked_count": 1284, "first_break_at": null}

# Daily Merkle root — single 32-byte anchor over every TDR for that day
get_daily_root(date="2026-05-14")
# → {"verified": true, "root_hash": "a05544...", "record_count": 18}

# Bulk export
GET /audit/export?strategy=VolBreakout&start=2026-03-01&format=jsonl
```

Daily roots are timestamped by an RFC 3161 authority by default since 0.5.3. Not built: signing records with a private key, anchoring to a public log, proving that nothing was left out. See [LIMITATIONS.md](LIMITATIONS.md).

## Security

- **Memory server (default).** Never places orders and never asks for broker keys. Records and recalls only, in a local SQLite file.
- **Sync.** `tradememory sync hyperliquid` reads public data with no key. `tradememory sync alpaca` makes read-only calls with keys from a file on your machine. Synced trades stay in your local database.
- **Brake (`proxy` extra).** Forwards the orders your policy allows to your broker's MCP server. Your broker keys are passed only to the broker process the proxy starts; TradeMemory never stores them.
- **Outbound calls.** RFC 3161 timestamping of daily audit roots, a 32-byte hash with no trade data (on by default; `TRADEMEMORY_TSA=off` turns it off). `tradememory sync` calls the venue you name. The evolution tools read public Binance market data (`api.binance.com`) when an agent calls them, and evolution calls the Anthropic API only if you set `ANTHROPIC_API_KEY`. Replay calls DeepSeek by default (or Anthropic), and only with that provider's key set. If you install `sentence-transformers` for hybrid recall, it downloads its model from Hugging Face on first use. The MT5 and Binance sync scripts in `scripts/` read their credentials from your environment, and the MT5 one posts trade summaries (symbol, prices, P&L) to a Discord webhook only if you set `DISCORD_WEBHOOK_URL`.
- **Tamper-evident, not tamper-proof.** Every record is hashed and linked to the one before, with daily Merkle roots. Changing a record breaks the chain; someone who can rewrite the whole database can rebuild it.

## Research Status

TradeMemory's OWM framework is grounded in cognitive science (Tulving 1972)
and reinforcement learning (Schaul et al. 2015). Current status:

- **OWM five-factor scoring:** implemented and tested (see the CI badge)
- **Statistical validation:** DSR, MBL implemented (Bailey-de Prado 2014)
- **Audit trail:** SHA-256 tamper-evident TDR
- **Evolution engine:** research phase (strategy generation works, statistical gate pass rate under optimization)
- **Hybrid recall:** OWM-only mode active, vector fusion available when embeddings configured
- **Empirical validation:** ongoing (n=14 trades, target n>=100 for statistical significance; at n=14 the confidence intervals are too wide to conclude anything - see validation/final_verdict.md)

## Documentation

| Doc | Description |
|-----|-------------|
| [Getting Started](docs/GETTING_STARTED.md) | Install → first trade → pre-flight checklist |
| [Use Cases](docs/USE_CASES.md) | 3 usage scenarios, each labelled first-party or independent |
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

MIT, see [LICENSE](LICENSE). The optional `proxy` extra installs [Mnemox Control](https://github.com/mnemox-ai/mnemox-control), whose engine is AGPL-3.0-only (a commercial license is available); TradeMemory itself stays MIT. For educational and research purposes only. Not financial advice.

<div align="center">Built by <a href="https://mnemox.ai">Mnemox</a></div>
