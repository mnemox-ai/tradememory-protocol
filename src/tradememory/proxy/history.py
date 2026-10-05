"""The account's closed trades, read from the broker when a learned rule needs them.

A learned rule asks "were this account's last N closed trades losses?". The
answer comes from the broker's own fill activities, through the same upstream
MCP server the brake guards, at the moment an order could trip the rule. Not
from the memory database: a stop that closed at the broker an hour ago is in
the broker's fills now, but in memory only after someone runs a sync, and a
shared database can hold other accounts' and venues' trades.

The first read pages through every fill, oldest first, the way
`tradememory sync alpaca` does; later reads in the same process fetch only
fills created after the newest one already seen. A symbol whose rebuilt open
size disagrees with the broker's current position (history older than the
activity window, or a transfer) is left out, as in the sync. Any failure
raises, so the brake refuses the order instead of guessing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Awaitable, Callable

from ..rules.check import Close
from ..sync.alpaca import to_fill
from ..sync.fills import build_round_trips
from . import alpaca

UpstreamCall = Callable[[str, dict[str, Any]], Awaitable[Any]]
PAGE_SIZE = 100
MAX_PAGES = 200  # 20,000 fills, the same ceiling as `tradememory sync alpaca`
# Re-read this much before the newest fill already seen: a fill the broker reports late is
# not missed by the next incremental read. Duplicates are dropped by id.
OVERLAP = timedelta(minutes=10)


class HistoryUnavailable(RuntimeError):
    """The broker's fill history could not be read completely."""


def _positions(payload: Any) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for p in alpaca.as_list(alpaca.unwrap(payload)):
        if not isinstance(p, dict) or "symbol" not in p:
            raise HistoryUnavailable(f"unexpected position entry: {str(p)[:120]}")
        qty = Decimal(str(p["qty"]))
        if p.get("side") == "short" and qty > 0:
            qty = -qty
        out[str(p["symbol"]).replace("/", "").upper()] = qty
    return out


class BrokerCloses:
    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        self._fills: dict[str, dict[str, Any]] = {}
        self._newest: datetime | None = None

    async def _page(self, upstream: UpstreamCall, args: dict[str, Any]) -> list[dict[str, Any]]:
        page = alpaca.as_list(alpaca.unwrap(await upstream("get_account_activities_by_type", args)))
        for a in page:
            if not isinstance(a, dict) or not a.get("id") or not a.get("transaction_time"):
                raise HistoryUnavailable(f"unexpected fill activity: {str(a)[:120]}")
        return page

    async def _refresh(self, upstream: UpstreamCall) -> None:
        base: dict[str, Any] = {"activity_type": "FILL", "direction": "asc", "page_size": PAGE_SIZE}
        if self._newest is not None:
            base["after"] = (self._newest - OVERLAP).isoformat().replace("+00:00", "Z")
        token: str | None = None
        for _ in range(MAX_PAGES):
            args = dict(base)
            if token:
                args["page_token"] = token
            page = await self._page(upstream, args)
            for a in page:
                self._fills[str(a["id"])] = a
                t = datetime.fromisoformat(str(a["transaction_time"]).replace("Z", "+00:00"))
                if self._newest is None or t > self._newest:
                    self._newest = t
            if len(page) < PAGE_SIZE:
                return
            if str(page[-1]["id"]) == token:
                raise HistoryUnavailable("the broker returned the same page twice")
            token = str(page[-1]["id"])
        raise HistoryUnavailable(f"more than {MAX_PAGES * PAGE_SIZE:,} fills to read; refusing rather than guessing")

    async def closes(self, upstream: UpstreamCall) -> list[Close]:
        """Closed round trips of this account, newest first."""
        try:
            await self._refresh(upstream)
            positions = _positions(await upstream("get_all_positions", {}))
            fills = sorted(self._fills.values(), key=lambda a: (str(a["transaction_time"]), str(a["id"])))
            built = build_round_trips([to_fill(a, self.account_id) for a in fills])
        except HistoryUnavailable:
            raise
        except Exception as exc:  # malformed activity, upstream error: never a partial answer
            raise HistoryUnavailable(f"{type(exc).__name__}: {exc}"[:300]) from exc
        mismatched = {
            s for s in set(built.open_positions) | set(positions)
            if built.open_positions.get(s, 0) != positions.get(s, 0)
        }
        trips = [t for t in built.trips if t.symbol not in mismatched]
        trips.sort(key=lambda t: t.exit_time, reverse=True)
        return [Close(closed_at=t.exit_time, symbol=t.symbol, pnl=float(t.net_pnl), trade_id=t.trip_id) for t in trips]
