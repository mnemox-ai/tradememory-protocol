"""
Unit tests for StateManager module.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from src.tradememory.state import StateManager
from src.tradememory.db import Database
from src.tradememory.models import SessionState


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(str(db_path))
        yield db


@pytest.fixture
def state_manager(temp_db):
    """Create a StateManager with temp database"""
    return StateManager(db=temp_db)


def test_load_new_state(state_manager):
    """Test loading state for new agent creates default state"""
    state = state_manager.load_state("agent-001")
    
    assert state.agent_id == "agent-001"
    assert state.warm_memory == {}
    assert state.active_positions == []
    assert state.risk_constraints == {}
    assert state.last_active is not None


def test_save_and_load_state(state_manager):
    """Test saving and loading state persists data"""
    # Create and save state
    state = SessionState(
        agent_id="agent-002",
        last_active=datetime.utcnow(),
        warm_memory={"last_strategy": "VolBreakout", "win_rate": 0.65},
        active_positions=["T-2026-001", "T-2026-002"],
        risk_constraints={"max_lot": 0.1, "daily_loss_limit": 100.0}
    )
    
    success = state_manager.save_state(state)
    assert success is True
    
    # Load state back
    loaded = state_manager.load_state("agent-002")
    
    assert loaded.agent_id == "agent-002"
    assert loaded.warm_memory["last_strategy"] == "VolBreakout"
    assert loaded.warm_memory["win_rate"] == 0.65
    assert len(loaded.active_positions) == 2
    assert "T-2026-001" in loaded.active_positions
    assert loaded.risk_constraints["max_lot"] == 0.1


def test_update_warm_memory(state_manager):
    """Test updating individual warm memory entries"""
    # Initialize state
    state_manager.load_state("agent-003")
    
    # Update memory
    success = state_manager.update_warm_memory("agent-003", "last_trade", "T-2026-100")
    assert success is True
    
    success = state_manager.update_warm_memory("agent-003", "total_trades", 42)
    assert success is True
    
    # Load and verify
    loaded = state_manager.load_state("agent-003")
    assert loaded.warm_memory["last_trade"] == "T-2026-100"
    assert loaded.warm_memory["total_trades"] == 42


def test_get_warm_memory(state_manager):
    """Test retrieving warm memory entries"""
    # Setup
    state_manager.update_warm_memory("agent-004", "strategy", "Pullback")
    
    # Get value
    value = state_manager.get_warm_memory("agent-004", "strategy")
    assert value == "Pullback"
    
    # Get non-existent key
    value = state_manager.get_warm_memory("agent-004", "nonexistent")
    assert value is None


def test_add_active_position(state_manager):
    """Test adding active positions"""
    # Initialize
    state_manager.load_state("agent-005")
    
    # Add positions
    state_manager.add_active_position("agent-005", "T-2026-201")
    state_manager.add_active_position("agent-005", "T-2026-202")
    
    # Verify
    loaded = state_manager.load_state("agent-005")
    assert len(loaded.active_positions) == 2
    assert "T-2026-201" in loaded.active_positions
    assert "T-2026-202" in loaded.active_positions


def test_remove_active_position(state_manager):
    """Test removing active positions"""
    # Setup
    state_manager.load_state("agent-006")
    state_manager.add_active_position("agent-006", "T-2026-301")
    state_manager.add_active_position("agent-006", "T-2026-302")
    state_manager.add_active_position("agent-006", "T-2026-303")
    
    # Remove one
    success = state_manager.remove_active_position("agent-006", "T-2026-302")
    assert success is True
    
    # Verify
    loaded = state_manager.load_state("agent-006")
    assert len(loaded.active_positions) == 2
    assert "T-2026-301" in loaded.active_positions
    assert "T-2026-303" in loaded.active_positions
    assert "T-2026-302" not in loaded.active_positions


def test_update_risk_constraints(state_manager):
    """Test updating risk constraints"""
    # Initialize
    state_manager.load_state("agent-007")
    
    # Update constraints
    constraints = {
        "max_lot": 0.2,
        "max_positions": 3,
        "daily_loss_limit": 200.0,
        "win_rate_threshold": 0.55
    }
    
    success = state_manager.update_risk_constraints("agent-007", constraints)
    assert success is True
    
    # Verify
    loaded = state_manager.load_state("agent-007")
    assert loaded.risk_constraints["max_lot"] == 0.2
    assert loaded.risk_constraints["max_positions"] == 3
    assert loaded.risk_constraints["daily_loss_limit"] == 200.0
    assert loaded.risk_constraints["win_rate_threshold"] == 0.55


def test_cross_session_persistence(temp_db):
    """Test that state persists across multiple StateManager instances"""
    # Session 1: Create and save state
    sm1 = StateManager(db=temp_db)
    sm1.update_warm_memory("agent-008", "session", 1)
    sm1.add_active_position("agent-008", "T-2026-401")
    
    # Session 2: New StateManager instance, load state
    sm2 = StateManager(db=temp_db)
    loaded = sm2.load_state("agent-008")
    
    assert loaded.warm_memory["session"] == 1
    assert "T-2026-401" in loaded.active_positions
    
    # Session 2: Update state
    sm2.update_warm_memory("agent-008", "session", 2)
    sm2.add_active_position("agent-008", "T-2026-402")
    
    # Session 3: Verify persistence
    sm3 = StateManager(db=temp_db)
    loaded = sm3.load_state("agent-008")
    
    assert loaded.warm_memory["session"] == 2
    assert len(loaded.active_positions) == 2
    assert "T-2026-401" in loaded.active_positions
    assert "T-2026-402" in loaded.active_positions


def test_last_active_updates_on_save(state_manager):
    """Test that last_active timestamp updates on save"""
    # Create state
    state1 = state_manager.load_state("agent-009")
    time1 = state1.last_active
    
    # Wait a bit (pytest runs fast, so timestamp might be same)
    import time
    time.sleep(0.1)
    
    # Save state
    state_manager.update_warm_memory("agent-009", "test", "value")
    
    # Load and check timestamp updated
    state2 = state_manager.load_state("agent-009")
    time2 = state2.last_active
    
    assert time2 >= time1  # Should be newer or equal
