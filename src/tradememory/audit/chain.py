"""Audit chain — linked-list of TDR content hashes with daily Merkle roots.

Design
------
- Each TDR has a content hash H_c (TradingDecisionRecord.compute_hash).
- The audit chain stores `chained_hash = SHA256(prev_chained_hash || H_c)`
  per record, plus a deterministic sequence number.
- The genesis record has `prev_hash = '0' * 64`.
- Daily Merkle roots are computed over the chained_hashes of all records
  whose UTC date falls in [period_start, period_end). Roots themselves
  form a secondary chain via `prev_root_hash`.

Tamper semantics
----------------
- Modifying any historical TDR (content) breaks H_c for that record AND
  every subsequent chained_hash.
- Modifying the chained_hash directly without re-linking forwards is
  detected by `verify_chain`.
- Modifying a daily root requires forging SHA-256 collisions for every
  record in that day (Merkle tree property).

Forwards-compat
---------------
- `tsa_token BLOB` column on audit_roots reserved for RFC 3161
  TimeStampToken (Phase 1.5).
- `data_hash` on audit_chain is the chained_hash, NOT the content_hash —
  the content_hash lives on the TDR (via compute_hash).
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .merkle import merkle_root


GENESIS_HASH = "0" * 64
ZERO_HASH = "0" * 64  # alias, used for empty-day roots


def chained_hash(prev_hash: str, content_hash: str) -> str:
    """Compute SHA256(prev_hash || content_hash) — link the chain forward.

    Both inputs are hex strings; output is also a hex string. Inputs are
    lower-cased for stability across producers.
    """
    payload = (prev_hash.lower() + content_hash.lower()).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class AuditChainEntry:
    """One record in the audit_chain table."""

    record_id: str
    sequence_num: int
    content_hash: str
    prev_hash: str
    data_hash: str  # = chained_hash(prev_hash, content_hash)
    chained_at: str  # UTC ISO-8601


@dataclass(frozen=True)
class DailyRoot:
    """One row in the audit_roots table."""

    period_start: str  # UTC ISO-8601 (YYYY-MM-DDT00:00:00+00:00)
    period_end: str    # exclusive upper bound
    root_hash: str
    prev_root_hash: str
    record_count: int
    first_sequence: Optional[int]
    last_sequence: Optional[int]
    generated_at: str


class ChainBuilder:
    """Append-and-verify operations against a SQLite-backed audit chain.

    Callers must supply a sqlite3.Connection. The class assumes the
    `audit_chain` and `audit_roots` tables already exist (created by
    Database._init_schema).
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ------------------------------------------------------------------
    # Append
    # ------------------------------------------------------------------

    def _latest_entry(self) -> Optional[AuditChainEntry]:
        row = self.conn.execute(
            "SELECT record_id, sequence_num, content_hash, prev_hash, "
            "data_hash, chained_at FROM audit_chain "
            "ORDER BY sequence_num DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return AuditChainEntry(*row)

    def append(self, record_id: str, content_hash: str) -> AuditChainEntry:
        """Append a new content_hash to the chain. Returns the new entry.

        Idempotent on record_id — if a row already exists for the same
        record_id with the SAME content_hash, returns the existing entry
        unchanged. If content_hash differs, raises ValueError (tampering
        prevention at append time).
        """
        existing = self.conn.execute(
            "SELECT record_id, sequence_num, content_hash, prev_hash, "
            "data_hash, chained_at FROM audit_chain WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if existing:
            entry = AuditChainEntry(*existing)
            if entry.content_hash != content_hash:
                raise ValueError(
                    f"record_id {record_id!r} already chained with a "
                    f"different content_hash; refusing to overwrite "
                    f"(stored={entry.content_hash[:12]}..., "
                    f"new={content_hash[:12]}...)"
                )
            return entry

        latest = self._latest_entry()
        prev_hash = latest.data_hash if latest else GENESIS_HASH
        seq = (latest.sequence_num + 1) if latest else 1
        data_hash = chained_hash(prev_hash, content_hash)
        chained_at = datetime.now(timezone.utc).isoformat()

        self.conn.execute(
            "INSERT INTO audit_chain "
            "(record_id, sequence_num, content_hash, prev_hash, "
            "data_hash, chained_at) VALUES (?, ?, ?, ?, ?, ?)",
            (record_id, seq, content_hash, prev_hash, data_hash, chained_at),
        )
        return AuditChainEntry(
            record_id=record_id,
            sequence_num=seq,
            content_hash=content_hash,
            prev_hash=prev_hash,
            data_hash=data_hash,
            chained_at=chained_at,
        )

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def get_entry(self, record_id: str) -> Optional[AuditChainEntry]:
        row = self.conn.execute(
            "SELECT record_id, sequence_num, content_hash, prev_hash, "
            "data_hash, chained_at FROM audit_chain WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        return AuditChainEntry(*row) if row else None

    def verify_chain(
        self,
        from_seq: Optional[int] = None,
        to_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Walk the chain and confirm every link is intact.

        Returns a dict with:
          - verified (bool)
          - checked_count (int)
          - first_break_at (Optional[int]) — sequence_num of first broken link
          - reason (Optional[str]) — human-readable cause of break
        """
        query = (
            "SELECT record_id, sequence_num, content_hash, prev_hash, "
            "data_hash, chained_at FROM audit_chain"
        )
        params: List[Any] = []
        conds: List[str] = []
        if from_seq is not None:
            conds.append("sequence_num >= ?")
            params.append(from_seq)
        if to_seq is not None:
            conds.append("sequence_num <= ?")
            params.append(to_seq)
        if conds:
            query += " WHERE " + " AND ".join(conds)
        query += " ORDER BY sequence_num ASC"

        rows = self.conn.execute(query, params).fetchall()
        if not rows:
            return {
                "verified": True,
                "checked_count": 0,
                "first_break_at": None,
                "reason": None,
            }

        # When verifying a slice that doesn't start at genesis, the slice's
        # prev_hash must equal the data_hash of the record immediately before.
        first_entry = AuditChainEntry(*rows[0])
        if first_entry.sequence_num == 1:
            expected_prev = GENESIS_HASH
        else:
            anchor = self.conn.execute(
                "SELECT data_hash FROM audit_chain WHERE sequence_num = ?",
                (first_entry.sequence_num - 1,),
            ).fetchone()
            if not anchor:
                return {
                    "verified": False,
                    "checked_count": 0,
                    "first_break_at": first_entry.sequence_num,
                    "reason": "missing predecessor sequence_num",
                }
            expected_prev = anchor["data_hash"] if isinstance(
                anchor, sqlite3.Row
            ) else anchor[0]

        checked = 0
        for row in rows:
            entry = AuditChainEntry(*row)
            if entry.prev_hash != expected_prev:
                return {
                    "verified": False,
                    "checked_count": checked,
                    "first_break_at": entry.sequence_num,
                    "reason": "prev_hash mismatch",
                }
            expected_dh = chained_hash(entry.prev_hash, entry.content_hash)
            if entry.data_hash != expected_dh:
                return {
                    "verified": False,
                    "checked_count": checked,
                    "first_break_at": entry.sequence_num,
                    "reason": "data_hash mismatch",
                }
            expected_prev = entry.data_hash
            checked += 1

        return {
            "verified": True,
            "checked_count": checked,
            "first_break_at": None,
            "reason": None,
        }

    # ------------------------------------------------------------------
    # Daily Merkle root
    # ------------------------------------------------------------------

    @staticmethod
    def _utc_day_bounds(date_str: str) -> Tuple[str, str]:
        """Given YYYY-MM-DD, return (start_iso, end_iso) UTC exclusive end."""
        # Parse loosely — accept full ISO or date-only.
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(date_str + "T00:00:00+00:00")
        dt = dt.astimezone(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start = dt.isoformat()
        end = dt.replace(
            day=dt.day  # avoid timedelta to keep semantics explicit; +1 day:
        )
        # Use timedelta for the +1 day boundary (cleaner than month math).
        from datetime import timedelta

        end_dt = dt + timedelta(days=1)
        return start, end_dt.isoformat()

    def _previous_root(self, period_start: str) -> Optional[DailyRoot]:
        row = self.conn.execute(
            "SELECT period_start, period_end, root_hash, prev_root_hash, "
            "record_count, first_sequence, last_sequence, generated_at "
            "FROM audit_roots WHERE period_start < ? "
            "ORDER BY period_start DESC LIMIT 1",
            (period_start,),
        ).fetchone()
        return DailyRoot(*row) if row else None

    def build_daily_root(
        self, date_str: str, request_tsa: Optional[bool] = None
    ) -> DailyRoot:
        """Build (or rebuild) the Merkle root for a single UTC date.

        Returns the DailyRoot. If a root already exists for this date, it is
        overwritten with the recomputed value (use for backfill / repair).

        `request_tsa=None` (the default) follows the TRADEMEMORY_TSA env
        setting — ON unless set to off — so freshly built roots get an
        RFC 3161 TimeStampToken from the configured TSA (default
        freetsa.org), stored as a BLOB in `audit_roots.tsa_token`. Pass an
        explicit False for bulk/backfill paths. TSA failures are logged but
        do NOT abort the root build — timestamping is an additive
        attestation layer, not a precondition for the chain.
        """
        if request_tsa is None:
            from .tsa import tsa_enabled_by_default

            request_tsa = tsa_enabled_by_default()

        period_start, period_end = self._utc_day_bounds(date_str)

        rows = self.conn.execute(
            "SELECT data_hash, sequence_num FROM audit_chain "
            "WHERE chained_at >= ? AND chained_at < ? "
            "ORDER BY sequence_num ASC",
            (period_start, period_end),
        ).fetchall()

        leaves: List[str] = [r["data_hash"] for r in rows] if rows else []
        root_hash = merkle_root(leaves) if leaves else ZERO_HASH
        first_seq = rows[0]["sequence_num"] if rows else None
        last_seq = rows[-1]["sequence_num"] if rows else None

        prev_root = self._previous_root(period_start)
        prev_root_hash = prev_root.root_hash if prev_root else ZERO_HASH
        generated_at = datetime.now(timezone.utc).isoformat()

        # Optional TSA attestation. Failures are non-fatal.
        tsa_token: Optional[bytes] = None
        if request_tsa and leaves:
            try:
                from .tsa import TSAError, request_timestamp

                resp = request_timestamp(root_hash)
                tsa_token = resp.response_der
            except Exception as e:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).warning(
                    "TSA timestamping failed for %s root %s: %s",
                    period_start, root_hash[:16], e,
                )

        self.conn.execute(
            "INSERT OR REPLACE INTO audit_roots "
            "(period_start, period_end, root_hash, prev_root_hash, "
            "record_count, first_sequence, last_sequence, generated_at, "
            "tsa_token) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                period_start, period_end, root_hash, prev_root_hash,
                len(leaves), first_seq, last_seq, generated_at, tsa_token,
            ),
        )

        return DailyRoot(
            period_start=period_start,
            period_end=period_end,
            root_hash=root_hash,
            prev_root_hash=prev_root_hash,
            record_count=len(leaves),
            first_sequence=first_seq,
            last_sequence=last_seq,
            generated_at=generated_at,
        )

    def verify_daily_root(self, date_str: str) -> Dict[str, Any]:
        """Recompute the Merkle root for a date and compare to stored."""
        period_start, period_end = self._utc_day_bounds(date_str)
        stored = self.conn.execute(
            "SELECT root_hash, record_count FROM audit_roots "
            "WHERE period_start = ?",
            (period_start,),
        ).fetchone()
        if not stored:
            return {
                "verified": False,
                "reason": "no root stored for date",
                "stored_root": None,
                "recomputed_root": None,
            }

        rows = self.conn.execute(
            "SELECT data_hash FROM audit_chain "
            "WHERE chained_at >= ? AND chained_at < ? "
            "ORDER BY sequence_num ASC",
            (period_start, period_end),
        ).fetchall()
        leaves = [r["data_hash"] for r in rows] if rows else []
        recomputed = merkle_root(leaves) if leaves else ZERO_HASH

        return {
            "verified": stored["root_hash"] == recomputed,
            "stored_root": stored["root_hash"],
            "recomputed_root": recomputed,
            "record_count": stored["record_count"],
            "leaf_count": len(leaves),
        }

    # ------------------------------------------------------------------
    # Backfill
    # ------------------------------------------------------------------

    def backfill(
        self,
        trade_iter: Iterable[Tuple[str, str, str]],
    ) -> Dict[str, int]:
        """Backfill the chain from an iterator of (record_id, content_hash, chained_at).

        The iterator MUST yield records in the desired chain order
        (typically ORDER BY timestamp ASC, id ASC). Existing audit_chain
        rows are wiped before backfill — this is a destructive rebuild
        and should only be called when the entire chain is being recomputed.
        """
        self.conn.execute("DELETE FROM audit_chain")
        self.conn.execute("DELETE FROM audit_roots")

        appended = 0
        prev_hash = GENESIS_HASH
        seq = 1
        days_touched: set[str] = set()

        for record_id, content_hash, chained_at in trade_iter:
            data_hash = chained_hash(prev_hash, content_hash)
            self.conn.execute(
                "INSERT INTO audit_chain "
                "(record_id, sequence_num, content_hash, prev_hash, "
                "data_hash, chained_at) VALUES (?, ?, ?, ?, ?, ?)",
                (record_id, seq, content_hash, prev_hash, data_hash, chained_at),
            )
            prev_hash = data_hash
            seq += 1
            appended += 1
            # Track which UTC day this record lives on for root rebuild.
            try:
                day = datetime.fromisoformat(
                    chained_at.replace("Z", "+00:00")
                ).astimezone(timezone.utc).strftime("%Y-%m-%d")
                days_touched.add(day)
            except Exception:
                pass

        # Rebuild Merkle roots for every touched day in ascending order.
        # Explicit request_tsa=False: backfill can touch many days and must
        # not hammer the TSA; timestamp fresh roots via the daily path.
        roots_built = 0
        for day in sorted(days_touched):
            self.build_daily_root(day, request_tsa=False)
            roots_built += 1

        return {"records": appended, "roots": roots_built}
