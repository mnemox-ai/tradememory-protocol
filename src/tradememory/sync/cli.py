"""`tradememory sync ...`: pull a venue's fill history into memory."""

from __future__ import annotations

import json
import os
from typing import Any

import click


def _read_env_file(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    with open(os.path.expanduser(path), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _emit(summary: dict[str, Any], report: str, as_json: bool, stats: dict[str, Any]) -> None:
    if as_json:
        click.echo(json.dumps({"summary": summary, "patterns": stats}, indent=2, default=str))
        return
    for key, value in summary.items():
        click.echo(f"{key.replace('_', ' ')}: {value}")
    click.echo("")
    click.echo(report)


@click.group()
def sync() -> None:
    """Pull a venue's fill history into TradeMemory (read-only on the venue)."""


@sync.command("hyperliquid")
@click.option("--address", required=True, help="The account's public address (0x...). No key is needed.")
@click.option("--db", "db_path", default=None, help="SQLite file to store into (default: TradeMemory's usual database).")
@click.option("--dry-run", is_flag=True, help="Fetch and report only; store nothing.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def sync_hyperliquid(address: str, db_path: str | None, dry_run: bool, as_json: bool) -> None:
    """Rebuild an address's Hyperliquid perp trades and store them in memory.

    Hyperliquid serves only an address's recent fills, so older history is
    gone; re-running stores only new trades.
    """
    from .fills import build_round_trips
    from .hyperliquid import fetch_fills, perp_fills
    from .report import loss_patterns, render_report

    try:
        raw, complete = fetch_fills(address)
        fills, spot = perp_fills(raw, address)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    built = build_round_trips(fills)
    summary: dict[str, Any] = {
        "fills_fetched": len(raw),
        "fetch_complete": complete,
        "spot_fills_skipped": spot,
        "closed_trades": len(built.trips),
        "open_positions": {k: str(v) for k, v in built.open_positions.items()},
        "trades_dropped_for_missing_history": built.dropped,
    }
    unpriced = sum(1 for f in fills if not f.fee_known)
    if unpriced:
        summary["fills_with_fee_in_another_token_not_netted"] = unpriced
    if not dry_run:
        from ..db import Database
        from .store import store_round_trips

        result = store_round_trips(Database(db_path), built.trips, venue="Hyperliquid", strategy="hyperliquid")
        summary["stored_new"] = len(result.stored)
        summary["already_stored"] = result.skipped
        if result.repaired:
            summary["finished_after_an_interrupted_run"] = len(result.repaired)
    stats = loss_patterns(built.trips)
    _emit(summary, render_report(stats, title=f"Hyperliquid {address[:6]}...{address[-4:]}"), as_json, stats)


@sync.command("alpaca")
@click.option("--env-file", default="~/.secrets/alpaca-paper.env", show_default=True,
              help="KEY=VALUE file with ALPACA_API_KEY and ALPACA_SECRET_KEY.")
@click.option("--db", "db_path", default=None,
              help="SQLite file the broker brake writes to, so its trades get their outcome.")
@click.option("--live", is_flag=True, help="Read the live account instead of paper. Read-only either way.")
@click.option("--dry-run", is_flag=True, help="Fetch and report only; store nothing.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def sync_alpaca(env_file: str, db_path: str | None, live: bool, dry_run: bool, as_json: bool) -> None:
    """Rebuild the account's trades from its fills and fill in the brake's outcomes."""
    from .alpaca import (
        LIVE_URL,
        PAPER_URL,
        fetch_fill_activities,
        fetch_positions,
        http_get,
        to_fill,
    )
    from .fills import build_round_trips
    from .report import loss_patterns, render_report

    env = _read_env_file(env_file)
    key_id = env.get("ALPACA_API_KEY") or env.get("APCA_API_KEY_ID")
    secret = env.get("ALPACA_SECRET_KEY") or env.get("APCA_API_SECRET_KEY")
    if not (key_id and secret):
        raise click.ClickException(f"{env_file} needs ALPACA_API_KEY and ALPACA_SECRET_KEY")
    get = http_get(LIVE_URL if live else PAPER_URL, key_id, secret)

    account = str(get("/v2/account", {})["id"])
    try:
        built = build_round_trips([to_fill(a, account) for a in fetch_fill_activities(get)])
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    broker = fetch_positions(get)
    mismatched = sorted(
        s for s in set(built.open_positions) | set(broker)
        if built.open_positions.get(s, 0) != broker.get(s, 0)
    )
    trips = [t for t in built.trips if t.symbol not in mismatched]
    summary: dict[str, Any] = {
        "account": "live" if live else "paper",
        "closed_trades": len(trips),
        "open_positions": {k: str(v) for k, v in built.open_positions.items()},
        "symbols_left_out_history_incomplete": mismatched,
    }
    if not dry_run:
        from ..db import Database
        from .store import store_round_trips

        db = Database(db_path)

        def link(trip):
            # The brake records a forwarded entry as "ord-<broker order id>".
            return db.get_trade(f"ord-{trip.order_ids[0]}") if trip.order_ids else None

        result = store_round_trips(db, trips, venue="Alpaca", strategy="alpaca", link=link)
        summary["brake_trades_given_outcome"] = len(result.linked)
        summary["stored_new"] = len(result.stored)
        summary["already_stored"] = result.skipped
        if result.repaired:
            summary["finished_after_an_interrupted_run"] = len(result.repaired)
    stats = loss_patterns(trips)
    _emit(summary, render_report(stats, title=f"Alpaca {'live' if live else 'paper'} account"), as_json, stats)
