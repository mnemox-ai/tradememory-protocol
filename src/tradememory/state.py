"""
StateManager - Cross-session state persistence for AI agents.
Implements Blueprint Section 2.1 StateManager functionality.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from .models import SessionState
from .db import Database


class StateManager:
    """
    StateManager handles cross-session state, agent identity continuity,
    and memory retrieval. Ensures the agent "wakes up" knowing who it is
    and what it has learned.
    """
    
    def __init__(self, db: Optional[Database] = None):
        """
        Initialize StateManager.
        
        Args:
            db: Database instance (creates new if None)
        """
        self.db = db or Database()
    
    def load_state(self, agent_id: str) -> SessionState:
        """
        Load agent state at session start.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            SessionState (creates new if not exists)
        """
        state_data = self.db.load_session_state(agent_id)
        
        if state_data:
            return SessionState(**state_data)
        
        # Create new state if doesn't exist
        new_state = SessionState(
            agent_id=agent_id,
            last_active=datetime.now(timezone.utc),
            warm_memory={},
            active_positions=[],
            risk_constraints={}
        )
        
        self.save_state(new_state)
        return new_state
    
    def save_state(self, state: SessionState) -> bool:
        """
        Persist current agent state.
        
        Args:
            state: SessionState to save
            
        Returns:
            True if successful
        """
        # Update last_active timestamp
        state.last_active = datetime.now(timezone.utc)
        
        success = self.db.save_session_state(state.model_dump())
        
        if not success:
            raise RuntimeError(f"Failed to save state for agent {state.agent_id}")
        
        return True
    
    def update_warm_memory(
        self,
        agent_id: str,
        key: str,
        value: Any
    ) -> bool:
        """
        Update a specific warm memory entry.
        
        Args:
            agent_id: Agent identifier
            key: Memory key
            value: Memory value
            
        Returns:
            True if successful
        """
        state = self.load_state(agent_id)
        state.warm_memory[key] = value
        return self.save_state(state)
    
    def get_warm_memory(self, agent_id: str, key: str) -> Optional[Any]:
        """
        Retrieve a warm memory entry.
        
        Args:
            agent_id: Agent identifier
            key: Memory key
            
        Returns:
            Memory value or None
        """
        state = self.load_state(agent_id)
        return state.warm_memory.get(key)
    
    def add_active_position(self, agent_id: str, trade_id: str) -> bool:
        """
        Add a trade to active positions list.
        
        Args:
            agent_id: Agent identifier
            trade_id: Trade ID
            
        Returns:
            True if successful
        """
        state = self.load_state(agent_id)
        
        if trade_id not in state.active_positions:
            state.active_positions.append(trade_id)
        
        return self.save_state(state)
    
    def remove_active_position(self, agent_id: str, trade_id: str) -> bool:
        """
        Remove a trade from active positions list.
        
        Args:
            agent_id: Agent identifier
            trade_id: Trade ID
            
        Returns:
            True if successful
        """
        state = self.load_state(agent_id)
        
        if trade_id in state.active_positions:
            state.active_positions.remove(trade_id)
        
        return self.save_state(state)
    
    def update_risk_constraints(
        self,
        agent_id: str,
        constraints: Dict[str, Any]
    ) -> bool:
        """
        Update dynamic risk parameters.
        
        Args:
            agent_id: Agent identifier
            constraints: Risk constraint dictionary
            
        Returns:
            True if successful
        """
        state = self.load_state(agent_id)
        state.risk_constraints = constraints
        return self.save_state(state)
