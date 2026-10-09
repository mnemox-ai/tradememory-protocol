# TradeMemory Protocol — Agent Context

## Project Rules

- Default branch is `master`.
- Use Python 3.10+ and UTC timestamps.
- Preserve platform-neutral core boundaries; broker-specific behavior belongs in adapters.
- Never hardcode credentials.
- Run relevant pytest coverage before claiming implementation completion.
- Evolution results must distinguish exploratory evidence from untouched validation.

## Recent Changes

- [2026-10-10] Implemented historical `as_of` recall and closed-outcome availability before ranking/limit; UTC replay callbacks, independent checkpoints and decision-cap settlement. Reused native Hyperliquid importer and hybrid recall for a four-arm prompt pilot: 120 prompts dry-run, 200 closed trips, no model responses. Final offline regression: 1,612 passed / 6 skipped; existing live API test failed 401. See `research/memory_decision_probe/RESULTS.md`.
- [2026-10-10] Added a local FinRL reuse probe in `research/finrl_probe/`: pinned unchanged upstream sources, 15 fixed PPO models, 48 trajectories and 22,536 independently audited accounting steps. Quarantined portfolio/generic-X failures; StockTradingEnv adapter passed 18 controls. Existing recall/MCP tests: 80 passed. No production strategy or recall changes.
- [2026-07-14] Added the formal 18-task Policy Evolution Plane implementation plan, including TDD, migration, statistical isolation, staged rollout, MT5 replay, privacy, independent reviews, full regression, and launch gates.
- [2026-07-14] Added and pushed the approved Policy Evolution Plane specification and design workflow task file after rebasing over four newer remote commits without force-push.
- [2026-07-14] Approved and documented the Protocol-centered Policy Evolution Plane design: typed recall/risk/strategy policies, immutable policy bundles, scoped assignments, separate validation and rollout lifecycles, automatic personal staged promotion, institutional approvals, local/VPC data plane, optional cohort cloud, and MT5 reference integration.
- [2026-04-10] Completed SSRT Phase 2 experiments; `mSPRT_t03` remained the strongest statistically valid method in the recorded experiments.

## Current Status

- Historical recall correctness is verified with future-data / timezone / mutation controls; this is frozen-snapshot eligibility, not bitemporal metadata reconstruction. Old replay callbacks must accept `as_of`; legacy naive broker-time DB snapshots need explicit normalization. pending: actual model pilot is blocked by Claude OAuth expiry and external-payload approval; authentication-only check sent zero trade rows. Frozen six cases have zero warn positives, so only numeric/citation calibration is possible. next: resolve login / model destination, run fixed arms, then design untouched balanced validation before making any efficacy claim. See `research/memory_decision_probe/README.md`.
- FinRL probe is exploratory reuse evidence, not alpha or memory efficacy. GLD 2025–2026 Q3 PPO median return was -5.62% across all five seeds; 3,629/13,935 historical recall top-5 outputs changed with wall clock versus replay clock. Raw snapshots/models/trajectories remain locally in the probe's ignored `.cache`; result JSON and hashes are versioned. pending: any memory efficacy study must use existing replay, a fixed actual decision-maker and equal-information/negative controls; none was run in this probe. See `research/finrl_probe/RESULTS.md`.
- Policy Evolution Plane design is approved; the formal implementation plan and executable `tasks.txt` are ready for execution selection.
- Existing automatic strategy promotion remains disabled pending correction of OOS feedback leakage, DSR gate semantics, multi-layer transaction atomicity, idempotency conflicts, and losing-memory recall coverage.
- The historical Policy Evolution Plane Tasks 1–18 are not the active execution queue; the current authorized work is the bounded historical recall / memory decision probe above. Resume that broader plan only when selected.
