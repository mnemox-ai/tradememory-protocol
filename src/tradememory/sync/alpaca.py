"""Alpaca fill history over the trading REST API (read-only calls only).

Used to close the broker brake's loop: the proxy opens a trade_records row
when it forwards an order, but never learns how that trade ended. Fills are
rebuilt into round trips, and a trip whose opening order went through the
proxy fills in that row's exit and P&L.

Alpaca does not report the position before each fill, so the history is
checked against the broker's current positions instead: a symbol whose
rebuilt open size disagrees with the broker (history older than the account
activity window, or a transfer) is left out rather than stored with wrong P&L.
Commissions on crypto arrive as separate fee activities and are not netted.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from .fills import Fill

PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL = "https://api.alpaca.markets"
PAGE_SIZE = 100
MAX_PAGES = 200

Get = Callable[[str, dict[str, Any]], Any]


def http_get(base_url: str, key_id: str, secret: str) -> Get:
    def get(path: str, params: dict[str, Any]) -> Any:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        request = urllib.request.Request(
            f"{base_url}{path}{query}",
            headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret},
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 — fixed https base URL
            return json.load(response)
    return get


def fetch_fill_activities(get: Get) -> list[dict[str, Any]]:
    """Every FILL activity, oldest first.

    Raises ValueError instead of returning a partial history: pages come
    oldest first, so a cut-off list would be missing the newest trades.
    """
    out: list[dict[str, Any]] = []
    token: str | None = None
    for _ in range(MAX_PAGES):
        params: dict[str, Any] = {"direction": "asc", "page_size": PAGE_SIZE}
        if token:
            params["page_token"] = token
        page = get("/v2/account/activities/FILL", params)
        if not isinstance(page, list):
            raise ValueError(f"unexpected response from Alpaca: {str(page)[:200]}")
        out.extend(page)
        if len(page) < PAGE_SIZE:
            return out
        if page[-1]["id"] == token:
            raise ValueError("Alpaca returned the same page twice; the fill history is incomplete")
        token = page[-1]["id"]
    raise ValueError(f"more than {MAX_PAGES * PAGE_SIZE:,} fill activities; stopped rather than store part of them")


def fetch_positions(get: Get) -> dict[str, Decimal]:
    """Broker's open positions as signed sizes."""
    positions: dict[str, Decimal] = {}
    for p in get("/v2/positions", {}) or []:
        qty = Decimal(str(p["qty"]))
        if p.get("side") == "short" and qty > 0:
            qty = -qty
        positions[str(p["symbol"]).replace("/", "").upper()] = qty
    return positions


def to_fill(raw: dict[str, Any], account: str) -> Fill:
    try:
        side = "buy" if raw["side"] == "buy" else "sell"  # "sell" and "sell_short"
        return Fill(
            source="alpaca",
            account=account,
            symbol=str(raw["symbol"]).replace("/", "").upper(),
            side=side,
            qty=Decimal(str(raw["qty"])),
            price=Decimal(str(raw["price"])),
            fee=Decimal(0),
            time=datetime.fromisoformat(str(raw["transaction_time"]).replace("Z", "+00:00")),
            fill_id=str(raw["id"]),
            order_id=str(raw["order_id"]) if raw.get("order_id") else None,
        )
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"malformed Alpaca fill activity: {exc!r}") from exc
