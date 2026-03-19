"""Migration utilities from L1/L2 tables to OWM memory tables."""

import json
from datetime import datetime, timezone


def migrate_trades_to_episodic(db) -> int:
    """
    Migrate all trade_records to episodic_memory.

    Mapping:
    - trade id → episodic id
    - market_context JSON → context_json
    - Tries to parse regime/session/atr from market_context JSON, None if missing
    - pnl_r direct copy
    - confidence direct copy or default 0.5
    - retrieval_strength = 1.0

    Uses INSERT OR IGNORE to avoid duplicates on re-run.
    Returns number of rows processed.
    """
    conn = db._get_connection()
    try:
        rows = conn.execute("SELECT * FROM trade_records").fetchall()
        count = 0
        now = datetime.now(timezone.utc).isoformat()

        for row in rows:
            trade = dict(row)

            # Parse market_context JSON
            raw_ctx = trade.get("market_context") or "{}"
            try:
                ctx = json.loads(raw_ctx) if isinstance(raw_ctx, str) else raw_ctx
            except (json.JSONDecodeError, TypeError):
                ctx = {}

            context_json = raw_ctx if isinstance(raw_ctx, str) else json.dumps(raw_ctx)

            # Extract structured fields from context
            regime = ctx.get("regime")
            session = ctx.get("session")
            atr_d1_raw = ctx.get("atr_d1") or ctx.get("atr_daily")
            atr_h1_raw = ctx.get("atr_h1") or ctx.get("atr_hourly")
            atr_d1 = float(atr_d1_raw) if atr_d1_raw is not None else None
            atr_h1 = float(atr_h1_raw) if atr_h1_raw is not None else None

            # entry_price from context (price field) or 0.0
            entry_price = ctx.get("entry_price") or ctx.get("price") or 0.0

            # confidence: direct copy or default 0.5
            confidence = trade.get("confidence")
            if confidence is None:
                confidence = 0.5

            # tags: keep as-is (already JSON string from DB)
            tags = trade.get("tags") or "[]"

            episodic = {
                "id": trade["id"],
                "timestamp": trade["timestamp"],
                "context_json": context_json,
                "context_regime": regime,
                "context_volatility_regime": ctx.get("volatility_regime"),
                "context_session": session,
                "context_atr_d1": atr_d1,
                "context_atr_h1": atr_h1,
                "strategy": trade["strategy"],
                "direction": trade["direction"],
                "entry_price": float(entry_price),
                "lot_size": trade.get("lot_size"),
                "exit_price": trade.get("exit_price"),
                "pnl": trade.get("pnl"),
                "pnl_r": trade.get("pnl_r"),
                "hold_duration_seconds": trade.get("hold_duration"),
                "max_adverse_excursion": None,
                "reflection": trade.get("lessons"),
                "confidence": confidence,
                "tags": tags,
                "retrieval_strength": 1.0,
                "retrieval_count": 0,
                "last_retrieved": None,
                "created_at": now,
            }

            conn.execute(
                """
                INSERT OR IGNORE INTO episodic_memory (
                    id, timestamp, context_json, context_regime,
                    context_volatility_regime, context_session,
                    context_atr_d1, context_atr_h1,
                    strategy, direction, entry_price, lot_size,
                    exit_price, pnl, pnl_r, hold_duration_seconds,
                    max_adverse_excursion, reflection, confidence,
                    tags, retrieval_strength, retrieval_count,
                    last_retrieved, created_at
                ) VALUES (
                    :id, :timestamp, :context_json, :context_regime,
                    :context_volatility_regime, :context_session,
                    :context_atr_d1, :context_atr_h1,
                    :strategy, :direction, :entry_price, :lot_size,
                    :exit_price, :pnl, :pnl_r, :hold_duration_seconds,
                    :max_adverse_excursion, :reflection, :confidence,
                    :tags, :retrieval_strength, :retrieval_count,
                    :last_retrieved, :created_at
                )
            """,
                episodic,
            )
            count += 1

        conn.commit()
        return count
    finally:
        conn.close()


def migrate_patterns_to_semantic(db) -> int:
    """
    Migrate all patterns to semantic_memory.

    Mapping:
    - pattern_id → semantic id
    - description → proposition
    - confidence → alpha/beta via: alpha = 1 + conf * n, beta = 1 + (1 - conf) * n
    - sample_size direct copy
    - metrics JSON → validity_conditions
    - source direct copy

    Uses INSERT OR IGNORE to avoid duplicates on re-run.
    Returns number of rows processed.
    """
    conn = db._get_connection()
    try:
        rows = conn.execute("SELECT * FROM patterns").fetchall()
        count = 0
        now = datetime.now(timezone.utc).isoformat()

        for row in rows:
            pattern = dict(row)

            conf = pattern.get("confidence") or 0.5
            n = pattern.get("sample_size") or 0
            alpha = 1.0 + conf * n
            beta = 1.0 + (1.0 - conf) * n

            semantic = {
                "id": pattern["pattern_id"],
                "proposition": pattern["description"],
                "alpha": alpha,
                "beta": beta,
                "sample_size": n,
                "strategy": pattern.get("strategy"),
                "symbol": pattern.get("symbol"),
                "regime": None,
                "volatility_regime": None,
                "validity_conditions": pattern.get("metrics") or "{}",
                "last_confirmed": None,
                "last_contradicted": None,
                "source": pattern.get("source", "backtest_auto"),
                "retrieval_strength": 1.0,
                "created_at": pattern.get("discovered_at") or now,
                "updated_at": now,
            }

            conn.execute(
                """
                INSERT OR IGNORE INTO semantic_memory (
                    id, proposition, alpha, beta, sample_size,
                    strategy, symbol, regime, volatility_regime,
                    validity_conditions, last_confirmed, last_contradicted,
                    source, retrieval_strength, created_at, updated_at
                ) VALUES (
                    :id, :proposition, :alpha, :beta, :sample_size,
                    :strategy, :symbol, :regime, :volatility_regime,
                    :validity_conditions, :last_confirmed, :last_contradicted,
                    :source, :retrieval_strength, :created_at, :updated_at
                )
            """,
                semantic,
            )
            count += 1

        conn.commit()
        return count
    finally:
        conn.close()


def initialize_affective(db, equity: float = 10000.0) -> bool:
    """
    Create initial affective_state row with given equity.

    Uses INSERT OR IGNORE — safe to call multiple times.
    Returns True on success.
    """
    conn = db._get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT OR IGNORE INTO affective_state (
                id, confidence_level, risk_appetite, momentum_bias,
                peak_equity, current_equity, drawdown_state,
                max_acceptable_drawdown, consecutive_wins,
                consecutive_losses, last_updated, history_json
            ) VALUES (
                'current', 0.5, 1.0, 0.0, ?, ?, 0.0, 0.20, 0, 0, ?, '[]'
            )
        """,
            (equity, equity, now),
        )
        conn.commit()
        return True
    finally:
        conn.close()
