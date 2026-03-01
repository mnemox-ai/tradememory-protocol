"""
Daily Trading Monitor — Option C (AI-Assisted)

Reads tradememory DB + MT5 open positions to detect anomalies.
Generates a daily status report with actionable alerts.

Usage:
    python scripts/daily_monitor.py [--output reports/]

Output: JSON report + human-readable summary
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

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Magic number → strategy name mapping
MAGIC_TO_STRATEGY = {
    0: "Manual",
    260111: "NG_Gold",
    260112: "VolBreakout",
    260113: "IntradayMomentum",
    20260217: "Pullback",
}

DB_PATH = PROJECT_ROOT / "data" / "tradememory.db"

# BATCH-001 backtest baselines (2024.01-2026.02, in-sample)
BACKTEST_BASELINE = {
    "VolBreakout": {
        "avg_pnl_pct": 29.2,
        "win_rate": 0.55,   # Estimated from PF 1.17
        "avg_trades_per_month": 3.5,
        "best_variant": "VB_XAUUSD_BUY_RR4_BUF0.1",
    },
    "IntradayMomentum": {
        "avg_pnl_pct": 47.0,
        "win_rate": 0.58,   # Estimated from PF 2.11
        "avg_trades_per_month": 5.0,
        "best_variant": "IM_XAUUSD_BUY_RR3.5_TH0.45",
    },
    "Pullback": {
        "avg_pnl_pct": 40.9,
        "win_rate": 0.52,   # Estimated from PF
        "avg_trades_per_month": 2.0,
        "best_variant": "PB_XAUUSD_BUY_RR3_PCT0.5",
    },
}


def get_db_trades(days_back=30):
    """Get recent trades from tradememory DB."""
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
    rows = conn.execute(
        "SELECT * FROM trade_records WHERE timestamp >= ? ORDER BY timestamp DESC",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_mt5_open_positions():
    """Get open positions from MT5."""
    try:
        import MetaTrader5 as MT5
    except ImportError:
        return []

    mt5_path = os.getenv("MT5_PATH", "")
    init_kwargs = dict(
        login=int(os.getenv("MT5_LOGIN", "0")),
        password=os.getenv("MT5_PASSWORD", ""),
        server=os.getenv("MT5_SERVER", ""),
        timeout=30000,
    )
    if mt5_path:
        init_kwargs["path"] = mt5_path

    if not MT5.initialize(**init_kwargs):
        return []

    positions = MT5.positions_get()
    account = MT5.account_info()
    balance = account.balance if account else 0
    MT5.shutdown()

    if not positions:
        return []

    result = []
    for p in positions:
        strategy = MAGIC_TO_STRATEGY.get(p.magic, f"Unknown_{p.magic}")
        result.append({
            "ticket": p.ticket,
            "symbol": p.symbol,
            "direction": "LONG" if p.type == 0 else "SHORT",
            "volume": p.volume,
            "open_price": p.price_open,
            "current_price": p.price_current,
            "profit": p.profit,
            "magic": p.magic,
            "strategy": strategy,
            "open_time": datetime.fromtimestamp(p.time).isoformat(),
        })

    return result, balance


def detect_anomalies(trades, open_positions, balance):
    """Detect trading anomalies based on rules."""
    alerts = []

    # Group closed trades by strategy
    strategy_trades = defaultdict(list)
    for t in trades:
        strategy_trades[t["strategy"]].append(t)

    # 1. Consecutive losses per strategy
    for strategy, strades in strategy_trades.items():
        sorted_trades = sorted(strades, key=lambda x: x.get("timestamp", ""))
        consecutive_losses = 0
        for t in reversed(sorted_trades):
            if t.get("pnl") is not None and t["pnl"] < 0:
                consecutive_losses += 1
            else:
                break
        if consecutive_losses >= 3:
            alerts.append({
                "level": "HIGH",
                "type": "consecutive_losses",
                "strategy": strategy,
                "count": consecutive_losses,
                "message": f"{strategy}: {consecutive_losses} consecutive losses",
            })

    # 2. Drawdown check
    total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)
    open_pnl = sum(p.get("profit", 0) for p in open_positions) if open_positions else 0
    if balance > 0:
        dd_pct = abs(min(total_pnl + open_pnl, 0)) / balance * 100
        if dd_pct > 5:
            alerts.append({
                "level": "HIGH",
                "type": "drawdown",
                "value": round(dd_pct, 2),
                "message": f"Account drawdown {dd_pct:.1f}% exceeds 5% threshold",
            })

    # 3. Strategy silence — not traded in X days
    deployed = ["VolBreakout", "IntradayMomentum", "Pullback"]
    for s in deployed:
        strades = strategy_trades.get(s, [])
        if len(strades) == 0:
            alerts.append({
                "level": "MEDIUM",
                "type": "strategy_silent",
                "strategy": s,
                "days": 7,
                "message": f"{s}: ZERO trades in the monitoring period",
            })
        else:
            last_trade_time = max(t.get("timestamp", "") for t in strades)
            if last_trade_time:
                parsed = datetime.fromisoformat(last_trade_time.replace("+00:00", "").replace("Z", ""))
                days_since = (datetime.now() - parsed).days
                if days_since > 5:
                    alerts.append({
                        "level": "MEDIUM",
                        "type": "strategy_silent",
                        "strategy": s,
                        "days": days_since,
                        "message": f"{s}: No trades in {days_since} days",
                    })

    # 4. Win rate drift from backtest baseline
    for strategy, strades in strategy_trades.items():
        if strategy not in BACKTEST_BASELINE:
            continue
        closed = [t for t in strades if t.get("pnl") is not None]
        if len(closed) >= 5:
            wins = sum(1 for t in closed if t["pnl"] > 0)
            real_wr = wins / len(closed)
            expected_wr = BACKTEST_BASELINE[strategy]["win_rate"]
            drift = real_wr - expected_wr
            if drift < -0.15:
                alerts.append({
                    "level": "MEDIUM",
                    "type": "win_rate_drift",
                    "strategy": strategy,
                    "real_wr": round(real_wr, 3),
                    "expected_wr": expected_wr,
                    "drift": round(drift, 3),
                    "sample_size": len(closed),
                    "message": f"{strategy}: WR {real_wr:.0%} vs backtest {expected_wr:.0%} (n={len(closed)})",
                })

    # 5. Large open position risk
    for p in open_positions:
        if balance > 0 and abs(p["profit"]) / balance > 0.03:
            pct = abs(p["profit"]) / balance * 100
            alerts.append({
                "level": "INFO",
                "type": "large_position",
                "strategy": p["strategy"],
                "profit": round(p["profit"], 2),
                "pct_of_balance": round(pct, 1),
                "message": f"{p['strategy']}: Open position PnL ${p['profit']:.2f} ({pct:.1f}% of balance)",
            })

    return alerts


def generate_report(trades, open_positions, balance, alerts):
    """Generate the daily monitoring report."""
    now = datetime.now()

    # Strategy breakdown
    strategy_stats = {}
    for t in trades:
        s = t["strategy"]
        if s not in strategy_stats:
            strategy_stats[s] = {"trades": 0, "wins": 0, "total_pnl": 0}
        strategy_stats[s]["trades"] += 1
        if t.get("pnl") is not None:
            strategy_stats[s]["total_pnl"] += t["pnl"]
            if t["pnl"] > 0:
                strategy_stats[s]["wins"] += 1

    report = {
        "generated_at": now.isoformat(),
        "period_days": 30,
        "account": {
            "balance": round(balance, 2),
            "open_positions": len(open_positions),
            "open_pnl": round(sum(p["profit"] for p in open_positions), 2) if open_positions else 0,
        },
        "strategy_summary": strategy_stats,
        "open_positions": open_positions,
        "alerts": alerts,
        "alert_counts": {
            "HIGH": sum(1 for a in alerts if a["level"] == "HIGH"),
            "MEDIUM": sum(1 for a in alerts if a["level"] == "MEDIUM"),
            "INFO": sum(1 for a in alerts if a["level"] == "INFO"),
        },
    }

    return report


def format_report_text(report):
    """Format report as human-readable text."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  Daily Trading Monitor — {report['generated_at'][:10]}")
    lines.append("=" * 60)

    # Account
    acct = report["account"]
    lines.append(f"\nAccount Balance: ${acct['balance']:,.2f}")
    lines.append(f"Open Positions: {acct['open_positions']} (PnL: ${acct['open_pnl']:,.2f})")

    # Open positions detail
    if report["open_positions"]:
        lines.append("\nOpen Positions:")
        for p in report["open_positions"]:
            lines.append(f"  {p['strategy']:<20} {p['symbol']} {p['direction']} {p['volume']} lots "
                        f"PnL: ${p['profit']:,.2f} (opened {p['open_time'][:10]})")

    # Strategy summary
    lines.append("\nStrategy Performance (last 30 days):")
    lines.append(f"  {'Strategy':<20} {'Trades':>7} {'Wins':>6} {'WR':>6} {'PnL':>12}")
    lines.append(f"  {'-'*20} {'-'*7} {'-'*6} {'-'*6} {'-'*12}")

    deployed = ["VolBreakout", "IntradayMomentum", "Pullback", "Manual", "NG_Gold"]
    for s in deployed:
        if s in report["strategy_summary"]:
            st = report["strategy_summary"][s]
            wr = f"{st['wins']/st['trades']*100:.0f}%" if st["trades"] > 0 else "N/A"
            lines.append(f"  {s:<20} {st['trades']:>7} {st['wins']:>6} {wr:>6} ${st['total_pnl']:>10,.2f}")

    # Alerts
    alerts = report["alerts"]
    ac = report["alert_counts"]
    lines.append(f"\nAlerts: {ac['HIGH']} HIGH / {ac['MEDIUM']} MEDIUM / {ac['INFO']} INFO")

    if alerts:
        for a in sorted(alerts, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "INFO": 2}[x["level"]]):
            icon = {"HIGH": "!!!", "MEDIUM": " ! ", "INFO": " i "}[a["level"]]
            lines.append(f"  [{icon}] {a['message']}")

    # Recommendations
    lines.append("\n" + "-" * 60)
    lines.append("Recommendations:")
    high_alerts = [a for a in alerts if a["level"] == "HIGH"]
    if high_alerts:
        lines.append("  >>> HIGH alerts detected — review before continuing <<<")
    silent = [a for a in alerts if a["type"] == "strategy_silent"]
    if silent:
        for a in silent:
            if a["strategy"] == "IntradayMomentum":
                lines.append(f"  - {a['strategy']}: FIX PositionSelect bug in NG_IntradayMomentum.mqh")
            elif a["strategy"] == "Pullback":
                lines.append(f"  - {a['strategy']}: Consider lowering PB_PullbackPct (0.6→0.5)")
            else:
                lines.append(f"  - {a['strategy']}: Check EA logs for entry conditions")

    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Daily Trading Monitor")
    parser.add_argument("--output", default="reports", help="Output directory")
    parser.add_argument("--days", type=int, default=30, help="Lookback days")
    args = parser.parse_args()

    # Create output dir
    output_dir = PROJECT_ROOT / args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Reading tradememory DB...")
    trades = get_db_trades(days_back=args.days)
    print(f"  Found {len(trades)} trades in last {args.days} days")

    print("Connecting to MT5...")
    mt5_result = get_mt5_open_positions()
    if mt5_result:
        open_positions, balance = mt5_result
        print(f"  Balance: ${balance:,.2f}, Open positions: {len(open_positions)}")
    else:
        open_positions, balance = [], 0
        print("  MT5 not available, using DB only")

    print("Detecting anomalies...")
    alerts = detect_anomalies(trades, open_positions, balance)
    print(f"  Found {len(alerts)} alerts")

    print("Generating report...")
    report = generate_report(trades, open_positions, balance, alerts)

    # Save JSON
    today = datetime.now().strftime("%Y-%m-%d")
    json_path = output_dir / f"daily_{today}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Print & save text
    text = format_report_text(report)
    print()
    print(text)

    txt_path = output_dir / f"daily_{today}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"\nSaved: {json_path}")
    print(f"Saved: {txt_path}")


if __name__ == "__main__":
    main()
