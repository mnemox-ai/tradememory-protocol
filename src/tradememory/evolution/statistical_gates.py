"""Statistical Gates — Deflated Sharpe Ratio + FDR control.

Three pure functions for multiple-testing correction in strategy evaluation:

1. deflated_sharpe_ratio() — Bailey & Lopez de Prado (2014)
2. min_backtest_length() — minimum observations needed
3. benjamini_hochberg() — FDR control for multiple strategies

References:
    Bailey, D. H., & Lopez de Prado, M. (2014).
    "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting,
     and Non-Normality." Journal of Portfolio Management.
"""

from __future__ import annotations

import math
from typing import List, Tuple


def deflated_sharpe_ratio(
    observed_sr: float,
    num_trials: int,
    num_obs: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> Tuple[float, float]:
    """Compute the Deflated Sharpe Ratio (DSR).

    Adjusts the observed Sharpe ratio for the number of trials (strategies tested),
    accounting for non-normality of returns.

    Args:
        observed_sr: Observed (annualized) Sharpe ratio.
        num_trials: Number of independent strategies/trials tested (M).
        num_obs: Number of observations (T) in the backtest.
        skewness: Skewness of returns (0 for normal).
        kurtosis: Kurtosis of returns (3 for normal).

    Returns:
        (dsr, p_value): DSR value and associated p-value.
        DSR > 0 means the strategy likely has real alpha after accounting for trials.
        p_value < 0.05 means statistically significant.
    """
    if num_trials < 1 or num_obs < 2:
        return 0.0, 1.0

    # Expected maximum SR under the null hypothesis (all M trials are noise).
    # Under null, each SR_hat ~ N(0, 1/(T-1)), so:
    # E[max(SR)] = sqrt(1/(T-1)) * E[max of M standard normals]
    # Using Gumbel approximation for E[max of M N(0,1)]:
    # E[Z_max] ≈ sqrt(2*ln(M)) - (ln(ln(M)) + ln(4π)) / (2*sqrt(2*ln(M)))
    if num_trials <= 1:
        sr_max = 0.0  # single trial: no selection bias
    else:
        ln_m = math.log(num_trials)
        z = math.sqrt(2 * ln_m)
        # Gumbel correction for expected max of M N(0,1)
        e_z_max = z - (math.log(math.log(num_trials)) + math.log(4 * math.pi)) / (2 * z)
        # Scale by SR null standard deviation
        sr_max = e_z_max * math.sqrt(1.0 / (num_obs - 1))

    # Standard error of the Sharpe ratio (accounting for non-normality)
    # SE(SR) = sqrt((1 - skew*SR + (kurtosis-1)/4 * SR^2) / (T-1))
    sr = observed_sr
    se_sr = math.sqrt(
        max(
            (1 - skewness * sr + ((kurtosis - 1) / 4) * sr * sr) / (num_obs - 1),
            1e-12,
        )
    )

    # DSR = (SR_observed - SR_max) / SE(SR)
    dsr = (sr - sr_max) / se_sr

    # p-value from standard normal CDF
    p_value = 1.0 - _norm_cdf(dsr)

    return round(dsr, 6), round(p_value, 6)


def min_backtest_length(
    target_sr: float,
    num_trials: int,
    alpha: float = 0.05,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> int:
    """Compute minimum backtest length needed for a target Sharpe ratio.

    Given a target SR and number of trials, returns the minimum number of
    observations T such that DSR > 0 at significance level alpha.

    Args:
        target_sr: Target (annualized) Sharpe ratio (SR*).
        num_trials: Number of strategies tested (M).
        alpha: Significance level (default 0.05).
        skewness: Skewness of returns.
        kurtosis: Kurtosis of returns.

    Returns:
        Minimum number of observations needed (T).
    """
    if target_sr <= 0 or num_trials < 1:
        return 0

    # Binary search for minimum T where DSR p-value < alpha
    lo, hi = 2, 100000

    # First check if hi is sufficient
    dsr, p = deflated_sharpe_ratio(target_sr, num_trials, hi, skewness, kurtosis)
    if p >= alpha:
        return hi  # even max isn't enough

    while lo < hi:
        mid = (lo + hi) // 2
        dsr, p = deflated_sharpe_ratio(target_sr, num_trials, mid, skewness, kurtosis)
        if p < alpha:
            hi = mid
        else:
            lo = mid + 1

    return lo


def benjamini_hochberg(
    p_values: List[float],
    alpha: float = 0.05,
) -> List[Tuple[int, float, bool]]:
    """Benjamini-Hochberg FDR correction for multiple testing.

    Args:
        p_values: List of p-values from multiple strategy tests.
        alpha: Target FDR level (default 0.05).

    Returns:
        List of (original_index, p_value, significant) tuples,
        sorted by original index.
    """
    if not p_values:
        return []

    m = len(p_values)

    # Sort by p-value (keep original indices)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])

    # Find BH threshold: largest k where p_(k) <= k/m * alpha
    significant = [False] * m
    max_significant_rank = -1

    for rank, (orig_idx, p) in enumerate(indexed):
        k = rank + 1  # 1-indexed rank
        threshold = (k / m) * alpha
        if p <= threshold:
            max_significant_rank = rank

    # All p-values with rank <= max_significant_rank are significant
    if max_significant_rank >= 0:
        for rank in range(max_significant_rank + 1):
            orig_idx = indexed[rank][0]
            significant[orig_idx] = True

    return [(i, p_values[i], significant[i]) for i in range(m)]


def _norm_cdf(x: float) -> float:
    """Standard normal CDF using the error function."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
