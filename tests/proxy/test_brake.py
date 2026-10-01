"""End-to-end tests of the brake against a stateful fake broker MCP.

Every test that expects an ALLOW asserts the upstream actually received the
order, and every test that expects a DENY asserts it did not. That pairing is
the positive control: a brake that blocks everything and a brake that blocks
nothing both fail this file.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal

import pytest

pytest.importorskip("mnemox_control")

from fastmcp import Client  # noqa: E402

from tradememory.audit.chain import ChainBuilder  # noqa: E402
from tradememory.db import Database  # noqa: E402
from tradememory.proxy import alpaca  # noqa: E402
from tradememory.proxy.policy import (  # noqa: E402
    load_policy,
    pnl_window,
    policy_to_json,
    seal_policy_file,
    template_policy,
)
from tradememory.proxy.server import build_proxy  # noqa: E402
from tradememory.proxy.state import ProxyState  # noqa: E402

from fake_alpaca import FakeAlpaca  # noqa: E402

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(sys.version_info < (3, 12), reason="proxy extra needs Python 3.12+"),
]

BRACKET = {"order_class": "bracket", "stop_loss_stop_price": "185", "take_profit_limit_price": "200"}


def order(symbol: str = "AAPL", side: str = "buy", qty: str | None = "1", cid: str | None = "c-1", **extra) -> dict:
    args = {"symbol": symbol, "side": side, "type": "market", "time_in_force": "day", **extra}
    if qty is not None:
        args["qty"] = qty
    if cid is not None:
        args["client_order_id"] = cid
    return args


class World:
    def __init__(self, tmp_path, **policy_overrides):
        self.fake = FakeAlpaca()
        settings = {
            "max_order_notional": "1000",
            "max_position_notional": "5000",
            "approval_notional": "1000",
            "require_protective_stop": True,
        }
        settings.update(policy_overrides)
        symbols = settings.pop("allowed_symbols", ["AAPL", "MSFT"])
        self.policy = template_policy(
            broker="alpaca", account_id="acct-1", owner_id="sean", allowed_symbols=symbols, **settings
        )
        self.policy_path = tmp_path / "policy.json"
        self.policy_path.write_text(policy_to_json(self.policy), encoding="utf-8")
        self.state_path = tmp_path / "state.json"
        self.db = Database(db_path=str(tmp_path / "tm.db"))
        self.server, self.brake = build_proxy(
            self.fake.server(), policy_path=self.policy_path, state_path=self.state_path, db=self.db
        )

    async def call(self, name: str, args: dict | None = None):
        async with Client(self.server) as client:
            return await client.call_tool(name, args or {}, raise_on_error=False)

    def events(self) -> list[tuple[str, str, dict]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "select tool, tier, factors_json from decision_events order by rowid"
            ).fetchall()
        return [(r[0], r[1], json.loads(r[2])) for r in rows]

    def tiers(self) -> list[str]:
        return [e[1] for e in self.events()]

    def chain(self) -> dict:
        with self.db.get_connection() as conn:
            return ChainBuilder(conn).verify_chain()

    def trade_count(self) -> int:
        with self.db.get_connection() as conn:
            return conn.execute("select count(*) from trade_records").fetchone()[0]

    def second_state(self) -> ProxyState:
        """What the CLI does: a separate ProxyState on the same file."""
        return ProxyState(self.state_path)


def codes(result) -> set[str]:
    rules = result.structured_content.get("denied_rules") or result.structured_content.get("rules") or []
    return {r["code"] for r in rules}


# --------------------------------------------------------------------------- pass-through


async def test_read_tools_pass_through_with_envelope_intact(tmp_path):
    w = World(tmp_path)
    res = await w.call("get_account_info")
    assert "_alpaca_mcp_security" in res.structured_content
    assert alpaca.unwrap(res.structured_content)["id"] == "acct-1"
    assert w.events() == []


async def test_benign_mutations_pass_through_and_are_recorded(tmp_path):
    w = World(tmp_path)
    res = await w.call("create_watchlist", {"name": "tech", "symbols": ["AAPL"]})
    assert alpaca.unwrap(res.structured_content)["name"] == "tech"
    assert w.tiers() == ["PASS_THROUGH"]


async def test_unknown_mutating_tool_is_refused(tmp_path):
    w = World(tmp_path)
    res = await w.call("transfer_funds", {"amount": "100"})
    assert res.structured_content["decision"] == "DENY" and "PROXY_UNSUPPORTED_TOOL" in codes(res)
    assert w.fake.placed == []


# --------------------------------------------------------------------------- denies


async def test_symbol_not_allowed_is_denied_and_chained(tmp_path):
    w = World(tmp_path)
    res = await w.call("place_stock_order", order("TSLA", cid="t1", **BRACKET))
    s = res.structured_content
    assert s["decision"] == "DENY" and s["order_placed"] is False
    assert "SYMBOL_NOT_ALLOWED" in codes(res)
    assert w.fake.placed == []
    events = w.events()
    assert [e[1] for e in events] == ["DENY"]
    assert events[0][2]["evaluation"]["decision"] == "DENY"
    assert events[0][2]["intent"]["symbol"] == "TSLA"
    chain = w.chain()
    assert chain["verified"] is True and chain["checked_count"] == 1


async def test_entry_without_protective_stop_is_denied(tmp_path):
    w = World(tmp_path)
    res = await w.call("place_stock_order", order(cid="ns"))
    assert "PROTECTIVE_STOP_REQUIRED" in codes(res)
    assert w.fake.placed == []


async def test_stop_loss_without_bracket_class_does_not_count_as_protection(tmp_path):
    w = World(tmp_path)
    res = await w.call("place_stock_order", order(cid="naked", stop_loss_stop_price="185"))
    assert res.structured_content["decision"] == "DENY"
    assert "PROTECTIVE_STOP_REQUIRED" in codes(res)
    assert w.fake.placed == []


async def test_order_notional_over_limit_is_denied(tmp_path):
    w = World(tmp_path)
    res = await w.call("place_stock_order", order(qty="10", cid="big", **BRACKET))  # 1900 > 1000
    assert "ORDER_NOTIONAL_EXCEEDED" in codes(res)
    assert w.fake.placed == []


async def test_position_limit_counts_existing_exposure(tmp_path):
    w = World(tmp_path, max_position_notional="1500")
    w.fake.positions.append({"symbol": "AAPL", "qty": "5", "side": "long"})  # 950 already held
    res = await w.call("place_stock_order", order(qty="5", cid="p", **BRACKET))  # +950 -> 1900
    assert "POSITION_NOTIONAL_EXCEEDED" in codes(res)
    assert w.fake.placed == []


async def test_daily_loss_limit_blocks_new_entries(tmp_path):
    w = World(tmp_path, max_daily_loss="100")
    w.fake.account.update({"equity": "9850", "last_equity": "10000"})
    res = await w.call("place_stock_order", order(cid="dl", **BRACKET))
    assert "DAILY_LOSS_LIMIT_REACHED" in codes(res)
    assert w.fake.placed == []


async def test_unsupported_order_type_is_denied_not_forwarded(tmp_path):
    w = World(tmp_path)
    res = await w.call(
        "place_stock_order",
        order(type="stop_limit", stop_price="188", limit_price="187", cid="sl", **BRACKET),
    )
    assert res.structured_content["decision"] == "DENY"
    assert "PROXY_FAIL_CLOSED" in codes(res)
    assert w.fake.placed == []


async def test_qty_and_notional_together_are_refused(tmp_path):
    w = World(tmp_path)
    res = await w.call("place_stock_order", order(qty="1", cid="both", notional="500", **BRACKET))
    assert res.structured_content["decision"] == "DENY"
    assert w.fake.placed == []


async def test_missing_client_order_id_is_refused(tmp_path):
    w = World(tmp_path)
    res = await w.call("place_stock_order", order(cid=None, **BRACKET))
    assert "PROXY_CLIENT_ORDER_ID_REQUIRED" in codes(res)
    assert w.fake.placed == []
    assert w.tiers() == ["DENY"]


async def test_unsupported_tools_are_denied(tmp_path):
    w = World(tmp_path)
    r1 = await w.call("place_option_order", {"qty": "1", "symbol": "AAPL250117C00190000", "side": "buy"})
    r2 = await w.call("replace_order_by_id", {"order_id": "ord-1", "qty": "5"})
    assert r1.structured_content["decision"] == "DENY" and "PROXY_UNSUPPORTED_TOOL" in codes(r1)
    assert r2.structured_content["decision"] == "DENY" and "PROXY_UNSUPPORTED_TOOL" in codes(r2)
    assert w.fake.placed == []
    assert w.tiers() == ["DENY", "DENY"]
    assert w.chain()["verified"] is True


# --------------------------------------------------------------------------- allows


async def test_bracket_order_within_policy_is_forwarded_exactly_once(tmp_path):
    w = World(tmp_path)
    args = order(cid="c-1", **BRACKET)
    res = await w.call("place_stock_order", args)
    s = res.structured_content
    assert s["decision"] == "ALLOW" and s["order_placed"] is True and s.get("replayed") is None
    assert s["approved_by_owner"] is False
    assert isinstance(s["prior_outcomes"], list)
    assert len(w.fake.placed) == 1 and w.fake.placed[0]["client_order_id"] == "c-1"
    assert alpaca.unwrap(s["upstream"])["id"] == "ord-1"
    assert w.fake.positions == [{"symbol": "AAPL", "qty": "1", "side": "long"}]
    assert w.trade_count() == 1
    assert w.tiers() == ["ALLOW"]
    assert w.chain()["verified"] is True

    # A retry with the same client_order_id replays the first result and places nothing new.
    res2 = await w.call("place_stock_order", args)
    s2 = res2.structured_content
    assert s2["decision"] == "ALLOW" and s2["replayed"] is True
    assert alpaca.unwrap(s2["upstream"])["id"] == "ord-1"
    assert len(w.fake.placed) == 1
    assert w.tiers() == ["ALLOW", "REPLAY"]
    assert w.chain()["verified"] is True and w.chain()["checked_count"] >= 3  # 2 decisions + 1 trade


async def test_client_order_id_reused_with_different_terms_is_refused(tmp_path):
    w = World(tmp_path)
    await w.call("place_stock_order", order(cid="c-1", **BRACKET))
    res = await w.call("place_stock_order", order(qty="2", cid="c-1", **BRACKET))
    assert "PROXY_CLIENT_ORDER_ID_REUSED" in codes(res)
    assert len(w.fake.placed) == 1
    assert w.tiers() == ["ALLOW", "DENY"]


async def test_bracket_legs_do_not_count_as_new_exposure(tmp_path):
    """After a bracket fills, its stop and take-profit legs rest as open sell orders; they close, not open."""
    w = World(tmp_path, max_position_notional="1000")
    await w.call("place_stock_order", order(qty="2", cid="first", **BRACKET))  # 380 held, two legs resting
    open_rows = [o for o in w.fake.orders if o["status"] == "new"]
    assert len(open_rows) == 2 and {o["position_intent"] for o in open_rows} == {"sell_to_close"}
    res = await w.call("place_stock_order", order(qty="2", cid="second", **BRACKET))  # +380 -> 760 < 1000
    assert res.structured_content["decision"] == "ALLOW", codes(res)
    assert len(w.fake.placed) == 2


async def test_notional_order_is_sized_from_the_mark(tmp_path):
    w = World(tmp_path)
    base = {"symbol": "AAPL", "side": "buy", "type": "market", "time_in_force": "day", **BRACKET}
    ok = await w.call("place_stock_order", {**base, "notional": "950", "client_order_id": "n1"})
    assert ok.structured_content["decision"] == "ALLOW"
    assert w.events()[-1][2]["intent"]["quantity"] == "5.000000000"
    too_big = await w.call("place_stock_order", {**base, "notional": "1500", "client_order_id": "n2"})
    assert "ORDER_NOTIONAL_EXCEEDED" in codes(too_big)
    assert len(w.fake.placed) == 1


async def test_one_sided_book_falls_back_to_last_trade(tmp_path):
    w = World(tmp_path)
    w.fake.one_sided_quotes = True
    res = await w.call("place_stock_order", order(cid="t", **BRACKET))
    assert res.structured_content["decision"] == "ALLOW"
    assert ("get_stock_latest_trade", {"symbols": "AAPL"}) in w.fake.calls
    assert len(w.fake.placed) == 1


async def test_closed_market_prices_from_last_trade_not_stale_book(tmp_path):
    w = World(tmp_path)
    w.fake.is_open = False
    w.fake.quotes["AAPL"] = ("320.91", "354.20")  # the real after-hours book on 2026-09-30
    w.fake.last_trade["AAPL"] = "333.05"
    res = await w.call("place_stock_order", order(qty="3", cid="closed", **{**BRACKET, "stop_loss_stop_price": "325"}))
    assert res.structured_content["decision"] == "ALLOW"
    assert ("get_stock_latest_trade", {"symbols": "AAPL"}) in w.fake.calls
    assert ("get_stock_latest_quote", {"symbols": "AAPL"}) not in w.fake.calls
    assert Decimal(w.events()[-1][2]["evaluation"]["reference_price"]) == Decimal("333.05")


async def test_stale_quote_while_market_open_is_refused(tmp_path):
    w = World(tmp_path)
    w.fake.quote_age_seconds = 600  # policy allows 60
    res = await w.call("place_stock_order", order(cid="stale", **BRACKET))
    assert "MARKET_STATE_STALE" in codes(res)
    assert w.fake.placed == []


async def test_live_server_argument_names_are_used(tmp_path):
    """Pins the argument names read from the live alpaca-mcp-server on 2026-10-01."""
    w = World(tmp_path)
    await w.call("place_stock_order", order(cid="names", **BRACKET))
    assert ("get_asset", {"symbol_or_asset_id": "AAPL"}) in w.fake.calls
    assert ("get_stock_latest_quote", {"symbols": "AAPL"}) in w.fake.calls
    assert ("get_orders", {"status": "open", "limit": 500, "nested": True}) in w.fake.calls
    assert ("get_clock", {}) in w.fake.calls


async def test_crypto_position_symbol_is_canonicalised_before_exposure(tmp_path):
    """Alpaca reports crypto positions as BTCUSD but trades them as BTC/USD; both are one exposure."""
    w = World(tmp_path, allowed_symbols=["BTC/USD"], max_position_notional="1000", require_protective_stop=False)
    w.fake.positions.append({"symbol": "BTCUSD", "qty": "0.01", "side": "long"})  # about 837 held
    args = {"symbol": "BTC/USD", "side": "buy", "notional": "300", "type": "market",
            "time_in_force": "gtc", "client_order_id": "btc-1"}
    res = await w.call("place_crypto_order", args)
    assert "POSITION_NOTIONAL_EXCEEDED" in codes(res)
    assert w.fake.placed == []
    small = {**args, "notional": "100", "client_order_id": "btc-2"}
    res2 = await w.call("place_crypto_order", small)
    assert res2.structured_content["decision"] == "ALLOW", codes(res2)
    assert len(w.fake.placed) == 1


# --------------------------------------------------------------------------- escalate


async def test_escalate_then_owner_approval_is_single_use(tmp_path):
    w = World(tmp_path, approval_notional="500")
    args = order(qty="4", cid="esc-1", **BRACKET)  # 760 >= 500 escalates, <= 1000 allowed
    res = await w.call("place_stock_order", args)
    s = res.structured_content
    assert s["decision"] == "ESCALATE" and s["order_placed"] is False
    assert "HUMAN_APPROVAL_REQUIRED" in codes(res)
    assert s["intent_id"] in s["how_to_approve"]
    assert w.fake.placed == []

    w.second_state().approve(s["intent_id"])  # the CLI path: a separate process, same file
    res2 = await w.call("place_stock_order", args)
    s2 = res2.structured_content
    assert s2["decision"] == "ALLOW" and s2["approved_by_owner"] is True
    assert len(w.fake.placed) == 1

    res3 = await w.call("place_stock_order", args)
    assert res3.structured_content.get("replayed") is True
    assert len(w.fake.placed) == 1
    assert w.tiers() == ["ESCALATE", "ALLOW", "REPLAY"]
    assert w.chain()["verified"] is True


async def test_approval_is_bound_to_the_escalated_terms(tmp_path):
    w = World(tmp_path, approval_notional="500")
    res = await w.call("place_stock_order", order(qty="3", cid="esc-1", **BRACKET))  # 570 escalates
    intent_id = res.structured_content["intent_id"]
    w.second_state().approve(intent_id)
    # Same client_order_id, different order: the approval must not carry over.
    res2 = await w.call("place_stock_order", order("MSFT", side="sell", qty="2", cid="esc-1",
                                                   **{**BRACKET, "stop_loss_stop_price": "420", "take_profit_limit_price": "400"}))
    assert res2.structured_content["decision"] in ("ESCALATE", "DENY")
    assert w.fake.placed == []
    # And the original terms still need a fresh approval, because the mismatch consumed it.
    res3 = await w.call("place_stock_order", order(qty="3", cid="esc-1", **BRACKET))
    assert res3.structured_content["decision"] == "ESCALATE"
    assert w.fake.placed == []


async def test_stale_approval_does_not_count(tmp_path):
    w = World(tmp_path, approval_notional="500")
    args = order(qty="4", cid="old", **BRACKET)
    res = await w.call("place_stock_order", args)
    intent_id = res.structured_content["intent_id"]
    w.brake.state.approve(intent_id, now=datetime(2026, 1, 1, tzinfo=UTC))
    res2 = await w.call("place_stock_order", args)
    assert res2.structured_content["decision"] == "ESCALATE"
    assert w.fake.placed == []


# --------------------------------------------------------------------------- fail closed


async def test_upstream_failure_fails_closed(tmp_path):
    w = World(tmp_path)
    w.fake.fail_quotes = True
    w.fake.fail_trades = True
    res = await w.call("place_stock_order", order(cid="q", **BRACKET))
    s = res.structured_content
    assert s["decision"] == "DENY" and s["order_placed"] is False
    assert codes(res) == {"PROXY_FAIL_CLOSED"}
    assert w.fake.placed == []
    assert w.tiers() == ["DENY"]
    assert w.chain()["verified"] is True


async def test_account_mismatch_fails_closed(tmp_path):
    w = World(tmp_path)
    w.fake.account["id"] = "someone-else"
    res = await w.call("place_stock_order", order(cid="m", **BRACKET))
    assert codes(res) == {"PROXY_FAIL_CLOSED"}
    assert "policy account" in res.structured_content["denied_rules"][0]["actual"]
    assert w.fake.placed == []


async def test_unknown_asset_fails_closed(tmp_path):
    w = World(tmp_path)
    del w.fake.assets["AAPL"]
    res = await w.call("place_stock_order", order(cid="ua", **BRACKET))
    assert codes(res) == {"PROXY_FAIL_CLOSED"}
    assert w.fake.placed == []


async def test_unrecognised_positions_shape_fails_closed(tmp_path):
    w = World(tmp_path)
    w.fake.positions_payload_override = {"symbol": "AAPL", "qty": "20", "side": "long"}  # an object, not a list
    res = await w.call("place_stock_order", order(cid="shape", **BRACKET))
    assert codes(res) == {"PROXY_FAIL_CLOSED"}
    assert w.fake.placed == []


async def test_forward_failure_is_recorded_and_reconciled_on_retry(tmp_path):
    w = World(tmp_path)
    w.fake.fail_place_after_accept = True  # the broker accepted, the response never arrived
    args = order(cid="lost", **BRACKET)
    res = await w.call("place_stock_order", args)
    s = res.structured_content
    assert s["decision"] == "ALLOW" and s["order_placed"] == "unknown"
    assert len(w.fake.placed) == 1
    assert w.tiers() == ["ALLOW", "FORWARD_FAILED"]

    w.fake.fail_place_after_accept = False
    res2 = await w.call("place_stock_order", args)
    s2 = res2.structured_content
    assert s2["decision"] == "ALLOW" and s2["replayed"] is True
    assert alpaca.unwrap(s2["upstream"])["client_order_id"] == "lost"
    assert len(w.fake.placed) == 1  # reconciled from the broker, not re-sent
    assert ("get_order_by_client_id", {"client_order_id": "lost"}) in w.fake.calls
    assert w.tiers() == ["ALLOW", "FORWARD_FAILED", "REPLAY"]
    assert w.chain()["verified"] is True


async def test_forward_failure_with_no_broker_order_is_retried_fresh(tmp_path):
    w = World(tmp_path)
    w.fake.fail_place_after_accept = True
    args = order(cid="vanished", **BRACKET)
    await w.call("place_stock_order", args)
    w.fake.orders.clear()  # the broker never recorded it
    w.fake.placed.clear()
    w.fake.fail_place_after_accept = False
    res = await w.call("place_stock_order", args)
    assert res.structured_content["decision"] == "ALLOW" and res.structured_content.get("replayed") is None
    assert len(w.fake.placed) == 1


# --------------------------------------------------------------------------- halt, exits, cancels


async def test_full_halt_blocks_entries_but_never_exits(tmp_path):
    w = World(tmp_path)
    w.fake.positions.append({"symbol": "AAPL", "qty": "1", "side": "long"})
    w.second_state().set_halt("FULL_HALT")  # the CLI path, while the proxy is running
    res = await w.call("place_stock_order", order(cid="h", **BRACKET))
    assert "FULL_HALT_ACTIVE" in codes(res)
    assert len(w.fake.placed) == 0

    res2 = await w.call("close_position", {"symbol_or_asset_id": "AAPL"})
    assert alpaca.unwrap(res2.structured_content)["status"] == "closed"
    assert w.fake.positions == []
    assert w.tiers() == ["DENY", "ALLOW_EXIT"]
    assert w.chain()["verified"] is True
    assert w.second_state().halt == "FULL_HALT"  # the proxy did not overwrite the owner's halt


async def test_broker_side_block_is_treated_as_full_halt(tmp_path):
    w = World(tmp_path)
    w.fake.account["trading_blocked"] = True
    res = await w.call("place_stock_order", order(cid="b", **BRACKET))
    assert "FULL_HALT_ACTIVE" in codes(res)
    assert w.fake.placed == []


async def test_cancelling_the_protective_stop_of_an_open_position_is_refused(tmp_path):
    w = World(tmp_path)
    await w.call("place_stock_order", order(qty="2", cid="first", **BRACKET))
    stop_leg = next(o for o in w.fake.orders if o["type"] == "stop" and o["status"] == "new")
    tp_leg = next(o for o in w.fake.orders if o["type"] == "limit" and o["status"] == "new")

    res = await w.call("cancel_order_by_id", {"order_id": stop_leg["id"]})
    assert "PROXY_PROTECTIVE_STOP_CANCEL_FORBIDDEN" in codes(res)
    assert stop_leg["id"] not in w.fake.cancelled

    res2 = await w.call("cancel_order_by_id", {"order_id": tp_leg["id"]})
    assert alpaca.unwrap(res2.structured_content)["status"] == "canceled"
    assert tp_leg["id"] in w.fake.cancelled

    res3 = await w.call("cancel_all_orders", {})
    assert "PROXY_PROTECTIVE_STOP_CANCEL_FORBIDDEN" in codes(res3)
    assert stop_leg["id"] not in w.fake.cancelled
    assert w.tiers() == ["ALLOW", "DENY", "ALLOW_CANCEL", "DENY"]


async def test_cancel_all_is_allowed_when_flat(tmp_path):
    w = World(tmp_path)
    w.fake.orders.append({"id": "resting", "client_order_id": "r", "symbol": "AAPL", "side": "buy", "qty": "1",
                          "filled_qty": "0", "type": "limit", "limit_price": "150", "stop_price": None,
                          "status": "new", "order_class": "simple", "position_intent": "buy_to_open", "legs": None})
    res = await w.call("cancel_all_orders", {})
    assert "resting" in w.fake.cancelled
    assert res.structured_content.get("decision") is None
    assert w.tiers() == ["ALLOW_CANCEL"]


# --------------------------------------------------------------------------- concurrency


async def test_concurrent_same_client_order_id_places_exactly_one_order(tmp_path):
    w = World(tmp_path)
    args = order(cid="race", **BRACKET)
    results = await asyncio.gather(*(w.call("place_stock_order", args) for _ in range(3)))
    decisions = sorted(r.structured_content["decision"] for r in results)
    assert decisions == ["ALLOW", "ALLOW", "ALLOW"]
    assert sum(1 for r in results if r.structured_content.get("replayed")) == 2
    assert len(w.fake.placed) == 1


async def test_concurrent_orders_cannot_jointly_exceed_the_position_limit(tmp_path):
    w = World(tmp_path, max_position_notional="1200")
    a = order(qty="5", cid="a", **BRACKET)  # 950 each; two would be 1900
    b = order(qty="5", cid="b", **BRACKET)
    results = await asyncio.gather(w.call("place_stock_order", a), w.call("place_stock_order", b))
    decisions = sorted(r.structured_content["decision"] for r in results)
    assert decisions == ["ALLOW", "DENY"]
    assert len(w.fake.placed) == 1


# --------------------------------------------------------------------------- memory tools on the proxy


async def test_memory_tools_are_exposed_and_see_proxy_trades(tmp_path):
    w = World(tmp_path)
    async with Client(w.server) as client:
        names = {t.name for t in await client.list_tools()}
    assert {"recall_memories", "get_behavioral_analysis", "get_agent_state", "brake_status", "place_stock_order"} <= names
    await w.call("place_stock_order", order(cid="mem", **BRACKET))
    status = await w.call("brake_status")
    payload = alpaca.unwrap(status.structured_content)
    assert payload["policy_hash"] == w.policy.content_hash
    assert payload["last_decision"]["decision"] == "ALLOW"
    recall = await w.call("recall_memories", {"symbol": "AAPL", "market_context": "buy AAPL", "limit": 3})
    assert recall.is_error is False and "decision" not in (recall.structured_content or {})
    assert w.tiers() == ["ALLOW"]  # local tools are neither evaluated nor recorded


async def test_account_reads_keep_the_equity_peak_honest(tmp_path):
    w = World(tmp_path, max_drawdown="100")
    w.fake.account["equity"] = "10500"
    await w.call("get_account_info")  # the agent looked at the account while equity was high
    w.fake.account["equity"] = "10350"  # 150 below the peak the proxy saw
    res = await w.call("place_stock_order", order(cid="dd", **BRACKET))
    assert "DRAWDOWN_LIMIT_REACHED" in codes(res)
    assert w.fake.placed == []


# --------------------------------------------------------------------------- pure helpers


async def test_pnl_window_matches_control():
    from mnemox_control.evaluator import _expected_pnl_window

    for hour in (0, 5, 22):
        stub = type("Policy", (), {"risk_day_start_hour_utc": hour})()
        for ts in (
            datetime(2026, 10, 1, 3, 30, tzinfo=UTC),
            datetime(2026, 10, 1, 5, 0, tzinfo=UTC),
            datetime(2026, 10, 1, 23, 59, tzinfo=UTC),
        ):
            assert pnl_window(hour, ts) == _expected_pnl_window(stub, ts)


async def test_policy_seal_roundtrip(tmp_path):
    policy = template_policy(broker="alpaca", account_id="a", owner_id="o", allowed_symbols=["aapl"])
    path = tmp_path / "p.json"
    path.write_text(policy_to_json(policy), encoding="utf-8")
    assert load_policy(path).content_hash == policy.content_hash
    assert load_policy(path).allowed_symbols == ("AAPL",)

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["max_order_notional"] = "5000"  # edited without re-sealing: must be refused
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_policy(path)
    seal_policy_file(path)
    assert str(load_policy(path).max_order_notional) == "5000"


async def test_unwrap_and_as_list_handle_every_upstream_shape():
    assert alpaca.unwrap({"_alpaca_mcp_security": {}, "data": {"id": 1}}) == {"id": 1}
    assert alpaca.unwrap({"result": [1, 2]}) == [1, 2]
    assert alpaca.unwrap({"_alpaca_mcp_security": {}, "data": {"result": [1]}}) == [1]
    assert alpaca.unwrap('{"_alpaca_mcp_security": {}, "data": {"x": 1}}') == {"x": 1}
    assert alpaca.unwrap("plain text") == "plain text"
    assert alpaca.unwrap({"id": "acct"}) == {"id": "acct"}
    assert alpaca.as_list(None) == []
    assert alpaca.as_list({"result": [1]}) == [1]
    with pytest.raises(alpaca.AdapterError):
        alpaca.as_list({"symbol": "AAPL", "qty": "1"})
    assert alpaca.parse_ts("2026-09-30T20:00:00.006168327Z") == datetime(2026, 9, 30, 20, 0, 0, 6168, tzinfo=UTC)


async def test_tool_classification_refuses_what_it_does_not_know():
    assert alpaca.classify_tool("place_stock_order") == "order"
    assert alpaca.classify_tool("close_position") == "exit"
    assert alpaca.classify_tool("cancel_order_by_id") == "cancel"
    assert alpaca.classify_tool("get_stock_bars") == "read"
    assert alpaca.classify_tool("create_watchlist") == "benign"
    assert alpaca.classify_tool("replace_order_by_id") == "unsupported"
    assert alpaca.classify_tool("transfer_funds") == "unknown"
    for name in alpaca.KNOWN_LIVE_TOOLS:
        assert alpaca.classify_tool(name) != "unknown", name
