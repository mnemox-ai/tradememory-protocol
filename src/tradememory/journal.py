"""
TradeJournal module - Structured trade memory with full context.
Implements Blueprint Section 2.1 TradeJournal functionality.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from .models import TradeRecord, MarketContext
from .db import Database


class TradeJournal:
    """
    TradeJournal records every trade decision with full context:
    entry/exit reasoning, market state, strategy used, confidence level,
    outcome, and post-trade notes.
    """
    
    def __init__(self, db: Optional[Database] = None):
        """
        Initialize TradeJournal.
        
        Args:
            db: Database instance (creates new if None)
        """
        self.db = db or Database()
    
    def record_decision(
        self,
        trade_id: str,
        symbol: str,
        direction: str,
        lot_size: float,
        strategy: str,
        confidence: float,
        reasoning: str,
        market_context: Dict[str, Any],
        references: Optional[List[str]] = None
    ) -> TradeRecord:
        """
        Record a trade decision with full context.
        
        Args:
            trade_id: Unique trade identifier (T-YYYY-NNNN)
            symbol: Trading instrument (XAUUSD, BTCUSDT, etc.)
            direction: 'long' or 'short'
            lot_size: Position size
            strategy: Strategy tag (VolBreakout, Pullback, etc.)
            confidence: Agent confidence score (0.0 - 1.0)
            reasoning: Natural language explanation of WHY
            market_context: Market snapshot (price, ATR, session, etc.)
            references: Past trade IDs that informed this decision
            
        Returns:
            TradeRecord instance
            
        Raises:
            ValueError: If validation fails
        """
        # Validate inputs
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(f"Confidence must be 0.0-1.0, got {confidence}")
        
        if direction not in ['long', 'short']:
            raise ValueError(f"Direction must be 'long' or 'short', got {direction}")
        
        # Create TradeRecord
        trade = TradeRecord(
            id=trade_id,
            timestamp=datetime.utcnow(),
            symbol=symbol,
            direction=direction,
            lot_size=lot_size,
            strategy=strategy,
            confidence=confidence,
            reasoning=reasoning,
            market_context=MarketContext(**market_context),
            references=references or []
        )
        
        # Persist to database
        success = self.db.insert_trade(trade.model_dump())
        
        if not success:
            raise RuntimeError(f"Failed to insert trade {trade_id} to database")
        
        return trade
    
    def record_outcome(
        self,
        trade_id: str,
        exit_price: float,
        pnl: float,
        exit_reasoning: str,
        pnl_r: Optional[float] = None,
        hold_duration: Optional[int] = None,
        slippage: Optional[float] = None,
        execution_quality: Optional[float] = None,
        lessons: Optional[str] = None
    ) -> bool:
        """
        Record trade outcome after position closes.
        
        Args:
            trade_id: Trade ID to update
            exit_price: Exit price
            pnl: Realized P&L in account currency
            exit_reasoning: Why the agent exited
            pnl_r: P&L in R-multiples (optional)
            hold_duration: Minutes held (optional)
            slippage: Entry slippage in pips (optional)
            execution_quality: 0.0-1.0 score (optional)
            lessons: What was learned (optional)
            
        Returns:
            True if successful
            
        Raises:
            ValueError: If validation fails
        """
        # Validate
        if execution_quality is not None and not (0.0 <= execution_quality <= 1.0):
            raise ValueError(f"Execution quality must be 0.0-1.0, got {execution_quality}")
        
        outcome_data = {
            'exit_timestamp': datetime.utcnow(),
            'exit_price': exit_price,
            'pnl': pnl,
            'exit_reasoning': exit_reasoning
        }
        
        # Optional fields
        if pnl_r is not None:
            outcome_data['pnl_r'] = pnl_r
        if hold_duration is not None:
            outcome_data['hold_duration'] = hold_duration
        if slippage is not None:
            outcome_data['slippage'] = slippage
        if execution_quality is not None:
            outcome_data['execution_quality'] = execution_quality
        if lessons:
            outcome_data['lessons'] = lessons
        
        # Update database
        success = self.db.update_trade_outcome(trade_id, outcome_data)
        
        if not success:
            raise RuntimeError(f"Failed to update trade {trade_id} outcome")
        
        return True
    
    def get_trade(self, trade_id: str) -> Optional[TradeRecord]:
        """
        Retrieve a trade record by ID.
        
        Args:
            trade_id: Trade ID
            
        Returns:
            TradeRecord or None if not found
        """
        trade_data = self.db.get_trade(trade_id)
        
        if not trade_data:
            return None
        
        # Convert back to TradeRecord model
        return TradeRecord(**trade_data)
    
    def query_history(
        self,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[TradeRecord]:
        """
        Query trade history with filters.
        
        Args:
            strategy: Filter by strategy tag
            symbol: Filter by symbol
            limit: Maximum results
            
        Returns:
            List of TradeRecord instances
        """
        trades_data = self.db.query_trades(
            strategy=strategy,
            symbol=symbol,
            limit=limit
        )
        
        return [TradeRecord(**td) for td in trades_data]
    
    def get_active_trades(self) -> List[TradeRecord]:
        """
        Get all currently open trades (no exit timestamp).
        
        Returns:
            List of active TradeRecord instances
        """
        # Query all recent trades and filter for active
        all_trades = self.db.query_trades(limit=1000)
        
        active = []
        for td in all_trades:
            if td.get('exit_timestamp') is None:
                active.append(TradeRecord(**td))
        
        return active
