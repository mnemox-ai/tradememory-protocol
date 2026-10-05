"""Rules learned from history: suggestion, the rules file, and the order check."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tradememory.db import Database
from tradememory.rules.check import RULE_CODE, Close, check_order, recent_closes
from tradememory.rules.store import (
    RulesError,
    active_rules,
    add_proposal,
    approve,
    load_rules,
    retire,
)
from tradememory.rules.suggest import describe_evidence, describe_rule, suggest_size_rule
from tradememory.trade_store import insert_trade_record

UTC = timezone.utc
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def stats(*, enough=True, sized_up=3, sized_net=-420.0, median=1000.0, after=8, trades=60, base=0.1, p=0.04):
    return {
        "trades": trades,
        "median_notional": median,
        "after_losing_streak": {
            "trades_after_streak": after,
            "sized_up": sized_up,
            "sized_up_share": sized_up / after if after else None,
            "baseline_sized_up_share": base,
            "sized_up_p_value": p,
            "sized_up_result": {"trades": sized_up, "win_rate": 0.33, "net_pnl": sized_net},
            "after_streak_result": {"trades": after, "win_rate": 0.4, "net_pnl": -100.0},
            "enough_data": enough,
        },
    }


# --------------------------------------------------------------------------- suggest


def test_suggests_when_sized_up_trades_after_a_streak_lost_money():
    rule = suggest_size_rule(stats(), source="Hyperliquid 0xabc")
    assert rule["kind"] == "size_after_losing_streak"
    assert rule["streak"] == 2 and rule["action"] == "escalate"
    assert rule["max_notional"] == "1500"  # 1.5 x median, the report's own "sized up"
    assert rule["evidence"]["sized_up"] == 3 and rule["evidence"]["sized_up_net_pnl"] == -420.0
    assert "After 2 losses in a row, new orders of $1,500 or more are held" in describe_rule(rule)
    assert "made -$420" in describe_evidence(rule)
    assert "(38%, against 10% of all trades)" in describe_evidence(rule)
    assert rule["evidence"]["p_value"] == 0.04


def test_threshold_rounds_down_to_whole_dollars():
    assert suggest_size_rule(stats(median=1234.9), source="x")["max_notional"] == "1852"
    assert suggest_size_rule(stats(median=0.2), source="x")["max_notional"] == "1"


@pytest.mark.parametrize("kwargs", [
    {"enough": False},  # too few trades after a streak to say anything
    {"sized_up": 1},  # one sized-up loser is an anecdote
    {"sized_up": 0},
    {"sized_net": 0.0},  # sizing up did not cost money
    {"sized_net": 250.0},
    {"median": 0.0},
    {"p": 0.11},  # sizes up after losses about as often as always
    {"p": None},
])
def test_no_suggestion_without_a_costly_habit(kwargs):
    assert suggest_size_rule(stats(**kwargs), source="x") is None


def test_no_suggestion_for_an_empty_history():
    assert suggest_size_rule({"trades": 0}, source="x") is None


# --------------------------------------------------------------------------- store


def proposal(**over):
    p = suggest_size_rule(stats(), source="Hyperliquid 0xabc")
    p.update(over)
    return p


def test_missing_file_means_no_rules(tmp_path):
    assert load_rules(tmp_path / "rules.json") == []
    assert active_rules(tmp_path / "rules.json") == []


def test_proposal_is_stored_once_and_inert(tmp_path):
    path = tmp_path / "rules.json"
    rule, created = add_proposal(proposal(), path=path, now=T0)
    again, created_again = add_proposal(proposal(), path=path, now=T0 + timedelta(days=1))
    assert created and not created_again and again["id"] == rule["id"]
    assert rule["status"] == "proposed" and active_rules(path) == []
    assert len(load_rules(path)) == 1


def test_approve_activates_with_the_owners_terms(tmp_path):
    path = tmp_path / "rules.json"
    rule, _ = add_proposal(proposal(), path=path, now=T0)
    active = approve(rule["id"][:6], path=path, now=T0, max_notional="500", action="deny")
    assert active["status"] == "active" and active["max_notional"] == "500" and active["action"] == "deny"
    assert [r["id"] for r in active_rules(path)] == [rule["id"]]
    with pytest.raises(ValueError):
        approve(rule["id"], path=path)  # already active
    with pytest.raises(KeyError):
        approve("r-nope", path=path)


@pytest.mark.parametrize("bad", ["0", "-5", "abc", "NaN", "Infinity"])
def test_approve_rejects_a_limit_that_is_not_a_positive_number(tmp_path, bad):
    path = tmp_path / "rules.json"
    rule, _ = add_proposal(proposal(), path=path)
    with pytest.raises(ValueError):
        approve(rule["id"], path=path, max_notional=bad)
    assert active_rules(path) == []


def test_editing_an_active_rule_breaks_the_file_until_it_is_retired(tmp_path):
    path = tmp_path / "rules.json"
    rule, _ = add_proposal(proposal(), path=path)
    approve(rule["id"], path=path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["rules"][0]["max_notional"] = "999999"  # loosened without approval
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RulesError, match="changed after it was approved"):
        active_rules(path)
    retire(rule["id"], path=path)
    assert active_rules(path) == []
    assert load_rules(path)[0]["status"] == "retired"


@pytest.mark.parametrize("content", [
    "{not json",
    "[]",
    json.dumps({"rules": "x"}),
    json.dumps({"rules": [{"id": "r-1", "kind": "other", "status": "active", "action": "escalate",
                           "streak": 2, "max_notional": "1"}]}),
    json.dumps({"rules": [{"id": "r-1", "kind": "size_after_losing_streak", "status": "active",
                           "action": "escalate", "streak": 2, "max_notional": "1"}]}),  # never approved
    json.dumps({"rules": [{"id": "r-1", "kind": "size_after_losing_streak", "status": "proposed",
                           "action": "escalate", "streak": 0, "max_notional": "1"}]}),
])
def test_a_file_that_cannot_be_trusted_is_refused(tmp_path, content):
    path = tmp_path / "rules.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(RulesError):
        active_rules(path)


# --------------------------------------------------------------------------- check


RULE = {"id": "r-1", "kind": "size_after_losing_streak", "streak": 2, "max_notional": "1500",
        "action": "escalate", "status": "active"}


def closes(*pnls: float) -> list[Close]:
    """Newest first."""
    return [Close(closed_at=T0 - timedelta(hours=i), symbol="AAPL", pnl=p, trade_id=f"t{i}") for i, p in enumerate(pnls)]


def test_holds_a_big_order_right_after_two_losses():
    hits = check_order([RULE], order_notional=Decimal("1500"), adds_risk=True, closes=closes(-10, -5, 30))
    assert len(hits) == 1
    hit = hits[0]
    assert hit["code"] == RULE_CODE and hit["action"] == "escalate" and hit["rule_id"] == "r-1"
    assert [c["trade_id"] for c in hit["losing_streak"]] == ["t0", "t1"]
    assert hit["history_as_of"] == T0.isoformat()


@pytest.mark.parametrize("notional,history,adds_risk", [
    (Decimal("1499.99"), (-10, -5), True),  # under the limit
    (Decimal("5000"), (-10, 5), True),  # the newest two are not both losses
    (Decimal("5000"), (5, -10, -5), True),  # a win since the losses ends the streak
    (Decimal("5000"), (-10, 0), True),  # break-even is not a loss
    (Decimal("5000"), (-10,), True),  # not enough history for a streak
    (Decimal("5000"), (-10, -5), False),  # reducing risk is never held
])
def test_does_not_hold(notional, history, adds_risk):
    assert check_order([RULE], order_notional=notional, adds_risk=adds_risk, closes=closes(*history)) == []


def test_an_order_whose_size_is_unknown_is_held():
    assert check_order([RULE], order_notional=None, adds_risk=True, closes=closes(-1, -1))


def test_recent_closes_reads_both_brake_rows_and_imported_trips(tmp_path):
    db = Database(db_path=str(tmp_path / "tm.db"))

    def add(tid, stamp, pnl, tags):
        insert_trade_record(db, trade_id=tid, timestamp=stamp, symbol="AAPL", direction="long",
                            entry_price=1.0, exit_price=1.0, pnl=pnl, pnl_r=None, strategy_name="s",
                            market_context="", tags=tags)

    add("old", "2026-09-30T10:00:00+00:00", -1.0, ["alpaca", "imported"])
    add("newer-z", "2026-10-01T09:00:00Z", -2.0, ["alpaca", "imported"])  # a different timestamp format
    add("hl", "2026-10-02T00:00:00+00:00", -3.0, ["hyperliquid", "imported"])  # another venue
    # A brake row: entered first, its exit written later by a sync.
    add("ord-1", "2026-09-29T08:00:00+00:00", 5.0, ["proxy", "alpaca"])
    db.update_trade_outcome("ord-1", {"exit_timestamp": "2026-10-01T11:00:00+00:00", "exit_price": 2.0,
                                      "pnl": 5.0, "pnl_r": None, "hold_duration": 1})
    got = recent_closes(db, venue="alpaca", limit=3)
    assert [c.trade_id for c in got] == ["ord-1", "newer-z", "old"]
    assert [c.trade_id for c in recent_closes(db, venue=None, limit=1)] == ["hl"]


# --------------------------------------------------------------------------- binomial tail


def test_binomial_tail_matches_exact_values():
    from math import comb

    from tradememory.sync.report import binomial_tail

    exact = sum(comb(20, k) * 0.3**k * 0.7**(20 - k) for k in range(9, 21))
    assert binomial_tail(9, 20, 0.3) == pytest.approx(exact, rel=1e-12)
    assert binomial_tail(0, 20, 0.3) == 1.0
    assert binomial_tail(3, 0, 0.3) is None
    assert binomial_tail(1, 5, 0.0) == 0.0 and binomial_tail(1, 5, 1.0) == 1.0


def test_binomial_tail_does_not_underflow_on_long_histories():
    from tradememory.sync.report import binomial_tail

    # (1 - 0.4) ** 5000 underflows a float; the log-space sum must not.
    assert binomial_tail(2000, 5000, 0.4) == pytest.approx(0.5, abs=0.02)
    assert binomial_tail(2300, 5000, 0.4) < 1e-9
