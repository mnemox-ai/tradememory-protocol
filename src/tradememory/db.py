"""
SQLite database operations for TradeMemory Protocol.
Single file database, no ORM (per CIO directive).
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager"""

    def __init__(self, db_path: str = "data/tradememory.db"):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dicts
        return conn

    def _init_schema(self):
        """Initialize database schema"""
        conn = self._get_connection()
        try:
            # Trade records table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_records (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    lot_size REAL NOT NULL,
                    strategy TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reasoning TEXT NOT NULL,
                    market_context TEXT NOT NULL,
                    trade_references TEXT NOT NULL,
                    exit_timestamp TEXT,
                    exit_price REAL,
                    pnl REAL,
                    pnl_r REAL,
                    hold_duration INTEGER,
                    exit_reasoning TEXT,
                    slippage REAL,
                    execution_quality REAL,
                    lessons TEXT,
                    tags TEXT,
                    grade TEXT
                )
            """)

            # Session state table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_state (
                    agent_id TEXT PRIMARY KEY,
                    last_active TEXT NOT NULL,
                    warm_memory TEXT NOT NULL,
                    active_positions TEXT NOT NULL,
                    risk_constraints TEXT NOT NULL
                )
            """)

            # Indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON trade_records(timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_strategy
                ON trade_records(strategy)
            """)

            # Patterns table (L2 layer)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    pattern_id TEXT PRIMARY KEY,
                    pattern_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    sample_size INTEGER NOT NULL,
                    date_range TEXT NOT NULL,
                    strategy TEXT,
                    symbol TEXT,
                    metrics TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'backtest_auto',
                    validation_status TEXT NOT NULL DEFAULT 'IN_SAMPLE',
                    discovered_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_patterns_strategy_symbol
                ON patterns(strategy, symbol)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_patterns_type
                ON patterns(pattern_type)
            """)

            # Strategy adjustments table (L3 layer)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_adjustments (
                    adjustment_id TEXT PRIMARY KEY,
                    adjustment_type TEXT NOT NULL,
                    parameter TEXT NOT NULL,
                    old_value TEXT NOT NULL,
                    new_value TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source_pattern_id TEXT,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'proposed',
                    created_at TEXT NOT NULL,
                    applied_at TEXT,
                    FOREIGN KEY (source_pattern_id) REFERENCES patterns(pattern_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_adjustments_status
                ON strategy_adjustments(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_adjustments_type
                ON strategy_adjustments(adjustment_type)
            """)

            # ========== OWM Tables ==========

            # Episodic Memory (Section 2.1)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memory (
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
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_regime
                ON episodic_memory(context_regime)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_strategy
                ON episodic_memory(strategy)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_timestamp
                ON episodic_memory(timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_pnl_r
                ON episodic_memory(pnl_r)
            """)

            # Semantic Memory (Section 2.2 — confidence/uncertainty computed in Python)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_memory (
                    id TEXT PRIMARY KEY,
                    proposition TEXT NOT NULL,
                    alpha REAL NOT NULL DEFAULT 1.0,
                    beta REAL NOT NULL DEFAULT 1.0,
                    sample_size INTEGER NOT NULL DEFAULT 0,
                    strategy TEXT,
                    symbol TEXT,
                    regime TEXT,
                    volatility_regime TEXT,
                    validity_conditions TEXT,
                    last_confirmed TEXT,
                    last_contradicted TEXT,
                    source TEXT NOT NULL,
                    retrieval_strength REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Procedural Memory (Section 2.3)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS procedural_memory (
                    id TEXT PRIMARY KEY,
                    strategy TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    behavior_type TEXT NOT NULL,
                    sample_size INTEGER NOT NULL DEFAULT 0,
                    avg_hold_winners REAL,
                    avg_hold_losers REAL,
                    disposition_ratio REAL,
                    actual_lot_mean REAL,
                    actual_lot_variance REAL,
                    kelly_fraction_suggested REAL,
                    lot_vs_kelly_ratio REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Affective State (Section 2.4 — single row, no GENERATED ALWAYS)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS affective_state (
                    id TEXT PRIMARY KEY,
                    confidence_level REAL NOT NULL DEFAULT 0.5,
                    risk_appetite REAL NOT NULL DEFAULT 1.0,
                    momentum_bias REAL NOT NULL DEFAULT 0.0,
                    peak_equity REAL NOT NULL,
                    current_equity REAL NOT NULL,
                    drawdown_state REAL NOT NULL DEFAULT 0.0,
                    max_acceptable_drawdown REAL NOT NULL DEFAULT 0.20,
                    consecutive_wins INTEGER NOT NULL DEFAULT 0,
                    consecutive_losses INTEGER NOT NULL DEFAULT 0,
                    last_updated TEXT NOT NULL,
                    history_json TEXT DEFAULT '[]'
                )
            """)

            # Prospective Memory (Section 2.5)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prospective_memory (
                    id TEXT PRIMARY KEY,
                    trigger_type TEXT NOT NULL,
                    trigger_condition TEXT NOT NULL,
                    planned_action TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    priority REAL NOT NULL DEFAULT 0.5,
                    expiry TEXT,
                    source_episodic_ids TEXT,
                    source_semantic_ids TEXT,
                    reasoning TEXT NOT NULL,
                    triggered_at TEXT,
                    outcome_pnl_r REAL,
                    outcome_reflection TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_prospective_status
                ON prospective_memory(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_prospective_trigger
                ON prospective_memory(trigger_type)
            """)

            # Recall event logging (for MCP recall analytics)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recall_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    query_symbol TEXT,
                    query_context TEXT,
                    query_regime TEXT,
                    num_candidates INTEGER DEFAULT 0,
                    num_returned INTEGER DEFAULT 0,
                    avg_score REAL DEFAULT 0.0
                )
            """)

            conn.commit()
        finally:
            conn.close()

    def insert_trade(self, trade_data: Dict[str, Any]) -> bool:
        """
        Insert a trade record.

        Args:
            trade_data: Trade record dictionary

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            # Convert datetime objects to ISO strings
            if isinstance(trade_data.get('timestamp'), datetime):
                trade_data['timestamp'] = trade_data['timestamp'].isoformat()
            if isinstance(trade_data.get('exit_timestamp'), datetime):
                trade_data['exit_timestamp'] = trade_data['exit_timestamp'].isoformat()

            # Serialize JSON fields
            trade_data['market_context'] = json.dumps(trade_data.get('market_context', {}))
            trade_data['trade_references'] = json.dumps(trade_data.get('references', []))
            trade_data['tags'] = json.dumps(trade_data.get('tags', []))

            conn.execute("""
                INSERT OR IGNORE INTO trade_records VALUES (
                    :id, :timestamp, :symbol, :direction, :lot_size, :strategy,
                    :confidence, :reasoning, :market_context, :trade_references,
                    :exit_timestamp, :exit_price, :pnl, :pnl_r, :hold_duration,
                    :exit_reasoning, :slippage, :execution_quality, :lessons,
                    :tags, :grade
                )
            """, trade_data)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting trade: {e}")
            return False
        finally:
            conn.close()

    def update_trade_outcome(self, trade_id: str, outcome_data: Dict[str, Any]) -> bool:
        """
        Update trade with exit outcome.

        Args:
            trade_id: Trade ID
            outcome_data: Exit data (exit_price, pnl, etc.)

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            # Convert datetime if present
            if isinstance(outcome_data.get('exit_timestamp'), datetime):
                outcome_data['exit_timestamp'] = outcome_data['exit_timestamp'].isoformat()

            # Build UPDATE query
            fields = []
            for key in ['exit_timestamp', 'exit_price', 'pnl', 'pnl_r',
                        'hold_duration', 'exit_reasoning', 'slippage',
                        'execution_quality', 'lessons', 'grade']:
                if key in outcome_data:
                    fields.append(f"{key} = :{key}")

            if not fields:
                return False

            query = f"UPDATE trade_records SET {', '.join(fields)} WHERE id = :id"  # nosec B608 — fields from internal whitelist
            outcome_data['id'] = trade_id

            conn.execute(query, outcome_data)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating trade outcome: {e}")
            return False
        finally:
            conn.close()

    def get_trade(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a trade record by ID.

        Args:
            trade_id: Trade ID

        Returns:
            Trade record dict or None
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM trade_records WHERE id = ?",
                (trade_id,)
            ).fetchone()

            if not row:
                return None

            # Convert to dict and deserialize JSON fields
            trade = dict(row)
            trade['market_context'] = json.loads(trade['market_context'])
            trade['references'] = json.loads(trade['trade_references'])
            del trade['trade_references']  # Remove DB column name
            trade['tags'] = json.loads(trade['tags'])

            return trade
        finally:
            conn.close()

    def query_trades(
        self,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query trade records with filters.

        Args:
            strategy: Filter by strategy
            symbol: Filter by symbol
            limit: Maximum number of results

        Returns:
            List of trade records
        """
        conn = self._get_connection()
        try:
            query = "SELECT * FROM trade_records WHERE 1=1"
            params: list[Any] = []

            if strategy:
                query += " AND strategy = ?"
                params.append(strategy)
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()

            trades = []
            for row in rows:
                trade = dict(row)
                trade['market_context'] = json.loads(trade['market_context'])
                trade['references'] = json.loads(trade['trade_references'])
                del trade['trade_references']  # Remove DB column name
                trade['tags'] = json.loads(trade['tags'])
                trades.append(trade)

            return trades
        finally:
            conn.close()

    def save_session_state(self, state_data: Dict[str, Any]) -> bool:
        """
        Save agent session state.

        Args:
            state_data: Session state dictionary

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            if isinstance(state_data.get('last_active'), datetime):
                state_data['last_active'] = state_data['last_active'].isoformat()

            # Serialize JSON fields
            state_data['warm_memory'] = json.dumps(state_data.get('warm_memory', {}))
            state_data['active_positions'] = json.dumps(state_data.get('active_positions', []))
            state_data['risk_constraints'] = json.dumps(state_data.get('risk_constraints', {}))

            conn.execute("""
                INSERT OR REPLACE INTO session_state VALUES (
                    :agent_id, :last_active, :warm_memory,
                    :active_positions, :risk_constraints
                )
            """, state_data)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving session state: {e}")
            return False
        finally:
            conn.close()

    def load_session_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Load agent session state.

        Args:
            agent_id: Agent identifier

        Returns:
            Session state dict or None
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM session_state WHERE agent_id = ?",
                (agent_id,)
            ).fetchone()

            if not row:
                return None

            state = dict(row)
            state['warm_memory'] = json.loads(state['warm_memory'])
            state['active_positions'] = json.loads(state['active_positions'])
            state['risk_constraints'] = json.loads(state['risk_constraints'])

            return state
        finally:
            conn.close()

    # ========== Patterns (L2) ==========

    def insert_pattern(self, pattern_data: Dict[str, Any]) -> bool:
        """
        Insert or replace a pattern record.

        Args:
            pattern_data: Pattern dictionary with pattern_id, description, etc.

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            pattern_data['metrics'] = json.dumps(pattern_data.get('metrics', {}))
            conn.execute("""
                INSERT OR REPLACE INTO patterns VALUES (
                    :pattern_id, :pattern_type, :description, :confidence,
                    :sample_size, :date_range, :strategy, :symbol,
                    :metrics, :source, :validation_status, :discovered_at
                )
            """, pattern_data)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting pattern: {e}")
            return False
        finally:
            conn.close()

    def query_patterns(
        self,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
        pattern_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query patterns with filters.

        Args:
            strategy: Filter by strategy
            symbol: Filter by symbol
            pattern_type: Filter by pattern type
            source: Filter by source (backtest_auto, manual)
            limit: Maximum results

        Returns:
            List of pattern dicts
        """
        conn = self._get_connection()
        try:
            query = "SELECT * FROM patterns WHERE 1=1"
            params: list[Any] = []

            if strategy:
                query += " AND strategy = ?"
                params.append(strategy)
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            if pattern_type:
                query += " AND pattern_type = ?"
                params.append(pattern_type)
            if source:
                query += " AND source = ?"
                params.append(source)

            query += " ORDER BY discovered_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()

            patterns = []
            for row in rows:
                p = dict(row)
                p['metrics'] = json.loads(p['metrics'])
                patterns.append(p)

            return patterns
        finally:
            conn.close()

    def get_pattern(self, pattern_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single pattern by ID.

        Args:
            pattern_id: Pattern identifier

        Returns:
            Pattern dict or None
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM patterns WHERE pattern_id = ?",
                (pattern_id,)
            ).fetchone()

            if not row:
                return None

            p = dict(row)
            p['metrics'] = json.loads(p['metrics'])
            return p
        finally:
            conn.close()

    # ========== Strategy Adjustments (L3) ==========

    def insert_adjustment(self, adjustment_data: Dict[str, Any]) -> bool:
        """
        Insert or replace a strategy adjustment record.

        Args:
            adjustment_data: Adjustment dictionary with adjustment_id, type, etc.

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO strategy_adjustments VALUES (
                    :adjustment_id, :adjustment_type, :parameter,
                    :old_value, :new_value, :reason,
                    :source_pattern_id, :confidence, :status,
                    :created_at, :applied_at
                )
            """, adjustment_data)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting adjustment: {e}")
            return False
        finally:
            conn.close()

    def query_adjustments(
        self,
        status: Optional[str] = None,
        adjustment_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Query strategy adjustments with filters.

        Args:
            status: Filter by status (proposed, approved, applied, rejected)
            adjustment_type: Filter by adjustment type
            limit: Maximum results

        Returns:
            List of adjustment dicts
        """
        conn = self._get_connection()
        try:
            query = "SELECT * FROM strategy_adjustments WHERE 1=1"
            params: list[Any] = []

            if status:
                query += " AND status = ?"
                params.append(status)
            if adjustment_type:
                query += " AND adjustment_type = ?"
                params.append(adjustment_type)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def update_adjustment_status(
        self,
        adjustment_id: str,
        status: str,
        applied_at: Optional[str] = None,
    ) -> bool:
        """
        Update the status of a strategy adjustment.

        Args:
            adjustment_id: Adjustment identifier
            status: New status (proposed, approved, applied, rejected)
            applied_at: ISO timestamp when applied (optional)

        Returns:
            True if successful (row was found and updated)
        """
        conn = self._get_connection()
        try:
            if applied_at:
                result = conn.execute(
                    "UPDATE strategy_adjustments SET status = ?, applied_at = ? "
                    "WHERE adjustment_id = ?",
                    (status, applied_at, adjustment_id),
                )
            else:
                result = conn.execute(
                    "UPDATE strategy_adjustments SET status = ? "
                    "WHERE adjustment_id = ?",
                    (status, adjustment_id),
                )
            conn.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating adjustment status: {e}")
            return False
        finally:
            conn.close()

    # ========== OWM: Episodic Memory ==========

    def insert_episodic(self, data: Dict[str, Any]) -> bool:
        """Insert an episodic memory record."""
        conn = self._get_connection()
        try:
            if isinstance(data.get('tags'), (list, dict)):
                data['tags'] = json.dumps(data['tags'])
            if isinstance(data.get('context_json'), dict):
                data['context_json'] = json.dumps(data['context_json'])
            if 'created_at' not in data:
                data['created_at'] = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                INSERT INTO episodic_memory (
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
            """, data)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting episodic memory: {e}")
            return False
        finally:
            conn.close()

    def query_episodic(
        self,
        strategy: Optional[str] = None,
        regime: Optional[str] = None,
        direction: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query episodic memories with filters."""
        conn = self._get_connection()
        try:
            query = "SELECT * FROM episodic_memory WHERE 1=1"
            params: list[Any] = []
            if strategy:
                query += " AND strategy = ?"
                params.append(strategy)
            if regime:
                query += " AND context_regime = ?"
                params.append(regime)
            if direction:
                query += " AND direction = ?"
                params.append(direction)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d['context_json'] = json.loads(d['context_json']) if d['context_json'] else {}
                d['tags'] = json.loads(d['tags']) if d['tags'] else []
                results.append(d)
            return results
        finally:
            conn.close()

    def update_episodic_retrieval(self, memory_id: str) -> bool:
        """Increment retrieval_count and update last_retrieved."""
        conn = self._get_connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            result = conn.execute(
                "UPDATE episodic_memory SET retrieval_count = retrieval_count + 1, "
                "last_retrieved = ? WHERE id = ?",
                (now, memory_id),
            )
            conn.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating episodic retrieval: {e}")
            return False
        finally:
            conn.close()

    def update_episodic_embedding(self, memory_id: str, embedding: list[float]) -> bool:
        """Store embedding vector for an episodic memory record.

        Adds the embedding column via ALTER TABLE if it doesn't exist yet.
        """
        conn = self._get_connection()
        try:
            # Ensure column exists (SQLite ignores duplicate ALTER TABLE ADD COLUMN)
            try:
                conn.execute(
                    "ALTER TABLE episodic_memory ADD COLUMN embedding TEXT"
                )
            except Exception:
                pass  # Column already exists

            embedding_json = json.dumps(embedding)
            result = conn.execute(
                "UPDATE episodic_memory SET embedding = ? WHERE id = ?",
                (embedding_json, memory_id),
            )
            conn.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating episodic embedding: {e}")
            return False
        finally:
            conn.close()

    # ========== OWM: Semantic Memory ==========

    def insert_semantic(self, data: Dict[str, Any]) -> bool:
        """Insert a semantic memory record."""
        conn = self._get_connection()
        try:
            if isinstance(data.get('validity_conditions'), (dict, list)):
                data['validity_conditions'] = json.dumps(data['validity_conditions'])
            now = datetime.now(timezone.utc).isoformat()
            data.setdefault('alpha', 1.0)
            data.setdefault('beta', 1.0)
            data.setdefault('sample_size', 0)
            data.setdefault('retrieval_strength', 1.0)
            data.setdefault('created_at', now)
            data.setdefault('updated_at', now)
            conn.execute("""
                INSERT INTO semantic_memory (
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
            """, data)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting semantic memory: {e}")
            return False
        finally:
            conn.close()

    def query_semantic(
        self,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
        regime: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query semantic memories with filters. Computes confidence/uncertainty in Python."""
        conn = self._get_connection()
        try:
            query = "SELECT * FROM semantic_memory WHERE 1=1"
            params: list[Any] = []
            if strategy:
                query += " AND strategy = ?"
                params.append(strategy)
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            if regime:
                query += " AND regime = ?"
                params.append(regime)
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d['validity_conditions'] = json.loads(d['validity_conditions']) if d['validity_conditions'] else None
                a, b = d['alpha'], d['beta']
                d['confidence'] = a / (a + b) if (a + b) > 0 else 0.5
                d['uncertainty'] = (a * b) / ((a + b) ** 2 * (a + b + 1)) if (a + b) > 0 else 1.0
                results.append(d)
            return results
        finally:
            conn.close()

    def update_semantic_bayesian(
        self,
        memory_id: str,
        confirmed: bool,
        weight: float = 1.0,
        evidence_id: Optional[str] = None,
    ) -> bool:
        """Update semantic memory Bayesian parameters (alpha/beta).

        Args:
            memory_id: Semantic memory ID to update
            confirmed: True = confirming evidence, False = contradicting
            weight: Bayesian update weight (default 1.0)
            evidence_id: Optional episodic memory ID that provided evidence
        """
        conn = self._get_connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            ref = evidence_id or now
            if confirmed:
                result = conn.execute(
                    "UPDATE semantic_memory SET alpha = alpha + ?, "
                    "sample_size = sample_size + 1, last_confirmed = ?, "
                    "updated_at = ? WHERE id = ?",
                    (weight, ref, now, memory_id),
                )
            else:
                result = conn.execute(
                    "UPDATE semantic_memory SET beta = beta + ?, "
                    "sample_size = sample_size + 1, last_contradicted = ?, "
                    "updated_at = ? WHERE id = ?",
                    (weight, ref, now, memory_id),
                )
            conn.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating semantic bayesian: {e}")
            return False
        finally:
            conn.close()

    # ========== OWM: Procedural Memory ==========

    def upsert_procedural(self, data: Dict[str, Any]) -> bool:
        """Insert or replace a procedural memory record."""
        conn = self._get_connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            data.setdefault('created_at', now)
            data['updated_at'] = now
            conn.execute("""
                INSERT OR REPLACE INTO procedural_memory (
                    id, strategy, symbol, behavior_type, sample_size,
                    avg_hold_winners, avg_hold_losers, disposition_ratio,
                    actual_lot_mean, actual_lot_variance,
                    kelly_fraction_suggested, lot_vs_kelly_ratio,
                    created_at, updated_at
                ) VALUES (
                    :id, :strategy, :symbol, :behavior_type, :sample_size,
                    :avg_hold_winners, :avg_hold_losers, :disposition_ratio,
                    :actual_lot_mean, :actual_lot_variance,
                    :kelly_fraction_suggested, :lot_vs_kelly_ratio,
                    :created_at, :updated_at
                )
            """, data)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error upserting procedural memory: {e}")
            return False
        finally:
            conn.close()

    def query_procedural(
        self,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query procedural memory records with filters."""
        conn = self._get_connection()
        try:
            query = "SELECT * FROM procedural_memory WHERE 1=1"
            params: list[Any] = []
            if strategy:
                query += " AND strategy = ?"
                params.append(strategy)
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ========== OWM: Affective State ==========

    def init_affective(self, peak_equity: float, current_equity: float) -> bool:
        """Initialize affective state if not exists."""
        conn = self._get_connection()
        try:
            existing = conn.execute(
                "SELECT id FROM affective_state WHERE id = 'current'"
            ).fetchone()
            if existing:
                return False
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                INSERT INTO affective_state (
                    id, confidence_level, risk_appetite, momentum_bias,
                    peak_equity, current_equity, drawdown_state,
                    max_acceptable_drawdown, consecutive_wins,
                    consecutive_losses, last_updated, history_json
                ) VALUES (
                    'current', 0.5, 1.0, 0.0, ?, ?, 0.0, 0.20, 0, 0, ?, '[]'
                )
            """, (peak_equity, current_equity, now))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error initializing affective state: {e}")
            return False
        finally:
            conn.close()

    def load_affective(self) -> Optional[Dict[str, Any]]:
        """Load the current affective state."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM affective_state WHERE id = 'current'"
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d['history_json'] = json.loads(d['history_json']) if d['history_json'] else []
            return d
        finally:
            conn.close()

    def save_affective(self, data: Dict[str, Any]) -> bool:
        """Save (INSERT OR REPLACE) the current affective state."""
        conn = self._get_connection()
        try:
            if isinstance(data.get('history_json'), (list, dict)):
                data['history_json'] = json.dumps(data['history_json'])
            data['id'] = 'current'
            data.setdefault('last_updated', datetime.now(timezone.utc).isoformat())
            conn.execute("""
                INSERT OR REPLACE INTO affective_state (
                    id, confidence_level, risk_appetite, momentum_bias,
                    peak_equity, current_equity, drawdown_state,
                    max_acceptable_drawdown, consecutive_wins,
                    consecutive_losses, last_updated, history_json
                ) VALUES (
                    :id, :confidence_level, :risk_appetite, :momentum_bias,
                    :peak_equity, :current_equity, :drawdown_state,
                    :max_acceptable_drawdown, :consecutive_wins,
                    :consecutive_losses, :last_updated, :history_json
                )
            """, data)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving affective state: {e}")
            return False
        finally:
            conn.close()

    # ========== OWM: Prospective Memory ==========

    def insert_prospective(self, data: Dict[str, Any]) -> bool:
        """Insert a prospective memory record."""
        conn = self._get_connection()
        try:
            if isinstance(data.get('trigger_condition'), (dict, list)):
                data['trigger_condition'] = json.dumps(data['trigger_condition'])
            if isinstance(data.get('planned_action'), (dict, list)):
                data['planned_action'] = json.dumps(data['planned_action'])
            if isinstance(data.get('source_episodic_ids'), (list,)):
                data['source_episodic_ids'] = json.dumps(data['source_episodic_ids'])
            if isinstance(data.get('source_semantic_ids'), (list,)):
                data['source_semantic_ids'] = json.dumps(data['source_semantic_ids'])
            data.setdefault('status', 'active')
            data.setdefault('priority', 0.5)
            data.setdefault('created_at', datetime.now(timezone.utc).isoformat())
            conn.execute("""
                INSERT INTO prospective_memory (
                    id, trigger_type, trigger_condition, planned_action,
                    action_type, status, priority, expiry,
                    source_episodic_ids, source_semantic_ids, reasoning,
                    triggered_at, outcome_pnl_r, outcome_reflection,
                    created_at
                ) VALUES (
                    :id, :trigger_type, :trigger_condition, :planned_action,
                    :action_type, :status, :priority, :expiry,
                    :source_episodic_ids, :source_semantic_ids, :reasoning,
                    :triggered_at, :outcome_pnl_r, :outcome_reflection,
                    :created_at
                )
            """, data)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting prospective memory: {e}")
            return False
        finally:
            conn.close()

    def query_prospective(
        self,
        status: Optional[str] = None,
        trigger_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query prospective memories with filters."""
        conn = self._get_connection()
        try:
            query = "SELECT * FROM prospective_memory WHERE 1=1"
            params: list[Any] = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if trigger_type:
                query += " AND trigger_type = ?"
                params.append(trigger_type)
            query += " ORDER BY priority DESC, created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d['trigger_condition'] = json.loads(d['trigger_condition']) if d['trigger_condition'] else {}
                d['planned_action'] = json.loads(d['planned_action']) if d['planned_action'] else {}
                d['source_episodic_ids'] = json.loads(d['source_episodic_ids']) if d['source_episodic_ids'] else []
                d['source_semantic_ids'] = json.loads(d['source_semantic_ids']) if d['source_semantic_ids'] else []
                results.append(d)
            return results
        finally:
            conn.close()

    def update_prospective_status(
        self,
        memory_id: str,
        status: str,
        triggered_at: Optional[str] = None,
        outcome_pnl_r: Optional[float] = None,
        outcome_reflection: Optional[str] = None,
    ) -> bool:
        """Update prospective memory status and optional outcome fields."""
        conn = self._get_connection()
        try:
            fields = ["status = ?"]
            params: list[Any] = [status]
            if triggered_at:
                fields.append("triggered_at = ?")
                params.append(triggered_at)
            if outcome_pnl_r is not None:
                fields.append("outcome_pnl_r = ?")
                params.append(outcome_pnl_r)
            if outcome_reflection is not None:
                fields.append("outcome_reflection = ?")
                params.append(outcome_reflection)
            params.append(memory_id)
            result = conn.execute(
                f"UPDATE prospective_memory SET {', '.join(fields)} WHERE id = ?",  # nosec B608 — fields from internal whitelist
                params,
            )
            conn.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating prospective status: {e}")
            return False
        finally:
            conn.close()
