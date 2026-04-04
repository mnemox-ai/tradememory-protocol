# TradeMemory README Rewrite + Commercial Packaging — Design Spec

> Date: 2026-04-05
> Status: Approved (all 5 sections)
> Author: Sean + Claude

---

## Context

TradeMemory has organic traction (328+ stars, word-of-mouth referrals) and at least one power user who built a complete trading workflow SOP on top of it. However, the current README speaks in engineering language (OWM, Bayesian, ACT-R) that alienates traders and gets misread as "tech flexing" by the trading community. The product needs repositioning from "research project" to "commercial product with open-source core."

### Key Insights from Real User (anonymized)

- Deployed on Synology NAS Docker, MCP SSE + REST API
- Trades US equities (not forex like the team)
- Built a complete pre-flight checklist workflow: recall → state → plans → risk → trade → reflect
- Designed their own cache strategy for MCP tools
- Built automation scripts (portfolio dashboard, price update, infra check)
- Found via friend recommendation (word of mouth)
- Quote: "Memory function is incredibly powerful"
- Quote: "Bad market conditions are when the memory layer is most useful"
- Using it for 1+ month in production

### Problem with Current README

- Opens with architecture description, not user pain
- SHA-256 audit trail prominent but irrelevant to individual traders
- Technical jargon (Bayesian, ACT-R, Kelly, DSR) in a trader-facing context
- No pricing signal
- No Getting Started workflow
- Gets misread as "another trading bot" instead of "memory layer"

---

## Deliverables

### D1: README.md Rewrite

**New structure (10 sections):**

#### 1. Hook

```
**Your trading AI has amnesia. And regulators are starting to notice.**

It makes the same mistakes every session. It can't explain why it traded.
It forgets everything when the context window ends. Meanwhile, MiFID II
is raising the bar for algorithmic decision documentation (Article 17).
The EU AI Act demands systematic logging of AI actions (Article 14).
Your competitors' agents are learning from every trade.

The AI trading stack is missing a layer. Every MCP server handles execution
— placing orders, fetching prices, reading charts. None handle memory.

Your agent can buy 100 shares of AAPL but can't answer: "What happened
last time I bought AAPL in this condition?"

**TradeMemory is the memory layer.** One `pip install`, and your AI agent
remembers every trade, every outcome, every mistake — with SHA-256
tamper-proof audit trail.

Used in production by traders running pre-flight checklists before every
position, and by EA systems logging thousands of decisions daily.
```

#### 2. What it does (3 bullets, trader language)

- Before trading: ask your memory — what happened last time in this market condition?
- After trading: one call records everything — five memory layers update automatically
- Safety rails: confidence tracking, drawdown alerts, losing streak detection — the system tells you when to stop

#### 3. Quick Start (3 steps: install → config → first trade)

```bash
# Step 1: Install
pip install tradememory-protocol

# Step 2: Add to Claude Desktop (claude_desktop_config.json)
{
  "mcpServers": {
    "tradememory": {
      "command": "uvx",
      "args": ["tradememory-protocol"]
    }
  }
}

# Step 3: Tell Claude
"Record my AAPL long at $195 — earnings beat, institutional buying, high confidence."
```

Full walkthrough: [Getting Started](docs/GETTING_STARTED.md)

#### 4. Who uses TradeMemory (3 use case cards)

Cards linking to `docs/USE_CASES.md`:
- US Equity Trader: Pre-flight workflow
- Forex EA System: Automated memory loop
- Compliance Team: Audit trail

#### 5. How it works (technical, for developers)

- OWM architecture diagram (existing asset)
- MCP Tools table — top 8 most-used only, rest in `<details>`
- REST API overview — link to API.md

#### 6. Pricing

| Tier | Price | Features | Audience |
|------|-------|----------|----------|
| Community | Free | 19 MCP tools, SQLite, self-hosted, full OWM + reflection engine | Individual traders, AI agent developers, researchers |
| Pro | $29/mo (Coming Soon) | Hosted API, web dashboard, priority support | Active traders, small teams |
| Enterprise | Contact Us | Private deployment, compliance reports, custom integration, SLA | Prop firms, funds, compliance teams |

- Community: no feature gating on existing functionality
- Pro "Coming Soon" = pricing signal, not commitment
- Enterprise = custom deal via dev@mnemox.ai

#### 7. Enterprise & Compliance

- Audit trail capabilities (TDR + SHA-256)
- Regulatory alignment table (MiFID II, EU AI Act) — moved from current prominent position to here
- CTA: dev@mnemox.ai

#### 8. Security (keep all 5 points, reformat to match new style)

Keep all existing items:
- Never touches API keys / no trade execution
- Read and record only
- No external network calls
- SHA-256 tamper detection
- 1,324 tests passing

#### 9. Documentation links table

#### 10. Star History + Footer

Star history chart preserved. MIT license. Built by Mnemox.

---

### D2: docs/GETTING_STARTED.md (New file)

**Dual-track design:**

#### Track A: Trader Track

For people using Claude Desktop / Claude Code to make trading decisions.

```
1. Install (30 seconds)
   pip install + Claude Desktop config

2. Your First Trade Memory (2 minutes)
   Example: Considering buying AAPL

   Step 1 — Ask memory
   Natural language: "What happened with AAPL trades before?"
   → Claude calls recall_memories

   Step 2 — Check state
   "How's my trading state?"
   → Claude calls get_agent_state

   Step 3 — Record completed trade
   "I bought 100 AAPL at $195 and sold at $205, made $1,000.
    Reason: earnings beat + institutional buying."
   → Claude calls remember_trade with full context (entry, exit, pnl)
   → Five memory layers update automatically in one call

   Note: remember_trade is designed to be called once after a trade
   is completed, with both entry and exit data. This is how real users
   do it — record the full trade with outcome, not entry and exit separately.

3. Pre-Flight Checklist (your trading SOP)
   Full flowchart: recall → state → legitimacy → trade → record → reflect
   Based on a real user workflow (anonymized)

4. Daily Review
   Ask Claude: "Run my daily trading review"
   → REST API /reflect/run_daily
```

#### Track B: Developer Track

For people building trading bots / agents with MCP or REST API.

```
1. Install + MCP Config (all platforms)

2. Core API Pattern
   remember_trade → write
   recall_memories → read
   get_agent_state → state

3. REST API Integration
   curl examples: record_decision → record_outcome → run_daily

4. Full Reference → API.md
```

**Key design decisions:**
- Trader Track uses only natural language (no function names visible)
- Developer Track gives code snippets
- Pre-Flight Checklist based on real user's SOP, credited as "Based on a real user workflow"

---

### D3: docs/USE_CASES.md (New file)

Three cases, all grounded in reality:

#### Case 1: US Equity Trader — Pre-Flight Workflow

- Based on real anonymized user
- Market: US equities
- Deployment: NAS Docker, MCP SSE + REST API
- Integration: Claude Code + chat bots via REST API
- Workflow: pre-flight → trade → reflect cycle
- Key insight: "Users treat TradeMemory as a discipline system, not a post-hoc journal"
- Attribution: "Based on a real user deployment, March 2026"

#### Case 2: Forex EA System — Automated Memory Loop

- Based on team's own NG_Gold system
- Market: XAUUSD
- Deployment: MT5 EA + MT5 Sync → TradeMemory
- Workflow: automated trade → auto-sync → decision logger → TDR audit
- Key insight: "Recording why you DIDN'T trade is as valuable as recording why you did"
- Attribution: "From the TradeMemory team's own production system"

#### Case 3: Compliance-First Fund — Audit Trail

- Representative scenario (not a real customer yet)
- Market: Multi-asset
- Need: MiFID II, EU AI Act compliance
- Workflow: every AI decision → TDR → SHA-256 → JSONL export
- Includes the existing VolBreakout FILTERED JSON example
- Key insight: "Regulators don't ask how much your AI made. They ask why it made each decision."
- Attribution: "Representative scenario based on TradeMemory's audit capabilities"

---

### D4: mnemox.ai/tradememory (New page)

Product landing page on existing mnemox-web (Next.js + Tailwind + Magic UI).

**Structure:**

```
1. Hero
   - Headline: same hook as README
   - Sub: "The memory layer for AI trading agents"
   - 2 CTAs: [Get Started — Free] → GitHub | [Enterprise] → /services#booking

2. Problem (3 columns)
   - "Same mistakes every session"
   - "No audit trail for regulators"
   - "Context window = memory loss"

3. How it works (3 steps, scroll-triggered CSS fade-in via IntersectionObserver)
   - Ask → recall memory before trading
   - Trade → record decision + auto-update five layers
   - Reflect → daily review + behavioral drift detection

4. Real Users (anonymized use case cards)
   - 3 cards linking to GitHub docs/USE_CASES.md

5. Pricing (3 tiers, same as README)

6. Trust signals
   - "1,324 tests passing"
   - "MIT open source"
   - "Used in production since March 2026"
   - Star count badge

7. CTA footer
   - [GitHub] [Get Started] [Contact Enterprise]
```

**Relationship to existing pages:**
- `/portfolio/tradememory` = case study (what we built, challenges, results)
- `/tradememory` = product page (what users get, how to use, pricing)
- Cross-linked but not duplicated

**Tech:** Next.js + Tailwind + Magic UI, consistent with existing mnemox-web.

---

## What NOT to change

- No code changes to TradeMemory itself
- No feature gating on existing free functionality
- No removal of technical documentation (OWM Framework, Research Log, etc.)
- Evolution Engine: keep in tools list but do not promote in README hook or use cases
- Hybrid Recall (embedding): do not mention until actually enabled

## What to be honest about

- Pro tier is "Coming Soon" — no timeline commitment
- Case 3 (Compliance) is a representative scenario, not a real customer
- Evolution Engine has 0% graduation rate — documented in Research Log, not hidden
- "Used in production" = real users, plural confirmed by word-of-mouth referral chain

## Length targets

- **README.md**: under 300 lines (including whitespace). Use `<details>` blocks for anything beyond the core message.
- **GETTING_STARTED.md**: under 200 lines per track. Trader Track should be completable in 5 minutes.
- **USE_CASES.md**: under 150 lines total. Each case 40-50 lines max.
- **Landing page**: single scroll, no pagination. 7 sections, each fits in one viewport.

## Files to create/modify

| File | Action | Priority |
|------|--------|----------|
| `README.md` | Rewrite | P0 |
| `docs/GETTING_STARTED.md` | New | P0 |
| `docs/USE_CASES.md` | New | P0 |
| `docs/README_ZH.md` | Update to match new README | P1 |
| mnemox-web `/tradememory` page | New page | P1 |

## Success criteria

1. A trader reads README and understands what TradeMemory does in 30 seconds without seeing "Bayesian" or "ACT-R"
2. A developer can go from zero to first recorded trade in 5 minutes using Getting Started
3. A compliance officer finds the audit trail section and contacts dev@mnemox.ai
4. Moon Lulu-type critics can't say "this is just a trading bot" — the messaging clearly says "memory layer, not decision maker"
