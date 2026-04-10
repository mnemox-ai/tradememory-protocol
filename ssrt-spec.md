# SSRT Implementation Spec — Phase 1

> Auto-claude task file references this spec. Read the relevant section before implementing each task.

## Background

Sequential Strategy Retirement Testing (SSRT) — a statistically rigorous framework for deciding when to retire a trading strategy. Uses mSPRT (Mixture Sequential Probability Ratio Test) with regime-aware null hypotheses.

**Paper**: "When to Pull the Plug: Sequential Hypothesis Testing for Trading Strategy Retirement under Regime Uncertainty"

**Key novelty**: The null hypothesis is not fixed "alpha > 0" but regime-dependent. A strategy's expected performance depends on market regime (trending_up, trending_down, ranging, volatile). When regime shifts, the null shifts too.

## Existing Code to Reuse

- `src/tradememory/owm/drift.py` → `cusum_drift_detect()` — use as baseline comparison
- `src/tradememory/owm/changepoint.py` → `BayesianChangepoint` — reference for state persistence pattern
- `src/tradememory/evolution/statistical_gates.py` → `benjamini_hochberg()` — reuse for multi-strategy (v2)
- `src/tradememory/evolution/backtester.py` → `FitnessMetrics`, `_compute_max_drawdown()` — reuse
- `src/tradememory/data/context_builder.py` → regime detection — reuse
- `src/tradememory/owm/context.py` → `ContextVector` regime field — reuse

## Conventions (match existing codebase)

- Python 3.10+, type hints everywhere
- Docstrings: Google style (see owm/ modules)
- No external dependencies beyond stdlib + numpy (no scipy for Phase 1)
- Pure functions where possible, classes for stateful engines
- Tests: pytest, use tmp_path for any file I/O
- Error handling: raise specific exceptions, never return False
- All timestamps UTC ISO-8601

---

## Task 1: Module Skeleton + Data Models

### Files to create

**`src/tradememory/ssrt/__init__.py`**:
```python
"""SSRT — Sequential Strategy Retirement Testing.

Provides statistically rigorous strategy retirement decisions using
mSPRT (Mixture Sequential Probability Ratio Test) with regime-aware
null hypotheses.
"""
from tradememory.ssrt.models import TradeResult, SSRTVerdict, RegimeBaseline, RetirementReport
from tradememory.ssrt.core import MixtureSPRT
from tradememory.ssrt.regime import RegimeAwareNull
```

**`src/tradememory/ssrt/models.py`**:

```python
@dataclass
class TradeResult:
    """Single trade outcome for sequential testing."""
    pnl: float              # raw P&L in account currency
    pnl_r: float            # R-multiple (risk-adjusted)
    regime: str             # "trending_up" | "trending_down" | "ranging" | "volatile"
    timestamp: str          # ISO-8601 UTC
    strategy: str           # strategy name
    symbol: str             # e.g. "XAUUSD"

@dataclass
class SSRTVerdict:
    """Result of a single sequential test update."""
    decision: str           # "CONTINUE" | "RETIRE" | "INCONCLUSIVE"
    p_value: float          # always-valid p-value (1/max(1, Lambda_n))
    lambda_n: float         # mixture likelihood ratio
    trades_analyzed: int    # cumulative trade count
    regime: str             # current regime used for null
    null_mean: float        # regime-specific null mean (mu_0)

@dataclass
class RegimeBaseline:
    """Per-regime performance baseline for null hypothesis."""
    regime: str
    mean_pnl_r: float       # historical mean R-multiple in this regime
    std_pnl_r: float        # historical std of R-multiples
    trade_count: int        # how many trades formed this baseline
    last_updated: str       # ISO-8601

@dataclass
class RetirementReport:
    """Full report for strategy retirement analysis."""
    strategy: str
    symbol: str
    verdict: SSRTVerdict
    regime_baselines: dict  # regime -> RegimeBaseline
    baseline_comparison: dict  # comparison with MaxDD, rolling Sharpe
    history: list           # list of SSRTVerdict snapshots over time
```

---

## Task 2: mSPRT Engine

### File: `src/tradememory/ssrt/core.py`

**Algorithm**: Mixture Sequential Probability Ratio Test (Johari et al. 2017)

The key idea: instead of testing against a point alternative (H1: mu = mu_1), we test against a MIXTURE of alternatives. This gives always-valid p-values — you can "peek" after every trade without inflating Type I error.

**Math**:
- Observations: x_1, x_2, ..., x_n (trade R-multiples, shifted by null mean)
- Shifted observations: z_i = x_i - mu_0 (where mu_0 is the regime-specific null)
- Under H0: z_i ~ N(0, sigma^2) (strategy performs at baseline)
- Under H1: z_i ~ N(theta, sigma^2) for some theta < 0 (strategy decayed)
- Mixing distribution: theta ~ N(0, tau^2)

**Mixture likelihood ratio** (for normal observations with known variance):
```
Lambda_n = sqrt(sigma^2 / (sigma^2 + n*tau^2)) * exp(n^2 * tau^2 * z_bar^2 / (2 * sigma^2 * (sigma^2 + n*tau^2)))
```
where z_bar = mean(z_1, ..., z_n)

**Always-valid p-value**: p_n = 1 / max(1, Lambda_n)

**Decision rules**:
- p_n < alpha (default 0.05) → RETIRE
- Lambda_n < beta/(1-alpha) → CONTINUE (strong evidence strategy is fine)
- Otherwise → INCONCLUSIVE

**Class interface**:
```python
class MixtureSPRT:
    def __init__(self, alpha=0.05, tau=1.0, sigma=1.5, null_mean=0.0):
        """
        Args:
            alpha: significance level (Type I error rate)
            tau: mixing distribution scale (controls sensitivity)
            sigma: assumed observation std (estimated from history)
            null_mean: baseline mean under H0 (regime-dependent)
        """

    def update(self, observation: float) -> SSRTVerdict:
        """Process one trade return, update statistics, return verdict."""

    def reset(self, null_mean: float = 0.0, sigma: float | None = None):
        """Reset state (e.g. when regime changes)."""

    def get_state(self) -> dict:
        """Serialize for persistence (like BayesianChangepoint pattern)."""

    @classmethod
    def from_state(cls, state: dict) -> "MixtureSPRT":
        """Restore from serialized state."""
```

**Implementation notes**:
- sigma should be estimated from the first 20-30 trades (burn-in period)
- During burn-in, always return INCONCLUSIVE
- tau controls sensitivity: small tau = detect small effects (more trades needed), large tau = detect large effects (fewer trades)
- Default tau=1.0 means we're looking for ~1 R-multiple shift in mean
- Use log-space arithmetic to avoid overflow: log(Lambda_n) instead of Lambda_n
- Track running sum and count for O(1) updates (don't store all observations)

**Key state variables**:
- n: trade count
- sum_z: sum of shifted observations
- sum_z_sq: sum of squared shifted observations (for online variance)
- log_lambda: current log-likelihood ratio

---

## Task 3: Regime-Aware Null

### File: `src/tradememory/ssrt/regime.py`

**Purpose**: Maintain per-regime performance baselines and provide regime-appropriate null hypotheses to the mSPRT engine.

**Class interface**:
```python
class RegimeAwareNull:
    VALID_REGIMES = {"trending_up", "trending_down", "ranging", "volatile"}

    def __init__(self, min_trades_per_regime: int = 10, default_null: float = 0.0):
        """
        Args:
            min_trades_per_regime: minimum trades before using regime-specific null
            default_null: fallback null mean when insufficient regime data
        """

    def update(self, trade: TradeResult):
        """Update regime baseline with new trade."""

    def get_null(self, regime: str) -> tuple[float, float]:
        """Return (null_mean, sigma) for given regime.
        Falls back to default if insufficient data.
        """

    def get_baselines(self) -> dict[str, RegimeBaseline]:
        """Return all regime baselines."""

    def get_state(self) -> dict:
        """Serialize for persistence."""

    @classmethod
    def from_state(cls, state: dict) -> "RegimeAwareNull":
        """Restore from serialized state."""
```

**Logic**:
1. Maintain running mean/variance per regime using Welford's online algorithm
2. When a regime has >= min_trades_per_regime, use its mean as null_mean
3. When insufficient data, use default_null (0.0 = assume no edge as baseline)
4. sigma is estimated per-regime when sufficient data, otherwise use pooled sigma

**Integration with MixtureSPRT**:
```python
# Usage pattern:
regime_null = RegimeAwareNull()
msprt = MixtureSPRT()

for trade in trade_stream:
    regime_null.update(trade)
    null_mean, sigma = regime_null.get_null(trade.regime)
    msprt.reset(null_mean=null_mean, sigma=sigma)  # only if regime changed
    observation = trade.pnl_r - null_mean  # shift by null
    verdict = msprt.update(observation)
```

**Important design decision**: When regime changes mid-test:
- Option A: Reset mSPRT entirely (lose accumulated evidence)
- Option B: Adjust the observation shift but keep accumulated evidence
- **Choose Option A** for Phase 1 — simpler, statistically cleaner. The cost is slower detection after regime change, but the benefit is correct Type I error control.

---

## Task 4: Unit Tests

### File: `tests/test_ssrt_core.py`

Test cases for MixtureSPRT:

1. **test_always_positive_returns_continue**: Feed 50 trades with pnl_r ~ N(1.0, 1.0). Should get CONTINUE or INCONCLUSIVE, never RETIRE.

2. **test_always_negative_returns_retire**: Feed 50 trades with pnl_r ~ N(-1.0, 1.0). Should eventually get RETIRE.

3. **test_burn_in_returns_inconclusive**: First 20 trades should always return INCONCLUSIVE regardless of values.

4. **test_p_value_always_valid**: After each update, p_value should be in [0, 1].

5. **test_lambda_monotonic_under_h0**: Under H0 (null is true), lambda should stay around 1 (not grow systematically).

6. **test_type_i_error_control**: Run 1000 simulations under H0 (pnl_r ~ N(0, 1)). RETIRE rate should be <= alpha + tolerance (say 0.08 for finite sample).

7. **test_serialization_roundtrip**: get_state() -> from_state() should produce identical results on next update.

8. **test_reset_clears_state**: After reset(), behaves like a fresh instance.

### File: `tests/test_ssrt_regime.py`

1. **test_update_builds_baselines**: Add trades in different regimes, verify baselines reflect correct means.

2. **test_insufficient_data_uses_default**: With <10 trades in a regime, get_null() returns default (0.0).

3. **test_sufficient_data_uses_regime_mean**: With >=10 trades, get_null() returns that regime's mean.

4. **test_multi_regime_independence**: Trending_up trades don't affect ranging baselines.

5. **test_serialization_roundtrip**: State persistence works correctly.

6. **test_invalid_regime_raises**: Unknown regime string raises ValueError.

---

## Task 5: Simulator + Baselines

### File: `src/tradememory/ssrt/simulator.py`

**Purpose**: Generate synthetic trade sequences with known decay patterns for controlled experiments.

```python
class DecaySimulator:
    """Generate trade sequences with injected decay patterns."""

    @staticmethod
    def no_decay(n_trades: int, mean: float = 0.5, std: float = 1.5,
                 regime: str = "trending_up", seed: int | None = None) -> list[TradeResult]:
        """Control: strategy with stable edge."""

    @staticmethod
    def sudden_death(n_trades: int, decay_at: int, pre_mean: float = 0.5,
                     post_mean: float = -0.3, std: float = 1.5,
                     regime: str = "trending_up", seed: int | None = None) -> list[TradeResult]:
        """Alpha drops to post_mean at trade #decay_at."""

    @staticmethod
    def linear_decay(n_trades: int, decay_start: int, decay_end: int,
                     pre_mean: float = 0.5, post_mean: float = -0.3,
                     std: float = 1.5, regime: str = "trending_up",
                     seed: int | None = None) -> list[TradeResult]:
        """Alpha decays linearly from pre_mean to post_mean between decay_start and decay_end."""

    @staticmethod
    def regime_specific_decay(n_trades: int, decay_at: int,
                              decay_regime: str = "trending_up",
                              safe_regime: str = "ranging",
                              regime_schedule: list[tuple[int, str]] | None = None,
                              seed: int | None = None) -> list[TradeResult]:
        """Alpha decays only in decay_regime, survives in safe_regime.
        regime_schedule: list of (trade_index, regime) to control regime sequence.
        """
```

Each method returns `list[TradeResult]` with realistic timestamps (1 trade per hour, UTC).

### File: `src/tradememory/ssrt/baselines.py`

**Purpose**: Baseline methods for comparison. Wrap existing implementations where possible.

```python
class MaxDDBaseline:
    """Stop when max drawdown exceeds threshold."""
    def __init__(self, threshold_pct: float = 20.0):
        ...
    def update(self, trade: TradeResult) -> str:
        """Returns "CONTINUE" or "RETIRE"."""
    def reset(self): ...

class RollingSharpeBaseline:
    """Stop when N-trade rolling Sharpe stays below 0."""
    def __init__(self, window: int = 30, consecutive: int = 3):
        ...
    def update(self, trade: TradeResult) -> str:
        """Returns "CONTINUE" or "RETIRE"."""
    def reset(self): ...

class CUSUMBaseline:
    """Wrapper around existing cusum_drift_detect()."""
    def __init__(self, threshold: float = 4.0, target_wr: float = 0.5):
        ...
    def update(self, trade: TradeResult) -> str:
        """Returns "CONTINUE" or "RETIRE"."""
    def reset(self): ...
```

All baselines share the same interface: `update(trade) -> str`, `reset()`.

---

## Task 6: Experiment Runner

### File: `scripts/research/ssrt_experiments.py`

**Purpose**: Run Monte Carlo experiments comparing SSRT vs baselines across decay scenarios.

**Experiment design**:

```python
SCENARIOS = {
    "no_decay":         {"method": "no_decay",          "n": 200, "params": {"mean": 0.5}},
    "sudden_death_50":  {"method": "sudden_death",      "n": 200, "params": {"decay_at": 50}},
    "sudden_death_100": {"method": "sudden_death",      "n": 200, "params": {"decay_at": 100}},
    "linear_decay":     {"method": "linear_decay",       "n": 200, "params": {"decay_start": 50, "decay_end": 150}},
    "regime_specific":  {"method": "regime_specific_decay", "n": 200, "params": {"decay_at": 50}},
}

METHODS = {
    "mSPRT":           MixtureSPRT(alpha=0.05, tau=1.0),
    "mSPRT_regime":    MixtureSPRT(alpha=0.05, tau=1.0),  # + RegimeAwareNull
    "MaxDD_10":        MaxDDBaseline(threshold_pct=10.0),
    "MaxDD_20":        MaxDDBaseline(threshold_pct=20.0),
    "RollingSharpe":   RollingSharpeBaseline(window=30),
    "CUSUM":           CUSUMBaseline(threshold=4.0),
}

N_SIMULATIONS = 500  # Monte Carlo runs per cell
```

**Metrics to collect per simulation**:
```python
@dataclass
class ExperimentResult:
    scenario: str
    method: str
    detected: bool         # did the method trigger retirement?
    detection_trade: int   # at which trade? (None if not detected)
    true_decay_trade: int  # ground truth (None for no_decay)
    detection_delay: int   # detection_trade - true_decay_trade (None if N/A)
    final_pnl: float       # cumulative P&L at detection (or at end)
    pnl_saved: float       # P&L difference vs running full sequence
```

**Output**: Save results to `validation/ssrt/experiment_results.json` with:
- Per-scenario, per-method aggregate metrics:
  - Type I error rate (false retirement on no_decay)
  - Type II error rate (missed retirement on decay scenarios)
  - Median detection delay
  - Mean P&L saved

**Print summary table** like:
```
Scenario          | Method        | Type I | Type II | Median Delay | Mean P&L Saved
no_decay          | mSPRT         |  0.04  |   ---   |     ---      |    ---
no_decay          | MaxDD_20      |  0.12  |   ---   |     ---      |    ---
sudden_death_50   | mSPRT         |  ---   |  0.08   |     12       |  +$450
sudden_death_50   | MaxDD_20      |  ---   |  0.22   |     28       |  +$210
...
```

**Run command**: `python scripts/research/ssrt_experiments.py`
Save results to `validation/ssrt/`.

---

## Task 7: Run Experiments + Analyze

Run the experiment script. Analyze results. Save summary to `validation/ssrt/phase1_results.md`.

Key questions to answer:
1. Does mSPRT control Type I error at alpha=0.05?
2. Does mSPRT detect decay faster than MaxDD/CUSUM?
3. Does regime-aware null improve detection on regime_specific_decay scenario?
4. What's the economic value (P&L saved) of SSRT vs baselines?

---

## Task 8: Run all tests

```bash
cd C:/Users/johns/projects/tradememory-protocol
python -m pytest tests/ -v --tb=short
```

All existing 1370+ tests must still pass. New SSRT tests must pass.
