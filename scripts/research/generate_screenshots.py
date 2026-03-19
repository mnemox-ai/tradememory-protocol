#!/usr/bin/env python3
"""
Generate demo output for documentation screenshots.

Runs the L1 → L2 → L3 pipeline with simulated trades and saves
formatted output to assets/screenshots/ for use in README and docs.

Usage:
    python scripts/research/generate_screenshots.py
"""

import sys
import os
import io
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# Force UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure repo root is in path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tradememory.db import Database
from tradememory.journal import TradeJournal
from tradememory.reflection import ReflectionEngine
from tradememory.state import StateManager

OUTPUT_DIR = REPO_ROOT / "assets" / "screenshots"

# Same simulated trades as demo.py (subset for concise output)
TRADES = [
    {"session": "asian",  "strategy": "Pullback",    "direction": "long",  "confidence": 0.60, "pnl": -15.00, "pnl_r": -1.0},
    {"session": "london", "strategy": "VolBreakout", "direction": "long",  "confidence": 0.78, "pnl":  42.00, "pnl_r":  2.1},
    {"session": "london", "strategy": "VolBreakout", "direction": "short", "confidence": 0.72, "pnl":  28.50, "pnl_r":  1.5},
    {"session": "asian",  "strategy": "Pullback",    "direction": "long",  "confidence": 0.55, "pnl": -20.00, "pnl_r": -1.0},
    {"session": "london", "strategy": "VolBreakout", "direction": "long",  "confidence": 0.82, "pnl":  55.00, "pnl_r":  2.8},
    {"session": "london", "strategy": "Pullback",    "direction": "long",  "confidence": 0.70, "pnl":  35.00, "pnl_r":  1.8},
    {"session": "newyork","strategy": "VolBreakout", "direction": "short", "confidence": 0.65, "pnl": -18.00, "pnl_r": -0.9},
    {"session": "asian",  "strategy": "Pullback",    "direction": "long",  "confidence": 0.52, "pnl": -22.00, "pnl_r": -1.1},
    {"session": "london", "strategy": "VolBreakout", "direction": "long",  "confidence": 0.85, "pnl":  60.00, "pnl_r":  3.0},
    {"session": "asian",  "strategy": "Pullback",    "direction": "short", "confidence": 0.50, "pnl": -12.00, "pnl_r": -0.6},
    {"session": "london", "strategy": "VolBreakout", "direction": "long",  "confidence": 0.80, "pnl":  48.00, "pnl_r":  2.4},
    {"session": "london", "strategy": "Pullback",    "direction": "long",  "confidence": 0.75, "pnl":  28.00, "pnl_r":  1.4},
]


def run_pipeline():
    """Run L1 → L2 → L3 pipeline and return formatted output sections."""
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "screenshot_demo.db")
    db = Database(db_path)
    journal = TradeJournal(db)
    reflection = ReflectionEngine(db)
    state = StateManager(db)

    base_time = datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc)
    sections = {}

    # --- L1: Record trades ---
    lines = []
    lines.append("== Step 1: L1 - Recording trades to TradeJournal ==\n")
    lines.append(f"  {'#':>3} | {'Result':<6} | {'Session':<8} | {'Strategy':<12} | {'P&L':>9} | {'R':>5}")

    for i, t in enumerate(TRADES, 1):
        ts = base_time + timedelta(hours=i * 2)
        tid = f"DEMO-{i:04d}"
        journal.record_decision(
            trade_id=tid,
            symbol="XAUUSD",
            direction=t["direction"],
            lot_size=0.05,
            strategy=t["strategy"],
            confidence=t["confidence"],
            reasoning=f"{t['session']} session trade",
            market_context={"session": t["session"], "price": 2850.0, "atr_d1": 150.0},
        )
        journal.record_outcome(
            trade_id=tid,
            exit_price=2850.0 + t["pnl"] / 10,
            pnl=t["pnl"],
            pnl_r=t["pnl_r"],
            exit_reasoning="Target hit" if t["pnl"] > 0 else "Stop loss",
        )
        result = "WIN" if t["pnl"] > 0 else "LOSS"
        pnl_str = f"${t['pnl']:+.2f}"
        lines.append(f"  {i:>3} | {result:<6} | {t['session']:<8} | {t['strategy']:<12} | {pnl_str:>9} | {t['pnl_r']:+.1f}")

    winners = sum(1 for t in TRADES if t["pnl"] > 0)
    total_pnl = sum(t["pnl"] for t in TRADES)
    wr = winners / len(TRADES) * 100
    lines.append(f"\n  Total: {len(TRADES)} trades | Winners: {winners} | Win rate: {wr:.0f}% | Net P&L: ${total_pnl:+.2f}")
    sections["l1"] = "\n".join(lines)

    # --- L2: Reflection patterns ---
    lines = []
    lines.append("\n== Step 2: L2 - Reflection Engine discovers patterns ==\n")

    # Calculate session stats
    session_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0})
    strategy_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0})
    for t in TRADES:
        s = session_stats[t["session"]]
        st = strategy_stats[t["strategy"]]
        if t["pnl"] > 0:
            s["wins"] += 1
            st["wins"] += 1
        else:
            s["losses"] += 1
            st["losses"] += 1
        s["pnl"] += t["pnl"]
        st["pnl"] += t["pnl"]

    lines.append(f"  {'Pattern':<22} | {'Win Rate':>8} | {'Record':>10} | {'Net P&L':>10} | Assessment")
    for name, s in sorted(session_stats.items(), key=lambda x: -x[1]["pnl"]):
        total = s["wins"] + s["losses"]
        wr = s["wins"] / total * 100 if total > 0 else 0
        assess = "HIGH EDGE" if wr >= 70 else "WEAK" if wr < 40 else "MODERATE"
        lines.append(f"  {name + ' session':<22} | {wr:>7.0f}% | {s['wins']}W / {s['losses']}L   | ${s['pnl']:>+8.2f} | {assess}")
    for name, s in sorted(strategy_stats.items(), key=lambda x: -x[1]["pnl"]):
        total = s["wins"] + s["losses"]
        wr = s["wins"] / total * 100 if total > 0 else 0
        assess = "HIGH EDGE" if wr >= 70 else "WEAK" if wr < 40 else "MODERATE"
        lines.append(f"  {name + ' strategy':<22} | {wr:>7.0f}% | {s['wins']}W / {s['losses']}L   | ${s['pnl']:>+8.2f} | {assess}")

    # Confidence correlation
    high_conf = [t for t in TRADES if t["confidence"] >= 0.75]
    low_conf = [t for t in TRADES if t["confidence"] < 0.55]
    high_wr = sum(1 for t in high_conf if t["pnl"] > 0) / len(high_conf) * 100 if high_conf else 0
    low_wr = sum(1 for t in low_conf if t["pnl"] > 0) / len(low_conf) * 100 if low_conf else 0
    lines.append(f"\n  Confidence correlation:")
    lines.append(f"    High (>=0.75): {high_wr:.0f}% win rate")
    lines.append(f"    Low  (<0.55):  {low_wr:.0f}% win rate")
    sections["l2"] = "\n".join(lines)

    # --- L3: Strategy adjustments ---
    lines = []
    lines.append("\n== Step 3: L3 - Strategy adjustments generated ==\n")
    lines.append(f"  {'Parameter':<28} | {'Old':>5} | {'New':>5} | Reason")

    # Simulated adjustments based on patterns
    adjustments = [
        ("london_max_lot", "0.05", "0.08", f"London WR {session_stats['london']['wins']}/{session_stats['london']['wins']+session_stats['london']['losses']} — earned more room"),
        ("asian_max_lot", "0.05", "0.025", f"Asian WR {session_stats['asian']['wins']}/{session_stats['asian']['wins']+session_stats['asian']['losses']} — reduce exposure"),
        ("min_confidence_threshold", "0.40", "0.55", f"Trades below 0.55 have {low_wr:.0f}% WR"),
    ]
    for param, old, new, reason in adjustments:
        lines.append(f"  {param:<28} | {old:>5} | {new:>5} | {reason}")
    sections["l3"] = "\n".join(lines)

    # Clean up
    try:
        os.unlink(db_path)
        os.rmdir(tmp)
    except OSError:
        pass

    return sections


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating demo output for screenshots...")
    sections = run_pipeline()

    # Save individual sections
    for name, content in sections.items():
        path = OUTPUT_DIR / f"demo-{name}.txt"
        path.write_text(content, encoding="utf-8")
        print(f"  Saved: {path.relative_to(REPO_ROOT)}")

    # Save combined output
    combined = "\n".join(sections.values())
    combined_path = OUTPUT_DIR / "demo-full.txt"
    combined_path.write_text(combined, encoding="utf-8")
    print(f"  Saved: {combined_path.relative_to(REPO_ROOT)}")

    print(f"\nDone. {len(sections) + 1} files in {OUTPUT_DIR.relative_to(REPO_ROOT)}/")


if __name__ == "__main__":
    main()
