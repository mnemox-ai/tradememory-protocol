"""Stateful fake of Alpaca's MCP server, shaped like the real tool results (trust envelope included).

It keeps an account, positions and orders in memory so a test can assert that
an ALLOW really changed upstream state and a DENY really did not.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastmcp import FastMCP


def envelope(data: Any) -> dict[str, Any]:
    return {
        "_alpaca_mcp_security": {"trust": "api_structured", "warning": "fake upstream"},
        "data": data,
    }


class FakeAlpaca:
    def __init__(self) -> None:
        self.account: dict[str, Any] = {
            "id": "acct-1",
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
        }
        self.assets: dict[str, dict[str, Any]] = {
            s: {"id": f"asset-{s}", "symbol": s, "tradable": True, "shortable": True, "fractionable": True}
            for s in self.quotes
        }
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
            return envelope([dict(p) for p in fake.positions])

        @mcp.tool
        def get_orders(status: str = "open") -> dict:
            fake.calls.append(("get_orders", {"status": status}))
            open_states = {"new", "accepted", "partially_filled", "pending_new"}
            rows = [o for o in fake.orders if status != "open" or o["status"] in open_states]
            return envelope([dict(o) for o in rows])

        @mcp.tool
        def get_asset(symbol: str) -> dict:
            fake.calls.append(("get_asset", {"symbol": symbol}))
            if symbol not in fake.assets:
                raise ValueError(f"asset {symbol} not found")
            return envelope(dict(fake.assets[symbol]))

        @mcp.tool
        def get_stock_latest_quote(symbol: str) -> dict:
            fake.calls.append(("get_stock_latest_quote", {"symbol": symbol}))
            if fake.fail_quotes:
                raise RuntimeError("quote feed down")
            bid, ask = fake.quotes[symbol]
            if fake.one_sided_quotes:
                bid = "0"
            return envelope({"symbol": symbol, "quote": {"bp": bid, "ap": ask, "bs": 1, "as": 1}})

        @mcp.tool
        def get_stock_latest_trade(symbol: str) -> dict:
            fake.calls.append(("get_stock_latest_trade", {"symbol": symbol}))
            if fake.fail_trades:
                raise RuntimeError("trade feed down")
            _, ask = fake.quotes[symbol]
            return envelope({"symbol": symbol, "trade": {"p": ask, "s": 1}})

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
            if type == "market":
                filled_qty = Decimal(qty) if qty else Decimal(notional) / Decimal(fake.quotes[symbol][1])
                order["status"] = "filled"
                order["filled_qty"] = str(filled_qty)
                fake._apply_fill(symbol, side, filled_qty)
            return envelope(dict(order))

        @mcp.tool
        def close_position(symbol: str) -> dict:
            fake.calls.append(("close_position", {"symbol": symbol}))
            fake.positions = [p for p in fake.positions if p["symbol"] != symbol]
            return envelope({"symbol": symbol, "status": "closed"})

        @mcp.tool
        def place_option_order(qty: str, symbol: str | None = None, side: str | None = None) -> dict:
            fake.placed.append({"option": True, "symbol": symbol})
            return envelope({"id": "opt-1"})

        @mcp.tool
        def replace_order_by_id(order_id: str, qty: str | None = None) -> dict:
            fake.placed.append({"replaced": order_id})
            return envelope({"id": order_id, "qty": qty})

        return mcp
