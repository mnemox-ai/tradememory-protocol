"""ProxyState on its own: corruption handling, locking, approval binding, TTLs, child environment."""

from __future__ import annotations

import json
import sys
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

pytest.importorskip("mnemox_control")

from tradememory.proxy.server import child_environment  # noqa: E402
from tradememory.proxy.state import ProxyState, StateCorrupt  # noqa: E402

pytestmark = pytest.mark.skipif(sys.version_info < (3, 12), reason="proxy extra needs Python 3.12+")


def write(path, text: str, encoding: str = "utf-8") -> None:
    path.write_bytes(text.encode(encoding))


# --------------------------------------------------------------------------- corruption


@pytest.mark.parametrize(
    "content",
    [
        '{"halt": "FULL_HALT", "trailing": true,}',  # trailing comma
        '{"halt": null}',
        '{"halt": ""}',
        '{"halt": 3}',
        '{"peak_equity": "abc"}',
        '{"peak_equity": "NaN"}',
        '{"approvals": []}',
        "[]",
    ],
)
def test_garbled_file_reads_as_full_halt_and_is_not_overwritten(tmp_path, content):
    path = tmp_path / "state.json"
    write(path, content)
    state = ProxyState(path)
    assert state.halt == "FULL_HALT"
    assert state.corrupt_reason
    with pytest.raises(StateCorrupt):
        state.observe_equity(Decimal("10000"))
    with pytest.raises(StateCorrupt):
        state.forwarded_result("x")
    assert path.read_bytes() == content.encode("utf-8"), "a corrupt file must never be written over"


def test_utf16_file_is_corrupt_not_defaults(tmp_path):
    path = tmp_path / "state.json"
    write(path, '{"halt": "NORMAL"}', encoding="utf-16")
    state = ProxyState(path)
    assert state.halt == "FULL_HALT"


def test_bom_file_is_read_normally(tmp_path):
    path = tmp_path / "state.json"
    write(path, '{"halt": "REDUCE_ONLY", "peak_equity": "12000"}', encoding="utf-8-sig")
    state = ProxyState(path)
    assert state.halt == "REDUCE_ONLY"
    assert state.observe_equity(Decimal("11000")) == Decimal("1000")


def test_owner_can_reset_a_corrupt_file_with_set_halt(tmp_path):
    path = tmp_path / "state.json"
    write(path, "{not json")
    state = ProxyState(path)
    state.set_halt("NORMAL")
    assert state.halt == "NORMAL"
    aside = [p for p in tmp_path.iterdir() if ".corrupt-" in p.name]
    assert len(aside) == 1 and aside[0].read_text(encoding="utf-8") == "{not json"


def test_missing_file_is_plain_defaults(tmp_path):
    state = ProxyState(tmp_path / "nope.json")
    assert state.halt == "NORMAL" and state.corrupt_reason is None
    assert state.observe_equity(Decimal("100")) == Decimal("0")


# --------------------------------------------------------------------------- locking


def test_concurrent_writers_do_not_lose_the_owners_halt(tmp_path):
    path = tmp_path / "state.json"
    proxy_side = ProxyState(path)
    cli_side = ProxyState(path)
    stop = threading.Event()

    def hammer() -> None:
        n = 0
        while not stop.is_set() and n < 150:
            proxy_side.observe_equity(Decimal(10000 + (n % 7)))  # the peak keeps moving, so this writes
            proxy_side.remember_forwarded(f"i{n}", "fp", {"id": n})
            n += 1

    worker = threading.Thread(target=hammer)
    worker.start()
    try:
        for _ in range(50):
            cli_side.set_halt("FULL_HALT")
            assert proxy_side.halt == "FULL_HALT"
            cli_side.set_halt("NORMAL")
    finally:
        stop.set()
        worker.join()
    cli_side.set_halt("FULL_HALT")
    assert ProxyState(path).halt == "FULL_HALT"
    json.loads(path.read_text(encoding="utf-8"))  # always a whole, valid file
    assert not [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]


def test_observe_equity_only_writes_when_the_peak_moves(tmp_path):
    path = tmp_path / "state.json"
    state = ProxyState(path)
    state.observe_equity(Decimal("100"))
    first = path.stat().st_mtime_ns
    state.observe_equity(Decimal("90"))
    assert path.stat().st_mtime_ns == first


# --------------------------------------------------------------------------- approvals


def test_approval_is_bound_to_the_escalated_terms_inside_the_state_module(tmp_path):
    state = ProxyState(tmp_path / "s.json")
    with pytest.raises(ValueError):
        state.approve("X")  # nothing escalated yet
    state.escalate("X", "fp1")
    assert state.approve("X") == "fp1"
    # The agent re-sends different terms under the same intent before the retry.
    state.escalate("X", "fp2")
    assert state.consume_approval("X", "fp2") is False  # the approval was for fp1 and is void now
    state.escalate("X", "fp1")
    assert state.consume_approval("X", "fp1") is False  # voided, not restored
    state.approve("X")
    assert state.consume_approval("X", "fp1") is True
    assert state.consume_approval("X", "fp1") is False  # single use


def test_approval_expires_and_naive_now_is_accepted(tmp_path):
    state = ProxyState(tmp_path / "s.json")
    state.escalate("X", "fp")
    state.approve("X", now=datetime(2026, 10, 1, 12, 0))  # naive, treated as UTC
    assert state.consume_approval("X", "fp", now=datetime(2026, 10, 1, 12, 20, tzinfo=UTC)) is False
    state.escalate("X", "fp")
    state.approve("X", now=datetime(2026, 10, 1, 12, 0, tzinfo=UTC))
    assert state.consume_approval("X", "fp", now=datetime(2026, 10, 1, 12, 10)) is True


def test_stale_escalations_and_forwards_are_pruned(tmp_path):
    state = ProxyState(tmp_path / "s.json")
    old = datetime(2026, 9, 1, tzinfo=UTC)
    state.escalate("old", "fp", now=old)
    state.remember_forwarded("done", "fp", {"id": 1}, now=old)
    state.escalate("new", "fp", now=old + timedelta(days=2))
    snapshot = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert "old" not in snapshot["escalated"] and "done" not in snapshot["forwarded"]
    assert "new" in snapshot["escalated"]


def test_forward_with_unreadable_timestamp_reconciles_instead_of_resending(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"forwarded": {"X": {"at": "garbage", "fingerprint": "fp", "status": "placed", "result": {"id": 1}}}}), encoding="utf-8")
    entry = ProxyState(path).forwarded_result("X")
    assert entry is not None and entry["status"] == "unknown"


# --------------------------------------------------------------------------- child environment


def test_child_environment_is_an_allowlist_plus_keys():
    parent = {
        "PATH": "/usr/bin", "HOME": "/home/u", "https_proxy": "http://p:3128", "UV_INDEX_URL": "https://idx",
        "ALPACA_API_KEY": "from-shell", "AWS_SECRET_ACCESS_KEY": "nope", "OPENAI_API_KEY": "nope",
    }
    env = child_environment(parent, {"ALPACA_SECRET_KEY": "from-file"}, paper=True)
    assert env["PATH"] == "/usr/bin" and env["https_proxy"] == "http://p:3128" and env["UV_INDEX_URL"] == "https://idx"
    assert env["ALPACA_API_KEY"] == "from-shell" and env["ALPACA_SECRET_KEY"] == "from-file"
    assert env["ALPACA_PAPER_TRADE"] == "true"
    assert "AWS_SECRET_ACCESS_KEY" not in env and "OPENAI_API_KEY" not in env
    assert child_environment(parent, {"ALPACA_PAPER_TRADE": "false"}, paper=True)["ALPACA_PAPER_TRADE"] == "true"
