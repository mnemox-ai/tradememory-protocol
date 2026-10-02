"""Write finished round trips into TradeMemory, once each.

A trip's id is derived from its first fill, so running a sync again stores
only the trips that were not there before. A trip the broker brake already
recorded (its opening order went through the proxy) keeps the brake's id:
the outcome is written onto that row instead of creating a second one, and
the trip enters episodic memory under the same id so recall can see it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Optional

from ..db import Database
from ..trade_store import store_trade_memory
from .fills import RoundTrip

Linker = Callable[[RoundTrip], Optional[dict]]


@dataclass
class StoreResult:
    stored: list[str] = field(default_factory=list)
    linked: list[str] = field(default_factory=list)  # brake rows that got their outcome
    skipped: int = 0  # already stored


def _f(x: Decimal) -> float:
    return float(x)


def _episodic_exists(db: Database, memory_id: str) -> bool:
    with db.get_connection() as conn:
        return conn.execute("SELECT 1 FROM episodic_memory WHERE id = ?", (memory_id,)).fetchone() is not None


def _describe(trip: RoundTrip, venue: str) -> str:
    hours = trip.hold_seconds / 3600
    held = f"{hours:.1f}h" if hours >= 1 else f"{trip.hold_seconds // 60}m"
    return (
        f"{trip.direction} {trip.symbol} on {venue}, max size {trip.max_position.normalize():f} "
        f"(about {_f(trip.notional):,.0f} notional), held {held}, {trip.adds} add(s)"
    )


def _pnl_r(trip: RoundTrip, stop: Optional[float]) -> Optional[float]:
    """R-multiple from the protective stop recorded at entry, when there was one."""
    if stop is None:
        return None
    risk = abs(_f(trip.avg_entry) - stop) * _f(trip.max_position)
    return _f(trip.net_pnl) / risk if risk > 0 else None


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
    """
    result = StoreResult()
    for trip in sorted(trips, key=lambda t: t.exit_time):
        row = link(trip) if link else None
        trade_id = row["id"] if row else trip.trip_id
        if _episodic_exists(db, trade_id):
            result.skipped += 1
            continue

        stop = None
        if row:
            ctx = row.get("market_context") or {}
            stop = ctx.get("protective_stop_price") if isinstance(ctx, dict) else None
        pnl_r = _pnl_r(trip, float(stop) if stop is not None else None)

        store_trade_memory(
            db,
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
            hold_seconds=trip.hold_seconds,
            lot_size=_f(trip.max_position),
            extra_context={
                "source": trip.source,
                "notional": _f(trip.notional),
                "fees": _f(trip.fees),
                "adds": trip.adds,
                "entry_time": trip.entry_time.isoformat(),
                "order_ids": trip.order_ids,
            },
            tags=[trip.source, "imported"],
            compute_dqs=False,
            embed=False,
            trade_record=row is None,
        )
        if row:
            db.update_trade_outcome(trade_id, {
                "exit_timestamp": trip.exit_time.isoformat(),
                "exit_price": _f(trip.avg_exit),
                "pnl": _f(trip.net_pnl),
                "pnl_r": pnl_r,
                "hold_duration": trip.hold_seconds,
            })
            result.linked.append(trade_id)
        else:
            result.stored.append(trade_id)
    return result
