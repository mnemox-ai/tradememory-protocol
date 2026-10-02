"""Write finished round trips into TradeMemory, once each.

A trip's id is derived from its first fill, so running a sync again stores
only the trips that were not there before. A trip the broker brake already
recorded (its opening order went through the proxy) keeps the brake's id:
the outcome is written onto that row instead of creating a second one, and
the trip enters episodic memory under the same id so recall can see it.

The writes for one trip are not a single transaction. A run that stops
halfway leaves the memory without its outcome row, and the next run finishes
that row. The semantic, procedural and affective layers are not redone, so a
trip cut off right after its memory was written counts in them only if it
got that far.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Optional

from ..db import Database
from ..trade_store import insert_trade_record, store_trade_memory
from .fills import RoundTrip

Linker = Callable[[RoundTrip], Optional[dict]]


@dataclass
class StoreResult:
    stored: list[str] = field(default_factory=list)
    linked: list[str] = field(default_factory=list)  # brake rows that got their outcome
    repaired: list[str] = field(default_factory=list)  # finished what an interrupted run left
    skipped: int = 0  # already stored


def _f(x: Decimal) -> float:
    return float(x)


def _episodic_exists(db: Database, memory_id: str) -> bool:
    with db.get_connection() as conn:
        return conn.execute("SELECT 1 FROM episodic_memory WHERE id = ?", (memory_id,)).fetchone() is not None


def _describe(trip: RoundTrip, venue: str) -> str:
    hours = trip.hold_seconds / 3600
    held = f"{hours:.1f}h" if hours >= 1 else f"{trip.hold_seconds // 60}m"
    text = (
        f"{trip.direction} {trip.symbol} on {venue}, max size {trip.max_position.normalize():f} "
        f"(about {_f(trip.notional):,.0f} notional), held {held}, {trip.adds} add(s)"
    )
    return text if trip.fees_complete else text + ", some fees paid in another token and not netted"


def _pnl_r(trip: RoundTrip, stop: Optional[float]) -> Optional[float]:
    """R-multiple from the protective stop recorded at entry, when there was one."""
    if stop is None:
        return None
    risk = abs(_f(trip.avg_entry) - stop) * _f(trip.max_position)
    return _f(trip.net_pnl) / risk if risk > 0 else None


def _same_trade(row: dict, trip: RoundTrip) -> bool:
    """The brake row is for this symbol and direction (its symbol may be "BTC/USD")."""
    symbol = str(row.get("symbol") or "").replace("/", "").upper()
    return symbol == trip.symbol and row.get("direction") == trip.direction


def store_round_trips(
    db: Database,
    trips: list[RoundTrip],
    *,
    venue: str,
    strategy: str,
    link: Linker | None = None,
) -> StoreResult:
    """Store each closed trip once, oldest exit first.

    ``link(trip)`` may return the brake's trade_records row for this trip
    (matched on the opening order); its id and protective stop are reused.
    A row for another symbol or direction is not used, and one row goes to
    one trip: an order that filled on both sides of a flat moment opens two
    trips, and only the first takes the row.
    """
    result = StoreResult()
    claimed: set[str] = set()
    for trip in sorted(trips, key=lambda t: t.exit_time):
        row = link(trip) if link else None
        if row is not None and (row["id"] in claimed or not _same_trade(row, trip)):
            row = None
        trade_id = row["id"] if row else trip.trip_id
        claimed.add(trade_id)

        stop = None
        if row:
            ctx = row.get("market_context") or {}
            stop = ctx.get("protective_stop_price") if isinstance(ctx, dict) else None
        pnl_r = _pnl_r(trip, float(stop) if stop is not None else None)
        fields: dict[str, Any] = dict(
            trade_id=trade_id,
            timestamp=trip.exit_time.isoformat(),
            symbol=trip.symbol,
            direction=trip.direction,
            entry_price=_f(trip.avg_entry),
            exit_price=_f(trip.avg_exit),
            pnl=_f(trip.net_pnl),
            pnl_r=pnl_r,
            strategy_name=row["strategy"] if row and row.get("strategy") else strategy,
            market_context=_describe(trip, venue),
            lot_size=_f(trip.max_position),
            tags=[trip.source, "imported"],
        )
        outcome = {
            "exit_timestamp": trip.exit_time.isoformat(),
            "exit_price": _f(trip.avg_exit),
            "pnl": _f(trip.net_pnl),
            "pnl_r": pnl_r,
            "hold_duration": trip.hold_seconds,
        }

        if _episodic_exists(db, trade_id):
            # Stored by an earlier run; finish the outcome row if that run
            # stopped before writing it.
            if row is not None and row.get("exit_price") is None:
                db.update_trade_outcome(trade_id, outcome)
                result.repaired.append(trade_id)
            elif row is None and db.get_trade(trade_id) is None:
                insert_trade_record(db, **fields)
                result.repaired.append(trade_id)
            else:
                result.skipped += 1
            continue

        store_trade_memory(
            db,
            **fields,
            hold_seconds=trip.hold_seconds,
            extra_context={
                "source": trip.source,
                "notional": _f(trip.notional),
                "fees": _f(trip.fees),
                "fees_complete": trip.fees_complete,
                "adds": trip.adds,
                "entry_time": trip.entry_time.isoformat(),
                "order_ids": trip.order_ids,
            },
            compute_dqs=False,
            embed=False,
            trade_record=row is None,
        )
        if row:
            db.update_trade_outcome(trade_id, outcome)
            result.linked.append(trade_id)
        else:
            result.stored.append(trade_id)
    return result
