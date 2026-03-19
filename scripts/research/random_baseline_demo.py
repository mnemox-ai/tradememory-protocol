#!/usr/bin/env python3
"""
Random Baseline Demo — Phase 13 Step 1

Generates synthetic OHLCV data (random walk), runs 200 random strategies,
then ranks a mock "Strategy C" (Sharpe 2.0) against the random distribution.

Usage:
    python scripts/research/random_baseline_demo.py
"""

import numpy as np


def generate_random_ohlcv(n_bars: int = 1000, start_price: float = 30000.0, seed: int = 42) -> np.ndarray:
    """Generate n_bars of hourly OHLCV via geometric random walk.

    Returns array with columns: [open, high, low, close, volume].
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, 0.001, n_bars)  # ~0.1% hourly vol
    prices = start_price * np.exp(np.cumsum(returns))

    ohlcv = np.zeros((n_bars, 5))
    for i in range(n_bars):
        base = prices[i]
        noise = rng.uniform(0.0005, 0.002, 3)
        ohlcv[i, 0] = base * (1 + rng.uniform(-0.001, 0.001))  # open
        ohlcv[i, 3] = base  # close
        ohlcv[i, 1] = max(ohlcv[i, 0], ohlcv[i, 3]) * (1 + noise[0])  # high
        ohlcv[i, 2] = min(ohlcv[i, 0], ohlcv[i, 3]) * (1 - noise[1])  # low
        ohlcv[i, 4] = rng.uniform(100, 10000)  # volume

    return ohlcv


def compute_sharpe(returns: np.ndarray, periods_per_year: float = 8760.0) -> float:
    """Annualized Sharpe ratio from a return series."""
    if len(returns) < 2 or np.std(returns) == 0:
        return 0.0
    return float(np.mean(returns) / np.std(returns) * np.sqrt(periods_per_year))


def random_strategy_sharpe(ohlcv: np.ndarray, rng: np.random.Generator) -> float:
    """Run one random strategy: random entry/exit on close prices, compute Sharpe."""
    closes = ohlcv[:, 3]
    n = len(closes)

    # Random long/short/flat signals
    signals = rng.choice([-1, 0, 1], size=n, p=[0.25, 0.5, 0.25])
    price_returns = np.diff(closes) / closes[:-1]
    strategy_returns = signals[:-1] * price_returns

    return compute_sharpe(strategy_returns)


def run_random_baseline(ohlcv: np.ndarray, n_strategies: int = 200, seed: int = 123) -> np.ndarray:
    """Run n_strategies random strategies, return array of Sharpe ratios."""
    rng = np.random.default_rng(seed)
    sharpes = np.array([random_strategy_sharpe(ohlcv, rng) for _ in range(n_strategies)])
    return sharpes


def percentile_rank(distribution: np.ndarray, value: float) -> float:
    """Percentile rank of value within distribution (0-100)."""
    return float(np.sum(distribution < value) / len(distribution) * 100)


def main():
    print("=" * 60)
    print("Phase 13 — Random Baseline Demo (Simulated Data)")
    print("=" * 60)

    # Step 1: Generate synthetic data
    print("\n[1] Generating 1000 bars of hourly OHLCV (random walk, start=$30,000)...")
    ohlcv = generate_random_ohlcv(n_bars=1000, start_price=30000.0)
    print(f"    Price range: ${ohlcv[:, 2].min():.2f} — ${ohlcv[:, 1].max():.2f}")

    # Step 2: Run 200 random strategies
    print("\n[2] Running 200 random strategies...")
    sharpes = run_random_baseline(ohlcv, n_strategies=200)

    mean_s = np.mean(sharpes)
    std_s = np.std(sharpes)
    p5 = np.percentile(sharpes, 5)
    p50 = np.percentile(sharpes, 50)
    p95 = np.percentile(sharpes, 95)

    print(f"    Distribution stats:")
    print(f"      Mean:  {mean_s:+.4f}")
    print(f"      Std:   {std_s:.4f}")
    print(f"      P5:    {p5:+.4f}")
    print(f"      P50:   {p50:+.4f}")
    print(f"      P95:   {p95:+.4f}")

    # Step 3: Rank Strategy C (Sharpe 2.0)
    strategy_c_sharpe = 2.0
    pct = percentile_rank(sharpes, strategy_c_sharpe)
    passed = pct >= 95.0

    print(f"\n[3] Strategy C (mock Sharpe = {strategy_c_sharpe}):")
    print(f"    Percentile rank: {pct:.1f}%")
    print(f"    Pass threshold:  95%")
    print(f"    Result:          {'PASS ✓' if passed else 'FAIL ✗'}")

    print("\n" + "=" * 60)
    print("Demo complete. Replace synthetic data with real Binance OHLCV")
    print("for production validation.")
    print("=" * 60)


if __name__ == "__main__":
    main()
