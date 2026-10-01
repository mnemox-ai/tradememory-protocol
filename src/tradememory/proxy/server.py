"""Build and run the proxy server: upstream broker MCP behind the brake, plus three memory tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.client.transports import StdioTransport

from ..db import Database
from .brake import BrakeMiddleware
from .policy import DEFAULT_POLICY_PATH, load_policy
from .state import DEFAULT_STATE_PATH, ProxyState

REQUIRED_UPSTREAM_TOOLS = (
    "get_account_info", "get_all_positions", "get_orders", "get_order_by_id",
    "get_order_by_client_id", "get_asset", "get_clock", "get_stock_latest_quote",
    "get_stock_latest_trade", "place_stock_order",
)

# Only what a child process needs to start: the broker keys plus the handful of
# variables Python and uv need to run. Never the proxy's whole environment.
_PASSTHROUGH_ENV = (
    "PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "SYSTEMROOT",
    "COMSPEC", "PATHEXT", "LANG", "LC_ALL", "UV_CACHE_DIR", "XDG_CACHE_HOME", "XDG_DATA_HOME",
    "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
)


def read_env_file(path: Path | str) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def alpaca_backend(
    *,
    env: dict[str, str],
    paper: bool = True,
    command: str = "uvx",
    args: list[str] | None = None,
) -> StdioTransport:
    """Spawn Alpaca's official MCP server as the upstream; keys go only to that process."""
    merged = {name: os.environ[name] for name in _PASSTHROUGH_ENV if name in os.environ}
    merged.update(env)
    merged["ALPACA_PAPER_TRADE"] = "true" if paper else "false"
    return StdioTransport(command=command, args=list(args or ["alpaca-mcp-server"]), env=merged)


def build_proxy(
    backend: Any,
    *,
    policy_path: Path | str = DEFAULT_POLICY_PATH,
    state_path: Path | str = DEFAULT_STATE_PATH,
    db: Database | None = None,
    agent_id: str = "mcp-agent",
    name: str = "tradememory-brake",
) -> tuple[FastMCP, BrakeMiddleware]:
    """Return (server, brake). The server forwards every upstream tool through the brake."""
    policy = load_policy(policy_path)
    database = db or Database()
    proxy = FastMCP.as_proxy(backend, name=name)

    from ..mcp_server import get_agent_state, get_behavioral_analysis, recall_memories, _get_db
    import tradememory.mcp_server as _mcp_module
    _mcp_module._db = database  # the memory tools and the brake share one database

    local_tools = {"recall_memories", "get_behavioral_analysis", "get_agent_state", "brake_status"}
    brake = BrakeMiddleware(
        policy=policy, state=ProxyState(state_path), db=database, agent_id=agent_id,
        recall=recall_memories, local_tools=local_tools,
    )
    proxy.add_middleware(brake)

    proxy.tool(recall_memories)
    proxy.tool(get_behavioral_analysis)
    proxy.tool(get_agent_state)

    @proxy.tool
    def brake_status() -> dict[str, Any]:
        """What the brake in front of this broker will and will not let through."""
        return {
            "policy_hash": policy.content_hash,
            "policy_id": str(policy.policy_id),
            "account_id": policy.account_id,
            "broker": policy.broker,
            "allowed_symbols": list(policy.allowed_symbols),
            "max_order_notional": str(policy.max_order_notional),
            "max_position_notional": str(policy.max_position_notional),
            "max_daily_loss": str(policy.max_daily_loss),
            "max_drawdown": str(policy.max_drawdown),
            "approval_notional": str(policy.approval_notional),
            "require_protective_stop": policy.require_protective_stop,
            "halt": brake.state.halt,
            "expires_at": policy.expires_at.isoformat(),
            "last_decision": brake.last_decision,
            "note": "orders need a client_order_id to be retried safely or approved after ESCALATE",
        }

    return proxy, brake
