"""
Phase 4: Full Experiment Runner
Run complete experiment matrix: 3yr x 3tf x 2sym x 3 strategies = 18 A/B + 72 ablation

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/research/run_phase4.py

Output:
    scripts/research/phase4_results.json
    scripts/research/phase4_report.md
"""

import asyncio
import logging
import sys
import time

# Setup logging before any imports that use it
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scripts/research/phase4.log", mode="w"),
    ],
)

logger = logging.getLogger(__name__)

# Suppress noisy per-trade logs from owm_helpers
logging.getLogger("tradememory.owm_helpers").setLevel(logging.WARNING)
logging.getLogger("tradememory.owm.changepoint").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def main():
    from tradememory.simulation.runner import run_full_experiment

    # Note: 15m excluded initially (105K bars too slow for per-trade DB writes).
    # Run 1h + 4h first, add 15m as a separate follow-up if needed.
    timeframes = sys.argv[1:] if len(sys.argv) > 1 else ["1h", "4h"]

    start = time.time()
    n = 2 * len(timeframes) * 3
    print("=" * 60)
    print("Phase 4: Full Experiment — 3yr x 2sym")
    print(f"  Symbols:    BTCUSDT, ETHUSDT")
    print(f"  Timeframes: {', '.join(timeframes)}")
    print("  Strategies: TrendFollow, Breakout, MeanReversion")
    print("  IS/OOS:     67% / 33%")
    print("  Days:       1095 (3 years)")
    print(f"  Total runs: {n} A/B + {n * 4} ablation = {n * 5} experiments")
    print("=" * 60)
    print()

    result = await run_full_experiment(
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframes=timeframes,
        days=1095,
        is_ratio=0.67,
        output_dir="scripts/research",
    )

    elapsed = time.time() - start

    print()
    print("=" * 60)
    print(f"COMPLETED in {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"  Successful: {result['successful']}/{result['total_experiments']}")
    print(f"  Failed:     {result['failed']}")
    print(f"  Results:    {result['output_json']}")
    print(f"  Report:     {result['output_md']}")
    print("=" * 60)
    print()
    print(result["summary"])


if __name__ == "__main__":
    asyncio.run(main())
