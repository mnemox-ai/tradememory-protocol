# ADR 001: OWM Multiplicative Scoring

**Status:** Accepted  
**Date:** 2025-12-15  
**Authors:** Sean Peng  
**Supersedes:** None

## Context

TradeMemory's Outcome-Weighted Memory (OWM) system needs to rank past trade memories by relevance when an agent queries "what happened last time in similar conditions?" The recall score determines which memories surface and which stay buried.

We evaluated four approaches:

| Approach | Training Data | Interpretability | Cold Start |
|----------|--------------|------------------|------------|
| Additive scoring (weighted sum) | None | High | Works |
| **Multiplicative scoring (product)** | **None** | **High** | **Works** |
| Neural network / learned weights | Large | Low | Fails |
| Simple heuristics (recency-only) | None | Trivial | Works |

The core question: how should five scoring dimensions combine into a single retrieval score?

- **Q** (Outcome Quality) -- how profitable was this memory's trade?
- **Sim** (Context Similarity) -- how similar is the current market to the memory's context?
- **Rec** (Recency) -- how recent is the memory?
- **Conf** (Confidence) -- how confident was the agent at the time?
- **Aff** (Affective Modulation) -- does the agent's current emotional state amplify or dampen retrieval?

## Decision

Multiplicative scoring: `Final = Q x Sim x Rec x Conf x Aff`

Each factor is normalized to `[0, 1]` with a configurable floor to prevent collapse.

### Rationale

**Zero-on-any-dimension property.** A memory with terrible outcome quality (Q near 0) should not surface regardless of how recent or contextually similar it is. Additive scoring cannot enforce this -- a high recency score would rescue a catastrophic trade. Multiplicative scoring makes this a mathematical guarantee.

**No training data required.** Neural approaches need hundreds of labeled recall examples to learn weights. TradeMemory must work from trade #1. Multiplicative scoring is effective immediately with sensible defaults.

**Independent interpretability.** When a memory ranks #1, we can explain exactly why: "Q=0.85 (profitable), Sim=0.92 (very similar context), Rec=0.70 (recent), Conf=0.60 (moderate confidence), Aff=1.0 (neutral state)." Each factor has a clear semantic meaning. This matters for trading where auditability is non-negotiable.

**Cognitive science grounding.** Tulving's encoding specificity principle (1973) demonstrates that memory retrieval depends on the *match* between encoding context and retrieval context across multiple independent dimensions. The multiplicative model mirrors this: a memory must match well on ALL dimensions to surface, not just dominate on one.

**Production constraints.** Deterministic computation, no GPU, no model loading, no inference latency. The entire recall operation is a SQLite query followed by Python arithmetic.

## Implementation Details

```
score = (
    outcome_quality(trade.pnl_r)          # Sigmoid-mapped R-multiple
    * context_similarity(query, trade)     # Cosine or keyword overlap
    * recency_decay(trade.timestamp)       # Exponential decay, half-life configurable
    * confidence_factor(trade.confidence)  # Linear passthrough
    * affective_modulation(agent_state)    # EWMA-based amplification/dampening
)
```

Each factor includes a floor value (default 0.05) to prevent a single near-zero dimension from zeroing the entire score. The floor is configurable per factor via `OWMConfig`.

## Consequences

### Positive

- Works from trade #1 with no training phase
- Fully explainable -- score breakdown available in every recall result
- Deterministic and testable -- no stochastic behavior
- Fast -- pure arithmetic, no model inference
- Grounded in established memory retrieval theory

### Negative

- **Calibration sensitivity.** If one factor's distribution is compressed (e.g., all trades have Conf between 0.48 and 0.52), it contributes almost nothing to ranking discrimination. Mitigated by per-factor normalization and configurable ranges.
- **No learned adaptation.** The system cannot discover that, for example, recency matters more than similarity for a particular user's trading style. Future work: optional per-user weight exponents (`Q^wq x Sim^ws x ...`).
- **Floor parameter tuning.** The floor prevents collapse but introduces a tuning knob. Default 0.05 was chosen empirically; may need adjustment for extreme trading styles.

### Alternatives Rejected

- **Additive scoring:** Violated the zero-on-any-dimension requirement. A trade with Q=0 and Sim=0.95 would still rank highly.
- **Neural scoring:** Cold start problem is a dealbreaker for a tool that must work immediately. Also violates the "no GPU" production constraint.
- **Recency-only:** Ignores outcome quality entirely. Would surface recent losing trades as readily as recent winners.
