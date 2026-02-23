"""
ReflectionEngine - AI-powered pattern discovery and learning.
Implements Blueprint Section 2.1 ReflectionEngine functionality.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date
import json

from .models import TradeRecord
from .journal import TradeJournal


class ReflectionEngine:
    """
    ReflectionEngine analyzes trade patterns and generates insights.
    Phase 1: Daily summary only (weekly/monthly in future sprints).
    """
    
    def __init__(self, journal: Optional[TradeJournal] = None):
        """
        Initialize ReflectionEngine.
        
        Args:
            journal: TradeJournal instance (creates new if None)
        """
        self.journal = journal or TradeJournal()
    
    def generate_daily_summary(
        self,
        target_date: Optional[date] = None,
        llm_provider: Optional[callable] = None
    ) -> str:
        """
        Generate daily trading summary with AI reflection.
        
        Args:
            target_date: Date to analyze (default: today)
            llm_provider: Optional LLM function (model, prompt) -> response
                         If None, uses rule-based summary
        
        Returns:
            Formatted daily summary string
        """
        if target_date is None:
            target_date = date.today()
        
        # Get today's trades
        trades = self._get_trades_for_date(target_date)
        
        if len(trades) == 0:
            return self._format_no_trades_summary(target_date)
        
        # Calculate performance metrics
        metrics = self._calculate_daily_metrics(trades)
        
        # Generate summary (LLM or rule-based)
        if llm_provider:
            return self._generate_llm_summary(target_date, trades, metrics, llm_provider)
        else:
            return self._generate_rule_based_summary(target_date, trades, metrics)
    
    def _get_trades_for_date(self, target_date: date) -> List[TradeRecord]:
        """Get all trades for a specific date (UTC timezone)"""
        # Query all recent trades
        all_trades = self.journal.query_history(limit=1000)
        
        # Filter for target date (compare date strings to handle timezone)
        target_str = target_date.isoformat()
        date_trades = []
        for trade in all_trades:
            # Convert timestamp to date string (UTC)
            if isinstance(trade.timestamp, str):
                trade_date_str = trade.timestamp[:10]  # YYYY-MM-DD
            else:
                trade_date_str = trade.timestamp.date().isoformat()
            
            if trade_date_str == target_str:
                date_trades.append(trade)
        
        return date_trades
    
    def _calculate_daily_metrics(self, trades: List[TradeRecord]) -> Dict[str, Any]:
        """Calculate performance metrics for a set of trades"""
        total = len(trades)
        winners = sum(1 for t in trades if t.pnl and t.pnl > 0)
        losers = sum(1 for t in trades if t.pnl and t.pnl < 0)
        breakeven = total - winners - losers
        
        total_pnl = sum(t.pnl for t in trades if t.pnl is not None)
        win_rate = (winners / total * 100) if total > 0 else 0.0
        
        # Average R-multiple
        r_values = [t.pnl_r for t in trades if t.pnl_r is not None]
        avg_r = sum(r_values) / len(r_values) if r_values else 0.0
        
        # Average confidence
        avg_confidence = sum(t.confidence for t in trades) / total if total > 0 else 0.0
        
        return {
            'total': total,
            'winners': winners,
            'losers': losers,
            'breakeven': breakeven,
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'avg_r': avg_r,
            'avg_confidence': avg_confidence
        }
    
    def _format_no_trades_summary(self, target_date: date) -> str:
        """Format summary when no trades occurred"""
        return f"""=== DAILY SUMMARY: {target_date.isoformat()} ===

PERFORMANCE:
No trades today.

STATUS: Waiting for market opportunities.
"""
    
    def _generate_rule_based_summary(
        self,
        target_date: date,
        trades: List[TradeRecord],
        metrics: Dict[str, Any]
    ) -> str:
        """Generate summary using rule-based logic (no LLM)"""
        
        summary = f"""=== DAILY SUMMARY: {target_date.isoformat()} ===

PERFORMANCE:
Trades: {metrics['total']} | Winners: {metrics['winners']} | Losers: {metrics['losers']}
Net P&L: ${metrics['total_pnl']:.2f} | Win Rate: {metrics['win_rate']:.1f}% | Avg R: {metrics['avg_r']:.2f}

"""
        
        # Add data sufficiency warning
        if metrics['total'] < 3:
            summary += "STATUS: Insufficient data for pattern analysis.\n\n"
        
        # Key observations (rule-based)
        observations = []
        
        if metrics['avg_confidence'] > 0.8:
            observations.append(f"High average confidence ({metrics['avg_confidence']:.2f}) - agent is selective.")
        
        if metrics['win_rate'] > 60:
            observations.append(f"Strong win rate ({metrics['win_rate']:.1f}%) - edge appears present.")
        elif metrics['win_rate'] < 40:
            observations.append(f"Low win rate ({metrics['win_rate']:.1f}%) - review entry criteria.")
        
        if metrics['avg_r'] < 0:
            observations.append(f"Negative avg R ({metrics['avg_r']:.2f}) - risk management issue.")
        
        if observations:
            summary += "KEY OBSERVATIONS:\n"
            for obs in observations[:3]:  # Max 3
                summary += f"- {obs}\n"
            summary += "\n"
        
        # Mistakes (identify losing trades with high confidence)
        mistakes = []
        for trade in trades:
            if trade.pnl and trade.pnl < 0 and trade.confidence > 0.75:
                mistakes.append(f"{trade.id}: High confidence ({trade.confidence:.2f}) but lost ${abs(trade.pnl):.2f}")
        
        if mistakes:
            summary += "MISTAKES:\n"
            for mistake in mistakes[:2]:  # Max 2
                summary += f"- {mistake}\n"
            summary += "\n"
        
        # Tomorrow advice
        summary += "TOMORROW:\n"
        if metrics['win_rate'] < 50:
            summary += "- Review entry criteria - consider tighter filters.\n"
        if metrics['avg_r'] < 1.0:
            summary += "- Focus on improving R-multiple - trail stops more aggressively.\n"
        if not observations:
            summary += "- Continue monitoring. More data needed.\n"
        
        return summary
    
    def _generate_llm_summary(
        self,
        target_date: date,
        trades: List[TradeRecord],
        metrics: Dict[str, Any],
        llm_provider: callable
    ) -> str:
        """
        Generate summary using LLM.
        
        Args:
            target_date: Date being analyzed
            trades: Trade records
            metrics: Calculated metrics
            llm_provider: Function (model, prompt) -> response_text
        """
        
        # Prepare trades JSON
        trades_json = json.dumps(
            [t.model_dump() for t in trades],
            indent=2,
            default=str
        )
        
        # Build prompt using CIO template
        prompt = f"""你是一個交易反思引擎。分析以下今日交易紀錄，產出結構化的每日摘要。

## 輸入
{trades_json}

## 輸出格式（嚴格遵守）
=== DAILY SUMMARY: {target_date.isoformat()} ===

PERFORMANCE:
Trades: {metrics['total']} | Winners: {metrics['winners']} | Losers: {metrics['losers']}
Net P&L: ${metrics['total_pnl']:.2f} | Win Rate: {metrics['win_rate']:.1f}% | Avg R: {metrics['avg_r']:.2f}

KEY OBSERVATIONS:
- [最多3條，每條1-2句，聚焦可執行的洞察]

MISTAKES:
- [如果有明顯錯誤的交易，指出原因]

TOMORROW:
- [基於今天的觀察，明天應注意什麼]

## 規則
- 不要廢話，不要鼓勵性語言
- 只寫有數據支撐的觀察
- 如果今天沒有交易，只寫 "No trades today."
- 如果交易太少（<3筆），標註 "Insufficient data for pattern analysis."
"""
        
        # Call LLM
        try:
            response = llm_provider("claude-sonnet-4-5", prompt)
            
            # Validate output format (DEC-010: prevent garbage in L2 memory)
            if self._validate_llm_output(response, target_date):
                return response
            else:
                # Malformed output → fallback to rule-based
                return self._generate_rule_based_summary(target_date, trades, metrics) + \
                       "\n(LLM output failed validation, using rule-based fallback)\n"
        
        except Exception as e:
            # Fallback to rule-based if LLM fails
            return self._generate_rule_based_summary(target_date, trades, metrics) + \
                   f"\n(LLM failed: {str(e)}, using rule-based fallback)\n"
    
    def _validate_llm_output(self, output: str, target_date: date) -> bool:
        """
        Validate LLM output matches expected template structure.
        
        Args:
            output: LLM response text
            target_date: Expected date in summary
        
        Returns:
            True if valid, False if malformed
        
        DEC-010: Garbage in L2 is worse than no L2.
        """
        if not output or len(output) < 50:
            return False
        
        # Check required sections
        required_sections = [
            f"=== DAILY SUMMARY: {target_date.isoformat()} ===",
            "PERFORMANCE:",
            "Trades:",
            "Win Rate:"
        ]
        
        for section in required_sections:
            if section not in output:
                return False
        
        # Check structure markers (at least 2 of these should exist)
        optional_sections = ["KEY OBSERVATIONS:", "MISTAKES:", "TOMORROW:"]
        found_count = sum(1 for s in optional_sections if s in output)
        
        if found_count < 2:
            return False
        
        return True
