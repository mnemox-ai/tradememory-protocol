# TradeMemory API Reference

TradeMemory exposes its functionality via HTTP endpoints. Any MCP-compatible AI agent or HTTP client can use these endpoints.

**Base URL:** `http://localhost:8000`

---

## Implemented Tools

### Trade Journal

#### `POST /trade/record_decision`

Record a trade entry decision with full context.

**Request body:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `trade_id` | string | yes | Unique trade ID (format: `T-YYYY-NNNN`) |
| `symbol` | string | yes | Trading instrument (e.g. `XAUUSD`) |
| `direction` | string | yes | `"long"` or `"short"` |
| `lot_size` | float | yes | Position size |
| `strategy` | string | yes | Strategy tag (e.g. `VolBreakout`) |
| `confidence` | float | yes | Agent confidence score, 0.0-1.0 |
| `reasoning` | string | yes | Natural language explanation of why |
| `market_context` | object | yes | See [MarketContext](#marketcontext) |
| `references` | string[] | no | Past trade IDs referenced (default: `[]`) |

**Response:**

```json
{
  "success": true,
  "trade_id": "T-2026-0251",
  "timestamp": "2026-02-23T09:03:42+00:00"
}
```

**Errors:**

- `400` — Invalid confidence (not 0.0-1.0), invalid direction, or database write failure.

**Example (Python):**

```python
import requests

resp = requests.post("http://localhost:8000/trade/record_decision", json={
    "trade_id": "T-2026-0251",
    "symbol": "XAUUSD",
    "direction": "long",
    "lot_size": 0.05,
    "strategy": "VolBreakout",
    "confidence": 0.72,
    "reasoning": "London open breakout above 2890 with volume confirmation.",
    "market_context": {
        "price": 2891.50,
        "session": "london",
        "atr": 28.3,
        "indicators": {"rsi_14": 58.2}
    },
    "references": ["T-2026-0247"]
})

data = resp.json()
print(data["trade_id"])   # T-2026-0251
print(data["timestamp"])  # 2026-02-23T09:03:42+00:00
```

---

#### `POST /trade/record_outcome`

Record the outcome of a trade after it closes.

**Request body:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `trade_id` | string | yes | ID of the trade to update |
| `exit_price` | float | yes | Price at exit |
| `pnl` | float | yes | Realized P&L in account currency |
| `exit_reasoning` | string | yes | Why the agent exited |
| `pnl_r` | float | no | P&L in R-multiples |
| `hold_duration` | int | no | Minutes the position was held |
| `slippage` | float | no | Entry slippage in pips |
| `execution_quality` | float | no | 0.0-1.0 score |
| `lessons` | string | no | What was learned from this trade |

**Response:**

```json
{
  "success": true,
  "trade_id": "T-2026-0251"
}
```

**Errors:**

- `400` — Trade ID not found, invalid execution_quality (not 0.0-1.0), or database write failure.

**Example (Python):**

```python
resp = requests.post("http://localhost:8000/trade/record_outcome", json={
    "trade_id": "T-2026-0251",
    "exit_price": 2897.20,
    "pnl": 28.50,
    "pnl_r": 2.1,
    "exit_reasoning": "Hit 2R target at 2897.",
    "hold_duration": 87,
    "slippage": 0.3,
    "execution_quality": 0.88,
    "lessons": "Volume confirmation at London open continues to work."
})
```

---

#### `POST /trade/query_history`

Search past trades by strategy, symbol, or both.

**Request body:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `strategy` | string | no | Filter by strategy name |
| `symbol` | string | no | Filter by trading instrument |
| `limit` | int | no | Max results (default: 100) |

**Response:**

```json
{
  "success": true,
  "count": 2,
  "trades": [
    {
      "id": "T-2026-0251",
      "timestamp": "2026-02-23T09:03:42+00:00",
      "symbol": "XAUUSD",
      "direction": "long",
      "strategy": "VolBreakout",
      "confidence": 0.72,
      "pnl": 28.50,
      "pnl_r": 2.1
    }
  ]
}
```

Trades are returned ordered by `timestamp DESC` (newest first). Each trade object contains all `TradeRecord` fields — see [SCHEMA.md](SCHEMA.md) for the full structure.

**Example (Python):**

```python
# Get all VolBreakout trades
resp = requests.post("http://localhost:8000/trade/query_history", json={
    "strategy": "VolBreakout",
    "limit": 50
})

trades = resp.json()["trades"]
win_rate = sum(1 for t in trades if t["pnl"] and t["pnl"] > 0) / len(trades)
print(f"VolBreakout win rate: {win_rate:.0%}")
```

---

#### `GET /trade/get_active`

Get all currently open positions (trades with no recorded outcome).

**Parameters:** None.

**Response:**

```json
{
  "success": true,
  "count": 1,
  "trades": [
    {
      "id": "T-2026-0253",
      "timestamp": "2026-02-23T14:22:10+00:00",
      "symbol": "XAUUSD",
      "direction": "long",
      "lot_size": 0.05,
      "strategy": "VolBreakout",
      "confidence": 0.85,
      "reasoning": "...",
      "pnl": null,
      "exit_timestamp": null
    }
  ]
}
```

**Example (Python):**

```python
resp = requests.get("http://localhost:8000/trade/get_active")
active = resp.json()["trades"]
print(f"{len(active)} open positions")
```

---

### Reflection

#### `POST /reflect/run_daily`

Generate a daily reflection summary. Uses LLM (Claude) if `ANTHROPIC_API_KEY` is set, otherwise falls back to rule-based analysis.

**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | no | Target date as `YYYY-MM-DD` (default: today) |

**Response:**

```json
{
  "success": true,
  "date": "2026-02-23",
  "summary": "=== DAILY SUMMARY: 2026-02-23 ===\n\nPERFORMANCE:\n..."
}
```

The `summary` field contains a markdown-formatted reflection report. See [REFLECTION_FORMAT.md](REFLECTION_FORMAT.md) for the full template.

**Example (Python):**

```python
# Today's reflection
resp = requests.post("http://localhost:8000/reflect/run_daily")
print(resp.json()["summary"])

# Specific date
resp = requests.post("http://localhost:8000/reflect/run_daily?date=2026-02-22")
```

---

### State Management

#### `POST /state/load`

Load agent state at session start. Creates a new empty state if the agent has no saved state.

**Request body:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | yes | Unique agent identifier |

**Response:**

```json
{
  "success": true,
  "state": {
    "agent_id": "ng_gold_v1",
    "last_active": "2026-02-23T08:45:12+00:00",
    "warm_memory": {
      "last_mt5_sync_timestamp": "2026-02-23T08:40:00+00:00"
    },
    "active_positions": ["T-2026-0250"],
    "risk_constraints": {
      "asian_max_lot": 0.025,
      "london_max_lot": 0.08
    }
  }
}
```

**Example (Python):**

```python
resp = requests.post("http://localhost:8000/state/load", json={
    "agent_id": "ng_gold_v1"
})

state = resp.json()["state"]
constraints = state["risk_constraints"]
insights = state["warm_memory"]
```

---

#### `POST /state/save`

Persist current agent state. Automatically updates `last_active` timestamp.

**Request body:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `state` | object | yes | Full `SessionState` object |

The `state` object must contain:

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | string | Agent identifier |
| `last_active` | string | ISO 8601 timestamp (auto-updated on save) |
| `warm_memory` | object | L2 insights as key-value pairs |
| `active_positions` | string[] | List of open trade IDs |
| `risk_constraints` | object | Dynamic risk parameters |

**Response:**

```json
{
  "success": true,
  "agent_id": "ng_gold_v1"
}
```

**Example (Python):**

```python
resp = requests.post("http://localhost:8000/state/save", json={
    "state": {
        "agent_id": "ng_gold_v1",
        "last_active": "2026-02-23T12:00:00+00:00",
        "warm_memory": {"session_bias": "london_bullish"},
        "active_positions": [],
        "risk_constraints": {"max_lot": 0.05}
    }
})
```

---

### MT5 Integration

#### `POST /mt5/connect`

Connect to a MetaTrader 5 account. Requires the `MetaTrader5` Python package (Windows only).

**Request body:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `login` | int | yes | MT5 account number |
| `password` | string | yes | Account password |
| `server` | string | yes | Broker server name |
| `path` | string | no | Path to MT5 terminal executable |

**Response:**

```json
{
  "success": true,
  "message": "Connected to MT5"
}
```

**Errors:**

- `400` — `MetaTrader5` package not installed, or connection failed.

---

#### `POST /mt5/sync`

Sync closed trades from MT5 to TradeJournal. Groups MT5 deals by position, determines entry/exit, and records both decision and outcome.

**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | no | Agent ID for state tracking (default: `ng-gold-agent`) |

**Response:**

```json
{
  "success": true,
  "agent_id": "ng-gold-agent",
  "stats": {
    "synced": 3,
    "skipped": 1,
    "errors": 0
  }
}
```

---

### Health Check

#### `GET /health`

**Response:**

```json
{
  "status": "healthy",
  "service": "TradeMemory Protocol",
  "version": "0.1.0"
}
```

---

## Not Yet Implemented (Phase 2)

These tools are planned but not yet available:

| Tool | Purpose |
|------|---------|
| `reflect.run_weekly` | Weekly deep reflection with strategy-level analysis |
| `reflect.get_insights` | Retrieve curated L2 insights |
| `reflect.query_patterns` | Ask specific questions about discovered patterns |
| `risk.get_constraints` | Get current dynamic risk parameters |
| `risk.check_trade` | Validate a proposed trade against active constraints |
| `risk.get_performance` | Get aggregated performance metrics |
| `risk.override` | Human override of risk parameters (requires auth) |
| `state.get_identity` | Get agent identity and personality context |
| `state.heartbeat` | Keep-alive signal for long-running agents |

---

## Data Types

### MarketContext

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `price` | float | yes | Current/entry price |
| `atr` | float | no | Average True Range |
| `session` | string | no | `"asian"`, `"london"`, or `"newyork"` |
| `indicators` | object | no | Key-value pairs of indicator values |
| `news_sentiment` | float | no | -1.0 (bearish) to 1.0 (bullish) |

### Error Response

All errors return HTTP 400 with:

```json
{
  "detail": "Human-readable error message"
}
```

---

## See Also

- [SCHEMA.md](SCHEMA.md) — Full data structure reference with JSON examples
- [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture and memory model
- [REFLECTION_FORMAT.md](REFLECTION_FORMAT.md) — Reflection report template
