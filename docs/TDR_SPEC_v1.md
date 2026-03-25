# Trading Decision Record (TDR) Specification v1.0

**Status**: Draft
**Author**: Mnemox AI
**Date**: 2026-03-25
**License**: Apache-2.0

---

## Abstract

This specification defines the **Trading Decision Record (TDR)** — a standardized, tamper-evident audit format for AI-assisted trading decisions. The TDR captures the complete context of a trading decision: what was decided, why it was decided, what memory informed the decision, and what happened afterward.

TDR is designed for:
- Regulatory compliance (MiFID II Article 17, EU AI Act Article 14)
- Post-hoc analysis of AI trading agent behavior
- Cross-system interoperability between trading memory providers

---

## 1. Motivation

AI trading agents make thousands of decisions. Without structured records, it is impossible to:
1. Audit why a specific trade was taken
2. Detect if memory retrieval introduced systematic bias
3. Verify that decision inputs were not tampered with after the fact
4. Satisfy regulatory requirements for algorithmic trading record-keeping

Existing trade logs capture *what happened* (entry, exit, P&L). TDR captures *why it happened* and *what the agent knew at the time*.

---

## 2. Record Structure

### 2.1 Identity Block

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `record_id` | string | yes | Unique, immutable identifier. Matches trade_id. |
| `timestamp` | datetime | yes | Decision timestamp in ISO 8601 UTC. |
| `agent_id` | string | yes | Identifier of the agent/EA that made the decision. |
| `model_version` | string | yes | Version of the trading memory system. |

### 2.2 Decision Block

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `decision_type` | enum | yes | `ENTRY`, `EXIT`, `HOLD`, or `SKIP`. |
| `symbol` | string | yes | Trading instrument (e.g., `XAUUSD`). |
| `direction` | string | no | `long` or `short`. Null for HOLD/SKIP. |
| `strategy` | string | yes | Strategy identifier. |

### 2.3 Context Block (WHY)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `signal_source` | string | yes | What triggered the decision. Human-readable. |
| `confidence_score` | float | yes | Agent confidence at decision time. Range [0.0, 1.0]. |
| `market` | MarketSnapshot | no | Market state at decision time. |

**MarketSnapshot**:

| Field | Type | Description |
|-------|------|-------------|
| `price` | float | Current price |
| `session` | string | Trading session (asian/london/newyork) |
| `regime` | string | Market regime (TRENDING/RANGING/TRANSITIONING) |
| `atr_m5` | float | 5-minute ATR |
| `atr_h1` | float | 1-hour ATR |
| `atr_d1` | float | Daily ATR |
| `spread_points` | int | Current spread in points |
| `ema_fast_h1` | float | Fast EMA on H1 |
| `ema_slow_h1` | float | Slow EMA on H1 |

### 2.4 Memory Block (WHAT informed this)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `similar_trades` | string[] | no | IDs of similar historical trades retrieved. |
| `relevant_beliefs` | string[] | no | Semantic memory propositions consulted. |
| `anti_resonance_applied` | bool | yes | Whether negative balance enforcement was active. |
| `negative_ratio` | float | no | Fraction of negative memories in recall. Range [0.0, 1.0]. |
| `recall_count` | int | no | Total memories retrieved. |

### 2.5 Risk Block

| Field | Type | Description |
|-------|------|-------------|
| `position_size` | float | Lot size / contract quantity |
| `risk_per_trade` | float | Risk in account currency |
| `risk_percent` | float | Risk as % of account equity |
| `max_loss_points` | float | Stop-loss distance in price points |

### 2.6 Outcome Block (filled on exit)

| Field | Type | Description |
|-------|------|-------------|
| `exit_timestamp` | datetime | When position closed |
| `exit_reason` | string | SL, TP, TIMEOUT, MANUAL, EA_CLOSE |
| `pnl` | float | Realized P&L in account currency |
| `pnl_r` | float | P&L in R-multiples (PnL / initial risk) |
| `hold_duration_minutes` | int | Time held |

### 2.7 Audit Block

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `data_hash` | string | yes | SHA-256 hex digest of decision inputs. |

---

## 3. Tamper Detection

### 3.1 Hash Computation

The `data_hash` is computed at record creation time from a deterministic JSON serialization of the decision inputs:

```python
payload = json.dumps({
    "trade_id": record_id,
    "timestamp": str(timestamp),
    "symbol": symbol,
    "direction": direction,
    "strategy": strategy,
    "confidence": confidence_score,
    "reasoning": signal_source,
    "market_context": market,  # full market snapshot dict
}, sort_keys=True, ensure_ascii=True)

data_hash = sha256(payload.encode("utf-8")).hexdigest()
```

### 3.2 Verification

To verify a record has not been tampered with:
1. Retrieve the stored record
2. Recompute the hash from the stored fields using the same algorithm
3. Compare `stored_hash == recomputed_hash`

A mismatch indicates that one or more input fields were modified after creation.

### 3.3 Limitations

- The hash covers decision *inputs*, not outcomes. Outcome fields (pnl, exit_price) are not hashed because they are filled asynchronously.
- The hash does not prevent deletion of records — only modification.
- For chain-of-custody guarantees, use an append-only database or external ledger.

---

## 4. Regulatory Mapping

### MiFID II Article 17 (Algorithmic Trading)

| Requirement | TDR Coverage |
|-------------|-------------|
| "Effective risk controls" | Risk Block (position_size, risk_percent) |
| "Sufficient detail for supervisory review" | Full TDR record |
| "Record of all orders, modifications, cancellations" | Decision + Outcome blocks |
| "Ability to reconstruct algorithm behavior" | Memory Block + Context Block |

### EU AI Act Article 14 (Human Oversight)

| Requirement | TDR Coverage |
|-------------|-------------|
| "Understand capabilities and limitations" | Memory Block (what the agent knew) |
| "Interpret system output" | Context Block (signal_source, confidence) |
| "Decide not to use the system" | anti_resonance_applied flag |
| "Intervene or halt" | decision_type SKIP/HOLD |

**Note**: TDR is *inspired by* these regulations. Full compliance requires legal review for your jurisdiction.

---

## 5. API Reference

### REST Endpoints

```
GET  /audit/decision-record/{trade_id}  → Single TDR (JSON)
GET  /audit/export?start=&end=&strategy= → Array of TDRs (JSON)
GET  /audit/export-jsonl?start=&end=     → TDRs in NDJSON format
GET  /audit/verify/{trade_id}            → Hash verification result
```

### MCP Tools

```
export_audit_trail(trade_id?, strategy?, start?, end?, limit?)
verify_audit_hash(trade_id)
```

---

## 6. Example Record

```json
{
  "record_id": "MT5-7047640363",
  "timestamp": "2026-03-25T10:00:00Z",
  "agent_id": "mt5_sync_v3",
  "model_version": "0.5.0",
  "decision_type": "ENTRY",
  "symbol": "XAUUSD",
  "direction": "long",
  "strategy": "VolBreakout",
  "signal_source": "SELL entry. ATR(M5)=13.62. Spread=33pts. H1 EMA bearish",
  "confidence_score": 0.7,
  "market": {
    "price": 4348.22,
    "session": "london",
    "regime": "TRENDING",
    "atr_m5": 13.62,
    "atr_h1": 45.2,
    "atr_d1": 150.3,
    "spread_points": 33
  },
  "memory": {
    "similar_trades": ["T-2026-0001", "T-2026-0005"],
    "relevant_beliefs": [
      "VolBreakout tends profitable in TRENDING regime (conf=0.72)"
    ],
    "anti_resonance_applied": true,
    "negative_ratio": 0.25,
    "recall_count": 10
  },
  "risk": {
    "position_size": 0.01,
    "risk_per_trade": 25.89,
    "risk_percent": 0.25
  },
  "exit_timestamp": "2026-03-25T14:00:00Z",
  "exit_reason": "TP hit",
  "pnl": 117.80,
  "pnl_r": 0.85,
  "hold_duration_minutes": 240,
  "data_hash": "a3f2b8c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1"
}
```

---

## 7. Versioning

This is TDR Spec v1.0. Future versions may add:
- Chain-of-custody with Merkle trees
- Multi-agent decision attribution
- Streaming TDR for real-time audit dashboards

Backward-compatible additions (new optional fields) will increment minor version. Breaking changes increment major version.
