"""Read-only replay recall over an immutable snapshot, with outcome eligibility."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from tradememory.owm.recall import as_utc


def _available_at(stamp, context_json, duration):
    """Canonical UTC with microseconds; unknown metadata fails closed."""
    try:
        entry = as_utc(stamp)
        context = json.loads(context_json)
        if not isinstance(context, dict) or (duration is not None and duration < 0):
            return None
        start = as_utc(context.get("entry_time") or stamp)
        if context.get("available_at"):
            available = as_utc(context["available_at"])
        elif duration is not None:
            available = start + timedelta(seconds=duration)
        elif context.get("entry_time"):
            available = entry  # native import timestamp is the known exit
        else:
            return None  # legacy entry with unknown duration is not an exit time
        return max(entry, available).isoformat(timespec="microseconds")
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def query_replay_memories(
    db_path: str,
    strategy: Optional[str] = None,
    regime: Optional[str] = None,
    session: Optional[str] = None,
    *,
    as_of: Optional[datetime] = None,
    symbol: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    """Filter BEFORE limiting. Legacy replay entries add the hold duration.

    Explicit context_json.available_at overrides that legacy convention.
    Imported fills carry entry_time while timestamp is the already-known exit.
    Invalid/missing SQL times and open outcomes are excluded in historical mode.
    A snapshot freezes metadata; this does not undo later reflections/updates.
    """
    conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.create_function("replay_available_at", 3, _available_at, deterministic=True)
    try:
        conditions, params = [], []
        for column, value in [("strategy", strategy), ("context_regime", regime), ("context_session", session)]:
            if value is not None:
                conditions.append(f"{column} = ?")
                params.append(value)
        if symbol is not None:
            conditions.append("CASE WHEN json_valid(context_json) THEN json_extract(context_json, '$.symbol') END = ?")
            params.append(symbol)
        if as_of is not None:
            cutoff = as_utc(as_of).isoformat(timespec="microseconds")
            conditions.extend([
                "pnl IS NOT NULL AND exit_price IS NOT NULL",
                "replay_available_at(timestamp, context_json, hold_duration_seconds) <= ?",
            ])
            params.append(cutoff)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT *, replay_available_at(timestamp, context_json, hold_duration_seconds) AS available_at FROM episodic_memory {where} ORDER BY retrieval_strength DESC, id ASC"
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be non-negative")
            sql += " LIMIT ?"
            params.append(limit)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def format_memory_context(rows: list[dict]) -> str:
    """One formatter for simple and hybrid recall; missing R stays unknown."""
    if not rows:
        return ""
    def number(value):
        return "unknown" if value is None else f"{value:.2f}"
    lines = ["## Similar Past Trades"]
    for i, row in enumerate(rows, 1):
        try:
            context = json.loads(row.get("context_json") or "{}")
        except (ValueError, TypeError):
            context = {}
        if not isinstance(context, dict):
            context = {}
        lines.append(
            f"{i}. [{row['strategy']}] id={row['id']} time={row['timestamp']} "
            f"symbol={context.get('symbol', 'unknown')} notional={number(context.get('notional'))} "
            f"entry={number(row['entry_price'])} exit={number(row['exit_price'])} "
            f"size={number(row.get('lot_size'))} pnl=${number(row['pnl'])} pnl_r={number(row['pnl_r'])}"
        )
        if row.get("reflection"):
            lines.append(f"   Reflection: {row['reflection'][:150]}")
    return "\n".join(lines)


def build_memory_context(
    db_path: str,
    strategy: Optional[str] = None,
    regime: Optional[str] = None,
    session: Optional[str] = None,
    atr_d1: float = 0.0,
    limit: int = 5,
    *,
    as_of: Optional[datetime] = None,
    symbol: Optional[str] = None,
) -> str:
    """Existing strength-ordered recall, now optionally bounded by decision time."""
    return format_memory_context(query_replay_memories(
        db_path, strategy, regime, session, as_of=as_of, symbol=symbol, limit=limit,
    ))


def recall_replay_memories(
    db_path: str,
    strategy: Optional[str] = None,
    regime: Optional[str] = None,
    session: Optional[str] = None,
    atr_d1: float = 0.0,
    limit: int = 5,
    *,
    as_of: datetime,
    symbol: Optional[str] = None,
    order: str = "losses_first",
) -> list[dict]:
    """Adapter to existing hybrid_recall; no new ranking or embeddings."""
    from tradememory.hybrid_recall import hybrid_recall
    from tradememory.owm.context import ContextVector

    rows = query_replay_memories(db_path, strategy, regime, session, as_of=as_of, symbol=symbol)
    candidates = []
    for row in rows:
        context = json.loads(row["context_json"])
        candidates.append({**row, "memory_type": "episodic",
                           "context": {**context, "regime": row["context_regime"],
                                       "session": row["context_session"], "atr_d1": row["context_atr_d1"]}})
    query = ContextVector(symbol=symbol or "", regime=regime or "", session=session or "", atr_d1=atr_d1)
    ranked = hybrid_recall(query, None, candidates, limit=limit, order=order, as_of=as_of)
    return [r.data for r in ranked]


def build_hybrid_memory_context(
    db_path: str, strategy: Optional[str] = None, regime: Optional[str] = None,
    session: Optional[str] = None, atr_d1: float = 0.0, limit: int = 5, *,
    as_of: datetime, symbol: Optional[str] = None, order: str = "losses_first",
) -> str:
    return format_memory_context(recall_replay_memories(
        db_path, strategy, regime, session, atr_d1, limit, as_of=as_of, symbol=symbol, order=order,
    ))
