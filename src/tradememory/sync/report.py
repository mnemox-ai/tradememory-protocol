"""Where a trader's own history loses money. Descriptive statistics only.

Every number here describes trades that already happened in one account.
Nothing in it says what to trade next.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from statistics import median
from typing import Any

from .fills import RoundTrip

STREAK = 2  # losses in a row before the next trade counts as "after a losing streak"
SIZE_UP = 1.5  # notional at least this many times the trader's median counts as sizing up
MIN_SAMPLE = 5  # below this a pattern is reported as "not enough trades"


def _f(x: Decimal) -> float:
    return float(x)


def _summary(trips: list[RoundTrip]) -> dict[str, Any]:
    if not trips:
        return {"trades": 0, "win_rate": None, "net_pnl": 0.0}
    wins = sum(1 for t in trips if t.net_pnl > 0)
    return {
        "trades": len(trips),
        "win_rate": wins / len(trips),
        "net_pnl": _f(sum((t.net_pnl for t in trips), Decimal(0))),
    }


def loss_patterns(trips: list[RoundTrip]) -> dict[str, Any]:
    if not trips:
        return {"trades": 0}
    by_entry = sorted(trips, key=lambda t: t.entry_time)
    by_exit = sorted(trips, key=lambda t: t.exit_time)
    median_notional = median(_f(t.notional) for t in trips)

    # 1. What happens to size right after losses in a row.
    after_streak: list[RoundTrip] = []
    recent: list[RoundTrip] = []  # the last STREAK trips closed before the current entry
    j = 0
    for trip in by_entry:
        while j < len(by_exit) and by_exit[j].exit_time <= trip.entry_time:
            if by_exit[j] is not trip:
                recent = (recent + [by_exit[j]])[-STREAK:]
            j += 1
        if len(recent) == STREAK and all(t.net_pnl < 0 for t in recent):
            after_streak.append(trip)
    sized_up = [t for t in after_streak if median_notional and _f(t.notional) >= SIZE_UP * median_notional]
    streak = {
        "trades_after_streak": len(after_streak),
        "sized_up": len(sized_up),
        "sized_up_share": len(sized_up) / len(after_streak) if after_streak else None,
        "sized_up_result": _summary(sized_up),
        "after_streak_result": _summary(after_streak),
        "enough_data": len(after_streak) >= MIN_SAMPLE,
    }

    # 2. Holding losers longer than winners.
    winners = [t.hold_seconds for t in trips if t.net_pnl > 0]
    losers = [t.hold_seconds for t in trips if t.net_pnl < 0]
    hold = {
        "median_hold_winners_s": median(winners) if winners else None,
        "median_hold_losers_s": median(losers) if losers else None,
        "enough_data": len(winners) >= MIN_SAMPLE and len(losers) >= MIN_SAMPLE,
    }

    # 3. Where it loses: symbols and entry hours (UTC).
    per_symbol: dict[str, list[RoundTrip]] = defaultdict(list)
    per_hour: dict[int, list[RoundTrip]] = defaultdict(list)
    for t in trips:
        per_symbol[t.symbol].append(t)
        per_hour[t.entry_time.hour].append(t)
    worst_symbols = sorted(
        (r for r in ({"symbol": s, **_summary(ts)} for s, ts in per_symbol.items()) if r["net_pnl"] < 0),
        key=lambda r: r["net_pnl"],
    )[:3]
    worst_hours = sorted(
        (r for r in ({"hour_utc": h, **_summary(ts)} for h, ts in per_hour.items() if len(ts) >= MIN_SAMPLE)
         if r["net_pnl"] < 0),
        key=lambda r: r["net_pnl"],
    )[:3]

    # 4. The single worst trades.
    biggest = [
        {
            "symbol": t.symbol,
            "direction": t.direction,
            "entry_time": t.entry_time.isoformat(),
            "net_pnl": _f(t.net_pnl),
            "notional": _f(t.notional),
            "hold_seconds": t.hold_seconds,
        }
        for t in sorted(trips, key=lambda t: t.net_pnl)[:3]
        if t.net_pnl < 0
    ]

    return {
        **_summary(trips),
        "fees": _f(sum((t.fees for t in trips), Decimal(0))),
        "median_notional": median_notional,
        "after_losing_streak": streak,
        "holding": hold,
        "worst_symbols": worst_symbols,
        "worst_entry_hours_utc": worst_hours,
        "biggest_losses": biggest,
    }


def _money(x: float) -> str:
    return f"{'-' if x < 0 else ''}${abs(x):,.0f}"


def _dur(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    if seconds >= 86400:
        return f"{seconds / 86400:.1f}d"
    if seconds >= 3600:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 60:.0f}m"


def render_report(stats: dict[str, Any], *, title: str) -> str:
    if not stats.get("trades"):
        return f"{title}\nNo closed trades found."
    lines = [
        title,
        "Descriptive statistics of this account's own closed trades. Not investment advice.",
        "",
        f"Closed trades: {stats['trades']}   win rate: {stats['win_rate']:.0%}   "
        f"net P&L: {_money(stats['net_pnl'])}   fees: {_money(stats['fees'])}",
        "",
    ]
    s = stats["after_losing_streak"]
    lines.append(f"After {STREAK} losses in a row ({s['trades_after_streak']} trades):")
    if not s["enough_data"]:
        lines.append("  not enough trades to say.")
    else:
        r = s["after_streak_result"]
        lines.append(
            f"  {s['sized_up']} of them ({s['sized_up_share']:.0%}) were {SIZE_UP:g}x your usual size or more."
        )
        lines.append(f"  All {s['trades_after_streak']} won {r['win_rate']:.0%} and made {_money(r['net_pnl'])}.")
        if s["sized_up"]:
            u = s["sized_up_result"]
            lines.append(f"  The {s['sized_up']} sized-up trades won {u['win_rate']:.0%} and made {_money(u['net_pnl'])}.")
    h = stats["holding"]
    lines.append("")
    if h["enough_data"]:
        lines.append(
            f"Median hold: winners {_dur(h['median_hold_winners_s'])}, losers {_dur(h['median_hold_losers_s'])}."
        )
    else:
        lines.append("Median hold: not enough winners and losers to compare.")
    if stats["worst_symbols"]:
        lines.append("")
        lines.append("Worst symbols:")
        for r in stats["worst_symbols"]:
            lines.append(f"  {r['symbol']:<10} {r['trades']:>4} trades  {_money(r['net_pnl']):>10}  won {r['win_rate']:.0%}")
    if stats["worst_entry_hours_utc"]:
        lines.append("")
        lines.append("Worst entry hours (UTC):")
        for r in stats["worst_entry_hours_utc"]:
            lines.append(f"  {r['hour_utc']:02d}:00     {r['trades']:>4} trades  {_money(r['net_pnl']):>10}  won {r['win_rate']:.0%}")
    if stats["biggest_losses"]:
        lines.append("")
        lines.append("Biggest single losses:")
        for r in stats["biggest_losses"]:
            lines.append(
                f"  {r['entry_time'][:16].replace('T', ' ')}  {r['direction']:<5} {r['symbol']:<8} "
                f"{_money(r['net_pnl']):>10}  held {_dur(r['hold_seconds'])}"
            )
    return "\n".join(lines)
