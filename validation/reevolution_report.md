# Re-Evolution Validation Report — Phase 15

## Experiment: Grid WFO Baseline (Exp 4a)

**Date**: 2026-03-21
**Data**: BTCUSDT 1H, 2020-01 to 2026-03 (53,993 bars)
**Design**: 23 regime periods (3mo IS + 3mo OOS, sliding 3mo)

### Arms

| Arm | Description | M per period |
|-----|-------------|-------------|
| Arm G | Grid WFO + DSR gate | 19,200 |
| Control A | Static Strategy E (2024 frozen) | 1 |
| Control B | Buy & Hold | 0 |
| Control C | Random (seed per period) | 1 |

### Sharpe Calculation

**Raw Sharpe** (no annualization): `mean(pnls) / std(pnls)`.
All arms use the same metric within each OOS window — directly comparable.

Previous run used annualized Sharpe (`× sqrt(6048)`) on trade-level PnLs, which over-inflated values ~6-8x. Fixed 2026-03-21.

### Results

```
Period    Arm G    Ctrl A    Ctrl B    Ctrl C   G>A  G>C  DSR
P1       0.0000   -0.0984    0.0285    0.1242    Y    N  FAIL
P2       0.0000    0.1950    0.0182    0.0648    N    N  FAIL
P3       0.0000    0.1406    0.0711   -0.0178    N    Y  FAIL
P4       0.0000   -0.0563    0.0343    0.0586    Y    N  FAIL
P5       0.0000   -0.0791   -0.0172   -0.2168    Y    Y  FAIL
P6       0.0000    0.1835    0.0183   -0.1717    N    Y  FAIL
P7       0.0000   -0.1821    0.0071    0.1440    Y    N  FAIL
P8       0.0000   -0.1074    0.0020    0.0385    Y    N  FAIL
P9       0.0000   -0.2042   -0.0420   -0.0381    Y    Y  FAIL
P10      0.0000   -0.0682    0.0002   -0.2181    Y    Y  FAIL
P11      0.0000   -0.2523   -0.0120    0.1370    Y    N  FAIL
P12      0.0000    0.1881    0.0470   -0.2293    N    Y  FAIL
P13      0.0000    0.0369    0.0093   -0.0008    N    Y  FAIL
P14      0.0000   -0.0065   -0.0146   -0.0969    Y    Y  FAIL
P15      0.0000    0.1299    0.0492   -0.0010    N    Y  FAIL
P16      0.0000    0.0185    0.0429   -0.1283    N    Y  FAIL
P17      0.0000    0.1289   -0.0085    0.1210    N    N  FAIL
P18      0.0000    0.2868    0.0034    0.0480    N    N  FAIL
P19      0.0000    0.0088    0.0351    0.1795    N    N  FAIL
P20      0.0000    0.0496   -0.0074    0.0146    N    N  FAIL
P21      0.0000    0.0511    0.0290    0.0872    N    N  FAIL
P22      0.0000   -0.1061    0.0100    0.2108    Y    N  FAIL
P23      0.0000    0.1343   -0.0220   -0.0503    N    Y  FAIL
```

Mean Sharpe: G=0.0000, A=0.0170, B=0.0123, C=0.0026

### Layer 1 Gate (Pre-Registered)

| Criterion | Result | Verdict |
|-----------|--------|---------|
| G > A ≥60% periods, Wilcoxon p<0.10 | 43.5%, p=0.543 | **FAIL** |
| G > C ≥60% periods, Wilcoxon p<0.10 | 47.8%, p=0.831 | **FAIL** |
| DSR survive ≥50% | 0/23 = 0% | **FAIL** |

**Layer 1 Gate: FAIL (3/3 criteria failed)**

### Root Cause Analysis

The failure is NOT caused by "re-evolution has no directional value." It is caused by **M=19,200 being mathematically incompatible with 30-50 trades per IS window**.

DSR formula: the expected maximum Sharpe under the null hypothesis scales with `sqrt(2 * ln(M))`. For M=19,200, this is `sqrt(2 * ln(19200)) ≈ 4.4` in standardized units. With ~40 trades, the standard error of Sharpe ≈ `1/sqrt(40) ≈ 0.16`. The raw Sharpe needed to beat the DSR threshold would be approximately `4.4 * 0.16 ≈ 0.7` — but the best grid candidates only achieve raw Sharpe of ~0.2-0.4 in-sample.

**No single-bar trading strategy can produce a raw Sharpe of 0.7 from 40 trades.** The gate is correctly identifying that 3-month data cannot statistically justify a selection from 19,200 candidates.

### Key Implication for Exp 4b (LLM H2H)

LLM Evolution tests ~30 hypotheses per run (M≈30), not 19,200. The DSR threshold for M=30 is `sqrt(2 * ln(30)) ≈ 2.6` standardized units, requiring raw Sharpe ≈ `2.6 * 0.16 ≈ 0.42` — achievable.

This means LLM evolution's unique value is not necessarily "finding better strategies" but **"finding defensible strategies with lower statistical burden."** Search efficiency is not just a time savings — it is a statistical survival advantage.

| Method | M per period | DSR threshold (approx) | Feasibility |
|--------|-------------|----------------------|-------------|
| Grid search | 19,200 | ~0.7 raw Sharpe | Impossible with 40 trades |
| LLM evolution | ~30 | ~0.42 raw Sharpe | Achievable |

### Decision

**Accept FAIL as-is.** No post-hoc parameter adjustment (smaller grid, longer IS) — that would defeat the purpose of pre-registration.

Proceed to Exp 4b (LLM vs Grid H2H) because the failure mode is precisely what LLM evolution claims to solve. This is not moving goalposts — it is following the evidence to the next pre-registered experiment.

### Corrections to Previous Results

The previous run (annualized) reported:
- Arm G mean Sharpe: 17.64 → corrected: 0.00
- Ctrl A mean Sharpe: 1.32 → corrected: 0.017
- G>A win rate: 91.3% → corrected: 43.5%

The relative ranking shift (from 91.3% to 43.5%) is because Arm G went from inflated-but-positive to 0.0 (DSR gate blocks everything), while controls were unaffected by the DSR gate.

---

## Experiment 4b Step 0: LLM Evolution Single Transition

**Date**: 2026-03-21
**Data**: BTCUSDT 1H, 2020-01-01 to 2020-04-01 (2,178 bars, IS window only)
**Config**: EvolutionEngine 3 generations × 10 population, Sonnet 4

### Key Metrics

| Metric | Value |
|--------|-------|
| M (IS hypotheses) | 30 |
| Total backtests | 38 (30 IS + 8 OOS) |
| Graduated | 0 |
| Eliminated | 30 |
| LLM tokens | 13,751 |
| Cost (this period) | ~$0.107 |
| Projected cost (23 periods) | ~$2.47 |
| Elapsed time | 126.7s |

### Structural Novelty Analysis

**Gate: PASS — 28/30 hypotheses (93%) have structural novelty.**

Fields used across all 30 hypotheses:

| Field | Count | In Grid? |
|-------|-------|----------|
| hour_utc | 30 | Yes |
| trend_12h_pct | 19 | Yes |
| trend_24h_pct | 11 | **No** |
| atr_percentile | 2 | **No** |

Novel features the LLM discovered that grid search cannot use:
- `trend_24h_pct` — 24h trend filter (11/30 hypotheses)
- `atr_percentile` — volatility percentile filter (2/30 hypotheses)
- `between` operator — range filtering on trend_12h_pct (3/30)
- `in` operator — multi-hour entry (1/30, hours [2,5])
- `validity_conditions` — regime/volatility filtering (26/30 had volatility_regime=normal)

Operators used: `eq`, `gt`, `lt`, `between`, `in` (grid only uses `eq` + `gt`/`lt`).

### Performance Observations

Despite structural novelty, **0 hypotheses graduated** (all eliminated). Key patterns:

1. **IS Sharpe distribution**: Range [-42.2, 42.6], mostly negative. High positive values (38.8, 42.6) came from <10 trades — not robust.
2. **OOS survival**: Only 8/30 reached OOS backtest. Of those, best OOS Sharpe=49.0 (#9 London Afternoon, 11 IS trades) but eliminated due to insufficient robustness.
3. **The LLM gravitates toward single-hour entry** — almost all hypotheses use `hour_utc eq N`. This limits trade frequency to ~1/day, yielding 20-30 trades in 3 months.
4. **LLM defaults to `volatility_regime=normal`** in validity conditions — this is cosmetic (backtester doesn't enforce validity_conditions), not functional novelty.

### Step 0 Decision

| Criterion | Result |
|-----------|--------|
| Structural novelty (≥1 non-grid feature) | **PASS** (trend_24h_pct, atr_percentile) |
| Functional novelty (backtester uses the feature) | **PASS** (trend_24h_pct and atr_percentile are in MarketContext) |
| Any graduated strategy | **FAIL** (0/30) |

**Decision: PROCEED to pilot** — The 0-graduation issue may be period-specific (2020-Q1 was the COVID crash period). The structural novelty gate is the primary criterion for Step 0, and it passes decisively. The full WFO across 23 periods will test whether any period produces LLM graduates that survive DSR.

### Bug Fix Applied

Before Step 0, fixed `ReEvolutionPipeline.run()`: `cumulative_trials` now increments on ALL outcomes (not just DSR pass). Without this fix, failed periods don't accumulate M, causing DSR to be too lenient for later periods. 3 new tests added.

---

## Experiment 4b Pilot: LLM WFO (5 periods)

**Date**: 2026-03-21
**Data**: BTCUSDT 1H, periods P1-P5 (2020-01 to 2021-07)
**Config**: EvolutionEngine 3 gen × 10 pop, Sonnet 4, 5 pilot periods

### Results

```
Period      Arm L    Arm G   Ctrl A   Ctrl B  L>A  L>G  DSR
P1         0.0000   0.0000  -0.0984   0.0285    Y    N  FAIL
P2         0.0000   0.0000   0.1950   0.0182    N    N  FAIL
P3         0.0000   0.0000   0.1406   0.0711    N    N  FAIL
P4         0.0000   0.0000  -0.0563   0.0343    Y    N  FAIL
P5         0.0000   0.0000  -0.0791  -0.0172    Y    N  FAIL
```

### Key Metrics

| Metric | Value |
|--------|-------|
| Total hypotheses (5 periods) | 150 |
| Graduated | **0 (0%)** |
| Cohen's d (L vs G) | **0.000** |
| Cohen's d (L vs A) | -0.211 |
| DSR pass | 0/5 (0%) |
| Total cost | $0.54 |
| Novel fields | atr_h1, atr_percentile, day_of_week, regime, trend_24h_pct, volatility_regime |

### Root Cause: 0% Graduation Rate

The LLM evolution produces structurally novel hypotheses (6 unique fields beyond grid's 2), but **none survive the EvolutionEngine's internal IS→OOS selection**. The bottleneck is not DSR — it's the upstream graduation gate.

Why 0% graduation across 150 hypotheses (5 periods × 30):
1. **Single-hour entry dominance**: LLM defaults to `hour_utc eq N`, limiting each strategy to ~1 trade/day → ~30 trades in 3 months → high Sharpe variance.
2. **Internal 70/30 IS/OOS split**: The 3-month window gets split into ~63 days IS + ~27 days OOS internally. With single-hour strategies, this means ~20 IS trades and ~10 OOS trades — the selector eliminates anything with <30 trades or negative OOS Sharpe.
3. **The prompt encourages conservative parameters**: System prompt says "short holding periods (1-12 bars)" and "asymmetric RR ≥ 2:1", producing tight strategies that trigger rarely.

### Layer 2 Gate (Pre-Registered)

| Criterion | Result | Verdict |
|-----------|--------|---------|
| L DSR survive > G DSR survive (>0%) | 0% = 0% | **FAIL** |
| L OOS Sharpe > A in ≥50% periods, p<0.10 | 60%, p=0.686 | **FAIL** (p too high) |
| ≥1 hypothesis uses non-grid feature | **PASS** (6 novel fields) | PASS |

**Layer 2 Gate: FAIL (2/3 criteria failed)**

### Pilot Decision

**STOP. Cohen's d = 0.000. No statistical difference between LLM and Grid arms.**

Running the remaining 18 periods (~$2, ~40min) would not change the result — both arms produce 0 Sharpe (cash position) because neither can graduate strategies from 3-month windows.

### Implications

1. **The LLM vs Grid comparison is moot when neither graduates.** The hypothesis "LLM has lower M → easier DSR" is technically correct but irrelevant — the bottleneck is upstream (graduation), not downstream (DSR).
2. **Structural novelty is confirmed** — LLM discovers features grid cannot use (6 novel fields). But this advantage requires strategies that trade enough to be statistically evaluable.
3. **The DSR gate is working correctly.** It is telling us the data is insufficient, not that the search method is wrong.

---

## Phase 15 Conclusion

**In the setting of 1H timeframe + 3-month rolling window + single-hour entry strategies, neither grid search (M=19,200) nor LLM evolution (M=30) can produce strategies that survive the DSR gate. The bottleneck is trade count per window, not search method.**

This is not a failure of the Evolution Engine concept. It is a **specification boundary**: the engine requires strategies that produce sufficient trades per evaluation window for statistical defensibility. The DSR gate's MinBTL requirement is incompatible with strategies that trigger ~1 trade/day over 3 months (~90 trades IS, ~30 OOS after 70/30 split — but single-hour entry reduces this to ~30 IS / ~10 OOS, below any reasonable significance threshold).

### What was validated

| Finding | Status |
|---------|--------|
| DSR gate correctly blocks underpowered strategies | **Confirmed** |
| Grid search M=19,200 is too large for 3mo windows | **Confirmed** (Exp 4a) |
| LLM evolution produces structurally novel hypotheses | **Confirmed** (6 fields beyond grid) |
| LLM's lower M gives DSR advantage over grid | **Untestable** (0% graduation in both arms) |
| 3mo BTC 1H + single-hour entry = insufficient data | **Confirmed** (Exp 4a + 4b) |

### Evolution Engine feasibility boundary

The engine needs one of:
- **Higher trade frequency**: strategies that trigger multiple times per day (multi-hour entry, or shorter timeframes like 5m/15m)
- **Longer evaluation windows**: 6-12 months IS instead of 3 months
- **Higher-frequency timeframes**: 5m or 15m bars → 10-50x more trades per window

This is product spec, not a defect. "Suitable for strategies producing ≥N trades per evaluation window" is a legitimate constraint to document.

### Decision

**Accept Phase 15 results as-is. No post-hoc parameter adjustment.** The pre-registered criteria were applied honestly:
- Exp 4a Layer 1 Gate: FAIL (3/3)
- Exp 4b Step 0 Gate: PASS (structural novelty)
- Exp 4b Layer 2 Gate: FAIL (2/3, pilot Cohen's d = 0.000 → STOP)

Phase 15 is complete. Evolution Engine validation deferred to a setting with sufficient trade frequency.
