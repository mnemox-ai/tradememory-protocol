"""Alpaca MCP adapter: unwrap upstream results and map them to Mnemox Control inputs.

Everything here is pure mapping. It never calls the network; the brake hands
it the raw payloads it fetched from the upstream MCP server.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal
from typing import Any

from mnemox_control.contracts import OrderIntent, OrderType, Side
from mnemox_control.state import (
    HaltState,
    InstrumentCatalog,
    InstrumentSpec,
    InstrumentType,
    MarketQuote,
    MarketSnapshot,
    OpenOrderExposure,
    OpenOrderStatus,
    Position,
    PositionMode,
    TrustedAccountSnapshot,
)

BROKER = "alpaca"
SOURCE = "alpaca-mcp"

# Tools whose call places a new order: evaluated before forwarding.
ORDER_TOOLS = frozenset({"place_stock_order", "place_crypto_order"})
# Tools that can only reduce risk: always forwarded, always recorded.
EXIT_TOOLS = frozenset({"close_position", "close_all_positions"})
# Tools that would bypass or exceed what policy v0 can evaluate: always denied, with the reason.
UNSUPPORTED_ORDER_TOOLS: dict[str, str] = {
    "place_option_order": "options are not covered by policy v0",
    "exercise_options_position": "options are not covered by policy v0",
    "replace_order_by_id": "replacing an order bypasses evaluation; cancel it and place a new order",
}
SUPPORTED_ORDER_TYPES = {
    "market": OrderType.MARKET,
    "limit": OrderType.LIMIT,
    "stop": OrderType.STOP,
}

# Fixed namespace so the same client_order_id always maps to the same intent_id (at-most-once).
INTENT_NAMESPACE = uuid.UUID("7c1f4a1e-8f3b-4d7e-9a26-5b2a3c4d5e6f")

TERMINAL_ORDER_STATUSES = frozenset(
    {
        "filled",
        "canceled",
        "cancelled",
        "expired",
        "rejected",
        "replaced",
        "done_for_day",
        "stopped",
        "suspended",
        "calculated",
    }
)


class AdapterError(ValueError):
    """Raised when an upstream payload cannot be mapped. The brake fails closed on it."""


def D(value: Any) -> Decimal:
    if value is None or value == "":
        raise AdapterError("missing numeric value")
    return Decimal(str(value))


def unwrap(result: Any) -> Any:
    """Return the payload of an upstream result, stripping Alpaca's trust envelope.

    Accepts a fastmcp ToolResult, a plain dict, or a string. Alpaca's
    TrustBoundaryMiddleware wraps structured content as
    {"_alpaca_mcp_security": {...}, "data": payload}; fastmcp wraps non-dict
    returns as {"result": value}.
    """
    payload: Any = result
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        payload = structured
    elif not isinstance(result, (dict, list, str)):
        content = getattr(result, "content", None) or []
        texts = [getattr(block, "text", None) for block in content]
        payload = next((t for t in texts if t), None)
    # The live server nests wrappers: envelope -> {"result": [...]} for list-returning
    # tools, and sometimes a JSON string inside. Peel until the shape is stable.
    for _ in range(4):
        before = payload
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return payload
        if isinstance(payload, dict):
            if "_alpaca_mcp_security" in payload and "data" in payload:
                payload = payload["data"]
            elif set(payload.keys()) == {"result"}:
                payload = payload["result"]
        if payload is before:
            break
    return payload


def as_list(payload: Any) -> list[Any]:
    """Coerce a positions/orders payload to a list whatever wrapper the server used."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("result", "positions", "orders", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []
    raise AdapterError(f"expected a list payload, got {type(payload).__name__}")


def is_crypto_symbol(symbol: str) -> bool:
    return "/" in symbol


def quote_from(symbol: str, payload: Any, price_tick: Decimal) -> MarketQuote:
    """Build a two-sided quote from the shapes Alpaca's quote tools return."""
    symbol = symbol.upper()
    quote: Any = payload
    if isinstance(payload, dict):
        if isinstance(payload.get("quote"), dict):
            quote = payload["quote"]
        elif isinstance(payload.get("quotes"), dict):
            quote = payload["quotes"].get(symbol) or next(iter(payload["quotes"].values()), None)
    if not isinstance(quote, dict):
        raise AdapterError(f"no quote payload for {symbol}")
    ask = quote.get("ap", quote.get("ask_price", quote.get("ask")))
    bid = quote.get("bp", quote.get("bid_price", quote.get("bid")))
    if ask in (None, 0, "0") or bid in (None, 0, "0"):
        raise AdapterError(f"no two-sided quote for {symbol}")
    bid_d, ask_d = D(bid), D(ask)
    if bid_d > ask_d:
        bid_d, ask_d = ask_d, bid_d
    mark = ((bid_d + ask_d) / 2).quantize(price_tick, rounding=ROUND_HALF_EVEN)
    if mark <= 0:
        mark = price_tick
    return MarketQuote(symbol=symbol, bid=bid_d, ask=ask_d, mark=mark)


def quote_from_trade(symbol: str, payload: Any, price_tick: Decimal) -> MarketQuote:
    """Fallback when the book is one-sided (closed market): use the last trade price."""
    trade: Any = payload
    if isinstance(payload, dict):
        if isinstance(payload.get("trade"), dict):
            trade = payload["trade"]
        elif isinstance(payload.get("trades"), dict):
            trade = payload["trades"].get(symbol.upper()) or next(iter(payload["trades"].values()), None)
    if not isinstance(trade, dict):
        raise AdapterError(f"no trade payload for {symbol}")
    price = D(trade.get("p", trade.get("price")))
    price = price.quantize(price_tick, rounding=ROUND_HALF_EVEN) or price_tick
    return MarketQuote(symbol=symbol.upper(), bid=price, ask=price, mark=price)


def instrument_spec(symbol: str, asset: Any) -> InstrumentSpec:
    symbol = symbol.upper()
    if not isinstance(asset, dict) or not ({"symbol", "tradable", "id"} & set(asset)):
        # An error string or an empty payload must never turn into default instrument facts.
        raise AdapterError(f"no asset facts for {symbol}: {str(asset)[:120]!r}")
    if asset.get("tradable") is False:
        raise AdapterError(f"{symbol} is not tradable at the broker")
    crypto = is_crypto_symbol(symbol)
    fractionable = bool(asset.get("fractionable", crypto))
    default_step = Decimal("0.000000001") if fractionable else Decimal("1")
    quantity_step = D(asset["min_trade_increment"]) if asset.get("min_trade_increment") else default_step
    min_quantity = D(asset["min_order_size"]) if asset.get("min_order_size") else quantity_step
    price_tick = D(asset["price_increment"]) if asset.get("price_increment") else Decimal("0.0001")
    if crypto:
        base, quote = symbol.split("/", 1)
    else:
        base, quote = symbol, "USD"
    return InstrumentSpec(
        instrument_id=f"{BROKER}:{symbol}",
        version=str(asset.get("id") or "v1"),
        broker=BROKER,
        symbol=symbol,
        instrument_type=InstrumentType.SPOT,
        position_mode=PositionMode.ONE_WAY,
        allows_short=bool(asset.get("shortable", False)) and not crypto,
        base_asset=base,
        quote_asset=quote,
        contract_multiplier=Decimal("1"),
        quantity_step=quantity_step,
        price_tick=price_tick,
        min_quantity=min_quantity,
        min_notional=Decimal("1"),
    )


def instrument_catalog(specs: list[InstrumentSpec], observed_at: datetime) -> InstrumentCatalog:
    return InstrumentCatalog(
        catalog_id=uuid.uuid4(),
        version=observed_at.date().isoformat(),
        broker=BROKER,
        instruments=tuple(sorted(specs, key=lambda s: s.symbol)),
        observed_at=observed_at,
    ).with_content_hash()


def market_snapshot(quotes: dict[str, MarketQuote], observed_at: datetime) -> MarketSnapshot:
    return MarketSnapshot(
        snapshot_id=uuid.uuid4(),
        source=SOURCE,
        quotes=tuple(quotes[s] for s in sorted(quotes)),
        observed_at=observed_at,
    ).with_content_hash()


def order_status(raw: str) -> OpenOrderStatus:
    raw = (raw or "").lower()
    if raw in {"new", "accepted", "pending_new", "held", "accepted_for_bidding"}:
        return OpenOrderStatus.NEW
    if raw == "partially_filled":
        return OpenOrderStatus.PARTIALLY_FILLED
    if raw in {"pending_cancel", "pending_replace"}:
        return OpenOrderStatus.PENDING_CANCEL
    return OpenOrderStatus.UNKNOWN


def account_snapshot(
    account: Any,
    positions: Any,
    orders: Any,
    quotes: dict[str, MarketQuote],
    *,
    halt: str,
    drawdown_from_peak: Decimal,
    pnl_period: tuple[datetime, datetime],
    observed_at: datetime,
    state_version: int,
) -> TrustedAccountSnapshot:
    if not isinstance(account, dict) or "id" not in account:
        raise AdapterError("account payload has no id")
    equity = D(account.get("equity"))
    cash = D(account.get("cash"))
    last_equity = D(account.get("last_equity")) if account.get("last_equity") not in (None, "") else equity
    halt_state = HaltState(halt)
    if account.get("trading_blocked") or account.get("account_blocked"):
        halt_state = HaltState.FULL_HALT

    pos_models: list[Position] = []
    for p in positions or []:
        if not isinstance(p, dict):
            continue
        qty = D(p.get("qty"))
        sign = Decimal("-1") if str(p.get("side", "long")).lower() == "short" else Decimal("1")
        pos_models.append(Position(symbol=str(p["symbol"]), signed_quantity=qty * sign))

    order_models: list[OpenOrderExposure] = []
    for o in orders or []:
        if not isinstance(o, dict):
            continue
        status_raw = str(o.get("status", ""))
        if status_raw.lower() in TERMINAL_ORDER_STATUSES:
            continue
        symbol = str(o["symbol"]).upper()
        filled = D(o.get("filled_qty") or "0")
        if o.get("qty") not in (None, ""):
            qty = D(o["qty"])
        elif o.get("notional") not in (None, ""):
            if symbol not in quotes:
                raise AdapterError(f"open notional order on {symbol} but no quote to size it")
            qty = D(o["notional"]) / quotes[symbol].mark
        else:
            raise AdapterError(f"open order {o.get('id')} has neither qty nor notional")
        remaining = qty - filled
        if remaining <= 0:
            continue
        if o.get("limit_price") not in (None, ""):
            reference = D(o["limit_price"])
        elif o.get("stop_price") not in (None, ""):
            reference = D(o["stop_price"])
        elif symbol in quotes:
            reference = quotes[symbol].mark
        else:
            raise AdapterError(f"open order on {symbol} has no reference price")
        order_models.append(
            OpenOrderExposure(
                broker_order_id=str(o.get("id") or o.get("client_order_id")),
                symbol=symbol,
                side=Side(str(o["side"]).upper()),
                remaining_quantity=remaining,
                reduce_only=False,
                reference_price=reference,
                status=order_status(status_raw),
            )
        )

    return TrustedAccountSnapshot(
        snapshot_id=uuid.uuid4(),
        state_version=state_version,
        source=SOURCE,
        account_id=str(account["id"]),
        broker=BROKER,
        equity=equity,
        cash_balance=cash,
        realized_pnl_today=equity - last_equity,
        realized_pnl_period_start=pnl_period[0],
        realized_pnl_period_end=pnl_period[1],
        drawdown_from_peak=drawdown_from_peak,
        positions=tuple(pos_models),
        open_orders=tuple(order_models),
        halt_state=halt_state,
        observed_at=observed_at,
    ).with_content_hash()


def intent_id_for(account_id: str, client_order_id: str | None) -> tuple[uuid.UUID, bool]:
    """Deterministic id when the agent supplied an idempotency key, else random.

    The bool says whether the id is deterministic, which is what makes the
    replay cache safe to use.
    """
    if client_order_id:
        return uuid.uuid5(INTENT_NAMESPACE, f"{account_id}:{client_order_id}"), True
    return uuid.uuid4(), False


def intent_from_call(
    tool: str,
    args: dict[str, Any],
    *,
    account_id: str,
    agent_id: str,
    quotes: dict[str, MarketQuote],
    specs: dict[str, InstrumentSpec],
    market_data_as_of: datetime,
    now: datetime,
) -> OrderIntent:
    symbol = str(args.get("symbol", "")).upper().strip()
    if not symbol:
        raise AdapterError("order has no symbol")
    side_raw = str(args.get("side", "")).lower()
    if side_raw not in {"buy", "sell"}:
        raise AdapterError(f"unsupported side {side_raw!r}")
    type_raw = str(args.get("type", "market")).lower()
    if type_raw not in SUPPORTED_ORDER_TYPES:
        raise AdapterError(
            f"order type {type_raw!r} is not evaluable by policy v0; use market, limit or stop"
        )
    order_type = SUPPORTED_ORDER_TYPES[type_raw]

    spec = specs.get(symbol)
    quote = quotes.get(symbol)
    if spec is None or quote is None:
        raise AdapterError(f"no instrument or quote for {symbol}")

    if args.get("qty") not in (None, ""):
        quantity = D(args["qty"])
    elif args.get("notional") not in (None, ""):
        quantity = (D(args["notional"]) / quote.mark).quantize(spec.quantity_step, rounding=ROUND_DOWN)
    else:
        raise AdapterError("order has neither qty nor notional")
    if quantity <= 0:
        raise AdapterError("order quantity is not positive")

    limit_price = D(args["limit_price"]) if args.get("limit_price") not in (None, "") else None
    stop_price = D(args["stop_price"]) if args.get("stop_price") not in (None, "") else None
    protective = (
        D(args["stop_loss_stop_price"]) if args.get("stop_loss_stop_price") not in (None, "") else None
    )
    if order_type is OrderType.MARKET:
        limit_price, stop_price = None, None
    elif order_type is OrderType.LIMIT:
        stop_price = None
    elif order_type is OrderType.STOP:
        limit_price = None

    intent_id, _ = intent_id_for(account_id, args.get("client_order_id"))
    advanced = args.get("advanced_instructions")
    advanced = advanced if isinstance(advanced, dict) else {}
    strategy_id = str(advanced.get("strategy") or "mcp-agent")

    return OrderIntent(
        intent_id=intent_id,
        agent_id=agent_id,
        account_id=account_id,
        broker=BROKER,
        symbol=symbol,
        side=Side(side_raw.upper()),
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
        stop_price=stop_price,
        protective_stop_price=protective,
        reduce_only=False,
        strategy_id=strategy_id,
        reason=f"{tool} via tradememory proxy",
        market_data_as_of=market_data_as_of,
        created_at=now,
    )


# Argument names below were read from the live server's tool schemas on
# 2026-10-01 (alpaca-mcp-server, 72 tools), not from its README: quotes and
# trades take plural ``symbols``, crypto data also needs ``loc``, and assets
# are looked up by ``symbol_or_asset_id``. ``tradememory proxy doctor`` re-checks them.
CRYPTO_LOC = "us"


def quote_call(symbol: str) -> tuple[str, dict[str, Any]]:
    """Which upstream tool and arguments fetch a latest quote for this symbol."""
    if is_crypto_symbol(symbol):
        return "get_crypto_latest_quote", {"loc": CRYPTO_LOC, "symbols": symbol}
    return "get_stock_latest_quote", {"symbols": symbol}


def trade_call(symbol: str) -> tuple[str, dict[str, Any]]:
    if is_crypto_symbol(symbol):
        return "get_crypto_latest_trade", {"loc": CRYPTO_LOC, "symbols": symbol}
    return "get_stock_latest_trade", {"symbols": symbol}


def asset_call(symbol: str) -> tuple[str, dict[str, Any]]:
    return "get_asset", {"symbol_or_asset_id": symbol}


def orders_call() -> tuple[str, dict[str, Any]]:
    return "get_orders", {"status": "open"}
