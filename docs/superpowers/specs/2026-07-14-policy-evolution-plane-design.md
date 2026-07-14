# TradeMemory Policy Evolution Plane — Design Specification

**Status:** Approved design
**Date:** 2026-07-14
**Owner:** Mnemox AI
**Scope:** TradeMemory Protocol core, MT5 reference adapter, local/cloud boundary

## 1. Executive Summary

TradeMemory will evolve from a persistent trading-memory service into a broker-neutral **Evolution and Control Plane**. It will convert observed trading outcomes into versioned recall, risk, and strategy policies; validate challengers against a champion; deploy them through staged rollouts; and automatically promote or roll back personal policies inside an immutable user risk envelope.

TradeMemory never becomes an execution engine. External EAs, agents, and broker adapters consume signed policy bundles, make deterministic execution decisions, and return evidence events. Raw trades, strategy intellectual property, and personal evolution remain local or inside the customer's VPC. An optional hosted service coordinates policy metadata, managed evaluation, dashboards, and privacy-preserving cohort intelligence. Enterprise customers may deploy the data plane through BYOC/VPC.

The first end-to-end reference implementation is MT5/NG_Gold. It uses a production decision core, an MT5 live adapter, an MT5 Strategy Tester adapter, deterministic tick fixtures, a golden event ledger, and champion/challenger replay.

## 2. Product Outcomes

The system is designed to produce four measurable outcomes:

1. Reduce repeated behavioral and risk-policy violations.
2. Improve risk-adjusted outcomes without increasing leverage or suppressing nearly all trading opportunities.
3. Make every policy change reproducible, attributable, reversible, and auditable.
4. Create a portable evolution protocol that works across traders, EAs, agents, and brokers.

The product does not promise profits, win-rate improvement, or autonomous alpha discovery. Financial effectiveness is always expressed as evidence with uncertainty, not as certainty.

## 3. Locked Product Decisions

- The architecture is a **Protocol-centered Evolution Plane**.
- The three evolvable policy types are `RecallPolicy`, `RiskPolicy`, and `StrategyPolicy`.
- Personal mode supports automatic staged promotion. The default profile is `Balanced`; users may choose `Conservative`, `Aggressive`, or `Manual`, and may opt out at any time.
- Institutional mode requires human approval and separation of duties before assignment changes.
- The objective is risk-first and multi-objective. Raw P&L is never the sole fitness function.
- Cold start uses global safety priors, optional cohort priors, and progressively dominant personal evidence.
- Cohort participation is explicit opt-in. Raw trades, prompts, embeddings, strategy parameters, and identifiable time series never enter the shared cohort service.
- Local/VPC stores raw evidence and runs personal evolution. Cloud coordinates and aggregates. Enterprise supports BYOC/VPC.
- TradeMemory never sends orders or stores broker execution credentials.
- The Adapter Protocol and reference adapters are open. Hosted cohort intelligence, managed validation, certified connectors, team workflows, and enterprise controls are commercial surfaces.
- Public product delivery has two layers sharing one backend: developer protocol and an official MT5 trader application.

## 4. Architecture

```text
External EA / Agent / Broker Adapter
        |
        v
Ingestion + Domain Event Store
        |
        +--> Journal / Memory / Performance Projections
        |          |
        |          v
        |     Evolution Plugins
        |          |
        |          v
        |       Validation
        |          |
        |          v
        |   Promotion Controller
        |          |
        |          v
        | Policy Assignment Registry
        |          |
        |          v
        +---- Policy Resolver ----> signed PolicyBundle
                                      |
                                      v
                              External adapter executes
```

### 4.1 Bounded Contexts

#### Evidence

Owns append-only domain events, idempotency, bitemporal availability, event corrections, integrity hashes, and projection checkpoints. Evidence distinguishes observable financial facts from control-plane decisions.

#### Memory

Owns episodic, semantic, procedural, affective, and prospective projections. OWM reads evidence projections and a resolved immutable `RecallPolicy`. It does not write policy assignments.

#### Evolution

Owns hypotheses and immutable policy candidates. It operates on frozen dataset manifests and cannot change validation rules, sealed holdouts, hard risk limits, or assignments.

#### Validation

Runs policy-specific evaluators and records reproducible results. It has no permission to activate policies. Strategy, recall, and risk policies share orchestration contracts but not outcome models or statistical assumptions.

#### Control

Owns rollout state, policy assignments, promotion, pause, rollback, and approval rules. The `PromotionController` is the only writer of policy assignments.

#### Cohort

Imports and exports privacy-preserving aggregate priors. It cannot access raw personal events and cannot directly activate a policy.

#### Adapters

MCP, REST, SDKs, MT5, and future connectors translate external messages into domain commands and events. They cannot bypass the control plane or mutate lifecycle tables directly.

## 5. Core Domain Model

### 5.1 DomainEvent

`DomainEvent` is the immutable event envelope for both evidence and control events.

Required fields:

- `event_id`
- `event_kind`: `evidence` or `control`
- `event_type`
- `schema_version`
- `stream_id`
- `sequence`
- `source`
- `source_event_id`
- `occurred_at`: when the underlying event happened
- `available_at`: when the information became legally available to a decision
- `ingested_at`: when TradeMemory received it
- `payload`
- `correction_of`
- `idempotency_key`
- `payload_hash`

`available_at` is mandatory for temporal-leakage prevention. Corrections append a new event and never mutate the original event.

### 5.2 PolicyArtifactVersion

An immutable, typed version of one policy. Shared envelope fields:

- `artifact_version_id`
- `policy_id`
- `policy_type`
- `version`
- `schema_version`
- `typed_body`
- `parent_version_id`
- `content_hash`
- `generator_ref`
- `created_at`

Policy bodies are not arbitrary JSON:

- `RecallPolicy`: hard filters, source quotas, outcome/scoring parameters, counterexample and large-loss quotas, decay, top-k, and fallback behavior.
- `RiskPolicy`: immutable user ceilings, sizing recommendation, drawdown/streak rules, exposure limits, expiry, and fail-closed behavior. It cannot contain broker order commands.
- `StrategyPolicy`: signal eligibility, entry/exit/filter logic, validity conditions, regime constraints, and parameter bounds. Execution remains adapter-owned.

### 5.3 PolicyBundle

A reproducible compatible set of policy versions:

- `bundle_id`
- `recall_version_id`
- `risk_version_id`
- `strategy_version_id`
- `compatibility_constraints`
- `content_hash`

Every decision records the full `bundle_id` and `content_hash`, not merely the strategy version.

### 5.4 PolicyCandidate

Represents an artifact or bundle entering governance:

- `candidate_id`
- `proposed_artifact_version_id` or `proposed_bundle_id`
- `base_assignment_revision`
- `scope`
- `hypothesis_refs`
- `evidence_cutoff`
- `trial_family_id`
- `state`
- `created_by`
- `created_at`

The candidate references immutable artifacts and evidence; it does not duplicate either.

### 5.5 ValidationRun

Separates operational state from scientific verdict:

- `run_id`
- `candidate_id`
- `run_status`: `queued`, `running`, `completed`, `errored`, or `cancelled`
- `verdict`: `pass`, `fail`, or `inconclusive`, populated only when completed
- `validator_versions`
- `dataset_manifest_hash`
- `as_of_available_at`
- `split_and_embargo_spec`
- `metrics`
- `gate_results`
- `started_at`
- `completed_at`
- `reproducibility_hash`

An error is never interpreted as a failed financial hypothesis, and insufficient evidence is never interpreted as a pass.

### 5.6 Rollout

Represents controlled exposure of a validated challenger:

- `rollout_id`
- `candidate_id`
- `scope`
- `stage`: `planned`, `shadow`, `canary`, `full`, `paused`, `aborted`, `rolled_back`, `superseded`
- `allocation_rule`
- `stable_routing_salt`
- `started_at`
- `stopped_at`
- `champion_bundle_id`
- `challenger_bundle_id`
- `rollback_target`
- `risk_budget`
- `rollback_triggers`

Paper testing is a validation mode, not a rollout stage. Rollback creates a new control event and assignment; it never rewrites rollout history.

### 5.7 PolicyAssignment

Defines which policy bundle applies to a scope:

- `assignment_id`
- `scope`: tenant, account, agent, strategy, symbol, and optional cohort dimensions
- `policy_slot` or `bundle_id`
- `environment`
- `effective_from`
- `effective_to`
- `allocation`
- `revision`
- `caused_by_event_id`

Assignments use compare-and-swap revisions and a single writer. There is no global singleton active policy. Canary routing must be stable and mutually exclusive.

### 5.8 CohortPrior

An immutable aggregate prior:

- `prior_id`
- `policy_type`
- `cohort_definition_hash`
- `sufficient_statistics`
- `effective_sample_size`
- `valid_window`
- `privacy_method`
- `privacy_budget`
- `consent_basis`
- `producer_version`
- `content_hash`
- `expires_at`

A cohort prior may influence candidate generation or a personal posterior. It cannot directly become a live assignment or override personal evidence.

## 6. Lifecycle State Machines

### 6.1 Candidate

```text
DRAFT -> SUBMITTED -> VALIDATING
VALIDATING -> NEEDS_EVIDENCE -> VALIDATING
VALIDATING -> REJECTED
VALIDATING -> VALIDATED -> ROLLOUT_PENDING
ROLLOUT_PENDING -> PROMOTED | ABORTED | WITHDRAWN
PROMOTED -> SUPERSEDED | ROLLED_BACK
```

### 6.2 Validation

```text
QUEUED -> RUNNING -> COMPLETED
                  -> ERRORED
                  -> CANCELLED

COMPLETED carries PASS | FAIL | INCONCLUSIVE
```

### 6.3 Rollout

```text
PLANNED -> SHADOW -> CANARY -> FULL -> SUPERSEDED
                  \-> ABORTED
CANARY/FULL -> PAUSED -> previous stage | ROLLED_BACK
```

Personal `Balanced Auto` may progress automatically through staged allocations when all gates pass. Institution assignments always require approval. Automatic rollback never requires approval.

## 7. Evolution Loop

```text
Observe
-> attribute outcome
-> construct evidence-backed hypothesis
-> generate typed mutation
-> create immutable candidate
-> functional validation
-> historical replay
-> locked walk-forward / sealed holdout
-> paper validation
-> shadow
-> canary
-> full assignment or rollback
```

Reflection only produces an evidence-backed hypothesis. A separate candidate factory validates schema and bounds before creating an artifact. The LLM is a mutation generator, not the evaluator, assignment authority, or source of truth.

### 7.1 Policy-specific Evolution Plugins

There is no single generic evolution implementation.

- `StrategyEvolutionPipeline` retains the current OHLCV, pattern, and backtest concepts after leakage and statistical-gate corrections.
- `RecallEvolutionPlugin` optimizes retrieval quality, decision usefulness, calibration, counterexample coverage, and downstream outcome attribution.
- `RiskEvolutionPlugin` optimizes downside and behavioral outcomes inside immutable user ceilings.

Plugins share candidate, validation-run, gate-result, and assignment interfaces. They do not share fitness definitions or statistical null hypotheses.

## 8. Fitness and Anti-Gaming Rules

### 8.1 Objective Hierarchy

1. Hard constraints: ruin risk, maximum drawdown, daily loss, user ceilings, minimum opportunity coverage, data integrity, and execution independence.
2. Primary objectives: risk-adjusted return, downside risk, calibration, and cross-regime stability.
3. Secondary objectives: net P&L, policy-violation reduction, execution quality, and operating cost.

### 8.2 Mandatory Anti-Gaming Gates

- Leverage-normalized comparison prevents promotion through higher leverage.
- Minimum trade and opportunity coverage prevents promotion by nearly eliminating trading.
- Realistic fees, spread, slippage, latency, and rejection assumptions are recorded.
- All candidate trials are counted for multiple-testing correction.
- A sealed holdout is query-limited and never fed back into generation.
- Reused OOS data is labeled exploratory and cannot authorize rollout.
- Parameter and regime stability are required; single-window performance is insufficient.
- Losing memories and counterexamples have minimum recall quotas.
- Missing evidence produces `inconclusive`, never `pass`.

## 9. Staged Promotion Profiles

Profiles configure allocation and evidence thresholds without altering immutable risk ceilings.

- `Conservative`: smaller canary allocations and longer soak periods.
- `Balanced`: default automated profile using progressive shadow and staged live exposure; `100%` means the full user-approved policy risk budget, never unrestricted account risk.
- `Aggressive`: larger permitted canary steps but identical hard safety gates.
- `Manual`: every forward transition requires user approval.

Exact allocation steps are configuration, not protocol constants. The reference `Balanced` sequence is shadow, then 1%, 5%, 10%, 25%, 50%, and 100% of the policy's permitted risk budget. Insufficient power pauses the rollout.

## 10. Hybrid Intelligence

### 10.1 Global Safety Priors

Available offline to all users. They include bounded risk practices, data-quality protections, anti-martingale limits, stale-policy expiry, and fail-closed behavior. They are not trading signals.

### 10.2 Cohort Priors

Cohorts are defined by non-identifying dimensions such as asset class, timeframe, strategy family, regime, and risk profile. Cohort exports contain sufficient statistics and intervention effects, not raw events.

Minimum privacy controls:

- explicit opt-in and field-level consent
- schema allowlist
- minimum cohort threshold
- rare-combination suppression
- user-level differential privacy with a recorded privacy budget
- secure aggregation
- region pinning
- revocation of future contributions
- no shared cross-tenant vector database

### 10.3 Personal Evolution

Personal evidence updates the local posterior and progressively dominates cohort priors as effective sample size grows. The transition is uncertainty-based rather than a fixed trade-count switch.

Gamification rewards playbook adherence, avoided low-quality trades, review completion, risk control, evidence accumulation, and successful rollback. It never rewards trade frequency, leverage, daily P&L, or winning streaks.

## 11. Adapter Protocol

The open Adapter Protocol exposes domain-level operations:

- `get_active_policy`
- `record_decision`
- `record_order_event`
- `record_fill`
- `record_outcome`
- `heartbeat`
- `ack_policy_version`

Supported transport classes:

- Local HTTP for normal live/demo integrations.
- MCP for reasoning agents.
- File/fixture transport for Strategy Tester, air-gapped, and legacy environments.
- Native IPC as a future certified low-latency connector.

Policy artifacts are cached and deterministic. LLM inference never runs in the per-tick execution hot path. When the gateway is unavailable, the adapter uses an unexpired signed cached bundle or follows its configured fail-closed behavior.

## 12. MT5 Reference Integration

The EA is separated into ports around a shared production decision core:

- `SignalSource`
- `PolicyPort`
- `ExecutionPort`
- `Clock`
- `EventSink`

Live/demo mode uses Local HTTP or approved IPC. Strategy Tester mode uses fixtures because MT5 prohibits `WebRequest` inside the tester. Both modes consume the same policy schema and decision core.

### 12.1 Test Harness

```text
scenario + ticks + expected ledger
-> pinned MT5 terminal/build
-> Strategy Tester / custom symbol
-> production decision core
-> tester policy fixture
-> simulated MT5 order lifecycle
-> golden event ledger
-> external orchestrator assertions
```

Deterministic scenarios cover wins, stops, consecutive losses, spread anomalies, slippage, duplicate/out-of-order events, rejection, partial fill, disconnect/reconnect, stale policy, promotion, rollback, and TradeMemory restart.

## 13. Verification Strategy

The evidence ladder separates three questions:

1. **Software correctness:** unit/property tests, fault injection, deterministic fixtures, golden-ledger replay, idempotency, restart, and rollback rehearsal.
2. **Historical financial evidence:** point-in-time historical replay, realistic friction, purged walk-forward, sealed holdout, DSR/PBO correction, regime slices, and champion/challenger paired deltas.
3. **Production reality:** forward shadow and tiny-live canary for broker rejection, routing, partial fills, queue position, latency slippage, market impact, and reconciliation.

Functional hard gates require zero invariant violations. Financial gates require pre-registered metrics and uncertainty bounds. A functional pass never implies financial effectiveness.

## 14. Existing Module Integration

- `journal.py` and `db.py`: add append-only domain events and atomic compatibility projections. Existing tables and APIs remain during migration.
- `mcp_server.py::remember_trade`: move multi-layer writes into one atomic command boundary; prevent partial five-layer updates.
- `owm/recall.py`: resolve immutable `RecallPolicy V1`, initially reproducing current deterministic behavior; add explicit counterexample/large-loss quotas.
- `reflection.py`: generate evidence-backed hypotheses only.
- `evolution/engine.py`: remain strategy-specific behind a shared plugin contract; do not generalize its OHLCV/backtest internals.
- `evolution/statistical_gates.py`: retain strategy validation after aligning implementation with ADR-004.
- `ssrt/`: remain a strategy return-retirement evaluator; do not reuse its null model for recall or risk policies.
- `strategy_adjustments`: import proposed/approved/rejected rows as legacy candidate history. Applied rows become legacy observations, not fabricated rollout records.
- `mcp_tools.py`: persist evolution runs rather than relying on the current in-memory log.

## 15. Current Correctness Gaps That Block Promotion

- Current generations reuse OOS results in subsequent mutation and graveyard feedback. These results are exploratory, not untouched validation.
- ADR-004 and re-evolution DSR gate semantics are inconsistent and trial counts require audit.
- `remember_trade` can partially update memory layers.
- `INSERT OR IGNORE` can hide same-ID/different-payload conflicts.
- OWM may suppress important losing memories without an explicit counterexample quota.
- Existing active strategy storage is not sufficiently scoped for canary routing and policy composition.

No automatic rollout is enabled until these gaps are corrected and regression-tested.

## 16. Migration Principles

Migration is additive and compatibility-first:

1. Add new domain tables without removing existing APIs or tables.
2. Backfill legacy snapshots with explicit low-provenance markers.
3. Atomically append events and update compatibility projections.
4. Shadow-rebuild projections and compare against existing records.
5. Introduce a `RecallPolicy V1` that exactly reproduces current ranking before evolving it.
6. Wrap the existing evolution engine as strategy-only and repair leakage/gate semantics.
7. Import strategy-adjustment history conservatively.
8. Enable scoped assignments, shadow, canary, rollback, then risk-policy canaries.
9. Add local cohort-prior ingestion only after personal evolution is validated.
10. Add opt-in hosted aggregation after privacy and deletion tests pass.

## 17. Commercial Packaging

### Community / Local

Permissively licensed core, MCP, local database, personal memory, policy artifacts, local evaluation, import/export, Adapter Protocol, Python SDK, MT5 reference bridge, and contract tests.

### TradeMemory Cloud

Managed backups and upgrades, dashboards, alerts, hosted evaluation compute, policy registry coordination, cross-device sync, cohort benchmarks, and cohort priors.

### Team

Shared workspace, private team cohorts, RBAC, approval workflow, strategy lineage, and team policy registry.

### Enterprise

BYOC/VPC, SSO/SCIM, customer-managed keys, immutable audit export, data residency, SLA, air-gapped options, certified connectors, and integration support.

## 18. Explicit Non-goals

- Broker execution, order routing, or credential custody
- Generic autonomous trading-agent orchestration
- Guaranteed profit or alpha claims
- One generic evaluator for all policy types
- Joint optimization of recall, risk, and strategy in the first release
- Neural recall ranking in the first release
- Raw-event cloud aggregation
- Federated learning in the first release
- Cross-broker cohort learning in the first release
- PostgreSQL or multi-region assignment registry before SQLite/local semantics are validated

## 19. Acceptance Criteria for the Design

Implementation planning may begin when:

- Every active decision resolves to one reproducible policy bundle and scope.
- Candidate lifecycle, validation verdict, and rollout exposure are distinct concepts.
- No future-available evidence can enter generation or evaluation.
- Every mutation is immutable, attributable, and reversible.
- Personal automatic promotion cannot exceed immutable user ceilings.
- Institution assignment changes require approval.
- Cohort priors cannot expose or override personal data.
- MT5 replay can exercise the production decision core without waiting for market hours.
- Existing public APIs have an additive migration path.
- Deferred enterprise and research features are explicitly excluded from the first implementation plan.
