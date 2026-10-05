"""Check an order against the owner's active rules.

The closed trades come from the broker at the moment of the check
(`tradememory.proxy.history`), not from the memory database: memory knows a
close only after a sync, and a shared database holds other accounts' trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from .suggest import SIZE_AFTER_LOSING_STREAK, money

RULE_CODE = "TM_RULE_SIZE_AFTER_LOSING_STREAK"


@dataclass(frozen=True)
class Close:
    closed_at: datetime
    symbol: str
    pnl: float
    trade_id: str


def rules_in_reach(rules: list[dict[str, Any]], size: Decimal | None) -> list[dict[str, Any]]:
    """Rules this order could trip. An order of unknown size could trip any of them."""
    return [r for r in rules if size is None or size >= Decimal(r["max_notional"])]


def check_order(rules: list[dict[str, Any]], *, size: Decimal | None, closes: list[Close]) -> list[dict[str, Any]]:
    """The rules this order trips, in the brake's flagged-rule shape.

    ``size`` is the position the order could leave the account with, valued
    at the reference price: the larger of the order's own notional and the
    worst-case position after it fills. The report learned the threshold from
    position sizes, so two small orders that add up to a big position are held
    like one big order. ``closes`` are the account's closed trades, newest first.
    Callers pass only orders that add risk.
    """
    hits: list[dict[str, Any]] = []
    for rule in rules_in_reach(rules, size):
        if rule["kind"] != SIZE_AFTER_LOSING_STREAK:
            continue
        streak = rule["streak"]
        last = closes[:streak]
        if len(last) < streak or any(c.pnl >= 0 for c in last):
            continue
        hits.append({
            "code": RULE_CODE,
            "rule_id": rule["id"],
            "action": rule["action"],
            "actual": str(size) if size is not None else None,
            "limit": rule["max_notional"],
            "subjects": [],
            "learned_from": rule.get("source"),
            "losing_streak": [
                {"trade_id": c.trade_id, "symbol": c.symbol, "pnl": c.pnl, "closed_at": c.closed_at.isoformat()}
                for c in last
            ],
            "message": (
                f"After {streak} losses in a row, orders that take a position to {money(rule['max_notional'])} "
                f"or more are {'held for the owner' if rule['action'] == 'escalate' else 'refused'} "
                f"(rule {rule['id']})."
            ),
        })
    return hits
