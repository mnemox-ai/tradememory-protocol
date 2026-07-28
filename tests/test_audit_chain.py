"""Tests for tradememory.audit — chain + Merkle root.

Covers:
  - chained_hash determinism + tamper sensitivity
  - merkle_root edge cases (empty, single, even, odd)
  - ChainBuilder.append (sequence numbering, idempotency, tamper guard)
  - ChainBuilder.verify_chain (intact + broken cases)
  - ChainBuilder.build_daily_root / verify_daily_root
  - End-to-end backfill from a populated trade_records table
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone

import pytest

from tradememory.audit.chain import (
    GENESIS_HASH,
    ChainBuilder,
    chained_hash,
)
from tradememory.audit.merkle import merkle_root
from tradememory.db import Database


# ---------------------------------------------------------------------------
# chained_hash
# ---------------------------------------------------------------------------

def test_chained_hash_is_deterministic():
    p, c = "a" * 64, "b" * 64
    assert chained_hash(p, c) == chained_hash(p, c)


def test_chained_hash_case_insensitive_inputs():
    upper = chained_hash("A" * 64, "B" * 64)
    lower = chained_hash("a" * 64, "b" * 64)
    assert upper == lower


def test_chained_hash_changes_with_either_input():
    base = chained_hash("0" * 64, "1" * 64)
    assert chained_hash("0" * 64, "2" * 64) != base
    assert chained_hash("1" * 64, "1" * 64) != base


def test_chained_hash_matches_manual_sha256():
    p = "00" * 32
    c = "11" * 32
    manual = hashlib.sha256((p + c).encode("ascii")).hexdigest()
    assert chained_hash(p, c) == manual


# ---------------------------------------------------------------------------
# merkle_root
# ---------------------------------------------------------------------------

def test_merkle_root_empty_is_zero_hash():
    assert merkle_root([]) == "0" * 64


def test_merkle_root_single_leaf_is_leaf():
    leaf = "ab" * 32
    assert merkle_root([leaf]) == leaf


def test_merkle_root_two_leaves():
    a, b = "00" * 32, "11" * 32
    expected = hashlib.sha256(bytes.fromhex(a) + bytes.fromhex(b)).hexdigest()
    assert merkle_root([a, b]) == expected


def test_merkle_root_three_leaves_duplicates_last():
    # Bitcoin rule: odd level duplicates last leaf.
    a, b, c = "00" * 32, "11" * 32, "22" * 32
    ab = hashlib.sha256(bytes.fromhex(a) + bytes.fromhex(b)).hexdigest()
    cc = hashlib.sha256(bytes.fromhex(c) + bytes.fromhex(c)).hexdigest()
    expected = hashlib.sha256(bytes.fromhex(ab) + bytes.fromhex(cc)).hexdigest()
    assert merkle_root([a, b, c]) == expected


def test_merkle_root_changes_when_any_leaf_changes():
    leaves = ["00" * 32, "11" * 32, "22" * 32, "33" * 32]
    root = merkle_root(leaves)
    leaves[2] = "ff" * 32
    assert merkle_root(leaves) != root


# ---------------------------------------------------------------------------
# ChainBuilder — append / verify
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Fresh Database in a tmp dir."""
    return Database(str(tmp_path / "tm.db"))


def _builder(db) -> ChainBuilder:
    """Return a ChainBuilder on a fresh connection."""
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    return ChainBuilder(conn)


def test_append_genesis_uses_zero_prev(db):
    cb = _builder(db)
    entry = cb.append("t1", "c1" * 32)
    assert entry.sequence_num == 1
    assert entry.prev_hash == GENESIS_HASH
    assert entry.data_hash == chained_hash(GENESIS_HASH, "c1" * 32)
    cb.conn.commit()


def test_append_chains_forward(db):
    cb = _builder(db)
    e1 = cb.append("t1", "c1" * 32)
    e2 = cb.append("t2", "c2" * 32)
    assert e2.sequence_num == 2
    assert e2.prev_hash == e1.data_hash
    assert e2.data_hash == chained_hash(e1.data_hash, "c2" * 32)
    cb.conn.commit()


def test_append_is_idempotent_on_same_content(db):
    cb = _builder(db)
    e1 = cb.append("t1", "c1" * 32)
    e1_again = cb.append("t1", "c1" * 32)
    assert e1.data_hash == e1_again.data_hash
    assert e1.sequence_num == e1_again.sequence_num
    cb.conn.commit()


def test_append_rejects_content_mismatch_on_same_record(db):
    cb = _builder(db)
    cb.append("t1", "c1" * 32)
    with pytest.raises(ValueError):
        cb.append("t1", "ff" * 32)
    cb.conn.commit()


def test_verify_chain_clean(db):
    cb = _builder(db)
    for i in range(5):
        cb.append(f"t{i}", f"{i:02d}" * 32)
    cb.conn.commit()
    res = cb.verify_chain()
    assert res["verified"] is True
    assert res["checked_count"] == 5
    assert res["first_break_at"] is None


def test_verify_chain_detects_content_tampering(db):
    cb = _builder(db)
    for i in range(5):
        cb.append(f"t{i}", f"{i:02d}" * 32)
    cb.conn.commit()

    # Tamper: overwrite content_hash on record 3 without re-linking.
    cb.conn.execute(
        "UPDATE audit_chain SET content_hash = ? WHERE sequence_num = 3",
        ("ff" * 32,),
    )
    cb.conn.commit()

    res = cb.verify_chain()
    assert res["verified"] is False
    assert res["first_break_at"] == 3
    assert res["reason"] == "data_hash mismatch"


def test_verify_chain_detects_prev_hash_tampering(db):
    cb = _builder(db)
    for i in range(3):
        cb.append(f"t{i}", f"{i:02d}" * 32)
    cb.conn.commit()

    cb.conn.execute(
        "UPDATE audit_chain SET prev_hash = ? WHERE sequence_num = 2",
        ("ff" * 32,),
    )
    cb.conn.commit()

    res = cb.verify_chain()
    assert res["verified"] is False
    assert res["first_break_at"] == 2


def test_verify_chain_slice(db):
    cb = _builder(db)
    for i in range(5):
        cb.append(f"t{i}", f"{i:02d}" * 32)
    cb.conn.commit()
    res = cb.verify_chain(from_seq=3, to_seq=5)
    assert res["verified"] is True
    assert res["checked_count"] == 3


# ---------------------------------------------------------------------------
# Daily Merkle roots
# ---------------------------------------------------------------------------

def test_build_daily_root_uses_merkle_over_data_hashes(db):
    """Manually insert entries with controlled chained_at, verify root."""
    cb = _builder(db)
    # Three records on the same day.
    day = "2026-05-14"
    leaves = []
    prev = GENESIS_HASH
    for i in range(3):
        content = f"{i:02d}" * 32
        dh = chained_hash(prev, content)
        cb.conn.execute(
            "INSERT INTO audit_chain (record_id, sequence_num, content_hash, "
            "prev_hash, data_hash, chained_at) VALUES (?, ?, ?, ?, ?, ?)",
            (f"t{i}", i + 1, content, prev, dh, f"{day}T0{i}:00:00+00:00"),
        )
        leaves.append(dh)
        prev = dh
    cb.conn.commit()

    root = cb.build_daily_root(day)
    assert root.record_count == 3
    assert root.first_sequence == 1
    assert root.last_sequence == 3
    assert root.root_hash == merkle_root(leaves)
    assert root.prev_root_hash == "0" * 64  # no prior days
    cb.conn.commit()


def test_verify_daily_root_detects_tampering(db):
    cb = _builder(db)
    day = "2026-05-14"
    prev = GENESIS_HASH
    for i in range(3):
        content = f"{i:02d}" * 32
        dh = chained_hash(prev, content)
        cb.conn.execute(
            "INSERT INTO audit_chain (record_id, sequence_num, content_hash, "
            "prev_hash, data_hash, chained_at) VALUES (?, ?, ?, ?, ?, ?)",
            (f"t{i}", i + 1, content, prev, dh, f"{day}T0{i}:00:00+00:00"),
        )
        prev = dh
    cb.build_daily_root(day)
    cb.conn.commit()

    # Tamper a record's data_hash.
    cb.conn.execute(
        "UPDATE audit_chain SET data_hash = ? WHERE sequence_num = 2",
        ("ff" * 32,),
    )
    cb.conn.commit()

    res = cb.verify_daily_root(day)
    assert res["verified"] is False
    assert res["stored_root"] != res["recomputed_root"]


def test_daily_roots_chain_by_prev_root(db):
    cb = _builder(db)
    # Day 1
    cb.conn.execute(
        "INSERT INTO audit_chain (record_id, sequence_num, content_hash, "
        "prev_hash, data_hash, chained_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("a", 1, "00" * 32, GENESIS_HASH,
         chained_hash(GENESIS_HASH, "00" * 32), "2026-05-13T12:00:00+00:00"),
    )
    cb.conn.commit()
    r1 = cb.build_daily_root("2026-05-13")
    cb.conn.commit()

    # Day 2
    cb.conn.execute(
        "INSERT INTO audit_chain (record_id, sequence_num, content_hash, "
        "prev_hash, data_hash, chained_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("b", 2, "11" * 32, r1.root_hash,
         chained_hash(r1.root_hash, "11" * 32), "2026-05-14T12:00:00+00:00"),
    )
    cb.conn.commit()
    r2 = cb.build_daily_root("2026-05-14")
    cb.conn.commit()

    assert r2.prev_root_hash == r1.root_hash
    assert r2.record_count == 1


# ---------------------------------------------------------------------------
# Insert hook — Database.insert_trade auto-appends to chain
# ---------------------------------------------------------------------------

def _sample_trade(trade_id: str, ts: str, direction: str = "long") -> dict:
    return {
        "id": trade_id,
        "timestamp": ts,
        "symbol": "XAUUSD",
        "direction": direction,
        "lot_size": 0.01,
        "strategy": "VolBreakout",
        "confidence": 0.7,
        "reasoning": "test",
        "market_context": {"session": "ASIA"},
        "references": [],
        "exit_timestamp": None,
        "exit_price": None,
        "pnl": None,
        "pnl_r": None,
        "hold_duration": None,
        "exit_reasoning": None,
        "slippage": None,
        "execution_quality": None,
        "lessons": None,
        "tags": [],
        "grade": None,
    }


def test_insert_trade_appends_to_chain(db):
    db.insert_trade(_sample_trade("T-1", "2026-05-14T01:00:00+00:00"))
    db.insert_trade(_sample_trade("T-2", "2026-05-14T02:00:00+00:00"))

    cb = _builder(db)
    res = cb.verify_chain()
    assert res["verified"] is True
    assert res["checked_count"] == 2

    e1 = cb.get_entry("T-1")
    e2 = cb.get_entry("T-2")
    assert e1.sequence_num == 1
    assert e1.prev_hash == GENESIS_HASH
    assert e2.sequence_num == 2
    assert e2.prev_hash == e1.data_hash


def test_insert_trade_duplicate_id_skips_chain(db):
    db.insert_trade(_sample_trade("T-1", "2026-05-14T01:00:00+00:00"))
    # Re-insert same id — should be ignored, chain not double-appended.
    db.insert_trade(_sample_trade("T-1", "2026-05-14T01:00:00+00:00"))

    cb = _builder(db)
    rows = cb.conn.execute(
        "SELECT COUNT(*) AS n FROM audit_chain"
    ).fetchone()
    assert rows["n"] == 1


# ---------------------------------------------------------------------------
# End-to-end backfill
# ---------------------------------------------------------------------------

def test_backfill_rebuilds_chain_from_trade_records(db):
    # Seed three trades; the insert_trade hook will already chain them.
    db.insert_trade(_sample_trade("T-1", "2026-05-13T10:00:00+00:00"))
    db.insert_trade(_sample_trade("T-2", "2026-05-13T11:00:00+00:00"))
    db.insert_trade(_sample_trade("T-3", "2026-05-14T09:00:00+00:00"))

    # Reconstruct iterator the way the backfill script does it.
    def _trade_iter():
        from tradememory.domain.tdr import TradingDecisionRecord
        import json as _json
        with db.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, symbol, direction, strategy, confidence, "
                "reasoning, market_context FROM trade_records "
                "ORDER BY timestamp ASC, id ASC"
            ).fetchall()
        for row in rows:
            mc = row["market_context"]
            if isinstance(mc, str):
                mc = _json.loads(mc)
            yield (
                row["id"],
                TradingDecisionRecord.compute_hash(
                    trade_id=row["id"],
                    timestamp=row["timestamp"],
                    symbol=row["symbol"],
                    direction=row["direction"],
                    strategy=row["strategy"],
                    confidence=row["confidence"],
                    reasoning=row["reasoning"],
                    market_context=mc,
                ),
                row["timestamp"],
            )

    cb = _builder(db)
    summary = cb.backfill(_trade_iter())
    cb.conn.commit()
    assert summary["records"] == 3
    assert summary["roots"] == 2  # two distinct UTC days

    verify = cb.verify_chain()
    assert verify["verified"] is True
    assert verify["checked_count"] == 3

    # Each day's root should also verify.
    for day in ("2026-05-13", "2026-05-14"):
        assert cb.verify_daily_root(day)["verified"] is True


# ---------------------------------------------------------------------------
# Bounds helper
# ---------------------------------------------------------------------------

def test_utc_day_bounds_date_only():
    start, end = ChainBuilder._utc_day_bounds("2026-05-14")
    assert start == "2026-05-14T00:00:00+00:00"
    assert end == "2026-05-15T00:00:00+00:00"


def test_utc_day_bounds_with_timestamp():
    start, _ = ChainBuilder._utc_day_bounds("2026-05-14T15:30:00+00:00")
    assert start == "2026-05-14T00:00:00+00:00"


# ---------------------------------------------------------------------------
# TSA token preservation on rebuild
# ---------------------------------------------------------------------------

def _seed_day(cb, day, n):
    prev = GENESIS_HASH
    for i in range(n):
        content = f"{i:02d}" * 32
        dh = chained_hash(prev, content)
        cb.conn.execute(
            "INSERT INTO audit_chain (record_id, sequence_num, content_hash, "
            "prev_hash, data_hash, chained_at) VALUES (?, ?, ?, ?, ?, ?)",
            (f"tok{i}", i + 1, content, prev, dh, f"{day}T0{i}:00:00+00:00"),
        )
        prev = dh
    cb.conn.commit()
    return prev


def test_rebuild_preserves_token_when_root_unchanged(db):
    """Rebuilding an identical root must never destroy an existing anchor."""
    cb = _builder(db)
    day = "2026-05-14"
    _seed_day(cb, day, 3)
    root1 = cb.build_daily_root(day, request_tsa=False)
    cb.conn.execute(
        "UPDATE audit_roots SET tsa_token = ? WHERE period_start = ?",
        (b"fake-tst", root1.period_start),
    )
    cb.conn.commit()

    root2 = cb.build_daily_root(day, request_tsa=False)
    assert root2.root_hash == root1.root_hash
    row = cb.conn.execute(
        "SELECT tsa_token FROM audit_roots WHERE period_start = ?",
        (root1.period_start,),
    ).fetchone()
    assert row["tsa_token"] == b"fake-tst"


def test_rebuild_drops_token_when_root_changed(db):
    """If the recomputed root differs, the old token no longer proves it."""
    cb = _builder(db)
    day = "2026-05-14"
    prev = _seed_day(cb, day, 3)
    root1 = cb.build_daily_root(day, request_tsa=False)
    cb.conn.execute(
        "UPDATE audit_roots SET tsa_token = ? WHERE period_start = ?",
        (b"fake-tst", root1.period_start),
    )
    # Append a fourth record inside the same day — root will change.
    content = "ff" * 32
    dh = chained_hash(prev, content)
    cb.conn.execute(
        "INSERT INTO audit_chain (record_id, sequence_num, content_hash, "
        "prev_hash, data_hash, chained_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("tok3", 4, content, prev, dh, f"{day}T09:00:00+00:00"),
    )
    cb.conn.commit()

    root2 = cb.build_daily_root(day, request_tsa=False)
    assert root2.root_hash != root1.root_hash
    row = cb.conn.execute(
        "SELECT tsa_token FROM audit_roots WHERE period_start = ?",
        (root1.period_start,),
    ).fetchone()
    assert row["tsa_token"] is None
