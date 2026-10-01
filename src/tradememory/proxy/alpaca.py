"""Alpaca MCP adapter: classify tools, unwrap upstream results, map them to Mnemox Control inputs.

Everything here is pure mapping. It never calls the network; the brake hands
it the raw payloads it fetched from the upstream MCP server.

Argument names and payload shapes were read from the live alpaca-mcp-server
(72 tools) on 2026-10-01, not from its README: quotes and trades take plural
``symbols`` and come back keyed by symbol, crypto data needs ``loc``, assets
are looked up by ``symbol_or_asset_id`` and return the canonical symbol
(``BTCUSD`` -> ``BTC/USD``), list tools wrap results as ``{"result": [...]}``
inside the trust envelope, and bracket legs carry ``position_intent``.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
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
CRYPTO_LOC = "us"
ORDERS_PAGE_LIMIT = 500  # Alpaca's maximum; hitting it means the book may be truncated

# ---------------------------------------------------------------- tool classes
ORDER_TOOLS = frozenset({"place_stock_order", "place_crypto_order"})
EXIT_TOOLS = frozenset({"close_position", "close_all_positions"})
CANCEL_TOOLS = frozenset({"cancel_order_by_id", "cancel_all_orders"})
UNSUPPORTED_ORDER_TOOLS: dict[str, str] = {
    "place_option_order": "options are not covered by policy v0",
    "exercise_options_position": "options are not covered by policy v0",
    "do_not_exercise_options_position": "options are not covered by policy v0",
    "replace_order_by_id": "replacing an order bypasses evaluation; cancel it and place a new order",
    "create_locate": "short-sale locates are not covered by policy v0",
}
# Mutations that cannot add market risk; forwarded and recorded, not evaluated.
BENIGN_TOOLS = frozenset(
    {
        "create_watchlist",
        "update_watchlist_by_id",
        "delete_watchlist_by_id",
        "add_asset_to_watchlist_by_id",
        "remove_asset_from_watchlist_by_id",
        "update_account_config",
    }
)
READ_PREFIXES = ("get_", "search_", "fetch_", "list_")

# The live tool list captured on 2026-10-01. `doctor` diffs the running server
# against it so a new mutating tool is noticed instead of silently denied.
KNOWN_LIVE_TOOLS = frozenset(
    """add_asset_to_watchlist_by_id cancel_all_orders cancel_order_by_id close_all_positions
    close_position create_locate create_watchlist delete_watchlist_by_id
    do_not_exercise_options_position exercise_options_position fetch_alpaca_doc
    get_account_activities get_account_activities_by_type get_account_config get_account_info
    get_all_assets get_all_positions get_alpaca_endpoint_docs get_asset get_calendar get_clock
    get_corporate_action_announcement get_corporate_action_announcements get_corporate_actions
    get_crypto_bars get_crypto_latest_bar get_crypto_latest_orderbook get_crypto_latest_quote
    get_crypto_latest_trade get_crypto_quotes get_crypto_snapshot get_crypto_trades
    get_fixed_income_latest_quotes get_locate get_locate_quotes get_locates get_market_movers
    get_most_active_stocks get_news get_open_position get_option_bars get_option_chain
    get_option_contract get_option_contracts get_option_exchange_codes get_option_latest_quote
    get_option_latest_trade get_option_snapshot get_option_trades get_order_by_client_id
    get_order_by_id get_orders get_portfolio_history get_stock_bars get_stock_latest_bar
    get_stock_latest_quote get_stock_latest_trade get_stock_quotes get_stock_snapshot
    get_stock_trades get_watchlist_by_id get_watchlists list_alpaca_api_endpoints
    place_crypto_order place_option_order place_stock_order remove_asset_from_watchlist_by_id
    replace_order_by_id search_alpaca_api_specs search_alpaca_docs update_account_config
    update_watchlist_by_id""".split()
)


def classify_tool(name: str) -> str:
    """order | exit | cancel | unsupported | benign | read | unknown. Unknown is refused."""
    if name in ORDER_TOOLS:
        return "order"
    if name in EXIT_TOOLS:
        return "exit"
    if name in CANCEL_TOOLS:
        return "cancel"
    if name in UNSUPPORTED_ORDER_TOOLS:
        return "unsupported"
    if name in BENIGN_TOOLS:
        return "benign"
    if name.startswith(READ_PREFIXES):
        return "read"
    return "unknown"


SUPPORTED_ORDER_TYPES = {
    "market": OrderType.MARKET,
    "limit": OrderType.LIMIT,
    "stop": OrderType.STOP,
}
BRACKET_CLASSES = {"bracket", "oto"}
STOP_ORDER_TYPES = {"stop", "stop_limit", "trailing_stop"}

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

_FRACTION = re.compile(r"(\.\d{6})\d+")


class AdapterError(ValueError):
    """Raised when an upstream payload cannot be mapped. The brake fails closed on it."""


def D(value: Any) -> Decimal:
    if value is None or value == "" or isinstance(value, bool):
        raise AdapterError("missing numeric value")
    return Decimal(str(value))


def parse_ts(value: Any) -> datetime | None:
    """Alpaca timestamps carry nanoseconds and a Z; fromisoformat wants <= 6 digits."""
    if not isinstance(value, str) or not value:
        return None
    text = _FRACTION.sub(r"\1", value.replace("Z", "+00:00"))
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


# ---------------------------------------------------------------- unwrapping
def unwrap(result: Any) -> Any:
    """Return the payload of an upstream result, stripping Alpaca's trust envelope.

    Accepts a fastmcp ToolResult, a plain dict, or a string. The live server
    nests wrappers: envelope -> {"result": [...]} for list-returning tools,
    sometimes with a JSON string inside. Peel until the shape is stable.
    """
    payload: Any = result
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        payload = structured
    elif not isinstance(result, (dict, list, str)):
        content = getattr(result, "content", None) or []
        texts = [getattr(block, "text", None) for block in content]
        payload = next((t for t in texts if t), None)
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
    """Coerce a positions/orders payload to a list, or refuse: an unknown shape must not read as 'empty'."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("result", "positions", "orders", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        raise AdapterError(f"expected a list payload, got an object with keys {sorted(payload)[:6]}")
    raise AdapterError(f"expected a list payload, got {type(payload).__name__}")


# ---------------------------------------------------------------- fingerprints
def intent_id_for(account_id: str, client_order_id: str) -> uuid.UUID:
    return uuid.uuid5(INTENT_NAMESPACE, f"{account_id}:{client_order_id}")


def terms_summary(tool: str, args: dict[str, Any]) -> str:
    """One readable line of the order terms, shown to the owner at approval time."""
    parts = [str(args.get("side", "?")).upper()]
    if args.get("qty") not in (None, ""):
        parts.append(f"{args['qty']} x")
    elif args.get("notional") not in (None, ""):
        parts.append(f"${args['notional']} of")
    parts.append(str(args.get("symbol", "?")).upper())
    parts.append(str(args.get("type", "market")).lower())
    for key, label in (("limit_price", "limit"), ("stop_price", "stop"), ("stop_loss_stop_price", "stop-loss"),
                       ("take_profit_limit_price", "take-profit")):
        if args.get(key) not in (None, ""):
            parts.append(f"{label} {args[key]}")
    if args.get("order_class"):
        parts.append(str(args["order_class"]))
    parts.append(f"[{tool}]")
    return " ".join(parts)


def request_fingerprint(tool: str, args: dict[str, Any]) -> str:
    """Hash of the order terms as the agent sent them. Approvals and replays bind to this."""
    keys = (
        "symbol", "side", "type", "qty", "notional", "limit_price", "stop_price",
        "stop_loss_stop_price", "stop_loss_limit_price", "take_profit_limit_price",
        "order_class", "time_in_force", "extended_hours", "trail_price", "trail_percent",
    )
    terms = {"tool": tool}
    for key in keys:
        value = args.get(key)
        if value is None or value == "":
            continue
        terms[key] = str(value).strip().upper() if key in ("symbol", "side", "type", "order_class") else str(value)
    return hashlib.sha256(json.dumps(terms, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------- assets
def is_crypto_asset(asset: dict[str, Any]) -> bool:
    return str(asset.get("class", "")).lower() == "crypto"


def canonical_symbol(asset: dict[str, Any], fallback: str) -> str:
    symbol = asset.get("symbol")
    return str(symbol).upper() if symbol else fallback.upper()


def instrument_spec(symbol: str, asset: Any) -> InstrumentSpec:
    if not isinstance(asset, dict) or not ({"symbol", "tradable", "id"} & set(asset)):
        # An error string or an empty payload must never turn into default instrument facts.
        raise AdapterError(f"no asset facts for {symbol}: {str(asset)[:120]!r}")
    if asset.get("tradable") is False:
        raise AdapterError(f"{symbol} is not tradable at the broker")
    symbol = canonical_symbol(asset, symbol)
    crypto = is_crypto_asset(asset)
    fractionable = bool(asset.get("fractionable", crypto))
    default_step = Decimal("0.000000001") if fractionable else Decimal("1")
    quantity_step = D(asset["min_trade_increment"]) if asset.get("min_trade_increment") else default_step
    min_quantity = D(asset["min_order_size"]) if asset.get("min_order_size") else quantity_step
    price_tick = D(asset["price_increment"]) if asset.get("price_increment") else Decimal("0.0001")
    if crypto and "/" in symbol:
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


# ---------------------------------------------------------------- quotes
def quote_from(symbol: str, payload: Any, price_tick: Decimal) -> tuple[MarketQuote, datetime | None]:
    """Two-sided quote plus its timestamp from the shapes Alpaca's quote tools return."""
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
    return MarketQuote(symbol=symbol, bid=bid_d, ask=ask_d, mark=mark), parse_ts(quote.get("t"))


def quote_from_trade(symbol: str, payload: Any, price_tick: Decimal) -> tuple[MarketQuote, datetime | None]:
    """Fallback when the book is one-sided or the market is closed: the last trade price."""
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
    return MarketQuote(symbol=symbol.upper(), bid=price, ask=price, mark=price), parse_ts(trade.get("t"))


def market_snapshot(quotes: dict[str, MarketQuote], observed_at: datetime) -> MarketSnapshot:
    return MarketSnapshot(
        snapshot_id=uuid.uuid4(),
        source=SOURCE,
        quotes=tuple(quotes[s] for s in sorted(quotes)),
        observed_at=observed_at,
    ).with_content_hash()


# ---------------------------------------------------------------- account
def order_status(raw: str) -> OpenOrderStatus:
    raw = (raw or "").lower()
    if raw in {"new", "accepted", "pending_new", "held", "accepted_for_bidding"}:
        return OpenOrderStatus.NEW
    if raw == "partially_filled":
        return OpenOrderStatus.PARTIALLY_FILLED
    if raw in {"pending_cancel", "pending_replace"}:
        return OpenOrderStatus.PENDING_CANCEL
    return OpenOrderStatus.UNKNOWN


def is_closing_order(order: dict[str, Any], positions: dict[str, Decimal]) -> bool:
    """A bracket/OCO leg that only closes an existing position; it adds no exposure."""
    intent = str(order.get("position_intent") or "").lower()
    if intent:
        return intent.endswith("_to_close")
    symbol = str(order.get("symbol", "")).upper()
    held = positions.get(symbol)
    if held is None or held == 0:
        return False
    if str(order.get("order_class") or "").lower() not in {"bracket", "oco", "oto"}:
        return False
    side = str(order.get("side", "")).lower()
    return (held > 0 and side == "sell") or (held < 0 and side == "buy")


def is_protective_leg(order: Any, positions: dict[str, Decimal]) -> bool:
    """True when cancelling this order would leave an open position without its stop."""
    if not isinstance(order, dict):
        raise AdapterError("order lookup returned no order")
    if str(order.get("status", "")).lower() in TERMINAL_ORDER_STATUSES:
        return False
    if str(order.get("type") or order.get("order_type") or "").lower() not in STOP_ORDER_TYPES:
        return False
    symbol = str(order.get("symbol", "")).upper()
    return is_closing_order(order, positions) and positions.get(symbol, Decimal("0")) != 0


def account_snapshot(
    account: Any,
    positions: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    quotes: dict[str, MarketQuote],
    *,
    halt: str,
    drawdown_from_peak: Decimal,
    pnl_period: tuple[datetime, datetime],
    observed_at: datetime,
    state_version: int,
) -> TrustedAccountSnapshot:
    """Positions and orders must already carry canonical symbols (see the brake's _collect)."""
    if not isinstance(account, dict) or "id" not in account:
        raise AdapterError("account payload has no id")
    equity = D(account.get("equity"))
    cash = D(account.get("cash"))
    last_equity = D(account.get("last_equity")) if account.get("last_equity") not in (None, "") else equity
    halt_state = HaltState(halt)
    if account.get("trading_blocked") or account.get("account_blocked"):
        halt_state = HaltState.FULL_HALT

    pos_models: list[Position] = []
    held: dict[str, Decimal] = {}
    for p in positions:
        if not isinstance(p, dict):
            raise AdapterError("position payload is not an object")
        qty = D(p.get("qty"))
        sign = Decimal("-1") if str(p.get("side", "long")).lower() == "short" else Decimal("1")
        symbol = str(p["symbol"]).upper()
        held[symbol] = qty * sign
        pos_models.append(Position(symbol=symbol, signed_quantity=qty * sign))

    order_models: list[OpenOrderExposure] = []
    for o in orders:
        if not isinstance(o, dict):
            raise AdapterError("order payload is not an object")
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
                reduce_only=is_closing_order(o, held),
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


# ---------------------------------------------------------------- intents
def intent_from_call(
    tool: str,
    args: dict[str, Any],
    *,
    account_id: str,
    agent_id: str,
    symbol: str,
    quotes: dict[str, MarketQuote],
    specs: dict[str, InstrumentSpec],
    market_data_as_of: datetime,
    now: datetime,
) -> OrderIntent:
    """Map the agent's call to an OrderIntent. ``symbol`` is the canonical symbol."""
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

    has_qty = args.get("qty") not in (None, "")
    has_notional = args.get("notional") not in (None, "")
    if has_qty and has_notional:
        raise AdapterError("order carries both qty and notional; send one so what is evaluated is what executes")
    if has_qty:
        quantity = D(args["qty"])
    elif has_notional:
        quantity = (D(args["notional"]) / quote.mark).quantize(spec.quantity_step, rounding=ROUND_DOWN)
    else:
        raise AdapterError("order has neither qty nor notional")
    if quantity <= 0:
        raise AdapterError("order quantity is not positive")

    limit_price = D(args["limit_price"]) if args.get("limit_price") not in (None, "") else None
    stop_price = D(args["stop_price"]) if args.get("stop_price") not in (None, "") else None
    # A stop-loss leg exists at Alpaca only inside a bracket/OTO class on the
    # stock tool. Anywhere else the field is decoration and must not satisfy
    # require_protective_stop.
    protective = None
    if (
        tool == "place_stock_order"
        and str(args.get("order_class") or "").lower() in BRACKET_CLASSES
        and args.get("stop_loss_stop_price") not in (None, "")
    ):
        protective = D(args["stop_loss_stop_price"])
    if order_type is OrderType.MARKET:
        limit_price, stop_price = None, None
    elif order_type is OrderType.LIMIT:
        stop_price = None
    elif order_type is OrderType.STOP:
        limit_price = None

    client_order_id = str(args.get("client_order_id") or "").strip()
    if not client_order_id:
        raise AdapterError("client_order_id is required")
    advanced = args.get("advanced_instructions")
    advanced = advanced if isinstance(advanced, dict) else {}
    strategy_id = str(advanced.get("strategy") or "mcp-agent")

    return OrderIntent(
        intent_id=intent_id_for(account_id, client_order_id),
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


# ---------------------------------------------------------------- upstream calls
def quote_call(symbol: str, crypto: bool) -> tuple[str, dict[str, Any]]:
    if crypto:
        return "get_crypto_latest_quote", {"loc": CRYPTO_LOC, "symbols": symbol}
    return "get_stock_latest_quote", {"symbols": symbol}


def trade_call(symbol: str, crypto: bool) -> tuple[str, dict[str, Any]]:
    if crypto:
        return "get_crypto_latest_trade", {"loc": CRYPTO_LOC, "symbols": symbol}
    return "get_stock_latest_trade", {"symbols": symbol}


def asset_call(symbol: str) -> tuple[str, dict[str, Any]]:
    return "get_asset", {"symbol_or_asset_id": symbol}


def orders_call() -> tuple[str, dict[str, Any]]:
    return "get_orders", {"status": "open", "nested": True, "limit": ORDERS_PAGE_LIMIT}


def order_by_id_call(order_id: str) -> tuple[str, dict[str, Any]]:
    return "get_order_by_id", {"order_id": order_id, "nested": False}


def order_by_client_id_call(client_order_id: str) -> tuple[str, dict[str, Any]]:
    return "get_order_by_client_id", {"client_order_id": client_order_id}
