"""Check an order against the owner's active rules, using the closed trades in memory.

The brake only knows the closes that reached memory: a broker sync
(`tradememory sync alpaca`) writes them. Each hit says how fresh that
history was, so a rule that did not fire because the latest losses were not
synced yet can be told apart from one that had nothing to fire on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ..db import Database
from .suggest import SIZE_AFTER_LOSING_STREAK

RULE_CODE = "TM_RULE_SIZE_AFTER_LOSING_STREAK"
SCAN_LIMIT = 500  # newest closed trades looked at; a streak needs only the last few


@dataclass(frozen=True)
class Close:
    closed_at: datetime
    symbol: str
    pnl: float
    trade_id: str


def _parse(stamp: Any) -> datetime | None:
    if not stamp:
        return None
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def recent_closes(db: Database, *, venue: str | None, limit: int) -> list[Close]:
    """The newest closed trades, newest first. ``venue`` keeps only rows tagged with it."""
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT id, symbol, timestamp, exit_timestamp, pnl, tags FROM trade_records "
            "WHERE pnl IS NOT NULL ORDER BY COALESCE(exit_timestamp, timestamp) DESC LIMIT ?",
            (SCAN_LIMIT,),
        ).fetchall()
    closes: list[Close] = []
    for row in rows:
        if venue is not None:
            try:
                tags = json.loads(row["tags"] or "[]")
            except ValueError:
                tags = []
            if venue not in tags:
                continue
        # Imported trips store their exit as the row timestamp; brake rows get exit_timestamp on sync.
        closed_at = _parse(row["exit_timestamp"]) or _parse(row["timestamp"])
        if closed_at is None:
            continue
        closes.append(Close(closed_at=closed_at, symbol=row["symbol"], pnl=float(row["pnl"]), trade_id=row["id"]))
    # SQLite sorted text; timestamps written in different formats sort wrong, so sort parsed values.
    closes.sort(key=lambda c: c.closed_at, reverse=True)
    return closes[:limit]


def check_order(
    rules: list[dict[str, Any]],
    *,
    order_notional: Decimal | None,
    adds_risk: bool,
    closes: list[Close],
) -> list[dict[str, Any]]:
    """The active rules this order trips, in the brake's flagged-rule shape."""
    if not adds_risk:
        return []  # reducing or closing risk is never held by a learned rule
    hits: list[dict[str, Any]] = []
    for rule in rules:
        if rule["kind"] != SIZE_AFTER_LOSING_STREAK:
            continue
        streak = rule["streak"]
        last = closes[:streak]
        if len(last) < streak or any(c.pnl >= 0 for c in last):
            continue
        limit = Decimal(rule["max_notional"])
        # Without a notional the order cannot be shown to be small: treat it as at the limit.
        if order_notional is not None and order_notional < limit:
            continue
        hits.append({
            "code": RULE_CODE,
            "rule_id": rule["id"],
            "action": rule["action"],
            "actual": str(order_notional) if order_notional is not None else None,
            "limit": rule["max_notional"],
            "subjects": [],
            "losing_streak": [
                {"trade_id": c.trade_id, "symbol": c.symbol, "pnl": c.pnl, "closed_at": c.closed_at.isoformat()}
                for c in last
            ],
            "history_as_of": closes[0].closed_at.isoformat() if closes else None,
            "message": (
                f"After {streak} losses in a row, orders of ${int(limit):,} or more are "
                f"{'held for the owner' if rule['action'] == 'escalate' else 'refused'} (rule {rule['id']})."
            ),
        })
    return hits
