"""
Dashboard service — business logic layer.

Computes derived metrics (win_rate, profit_factor, max_drawdown_pct)
from raw repository data. No direct DB access.
"""

import json
import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import List, Optional

from ..exceptions import StrategyNotFoundError
from ..repositories.trade import TradeRepository, TradeRow

logger = logging.getLogger(__name__)

KNOWN_REGIMES = ("trending_up", "trending_down", "ranging", "volatile", "unknown")

BATCH_001_BASELINES = {
    "VolBreakout": {"pf": 1.17, "wr": 0.55},
    "IntradayMomentum": {"pf": 1.78, "wr": 0.58},
    "Pullback": {"pf": 1.45, "wr": 0.52},
}


class DashboardService:
    """Business logic for dashboard endpoints."""

    def __init__(self, repo: TradeRepository):
        self._repo = repo

    def get_overview(self) -> dict:
        """
        Compute overview metrics from trade, memory, and equity data.

        Returns a dict matching OverviewResponse schema.
        """
        trade_stats = self._repo.get_trade_stats()
        memory_stats = self._repo.get_memory_stats()
        equity_stats = self._repo.get_equity_stats()

        # Compute derived metrics
        win_rate = 0.0
        if trade_stats.total_trades > 0:
            win_rate = round(trade_stats.win_count / trade_stats.total_trades, 4)

        profit_factor = 0.0
        if trade_stats.gross_loss > 0:
            profit_factor = round(
                trade_stats.gross_profit / trade_stats.gross_loss, 4
            )
        elif trade_stats.gross_profit > 0:
            # All wins, no losses
            profit_factor = float("inf")

        # max_drawdown_pct from affective_state drawdown_state
        max_drawdown_pct = round(equity_stats.drawdown_state * 100, 2)

        return {
            "total_trades": trade_stats.total_trades,
            "total_pnl": round(trade_stats.total_pnl, 2),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "current_equity": round(equity_stats.current_equity, 2),
            "max_drawdown_pct": max_drawdown_pct,
            "memory_count": memory_stats.memory_count,
            "avg_confidence": memory_stats.avg_confidence,
            "last_trade_date": trade_stats.last_trade_date,
            "strategies": trade_stats.strategies,
        }

    def get_equity_curve(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> List[dict]:
        """
        Compute equity curve from closed trades.

        Groups by date. Computes cumulative PnL and drawdown_pct per day.
        """
        trades = self._repo.get_closed_trades(
            start_date=start_date, end_date=end_date, strategy=strategy
        )
        if not trades:
            return []

        # Group trades by date (YYYY-MM-DD)
        daily: dict[str, list[TradeRow]] = defaultdict(list)
        for t in trades:
            date_str = t.timestamp[:10]
            daily[date_str].append(t)

        cumulative_pnl = 0.0
        peak = 0.0
        result = []

        for date_str in sorted(daily.keys()):
            day_trades = daily[date_str]
            for t in day_trades:
                cumulative_pnl += t.pnl
                if cumulative_pnl > peak:
                    peak = cumulative_pnl

            drawdown_pct = 0.0
            if peak > 0:
                drawdown_pct = round((peak - cumulative_pnl) / peak * 100, 2)

            result.append({
                "date": date_str,
                "cumulative_pnl": round(cumulative_pnl, 2),
                "drawdown_pct": drawdown_pct,
                "trade_count": len(day_trades),
            })

        return result

    def get_rolling_metrics(
        self,
        window_size: int = 10,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> List[dict]:
        """
        Compute rolling window metrics over closed trades.

        For each trade after the first `window_size` trades, compute:
        - rolling_pf: sum(positive pnl) / abs(sum(negative pnl))
        - rolling_wr: wins / total in window
        - rolling_avg_r: mean(pnl_r) in window (0.0 if pnl_r is None)
        Groups output by date (last trade date in window).
        """
        trades = self._repo.get_closed_trades(
            start_date=start_date, end_date=end_date, strategy=strategy
        )
        if len(trades) < window_size:
            return []

        result = []
        for i in range(window_size, len(trades) + 1):
            window = trades[i - window_size : i]
            last_trade = window[-1]
            date_str = last_trade.timestamp[:10]

            wins = sum(1 for t in window if t.pnl > 0)
            gross_profit = sum(t.pnl for t in window if t.pnl > 0)
            gross_loss = abs(sum(t.pnl for t in window if t.pnl < 0))

            rolling_pf = 0.0
            if gross_loss > 0:
                rolling_pf = round(gross_profit / gross_loss, 4)
            elif gross_profit > 0:
                rolling_pf = 9999.99  # All wins, no losses (JSON-safe sentinel)

            rolling_wr = round(wins / window_size, 4)

            pnl_r_values = [t.pnl_r for t in window if t.pnl_r is not None]
            rolling_avg_r = 0.0
            if pnl_r_values:
                rolling_avg_r = round(sum(pnl_r_values) / len(pnl_r_values), 4)

            result.append({
                "date": date_str,
                "rolling_pf": rolling_pf,
                "rolling_wr": rolling_wr,
                "rolling_avg_r": rolling_avg_r,
                "window_size": window_size,
            })

        return result

    def get_memory_growth(self) -> List[dict]:
        """
        Compute memory growth by regime per day.

        Returns daily totals with breakdown by regime category.
        """
        rows = self._repo.get_memory_growth_by_regime()
        if not rows:
            return []

        # Group by date
        daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for r in rows:
            regime = r.regime if r.regime in KNOWN_REGIMES else "unknown"
            daily[r.date][regime] += r.count

        result = []
        cumulative = 0
        for date_str in sorted(daily.keys()):
            regimes = daily[date_str]
            day_total = sum(regimes.values())
            cumulative += day_total
            result.append({
                "date": date_str,
                "total_memories": cumulative,
                "trending_up": regimes.get("trending_up", 0),
                "trending_down": regimes.get("trending_down", 0),
                "ranging": regimes.get("ranging", 0),
                "volatile": regimes.get("volatile", 0),
                "unknown": regimes.get("unknown", 0),
            })

        return result

    def get_confidence_calibration(self) -> List[dict]:
        """
        Get confidence calibration data from episodic memory.

        Returns list of {trade_id, entry_confidence, actual_pnl_r, strategy}.
        """
        rows = self._repo.get_calibration_data()
        return [
            {
                "trade_id": r.trade_id,
                "entry_confidence": round(r.entry_confidence, 4),
                "actual_pnl_r": round(r.actual_pnl_r, 4),
                "strategy": r.strategy,
            }
            for r in rows
        ]

    def get_reflections(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        reviews_dir: Optional[Path] = None,
    ) -> List[dict]:
        """
        Scan daily_reviews directory for markdown reflection files.

        Parses date from filename, grade via regex, strategy mentions,
        and first 200 chars as summary. Returns sorted by date DESC.
        If directory doesn't exist, returns empty list (normal state).
        """
        if reviews_dir is None:
            reviews_dir = Path(__file__).parent.parent.parent.parent / "data" / "daily_reviews"

        if not reviews_dir.exists() or not reviews_dir.is_dir():
            return []

        grade_re = re.compile(r"Grade:\s*([A-F])", re.IGNORECASE)
        strategy_keywords = ["VolBreakout", "IntradayMomentum", "Pullback", "MeanReversion"]

        results = []
        for md_file in reviews_dir.glob("*.md"):
            # Extract date from filename (YYYY-MM-DD.md)
            date_str = md_file.stem
            if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
                continue

            # Apply date filters
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to read reflection {md_file}: {e}")
                continue

            # Parse grade
            grade_match = grade_re.search(content)
            grade = grade_match.group(1).upper() if grade_match else None

            # Parse strategy mentions
            strategy = None
            for kw in strategy_keywords:
                if kw.lower() in content.lower():
                    strategy = kw
                    break

            # Summary: first 200 chars, strip markdown
            summary = content[:200].strip()

            results.append({
                "date": date_str,
                "type": "daily_review",
                "grade": grade,
                "strategy": strategy,
                "summary": summary,
                "full_path": str(md_file),
            })

        results.sort(key=lambda r: r["date"], reverse=True)
        return results

    def get_adjustments(self) -> List[dict]:
        """
        Get strategy adjustments from DB, sorted by created_at DESC.
        """
        rows = self._repo.get_adjustments()
        return [
            {
                "id": r.adjustment_id,
                "timestamp": r.created_at,
                "adjustment_type": r.adjustment_type,
                "parameter": r.parameter,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "reason": r.reason,
                "status": r.status,
                "strategy": r.strategy,
            }
            for r in rows
        ]

    def get_beliefs(self) -> List[dict]:
        """
        Get Bayesian beliefs from semantic_memory.

        Computes confidence = alpha / (alpha + beta).
        Determines trend: improving/declining/stable based on
        last_confirmed vs last_contradicted timestamps.
        """
        rows = self._repo.get_beliefs()
        results = []
        for r in rows:
            # Confidence = mean of Beta distribution
            denom = r.alpha + r.beta
            confidence = round(r.alpha / denom, 4) if denom > 0 else 0.5

            # Trend determination
            if r.last_confirmed is not None and (
                r.last_contradicted is None or r.last_confirmed > r.last_contradicted
            ):
                trend = "improving"
            elif (
                r.last_contradicted is not None
                and r.last_confirmed is not None
                and r.last_contradicted > r.last_confirmed
            ):
                trend = "declining"
            else:
                trend = "stable"

            results.append({
                "id": r.id,
                "proposition": r.proposition,
                "alpha": r.alpha,
                "beta": r.beta,
                "confidence": confidence,
                "strategy": r.strategy,
                "regime": r.regime,
                "sample_size": r.sample_size,
                "trend": trend,
            })
        return results

    def get_dream_results(self, dream_path: Optional[Path] = None) -> List[dict]:
        """
        Load trade-dreaming simulation results from JSON files.

        If path doesn't exist or has no JSON files, returns empty list
        (this is normal — dreaming is Phase 2).
        """
        if dream_path is None:
            dream_path = Path(
                os.environ.get(
                    "DREAM_DATA_PATH",
                    str(Path.home() / "projects" / "trade-dreaming" / "data"),
                )
            )

        if not dream_path.exists() or not dream_path.is_dir():
            return []

        results = []
        for json_file in sorted(dream_path.glob("*.json"), reverse=True):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to parse dream file {json_file}: {e}")
                continue

            # Support both single session and list of sessions
            sessions = data if isinstance(data, list) else [data]
            for sess in sessions:
                try:
                    results.append({
                        "id": sess.get("id", json_file.stem),
                        "timestamp": sess.get("timestamp", ""),
                        "condition": sess.get("condition", "unknown"),
                        "trades": sess.get("trades", 0),
                        "pf": sess.get("pf", 0.0),
                        "pnl": sess.get("pnl", 0.0),
                        "wr": sess.get("wr", 0.0),
                        "has_memory": sess.get("has_memory", False),
                        "memory_type": sess.get("memory_type"),
                        "resonance_detected": sess.get("resonance_detected", False),
                    })
                except Exception as e:
                    logger.warning(f"Failed to parse dream session in {json_file}: {e}")
                    continue

        return results

    def get_strategy_detail(self, name: str) -> dict:
        """
        Compute detailed KPIs for a specific strategy.

        Raises StrategyNotFoundError if no trades exist for the strategy.
        """
        # Validate strategy exists
        known = self._repo.get_distinct_strategies()
        if name not in known:
            raise StrategyNotFoundError(f"Strategy '{name}' not found")

        trades = self._repo.get_strategy_trades(name)
        if not trades:
            raise StrategyNotFoundError(f"Strategy '{name}' has no closed trades")

        total_trades = len(trades)
        wins = sum(1 for t in trades if t.pnl > 0)
        win_rate = round(wins / total_trades, 4) if total_trades > 0 else 0.0

        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        profit_factor = 0.0
        if gross_loss > 0:
            profit_factor = round(gross_profit / gross_loss, 4)
        elif gross_profit > 0:
            profit_factor = 9999.99

        pnl_r_values = [t.pnl_r for t in trades if t.pnl_r is not None]
        avg_pnl_r = round(sum(pnl_r_values) / len(pnl_r_values), 4) if pnl_r_values else 0.0

        hold_values = [t.hold_duration for t in trades if t.hold_duration is not None]
        avg_hold_seconds = int(sum(hold_values) / len(hold_values)) if hold_values else 0

        # Session analysis
        session_pnl: dict[str, list[float]] = defaultdict(list)
        for t in trades:
            sess = t.context_session or "unknown"
            session_pnl[sess].append(t.pnl)

        best_session = "unknown"
        worst_session = "unknown"
        if session_pnl:
            best_session = max(session_pnl, key=lambda s: sum(session_pnl[s]))
            worst_session = min(session_pnl, key=lambda s: sum(session_pnl[s]))

        # Baselines
        baseline = BATCH_001_BASELINES.get(name, {"pf": 0.0, "wr": 0.0})

        # Trade list for frontend
        trade_list = [
            {
                "id": t.id,
                "date": (t.timestamp.strftime("%Y-%m-%d") if hasattr(t.timestamp, "strftime") else str(t.timestamp)[:10]) if t.timestamp else None,
                "timestamp": t.timestamp,
                "side": getattr(t, "direction", "unknown").upper() if getattr(t, "direction", None) else "UNKNOWN",
                "pnl": t.pnl,
                "pnl_r": t.pnl_r if t.pnl_r is not None else 0.0,
                "hold_seconds": t.hold_duration,
                "session": t.context_session,
            }
            for t in trades
        ]

        # Session heatmap: group by (session, day_of_week)
        heatmap: dict[tuple[str, int], list[float]] = defaultdict(list)
        for t in trades:
            sess = t.context_session or "unknown"
            try:
                from datetime import datetime as dt
                parsed = dt.fromisoformat(t.timestamp.replace("Z", "+00:00"))
                dow = parsed.weekday()  # 0=Mon, 6=Sun
            except (ValueError, AttributeError):
                dow = 0
            heatmap[(sess, dow)].append(t.pnl)

        session_heatmap = [
            {
                "session": sess,
                "day_of_week": dow,
                "trade_count": len(pnls),
                "avg_pnl": round(sum(pnls) / len(pnls), 2),
            }
            for (sess, dow), pnls in sorted(heatmap.items())
        ]

        return {
            "name": name,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_pnl_r": avg_pnl_r,
            "avg_hold_seconds": avg_hold_seconds,
            "best_session": best_session,
            "worst_session": worst_session,
            "baseline_pf": baseline["pf"],
            "baseline_wr": baseline["wr"],
            "trades": trade_list,
            "session_heatmap": session_heatmap,
        }
