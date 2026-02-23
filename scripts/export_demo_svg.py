#!/usr/bin/env python3
"""Export demo output as SVG for README embedding."""

import sys
import os
import time
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tradememory.db import Database
from src.tradememory.journal import TradeJournal
import tempfile

# Recording console — no progress bars (they don't render in SVG)
console = Console(record=True, width=90)

# Same trade data
SIMULATED_TRADES = [
    {"day": 1, "session": "asian",  "strategy": "Pullback",     "direction": "long",  "confidence": 0.60, "pnl": -15.00, "pnl_r": -1.0, "entry": 2845.30, "exit": 2842.30},
    {"day": 1, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.78, "pnl":  42.00, "pnl_r":  2.1, "entry": 2847.00, "exit": 2855.40},
    {"day": 1, "session": "london", "strategy": "VolBreakout",  "direction": "short", "confidence": 0.72, "pnl":  28.50, "pnl_r":  1.5, "entry": 2860.00, "exit": 2854.30},
    {"day": 1, "session": "asian",  "strategy": "Pullback",     "direction": "long",  "confidence": 0.55, "pnl": -20.00, "pnl_r": -1.0, "entry": 2838.50, "exit": 2834.50},
    {"day": 2, "session": "asian",  "strategy": "Pullback",     "direction": "short", "confidence": 0.58, "pnl":  10.00, "pnl_r":  0.5, "entry": 2852.00, "exit": 2850.00},
    {"day": 2, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.82, "pnl":  55.00, "pnl_r":  2.8, "entry": 2855.00, "exit": 2866.00},
    {"day": 2, "session": "london", "strategy": "Pullback",     "direction": "long",  "confidence": 0.70, "pnl":  35.00, "pnl_r":  1.8, "entry": 2862.00, "exit": 2869.00},
    {"day": 2, "session": "newyork","strategy": "VolBreakout",  "direction": "short", "confidence": 0.65, "pnl": -18.00, "pnl_r": -0.9, "entry": 2870.00, "exit": 2873.60},
    {"day": 2, "session": "asian",  "strategy": "Pullback",     "direction": "long",  "confidence": 0.52, "pnl": -22.00, "pnl_r": -1.1, "entry": 2848.00, "exit": 2843.60},
    {"day": 3, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.85, "pnl":  60.00, "pnl_r":  3.0, "entry": 2870.00, "exit": 2882.00},
    {"day": 3, "session": "asian",  "strategy": "Pullback",     "direction": "short", "confidence": 0.50, "pnl": -12.00, "pnl_r": -0.6, "entry": 2865.00, "exit": 2867.40},
    {"day": 3, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.80, "pnl":  38.00, "pnl_r":  1.9, "entry": 2878.00, "exit": 2885.60},
    {"day": 3, "session": "newyork","strategy": "Pullback",     "direction": "short", "confidence": 0.68, "pnl":  20.00, "pnl_r":  1.0, "entry": 2890.00, "exit": 2886.00},
    {"day": 3, "session": "asian",  "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.48, "pnl": -25.00, "pnl_r": -1.3, "entry": 2862.00, "exit": 2857.00},
    {"day": 4, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.88, "pnl":  48.00, "pnl_r":  2.4, "entry": 2885.00, "exit": 2894.60},
    {"day": 4, "session": "london", "strategy": "Pullback",     "direction": "short", "confidence": 0.75, "pnl":  30.00, "pnl_r":  1.5, "entry": 2898.00, "exit": 2892.00},
    {"day": 4, "session": "asian",  "strategy": "Pullback",     "direction": "long",  "confidence": 0.45, "pnl": -18.00, "pnl_r": -0.9, "entry": 2880.00, "exit": 2876.40},
    {"day": 4, "session": "newyork","strategy": "VolBreakout",  "direction": "long",  "confidence": 0.70, "pnl":  22.00, "pnl_r":  1.1, "entry": 2892.00, "exit": 2896.40},
    {"day": 5, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.90, "pnl":  65.00, "pnl_r":  3.3, "entry": 2895.00, "exit": 2908.00},
    {"day": 5, "session": "asian",  "strategy": "Pullback",     "direction": "short", "confidence": 0.50, "pnl":  -8.00, "pnl_r": -0.4, "entry": 2888.00, "exit": 2889.60},
    {"day": 5, "session": "newyork","strategy": "Pullback",     "direction": "long",  "confidence": 0.62, "pnl":  15.00, "pnl_r":  0.8, "entry": 2905.00, "exit": 2908.00},
    {"day": 5, "session": "london", "strategy": "VolBreakout",  "direction": "short", "confidence": 0.76, "pnl":  32.00, "pnl_r":  1.6, "entry": 2912.00, "exit": 2905.60},
    {"day": 6, "session": "asian",  "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.42, "pnl": -30.00, "pnl_r": -1.5, "entry": 2900.00, "exit": 2894.00},
    {"day": 6, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.84, "pnl":  52.00, "pnl_r":  2.6, "entry": 2902.00, "exit": 2912.40},
    {"day": 6, "session": "london", "strategy": "Pullback",     "direction": "long",  "confidence": 0.72, "pnl":  25.00, "pnl_r":  1.3, "entry": 2908.00, "exit": 2913.00},
    {"day": 6, "session": "newyork","strategy": "VolBreakout",  "direction": "short", "confidence": 0.60, "pnl": -10.00, "pnl_r": -0.5, "entry": 2915.00, "exit": 2917.00},
    {"day": 7, "session": "london", "strategy": "VolBreakout",  "direction": "long",  "confidence": 0.92, "pnl":  70.00, "pnl_r":  3.5, "entry": 2910.00, "exit": 2924.00},
    {"day": 7, "session": "asian",  "strategy": "Pullback",     "direction": "long",  "confidence": 0.48, "pnl": -16.00, "pnl_r": -0.8, "entry": 2905.00, "exit": 2901.80},
    {"day": 7, "session": "newyork","strategy": "Pullback",     "direction": "short", "confidence": 0.66, "pnl":  18.00, "pnl_r":  0.9, "entry": 2928.00, "exit": 2924.40},
    {"day": 7, "session": "london", "strategy": "Pullback",     "direction": "long",  "confidence": 0.74, "pnl":  28.00, "pnl_r":  1.4, "entry": 2920.00, "exit": 2925.60},
]

SESSION_STYLE = {
    "asian": ("bold yellow", "Asia  "),
    "london": ("bold cyan", "London"),
    "newyork": ("bold magenta", "NY    "),
}


def main():
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "demo.db"
    db = Database(str(db_path))
    journal = TradeJournal(db=db)

    # Header
    console.print()
    console.print(Panel.fit(
        "[bold white]TradeMemory Protocol[/bold white]\n"
        "[dim]Persistent memory for AI trading agents[/dim]",
        border_style="bright_blue",
        padding=(1, 4),
    ))
    console.print()
    console.print("  Simulating [bold]30 XAUUSD trades[/bold] over 7 days.", style="dim")
    console.print("  No API key required. All data is simulated.", style="dim")
    console.print()

    # Step 1: Record Trades
    console.rule("[bold cyan]Step 1: L1 — Recording trades to TradeJournal[/bold cyan]")
    console.print()

    table = Table(title="Trade Log", box=box.ROUNDED, show_lines=False, title_style="bold white")
    table.add_column("#", style="dim", width=4)
    table.add_column("Result", width=6)
    table.add_column("Session", width=8)
    table.add_column("Strategy", width=12)
    table.add_column("Dir", width=5)
    table.add_column("Conf", width=5, justify="right")
    table.add_column("P&L", width=10, justify="right")
    table.add_column("R", width=6, justify="right")

    base_time = datetime(2026, 2, 17, 8, 0, 0, tzinfo=timezone.utc)

    for i, trade in enumerate(SIMULATED_TRADES):
        trade_id = f"DEMO-{i+1:03d}"
        day_offset = timedelta(days=trade["day"] - 1, hours=random.randint(0, 8))
        ts = base_time + day_offset

        journal.record_decision(
            trade_id=trade_id, symbol="XAUUSD",
            direction=trade["direction"], lot_size=0.05,
            strategy=trade["strategy"], confidence=trade["confidence"],
            reasoning=f"Day {trade['day']} {trade['session']} — {trade['strategy']}",
            market_context={"price": trade["entry"], "session": trade["session"]},
        )
        journal.record_outcome(
            trade_id=trade_id, exit_price=trade["exit"],
            pnl=trade["pnl"], pnl_r=trade["pnl_r"],
            exit_reasoning="Target hit" if trade["pnl"] > 0 else "Stop hit",
            hold_duration=random.randint(15, 180),
        )

        result = "[green]WIN[/green]" if trade["pnl"] > 0 else "[red]LOSS[/red]"
        sess_style, sess_label = SESSION_STYLE[trade["session"]]
        pnl_style = "green" if trade["pnl"] > 0 else "red"
        pnl_str = f"${trade['pnl']:+.2f}"

        table.add_row(
            str(i + 1), result,
            f"[{sess_style}]{sess_label}[/{sess_style}]",
            trade["strategy"], trade["direction"],
            f"{trade['confidence']:.2f}",
            f"[{pnl_style}]{pnl_str}[/{pnl_style}]",
            f"{trade['pnl_r']:+.1f}",
        )

    console.print(table)

    total_pnl = sum(t["pnl"] for t in SIMULATED_TRADES)
    winners = sum(1 for t in SIMULATED_TRADES if t["pnl"] > 0)
    console.print(
        f"\n  [bold]Total:[/bold] {len(SIMULATED_TRADES)} trades | "
        f"Winners: {winners} | "
        f"Win rate: {winners/len(SIMULATED_TRADES)*100:.0f}% | "
        f"Net P&L: [{'green' if total_pnl > 0 else 'red'}]${total_pnl:+.2f}[/]"
    )

    # Step 2: Pattern Discovery
    console.print()
    console.rule("[bold cyan]Step 2: L2 — Reflection Engine discovers patterns[/bold cyan]")
    console.print()

    session_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0})
    strategy_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "avg_r": []})

    for t in SIMULATED_TRADES:
        s = session_stats[t["session"]]
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

    ptable = Table(title="Discovered Patterns", box=box.ROUNDED, title_style="bold white")
    ptable.add_column("Pattern", width=25)
    ptable.add_column("Win Rate", width=10, justify="right")
    ptable.add_column("Record", width=10, justify="center")
    ptable.add_column("Net P&L", width=12, justify="right")
    ptable.add_column("Assessment", width=14)

    for session in ["london", "asian", "newyork"]:
        s = session_stats[session]
        total = s["wins"] + s["losses"]
        wr = s["wins"] / total * 100 if total else 0
        badge = "[bold green]HIGH EDGE[/]" if wr >= 70 else "[yellow]MODERATE[/]" if wr >= 50 else "[bold red]WEAK[/]"
        pnl_style = "green" if s["pnl"] > 0 else "red"
        sess_style, sess_label = SESSION_STYLE[session]
        ptable.add_row(
            f"[{sess_style}]{session.capitalize()} session[/{sess_style}]",
            f"{wr:.0f}%", f"{s['wins']}W / {s['losses']}L",
            f"[{pnl_style}]${s['pnl']:+.2f}[/{pnl_style}]", badge,
        )

    for strategy in ["VolBreakout", "Pullback"]:
        st = strategy_stats[strategy]
        total = st["wins"] + st["losses"]
        wr = st["wins"] / total * 100 if total else 0
        badge = "[bold green]HIGH EDGE[/]" if wr >= 65 else "[yellow]MODERATE[/]" if wr >= 50 else "[bold red]WEAK[/]"
        pnl_style = "green" if st["pnl"] > 0 else "red"
        ptable.add_row(
            f"[bold]{strategy}[/bold] strategy",
            f"{wr:.0f}%", f"{st['wins']}W / {st['losses']}L",
            f"[{pnl_style}]${st['pnl']:+.2f}[/{pnl_style}]", badge,
        )

    console.print(ptable)

    high_conf = [t for t in SIMULATED_TRADES if t["confidence"] >= 0.75]
    low_conf = [t for t in SIMULATED_TRADES if t["confidence"] < 0.55]
    hc_wr = sum(1 for t in high_conf if t["pnl"] > 0) / len(high_conf) * 100 if high_conf else 0
    lc_wr = sum(1 for t in low_conf if t["pnl"] > 0) / len(low_conf) * 100 if low_conf else 0

    console.print(f"\n  [bold]Confidence correlation:[/bold]")
    console.print(f"    High (>0.75): [green]{hc_wr:.0f}%[/green] win rate (n={len(high_conf)})")
    console.print(f"    Low  (<0.55): [red]{lc_wr:.0f}%[/red] win rate (n={len(low_conf)})")
    console.print(f"    Insight: High-confidence trades win [bold]{hc_wr - lc_wr:.0f}%[/bold] more often")

    # Step 3: Strategy Adjustments
    console.print()
    console.rule("[bold cyan]Step 3: L3 — Strategy adjustments generated[/bold cyan]")
    console.print()

    adjustments = []
    for session in ["london", "asian", "newyork"]:
        s = session_stats[session]
        total = s["wins"] + s["losses"]
        wr = s["wins"] / total * 100 if total else 0
        if wr < 50:
            adjustments.append({"param": f"{session}_max_lot", "old": "0.05", "new": "0.025",
                                "reason": f"{session.capitalize()} WR {wr:.0f}% — reduce exposure"})
        elif wr >= 70:
            adjustments.append({"param": f"{session}_max_lot", "old": "0.05", "new": "0.08",
                                "reason": f"{session.capitalize()} WR {wr:.0f}% — earned more room"})

    adjustments.append({"param": "min_confidence_threshold", "old": "0.40", "new": "0.55",
                        "reason": f"Trades below 0.55 have {lc_wr:.0f}% WR — filter out"})

    atable = Table(title="Strategy Adjustments", box=box.ROUNDED, title_style="bold white")
    atable.add_column("#", width=3)
    atable.add_column("Parameter", width=28)
    atable.add_column("Old", width=6, justify="right")
    atable.add_column("", width=3, justify="center")
    atable.add_column("New", width=6, justify="right")
    atable.add_column("Reason", width=32)

    for i, adj in enumerate(adjustments, 1):
        new_style = "green" if float(adj["new"]) > float(adj["old"]) else "red"
        atable.add_row(
            str(i), adj["param"], adj["old"], "->",
            f"[{new_style}]{adj['new']}[/{new_style}]", adj["reason"],
        )

    console.print(atable)

    # Final panel
    console.print()
    london_wr = session_stats["london"]["wins"] / (session_stats["london"]["wins"] + session_stats["london"]["losses"]) * 100
    asian_wr = session_stats["asian"]["wins"] / (session_stats["asian"]["wins"] + session_stats["asian"]["losses"]) * 100

    console.print(Panel.fit(
        f"[bold white]Demo Complete[/bold white]\n\n"
        f"  Trades recorded:      [bold]{len(SIMULATED_TRADES)}[/bold]\n"
        f"  Patterns discovered:  [bold]6[/bold]\n"
        f"  Strategy adjustments: [bold]{len(adjustments)}[/bold]\n\n"
        f"  Key insight: London [green]{london_wr:.0f}% WR[/green] >> Asian [red]{asian_wr:.0f}% WR[/red]\n\n"
        f"  [dim]github.com/mnemox-ai/tradememory-protocol[/dim]",
        border_style="bright_green",
        padding=(1, 3),
    ))
    console.print()

    # Export SVG
    out_path = Path(__file__).parent.parent / "docs" / "demo.svg"
    svg = console.export_svg(title="TradeMemory Protocol — Demo")
    out_path.write_text(svg, encoding="utf-8")
    print(f"SVG exported to: {out_path}")


if __name__ == "__main__":
    main()
