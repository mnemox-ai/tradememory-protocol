"""
Weekly Trading Report — Option C (AI-Assisted)

Generates a comprehensive weekly performance report comparing
real trades vs BATCH-001 backtest baselines.

Usage:
    python scripts/weekly_report.py [--output reports/]
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / "data" / "tradememory.db"
BACKTEST_DB = PROJECT_ROOT / "data" / "backtest_v1.db"

# BATCH-001 baselines
BACKTEST_BASELINE = {
    "VolBreakout": {
        "avg_pnl_pct": 29.2,
        "profit_rate": 1.0,  # 16/16 profitable
        "avg_pf": 1.17,
        "best_pf": 1.36,
        "avg_wr": 0.55,
    },
    "IntradayMomentum": {
        "avg_pnl_pct": 47.0,
        "profit_rate": 0.94,  # 34/36
        "avg_pf": 1.78,
        "best_pf": 2.11,
        "avg_wr": 0.58,
    },
    "Pullback": {
        "avg_pnl_pct": 40.9,
        "profit_rate": 1.0,  # 9/9
        "avg_pf": 1.45,
        "best_pf": 1.62,
        "avg_wr": 0.52,
    },
}


def get_trades_since(since_date):
    """Get all trades from DB since a given date."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM trade_records WHERE timestamp >= ? ORDER BY timestamp",
        (since_date.isoformat(),),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_backtest_stats(strategy, symbol="XAUUSD"):
    """Get backtest stats for comparison."""
    if not BACKTEST_DB.exists():
        return None
    conn = sqlite3.connect(str(BACKTEST_DB))
    conn.row_factory = sqlite3.Row

    # Attempt to query — backtest DB schema may differ
    try:
        rows = conn.execute(
            "SELECT * FROM trade_records WHERE strategy LIKE ? AND symbol = ?",
            (f"%{strategy}%", symbol),
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return None

    conn.close()
    if not rows:
        return None

    trades = [dict(r) for r in rows]
    total = len(trades)
    wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
    total_pnl = sum(t.get("pnl") or 0 for t in trades)

    return {
        "total_trades": total,
        "wins": wins,
        "win_rate": wins / total if total > 0 else 0,
        "total_pnl": total_pnl,
    }


def compute_strategy_metrics(trades):
    """Compute per-strategy metrics from trade list."""
    by_strategy = defaultdict(list)
    for t in trades:
        by_strategy[t["strategy"]].append(t)

    metrics = {}
    for strategy, strades in by_strategy.items():
        closed = [t for t in strades if t.get("pnl") is not None]
        total = len(closed)
        wins = sum(1 for t in closed if t["pnl"] > 0)
        losses = sum(1 for t in closed if t["pnl"] <= 0)
        total_pnl = sum(t["pnl"] for t in closed)
        gross_profit = sum(t["pnl"] for t in closed if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in closed if t["pnl"] <= 0))

        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0
        avg_win = gross_profit / wins if wins > 0 else 0
        avg_loss = gross_loss / losses if losses > 0 else 0

        metrics[strategy] = {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / total if total > 0 else 0,
            "total_pnl": round(total_pnl, 2),
            "profit_factor": round(pf, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "expectancy": round(total_pnl / total, 2) if total > 0 else 0,
        }

    return metrics


def generate_weekly_text(since_date, metrics, all_trades):
    """Generate weekly report text."""
    lines = []
    lines.append("=" * 65)
    lines.append(f"  Weekly Trading Report")
    lines.append(f"  Period: {since_date.strftime('%Y-%m-%d')} → {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("=" * 65)

    # Overall
    all_closed = [t for t in all_trades if t.get("pnl") is not None]
    total_pnl = sum(t["pnl"] for t in all_closed)
    total_trades = len(all_closed)
    lines.append(f"\nOverall: {total_trades} trades, PnL: ${total_pnl:,.2f}")

    # Per strategy with backtest comparison
    lines.append(f"\n{'Strategy':<20} {'Trades':>7} {'WR':>7} {'PF':>7} {'PnL':>10} {'vs Backtest':>15}")
    lines.append(f"{'-'*20} {'-'*7} {'-'*7} {'-'*7} {'-'*10} {'-'*15}")

    deployed = ["VolBreakout", "IntradayMomentum", "Pullback"]
    for s in deployed:
        if s in metrics:
            m = metrics[s]
            wr_str = f"{m['win_rate']*100:.0f}%"
            pf_str = f"{m['profit_factor']:.2f}"

            # Compare to backtest
            baseline = BACKTEST_BASELINE.get(s, {})
            bt_wr = baseline.get("avg_wr", 0)
            drift = ""
            if m["total_trades"] >= 5 and bt_wr > 0:
                wr_diff = m["win_rate"] - bt_wr
                if wr_diff < -0.10:
                    drift = f"WR -{abs(wr_diff)*100:.0f}%"
                elif wr_diff > 0.10:
                    drift = f"WR +{wr_diff*100:.0f}%"
                else:
                    drift = "On track"
            elif m["total_trades"] == 0:
                drift = "NO TRADES"
            else:
                drift = f"n={m['total_trades']} (low)"

            lines.append(f"{s:<20} {m['total_trades']:>7} {wr_str:>7} {pf_str:>7} ${m['total_pnl']:>8,.2f} {drift:>15}")
        else:
            lines.append(f"{s:<20} {'0':>7} {'N/A':>7} {'N/A':>7} {'$0.00':>10} {'NO TRADES':>15}")

    # Other strategies
    for s, m in metrics.items():
        if s not in deployed:
            wr_str = f"{m['win_rate']*100:.0f}%"
            lines.append(f"{s:<20} {m['total_trades']:>7} {wr_str:>7} {m['profit_factor']:>7.2f} ${m['total_pnl']:>8,.2f} {'(not tracked)':>15}")

    # Known issues
    lines.append("\n" + "-" * 65)
    lines.append("Known Issues:")
    if "IntradayMomentum" not in metrics or metrics.get("IntradayMomentum", {}).get("total_trades", 0) == 0:
        lines.append("  [BUG] IntradayMomentum: PositionSelect blocks when VB has open position")
        lines.append("        Fix: Replace PositionSelect(_Symbol) with HasOpenPositionByMagic()")
    if "Pullback" not in metrics or metrics.get("Pullback", {}).get("total_trades", 0) == 0:
        lines.append("  [TUNE] Pullback: Breakout detected but pullback level not reached")
        lines.append("         Fix: Lower PB_PullbackPct from 0.6 to 0.5")

    # Next actions
    lines.append("\nNext Actions:")
    lines.append("  1. Fix IM PositionSelect bug (requires .mqh edit + recompile)")
    lines.append("  2. Lower PB threshold (requires .set file update)")
    lines.append("  3. OOS backtest 2022-2023 to validate BATCH-001 results")
    lines.append("  4. After fixes: monitor for 1 week before go-live")

    lines.append("=" * 65)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Weekly Trading Report")
    parser.add_argument("--output", default="reports", help="Output directory")
    parser.add_argument("--weeks", type=int, default=1, help="Lookback weeks")
    args = parser.parse_args()

    output_dir = PROJECT_ROOT / args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    since_date = datetime.now() - timedelta(weeks=args.weeks)
    print(f"Generating weekly report since {since_date.strftime('%Y-%m-%d')}...")

    trades = get_trades_since(since_date)
    print(f"  Found {len(trades)} trades")

    metrics = compute_strategy_metrics(trades)

    # Generate text report
    text = generate_weekly_text(since_date, metrics, trades)
    print()
    print(text)

    # Save
    today = datetime.now().strftime("%Y-%m-%d")
    txt_path = output_dir / f"weekly_{today}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    json_path = output_dir / f"weekly_{today}.json"
    report_data = {
        "generated_at": datetime.now().isoformat(),
        "period_start": since_date.isoformat(),
        "strategy_metrics": metrics,
        "total_trades": len(trades),
        "backtest_baselines": BACKTEST_BASELINE,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"\nSaved: {txt_path}")
    print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()
