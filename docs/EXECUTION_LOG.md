# TradeMemory Execution Log

## Phase 0: Supplementary Foundation

### 0.7 Credential Rotation
- Status: DONE
- Started: 2026-03-25
- Completed: 2026-03-25
- Findings: .env was NEVER committed to git history (gitignore was always in place). No BFG needed.
- Changes:
  - Created `C:\Users\johns\Desktop\tradememory-secrets\` (backup of all secrets)
  - Updated `.gitignore` with stricter rules (`.env.*`, `*.key`, `*secrets*`, `!.env.example`)
  - Added `ANTHROPIC_API_KEY` placeholder to `.env.example`
- Files: `.gitignore`, `.env.example`

### 0.1 Event Log Parsing + 0.2 Dynamic Confidence
- Status: DONE
- Started: 2026-03-25
- Completed: 2026-03-25
- Changes:
  - Added `EventLogReader` class to `scripts/mt5_sync_v3.py` (~160 LOC)
  - Matching by `position_id` <-> event_log `pos_id=XXXX` from TRADE_OPEN rows
  - For M260111 (NG_Gold): also matches DECISION events with `score_breakdown`
  - Reasoning now includes: direction, ATR(M5), spread, EMA trend, score breakdown
  - Confidence: from `score_total/100` (DECISION) or spread/ATR ratio (TRADE_OPEN)
  - 7 test cases covering: match, no-match, missing dir, DECISION with score, confidence levels
- Files: `scripts/mt5_sync_v3.py`, `tests/test_event_log_reader.py`

### 0.3 pnl_r Calculation
- Status: DONE
- Completed: 2026-03-25
- Changes:
  - Added R-multiple calculation in `_post_trade_to_memory()`: `pnl / (entry_price * lot_size)`
  - Risk proxy uses ~1% of notional (XAUUSD: entry_price * lot_size * 1.0)
  - Sent as `pnl_r` in `record_outcome` payload
- Files: `scripts/mt5_sync_v3.py`
- Note: Approximate. Real pnl_r needs SL distance, which MT5 deal history doesn't expose.

### 0.4 Exit Reasoning
- Status: DONE
- Completed: 2026-03-25
- Changes:
  - Parse `deal.comment` for [sl]/[tp] tags
  - Detect timeout (hold_duration >= 1440 min = MaxHoldingBars)
  - Default: "Manual or EA close"
  - Appends profit/loss amount
- Files: `scripts/mt5_sync_v3.py`

### 0.5 References Backfill
- Status: DONE
- Completed: 2026-03-25
- Changes:
  - Before `record_decision` POST, calls `recall_similar()` from trade_advisor
  - Top 5 similar trades formatted as references: "id (direction pnl=X.XX)"
  - Graceful fallback on failure (empty list)
- Files: `scripts/mt5_sync_v3.py`

### 0.6 Regime Context
- Status: DONE
- Completed: 2026-03-25
- Changes:
  - Added `read_regime()` function: reads `NG_Regime.dat` binary file (44-byte packed struct)
  - Returns: regime label (TRENDING/RANGING/TRANSITIONING), ATR(H1), ATR(D1), ATR ratio
  - Merged into `market_context.regime` in `record_decision` payload
- Files: `scripts/mt5_sync_v3.py`

### Test Results
- Full suite: 1189 passed, 1 skipped, 0 failed (was 1181 before Phase 0)
- New tests: 7 (test_event_log_reader.py)
