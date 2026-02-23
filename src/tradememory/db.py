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
                INSERT INTO trade_records VALUES (
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
            params = []
            
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
