"""Storing rebuilt trades in memory once each, closing the brake's loop, and the loss report."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from tradememory.db import Database
from tradememory.sync.fills import RoundTrip
from tradememory.sync.report import loss_patterns, render_report
from tradememory.sync.store import store_round_trips

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


@pytest.fixture()
def db():
    path = os.path.join(tempfile.mkdtemp(), "sync.db")
    return Database(db_path=path)


def trip(n, net, size=1, symbol="BTC", hours=1, start_hour=0, direction="long", order_ids=None):
    entry = T0 + timedelta(hours=start_hour)
    price = D(100)
    return RoundTrip(
        source="test", account="a", symbol=symbol, direction=direction,
        entry_time=entry, exit_time=entry + timedelta(hours=hours),
        opened_qty=D(size), max_position=D(size), avg_entry=price,
        avg_exit=price + D(net) / D(size), gross_pnl=D(net), fees=D(0), adds=0,
        fill_ids=[f"f{n}"], order_ids=order_ids or [f"o{n}"],
    )


def _count(db, table):
    with db.get_connection() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_trips_are_stored_once(db):
    trips = [trip(1, -50, start_hour=0), trip(2, 30, start_hour=2)]
    first = store_round_trips(db, trips, venue="Test", strategy="imported")
    again = store_round_trips(db, trips, venue="Test", strategy="imported")
    assert len(first.stored) == 2 and again.skipped == 2 and not again.stored
    assert _count(db, "episodic_memory") == 2 and _count(db, "trade_records") == 2
    row = db.get_trade(trips[0].trip_id)
    assert row["pnl"] == -50.0 and row["lot_size"] == 1.0 and row["strategy"] == "imported"


def test_a_brake_trade_gets_its_outcome_instead_of_a_second_row(db):
    db.insert_trade({
        "id": "ord-ORDER1", "timestamp": T0.isoformat(), "symbol": "AAPL", "direction": "long",
        "lot_size": 2.0, "strategy": "agent-1", "confidence": 0.5, "reasoning": "forwarded by the proxy",
        "market_context": {"entry_price": 100.0, "protective_stop_price": 95.0}, "references": [],
        "exit_timestamp": None, "exit_price": None, "pnl": None, "pnl_r": None, "hold_duration": None,
        "exit_reasoning": None, "slippage": None, "execution_quality": None, "lessons": None,
        "tags": ["proxy"], "grade": None,
    })
    t = trip(9, -10, size=2, symbol="AAPL", order_ids=["ORDER1", "STOPLEG"])
    result = store_round_trips(db, [t], venue="Alpaca", strategy="alpaca",
                               link=lambda tr: db.get_trade(f"ord-{tr.order_ids[0]}"))
    assert result.linked == ["ord-ORDER1"] and not result.stored
    row = db.get_trade("ord-ORDER1")
    assert row["pnl"] == -10.0 and row["exit_price"] == 95.0
    assert row["pnl_r"] == pytest.approx(-1.0)  # risk = (100 - 95) * 2
    assert _count(db, "trade_records") == 1 and _count(db, "episodic_memory") == 1


def _brake_row(db, order="ORDER1", symbol="AAPL", direction="long", stop=95.0):
    db.insert_trade({
        "id": f"ord-{order}", "timestamp": T0.isoformat(), "symbol": symbol, "direction": direction,
        "lot_size": 2.0, "strategy": "agent-1", "confidence": 0.5, "reasoning": "forwarded by the proxy",
        "market_context": {"entry_price": 100.0, "protective_stop_price": stop}, "references": [],
        "exit_timestamp": None, "exit_price": None, "pnl": None, "pnl_r": None, "hold_duration": None,
        "exit_reasoning": None, "slippage": None, "execution_quality": None, "lessons": None,
        "tags": ["proxy"], "grade": None,
    })


def _link(db):
    return lambda tr: db.get_trade(f"ord-{tr.order_ids[0]}")


def _fail_once(monkeypatch, obj, name):
    real = getattr(obj, name)
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("process killed here")
        return real(*args, **kwargs)
    monkeypatch.setattr(obj, name, flaky)


def test_an_interrupted_run_gives_the_brake_row_its_outcome_next_time(db, monkeypatch):
    _brake_row(db)
    t = trip(9, -10, size=2, symbol="AAPL", order_ids=["ORDER1"])
    _fail_once(monkeypatch, db, "update_trade_outcome")
    with pytest.raises(RuntimeError):
        store_round_trips(db, [t], venue="Alpaca", strategy="alpaca", link=_link(db))
    assert db.get_trade("ord-ORDER1")["exit_price"] is None  # memory written, outcome not
    again = store_round_trips(db, [t], venue="Alpaca", strategy="alpaca", link=_link(db))
    assert again.repaired == ["ord-ORDER1"] and again.skipped == 0
    assert db.get_trade("ord-ORDER1")["pnl"] == -10.0
    third = store_round_trips(db, [t], venue="Alpaca", strategy="alpaca", link=_link(db))
    assert third.skipped == 1 and not third.repaired
    assert _count(db, "episodic_memory") == 1 and _count(db, "trade_records") == 1


def test_an_interrupted_run_gets_its_trade_record_next_time(db, monkeypatch):
    t = trip(1, -50)
    _fail_once(monkeypatch, db, "insert_trade")
    with pytest.raises(RuntimeError):
        store_round_trips(db, [t], venue="Test", strategy="imported")
    assert db.get_trade(t.trip_id) is None
    again = store_round_trips(db, [t], venue="Test", strategy="imported")
    assert again.repaired == [t.trip_id]
    assert db.get_trade(t.trip_id)["pnl"] == -50.0 and _count(db, "episodic_memory") == 1


def test_a_brake_row_for_another_symbol_or_direction_is_not_used(db):
    _brake_row(db, order="ORDER1", direction="short")
    t = trip(9, -10, size=2, symbol="AAPL", order_ids=["ORDER1"])
    result = store_round_trips(db, [t], venue="Alpaca", strategy="alpaca", link=_link(db))
    assert result.stored == [t.trip_id] and not result.linked
    assert db.get_trade("ord-ORDER1")["exit_price"] is None


def test_one_brake_row_goes_to_one_trip(db):
    # One working order filled on both sides of a flat moment: two trips name it.
    _brake_row(db, order="ORDER1")
    first = trip(1, -10, symbol="AAPL", order_ids=["ORDER1", "X1"], start_hour=0)
    second = trip(2, 5, symbol="AAPL", order_ids=["ORDER1", "X2"], start_hour=3)
    result = store_round_trips(db, [second, first], venue="Alpaca", strategy="alpaca", link=_link(db))
    assert result.linked == ["ord-ORDER1"] and result.stored == [second.trip_id]
    assert db.get_trade("ord-ORDER1")["pnl"] == -10.0 and db.get_trade(second.trip_id)["pnl"] == 5.0
    again = store_round_trips(db, [second, first], venue="Alpaca", strategy="alpaca", link=_link(db))
    assert again.skipped == 2 and not again.repaired


def test_a_crypto_brake_row_written_with_a_slash_still_links(db):
    _brake_row(db, order="C1", symbol="BTC/USD")
    t = trip(4, 12, symbol="BTCUSD", order_ids=["C1"])
    assert store_round_trips(db, [t], venue="Alpaca", strategy="alpaca", link=_link(db)).linked == ["ord-C1"]


def test_a_trade_with_unpriced_fees_says_so(db):
    t = trip(5, 20)
    t.fees_complete = False
    store_round_trips(db, [t], venue="Hyperliquid", strategy="hyperliquid")
    (ep,) = db.query_episodic(limit=5)
    assert ep["context_json"]["fees_complete"] is False
    assert "not netted" in ep["context_json"]["description"]


@pytest.mark.asyncio
async def test_imported_losses_come_back_first_before_a_trade(db):
    import tradememory.mcp_server as mod
    from tradememory.mcp_server import recall_memories

    store_round_trips(db, [trip(1, 80, start_hour=0), trip(2, -300, start_hour=3), trip(3, 40, start_hour=6)],
                      venue="Hyperliquid", strategy="hyperliquid")
    mod._db = db
    try:
        result = await recall_memories(symbol="BTC", market_context="long BTC", memory_types=["episodic"],
                                       use_hybrid=False, order="losses_first", limit=3)
    finally:
        mod._db = None
    assert result["memories"][0]["pnl"] == -300.0


def test_report_sees_sizing_up_after_losses():
    trips = []
    hour = 0
    for i in range(6):
        trips += [trip(f"{i}a", -20, start_hour=hour), trip(f"{i}b", -20, start_hour=hour + 2),
                  trip(f"{i}c", -90, size=3, start_hour=hour + 4)]  # 3x size right after two losses
        trips.append(trip(f"{i}d", 25, start_hour=hour + 6))
        hour += 8
    stats = loss_patterns(trips)
    s = stats["after_losing_streak"]
    assert s["enough_data"] and s["sized_up"] >= 6
    assert s["sized_up_result"]["net_pnl"] <= -540
    text = render_report(stats, title="t")
    assert "Not investment advice" in text and "should" not in text.lower()


def test_report_is_honest_about_small_samples():
    stats = loss_patterns([trip(1, -5), trip(2, 5, start_hour=2)])
    text = render_report(stats, title="t")
    assert "not enough trades to say" in text
    assert render_report(loss_patterns([]), title="t").endswith("No closed trades found.")
