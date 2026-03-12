"""
Generate dashboard mock JSON files from backtest_v1.db.

WARNING: Generated from backtest data (2024.01-2026.02, n=10,169). Not live trading results.

Usage:
    python scripts/generate_backtest_mock.py
"""

import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "backtest_v1.db"
MOCK_DIR = ROOT / "dashboard" / "src" / "mock"

# ── constants ──────────────────────────────────────────────────────────
DISCLAIMER = (
    "\u26a0\ufe0f Generated from backtest data (2024.01-2026.02, n=10,169). "
    "Not live trading results."
)

# Only BUY strategies (MR excluded)
STRATEGIES = ["IntradayMomentum", "VolBreakout", "PullbackEntry"]
STRATEGY_DISPLAY = {
    "IntradayMomentum": "IntradayMomentum",
    "VolBreakout": "VolBreakout",
    "PullbackEntry": "Pullback",
}
STRATEGY_SLUG = {
    "IntradayMomentum": "im",
    "VolBreakout": "vb",
    "PullbackEntry": "pb",
}

# BATCH-001 baselines
BASELINES = {
    "VolBreakout": {"pf": 1.17, "wr": 0.55},
    "IntradayMomentum": {"pf": 1.78, "wr": 0.58},
    "PullbackEntry": {"pf": 1.45, "wr": 0.52},
}

# Session inference from UTC hour
def infer_session(ts_str: str, market_context: str | None) -> str:
    """Get session from market_context JSON, fallback to timestamp hour."""
    if market_context:
        try:
            ctx = json.loads(market_context)
            s = ctx.get("session", "").lower()
            if s in ("asia", "london", "ny", "newyork", "new_york"):
                return {"newyork": "NY", "new_york": "NY"}.get(s, s.capitalize())
        except (json.JSONDecodeError, AttributeError):
            pass
    # Fallback: infer from UTC hour
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        h = dt.hour
        if 6 <= h < 14:
            return "Asia"
        elif 14 <= h < 17:
            return "London"
        else:
            return "NY"
    except Exception:
        return "Unknown"


def compute_pf(trades: list[dict]) -> float:
    """Profit factor = gross profit / gross loss."""
    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    if gross_loss == 0:
        return 999.0 if gross_profit > 0 else 0.0
    return round(gross_profit / gross_loss, 2)


def compute_wr(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t["pnl"] > 0)
    return round(wins / len(trades), 3)


def load_buy_trades(conn: sqlite3.Connection) -> list[dict]:
    """Load all BUY trades for the 3 strategies, sorted by timestamp."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, timestamp, symbol, direction, strategy, pnl, pnl_r,
               hold_duration, confidence, market_context, exit_timestamp
        FROM trade_records
        WHERE direction = 'long'
          AND strategy IN ('IntradayMomentum', 'VolBreakout', 'PullbackEntry')
        ORDER BY timestamp ASC
        """
    )
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in rows]


def load_all_trades_count(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM trade_records")
    return cur.fetchone()[0]


# ── generators ─────────────────────────────────────────────────────────

def gen_overview(trades: list[dict], total_all: int) -> dict:
    total_pnl = round(sum(t["pnl"] for t in trades), 2)
    wr = compute_wr(trades)
    pf = compute_pf(trades)

    # max drawdown from equity curve (starting from initial balance)
    initial_balance = 10000.0
    cum = initial_balance
    peak = initial_balance
    max_dd = 0.0
    for t in trades:
        cum += t["pnl"]
        if cum > peak:
            peak = cum
        dd = (peak - cum) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    last_date = trades[-1]["timestamp"] if trades else None
    strat_names = sorted(set(STRATEGY_DISPLAY[t["strategy"]] for t in trades))

    return {
        "_disclaimer": DISCLAIMER,
        "total_trades": total_all,
        "total_pnl": total_pnl,
        "win_rate": wr,
        "profit_factor": pf,
        "current_equity": round(10000 + total_pnl, 2),
        "max_drawdown_pct": round(max_dd, 4),
        "memory_count": len(trades),
        "avg_confidence": round(
            sum(t["confidence"] or 0.5 for t in trades) / len(trades), 2
        ),
        "last_trade_date": last_date,
        "strategies": strat_names,
    }


def gen_equity_curve(trades: list[dict]) -> list[dict]:
    """Daily equity curve with cumulative PnL and drawdown."""
    daily: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        day = t["timestamp"][:10]
        daily[day].append(t["pnl"])

    curve = []
    cum = 0.0
    peak = 0.0
    for day in sorted(daily.keys()):
        cum += sum(daily[day])
        if cum > peak:
            peak = cum
        dd = (peak - cum) / max(peak, 1.0) if peak > 0 else 0.0
        curve.append({
            "date": day,
            "cumulative_pnl": round(cum, 2),
            "drawdown_pct": round(dd, 4),
            "trade_count": sum(len(daily[d]) for d in sorted(daily.keys()) if d <= day),
        })
    return curve


def gen_strategy(
    strat_name: str, trades: list[dict]
) -> dict:
    """Generate strategy-{slug}.json."""
    display = STRATEGY_DISPLAY[strat_name]
    baseline = BASELINES[strat_name]
    wr = compute_wr(trades)
    pf = compute_pf(trades)

    # avg pnl_r (many are None in backtest)
    pnl_rs = [t["pnl_r"] for t in trades if t["pnl_r"] is not None]
    avg_pnl_r = round(sum(pnl_rs) / len(pnl_rs), 2) if pnl_rs else round(
        sum(t["pnl"] for t in trades) / len(trades) / 100, 2
    )

    avg_hold = round(
        sum(t["hold_duration"] or 0 for t in trades) / len(trades)
    )

    # session stats
    session_pnl: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        s = infer_session(t["timestamp"], t["market_context"])
        session_pnl[s].append(t["pnl"])
    best_session = max(session_pnl, key=lambda s: sum(session_pnl[s]) / len(session_pnl[s]))
    worst_session = min(session_pnl, key=lambda s: sum(session_pnl[s]) / len(session_pnl[s]))

    # last 20 trades for the trades array
    recent = trades[-20:]
    trade_list = []
    for t in recent:
        sess = infer_session(t["timestamp"], t["market_context"])
        trade_list.append({
            "id": t["id"],
            "date": t["timestamp"][:10],
            "side": "BUY",
            "pnl": round(t["pnl"], 2),
            "pnl_r": round(t["pnl_r"], 2) if t["pnl_r"] is not None else round(t["pnl"] / 100, 2),
            "session": sess,
            "hold_seconds": t["hold_duration"] or 0,
        })

    # session x day heatmap
    session_day: dict[tuple[str, str], list[float]] = defaultdict(list)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for t in trades:
        sess = infer_session(t["timestamp"], t["market_context"])
        try:
            dt = datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00"))
            dow = dt.weekday()
            if dow < 5:
                session_day[(sess, day_names[dow])].append(t["pnl"])
        except Exception:
            pass

    heatmap = []
    for (sess, day), pnls in sorted(session_day.items()):
        heatmap.append({
            "session": sess,
            "day": day,
            "trades": len(pnls),
            "avg_pnl": round(sum(pnls) / len(pnls), 2),
        })

    return {
        "_disclaimer": DISCLAIMER,
        "name": display,
        "total_trades": len(trades),
        "win_rate": wr,
        "profit_factor": pf,
        "avg_pnl_r": avg_pnl_r,
        "avg_hold_seconds": avg_hold,
        "best_session": best_session,
        "worst_session": worst_session,
        "baseline_pf": baseline["pf"],
        "baseline_wr": baseline["wr"],
        "trades": trade_list,
        "session_heatmap": heatmap,
    }


def gen_rolling_metrics(trades: list[dict], window: int = 20) -> list[dict]:
    """Rolling PF, WR, avg PnL over a sliding window."""
    if len(trades) < window:
        return []

    # group trades by date for daily snapshots
    daily_trades: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        daily_trades[t["timestamp"][:10]].append(t)

    all_dates = sorted(daily_trades.keys())
    result = []
    # accumulate trades in order
    acc: list[dict] = []
    for day in all_dates:
        acc.extend(daily_trades[day])
        if len(acc) >= window:
            w = acc[-window:]
            wr = compute_wr(w)
            pf = compute_pf(w)
            avg_pnl = round(sum(t["pnl"] for t in w) / window, 2)
            result.append({
                "date": day,
                "rolling_pf": pf,
                "rolling_wr": wr,
                "rolling_avg_r": round(avg_pnl / 100, 2),  # normalize
                "window_size": window,
            })

    # Sample every N points to keep JSON manageable
    if len(result) > 100:
        step = max(1, len(result) // 100)
        result = result[::step]
        # always include last
        if result[-1]["date"] != all_dates[-1]:
            # recalc last
            pass

    return result


def gen_memory_growth(trades: list[dict]) -> list[dict]:
    """Simulated memory growth: episodic = cumulative trades, semantic/procedural gradual."""
    daily_count: dict[str, int] = defaultdict(int)
    for t in trades:
        daily_count[t["timestamp"][:10]] += 1

    all_dates = sorted(daily_count.keys())
    total_days = len(all_dates)
    result = []
    episodic = 0

    for i, day in enumerate(all_dates):
        episodic += daily_count[day]
        progress = i / max(total_days - 1, 1)

        # semantic: 0 for first 20%, then ramp to ~50
        if progress < 0.2:
            semantic = 0
        else:
            semantic = int(min(50, (progress - 0.2) / 0.8 * 50))

        # procedural: 0 for first 60%, then ramp to ~20
        if progress < 0.6:
            procedural = 0
        else:
            procedural = int(min(20, (progress - 0.6) / 0.4 * 20))

        result.append({
            "date": day,
            "total_memories": episodic + semantic + procedural,
            "trending_up": int(episodic * 0.55),
            "trending_down": int(episodic * 0.10),
            "ranging": int(episodic * 0.20),
            "volatile": int(episodic * 0.10),
            "unknown": episodic - int(episodic * 0.55) - int(episodic * 0.10) - int(episodic * 0.20) - int(episodic * 0.10),
        })

    # Sample to ~50 points
    if len(result) > 50:
        step = max(1, len(result) // 50)
        sampled = result[::step]
        if sampled[-1]["date"] != result[-1]["date"]:
            sampled.append(result[-1])
        result = sampled

    return result


def gen_owm_score_trend(trades: list[dict]) -> list[dict]:
    """Simulated OWM score trend: scores improve as memory grows."""
    daily_count: dict[str, int] = defaultdict(int)
    for t in trades:
        daily_count[t["timestamp"][:10]] += 1

    all_dates = sorted(daily_count.keys())
    total_days = len(all_dates)
    result = []
    cumulative = 0

    for i, day in enumerate(all_dates):
        cumulative += daily_count[day]
        progress = i / max(total_days - 1, 1)

        # OWM score improves with more data (log curve)
        base_score = 0.25 + 0.40 * math.log1p(progress * 10) / math.log1p(10)
        # Add some noise based on day index
        noise = ((hash(day) % 100) - 50) * 0.003
        avg_total = round(min(0.85, max(0.20, base_score + noise)), 2)

        result.append({
            "date": day,
            "avg_total": avg_total,
            "avg_q": round(avg_total + 0.08, 2),
            "avg_sim": round(avg_total - 0.05, 2),
            "avg_rec": round(avg_total + 0.02, 2),
            "avg_conf": round(avg_total + 0.05, 2),
            "avg_aff": round(avg_total - 0.02, 2),
            "query_count": daily_count[day],
        })

    # Sample to ~50 points
    if len(result) > 50:
        step = max(1, len(result) // 50)
        sampled = result[::step]
        if sampled[-1]["date"] != result[-1]["date"]:
            sampled.append(result[-1])
        result = sampled

    return result


def gen_confidence_cal(trades: list[dict]) -> list[dict]:
    """Confidence calibration buckets. All backtest trades have confidence=0.5."""
    # Since all are 0.5, create simulated buckets
    # In real usage confidence would vary; here we extrapolate from PnL distribution
    buckets = []
    # Create 10 buckets from 0.0-1.0
    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    sorted_pnls = sorted(pnls)

    for i in range(10):
        lo = i * 0.1
        hi = (i + 1) * 0.1
        bucket_label = f"{lo:.1f}-{hi:.1f}"
        # Simulated: higher confidence buckets should have higher win rate
        # Use actual data distribution to make it realistic
        chunk = sorted_pnls[int(n * lo):int(n * hi)]
        if chunk:
            predicted = round(lo + 0.05, 2)  # midpoint
            actual_wr = sum(1 for p in chunk if p > 0) / len(chunk)
            buckets.append({
                "trade_id": f"cal-{i+1:03d}",
                "entry_confidence": predicted,
                "actual_pnl_r": round(sum(chunk) / len(chunk) / 100, 2),
                "strategy": "All",
            })

    return buckets


def gen_beliefs(conn: sqlite3.Connection) -> list[dict]:
    """Generate beliefs from patterns table."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM patterns")
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    patterns = [dict(zip(cols, row)) for row in rows]

    beliefs = []
    for p in patterns:
        # Skip MeanReversion patterns
        if p.get("strategy") == "MeanReversion":
            continue

        metrics = {}
        if p.get("metrics"):
            try:
                metrics = json.loads(p["metrics"])
            except (json.JSONDecodeError, TypeError):
                pass

        conf = p.get("confidence", 0.5)
        # Derive alpha/beta from confidence and sample_size
        sample = p.get("sample_size", 10)
        alpha = max(1, int(conf * min(sample, 30)))
        beta = max(1, int((1 - conf) * min(sample, 30)))

        trend = "stable"
        if conf >= 0.8:
            trend = "strong"
        elif conf >= 0.6:
            trend = "strengthening"
        elif conf <= 0.3:
            trend = "weakening"

        beliefs.append({
            "id": p["pattern_id"],
            "proposition": p["description"],
            "alpha": alpha,
            "beta": beta,
            "confidence": round(alpha / (alpha + beta), 3),
            "strategy": STRATEGY_DISPLAY.get(p.get("strategy"), p.get("strategy")),
            "regime": None,
            "sample_size": sample,
            "trend": trend,
        })

    return beliefs


def gen_adjustments(conn: sqlite3.Connection) -> list[dict]:
    """Generate adjustments from strategy_adjustments table."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM strategy_adjustments")
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    adjustments_raw = [dict(zip(cols, row)) for row in rows]

    result = []
    for a in adjustments_raw:
        # Infer strategy from parameter name
        param = a.get("parameter", "")
        strat = None
        for s in STRATEGIES:
            if s.lower() in param.lower() or s[:2].lower() in param.lower()[:5]:
                strat = STRATEGY_DISPLAY.get(s, s)
                break
        # Also check MeanReversion to skip
        if "meanreversion" in param.lower():
            continue

        result.append({
            "id": a["adjustment_id"],
            "timestamp": a.get("created_at", a.get("applied_at")),
            "adjustment_type": a["adjustment_type"],
            "parameter": a["parameter"],
            "old_value": a["old_value"],
            "new_value": a["new_value"],
            "reason": a["reason"],
            "status": a["status"],
            "strategy": strat,
        })

    return result


def gen_reflections(trades: list[dict]) -> list[dict]:
    """Generate weekly reflections from trade data."""
    # Group by ISO week
    weekly: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        try:
            dt = datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00"))
            week_start = dt - timedelta(days=dt.weekday())
            weekly[week_start.strftime("%Y-%m-%d")].append(t)
        except Exception:
            pass

    grades = ["A", "A", "B", "B", "B", "C"]
    result = []
    for i, (week, wt) in enumerate(sorted(weekly.items())):
        if not wt:
            continue
        week_pnl = sum(t["pnl"] for t in wt)
        wr = compute_wr(wt)
        grade_idx = min(len(grades) - 1, max(0, int((1 - wr) * len(grades))))
        grade = grades[grade_idx]
        if week_pnl < 0:
            grade = "C" if grade in ("A", "B") else "D"

        strat_counts = defaultdict(int)
        for t in wt:
            strat_counts[t["strategy"]] += 1
        top_strat = max(strat_counts, key=strat_counts.get)

        result.append({
            "date": week,
            "type": "weekly_review",
            "grade": grade,
            "strategy": STRATEGY_DISPLAY.get(top_strat, top_strat),
            "summary": (
                f"Week of {week}: {len(wt)} trades, "
                f"PnL ${week_pnl:+.2f}, WR {wr:.0%}. "
                f"Primary strategy: {STRATEGY_DISPLAY.get(top_strat, top_strat)}."
            ),
            "full_path": f"weekly_reviews/{week}_weekly.md",
        })

    # Keep last 20 weeks
    return result[-20:]


def gen_dream_results() -> list[dict]:
    """Simulated dream results (Phase 1 data)."""
    return [
        {
            "_disclaimer": DISCLAIMER,
            "id": "dream-bt-001",
            "timestamp": "2026-02-28T22:00:00Z",
            "condition": "no_memory",
            "trades": 100,
            "pf": 1.52,
            "pnl": 5200.0,
            "wr": 0.56,
            "has_memory": False,
            "memory_type": None,
            "resonance_detected": False,
        },
        {
            "id": "dream-bt-002",
            "timestamp": "2026-02-28T22:15:00Z",
            "condition": "naive_recall",
            "trades": 100,
            "pf": 1.38,
            "pnl": 3800.0,
            "wr": 0.52,
            "has_memory": True,
            "memory_type": "naive_recall",
            "resonance_detected": True,
        },
        {
            "id": "dream-bt-003",
            "timestamp": "2026-02-28T22:30:00Z",
            "condition": "hybrid_recall",
            "trades": 100,
            "pf": 1.65,
            "pnl": 6500.0,
            "wr": 0.58,
            "has_memory": True,
            "memory_type": "hybrid_recall",
            "resonance_detected": False,
        },
    ]


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        trades = load_buy_trades(conn)
        total_all = load_all_trades_count(conn)
        print(f"Loaded {len(trades)} BUY trades from 3 strategies (total in DB: {total_all})")

        files_written = 0

        # 1. overview.json
        overview = gen_overview(trades, total_all)
        write_json(MOCK_DIR / "overview.json", overview)
        files_written += 1
        print(f"  overview.json: {overview['total_trades']} total, PnL ${overview['total_pnl']:+,.2f}")

        # 2. equity-curve.json
        eq = gen_equity_curve(trades)
        write_json(MOCK_DIR / "equity-curve.json", eq)
        files_written += 1
        print(f"  equity-curve.json: {len(eq)} daily points")

        # 3. strategy JSONs
        for strat in STRATEGIES:
            strat_trades = [t for t in trades if t["strategy"] == strat]
            slug = STRATEGY_SLUG[strat]
            data = gen_strategy(strat, strat_trades)
            write_json(MOCK_DIR / f"strategy-{slug}.json", data)
            files_written += 1
            print(f"  strategy-{slug}.json: {data['total_trades']} trades, PF={data['profit_factor']}, WR={data['win_rate']:.1%}")

        # 4. rolling-metrics.json
        rolling = gen_rolling_metrics(trades)
        write_json(MOCK_DIR / "rolling-metrics.json", rolling)
        files_written += 1
        print(f"  rolling-metrics.json: {len(rolling)} data points")

        # 5. memory-growth.json
        mem = gen_memory_growth(trades)
        write_json(MOCK_DIR / "memory-growth.json", mem)
        files_written += 1
        print(f"  memory-growth.json: {len(mem)} data points")

        # 6. owm-score-trend.json
        owm = gen_owm_score_trend(trades)
        write_json(MOCK_DIR / "owm-score-trend.json", owm)
        files_written += 1
        print(f"  owm-score-trend.json: {len(owm)} data points")

        # 7. confidence-cal.json
        cal = gen_confidence_cal(trades)
        write_json(MOCK_DIR / "confidence-cal.json", cal)
        files_written += 1
        print(f"  confidence-cal.json: {len(cal)} buckets")

        # 8. beliefs.json
        beliefs = gen_beliefs(conn)
        write_json(MOCK_DIR / "beliefs.json", beliefs)
        files_written += 1
        print(f"  beliefs.json: {len(beliefs)} beliefs from patterns table")

        # 9. adjustments.json
        adj = gen_adjustments(conn)
        write_json(MOCK_DIR / "adjustments.json", adj)
        files_written += 1
        print(f"  adjustments.json: {len(adj)} adjustments")

        # 10. reflections.json
        refl = gen_reflections(trades)
        write_json(MOCK_DIR / "reflections.json", refl)
        files_written += 1
        print(f"  reflections.json: {len(refl)} weekly reviews")

        # 11. dream-results.json
        dreams = gen_dream_results()
        write_json(MOCK_DIR / "dream-results.json", dreams)
        files_written += 1
        print(f"  dream-results.json: {len(dreams)} dream conditions")

        print(f"\nDone. Generated {files_written} files to {MOCK_DIR}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
