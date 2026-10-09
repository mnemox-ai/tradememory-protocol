"""Tests for replay memory_recall module."""

import json
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tradememory.replay.memory_recall import build_memory_context, query_replay_memories

_SCHEMA = """
CREATE TABLE episodic_memory (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    context_json TEXT NOT NULL,
    context_regime TEXT,
    context_volatility_regime TEXT,
    context_session TEXT,
    context_atr_d1 REAL,
    context_atr_h1 REAL,
    strategy TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    lot_size REAL,
    exit_price REAL,
    pnl REAL,
    pnl_r REAL,
    hold_duration_seconds INTEGER,
    max_adverse_excursion REAL,
    reflection TEXT,
    confidence REAL DEFAULT 0.5,
    tags TEXT,
    retrieval_strength REAL DEFAULT 1.0,
    retrieval_count INTEGER DEFAULT 0,
    last_retrieved TEXT,
    created_at TEXT NOT NULL
);
"""


def _insert(conn, id, strategy="VolBreakout", regime="trending", session="london",
            entry=5100.0, exit_=5150.0, pnl=50.0, pnl_r=1.5,
            reflection="Good entry on breakout", strength=1.0, duration=0):
    conn.execute(
        """INSERT INTO episodic_memory
           (id, timestamp, context_json, context_regime, context_session,
            strategy, direction, entry_price, exit_price, pnl, pnl_r,
            reflection, retrieval_strength, created_at, hold_duration_seconds)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (id, "2026-03-01T10:00:00", "{}", regime, session,
         strategy, "long", entry, exit_, pnl, pnl_r,
         reflection, strength, "2026-03-01T10:00:00", duration),
    )


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "test.db")
        conn = sqlite3.connect(path)
        conn.executescript(_SCHEMA)
        conn.close()
        yield path


class TestEmptyDB:
    def test_returns_empty_string(self, db_path):
        result = build_memory_context(db_path, "VolBreakout", "trending", "london", 150.0)
        assert result == ""


class TestPopulatedDB:
    def test_returns_max_limit(self, db_path):
        conn = sqlite3.connect(db_path)
        for i in range(8):
            _insert(conn, f"E-{i:03d}", strength=float(i))
        conn.commit()
        conn.close()

        result = build_memory_context(db_path, "VolBreakout", "trending", "london", 150.0, limit=5)
        # Header + up to 5 trades (each with reflection line)
        assert "## Similar Past Trades" in result
        assert result.count("[VolBreakout]") == 5

    def test_ordered_by_retrieval_strength(self, db_path):
        conn = sqlite3.connect(db_path)
        _insert(conn, "E-low", pnl=10.0, strength=0.1)
        _insert(conn, "E-high", pnl=99.0, strength=9.0)
        conn.commit()
        conn.close()

        result = build_memory_context(db_path, "VolBreakout", "trending", "london", 150.0)
        assert result.index("pnl=$99.00") < result.index("pnl=$10.00")

    def test_reflection_truncated_at_150(self, db_path):
        long_text = "A" * 300
        conn = sqlite3.connect(db_path)
        _insert(conn, "E-long", reflection=long_text)
        conn.commit()
        conn.close()

        result = build_memory_context(db_path, "VolBreakout", "trending", "london", 150.0)
        # Reflection line should contain at most 150 A's
        assert "A" * 150 in result
        assert "A" * 151 not in result


class TestStrategyFiltering:
    def test_filters_by_strategy(self, db_path):
        conn = sqlite3.connect(db_path)
        _insert(conn, "E-vb", strategy="VolBreakout")
        _insert(conn, "E-im", strategy="IntradayMomentum")
        conn.commit()
        conn.close()

        result = build_memory_context(db_path, "VolBreakout", "trending", "london", 150.0)
        assert "[VolBreakout]" in result
        assert "[IntradayMomentum]" not in result

    def test_filters_by_regime(self, db_path):
        conn = sqlite3.connect(db_path)
        _insert(conn, "E-trend", regime="trending")
        _insert(conn, "E-range", regime="range_bound")
        conn.commit()
        conn.close()

        result = build_memory_context(db_path, "VolBreakout", "trending", "london", 150.0)
        assert result.count("[VolBreakout]") == 1

    def test_filters_by_session(self, db_path):
        conn = sqlite3.connect(db_path)
        _insert(conn, "E-ldn", session="london")
        _insert(conn, "E-asia", session="asian")
        conn.commit()
        conn.close()

        result = build_memory_context(db_path, "VolBreakout", "trending", "london", 150.0)
        assert result.count("[VolBreakout]") == 1

class TestHistoricalEligibility:
    def test_imported_exit_timestamp_does_not_add_duration_twice(self, db_path):
        with closing(sqlite3.connect(db_path)) as conn, conn:
            _insert(conn, "imported")
            conn.execute("UPDATE episodic_memory SET hold_duration_seconds=7200, context_json=?",
                         ('{"entry_time":"2026-03-01T08:00:00Z"}',))
        result = build_memory_context(db_path, as_of=datetime(2026, 3, 1, 10, tzinfo=timezone.utc))
        assert "id=imported" in result
    def test_future_high_rank_cannot_hide_past_before_limit(self, db_path):
        with closing(sqlite3.connect(db_path)) as conn, conn:
            _insert(conn, "past", pnl=-25, strength=.1)
            _insert(conn, "future", pnl=-999, strength=100)
            conn.execute("UPDATE episodic_memory SET timestamp='2030-01-01T00:00:00Z' WHERE id='future'")
        cutoff = datetime(2026, 3, 1, 11, tzinfo=timezone.utc)
        assert "future" in build_memory_context(db_path, limit=1)  # positive fault control
        bounded = build_memory_context(db_path, limit=1, as_of=cutoff)
        assert "id=past" in bounded and "future" not in bounded

    def test_outcome_not_visible_at_entry_and_explicit_available_time(self, db_path):
        with closing(sqlite3.connect(db_path)) as conn, conn:
            _insert(conn, "legacy")
            _insert(conn, "explicit")
            _insert(conn, "open", pnl=None, pnl_r=None, exit_=None)
            conn.execute("UPDATE episodic_memory SET hold_duration_seconds=7200 WHERE id='legacy'")
            conn.execute("UPDATE episodic_memory SET context_json=? WHERE id='explicit'",
                         ('{"available_at":"2026-03-01T13:00:00Z"}',))
        at11 = datetime(2026, 3, 1, 11, tzinfo=timezone.utc)
        assert build_memory_context(db_path, as_of=at11) == ""
        at12 = at11.replace(hour=12)
        assert "id=legacy" in build_memory_context(db_path, as_of=at12)
        assert "id=explicit" not in build_memory_context(db_path, as_of=at12)
        at13 = at11.replace(hour=13)
        assert "id=explicit" in build_memory_context(db_path, as_of=at13)
        assert "id=open" not in build_memory_context(db_path, as_of=at13)

    def test_timezone_and_microsecond_boundaries(self, db_path):
        with closing(sqlite3.connect(db_path)) as conn, conn:
            for mid, stamp in [("past", "2026-03-01T11:00:00+02:00"),
                               ("offset-future", "2026-03-01T09:00:00-02:00"),
                               ("exact", "2026-03-01T10:00:00Z"),
                               ("tiny-future", "2026-03-01T10:00:00.000001Z")]:
                _insert(conn, mid)
                conn.execute("UPDATE episodic_memory SET timestamp=? WHERE id=?", (stamp, mid))
        result = build_memory_context(db_path, as_of=datetime(2026, 3, 1, 10, tzinfo=timezone.utc))
        assert "id=past" in result and "id=exact" in result
        assert "id=offset-future" not in result and "id=tiny-future" not in result

    def test_unknown_outcome_metadata_fails_closed(self, db_path):
        with closing(sqlite3.connect(db_path)) as conn, conn:
            for mid in ["bad-json", "bad-time", "bad-duration", "bad-available"]:
                _insert(conn, mid)
            conn.execute("UPDATE episodic_memory SET context_json='broken' WHERE id='bad-json'")
            conn.execute("UPDATE episodic_memory SET timestamp='broken' WHERE id='bad-time'")
            conn.execute("UPDATE episodic_memory SET hold_duration_seconds=-1 WHERE id='bad-duration'")
            conn.execute("UPDATE episodic_memory SET context_json=? WHERE id='bad-available'",
                         ('{"available_at":"broken"}',))
        assert build_memory_context(db_path, as_of=datetime(2026, 3, 2, tzinfo=timezone.utc)) == ""

    def test_missing_r_preserved_and_db_read_only(self, db_path):
        import hashlib
        with closing(sqlite3.connect(db_path)) as conn, conn:
            _insert(conn, "no-r", pnl=-30, pnl_r=None)
        before = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()
        result = build_memory_context(db_path, as_of=datetime(2026, 3, 2, tzinfo=timezone.utc))
        assert "pnl=$-30.00 pnl_r=unknown" in result
        assert hashlib.sha256(Path(db_path).read_bytes()).hexdigest() == before

    def test_unknown_legacy_duration_cannot_make_outcome_available(self, db_path):
        with closing(sqlite3.connect(db_path)) as conn, conn:
            _insert(conn, "unknown-duration", pnl=-30, duration=None)
        cutoff = datetime(2026, 3, 2, tzinfo=timezone.utc)
        assert query_replay_memories(db_path, as_of=cutoff) == []
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute("UPDATE episodic_memory SET context_json=? WHERE id='unknown-duration'",
                         (json.dumps({"available_at": "2026-03-01T00:00:00Z"}),))
        assert len(query_replay_memories(db_path, as_of=cutoff)) == 1
