"""Owner-side state the brake needs between calls: peak equity, halt, approvals, replay cache.

Kept in a plain JSON file so the owner can read and edit it. Nothing here is
trusted evidence; the evidence is the chained decision events in TradeMemory.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

DEFAULT_STATE_PATH = Path.home() / ".tradememory" / "proxy-state.json"
APPROVAL_TTL = timedelta(minutes=15)
REPLAY_TTL = timedelta(hours=24)

HALT_STATES = ("NORMAL", "SOFT_HALT", "REDUCE_ONLY", "FULL_HALT", "RECONCILE_REQUIRED")


class ProxyState:
    def __init__(self, path: Path | str = DEFAULT_STATE_PATH):
        self.path = Path(path)
        self._data: dict[str, Any] = {
            "peak_equity": None,
            "halt": "NORMAL",
            "approvals": {},
            "forwarded": {},
        }
        if self.path.exists():
            self._data.update(json.loads(self.path.read_text(encoding="utf-8")))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    # peak equity, for drawdown_from_peak
    def observe_equity(self, equity: Decimal) -> Decimal:
        """Record equity; return drawdown from the running peak (never negative)."""
        stored = self._data.get("peak_equity")
        peak = Decimal(stored) if stored else equity
        if equity > peak:
            peak = equity
        self._data["peak_equity"] = str(peak)
        self._save()
        return max(Decimal("0"), peak - equity)

    # halt
    @property
    def halt(self) -> str:
        return str(self._data.get("halt") or "NORMAL")

    def set_halt(self, value: str) -> None:
        value = value.upper()
        if value not in HALT_STATES:
            raise ValueError(f"halt must be one of {HALT_STATES}")
        self._data["halt"] = value
        self._save()

    # human approvals for ESCALATE
    def approve(self, intent_id: str, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        self._data["approvals"][intent_id] = now.isoformat()
        self._save()

    def consume_approval(self, intent_id: str, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        stamp = self._data["approvals"].pop(intent_id, None)
        self._save()
        if stamp is None:
            return False
        return datetime.fromisoformat(stamp) >= now - APPROVAL_TTL

    # at-most-once replay cache keyed by intent_id
    def remember_forwarded(
        self, intent_id: str, result: dict[str, Any], now: datetime | None = None
    ) -> None:
        now = now or datetime.now(UTC)
        self._prune(now)
        self._data["forwarded"][intent_id] = {"at": now.isoformat(), "result": result}
        self._save()

    def forwarded_result(self, intent_id: str, now: datetime | None = None) -> dict[str, Any] | None:
        now = now or datetime.now(UTC)
        entry = self._data["forwarded"].get(intent_id)
        if not entry:
            return None
        if datetime.fromisoformat(entry["at"]) < now - REPLAY_TTL:
            return None
        return dict(entry["result"])

    def _prune(self, now: datetime) -> None:
        cutoff = now - REPLAY_TTL
        self._data["forwarded"] = {
            key: value
            for key, value in self._data["forwarded"].items()
            if datetime.fromisoformat(value["at"]) >= cutoff
        }

    @staticmethod
    def next_state_version() -> int:
        """Monotonic-enough version for TrustedAccountSnapshot.state_version."""
        return time.time_ns() // 1000
