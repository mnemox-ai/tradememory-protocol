# TradeMemory Policy Evolution Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a broker-neutral, reproducible Policy Evolution Plane that evolves typed recall, risk, and strategy policies; validates challengers; performs scoped staged rollout and rollback; and proves the full loop through an MT5 reference harness without placing orders itself.

**Architecture:** Add an append-only domain-event and immutable policy layer beside the existing SQLite schema, then migrate existing memory and strategy services behind typed repositories and plugins. A deterministic control plane owns assignments and rollout; external adapters consume signed policy bundles and return evidence. The first release is local-first and includes cohort contracts but not hosted aggregation or enterprise deployment automation.

**Tech Stack:** Python 3.10+, Pydantic 2, sqlite3, FastMCP, FastAPI, pytest/pytest-asyncio/Hypothesis, Alembic for hosted PostgreSQL parity, PowerShell/Python MT5 orchestration, MQL5 reference adapter.

## Global Constraints

- TradeMemory never stores broker execution credentials, routes orders, or mutates positions.
- Raw trades, memories, strategy parameters, prompts, and embeddings remain local/VPC.
- Every timestamp is UTC and every temporal evaluation uses `available_at <= decision_time`.
- Every policy body is typed; arbitrary JSON cannot become an active policy.
- Every decision records a reproducible `PolicyBundle` ID and content hash.
- Validation execution state is separate from `PASS`, `FAIL`, and `INCONCLUSIVE` verdicts.
- Only `PromotionController` may write policy assignments; assignment updates use compare-and-swap revisions.
- Personal automatic rollout stays inside immutable user ceilings; institutional assignment changes require approval.
- `paper` is a validation mode; rollout exposure stages are `SHADOW`, `CANARY`, and `FULL`.
- Missing evidence is `INCONCLUSIVE`; errors and timeouts never promote candidates.
- Existing APIs and SQLite data remain readable throughout additive migration.
- No automatic rollout is enabled until OOS leakage, DSR semantics, atomic writes, idempotency conflicts, and losing-memory coverage are corrected.
- Every task follows TDD and ends with its focused tests, relevant regression tests, diff review, `AGENTS.md` status update, commit, and push.

## Delivery Phases and Gates

| Phase | Tasks | Exit gate |
|---|---|---|
| Foundation | 1–5 | Events, typed policies, bundles, repositories, and atomic compatibility writes pass rebuild/idempotency tests |
| Evolution correctness | 6–10 | Recall V1 parity, validation contracts, clean strategy holdout, recall/risk plugins, and persisted candidate history pass statistical reviews |
| Control and integration | 11–14 | Scoped assignments, deterministic rollout/rollback, open adapter contract, and local gateway pass safety/contract tests |
| MT5 and release | 15–18 | Deterministic MT5 replay, migration rehearsal, security/privacy review, full regression, and final independent reviews pass |

---

## Phase 1 — Foundation

### Task 1: Freeze Baseline and Add Architecture ADRs

**Files:**
- Create: `docs/adr/005-policy-evolution-boundaries.md`
- Create: `docs/adr/006-bitemporal-domain-events.md`
- Create: `tests/test_policy_evolution_baseline.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Existing public MCP tool list, SQLite schema, OWM recall output, evolution status enums.
- Produces: A machine-readable baseline fixture and accepted invariants used by all later tasks.

- [ ] **Step 1: Write a failing baseline test that asserts frozen public behavior**

```python
from tradememory.evolution.models import HypothesisStatus
from tradememory.mcp_server import mcp


def test_evolution_baseline_contract():
    names = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert "remember_trade" in names
    assert "recall_memories" in names
    assert "evolution_evolve_strategy" in names
    assert HypothesisStatus.GRADUATED.value == "graduated"
```

- [ ] **Step 2: Run the baseline and capture the actual FastMCP introspection API**

Run: `python -m pytest tests/test_policy_evolution_baseline.py -v`

Expected: FAIL only if the current FastMCP API differs; adjust the introspection expression to the installed API without changing production behavior, then rerun to PASS.

- [ ] **Step 3: Write ADR-005 with explicit bounded contexts and dependency direction**

Record Evidence, Memory, Evolution, Validation, Control, Cohort, and Adapter responsibilities; record that MCP/REST are outer adapters and that the current strategy engine remains strategy-specific.

- [ ] **Step 4: Write ADR-006 with bitemporal and correction semantics**

Define `occurred_at`, `available_at`, `ingested_at`, append-only correction events, payload-hash idempotency, and prohibition of future-available evidence.

- [ ] **Step 5: Run documentation and baseline checks**

Run: `python -m pytest tests/test_policy_evolution_baseline.py tests/test_mcp_tools.py tests/test_models.py -v`

Expected: all selected tests PASS.

- [ ] **Step 6: Review, update status, commit, and push**

```bash
git diff --check
git diff -- docs/adr tests/test_policy_evolution_baseline.py
git add docs/adr/005-policy-evolution-boundaries.md docs/adr/006-bitemporal-domain-events.md tests/test_policy_evolution_baseline.py AGENTS.md
git commit -m "docs: lock policy evolution boundaries"
git push origin master
```

Reviewer gate: reject if an ADR permits execution inside TradeMemory or permits validation to write assignments.

### Task 2: Add Typed Domain Models

**Files:**
- Create: `src/tradememory/policy/__init__.py`
- Create: `src/tradememory/policy/models.py`
- Create: `tests/test_policy_models.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Produces: `DomainEvent`, `RecallPolicy`, `RiskPolicy`, `StrategyPolicy`, `PolicyArtifactVersion`, `PolicyBundle`, `PolicyCandidate`, `ValidationRun`, `Rollout`, `PolicyAssignment`, and `CohortPrior`.
- Consumes: Pydantic 2 and UTC-aware `datetime`.

- [ ] **Step 1: Write failing model tests**

```python
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from tradememory.policy.models import (
    DomainEvent,
    PolicyBundle,
    RecallPolicy,
    RiskPolicy,
    ValidationRun,
)


NOW = datetime(2026, 7, 14, tzinfo=timezone.utc)


def test_event_rejects_naive_time_and_hashes_payload():
    with pytest.raises(ValidationError):
        DomainEvent.evidence(
            event_type="trade.closed",
            stream_id="trade:T-1",
            occurred_at=datetime(2026, 7, 14),
            available_at=NOW,
            payload={"pnl_r": -1.0},
            source="mt5",
            source_event_id="deal:1",
        )
    event = DomainEvent.evidence(
        event_type="trade.closed",
        stream_id="trade:T-1",
        occurred_at=NOW,
        available_at=NOW,
        payload={"pnl_r": -1.0},
        source="mt5",
        source_event_id="deal:1",
    )
    assert len(event.payload_hash) == 64


def test_risk_policy_cannot_exceed_immutable_ceiling():
    with pytest.raises(ValidationError):
        RiskPolicy(max_risk_per_trade=0.02, immutable_max_risk_per_trade=0.01)


def test_validation_error_has_no_financial_verdict():
    run = ValidationRun.errored(candidate_id="cand-1", error_code="DATASET_MISSING")
    assert run.run_status == "errored"
    assert run.verdict is None


def test_bundle_hash_changes_when_any_slot_changes():
    first = PolicyBundle.build("recall:1", "risk:1", "strategy:1")
    second = PolicyBundle.build("recall:2", "risk:1", "strategy:1")
    assert first.content_hash != second.content_hash
```

- [ ] **Step 2: Verify the tests fail because the policy package does not exist**

Run: `python -m pytest tests/test_policy_models.py -v`

Expected: FAIL with `ModuleNotFoundError: tradememory.policy`.

- [ ] **Step 3: Implement enums, canonical hashing, typed policy bodies, and validators**

```python
class ValidationVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class ValidationRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    ERRORED = "errored"
    CANCELLED = "cancelled"


class RolloutStage(str, Enum):
    PLANNED = "planned"
    SHADOW = "shadow"
    CANARY = "canary"
    FULL = "full"
    PAUSED = "paused"
    ABORTED = "aborted"
    ROLLED_BACK = "rolled_back"
    SUPERSEDED = "superseded"
```

Use `json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)` followed by SHA-256 for canonical content hashes. Add model validators that require timezone-aware UTC values and enforce policy bounds.

- [ ] **Step 4: Run focused model and property tests**

Run: `python -m pytest tests/test_policy_models.py tests/test_models.py tests/test_property_based.py -v`

Expected: all selected tests PASS.

- [ ] **Step 5: Review typed boundaries, update status, commit, and push**

```bash
git diff --check
git add src/tradememory/policy tests/test_policy_models.py AGENTS.md
git commit -m "feat: add typed policy evolution models"
git push origin master
```

Reviewer gate: reject arbitrary `dict` policy activation, naive timestamps, mutable artifact bodies, or a validation error carrying a verdict.

### Task 3: Add Additive SQLite Schema and Repositories

**Files:**
- Create: `src/tradememory/policy/repository.py`
- Create: `tests/test_policy_repository.py`
- Create: `alembic/versions/004_policy_evolution_plane.py`
- Modify: `src/tradememory/db.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Task 2 Pydantic models.
- Produces: `EventRepository.append`, `ArtifactRepository.put`, `CandidateRepository.save`, `ValidationRepository.save`, `AssignmentRepository.compare_and_swap`, `RolloutRepository.save`.

- [ ] **Step 1: Write failing repository tests for idempotency and compare-and-swap**

```python
def test_same_idempotency_key_with_different_payload_is_conflict(policy_db, event_factory):
    repo = EventRepository(policy_db)
    first = event_factory(idempotency_key="mt5:deal:7", payload={"pnl": 10})
    second = event_factory(idempotency_key="mt5:deal:7", payload={"pnl": 11})
    repo.append(first)
    with pytest.raises(IdempotencyConflict):
        repo.append(second)


def test_assignment_compare_and_swap_rejects_stale_revision(policy_db, assignment):
    repo = AssignmentRepository(policy_db)
    saved = repo.compare_and_swap(assignment, expected_revision=0)
    with pytest.raises(RevisionConflict):
        repo.compare_and_swap(saved.model_copy(update={"bundle_id": "bundle:new"}), expected_revision=0)
```

- [ ] **Step 2: Run tests and verify missing repositories fail**

Run: `python -m pytest tests/test_policy_repository.py -v`

Expected: FAIL on missing repository imports.

- [ ] **Step 3: Add SQLite tables and indexes without removing existing tables**

Add `domain_events`, `policy_artifacts`, `policy_bundles`, `policy_candidates`, `validation_runs`, `rollouts`, `policy_assignments`, and `cohort_priors`. Enforce unique `(source, source_event_id)`, unique `idempotency_key`, unique artifact content hash, and scoped assignment revision.

- [ ] **Step 4: Implement repository methods with explicit transactions and typed serialization**

`compare_and_swap` must execute `UPDATE policy_assignments SET bundle_id=?, allocation=?, effective_from=?, effective_to=?, revision=revision+1, caused_by_event_id=? WHERE assignment_id=? AND revision=?`, require `rowcount == 1`, and increment revision atomically.

- [ ] **Step 5: Add Alembic parity migration**

The hosted migration must create the same logical columns, uniqueness constraints, and indexes as SQLite initialization. Downgrade removes only the new policy-evolution tables.

- [ ] **Step 6: Run repository, migration, and existing DB tests**

Run: `python -m pytest tests/test_policy_repository.py tests/test_owm_db.py tests/test_journal.py tests/test_strategy_adjustments.py -v`

Expected: all selected tests PASS; legacy tables remain readable.

- [ ] **Step 7: Review DDL, update status, commit, and push**

```bash
git diff --check
git add src/tradememory/db.py src/tradememory/policy/repository.py tests/test_policy_repository.py alembic/versions/004_policy_evolution_plane.py AGENTS.md
git commit -m "feat: persist policy evolution state"
git push origin master
```

Reviewer gate: manually inspect unique constraints, downgrade scope, transaction boundaries, and payload-hash conflict behavior.

### Task 4: Make Trade Recording Atomic and Event-backed

**Files:**
- Create: `src/tradememory/evidence/service.py`
- Create: `src/tradememory/evidence/__init__.py`
- Create: `tests/test_evidence_service.py`
- Modify: `src/tradememory/db.py`
- Modify: `src/tradememory/journal.py`
- Modify: `src/tradememory/mcp_server.py`
- Modify: `tests/test_owm_new_tools.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: `DomainEvent`, event repository, existing trade/memory update helpers.
- Produces: `EvidenceService.remember_closed_trade(command) -> RememberTradeResult` and atomic compatibility projections.

- [ ] **Step 1: Write a failure-injection test proving no partial five-layer state**

```python
def test_remember_trade_rolls_back_every_projection_on_failure(db, closed_trade_command, monkeypatch):
    service = EvidenceService(db)
    monkeypatch.setattr(service, "_update_procedural", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        service.remember_closed_trade(closed_trade_command)
    assert db.get_trade(closed_trade_command.trade_id) is None
    assert db.get_episodic(closed_trade_command.trade_id) is None
    assert db.count_domain_events(stream_id=f"trade:{closed_trade_command.trade_id}") == 0
```

- [ ] **Step 2: Verify the test fails under current multi-transaction behavior**

Run: `python -m pytest tests/test_evidence_service.py::test_remember_trade_rolls_back_every_projection_on_failure -v`

Expected: FAIL because `EvidenceService` does not exist.

- [ ] **Step 3: Add one database transaction boundary for event append and compatibility writes**

Expose a connection-scoped transaction context from `Database`; make helpers accept the active connection rather than opening independent transactions.

- [ ] **Step 4: Route Journal and `remember_trade` through EvidenceService**

Preserve existing MCP response keys. Include the emitted event ID and payload hash as additive response fields.

- [ ] **Step 5: Test duplicates, retries, failure injection, and legacy compatibility**

Run: `python -m pytest tests/test_evidence_service.py tests/test_journal.py tests/test_owm_new_tools.py tests/test_integration.py -v`

Expected: all selected tests PASS; retries return the original result only when payload hashes match.

- [ ] **Step 6: Review atomicity, update status, commit, and push**

```bash
git diff --check
git add src/tradememory/evidence src/tradememory/db.py src/tradememory/journal.py src/tradememory/mcp_server.py tests AGENTS.md
git commit -m "feat: record trade evidence atomically"
git push origin master
```

Reviewer gate: inject failure after every projection write and reject any surviving partial state.

### Task 5: Add Deterministic Projection Rebuild and Legacy Backfill

**Files:**
- Create: `src/tradememory/evidence/projector.py`
- Create: `src/tradememory/evidence/backfill.py`
- Create: `scripts/backfill_policy_events.py`
- Create: `tests/test_evidence_projection.py`
- Modify: `src/tradememory/db.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Ordered `DomainEvent` streams and legacy trade rows.
- Produces: `ProjectionRebuilder.rebuild`, projection checkpoints, and `legacy.snapshot` events marked `provenance="legacy_backfill"`.

- [ ] **Step 1: Write failing deterministic rebuild tests**

```python
def test_rebuild_twice_produces_identical_projection_hash(db_with_events):
    rebuilder = ProjectionRebuilder(db_with_events)
    first = rebuilder.rebuild(stream_prefix="trade:")
    second = rebuilder.rebuild(stream_prefix="trade:")
    assert first.projection_hash == second.projection_hash


def test_legacy_backfill_never_invents_rollout(db_with_applied_adjustment):
    LegacyBackfill(db_with_applied_adjustment).run()
    assert db_with_applied_adjustment.count_events("legacy.application_observed") == 1
    assert db_with_applied_adjustment.count_rollouts() == 0
```

- [ ] **Step 2: Run and verify missing projector/backfill failures**

Run: `python -m pytest tests/test_evidence_projection.py -v`

Expected: FAIL on missing classes.

- [ ] **Step 3: Implement ordered replay, checkpoints, correction application, and dry-run backfill**

The script defaults to `--dry-run`, prints counts and hashes, requires `--apply` to write, and never deletes legacy rows.

- [ ] **Step 4: Run projection and legacy regression tests**

Run: `python -m pytest tests/test_evidence_projection.py tests/test_owm_migration.py tests/test_strategy_adjustments.py -v`

Expected: all selected tests PASS.

- [ ] **Step 5: Run backfill twice against a temporary copied database**

Run: `python scripts/backfill_policy_events.py --db data/test-backfill.db --apply`

Expected: first run reports inserted events; second run reports zero new events and the same projection hash.

- [ ] **Step 6: Review, update status, commit, and push**

```bash
git diff --check
git add src/tradememory/evidence scripts/backfill_policy_events.py tests/test_evidence_projection.py AGENTS.md
git commit -m "feat: rebuild evidence projections"
git push origin master
```

Reviewer gate: reject destructive backfill, non-deterministic ordering, or inferred historical rollout state.

---

## Phase 2 — Evolution Correctness

### Task 6: Introduce RecallPolicy V1 with Exact Ranking Parity

**Files:**
- Create: `src/tradememory/policy/recall.py`
- Create: `tests/test_recall_policy.py`
- Modify: `src/tradememory/owm/recall.py`
- Modify: `src/tradememory/mcp_server.py`
- Modify: `tests/test_owm_recall.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Resolved `RecallPolicy` or deterministic V1 default.
- Produces: `RecallResult` carrying `policy_version_id`, `bundle_hash`, score components, and counterexample coverage.

- [ ] **Step 1: Freeze current ranking with a golden fixture**

```python
def test_default_recall_policy_preserves_legacy_ranking(memory_fixture, query_context):
    legacy = outcome_weighted_recall(memory_fixture, query_context)
    policy = RecallPolicy.v1_legacy_defaults()
    governed = outcome_weighted_recall(memory_fixture, query_context, policy=policy)
    assert [item.memory_id for item in governed] == [item.memory_id for item in legacy]
```

- [ ] **Step 2: Write counterexample-quota tests**

```python
def test_large_loss_quota_keeps_warning_memory(memory_fixture, query_context):
    policy = RecallPolicy.v1_legacy_defaults().model_copy(update={"min_large_loss_results": 1})
    results = outcome_weighted_recall(memory_fixture, query_context, policy=policy, top_k=5)
    assert any(item.pnl_r <= -2 for item in results)
```

- [ ] **Step 3: Verify quota tests fail before implementation**

Run: `python -m pytest tests/test_recall_policy.py -v`

Expected: parity may pass after signature wiring; quota test FAILS until quota selection is implemented.

- [ ] **Step 4: Implement typed policy scoring and deterministic quota merge**

Score normal candidates and warning candidates separately, merge by stable memory ID order, deduplicate, and preserve `top_k`. Record the resolved policy and bundle hashes in recall events.

- [ ] **Step 5: Run recall, anti-resonance, and integration tests**

Run: `python -m pytest tests/test_recall_policy.py tests/test_owm_recall.py tests/test_anti_resonance.py tests/test_recall_hybrid_wireup.py -v`

Expected: all selected tests PASS.

- [ ] **Step 6: Review, update status, commit, and push**

```bash
git diff --check
git add src/tradememory/policy/recall.py src/tradememory/owm/recall.py src/tradememory/mcp_server.py tests AGENTS.md
git commit -m "feat: govern outcome-weighted recall"
git push origin master
```

Reviewer gate: compare exact legacy ordering and verify quotas cannot exceed `top_k` or leak future outcomes.

### Task 7: Build Policy-specific Validation Framework

**Files:**
- Create: `src/tradememory/validation/__init__.py`
- Create: `src/tradememory/validation/contracts.py`
- Create: `src/tradememory/validation/service.py`
- Create: `tests/test_policy_validation.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Produces: `PolicyValidator` protocol, `ValidationDatasetManifest`, `GateResult`, `ValidationService.run(candidate_id, validator) -> ValidationRun`.
- Consumes: Candidate and repository interfaces from Tasks 2–3.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_validator_exception_records_errored_without_verdict(validation_service, candidate):
    run = validation_service.run(candidate.id, RaisingValidator())
    assert run.run_status == "errored"
    assert run.verdict is None


def test_insufficient_sample_is_completed_inconclusive(validation_service, candidate):
    run = validation_service.run(candidate.id, InsufficientEvidenceValidator())
    assert run.run_status == "completed"
    assert run.verdict == "inconclusive"
```

- [ ] **Step 2: Run and verify missing validation package failures**

Run: `python -m pytest tests/test_policy_validation.py -v`

Expected: FAIL on missing imports.

- [ ] **Step 3: Implement policy-neutral orchestration only**

```python
class PolicyValidator(Protocol):
    policy_type: PolicyType

    def validate(
        self,
        candidate: PolicyCandidate,
        manifest: ValidationDatasetManifest,
    ) -> ValidationOutcome:
        """Return gate results and PASS/FAIL/INCONCLUSIVE; never activate policy."""
```

Persist queued, running, and terminal transitions. Hash validator versions, dataset manifest, temporal cutoff, split/embargo specification, metrics, and gate results.

- [ ] **Step 4: Test reproducibility and forbidden assignment writes**

Run: `python -m pytest tests/test_policy_validation.py tests/test_policy_repository.py -v`

Expected: all selected tests PASS; validation service has no assignment repository dependency.

- [ ] **Step 5: Review, update status, commit, and push**

```bash
git diff --check
git add src/tradememory/validation tests/test_policy_validation.py AGENTS.md
git commit -m "feat: add policy validation contracts"
git push origin master
```

Reviewer gate: reject shared financial fitness logic in the orchestration service.

### Task 8: Repair Strategy Evolution Leakage and Statistical Gates

**Files:**
- Create: `src/tradememory/evolution/dataset_manifest.py`
- Create: `tests/test_evolution_temporal_isolation.py`
- Modify: `src/tradememory/evolution/engine.py`
- Modify: `src/tradememory/evolution/re_evolution.py`
- Modify: `src/tradememory/evolution/statistical_gates.py`
- Modify: `src/tradememory/evolution/models.py`
- Modify: `docs/adr/004-evolution-statistical-gates.md`
- Modify: existing evolution tests
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Strategy-only `PolicyValidator` contract.
- Produces: Frozen exploration/training/validation/sealed-holdout manifests and correctly counted trial families.

- [ ] **Step 1: Write tests that prohibit OOS feedback into generation**

```python
def test_generator_never_receives_validation_or_holdout_results(spy_generator, four_way_series):
    engine = EvolutionEngine(spy_generator.llm, config=four_way_config())
    engine.evolve_sync(four_way_series)
    assert spy_generator.received_sources <= {"exploration", "training"}
```

- [ ] **Step 2: Write DSR semantics and trial-count tests**

```python
def test_dsr_gate_uses_p_value_threshold_and_counts_each_trial_once():
    result = evaluate_dsr_gate(observed_sr=1.2, returns=SAMPLE_RETURNS, trial_ids=["a", "b", "c"])
    assert result.passed == (result.p_value < 0.05)
    assert result.num_trials == 3
```

- [ ] **Step 3: Run tests and capture current leakage/gate failures**

Run: `python -m pytest tests/test_evolution_temporal_isolation.py tests/test_re_evolution.py tests/test_statistical_gates.py -v`

Expected: new isolation and DSR tests FAIL against current behavior.

- [ ] **Step 4: Split datasets and rename contaminated semantics**

Use ordered exploration/training/validation/sealed-holdout partitions. Only exploration/training results may feed mutation. Rename current cross-generation OOS survivors to `EXPLORATORY_SURVIVOR`; reserve governed `VALIDATED` for an untouched validation run.

- [ ] **Step 5: Align ADR and implementation**

Make the DSR API return statistic and p-value explicitly. Count unique `trial_family_id + candidate_id`; remove double counting. Record every rejected and errored trial.

- [ ] **Step 6: Run all evolution and replay tests**

Run: `python -m pytest tests/test_engine.py tests/test_evolution_models.py tests/test_re_evolution.py tests/test_statistical_gates.py tests/test_evolution_temporal_isolation.py tests/test_replay_engine.py -v`

Expected: all selected tests PASS; no holdout information reaches generation.

- [ ] **Step 7: Independent quantitative review checkpoint**

Run a read-only high-reasoning review focused on split chronology, multiple-testing accounting, DSR threshold semantics, and sealed-holdout access. Record findings in `docs/reviews/policy-evolution-strategy-validation.md`; resolve all correctness findings before commit.

- [ ] **Step 8: Commit and push**

```bash
git diff --check
git add src/tradememory/evolution tests docs/adr/004-evolution-statistical-gates.md docs/reviews/policy-evolution-strategy-validation.md AGENTS.md
git commit -m "fix: isolate strategy evolution validation"
git push origin master
```

Reviewer gate: reject if any evaluation slice influences subsequent candidate generation or if a repeated trial is omitted from correction.

### Task 9: Add Recall and Risk Evolution Plugins

**Files:**
- Create: `src/tradememory/evolution/contracts.py`
- Create: `src/tradememory/evolution/recall_plugin.py`
- Create: `src/tradememory/evolution/risk_plugin.py`
- Create: `tests/test_recall_evolution_plugin.py`
- Create: `tests/test_risk_evolution_plugin.py`
- Modify: `src/tradememory/owm/dqs.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Evidence-backed hypotheses, typed artifacts, policy-specific validation contract.
- Produces: `EvolutionPlugin.propose`, recall/risk candidates, and policy-specific validators. Strategy engine implements the same orchestration interface without sharing fitness code.

- [ ] **Step 1: Write plugin boundary and anti-gaming tests**

```python
def test_risk_candidate_cannot_raise_user_ceiling(risk_plugin, risk_context):
    proposal = risk_plugin.propose(risk_context.with_requested_risk(0.02))
    assert proposal.artifact.body.max_risk_per_trade <= 0.01


def test_recall_validator_fails_candidate_that_hides_large_losses(recall_validator, recall_candidate):
    outcome = recall_validator.validate(recall_candidate, RECALL_MANIFEST)
    assert outcome.verdict == "fail"
    assert "large_loss_coverage" in outcome.failed_gates


def test_risk_validator_rejects_no_trade_cheat(risk_validator, skip_all_candidate):
    outcome = risk_validator.validate(skip_all_candidate, RISK_MANIFEST)
    assert outcome.verdict == "fail"
    assert "minimum_opportunity_coverage" in outcome.failed_gates
```

- [ ] **Step 2: Run and verify missing plugin failures**

Run: `python -m pytest tests/test_recall_evolution_plugin.py tests/test_risk_evolution_plugin.py -v`

Expected: FAIL on missing plugins.

- [ ] **Step 3: Implement shared plugin SPI and typed generators**

```python
class EvolutionPlugin(Protocol):
    policy_type: PolicyType

    def propose(self, context: EvolutionContext) -> PolicyCandidate:
        raise NotImplementedError

    def validator(self) -> PolicyValidator:
        raise NotImplementedError
```

The actual implementation must use concrete methods without an ellipsis body. Recall fitness includes relevance calibration, decision usefulness, counterexample coverage, and downstream attribution. Risk fitness includes drawdown/downside, opportunity coverage, leverage-normalized returns, and immutable ceiling compliance.

- [ ] **Step 4: Add cold-start and insufficient-evidence behavior**

Global safety priors may propose bounded risk rules; cohort priors may influence generation; neither can authorize rollout without personal validation. Fewer than the validator's effective sample threshold returns `INCONCLUSIVE`.

- [ ] **Step 5: Run OWM, DQS, simulation, and plugin tests**

Run: `python -m pytest tests/test_recall_evolution_plugin.py tests/test_risk_evolution_plugin.py tests/test_dqs.py tests/test_simulation.py tests/test_owm_recall.py -v`

Expected: all selected tests PASS; skip-all and leverage-increase candidates fail.

- [ ] **Step 6: Review, update status, commit, and push**

```bash
git diff --check
git add src/tradememory/evolution src/tradememory/owm/dqs.py tests AGENTS.md
git commit -m "feat: evolve recall and risk policies"
git push origin master
```

Reviewer gate: reject shared SSRT nulls, raw-PnL-only fitness, and direct policy assignment.

### Task 10: Persist Candidates, Hypotheses, and Evolution History

**Files:**
- Create: `src/tradememory/evolution/candidate_factory.py`
- Create: `tests/test_candidate_factory.py`
- Modify: `src/tradememory/reflection.py`
- Modify: `src/tradememory/evolution/mcp_tools.py`
- Modify: `src/tradememory/mcp_server.py`
- Modify: `tests/test_evolution_mcp_tools.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Reflection hypotheses, typed plugin proposals, candidate repository.
- Produces: Schema-bounded immutable candidates and persisted evolution logs.

- [ ] **Step 1: Write tests separating hypothesis from governed candidate**

```python
def test_reflection_cannot_create_assignment(reflection_engine, repositories):
    hypothesis = reflection_engine.generate_hypothesis(EVIDENCE_WINDOW)
    assert hypothesis.kind == "evidence_backed_hypothesis"
    assert repositories.assignments.count() == 0


def test_candidate_factory_rejects_out_of_bounds_body(candidate_factory):
    with pytest.raises(PolicyBoundsError):
        candidate_factory.create(RISK_HYPOTHESIS, {"max_risk_per_trade": 0.5})
```

- [ ] **Step 2: Run tests and verify current direct/in-memory gaps**

Run: `python -m pytest tests/test_candidate_factory.py tests/test_evolution_mcp_tools.py -v`

Expected: FAIL on missing factory and persisted history assertions.

- [ ] **Step 3: Implement hypothesis output and candidate factory**

Reflection output includes evidence IDs, supporting and contradicting observations, cutoff, attribution uncertainty, and policy type. Candidate factory validates typed body, bounds, parent version, trial family, and scope.

- [ ] **Step 4: Replace `_evolution_log` with repository queries**

Keep existing MCP response shape while adding pagination, persisted run IDs, candidate IDs, and reproducibility hashes.

- [ ] **Step 5: Run reflection and evolution endpoint tests**

Run: `python -m pytest tests/test_candidate_factory.py tests/test_reflection.py tests/test_evolution_mcp_tools.py tests/test_evolution_endpoints.py -v`

Expected: all selected tests PASS and history survives process restart.

- [ ] **Step 6: Review, update status, commit, and push**

```bash
git diff --check
git add src/tradememory/reflection.py src/tradememory/evolution src/tradememory/mcp_server.py tests AGENTS.md
git commit -m "feat: govern policy candidates"
git push origin master
```

Reviewer gate: restart the process between write/read tests and reject any in-memory source of authoritative history.

---

## Phase 3 — Control and Integration

### Task 11: Implement Scoped Policy Resolution and Bundle Assignment

**Files:**
- Create: `src/tradememory/control/__init__.py`
- Create: `src/tradememory/control/resolver.py`
- Create: `src/tradememory/control/assignment_service.py`
- Create: `tests/test_policy_assignment.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Produces: `PolicyScope`, `PolicyResolver.resolve(scope, at) -> ResolvedPolicyBundle`, `AssignmentService.assign(command)`.
- Consumes: Assignment/artifact/bundle repositories.

- [ ] **Step 1: Write specificity, time, and canary-routing tests**

```python
def test_account_assignment_beats_tenant_default(resolver, assignments):
    assignments.add(tenant_default("bundle:tenant"))
    assignments.add(account_override("acct-7", "bundle:account"))
    assert resolver.resolve(scope(account="acct-7"), AT).bundle_id == "bundle:account"


def test_same_subject_routes_stably_during_canary(resolver, canary_assignment):
    first = resolver.resolve(scope(account="acct-7"), AT)
    second = resolver.resolve(scope(account="acct-7"), AT)
    assert first.bundle_id == second.bundle_id
```

- [ ] **Step 2: Run and verify missing resolver failures**

Run: `python -m pytest tests/test_policy_assignment.py -v`

Expected: FAIL on missing control package.

- [ ] **Step 3: Implement deterministic precedence and CAS assignment writes**

Precedence is account/agent/strategy/symbol-specific assignment, then tenant default, then built-in safe bundle. Reject overlapping assignments of equal precedence and effective window.

- [ ] **Step 4: Add bundle compatibility checks**

Resolver rejects missing artifacts, hash mismatch, expired bundle, schema incompatibility, and risk ceilings weaker than the user envelope.

- [ ] **Step 5: Run assignment/repository concurrency tests**

Run: `python -m pytest tests/test_policy_assignment.py tests/test_policy_repository.py -v`

Expected: all selected tests PASS, including concurrent stale-revision rejection.

- [ ] **Step 6: Review, update status, commit, and push**

```bash
git diff --check
git add src/tradememory/control tests/test_policy_assignment.py AGENTS.md
git commit -m "feat: resolve scoped policy bundles"
git push origin master
```

Reviewer gate: reject global active-version state, unstable routing, or fallback to an expired challenger.

### Task 12: Implement Promotion Controller and Automatic Rollback

**Files:**
- Create: `src/tradememory/control/promotion.py`
- Create: `src/tradememory/control/profiles.py`
- Create: `tests/test_promotion_controller.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Completed validation runs, rollout repository, assignment service, sequential evidence, user profile and immutable risk envelope.
- Produces: Deterministic rollout transitions and assignment control events.

- [ ] **Step 1: Write transition-table tests**

```python
@pytest.mark.parametrize("verdict,expected", [
    ("pass", "shadow"),
    ("fail", "aborted"),
    ("inconclusive", "planned"),
])
def test_validation_verdict_controls_first_transition(controller, rollout, verdict, expected):
    assert controller.on_validation(rollout, completed_run(verdict)).stage == expected


def test_hard_limit_breach_rolls_back_without_approval(controller, canary_rollout):
    result = controller.on_evidence(canary_rollout, max_drawdown_breach())
    assert result.stage == "rolled_back"
    assert result.assignment.bundle_id == canary_rollout.champion_bundle_id
```

- [ ] **Step 2: Run and verify missing controller failures**

Run: `python -m pytest tests/test_promotion_controller.py -v`

Expected: FAIL on missing promotion module.

- [ ] **Step 3: Implement profiles and deterministic state machine**

Profiles define allocation steps and soak/evidence requirements. `Balanced` uses shadow, 1%, 5%, 10%, 25%, 50%, and 100% of user-approved policy risk budget. The controller never alters immutable ceilings or evaluator configuration.

- [ ] **Step 4: Add institutional approval and personal opt-out behavior**

Institution transitions stop at `approval_required`; personal `Manual` does the same. Opt-out creates a control event, restores champion assignment, and prevents new automatic transitions.

- [ ] **Step 5: Test crash/retry, duplicate evidence, pause, and rollback rehearsal**

Run: `python -m pytest tests/test_promotion_controller.py tests/test_policy_assignment.py tests/test_policy_repository.py -v`

Expected: all selected tests PASS and retries do not duplicate assignment changes.

- [ ] **Step 6: Independent safety review checkpoint**

Review every transition and invariant against the design spec. Record the table, hard triggers, rollback target validation, and fail-closed cases in `docs/reviews/policy-rollout-safety.md`.

- [ ] **Step 7: Commit and push**

```bash
git diff --check
git add src/tradememory/control tests docs/reviews/policy-rollout-safety.md AGENTS.md
git commit -m "feat: control staged policy rollout"
git push origin master
```

Reviewer gate: reject any path from error/inconclusive to increased exposure, any approval bypass, or rollback that mutates historical rows.

### Task 13: Publish the Open Adapter Protocol and Python SDK

**Files:**
- Create: `src/tradememory/adapters/__init__.py`
- Create: `src/tradememory/adapters/protocol.py`
- Create: `src/tradememory/adapters/python_sdk.py`
- Create: `docs/ADAPTER_PROTOCOL.md`
- Create: `tests/test_adapter_protocol.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Produces: typed requests/responses for `get_active_policy`, `record_decision`, `record_order_event`, `record_fill`, `record_outcome`, `heartbeat`, and `ack_policy_version`.
- Consumes: evidence service and policy resolver; contains no execution method.

- [ ] **Step 1: Write contract tests and explicit no-execution assertion**

```python
def test_adapter_contract_has_no_order_submission_method():
    methods = set(AdapterClient.__abstractmethods__)
    assert methods == {
        "get_active_policy",
        "record_decision",
        "record_order_event",
        "record_fill",
        "record_outcome",
        "heartbeat",
        "ack_policy_version",
    }
```

- [ ] **Step 2: Run and verify missing adapter failures**

Run: `python -m pytest tests/test_adapter_protocol.py -v`

Expected: FAIL on missing adapter package.

- [ ] **Step 3: Implement typed commands, responses, signatures, expiry, and idempotency**

`get_active_policy` returns bundle ID, artifact bodies, content hashes, signature metadata, expiry, assignment revision, and fail-closed instructions. Event commands require source event ID and idempotency key.

- [ ] **Step 4: Implement an in-process Python client and contract fixture suite**

The in-process client uses the same service layer as HTTP/MCP and is the reference for connector certification.

- [ ] **Step 5: Run SDK, MCP, event, and model tests**

Run: `python -m pytest tests/test_adapter_protocol.py tests/test_evidence_service.py tests/test_policy_assignment.py tests/test_mcp_tools.py -v`

Expected: all selected tests PASS.

- [ ] **Step 6: Review public API, update status, commit, and push**

```bash
git diff --check
git add src/tradememory/adapters docs/ADAPTER_PROTOCOL.md tests/test_adapter_protocol.py AGENTS.md
git commit -m "feat: publish trading adapter protocol"
git push origin master
```

Reviewer gate: reject credential fields, order submission, untyped policy bodies, or undocumented retry behavior.

### Task 14: Add Local HTTP Gateway and MCP/REST Evolution APIs

**Files:**
- Create: `src/tradememory/gateway.py`
- Create: `tests/test_local_gateway.py`
- Modify: `src/tradememory/server.py`
- Modify: `src/tradememory/mcp_server.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Adapter SDK service, resolver, evidence service, candidate/validation/rollout repositories.
- Produces: localhost HTTP endpoints and MCP tools for policy query, evidence ingestion, status, opt-out, and manual approval.

- [ ] **Step 1: Write authentication, localhost, and response-contract tests**

```python
def test_gateway_rejects_non_loopback_bind_without_auth():
    with pytest.raises(UnsafeBindError):
        GatewayConfig(host="0.0.0.0", bearer_token=None)


def test_policy_endpoint_never_returns_broker_credentials(client):
    response = client.get("/v1/policies/active", params=VALID_SCOPE)
    assert response.status_code == 200
    assert "credentials" not in response.text.lower()
```

- [ ] **Step 2: Run and verify missing gateway failures**

Run: `python -m pytest tests/test_local_gateway.py -v`

Expected: FAIL on missing gateway.

- [ ] **Step 3: Implement localhost-safe endpoints and additive MCP tools**

Expose policy bundle query, seven adapter events, rollout status, opt-out, approval, and rollback request. Reuse existing bearer-auth scaffold; require authentication for non-loopback binding.

- [ ] **Step 4: Add timeout and cached-policy contract behavior**

Gateway responses include expiry and fail-closed instruction. The adapter, not the gateway, decides whether an unexpired cached bundle is usable.

- [ ] **Step 5: Run server, auth, audit, MCP, and gateway tests**

Run: `python -m pytest tests/test_local_gateway.py tests/test_server.py tests/test_auth.py tests/test_audit_chain.py tests/test_mcp_tools.py -v`

Expected: all selected tests PASS.

- [ ] **Step 6: Security review, update status, commit, and push**

```bash
git diff --check
git add src/tradememory/gateway.py src/tradememory/server.py src/tradememory/mcp_server.py tests AGENTS.md
git commit -m "feat: expose local policy gateway"
git push origin master
```

Reviewer gate: inspect bind defaults, authentication, payload limits, log redaction, and absence of execution endpoints.

---

## Phase 4 — MT5 and Release

### Task 15: Build MT5 Production Decision Core and Reference Bridge

**Files:**
- Create: `adapters/mt5/TradeMemoryBridge.mqh`
- Create: `adapters/mt5/TradeMemoryReferenceEA.mq5`
- Create: `adapters/mt5/schemas/policy-bundle-v1.json`
- Create: `docs/MT5_POLICY_ADAPTER.md`
- Create: `tests/test_mt5_adapter_contract.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Adapter Protocol policy bundle and event schemas.
- Produces: MQL5 `PolicyPort`, `Clock`, `EventSink`, and reference decision-core integration. Existing EA strategy logic remains external.

- [ ] **Step 1: Write schema and source-level contract tests**

```python
def test_mt5_bridge_implements_all_adapter_events():
    source = Path("adapters/mt5/TradeMemoryBridge.mqh").read_text(encoding="utf-8")
    for name in ["GetActivePolicy", "RecordDecision", "RecordOrderEvent", "RecordFill", "RecordOutcome", "Heartbeat", "AckPolicyVersion"]:
        assert name in source


def test_mt5_bridge_contains_no_trade_submission():
    source = Path("adapters/mt5/TradeMemoryBridge.mqh").read_text(encoding="utf-8")
    assert "OrderSend(" not in source
```

- [ ] **Step 2: Run and verify missing bridge failures**

Run: `python -m pytest tests/test_mt5_adapter_contract.py -v`

Expected: FAIL because adapter files do not exist.

- [ ] **Step 3: Implement live/demo Local HTTP transport and signed cache**

Use `OnTimer` to fetch policy and flush evidence; `OnTick` reads only the verified unexpired cache. Require the user to allowlist the localhost gateway URL. Fail closed when policy is expired and the configured policy requires it.

- [ ] **Step 4: Implement event JSONL spool and retry semantics**

Every event has source event ID, idempotency key, policy bundle hash, UTC time, and monotonic local sequence. Disk spool survives terminal restart and deletes only acknowledged events.

- [ ] **Step 5: Compile the reference EA and run Python contract tests**

Run: `python -m pytest tests/test_mt5_adapter_contract.py tests/test_adapter_protocol.py -v`

Run: MetaEditor command-line compile for `adapters/mt5/TradeMemoryReferenceEA.mq5`.

Expected: Python tests PASS and compiler reports zero errors.

- [ ] **Step 6: Review, update status, commit, and push**

```bash
git diff --check
git add adapters/mt5 docs/MT5_POLICY_ADAPTER.md tests/test_mt5_adapter_contract.py AGENTS.md
git commit -m "feat: add MT5 policy adapter"
git push origin master
```

Reviewer gate: manually verify no `OrderSend`, no credential persistence, no LLM call in `OnTick`, and crash-safe spool behavior.

### Task 16: Build Deterministic MT5 Strategy Tester Harness

**Files:**
- Create: `adapters/mt5/TradeMemoryTesterPort.mqh`
- Create: `scripts/mt5_policy_replay.py`
- Create: `tests/fixtures/mt5/scenarios/consecutive-loss-guardrail.json`
- Create: `tests/fixtures/mt5/scenarios/policy-rollback.json`
- Create: `tests/fixtures/mt5/expected/consecutive-loss-guardrail.events.jsonl`
- Create: `tests/fixtures/mt5/expected/policy-rollback.events.jsonl`
- Create: `tests/test_mt5_policy_replay.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Deterministic scenario, custom ticks, signed policy fixtures, pinned terminal configuration.
- Produces: Golden event ledger and `ReplayResult` with decision/order/outcome/promotion assertions.

- [ ] **Step 1: Write failing golden-ledger replay tests**

```python
def test_consecutive_loss_scenario_reduces_risk(run_mt5_replay):
    result = run_mt5_replay("consecutive-loss-guardrail")
    assert result.events_of_type("risk.adjusted")[-1]["size_multiplier"] == 0.5
    assert result.no_duplicate_idempotency_keys()


def test_policy_rollback_restores_champion_bundle(run_mt5_replay):
    result = run_mt5_replay("policy-rollback")
    assert result.last("policy.assigned")["bundle_id"] == result.metadata["champion_bundle_id"]
```

- [ ] **Step 2: Run and verify missing harness failures**

Run: `python -m pytest tests/test_mt5_policy_replay.py -v`

Expected: FAIL because the replay orchestrator does not exist.

- [ ] **Step 3: Implement tester fixture transport**

Because MT5 Strategy Tester prohibits `WebRequest`, read policy responses from tester files and write events to the agent sandbox. Use the same schemas and decision core as live mode.

- [ ] **Step 4: Implement pinned terminal orchestration and report watchdog**

Generate tester INI, launch portable `terminal64.exe /config:<ini>`, enforce timeout, parse terminal/tester logs, require an explicit completion sentinel, and fail on compile/tester error even if process exit is zero.

- [ ] **Step 5: Add deterministic scenarios and golden ledgers**

Cover winning trade, stop, consecutive losses, stale policy, duplicate event, reject, partial fill, disconnect/restart, promotion, and rollback. Scenario timestamps are fixed UTC and policy fixtures carry fixed hashes.

- [ ] **Step 6: Run offline and MT5-enabled suites**

Run: `python -m pytest tests/test_mt5_policy_replay.py -v -m "not integration"`

Run on MT5 host: `python -m pytest tests/test_mt5_policy_replay.py -v -m integration`

Expected: offline parser tests PASS; MT5 integration reproduces the committed golden ledgers byte-for-byte except explicitly normalized terminal-generated IDs.

- [ ] **Step 7: Review, update status, commit, and push**

```bash
git diff --check
git add adapters/mt5 scripts/mt5_policy_replay.py tests/fixtures/mt5 tests/test_mt5_policy_replay.py AGENTS.md
git commit -m "test: replay MT5 policy evolution"
git push origin master
```

Reviewer gate: reject a separate tester decision algorithm, unpinned terminal build, missing watchdog, or golden output that contains ignored financial decisions.

### Task 17: Add Cohort Contract and Privacy Boundary Without Hosted Aggregation

**Files:**
- Create: `src/tradememory/cohort/__init__.py`
- Create: `src/tradememory/cohort/models.py`
- Create: `src/tradememory/cohort/exporter.py`
- Create: `tests/test_cohort_privacy.py`
- Create: `docs/COHORT_PRIVACY.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: allowlisted local aggregate projections.
- Produces: `CohortContribution`, `CohortPrior`, local export preview, and consent receipt. No network client is implemented in this task.

- [ ] **Step 1: Write deny-by-default privacy tests**

```python
FORBIDDEN = {"account_id", "order_id", "timestamp", "prompt", "reasoning", "embedding", "strategy_parameters", "raw_pnl_path"}


def test_export_contains_only_allowlisted_aggregates(cohort_exporter, personal_db):
    payload = cohort_exporter.preview(personal_db, consent=OPTED_IN)
    assert FORBIDDEN.isdisjoint(payload.model_dump().keys())


def test_no_consent_produces_no_contribution(cohort_exporter, personal_db):
    assert cohort_exporter.preview(personal_db, consent=OPTED_OUT) is None
```

- [ ] **Step 2: Run and verify missing cohort failures**

Run: `python -m pytest tests/test_cohort_privacy.py -v`

Expected: FAIL on missing cohort package.

- [ ] **Step 3: Implement allowlist-only aggregate models and local preview**

Require cohort-definition hash, sufficient statistics, effective sample size, valid window, privacy-method metadata, consent receipt, producer version, content hash, and expiry. Suppress cohorts below configured minimum size.

- [ ] **Step 4: Add payload scanning and deletion/opt-out semantics**

Opt-out stops future contribution generation. Imported priors remain immutable evidence with expiry; they cannot be assigned directly.

- [ ] **Step 5: Run privacy, auth, audit, and model tests**

Run: `python -m pytest tests/test_cohort_privacy.py tests/test_auth.py tests/test_audit_chain.py tests/test_policy_models.py -v`

Expected: all selected tests PASS and forbidden fields never serialize.

- [ ] **Step 6: Independent privacy review checkpoint**

Review schema allowlist, consent, cohort suppression, personal-data inference risk, and absence of network/raw export. Record findings in `docs/reviews/cohort-contract-privacy.md`.

- [ ] **Step 7: Commit and push**

```bash
git diff --check
git add src/tradememory/cohort tests/test_cohort_privacy.py docs/COHORT_PRIVACY.md docs/reviews/cohort-contract-privacy.md AGENTS.md
git commit -m "feat: define private cohort contracts"
git push origin master
```

Reviewer gate: reject raw timestamps, rare strategy identifiers, pseudonymous account IDs, embeddings, or automatic opt-in.

### Task 18: Migration Rehearsal, Full Verification, Reviews, and Release Gate

**Files:**
- Create: `scripts/verify_policy_migration.py`
- Create: `docs/reviews/policy-evolution-final-review.md`
- Create: `docs/reviews/policy-evolution-security-review.md`
- Create: `docs/reviews/policy-evolution-test-report.md`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/API.md`
- Modify: `CHANGELOG.md`
- Modify: `AGENTS.md`
- Modify: `tasks.txt`

**Interfaces:**
- Consumes: All prior tasks.
- Produces: Reproducible release evidence and a go/no-go verdict. No deployment or version bump occurs unless separately authorized.

- [ ] **Step 1: Add migration verification script**

The script copies a legacy SQLite DB, records row counts and audit-chain head, applies schema/backfill, rebuilds projections, runs integrity checks, restarts services, reruns the process, and emits JSON with `legacy_rows_preserved`, `idempotent`, `projection_hash`, `audit_chain_valid`, and `errors`.

- [ ] **Step 2: Write script tests and run migration twice**

Run: `python -m pytest tests/test_owm_migration.py tests/test_policy_repository.py tests/test_evidence_projection.py -v`

Run: `python scripts/verify_policy_migration.py --source data/tradememory.db --work-dir reports/policy-migration`

Expected: source DB remains unchanged; both passes preserve row counts, produce identical projection hash, and report zero errors.

- [ ] **Step 3: Run formatting, type, and complete automated tests**

```bash
python -m ruff check src tests scripts
python -m mypy src/tradememory
python -m pytest tests -v --cov=tradememory --cov-report=term-missing --cov-report=xml
```

Expected: ruff and mypy exit 0; all tests pass except explicitly documented external-key integration skips; new policy/evidence/control packages maintain at least 90% line coverage and 100% transition-table branch coverage.

- [ ] **Step 4: Run deterministic replay and restart tests**

Run: `python -m pytest tests/test_mt5_policy_replay.py tests/test_evidence_service.py tests/test_promotion_controller.py -v`

Expected: golden ledgers match; no duplicate assignment or event appears after restart/retry.

- [ ] **Step 5: Run pre-landing code review**

Invoke `/review` against the complete diff. Resolve every P0/P1 and all correctness, SQL safety, temporal leakage, transaction, and trust-boundary findings. Record resolved findings and commit hashes in `docs/reviews/policy-evolution-final-review.md`.

- [ ] **Step 6: Run adversarial architecture challenge**

Invoke `/codex challenge` with focus on temporal leakage, candidate/assignment authority, canary routing, rollback races, idempotency, payload integrity, and no-execution boundary. Resolve substantive findings and record accepted/rejected rationale.

- [ ] **Step 7: Run security review**

Invoke `/cso` in comprehensive mode against local gateway, adapter schemas, cohort export, audit chain, bearer auth, SQLite permissions, secrets, dependency supply chain, and prompt/memory trust boundaries. Record the final table in `docs/reviews/policy-evolution-security-review.md`.

- [ ] **Step 8: Run launch gate only before public/beta deployment**

Invoke `/launch-gate` and require:

- exception paths do not silently swallow errors
- authn/authz and assignment authority are server-side
- raw/private data remains local and cohort export is explicit opt-in
- event/assignment writes are atomic, idempotent, and race-safe
- policy resolution, rollout, rollback, and adapter failures are observable

Any deferred item is written to `AGENTS.md` with owner and blocking condition. Any red item blocks release.

- [ ] **Step 9: Update docs and produce test report**

Document architecture, API schemas, migration, opt-out/manual modes, MT5 setup, tester limitation, cached-policy behavior, failure modes, and non-profitability claims. `docs/reviews/policy-evolution-test-report.md` contains commands, environment, counts, coverage, skipped tests, replay hashes, and unresolved limitations.

- [ ] **Step 10: Final diff and clean-worktree verification**

```bash
git diff --check
git status --short
git diff --stat origin/master...HEAD
```

Expected: no whitespace errors, only intentional files changed, no generated secrets/databases/reports containing private trades staged.

- [ ] **Step 11: Commit documentation/status and push**

```bash
git add README.md docs CHANGELOG.md AGENTS.md tasks.txt scripts/verify_policy_migration.py
git commit -m "docs: finalize policy evolution release evidence"
git push origin master
```

Reviewer gate: final verdict is `GO` only if automated checks pass, MT5 replay is deterministic, migration is reversible/idempotent, security has no unresolved red finding, and launch gate has no red finding.

## Execution Rules

1. Execute tasks in numeric order; later tasks consume exact interfaces from earlier tasks.
2. Use one implementation agent per task and two reviews per task: spec compliance first, code quality second.
3. Do not combine commits across task boundaries.
4. After every commit/push, update `AGENTS.md` Recent Changes and Current Status in that same commit or an immediate follow-up commit.
5. Stop on a failed gate; do not mark a task complete because most tests pass.
6. Do not activate auto rollout in production during implementation. The plan builds and validates the capability; public activation requires Task 18 launch authorization.
7. Preserve user changes and rebase without force-push if remote `master` advances.

## Deferred Follow-up Plans

The following require separate approved specs and implementation plans after this plan passes:

- Hosted cohort aggregation with differential privacy and secure aggregation
- TradeMemory Cloud billing, sync, dashboards, and managed evaluation compute
- Enterprise BYOC/VPC packaging, SSO/SCIM/KMS, data residency, and SLA
- Certified low-latency IPC connectors and additional broker adapters
- Cross-policy joint optimization and neural recall ranking
- Public rollout pricing, onboarding experiments, and gamification UI
