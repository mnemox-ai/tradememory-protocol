"""The brake enforcing rules the owner approved from their own history.

The closed trades come from the broker's fill activities (the fake keeps them
in the live shape), never from the memory database. Positive control as in
test_brake.py: every held or refused order asserts the fake broker never
received it, every allowed one asserts it did.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):  # datetime.UTC and mnemox-control both need newer Pythons
    pytest.skip("proxy extra needs Python 3.12+", allow_module_level=True)
pytest.importorskip("mnemox_control")

import hashlib  # noqa: E402
import json  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

from fastmcp import Client  # noqa: E402

from tradememory.audit.chain import ChainBuilder  # noqa: E402
from tradememory.db import Database  # noqa: E402
from tradememory.proxy.policy import policy_to_json, template_policy  # noqa: E402
from tradememory.proxy.server import build_proxy  # noqa: E402
from tradememory.proxy.state import ProxyState  # noqa: E402
from tradememory.rules.check import RULE_CODE  # noqa: E402
from tradememory.rules.store import add_proposal, approve, retire  # noqa: E402
from tradememory.trade_store import insert_trade_record  # noqa: E402

from fake_alpaca import FakeAlpaca  # noqa: E402

pytestmark = pytest.mark.asyncio

BRACKET = {"order_class": "bracket", "stop_loss_stop_price": "185", "take_profit_limit_price": "200"}
PROPOSAL = {
    "kind": "size_after_losing_streak", "streak": 2, "max_notional": "1500", "action": "escalate",
    "source": "Hyperliquid 0xabc",
    "evidence": {"history_trades": 60, "median_notional": 1000.0, "trades_after_streak": 8, "sized_up": 4,
                 "sized_up_share": 0.5, "usual_sized_up_share": 0.2, "p_value": 0.03,
                 "sized_up_win_rate": 0.25, "sized_up_net_pnl": -420.0},
}


def order(qty: str = "1", cid: str = "c-1", side: str = "buy", bracket: bool = True) -> dict:
    args = {"symbol": "AAPL", "side": side, "type": "market", "time_in_force": "day", "qty": qty,
            "client_order_id": cid}
    if bracket:
        args.update(BRACKET)
    return args


class World:
    """A brake with a rules file in front of a fake broker that has a fill history."""

    def __init__(self, tmp_path, *, max_notional: str = "300", action: str = "escalate", approved: bool = True,
                 **policy_overrides):
        self.fake = FakeAlpaca()
        settings = {"max_order_notional": "5000", "approval_notional": "5000"}
        settings.update(policy_overrides)
        policy = template_policy(broker="alpaca", account_id="acct-1", owner_id="sean",
                                 allowed_symbols=["AAPL", "MSFT"], **settings)
        policy_path = tmp_path / "policy.json"
        policy_path.write_text(policy_to_json(policy), encoding="utf-8")
        self.state_path = tmp_path / "state.json"
        self.rules_path = tmp_path / "rules.json"
        self.db = Database(db_path=str(tmp_path / "tm.db"))
        self.rule, _ = add_proposal(PROPOSAL, path=self.rules_path)
        if approved:
            approve(self.rule["id"], path=self.rules_path, max_notional=max_notional, action=action)
        self.server, self.brake = build_proxy(
            self.fake.server(), policy_path=policy_path, state_path=self.state_path,
            rules_path=self.rules_path, db=self.db,
        )

    async def call(self, name: str, args: dict | None = None):
        async with Client(self.server) as client:
            return await client.call_tool(name, args or {}, raise_on_error=False)

    def events(self) -> list[tuple[str, dict]]:
        with self.db.get_connection() as conn:
            rows = conn.execute("select tier, factors_json from decision_events order by rowid").fetchall()
        return [(r[0], json.loads(r[1])) for r in rows]

    def activity_reads(self) -> int:
        return sum(1 for name, _ in self.fake.calls if name == "get_account_activities_by_type")


def codes(result) -> set[str]:
    s = result.structured_content
    return {r["code"] for r in (s.get("denied_rules") or s.get("rules") or [])}


def factors_hash(factors: dict) -> str:
    body = {k: v for k, v in factors.items() if k != "content_hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# --------------------------------------------------------------------------- holds


async def test_a_big_order_after_two_losses_is_held_then_released_by_approval(tmp_path):
    w = World(tmp_path)
    w.fake.closed_trades(40.0, -12.0, -7.5)
    res = await w.call("place_stock_order", order(qty="2", cid="after-streak"))  # ~380, limit 300
    s = res.structured_content
    assert s["decision"] == "ESCALATE" and s["order_placed"] is False and RULE_CODE in codes(res)
    hit = next(r for r in s["rules"] if r["code"] == RULE_CODE)
    assert hit["rule_id"] == w.rule["id"] and [c["pnl"] for c in hit["losing_streak"]] == [-7.5, -12.0]
    assert hit["learned_from"] == "Hyperliquid 0xabc"
    assert "held by After 2 losses in a row" in s["terms"]
    assert s["terms_fingerprint"].endswith(f"+rules:{w.rule['id']}")
    assert w.fake.placed == []

    tier, factors = w.events()[-1]
    assert tier == "ESCALATE" and factors["control_decision"] == "ALLOW"
    assert factors["learned_rules_checked"]["history"] == "read from the broker"
    assert factors["learned_rules_checked"]["closes_seen"] == 3
    # The chain anchors the whole record, and the reply names that hash.
    assert factors["content_hash"] == factors_hash(factors) == s["decision_record_hash"]
    assert "evaluation_hash" not in s and s["control_decision"] == "ALLOW"

    ProxyState(w.state_path).approve(s["intent_id"], s["terms_fingerprint"], datetime.now(UTC))
    res = await w.call("place_stock_order", order(qty="2", cid="after-streak"))
    assert res.structured_content["decision"] == "ALLOW" and res.structured_content["approved_by_owner"] is True
    assert len(w.fake.placed) == 1
    with w.db.get_connection() as conn:
        assert ChainBuilder(conn).verify_chain()["verified"] is True


async def test_splitting_into_small_orders_is_held_by_the_resulting_position(tmp_path):
    w = World(tmp_path)
    w.fake.closed_trades(-12.0, -7.5)
    w.fake.positions.append({"symbol": "AAPL", "qty": "1", "side": "long"})
    w.fake.record_fill("AAPL", "buy", "1", "190", at=datetime.now(UTC) - timedelta(minutes=5))
    res = await w.call("place_stock_order", order(qty="1", cid="second-half"))  # order ~190, position ~380
    assert res.structured_content["decision"] == "ESCALATE" and RULE_CODE in codes(res)
    assert w.fake.placed == []


async def test_deny_action_refuses_outright(tmp_path):
    w = World(tmp_path, action="deny")
    w.fake.closed_trades(-1.0, -1.0)
    res = await w.call("place_stock_order", order(qty="2", cid="deny"))
    s = res.structured_content
    assert s["decision"] == "DENY" and RULE_CODE in codes(res)
    assert s["message"] == "order refused by a rule you approved"
    assert w.fake.placed == []


async def test_evaluate_order_reports_the_hold_without_placing(tmp_path):
    w = World(tmp_path)
    w.fake.closed_trades(-1.0, -1.0)
    res = await w.call("evaluate_order", {"symbol": "AAPL", "side": "buy", "qty": "2", **BRACKET})
    s = res.structured_content
    assert s["decision"] == "ESCALATE" and s["dry_run"] is True and RULE_CODE in codes(res)
    assert w.fake.placed == []


# --------------------------------------------------------------------------- the history is the broker's


async def test_the_memory_database_cannot_hide_or_fake_the_streak(tmp_path):
    w = World(tmp_path)
    w.fake.closed_trades(-12.0, -7.5)
    # Newer rows in memory, from another venue and from another Alpaca account: none of them count.
    for i in range(600):
        insert_trade_record(w.db, trade_id=f"hl-{i}", timestamp=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
                            symbol="BTC", direction="long", entry_price=1.0, exit_price=2.0, pnl=50.0, pnl_r=None,
                            strategy_name="s", market_context="", tags=["hyperliquid", "imported"])
    insert_trade_record(w.db, trade_id="paper-win", timestamp=datetime.now(UTC).isoformat(), symbol="AAPL",
                        direction="long", entry_price=1.0, exit_price=2.0, pnl=99.0, pnl_r=None,
                        strategy_name="s", market_context="", tags=["alpaca", "imported"])
    res = await w.call("place_stock_order", order(qty="2", cid="db-noise"))
    assert res.structured_content["decision"] == "ESCALATE" and w.fake.placed == []


async def test_a_close_at_the_broker_counts_without_any_sync(tmp_path):
    w = World(tmp_path)
    w.fake.closed_trades(-12.0)
    # The agent's own trade goes through, then the stop closes it at a loss at the broker.
    res = await w.call("place_stock_order", order(qty="1", cid="entry"))
    assert res.structured_content["decision"] == "ALLOW"
    w.fake.quotes["AAPL"] = ("185.00", "185.04")
    await w.call("close_position", {"symbol_or_asset_id": "AAPL"})
    w.fake.quotes["AAPL"] = ("189.98", "190.02")
    res = await w.call("place_stock_order", order(qty="2", cid="revenge"))
    assert res.structured_content["decision"] == "ESCALATE" and RULE_CODE in codes(res)
    assert len(w.fake.placed) == 1  # only the first entry


async def test_unreadable_history_refuses_only_orders_big_enough_to_matter(tmp_path):
    w = World(tmp_path)
    w.fake.fail_activities = True
    res = await w.call("place_stock_order", order(qty="1", cid="small"))  # ~190, below 300: no history needed
    assert res.structured_content["decision"] == "ALLOW"
    assert w.events()[-1][1]["learned_rules_checked"]["history"] == "not read: below every rule's limit"
    res = await w.call("place_stock_order", order(qty="2", cid="big"))
    assert res.structured_content["decision"] == "DENY" and "PROXY_FAIL_CLOSED" in codes(res)
    assert len(w.fake.placed) == 1


async def test_history_is_read_incrementally(tmp_path):
    w = World(tmp_path)
    w.fake.closed_trades(*([5.0] * 150))  # 300 fills: three pages the first time
    await w.call("place_stock_order", order(qty="2", cid="first"))
    first = w.activity_reads()
    await w.call("place_stock_order", order(qty="2", cid="second"))
    assert first >= 3 and w.activity_reads() - first == 1
    after = [args["after"] for name, args in w.fake.calls if name == "get_account_activities_by_type"][-1]
    assert after is not None


# --------------------------------------------------------------------------- what is not held


async def test_small_orders_and_orders_after_a_win_go_through(tmp_path):
    w = World(tmp_path)
    w.fake.closed_trades(-12.0, -7.5)
    res = await w.call("place_stock_order", order(qty="1", cid="small"))  # ~190, under 300
    assert res.structured_content["decision"] == "ALLOW"
    await w.call("close_position", {"symbol_or_asset_id": "AAPL"})  # sells at the bid: a small loss
    w.fake.closed_trades(25.0)
    res = await w.call("place_stock_order", order(qty="2", cid="after-win"))
    assert res.structured_content["decision"] == "ALLOW"
    assert len(w.fake.placed) == 2
    assert "learned_rules" not in w.events()[-1][1]


async def test_proposed_and_retired_rules_are_not_enforced(tmp_path):
    w = World(tmp_path, approved=False)
    w.fake.closed_trades(-1.0, -1.0)
    res = await w.call("place_stock_order", order(qty="2", cid="proposed"))
    assert res.structured_content["decision"] == "ALLOW"
    await w.call("close_position", {"symbol_or_asset_id": "AAPL"})
    w.fake.closed_trades(-1.0, -1.0)
    approve(w.rule["id"], path=w.rules_path, max_notional="300")
    res = await w.call("place_stock_order", order(qty="2", cid="now-active"))
    assert res.structured_content["decision"] == "ESCALATE"  # picked up without a restart
    retire(w.rule["id"], path=w.rules_path)
    res = await w.call("place_stock_order", order(qty="2", cid="retired"))
    assert res.structured_content["decision"] == "ALLOW"
    assert len(w.fake.placed) == 2


async def test_a_rule_edited_after_approval_fails_closed_without_leaking_the_path(tmp_path):
    w = World(tmp_path)
    data = json.loads(w.rules_path.read_text(encoding="utf-8"))
    data["rules"][0]["max_notional"] = "1000000"
    w.rules_path.write_text(json.dumps(data), encoding="utf-8")
    res = await w.call("place_stock_order", order(qty="1", cid="tampered"))
    s = res.structured_content
    assert s["decision"] == "DENY" and "PROXY_FAIL_CLOSED" in codes(res)
    assert str(tmp_path) not in json.dumps(s)
    assert w.fake.placed == []
    status = (await w.call("brake_status")).structured_content
    assert "changed by hand" in status["learned_rules"]["error"]


async def test_reducing_a_position_never_reads_a_broken_rules_file(tmp_path):
    w = World(tmp_path, require_protective_stop=False)
    w.fake.positions.append({"symbol": "AAPL", "qty": "5", "side": "long"})
    w.rules_path.write_text("", encoding="utf-8")  # broken
    res = await w.call("place_stock_order", order(qty="2", cid="trim", side="sell", bracket=False))
    assert res.structured_content["decision"] == "ALLOW" and len(w.fake.placed) == 1


async def test_exits_are_never_held(tmp_path):
    w = World(tmp_path)
    w.fake.positions.append({"symbol": "AAPL", "qty": "5", "side": "long"})
    w.fake.closed_trades(-1.0, -1.0)
    await w.call("close_position", {"symbol_or_asset_id": "AAPL"})
    assert [t for t, _ in w.events()] == ["ALLOW_EXIT"]


async def test_an_approval_given_before_the_rule_fired_does_not_cover_it(tmp_path):
    # Control escalates on its own (approval_notional 300); the owner approves those terms.
    w = World(tmp_path, approval_notional="300")
    res = await w.call("place_stock_order", order(qty="2", cid="big"))
    s = res.structured_content
    assert s["decision"] == "ESCALATE" and RULE_CODE not in codes(res)
    ProxyState(w.state_path).approve(s["intent_id"], s["terms_fingerprint"], datetime.now(UTC))
    # Two losses close at the broker before the agent retries the same terms.
    w.fake.closed_trades(-1.0, -1.0)
    res = await w.call("place_stock_order", order(qty="2", cid="big"))
    assert res.structured_content["decision"] == "ESCALATE" and RULE_CODE in codes(res)
    assert w.fake.placed == []
