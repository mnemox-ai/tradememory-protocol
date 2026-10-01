"""Stateful fake of Alpaca's MCP server, shaped like the real one.

Tool names, argument names and payload shapes mirror what the live
alpaca-mcp-server (72 tools) returned on 2026-10-01, trust envelope included:
quotes and trades take plural ``symbols`` and come back keyed by symbol with a
``t`` timestamp, crypto data needs ``loc``, assets are looked up by
``symbol_or_asset_id`` and return the canonical symbol (``BTCUSD`` ->
``BTC/USD``), list tools wrap their result as ``{"result": [...]}``, bracket
parents carry ``legs`` and ``position_intent``.

It keeps an account, positions and orders in memory so a test can assert that
an ALLOW really changed upstream state and a DENY really did not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastmcp import FastMCP


def envelope(data: Any) -> dict[str, Any]:
    return {
        "_alpaca_mcp_security": {
            "trust": "untrusted_tool_output",
            "risk": "api_structured",
            "instructions": "fake upstream",
        },
        "data": data,
    }


OPEN_STATES = {"new", "accepted", "partially_filled", "pending_new", "held"}


class FakeAlpaca:
    def __init__(self) -> None:
        self.account: dict[str, Any] = {
            "id": "acct-1",
            "account_number": "PA0000000000",
            "status": "ACTIVE",
            "equity": "10000",
            "cash": "10000",
            "last_equity": "10000",
            "trading_blocked": False,
            "account_blocked": False,
        }
        self.positions: list[dict[str, Any]] = []
        self.orders: list[dict[str, Any]] = []
        self.placed: list[dict[str, Any]] = []
        self.cancelled: list[str] = []
        self.quotes: dict[str, tuple[str, str]] = {
            "AAPL": ("189.98", "190.02"),
            "MSFT": ("409.90", "410.10"),
            "TSLA": ("249.90", "250.10"),
            "BTC/USD": ("83659.42", "83682.99"),
        }
        self.last_trade: dict[str, str] = {s: ask for s, (_, ask) in self.quotes.items()}
        self.assets: dict[str, dict[str, Any]] = {
            s: {
                "id": f"asset-{s}",
                "class": "crypto" if "/" in s else "us_equity",
                "symbol": s,
                "status": "active",
                "tradable": True,
                "shortable": "/" not in s,
                "fractionable": True,
            }
            for s in self.quotes
        }
        self.assets["BTC/USD"].update(
            {"min_order_size": "0.000011983", "min_trade_increment": "0.000000001", "price_increment": "0.000000001"}
        )
        self.is_open = True
        self.quote_age_seconds = 1
        self.fail_quotes = False
        self.one_sided_quotes = False
        self.fail_trades = False
        self.fail_place_after_accept = False
        self.positions_payload_override: Any = None
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._n = 0

    # ------------------------------------------------------------------ helpers
    def _canon(self, symbol: str) -> str:
        symbol = symbol.upper()
        if symbol in self.assets:
            return symbol
        for s in self.assets:
            if s.replace("/", "") == symbol:
                return s
        return symbol

    def _apply_fill(self, symbol: str, side: str, qty: Decimal) -> None:
        signed = qty if side == "buy" else -qty
        for p in self.positions:
            if self._canon(p["symbol"]) == symbol:
                current = Decimal(p["qty"]) * (1 if p["side"] == "long" else -1)
                new = current + signed
                if new == 0:
                    self.positions.remove(p)
                else:
                    p["qty"] = str(abs(new))
                    p["side"] = "long" if new > 0 else "short"
                return
        self.positions.append({"symbol": symbol, "qty": str(abs(signed)), "side": "long" if signed > 0 else "short"})

    def _ts(self) -> str:
        return (datetime.now(UTC) - timedelta(seconds=self.quote_age_seconds)).isoformat().replace("+00:00", "Z")

    def _new_id(self) -> str:
        self._n += 1
        return f"ord-{self._n}"

    def _held(self) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for p in self.positions:
            out[self._canon(p["symbol"])] = Decimal(p["qty"]) * (1 if p["side"] == "long" else -1)
        return out

    # ------------------------------------------------------------------ server
    def server(self) -> FastMCP:
        mcp = FastMCP("fake-alpaca")
        fake = self

        @mcp.tool
        def get_account_info() -> dict:
            fake.calls.append(("get_account_info", {}))
            return envelope(dict(fake.account))

        @mcp.tool
        def get_all_positions() -> dict:
            fake.calls.append(("get_all_positions", {}))
            if fake.positions_payload_override is not None:
                return envelope(fake.positions_payload_override)
            return envelope({"result": [dict(p) for p in fake.positions]})

        @mcp.tool
        def get_orders(
            status: str | None = None, limit: int | None = None, nested: bool | None = None,
            symbols: str | None = None,
        ) -> dict:
            fake.calls.append(("get_orders", {"status": status, "limit": limit, "nested": nested}))
            rows = [o for o in fake.orders if status in (None, "all") or (status == "open" and o["status"] in OPEN_STATES)]
            return envelope({"result": [dict(o) for o in rows]})

        @mcp.tool
        def get_order_by_id(order_id: str, nested: bool | None = None) -> dict:
            fake.calls.append(("get_order_by_id", {"order_id": order_id}))
            for o in fake.orders:
                if o["id"] == order_id:
                    return envelope(dict(o))
            raise ValueError(f"HTTP error 404: order not found for {order_id}")

        @mcp.tool
        def get_order_by_client_id(client_order_id: str) -> dict:
            fake.calls.append(("get_order_by_client_id", {"client_order_id": client_order_id}))
            for o in fake.orders:
                if o.get("client_order_id") == client_order_id:
                    return envelope(dict(o))
            raise ValueError(f"HTTP error 404: order not found for client_order_id {client_order_id}")

        @mcp.tool
        def get_asset(symbol_or_asset_id: str) -> dict:
            fake.calls.append(("get_asset", {"symbol_or_asset_id": symbol_or_asset_id}))
            canon = fake._canon(symbol_or_asset_id)
            if canon not in fake.assets:
                raise ValueError(f"HTTP error 404: asset not found for {symbol_or_asset_id}")
            return envelope(dict(fake.assets[canon]))

        @mcp.tool
        def get_clock() -> dict:
            fake.calls.append(("get_clock", {}))
            return envelope({"is_open": fake.is_open, "timestamp": "2026-10-01T09:45:00-04:00"})

        def _quote_payload(symbols: str) -> dict:
            out = {}
            for s in symbols.split(","):
                bid, ask = fake.quotes[s]
                if fake.one_sided_quotes:
                    bid = "0"
                out[s] = {"ap": float(ask), "as": 1, "bp": float(bid), "bs": 1, "t": fake._ts()}
            return envelope({"quotes": out})

        def _trade_payload(symbols: str) -> dict:
            return envelope({"trades": {s: {"p": float(fake.last_trade[s]), "s": 1, "t": fake._ts()} for s in symbols.split(",")}})

        @mcp.tool
        def get_stock_latest_quote(symbols: str, feed: str | None = None, currency: str | None = None) -> dict:
            fake.calls.append(("get_stock_latest_quote", {"symbols": symbols}))
            if fake.fail_quotes:
                raise RuntimeError("HTTP error 503: quote feed down")
            return _quote_payload(symbols)

        @mcp.tool
        def get_stock_latest_trade(symbols: str, feed: str | None = None, currency: str | None = None) -> dict:
            fake.calls.append(("get_stock_latest_trade", {"symbols": symbols}))
            if fake.fail_trades:
                raise RuntimeError("HTTP error 503: trade feed down")
            return _trade_payload(symbols)

        @mcp.tool
        def get_crypto_latest_quote(loc: str, symbols: str) -> dict:
            fake.calls.append(("get_crypto_latest_quote", {"loc": loc, "symbols": symbols}))
            if loc != "us":
                raise ValueError("HTTP error 400: Invalid location")
            return _quote_payload(symbols)

        @mcp.tool
        def get_crypto_latest_trade(loc: str, symbols: str) -> dict:
            fake.calls.append(("get_crypto_latest_trade", {"loc": loc, "symbols": symbols}))
            return _trade_payload(symbols)

        @mcp.tool
        def place_stock_order(
            symbol: str,
            side: str,
            qty: str | None = None,
            notional: str | None = None,
            type: str = "market",
            time_in_force: str = "day",
            limit_price: str | None = None,
            stop_price: str | None = None,
            client_order_id: str | None = None,
            order_class: str | None = None,
            take_profit_limit_price: str | None = None,
            stop_loss_stop_price: str | None = None,
            stop_loss_limit_price: str | None = None,
        ) -> dict:
            # Assumption mirrored from Alpaca's order API: stop_loss / take_profit legs exist
            # only for bracket and OTO classes; a simple order with them is rejected.
            if (stop_loss_stop_price or take_profit_limit_price) and (order_class or "simple") not in ("bracket", "oto"):
                raise ValueError("HTTP error 422: stop_loss and take_profit require order_class bracket or oto")
            order = {
                "id": fake._new_id(),
                "client_order_id": client_order_id,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "notional": notional,
                "type": type,
                "status": "accepted",
                "filled_qty": "0",
                "limit_price": limit_price,
                "stop_price": stop_price,
                "order_class": order_class or "simple",
                "position_intent": "buy_to_open" if side == "buy" else "sell_to_close",
                "legs": None,
            }
            fake.placed.append(order)
            fake.orders.append(order)
            if fake.fail_place_after_accept:
                raise RuntimeError("HTTP error 504: gateway timeout after submit")
            if type == "market" and fake.is_open:
                filled_qty = Decimal(qty) if qty else Decimal(notional) / Decimal(fake.quotes[symbol][1])
                order["status"] = "filled"
                order["filled_qty"] = str(filled_qty)
                fake._apply_fill(symbol, side, filled_qty)
                if order_class in ("bracket", "oto"):
                    legs = []
                    opposite = "sell" if side == "buy" else "buy"
                    if stop_loss_stop_price:
                        legs.append({
                            "id": fake._new_id(), "client_order_id": f"leg-sl-{order['id']}", "symbol": symbol,
                            "side": opposite, "qty": str(filled_qty), "filled_qty": "0", "type": "stop",
                            "stop_price": stop_loss_stop_price, "limit_price": None, "status": "new",
                            "order_class": order_class, "position_intent": f"{opposite}_to_close", "legs": None,
                        })
                    if take_profit_limit_price:
                        legs.append({
                            "id": fake._new_id(), "client_order_id": f"leg-tp-{order['id']}", "symbol": symbol,
                            "side": opposite, "qty": str(filled_qty), "filled_qty": "0", "type": "limit",
                            "stop_price": None, "limit_price": take_profit_limit_price, "status": "new",
                            "order_class": order_class, "position_intent": f"{opposite}_to_close", "legs": None,
                        })
                    order["legs"] = [dict(leg) for leg in legs]
                    fake.orders.extend(legs)
            return envelope(dict(order))

        @mcp.tool
        def place_crypto_order(
            symbol: str,
            side: str,
            qty: str | None = None,
            notional: str | None = None,
            type: str = "market",
            time_in_force: str = "gtc",
            limit_price: str | None = None,
            stop_price: str | None = None,
            client_order_id: str | None = None,
        ) -> dict:
            order = {
                "id": fake._new_id(), "client_order_id": client_order_id, "symbol": symbol, "side": side,
                "qty": qty, "notional": notional, "type": type, "status": "accepted", "filled_qty": "0",
                "limit_price": limit_price, "stop_price": stop_price, "order_class": "simple",
                "position_intent": "buy_to_open" if side == "buy" else "sell_to_close", "legs": None,
            }
            fake.placed.append(order)
            fake.orders.append(order)
            return envelope(dict(order))

        @mcp.tool
        def cancel_order_by_id(order_id: str) -> dict:
            fake.calls.append(("cancel_order_by_id", {"order_id": order_id}))
            for o in fake.orders:
                if o["id"] == order_id:
                    o["status"] = "canceled"
                    fake.cancelled.append(order_id)
                    return envelope({"id": order_id, "status": "canceled"})
            raise ValueError(f"HTTP error 404: order not found for {order_id}")

        @mcp.tool
        def cancel_all_orders() -> dict:
            fake.calls.append(("cancel_all_orders", {}))
            ids = [o["id"] for o in fake.orders if o["status"] in OPEN_STATES]
            for o in fake.orders:
                if o["status"] in OPEN_STATES:
                    o["status"] = "canceled"
            fake.cancelled.extend(ids)
            return envelope({"result": [{"id": i, "status": 200} for i in ids]})

        @mcp.tool
        def close_position(symbol_or_asset_id: str, qty: str | None = None, percentage: str | None = None) -> dict:
            fake.calls.append(("close_position", {"symbol_or_asset_id": symbol_or_asset_id}))
            canon = fake._canon(symbol_or_asset_id)
            fake.positions = [p for p in fake.positions if fake._canon(p["symbol"]) != canon]
            return envelope({"symbol": canon, "status": "closed"})

        @mcp.tool
        def create_watchlist(name: str, symbols: list[str] | None = None) -> dict:
            fake.calls.append(("create_watchlist", {"name": name}))
            return envelope({"id": "wl-1", "name": name, "assets": symbols or []})

        @mcp.tool
        def place_option_order(qty: str, symbol: str | None = None, side: str | None = None) -> dict:
            fake.placed.append({"option": True, "symbol": symbol})
            return envelope({"id": "opt-1"})

        @mcp.tool
        def replace_order_by_id(order_id: str, qty: str | None = None) -> dict:
            fake.placed.append({"replaced": order_id})
            return envelope({"id": order_id, "qty": qty})

        @mcp.tool
        def transfer_funds(amount: str) -> dict:
            """A mutating tool the brake has never heard of; must be refused."""
            fake.placed.append({"transfer": amount})
            return envelope({"id": "xfer-1"})

        return mcp
