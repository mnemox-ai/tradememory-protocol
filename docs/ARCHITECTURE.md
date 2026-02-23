# Architecture Overview

This document describes the internal architecture of TradeMemory Protocol, its module structure, data flow, and the 3-layer memory model.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    External Data Sources                         │
│   MT5 Terminal    Binance API    Alpaca API    Manual Input      │
└───────┬──────────────┬──────────────┬──────────────┬────────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
┌──────────────────────────────────────────────────────────────────┐
│  Adapter Layer                                                   │
│  trade_adapter.py / mt5_sync.py / (future: binance_adapter.py)  │
│  Converts platform-specific data → standardized TradeRecord      │
└──────────────────────────┬───────────────────────────────────────┘
                           │ TradeRecord (Pydantic model)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  TradeMemory Protocol Server (FastAPI + MCP)                     │
│                                                                  │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ TradeJournal │  │ ReflectionEngine │  │  AdaptiveRisk    │   │
│  │              │  │                  │  │  (Phase 2)       │   │
│  │ record_      │  │ generate_daily_  │  │                  │   │
│  │  decision()  │──│  summary()       │──│ get_constraints()│   │
│  │ record_      │  │ _validate_llm_   │  │ check_trade()    │   │
│  │  outcome()   │  │  output()        │  │                  │   │
│  │ query_       │  │ _calculate_      │  │                  │   │
│  │  history()   │  │  daily_metrics() │  │                  │   │
│  └──────┬───────┘  └────────┬─────────┘  └──────────────────┘   │
│         │                   │                                    │
│         ▼                   ▼                                    │
│  ┌──────────────┐  ┌──────────────────┐                         │
│  │ StateManager │  │ Claude API       │                         │
│  │              │  │ (LLM reflection) │                         │
│  │ load_state() │  │ with rule-based  │                         │
│  │ save_state() │  │ fallback         │                         │
│  └──────┬───────┘  └──────────────────┘                         │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              3-Layer Memory Architecture                  │   │
│  │  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐  │   │
│  │  │ L1 (Hot) │  │  L2 (Warm)   │  │    L3 (Cold)      │  │   │
│  │  │ RAM      │  │  JSON files  │  │    SQLite          │  │   │
│  │  └──────────┘  └──────────────┘  └───────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3-Layer Memory Architecture

TradeMemory uses a tiered memory model inspired by how human traders develop expertise: recent events stay sharp in mind (L1), key lessons are curated for quick recall (L2), and the full history is archived for deep analysis (L3).

### L1 — Hot Memory (RAM)

| Property | Value |
|----------|-------|
| **Storage** | In-process Python objects |
| **Lifetime** | Current session only |
| **Access speed** | Instant (no I/O) |
| **Contents** | Active positions, current session state, pending decisions |

L1 holds the working set for a single agent session. When an agent calls `state.load`, the StateManager loads its identity, active positions, and risk constraints into L1. Changes are flushed to L3 on `state.save` or at session end.

**Example contents:**
- 2 open positions (XAUUSD long, GBPUSD short)
- Current risk constraints (max lot 0.05, London session only)
- Session metadata (agent ID, last active timestamp)

### L2 — Warm Memory (JSON files)

| Property | Value |
|----------|-------|
| **Storage** | JSON files in `reflections/` directory |
| **Lifetime** | Persists across sessions |
| **Access speed** | Fast (file read) |
| **Contents** | Curated insights, discovered patterns, reflection reports |

L2 is the agent's "learned knowledge". The ReflectionEngine writes here after daily analysis. Only validated, structured insights make it into L2 — raw LLM output is validated against a template before storage (DEC-010: garbage in L2 is worse than no L2).

**Example contents:**
- "Asian session breakouts have 25% win rate vs 80% in London" (confidence: 0.92)
- "Trades held >45 min average 1.8R vs 1.1R for shorter holds" (confidence: 0.72)
- Risk adjustment: Asian max lot reduced 0.05 → 0.025

### L3 — Cold Memory (SQLite)

| Property | Value |
|----------|-------|
| **Storage** | SQLite database (`data/tradememory.db`) |
| **Lifetime** | Permanent |
| **Access speed** | Standard DB query |
| **Contents** | Every trade record, full history, session state snapshots |

L3 is the complete archive. Every `record_decision` and `record_outcome` call writes here. The ReflectionEngine queries L3 to discover patterns across hundreds of trades. In production, L3 can be swapped for PostgreSQL without changing the application layer.

**Database tables:**

```
trade_records
├── id              TEXT PRIMARY KEY    (T-YYYY-NNNN)
├── timestamp       TEXT                (ISO 8601 UTC)
├── symbol          TEXT                (XAUUSD, BTCUSDT, etc.)
├── direction       TEXT                (long / short)
├── lot_size        REAL
├── strategy        TEXT
├── confidence      REAL                (0.0 - 1.0)
├── reasoning       TEXT
├── market_context  TEXT                (JSON)
├── trade_references TEXT               (JSON array)
├── exit_timestamp  TEXT                (nullable)
├── exit_price      REAL                (nullable)
├── pnl             REAL                (nullable)
├── pnl_r           REAL                (nullable)
├── hold_duration   INTEGER             (nullable, minutes)
├── exit_reasoning  TEXT                (nullable)
├── slippage        REAL                (nullable)
├── execution_quality REAL              (nullable, 0.0-1.0)
├── lessons         TEXT                (nullable)
├── tags            TEXT                (JSON array)
└── grade           TEXT                (nullable, A-F)

session_state
├── agent_id          TEXT PRIMARY KEY
├── last_active       TEXT              (ISO 8601 UTC)
├── warm_memory       TEXT              (JSON object)
├── active_positions  TEXT              (JSON array)
└── risk_constraints  TEXT              (JSON object)
```

**Indexes:** `idx_timestamp` (DESC), `idx_strategy` for common query patterns.

---

## Data Flow

### Single Trade Lifecycle

```
1. CHECK       Agent calls risk.get_constraints()
               ← Returns: {max_lot: 0.05, sessions: [london]}
                  │
2. DECIDE      Agent calls trade.record_decision()
               → Writes TradeRecord to L3 (SQLite)
               → Updates L1 active positions
                  │
3. MONITOR     Trade is open. Agent tracks via trade.get_active()
                  │
4. CLOSE       Agent calls trade.record_outcome()
               → Updates TradeRecord in L3 with exit data
               → Removes from L1 active positions
                  │
5. REFLECT     ReflectionEngine runs (daily at 23:55)
               → Reads all day's trades from L3
               → Calculates metrics (win rate, avg R, etc.)
               → Calls Claude API for pattern analysis
               → Validates LLM output (DEC-010)
               → Writes reflection report to L2 (JSON)
                  │
6. ADAPT       Next session: agent loads updated state
               → L2 insights inform decision-making
               → Risk constraints reflect learned patterns
```

### MT5 Auto-Sync Flow

```
MT5 Terminal (running EA)
    │
    │  MetaTrader5 Python API
    ▼
trade_adapter.py
    │  Polls every 60s for closed positions
    │  Converts MT5 deals → TradeRecord format
    │  Groups deals by position_id
    │  Determines entry/exit, calculates P&L
    ▼
MCP Server API
    │  POST /trade/record_decision
    │  POST /trade/record_outcome
    ▼
TradeJournal → L3 (SQLite)
```

### Daily Reflection Flow

```
daily_reflection.py (triggered by Task Scheduler / cron at 23:55)
    │
    ▼
ReflectionEngine.generate_daily_summary()
    │
    ├── _get_trades_for_date()     ← queries L3
    ├── _calculate_daily_metrics() ← win rate, P&L, avg R
    │
    ├── [If LLM available]
    │   ├── _generate_llm_summary()    ← Claude API call
    │   └── _validate_llm_output()     ← template validation
    │       ├── Valid   → use LLM output
    │       └── Invalid → fall back to rule-based
    │
    └── [If no LLM / fallback]
        └── _generate_rule_based_summary()
    │
    ▼
Write to reflections/YYYY-MM-DD.md (L2)
```

---

## Module Reference

| Module | File | Responsibility |
|--------|------|---------------|
| **Models** | `src/tradememory/models.py` | Pydantic schemas: `TradeRecord`, `MarketContext`, `SessionState` |
| **Database** | `src/tradememory/db.py` | SQLite operations, schema init, CRUD for trades and state |
| **TradeJournal** | `src/tradememory/journal.py` | Trade recording, querying, validation (confidence, direction) |
| **StateManager** | `src/tradememory/state.py` | Session persistence, warm memory, active positions, risk constraints |
| **ReflectionEngine** | `src/tradememory/reflection.py` | Daily summaries, LLM integration, output validation, metrics |
| **MT5Connector** | `src/tradememory/mt5_connector.py` | MT5 trade sync bridge (calls TradeJournal internally) |
| **MCP Server** | `src/tradememory/server.py` | FastAPI endpoints exposing all modules as MCP tools |
| **Trade Adapter** | `trade_adapter.py` | MT5 deal → TradeRecord conversion, sync loop |
| **MT5 Sync** | `mt5_sync.py` | Standalone MT5 polling service |
| **Daily Reflection** | `daily_reflection.py` | Scheduled reflection runner |
| **Dashboard** | `dashboard.py` | Streamlit monitoring UI |

---

## Design Principles

1. **Platform-agnostic core.** MT5-specific code is isolated in `trade_adapter.py` and `mt5_sync.py`. The core modules (`journal`, `state`, `reflection`) know nothing about brokers. Adding Binance or Alpaca means writing a new adapter, not modifying core.

2. **LLM outputs are never trusted blindly.** Every LLM response passes through `_validate_llm_output()` before reaching L2 memory. Invalid output triggers a deterministic rule-based fallback. (DEC-010)

3. **All timestamps in UTC.** No local timezone handling inside the protocol. Adapters convert to UTC at ingestion. (DEC-014)

4. **No ORM.** Direct SQLite with raw SQL for transparency and debuggability. The `Database` class is the only module that touches SQL.

5. **Graceful degradation.** If MT5 is unavailable, the import is guarded (`MT5 = None`). If the LLM API fails, rule-based reflection runs. If no trades exist, the system reports "No trades today" rather than crashing.

---

## See Also

- [SCHEMA.md](SCHEMA.md) — Full data structure reference with JSON examples
- [API.md](API.md) — MCP tool endpoint documentation
- [REFLECTION_FORMAT.md](REFLECTION_FORMAT.md) — Reflection report template
- [README.md](../README.md) — Project overview and quick start
