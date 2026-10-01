"""End-to-end tests of the brake against a stateful fake broker MCP.

Every test that expects an ALLOW asserts the upstream actually received the
order, and every test that expects a DENY asserts it did not. That pairing is
the positive control: a brake that blocks everything and a brake that blocks
nothing both fail this file.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

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

from fake_alpaca import FakeAlpaca  # noqa: E402

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(sys.version_info < (3, 12), reason="proxy extra needs Python 3.12+"),
]

BRACKET = {"order_class": "bracket", "stop_loss_stop_price": "185", "take_profit_limit_price": "200"}


def order(symbol: str = "AAPL", side: str = "buy", qty: str | None = "1", **extra) -> dict:
    args = {"symbol": symbol, "side": side, "type": "market", "time_in_force": "day", **extra}
    if qty is not None:
        args["qty"] = qty
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
        self.policy = template_policy(
            broker="alpaca", account_id="acct-1", owner_id="sean", allowed_symbols=["AAPL", "MSFT"], **settings
        )
        self.policy_path = tmp_path / "policy.json"
        self.policy_path.write_text(policy_to_json(self.policy), encoding="utf-8")
        self.db = Database(db_path=str(tmp_path / "tm.db"))
        self.server, self.brake = build_proxy(
            self.fake.server(), policy_path=self.policy_path, state_path=tmp_path / "state.json", db=self.db
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


# --------------------------------------------------------------------------- denies


async def test_symbol_not_allowed_is_denied_and_chained(tmp_path):
    w = World(tmp_path)
    res = await w.call("place_stock_order", order("TSLA", client_order_id="t1", **BRACKET))
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
    res = await w.call("place_stock_order", order(client_order_id="ns"))
    assert "PROTECTIVE_STOP_REQUIRED" in codes(res)
    assert w.fake.placed == []


async def test_order_notional_over_limit_is_denied(tmp_path):
    w = World(tmp_path)
    res = await w.call("place_stock_order", order(qty="10", client_order_id="big", **BRACKET))  # 1900 > 1000
    assert "ORDER_NOTIONAL_EXCEEDED" in codes(res)
    assert w.fake.placed == []


async def test_position_limit_counts_existing_exposure(tmp_path):
    w = World(tmp_path, max_position_notional="1500")
    w.fake.positions.append({"symbol": "AAPL", "qty": "5", "side": "long"})  # 950 already held
    res = await w.call("place_stock_order", order(qty="5", client_order_id="p", **BRACKET))  # +950 -> 1900
    assert "POSITION_NOTIONAL_EXCEEDED" in codes(res)
    assert w.fake.placed == []


async def test_daily_loss_limit_blocks_new_entries(tmp_path):
    w = World(tmp_path, max_daily_loss="100")
    w.fake.account.update({"equity": "9850", "last_equity": "10000"})
    res = await w.call("place_stock_order", order(client_order_id="dl", **BRACKET))
    assert "DAILY_LOSS_LIMIT_REACHED" in codes(res)
    assert w.fake.placed == []


async def test_unsupported_order_type_is_denied_not_forwarded(tmp_path):
    w = World(tmp_path)
    res = await w.call(
        "place_stock_order",
        order(type="stop_limit", stop_price="188", limit_price="187", client_order_id="sl", **BRACKET),
    )
    assert res.structured_content["decision"] == "DENY"
    assert "PROXY_FAIL_CLOSED" in codes(res)
    assert w.fake.placed == []


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
    args = order(client_order_id="c-1", **BRACKET)
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


async def test_without_client_order_id_each_call_is_a_new_order(tmp_path):
    w = World(tmp_path)
    await w.call("place_stock_order", order(**BRACKET))
    await w.call("place_stock_order", order(**BRACKET))
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
    res = await w.call("place_stock_order", order(client_order_id="t", **BRACKET))
    assert res.structured_content["decision"] == "ALLOW"
    assert ("get_stock_latest_trade", {"symbol": "AAPL"}) in w.fake.calls
    assert len(w.fake.placed) == 1


# --------------------------------------------------------------------------- escalate


async def test_escalate_then_owner_approval_is_single_use(tmp_path):
    w = World(tmp_path, approval_notional="500")
    args = order(qty="4", client_order_id="esc-1", **BRACKET)  # 760 >= 500 escalates, <= 1000 allowed
    res = await w.call("place_stock_order", args)
    s = res.structured_content
    assert s["decision"] == "ESCALATE" and s["order_placed"] is False
    assert "HUMAN_APPROVAL_REQUIRED" in codes(res)
    assert s["intent_id"] in s["how_to_approve"]
    assert w.fake.placed == []

    w.brake.state.approve(s["intent_id"])
    res2 = await w.call("place_stock_order", args)
    s2 = res2.structured_content
    assert s2["decision"] == "ALLOW" and s2["approved_by_owner"] is True
    assert len(w.fake.placed) == 1

    res3 = await w.call("place_stock_order", args)
    assert res3.structured_content.get("replayed") is True
    assert len(w.fake.placed) == 1
    assert w.tiers() == ["ESCALATE", "ALLOW", "REPLAY"]
    assert w.chain()["verified"] is True


async def test_escalate_without_client_order_id_cannot_be_approved(tmp_path):
    w = World(tmp_path, approval_notional="500")
    res = await w.call("place_stock_order", order(qty="4", **BRACKET))
    assert res.structured_content["decision"] == "ESCALATE"
    assert "client_order_id" in res.structured_content["how_to_approve"]
    assert w.fake.placed == []


async def test_stale_approval_does_not_count(tmp_path):
    w = World(tmp_path, approval_notional="500")
    args = order(qty="4", client_order_id="old", **BRACKET)
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
    res = await w.call("place_stock_order", order(client_order_id="q", **BRACKET))
    s = res.structured_content
    assert s["decision"] == "DENY" and s["order_placed"] is False
    assert codes(res) == {"PROXY_FAIL_CLOSED"}
    assert w.fake.placed == []
    assert w.tiers() == ["DENY"]
    assert w.chain()["verified"] is True


async def test_account_mismatch_fails_closed(tmp_path):
    w = World(tmp_path)
    w.fake.account["id"] = "someone-else"
    res = await w.call("place_stock_order", order(client_order_id="m", **BRACKET))
    assert codes(res) == {"PROXY_FAIL_CLOSED"}
    assert "policy account" in res.structured_content["denied_rules"][0]["actual"]
    assert w.fake.placed == []


async def test_unknown_asset_fails_closed(tmp_path):
    w = World(tmp_path)
    del w.fake.assets["AAPL"]
    res = await w.call("place_stock_order", order(client_order_id="ua", **BRACKET))
    assert codes(res) == {"PROXY_FAIL_CLOSED"}
    assert w.fake.placed == []


# --------------------------------------------------------------------------- halt and exits


async def test_full_halt_blocks_entries_but_never_exits(tmp_path):
    w = World(tmp_path)
    w.fake.positions.append({"symbol": "AAPL", "qty": "1", "side": "long"})
    w.brake.state.set_halt("FULL_HALT")
    res = await w.call("place_stock_order", order(client_order_id="h", **BRACKET))
    assert "FULL_HALT_ACTIVE" in codes(res)
    assert len(w.fake.placed) == 0

    res2 = await w.call("close_position", {"symbol": "AAPL"})
    assert alpaca.unwrap(res2.structured_content)["status"] == "closed"
    assert w.fake.positions == []
    assert w.tiers() == ["DENY", "ALLOW_EXIT"]
    assert w.chain()["verified"] is True


async def test_broker_side_block_is_treated_as_full_halt(tmp_path):
    w = World(tmp_path)
    w.fake.account["trading_blocked"] = True
    res = await w.call("place_stock_order", order(client_order_id="b", **BRACKET))
    assert "FULL_HALT_ACTIVE" in codes(res)
    assert w.fake.placed == []


# --------------------------------------------------------------------------- memory tools on the proxy


async def test_memory_tools_are_exposed_and_see_proxy_trades(tmp_path):
    w = World(tmp_path)
    async with Client(w.server) as client:
        names = {t.name for t in await client.list_tools()}
    assert {"recall_memories", "get_behavioral_analysis", "get_agent_state", "brake_status", "place_stock_order"} <= names
    await w.call("place_stock_order", order(client_order_id="mem", **BRACKET))
    status = await w.call("brake_status")
    payload = alpaca.unwrap(status.structured_content)
    assert payload["policy_hash"] == w.policy.content_hash
    assert payload["last_decision"]["decision"] == "ALLOW"


# --------------------------------------------------------------------------- pure helpers (sync)


@pytest.mark.asyncio(loop_scope="function")
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


async def test_unwrap_handles_every_upstream_shape():
    assert alpaca.unwrap({"_alpaca_mcp_security": {}, "data": {"id": 1}}) == {"id": 1}
    assert alpaca.unwrap({"result": [1, 2]}) == [1, 2]
    assert alpaca.unwrap('{"_alpaca_mcp_security": {}, "data": {"x": 1}}') == {"x": 1}
    assert alpaca.unwrap("plain text") == "plain text"
    assert alpaca.unwrap({"id": "acct"}) == {"id": "acct"}
