# TradeMemory Execution Log

## Phase 0: Supplementary Foundation — COMPLETE

Commit: `de606f1` | Pushed: 2026-03-25 | Tests: 1199 passed, 1 skipped

### 0.7 Credential Rotation
- Status: DONE
- Findings: .env was NEVER committed to git history. No BFG needed.
- Changes:
  - Created `C:\Users\johns\Desktop\tradememory-secrets\` (backup)
  - `.gitignore` hardened (`.env.*`, `*.key`, `*secrets*`, `!.env.example`)
  - Added `ANTHROPIC_API_KEY` placeholder to `.env.example`

### 0.1 Event Log Parsing + 0.2 Dynamic Confidence
- Status: DONE
- Added `EventLogReader` class (~160 LOC) to `scripts/mt5_sync_v3.py`
- Matching: `position_id` <-> event_log `pos_id=XXXX`
- Reasoning: direction + ATR(M5) + spread + EMA trend + score breakdown
- Confidence: `score_total/100` (DECISION) or spread/ATR ratio (TRADE_OPEN)

### 0.3 pnl_r Calculation (Revised)
- Status: DONE
- **Real R-multiple**, not approximate. Three-layer SL source:
  1. Exit deal comment `[sl XXXX.XX]` (most reliable)
  2. MT5 `history_orders_get` SL field
  3. ATR(M5) x multiplier estimate (VB=1.5x, IM=1.0x)
- Formula: `pnl / (sl_distance * lot_size * contract_size)`
- Contract size from `MT5.symbol_info()`, fallback to hardcoded (XAUUSD=100)

### 0.4 Exit Reasoning
- Status: DONE
- Parses `deal.comment` for `[sl XXXX]` / `[tp XXXX]` with actual price
- Timeout detection (hold >= 1440 min)
- Appends P&L and R-multiple to exit reasoning string

### 0.5 References Backfill
- Status: DONE
- Calls `recall_similar()` before `record_decision`, top 5 similar trades
- Graceful fallback on failure

### 0.6 Regime Context
- Status: DONE
- Reads `NG_Regime.dat` binary (44-byte packed struct)
- Merges regime/ATR(H1)/ATR(D1)/ratio into `market_context.regime`

### Test Results
- Full suite: 1199 passed, 1 skipped, 0 failed
- New tests: 17 (test_event_log_reader.py)

---

## Phase 1: Real Data Validation — BASELINE COLLECTING

NG_Gold demo running with enriched mt5_sync_v3. Awaiting 4 weeks of trade data.

---

## Phase 2: Compliance Output Layer — COMPLETE

Commit: pending | Tests: 1214 passed, 1 skipped

### 2.1 TradingDecisionRecord Schema
- Status: DONE
- Created `src/tradememory/domain/tdr.py` with Pydantic models:
  - `TradingDecisionRecord` — full audit record (MiFID II / EU AI Act inspired)
  - `MemoryContext` — similar_trades, beliefs, anti_resonance_applied, negative_ratio
  - `MarketSnapshot` — price, session, regime, ATR, EMA, spread
  - `RiskSnapshot` — position_size, risk_per_trade, risk_percent
- Factory method: `from_trade_record()` builds TDR from existing DB rows

### 2.2 REST /audit/decision-record/{trade_id}
- Status: DONE
- Returns complete TDR JSON with memory context and data_hash
- Enriches with semantic beliefs from L2 memory layer
- 404 on missing trade

### 2.3 Batch export /audit/export + /audit/export-jsonl
- Status: DONE
- `/audit/export` — JSON array with date range + strategy filters
- `/audit/export-jsonl` — NDJSON (one JSON per line), same filters
- Params: start, end, strategy, limit

### 2.4 MCP tool export_audit_trail + verify_audit_hash
- Status: DONE
- `export_audit_trail` — query by trade_id, strategy, date range (MCP tool #16)
- `verify_audit_hash` — recompute SHA256 and compare (MCP tool #17)

### 2.5 PDF Report
- Status: DEFERRED (Sean's decision)

### 2.6 data_hash Tamper Detection
- Status: DONE
- SHA256 of (trade_id, timestamp, symbol, direction, strategy, confidence, reasoning, market_context)
- Deterministic: same inputs always produce same hash
- `/audit/verify/{trade_id}` endpoint for integrity checking

### Test Results
- 15 new tests in `tests/test_audit.py`
- Covers: TDR schema, hash determinism, hash tamper detection, single record, export JSON/JSONL, date range filter, strategy filter, verify endpoint

---

## Phase 3: Open Source & Promotion — MATERIALS READY

### 3.1 TDR Spec v1.0
- Status: DONE
- File: `docs/TDR_SPEC_v1.md`
- RFC-style spec: 7 sections, record structure, tamper detection, regulatory mapping, API reference, example

### 3.2 anti-resonance Package Design
- Status: DRAFT
- File: `docs/anti-resonance-package.md`
- Package structure, API design, README outline, target audience
- Next: extract code into standalone repo `mnemox-ai/anti-resonance`

### 3.3 MQL5 Forum Article
- Status: DRAFT
- File: `docs/article-adding-memory-to-ea.md`
- "Adding Memory to Your EA: A Practical Guide" — 7 sections + zh-TW outline
- Placeholder for Section 6 (real data results from Phase 1)

### 3.4 Blog Post
- Status: BLOCKED on Phase 1 results
- Will use A/B comparison data once baseline collection completes

### 3.5 Demo Script Update
- Status: DONE
- Added Phase 6 (TDR audit) to `scripts/demo.py`
- Shows: record_id, strategy, confidence, signal, anti_resonance, data_hash, P&L
