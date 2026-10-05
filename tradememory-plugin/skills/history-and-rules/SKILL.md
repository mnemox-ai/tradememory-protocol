---
name: history-and-rules
description: How TradeMemory turns a trader's own fill history into rules the trader approves and the broker brake enforces. Use when the trader wants to see where their history loses money, asks about revenge trading or sizing up after losses, sees a suggested rule, or wants an agent's orders checked before they reach the broker. Triggers on "sync my trades", "where do I lose money", "losing streak", "size up after losses", "suggested rule", "approve rule", "brake", "hold this order".
---

# History and rules

TradeMemory closes one loop: sync fills, find where the history loses money, turn a costly habit into a rule the trader approves, check new orders against it before they reach the broker, and fold the outcomes back into memory.

## 1. Sync

`tradememory sync hyperliquid --address 0x...` (public, no key) or `tradememory sync alpaca --env-file <file with the trader's keys>` (read-only). Each closed trade is stored once. The report is descriptive statistics of the trader's own past trades.

## 2. The habit it looks for

After two losses in a row, does the trader size up (1.5 times their median notional or more) more often than they size up at all? The report compares the two shares. It calls it "more often than usual" only when a one-sided binomial test against the trader's own rate gives p <= 0.10 and the share is at least 5 points higher. Most histories do not show it; say so plainly when this one does not.

## 3. Rules

When the habit shows and those bigger trades lost money in total, the sync saves a proposed rule: after 2 losses in a row, new orders at or above that size are held for the trader's approval. A proposed rule does nothing.

- `tradememory rules list`: proposed and active rules with their evidence.
- `tradememory rules approve <id> [--max-notional N] [--action deny]`: only the trader runs this. Never approve a rule on the trader's behalf.
- `tradememory rules retire <id>`: turn it off; it stays as a record.

## 4. The brake

The brake (`pip install "tradememory-protocol[proxy]"`, Python 3.12+, preview) sits between an agent and Alpaca's official MCP server. Order tools are evaluated against the trader's sealed policy and their approved rules before anything is forwarded. A held order returns `ESCALATE` with code `TM_RULE_SIZE_AFTER_LOSING_STREAK`, the two losing trades that triggered it, and the `tradememory proxy approve` command that releases exactly those terms. Reducing or closing a position is never held. The brake counts only closes that a sync has written, so after trades close the trader runs `tradememory sync alpaca --db <brake database>`.

When an order comes back held or refused, tell the trader which rule and which trades caused it. Do not retry with different terms to get around it.
