"""
ReflectionEngine - AI-powered pattern discovery and learning.
Implements Blueprint Section 2.1 ReflectionEngine functionality.
"""

from typing import Callable, List, Dict, Any, Optional
from datetime import date, timedelta
from collections import defaultdict
import json

from .models import TradeRecord
from .journal import TradeJournal


class ReflectionEngine:
    """
    ReflectionEngine analyzes trade patterns and generates insights.
    Supports daily, weekly, and monthly reflection cycles.
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
        llm_provider: Optional[Callable[..., str]] = None
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
        llm_provider: Callable[..., str]
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

    # ========== Date Range Helper ==========

    def _get_trades_for_date_range(
        self, start_date: date, end_date: date
    ) -> List[TradeRecord]:
        """Get all trades within a date range (inclusive, UTC timezone)."""
        all_trades = self.journal.query_history(limit=10000)
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        result = []
        for trade in all_trades:
            if isinstance(trade.timestamp, str):
                trade_date_str = trade.timestamp[:10]
            else:
                trade_date_str = trade.timestamp.date().isoformat()
            if start_str <= trade_date_str <= end_str:
                result.append(trade)
        return result

    # ========== Weekly Reflection ==========

    def generate_weekly_summary(
        self,
        week_ending: Optional[date] = None,
        llm_provider: Optional[Callable[..., str]] = None,
    ) -> str:
        """
        Generate weekly trading summary.

        Args:
            week_ending: Last day of the week (default: last Sunday)
            llm_provider: Optional LLM function (model, prompt) -> response
        """
        if week_ending is None:
            today = date.today()
            # Default to last Sunday
            days_since_sunday = (today.weekday() + 1) % 7
            week_ending = today - timedelta(days=days_since_sunday)

        week_start = week_ending - timedelta(days=6)
        trades = self._get_trades_for_date_range(week_start, week_ending)

        if len(trades) == 0:
            return self._format_no_trades_weekly(week_ending)

        metrics = self._calculate_weekly_metrics(trades, week_start, week_ending)

        if llm_provider:
            return self._generate_llm_weekly_summary(
                week_ending, trades, metrics, llm_provider
            )
        return self._generate_rule_based_weekly_summary(
            week_ending, trades, metrics
        )

    def _calculate_weekly_metrics(
        self,
        trades: List[TradeRecord],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Calculate weekly performance metrics."""
        base = self._calculate_daily_metrics(trades)

        # --- Strategy breakdown ---
        strategy_map: Dict[str, List[TradeRecord]] = defaultdict(list)
        for t in trades:
            strategy_map[t.strategy].append(t)

        strategy_breakdown: Dict[str, Dict[str, Any]] = {}
        for strat, strat_trades in strategy_map.items():
            total = len(strat_trades)
            winners = sum(1 for t in strat_trades if t.pnl and t.pnl > 0)
            total_pnl = sum(t.pnl for t in strat_trades if t.pnl is not None)
            strategy_breakdown[strat] = {
                "total": total,
                "winners": winners,
                "win_rate": (winners / total * 100) if total > 0 else 0.0,
                "total_pnl": total_pnl,
            }

        # --- Session patterns ---
        session_map: Dict[str, List[TradeRecord]] = defaultdict(list)
        for t in trades:
            sess = (
                t.market_context.session
                if hasattr(t.market_context, "session") and t.market_context.session
                else "unknown"
            )
            session_map[sess].append(t)

        session_patterns: Dict[str, Dict[str, Any]] = {}
        for sess, sess_trades in session_map.items():
            total = len(sess_trades)
            winners = sum(1 for t in sess_trades if t.pnl and t.pnl > 0)
            total_pnl = sum(t.pnl for t in sess_trades if t.pnl is not None)
            session_patterns[sess] = {
                "total": total,
                "winners": winners,
                "win_rate": (winners / total * 100) if total > 0 else 0.0,
                "total_pnl": total_pnl,
            }

        # --- Day-of-week analysis ---
        dow_map: Dict[str, List[TradeRecord]] = defaultdict(list)
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for t in trades:
            if isinstance(t.timestamp, str):
                td = date.fromisoformat(t.timestamp[:10])
            else:
                td = t.timestamp.date()
            dow_map[day_names[td.weekday()]].append(t)

        day_of_week: Dict[str, Dict[str, Any]] = {}
        best_day = ("", -float("inf"))
        worst_day = ("", float("inf"))
        for day_name, day_trades in dow_map.items():
            total_pnl = sum(t.pnl for t in day_trades if t.pnl is not None)
            total = len(day_trades)
            winners = sum(1 for t in day_trades if t.pnl and t.pnl > 0)
            day_of_week[day_name] = {
                "total": total,
                "winners": winners,
                "win_rate": (winners / total * 100) if total > 0 else 0.0,
                "total_pnl": total_pnl,
            }
            if total_pnl > best_day[1]:
                best_day = (day_name, total_pnl)
            if total_pnl < worst_day[1]:
                worst_day = (day_name, total_pnl)

        # --- Streak analysis ---
        sorted_trades = sorted(trades, key=lambda t: t.timestamp if isinstance(t.timestamp, str) else t.timestamp.isoformat())
        max_win_streak = 0
        max_loss_streak = 0
        current_win = 0
        current_loss = 0
        for t in sorted_trades:
            if t.pnl and t.pnl > 0:
                current_win += 1
                current_loss = 0
            elif t.pnl and t.pnl < 0:
                current_loss += 1
                current_win = 0
            else:
                current_win = 0
                current_loss = 0
            max_win_streak = max(max_win_streak, current_win)
            max_loss_streak = max(max_loss_streak, current_loss)

        # --- Risk-adjusted metrics ---
        win_pnls = [t.pnl for t in trades if t.pnl and t.pnl > 0]
        loss_pnls = [t.pnl for t in trades if t.pnl and t.pnl < 0]
        gross_wins = sum(win_pnls) if win_pnls else 0.0
        gross_losses = abs(sum(loss_pnls)) if loss_pnls else 0.0
        profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else float("inf") if gross_wins > 0 else 0.0
        avg_win = (gross_wins / len(win_pnls)) if win_pnls else 0.0
        avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0
        best_trade = max((t.pnl for t in trades if t.pnl is not None), default=0.0)
        worst_trade = min((t.pnl for t in trades if t.pnl is not None), default=0.0)

        base.update({
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "strategy_breakdown": strategy_breakdown,
            "session_patterns": session_patterns,
            "day_of_week": day_of_week,
            "best_day": best_day[0],
            "worst_day": worst_day[0],
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
        })
        return base

    def _format_no_trades_weekly(self, week_ending: date) -> str:
        week_start = week_ending - timedelta(days=6)
        return f"""=== WEEKLY SUMMARY: {week_start.isoformat()} to {week_ending.isoformat()} ===

PERFORMANCE:
No trades this week.

STATUS: Waiting for market opportunities.
"""

    def _generate_rule_based_weekly_summary(
        self,
        week_ending: date,
        trades: List[TradeRecord],
        metrics: Dict[str, Any],
    ) -> str:
        week_start = week_ending - timedelta(days=6)
        pf_str = f"{metrics['profit_factor']:.2f}" if metrics['profit_factor'] != float("inf") else "INF"

        summary = f"""=== WEEKLY SUMMARY: {week_start.isoformat()} to {week_ending.isoformat()} ===

PERFORMANCE:
Trades: {metrics['total']} | Winners: {metrics['winners']} | Losers: {metrics['losers']}
Net P&L: ${metrics['total_pnl']:.2f} | Win Rate: {metrics['win_rate']:.1f}% | Avg R: {metrics['avg_r']:.2f} | Profit Factor: {pf_str}

"""

        if metrics["total"] < 5:
            summary += "STATUS: Insufficient data for weekly pattern analysis.\n\n"

        # Strategy breakdown
        if metrics["strategy_breakdown"]:
            summary += "STRATEGY BREAKDOWN:\n"
            for strat, stats in metrics["strategy_breakdown"].items():
                flag = ""
                if stats["win_rate"] >= 60:
                    flag = " [STRONG]"
                elif stats["win_rate"] <= 35:
                    flag = " [WEAK]"
                summary += (
                    f"- {strat}: {stats['total']} trades, "
                    f"{stats['winners']} wins, "
                    f"WR {stats['win_rate']:.1f}%, "
                    f"P&L ${stats['total_pnl']:.2f}{flag}\n"
                )
            summary += "\n"

        # Session patterns
        if metrics["session_patterns"]:
            summary += "SESSION PATTERNS:\n"
            for sess, stats in metrics["session_patterns"].items():
                summary += (
                    f"- {sess}: {stats['total']} trades, "
                    f"WR {stats['win_rate']:.1f}%, "
                    f"P&L ${stats['total_pnl']:.2f}\n"
                )
            summary += "\n"

        # Day of week
        if metrics["best_day"]:
            summary += "DAY OF WEEK:\n"
            summary += f"- Best: {metrics['best_day']}\n"
            summary += f"- Worst: {metrics['worst_day']}\n\n"

        # Streaks
        summary += "STREAKS:\n"
        summary += f"- Max win streak: {metrics['max_win_streak']}\n"
        summary += f"- Max loss streak: {metrics['max_loss_streak']}\n\n"

        # Key observations
        observations = []
        if metrics["win_rate"] > 60:
            observations.append(f"Strong weekly win rate ({metrics['win_rate']:.1f}%) — edge consistent.")
        elif metrics["win_rate"] < 40:
            observations.append(f"Low weekly win rate ({metrics['win_rate']:.1f}%) — review entry criteria.")

        if metrics["max_loss_streak"] >= 3:
            observations.append(f"Loss streak of {metrics['max_loss_streak']} detected — check for tilt or regime change.")

        if metrics["avg_loss"] != 0 and metrics["avg_win"] > 0:
            rr = metrics["avg_win"] / abs(metrics["avg_loss"])
            if rr < 1.0:
                observations.append(f"Reward/risk ratio {rr:.2f} < 1.0 — improve target placement.")

        # Flag weak strategies
        for strat, stats in metrics["strategy_breakdown"].items():
            if stats["total"] >= 3 and stats["win_rate"] <= 30:
                observations.append(f"Strategy '{strat}' underperforming ({stats['win_rate']:.0f}% WR) — consider pausing.")

        if observations:
            summary += "KEY OBSERVATIONS:\n"
            for obs in observations[:4]:
                summary += f"- {obs}\n"
            summary += "\n"

        # Next week
        summary += "NEXT WEEK:\n"
        if metrics["win_rate"] < 50:
            summary += "- Tighten entry filters — selectivity over volume.\n"
        if metrics["max_loss_streak"] >= 3:
            summary += "- Implement cooldown after 3 consecutive losses.\n"
        if not observations:
            summary += "- Continue current approach. More data needed for patterns.\n"

        return summary

    def _generate_llm_weekly_summary(
        self,
        week_ending: date,
        trades: List[TradeRecord],
        metrics: Dict[str, Any],
        llm_provider: Callable[..., str],
    ) -> str:
        week_start = week_ending - timedelta(days=6)
        trades_json = json.dumps(
            [t.model_dump() for t in trades], indent=2, default=str
        )

        prompt = f"""你是一個交易反思引擎。分析以下一週交易紀錄，產出結構化的週摘要。

## 輸入
{trades_json}

## 輸出格式（嚴格遵守）
=== WEEKLY SUMMARY: {week_start.isoformat()} to {week_ending.isoformat()} ===

PERFORMANCE:
Trades: {metrics['total']} | Winners: {metrics['winners']} | Losers: {metrics['losers']}
Net P&L: ${metrics['total_pnl']:.2f} | Win Rate: {metrics['win_rate']:.1f}%

STRATEGY BREAKDOWN:
- [每個策略的交易數/勝率/P&L]

SESSION PATTERNS:
- [每個 session 的表現]

KEY OBSERVATIONS:
- [最多4條，每條1-2句，聚焦可執行的洞察]

NEXT WEEK:
- [基於這週的觀察，下週應注意什麼]

## 規則
- 不要廢話，不要鼓勵性語言
- 只寫有數據支撐的觀察
- 如果交易太少（<5筆），標註 "Insufficient data for weekly pattern analysis."
"""

        try:
            response = llm_provider("claude-sonnet-4-5", prompt)
            if self._validate_weekly_llm_output(response, week_ending):
                return response
            return self._generate_rule_based_weekly_summary(week_ending, trades, metrics) + \
                   "\n(LLM output failed validation, using rule-based fallback)\n"
        except Exception as e:
            return self._generate_rule_based_weekly_summary(week_ending, trades, metrics) + \
                   f"\n(LLM failed: {str(e)}, using rule-based fallback)\n"

    def _validate_weekly_llm_output(self, output: str, week_ending: date) -> bool:
        """Validate weekly LLM output (DEC-010 pattern)."""
        if not output or len(output) < 80:
            return False

        week_start = week_ending - timedelta(days=6)
        required = [
            f"=== WEEKLY SUMMARY: {week_start.isoformat()} to {week_ending.isoformat()} ===",
            "PERFORMANCE:",
            "Trades:",
            "Win Rate:",
        ]
        for section in required:
            if section not in output:
                return False

        optional = ["STRATEGY BREAKDOWN:", "SESSION PATTERNS:", "KEY OBSERVATIONS:", "NEXT WEEK:"]
        if sum(1 for s in optional if s in output) < 2:
            return False

        return True

    # ========== Monthly Reflection ==========

    def generate_monthly_summary(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
        llm_provider: Optional[Callable[..., str]] = None,
    ) -> str:
        """
        Generate monthly trading summary.

        Args:
            year: Target year (default: current)
            month: Target month (default: current)
            llm_provider: Optional LLM function
        """
        today = date.today()
        if year is None:
            year = today.year
        if month is None:
            month = today.month

        start_date = date(year, month, 1)
        # Last day of month
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        trades = self._get_trades_for_date_range(start_date, end_date)

        if len(trades) == 0:
            return self._format_no_trades_monthly(year, month)

        metrics = self._calculate_monthly_metrics(trades, start_date, end_date)

        if llm_provider:
            return self._generate_llm_monthly_summary(
                year, month, trades, metrics, llm_provider
            )
        return self._generate_rule_based_monthly_summary(year, month, trades, metrics)

    def _calculate_monthly_metrics(
        self,
        trades: List[TradeRecord],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Calculate monthly metrics including weekly trends and strategy evolution."""
        base = self._calculate_weekly_metrics(trades, start_date, end_date)

        # --- Trading days ---
        trade_dates = set()
        for t in trades:
            if isinstance(t.timestamp, str):
                trade_dates.add(t.timestamp[:10])
            else:
                trade_dates.add(t.timestamp.date().isoformat())
        trading_days = len(trade_dates)
        avg_trades_per_day = base["total"] / trading_days if trading_days > 0 else 0.0

        # --- Weekly trends ---
        weekly_trends: list[Dict[str, Any]] = []
        current = start_date
        week_num = 1
        while current <= end_date:
            w_end = min(current + timedelta(days=6), end_date)
            w_trades = [
                t for t in trades
                if current.isoformat() <= (
                    t.timestamp[:10] if isinstance(t.timestamp, str) else t.timestamp.date().isoformat()
                ) <= w_end.isoformat()
            ]
            if w_trades:
                total = len(w_trades)
                winners = sum(1 for t in w_trades if t.pnl and t.pnl > 0)
                total_pnl = sum(t.pnl for t in w_trades if t.pnl is not None)
                weekly_trends.append({
                    "week": week_num,
                    "start": current.isoformat(),
                    "end": w_end.isoformat(),
                    "trades": total,
                    "win_rate": (winners / total * 100) if total > 0 else 0.0,
                    "pnl": total_pnl,
                })
            week_num += 1
            current = w_end + timedelta(days=1)

        # Trend direction
        if len(weekly_trends) >= 2:
            first_wr = weekly_trends[0]["win_rate"]
            last_wr = weekly_trends[-1]["win_rate"]
            if last_wr > first_wr + 5:
                trend_direction = "improving"
            elif last_wr < first_wr - 5:
                trend_direction = "declining"
            else:
                trend_direction = "stable"
        else:
            trend_direction = "insufficient_data"

        # --- Strategy evolution: first half vs second half ---
        mid = start_date + timedelta(days=(end_date - start_date).days // 2)
        first_half = [
            t for t in trades
            if (t.timestamp[:10] if isinstance(t.timestamp, str) else t.timestamp.date().isoformat()) <= mid.isoformat()
        ]
        second_half = [
            t for t in trades
            if (t.timestamp[:10] if isinstance(t.timestamp, str) else t.timestamp.date().isoformat()) > mid.isoformat()
        ]

        strategy_evolution: Dict[str, Dict[str, Any]] = {}
        all_strategies = set(t.strategy for t in trades)
        for strat in all_strategies:
            fh = [t for t in first_half if t.strategy == strat]
            sh = [t for t in second_half if t.strategy == strat]
            fh_total = len(fh)
            sh_total = len(sh)
            fh_wr = (sum(1 for t in fh if t.pnl and t.pnl > 0) / fh_total * 100) if fh_total > 0 else 0.0
            sh_wr = (sum(1 for t in sh if t.pnl and t.pnl > 0) / sh_total * 100) if sh_total > 0 else 0.0

            if sh_wr > fh_wr + 5:
                direction = "improving"
            elif sh_wr < fh_wr - 5:
                direction = "declining"
            else:
                direction = "stable"

            strategy_evolution[strat] = {
                "first_half_trades": fh_total,
                "first_half_wr": fh_wr,
                "second_half_trades": sh_total,
                "second_half_wr": sh_wr,
                "direction": direction,
            }

        base.update({
            "trading_days": trading_days,
            "avg_trades_per_day": avg_trades_per_day,
            "weekly_trends": weekly_trends,
            "trend_direction": trend_direction,
            "strategy_evolution": strategy_evolution,
        })
        return base

    def _format_no_trades_monthly(self, year: int, month: int) -> str:
        return f"""=== MONTHLY SUMMARY: {year}-{month:02d} ===

PERFORMANCE:
No trades this month.

STATUS: Waiting for market opportunities.
"""

    def _generate_rule_based_monthly_summary(
        self,
        year: int,
        month: int,
        trades: List[TradeRecord],
        metrics: Dict[str, Any],
    ) -> str:
        pf_str = f"{metrics['profit_factor']:.2f}" if metrics['profit_factor'] != float("inf") else "INF"

        summary = f"""=== MONTHLY SUMMARY: {year}-{month:02d} ===

PERFORMANCE:
Trades: {metrics['total']} | Winners: {metrics['winners']} | Losers: {metrics['losers']}
Net P&L: ${metrics['total_pnl']:.2f} | Win Rate: {metrics['win_rate']:.1f}% | Avg R: {metrics['avg_r']:.2f} | Profit Factor: {pf_str}
Trading Days: {metrics['trading_days']} | Avg Trades/Day: {metrics['avg_trades_per_day']:.1f}

"""

        # Weekly trends
        if metrics["weekly_trends"]:
            summary += "WEEKLY TRENDS:\n"
            for wt in metrics["weekly_trends"]:
                summary += (
                    f"- Week {wt['week']} ({wt['start']} to {wt['end']}): "
                    f"{wt['trades']} trades, WR {wt['win_rate']:.1f}%, P&L ${wt['pnl']:.2f}\n"
                )
            summary += f"- Trend: {metrics['trend_direction']}\n\n"

        # Strategy breakdown
        if metrics["strategy_breakdown"]:
            summary += "STRATEGY BREAKDOWN:\n"
            for strat, stats in metrics["strategy_breakdown"].items():
                flag = ""
                if stats["win_rate"] >= 60:
                    flag = " [STRONG]"
                elif stats["win_rate"] <= 35:
                    flag = " [WEAK]"
                summary += (
                    f"- {strat}: {stats['total']} trades, "
                    f"{stats['winners']} wins, "
                    f"WR {stats['win_rate']:.1f}%, "
                    f"P&L ${stats['total_pnl']:.2f}{flag}\n"
                )
            summary += "\n"

        # Strategy evolution
        if metrics["strategy_evolution"]:
            summary += "STRATEGY EVOLUTION:\n"
            for strat, evo in metrics["strategy_evolution"].items():
                summary += (
                    f"- {strat}: 1st half WR {evo['first_half_wr']:.1f}% "
                    f"({evo['first_half_trades']} trades) -> "
                    f"2nd half WR {evo['second_half_wr']:.1f}% "
                    f"({evo['second_half_trades']} trades) "
                    f"[{evo['direction']}]\n"
                )
            summary += "\n"

        # Session patterns
        if metrics["session_patterns"]:
            summary += "SESSION PATTERNS:\n"
            for sess, stats in metrics["session_patterns"].items():
                summary += (
                    f"- {sess}: {stats['total']} trades, "
                    f"WR {stats['win_rate']:.1f}%, "
                    f"P&L ${stats['total_pnl']:.2f}\n"
                )
            summary += "\n"

        # Key observations
        observations = []
        if metrics["trend_direction"] == "improving":
            observations.append("Win rate trending upward across weeks — adaptation working.")
        elif metrics["trend_direction"] == "declining":
            observations.append("Win rate declining across weeks — review for regime change.")

        for strat, evo in metrics["strategy_evolution"].items():
            if evo["direction"] == "declining" and evo["first_half_trades"] >= 3:
                observations.append(f"Strategy '{strat}' declining ({evo['first_half_wr']:.0f}% -> {evo['second_half_wr']:.0f}%) — reassess.")

        if metrics["win_rate"] > 55:
            observations.append(f"Solid monthly win rate ({metrics['win_rate']:.1f}%) — maintain discipline.")
        elif metrics["win_rate"] < 40:
            observations.append(f"Low monthly win rate ({metrics['win_rate']:.1f}%) — major review needed.")

        if observations:
            summary += "KEY OBSERVATIONS:\n"
            for obs in observations[:4]:
                summary += f"- {obs}\n"
            summary += "\n"

        # Next month
        summary += "NEXT MONTH:\n"
        if metrics["trend_direction"] == "declining":
            summary += "- Reduce position sizes until trend stabilizes.\n"
        if metrics["win_rate"] < 45:
            summary += "- Focus on highest-conviction setups only.\n"
        for strat, evo in metrics["strategy_evolution"].items():
            if evo["direction"] == "declining" and evo["second_half_wr"] < 35:
                summary += f"- Consider pausing strategy '{strat}'.\n"
        if not observations:
            summary += "- Continue current approach. More data needed.\n"

        return summary

    def _generate_llm_monthly_summary(
        self,
        year: int,
        month: int,
        trades: List[TradeRecord],
        metrics: Dict[str, Any],
        llm_provider: Callable[..., str],
    ) -> str:
        trades_json = json.dumps(
            [t.model_dump() for t in trades], indent=2, default=str
        )

        prompt = f"""你是一個交易反思引擎。分析以下一個月的交易紀錄，產出結構化的月摘要。

## 輸入
{trades_json}

## 輸出格式（嚴格遵守）
=== MONTHLY SUMMARY: {year}-{month:02d} ===

PERFORMANCE:
Trades: {metrics['total']} | Winners: {metrics['winners']} | Losers: {metrics['losers']}
Net P&L: ${metrics['total_pnl']:.2f} | Win Rate: {metrics['win_rate']:.1f}%

WEEKLY TRENDS:
- [每週交易數/勝率/P&L，趨勢方向]

STRATEGY BREAKDOWN:
- [每個策略的詳細表現]

STRATEGY EVOLUTION:
- [前半月 vs 後半月 的策略表現變化]

KEY OBSERVATIONS:
- [最多4條，月度級別的洞察]

NEXT MONTH:
- [策略性建議]

## 規則
- 不要廢話，不要鼓勵性語言
- 只寫有數據支撐的觀察
- 著重月度趨勢和策略演化
"""

        try:
            response = llm_provider("claude-sonnet-4-5", prompt)
            if self._validate_monthly_llm_output(response, year, month):
                return response
            return self._generate_rule_based_monthly_summary(year, month, trades, metrics) + \
                   "\n(LLM output failed validation, using rule-based fallback)\n"
        except Exception as e:
            return self._generate_rule_based_monthly_summary(year, month, trades, metrics) + \
                   f"\n(LLM failed: {str(e)}, using rule-based fallback)\n"

    def _validate_monthly_llm_output(self, output: str, year: int, month: int) -> bool:
        """Validate monthly LLM output (DEC-010 pattern)."""
        if not output or len(output) < 80:
            return False

        required = [
            f"=== MONTHLY SUMMARY: {year}-{month:02d} ===",
            "PERFORMANCE:",
            "Trades:",
            "Win Rate:",
        ]
        for section in required:
            if section not in output:
                return False

        optional = ["WEEKLY TRENDS:", "STRATEGY BREAKDOWN:", "KEY OBSERVATIONS:", "NEXT MONTH:"]
        if sum(1 for s in optional if s in output) < 2:
            return False

        return True
