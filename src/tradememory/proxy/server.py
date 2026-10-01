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

# Only what a child process needs to start: the broker keys plus the variables
# Python, uv and the network stack need. Never the proxy's whole environment.
_PASSTHROUGH_ENV = frozenset(
    name.upper()
    for name in (
        "PATH", "HOME", "USERPROFILE", "USERNAME", "USER", "LOGNAME", "SHELL", "TERM",
        "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "TMPDIR", "SYSTEMROOT", "SYSTEMDRIVE",
        "HOMEDRIVE", "HOMEPATH", "COMSPEC", "PATHEXT", "PROCESSOR_ARCHITECTURE",
        "LANG", "LC_ALL", "LC_CTYPE", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
        "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY",
    )
)
_UV_PASSTHROUGH = frozenset(
    {
        "UV_CACHE_DIR", "UV_TOOL_DIR", "UV_TOOL_BIN_DIR", "UV_PYTHON", "UV_PYTHON_INSTALL_DIR",
        "UV_PYTHON_PREFERENCE", "UV_PYTHON_DOWNLOADS", "UV_INDEX", "UV_INDEX_URL", "UV_DEFAULT_INDEX",
        "UV_EXTRA_INDEX_URL", "UV_NATIVE_TLS", "UV_SYSTEM_CERTS", "UV_OFFLINE", "UV_NO_PROGRESS",
        "UV_LINK_MODE", "UV_HTTP_TIMEOUT", "UV_CONCURRENT_DOWNLOADS", "UV_NO_CACHE",
    }
)
KEY_NAMES = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")


def child_environment(parent: dict[str, str], env: dict[str, str], *, paper: bool) -> dict[str, str]:
    """Environment for the broker process.

    Allowlisted parent variables (never publish tokens or unrelated secrets),
    then the env file, then the paper flag. Broker keys come from the env file;
    the parent shell's ALPACA_* variables are used only when no env file was
    given at all, so a typo in the file cannot silently fall back to the
    shell's (possibly live) account.
    """
    merged = {
        name: value
        for name, value in parent.items()
        if name.upper() in _PASSTHROUGH_ENV or name.upper() in _UV_PASSTHROUGH
    }
    if env:
        missing = [k for k in KEY_NAMES if not env.get(k)]
        if missing:
            raise ValueError(f"the env file must define {' and '.join(KEY_NAMES)}; missing {missing}")
    else:
        for name, value in parent.items():
            if name.upper().startswith("ALPACA_"):
                merged[name.upper()] = value
    merged.update(env)
    merged["ALPACA_PAPER_TRADE"] = "true" if paper else "false"
    return merged


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
    merged = child_environment(dict(os.environ), env, paper=paper)
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
            "state_corrupt_reason": brake.state.corrupt_reason,
            "expires_at": policy.expires_at.isoformat(),
            "last_decision": brake.last_decision,
            "note": "orders need a client_order_id to be retried safely or approved after ESCALATE",
        }

    return proxy, brake
