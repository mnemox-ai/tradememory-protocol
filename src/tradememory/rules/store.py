"""The rules file: proposed, active and retired rules, kept next to the brake's policy.

A rule is proposed by `tradememory sync ...` and does nothing until the owner
approves it. Approval stamps a content hash over the rule's terms; an active
rule whose terms no longer match its hash was edited after approval and the
whole file is refused, so the brake fails closed instead of enforcing terms
nobody approved.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .suggest import SIZE_AFTER_LOSING_STREAK

DEFAULT_RULES_PATH = Path.home() / ".tradememory" / "rules.json"
KINDS = {SIZE_AFTER_LOSING_STREAK}
ACTIONS = {"escalate", "deny"}
STATUSES = {"proposed", "active", "retired"}
# Fields the approval covers. Changing any of them on an active rule breaks its hash.
TERMS = ("id", "kind", "streak", "max_notional", "action", "approved_at")


class RulesError(RuntimeError):
    """The rules file cannot be trusted; the brake refuses orders until it is fixed."""


def _iso(now: datetime) -> str:
    return now.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rule_id(kind: str, streak: int, max_notional: str, source: str) -> str:
    key = f"{kind}|{streak}|{max_notional}|{source}"
    return "r-" + hashlib.sha256(key.encode()).hexdigest()[:10]


def terms_hash(rule: dict[str, Any]) -> str:
    terms = {k: rule.get(k) for k in TERMS}
    return hashlib.sha256(json.dumps(terms, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _positive_decimal(value: Any) -> Decimal | None:
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return None
    return d if d.is_finite() and d > 0 else None


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
    if _positive_decimal(rule.get("max_notional")) is None:
        raise RulesError(f"{where} max_notional must be a positive number")
    if not isinstance(rule.get("id"), str) or not rule["id"]:
        raise RulesError(f"{where} has no id")
    if rule["status"] == "active" and verify_hash:
        if not rule.get("approved_at"):
            raise RulesError(f"{where} ({rule['id']}) is active but was never approved")
        if rule.get("content_hash") != terms_hash(rule):
            raise RulesError(
                f"{where} ({rule['id']}) was changed after it was approved; "
                f"retire it and approve it again"
            )
    return rule


def load_rules(path: Path | str = DEFAULT_RULES_PATH, *, verify_hash: bool = True) -> list[dict[str, Any]]:
    """Every rule in the file, validated. A missing file means no rules.

    ``verify_hash=False`` is only for retiring a rule that was edited after approval.
    """
    p = Path(path).expanduser()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RulesError(f"cannot read {p}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise RulesError(f"{p} is not a rules file (expected an object with a 'rules' list)")
    rules = [_validate(r, i, verify_hash=verify_hash) for i, r in enumerate(data["rules"])]
    ids = [r["id"] for r in rules]
    if len(ids) != len(set(ids)):
        raise RulesError(f"{p} has two rules with the same id")
    return rules


def active_rules(path: Path | str = DEFAULT_RULES_PATH) -> list[dict[str, Any]]:
    return [r for r in load_rules(path) if r["status"] == "active"]


def _write(path: Path, rules: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        "created_at": _iso(now or datetime.now(UTC)),
        "approved_at": None,
        "retired_at": None,
        "content_hash": None,
    }
    _validate(rule, len(rules))
    _write(p, rules + [rule])
    return rule, True


def _find(rules: list[dict[str, Any]], rid: str) -> dict[str, Any]:
    matches = [r for r in rules if r["id"] == rid or r["id"].startswith(rid)] if rid else []
    if len(matches) != 1:
        raise KeyError(rid if not matches else f"{rid} matches more than one rule")
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
    rules = load_rules(p)
    rule = _find(rules, rid)
    if rule["status"] != "proposed":
        raise ValueError(f"{rule['id']} is {rule['status']}; only a proposed rule can be approved")
    if max_notional is not None:
        if _positive_decimal(max_notional) is None:
            raise ValueError("max_notional must be a positive number")
        rule["max_notional"] = str(Decimal(str(max_notional)))
    if action is not None:
        if action not in ACTIONS:
            raise ValueError(f"action must be one of {sorted(ACTIONS)}")
        rule["action"] = action
    rule["status"] = "active"
    rule["approved_at"] = _iso(now or datetime.now(UTC))
    rule["content_hash"] = terms_hash(rule)
    _write(p, rules)
    return rule


def retire(rid: str, *, path: Path | str = DEFAULT_RULES_PATH, now: datetime | None = None) -> dict[str, Any]:
    """Turn a rule off for good. A retired rule is kept as a record and never enforced."""
    p = Path(path).expanduser()
    # An active rule edited after approval must still be retirable, or the file stays refused.
    rules = load_rules(p, verify_hash=False)
    rule = _find(rules, rid)
    if rule["status"] == "retired":
        return rule
    rule["status"] = "retired"
    rule["retired_at"] = _iso(now or datetime.now(UTC))
    _write(p, rules)
    return rule
