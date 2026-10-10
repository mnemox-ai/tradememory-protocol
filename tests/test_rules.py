"""Rules learned from history: suggestion, the rules file, and the order check."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tradememory.rules import store
from tradememory.rules.check import RULE_CODE, Close, check_order
from tradememory.rules.store import (
    RulesError,
    active_rules,
    add_proposal,
    approve,
    load_rules,
    retire,
)
from tradememory.rules.suggest import describe_evidence, describe_rule, money, suggest_size_rule

UTC = timezone.utc
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def stats(*, enough=True, sized_up=3, sized_net=-420.0, median=1000.0, after=8, trades=60, base=0.1, p=0.04,
          more_often=True):
    return {
        "trades": trades,
        "median_notional": median,
        "after_losing_streak": {
            "trades_after_streak": after,
            "sized_up": sized_up,
            "sized_up_share": sized_up / after if after else None,
            "baseline_sized_up_share": base,
            "sized_up_p_value": p,
            "more_often_than_usual": more_often,
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
    assert "After 2 losses in a row, orders that take a position to $1,500 or more are held" in describe_rule(rule)
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
    {"more_often": False},  # sizes up after losses about as often as always
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


@pytest.mark.parametrize("bad", ["0", "-5", "abc", "NaN", "Infinity", "1000.5", "1,000"])
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
    with pytest.raises(RulesError, match="changed by hand"):
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
        "action": "escalate", "status": "active", "source": "Hyperliquid 0xabc"}


def closes(*pnls: float) -> list[Close]:
    """Newest first."""
    return [Close(closed_at=T0 - timedelta(hours=i), symbol="AAPL", pnl=p, trade_id=f"t{i}") for i, p in enumerate(pnls)]


def test_holds_a_big_position_right_after_two_losses():
    hits = check_order([RULE], size=Decimal("1500"), closes=closes(-10, -5, 30))
    assert len(hits) == 1
    hit = hits[0]
    assert hit["code"] == RULE_CODE and hit["action"] == "escalate" and hit["rule_id"] == "r-1"
    assert [c["trade_id"] for c in hit["losing_streak"]] == ["t0", "t1"]
    assert hit["learned_from"] == "Hyperliquid 0xabc"
    assert "orders that take a position to $1,500 or more" in hit["message"]


@pytest.mark.parametrize("size,history", [
    (Decimal("1499.99"), (-10, -5)),  # under the limit
    (Decimal("5000"), (-10, 5)),  # the newest two are not both losses
    (Decimal("5000"), (5, -10, -5)),  # a win since the losses ends the streak
    (Decimal("5000"), (-10, 0)),  # break-even is not a loss
    (Decimal("5000"), (-10,)),  # not enough history for a streak
    (Decimal("5000"), ()),
])
def test_does_not_hold(size, history):
    assert check_order([RULE], size=size, closes=closes(*history)) == []


def test_an_order_whose_size_is_unknown_is_held():
    assert check_order([RULE], size=None, closes=closes(-1, -1))


# --------------------------------------------------------------------------- store, continued


def test_limits_are_stored_as_whole_numbers_and_shown_exactly(tmp_path):
    path = tmp_path / "rules.json"
    rule, _ = add_proposal(proposal(), path=path)
    active = approve(rule["id"], path=path, max_notional=" 1e3 ")
    assert active["max_notional"] == "1000"
    assert "$1,000 or more" in describe_rule(active)
    assert money("1000") == "$1,000" and money("1000.5") == "$1,000.5"


def test_a_retired_rule_flipped_back_on_by_hand_is_refused(tmp_path):
    path = tmp_path / "rules.json"
    rule, _ = add_proposal(proposal(), path=path)
    approve(rule["id"], path=path)
    retire(rule["id"], path=path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["rules"][0]["status"] = "active"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RulesError, match="changed by hand"):
        active_rules(path)


def test_switching_an_active_rule_off_by_hand_is_refused(tmp_path):
    path = tmp_path / "rules.json"
    rule, _ = add_proposal(proposal(), path=path)
    approve(rule["id"], path=path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["rules"][0]["status"] = "proposed"
    data["rules"][0]["content_hash"] = None
    path.write_text(json.dumps(data), encoding="utf-8")
    # "proposed" with an approval stamp still on it: someone switched it off without retiring it.
    with pytest.raises(RulesError, match="switched back to proposed"):
        active_rules(path)
    data["rules"][0]["status"] = "retired"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RulesError):
        active_rules(path)


def test_a_short_prefix_does_not_pick_a_rule(tmp_path):
    path = tmp_path / "rules.json"
    rule, _ = add_proposal(proposal(), path=path)
    with pytest.raises(KeyError):
        retire("r", path=path)
    with pytest.raises(KeyError):
        approve(rule["id"][:5], path=path)
    assert approve(rule["id"][:6], path=path)["status"] == "active"


def test_a_rules_path_that_cannot_be_read_is_refused_not_ignored(tmp_path):
    folder = tmp_path / "rules.json"
    folder.mkdir()
    with pytest.raises(RulesError):
        active_rules(folder)


def test_a_write_waits_for_the_lock_and_gives_up_cleanly(tmp_path, monkeypatch):
    path = tmp_path / "rules.json"
    rule, _ = add_proposal(proposal(), path=path)
    monkeypatch.setattr(store, "LOCK_TIMEOUT_SECONDS", 0.2)
    import sys
    import threading

    if sys.platform != "win32":
        pytest.skip("flock blocks without a timeout; the Windows path polls")
    held = threading.Event()
    release = threading.Event()

    def hold():
        with store._locked(path):
            held.set()
            release.wait(5)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(5)
    try:
        with pytest.raises(RulesError, match="locked"):
            approve(rule["id"], path=path)
    finally:
        release.set()
        t.join()
    assert approve(rule["id"], path=path)["status"] == "active"


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


def test_more_often_than_usual_needs_both_significance_and_a_real_difference():
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal as D

    from tradememory.sync.fills import RoundTrip
    from tradememory.sync.report import loss_patterns

    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def trip(i, pnl, size):
        return RoundTrip(source="x", account="a", symbol="BTC", direction="long",
                         entry_time=t0 + timedelta(hours=2 * i), exit_time=t0 + timedelta(hours=2 * i + 1),
                         opened_qty=D(size), max_position=D(size), avg_entry=D(100), avg_exit=D(100),
                         gross_pnl=D(pnl), fees=D(0), adds=0, fill_ids=[f"f{i}"])

    # Cycle: win, loss, loss, then a big losing trade. Half the trades after two losses
    # are big (the big one, and the small win that follows it), against a quarter overall.
    pattern = [(10, 1), (-5, 1), (-5, 1), (-20, 3)]
    trips = [trip(i, *pattern[i % 4]) for i in range(80)]
    s = loss_patterns(trips)["after_losing_streak"]
    assert s["sized_up_share"] == pytest.approx(0.5, abs=0.02) and s["baseline_sized_up_share"] == 0.25
    assert s["sized_up_p_value"] < 0.01 and s["more_often_than_usual"] is True
    assert suggest_size_rule(loss_patterns(trips), source="x") is not None

    # Same sizes everywhere: never more often than usual, whatever the p-value says.
    flat = [trip(i, -5, 1) for i in range(60)]
    s = loss_patterns(flat)["after_losing_streak"]
    assert s["more_often_than_usual"] is False
