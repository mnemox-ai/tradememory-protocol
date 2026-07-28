# TradeMemory Protocol — Known Limitations & Roadmap

> Last updated: 2026-07-29 · Applies to: v0.5.2 (post-audit-chain refit)

We publish this document because partners, regulators, and the open-source
community deserve to know what TradeMemory does **today**, what is **research-
stage**, and what is **planned but not yet shipped**. If you see something
on our README, in a talk, or in the paper that conflicts with this file —
**this file is canonical**. Open an issue and we will fix the inconsistency
upstream.

The goal is to be a partner you can build on without surprises later.

---

## 1. Empirical validation status

### What is validated
- **L2 multi-strategy CUSUM detector** — 200 strategies × 6 agents, 73.5% win
  rate vs baseline, d=0.76, p≈0, bootstrap CI [+3180, +4560], 4/4 statistical
  gates pass. See `scripts/research/phase4_results.md`.
- **mSPRT (tau=0.3) drift engine** — 22,500 Monte Carlo runs, 81.4% power
  with Type-I=0.008 (the only method in the comparison below the 5%
  threshold). See `validation/ssrt/`.
- **OWM recall scoring** — covered by 1,374+ unit and property-based tests.

### What is NOT validated (research-stage, do not trust for alpha decisions)
- **Phase 5 rigorous validation: INVALID.** 100 experiments (2 symbols × 1h ×
  50 grid strategies × 5 agents) showed that the CalibratedAgent skipped 97%
  of trades, so the apparent drawdown reduction came from *not trading*, not
  from skill. 0/100 DSR PASS. Sensitivity sweep collapsed (all 10 hazard
  rates produced identical 0.9883 reduction). See `scripts/research/phase5_results.md`.
  - **What this means for you:** the DQS skip-tier thresholds were too
    aggressive on a cold-start database. The L1+L2 components themselves
    are sound; the integrated 4-tier gating is what failed validation.
- **BOCPD changepoint detector** — flagged "DEAD" on sparse binary outcomes
  in Level 0/1 validation. Not recommended as the sole drift signal. CUSUM
  + mSPRT are the recommended detectors today.
- **DQS (Decision Quality Score)** — flagged "DEAD" at the integration level
  in Phase 5; the underlying 5 factors compute correctly, the calibration
  layer is what we are still rebuilding.

### Path to clean validation
- **Phase 6 (Q3 2026):** revisit DQS calibration on a denser real-trade
  corpus; rerun the 4-tier gate with a less aggressive skip threshold.
- **Live partner pilot:** the OTSO conversation, if it converges, will
  generate the multi-broker, multi-strategy ground truth we currently lack.

---

## 2. Architecture maturity

### Today (v0.5.2)
- **Single-tenant SQLite** is the production storage layer (`db.py`).
- FastAPI REST server binds to `127.0.0.1` only — there is an explicit
  comment in `server.py` line ~40 noting this.
- **No bearer-token auth, no API keys, no RBAC, no rate limiting.**
- Memory is local-process — no horizontal scaling.

### In progress
- A second PostgreSQL stack lives in parallel under `database.py`,
  `alembic/`, `repositories/`, and `services/`. This is the dashboard +
  hybrid-recall track and is **not yet the production write path**. You
  will see two DB layers in the repo — this is a known mid-migration state,
  not a permanent architecture.

### 30-day roadmap (gates on enterprise pilots)
- `tenant_id` + bearer-token authentication on every REST endpoint.
- Bring `hybrid_recall.py` (pgvector + outcome-weighted fusion) into the
  production hot path; it currently exists but is not wired in.
- Decide and document a single canonical DB stack to converge on.

### 60-90 day roadmap
- Row-level encryption for hosted deployments.
- OTEL traces + Prometheus metrics.
- JS / Go SDKs (today the client surface is Python + MCP only).

---

## 3. Audit chain maturity

### Today (v0.5.2 — new in this release)
- **Linked SHA-256 chain.** Every TDR's content hash is linked via
  `chained_hash = SHA256(prev_chained_hash || content_hash)`. Tampering
  with any historical record invalidates every subsequent link.
- **Daily Merkle roots.** Each UTC day's chained hashes are summarised by
  a Merkle root; roots themselves chain across days via `prev_root_hash`.
- **MCP tools:** `verify_audit_hash`, `verify_audit_chain`,
  `get_daily_root`. Tests: `tests/test_audit_chain.py` (25 cases).
- **Backfill script** at `scripts/backfill_audit_chain.py` deterministically
  rebuilds the chain from `trade_records` (ORDER BY timestamp, id).

### What this gives you
- Per-record tamper detection (was always there, via content hash).
- **NEW:** cross-record tamper detection (chain), and a compact daily root
  that can be published externally.

### What is NOT in v0.5.2
- **RFC 3161 TSA timestamping** — daily roots are local-only today. A
  `tsa_token BLOB` column is reserved on `audit_roots` for the
  TimeStampToken; the client code is on the 1-2 week roadmap.
- **External anchoring** (OpenTimestamps / blockchain / public log). On the
  60-day roadmap.
- **zkML proof of inference** — proving "this strategy was actually run on
  this market context to produce this decision" is on the 90-day roadmap
  via EZKL integration. The audit chain proves *memory existed*; zkML
  would prove *computation was honest*.

---

## 4. Anti-resonance (NEW in v0.5.2)

### What changed
The `MemoryContext.anti_resonance_applied` flag in earlier versions was set
to `len(refs) > 0` at three call sites — i.e. it was True whenever any
similar memory was recalled, regardless of whether the recalled evidence
opposed the proposed action. This was misleading and we have fixed it.

### Today
- `owm/anti_resonance.py` implements `compute_recall_consonance(refs,
  proposed_direction)`. Each ref's `pnl_r` and `direction` are weighted by
  similarity and capped at 3R, then averaged. Output: a consonance score
  in `[0, 1]` where 1 = full support, 0 = full opposition.
- `anti_resonance_applied = score < 0.4` (i.e., counter-evidence
  dominates).
- `suppression_recommended = score < 0.2` (strong counter-evidence — agent
  should consider blocking the trade).
- TDR now carries `recall_consonance_score`, `evidence_supporting_count`,
  `evidence_opposing_count`, and `suppression_recommended`.

### Limitations
- Thresholds (0.4 / 0.2) are reasonable defaults but not yet tuned on real
  trade data. They will be SSRT-tuned in Phase 6.
- The scoring weights `pnl_r` linearly up to 3R. A skewed-distribution
  weighting (e.g., log-pnl) is plausible and on the research backlog.
- Empirical validation that this reduces real drawdown is **not yet
  available** — Phase 5 ran on a different (legacy boolean) flag. New
  validation is in progress.

---

## 5. Broker coverage

### Today
- **MetaTrader 5 only** (`mt5_connector.py`). Polling sync, not event-driven.

### Roadmap
- IBKR (30-60 day) and Alpaca (60-90 day) connectors for the US equity
  segment.
- CCXT (60-90 day) for crypto venues — driven by the Polystrat / agent-
  marketplace direction.
- FIX gateway is on the long-term backlog (180+ day).

---

## 6. LLM provider coverage

### Today
- The `evolution/llm.py` calls go through `anthropic.AsyncAnthropic` only.

### Roadmap
- OpenAI fallback (30 day) — the Protocol abstraction is already in place,
  it just isn't implemented yet.
- Local model support via Ollama / vLLM (60-90 day).

---

## 7. Operational gaps you should know about

- **No HA / replication.** SQLite is a single file. Backup is `cp tradememory.db tradememory.db.bak`.
- **No baseline metrics endpoint** (no Prometheus / OTEL). The `/health`
  endpoint exists; serious observability is on the roadmap.
- **CHANGELOG** is current through v0.5.2 (0.5.1 and 0.5.2 sections added
  2026-07-29).
- **db.py uses raw `CREATE TABLE IF NOT EXISTS`** — this violates our own
  internal migration checklist. The PG track uses Alembic
  properly; the SQLite layer will follow when we converge stacks.

---

## What we are confident about (the strong parts)

We list limitations here precisely because the strong parts are strong:

- **OWM recall math** (`owm/recall.py`) — 5-factor scoring (Q · Sim · Rec ·
  Conf · Aff), pure Python, well-tested, defensible in the paper.
- **BOCPD / CUSUM / mSPRT** — implemented from scratch, validated where
  marked, not borrowed from third-party libraries we cannot reproduce.
- **5 memory layers** (episodic / semantic / procedural / affective /
  prospective) with documented inter-layer flows and ADRs.
- **MCP standard, native integration** (not a wrapper) — Linux Foundation's
  Agentic AI Foundation governs MCP as of Dec 2025; we ship against the
  reference spec.
- **1,400+ tests** including hypothesis property-based and integration
  tests without mocks.
- **Honest research log** — the same one that flagged Phase 5 INVALID is
  the one we cite in talks. We don't hide adverse results.

---

## How to reach us

If something in this document is wrong, outdated, or you spot a gap that
isn't listed — open an issue or email `dev@mnemox.ai`. We update this file
in the same commit as the change it describes.
