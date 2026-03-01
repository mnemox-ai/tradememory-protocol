"""
SQLite database operations for TradeMemory Protocol.
Single file database, no ORM (per CIO directive).
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import json


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
            print(f"Error inserting trade: {e}")
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
            
            query = f"UPDATE trade_records SET {', '.join(fields)} WHERE id = :id"
            outcome_data['id'] = trade_id
            
            conn.execute(query, outcome_data)
            conn.commit()
            return True
        except Exception as e:
            print(f"Error updating trade outcome: {e}")
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
            print(f"Error saving session state: {e}")
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
            print(f"Error inserting pattern: {e}")
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
            print(f"Error inserting adjustment: {e}")
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
            print(f"Error updating adjustment status: {e}")
            return False
        finally:
            conn.close()
