# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [0.5.4] - 2026-07-29

Hotfix release: an adversarial review immediately after 0.5.3 found three
critical gaps in the new anchoring path. Fixed same-day.

### Fixed
- **Rebuilds no longer destroy existing anchors.** `build_daily_root` used
  `INSERT OR REPLACE`, which nulled a stored `tsa_token` on every rebuild
  (TSA off, TSA failure, or backfill). The token is now carried forward
  when the recomputed root hash is unchanged — and honestly dropped when
  the data (and therefore the root) actually changed.
- **TSA rejections can no longer masquerade as anchors.** `request_timestamp`
  now parses PKIStatus and raises on an explicit rejection (status not in
  granted/grantedWithMods) instead of storing the rejection response and
  reporting `has_tsa_token: true`.
- **`POST /audit/root/{date}` is protect-by-default.** An already-anchored
  root is returned as-is (`already_anchored: true`) instead of being
  rebuilt; pass `force=true` to rebuild. The endpoint is also sync now, so
  the blocking TSA call runs on the threadpool instead of stalling the
  event loop.
- **Anchoring uses the last completed UTC day.** `daily_reflection.py`
  previously used local "yesterday", which on UTC+N machines could anchor
  a UTC day that had not finished yet; backfill runs (`--date`) now anchor
  relative to the target date.
- **`plan_triggered` events dedup per (plan, UTC day)** — agents polling
  `check_active_plans` no longer flood `decision_events` with the same
  standing alert. Plan id is stored in `linked_trade_id` for joins.
- decision_events persistence failures now log at WARNING (was DEBUG).
- Test suite forces `TRADEMEMORY_TSA=off` unconditionally (was
  `setdefault`, which an inherited env var could override).
- Version strings caught up in `server.py` (REST app said 0.5.2) and the
  TSA client User-Agent no longer embeds a stale version.

---

## [0.5.3] - 2026-07-29

### Added
- **Anchored audit by default.** RFC 3161 timestamping of daily Merkle
  roots is now ON unless `TRADEMEMORY_TSA=off`: `build_daily_root` and the
  `get_daily_root` MCP tool default to the env setting, a new
  `POST /audit/root/{date}` REST endpoint builds+timestamps a root, and
  `scripts/daily_reflection.py` anchors yesterday's root as part of the
  daily loop. Only a 32-byte hash leaves the machine — never trade data.
  Backfill paths explicitly skip TSA to avoid hammering the authority.
- **`decision_events` table** — every pre-trade gate check
  (`check_trade_legitimacy`, `compute_dqs`) and every plan trigger is now
  persisted with tier, score, factors and recommendation
  (`Database.insert_decision_event` / `query_decision_events`). This is
  the instrumentation for post-alert behavior metrics (sizing change
  after a caution, skip rate after an alert). Events accumulate from
  v0.5.3 forward; alert history cannot be backfilled.

### Changed
- Hosted MCP endpoint (`/mcp`) now requires the same Bearer
  `tm_live_*`/`tm_test_*` API key as the REST endpoints — it previously
  served tool calls unauthenticated (fixed post-0.5.2, recorded here).
- `LIMITATIONS.md` corrected: the RFC 3161 client shipped in v0.5.2 and
  is on by default in v0.5.3 (previously understated as roadmap-only).

---

## [0.5.2] - 2026-07-29

### Added
- **RFC 3161 TSA client (`audit/tsa.py`)** — opt-in trusted timestamping of
  daily Merkle roots (default endpoint freetsa.org; disabled by default).
  Hand-rolled DER, zero new runtime dependencies.
- **Bearer auth scaffold** for the hosted API surface, and **hybrid recall
  wired into production** (OWM + optional vector fusion).
- **SSRT module (`ssrt/`)** — mSPRT sequential testing engine for strategy
  retirement decisions, with Monte Carlo validation experiments (Phase 1+2).
- **arXiv paper reproduction package** — `research/level2/` now contains the
  full main experiment (`run_matrix.py`, `analyze.py`, `RESULTS.md`, raw
  `results.json`) plus a rolling-reproduction caveat in `research/README.md`.
- **Audit chain (`audit/`).** Per-record content hashes are now linked into a
  forward-chained SHA-256 chain (`chained_hash = SHA256(prev_hash || content_hash)`)
  with a genesis block (`0` * 64). Tampering with any historical record
  invalidates every subsequent link.
  - `audit_chain` table: `record_id`, `sequence_num`, `content_hash`,
    `prev_hash`, `data_hash`, `chained_at`.
  - `audit_roots` table: daily UTC Merkle roots over `audit_chain.data_hash`,
    themselves chained via `prev_root_hash`. `tsa_token` BLOB reserved for
    RFC 3161 (Phase 1.5).
  - New MCP tools: `verify_audit_chain(from_seq, to_seq)`,
    `get_daily_root(date, rebuild=False)`.
  - Existing `verify_audit_hash(trade_id)` now also surfaces the chain entry.
  - `Database.insert_trade` automatically appends to the chain on a fresh
    insert; duplicate-id inserts skip the chain append.
  - `scripts/backfill_audit_chain.py` deterministically rebuilds the chain
    and daily roots from `trade_records` (ORDER BY timestamp, id).
  - 25 new tests in `tests/test_audit_chain.py`.
- **Anti-resonance (`owm/anti_resonance.py`) — real algorithm.** Computes a
  `recall_consonance_score` in `[0, 1]` evaluating whether recalled refs
  collectively support (1.0) or oppose (0.0) the proposed direction.
  - `anti_resonance_applied = score < APPLIED_THRESHOLD` (default 0.4) — i.e.
    counter-evidence dominates. `suppression_recommended = score < 0.2`.
  - `MemoryContext` gains `recall_consonance_score`,
    `evidence_supporting_count`, `evidence_opposing_count`, and
    `suppression_recommended`.
  - 25 new tests in `tests/test_anti_resonance.py`.
- **`LIMITATIONS.md`** at repo root, linked from README. Documents validated
  vs. research-stage components, architecture gaps (no auth, no multi-tenancy,
  parallel DB stacks), broker / LLM coverage, and a per-area roadmap.

### Changed
- **`MemoryContext.anti_resonance_applied`** is no longer `len(refs) > 0`. It
  is now derived from `compute_recall_consonance` against the proposed
  direction. The three call sites (`mcp_server.py` x2 and `server.py`) all
  funnel through a `_build_memory_context` helper.
- TDR `MemoryContext` description updated to reflect the real semantic.

### Fixed
- CI test collection: `numpy` and `hypothesis` are now declared dependencies
  (test collection had been failing on CI since the SSRT and property-based
  test suites were added).
- The three call sites in `mcp_server.py` and `server.py` that set
  `anti_resonance_applied = len(refs) > 0` — a behavioural lie that was
  flagged in the pre-OTSO audit. The flag now reflects actual counter-evidence.

### Notes
- 1,459 tests collected and passing on CI (3.10/3.11/3.12) at release time.
- Phase 5 INVALID result is retained in the research log and now explicitly
  documented in `LIMITATIONS.md` Section 1.

---

## [0.5.1] - 2026-03-27

### Added
- **TDR audit schema (Phase 2)** — Trading Decision Records with REST/MCP
  audit endpoints and per-record tamper detection.
- **DecisionLogReader** — JSONL decision context for rich reasoning.
- **Onboarding CLI** — setup wizard, `doctor`, multi-platform config.
- **event_log integration** and credential hardening for the full trade
  context pipeline.

### Fixed
- Pipeline P0-P2: `strategy_map`, TDR JSONL path, corruption handler.
- Security: path traversal, audit-hash handling, recall_events, and
  local-only binding.

### Changed
- README rewritten around the audit + memory dual-core positioning.

---

## [0.5.0] - 2026-03-16

### Added
- **Evolution Engine** — automated observe → hypothesize → backtest → select loop
  - `src/tradememory/evolution/`: models, backtester, generator, selector, engine
  - LLM-powered pattern discovery (Anthropic Sonnet) with structured JSON output
  - Vectorized backtester: ATR-based SL/TP, long/short, time-based exit, dynamic Sharpe annualization
  - Hypothesis generator: explore/exploit temperature control, graveyard-aware
  - Selection & Elimination: IS rank → OOS validation (Sharpe > 1.0, trade_count > 30, max_dd < 20%)
  - Evolution Orchestrator: multi-generation, configurable population_size/mutation_rate
  - Strategy Graveyard for learning from failures
- **OWM Completion** — all 5 memory types fully implemented
  - Episodic decay: power-law S(t) = S₀ × (1 + t/τ)^(-d) × boost(n) with rehearsal boost
  - Semantic decay: Bayesian Beta(α,β) posterior update, regime_match_factor, τ=180d
  - Auto-induction: episodic patterns → semantic memory (check_auto_induction)
  - Procedural drift: CUSUM detection for behavioral stats (holding time, SL/TP ratio, disposition)
  - Affective EWMA: ewma_confidence (λ=0.9), risk_appetite linked to drawdown
  - Prospective feedback: evaluate_trigger condition matching, record_outcome tracking
- **Platform-Agnostic Data Layer** (Phase 9)
  - DataSource Protocol (runtime_checkable): fetch_ohlcv(), available_symbols()
  - Binance historical data adapter: REST API, rate limiting, parquet cache
  - Context Builder: ATR, trend, volatility regime, time-of-day from OHLCVSeries
  - MT5 CSV adapter: tab/comma auto-detect, DataSource Protocol wrapper
  - OHLCV model, Timeframe enum, OHLCVSeries with IS/OOS split()
- **Evolution MCP Tools** (Phase 11)
  - 5 new MCP tools: fetch_market_data, discover_patterns, run_backtest, evolve_strategy, get_evolution_log
  - 4 REST endpoints: POST /evolution/run, GET /evolution/runs, GET /evolution/runs/{id}, GET /evolution/graveyard
  - 3 Pydantic response models
- **Integration & Validation** (Phase 12)
  - Evolution demo script: mock BTC 1H data, 3-generation evolution, text equity curve
  - Dashboard evolution page: surviving/graveyard tables, fitness trend, run summary
  - Research log auto-write (EXP-00X format)
- 656 new tests (1,055 total, up from 399)

### Changed
- All `from src.tradememory` imports fixed to `from tradememory` (180+ files)
- Sharpe annualization now dynamic per timeframe (was hardcoded sqrt(252))
- Trailing stop uses ATR; SL/TP takes priority over time-based exit

### Stats
- 15 MCP tools (was 10), 30+ REST endpoints
- 1,055 tests passing, 0 failures
- Phases 8-12 complete (P1: 42/42, P2: 20/20)

---

## [0.4.0] - 2026-03-05

### Added
- **Outcome-Weighted Memory (OWM)** — cognitive science-based recall system for AI trading agents
  - 5 memory types: Episodic trade events, Semantic strategy rules, Procedural behavioral patterns, Affective confidence/risk state, Prospective conditional plans
  - Core recall formula: `Score(m,C) = Q(m) * Sim(m,C) * Rec(m) * Conf(m) * Aff(m)`
  - Based on ACT-R (Anderson 2007), Kelly Criterion (Kelly 1956), Bayesian updating, and Tulving's memory taxonomy
- 6 new MCP tools (10 total):
  - `remember_trade` — store trade with full OWM episodic encoding
  - `recall_memories` — outcome-weighted recall with score breakdown
  - `get_behavioral_analysis` — procedural memory behavioral bias detection
  - `get_agent_state` — affective state (confidence, risk appetite, drawdown)
  - `create_trading_plan` — prospective memory conditional plans
  - `check_active_plans` — trigger condition matching against current context
- Kelly-from-memory position sizing with fractional Kelly and risk appetite adjustment
- `docs/OWM_FRAMEWORK.md` — 1,875-line theoretical specification
- OWM data migration utility (`owm/migration.py`)
- 5 new OWM database tables (episodic, semantic, procedural, affective, prospective)
- 7 new REST API endpoints under `/owm/` prefix
- 196 new tests (399 total)

### Changed
- `recall_similar_trades` MCP tool now auto-upgrades to OWM formula when episodic data exists (falls back to original logic otherwise)
- REST API server expanded with 7 new OWM endpoints under `/owm/` prefix

### Migration
- Zero breaking changes. All 4 original MCP tools work identically.
- New OWM tools are additive — use them when ready.
- Run `migration.py` to convert existing trade data to episodic format (optional).

---

## [0.3.1] - 2026-03-03

### Added
- `scripts/research/generate_screenshots.py` — generates demo output for documentation
- `ROADMAP.md` — 5-phase development roadmap
- OpenClaw Skill (`.skills/tradememory/SKILL.md`) with env var declarations and security section
- Hosted API server (`hosted/server.py`) with account isolation and API key auth
- Marketing materials (`marketing/`) for Forex Factory, Reddit, MQL5

### Changed
- Repository reorganized: scripts, docs, and deploy configs moved to proper subdirectories
- All path references updated across 25+ files
- README architecture diagram replaced with Mermaid (GitHub-native rendering)
- Test count unified across all documentation (203 tests)

### Fixed
- ClawHub security scan "Suspicious" marking — env vars now declared in Skill frontmatter
- `test_hosted_server.py` import errors — added `pytest.importorskip("fastapi")`

---

## [0.3.0] - 2026-03-01

### Added
- **L3 Strategy Adjustments** — Rule-based strategy tuning from L2 patterns
  - `strategy_adjustments` table in SQLite with proposed/approved/applied/rejected lifecycle
  - 5 deterministic rules: strategy_disable, strategy_prefer, session_reduce, session_increase, direction_restrict
  - `generate_l3_adjustments()` in ReflectionEngine — reads L2 patterns, outputs proposed adjustments
  - 3 CRUD methods in Database: `insert_adjustment`, `query_adjustments`, `update_adjustment_status`
  - 3 REST API endpoints: `POST /reflect/generate_adjustments`, `GET /adjustments/query`, `POST /adjustments/update_status`
  - 21 new tests (CRUD, 5 rules, edge cases, integration)
  - `demo.py` Step 6: production L1→L2→L3 pipeline
- GitHub Actions CI — Python 3.10/3.11/3.12 matrix testing on push/PR
- `scripts/research/record_demo.py` — Rich-formatted demo for terminal recording
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
