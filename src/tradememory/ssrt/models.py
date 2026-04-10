"""Data models for SSRT (Sequential Strategy Retirement Testing).

Defines the core dataclasses used across the SSRT module:
TradeResult, SSRTVerdict, RegimeBaseline, and RetirementReport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TradeResult:
    """Single trade outcome for sequential testing.

    Attributes:
        pnl: Raw P&L in account currency.
        pnl_r: R-multiple (risk-adjusted).
        regime: Market regime classification
            ("trending_up" | "trending_down" | "ranging" | "volatile").
        timestamp: ISO-8601 UTC timestamp.
        strategy: Strategy name.
        symbol: Trading symbol, e.g. "XAUUSD".
    """

    pnl: float
    pnl_r: float
    regime: str
    timestamp: str
    strategy: str
    symbol: str


@dataclass
class SSRTVerdict:
    """Result of a single sequential test update.

    Attributes:
        decision: Test outcome ("CONTINUE" | "RETIRE" | "INCONCLUSIVE").
        p_value: Always-valid p-value (1 / max(1, lambda_n)).
        lambda_n: Mixture likelihood ratio.
        trades_analyzed: Cumulative trade count.
        regime: Current regime used for null hypothesis.
        null_mean: Regime-specific null mean (mu_0).
    """

    decision: str
    p_value: float
    lambda_n: float
    trades_analyzed: int
    regime: str
    null_mean: float


@dataclass
class RegimeBaseline:
    """Per-regime performance baseline for null hypothesis.

    Attributes:
        regime: Market regime classification.
        mean_pnl_r: Historical mean R-multiple in this regime.
        std_pnl_r: Historical standard deviation of R-multiples.
        trade_count: Number of trades that formed this baseline.
        last_updated: ISO-8601 UTC timestamp of last update.
    """

    regime: str
    mean_pnl_r: float
    std_pnl_r: float
    trade_count: int
    last_updated: str


@dataclass
class RetirementReport:
    """Full report for strategy retirement analysis.

    Attributes:
        strategy: Strategy name.
        symbol: Trading symbol.
        verdict: Final SSRT verdict.
        regime_baselines: Mapping of regime name to RegimeBaseline.
        baseline_comparison: Comparison with MaxDD, rolling Sharpe, etc.
        history: List of SSRTVerdict snapshots over time.
    """

    strategy: str
    symbol: str
    verdict: SSRTVerdict
    regime_baselines: dict = field(default_factory=dict)
    baseline_comparison: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
