#!/usr/bin/env python3
"""Seed strategy backtest trades from JSON into Supabase live_trades table.

Reads backtest JSON, deletes existing backtest rows for the strategy,
then inserts all trades.

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/seed_backtest_trades.py              # default: Strategy E
    python scripts/seed_backtest_trades.py --strategy c  # Strategy C

Env vars required:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
"""

import argparse
import json
import os
import sys
from pathlib import Path

from supabase import create_client

STRATEGY_CONFIGS = {
    "c": ("strategy_c", "strategy_c_backtest.json"),
    "e": ("strategy_e", "strategy_e_backtest.json"),
}


def get_supabase():
    """Create Supabase client from env vars."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def load_trades(json_path: Path) -> list[dict]:
    """Load backtest trades from JSON file."""
    if not json_path.exists():
        print(f"ERROR: {json_path} not found. Run export_backtest_trades.py first.")
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        trades = json.load(f)

    print(f"Loaded {len(trades)} trades from {json_path}")
    return trades


def main():
    parser = argparse.ArgumentParser(description="Seed backtest trades into Supabase")
    parser.add_argument("--strategy", choices=["c", "e"], default="e", help="Strategy to seed (default: e)")
    args = parser.parse_args()

    strategy_id, json_filename = STRATEGY_CONFIGS[args.strategy]
    json_path = Path(__file__).parent.parent / "data" / json_filename

    print(f"=== Seed Strategy {args.strategy.upper()} Backtest Trades into Supabase ===\n")

    # 1. Load JSON
    trades = load_trades(json_path)

    # 2. Connect Supabase
    sb = get_supabase()

    # 3. DELETE existing backtest rows for this strategy
    print(f"Deleting existing backtest trades for {strategy_id}...")
    result = (
        sb.table("live_trades")
        .delete()
        .eq("strategy_id", strategy_id)
        .eq("trade_type", "backtest")
        .execute()
    )
    deleted = len(result.data) if result.data else 0
    print(f"  Deleted {deleted} existing rows")

    # 4. INSERT trades (batch insert, override strategy_id to match live system)
    print(f"\nPreparing {len(trades)} trades for batch insert...")
    rows = []
    for trade in trades:
        row = {
            "strategy_id": strategy_id,
            "symbol": trade["symbol"],
            "direction": trade["direction"],
            "entry_price": trade["entry_price"],
            "exit_price": trade["exit_price"],
            "entry_time": trade["entry_time"],
            "exit_time": trade["exit_time"],
            "pnl_pct": trade["pnl_pct"],
            "pnl_r": trade["pnl_r"],
            "exit_reason": trade["exit_reason"],
            "trade_type": "backtest",
        }
        # Include optional fields if present
        if trade.get("holding_bars") is not None:
            row["holding_bars"] = trade["holding_bars"]
        if trade.get("atr_at_entry") is not None:
            row["atr_at_entry"] = trade["atr_at_entry"]
        if trade.get("trend_12h_pct") is not None:
            row["trend_12h_pct"] = trade["trend_12h_pct"]
        rows.append(row)

    # Batch insert (chunks of 100 if > 500 rows)
    BATCH_SIZE = 100
    inserted = 0
    errors = 0

    if len(rows) <= 500:
        batches = [rows]
    else:
        batches = [rows[i : i + BATCH_SIZE] for i in range(0, len(rows), BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches):
        try:
            sb.table("live_trades").insert(batch).execute()
            inserted += len(batch)
            if len(batches) > 1:
                print(f"  Batch {batch_idx + 1}/{len(batches)}: {len(batch)} rows inserted")
        except Exception as e:
            errors += len(batch)
            print(f"  ERROR on batch {batch_idx + 1}: {e}")

    # 5. Summary
    print(f"\n--- Summary ---")
    print(f"  Loaded:   {len(trades)}")
    print(f"  Inserted: {inserted}")
    print(f"  Errors:   {errors}")
    print(f"  Deleted:  {deleted} (prior backtest rows)")

    if trades:
        wins = sum(1 for t in trades if t["pnl_pct"] > 0)
        losses = len(trades) - wins
        total_pnl = sum(t["pnl_pct"] for t in trades)
        print(f"  Wins:     {wins}")
        print(f"  Losses:   {losses}")
        print(f"  Total PnL%: {total_pnl:.2f}%")

    if errors > 0:
        print("\nWARNING: Some inserts failed. Check table schema matches.")
        sys.exit(1)


if __name__ == "__main__":
    main()
