"""Owner-side state the brake needs between calls: peak equity, halt, escalations, approvals, replay cache.

A plain JSON file so the owner can read it and the CLI can change it while the
proxy is running. Every operation takes an OS file lock, re-reads the file,
applies one change and writes it back atomically, so `tradememory proxy halt`
in one shell is seen by the next order in the other and nobody's write is
lost. A file that exists but cannot be read, parsed or validated is treated as
corrupt: the halt reads as FULL_HALT and nothing is written over it until the
owner sets the halt explicitly (the corrupt file is kept aside). Nothing here
is trusted evidence; the evidence is the chained decision events in TradeMemory.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

DEFAULT_STATE_PATH = Path.home() / ".tradememory" / "proxy-state.json"
APPROVAL_TTL = timedelta(minutes=15)
ESCALATION_TTL = timedelta(hours=24)
REPLAY_TTL = timedelta(hours=24)

HALT_STATES = ("NORMAL", "SOFT_HALT", "REDUCE_ONLY", "FULL_HALT", "RECONCILE_REQUIRED")
LOCK_TIMEOUT_SECONDS = 10.0


class StateCorrupt(RuntimeError):
    """The state file exists but cannot be trusted. The brake fails closed on it."""


def _aware(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _parse(stamp: Any) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


class ProxyState:
    def __init__(self, path: Path | str = DEFAULT_STATE_PATH):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self._data: dict[str, Any] = self._empty()
        self.corrupt_reason: str | None = None
        self.last_recovery: dict[str, Any] | None = None
        with self._locked():
            self._load()

    # ---------------------------------------------------------------- file
    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"peak_equity": None, "halt": "NORMAL", "escalated": {}, "approvals": {}, "forwarded": {}}

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        """Exclusive OS lock shared by every process touching this state file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+b")  # noqa: SIM115 - closed in finally
        try:
            if sys.platform == "win32":
                # LK_LOCK retries once a second and gives up after ten; poll LK_NBLCK instead.
                handle.seek(0)
                deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(0.005)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                if sys.platform == "win32":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def _mark_corrupt(self, reason: str) -> None:
        self.corrupt_reason = reason
        self._data = self._empty()
        self._data["halt"] = "FULL_HALT"

    def _load(self) -> None:
        """Read and validate the file. Missing file: defaults. Unreadable or invalid file: corrupt."""
        self.corrupt_reason = None
        data = self._empty()
        if not self.path.exists():
            self._data = data
            return
        raw: str | None = None
        last_error: Exception | None = None
        for _ in range(3):  # a rename in flight on Windows can refuse the read for a moment
            try:
                raw = self.path.read_text(encoding="utf-8-sig")
                break
            except ValueError as exc:  # UnicodeDecodeError: wrong encoding, not transient
                self._mark_corrupt(f"state file is not UTF-8: {exc}")
                return
            except OSError as exc:
                last_error = exc
                time.sleep(0.05)
        if raw is None:
            self._mark_corrupt(f"state file unreadable: {last_error}")
            return
        try:
            loaded = json.loads(raw)
        except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError both derive from ValueError
            self._mark_corrupt(f"state file is not valid JSON: {exc}")
            return
        if not isinstance(loaded, dict):
            self._mark_corrupt("state file is not a JSON object")
            return

        halt = loaded.get("halt", "NORMAL")
        if not isinstance(halt, str) or halt.strip().upper() not in HALT_STATES:
            self._mark_corrupt(f"halt is not a known state: {halt!r}")
            return
        data["halt"] = halt.strip().upper()

        peak = loaded.get("peak_equity")
        if peak is not None:
            try:
                peak_d = Decimal(str(peak))
                ok = peak_d.is_finite() and peak_d >= 0
            except InvalidOperation:
                ok = False
            if not ok:
                self._mark_corrupt(f"peak_equity is not a finite non-negative number: {peak!r}")
                return
            data["peak_equity"] = str(peak_d)

        for key in ("escalated", "approvals", "forwarded"):
            value = loaded.get(key, {})
            if not isinstance(value, dict) or any(not isinstance(v, dict) for v in value.values()):
                self._mark_corrupt(f"{key} is not an object of objects")
                return
            data[key] = value
        self._data = data

    def _salvage(self) -> tuple[dict[str, Any], list[str]]:
        """What can be kept from a corrupt file: fields that validate on their own."""
        kept: dict[str, Any] = self._empty()
        salvaged: list[str] = []
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return kept, salvaged
        if not isinstance(loaded, dict):
            return kept, salvaged
        peak = loaded.get("peak_equity")
        if peak is not None:
            try:
                peak_d = Decimal(str(peak))
                if peak_d.is_finite() and peak_d >= 0:
                    kept["peak_equity"] = str(peak_d)
                    salvaged.append("peak_equity")
            except InvalidOperation:
                pass
        for key in ("escalated", "approvals", "forwarded"):
            value = loaded.get(key)
            if isinstance(value, dict) and all(isinstance(v, dict) for v in value.values()):
                kept[key] = value
                salvaged.append(key)
        return kept, salvaged

    def _write(self) -> None:
        """Unique temp file, fsync, atomic replace. Never a shared temp name."""
        fd, tmp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(self._data, indent=2, sort_keys=True))
                fh.flush()
                os.fsync(fh.fileno())
            for attempt in range(20):  # Windows can refuse the replace for a moment after a close
                try:
                    os.replace(tmp_name, self.path)
                    break
                except PermissionError:
                    if attempt == 19:
                        raise
                    time.sleep(0.01)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise

    def _mutate(self, fn: Callable[[dict[str, Any]], Any], *, now: datetime | None = None,
                allow_when_corrupt: bool = False) -> Any:
        """Lock, re-read, apply one change, write atomically. Returns what fn returned."""
        with self._locked():
            self._load()
            self.last_recovery = None
            if self.corrupt_reason is not None:
                if not allow_when_corrupt:
                    raise StateCorrupt(self.corrupt_reason)
                kept, salvaged = self._salvage()
                aside = self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}")
                os.replace(self.path, aside)  # if this fails the corrupt file stays untouched
                self.last_recovery = {
                    "reason": self.corrupt_reason, "moved_to": str(aside), "salvaged": salvaged,
                    "reset": [k for k in ("peak_equity", "escalated", "approvals", "forwarded") if k not in salvaged],
                }
                self._data = kept
                self.corrupt_reason = None
            if now is not None:
                self._prune(self._data, _aware(now))
            result = fn(self._data)
            self._write()
            return result

    def _snapshot(self) -> dict[str, Any]:
        with self._locked():
            self._load()
            if self.corrupt_reason is not None:
                raise StateCorrupt(self.corrupt_reason)
            return self._data

    # ---------------------------------------------------------------- equity
    def observe_equity(self, equity: Decimal) -> Decimal:
        """Record equity; return drawdown from the running peak (never negative). Writes only when the peak moves."""
        with self._locked():
            self._load()
            if self.corrupt_reason is not None:
                raise StateCorrupt(self.corrupt_reason)
            stored = self._data.get("peak_equity")
            peak = Decimal(stored) if stored else equity
            if equity > peak or stored is None:
                self._data["peak_equity"] = str(max(peak, equity))
                self._write()
                peak = max(peak, equity)
            return max(Decimal("0"), peak - equity)

    # ---------------------------------------------------------------- halt
    @property
    def halt(self) -> str:
        """The owner's halt; FULL_HALT whenever the file cannot be trusted."""
        with self._locked():
            self._load()
        if self.corrupt_reason is not None:
            return "FULL_HALT"
        return str(self._data.get("halt") or "FULL_HALT")

    def set_halt(self, value: str) -> dict[str, Any] | None:
        """Set the owner halt. On a corrupt file this is the one write allowed: the corrupt
        file is moved aside first and whatever validates on its own is kept. Returns the
        recovery record when that happened, else None."""
        value = value.upper()
        if value not in HALT_STATES:
            raise ValueError(f"halt must be one of {HALT_STATES}")
        self._mutate(lambda data: data.__setitem__("halt", value), allow_when_corrupt=True)
        return self.last_recovery

    # ---------------------------------------------------------------- escalation and approval
    def escalate(self, intent_id: str, fingerprint: str, now: datetime | None = None, *, summary: str = "") -> None:
        """Remember the exact terms that escalated. New terms for the same intent void any pending approval."""
        at = _aware(now)

        def apply(data: dict[str, Any]) -> None:
            previous = data["escalated"].get(intent_id)
            if isinstance(previous, dict) and previous.get("fingerprint") != fingerprint:
                data["approvals"].pop(intent_id, None)
            data["escalated"][intent_id] = {"fingerprint": fingerprint, "at": at.isoformat(), "summary": summary}

        self._mutate(apply, now=at)

    def escalation(self, intent_id: str) -> dict[str, Any] | None:
        """The pending escalation for an intent, for the CLI to show what is being approved."""
        entry = self._snapshot()["escalated"].get(intent_id)
        return dict(entry) if isinstance(entry, dict) else None

    def approve(self, intent_id: str, fingerprint: str, now: datetime | None = None) -> str:
        """Approve exactly the terms the owner reviewed. Refused when the pending escalation
        carries different terms (the agent re-sent the order meanwhile). Returns the summary."""
        at = _aware(now)

        def apply(data: dict[str, Any]) -> str:
            escalated = data["escalated"].get(intent_id)
            if not isinstance(escalated, dict) or not escalated.get("fingerprint"):
                raise ValueError(f"nothing escalated for intent {intent_id}; approve after the agent's ESCALATE")
            if escalated["fingerprint"] != fingerprint:
                raise ValueError(
                    "the pending escalation carries different terms than the ones being approved: "
                    f"{escalated.get('summary') or escalated['fingerprint']}"
                )
            data["approvals"][intent_id] = {"at": at.isoformat(), "fingerprint": fingerprint}
            return str(escalated.get("summary") or fingerprint)

        return str(self._mutate(apply, now=at))

    def consume_approval(self, intent_id: str, fingerprint: str, now: datetime | None = None) -> bool:
        """Single use. True only for a fresh approval whose stored terms equal these terms."""
        at = _aware(now)

        def apply(data: dict[str, Any]) -> bool:
            approval = data["approvals"].pop(intent_id, None)
            if not isinstance(approval, dict):
                return False
            approved_at = _parse(approval.get("at"))
            if approved_at is None or approved_at < at - APPROVAL_TTL:
                return False
            if approval.get("fingerprint") != fingerprint:
                return False
            escalated = data["escalated"].get(intent_id)
            if not isinstance(escalated, dict) or escalated.get("fingerprint") != fingerprint:
                return False
            data["escalated"].pop(intent_id, None)
            return True

        return bool(self._mutate(apply, now=at))

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
        at = _aware(now)

        def apply(data: dict[str, Any]) -> None:
            data["forwarded"][intent_id] = {
                "at": at.isoformat(), "fingerprint": fingerprint, "status": status, "result": result,
            }

        self._mutate(apply, now=at)

    def mark_unknown(self, intent_id: str, fingerprint: str, error: str, now: datetime | None = None) -> None:
        self.remember_forwarded(intent_id, fingerprint, {"error": error[:300]}, now, status="unknown")

    def forget_forwarded(self, intent_id: str) -> None:
        self._mutate(lambda data: data["forwarded"].pop(intent_id, None))

    def forwarded_result(self, intent_id: str, now: datetime | None = None) -> dict[str, Any] | None:
        """The remembered forward for this intent, or None. A record with an unreadable
        timestamp is returned as status 'unknown' so the brake reconciles instead of re-sending."""
        at = _aware(now)
        data = self._snapshot()
        entry = data["forwarded"].get(intent_id)
        if not isinstance(entry, dict):
            return None
        stamp = _parse(entry.get("at"))
        if stamp is None:
            return {**entry, "status": "unknown"}
        if stamp < at - REPLAY_TTL:
            return None
        return dict(entry)

    @staticmethod
    def _prune(data: dict[str, Any], now: datetime) -> None:
        def keep(bucket: str, ttl: timedelta, *, unreadable_becomes_unknown: bool) -> None:
            cutoff = now - ttl
            fresh: dict[str, Any] = {}
            for key, value in data.get(bucket, {}).items():
                if not isinstance(value, dict):
                    continue
                stamp = _parse(value.get("at"))
                if stamp is None:
                    if unreadable_becomes_unknown:
                        # A forward whose time we cannot read must still force reconciliation;
                        # re-stamp it so it ages out normally instead of vanishing.
                        fresh[key] = {**value, "at": now.isoformat(), "status": "unknown"}
                    continue
                if stamp >= cutoff:
                    fresh[key] = value
            data[bucket] = fresh

        keep("forwarded", REPLAY_TTL, unreadable_becomes_unknown=True)
        keep("escalated", ESCALATION_TTL, unreadable_becomes_unknown=False)
        keep("approvals", APPROVAL_TTL, unreadable_becomes_unknown=False)

    @staticmethod
    def next_state_version() -> int:
        """Monotonic-enough version for TrustedAccountSnapshot.state_version."""
        return time.time_ns() // 1000
