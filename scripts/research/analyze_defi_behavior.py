#!/usr/bin/env python3
"""Analyze DeFi behavior fingerprint from whale wallet trade CSV.

Dimensions:
1. Fund flow: Aave deposit/withdraw timing, amount distribution
2. Token preference shifts: stablecoin ↔ yield ↔ LST transitions
3. Operational tempo: burst vs steady, daily tx histogram
4. Time/day-of-week preference: session heatmap
5. Gas sensitivity: activity vs gas cost correlation

Data source: CSV from fetch_whale_trades.py (Etherscan V2 API).

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/research/analyze_defi_behavior.py data/whale_0xb99a2c_trades.csv
    python scripts/research/analyze_defi_behavior.py data/whale_0xb99a2c_trades.csv --output scripts/research/output/abraxas_fingerprint.json
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, stdev

# --- Token classification ---

STABLECOINS = {
    "USDT", "USDC", "DAI", "BUSD", "TUSD", "FRAX", "LUSD", "GUSD",
    "USDP", "PYUSD", "FDUSD", "DOLA", "crvUSD", "GHO", "sUSD",
    "USDS", "sUSDS",
}
LST_TOKENS = {"wstETH", "stETH", "eETH", "rETH", "cbETH", "weETH", "rsETH"}
AAVE_TOKENS = {
    "aEthWETH", "aEthUSDT", "aEthUSDC", "aEthDAI", "aEthLBTC",
    "AWETH", "AWSTETH", "aEthwstETH", "aEthweETH", "aEthcbBTC",
    "aEthsUSDe",
}
FARMING_LP = {
    "farmdUSDCV3", "farmdDAIV3", "farmdUSDTV3", "farmdWETHV3",
    "cDAI", "cUSDC", "cUSDTv3", "yvUSDC", "yvDAI",
}
GOVERNANCE = {"AAVE", "COMP", "CRV", "MKR", "LDO", "RPL", "SKY", "EIGEN"}
WRAPPED_BTC = {"WBTC", "LBTC", "cbBTC", "tBTC", "aBTC", "eBTC"}
ETHENA = {"USDe", "sUSDe", "ENA"}
SPARK_TOKENS = {"spWETH", "spwstETH", "spcbBTC", "spweETH"}
WRAPPED_ETH = {"WETH", "ETH"}

SESSION_RANGES = {
    "Asia (00-08 UTC)": (0, 8),
    "London (08-13 UTC)": (8, 13),
    "New York (13-21 UTC)": (13, 21),
    "Off-hours (21-24 UTC)": (21, 24),
}

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def classify_token(symbol: str) -> str:
    """Classify a token into a category."""
    if symbol in STABLECOINS:
        return "stablecoin"
    if symbol in LST_TOKENS:
        return "LST"
    if symbol in AAVE_TOKENS:
        return "aave"
    if symbol in FARMING_LP:
        return "farming_lp"
    if symbol in GOVERNANCE:
        return "governance"
    if symbol in WRAPPED_BTC:
        return "wrapped_btc"
    if symbol in ETHENA:
        return "ethena"
    if symbol in SPARK_TOKENS:
        return "spark"
    if symbol in WRAPPED_ETH:
        return "ETH"
    # Pendle prefix matching: PT-* and YT-* tokens
    if symbol.startswith("PT-") or symbol.startswith("YT-"):
        return "pendle"
    # Spark stablecoin wrappers: S*USDT, S*USDC, etc.
    if symbol.startswith("S*"):
        return "spark"
    return "other"


def load_trades(csv_path: str) -> list[dict]:
    """Load trades from whale CSV."""
    trades = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts = datetime.strptime(row["open_time"], "%Y-%m-%d %H:%M:%S")
                ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, KeyError):
                continue

            # Parse tokens_sold and tokens_bought
            sold_raw = row.get("tokens_sold", "")
            bought_raw = row.get("tokens_bought", "")
            sold_token = sold_raw.split(":")[0] if ":" in sold_raw else ""
            bought_token = bought_raw.split(":")[0] if ":" in bought_raw else ""
            sold_amount = float(sold_raw.split(":")[1]) if ":" in sold_raw else 0
            bought_amount = float(bought_raw.split(":")[1]) if ":" in bought_raw else 0

            trades.append({
                "timestamp": ts,
                "symbol": row.get("symbol", ""),
                "side": row.get("side", ""),
                "volume": float(row.get("volume", 0)),
                "gas_cost_eth": float(row.get("gas_cost_eth", 0)),
                "tx_hash": row.get("tx_hash", ""),
                "sold_token": sold_token,
                "bought_token": bought_token,
                "sold_amount": sold_amount,
                "bought_amount": bought_amount,
                "sold_category": classify_token(sold_token),
                "bought_category": classify_token(bought_token),
            })
    return trades


# =============================================================================
# Dimension 1: Fund Flow (Aave deposit/withdraw timing & amounts)
# =============================================================================

def analyze_fund_flow(trades: list[dict]) -> dict:
    """Analyze Aave deposit/withdraw patterns."""
    aave_txs = []
    for t in trades:
        is_deposit = t["bought_category"] == "aave"
        is_withdraw = t["sold_category"] == "aave"
        if is_deposit or is_withdraw:
            action = "deposit" if is_deposit else "withdraw"
            # Estimate USD value from the non-aave side
            if is_deposit:
                usd_est = t["sold_amount"]
                source_token = t["sold_token"]
            else:
                usd_est = t["bought_amount"]
                source_token = t["bought_token"]

            aave_txs.append({
                "timestamp": t["timestamp"].isoformat(),
                "action": action,
                "token": t["bought_token"] if is_deposit else t["sold_token"],
                "source_token": source_token,
                "amount_raw": t["sold_amount"] if is_deposit else t["bought_amount"],
                "usd_estimate": usd_est,
                "hour": t["timestamp"].hour,
                "weekday": t["timestamp"].weekday(),
            })

    if not aave_txs:
        return {"total_aave_txs": 0, "deposits": 0, "withdrawals": 0}

    deposits = [tx for tx in aave_txs if tx["action"] == "deposit"]
    withdrawals = [tx for tx in aave_txs if tx["action"] == "withdraw"]
    deposit_amounts = [tx["usd_estimate"] for tx in deposits]
    withdraw_amounts = [tx["usd_estimate"] for tx in withdrawals]

    return {
        "total_aave_txs": len(aave_txs),
        "deposits": len(deposits),
        "withdrawals": len(withdrawals),
        "deposit_amount_stats": _amount_stats(deposit_amounts) if deposit_amounts else {},
        "withdraw_amount_stats": _amount_stats(withdraw_amounts) if withdraw_amounts else {},
        "deposit_tokens": dict(Counter(tx["token"] for tx in deposits).most_common()),
        "withdraw_tokens": dict(Counter(tx["token"] for tx in withdrawals).most_common()),
        "sample_timeline": aave_txs[:10],
    }


def _amount_stats(amounts: list[float]) -> dict:
    """Compute basic stats for a list of amounts."""
    if not amounts:
        return {}
    result = {
        "count": len(amounts),
        "total": round(sum(amounts), 2),
        "mean": round(mean(amounts), 2),
        "median": round(median(amounts), 2),
        "min": round(min(amounts), 2),
        "max": round(max(amounts), 2),
    }
    if len(amounts) > 1:
        result["stdev"] = round(stdev(amounts), 2)
    return result


# =============================================================================
# Dimension 2: Token Preference Shifts
# =============================================================================

def analyze_token_shifts(trades: list[dict]) -> dict:
    """Analyze token preference transitions over time."""
    # Monthly breakdown of category flows
    monthly_flows: dict[str, Counter] = defaultdict(Counter)
    transition_pairs = Counter()

    for t in trades:
        month_key = t["timestamp"].strftime("%Y-%m")
        flow_key = f"{t['sold_category']}→{t['bought_category']}"
        monthly_flows[month_key][flow_key] += 1
        transition_pairs[flow_key] += 1

    # Token-level counts
    sold_tokens = Counter(t["sold_token"] for t in trades)
    bought_tokens = Counter(t["bought_token"] for t in trades)

    return {
        "top_transitions": dict(transition_pairs.most_common(15)),
        "top_sold_tokens": dict(sold_tokens.most_common(15)),
        "top_bought_tokens": dict(bought_tokens.most_common(15)),
        "monthly_flow_summary": {
            month: dict(flows.most_common(5))
            for month, flows in sorted(monthly_flows.items())
        },
    }


# =============================================================================
# Dimension 3: Operational Tempo (burst vs steady)
# =============================================================================

def analyze_tempo(trades: list[dict]) -> dict:
    """Analyze operational rhythm: burst vs steady patterns."""
    if not trades:
        return {}

    # Daily transaction counts
    daily_counts: Counter = Counter()
    for t in trades:
        day_key = t["timestamp"].strftime("%Y-%m-%d")
        daily_counts[day_key] += 1

    counts = list(daily_counts.values())
    total_days = len(daily_counts)

    # Histogram buckets
    histogram = {
        "1-5 txs": 0,
        "6-10 txs": 0,
        "11-20 txs": 0,
        "21-50 txs": 0,
        "50+ txs": 0,
    }
    for c in counts:
        if c <= 5:
            histogram["1-5 txs"] += 1
        elif c <= 10:
            histogram["6-10 txs"] += 1
        elif c <= 20:
            histogram["11-20 txs"] += 1
        elif c <= 50:
            histogram["21-50 txs"] += 1
        else:
            histogram["50+ txs"] += 1

    # Burst detection: days with > 2x median
    median_daily = median(counts) if counts else 0
    burst_threshold = max(median_daily * 2, 10)
    burst_days = [
        {"date": day, "txs": count}
        for day, count in daily_counts.most_common()
        if count >= burst_threshold
    ]

    # Inactive gaps (consecutive days with 0 txs)
    all_dates = sorted(daily_counts.keys())
    gaps = []
    if len(all_dates) >= 2:
        for i in range(1, len(all_dates)):
            d1 = datetime.strptime(all_dates[i - 1], "%Y-%m-%d")
            d2 = datetime.strptime(all_dates[i], "%Y-%m-%d")
            gap_days = (d2 - d1).days - 1
            if gap_days >= 7:
                gaps.append({
                    "from": all_dates[i - 1],
                    "to": all_dates[i],
                    "gap_days": gap_days,
                })

    return {
        "total_active_days": total_days,
        "total_txs": len(trades),
        "txs_per_active_day": {
            "mean": round(mean(counts), 1) if counts else 0,
            "median": round(median(counts), 1) if counts else 0,
            "max": max(counts) if counts else 0,
            "stdev": round(stdev(counts), 1) if len(counts) > 1 else 0,
        },
        "daily_histogram": histogram,
        "burst_days_count": len(burst_days),
        "burst_threshold": burst_threshold,
        "top_burst_days": burst_days[:10],
        "inactive_gaps_7d_plus": gaps,
    }


# =============================================================================
# Dimension 4: Time & Day-of-Week Preference
# =============================================================================

def analyze_time_preference(trades: list[dict]) -> dict:
    """Analyze session and day-of-week preferences."""
    if not trades:
        return {}

    hours = Counter(t["timestamp"].hour for t in trades)
    weekdays = Counter(t["timestamp"].weekday() for t in trades)
    total = len(trades)

    # Session breakdown
    session_counts = {}
    for name, (start, end) in SESSION_RANGES.items():
        count = sum(hours.get(h, 0) for h in range(start, end))
        session_counts[name] = {
            "count": count,
            "pct": round(count / total * 100, 1),
        }

    # Day of week
    dow_data = {}
    for i in range(7):
        count = weekdays.get(i, 0)
        dow_data[DAY_NAMES[i]] = {
            "count": count,
            "pct": round(count / total * 100, 1),
        }

    # Hour histogram (text-based)
    hour_histogram = {}
    for h in range(24):
        count = hours.get(h, 0)
        hour_histogram[f"{h:02d}:00"] = {
            "count": count,
            "pct": round(count / total * 100, 1),
            "bar": "█" * max(1, int(count / total * 200)),
        }

    return {
        "session_breakdown": session_counts,
        "day_of_week": dow_data,
        "hour_histogram": hour_histogram,
        "peak_hour_utc": max(hours, key=hours.get),
        "peak_day": DAY_NAMES[max(weekdays, key=weekdays.get)],
    }


# =============================================================================
# Dimension 5: Gas Sensitivity
# =============================================================================

def analyze_gas_sensitivity(trades: list[dict]) -> dict:
    """Analyze whether high gas periods reduce activity."""
    if not trades:
        return {}

    gas_costs = [t["gas_cost_eth"] for t in trades if t["gas_cost_eth"] > 0]
    if not gas_costs:
        return {"note": "No gas data available"}

    # Quartile-based analysis
    sorted_gas = sorted(gas_costs)
    n = len(sorted_gas)
    q1 = sorted_gas[n // 4]
    q2 = sorted_gas[n // 2]
    q3 = sorted_gas[3 * n // 4]

    # Daily gas vs tx count correlation
    daily_data: dict[str, dict] = defaultdict(lambda: {"txs": 0, "gas_total": 0.0, "gas_costs": []})
    for t in trades:
        day = t["timestamp"].strftime("%Y-%m-%d")
        daily_data[day]["txs"] += 1
        daily_data[day]["gas_total"] += t["gas_cost_eth"]
        daily_data[day]["gas_costs"].append(t["gas_cost_eth"])

    # Categorize days by gas level
    day_gas_medians = {}
    for day, data in daily_data.items():
        if data["gas_costs"]:
            day_gas_medians[day] = median(data["gas_costs"])

    if not day_gas_medians:
        return {"note": "Insufficient gas data"}

    all_medians = sorted(day_gas_medians.values())
    gas_q2 = all_medians[len(all_medians) // 2]

    low_gas_days = [d for d, m in day_gas_medians.items() if m <= gas_q2]
    high_gas_days = [d for d, m in day_gas_medians.items() if m > gas_q2]

    low_gas_txs = [daily_data[d]["txs"] for d in low_gas_days] if low_gas_days else [0]
    high_gas_txs = [daily_data[d]["txs"] for d in high_gas_days] if high_gas_days else [0]

    return {
        "gas_cost_eth_stats": {
            "mean": round(mean(gas_costs), 6),
            "median": round(q2, 6),
            "q1": round(q1, 6),
            "q3": round(q3, 6),
            "min": round(min(gas_costs), 6),
            "max": round(max(gas_costs), 6),
            "total": round(sum(gas_costs), 4),
        },
        "activity_by_gas_level": {
            "low_gas_days": {
                "count": len(low_gas_days),
                "avg_txs_per_day": round(mean(low_gas_txs), 1),
            },
            "high_gas_days": {
                "count": len(high_gas_days),
                "avg_txs_per_day": round(mean(high_gas_txs), 1),
            },
            "gas_sensitive": mean(high_gas_txs) < mean(low_gas_txs) * 0.8,
        },
    }


# =============================================================================
# Terminal Output
# =============================================================================

def print_summary(report: dict):
    """Print a readable terminal summary."""
    meta = report["meta"]
    print(f"\n{'='*70}")
    print(f"  DeFi BEHAVIOR FINGERPRINT — {meta['wallet'][:10]}...")
    print(f"{'='*70}")
    print(f"  Total swaps: {meta['total_trades']:,}")
    print(f"  Date range:  {meta['date_range']['start']} → {meta['date_range']['end']}")
    print(f"  Active days: {report['tempo']['total_active_days']}")
    print()

    # Fund flow
    ff = report["fund_flow"]
    print(f"  ── FUND FLOW (Aave) ──")
    print(f"  Aave interactions: {ff['total_aave_txs']} ({ff['deposits']} deposits, {ff['withdrawals']} withdrawals)")
    if ff.get("deposit_tokens"):
        print(f"  Deposit tokens:   {', '.join(f'{k}({v})' for k, v in list(ff['deposit_tokens'].items())[:5])}")
    if ff.get("withdraw_tokens"):
        print(f"  Withdraw tokens:  {', '.join(f'{k}({v})' for k, v in list(ff['withdraw_tokens'].items())[:5])}")
    print()

    # Token shifts
    ts = report["token_shifts"]
    print(f"  ── TOKEN PREFERENCE SHIFTS ──")
    print(f"  Top transitions:")
    for flow, count in list(ts["top_transitions"].items())[:8]:
        pct = round(count / meta["total_trades"] * 100, 1)
        print(f"    {flow:35s}  {count:4d}  ({pct}%)")
    print()

    # Tempo
    tempo = report["tempo"]
    print(f"  ── OPERATIONAL TEMPO ──")
    tpad = tempo["txs_per_active_day"]
    print(f"  Txs/active day: mean={tpad['mean']}, median={tpad['median']}, max={tpad['max']}")
    print(f"  Daily histogram:")
    for bucket, count in tempo["daily_histogram"].items():
        bar = "█" * max(1, count)
        print(f"    {bucket:12s}  {count:3d} days  {bar}")
    if tempo["burst_days_count"] > 0:
        print(f"  Burst days (>{tempo['burst_threshold']} txs): {tempo['burst_days_count']}")
        for bd in tempo["top_burst_days"][:5]:
            print(f"    {bd['date']}: {bd['txs']} txs")
    if tempo["inactive_gaps_7d_plus"]:
        print(f"  Inactive gaps (7d+): {len(tempo['inactive_gaps_7d_plus'])}")
        for gap in tempo["inactive_gaps_7d_plus"][:3]:
            print(f"    {gap['from']} → {gap['to']} ({gap['gap_days']}d)")
    print()

    # Time preference
    tp = report["time_preference"]
    print(f"  ── TIME PREFERENCE ──")
    print(f"  Peak hour: {tp['peak_hour_utc']:02d}:00 UTC  |  Peak day: {tp['peak_day']}")
    print(f"  Sessions:")
    for session, data in tp["session_breakdown"].items():
        bar = "█" * max(1, int(data["pct"] / 2))
        print(f"    {session:25s}  {data['count']:4d}  ({data['pct']:5.1f}%)  {bar}")
    print(f"  Day of week:")
    for day, data in tp["day_of_week"].items():
        bar = "█" * max(1, int(data["pct"] / 2))
        print(f"    {day:3s}  {data['count']:4d}  ({data['pct']:5.1f}%)  {bar}")
    print()

    # Gas sensitivity
    gs = report["gas_sensitivity"]
    if "gas_cost_eth_stats" in gs:
        gstats = gs["gas_cost_eth_stats"]
        agl = gs["activity_by_gas_level"]
        print(f"  ── GAS SENSITIVITY ──")
        print(f"  Gas cost (ETH): median={gstats['median']:.6f}, mean={gstats['mean']:.6f}, total={gstats['total']:.4f}")
        print(f"  Low-gas days:  {agl['low_gas_days']['count']} days, avg {agl['low_gas_days']['avg_txs_per_day']} txs/day")
        print(f"  High-gas days: {agl['high_gas_days']['count']} days, avg {agl['high_gas_days']['avg_txs_per_day']} txs/day")
        sensitive = agl["gas_sensitive"]
        print(f"  Gas sensitive:  {'YES — reduces activity in high gas' if sensitive else 'NO — activity unaffected by gas'}")
    print()
    print(f"{'='*70}")


# =============================================================================
# Main
# =============================================================================

def build_report(trades: list[dict], wallet_label: str = "unknown") -> dict:
    """Build the full fingerprint report."""
    timestamps = [t["timestamp"] for t in trades]
    return {
        "meta": {
            "wallet": wallet_label,
            "total_trades": len(trades),
            "date_range": {
                "start": min(timestamps).strftime("%Y-%m-%d") if timestamps else "",
                "end": max(timestamps).strftime("%Y-%m-%d") if timestamps else "",
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "fund_flow": analyze_fund_flow(trades),
        "token_shifts": analyze_token_shifts(trades),
        "tempo": analyze_tempo(trades),
        "time_preference": analyze_time_preference(trades),
        "gas_sensitivity": analyze_gas_sensitivity(trades),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Analyze DeFi behavior fingerprint from whale trade CSV"
    )
    parser.add_argument("csv_path", help="Path to whale trades CSV (from fetch_whale_trades.py)")
    parser.add_argument(
        "--output", "-o",
        default="scripts/research/output/defi_fingerprint.json",
        help="Output JSON report path",
    )
    parser.add_argument(
        "--wallet", "-w",
        default="0xb99a2c (Abraxas Capital)",
        help="Wallet label for the report",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}")
        sys.exit(1)

    print(f"Loading trades from {csv_path}...")
    trades = load_trades(str(csv_path))
    if not trades:
        print("ERROR: No trades loaded.")
        sys.exit(1)

    print(f"Loaded {len(trades)} trades. Analyzing...")
    report = build_report(trades, wallet_label=args.wallet)

    # Terminal summary
    print_summary(report)

    # Save JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"Report saved to {output_path}")


if __name__ == "__main__":
    main()
