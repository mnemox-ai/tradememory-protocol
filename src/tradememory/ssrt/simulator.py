"""Synthetic trade sequence generator for SSRT experiments."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import numpy as np

from tradememory.ssrt.models import TradeResult


class DecaySimulator:
    """Generate trade sequences with injected decay patterns."""

    @staticmethod
    def _make_trades(
        pnl_rs: list[float],
        regimes: list[str],
        strategy: str = "test_strategy",
        symbol: str = "XAUUSD",
        base_time: str = "2026-01-01T00:00:00Z",
    ) -> list[TradeResult]:
        """Convert arrays of pnl_r and regimes into TradeResult list."""
        base = datetime.fromisoformat(base_time.replace("Z", "+00:00"))
        trades = []
        for i, (pnl_r, regime) in enumerate(zip(pnl_rs, regimes)):
            ts = base + timedelta(hours=i)
            trades.append(TradeResult(
                pnl=float(pnl_r * 100),  # assume $100 per R
                pnl_r=float(pnl_r),
                regime=regime,
                timestamp=ts.isoformat(),
                strategy=strategy,
                symbol=symbol,
            ))
        return trades

    @staticmethod
    def no_decay(
        n_trades: int,
        mean: float = 0.5,
        std: float = 1.5,
        regime: str = "trending_up",
        seed: int | None = None,
    ) -> list[TradeResult]:
        """Control: strategy with stable edge."""
        rng = np.random.default_rng(seed)
        pnl_rs = rng.normal(mean, std, n_trades).tolist()
        regimes = [regime] * n_trades
        return DecaySimulator._make_trades(pnl_rs, regimes)

    @staticmethod
    def sudden_death(
        n_trades: int,
        decay_at: int,
        pre_mean: float = 0.5,
        post_mean: float = -0.3,
        std: float = 1.5,
        regime: str = "trending_up",
        seed: int | None = None,
    ) -> list[TradeResult]:
        """Alpha drops to post_mean at trade #decay_at."""
        rng = np.random.default_rng(seed)
        pnl_rs = []
        for i in range(n_trades):
            mean = pre_mean if i < decay_at else post_mean
            pnl_rs.append(float(rng.normal(mean, std)))
        regimes = [regime] * n_trades
        return DecaySimulator._make_trades(pnl_rs, regimes)

    @staticmethod
    def linear_decay(
        n_trades: int,
        decay_start: int,
        decay_end: int,
        pre_mean: float = 0.5,
        post_mean: float = -0.3,
        std: float = 1.5,
        regime: str = "trending_up",
        seed: int | None = None,
    ) -> list[TradeResult]:
        """Alpha decays linearly from pre_mean to post_mean."""
        rng = np.random.default_rng(seed)
        pnl_rs = []
        for i in range(n_trades):
            if i < decay_start:
                mean = pre_mean
            elif i >= decay_end:
                mean = post_mean
            else:
                frac = (i - decay_start) / (decay_end - decay_start)
                mean = pre_mean + frac * (post_mean - pre_mean)
            pnl_rs.append(float(rng.normal(mean, std)))
        regimes = [regime] * n_trades
        return DecaySimulator._make_trades(pnl_rs, regimes)

    @staticmethod
    def regime_specific_decay(
        n_trades: int,
        decay_at: int,
        decay_regime: str = "trending_up",
        safe_regime: str = "ranging",
        regime_schedule: list[tuple[int, str]] | None = None,
        pre_mean: float = 0.5,
        post_mean: float = -0.3,
        safe_mean: float = 0.3,
        std: float = 1.5,
        seed: int | None = None,
    ) -> list[TradeResult]:
        """Alpha decays only in decay_regime, survives in safe_regime.

        regime_schedule: list of (trade_index, regime) transitions.
        If None, alternates every 25 trades.
        """
        rng = np.random.default_rng(seed)

        if regime_schedule is None:
            regime_schedule = []
            for i in range(0, n_trades, 25):
                r = decay_regime if (i // 25) % 2 == 0 else safe_regime
                regime_schedule.append((i, r))

        # Build regime array
        regimes = []
        current_regime = regime_schedule[0][1] if regime_schedule else decay_regime
        schedule_idx = 0
        for i in range(n_trades):
            while schedule_idx < len(regime_schedule) - 1 and regime_schedule[schedule_idx + 1][0] <= i:
                schedule_idx += 1
            current_regime = regime_schedule[schedule_idx][1]
            regimes.append(current_regime)

        pnl_rs = []
        for i in range(n_trades):
            if regimes[i] == decay_regime:
                mean = pre_mean if i < decay_at else post_mean
            else:
                mean = safe_mean
            pnl_rs.append(float(rng.normal(mean, std)))

        return DecaySimulator._make_trades(pnl_rs, regimes)
