# anti-resonance — Package Design Draft

**Package name**: `anti-resonance`
**PyPI**: `pip install anti-resonance`
**Repository**: `mnemox-ai/anti-resonance`
**Dependencies**: None (pure Python, stdlib only)

---

## What It Does

When AI agents retrieve memories to inform decisions, they tend to over-retrieve positive outcomes (confirmation bias). `anti-resonance` forces a minimum ratio of negative memories into the recall set.

```python
from anti_resonance import ensure_negative_balance

# Your recall results (ranked by relevance/score)
results = my_recall_function(query, top_k=10)

# Force at least 20% negative outcomes in results
balanced = ensure_negative_balance(
    results=results,
    all_candidates=full_candidate_pool,
    min_negative_ratio=0.2,
    outcome_key="pnl",        # field name for outcome value
)
```

## Algorithm

1. Count negative outcomes in top-K results
2. If ratio >= threshold: return unchanged
3. Otherwise: replace lowest-scoring positive items with highest-scoring negative items from the candidate pool
4. Re-sort by score

## Core API

```python
def ensure_negative_balance(
    results: list[dict],
    all_candidates: list[dict],
    min_negative_ratio: float = 0.2,
    outcome_key: str = "pnl",
    score_key: str = "score",
    id_key: str = "id",
) -> list[dict]:
    """Enforce minimum negative outcome ratio in recall results.

    Args:
        results: Top-K ranked results from any recall system.
        all_candidates: Full candidate pool (superset of results).
        min_negative_ratio: Minimum fraction of negative outcomes (default 0.2).
        outcome_key: Dict key for the outcome value (negative = bad outcome).
        score_key: Dict key for the relevance/quality score.
        id_key: Dict key for unique identifier.

    Returns:
        Adjusted results list with negative ratio >= min_negative_ratio.
    """
```

## Why This Matters

| Without anti-resonance | With anti-resonance |
|------------------------|---------------------|
| Agent recalls 10 winning trades | Agent recalls 8 wins + 2 losses |
| Develops false confidence | Maintains calibrated risk awareness |
| Ignores failure modes | Learns from both success and failure |
| Echo chamber effect | Balanced decision context |

## Package Structure

```
anti_resonance/
    __init__.py          # ensure_negative_balance + helpers
    _balance.py          # Core algorithm
    _types.py            # Protocol for scored items
py.typed                 # PEP 561
tests/
    test_balance.py      # Edge cases, empty, all-positive, all-negative
pyproject.toml
README.md
LICENSE                  # Apache-2.0
```

## README Outline

1. One-line: "Stop your AI from only remembering the good times"
2. Install: `pip install anti-resonance`
3. Quick example (5 lines)
4. Why: confirmation bias in LLM memory retrieval
5. Algorithm explanation (the 4 steps above)
6. API reference
7. Used in: TradeMemory Protocol (link)
8. Paper reference: FinMem echo chamber problem

## Target Audience

- AI agent developers building memory-augmented systems
- LLM application developers using RAG with outcome data
- Trading system developers concerned about survivorship bias

## Size Target

- < 100 lines of core logic
- 0 dependencies
- Python 3.8+
