# TradeMemory API Reference

> **Status:** Work in progress. This document will contain full MCP tool specifications.

---

## Overview

TradeMemory exposes its functionality via MCP (Model Context Protocol) tools. Any MCP-compatible AI agent can use these tools to access persistent memory and adaptive decision-making capabilities.

**Base URL:** `http://localhost:8000` (default)

---

## Tool Categories

### Trade Journal
Tools for recording and querying trade decisions and outcomes.

- `trade.record_decision` — Log a trade entry decision
- `trade.record_outcome` — Log trade result
- `trade.query_history` — Search past trades
- `trade.get_active` — Get current open positions

### Reflection
Tools for analyzing trading patterns and retrieving insights.

- `reflect.run_daily` — Trigger daily summary
- `reflect.run_weekly` — Trigger weekly reflection *(Not Yet Implemented)*
- `reflect.get_insights` — Get curated insights (L2 memory) *(Not Yet Implemented)*
- `reflect.query_patterns` — Ask specific questions about patterns *(Not Yet Implemented)*

### Risk Management *(Not Yet Implemented)*
Tools for checking and managing risk parameters.

- `risk.get_constraints` — Get current dynamic risk parameters *(Not Yet Implemented)*
- `risk.check_trade` — Validate proposed trade against constraints *(Not Yet Implemented)*
- `risk.get_performance` — Get performance metrics *(Not Yet Implemented)*
- `risk.override` — Human override of risk parameters (requires auth) *(Not Yet Implemented)*

### State Management
Tools for session persistence and agent identity.

- `state.load` — Load agent state at session start
- `state.save` — Persist current state
- `state.get_identity` — Get agent identity context *(Not Yet Implemented)*
- `state.heartbeat` — Keep-alive signal for long-running agents *(Not Yet Implemented)*

---

## Detailed Documentation

### `trade.record_decision`

Record a trade entry decision with full context.

**Parameters:**

See [SCHEMA.md](SCHEMA.md#example-recording-a-trade-decision) for full parameter specification and examples.

**Response:**

```json
{
  "trade_id": "T-YYYY-NNNN",
  "timestamp": "ISO 8601 UTC",
  "status": "recorded"
}
```

---

### `trade.record_outcome`

Record the outcome of a trade after it closes.

**Parameters:**

See [SCHEMA.md](SCHEMA.md#example-recording-trade-outcome) for full parameter specification and examples.

**Response:**

```json
{
  "trade_id": "T-YYYY-NNNN",
  "status": "outcome_recorded",
  "pnl": 28.50,
  "pnl_r": 2.1
}
```

---

### `state.load`

Load agent state at the start of a session.

**Parameters:**

```json
{
  "agent_id": "string"
}
```

**Response:**

See [SCHEMA.md](SCHEMA.md#example-loading-state) for full response structure.

---

## Error Handling

All tools return errors in this format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {}
  }
}
```

**Common Error Codes:**

- `INVALID_PARAMETERS` — Missing or invalid parameters
- `TRADE_NOT_FOUND` — Trade ID does not exist
- `CONSTRAINT_VIOLATION` — Proposed trade violates risk constraints
- `DATABASE_ERROR` — Database operation failed
- `AUTH_REQUIRED` — Operation requires authentication

---

## Authentication (Phase 2)

Some tools (e.g., `risk.override`) will require authentication in Phase 2. Details TBD.

---

## Rate Limits (Phase 2+)

SaaS hosted version will have rate limits:
- **Free tier:** 1000 tool calls/day
- **Pro tier:** 50,000 tool calls/day
- **Enterprise:** Unlimited

Self-hosted instances have no rate limits.

---

## See Also

- [SCHEMA.md](SCHEMA.md) — Full data structure reference with examples
- [README.md](../README.md) — Project overview
- [REFLECTION_FORMAT.md](REFLECTION_FORMAT.md) — Reflection report format
