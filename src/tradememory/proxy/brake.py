"""The brake: a fastmcp middleware that evaluates order tools before they reach the broker.

Invariants (tests/proxy pins each one):
- An order tool is never forwarded without a sealed, in-window evaluation that said ALLOW,
  or ESCALATE lifted by a fresh owner approval of the exact same terms.
- Any failure to build that evaluation is a DENY, never a pass-through. Tools the brake
  does not classify are refused too.
- Exit tools are never blocked; they are recorded.
- Cancelling the protective stop of an open position is refused while the policy
  requires stops; other cancels are forwarded and recorded.
- The same client_order_id is forwarded at most once; a retry returns the first result,
  and a retry after a failed forward reconciles with the broker before placing anything.
- Every decision, including replays, failed forwards and fail-closed denies, is a
  decision_events row and its audit-chain link, written in one transaction.
- Order evaluations are serialised, so two concurrent orders cannot both pass a limit
  that only one of them fits under.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mnemox_control.canonical import content_sha256
from mnemox_control.contracts import Decision, OrderIntent, PolicyBundle
from mnemox_control.evaluation import EvaluationResult, PositionEffect, RuleOutcome
from mnemox_control.evaluator import evaluate
from mnemox_control.state import InstrumentSpec, MarketQuote

from ..audit.chain import ChainBuilder
from ..db import Database
from ..rules.check import check_order, rules_in_reach
from ..rules.store import RulesError, active_rules
from . import alpaca
from .history import BrokerCloses
from .policy import pnl_window
from .state import ProxyState

log = logging.getLogger("tradememory.proxy")

UpstreamCall = Callable[[str, dict[str, Any]], Awaitable[Any]]
INSTRUMENT_CACHE_TTL = timedelta(minutes=5)
FAIL_CLOSED_CODE = "PROXY_FAIL_CLOSED"
UNSUPPORTED_CODE = "PROXY_UNSUPPORTED_TOOL"
CLIENT_ORDER_ID_REQUIRED_CODE = "PROXY_CLIENT_ORDER_ID_REQUIRED"
CLIENT_ORDER_ID_REUSED_CODE = "PROXY_CLIENT_ORDER_ID_REUSED"
STOP_CANCEL_CODE = "PROXY_PROTECTIVE_STOP_CANCEL_FORBIDDEN"
ARGS_STORED_LIMIT = 4096


class ForwardError(RuntimeError):
    """The broker call failed after an ALLOW was recorded; the order's fate is unknown."""


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json"))
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _stored_args(args: dict[str, Any]) -> Any:
    """Arguments as recorded on a decision: bounded so an agent cannot bloat the ledger."""
    safe = _json_safe(args)
    text = json.dumps(safe, sort_keys=True, separators=(",", ":"))
    if len(text) <= ARGS_STORED_LIMIT:
        return safe
    return {"_truncated": True, "_sha256": hashlib.sha256(text.encode()).hexdigest(), "_head": text[:ARGS_STORED_LIMIT]}


class Collected:
    """Everything one evaluation needs, built from live upstream reads."""

    def __init__(self) -> None:
        self.intent: OrderIntent | None = None
        self.account = None
        self.market = None
        self.instruments = None
        self.quotes: dict[str, MarketQuote] = {}


class BrakeMiddleware(Middleware):
    def __init__(
        self,
        *,
        policy: PolicyBundle,
        state: ProxyState,
        db: Database,
        agent_id: str = "mcp-agent",
        upstream: UpstreamCall | None = None,
        clock: Callable[[], datetime] | None = None,
        recall: Callable[..., Awaitable[dict[str, Any]]] | None = None,
        local_tools: set[str] | frozenset[str] | None = None,
        rules_path: Path | str | None = None,
    ) -> None:
        self.policy = policy
        # Owner-approved rules learned from history, re-read on every order so an
        # approval or retirement takes effect without restarting the proxy.
        self.rules_path = rules_path
        self._closes = BrokerCloses(policy.account_id)
        self.state = state
        self.db = db
        self.agent_id = agent_id
        self._upstream_override = upstream
        self.clock = clock or (lambda: datetime.now(UTC))
        self.recall = recall
        # Tools the proxy itself serves (memory, status). They never reach the broker.
        self.local_tools = frozenset(local_tools or ())
        self._spec_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self.last_decision: dict[str, Any] | None = None

    # ------------------------------------------------------------------ routing
    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext) -> ToolResult:
        name = context.message.name
        args = dict(context.message.arguments or {})
        kind = "read" if name in self.local_tools else alpaca.classify_tool(name)
        if kind == "read":
            result = await call_next(context)
            if name == "get_account_info":
                self._observe_equity_from(result)
            return result
        if kind == "benign":
            result = await call_next(context)
            self._record_safe(tool=name, decision="PASS_THROUGH", intent=None, evaluation=None,
                              extra={"args": _stored_args(args)},
                              note="account-config or watchlist change; forwarded, not evaluated")
            return result
        if kind == "exit":
            result = await call_next(context)
            self._record_safe(tool=name, decision="ALLOW_EXIT", intent=None, evaluation=None,
                              extra={"args": _stored_args(args)}, note="exit tools are never blocked")
            return result
        if kind in ("unsupported", "unknown"):
            reason = alpaca.UNSUPPORTED_ORDER_TOOLS.get(
                name, "tool is not classified by the brake and is refused until it is"
            )
            return self._deny(tool=name, intent=None, evaluation=None,
                              rules=[{"code": UNSUPPORTED_CODE, "actual": reason}],
                              extra={"args": _stored_args(args)}, message=reason)
        async with self._lock:
            if kind == "cancel":
                return await self._cancel_guard(context, call_next, name, args)
            return await self._guard(context, call_next, name, args)

    # ------------------------------------------------------------------ the gate
    async def _guard(
        self, context: MiddlewareContext, call_next: CallNext, tool: str, args: dict[str, Any]
    ) -> ToolResult:
        now = self.clock()
        stored = _stored_args(args)

        client_order_id = str(args.get("client_order_id") or "").strip()
        if not client_order_id:
            return self._deny(
                tool=tool, intent=None, evaluation=None,
                rules=[{"code": CLIENT_ORDER_ID_REQUIRED_CODE,
                        "actual": "orders need a client_order_id so they can be retried, approved and reconciled safely"}],
                extra={"args": stored}, message="client_order_id is required",
            )
        intent_key = str(alpaca.intent_id_for(self.policy.account_id, client_order_id))
        fingerprint = alpaca.request_fingerprint(tool, args)

        try:
            upstream = self._upstream_for(context)

            # Replay and reconciliation come before any market read.
            entry = self.state.forwarded_result(intent_key, now)
            if entry is not None:
                if entry.get("fingerprint") != fingerprint:
                    return self._deny(
                        tool=tool, intent=None, evaluation=None,
                        rules=[{"code": CLIENT_ORDER_ID_REUSED_CODE,
                                "actual": "this client_order_id was already used for an order with different terms"}],
                        extra={"args": stored, "intent_id": intent_key},
                        message="client_order_id reused with different terms",
                    )
                if entry.get("status") == "unknown":
                    found = await self._lookup_by_client_id(upstream, client_order_id)
                    if found is None:
                        self.state.forget_forwarded(intent_key)
                        entry = None
                    else:
                        self.state.remember_forwarded(intent_key, fingerprint, found, now)
                        entry = {"status": "placed", "result": found}
                if entry is not None:
                    self._record(tool=tool, decision="REPLAY", intent=None, evaluation=None,
                                 extra={"args": stored, "intent_id": intent_key, "replayed": True},
                                 note="same client_order_id already forwarded")
                    structured = {"decision": "ALLOW", "replayed": True, "order_placed": True,
                                  "intent_id": intent_key, "upstream": entry.get("result")}
                    return ToolResult(content=json.dumps(structured), structured_content=structured)

            collected = await self._collect(upstream, tool, args, now)
            evaluation = evaluate(
                policy=self.policy, intent=collected.intent, account=collected.account,
                market=collected.market, instruments=collected.instruments, evaluated_at=now,
            )
            intent = collected.intent

            learned, checked = await self._learned_hits(evaluation, upstream)
            decision = self._combine(evaluation.decision, learned)
            # An approval covers the terms and the reasons the owner was shown: a learned rule
            # that fires after an approval was given makes that approval stale.
            approval_key = self._approval_key(fingerprint, learned)
            approved = False
            if decision is Decision.ESCALATE and self.state.consume_approval(intent_key, approval_key, now):
                decision, approved = Decision.ALLOW, True
            flagged = [
                {"code": r.code.value, "actual": _json_safe(r.actual), "limit": _json_safe(r.limit),
                 "subjects": list(r.subjects)}
                for r in evaluation.rules if r.outcome in (RuleOutcome.DENY, RuleOutcome.ESCALATE)
            ] + learned
            learned_extra = self._learned_extra(evaluation, learned, checked)
            if decision is Decision.DENY:
                return self._deny(tool=tool, intent=intent, evaluation=evaluation, rules=flagged,
                                  extra={"args": stored, **learned_extra},
                                  message="order refused by a rule you approved" if learned
                                  and evaluation.decision is not Decision.DENY else "order refused by policy")
            if decision is Decision.ESCALATE:
                summary = alpaca.terms_summary(tool, args)
                if learned:
                    summary += " | held by " + "; ".join(h["message"] for h in learned)
                self.state.escalate(intent_key, approval_key, now, summary=summary)
                event_id = self._record(tool=tool, decision="ESCALATE", intent=intent, evaluation=evaluation,
                                        extra={"args": stored, "rules": flagged, "fingerprint": fingerprint,
                                               "terms": summary, **learned_extra},
                                        note="human approval required")
                structured = {
                    "decision": "ESCALATE", "order_placed": False, "intent_id": intent_key,
                    "decision_event": event_id, "policy_hash": evaluation.policy_hash,
                    **self._hashes(evaluation, learned, event_id, checked is not None), "rules": flagged,
                    "terms": summary, "terms_fingerprint": approval_key,
                    "how_to_approve": (
                        f"owner runs: tradememory proxy approve {intent_key} --terms {approval_key} "
                        "(the CLI shows the terms it is approving); then retry this call with the same "
                        "client_order_id and the same terms (any change is refused)"
                    ),
                }
                return ToolResult(content=json.dumps(structured), structured_content=structured)

            # ALLOW: record first, then forward exactly once.
            event_id = self._record(tool=tool, decision="ALLOW", intent=intent, evaluation=evaluation,
                                    extra={"args": stored, "approved_by_owner": approved, "fingerprint": fingerprint,
                                           **learned_extra},
                                    note="forwarded to broker")
        except Exception as exc:  # fail closed, whatever broke
            log.warning("brake fail-closed on %s: %s", tool, exc)
            return self._deny(
                tool=tool, intent=None, evaluation=None,
                rules=[{"code": FAIL_CLOSED_CODE, "actual": f"{type(exc).__name__}: {exc}"[:300]}],
                extra={"args": stored}, message="the brake could not evaluate this order and refused it",
            )

        try:
            upstream_result = await call_next(context)
            if getattr(upstream_result, "is_error", False):
                # fastmcp hands upstream failures back as error results, not exceptions.
                texts = [getattr(b, "text", "") for b in (getattr(upstream_result, "content", None) or [])]
                raise ForwardError(" ".join(t for t in texts if t) or "upstream returned an error")
        except Exception as exc:
            # The broker may or may not have the order. Say so, remember it, reconcile on retry.
            error = f"{type(exc).__name__}: {exc}"[:300]
            try:
                self.state.mark_unknown(intent_key, fingerprint, error, now)
            except Exception as state_exc:  # the order may be live; never lose the response over bookkeeping
                log.error("could not mark %s unknown: %s", intent_key, state_exc)
            self._record_safe(tool=tool, decision="FORWARD_FAILED", intent=intent, evaluation=evaluation,
                              extra={"args": stored, "error": error, "decision_event_allow": event_id},
                              note="broker call failed after ALLOW; outcome unknown until reconciled")
            structured = {
                "decision": "ALLOW", "order_placed": "unknown", "intent_id": intent_key,
                "decision_event": event_id, "error": error,
                "message": ("the broker call failed after the order was approved; retry with the same "
                            "client_order_id and the brake will check the broker before placing anything"),
            }
            return ToolResult(content=json.dumps(structured), structured_content=structured)

        payload = _json_safe(alpaca.unwrap(upstream_result))
        cache_value = payload if isinstance(payload, dict) else {"result": payload}
        try:
            self.state.remember_forwarded(intent_key, fingerprint, cache_value, now)
        except Exception as state_exc:  # the order is placed; the agent must still get the result
            log.error("could not remember forward %s: %s", intent_key, state_exc)
        self._record_trade(tool, intent, evaluation, payload, event_id, now)
        prior = await self._prior_outcomes(tool, intent)

        structured = {
            "decision": "ALLOW", "order_placed": True, "intent_id": intent_key,
            "decision_event": event_id, "policy_hash": evaluation.policy_hash,
            **self._hashes(evaluation, learned, event_id, checked is not None), "approved_by_owner": approved,
            "prior_outcomes": prior,
            "upstream": getattr(upstream_result, "structured_content", None) or payload,
        }
        return ToolResult(content=upstream_result.content, structured_content=structured)

    async def _cancel_guard(
        self, context: MiddlewareContext, call_next: CallNext, tool: str, args: dict[str, Any]
    ) -> ToolResult:
        stored = _stored_args(args)
        try:
            if self.policy.require_protective_stop:
                upstream = self._upstream_for(context)
                raw_positions = alpaca.as_list(alpaca.unwrap(await upstream("get_all_positions", {})))
                held: dict[str, Decimal] = {}
                for p in raw_positions:
                    if not isinstance(p, dict):
                        raise alpaca.AdapterError("position payload is not an object")
                    sign = Decimal("-1") if str(p.get("side", "long")).lower() == "short" else Decimal("1")
                    held[str(p["symbol"]).upper()] = alpaca.D(p.get("qty")) * sign
                if tool == "cancel_all_orders" and any(q != 0 for q in held.values()):
                    return self._deny(
                        tool=tool, intent=None, evaluation=None,
                        rules=[{"code": STOP_CANCEL_CODE, "actual": "open positions would lose their protective stops"}],
                        extra={"args": stored},
                        message="cancel_all_orders is refused while positions are open and stops are required",
                    )
                if tool == "cancel_order_by_id":
                    name, arguments = alpaca.order_by_id_call(str(args.get("order_id", "")))
                    order = alpaca.unwrap(await upstream(name, arguments))
                    if alpaca.is_protective_leg(order, held):
                        return self._deny(
                            tool=tool, intent=None, evaluation=None,
                            rules=[{"code": STOP_CANCEL_CODE,
                                    "actual": f"order {args.get('order_id')} is the protective stop of an open position"}],
                            extra={"args": stored},
                            message="cancelling a protective stop is refused while the position is open",
                        )
        except Exception as exc:
            log.warning("cancel guard fail-closed on %s: %s", tool, exc)
            return self._deny(
                tool=tool, intent=None, evaluation=None,
                rules=[{"code": FAIL_CLOSED_CODE, "actual": f"{type(exc).__name__}: {exc}"[:300]}],
                extra={"args": stored}, message="the brake could not check this cancel and refused it",
            )
        result = await call_next(context)
        self._record_safe(tool=tool, decision="ALLOW_CANCEL", intent=None, evaluation=None,
                          extra={"args": stored}, note="cancel forwarded")
        return result

    # ------------------------------------------------------------------ dry run
    async def dry_run(self, args: dict[str, Any], upstream: UpstreamCall) -> dict[str, Any]:
        """Evaluate an order against the policy and live state without placing it.

        Same reads, same evaluation, same decision shape as a real order; nothing
        is forwarded, no replay or approval state is touched, and the event is
        recorded as DRY_RUN. This is what an advisory layer in another framework
        calls, because an advisor must never place an order itself.
        """
        now = self.clock()
        args = dict(args)
        args.setdefault("client_order_id", "dry-run")
        tool = "place_crypto_order" if "/" in str(args.get("symbol", "")) else "place_stock_order"
        stored = _stored_args(args)
        async with self._lock:
            try:
                collected = await self._collect(upstream, tool, args, now)
                evaluation = evaluate(
                    policy=self.policy, intent=collected.intent, account=collected.account,
                    market=collected.market, instruments=collected.instruments, evaluated_at=now,
                )
                learned, checked = await self._learned_hits(evaluation, upstream)
            except Exception as exc:
                rules = [{"code": FAIL_CLOSED_CODE, "actual": f"{type(exc).__name__}: {exc}"[:300]}]
                event_id = self._record_safe(tool=tool, decision="DRY_RUN", intent=None, evaluation=None,
                                             extra={"args": stored, "rules": rules, "result": "DENY"},
                                             note="dry run could not evaluate; a real order would be refused")
                return {"decision": "DENY", "dry_run": True, "order_placed": False, "denied_rules": rules,
                        "rules": rules, "decision_event": event_id, "policy_hash": self.policy.content_hash,
                        "message": "the brake could not evaluate this order; a real order would be refused"}
            flagged = [
                {"code": r.code.value, "actual": _json_safe(r.actual), "limit": _json_safe(r.limit),
                 "subjects": list(r.subjects)}
                for r in evaluation.rules if r.outcome in (RuleOutcome.DENY, RuleOutcome.ESCALATE)
            ] + learned
            decision = self._combine(evaluation.decision, learned)
            event_id = self._record_safe(tool=tool, decision="DRY_RUN", intent=collected.intent,
                                         evaluation=evaluation,
                                         extra={"args": stored, "rules": flagged, "result": decision.value,
                                                **self._learned_extra(evaluation, learned, checked)},
                                         note="dry run; nothing forwarded")
            return {
                "decision": decision.value, "dry_run": True, "order_placed": False,
                "rules": flagged, "denied_rules": flagged if decision is Decision.DENY else [],
                "terms": alpaca.terms_summary(tool, args), "decision_event": event_id,
                "policy_hash": evaluation.policy_hash, **self._hashes(evaluation, learned, event_id, checked is not None),
            }

    # ------------------------------------------------------------------ learned rules
    async def _learned_hits(
        self, evaluation: EvaluationResult, upstream: UpstreamCall
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """(the active owner-approved rules this order trips, what was checked).

        Orders that reduce or close a position are never held and never read the rules
        file. A broken rules file, or a broker history that cannot be read when an order
        is big enough to trip a rule, raises: the brake refuses the order.
        """
        if self.rules_path is None or evaluation.decision is Decision.DENY:
            return [], None
        if evaluation.position_effect in (PositionEffect.REDUCE, PositionEffect.CLOSE):
            return [], None
        try:
            rules = active_rules(self.rules_path)
        except RulesError as exc:
            # The reason goes to the owner's terminal, not to the agent: no local paths in the reply.
            log.error("rules file refused: %s", exc)
            raise RuntimeError("the rules file cannot be trusted; run `tradememory rules list` to see why") from None
        if not rules:
            return [], None
        sizes = [v for v in (evaluation.order_notional, evaluation.worst_case_position_notional) if v is not None]
        size = max(sizes) if sizes else None
        checked: dict[str, Any] = {
            "rules": [r["id"] for r in rules], "position_notional": str(size) if size is not None else None,
        }
        reachable = rules_in_reach(rules, size)
        if not reachable:
            checked["history"] = "not read: below every rule's limit"
            return [], checked
        closes = await self._closes.closes(upstream)
        checked.update({
            "history": "read from the broker",
            "closes_seen": len(closes),
            "latest_close": closes[0].closed_at.isoformat() if closes else None,
        })
        return check_order(reachable, size=size, closes=closes), checked

    @staticmethod
    def _approval_key(fingerprint: str, learned: list[dict[str, Any]]) -> str:
        if not learned:
            return fingerprint
        return f"{fingerprint}+rules:{','.join(sorted(h['rule_id'] for h in learned))}"

    @staticmethod
    def _combine(control: Decision, learned: list[dict[str, Any]]) -> Decision:
        """The stricter of Control's decision and the learned rules'. A rule never loosens."""
        if control is Decision.DENY or not learned:
            return control
        if any(h["action"] == "deny" for h in learned):
            return Decision.DENY
        return Decision.ESCALATE

    @staticmethod
    def _learned_extra(
        evaluation: EvaluationResult, learned: list[dict[str, Any]], checked: dict[str, Any] | None
    ) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if checked is not None:
            extra["learned_rules_checked"] = checked
        if learned:
            extra["learned_rules"] = learned
            extra["control_decision"] = evaluation.decision.value
        return extra

    def _hashes(self, evaluation: EvaluationResult, learned: list[dict[str, Any]], event_id: str | None,
                rules_checked: bool) -> dict[str, Any]:
        """Hashes a verifier can use. Control's evaluation hash describes Control's decision only;
        the decision record hash is what the audit chain anchored for this decision."""
        control = content_sha256(evaluation)
        out: dict[str, Any] = {"control_evaluation_hash": control}
        record = None
        if event_id is not None and self.last_decision is not None and self.last_decision.get("event_id") == event_id:
            record = self.last_decision.get("content_hash")
            out["decision_record_hash"] = record
        if learned:
            out["control_decision"] = evaluation.decision.value
        # Kept with its old meaning when no learned rule was involved. Once rules were checked,
        # the chain covers the whole record and only decision_record_hash matches the chain link.
        if not rules_checked:
            out["evaluation_hash"] = control
        return out

    # ------------------------------------------------------------------ collection
    @staticmethod
    def upstream_from_server(server: Any) -> UpstreamCall:
        """Call upstream tools on the proxy server itself, bypassing this middleware."""

        async def call(name: str, arguments: dict[str, Any]) -> Any:
            result = await server.call_tool(name, arguments, run_middleware=False)
            if getattr(result, "is_error", False):
                texts = [getattr(b, "text", "") for b in (getattr(result, "content", None) or [])]
                raise alpaca.AdapterError(f"upstream {name} failed: {' '.join(t for t in texts if t)[:300]}")
            return result

        return call

    def _upstream_for(self, context: MiddlewareContext) -> UpstreamCall:
        if self._upstream_override is not None:
            return self._upstream_override
        fastmcp_ctx = context.fastmcp_context
        server = getattr(fastmcp_ctx, "fastmcp", None)
        if server is None:
            raise RuntimeError("no upstream available: middleware has no fastmcp context")
        return self.upstream_from_server(server)

    async def _lookup_by_client_id(self, upstream: UpstreamCall, client_order_id: str) -> dict[str, Any] | None:
        """The broker's view of a client_order_id: an order dict, or None when it has none."""
        name, arguments = alpaca.order_by_client_id_call(client_order_id)
        try:
            order = alpaca.unwrap(await upstream(name, arguments))
        except Exception as exc:
            text = str(exc).lower()
            if "404" in text or "not found" in text:
                return None
            raise  # cannot tell whether the broker has it: fail closed upstairs
        if isinstance(order, dict) and order.get("id"):
            return _json_safe(order)
        return None

    async def _asset(self, upstream: UpstreamCall, raw_symbol: str, now: datetime) -> dict[str, Any]:
        key = raw_symbol.upper().strip()
        cached = self._spec_cache.get(key)
        if cached and now - cached[0] < INSTRUMENT_CACHE_TTL:
            return cached[1]
        name, arguments = alpaca.asset_call(key)
        asset = alpaca.unwrap(await upstream(name, arguments))
        if not isinstance(asset, dict) or not ({"symbol", "tradable", "id"} & set(asset)):
            raise alpaca.AdapterError(f"no asset facts for {key}: {str(asset)[:120]!r}")
        self._spec_cache[key] = (now, asset)
        return asset

    async def _collect(
        self, upstream: UpstreamCall, tool: str, args: dict[str, Any], now: datetime
    ) -> Collected:
        c = Collected()
        account = alpaca.unwrap(await upstream("get_account_info", {}))
        if not isinstance(account, dict) or "id" not in account:
            raise alpaca.AdapterError("get_account_info returned no account")
        account_id = str(account["id"])
        if account_id != self.policy.account_id:
            raise alpaca.AdapterError(
                f"upstream account {account_id} is not the policy account {self.policy.account_id}"
            )
        positions = alpaca.as_list(alpaca.unwrap(await upstream("get_all_positions", {})))
        orders_tool, orders_args = alpaca.orders_call()
        orders = alpaca.as_list(alpaca.unwrap(await upstream(orders_tool, orders_args)))
        if len(orders) >= alpaca.ORDERS_PAGE_LIMIT:
            raise alpaca.AdapterError("open-order list hit the page limit; exposure cannot be trusted")
        clock = alpaca.unwrap(await upstream("get_clock", {}))
        market_open = bool(clock.get("is_open")) if isinstance(clock, dict) else False

        raw_symbol = str(args.get("symbol", "")).upper().strip()
        if not raw_symbol:
            raise alpaca.AdapterError("order has no symbol")
        raw_symbols = {raw_symbol}
        raw_symbols |= {str(p["symbol"]).upper() for p in positions if isinstance(p, dict) and p.get("symbol")}
        raw_symbols |= {
            str(o["symbol"]).upper() for o in orders
            if isinstance(o, dict) and o.get("symbol")
            and str(o.get("status", "")).lower() not in alpaca.TERMINAL_ORDER_STATUSES
        }

        # Canonical symbols come from the broker's asset record (BTCUSD -> BTC/USD), never from string games.
        assets: dict[str, dict[str, Any]] = {}
        canonical: dict[str, str] = {}
        for raw in sorted(raw_symbols):
            asset = await self._asset(upstream, raw, now)
            canonical[raw] = alpaca.canonical_symbol(asset, raw)
            assets[canonical[raw]] = asset
        for p in positions:
            if isinstance(p, dict) and p.get("symbol"):
                p["symbol"] = canonical[str(p["symbol"]).upper()]
        for o in orders:
            if isinstance(o, dict) and o.get("symbol") and str(o["symbol"]).upper() in canonical:
                o["symbol"] = canonical[str(o["symbol"]).upper()]
        symbol = canonical[raw_symbol]

        specs: dict[str, InstrumentSpec] = {}
        quotes: dict[str, MarketQuote] = {}
        quote_times: list[datetime] = []
        for canon in sorted(assets):
            asset = assets[canon]
            specs[canon] = alpaca.instrument_spec(canon, asset)
            quote, ts = await self._quote(upstream, canon, specs[canon].price_tick,
                                          market_open, alpaca.is_crypto_asset(asset))
            quotes[canon] = quote
            if ts is not None:
                quote_times.append(ts)
        c.quotes = quotes
        # While the market is open the snapshot is as old as its oldest quote, so a dead
        # feed trips MARKET_STATE_STALE. Closed-market pricing comes from the last trade and
        # is stamped now by design; the policy's trading windows decide whether that is allowed.
        market_observed_at = min(quote_times) if (market_open and quote_times) else now
        if market_observed_at > now:
            market_observed_at = now

        equity = alpaca.D(account.get("equity"))
        drawdown = self.state.observe_equity(equity)
        c.account = alpaca.account_snapshot(
            account, positions, orders, quotes,
            halt=self.state.halt, drawdown_from_peak=drawdown,
            pnl_period=pnl_window(self.policy.risk_day_start_hour_utc, now),
            observed_at=now, state_version=self.state.next_state_version(),
        )
        c.market = alpaca.market_snapshot(quotes, market_observed_at)
        c.instruments = alpaca.instrument_catalog(list(specs.values()), now)
        c.intent = alpaca.intent_from_call(
            tool, args, account_id=account_id, agent_id=self.agent_id, symbol=symbol,
            quotes=quotes, specs=specs, market_data_as_of=market_observed_at, now=now,
        )
        return c

    async def _quote(
        self, upstream: UpstreamCall, symbol: str, tick: Decimal, market_open: bool, crypto: bool
    ) -> tuple[MarketQuote, datetime | None]:
        """Live two-sided book while the market is open; last trade otherwise.

        A closed book is stale and wide (the real after-hours AAPL book was
        320.91 / 354.20 against a last trade of 333.05), so sizing from its
        midpoint would misstate every notional. Crypto trades around the clock
        and always uses its book.
        """
        if market_open or crypto:
            name, arguments = alpaca.quote_call(symbol, crypto)
            try:
                return alpaca.quote_from(symbol, alpaca.unwrap(await upstream(name, arguments)), tick)
            except alpaca.AdapterError:
                pass  # one-sided or empty book: fall through to the last trade
        name, arguments = alpaca.trade_call(symbol, crypto)
        return alpaca.quote_from_trade(symbol, alpaca.unwrap(await upstream(name, arguments)), tick)

    def _observe_equity_from(self, result: Any) -> None:
        """Keep the running equity peak honest between orders, from pass-through account reads."""
        try:
            account = alpaca.unwrap(result)
            if isinstance(account, dict) and str(account.get("id")) == self.policy.account_id:
                self.state.observe_equity(alpaca.D(account.get("equity")))
        except Exception as exc:
            log.debug("equity observation skipped: %s", exc)

    # ------------------------------------------------------------------ results
    def _deny(
        self,
        *,
        tool: str,
        intent: OrderIntent | None,
        evaluation: EvaluationResult | None,
        rules: list[dict[str, Any]],
        extra: dict[str, Any],
        message: str,
    ) -> ToolResult:
        event_id = self._record_safe(tool=tool, decision="DENY", intent=intent, evaluation=evaluation,
                                     extra={**extra, "rules": rules}, note=message)
        structured: dict[str, Any] = {
            "decision": "DENY", "order_placed": False, "decision_event": event_id,
            "policy_hash": self.policy.content_hash, "denied_rules": rules, "message": message,
        }
        if intent is not None:
            structured["intent_id"] = str(intent.intent_id)
        if evaluation is not None:
            structured.update(self._hashes(evaluation, extra.get("learned_rules") or [], event_id,
                                           "learned_rules_checked" in extra))
        return ToolResult(content=json.dumps(structured), structured_content=structured)

    # ------------------------------------------------------------------ recording
    def _record(
        self,
        *,
        tool: str,
        decision: str,
        intent: OrderIntent | None,
        evaluation: EvaluationResult | None,
        extra: dict[str, Any],
        note: str,
    ) -> str:
        factors: dict[str, Any] = {
            "decision": decision,
            "policy_hash": self.policy.content_hash,
            "intent": _json_safe(intent.model_dump(mode="json")) if intent is not None else None,
            "evaluation": _json_safe(evaluation.model_dump(mode="json")) if evaluation is not None else None,
            **_json_safe(extra),
        }
        # Control's evaluation hash anchors the decision only when Control alone made it;
        # a learned rule changes the outcome, so the chain must cover the whole record.
        if (evaluation is not None and decision in ("ALLOW", "DENY", "ESCALATE")
                and "learned_rules" not in extra and "learned_rules_checked" not in extra):
            content_hash = content_sha256(evaluation)
        else:
            content_hash = hashlib.sha256(
                json.dumps(factors, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        factors["content_hash"] = content_hash
        with self.db.get_connection() as conn:  # event row and chain link in one transaction
            event_id = self.db.insert_decision_event(
                tool=tool,
                strategy=intent.strategy_id if intent is not None else None,
                symbol=intent.symbol if intent is not None else None,
                tier=decision,
                score=None,
                factors=factors,
                recommendation=note,
                linked_trade_id=str(intent.intent_id) if intent is not None else None,
                conn=conn,
            )
            ChainBuilder(conn).append(record_id=f"decision:{event_id}", content_hash=content_hash)
        self.last_decision = {"event_id": event_id, "tool": tool, "decision": decision, "content_hash": content_hash}
        return event_id

    def _record_safe(self, **kwargs: Any) -> str | None:
        """Record without ever failing the agent's call; used after a forward already happened."""
        try:
            return self._record(**kwargs)
        except Exception as exc:
            log.error("could not record %s decision for %s: %s", kwargs.get("decision"), kwargs.get("tool"), exc)
            return None

    def _record_trade(
        self,
        tool: str,
        intent: OrderIntent,
        evaluation: EvaluationResult,
        payload: Any,
        event_id: str,
        now: datetime,
    ) -> None:
        """Open a trade record for risk-adding fills so behavioral analysis sees proxy orders."""
        if evaluation.position_effect not in (PositionEffect.OPEN, PositionEffect.INCREASE):
            return
        broker_order_id = payload.get("id") if isinstance(payload, dict) else None
        entry_price = float(evaluation.reference_price) if evaluation.reference_price is not None else None
        trade = {
            "id": f"ord-{broker_order_id or intent.intent_id}",
            "timestamp": now,
            "symbol": intent.symbol,
            "direction": "long" if intent.side.value == "BUY" else "short",
            "lot_size": float(intent.quantity),
            "strategy": intent.strategy_id,
            "confidence": 0.5,
            "reasoning": f"{tool} forwarded by the proxy after ALLOW",
            "market_context": {
                "entry_price": entry_price,
                # Kept so `tradememory sync alpaca` can express the outcome in R.
                "protective_stop_price": (
                    float(intent.protective_stop_price) if intent.protective_stop_price is not None else None
                ),
                "policy_hash": evaluation.policy_hash,
                "intent_id": str(intent.intent_id),
                "decision_event": event_id,
                "broker": alpaca.BROKER,
            },
            "references": [],
            "exit_timestamp": None,
            "exit_price": None,
            "pnl": None,
            "pnl_r": None,
            "hold_duration": None,
            "exit_reasoning": None,
            "slippage": None,
            "execution_quality": None,
            "lessons": None,
            "tags": ["proxy", alpaca.BROKER],
            "grade": None,
        }
        try:
            self.db.insert_trade(trade)
        except Exception as exc:  # the order is already placed; never fail the agent on bookkeeping
            log.warning("could not record trade for %s: %s", intent.intent_id, exc)

    async def _prior_outcomes(self, tool: str, intent: OrderIntent) -> list[dict[str, Any]]:
        if self.recall is None:
            return []
        try:
            # The order just went out: show the losing trades from similar
            # conditions first, not the flattering ones.
            result = await self.recall(
                symbol=intent.symbol,
                market_context=f"{tool} {intent.side.value} {intent.symbol}",
                strategy_name=None,
                limit=3,
                order="losses_first",
            )
        except Exception as exc:
            log.warning("recall failed for %s: %s", intent.symbol, exc)
            return []
        memories = result.get("memories") if isinstance(result, dict) else None
        out: list[dict[str, Any]] = []
        for m in memories or []:
            if not isinstance(m, dict):
                continue
            out.append({
                k: _json_safe(m.get(k))
                for k in ("memory_id", "direction", "pnl", "pnl_r", "lot_size", "reflection")
                if k in m
            })
        return out[:3]
