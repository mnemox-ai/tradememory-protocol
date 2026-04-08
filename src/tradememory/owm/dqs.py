"""Decision Quality Score (DQS) Engine — process-oriented pre-trade evaluation.

Unlike the Legitimacy Gate (which uses hard-coded thresholds), DQS measures
the quality of the *decision process* and can learn optimal weights from
historical data via calibrate().

Five factors, each 0-2, total 0-10:
  1. Regime Match — strategy win rate in current regime vs overall
  2. Position Sizing — proposed lot vs Kelly fraction
  3. Process Adherence — similarity to past successful trades (OWM score)
  4. Risk State — drawdown, consecutive losses, confidence
  5. Historical Pattern — average pnl_r of similar past trades
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class DQSResult:
    """Result of a Decision Quality Score computation."""

    score: float  # 0-10
    factors: Dict[str, Dict[str, Any]]  # {name: {score, max, description}}
    tier: str  # "go" (>=7), "proceed" (5-7), "caution" (3-5), "skip" (<3)
    position_multiplier: float  # 1.0, 0.7, 0.3, 0.0
    recommendation: str


class DQSEngine:
    """Compute Decision Quality Scores from memory layers.

    Args:
        db: Database instance for querying memory layers.
        weights: Optional learned weights (from calibrate). Default: equal.
    """

    def __init__(self, db: Any, weights: Optional[List[float]] = None) -> None:
        self.db = db
        # 5 weights, default equal (each factor already 0-2)
        self.weights = weights or [1.0, 1.0, 1.0, 1.0, 1.0]

    # ------------------------------------------------------------------
    # Factor 1: Regime Match (0-2)
    # ------------------------------------------------------------------

    def _regime_match(
        self, strategy: str, current_regime: Optional[str]
    ) -> Tuple[float, str]:
        """Score based on strategy performance in current regime."""
        if not current_regime:
            return 1.0, "No regime specified — neutral score"

        # All trades for this strategy
        all_trades = self.db.query_episodic(strategy=strategy, limit=10000)
        if not all_trades:
            return 1.0, "No history — neutral score"

        total = len(all_trades)
        wins_total = sum(1 for t in all_trades if (t.get("pnl") or 0) > 0)
        overall_wr = wins_total / total if total > 0 else 0.5

        # Trades in current regime
        regime_trades = self.db.query_episodic(
            strategy=strategy, regime=current_regime, limit=10000
        )
        regime_count = len(regime_trades)

        if regime_count == 0:
            return 1.0, f"No trades in '{current_regime}' regime — neutral (not penalized)"

        regime_wins = sum(1 for t in regime_trades if (t.get("pnl") or 0) > 0)
        regime_wr = regime_wins / regime_count

        if overall_wr <= 0:
            ratio = 1.0
        else:
            ratio = regime_wr / overall_wr

        # 2.0 if regime_wr >= overall_wr, scale down proportionally
        score = min(2.0, 2.0 * ratio)
        score = max(0.0, score)

        desc = (
            f"Regime '{current_regime}': WR={regime_wr:.0%} "
            f"({regime_count} trades) vs overall WR={overall_wr:.0%}"
        )
        return score, desc

    # ------------------------------------------------------------------
    # Factor 2: Position Sizing (0-2)
    # ------------------------------------------------------------------

    def _position_sizing(
        self, strategy: str, symbol: str, proposed_lot: float
    ) -> Tuple[float, str]:
        """Score based on proposed lot vs Kelly fraction."""
        procs = self.db.query_procedural(strategy=strategy, symbol=symbol, limit=1)
        if not procs:
            return 1.0, "No procedural memory — neutral score"

        proc = procs[0]
        kelly = proc.get("kelly_fraction_suggested")
        if not kelly or kelly <= 0:
            return 1.0, "No Kelly fraction available — neutral score"

        deviation = abs(proposed_lot - kelly) / kelly

        # Continuous: exponential decay from 2.0 as deviation grows
        # deviation=0 → 2.0, deviation=0.5 → ~1.2, deviation=2.0 → ~0.04
        score = 2.0 * math.exp(-1.5 * deviation)
        score = max(0.0, min(2.0, score))

        desc = f"Proposed={proposed_lot:.3f}, Kelly={kelly:.3f}, deviation={deviation:.1%}"
        return score, desc

    # ------------------------------------------------------------------
    # Factor 3: Process Adherence (0-2)
    # ------------------------------------------------------------------

    def _process_adherence(
        self,
        strategy: str,
        symbol: str,
        context_regime: Optional[str],
        context_atr_d1: Optional[float],
        market_context: str,
    ) -> Tuple[float, str]:
        """Score based on OWM similarity to past successful trades."""
        from .context import ContextVector
        from .recall import outcome_weighted_recall

        # Build query context
        query = ContextVector(
            symbol=symbol,
            regime=context_regime,
            atr_d1=context_atr_d1,
        )

        # Get episodic memories for this strategy
        episodes = self.db.query_episodic(strategy=strategy, limit=100)
        if not episodes:
            return 1.0, "No episodic memory — neutral score"

        # Convert to format expected by OWM recall
        memories = []
        for ep in episodes:
            ctx_json = ep.get("context_json")
            if isinstance(ctx_json, str):
                try:
                    ctx_json = json.loads(ctx_json)
                except (json.JSONDecodeError, TypeError):
                    ctx_json = {}
            elif ctx_json is None:
                ctx_json = {}

            mem = {
                "id": ep.get("id", ""),
                "type": "episodic",
                "pnl_r": ep.get("pnl_r"),
                "confidence": ep.get("confidence", 0.5),
                "timestamp": ep.get("timestamp", ""),
                "context": ctx_json,
            }
            memories.append(mem)

        if not memories:
            return 1.0, "No valid memories — neutral score"

        # Run OWM recall
        scored = outcome_weighted_recall(query, memories, limit=3)

        if not scored:
            return 0.5, "No similar trades found — low but not penalized"

        avg_score = sum(m.score for m in scored) / len(scored)

        # Continuous: linear map [0, 0.7] → [0.5, 2.0], clamped
        factor_score = 0.5 + (avg_score / 0.7) * 1.5
        factor_score = max(0.0, min(2.0, factor_score))

        desc = f"Top {len(scored)} matches avg OWM score={avg_score:.3f}"
        return factor_score, desc

    # ------------------------------------------------------------------
    # Factor 4: Risk State (0-2)
    # ------------------------------------------------------------------

    def _risk_state(self) -> Tuple[float, str]:
        """Score based on current affective state."""
        state = self.db.load_affective()
        if state is None:
            return 1.0, "No affective state — neutral score"

        dd = state.get("drawdown_state", 0.0) * 100  # 0-1 → 0-100
        losses = state.get("consecutive_losses", 0)
        conf = state.get("confidence_level", 0.5)

        # Hard stops
        if dd > 20.0 or losses > 4:
            desc = f"DANGER: dd={dd:.1f}%, losses={losses}, conf={conf:.2f}"
            return 0.0, desc

        # Good conditions
        score = 2.0
        reasons = []

        if dd >= 5.0:
            score -= 0.5
            reasons.append(f"dd={dd:.1f}%")
        if dd >= 10.0:
            score -= 0.5
            reasons.append(f"high dd")

        if losses >= 2:
            score -= 0.3
            reasons.append(f"{losses} consecutive losses")
        if losses >= 3:
            score -= 0.3

        if conf < 0.6:
            score -= 0.4
            reasons.append(f"low conf={conf:.2f}")

        score = max(0.0, score)
        desc = ", ".join(reasons) if reasons else f"Good: dd={dd:.1f}%, losses={losses}, conf={conf:.2f}"
        return score, desc

    # ------------------------------------------------------------------
    # Factor 5: Historical Pattern (0-2)
    # ------------------------------------------------------------------

    def _historical_pattern(
        self,
        strategy: str,
        symbol: str,
        context_regime: Optional[str],
        context_atr_d1: Optional[float],
    ) -> Tuple[float, str]:
        """Score based on average pnl_r of similar past trades."""
        from .context import ContextVector
        from .recall import outcome_weighted_recall

        query = ContextVector(
            symbol=symbol,
            regime=context_regime,
            atr_d1=context_atr_d1,
        )

        episodes = self.db.query_episodic(strategy=strategy, limit=200)
        if not episodes:
            return 1.0, "No history — neutral score"

        memories = []
        for ep in episodes:
            ctx_json = ep.get("context_json")
            if isinstance(ctx_json, str):
                try:
                    ctx_json = json.loads(ctx_json)
                except (json.JSONDecodeError, TypeError):
                    ctx_json = {}
            elif ctx_json is None:
                ctx_json = {}

            mem = {
                "id": ep.get("id", ""),
                "type": "episodic",
                "pnl_r": ep.get("pnl_r"),
                "confidence": ep.get("confidence", 0.5),
                "timestamp": ep.get("timestamp", ""),
                "context": ctx_json,
            }
            memories.append(mem)

        scored = outcome_weighted_recall(query, memories, limit=5)
        if not scored:
            return 1.0, "Insufficient similar trades — neutral"

        pnl_rs = [m.data.get("pnl_r") for m in scored if m.data.get("pnl_r") is not None]
        if not pnl_rs:
            return 1.0, "No pnl_r data in matches — neutral"

        avg_pnl_r = sum(pnl_rs) / len(pnl_rs)

        # Continuous: sigmoid-like mapping centered at 0
        # avg_pnl_r = -1 → ~0.2, avg_pnl_r = 0 → 1.0, avg_pnl_r = 1 → ~1.8
        factor_score = 1.0 + math.tanh(avg_pnl_r) * 1.0
        factor_score = max(0.0, min(2.0, factor_score))

        desc = f"Top {len(pnl_rs)} similar trades avg pnl_r={avg_pnl_r:.3f}"
        return factor_score, desc

    # ------------------------------------------------------------------
    # Main compute
    # ------------------------------------------------------------------

    def compute(
        self,
        symbol: str,
        strategy_name: str,
        direction: str,
        proposed_lot_size: float = 0.1,
        market_context: str = "",
        context_regime: Optional[str] = None,
        context_atr_d1: Optional[float] = None,
    ) -> DQSResult:
        """Compute Decision Quality Score.

        Returns DQSResult with score (0-10), factor breakdown, tier, and
        position_multiplier.
        """
        # Compute each factor
        f1_score, f1_desc = self._regime_match(strategy_name, context_regime)
        f2_score, f2_desc = self._position_sizing(strategy_name, symbol, proposed_lot_size)
        f3_score, f3_desc = self._process_adherence(
            strategy_name, symbol, context_regime, context_atr_d1, market_context
        )
        f4_score, f4_desc = self._risk_state()
        f5_score, f5_desc = self._historical_pattern(
            strategy_name, symbol, context_regime, context_atr_d1
        )

        raw_scores = [f1_score, f2_score, f3_score, f4_score, f5_score]

        # Apply weights
        weighted_sum = sum(s * w for s, w in zip(raw_scores, self.weights))
        weight_total = sum(self.weights)
        # Normalize to 0-10 scale (max raw = 2 per factor)
        if weight_total > 0:
            score = (weighted_sum / weight_total) * 5.0  # *5 because max per factor is 2
        else:
            score = 5.0

        score = max(0.0, min(10.0, score))

        # Tier (4-level)
        if score >= 7.0:
            tier = "go"
            multiplier = 1.0
        elif score >= 5.0:
            tier = "proceed"
            multiplier = 0.7
        elif score >= 3.0:
            tier = "caution"
            multiplier = 0.3
        else:
            tier = "skip"
            multiplier = 0.0

        factors = {
            "regime_match": {"score": round(f1_score, 3), "max": 2.0, "description": f1_desc},
            "position_sizing": {"score": round(f2_score, 3), "max": 2.0, "description": f2_desc},
            "process_adherence": {"score": round(f3_score, 3), "max": 2.0, "description": f3_desc},
            "risk_state": {"score": round(f4_score, 3), "max": 2.0, "description": f4_desc},
            "historical_pattern": {"score": round(f5_score, 3), "max": 2.0, "description": f5_desc},
        }

        recommendation = self._build_recommendation(
            strategy_name, score, tier, factors
        )

        return DQSResult(
            score=round(score, 2),
            factors=factors,
            tier=tier,
            position_multiplier=multiplier,
            recommendation=recommendation,
        )

    def _build_recommendation(
        self, strategy: str, score: float, tier: str, factors: dict
    ) -> str:
        """Build human-readable recommendation."""
        if tier == "go":
            return f"{strategy}: DQS {score:.1f}/10 — process checks passed, proceed at full size."

        warnings = []
        for name, info in factors.items():
            if info["score"] < 1.0:
                warnings.append(f"{name} ({info['score']:.1f}/2)")

        warning_text = ", ".join(warnings) if warnings else "multiple factors below threshold"

        if tier == "proceed":
            return (
                f"{strategy}: DQS {score:.1f}/10 — proceed at 70% size. "
                f"Weak: {warning_text}."
            )
        if tier == "caution":
            return (
                f"{strategy}: DQS {score:.1f}/10 — caution, 30% size only. "
                f"Weak: {warning_text}."
            )
        return (
            f"{strategy}: DQS {score:.1f}/10 — skip this trade. "
            f"Weak: {warning_text}."
        )

    # ------------------------------------------------------------------
    # Calibrate — learn weights from historical data
    # ------------------------------------------------------------------

    def calibrate(self, min_trades: int = 50) -> dict:
        """Learn factor weights from historical trade outcomes.

        Runs logistic regression (gradient descent) on retroactively computed
        DQS factors vs win/loss outcomes. No external dependencies — pure
        Python + math module.

        Args:
            min_trades: Minimum trades required for calibration.

        Returns:
            Dict with learned_weights, r_squared, sample_size, and status.
        """
        all_trades = self.db.query_episodic(limit=100000)
        if len(all_trades) < min_trades:
            return {
                "status": "insufficient_data",
                "sample_size": len(all_trades),
                "min_required": min_trades,
                "learned_weights": None,
            }

        # Build feature matrix X and labels y
        X: List[List[float]] = []
        y: List[float] = []

        for trade in all_trades:
            pnl = trade.get("pnl")
            if pnl is None:
                continue

            strategy = trade.get("strategy", "")
            regime = trade.get("context_regime")
            symbol_val = "XAUUSD"  # Default; context_json may have it
            ctx = trade.get("context_json")
            if isinstance(ctx, str):
                try:
                    ctx = json.loads(ctx)
                except (json.JSONDecodeError, TypeError):
                    ctx = {}
            elif ctx is None:
                ctx = {}
            if ctx.get("symbol"):
                symbol_val = ctx["symbol"]

            # Retroactively compute factors (simplified — skip OWM recall)
            f1, _ = self._regime_match(strategy, regime)
            f2 = 1.0  # Can't retroactively know proposed lot
            f3 = 1.0  # Skip OWM recall for speed
            f4, _ = self._risk_state()
            f5 = 1.0  # Skip OWM recall for speed

            X.append([f1, f2, f3, f4, f5])
            y.append(1.0 if pnl > 0 else 0.0)

        if len(X) < min_trades:
            return {
                "status": "insufficient_valid_data",
                "sample_size": len(X),
                "min_required": min_trades,
                "learned_weights": None,
            }

        # Logistic regression via gradient descent
        weights = self._logistic_regression(X, y, lr=0.01, epochs=200)

        # Compute pseudo R-squared (McFadden)
        ll_model = self._log_likelihood(X, y, weights)
        # Null model: intercept only (all weights = 0)
        ll_null = self._log_likelihood(X, y, [0.0] * len(weights))
        r_squared = 1.0 - (ll_model / ll_null) if ll_null != 0 else 0.0

        # Normalize weights to be positive and sum-preserving
        min_w = min(weights)
        shifted = [w - min_w + 0.1 for w in weights]
        total = sum(shifted)
        normalized = [w / total * 5.0 for w in shifted]  # Scale to sum=5

        self.weights = normalized

        return {
            "status": "calibrated",
            "sample_size": len(X),
            "learned_weights": {
                "regime_match": round(normalized[0], 4),
                "position_sizing": round(normalized[1], 4),
                "process_adherence": round(normalized[2], 4),
                "risk_state": round(normalized[3], 4),
                "historical_pattern": round(normalized[4], 4),
            },
            "r_squared": round(r_squared, 4),
            "raw_coefficients": [round(w, 4) for w in weights],
        }

    @staticmethod
    def _sigmoid(x: float) -> float:
        """Numerically stable sigmoid."""
        if x >= 0:
            return 1.0 / (1.0 + math.exp(-x))
        ex = math.exp(x)
        return ex / (1.0 + ex)

    def _logistic_regression(
        self,
        X: List[List[float]],
        y: List[float],
        lr: float = 0.01,
        epochs: int = 200,
    ) -> List[float]:
        """Simple logistic regression via gradient descent. No dependencies."""
        n_features = len(X[0])
        weights = [0.0] * n_features
        n = len(X)

        for _ in range(epochs):
            gradients = [0.0] * n_features
            for i in range(n):
                z = sum(X[i][j] * weights[j] for j in range(n_features))
                pred = self._sigmoid(z)
                error = pred - y[i]
                for j in range(n_features):
                    gradients[j] += error * X[i][j]

            for j in range(n_features):
                weights[j] -= lr * (gradients[j] / n)

        return weights

    def _log_likelihood(
        self,
        X: List[List[float]],
        y: List[float],
        weights: List[float],
    ) -> float:
        """Compute log-likelihood for logistic regression."""
        ll = 0.0
        eps = 1e-15
        for i in range(len(X)):
            z = sum(X[i][j] * weights[j] for j in range(len(weights)))
            p = self._sigmoid(z)
            p = max(eps, min(1 - eps, p))
            ll += y[i] * math.log(p) + (1 - y[i]) * math.log(1 - p)
        return ll
