"""Stateful fake of Alpaca's MCP server, shaped like the real one.

Tool names, argument names and payload shapes mirror what the live
alpaca-mcp-server (72 tools) returned on 2026-10-01, trust envelope included:
quotes and trades take plural ``symbols`` and come back keyed by symbol, crypto
data needs ``loc``, assets are looked up by ``symbol_or_asset_id``, and list
tools wrap their result as ``{"result": [...]}``.

It keeps an account, positions and orders in memory so a test can assert that
an ALLOW really changed upstream state and a DENY really did not.
"""

from __future__ import annotations

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
        self.fail_quotes = False
        self.one_sided_quotes = False
        self.fail_trades = False
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._n = 0

    def _apply_fill(self, symbol: str, side: str, qty: Decimal) -> None:
        signed = qty if side == "buy" else -qty
        for p in self.positions:
            if p["symbol"] == symbol:
                current = Decimal(p["qty"]) * (1 if p["side"] == "long" else -1)
                new = current + signed
                if new == 0:
                    self.positions.remove(p)
                else:
                    p["qty"] = str(abs(new))
                    p["side"] = "long" if new > 0 else "short"
                return
        self.positions.append({"symbol": symbol, "qty": str(abs(signed)), "side": "long" if signed > 0 else "short"})

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
            return envelope({"result": [dict(p) for p in fake.positions]})

        @mcp.tool
        def get_orders(status: str | None = None, limit: int | None = None) -> dict:
            fake.calls.append(("get_orders", {"status": status}))
            open_states = {"new", "accepted", "partially_filled", "pending_new"}
            rows = [o for o in fake.orders if status != "open" or o["status"] in open_states]
            return envelope({"result": [dict(o) for o in rows]})

        @mcp.tool
        def get_asset(symbol_or_asset_id: str) -> dict:
            fake.calls.append(("get_asset", {"symbol_or_asset_id": symbol_or_asset_id}))
            if symbol_or_asset_id not in fake.assets:
                raise ValueError(f"HTTP error 404: asset not found for {symbol_or_asset_id}")
            return envelope(dict(fake.assets[symbol_or_asset_id]))

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
                out[s] = {"ap": float(ask), "as": 1, "bp": float(bid), "bs": 1, "t": "2026-10-01T13:45:00Z"}
            return envelope({"quotes": out})

        def _trade_payload(symbols: str) -> dict:
            return envelope({"trades": {s: {"p": float(fake.last_trade[s]), "s": 1} for s in symbols.split(",")}})

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
            fake._n += 1
            order = {
                "id": f"ord-{fake._n}",
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
                "order_class": order_class,
                "stop_loss_stop_price": stop_loss_stop_price,
            }
            fake.placed.append(order)
            fake.orders.append(order)
            if type == "market" and fake.is_open:
                filled_qty = Decimal(qty) if qty else Decimal(notional) / Decimal(fake.quotes[symbol][1])
                order["status"] = "filled"
                order["filled_qty"] = str(filled_qty)
                fake._apply_fill(symbol, side, filled_qty)
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
            fake._n += 1
            order = {
                "id": f"ord-{fake._n}", "client_order_id": client_order_id, "symbol": symbol, "side": side,
                "qty": qty, "notional": notional, "type": type, "status": "accepted", "filled_qty": "0",
            }
            fake.placed.append(order)
            fake.orders.append(order)
            return envelope(dict(order))

        @mcp.tool
        def close_position(symbol_or_asset_id: str, qty: str | None = None, percentage: str | None = None) -> dict:
            fake.calls.append(("close_position", {"symbol_or_asset_id": symbol_or_asset_id}))
            fake.positions = [p for p in fake.positions if p["symbol"] != symbol_or_asset_id]
            return envelope({"symbol": symbol_or_asset_id, "status": "closed"})

        @mcp.tool
        def place_option_order(qty: str, symbol: str | None = None, side: str | None = None) -> dict:
            fake.placed.append({"option": True, "symbol": symbol})
            return envelope({"id": "opt-1"})

        @mcp.tool
        def replace_order_by_id(order_id: str, qty: str | None = None) -> dict:
            fake.placed.append({"replaced": order_id})
            return envelope({"id": order_id, "qty": qty})

        return mcp
