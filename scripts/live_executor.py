#!/usr/bin/env python3
"""Strategy E live paper trading executor.

Runs hourly via GitHub Actions. Checks BTCUSDT 1H bars from Binance,
manages paper positions in Supabase (live_positions / live_trades tables).

Env vars required:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
Optional:
  TRADEMEMORY_API_URL  (for OWM memory on close)
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from supabase import create_client

# Allow importing from scripts/ (for build_strategy_e)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from strategy_definitions import build_strategy_e

from tradememory.data.binance import BinanceDataSource
from tradememory.data.context_builder import build_context, compute_atr
from tradememory.data.models import Timeframe
from tradememory.evolution.backtester import check_entry

USER_AGENT = "tradememory-live-executor/1.0 (github.com/mnemox-ai/tradememory-protocol)"
STRATEGY_ID = "strategy_e"


def get_supabase():
    """Create Supabase client from env vars."""
    url = os.environ["SUPABASE_URL"].strip()
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
    return create_client(url, key)


async def fetch_bars():
    """Fetch last 30 BTCUSDT 1H bars from Binance."""
    source = BinanceDataSource(base_url=os.environ.get("BINANCE_BASE_URL"))
    try:
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=35)  # extra buffer for ATR(14)
        series = await source.fetch_ohlcv(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            start=start,
            end=now,
            limit=30,
        )
        return series
    finally:
        await source.close()


def check_exit(pos: dict, bar) -> dict | None:
    """Check if open position should exit on this bar.

    Priority: SL > TP > time.
    Returns exit info dict or None.
    """
    direction = pos["direction"]
    sl = pos["stop_loss"]
    tp = pos["take_profit"]
    max_exit = datetime.fromisoformat(pos["max_exit_time"])
    now = datetime.now(timezone.utc)

    exit_price = None
    reason = None

    if direction == "long":
        if bar.low <= sl:
            exit_price, reason = sl, "sl"
        elif bar.high >= tp:
            exit_price, reason = tp, "tp"
    else:  # short
        if bar.high >= sl:
            exit_price, reason = sl, "sl"
        elif bar.low <= tp:
            exit_price, reason = tp, "tp"

    if exit_price is None and now >= max_exit:
        exit_price, reason = bar.close, "time"

    if exit_price is None:
        return None

    entry = pos["entry_price"]
    if direction == "long":
        pnl_pct = (exit_price - entry) / entry * 100
    else:
        pnl_pct = (entry - exit_price) / entry * 100

    sl_distance = abs(entry - sl)
    sl_pct = sl_distance / entry * 100
    pnl_r = pnl_pct / sl_pct if sl_pct > 0 else 0.0

    return {
        "exit_price": round(exit_price, 2),
        "reason": reason,
        "pnl_pct": round(pnl_pct, 4),
        "pnl_r": round(pnl_r, 4),
    }


def fire_and_forget_owm(pos: dict, exit_info: dict):
    """POST trade memory to OWM API (best-effort)."""
    api_url = os.environ.get("TRADEMEMORY_API_URL")
    if not api_url:
        return

    payload = {
        "memory_type": "episodic",
        "content": {
            "strategy": STRATEGY_ID,
            "symbol": "BTCUSDT",
            "direction": pos["direction"],
            "entry_price": pos["entry_price"],
            "exit_price": exit_info["exit_price"],
            "pnl_pct": exit_info["pnl_pct"],
            "pnl_r": exit_info["pnl_r"],
            "exit_reason": exit_info["reason"],
            "trade_type": "paper",
        },
        "context": {
            "strategy_id": STRATEGY_ID,
            "trade_type": "paper",
        },
    }

    try:
        with httpx.Client(timeout=5.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.post(f"{api_url}/owm/remember", json=payload)
            print(f"  OWM remember: {resp.status_code}")
    except Exception as e:
        print(f"  WARNING: OWM remember failed: {e}")


async def main():
    print(f"=== Strategy E Live Executor — {datetime.now(timezone.utc).isoformat()} ===")

    # 1. Fetch bars
    series = await fetch_bars()
    if not series or len(series.bars) < 15:
        print(f"ERROR: Only {len(series.bars) if series else 0} bars fetched, need >= 15")
        return

    last_bar = series.bars[-1]
    print(f"Last bar: {last_bar.timestamp.isoformat()} close={last_bar.close}")

    # 2. Build context + ATR
    ctx = build_context(series, bar_index=-1)
    atr = compute_atr(series.bars, period=14)
    print(f"Context: hour_utc={ctx.hour_utc} trend_12h_pct={ctx.trend_12h_pct} ATR(14)={atr}")

    # 3. Connect Supabase
    sb = get_supabase()

    # 4. Check open position
    result = (
        sb.table("live_positions")
        .select("*")
        .eq("strategy_id", STRATEGY_ID)
        .eq("status", "open")
        .limit(1)
        .execute()
    )
    pos = result.data[0] if result.data else None

    if pos:
        print(f"Open position: entry={pos['entry_price']} sl={pos['stop_loss']} tp={pos['take_profit']}")

        # 5. Check exit
        exit_info = check_exit(pos, last_bar)
        if exit_info:
            print(f"  EXIT: {exit_info['reason']} @ {exit_info['exit_price']} "
                  f"PnL={exit_info['pnl_pct']:.2f}% R={exit_info['pnl_r']:.2f}")

            # Insert trade record
            sb.table("live_trades").insert({
                "strategy_id": STRATEGY_ID,
                "symbol": "BTCUSDT",
                "direction": pos["direction"],
                "entry_price": pos["entry_price"],
                "exit_price": exit_info["exit_price"],
                "entry_time": pos["entry_time"],
                "exit_time": datetime.now(timezone.utc).isoformat(),
                "exit_reason": exit_info["reason"],
                "pnl_pct": exit_info["pnl_pct"],
                "pnl_r": exit_info["pnl_r"],
                "trade_type": "paper",
            }).execute()

            # Close position
            sb.table("live_positions").update({
                "status": "closed",
                "closed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", pos["id"]).execute()

            print("  Position closed, trade recorded.")

            # OWM memory (fire-and-forget)
            fire_and_forget_owm(pos, exit_info)
        else:
            print("  No exit signal.")
    else:
        print("No open position.")

        # 6. Check entry
        pattern = build_strategy_e()
        should_enter = check_entry(pattern, ctx)
        print(f"Entry signal: {should_enter}")

        if should_enter and atr and atr > 0:
            entry = last_bar.close
            sl = entry - atr * 1.0
            tp = entry + atr * 2.0
            max_exit_time = last_bar.timestamp + timedelta(hours=6)

            sb.table("live_positions").insert({
                "strategy_id": STRATEGY_ID,
                "symbol": "BTCUSDT",
                "direction": "long",
                "entry_price": round(entry, 2),
                "stop_loss": round(sl, 2),
                "take_profit": round(tp, 2),
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "max_exit_time": max_exit_time.isoformat(),
                "status": "open",
            }).execute()

            print(f"  OPENED: entry={entry:.2f} sl={sl:.2f} tp={tp:.2f} "
                  f"max_exit={max_exit_time.isoformat()}")
        elif not should_enter:
            print("  No entry conditions met.")
        else:
            print("  ATR invalid, skipping entry.")

    print("=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
