"""Fault controls for independent arms, future exclusion and the response judge."""
import hashlib
import importlib.util
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

from test_replay_memory_recall import _SCHEMA, _insert


@pytest.fixture
def probe(tmp_path, monkeypatch):
    path = Path(__file__).parents[1]/"research/memory_decision_probe/run_probe.py"
    spec = importlib.util.spec_from_file_location("tested_memory_probe", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "CACHE", tmp_path)
    with closing(sqlite3.connect(tmp_path/"seed.db")) as conn, conn:
        conn.executescript(_SCHEMA)
        for i in range(3):
            _insert(conn, f"past-{i}", pnl=-10*(i+1), pnl_r=None)
            conn.execute("UPDATE episodic_memory SET context_json=? WHERE id=?",
                         (json.dumps({"symbol": "CONTROL", "notional": 100}), f"past-{i}"))
        _insert(conn, "future", pnl=-987654, strength=100)
        conn.execute("UPDATE episodic_memory SET timestamp='2030-01-01T00:00:00Z' WHERE id='future'")
    return module


def test_arm_mutation_cannot_change_seed_or_other_arm(probe, tmp_path):
    original = hashlib.sha256((tmp_path/"seed.db").read_bytes()).hexdigest()
    a = probe.make_arm(tmp_path/"runs", "no_history", 0)
    b = probe.make_arm(tmp_path/"runs", "raw_csv", 0)
    with closing(sqlite3.connect(a/"memory.db")) as conn, conn:
        conn.execute("UPDATE episodic_memory SET pnl=999 WHERE id='past-0'")
    with closing(sqlite3.connect(b/"memory.db")) as conn:
        assert conn.execute("SELECT pnl FROM episodic_memory WHERE id='past-0'").fetchone()[0] == -10
    assert hashlib.sha256((tmp_path/"seed.db").read_bytes()).hexdigest() == original
    with pytest.raises(FileExistsError):
        probe.make_arm(tmp_path/"runs", "no_history", 0)


@pytest.mark.parametrize("arm", ["no_history", "raw_csv", "tradememory", "wrong_pnl"])
def test_every_prompt_excludes_future_even_negative_control(probe, tmp_path, arm):
    folder = probe.make_arm(tmp_path/"runs", arm, 0)
    before = probe.sha(folder/"memory.db")
    case = {"as_of": "2026-03-02T00:00:00+00:00", "proposal_notional": 200,
            "eligible_ids": [f"past-{i}" for i in range(3)]}
    system, user = probe.prompt_for(case, arm, folder/"memory.db")
    assert "987654" not in user and "id=future" not in user
    assert probe.sha(folder/"memory.db") == before
    assert "Never execute orders" in system


def test_judge_rejects_invented_evidence_and_all_insufficient(probe):
    case = {"eligible_ids": ["a", "b", "c"],
            "oracle": {"assessment": "warn", "last3_net_pnl": "-60", "evidence_ids": ["a", "b", "c"]}}
    good = probe.grade(case, probe.Answer(assessment="warn", last3_net_pnl=-60, evidence_ids=["a", "b", "c"]))
    assert good["correct_assessment"] and good["correct_last3_pnl"] and good["correct_evidence_ids"]
    fake = probe.grade(case, probe.Answer(assessment="allow", last3_net_pnl=-60, evidence_ids=["a", "b", "future"]))
    assert fake["missed_warn"] and not fake["correct_evidence_ids"] and fake["invented_or_future_ids"] == ["future"]
    nothing = probe.grade(case, probe.Answer(assessment="insufficient", last3_net_pnl=None, evidence_ids=[]))
    assert nothing["insufficient"] and not nothing["correct_assessment"] and not nothing["correct_last3_pnl"]


def test_native_windows_cli_runs_without_batch_shell(probe, tmp_path, monkeypatch):
    wrapper = tmp_path/"claude.CMD"
    native = tmp_path/"node_modules/@anthropic-ai/claude-code/bin/claude.exe"
    native.parent.mkdir(parents=True)
    native.touch()
    monkeypatch.setattr(probe.shutil, "which", lambda name: str(wrapper) if name == "claude" else None)
    assert probe.cli_command() == [str(native)]


def test_auth_only_calibration_never_reads_trade_history(probe, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Authentication-only check accessed trade history")
    monkeypatch.setattr(probe, "check_inputs", forbidden)
    monkeypatch.setattr(probe, "prompt_for", forbidden)
    calls = []
    def failed_call(system, prompt, model, receipt):
        calls.append(prompt)
        raise RuntimeError("OAuth session expired")
    monkeypatch.setattr(probe, "call_claude", failed_call)
    output = tmp_path/"auth-only"
    with pytest.raises(RuntimeError, match="OAuth"):
        probe.calibrate(output, None)
    result = json.loads((output/"results.json").read_text())
    assert calls == ["No history supplied."]
    assert result["trade_rows_sent"] == 0 and result["status"] == "blocked_model"


def test_invalid_first_answer_is_preserved_and_stops_comparison(probe, tmp_path, monkeypatch):
    case = {"id": "control", "as_of": "2026-03-02T00:00:00+00:00", "proposal_notional": 200,
            "eligible_ids": [f"past-{i}" for i in range(3)]}
    probe.write(tmp_path/"cases.json", [case])
    monkeypatch.setattr(probe, "check_inputs", lambda: {"test_control": True})
    calls = []
    def call(system, prompt, model, receipt):
        calls.append(prompt)
        if len(calls) == 1:
            return probe.Answer(assessment="insufficient", last3_net_pnl=None, evidence_ids=[]), {"model": "test-only"}
        raise ValueError("Invalid JSON response")
    monkeypatch.setattr(probe, "call_claude", call)
    output = tmp_path/"failed-first-answer"
    with pytest.raises(ValueError, match="Invalid JSON"):
        probe.run(output, None, False)
    result = json.loads((output/"results.json").read_text())
    assert len(calls) == 2 and result["status"] == "incomplete"
    assert len(result["records"]) == 1
    assert result["records"][0]["status"] == "model_error"
    assert "answer" not in result["records"][0] and "grade" not in result["records"][0]
