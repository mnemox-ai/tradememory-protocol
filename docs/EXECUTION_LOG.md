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

## Phase 1: Real Data Validation — READY TO START

Baseline collection begins. NG_Gold demo running with enriched mt5_sync_v3.
