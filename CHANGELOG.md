# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Added
- **L3 Strategy Adjustments** — Rule-based strategy tuning from L2 patterns
  - `strategy_adjustments` table in SQLite with proposed/approved/applied/rejected lifecycle
  - 5 deterministic rules: strategy_disable, strategy_prefer, session_reduce, session_increase, direction_restrict
  - `generate_l3_adjustments()` in ReflectionEngine — reads L2 patterns, outputs proposed adjustments
  - 3 CRUD methods in Database: `insert_adjustment`, `query_adjustments`, `update_adjustment_status`
  - 3 REST API endpoints: `POST /reflect/generate_adjustments`, `GET /adjustments/query`, `POST /adjustments/update_status`
  - 21 new tests (CRUD, 5 rules, edge cases, integration) — total 181 tests passing
  - `demo.py` Step 6: production L1→L2→L3 pipeline
- GitHub Actions CI — Python 3.10/3.11/3.12 matrix testing on push/PR
- `scripts/record_demo.py` — Rich-formatted demo for terminal recording
- `docs/AWESOME_LISTS.md` — Awesome list submission tracker
- `SECURITY.md` — Vulnerability reporting policy
- GitHub Discussions templates (Ideas, Show & Tell, Q&A)
- `pyproject.toml` — Full PyPI metadata, `tradememory` CLI entry point

### Changed
- README rewritten: removed marketing tone, honest feature status, developer-focused
- Removed internal docs from public repo (LAUNCH_STRATEGY, DEMO_STORYLINE, ARIADNG_UX_REVIEW)
- CHANGELOG rewritten with honest timeline (no fake sprint numbering)
- Phase 2 features clearly marked as "not yet implemented"
- API.md emoji headers replaced with plain text

### Removed
- `docs/LAUNCH_STRATEGY.md` — Internal strategy document
- `docs/DEMO_STORYLINE.md` — Internal planning document
- `docs/ARIADNG_UX_REVIEW.md` — Internal review document
- `docs/DEMO_RESULTS_TEMPLATE.md` — Unused template
- Legacy `.md` issue templates (replaced by `.yml`)

---

## [0.1.0] - 2026-02-23

Initial open-source release. Built over 2 days of intensive development.

### Added
- Core MCP server (FastAPI) with trade journal, reflection engine, state management
- TradeRecord and SessionState data models (Pydantic v2)
- SQLite database with schema initialization
- TradeJournal — record decisions, outcomes, query history
- ReflectionEngine — daily summary generation (rule-based + optional LLM)
- LLM output validation with rule-based fallback
- StateManager — cross-session persistence, warm memory, risk constraints
- MT5 trade adapter — converts MetaTrader 5 deals to TradeRecord format
- MT5 sync service — polls for closed trades every 60s
- Streamlit monitoring dashboard
- `demo.py` — Interactive demo with 30 simulated XAUUSD trades (no API key needed)
- `install.sh` — One-click install script
- Dockerfile + docker-compose.yml
- `.devcontainer/devcontainer.json` — GitHub Codespaces support
- English and Chinese tutorials (`docs/TUTORIAL.md`, `docs/TUTORIAL_ZH.md`)
- Before/After comparison document (`docs/BEFORE_AFTER.md`)
- Architecture documentation (`docs/ARCHITECTURE.md`)
- API reference, schema docs, reflection format docs
- GitHub issue templates (bug report, feature request, question)
- CONTRIBUTING.md, SECURITY.md
- 111 unit tests (journal, state, reflection, models, LLM validation, adaptive risk, server)
- Guarded `import MetaTrader5` for cross-platform compatibility
- UTC timezone enforcement for all timestamps

### Technical Decisions
- Platform-agnostic core — MT5-specific code isolated in adapters
- LLM outputs validated before entering L2 memory (garbage prevention)
- Rule-based reflection fallback when no API key is configured
- 3-layer memory: L1 (hot/RAM), L2 (warm/JSON), L3 (cold/SQLite)
