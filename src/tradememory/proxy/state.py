"""Owner-side state the brake needs between calls: peak equity, halt, escalations, approvals, replay cache.

Kept in a plain JSON file so the owner can read it and the CLI can change it
while the proxy is running. Every operation re-reads the file first and
writes it back atomically, so `tradememory proxy halt` in one shell is seen
by the next order in the other. Nothing here is trusted evidence; the
evidence is the chained decision events in TradeMemory.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

DEFAULT_STATE_PATH = Path.home() / ".tradememory" / "proxy-state.json"
APPROVAL_TTL = timedelta(minutes=15)
REPLAY_TTL = timedelta(hours=24)

HALT_STATES = ("NORMAL", "SOFT_HALT", "REDUCE_ONLY", "FULL_HALT", "RECONCILE_REQUIRED")


def _parse(stamp: Any) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


class ProxyState:
    def __init__(self, path: Path | str = DEFAULT_STATE_PATH):
        self.path = Path(path)
        self._data = self._read()

    # ---------------------------------------------------------------- file
    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"peak_equity": None, "halt": "NORMAL", "escalated": {}, "approvals": {}, "forwarded": {}}

    def _read(self) -> dict[str, Any]:
        data = self._empty()
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                loaded = {}
            if isinstance(loaded, dict):
                for key in data:
                    if key in loaded and isinstance(loaded[key], type(data[key]) if data[key] is not None else object):
                        data[key] = loaded[key]
                    elif key in loaded and data[key] is None:
                        data[key] = loaded[key]
        return data

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def _mutate(self, fn: Callable[[dict[str, Any]], Any]) -> Any:
        """Re-read, apply one change, write atomically. Returns what fn returned."""
        self._data = self._read()
        result = fn(self._data)
        self._write()
        return result

    # ---------------------------------------------------------------- equity
    def observe_equity(self, equity: Decimal) -> Decimal:
        """Record equity; return drawdown from the running peak (never negative)."""

        def apply(data: dict[str, Any]) -> Decimal:
            stored = data.get("peak_equity")
            peak = Decimal(str(stored)) if stored else equity
            if equity > peak:
                peak = equity
            data["peak_equity"] = str(peak)
            return max(Decimal("0"), peak - equity)

        return self._mutate(apply)

    # ---------------------------------------------------------------- halt
    @property
    def halt(self) -> str:
        self._data = self._read()
        value = str(self._data.get("halt") or "NORMAL").upper()
        return value if value in HALT_STATES else "FULL_HALT"  # a garbled halt reads as the safe one

    def set_halt(self, value: str) -> None:
        value = value.upper()
        if value not in HALT_STATES:
            raise ValueError(f"halt must be one of {HALT_STATES}")
        self._mutate(lambda data: data.__setitem__("halt", value))

    # ---------------------------------------------------------------- escalation and approval
    def escalate(self, intent_id: str, fingerprint: str, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)

        def apply(data: dict[str, Any]) -> None:
            data["escalated"][intent_id] = {"fingerprint": fingerprint, "at": now.isoformat()}

        self._mutate(apply)

    def approve(self, intent_id: str, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        self._mutate(lambda data: data["approvals"].__setitem__(intent_id, now.isoformat()))

    def consume_approval(self, intent_id: str, fingerprint: str, now: datetime | None = None) -> bool:
        """Single use. Succeeds only for a fresh approval of the exact terms that escalated."""
        now = now or datetime.now(UTC)

        def apply(data: dict[str, Any]) -> bool:
            stamp = data["approvals"].pop(intent_id, None)
            if stamp is None:
                return False
            approved_at = _parse(stamp)
            if approved_at is None or approved_at < now - APPROVAL_TTL:
                return False
            escalated = data["escalated"].get(intent_id)
            if not isinstance(escalated, dict) or escalated.get("fingerprint") != fingerprint:
                return False
            data["escalated"].pop(intent_id, None)
            return True

        return bool(self._mutate(apply))

    # ---------------------------------------------------------------- at-most-once
    def remember_forwarded(
        self,
        intent_id: str,
        fingerprint: str,
        result: dict[str, Any],
        now: datetime | None = None,
        *,
        status: str = "placed",
    ) -> None:
        now = now or datetime.now(UTC)

        def apply(data: dict[str, Any]) -> None:
            self._prune(data, now)
            data["forwarded"][intent_id] = {
                "at": now.isoformat(), "fingerprint": fingerprint, "status": status, "result": result,
            }

        self._mutate(apply)

    def mark_unknown(self, intent_id: str, fingerprint: str, error: str, now: datetime | None = None) -> None:
        self.remember_forwarded(intent_id, fingerprint, {"error": error[:300]}, now, status="unknown")

    def forget_forwarded(self, intent_id: str) -> None:
        self._mutate(lambda data: data["forwarded"].pop(intent_id, None))

    def forwarded_result(self, intent_id: str, now: datetime | None = None) -> dict[str, Any] | None:
        now = now or datetime.now(UTC)
        self._data = self._read()
        entry = self._data["forwarded"].get(intent_id)
        if not isinstance(entry, dict):
            return None
        at = _parse(entry.get("at"))
        if at is None or at < now - REPLAY_TTL:
            return None
        return dict(entry)

    @staticmethod
    def _prune(data: dict[str, Any], now: datetime) -> None:
        cutoff = now - REPLAY_TTL
        data["forwarded"] = {
            key: value
            for key, value in data["forwarded"].items()
            if isinstance(value, dict) and (_parse(value.get("at")) or cutoff) >= cutoff
        }

    @staticmethod
    def next_state_version() -> int:
        """Monotonic-enough version for TrustedAccountSnapshot.state_version."""
        return time.time_ns() // 1000
