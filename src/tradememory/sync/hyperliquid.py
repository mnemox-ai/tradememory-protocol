"""Hyperliquid fill history from the public info API. No key, no signature.

The API returns at most 2,000 fills per call and only the 10,000 most recent
fills of an address, so a history older than that cannot be recovered; the
sooner an address is synced, the more of it is kept.

Only perpetual fills are turned into trades. Spot fills move balances that
deposits and transfers also move, and those are not in the fill feed, so a
spot "position" cannot be rebuilt from fills alone.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from .fills import Fill

API_URL = "https://api.hyperliquid.xyz/info"
PAGE_SIZE = 2000
MAX_PAGES = 6  # 10,000 retrievable fills, with room for overlap at page edges
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

Post = Callable[[dict[str, Any]], Any]


def _post(body: dict[str, Any], retries: int = 4) -> Any:
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 — fixed https URL
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # 429 = the per-IP weight limit; back off and try again.
            if exc.code not in (429, 500, 502, 503) or attempt == retries:
                raise
            time.sleep(2 ** attempt)


def fetch_fills(address: str, post: Post | None = None, start_ms: int = 0) -> list[dict[str, Any]]:
    """Every retrievable fill for ``address``, oldest first, deduplicated by trade id."""
    if not ADDRESS_RE.match(address):
        raise ValueError(f"not a Hyperliquid address: {address!r}")
    post = post or _post
    seen: set[Any] = set()
    out: list[dict[str, Any]] = []
    cursor = start_ms
    for _ in range(MAX_PAGES):
        page = post({"type": "userFillsByTime", "user": address, "startTime": cursor, "aggregateByTime": False})
        if not isinstance(page, list):
            raise ValueError(f"unexpected response from Hyperliquid: {str(page)[:200]}")
        fresh = [f for f in page if (f.get("tid"), f.get("hash")) not in seen]
        for f in fresh:
            seen.add((f.get("tid"), f.get("hash")))
        out.extend(fresh)
        if len(page) < PAGE_SIZE or not fresh:
            break
        # The next page starts at the last timestamp returned; fills sharing
        # that millisecond come back again and are dropped as duplicates.
        cursor = max(int(f["time"]) for f in page)
    out.sort(key=lambda f: (int(f["time"]), str(f.get("tid"))))
    return out


def is_perp(raw: dict[str, Any]) -> bool:
    coin = str(raw.get("coin", ""))
    return not coin.startswith("@") and "/" not in coin and raw.get("dir") not in ("Buy", "Sell")


def to_fill(raw: dict[str, Any], address: str) -> Fill:
    """One perpetual fill as a Fill. Raises ValueError on a malformed record."""
    try:
        side = {"B": "buy", "A": "sell"}[raw["side"]]
        fee = Decimal(str(raw.get("fee", "0")))
        if raw.get("feeToken", "USDC") != "USDC":
            fee = Decimal(0)  # paid in another token; not comparable to USDC P&L
        return Fill(
            source="hyperliquid",
            account=address.lower(),
            symbol=str(raw["coin"]).upper(),
            side=side,
            qty=Decimal(str(raw["sz"])),
            price=Decimal(str(raw["px"])),
            fee=fee,
            time=datetime.fromtimestamp(int(raw["time"]) / 1000, tz=timezone.utc),
            fill_id=f"{raw['tid']}",
            order_id=str(raw["oid"]) if raw.get("oid") is not None else None,
            start_position=Decimal(str(raw["startPosition"])) if raw.get("startPosition") is not None else None,
        )
    except (KeyError, InvalidOperation, TypeError) as exc:
        raise ValueError(f"malformed Hyperliquid fill: {exc!r}") from exc


def perp_fills(raw_fills: list[dict[str, Any]], address: str) -> tuple[list[Fill], int]:
    """(perpetual fills as Fill, count of spot fills skipped)."""
    fills, spot = [], 0
    for raw in raw_fills:
        if not is_perp(raw):
            spot += 1
            continue
        fills.append(to_fill(raw, address))
    return fills, spot
