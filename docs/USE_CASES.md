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
