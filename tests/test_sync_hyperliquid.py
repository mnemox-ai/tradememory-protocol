"""Hyperliquid fill fetching and normalisation, against a stateful fake API.

The fake mirrors what a live call returned on 2026-10-02: userFillsByTime
returns up to 2,000 fills oldest first starting at startTime, and the next
page starting at the last timestamp repeats the fills of that millisecond.
"""

from decimal import Decimal as D

import pytest

from tradememory.sync.fills import build_round_trips
from tradememory.sync.hyperliquid import PAGE_SIZE, fetch_fills, perp_fills, to_fill

ADDR = "0x" + "ab" * 20


def raw(tid, time, side="B", sz="1", px="100", coin="BTC", start="0", closed="0", fee="0.01", dir_="Open Long",
        fee_token="USDC", oid=None):
    return {"tid": tid, "hash": f"h{tid}", "time": time, "side": side, "sz": sz, "px": px, "coin": coin,
            "startPosition": start, "closedPnl": closed, "fee": fee, "dir": dir_, "feeToken": fee_token,
            "oid": oid if oid is not None else tid * 10, "crossed": True}


class FakeInfoAPI:
    def __init__(self, fills):
        self.fills = sorted(fills, key=lambda f: f["time"])
        self.calls = []

    def __call__(self, body):
        self.calls.append(body)
        assert body["type"] == "userFillsByTime" and body["user"] == ADDR
        return [f for f in self.fills if f["time"] >= body["startTime"]][:PAGE_SIZE]


def test_pages_through_and_drops_the_repeated_millisecond():
    # 4,500 fills where every 10 share a millisecond, so page edges overlap.
    fills = [raw(i, 1_000_000 + i // 10) for i in range(4500)]
    api = FakeInfoAPI(fills)
    got = fetch_fills(ADDR, post=api)
    assert [f["tid"] for f in got] == list(range(4500))
    assert len(api.calls) == 3


def test_stops_when_a_page_brings_nothing_new():
    # 2,000 fills in one millisecond: the second page would repeat the first.
    api = FakeInfoAPI([raw(i, 5_000) for i in range(PAGE_SIZE)])
    assert len(fetch_fills(ADDR, post=api)) == PAGE_SIZE
    assert len(api.calls) == 2


def test_rejects_something_that_is_not_an_address():
    with pytest.raises(ValueError):
        fetch_fills("vitalik.eth", post=lambda body: [])


def test_normalises_side_position_fee_and_symbol():
    f = to_fill(raw(7, 1_700_000_000_000, side="A", sz="0.5", px="64000.5", coin="btc", start="-1.5",
                    fee="0.2", fee_token="HYPE"), ADDR.upper().replace("0X", "0x"))
    assert (f.side, f.qty, f.price, f.symbol) == ("sell", D("0.5"), D("64000.5"), "BTC")
    assert f.start_position == D("-1.5") and f.fee == 0  # fee paid in another token is not netted
    assert f.account == ADDR and f.order_id == "70"


def test_spot_fills_are_skipped():
    fills, spot = perp_fills([
        raw(1, 1, coin="@107", dir_="Buy"), raw(2, 2, coin="PURR/USDC", dir_="Buy"),
        raw(3, 3, dir_="Sell"), raw(4, 4),
    ], ADDR)
    assert spot == 3 and [f.fill_id for f in fills] == ["4"]


def test_rebuilt_profit_matches_the_venues_closed_pnl():
    # Open 2 long at 100 and 110, close 1 at 120 (venue: +20), close 1 at 105 (venue: -5).
    history = [
        raw(1, 1000, sz="1", px="100", start="0", dir_="Open Long"),
        raw(2, 2000, sz="1", px="110", start="1", dir_="Open Long"),
        raw(3, 3000, side="A", sz="1", px="120", start="2", closed="20", dir_="Close Long"),
        raw(4, 4000, side="A", sz="1", px="105", start="1", closed="-5", dir_="Close Long"),
    ]
    fills, _ = perp_fills(history, ADDR)
    (trip,) = build_round_trips(fills).trips
    assert trip.gross_pnl == sum(D(f["closedPnl"]) for f in history)
    assert trip.fees == D("0.04")
