# TradeMemory Protocol — Agent Context

## Project Rules

- Default branch is `master`.
- Use Python 3.10+ and UTC timestamps.
- Preserve platform-neutral core boundaries; broker-specific behavior belongs in adapters.
- Never hardcode credentials.
- Run relevant pytest coverage before claiming implementation completion.
- Evolution results must distinguish exploratory evidence from untouched validation.

## Recent Changes

- [2026-07-14] Added and pushed the approved Policy Evolution Plane specification and design workflow task file after rebasing over four newer remote commits without force-push.
- [2026-07-14] Approved and documented the Protocol-centered Policy Evolution Plane design: typed recall/risk/strategy policies, immutable policy bundles, scoped assignments, separate validation and rollout lifecycles, automatic personal staged promotion, institutional approvals, local/VPC data plane, optional cohort cloud, and MT5 reference integration.
- [2026-04-10] Completed SSRT Phase 2 experiments; `mSPRT_t03` remained the strongest statistically valid method in the recorded experiments.

## Current Status

- Policy Evolution Plane design specification is written and awaiting Sean's document review before implementation planning.
- Existing automatic strategy promotion remains disabled pending correction of OOS feedback leakage, DSR gate semantics, multi-layer transaction atomicity, idempotency conflicts, and losing-memory recall coverage.
- Next approved workflow: review design spec, then create a detailed implementation plan and replace the design-only `tasks.txt`.
