"""Policy file handling: load, seal and template a Mnemox Control PolicyBundle."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from mnemox_control.contracts import PolicyBundle

DEFAULT_POLICY_PATH = Path.home() / ".tradememory" / "policy.json"


def load_policy(path: Path | str) -> PolicyBundle:
    """Load a policy file and verify its seal.

    A policy whose content_hash does not match its content is refused.
    Control would deny every intent with HASH_MISMATCH anyway, but failing at
    startup gives the owner a readable error instead of a silent brick.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    policy = PolicyBundle.model_validate(raw)
    if policy.content_hash is None:
        raise ValueError(f"policy {path} is not sealed; run 'tradememory proxy seal {path}'")
    resealed = policy.model_copy(update={"content_hash": None}).with_content_hash()
    if resealed.content_hash != policy.content_hash:
        raise ValueError(
            f"policy {path} content_hash does not match its content; "
            f"run 'tradememory proxy seal {path}' after editing"
        )
    return policy


def seal_policy_file(path: Path | str) -> str:
    """Recompute and write content_hash for an edited policy file. Returns the hash."""
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw.pop("content_hash", None)
    sealed = PolicyBundle.model_validate(raw).with_content_hash()
    p.write_text(policy_to_json(sealed), encoding="utf-8")
    return sealed.content_hash or ""


def policy_to_json(policy: PolicyBundle) -> str:
    return json.dumps(policy.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def template_policy(
    *,
    broker: str,
    account_id: str,
    owner_id: str,
    allowed_symbols: list[str],
    max_order_notional: str = "1000",
    max_position_notional: str = "5000",
    max_daily_loss: str = "200",
    max_drawdown: str = "1000",
    approval_notional: str = "1000",
    max_leverage: str = "1",
    max_open_orders: int = 10,
    require_protective_stop: bool = True,
    max_stop_distance_bps: int | None = 500,
    min_stop_distance_bps: int | None = 10,
    allow_position_reversal: bool = False,
    days_valid: int = 30,
    now: datetime | None = None,
) -> PolicyBundle:
    """Build a sealed, conservative default policy for one broker account.

    Defaults are deliberately tight; a brake that starts loose teaches the
    owner nothing. approval_notional equal to max_order_notional means
    nothing escalates by default; lower it to require human approval above
    a size.
    """
    now = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)

    def iso(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    body: dict[str, Any] = {
        "policy_id": str(uuid.uuid4()),
        "version": "0.3",
        "revision": 1,
        "previous_policy_hash": None,
        "owner_id": owner_id,
        "account_id": account_id,
        "broker": broker,
        "allowed_symbols": allowed_symbols,
        "max_order_notional": max_order_notional,
        "max_position_notional": max_position_notional,
        "max_leverage": max_leverage,
        "max_daily_loss": max_daily_loss,
        "max_drawdown": max_drawdown,
        "approval_notional": approval_notional,
        "max_state_age_seconds": 120,
        "max_market_age_seconds": 60,
        "max_instrument_age_seconds": 86400,
        "max_price_deviation_bps": "100",
        "max_open_orders": max_open_orders,
        "max_order_quantity": None,
        "require_protective_stop": require_protective_stop,
        "max_stop_distance_bps": max_stop_distance_bps if require_protective_stop else None,
        "min_stop_distance_bps": min_stop_distance_bps if require_protective_stop else None,
        "allow_position_reversal": allow_position_reversal,
        "risk_day_start_hour_utc": 0,
        "allowed_weekly_windows": [{"start_minute_utc": 0, "end_minute_utc": 10080}],
        "valid_from": iso(now),
        "expires_at": iso(now + timedelta(days=days_valid)),
        "created_at": iso(now),
        "content_hash": None,
    }
    return PolicyBundle.model_validate(body).with_content_hash()


def pnl_window(risk_day_start_hour_utc: int, evaluated_at: datetime) -> tuple[datetime, datetime]:
    """The realized-P&L day Control expects, keyed to the policy's risk-day start.

    Must stay identical to mnemox_control.evaluator._expected_pnl_window;
    tests/proxy/test_policy.py pins the equivalence so a Control upgrade
    cannot silently produce PNL_WINDOW_MISMATCH on every intent.
    """
    evaluated_at = evaluated_at.astimezone(UTC)
    start = evaluated_at.replace(hour=risk_day_start_hour_utc, minute=0, second=0, microsecond=0)
    if evaluated_at < start:
        start -= timedelta(days=1)
    return start, start + timedelta(days=1)


def decimal_str(value: Decimal | str | float | int) -> str:
    return str(Decimal(str(value)))
