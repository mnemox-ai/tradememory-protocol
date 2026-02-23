# TradeMemory Data Schema

This document describes the core data structures used in TradeMemory Protocol. All examples show actual JSON payloads that you'll work with when calling MCP tools.

---

## TradeRecord

The `TradeRecord` is the fundamental unit of memory in TradeMemory. Every trade decision is recorded with this structure.

### Schema

```typescript
{
  // Identifiers
  id: string              // Unique trade ID (format: T-YYYY-NNNN)
  timestamp: datetime     // Decision timestamp (ISO 8601 UTC)
  
  // Trade Parameters
  symbol: string          // Trading instrument (XAUUSD, BTCUSDT, etc.)
  direction: "long" | "short"
  lot_size: float         // Position size
  strategy: string        // Strategy tag (VolBreakout, Pullback, etc.)
  confidence: float       // Agent's confidence score (0.0 - 1.0)
  
  // Decision Context
  reasoning: string       // Natural language explanation of WHY
  market_context: {
    price: float          // Entry price
    atr: float            // Current ATR (Average True Range)
    session: string       // Trading session (asian/london/newyork)
    indicators?: dict     // Optional: relevant indicator values
    news_sentiment?: float // Optional: -1.0 to 1.0
  }
  references: string[]    // References to past trades (e.g., ["T-2026-0247"])
  
  // Outcome (filled after trade closes)
  exit_timestamp?: datetime
  exit_price?: float
  pnl?: float             // Realized P&L in account currency
  pnl_r?: float           // P&L in R-multiples
  hold_duration?: int     // Minutes held
  exit_reasoning?: string // Why the agent exited
  slippage?: float        // Entry slippage in pips
  execution_quality?: float // 0.0 - 1.0 score
  
  // Post-Trade Reflection (filled by ReflectionEngine)
  lessons?: string        // What was learned
  tags?: string[]         // Auto-generated pattern tags
  grade?: "A" | "B" | "C" | "D" | "F" // Quality of decision
}
```

### Example: Recording a Trade Decision

**Request to `trade.record_decision`:**

```json
{
  "symbol": "XAUUSD",
  "direction": "long",
  "lot_size": 0.05,
  "strategy": "VolBreakout",
  "confidence": 0.72,
  "reasoning": "London session open with strong momentum above 20-period high. Volume spike confirmed at 09:03. Price broke 2890 resistance with conviction. Similar setup to successful trade T-2026-0247 on Feb 15.",
  "market_context": {
    "price": 2891.50,
    "atr": 28.3,
    "session": "london",
    "indicators": {
      "rsi_14": 58.2,
      "bb_position": 0.82,
      "volume_ratio": 1.45
    }
  },
  "references": ["T-2026-0247"]
}
```

**Response:**

```json
{
  "trade_id": "T-2026-0251",
  "timestamp": "2026-02-23T09:03:42Z",
  "status": "recorded"
}
```

### Example: Recording Trade Outcome

**Request to `trade.record_outcome`:**

```json
{
  "trade_id": "T-2026-0251",
  "exit_price": 2897.20,
  "pnl": 28.50,
  "pnl_r": 2.1,
  "exit_reasoning": "Hit 2R target at 2897. Momentum fading near previous resistance zone. Trailing stop would have been better in hindsight.",
  "lessons": "Good entry timing on volume confirmation. Exit was premature — price continued to 2902. Consider implementing trailing stop for strong momentum trades.",
  "hold_duration": 87,
  "slippage": 0.3,
  "execution_quality": 0.88
}
```

**Response:**

```json
{
  "trade_id": "T-2026-0251",
  "status": "outcome_recorded",
  "pnl": 28.50,
  "pnl_r": 2.1
}
```

---

## SessionState

Represents the agent's persistent state across sessions. Loaded at the start of every session via `state.load`.

### Schema

```typescript
{
  // Agent Identity
  agent_id: string        // Unique agent identifier
  agent_name: string      // Human-readable name
  personality?: string    // Optional: agent personality context
  
  // Session Context
  session_id: string      // Current session ID
  last_active: datetime   // Last activity timestamp
  
  // Active Positions
  active_positions: {
    trade_id: string
    symbol: string
    direction: "long" | "short"
    lot_size: float
    entry_price: float
    entry_time: datetime
    unrealized_pnl?: float
  }[]
  
  // Warm Memory (L2)
  curated_insights: {
    pattern: string       // Pattern description
    confidence: float     // 0.0 - 1.0
    evidence: string[]    // Supporting trade IDs
    created_at: datetime
  }[]
  
  // Risk Parameters (updated by AdaptiveRisk)
  risk_constraints: {
    max_lot_size: float
    risk_per_trade_percent: float
    allowed_sessions: string[]    // e.g., ["london", "newyork"]
    restricted_strategies?: string[]
    reason?: string               // Why these constraints
  }
  
  // Performance Metrics
  performance: {
    total_trades: int
    win_rate: float
    avg_pnl_r: float
    current_streak: int           // Positive = wins, negative = losses
    sharpe_ratio?: float
  }
}
```

### Example: Loading State

**Request to `state.load`:**

```json
{
  "agent_id": "ng_gold_v1"
}
```

**Response:**

```json
{
  "agent_id": "ng_gold_v1",
  "agent_name": "NG Gold Trading Agent",
  "session_id": "sess-2026-02-23-001",
  "last_active": "2026-02-23T08:45:12Z",
  
  "active_positions": [
    {
      "trade_id": "T-2026-0250",
      "symbol": "XAUUSD",
      "direction": "long",
      "lot_size": 0.05,
      "entry_price": 2888.30,
      "entry_time": "2026-02-23T07:12:33Z",
      "unrealized_pnl": 12.50
    }
  ],
  
  "curated_insights": [
    {
      "pattern": "Asian session breakout trades have 25% win rate vs 80% in London session",
      "confidence": 0.92,
      "evidence": ["T-2026-0241", "T-2026-0243", "T-2026-0245", "T-2026-0248"],
      "created_at": "2026-02-22T23:00:00Z"
    },
    {
      "pattern": "Trades with confidence > 0.7 have 2x better win rate than confidence < 0.5",
      "confidence": 0.87,
      "evidence": ["T-2026-0230", "T-2026-0235", "T-2026-0242"],
      "created_at": "2026-02-22T23:00:00Z"
    }
  ],
  
  "risk_constraints": {
    "max_lot_size": 0.05,
    "risk_per_trade_percent": 1.0,
    "allowed_sessions": ["london", "newyork"],
    "reason": "Asian session performance poor (3 consecutive losses). Reduced exposure until pattern improves."
  },
  
  "performance": {
    "total_trades": 47,
    "win_rate": 0.638,
    "avg_pnl_r": 1.24,
    "current_streak": 2,
    "sharpe_ratio": 1.83
  }
}
```

---

## ReflectionReport

Generated by the `ReflectionEngine` after daily/weekly analysis. Retrieved via `reflect.get_insights`.

### Schema

```typescript
{
  // Report Metadata
  report_id: string
  report_type: "daily" | "weekly" | "monthly"
  period_start: datetime
  period_end: datetime
  generated_at: datetime
  
  // Performance Summary
  summary: {
    total_trades: int
    winners: int
    losers: int
    net_pnl: float
    win_rate: float
    avg_r: float
  }
  
  // Discovered Patterns
  patterns: {
    type: "positive" | "negative" | "neutral"
    description: string
    evidence: string[]      // Trade IDs
    confidence: float
    recommendation?: string // What to do about it
  }[]
  
  // Risk Adjustments Made
  risk_adjustments: {
    parameter: string       // What was changed
    old_value: any
    new_value: any
    reason: string
  }[]
  
  // Carry Forward Items
  action_items: string[]    // Things to monitor/test next period
}
```

### Example: Weekly Reflection Report

**Request to `reflect.get_insights`:**

```json
{
  "report_type": "weekly",
  "week": "2026-W08"
}
```

**Response:**

```json
{
  "report_id": "REFL-2026-W08",
  "report_type": "weekly",
  "period_start": "2026-02-17T00:00:00Z",
  "period_end": "2026-02-21T23:59:59Z",
  "generated_at": "2026-02-22T00:15:33Z",
  
  "summary": {
    "total_trades": 12,
    "winners": 8,
    "losers": 4,
    "net_pnl": 187.30,
    "win_rate": 0.667,
    "avg_r": 1.24
  },
  
  "patterns": [
    {
      "type": "positive",
      "description": "VolBreakout strategy performed exceptionally in London session (5/5 wins). Confidence correlation strong: trades with confidence > 0.7 had 80% win rate vs 40% below 0.7.",
      "evidence": ["T-2026-0241", "T-2026-0243", "T-2026-0247", "T-2026-0249", "T-2026-0251"],
      "confidence": 0.94,
      "recommendation": "Increase London session allocation. Consider raising max lot size for high-confidence London breakouts."
    },
    {
      "type": "negative",
      "description": "Asian session entries continue to underperform. 3 of 4 losses were Asian session. Low volatility causing false breakouts.",
      "evidence": ["T-2026-0238", "T-2026-0242", "T-2026-0245"],
      "confidence": 0.89,
      "recommendation": "Reduce Asian session position size by 50% or skip entirely until pattern changes."
    },
    {
      "type": "neutral",
      "description": "Holding winners longer than 45 minutes improved average R from 1.1 to 1.8. Current exit timing may be too aggressive.",
      "evidence": ["T-2026-0247", "T-2026-0249"],
      "confidence": 0.72,
      "recommendation": "Test trailing stop approach on strong momentum trades."
    }
  ],
  
  "risk_adjustments": [
    {
      "parameter": "asian_session_max_lot",
      "old_value": 0.05,
      "new_value": 0.025,
      "reason": "Asian session win rate dropped to 25%. Reducing exposure."
    },
    {
      "parameter": "london_breakout_max_lot",
      "old_value": 0.05,
      "new_value": 0.08,
      "reason": "London VolBreakout strategy earned more room with 100% win rate this week."
    }
  ],
  
  "action_items": [
    "Monitor if Asian session pattern continues next week",
    "Test trailing stop implementation on London session trades",
    "Watch for NFP impact on Friday (high volatility expected)"
  ]
}
```

---

## RiskConstraints

Current risk parameters enforced by `AdaptiveRisk` module. Retrieved via `risk.get_constraints`.

### Schema

```typescript
{
  // Global Constraints
  max_lot_size: float           // Maximum position size per trade
  risk_per_trade_percent: float // Max risk as % of account
  max_daily_loss: float         // Circuit breaker (optional)
  max_open_trades: int          // Maximum concurrent positions
  
  // Session-Specific
  allowed_sessions: string[]    // Which trading sessions are allowed
  session_constraints?: {
    [session: string]: {
      max_lot_size: float
      max_trades_per_session: int
    }
  }
  
  // Strategy-Specific
  strategy_constraints?: {
    [strategy: string]: {
      max_lot_size: float
      min_confidence: float     // Minimum confidence to trade this strategy
    }
  }
  
  // Metadata
  last_updated: datetime
  reason: string                // Why these constraints exist
}
```

### Example: Getting Current Constraints

**Request to `risk.get_constraints`:**

```json
{
  "agent_id": "ng_gold_v1"
}
```

**Response:**

```json
{
  "max_lot_size": 0.08,
  "risk_per_trade_percent": 1.0,
  "max_daily_loss": 150.0,
  "max_open_trades": 3,
  
  "allowed_sessions": ["london", "newyork"],
  "session_constraints": {
    "london": {
      "max_lot_size": 0.08,
      "max_trades_per_session": 5
    },
    "newyork": {
      "max_lot_size": 0.05,
      "max_trades_per_session": 3
    },
    "asian": {
      "max_lot_size": 0.025,
      "max_trades_per_session": 2
    }
  },
  
  "strategy_constraints": {
    "VolBreakout": {
      "max_lot_size": 0.08,
      "min_confidence": 0.65
    },
    "Pullback": {
      "max_lot_size": 0.05,
      "min_confidence": 0.70
    }
  },
  
  "last_updated": "2026-02-22T23:00:15Z",
  "reason": "Adjusted based on weekly reflection. London VolBreakout earned more room (5/5 wins). Asian session reduced due to poor performance."
}
```

---

## Notes for Developers

### Timestamps
- All timestamps are **ISO 8601 format in UTC**
- Example: `"2026-02-23T09:03:42Z"`

### Trade IDs
- Format: `T-YYYY-NNNN` (e.g., `T-2026-0251`)
- Auto-generated by TradeJournal on `record_decision`

### Confidence Scores
- Range: `0.0` to `1.0`
- `< 0.5`: Low confidence
- `0.5 - 0.7`: Medium confidence
- `> 0.7`: High confidence
- The ReflectionEngine uses this to correlate confidence with win rate

### R-Multiples
- Standardized way to measure trade performance
- `pnl_r = actual_pnl / initial_risk`
- Example: If you risk $10 and make $21 profit, that's 2.1R

### Sessions
- Standard values: `"asian"`, `"london"`, `"newyork"`
- Custom sessions can be defined per market

---

## Validation Rules

TradeMemory enforces these rules when recording trades:

1. **Required fields on `record_decision`:**
   - `symbol`, `direction`, `lot_size`, `strategy`, `confidence`, `reasoning`, `market_context.price`, `market_context.session`

2. **Confidence must be between 0.0 and 1.0**

3. **Lot size must not exceed `risk_constraints.max_lot_size`**

4. **Session must be in `risk_constraints.allowed_sessions`** (if defined)

5. **Trade outcome can only be recorded once per trade_id**

6. **Exit timestamp must be after entry timestamp**

---

## See Also

- [README.md](../README.md) — Project overview
- [API.md](API.md) — HTTP endpoint documentation
