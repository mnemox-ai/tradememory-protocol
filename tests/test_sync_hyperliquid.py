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
    got, complete = fetch_fills(ADDR, post=api)
    assert [f["tid"] for f in got] == list(range(4500))
    assert complete and len(api.calls) == 3


def test_a_full_page_inside_one_millisecond_is_skipped_and_flagged():
    # 2,000 fills in one millisecond: asking again from that time returns the
    # same page forever. Move past it, keep what comes after, say it is partial.
    api = FakeInfoAPI([raw(i, 5_000) for i in range(PAGE_SIZE)] + [raw(PAGE_SIZE, 6_000)])
    got, complete = fetch_fills(ADDR, post=api)
    assert len(got) == PAGE_SIZE + 1 and got[-1]["time"] == 6_000
    assert not complete and len(api.calls) == 3


def test_running_out_of_pages_is_flagged_not_silent(monkeypatch):
    from tradememory.sync import hyperliquid

    monkeypatch.setattr(hyperliquid, "MAX_PAGES", 3)
    api = FakeInfoAPI([raw(i, 1_000 + i) for i in range(3 * PAGE_SIZE + 100)])
    got, complete = fetch_fills(ADDR, post=api)
    assert not complete and len(api.calls) == 3


def test_rate_limit_backoff_outlasts_the_one_minute_window(monkeypatch):
    # The weight limit is per minute; 2026-10-02 probing hit 429 after
    # retries that waited 15 s in total.
    import io
    import urllib.error

    from tradememory.sync import hyperliquid

    calls, waits = [], []

    def urlopen(request, timeout):
        calls.append(1)
        if len(calls) <= 6:
            raise urllib.error.HTTPError(hyperliquid.API_URL, 429, "Too Many Requests", {}, None)
        return io.BytesIO(b"[]")

    monkeypatch.setattr(hyperliquid.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(hyperliquid.time, "sleep", waits.append)
    assert hyperliquid._post({"type": "userFillsByTime"}) == []
    assert sum(waits) >= 60


def test_rejects_something_that_is_not_an_address():
    with pytest.raises(ValueError):
        fetch_fills("vitalik.eth", post=lambda body: [])


def test_normalises_side_position_fee_and_symbol():
    f = to_fill(raw(7, 1_700_000_000_000, side="A", sz="0.5", px="64000.5", coin="btc", start="-1.5",
                    fee="0.2", fee_token="HYPE"), ADDR.upper().replace("0X", "0x"))
    assert (f.side, f.qty, f.price, f.symbol) == ("sell", D("0.5"), D("64000.5"), "BTC")
    assert f.start_position == D("-1.5") and f.fee == 0  # fee paid in another token is not netted
    assert not f.fee_known and to_fill(raw(8, 1), ADDR).fee_known
    assert f.account == ADDR and f.order_id == "70"


def test_a_fill_without_a_fee_is_malformed_not_free():
    record = raw(9, 1)
    del record["fee"]
    with pytest.raises(ValueError):
        to_fill(record, ADDR)


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


def test_an_outcome_contract_settling_at_zero_closes_as_a_full_loss():
    # Live shape (2026-10-05): a "#..." outcome market closes the losing side with a
    # Settlement fill at px 0.0; one address in ten in a leaderboard sample had one,
    # and rejecting price 0 used to stop the whole sync.
    history = [
        raw(1, 1000, sz="1773", px="0.333", coin="#6951", start="0", dir_="Open Long", fee="0"),
        raw(2, 2000, side="A", sz="1773", px="0.0", coin="#6951", start="1773", closed="-590.409",
            dir_="Settlement", fee="0"),
    ]
    fills, spot = perp_fills(history, ADDR)
    (trip,) = build_round_trips(fills).trips
    assert spot == 0 and trip.symbol == "#6951"
    assert trip.avg_exit == 0 and trip.gross_pnl == D("-590.409")


def test_a_negative_price_is_still_refused():
    with pytest.raises(ValueError, match="must not be negative"):
        perp_fills([raw(1, 1000, px="-1")], ADDR)
