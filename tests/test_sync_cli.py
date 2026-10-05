"""`tradememory sync hyperliquid|alpaca` end to end, with the venues faked."""

import json
import os
import tempfile

import pytest
from click.testing import CliRunner

from tradememory.cli import cli
from tradememory.db import Database

ADDR = "0x" + "cd" * 20


def _hl(tid, time, side, px, start, sz="1", coin="ETH"):
    return {"tid": tid, "hash": f"h{tid}", "time": time, "side": side, "sz": sz, "px": px, "coin": coin,
            "startPosition": start, "closedPnl": "0", "fee": "0.1", "dir": "Open Long", "feeToken": "USDC",
            "oid": tid}


def test_hyperliquid_sync_stores_and_reports(monkeypatch):
    history = [_hl(1, 1000, "B", "100", "0"), _hl(2, 2000, "A", "90", "1"),
               _hl(3, 3000, "B", "100", "0"), _hl(4, 4000, "A", "112", "1")]
    monkeypatch.setattr("tradememory.sync.hyperliquid.fetch_fills", lambda address: (history, True))
    db_path = os.path.join(tempfile.mkdtemp(), "hl.db")

    out = CliRunner().invoke(cli, ["sync", "hyperliquid", "--address", ADDR, "--db", db_path])
    assert out.exit_code == 0, out.output
    assert "closed trades: 2" in out.output and "stored new: 2" in out.output
    assert "fetch complete: True" in out.output
    assert "Not investment advice" in out.output

    again = CliRunner().invoke(cli, ["sync", "hyperliquid", "--address", ADDR, "--db", db_path, "--json"])
    payload = json.loads(again.output)
    assert payload["summary"]["stored_new"] == 0 and payload["summary"]["already_stored"] == 2


def test_hyperliquid_dry_run_writes_nothing(monkeypatch):
    monkeypatch.setattr("tradememory.sync.hyperliquid.fetch_fills", lambda address: ([], True))
    db_path = os.path.join(tempfile.mkdtemp(), "never.db")
    out = CliRunner().invoke(cli, ["sync", "hyperliquid", "--address", ADDR, "--db", db_path, "--dry-run"])
    assert out.exit_code == 0 and not os.path.exists(db_path)


class FakeAlpaca:
    """Read-only Alpaca REST: account, FILL activities (paged), positions."""

    def __init__(self, activities, positions):
        self.activities, self.positions = activities, positions

    def __call__(self, path, params):
        if path == "/v2/account":
            return {"id": "acct-1"}
        if path == "/v2/positions":
            return self.positions
        assert path == "/v2/account/activities/FILL" and params["direction"] == "asc"
        start = 0
        if "page_token" in params:
            start = next(i for i, a in enumerate(self.activities) if a["id"] == params["page_token"]) + 1
        return self.activities[start:start + params["page_size"]]


def _act(i, side, qty, price, order, symbol="AAPL", minute=0):
    return {"id": f"act{i:04d}", "activity_type": "FILL", "transaction_time": f"2026-10-01T13:{minute:02d}:00Z",
            "side": side, "qty": str(qty), "price": str(price), "symbol": symbol, "order_id": order}


def test_alpaca_sync_gives_the_brake_trade_its_outcome(monkeypatch, tmp_path):
    env = tmp_path / "alpaca.env"
    env.write_text("ALPACA_API_KEY=PKTEST\nALPACA_SECRET_KEY=secret\n", encoding="utf-8")
    db_path = str(tmp_path / "brake.db")
    db = Database(db_path=db_path)
    db.insert_trade({
        "id": "ord-ENTRY1", "timestamp": "2026-10-01T09:30:00+00:00", "symbol": "AAPL", "direction": "long",
        "lot_size": 1.0, "strategy": "agent", "confidence": 0.5, "reasoning": "forwarded by the proxy",
        "market_context": {"entry_price": 329.0, "protective_stop_price": 320.0}, "references": [],
        "exit_timestamp": None, "exit_price": None, "pnl": None, "pnl_r": None, "hold_duration": None,
        "exit_reasoning": None, "slippage": None, "execution_quality": None, "lessons": None,
        "tags": ["proxy"], "grade": None,
    })
    activities = [
        _act(1, "buy", 1, "328.94", "ENTRY1", minute=32), _act(2, "sell", 1, "320.00", "STOPLEG", minute=50),
        # TSLA history began before the activity window: the broker still holds 5 we never saw bought.
        _act(3, "buy", 1, "250", "T1", symbol="TSLA", minute=1), _act(4, "sell", 1, "260", "T2", symbol="TSLA", minute=2),
    ]
    fake = FakeAlpaca(activities, positions=[{"symbol": "TSLA", "qty": "5", "side": "long"}])
    monkeypatch.setattr("tradememory.sync.alpaca.http_get", lambda base, key, secret: fake)

    out = CliRunner().invoke(cli, ["sync", "alpaca", "--env-file", str(env), "--db", db_path, "--json"])
    assert out.exit_code == 0, out.output
    summary = json.loads(out.output)["summary"]
    assert summary["brake_trades_given_outcome"] == 1 and summary["stored_new"] == 0
    assert summary["symbols_left_out_history_incomplete"] == ["TSLA"]
    row = db.get_trade("ord-ENTRY1")
    assert row["exit_price"] == 320.0 and round(row["pnl"], 2) == -8.94
    assert round(row["pnl_r"], 3) == round(-8.94 / 8.94, 3)  # stop 320 vs fill 328.94: lost one R


def test_alpaca_history_too_long_to_page_is_refused_not_cut(monkeypatch):
    from tradememory.sync import alpaca

    monkeypatch.setattr(alpaca, "MAX_PAGES", 2)
    fake = FakeAlpaca([_act(i, "buy", 1, 10, f"o{i}") for i in range(250)], positions=[])
    with pytest.raises(ValueError, match="stopped rather than store part"):
        alpaca.fetch_fill_activities(fake)
    short = FakeAlpaca([_act(i, "buy", 1, 10, f"o{i}") for i in range(150)], positions=[])
    assert len(alpaca.fetch_fill_activities(short)) == 150


def test_alpaca_sync_needs_keys(tmp_path):
    env = tmp_path / "empty.env"
    env.write_text("# nothing here\n", encoding="utf-8")
    out = CliRunner().invoke(cli, ["sync", "alpaca", "--env-file", str(env), "--dry-run"])
    assert out.exit_code != 0 and "ALPACA_API_KEY" in out.output


def _always_suggest(stats, *, source):
    return {"kind": "size_after_losing_streak", "streak": 2, "max_notional": "1500", "action": "escalate",
            "source": source, "evidence": {"history_trades": 9, "median_notional": 1000.0, "trades_after_streak": 6,
                                           "sized_up": 3, "sized_up_share": 0.5, "usual_sized_up_share": 0.2,
                                           "p_value": 0.03, "sized_up_win_rate": 0.0, "sized_up_net_pnl": -90.0}}


def test_a_suggested_rule_is_saved_only_outside_a_dry_run(monkeypatch, tmp_path):
    monkeypatch.setattr("tradememory.sync.hyperliquid.fetch_fills", lambda address: ([], True))
    monkeypatch.setattr("tradememory.rules.suggest.suggest_size_rule", _always_suggest)
    rules = tmp_path / "rules.json"
    db_path = str(tmp_path / "tm.db")
    out = CliRunner().invoke(cli, ["sync", "hyperliquid", "--address", ADDR, "--db", db_path, "--dry-run",
                                   "--rules", str(rules)])
    assert out.exit_code == 0, out.output
    assert "not saved (dry run)" in out.output and not rules.exists()
    out = CliRunner().invoke(cli, ["sync", "hyperliquid", "--address", ADDR, "--db", db_path, "--rules", str(rules)])
    assert out.exit_code == 0, out.output
    assert "tradememory rules approve r-" in out.output
    assert json.loads(rules.read_text(encoding="utf-8"))["rules"][0]["status"] == "proposed"


def test_a_broken_rules_file_is_reported_not_overwritten(monkeypatch, tmp_path):
    monkeypatch.setattr("tradememory.sync.hyperliquid.fetch_fills", lambda address: ([], True))
    monkeypatch.setattr("tradememory.rules.suggest.suggest_size_rule", _always_suggest)
    rules = tmp_path / "rules.json"
    rules.write_text("{broken", encoding="utf-8")
    out = CliRunner().invoke(cli, ["sync", "hyperliquid", "--address", ADDR, "--db", str(tmp_path / "tm.db"),
                                   "--rules", str(rules)])
    assert out.exit_code == 0, out.output
    assert "not saved:" in out.output and rules.read_text(encoding="utf-8") == "{broken"
