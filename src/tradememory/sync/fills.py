"""Turn a venue's fill history into finished trades.

A round trip starts when a symbol's position leaves zero and ends when it
returns to zero. Adds and partial exits inside it belong to the same trip;
a fill that crosses zero closes one trip and opens the next. P&L is matched
first-in, first-out.

When a venue reports the position before each fill (Hyperliquid's
``startPosition``) and it disagrees with the position the fills so far add
up to, the history has a hole (it started mid-position, or fills are
missing). The trip in progress is dropped rather than stored with an entry
price nobody knows, and tracking resumes once the position is flat again.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Callable, Iterable, Iterator

ZERO = Decimal(0)


@dataclass(frozen=True)
class Fill:
    source: str
    account: str
    symbol: str
    side: str  # "buy" | "sell"
    qty: Decimal  # > 0
    price: Decimal  # > 0
    fee: Decimal  # quote currency; a rebate is negative
    time: datetime  # timezone-aware
    fill_id: str
    order_id: str | None = None
    start_position: Decimal | None = None  # signed position before this fill, when the venue reports it
    fee_known: bool = True  # False: charged in another token, so ``fee`` is 0 and not netted

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell', got {self.side!r}")
        if self.qty <= 0 or self.price <= 0:
            raise ValueError(f"fill {self.fill_id}: qty and price must be positive")
        if self.time.tzinfo is None:
            raise ValueError(f"fill {self.fill_id}: time must be timezone-aware")

    @property
    def signed_qty(self) -> Decimal:
        return self.qty if self.side == "buy" else -self.qty


@dataclass
class RoundTrip:
    source: str
    account: str
    symbol: str
    direction: str  # "long" | "short"
    entry_time: datetime
    exit_time: datetime
    opened_qty: Decimal  # everything added while the position was open
    max_position: Decimal  # largest absolute size reached
    avg_entry: Decimal
    avg_exit: Decimal
    gross_pnl: Decimal
    fees: Decimal
    adds: int  # orders that increased the position after the opening order
    fill_ids: list[str] = field(default_factory=list)
    order_ids: list[str] = field(default_factory=list)
    fees_complete: bool = True  # False when a fill's fee was paid in another token

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.fees

    @property
    def notional(self) -> Decimal:
        """Size at its largest, valued at the average entry price."""
        return self.max_position * self.avg_entry

    @property
    def hold_seconds(self) -> int:
        return max(0, int((self.exit_time - self.entry_time).total_seconds()))

    @property
    def trip_id(self) -> str:
        key = f"{self.account}|{self.symbol}|{self.direction}|{self.fill_ids[0]}"
        return f"{self.source}-{hashlib.sha256(key.encode()).hexdigest()[:16]}"


@dataclass
class _Open:
    direction: str
    entry_time: datetime
    lots: list[list[Decimal]]  # FIFO [remaining qty, price]
    opened_qty: Decimal
    entry_cost: Decimal
    exit_qty: Decimal = ZERO
    exit_value: Decimal = ZERO
    gross: Decimal = ZERO
    fees: Decimal = ZERO
    adds: int = 0
    max_position: Decimal = ZERO
    fill_ids: list[str] = field(default_factory=list)
    order_ids: list[str] = field(default_factory=list)
    fees_complete: bool = True

    def touch(self, fill: Fill) -> None:
        if fill.fill_id not in self.fill_ids:
            self.fill_ids.append(fill.fill_id)
        if fill.order_id and fill.order_id not in self.order_ids:
            self.order_ids.append(fill.order_id)
        if not fill.fee_known:
            self.fees_complete = False


@dataclass
class BuildResult:
    trips: list[RoundTrip]  # closed, ordered by exit time
    open_positions: dict[str, Decimal]  # symbol -> signed size still open at the end
    dropped: int  # trips discarded because the history had a hole


def _sign(x: Decimal) -> int:
    return (x > 0) - (x < 0)


def _id_order(f: Fill) -> tuple:
    # Numeric ids must not sort as text ("100" before "99").
    return (f.time, len(f.fill_id), f.fill_id)


def _start(f: Fill) -> Decimal:
    assert f.start_position is not None
    return f.start_position


def _chain(group: list[Fill], start: Decimal) -> list[Fill] | None:
    """``group`` ordered so each fill starts where the previous one ended, from ``start``.

    Each fill is a step from its starting position to the position after it,
    so an order that uses every fill is an Euler trail (Hierholzer). A greedy
    walk is not enough: when the position comes back to the same size inside
    one millisecond, the first matching fill can be the wrong branch. Ties go
    to the lower id. None when no such order exists.
    """
    steps: dict[Decimal, list[Fill]] = {}
    for f in sorted(group, key=_id_order, reverse=True):  # pop() takes the lowest id
        steps.setdefault(_start(f), []).append(f)
    stack: list[tuple[Decimal, Fill | None]] = [(start, None)]
    trail: list[Fill] = []
    while stack:
        node, via = stack[-1]
        out = steps.get(node)
        if out:
            f = out.pop()
            stack.append((_start(f) + f.signed_qty, f))
        else:
            stack.pop()
            if via is not None:
                trail.append(via)
    trail.reverse()
    position = start
    for f in trail:
        if _start(f) != position:
            return None
        position += f.signed_qty
    return trail if len(trail) == len(group) else None


def _trail_start(group: list[Fill]) -> Decimal:
    """Where a group's fills start by their own account: one more step out than in."""
    balance: dict[Decimal, int] = {}
    for f in group:
        balance[_start(f)] = balance.get(_start(f), 0) + 1
        end = _start(f) + f.signed_qty
        balance[end] = balance.get(end, 0) - 1
    return next((node for node, b in balance.items() if b == 1), _start(group[0]))


def _greedy(group: list[Fill], start: Decimal) -> list[Fill]:
    """Chain as far as the starting positions allow, then id order."""
    remaining = list(group)
    out: list[Fill] = []
    current = start
    while remaining:
        nxt = next((f for f in remaining if _start(f) == current), None)
        if nxt is None:
            return out + remaining
        remaining.remove(nxt)
        out.append(nxt)
        current = _start(nxt) + nxt.signed_qty
    return out


def _execution_order(series: list[Fill], position_now: Callable[[], Decimal]) -> Iterator[Fill]:
    """Yield fills in the order they executed.

    Fills sharing a timestamp (one order sweeping several resting orders) are
    not numbered in execution order on every venue: Hyperliquid's trade ids
    inside one millisecond are not sequential. When the venue reports the
    position before each fill, chain them so each starts where the previous
    one left off. If the position before the millisecond is not where they
    start (a hole), chain from where they say they start, so the hole shows
    up once, at the first fill. Without that report, fall back to id order.
    """
    i = 0
    while i < len(series):
        j = i
        while j < len(series) and series[j].time == series[i].time:
            j += 1
        group = series[i:j]
        if len(group) > 1 and all(f.start_position is not None for f in group):
            now = position_now()
            yield from (_chain(group, now) or _chain(group, _trail_start(group)) or _greedy(group, now))
        else:
            yield from group
        i = j


def build_round_trips(fills: Iterable[Fill]) -> BuildResult:
    by_symbol: dict[str, list[Fill]] = {}
    for f in fills:
        by_symbol.setdefault(f.symbol, []).append(f)

    trips: list[RoundTrip] = []
    open_positions: dict[str, Decimal] = {}
    dropped = 0

    for symbol, series in by_symbol.items():
        series.sort(key=_id_order)
        position = ZERO
        trip: _Open | None = None
        blind = False  # inside a position whose entry we never saw
        counted = False  # the blind stretch's trade was already counted as dropped

        for f in _execution_order(series, lambda: position):
            if f.start_position is not None and f.start_position != position:
                # A hole. A trade dropped here, or a blind stretch, counts once
                # however many holes it spans.
                if trip is not None:
                    dropped += 1
                    trip = None
                    counted = True
                elif not blind:
                    counted = False
                position = f.start_position
                if blind and position == 0 and not counted:
                    dropped += 1  # the blind stretch ended inside the hole
                blind = position != 0

            s = f.signed_qty
            if blind:
                before = position
                position += s
                if position == 0 or _sign(position) != _sign(before):
                    # Flat again, or flipped through zero: the hole is behind us.
                    blind = False
                    if not counted:
                        dropped += 1
                    if position != 0:
                        trip = _open_trip(f, abs(position), f.fee * abs(position) / f.qty)
                continue

            if position == 0:
                trip = _open_trip(f, f.qty, f.fee)
                position = s
                continue

            assert trip is not None
            if _sign(s) == _sign(position):
                trip.lots.append([f.qty, f.price])
                trip.opened_qty += f.qty
                trip.entry_cost += f.qty * f.price
                trip.fees += f.fee
                if f.order_id is None or f.order_id not in trip.order_ids:
                    trip.adds += 1  # one order filled in pieces is one add
                trip.touch(f)
                position += s
                trip.max_position = max(trip.max_position, abs(position))
                continue

            closing = min(f.qty, abs(position))
            direction_sign = 1 if trip.direction == "long" else -1
            remaining = closing
            while remaining > 0:
                lot = trip.lots[0]
                take = min(lot[0], remaining)
                trip.gross += (f.price - lot[1]) * take * direction_sign
                lot[0] -= take
                remaining -= take
                if lot[0] == 0:
                    trip.lots.pop(0)
            trip.exit_qty += closing
            trip.exit_value += closing * f.price
            trip.fees += f.fee * closing / f.qty
            trip.touch(f)
            position += _sign(s) * closing

            if position == 0:
                trips.append(_finish(trip, f, symbol))
                trip = None
                leftover = f.qty - closing
                if leftover > 0:
                    trip = _open_trip(f, leftover, f.fee * leftover / f.qty)
                    position = _sign(s) * leftover

        if position != 0:
            open_positions[symbol] = position

    trips.sort(key=lambda t: (t.exit_time, t.trip_id))
    return BuildResult(trips=trips, open_positions=open_positions, dropped=dropped)


def _open_trip(f: Fill, qty: Decimal, fee: Decimal) -> _Open:
    trip = _Open(
        direction="long" if f.side == "buy" else "short",
        entry_time=f.time,
        lots=[[qty, f.price]],
        opened_qty=qty,
        entry_cost=qty * f.price,
        fees=fee,
        max_position=qty,
    )
    trip.touch(f)
    return trip


def _finish(trip: _Open, last: Fill, symbol: str) -> RoundTrip:
    return RoundTrip(
        source=last.source,
        account=last.account,
        symbol=symbol,
        direction=trip.direction,
        entry_time=trip.entry_time,
        exit_time=last.time,
        opened_qty=trip.opened_qty,
        max_position=trip.max_position,
        avg_entry=trip.entry_cost / trip.opened_qty,
        avg_exit=trip.exit_value / trip.exit_qty,
        gross_pnl=trip.gross,
        fees=trip.fees,
        adds=trip.adds,
        fill_ids=list(trip.fill_ids),
        order_ids=list(trip.order_ids),
        fees_complete=trip.fees_complete,
    )
