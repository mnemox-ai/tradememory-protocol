"""The rules file: proposed, active and retired rules, kept next to the brake's policy.

A rule is proposed by `tradememory sync ...` and does nothing until the owner
approves it. Approval stamps a hash over the rule's terms and status; a rule
whose terms or status no longer match its hash was edited by hand, and the
whole file is refused, so the brake refuses orders instead of enforcing terms
nobody approved. The hash is not a signature: anyone who can write the file
can also recompute it. It catches accidental and careless edits (a raised
limit, a retired rule flipped back on), not someone determined who already
has write access to your files.

Writes take an OS file lock and replace the file atomically, so a sync
proposing a rule cannot undo an approval made at the same moment.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

from .suggest import SIZE_AFTER_LOSING_STREAK

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

DEFAULT_RULES_PATH = Path.home() / ".tradememory" / "rules.json"
KINDS = {SIZE_AFTER_LOSING_STREAK}
ACTIONS = {"escalate", "deny"}
STATUSES = {"proposed", "active", "retired"}
# What the owner's approval (or retirement) covers. Changing any of them by hand breaks the hash.
TERMS = ("id", "kind", "streak", "max_notional", "action", "status", "approved_at", "retired_at")
MIN_ID_PREFIX = 6  # "r-" and four characters: enough to pick a rule, too long to hit one by accident
LOCK_TIMEOUT_SECONDS = 10


class RulesError(RuntimeError):
    """The rules file cannot be trusted; the brake refuses orders until it is fixed."""


def _iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rule_id(kind: str, streak: int, max_notional: str, source: str) -> str:
    key = f"{kind}|{streak}|{max_notional}|{source}"
    return "r-" + hashlib.sha256(key.encode()).hexdigest()[:10]


def terms_hash(rule: dict[str, Any]) -> str:
    terms = {k: rule.get(k) for k in TERMS}
    return hashlib.sha256(json.dumps(terms, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def whole_dollars(value: Any) -> str | None:
    """A limit as a whole positive number of account currency, or None when it is not one."""
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    if not d.is_finite() or d <= 0 or d != d.to_integral_value():
        return None
    return str(int(d))


def _validate(rule: Any, index: int, *, verify_hash: bool = True) -> dict[str, Any]:
    where = f"rule {index}"
    if not isinstance(rule, dict):
        raise RulesError(f"{where} is not an object")
    if rule.get("kind") not in KINDS:
        raise RulesError(f"{where} has unknown kind {rule.get('kind')!r}")
    if rule.get("status") not in STATUSES:
        raise RulesError(f"{where} has unknown status {rule.get('status')!r}")
    if rule.get("action") not in ACTIONS:
        raise RulesError(f"{where} has unknown action {rule.get('action')!r}")
    streak = rule.get("streak")
    if not isinstance(streak, int) or isinstance(streak, bool) or not 1 <= streak <= 20:
        raise RulesError(f"{where} streak must be a whole number from 1 to 20")
    if whole_dollars(rule.get("max_notional")) != rule.get("max_notional"):
        raise RulesError(f"{where} max_notional must be a whole positive number written as digits")
    if not isinstance(rule.get("id"), str) or not rule["id"].startswith("r-"):
        raise RulesError(f"{where} has no id")
    if rule["status"] == "proposed" and verify_hash and (rule.get("approved_at") or rule.get("retired_at")):
        raise RulesError(f"{where} ({rule['id']}) was approved once and switched back to proposed by hand")
    if rule["status"] in ("active", "retired") and verify_hash:
        if not rule.get("approved_at"):
            raise RulesError(f"{where} ({rule['id']}) is {rule['status']} but was never approved")
        if rule.get("content_hash") != terms_hash(rule):
            raise RulesError(
                f"{where} ({rule['id']}) was changed by hand after it was approved; "
                f"retire it with `tradememory rules retire {rule['id']}` and approve it again"
            )
    return rule


def load_rules(path: Path | str = DEFAULT_RULES_PATH, *, verify_hash: bool = True) -> list[dict[str, Any]]:
    """Every rule in the file, validated. A file that does not exist means no rules.

    ``verify_hash=False`` is only for retiring a rule that was edited by hand.
    Any other read failure (permissions, a directory, bad JSON) raises.
    """
    p = Path(path).expanduser()
    try:
        text = p.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise RulesError(f"cannot read the rules file: {exc.strerror or exc}") from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise RulesError(f"the rules file is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise RulesError("not a rules file (expected an object with a 'rules' list)")
    rules = [_validate(r, i, verify_hash=verify_hash) for i, r in enumerate(data["rules"])]
    ids = [r["id"] for r in rules]
    if len(ids) != len(set(ids)):
        raise RulesError("two rules have the same id")
    return rules


def active_rules(path: Path | str = DEFAULT_RULES_PATH) -> list[dict[str, Any]]:
    return [r for r in load_rules(path) if r["status"] == "active"]


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Exclusive OS lock around one read-modify-write of the rules file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path.with_name(path.name + ".lock"), "a+b")  # noqa: SIM115 - closed in finally
    try:
        if sys.platform == "win32":
            handle.seek(0)
            deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
            while True:  # LK_LOCK gives up after ten one-second retries; poll LK_NBLCK instead
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise RulesError("the rules file is locked by another process") from None
                    time.sleep(0.02)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if sys.platform == "win32":
                handle.seek(0)
                with contextlib.suppress(OSError):
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _write(path: Path, rules: list[dict[str, Any]]) -> None:
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"version": 1, "rules": rules}, indent=2, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        for attempt in range(20):  # Windows can refuse the replace for a moment after a close
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.01)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def add_proposal(
    proposal: dict[str, Any], *, path: Path | str = DEFAULT_RULES_PATH, now: datetime | None = None
) -> tuple[dict[str, Any], bool]:
    """Store a suggested rule as proposed. Returns (rule, True) or the existing rule and False."""
    p = Path(path).expanduser()
    with _locked(p):
        rules = load_rules(p)
        rid = rule_id(proposal["kind"], proposal["streak"], proposal["max_notional"], proposal["source"])
        for r in rules:
            if r["id"] == rid:
                return r, False
        rule = {
            "id": rid,
            "kind": proposal["kind"],
            "streak": proposal["streak"],
            "max_notional": str(proposal["max_notional"]),
            "action": proposal["action"],
            "source": proposal["source"],
            "evidence": proposal["evidence"],
            "status": "proposed",
            "created_at": _iso(now or datetime.now(timezone.utc)),
            "approved_at": None,
            "retired_at": None,
            "content_hash": None,
        }
        _validate(rule, len(rules))
        _write(p, rules + [rule])
        return rule, True


def _find(rules: list[dict[str, Any]], rid: str) -> dict[str, Any]:
    rid = rid.strip()
    exact = [r for r in rules if r["id"] == rid]
    if exact:
        return exact[0]
    if len(rid) < MIN_ID_PREFIX:
        raise KeyError(f"no rule {rid!r}; give the full id or at least {MIN_ID_PREFIX} characters of it")
    matches = [r for r in rules if r["id"].startswith(rid)]
    if len(matches) != 1:
        raise KeyError(f"no rule {rid!r}" if not matches else f"{rid!r} matches more than one rule")
    return matches[0]


def approve(
    rid: str,
    *,
    path: Path | str = DEFAULT_RULES_PATH,
    now: datetime | None = None,
    max_notional: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    """Turn a proposed rule on, optionally with the owner's own limit or action."""
    p = Path(path).expanduser()
    with _locked(p):
        rules = load_rules(p)
        rule = _find(rules, rid)
        if rule["status"] != "proposed":
            raise ValueError(f"{rule['id']} is {rule['status']}; only a proposed rule can be approved")
        if max_notional is not None:
            limit = whole_dollars(max_notional)
            if limit is None:
                raise ValueError("--max-notional must be a whole positive number, e.g. 1500")
            rule["max_notional"] = limit
        if action is not None:
            if action not in ACTIONS:
                raise ValueError(f"action must be one of {sorted(ACTIONS)}")
            rule["action"] = action
        rule["status"] = "active"
        rule["approved_at"] = _iso(now or datetime.now(timezone.utc))
        rule["content_hash"] = terms_hash(rule)
        _write(p, rules)
        return rule


def retire(rid: str, *, path: Path | str = DEFAULT_RULES_PATH, now: datetime | None = None) -> dict[str, Any]:
    """Turn a rule off for good. A retired rule is kept as a record and never enforced."""
    p = Path(path).expanduser()
    with _locked(p):
        # A rule edited by hand must still be retirable, or the file stays refused.
        rules = load_rules(p, verify_hash=False)
        rule = _find(rules, rid)
        if rule["status"] == "retired":
            return rule
        rule["status"] = "retired"
        rule["retired_at"] = _iso(now or datetime.now(timezone.utc))
        if not rule.get("approved_at"):
            rule["approved_at"] = rule["retired_at"]  # a proposal turned down: the retirement is the decision
        rule["content_hash"] = terms_hash(rule)
        _write(p, rules)
        return rule
