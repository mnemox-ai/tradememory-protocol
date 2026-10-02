"""Rebuilding finished trades from fills: FIFO P&L, scale-ins, flips, holes."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from tradememory.sync.fills import Fill, build_round_trips

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
_n = 0


def fill(side, qty, price, minutes=0, symbol="BTC", fee="0", start=None, order=None):
    global _n
    _n += 1
    return Fill(
        source="test", account="acct", symbol=symbol, side=side, qty=D(str(qty)), price=D(str(price)),
        fee=D(fee), time=T0 + timedelta(minutes=minutes), fill_id=f"f{_n}",
        order_id=order or f"o{_n}", start_position=None if start is None else D(str(start)),
    )


def test_one_long_trade():
    r = build_round_trips([fill("buy", 1, 100), fill("sell", 1, 110, minutes=30)])
    (t,) = r.trips
    assert (t.direction, t.gross_pnl, t.avg_entry, t.avg_exit) == ("long", D(10), D(100), D(110))
    assert t.hold_seconds == 1800 and r.open_positions == {} and r.dropped == 0


def test_scale_in_and_partial_exits_match_first_in_first_out():
    r = build_round_trips([
        fill("buy", 1, 100), fill("buy", 1, 110, minutes=1),
        fill("sell", 1, 120, minutes=2),  # closes the 100 lot: +20
        fill("sell", 1, 105, minutes=3),  # closes the 110 lot: -5
    ])
    (t,) = r.trips
    assert t.gross_pnl == D(15)
    assert (t.adds, t.max_position, t.opened_qty) == (1, D(2), D(2))
    assert (t.avg_entry, t.avg_exit) == (D(105), D("112.5"))


def test_short_trade_profits_when_price_falls():
    (t,) = build_round_trips([fill("sell", 2, 50), fill("buy", 2, 40, minutes=5)]).trips
    assert (t.direction, t.gross_pnl) == ("short", D(20))


def test_a_fill_through_zero_closes_one_trade_and_opens_the_next():
    r = build_round_trips([
        fill("buy", 1, 100),
        fill("sell", 3, 90, minutes=1, fee="0.3"),  # -10 on the long, then short 2 @ 90
        fill("buy", 2, 80, minutes=2),  # +20 on the short
    ])
    first, second = r.trips
    assert (first.direction, first.gross_pnl, first.fees) == ("long", D(-10), D("0.1"))
    assert (second.direction, second.gross_pnl, second.fees) == ("short", D(20), D("0.2"))
    assert first.trip_id != second.trip_id
    assert first.net_pnl == D("-10.1")


def test_history_that_starts_mid_position_is_dropped_not_guessed():
    r = build_round_trips([
        fill("sell", 2, 100, start=2),  # we never saw the 2 being bought
        fill("buy", 1, 100, minutes=1, start=0),
        fill("sell", 1, 105, minutes=2, start=1),
    ])
    assert r.dropped == 1
    (t,) = r.trips
    assert t.gross_pnl == D(5)


def test_adding_to_an_unknown_position_stays_unknown_until_flat():
    r = build_round_trips([
        fill("buy", 1, 100, start=1),  # 1 already open, unknown entry; now 2
        fill("sell", 2, 90, minutes=1, start=2),  # flat again
    ])
    assert r.trips == [] and r.dropped == 1 and r.open_positions == {}


def test_a_gap_in_the_middle_drops_the_trade_in_progress():
    r = build_round_trips([
        fill("buy", 1, 100, start=0),
        # a missing fill bought 1 more; the venue says we held 2 here
        fill("sell", 2, 110, minutes=5, start=2),
    ])
    assert r.trips == [] and r.dropped == 1


def test_open_position_is_reported_not_stored():
    r = build_round_trips([fill("buy", D("0.0123"), 64000), fill("sell", D("0.005"), 65000, minutes=1)])
    assert r.trips == [] and r.open_positions == {"BTC": D("0.0073")}


def test_symbols_are_independent_and_ids_are_stable():
    fills = [fill("buy", 1, 10, symbol="ETH"), fill("buy", 1, 100), fill("sell", 1, 11, minutes=1, symbol="ETH"),
             fill("sell", 1, 90, minutes=2)]
    a = build_round_trips(fills)
    b = build_round_trips(list(reversed(fills)))
    assert [t.trip_id for t in a.trips] == [t.trip_id for t in b.trips]
    assert {t.symbol: t.gross_pnl for t in a.trips} == {"ETH": D(1), "BTC": D(-10)}


@pytest.mark.parametrize("kwargs", [
    {"side": "hold"}, {"qty": D(0)}, {"price": D(-1)}, {"time": datetime(2026, 9, 1)},
])
def test_bad_fills_are_rejected(kwargs):
    base = dict(source="t", account="a", symbol="X", side="buy", qty=D(1), price=D(1), fee=D(0), time=T0, fill_id="x")
    base.update(kwargs)
    with pytest.raises(ValueError):
        Fill(**base)


def test_fills_in_one_millisecond_keep_numeric_order():
    # Sorted as text, fill "100" would come before "99" and the history
    # would look broken (2026-10-02: 703 of 9,409 live fills dropped).
    same = T0
    buy = Fill(source="t", account="a", symbol="ETH", side="buy", qty=D(1), price=D(100), fee=D(0),
               time=same, fill_id="99", start_position=D(0))
    sell = Fill(source="t", account="a", symbol="ETH", side="sell", qty=D(1), price=D(101), fee=D(0),
                time=same, fill_id="100", start_position=D(1))
    r = build_round_trips([sell, buy])
    assert r.dropped == 0 and len(r.trips) == 1 and r.trips[0].gross_pnl == D(1)


def test_one_millisecond_sweep_is_ordered_by_the_position_chain():
    # Live Hyperliquid, 2026-10-02: one order swept several resting orders in
    # the same millisecond and the trade ids were not in execution order. The
    # position before each fill is the only reliable order.
    t = T0
    legs = [  # (fill id, qty, position before)
        ("5629", 17067, 84076), ("2888", 30497, 20000), ("3026", 34503, 211330),
        ("3208", 63987, 147343), ("6842", 20000, 127343), ("9106", 33579, 50497), ("1069", 26200, 101143),
    ]
    sweep = [Fill(source="t", account="a", symbol="SKR", side="buy", qty=D(q), price=D(1), fee=D(0), time=t,
                  fill_id=fid, start_position=D(sp)) for fid, q, sp in legs]
    opener = Fill(source="t", account="a", symbol="SKR", side="buy", qty=D(20000), price=D(1), fee=D(0),
                  time=t - timedelta(seconds=1), fill_id="1", start_position=D(0))
    closer = Fill(source="t", account="a", symbol="SKR", side="sell", qty=D(245833), price=D(2), fee=D(0),
                  time=t + timedelta(seconds=1), fill_id="2", start_position=D(245833))
    r = build_round_trips([closer, *sweep, opener])
    assert r.dropped == 0 and len(r.trips) == 1
    assert r.trips[0].gross_pnl == D(245833) and r.trips[0].adds == 7
