"""
Binance Sync — Poll Binance spot account trades and push to TradeMemory.

Architecture:
  Binance REST API → binance_sync.py → TradeMemory REST API (POST /trades)

Usage:
  # Set environment variables (or use .env file):
  BINANCE_API_KEY=...
  BINANCE_API_SECRET=...
  TRADEMEMORY_API=http://localhost:8000   # optional, default

  python scripts/research/binance_sync.py              # one-shot sync
  python scripts/research/binance_sync.py --watch 60   # poll every 60 seconds
"""

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration (all from environment, never hardcoded)
# ---------------------------------------------------------------------------

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL", "https://api.binance.com")
TRADEMEMORY_API = os.getenv("TRADEMEMORY_API", "http://localhost:8000")
SYNC_INTERVAL = int(os.getenv("BINANCE_SYNC_INTERVAL", "60"))

# Symbols to sync — comma-separated, e.g. "BTCUSDT,ETHUSDT,SOLUSDT"
WATCH_SYMBOLS = [
    s.strip().upper()
    for s in os.getenv("BINANCE_WATCH_SYMBOLS", "BTCUSDT").split(",")
    if s.strip()
]

# Track last synced trade ID per symbol to avoid duplicates
_last_trade_id: Dict[str, int] = {}


# ---------------------------------------------------------------------------
# Binance API helpers (minimal, no SDK dependency)
# ---------------------------------------------------------------------------


def _sign(params: Dict[str, Any]) -> str:
    """Generate HMAC SHA256 signature for Binance API."""
    query_string = urllib.parse.urlencode(params)
    return hmac.new(
        BINANCE_API_SECRET.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _binance_get(endpoint: str, params: Optional[Dict[str, Any]] = None, signed: bool = False) -> Any:
    """Make authenticated GET request to Binance API."""
    url = f"{BINANCE_BASE_URL}{endpoint}"
    params = params or {}

    if signed:
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = _sign(params)

    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_my_trades(symbol: str, limit: int = 50, from_id: Optional[int] = None) -> List[Dict]:
    """Fetch recent trades for a symbol from Binance spot account.

    Docs: GET /api/v3/myTrades
    Returns list of fills (partial fills possible).
    """
    params: Dict[str, Any] = {"symbol": symbol, "limit": limit}
    if from_id is not None:
        params["fromId"] = from_id
    return _binance_get("/api/v3/myTrades", params=params, signed=True)


# ---------------------------------------------------------------------------
# Trade pairing — match BUY + SELL into round-trip trades
# ---------------------------------------------------------------------------


def pair_trades(fills: List[Dict]) -> List[Dict]:
    """Pair BUY and SELL fills into round-trip trades.

    Simple FIFO: first BUY matches first SELL.
    Partial fills on the same orderId are aggregated.

    Returns list of paired trades with entry/exit info.
    """
    # Aggregate fills by orderId
    orders: Dict[int, Dict] = {}
    for fill in fills:
        oid = fill["orderId"]
        if oid not in orders:
            orders[oid] = {
                "orderId": oid,
                "symbol": fill["symbol"],
                "isBuyer": fill["isBuyer"],
                "qty": 0.0,
                "cost": 0.0,
                "commission": 0.0,
                "commissionAsset": fill.get("commissionAsset", ""),
                "time": fill["time"],
            }
        o = orders[oid]
        qty = float(fill["qty"])
        price = float(fill["price"])
        o["qty"] += qty
        o["cost"] += qty * price
        o["commission"] += float(fill["commission"])

    # Calculate average price per order
    for o in orders.values():
        o["avgPrice"] = o["cost"] / o["qty"] if o["qty"] > 0 else 0.0

    # Sort by time
    sorted_orders = sorted(orders.values(), key=lambda x: x["time"])

    # FIFO pairing
    buys = [o for o in sorted_orders if o["isBuyer"]]
    sells = [o for o in sorted_orders if not o["isBuyer"]]

    paired = []
    for buy, sell in zip(buys, sells):
        qty = min(buy["qty"], sell["qty"])
        pnl = (sell["avgPrice"] - buy["avgPrice"]) * qty
        pnl -= buy["commission"] + sell["commission"]  # rough commission deduction

        paired.append({
            "symbol": buy["symbol"],
            "direction": "long",
            "entry_price": buy["avgPrice"],
            "exit_price": sell["avgPrice"],
            "qty": qty,
            "pnl": round(pnl, 4),
            "entry_time": datetime.fromtimestamp(buy["time"] / 1000, tz=timezone.utc).isoformat(),
            "exit_time": datetime.fromtimestamp(sell["time"] / 1000, tz=timezone.utc).isoformat(),
            "entry_order_id": buy["orderId"],
            "exit_order_id": sell["orderId"],
        })

    return paired


# ---------------------------------------------------------------------------
# Push to TradeMemory
# ---------------------------------------------------------------------------


def push_to_tradememory(trade: Dict) -> bool:
    """Push a paired trade to TradeMemory REST API.

    Uses POST /owm/remember endpoint (OWM multi-layer storage).
    Falls back to POST /trades if OWM endpoint unavailable.
    """
    # Try OWM endpoint first
    owm_payload = {
        "symbol": trade["symbol"],
        "direction": trade["direction"],
        "entry_price": trade["entry_price"],
        "exit_price": trade["exit_price"],
        "pnl": trade["pnl"],
        "strategy_name": "BinanceSpot",
        "market_context": f"Binance spot {trade['direction']} {trade['symbol']}. "
                          f"Entry: {trade['entry_price']}, Exit: {trade['exit_price']}. "
                          f"Qty: {trade['qty']}.",
        "timestamp": trade["exit_time"],
        "trade_id": f"binance-{trade['exit_order_id']}",
    }

    try:
        resp = requests.post(
            f"{TRADEMEMORY_API}/owm/remember",
            json=owm_payload,
            timeout=10,
        )
        if resp.status_code == 200:
            result = resp.json()
            print(f"[OK] {trade['symbol']} {trade['direction']} PnL={trade['pnl']:+.2f} → {result.get('memory_id', '?')}")
            return True

        # Fallback to legacy endpoint
        legacy_payload = {
            "symbol": trade["symbol"],
            "direction": trade["direction"],
            "entry_price": trade["entry_price"],
            "strategy_name": "BinanceSpot",
            "market_context": owm_payload["market_context"],
            "exit_price": trade["exit_price"],
            "pnl": trade["pnl"],
            "trade_id": owm_payload["trade_id"],
            "timestamp": trade["exit_time"],
        }
        resp = requests.post(
            f"{TRADEMEMORY_API}/trades",
            json=legacy_payload,
            timeout=10,
        )
        resp.raise_for_status()
        print(f"[OK-legacy] {trade['symbol']} {trade['direction']} PnL={trade['pnl']:+.2f}")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to push {trade['symbol']}: {e}")
        return False


# ---------------------------------------------------------------------------
# Sync loop
# ---------------------------------------------------------------------------


def sync_once() -> int:
    """Run one sync cycle. Returns number of new trades pushed."""
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        print("[ERROR] BINANCE_API_KEY and BINANCE_API_SECRET must be set")
        return 0

    total_pushed = 0

    for symbol in WATCH_SYMBOLS:
        from_id = _last_trade_id.get(symbol)
        try:
            fills = fetch_my_trades(symbol, limit=50, from_id=from_id)
        except Exception as e:
            print(f"[ERROR] Binance API error for {symbol}: {e}")
            continue

        if not fills:
            continue

        # Update last trade ID
        max_id = max(f["id"] for f in fills)
        if from_id is not None and max_id <= from_id:
            continue  # No new trades
        _last_trade_id[symbol] = max_id

        # Pair and push
        paired = pair_trades(fills)
        for trade in paired:
            if push_to_tradememory(trade):
                total_pushed += 1

    return total_pushed


def main():
    """Entry point. Use --watch N for continuous polling."""
    watch_mode = False
    interval = SYNC_INTERVAL

    if "--watch" in sys.argv:
        watch_mode = True
        idx = sys.argv.index("--watch")
        if idx + 1 < len(sys.argv):
            interval = int(sys.argv[idx + 1])

    print(f"[binance_sync] Symbols: {WATCH_SYMBOLS}")
    print(f"[binance_sync] TradeMemory API: {TRADEMEMORY_API}")

    if watch_mode:
        print(f"[binance_sync] Watch mode: polling every {interval}s")
        while True:
            n = sync_once()
            if n > 0:
                print(f"[binance_sync] Pushed {n} new trade(s)")
            time.sleep(interval)
    else:
        n = sync_once()
        print(f"[binance_sync] Done. Pushed {n} trade(s)")


if __name__ == "__main__":
    main()
