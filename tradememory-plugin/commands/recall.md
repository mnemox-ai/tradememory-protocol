---
description: Before an order, recall the losing trades from similar conditions first
argument-hint: "[symbol] [current market conditions]"
---

# Recall before the next order

Show the trader what their own losing trades in similar conditions looked like before they place the next order.

## Workflow

### Step 1: Get the context

Use the arguments if given. Otherwise ask for the symbol and a short description of current conditions (trend or range, volatility, session). Ask for the strategy name only if the trader uses named strategies.

### Step 2: Recall, losses first

Call the `recall_memories` tool with `order: "losses_first"`:

```
recall_memories({
  symbol: "XAUUSD",
  market_context: "ranging, low volatility, Asian session",
  order: "losses_first",
  limit: 10
})
```

With `losses_first`, every losing trade ranks above every winning one, bigger losses in similar conditions first, and the trader's current losing streak does not push losses down.

### Step 3: Present

For each recalled trade show the symbol, direction, size (`lot_size` when recorded), P&L and R multiple when recorded, and the reflection that was written at the time. Then say in one or two sentences what the losing trades have in common, using only what the records show.

Do not tell the trader whether to take the trade. These are their own past results, not a forecast.

## Example

```
User: /recall XAUUSD ranging, low volatility, Asian session
```
