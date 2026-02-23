# TradeMemory Protocol - Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## Sprint 5 - 2026-02-23

### Changed
- Brand established as **Mnemox** (mnemox.ai)
- All GitHub URLs updated from `sean-sys` to `mnemox`
- OpenClaw references replaced with Mnemox branding
- Social preview image regenerated with Mnemox URL
- Architecture documentation (`docs/ARCHITECTURE.md`) added

---

## [0.1.0] - 2026-02-23

### Added
- Initial open-source release
- Guarded `import MetaTrader5` for cross-platform compatibility
- Quick Start guide (`docs/QUICK_START.md`)
- Financial disclaimer in README
- GitHub issue templates and PR template

### Fixed
- Python 3.14 `datetime.utcnow()` deprecation warnings (replaced with `datetime.now(timezone.utc)`)
- README test count updated from 27 to 36

---

## Sprint 4 - 2026-02-23

### Added
- Daily reflection runner (`daily_reflection.py`) with Task Scheduler / cron support
- LLM output validation (DEC-010) with rule-based fallback
- 9 new LLM validation tests (total: 36 tests)
- Streamlit monitoring dashboard (`dashboard.py`)
- MT5 sync setup guide (`MT5_SYNC_SETUP.md`)
- Daily reflection setup guide (`DAILY_REFLECTION_SETUP.md`)

### Changed
- ReflectionEngine now validates LLM output before storing in L2 memory
- Improved error handling in trade adapter sync loop

---

## Sprint 3 - 2026-02-23

### Added
- ReflectionEngine with daily summary generation (LLM + rule-based)
- MT5 trade adapter (`trade_adapter.py`) - converts MT5 deals to TradeRecord format
- MT5 sync service (`mt5_sync.py`) - polls for closed trades every 60s
- UTC timezone enforcement for all MT5 timestamps (DEC-014)
- Reflection tests (5 tests)
- Architecture decision records (DEC-001 through DEC-016)

### Changed
- TradeJournal query_history now supports strategy and symbol filters

---

## Sprint 2 - 2026-02-23

### Added
- StateManager for cross-session persistence
- Warm memory (L2) read/write operations
- Active position tracking
- Dynamic risk constraint storage
- State persistence tests (9 tests)
- `.env.example` with all configuration variables

### Changed
- Database schema extended for session state table

---

## Sprint 1 - 2026-02-23

### Added
- Project structure with FastAPI + MCP SDK
- TradeRecord and SessionState data models (Pydantic)
- SQLite database with schema initialization
- TradeJournal module (record_decision, record_outcome, query_history)
- MarketContext model (price, ATR, session, indicators)
- Initial test suite (13 tests)
- README with architecture diagram
- docs/SCHEMA.md, docs/API.md, docs/REFLECTION_FORMAT.md
- MIT License, CONTRIBUTING.md
