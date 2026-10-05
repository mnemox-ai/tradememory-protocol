---
description: Pull a venue's fill history into memory and show where it loses money
argument-hint: "[hyperliquid <address> | alpaca]"
---

# Sync history

Rebuild closed trades from a venue's fills, store each one in TradeMemory once, and print where the history loses money. This runs the `tradememory` command line program, so it needs a terminal (Claude Code).

## Workflow

### Step 1: Pick the source

- **Hyperliquid**: needs only the account's public address (0x followed by 40 hex characters). No key. The venue serves only an address's recent fills.
- **Alpaca**: needs the trader's own API keys in a local `KEY=VALUE` file (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`). Ask where that file is. Never ask the trader to paste keys into the chat. Calls are read-only.

### Step 2: Run it

```bash
tradememory sync hyperliquid --address 0x...
tradememory sync alpaca --env-file ~/.secrets/alpaca-paper.env
```

Add `--dry-run` to report without storing anything. If `tradememory` is not installed, install it first with `pip install tradememory-protocol`.

### Step 3: Read the report back

Summarise the numbers the command printed: closed trades, win rate, net P&L, what happens after two losses in a row (and whether that is more often than the trader's usual rate), hold times of winners against losers, the worst symbols and hours, the biggest single losses. Quote the numbers; do not add new ones.

If the report ends with a suggested rule, show its sentence and its reason, and tell the trader it does nothing until they approve it themselves with `tradememory rules approve <id>`. Do not run the approval for them.

These are descriptive statistics of the trader's own past trades, not advice.
