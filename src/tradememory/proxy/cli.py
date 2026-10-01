"""Click commands for the broker proxy: init, seal, run, approve, halt, status, config, doctor.

Imports of mnemox-control happen inside the commands so the base package keeps
working for people who never install the proxy extra.
"""

from __future__ import annotations

import click


@click.group()
def proxy() -> None:
    """Brake + memory in front of a broker MCP server. Needs the [proxy] extra and Python 3.12+."""


def _paths(policy: str | None, state: str | None):
    from pathlib import Path

    from .policy import DEFAULT_POLICY_PATH
    from .state import DEFAULT_STATE_PATH

    return (
        Path(policy) if policy else DEFAULT_POLICY_PATH,
        Path(state) if state else DEFAULT_STATE_PATH,
    )


@proxy.command("init")
@click.option("--account-id", required=True, help="Broker account id the policy binds to (Alpaca: the account 'id').")
@click.option("--symbols", required=True, help="Comma-separated allowed symbols, e.g. AAPL,MSFT,BTC/USD")
@click.option("--owner", default="owner", show_default=True)
@click.option("--broker", default="alpaca", show_default=True)
@click.option("--max-order-notional", default="1000", show_default=True)
@click.option("--max-position-notional", default="5000", show_default=True)
@click.option("--max-daily-loss", default="200", show_default=True)
@click.option("--max-drawdown", default="1000", show_default=True)
@click.option("--approval-notional", default="1000", show_default=True, help="Orders at or above this need owner approval.")
@click.option("--require-stop/--no-require-stop", default=True, show_default=True, help="Entries must carry a bracket stop (stop_loss_stop_price).")
@click.option("--out", default=None, help="Policy path (default ~/.tradememory/policy.json)")
def proxy_init(account_id, symbols, owner, broker, max_order_notional, max_position_notional,
               max_daily_loss, max_drawdown, approval_notional, require_stop, out) -> None:
    """Write a sealed, conservative policy for one broker account."""
    from .policy import policy_to_json, template_policy

    policy_path, _ = _paths(out, None)
    policy = template_policy(
        broker=broker,
        account_id=account_id,
        owner_id=owner,
        allowed_symbols=[s.strip() for s in symbols.split(",") if s.strip()],
        max_order_notional=max_order_notional,
        max_position_notional=max_position_notional,
        max_daily_loss=max_daily_loss,
        max_drawdown=max_drawdown,
        approval_notional=approval_notional,
        require_protective_stop=require_stop,
    )
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(policy_to_json(policy), encoding="utf-8")
    click.echo(f"policy written: {policy_path}\npolicy_hash: {policy.content_hash}")
    click.echo(f"edit it if you like, then: tradememory proxy seal {policy_path}")


@proxy.command("seal")
@click.argument("path")
def proxy_seal(path) -> None:
    """Re-seal a policy file after editing it."""
    from .policy import seal_policy_file

    click.echo(f"policy_hash: {seal_policy_file(path)}")


@proxy.command("run")
@click.option("--policy", default=None)
@click.option("--state", default=None)
@click.option("--env-file", default=None, help="KEY=VALUE file with ALPACA_API_KEY / ALPACA_SECRET_KEY. Passed only to the broker process.")
@click.option("--upstream", default="uvx alpaca-mcp-server", show_default=True, help="Command that starts the broker MCP server.")
@click.option("--agent-id", default="mcp-agent", show_default=True)
@click.option("--live", is_flag=True, help="Use the live account instead of paper. Refused without --i-accept-live-trading.")
@click.option("--i-accept-live-trading", is_flag=True)
def proxy_run(policy, state, env_file, upstream, agent_id, live, i_accept_live_trading) -> None:
    """Run the proxy on stdio: point your MCP client here instead of at the broker."""
    import shlex

    from .server import alpaca_backend, build_proxy, read_env_file

    if live and not i_accept_live_trading:
        raise click.UsageError("--live needs --i-accept-live-trading")
    policy_path, state_path = _paths(policy, state)
    env = read_env_file(env_file) if env_file else {}
    parts = shlex.split(upstream)
    backend = alpaca_backend(env=env, paper=not live, command=parts[0], args=parts[1:])
    server, _ = build_proxy(backend, policy_path=policy_path, state_path=state_path, agent_id=agent_id)
    server.run()


@proxy.command("approve")
@click.argument("intent_id")
@click.option("--state", default=None)
def proxy_approve(intent_id, state) -> None:
    """Approve one escalated intent; the agent then retries with the same client_order_id."""
    from .state import ProxyState

    _, state_path = _paths(None, state)
    ProxyState(state_path).approve(intent_id)
    click.echo(f"approved {intent_id} for 15 minutes")


@proxy.command("halt")
@click.argument("value", type=click.Choice(["NORMAL", "SOFT_HALT", "REDUCE_ONLY", "FULL_HALT"], case_sensitive=False))
@click.option("--state", default=None)
def proxy_halt(value, state) -> None:
    """Set the owner halt: FULL_HALT refuses every new order; exits always pass."""
    from .state import ProxyState

    _, state_path = _paths(None, state)
    ProxyState(state_path).set_halt(value)
    click.echo(f"halt = {value.upper()}")


@proxy.command("status")
@click.option("--policy", default=None)
@click.option("--state", default=None)
def proxy_status(policy, state) -> None:
    """Show the active policy and owner state."""
    from .policy import load_policy
    from .state import ProxyState

    policy_path, state_path = _paths(policy, state)
    p = load_policy(policy_path)
    s = ProxyState(state_path)
    click.echo(
        f"policy {policy_path}\n"
        f"  hash {p.content_hash}\n"
        f"  account {p.broker}/{p.account_id}\n"
        f"  symbols {', '.join(p.allowed_symbols)}\n"
        f"  max order {p.max_order_notional}  max position {p.max_position_notional}\n"
        f"  daily loss {p.max_daily_loss}  drawdown {p.max_drawdown}  approval at {p.approval_notional}\n"
        f"  protective stop required: {p.require_protective_stop}\n"
        f"  expires {p.expires_at.isoformat()}\n"
        f"state {state_path}\n"
        f"  halt {s.halt}"
    )


@proxy.command("config")
@click.option("--policy", default=None)
@click.option("--env-file", default="~/.secrets/alpaca-paper.env", show_default=True)
def proxy_config(policy, env_file) -> None:
    """Print the MCP client config that routes an agent through the brake."""
    import json

    policy_path, _ = _paths(policy, None)
    snippet = {
        "mcpServers": {
            "alpaca-with-brake": {
                "command": "tradememory",
                "args": ["proxy", "run", "--policy", str(policy_path), "--env-file", env_file],
            }
        }
    }
    click.echo(json.dumps(snippet, indent=2))


@proxy.command("doctor")
@click.option("--policy", default=None)
@click.option("--env-file", default=None)
@click.option("--upstream", default="uvx alpaca-mcp-server", show_default=True)
def proxy_doctor(policy, env_file, upstream) -> None:
    """Start the upstream once, check the tools the brake needs, and compare the account id."""
    import asyncio
    import shlex

    from fastmcp import Client

    from . import alpaca
    from .policy import load_policy
    from .server import REQUIRED_UPSTREAM_TOOLS, alpaca_backend, read_env_file

    policy_path, _ = _paths(policy, None)
    p = load_policy(policy_path)
    env = read_env_file(env_file) if env_file else {}
    parts = shlex.split(upstream)

    async def check() -> bool:
        async with Client(alpaca_backend(env=env, paper=True, command=parts[0], args=parts[1:])) as c:
            names = {t.name for t in await c.list_tools()}
            missing = [n for n in REQUIRED_UPSTREAM_TOOLS if n not in names]
            click.echo(f"upstream tools: {len(names)}; missing required: {missing or 'none'}")
            unknown = sorted(n for n in names if alpaca.classify_tool(n) == "unknown")
            new = sorted(names - alpaca.KNOWN_LIVE_TOOLS)
            click.echo(f"tools the brake refuses as unclassified: {unknown or 'none'}")
            click.echo(f"tools not in the list captured on 2026-10-01: {new or 'none'}")
            res = await c.call_tool("get_account_info", {})
            raw = res.structured_content if res.structured_content is not None else res.content
            account = alpaca.unwrap(raw)
            acct = account.get("id") if isinstance(account, dict) else None
            verdict = "MATCH" if acct == p.account_id else "MISMATCH (every order would be refused)"
            click.echo(f"upstream account id: {acct}; policy account id: {p.account_id}; {verdict}")
            return not missing and not unknown and acct == p.account_id

    ok = asyncio.run(check())
    raise SystemExit(0 if ok else 1)
