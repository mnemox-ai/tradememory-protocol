# TradeMemory Hosted API Specification

> **Status (August 2026):** Historical design document. The hosted API described below was never launched and is not offered for sale; TradeMemory is self-hosted only. Kept for reference.

Base URL: `https://mcp.mnemox.ai/api/v1`

## Authentication

All requests require an API key in the `Authorization` header:

```
Authorization: Bearer tm_live_xxxxxxxxxxxxxxxx
```

API keys are issued per account. Two key types:
- `tm_live_*` — Production keys (metered usage)
- `tm_test_*` — Test keys (no billing, data isolated, rate-limited to 10 req/min)

Keys are managed via the dashboard at `https://mcp.mnemox.ai/dashboard`.

---

## Rate Limiting

Limits are enforced per API key using a sliding window (1 minute).

| Plan    | Requests/min | Requests/day | Burst (10s) |
|---------|-------------|-------------|-------------|
| Free    | 10          | 500         | 5           |
| Trader  | 60          | 10,000      | 20          |
| Pro     | 200         | 50,000      | 50          |
| Fund    | 600         | 200,000     | 100         |

Rate limit headers included in every response:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 58
X-RateLimit-Reset: 1709510400
```

When exceeded, the API returns `429 Too Many Requests` with a `Retry-After` header (seconds).

---

## Pricing

### Monthly Plans

| Plan    | Price    | Credits/mo | Overage     | Features                                    |
|---------|----------|-----------|-------------|---------------------------------------------|
| Free    | $0       | 100       | Blocked     | L1 store/recall only, 1 API key             |
| Trader  | $29/mo   | 5,000     | $0.008/cr   | Full L1-L3, 3 API keys, daily reflection    |
| Pro     | $79/mo   | 20,000    | $0.005/cr   | Full L1-L3, 10 API keys, webhook, priority  |
| Fund    | $299/mo  | 100,000   | $0.004/cr   | Full L1-L3, unlimited keys, SLA, dedicated  |

### Credit Packs (Pay-as-you-go)

| Pack     | Credits | Price | Per Credit |
|----------|---------|-------|------------|
| Starter  | 1,000   | $10   | $0.010     |
| Growth   | 5,000   | $40   | $0.008     |
| Scale    | 25,000  | $150  | $0.006     |

Credit packs never expire. Monthly plan credits reset on billing date.

### Credit Costs Per Operation

| Operation                  | Credits | Notes                       |
|----------------------------|---------|------------------------------|
| `POST /trades`             | 1       | Store a trade                |
| `GET /trades`              | 1       | Recall trades (per request)  |
| `GET /trades/:id`          | 1       | Single trade lookup          |
| `GET /performance`         | 2       | Aggregate stats computation  |
| `GET /trades/:id/reflection` | 1    | Trade reflection             |
| `POST /patterns/discover`  | 5       | L2 pattern discovery         |
| `GET /patterns`            | 1       | Query stored patterns        |
| `POST /adjustments/generate` | 5    | L3 adjustment generation     |
| `GET /adjustments`         | 1       | Query adjustments            |
| `PATCH /adjustments/:id`   | 1       | Update adjustment status     |
| `POST /reflect/daily`      | 3       | Daily reflection             |
| `POST /reflect/weekly`     | 5       | Weekly reflection            |
| `POST /reflect/monthly`    | 10      | Monthly reflection           |
| `GET /health`              | 0       | Free                         |
| `GET /usage`               | 0       | Free                         |

---

## Endpoints

### Health & Account

#### `GET /health`

Returns service status. No auth required.

```json
{
  "status": "healthy",
  "version": "0.4.0"
}
```

#### `GET /usage`

Returns current billing period usage.

```json
{
  "plan": "trader",
  "credits_used": 1247,
  "credits_limit": 5000,
  "credits_remaining": 3753,
  "period_start": "2026-03-01T00:00:00Z",
  "period_end": "2026-03-31T23:59:59Z",
  "overage_enabled": true
}
```

---

### L1 — Trade Memory

#### `POST /trades`

Store a trade decision with full context.

**Request:**

```json
{
  "symbol": "XAUUSD",
  "direction": "long",
  "entry_price": 5175.50,
  "strategy_name": "VolBreakout",
  "market_context": "Asia range breakout, ATR(D1)=150, above 20-EMA",
  "exit_price": 5210.00,
  "pnl": 345.00,
  "reflection": "Clean breakout with good volume confirmation",
  "trade_id": "MT5-2350718677",
  "timestamp": "2026-03-03T10:30:00Z"
}
```

**Response** `201 Created`:

```json
{
  "memory_id": "MT5-2350718677",
  "symbol": "XAUUSD",
  "direction": "long",
  "strategy": "VolBreakout",
  "stored_at": "2026-03-03T10:30:00Z",
  "has_outcome": true,
  "status": "stored",
  "credits_used": 1
}
```

Required fields: `symbol`, `direction`, `entry_price`, `strategy_name`, `market_context`.

#### `GET /trades`

Query past trades with filters.

**Query parameters:**

| Param      | Type   | Description                    |
|------------|--------|--------------------------------|
| `symbol`   | string | Filter by symbol (e.g. XAUUSD) |
| `strategy` | string | Filter by strategy name        |
| `limit`    | int    | Max results (default 20, max 100) |
| `offset`   | int    | Pagination offset (default 0)  |

**Response** `200 OK`:

```json
{
  "trades": [...],
  "count": 15,
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

#### `GET /trades/:id`

Get a single trade by ID.

**Response** `200 OK`:

```json
{
  "trade_id": "MT5-2350718677",
  "symbol": "XAUUSD",
  "direction": "long",
  "strategy": "VolBreakout",
  "timestamp": "2026-03-03T10:30:00Z",
  "market_context": { "description": "Asia range breakout..." },
  "entry_price": 5175.50,
  "exit_price": 5210.00,
  "pnl": 345.00,
  "reflection": "Clean breakout with good volume confirmation",
  "lessons": "Clean breakout with good volume confirmation"
}
```

**Error** `404 Not Found`:

```json
{
  "error": "trade_not_found",
  "message": "Trade 'xxx' not found"
}
```

---

### Performance

#### `GET /performance`

Aggregate performance stats per strategy.

**Query parameters:**

| Param      | Type   | Description             |
|------------|--------|-------------------------|
| `symbol`   | string | Filter by symbol        |
| `strategy` | string | Filter by strategy name |

**Response** `200 OK`:

```json
{
  "symbol": "XAUUSD",
  "total_closed_trades": 42,
  "strategies": {
    "VolBreakout": {
      "trade_count": 18,
      "win_rate": 66.7,
      "total_pnl": 2340.50,
      "avg_pnl": 130.03,
      "avg_winner": 285.20,
      "avg_loser": -105.40,
      "profit_factor": 1.85,
      "best_trade": { "id": "MT5-xxx", "pnl": 1175.09 },
      "worst_trade": { "id": "MT5-yyy", "pnl": -227.00 }
    }
  }
}
```

---

### Reflection

#### `GET /trades/:id/reflection`

Get full context and reflection for a specific trade.

**Response** `200 OK`:

```json
{
  "trade_id": "MT5-2350718677",
  "symbol": "XAUUSD",
  "direction": "long",
  "strategy": "VolBreakout",
  "timestamp": "2026-03-03T10:30:00Z",
  "market_context": { "description": "..." },
  "reasoning": "...",
  "pnl": 345.00,
  "exit_reasoning": "...",
  "lessons": "...",
  "grade": null,
  "tags": []
}
```

#### `POST /reflect/daily`

Generate daily reflection summary.

**Request:**

```json
{
  "date": "2026-03-03"
}
```

**Response** `200 OK`:

```json
{
  "date": "2026-03-03",
  "summary": { ... }
}
```

#### `POST /reflect/weekly`

Generate weekly reflection summary.

**Request:**

```json
{
  "week_ending": "2026-03-02"
}
```

#### `POST /reflect/monthly`

Generate monthly reflection summary.

**Request:**

```json
{
  "year": 2026,
  "month": 3
}
```

---

### L2 — Pattern Discovery

#### `POST /patterns/discover`

Trigger L2 pattern discovery from stored trade data.

**Request:**

```json
{
  "starting_balance": 10000.0
}
```

**Response** `200 OK`:

```json
{
  "patterns_discovered": 5,
  "patterns": [
    {
      "pattern_type": "strategy_performance",
      "strategy": "VolBreakout",
      "symbol": "XAUUSD",
      "description": "Win rate 66.7% with PF 1.85",
      "confidence": 0.82,
      "sample_size": 18,
      "discovered_at": "2026-03-03T12:00:00Z"
    }
  ],
  "credits_used": 5
}
```

#### `GET /patterns`

Query stored L2 patterns.

**Query parameters:**

| Param          | Type   | Description              |
|----------------|--------|--------------------------|
| `strategy`     | string | Filter by strategy name  |
| `symbol`       | string | Filter by symbol         |
| `pattern_type` | string | Filter by detector type  |

**Response** `200 OK`:

```json
{
  "count": 5,
  "patterns": [...]
}
```

---

### L3 — Strategy Adjustments

#### `POST /adjustments/generate`

Generate L3 strategy adjustments from L2 patterns.

**Response** `200 OK`:

```json
{
  "adjustments_generated": 3,
  "adjustments": [
    {
      "id": "adj-001",
      "type": "strategy_prefer",
      "strategy": "VolBreakout",
      "description": "Prefer VolBreakout for XAUUSD (PF 1.85, WR 66.7%)",
      "status": "proposed",
      "generated_at": "2026-03-03T12:00:00Z"
    }
  ],
  "credits_used": 5
}
```

#### `GET /adjustments`

Query stored adjustments.

**Query parameters:**

| Param             | Type   | Description                                          |
|-------------------|--------|------------------------------------------------------|
| `status`          | string | Filter: `proposed`, `approved`, `applied`, `rejected` |
| `adjustment_type` | string | Filter by type                                       |

**Response** `200 OK`:

```json
{
  "count": 3,
  "adjustments": [...]
}
```

#### `PATCH /adjustments/:id`

Update the status of an adjustment.

**Request:**

```json
{
  "status": "approved",
  "applied_at": "2026-03-03T14:00:00Z"
}
```

**Response** `200 OK`:

```json
{
  "adjustment_id": "adj-001",
  "status": "approved"
}
```

---

## Error Format

All errors follow a consistent format:

```json
{
  "error": "error_code",
  "message": "Human-readable description"
}
```

| HTTP Code | Error Code            | Description                       |
|-----------|-----------------------|-----------------------------------|
| 400       | `bad_request`         | Invalid request body or params    |
| 401       | `unauthorized`        | Missing or invalid API key        |
| 403       | `forbidden`           | Key lacks permission for this op  |
| 404       | `not_found`           | Resource not found                |
| 409       | `conflict`            | Duplicate trade_id                |
| 422       | `validation_error`    | Request validation failed         |
| 429       | `rate_limited`        | Rate limit exceeded               |
| 402       | `credits_exhausted`   | No credits remaining (Free plan)  |
| 500       | `internal_error`      | Server error                      |

---

## Webhooks (Pro+ plans)

Subscribe to trade events via webhook. Configure in dashboard.

**Events:**

| Event                    | Trigger                              |
|--------------------------|--------------------------------------|
| `trade.stored`           | New trade stored                     |
| `pattern.discovered`     | New L2 pattern found                 |
| `adjustment.generated`   | New L3 adjustment proposed           |
| `reflection.completed`   | Daily/weekly/monthly reflection done |

**Webhook payload:**

```json
{
  "event": "trade.stored",
  "timestamp": "2026-03-03T10:30:00Z",
  "data": { ... }
}
```

Webhooks include an `X-TM-Signature` header (HMAC-SHA256 of body with webhook secret) for verification.

---

## Data Isolation

Each API key belongs to one account. Accounts are fully isolated:
- Trades, patterns, and adjustments are scoped to the account
- No cross-account data access
- Test keys (`tm_test_*`) use a separate data namespace

---

## Migration from Self-Hosted

For users migrating from the local SQLite-based setup:

1. Export trades: `GET /trades?limit=10000` from local server
2. Bulk import: `POST /trades/import` (accepts array of trade objects, max 500 per request)
3. Patterns and adjustments regenerate automatically from imported data

```
POST /trades/import
Content-Type: application/json

{
  "trades": [ ... ]
}
```

**Response** `200 OK`:

```json
{
  "imported": 42,
  "skipped": 0,
  "errors": [],
  "credits_used": 42
}
```
