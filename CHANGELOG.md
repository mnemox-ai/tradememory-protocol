# TradeMemory Protocol - Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Added
- GitHub Actions CI pipeline — Python 3.10/3.11/3.12 matrix testing on push/PR
- `scripts/record_demo.py` — Rich-formatted demo for asciinema/terminalizer recording
- `docs/AWESOME_LISTS.md` — Submission tracker for awesome-mcp-servers lists
- `SECURITY.md` — Security vulnerability reporting policy
- GitHub Discussions templates (Ideas, Show & Tell, Q&A)
- `pyproject.toml` — Full PyPI metadata, entry point (`tradememory` CLI), project URLs

### Changed
- `pyproject.toml` — Updated author to Mnemox, requires-python lowered to 3.10, added classifiers and keywords
- `server.py` — Added `main()` entry point for CLI usage
- Issue templates — Removed legacy `.md` templates, kept structured `.yml` versions
- CHANGELOG — Backfilled Week 1-3 sprint changes

---

## Sprint 7 (Week 3) - 2026-02-24

### Added
- `.github/workflows/ci.yml` — GitHub Actions CI with Python 3.10/3.11/3.12 matrix
- `scripts/record_demo.py` — Rich library demo for terminal recording (asciinema/terminalizer)
- `docs/AWESOME_LISTS.md` — Awesome list submission tracker
- README CI badge (passing/failing)
- README demo GIF recording instructions

### Removed
- Legacy `.md` issue templates (replaced by `.yml` versions)

---

## Sprint 6 (Week 2) - 2026-02-24

### Added
- `Dockerfile` — Python 3.11-slim, pip install, default MCP server start
- `docker-compose.yml` — ANTHROPIC_API_KEY env, persistent volume for data
- `.dockerignore` — Exclude non-essential files from Docker image
- `docs/BEFORE_AFTER.md` — 5-stage before/after comparison with quantified data (EN+ZH)
- `.devcontainer/devcontainer.json` — GitHub Codespaces support (Python 3.11, auto setup)
- `CONTRIBUTING.md` — Complete rewrite: fork/branch/PR flow, code style, testing requirements
- README "Open in GitHub Codespaces" badge
- README Docker usage section

---

## Sprint 5 (Week 1) - 2026-02-23

### Added
- `demo.py` — Interactive demo: 30 simulated XAUUSD trades, full L1→L2→L3 pipeline, no API key needed
- `install.sh` — One-click install script (Python check, venv, pip, test, success message)
- `docs/TUTORIAL.md` — English step-by-step tutorial (6 steps, install to memory-powered trading)
- `docs/TUTORIAL_ZH.md` — Traditional Chinese step-by-step tutorial
- README before/after comparison table
- README one-line install command
- README tutorial links

### Changed
- Brand established as **Mnemox** (mnemox.ai), GitHub org: mnemox-ai
- All GitHub URLs updated to `mnemox-ai/tradememory-protocol`
- Social preview image regenerated with Mnemox branding
- Architecture documentation (`docs/ARCHITECTURE.md`) added

### Fixed
- Windows cp950 encoding error in demo.py (force UTF-8 output)
- All GitHub URLs changed from `/main/` to `/master/` branch references
- README Contributing section aligned with CONTRIBUTING.md

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
- Pydantic v2 `class Config` deprecation (migrated to `model_config = ConfigDict(...)`)
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
