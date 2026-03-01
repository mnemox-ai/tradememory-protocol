#!/usr/bin/env python3
"""
TradeMemory Protocol — Interactive Demo
========================================
No API key required. Uses simulated XAUUSD trades to demonstrate
the full L1 (record) → L2 (discover patterns) → L3 (strategy adjustment) pipeline.

Usage:
    python demo.py
"""

import sys
import os
import time
import random
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# Force UTF-8 output on Windows (cp950/cp936 can't encode emoji)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Use local imports so demo works from repo root
from src.tradememory.db import Database
from src.tradememory.journal import TradeJournal
from src.tradememory.reflection import ReflectionEngine
from src.tradememory.state import StateManager


# ─────────────────────────────────────────────────────
# Simulated trade data (30 XAUUSD trades over 7 days)
# ─────────────────────────────────────────────────────

SIMULATED_TRADES = [
    # Day 1 - Mixed results
    {"day": 1, "session": "asian",  "strategy": "Pullback",     "direction": "long",  "confidence": 0.60, "pnl": -15.00, "pnl_r": -1.0, "entry": 2845.30, "exit": 2842.30},
    {"day": 1, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.78, "pnl":  42.00, "pnl_r":  2.1, "entry": 2847.00, "exit": 2855.40},
    {"day": 1, "session": "london", "strategy": "VolBreakout",  "direction": "short", "confidence": 0.72, "pnl":  28.50, "pnl_r":  1.5, "entry": 2860.00, "exit": 2854.30},
    {"day": 1, "session": "asian",  "strategy": "Pullback",     "direction": "long",  "confidence": 0.55, "pnl": -20.00, "pnl_r": -1.0, "entry": 2838.50, "exit": 2834.50},
    # Day 2 - London strong, Asian weak
    {"day": 2, "session": "asian",  "strategy": "Pullback",     "direction": "short", "confidence": 0.58, "pnl":  10.00, "pnl_r":  0.5, "entry": 2852.00, "exit": 2850.00},
    {"day": 2, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.82, "pnl":  55.00, "pnl_r":  2.8, "entry": 2855.00, "exit": 2866.00},
    {"day": 2, "session": "london", "strategy": "Pullback",     "direction": "long",  "confidence": 0.70, "pnl":  35.00, "pnl_r":  1.8, "entry": 2862.00, "exit": 2869.00},
    {"day": 2, "session": "newyork","strategy": "VolBreakout",  "direction": "short", "confidence": 0.65, "pnl": -18.00, "pnl_r": -0.9, "entry": 2870.00, "exit": 2873.60},
    {"day": 2, "session": "asian",  "strategy": "Pullback",     "direction": "long",  "confidence": 0.52, "pnl": -22.00, "pnl_r": -1.1, "entry": 2848.00, "exit": 2843.60},
    # Day 3 - Pattern emerging
    {"day": 3, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.85, "pnl":  60.00, "pnl_r":  3.0, "entry": 2870.00, "exit": 2882.00},
    {"day": 3, "session": "asian",  "strategy": "Pullback",     "direction": "short", "confidence": 0.50, "pnl": -12.00, "pnl_r": -0.6, "entry": 2865.00, "exit": 2867.40},
    {"day": 3, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.80, "pnl":  38.00, "pnl_r":  1.9, "entry": 2878.00, "exit": 2885.60},
    {"day": 3, "session": "newyork","strategy": "Pullback",     "direction": "short", "confidence": 0.68, "pnl":  20.00, "pnl_r":  1.0, "entry": 2890.00, "exit": 2886.00},
    {"day": 3, "session": "asian",  "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.48, "pnl": -25.00, "pnl_r": -1.3, "entry": 2862.00, "exit": 2857.00},
    # Day 4 - More data
    {"day": 4, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.88, "pnl":  48.00, "pnl_r":  2.4, "entry": 2885.00, "exit": 2894.60},
    {"day": 4, "session": "london", "strategy": "Pullback",     "direction": "short", "confidence": 0.75, "pnl":  30.00, "pnl_r":  1.5, "entry": 2898.00, "exit": 2892.00},
    {"day": 4, "session": "asian",  "strategy": "Pullback",     "direction": "long",  "confidence": 0.45, "pnl": -18.00, "pnl_r": -0.9, "entry": 2880.00, "exit": 2876.40},
    {"day": 4, "session": "newyork","strategy": "VolBreakout",  "direction": "long",  "confidence": 0.70, "pnl":  22.00, "pnl_r":  1.1, "entry": 2892.00, "exit": 2896.40},
    # Day 5
    {"day": 5, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.90, "pnl":  65.00, "pnl_r":  3.3, "entry": 2895.00, "exit": 2908.00},
    {"day": 5, "session": "asian",  "strategy": "Pullback",     "direction": "short", "confidence": 0.50, "pnl":  -8.00, "pnl_r": -0.4, "entry": 2888.00, "exit": 2889.60},
    {"day": 5, "session": "newyork","strategy": "Pullback",     "direction": "long",  "confidence": 0.62, "pnl":  15.00, "pnl_r":  0.8, "entry": 2905.00, "exit": 2908.00},
    {"day": 5, "session": "london", "strategy": "VolBreakout",  "direction": "short", "confidence": 0.76, "pnl":  32.00, "pnl_r":  1.6, "entry": 2912.00, "exit": 2905.60},
    # Day 6
    {"day": 6, "session": "asian",  "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.42, "pnl": -30.00, "pnl_r": -1.5, "entry": 2900.00, "exit": 2894.00},
    {"day": 6, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.84, "pnl":  52.00, "pnl_r":  2.6, "entry": 2902.00, "exit": 2912.40},
    {"day": 6, "session": "london", "strategy": "Pullback",     "direction": "long",  "confidence": 0.72, "pnl":  25.00, "pnl_r":  1.3, "entry": 2908.00, "exit": 2913.00},
    {"day": 6, "session": "newyork","strategy": "VolBreakout",  "direction": "short", "confidence": 0.60, "pnl": -10.00, "pnl_r": -0.5, "entry": 2915.00, "exit": 2917.00},
    # Day 7
    {"day": 7, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.92, "pnl":  70.00, "pnl_r":  3.5, "entry": 2910.00, "exit": 2924.00},
    {"day": 7, "session": "asian",  "strategy": "Pullback",     "direction": "long",  "confidence": 0.48, "pnl": -16.00, "pnl_r": -0.8, "entry": 2905.00, "exit": 2901.80},
    {"day": 7, "session": "newyork","strategy": "Pullback",     "direction": "short", "confidence": 0.66, "pnl":  18.00, "pnl_r":  0.9, "entry": 2928.00, "exit": 2924.40},
    {"day": 7, "session": "london", "strategy": "Pullback",     "direction": "long",  "confidence": 0.74, "pnl":  28.00, "pnl_r":  1.4, "entry": 2920.00, "exit": 2925.60},
]


def slow_print(text, delay=0.02):
    """Print text with typewriter effect."""
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()


def print_header(text):
    print()
    print("=" * 64)
    slow_print(f"  {text}")
    print("=" * 64)
    print()


def print_step(num, text):
    print(f"\n{'─' * 64}")
    slow_print(f"  Step {num}: {text}")
    print(f"{'─' * 64}\n")


def main():
    # Setup temp database so demo doesn't pollute anything
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "demo.db"
    db = Database(str(db_path))
    journal = TradeJournal(db=db)
    reflection = ReflectionEngine(journal=journal)
    state_mgr = StateManager(db=db)

    print_header("TradeMemory Protocol — Interactive Demo")
    slow_print("  Simulating 30 XAUUSD trades over 7 days.")
    slow_print("  No API key required. All data is simulated.")
    print()
    time.sleep(1)

    # ──────────────────────────────────────────────────
    # STEP 1: L1 — Record trades
    # ──────────────────────────────────────────────────
    print_step(1, "L1 — Recording trades to TradeJournal")
    slow_print("  Every trade decision is stored with full context:")
    slow_print("  reasoning, confidence, market session, and outcome.\n")
    time.sleep(0.5)

    base_time = datetime(2026, 2, 17, 8, 0, 0, tzinfo=timezone.utc)

    for i, trade in enumerate(SIMULATED_TRADES):
        trade_id = f"DEMO-{i+1:03d}"
        day_offset = timedelta(days=trade["day"] - 1, hours=random.randint(0, 8))
        ts = base_time + day_offset

        session_emoji = {"asian": "🌏", "london": "🇬🇧", "newyork": "🇺🇸"}[trade["session"]]
        result_emoji = "🟢" if trade["pnl"] > 0 else "🔴"
        pnl_str = f"+${trade['pnl']:.2f}" if trade["pnl"] > 0 else f"-${abs(trade['pnl']):.2f}"

        # Record decision
        journal.record_decision(
            trade_id=trade_id,
            symbol="XAUUSD",
            direction=trade["direction"],
            lot_size=0.05,
            strategy=trade["strategy"],
            confidence=trade["confidence"],
            reasoning=f"Day {trade['day']} {trade['session']} session - {trade['strategy']} setup",
            market_context={"price": trade["entry"], "session": trade["session"]}
        )

        # Record outcome
        journal.record_outcome(
            trade_id=trade_id,
            exit_price=trade["exit"],
            pnl=trade["pnl"],
            pnl_r=trade["pnl_r"],
            exit_reasoning="Target hit" if trade["pnl"] > 0 else "Stop hit",
            hold_duration=random.randint(15, 180)
        )

        print(f"  {result_emoji} {trade_id}  {session_emoji} {trade['session']:8s}  "
              f"{trade['strategy']:12s}  {trade['direction']:5s}  "
              f"conf: {trade['confidence']:.2f}  {pnl_str:>10s}  ({trade['pnl_r']:+.1f}R)")
        time.sleep(0.05)

    total_pnl = sum(t["pnl"] for t in SIMULATED_TRADES)
    winners = sum(1 for t in SIMULATED_TRADES if t["pnl"] > 0)
    print(f"\n  Total: {len(SIMULATED_TRADES)} trades | "
          f"Winners: {winners} | "
          f"Win rate: {winners/len(SIMULATED_TRADES)*100:.0f}% | "
          f"Net P&L: ${total_pnl:+.2f}")
    time.sleep(1)

    # ──────────────────────────────────────────────────
    # STEP 2: L2 — Discover patterns (mock reflection)
    # ──────────────────────────────────────────────────
    print_step(2, "L2 — Reflection Engine discovers patterns")
    slow_print("  Analyzing all 30 trades for session, strategy, and confidence patterns...\n")
    time.sleep(1)

    # Calculate real patterns from the data
    session_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": []})
    strategy_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "avg_r": []})

    for t in SIMULATED_TRADES:
        s = session_stats[t["session"]]
        s["trades"].append(t)
        s["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            s["wins"] += 1
        else:
            s["losses"] += 1

        st = strategy_stats[t["strategy"]]
        st["avg_r"].append(t["pnl_r"])
        st["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            st["wins"] += 1
        else:
            st["losses"] += 1

    print("  Patterns discovered:\n")
    pattern_num = 1
    patterns_found = []

    for session in ["london", "asian", "newyork"]:
        s = session_stats[session]
        total = s["wins"] + s["losses"]
        wr = s["wins"] / total * 100 if total > 0 else 0
        emoji = {"london": "🇬🇧", "asian": "🌏", "newyork": "🇺🇸"}[session]

        if wr >= 70:
            badge = "HIGH EDGE"
            indicator = "🟢"
        elif wr >= 50:
            badge = "MODERATE"
            indicator = "🟡"
        else:
            badge = "WEAK"
            indicator = "🔴"

        print(f"  {indicator} Pattern {pattern_num}: {emoji} {session.capitalize()} session")
        print(f"     Win rate: {wr:.0f}% ({s['wins']}W / {s['losses']}L, n={total})")
        print(f"     Net P&L: ${s['pnl']:+.2f}")
        print(f"     Assessment: {badge}")
        print()
        patterns_found.append({"session": session, "wr": wr, "badge": badge, "n": total})
        pattern_num += 1
        time.sleep(0.5)

    for strategy in ["VolBreakout", "Pullback"]:
        st = strategy_stats[strategy]
        total = st["wins"] + st["losses"]
        wr = st["wins"] / total * 100 if total > 0 else 0
        avg_r = sum(st["avg_r"]) / len(st["avg_r"]) if st["avg_r"] else 0

        indicator = "🟢" if wr >= 60 else "🟡" if wr >= 50 else "🔴"
        print(f"  {indicator} Pattern {pattern_num}: {strategy} strategy")
        print(f"     Win rate: {wr:.0f}% ({st['wins']}W / {st['losses']}L, n={total})")
        print(f"     Avg R: {avg_r:+.2f} | Net P&L: ${st['pnl']:+.2f}")
        print()
        pattern_num += 1
        time.sleep(0.5)

    # High confidence analysis
    high_conf = [t for t in SIMULATED_TRADES if t["confidence"] >= 0.75]
    low_conf = [t for t in SIMULATED_TRADES if t["confidence"] < 0.55]
    hc_wr = sum(1 for t in high_conf if t["pnl"] > 0) / len(high_conf) * 100 if high_conf else 0
    lc_wr = sum(1 for t in low_conf if t["pnl"] > 0) / len(low_conf) * 100 if low_conf else 0

    print(f"  📊 Pattern {pattern_num}: Confidence correlation")
    print(f"     High confidence (>0.75): {hc_wr:.0f}% win rate (n={len(high_conf)})")
    print(f"     Low confidence  (<0.55): {lc_wr:.0f}% win rate (n={len(low_conf)})")
    print(f"     Insight: High-confidence trades win {hc_wr - lc_wr:.0f}% more often")
    print()
    time.sleep(1)

    # ──────────────────────────────────────────────────
    # STEP 3: L3 — Generate strategy adjustments
    # ──────────────────────────────────────────────────
    print_step(3, "L3 — Strategy adjustments generated")
    slow_print("  Based on discovered patterns, the system recommends:\n")
    time.sleep(0.5)

    adjustments = []

    # Session-based adjustments
    for p in patterns_found:
        if p["wr"] < 50:
            adj = {"param": f"{p['session']}_max_lot", "old": 0.05, "new": 0.025,
                   "reason": f"{p['session'].capitalize()} session win rate {p['wr']:.0f}% — reduce exposure"}
            adjustments.append(adj)
        elif p["wr"] >= 70:
            adj = {"param": f"{p['session']}_max_lot", "old": 0.05, "new": 0.08,
                   "reason": f"{p['session'].capitalize()} session win rate {p['wr']:.0f}% — earned more room"}
            adjustments.append(adj)

    # Confidence-based adjustment
    adjustments.append({
        "param": "min_confidence_threshold",
        "old": 0.40,
        "new": 0.55,
        "reason": f"Trades below 0.55 confidence have {lc_wr:.0f}% win rate — filter them out"
    })

    for i, adj in enumerate(adjustments, 1):
        emoji = "📉" if adj["new"] < adj["old"] else "📈" if adj["new"] > adj["old"] else "📊"
        print(f"  {emoji} Adjustment {i}: {adj['param']}")
        print(f"     {adj['old']} --> {adj['new']}")
        print(f"     Reason: {adj['reason']}")
        print()
        time.sleep(0.5)

    # Save adjustments to state
    state = state_mgr.load_state("demo-agent")
    risk_constraints = {}
    for adj in adjustments:
        risk_constraints[adj["param"]] = adj["new"]
    state_mgr.update_risk_constraints("demo-agent", risk_constraints)

    # Store patterns in warm memory
    for p in patterns_found:
        state_mgr.update_warm_memory(
            "demo-agent",
            f"{p['session']}_win_rate",
            p["wr"]
        )

    # ──────────────────────────────────────────────────
    # STEP 4: Show what the agent sees next session
    # ──────────────────────────────────────────────────
    print_step(4, "Next session — Agent wakes up with memory")
    slow_print("  When the agent starts a new session, it loads its state:\n")
    time.sleep(0.5)

    loaded = state_mgr.load_state("demo-agent")
    print("  Agent state loaded:")
    print(f"    Agent ID:    {loaded.agent_id}")
    print(f"    Last active: {loaded.last_active.strftime('%Y-%m-%d %H:%M UTC')}")
    print()
    print("  Warm memory (learned patterns):")
    for k, v in loaded.warm_memory.items():
        print(f"    {k}: {v:.1f}%" if isinstance(v, float) else f"    {k}: {v}")
    print()
    print("  Risk constraints (auto-adjusted):")
    for k, v in loaded.risk_constraints.items():
        print(f"    {k}: {v}")
    print()
    time.sleep(1)

    # ──────────────────────────────────────────────────
    # STEP 5: Before/After comparison
    # ──────────────────────────────────────────────────
    print_step(5, "Before vs After — The difference memory makes")

    print("  Without TradeMemory          With TradeMemory")
    print("  ─────────────────────        ─────────────────────")
    print('  Trade 1:  AI analyzes         Trade 1:  Same')
    print('            market, gives')
    print('            recommendation')
    print()
    print('  Trade 5:  AI starts fresh,    Trade 5:  "Past 4 Asian trades:')
    print('            no memory of                   3 losses. Reducing')
    print('            past trades                    lot size by 50%."')
    print()
    print('  Trade 15: AI has no idea      Trade 15: "London VolBreakout')
    print('            what its win                   win rate: 73%.')
    print('            rate is                        Going full size."')
    print()
    print('  Trade 30: Same mistakes       Trade 30: Auto-adjusted strategy')
    print('            repeated.                      weights. Avoids low')
    print('            No learning.                   win-rate sessions.')
    print()
    time.sleep(1)

    # ──────────────────────────────────────────────────
    # STEP 6: Production Pipeline (L1 → L2 → L3)
    # ──────────────────────────────────────────────────
    print_step(6, "Production Pipeline — L1 \u2192 L2 \u2192 L3")
    slow_print("  Running the REAL 3-layer pipeline on the demo data:\n")
    time.sleep(0.5)

    # L2: discover patterns from recorded trades
    print("  [L2] Discovering patterns from 30 trades...")
    l2_patterns = reflection.discover_patterns_from_backtest(db=db)
    print(f"       Found {len(l2_patterns)} patterns")
    for p in l2_patterns[:5]:
        print(f"       - {p['pattern_id']}: {p['description'][:70]}...")
    if len(l2_patterns) > 5:
        print(f"       ... and {len(l2_patterns) - 5} more")
    print()
    time.sleep(0.5)

    # L3: generate strategy adjustments from patterns
    print("  [L3] Generating strategy adjustments from patterns...")
    l3_adjustments = reflection.generate_l3_adjustments(db=db)
    print(f"       Generated {len(l3_adjustments)} adjustments")
    for adj in l3_adjustments:
        type_emoji = {
            'strategy_disable': '🚫',
            'strategy_prefer': '⭐',
            'session_reduce': '📉',
            'session_increase': '📈',
            'direction_restrict': '🔒',
        }.get(adj['adjustment_type'], '📊')
        print(f"       {type_emoji} [{adj['adjustment_type']}] "
              f"{adj['parameter']}: {adj['old_value']} \u2192 {adj['new_value']}")
        print(f"          Reason: {adj['reason'][:80]}")
    print()

    # Show stored adjustments
    stored_adj = db.query_adjustments()
    proposed = [a for a in stored_adj if a['status'] == 'proposed']
    print(f"  [{len(proposed)} adjustments stored as 'proposed', awaiting approval]")
    print()
    time.sleep(1)

    # ──────────────────────────────────────────────────
    # Final summary
    # ──────────────────────────────────────────────────
    print_header("Demo complete!")

    asian_wr = session_stats["asian"]["wins"] / (session_stats["asian"]["wins"] + session_stats["asian"]["losses"]) * 100
    london_wr = session_stats["london"]["wins"] / (session_stats["london"]["wins"] + session_stats["london"]["losses"]) * 100

    print(f"  Trades recorded:        {len(SIMULATED_TRADES)}")
    print(f"  L2 patterns discovered: {len(l2_patterns)}")
    print(f"  L3 adjustments:         {len(l3_adjustments)} (rule-based)")
    print(f"  Mock adjustments:       {len(adjustments)} (session-based)")
    print()
    print(f"  Key insight: London session ({london_wr:.0f}% WR) >> Asian session ({asian_wr:.0f}% WR)")
    print(f"  Action taken: Asian lot size reduced 0.05 --> 0.025")
    print()
    print("  ─────────────────────────────────────────────────────")
    print()
    slow_print("  This demo used simulated data and a rule-based engine.")
    slow_print("  Connect a real API key to unlock Claude-powered reflection")
    slow_print("  that analyzes YOUR actual trades with deeper insights.")
    print()
    print("  Next steps:")
    print("    1. cp .env.example .env")
    print("    2. Add your ANTHROPIC_API_KEY to .env")
    print("    3. python -m src.tradememory.server")
    print()
    print("  Docs: https://github.com/mnemox-ai/tradememory-protocol")
    print()


if __name__ == "__main__":
    main()
