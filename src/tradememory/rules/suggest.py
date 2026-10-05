"""Turn a history's loss patterns into a rule the owner can approve.

Only one kind exists so far: size after a losing streak. It is suggested when
the history shows the trader sizing up right after losses in a row more often
than they size up in general (a one-sided binomial test against their own
rate, p <= 0.10, and at least 5 points above it: the report's
``more_often_than_usual``), and those sized-up trades losing money in total. Without the comparison, a trader who often trades big would be told
they "revenge trade": in a 2026-10-05 sample of leaderboard accounts the
share after a streak sat within a few points of each trader's usual share.
The threshold is the size the report calls "sized up" (SIZE_UP times the
median notional), so the rule holds exactly the orders the report counted.

The web page on mnemox.ai ports this function; tests/test_rules.py
and the page's parity fixtures pin the two to the same output.
"""

from __future__ import annotations

import math
from typing import Any

from ..sync.report import SIZE_UP, STREAK

SIZE_AFTER_LOSING_STREAK = "size_after_losing_streak"
MIN_SIZED_UP = 2  # one sized-up loser is an anecdote, not a habit


def suggest_size_rule(stats: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    """A proposed rule from ``loss_patterns`` output, or None when the history does not call for one."""
    streak = stats.get("after_losing_streak")
    median_notional = stats.get("median_notional")
    if not streak or not streak.get("enough_data") or not median_notional:
        return None
    if streak["sized_up"] < MIN_SIZED_UP:
        return None
    if not streak.get("more_often_than_usual"):
        return None
    p_value = streak["sized_up_p_value"]
    sized_up = streak["sized_up_result"]
    if sized_up["net_pnl"] >= 0:
        return None
    # Whole dollars, rounded down: an order at the reported "sized up" size is held.
    max_notional = max(1, math.floor(SIZE_UP * median_notional))
    return {
        "kind": SIZE_AFTER_LOSING_STREAK,
        "streak": STREAK,
        "max_notional": str(max_notional),
        "action": "escalate",
        "source": source,
        "evidence": {
            "history_trades": stats["trades"],
            "median_notional": round(median_notional, 2),
            "trades_after_streak": streak["trades_after_streak"],
            "sized_up": streak["sized_up"],
            "sized_up_share": round(streak["sized_up_share"], 4),
            "usual_sized_up_share": round(streak["baseline_sized_up_share"], 4),
            "p_value": round(p_value, 4),
            "sized_up_win_rate": sized_up["win_rate"],
            "sized_up_net_pnl": round(sized_up["net_pnl"], 2),
        },
    }


def describe_rule(rule: dict[str, Any]) -> str:
    """One line a person can approve or turn down."""
    held = "held for your approval" if rule.get("action", "escalate") == "escalate" else "refused"
    return (
        f"After {rule['streak']} losses in a row, new orders of ${int(rule['max_notional']):,} "
        f"or more are {held}."
    )


def describe_evidence(rule: dict[str, Any]) -> str:
    e = rule["evidence"]
    return (
        f"In {e['history_trades']} closed trades ({rule['source']}), {e['sized_up']} of the "
        f"{e['trades_after_streak']} trades after {rule['streak']} losses in a row were "
        f"{SIZE_UP:g}x the usual size or more ({e['sized_up_share']:.0%}, against "
        f"{e['usual_sized_up_share']:.0%} of all trades); together they made "
        f"{'-' if e['sized_up_net_pnl'] < 0 else ''}${abs(e['sized_up_net_pnl']):,.0f}."
    )
