# TradeMemory README Rewrite + Commercial Packaging — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite README from engineering language to commercial product positioning, add Getting Started guide and Use Cases document.

**Architecture:** Documentation-only changes. Three new/rewritten markdown files in the tradememory-protocol repo. No code changes. Content based on approved design spec at `docs/superpowers/specs/2026-04-05-readme-rewrite-design.md`.

**Tech Stack:** Markdown, existing GitHub repo structure.

---

### Task 1: Write USE_CASES.md

**Why first:** README Section 4 links to this file. Write it before README so links aren't broken.

**Files:**
- Create: `docs/USE_CASES.md`

**Length target:** Under 150 lines total. Each case 40-50 lines max.

- [ ] **Step 1: Create docs/USE_CASES.md with all 3 cases**

```markdown
# Real-World Use Cases

Three ways teams use TradeMemory in production.

---

## Case 1: US Equity Trader — Pre-Flight Workflow

**Profile**

| | |
|---|---|
| Market | US equities |
| Deployment | NAS Docker, MCP SSE + REST API |
| Integration | Claude Code + chat bots via REST API |

**How they use it**

Every trade goes through a pre-flight checklist before execution:

1. **Recall** — Ask TradeMemory for past trades in similar market conditions
2. **State check** — Verify confidence level, drawdown percentage, and streak status
3. **Plan check** — See if any pre-set trading plans have been triggered
4. **Risk check** — Run position sizing through the risk endpoint
5. **Execute** — Only if all checks pass
6. **Record** — One call to `remember_trade` captures everything and updates five memory layers automatically
7. **Reflect** — Daily and weekly reviews via REST API

The trader also built automation scripts for portfolio dashboards, price updates, and infrastructure health checks — all feeding into TradeMemory via REST API.

> **Key insight:** Users treat TradeMemory as a discipline system — memory is the starting point of the decision process, not an afterthought.

*Based on a real user deployment, March 2026.*

---

## Case 2: Forex EA System — Automated Memory Loop

**Profile**

| | |
|---|---|
| Market | XAUUSD (Gold) |
| Deployment | MT5 Expert Advisor + MT5 Sync → TradeMemory |
| Strategies | VolBreakout, IntradayMomentum, Pullback |

**How they use it**

The EA trades automatically. TradeMemory records everything:

1. **Auto-sync** — MT5 Sync pushes every closed trade to TradeMemory with full context
2. **Decision logging** — Every signal is recorded as a Trading Decision Record (TDR), including signals that were blocked by filters
3. **Audit trail** — Each TDR is SHA-256 hashed at creation for tamper detection
4. **Weekly review** — `get_strategy_performance` compares strategies side by side

The system logs thousands of decisions daily. Most are "FILTERED" — valid signals blocked by risk rules. These filtered decisions are the most valuable review data.

> **Key insight:** Recording why you DIDN'T trade is as valuable as recording why you did. Filtered signals reveal how your risk rules interact with real market conditions.

*From the TradeMemory team's own production system.*

---

## Case 3: Compliance-First Fund — Audit Trail

**Profile**

| | |
|---|---|
| Market | Multi-asset (equities + crypto) |
| Need | MiFID II Article 17, EU AI Act Article 14 |
| Deployment | Private server, REST API |

**How they use it**

Every AI decision — including decisions NOT to trade — generates a complete audit record:

```json
{
  "ts": "2026-03-26 07:55:00",
  "strategy": "VolBreakout",
  "decision": "FILTERED",
  "signal_direction": "SHORT",
  "filters_json": {
    "filters": [
      {"name": "spread_gate", "passed": true},
      {"name": "sell_allowed", "passed": false, "blocked": true},
      {"name": "account_risk", "passed": true}
    ]
  },
  "regime": "TRENDING",
  "consec_losses": 0
}
```

A regulator reads this and immediately understands: the agent saw a valid signal, but policy blocked it. No guessing, no black box.

```bash
# Verify record integrity
GET /audit/verify/{trade_id}
# → {"verified": true, "stored_hash": "a3f8c9...", "computed_hash": "a3f8c9..."}

# Bulk export for regulatory submission
GET /audit/export?strategy=VolBreakout&start=2026-03-01&format=jsonl
```

> **Key insight:** Regulators don't ask how much your AI made. They ask why it made each decision.

*Representative scenario based on TradeMemory's audit capabilities.*

---

[Back to README](../README.md) · [Getting Started](GETTING_STARTED.md) · [API Reference](API.md)
```

- [ ] **Step 2: Verify line count is under 150**

Run: `wc -l docs/USE_CASES.md`
Expected: under 150 lines

- [ ] **Step 3: Commit**

```bash
git add docs/USE_CASES.md
git commit -m "docs: add real-world use cases — 3 production scenarios"
```

---

### Task 2: Write GETTING_STARTED.md

**Files:**
- Create: `docs/GETTING_STARTED.md`

**Length target:** Under 200 lines per track.

- [ ] **Step 1: Create docs/GETTING_STARTED.md with dual-track design**

```markdown
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
```

- [ ] **Step 2: Verify line count**

Run: `wc -l docs/GETTING_STARTED.md`
Expected: under 200 lines per track (roughly 200 total)

- [ ] **Step 3: Commit**

```bash
git add docs/GETTING_STARTED.md
git commit -m "docs: add Getting Started guide — dual track (trader + developer)"
```

---

### Task 3: Archive old README for reference

**Files:**
- Create: `docs/README_OLD_2026-04-05.md`

- [ ] **Step 1: Copy current README to archive**

```bash
cp README.md docs/README_OLD_2026-04-05.md
```

- [ ] **Step 2: Commit archive**

```bash
git add docs/README_OLD_2026-04-05.md
git commit -m "docs: archive old README before rewrite"
```

---

### Task 4: Rewrite README.md

**Files:**
- Modify: `README.md` (full rewrite, keep mcp-name comment and header image)

**Length target:** Under 300 lines including whitespace.

**Important:** Back up the current README content — it has the VolBreakout JSON example (now moved to USE_CASES.md Case 3) and the regulatory alignment table (now in Enterprise section).

- [ ] **Step 1: Read current README to capture any content we need to preserve**

Run: `cat README.md | head -5` — capture the mcp-name comment and header image HTML

Content to preserve:
- Line 1: `<!-- mcp-name: io.github.mnemox-ai/tradememory-protocol -->`
- Lines 3-5: header image
- Lines 7-16: badges + nav links (update nav links)
- Architecture diagram (`assets/schema.png`)
- Memory pipeline diagram (`assets/memory-pipeline.png`)
- OWM factors diagram (`assets/owm-factors.png`)
- Star history chart (bottom)
- Regulatory alignment table (move to Enterprise section)

- [ ] **Step 2: Write the new README.md**

The full new README follows this structure (all 10 sections from spec):

```markdown
<!-- mcp-name: io.github.mnemox-ai/tradememory-protocol -->

<p align="center">
  <img src="assets/header.png" alt="TradeMemory Protocol" width="600">
</p>

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/tradememory-protocol?style=flat-square&color=blue)](https://pypi.org/project/tradememory-protocol/)
[![Tests](https://img.shields.io/badge/tests-1%2C324_passed-brightgreen?style=flat-square)](https://github.com/mnemox-ai/tradememory-protocol/actions)
[![MCP Tools](https://img.shields.io/badge/MCP_tools-19-blueviolet?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
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
<summary>All 19 MCP tools + REST API</summary>

| Category | Tools |
|----------|-------|
| **Core Memory** | `store_trade_memory` · `recall_similar_trades` · `get_strategy_performance` · `get_trade_reflection` |
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
| MCP tools | 19 tools | 19 tools | 19 tools |
| Storage | SQLite, self-hosted | Hosted API | Private deployment |
| Dashboard | — | Web dashboard | Custom dashboard |
| Compliance | Audit trail included | Audit trail included | Compliance reports + SLA |
| Support | GitHub Issues | Priority support | Dedicated support |
| | [Get Started →](docs/GETTING_STARTED.md) | *Coming soon* | [dev@mnemox.ai](mailto:dev@mnemox.ai) |

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
```

- [ ] **Step 3: Verify line count is under 300**

Run: `wc -l README.md`
Expected: under 300 lines

- [ ] **Step 4: Verify all internal links work**

Run: `grep -oP '\(docs/[^)]+\)' README.md | sort -u` — check each file exists

Expected files exist:
- `docs/GETTING_STARTED.md` (created in Task 2)
- `docs/USE_CASES.md` (created in Task 1)
- `docs/API.md` ✓
- `docs/OWM_FRAMEWORK.md` ✓
- `docs/ARCHITECTURE.md` ✓
- `docs/TUTORIAL.md` ✓
- `docs/MT5_SYNC_SETUP.md` ✓
- `docs/RESEARCH_LOG.md` ✓
- `docs/README_ZH.md` ✓
- `docs/trading-ai-failure-taxonomy.md` ✓

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README — commercial positioning, pricing, use cases"
```

---

### Task 5: Verify everything

- [ ] **Step 1: Check line counts**

```bash
wc -l README.md docs/USE_CASES.md docs/GETTING_STARTED.md
```

Expected:
- README.md: under 300
- USE_CASES.md: under 150
- GETTING_STARTED.md: under 200

- [ ] **Step 2: Check no Bayesian/ACT-R/Kelly in first 50 lines of README**

```bash
head -50 README.md | grep -i -E "bayesian|act-r|kelly|deflated sharpe"
```

Expected: no matches

- [ ] **Step 3: Check "memory layer" appears in first 30 lines**

```bash
head -30 README.md | grep -i "memory layer"
```

Expected: at least 1 match

- [ ] **Step 4: Check all doc links resolve**

```bash
for f in docs/GETTING_STARTED.md docs/USE_CASES.md docs/API.md docs/OWM_FRAMEWORK.md docs/ARCHITECTURE.md docs/TUTORIAL.md docs/MT5_SYNC_SETUP.md docs/RESEARCH_LOG.md docs/README_ZH.md docs/trading-ai-failure-taxonomy.md; do
  [ -f "$f" ] && echo "OK: $f" || echo "MISSING: $f"
done
```

Expected: all OK

- [ ] **Step 5: Push**

```bash
git push origin master
```

---

## Execution Order

```
Task 1: USE_CASES.md          → commit
Task 2: GETTING_STARTED.md    → commit
Task 3: Archive old README    → commit
Task 4: Rewrite README.md     → commit
Task 5: Verify + push
```

## Out of Scope (P1 — separate plan)

- `docs/README_ZH.md` update to match new README
- `mnemox.ai/tradememory` landing page (different repo: mnemox-web)
