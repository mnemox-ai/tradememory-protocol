"""The brake: a fastmcp middleware that evaluates order tools before they reach the broker.

Invariants (tests pin each one):
- An order tool is never forwarded without a sealed, in-window evaluation that said ALLOW.
- Any failure to build that evaluation is a DENY, never a pass-through.
- Exit tools are never blocked; they are recorded.
- The same deterministic intent is forwarded at most once; a retry returns the first result.
- Every decision, including replays and fail-closed denies, is a chained decision event.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
from . import alpaca
from .policy import pnl_window
from .state import ProxyState

log = logging.getLogger("tradememory.proxy")

UpstreamCall = Callable[[str, dict[str, Any]], Awaitable[Any]]
INSTRUMENT_CACHE_TTL = timedelta(hours=1)
FAIL_CLOSED_CODE = "PROXY_FAIL_CLOSED"
UNSUPPORTED_CODE = "PROXY_UNSUPPORTED_TOOL"


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
    ) -> None:
        self.policy = policy
        self.state = state
        self.db = db
        self.agent_id = agent_id
        self._upstream_override = upstream
        self.clock = clock or (lambda: datetime.now(UTC))
        self.recall = recall
        self._spec_cache: dict[str, tuple[datetime, InstrumentSpec]] = {}
        self.last_decision: dict[str, Any] | None = None

    # ------------------------------------------------------------------ routing
    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext) -> ToolResult:
        name = context.message.name
        args = dict(context.message.arguments or {})
        if name in alpaca.EXIT_TOOLS:
            result = await call_next(context)
            self._record(
                tool=name, decision="ALLOW_EXIT", intent=None, evaluation=None,
                extra={"args": _json_safe(args)}, note="exit tools are never blocked",
            )
            return result
        if name in alpaca.UNSUPPORTED_ORDER_TOOLS:
            reason = alpaca.UNSUPPORTED_ORDER_TOOLS[name]
            return self._deny(
                tool=name, intent=None, evaluation=None,
                rules=[{"code": UNSUPPORTED_CODE, "actual": reason}],
                extra={"args": _json_safe(args)}, message=reason,
            )
        if name not in alpaca.ORDER_TOOLS:
            return await call_next(context)
        return await self._guard(context, call_next, name, args)

    # ------------------------------------------------------------------ the gate
    async def _guard(
        self, context: MiddlewareContext, call_next: CallNext, tool: str, args: dict[str, Any]
    ) -> ToolResult:
        now = self.clock()
        try:
            upstream = self._upstream_for(context)
            collected = await self._collect(upstream, tool, args, now)
            evaluation = evaluate(
                policy=self.policy,
                intent=collected.intent,
                account=collected.account,
                market=collected.market,
                instruments=collected.instruments,
                evaluated_at=now,
            )
        except Exception as exc:  # fail closed, whatever broke
            log.warning("brake fail-closed on %s: %s", tool, exc)
            return self._deny(
                tool=tool, intent=None, evaluation=None,
                rules=[{"code": FAIL_CLOSED_CODE, "actual": f"{type(exc).__name__}: {exc}"}],
                extra={"args": _json_safe(args)},
                message="the brake could not evaluate this order and refused it",
            )

        intent = collected.intent
        intent_id = str(intent.intent_id)
        _, deterministic = alpaca.intent_id_for(intent.account_id, args.get("client_order_id"))

        if deterministic:
            cached = self.state.forwarded_result(intent_id, now)
            if cached is not None:
                self._record(
                    tool=tool, decision="REPLAY", intent=intent, evaluation=evaluation,
                    extra={"replayed": True}, note="same client_order_id already forwarded",
                )
                structured = {
                    "decision": "ALLOW", "replayed": True, "order_placed": True,
                    "intent_id": intent_id, "upstream": cached,
                }
                return ToolResult(content=json.dumps(structured), structured_content=structured)

        decision = evaluation.decision
        approved = False
        if decision is Decision.ESCALATE and deterministic and self.state.consume_approval(intent_id, now):
            decision, approved = Decision.ALLOW, True

        flagged_rules = [
            {
                "code": r.code.value,
                "actual": _json_safe(r.actual),
                "limit": _json_safe(r.limit),
                "subjects": list(r.subjects),
            }
            for r in evaluation.rules
            if r.outcome in (RuleOutcome.DENY, RuleOutcome.ESCALATE)
        ]

        if decision is Decision.DENY:
            return self._deny(
                tool=tool, intent=intent, evaluation=evaluation, rules=flagged_rules,
                extra={"args": _json_safe(args)}, message="order refused by policy",
            )
        if decision is Decision.ESCALATE:
            event_id = self._record(
                tool=tool, decision="ESCALATE", intent=intent, evaluation=evaluation,
                extra={"args": _json_safe(args), "rules": flagged_rules}, note="human approval required",
            )
            structured: dict[str, Any] = {
                "decision": "ESCALATE", "order_placed": False, "intent_id": intent_id,
                "decision_event": event_id, "policy_hash": evaluation.policy_hash,
                "evaluation_hash": content_sha256(evaluation), "rules": flagged_rules,
                "how_to_approve": (
                    f"owner runs: tradememory proxy approve {intent_id}; "
                    "then retry this call with the same client_order_id"
                ),
            }
            if not deterministic:
                structured["how_to_approve"] = (
                    "this call had no client_order_id so it cannot be approved and retried; "
                    "resend with a client_order_id to get an approvable intent"
                )
            return ToolResult(content=json.dumps(structured), structured_content=structured)

        # ALLOW: record first, then forward exactly once.
        event_id = self._record(
            tool=tool, decision="ALLOW", intent=intent, evaluation=evaluation,
            extra={"args": _json_safe(args), "approved_by_owner": approved}, note="forwarded to broker",
        )
        upstream_result = await call_next(context)
        payload = _json_safe(alpaca.unwrap(upstream_result))
        if deterministic:
            cache_value = payload if isinstance(payload, dict) else {"result": payload}
            self.state.remember_forwarded(intent_id, cache_value, now)
        self._record_trade(tool, intent, evaluation, payload, event_id, now)
        prior = await self._prior_outcomes(tool, intent)

        structured = {
            "decision": "ALLOW", "order_placed": True, "intent_id": intent_id,
            "decision_event": event_id, "policy_hash": evaluation.policy_hash,
            "evaluation_hash": content_sha256(evaluation),
            "approved_by_owner": approved,
            "prior_outcomes": prior,
            "upstream": getattr(upstream_result, "structured_content", None) or payload,
        }
        return ToolResult(content=upstream_result.content, structured_content=structured)

    # ------------------------------------------------------------------ collection
    def _upstream_for(self, context: MiddlewareContext) -> UpstreamCall:
        if self._upstream_override is not None:
            return self._upstream_override
        fastmcp_ctx = context.fastmcp_context
        server = getattr(fastmcp_ctx, "fastmcp", None)
        if server is None:
            raise RuntimeError("no upstream available: middleware has no fastmcp context")

        async def call(name: str, arguments: dict[str, Any]) -> Any:
            result = await server.call_tool(name, arguments, run_middleware=False)
            if getattr(result, "is_error", False):
                texts = [getattr(b, "text", "") for b in (getattr(result, "content", None) or [])]
                raise alpaca.AdapterError(f"upstream {name} failed: {' '.join(t for t in texts if t)[:300]}")
            return result

        return call

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
        positions = alpaca.unwrap(await upstream("get_all_positions", {})) or []
        orders = alpaca.unwrap(await upstream("get_orders", {"status": "open"})) or []
        if isinstance(positions, dict):
            positions = positions.get("positions") or positions.get("items") or []
        if isinstance(orders, dict):
            orders = orders.get("orders") or orders.get("items") or []

        symbols = {str(args.get("symbol", "")).upper().strip()}
        symbols |= {str(p["symbol"]).upper() for p in positions if isinstance(p, dict) and p.get("symbol")}
        symbols |= {
            str(o["symbol"]).upper()
            for o in orders
            if isinstance(o, dict)
            and o.get("symbol")
            and str(o.get("status", "")).lower() not in alpaca.TERMINAL_ORDER_STATUSES
        }
        symbols.discard("")

        specs: dict[str, InstrumentSpec] = {}
        for symbol in sorted(symbols):
            specs[symbol] = await self._spec(upstream, symbol, now)
        quotes: dict[str, MarketQuote] = {}
        for symbol in sorted(symbols):
            quotes[symbol] = await self._quote(upstream, symbol, specs[symbol].price_tick)
        c.quotes = quotes

        equity = alpaca.D(account.get("equity"))
        drawdown = self.state.observe_equity(equity)
        c.account = alpaca.account_snapshot(
            account, positions, orders, quotes,
            halt=self.state.halt, drawdown_from_peak=drawdown,
            pnl_period=pnl_window(self.policy.risk_day_start_hour_utc, now),
            observed_at=now, state_version=self.state.next_state_version(),
        )
        c.market = alpaca.market_snapshot(quotes, now)
        c.instruments = alpaca.instrument_catalog(list(specs.values()), now)
        c.intent = alpaca.intent_from_call(
            tool, args, account_id=account_id, agent_id=self.agent_id,
            quotes=quotes, specs=specs, market_data_as_of=now, now=now,
        )
        return c

    async def _spec(self, upstream: UpstreamCall, symbol: str, now: datetime) -> InstrumentSpec:
        cached = self._spec_cache.get(symbol)
        if cached and now - cached[0] < INSTRUMENT_CACHE_TTL:
            return cached[1]
        asset = alpaca.unwrap(await upstream("get_asset", {"symbol": symbol}))
        spec = alpaca.instrument_spec(symbol, asset)
        self._spec_cache[symbol] = (now, spec)
        return spec

    async def _quote(self, upstream: UpstreamCall, symbol: str, tick: Decimal) -> MarketQuote:
        name, arguments = alpaca.quote_call(symbol)
        try:
            return alpaca.quote_from(symbol, alpaca.unwrap(await upstream(name, arguments)), tick)
        except alpaca.AdapterError:
            name, arguments = alpaca.trade_call(symbol)
            return alpaca.quote_from_trade(symbol, alpaca.unwrap(await upstream(name, arguments)), tick)

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
        event_id = self._record(
            tool=tool, decision="DENY", intent=intent, evaluation=evaluation,
            extra={**extra, "rules": rules}, note=message,
        )
        structured: dict[str, Any] = {
            "decision": "DENY", "order_placed": False, "decision_event": event_id,
            "policy_hash": self.policy.content_hash, "denied_rules": rules, "message": message,
        }
        if intent is not None:
            structured["intent_id"] = str(intent.intent_id)
        if evaluation is not None:
            structured["evaluation_hash"] = content_sha256(evaluation)
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
        if evaluation is not None:
            content_hash = content_sha256(evaluation)
        else:
            content_hash = hashlib.sha256(
                json.dumps(factors, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        factors["content_hash"] = content_hash
        event_id = self.db.insert_decision_event(
            tool=tool,
            strategy=intent.strategy_id if intent is not None else None,
            symbol=intent.symbol if intent is not None else None,
            tier=decision,
            score=None,
            factors=factors,
            recommendation=note,
            linked_trade_id=str(intent.intent_id) if intent is not None else None,
        )
        with self.db.get_connection() as conn:
            ChainBuilder(conn).append(record_id=f"decision:{event_id}", content_hash=content_hash)
        self.last_decision = {
            "event_id": event_id, "tool": tool, "decision": decision, "content_hash": content_hash,
        }
        return event_id

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
            result = await self.recall(
                symbol=intent.symbol,
                market_context=f"{tool} {intent.side.value} {intent.symbol}",
                strategy_name=None,
                limit=3,
            )
        except Exception as exc:
            log.warning("recall failed for %s: %s", intent.symbol, exc)
            return []
        memories = result.get("memories") if isinstance(result, dict) else None
        out: list[dict[str, Any]] = []
        for m in memories or []:
            if not isinstance(m, dict):
                continue
            out.append({k: _json_safe(m.get(k)) for k in ("timestamp", "direction", "pnl_r", "reflection") if k in m})
        return out[:3]
