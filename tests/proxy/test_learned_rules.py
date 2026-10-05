"""The brake enforcing rules the owner approved from their own history.

Positive control as in test_brake.py: every held or refused order asserts the
fake broker never received it, every allowed one asserts it did.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):  # datetime.UTC and mnemox-control both need newer Pythons
    pytest.skip("proxy extra needs Python 3.12+", allow_module_level=True)
pytest.importorskip("mnemox_control")

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


def order(qty: str = "1", cid: str = "c-1", side: str = "buy") -> dict:
    return {"symbol": "AAPL", "side": side, "type": "market", "time_in_force": "day", "qty": qty,
            "client_order_id": cid, **BRACKET}


class World:
    """A brake with a rules file and a memory that already holds some closed trades."""

    def __init__(self, tmp_path, *, max_notional: str = "300", action: str = "escalate", approved: bool = True):
        self.fake = FakeAlpaca()
        policy = template_policy(broker="alpaca", account_id="acct-1", owner_id="sean",
                                 allowed_symbols=["AAPL", "MSFT"], max_order_notional="5000",
                                 approval_notional="5000")
        policy_path = tmp_path / "policy.json"
        policy_path.write_text(policy_to_json(policy), encoding="utf-8")
        self.state_path = tmp_path / "state.json"
        self.rules_path = tmp_path / "rules.json"
        self.db = Database(db_path=str(tmp_path / "tm.db"))
        proposal = {"kind": "size_after_losing_streak", "streak": 2, "max_notional": "1500",
                    "action": "escalate", "source": "Hyperliquid 0xabc",
                    "evidence": {"history_trades": 60, "median_notional": 1000.0, "trades_after_streak": 8,
                                 "sized_up": 3, "sized_up_win_rate": 0.33, "sized_up_net_pnl": -420.0}}
        self.rule, _ = add_proposal(proposal, path=self.rules_path)
        if approved:
            approve(self.rule["id"], path=self.rules_path, max_notional=max_notional, action=action)
        self.server, self.brake = build_proxy(
            self.fake.server(), policy_path=policy_path, state_path=self.state_path,
            rules_path=self.rules_path, db=self.db,
        )
        self._n = 0

    def closed(self, *pnls: float, venue: str = "alpaca") -> None:
        """Closed trades in memory, oldest first, the way a sync stores them."""
        base = datetime.now(UTC) - timedelta(hours=len(pnls) + 1)
        for pnl in pnls:
            self._n += 1
            insert_trade_record(self.db, trade_id=f"trip-{self._n}",
                                timestamp=(base + timedelta(hours=self._n)).isoformat(), symbol="AAPL",
                                direction="long", entry_price=190.0, exit_price=190.0 + pnl, pnl=pnl,
                                pnl_r=None, strategy_name="s", market_context="", tags=[venue, "imported"])

    async def call(self, name: str, args: dict | None = None):
        async with Client(self.server) as client:
            return await client.call_tool(name, args or {}, raise_on_error=False)

    def events(self) -> list[tuple[str, dict]]:
        with self.db.get_connection() as conn:
            rows = conn.execute("select tier, factors_json from decision_events order by rowid").fetchall()
        return [(r[0], json.loads(r[1])) for r in rows]


def codes(result) -> set[str]:
    s = result.structured_content
    return {r["code"] for r in (s.get("denied_rules") or s.get("rules") or [])}


async def test_a_big_order_after_two_losses_is_held_then_released_by_approval(tmp_path):
    w = World(tmp_path)
    w.closed(40.0, -12.0, -7.5)
    res = await w.call("place_stock_order", order(qty="2", cid="after-streak"))  # ~380, limit 300
    s = res.structured_content
    assert s["decision"] == "ESCALATE" and s["order_placed"] is False
    assert RULE_CODE in codes(res)
    hit = next(r for r in s["rules"] if r["code"] == RULE_CODE)
    assert hit["rule_id"] == w.rule["id"] and [c["pnl"] for c in hit["losing_streak"]] == [-7.5, -12.0]
    assert w.fake.placed == []

    tier, factors = w.events()[-1]
    assert tier == "ESCALATE" and factors["control_decision"] == "ALLOW"
    assert factors["learned_rules"][0]["rule_id"] == w.rule["id"]
    # The chain anchors the learned rule too, not only Control's evaluation.
    assert factors["content_hash"] != s.get("evaluation_hash")

    # The owner approves these exact terms; the same call now goes through, once.
    ProxyState(w.state_path).approve(s["intent_id"], s["terms_fingerprint"], datetime.now(UTC))
    res = await w.call("place_stock_order", order(qty="2", cid="after-streak"))
    assert res.structured_content["decision"] == "ALLOW" and res.structured_content["approved_by_owner"] is True
    assert len(w.fake.placed) == 1
    with w.db.get_connection() as conn:
        assert ChainBuilder(conn).verify_chain()["verified"] is True


async def test_small_orders_and_orders_after_a_win_go_through(tmp_path):
    w = World(tmp_path)
    w.closed(-12.0, -7.5)
    res = await w.call("place_stock_order", order(qty="1", cid="small"))  # ~190, under 300
    assert res.structured_content["decision"] == "ALLOW"
    w.closed(25.0)  # the streak is over
    res = await w.call("place_stock_order", order(qty="2", cid="after-win"))
    assert res.structured_content["decision"] == "ALLOW"
    assert len(w.fake.placed) == 2
    assert "learned_rules" not in w.events()[-1][1]


async def test_losses_on_another_venue_do_not_count(tmp_path):
    w = World(tmp_path)
    w.closed(-12.0, -7.5, venue="hyperliquid")
    res = await w.call("place_stock_order", order(qty="2", cid="other-venue"))
    assert res.structured_content["decision"] == "ALLOW" and len(w.fake.placed) == 1


async def test_deny_action_refuses_outright(tmp_path):
    w = World(tmp_path, action="deny")
    w.closed(-1.0, -1.0)
    res = await w.call("place_stock_order", order(qty="2", cid="deny"))
    s = res.structured_content
    assert s["decision"] == "DENY" and RULE_CODE in codes(res)
    assert s["message"] == "order refused by a rule you approved"
    assert w.fake.placed == []


async def test_proposed_and_retired_rules_are_not_enforced(tmp_path):
    w = World(tmp_path, approved=False)
    w.closed(-1.0, -1.0)
    res = await w.call("place_stock_order", order(qty="2", cid="proposed"))
    assert res.structured_content["decision"] == "ALLOW"
    approve(w.rule["id"], path=w.rules_path, max_notional="300")
    res = await w.call("place_stock_order", order(qty="2", cid="now-active"))
    assert res.structured_content["decision"] == "ESCALATE"  # picked up without a restart
    retire(w.rule["id"], path=w.rules_path)
    res = await w.call("place_stock_order", order(qty="2", cid="retired"))
    assert res.structured_content["decision"] == "ALLOW"
    assert len(w.fake.placed) == 2


async def test_a_rule_edited_after_approval_fails_closed(tmp_path):
    w = World(tmp_path)
    data = json.loads(w.rules_path.read_text(encoding="utf-8"))
    data["rules"][0]["max_notional"] = "1000000"
    w.rules_path.write_text(json.dumps(data), encoding="utf-8")
    res = await w.call("place_stock_order", order(qty="1", cid="tampered"))
    assert res.structured_content["decision"] == "DENY" and "PROXY_FAIL_CLOSED" in codes(res)
    assert w.fake.placed == []
    status = (await w.call("brake_status")).structured_content
    assert "changed after it was approved" in status["learned_rules"]["error"]


async def test_exits_are_never_held(tmp_path):
    w = World(tmp_path)
    w.fake.positions.append({"symbol": "AAPL", "qty": "5", "side": "long"})
    w.closed(-1.0, -1.0)
    await w.call("close_position", {"symbol_or_asset_id": "AAPL"})
    tiers = [t for t, _ in w.events()]
    assert tiers == ["ALLOW_EXIT"]


async def test_evaluate_order_reports_the_hold_without_placing(tmp_path):
    w = World(tmp_path)
    w.closed(-1.0, -1.0)
    res = await w.call("evaluate_order", {"symbol": "AAPL", "side": "buy", "qty": "2", **BRACKET})
    s = res.structured_content
    assert s["decision"] == "ESCALATE" and s["dry_run"] is True and RULE_CODE in codes(res)
    assert w.fake.placed == []
