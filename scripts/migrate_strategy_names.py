"""
One-time migration: Fix strategy names in tradememory.db using MT5 magic numbers.

Existing trades were all stored as strategy="NG_Gold". This script:
1. Queries MT5 for historical deals to get magic numbers
2. Maps magic → strategy name
3. Updates trade_records in tradememory.db

Usage:
    python scripts/migrate_strategy_names.py [--dry-run]

Requires: MetaTrader5 package + MT5 terminal running
"""

import os
import sys
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Magic number → strategy name mapping (same as mt5_sync.py)
MAGIC_TO_STRATEGY = {
    0: "Manual",                   # Manual trades (MT5 default, no EA)
    260111: "NG_Gold",             # Default legacy magic
    260112: "VolBreakout",         # NG_Gold.mq5 Strategy_Mode=2
    260113: "IntradayMomentum",    # NG_Gold.mq5 Strategy_Mode=8
    20260217: "Pullback",          # NG_Pullback_Entry.mq5
}

DB_PATH = os.getenv("TRADEMEMORY_DB", "data/tradememory.db")


def get_mt5_magic_map() -> dict:
    """Query MT5 for all historical deals and build position_id → magic mapping."""
    try:
        import MetaTrader5 as MT5
    except ImportError:
        print("[ERROR] MetaTrader5 not installed")
        sys.exit(1)

    mt5_path = os.getenv("MT5_PATH", "")
    login = int(os.getenv("MT5_LOGIN", "0"))
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")

    init_kwargs = dict(login=login, password=password, server=server, timeout=30000)
    if mt5_path:
        init_kwargs["path"] = mt5_path

    if not MT5.initialize(**init_kwargs):
        print(f"[ERROR] MT5 initialize failed: {MT5.last_error()}")
        sys.exit(1)

    print(f"[OK] Connected to MT5: {MT5.account_info().login}")

    # Get all history
    deals = MT5.history_deals_get(datetime(2020, 1, 1), datetime.now())
    MT5.shutdown()

    if deals is None or len(deals) == 0:
        print("[WARN] No deals found in MT5 history")
        return {}

    # Build position_id → magic mapping (use entry deal's magic)
    magic_map = {}
    for deal in deals:
        if deal.position_id == 0:
            continue
        if deal.entry == 0:  # DEAL_ENTRY_IN
            magic_map[deal.position_id] = deal.magic

    print(f"[OK] Found {len(magic_map)} position → magic mappings")
    return magic_map


def migrate(dry_run: bool = False):
    """Run the migration."""
    print(f"Database: {DB_PATH}")
    print(f"Dry run: {dry_run}")
    print()

    # Step 1: Get MT5 magic numbers
    magic_map = get_mt5_magic_map()

    # Step 2: Read current DB state
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, strategy, reasoning, market_context FROM trade_records"
    ).fetchall()

    print(f"\nFound {len(rows)} trades in DB:")
    print("-" * 80)

    updates = []
    for row in rows:
        trade_id = row["id"]
        current_strategy = row["strategy"]

        # Extract position_id from trade_id (format: MT5-{position_id})
        if not trade_id.startswith("MT5-"):
            print(f"  {trade_id}: SKIP (not MT5 trade)")
            continue

        try:
            position_id = int(trade_id.split("-")[1])
        except (IndexError, ValueError):
            print(f"  {trade_id}: SKIP (bad format)")
            continue

        magic = magic_map.get(position_id)
        if magic is None:
            print(f"  {trade_id}: SKIP (position {position_id} not found in MT5 history)")
            continue

        new_strategy = MAGIC_TO_STRATEGY.get(magic, f"Unknown_Magic_{magic}")

        # Update market_context to include magic_number
        ctx = json.loads(row["market_context"])
        ctx["magic_number"] = magic
        new_ctx = json.dumps(ctx)

        new_reasoning = f"Auto-synced from MT5 (magic={magic})"

        status = "CHANGE" if current_strategy != new_strategy else "OK"
        print(
            f"  {trade_id}: magic={magic} | "
            f"{current_strategy} → {new_strategy} [{status}]"
        )

        if current_strategy != new_strategy or "magic" not in row["reasoning"]:
            updates.append((new_strategy, new_reasoning, new_ctx, trade_id))

    print(f"\n{len(updates)} trades need updating.")

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        conn.close()
        return

    if len(updates) == 0:
        print("Nothing to do.")
        conn.close()
        return

    # Step 3: Apply updates
    for new_strategy, new_reasoning, new_ctx, trade_id in updates:
        conn.execute(
            "UPDATE trade_records SET strategy=?, reasoning=?, market_context=? WHERE id=?",
            (new_strategy, new_reasoning, new_ctx, trade_id),
        )
    conn.commit()
    conn.close()

    print(f"\n[OK] Updated {len(updates)} trades successfully.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    migrate(dry_run=dry_run)
