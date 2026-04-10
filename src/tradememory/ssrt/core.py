"""mSPRT engine for sequential strategy retirement testing."""

from __future__ import annotations

import math
from typing import Any

from tradememory.ssrt.models import SSRTVerdict


class MixtureSPRT:
    """Mixture Sequential Probability Ratio Test with always-valid p-values.

    Uses a Gaussian mixing distribution over the alternative hypothesis,
    yielding a closed-form likelihood ratio that can be updated incrementally.

    Reference: Johari et al. 2017, "Peeking at A/B Tests".

    Args:
        alpha: Significance level (Type I error rate).
        tau: Mixing distribution scale. Controls sensitivity:
            small tau = detect small effects (more trades needed),
            large tau = detect large effects (fewer trades).
        sigma: Assumed observation std (estimated from history).
        null_mean: Baseline mean under H0 (regime-dependent).
        burn_in: Minimum trades before making decisions.
    """

    def __init__(
        self,
        alpha: float = 0.05,
        tau: float = 1.0,
        sigma: float = 1.5,
        null_mean: float = 0.0,
        burn_in: int = 20,
    ):
        if alpha <= 0 or alpha >= 1:
            raise ValueError("alpha must be in (0, 1)")
        if tau <= 0:
            raise ValueError("tau must be positive")
        if sigma <= 0:
            raise ValueError("sigma must be positive")
        if burn_in < 0:
            raise ValueError("burn_in must be non-negative")

        self.alpha = alpha
        self.tau = tau
        self.sigma = sigma
        self.null_mean = null_mean
        self.burn_in = burn_in

        # Running statistics (O(1) updates)
        self.n: int = 0
        self.sum_z: float = 0.0
        self.sum_z_sq: float = 0.0
        self._log_lambda: float = 0.0

    def update(self, observation: float) -> SSRTVerdict:
        """Process one trade return, update statistics, return verdict.

        Args:
            observation: Trade R-multiple (NOT shifted -- we shift
                internally by null_mean).

        Returns:
            SSRTVerdict with decision, p-value, and diagnostics.
        """
        z = observation - self.null_mean
        self.n += 1
        self.sum_z += z
        self.sum_z_sq += z * z

        # Compute log-Lambda using the mixture formula
        z_bar = self.sum_z / self.n
        sigma_sq = self.sigma ** 2
        tau_sq = self.tau ** 2
        n = self.n

        # log(Lambda_n) = -0.5 * log(1 + n*tau^2/sigma^2)
        #               + n^2*tau^2*z_bar^2 / (2*sigma^2*(sigma^2 + n*tau^2))
        ratio = n * tau_sq / sigma_sq
        log_lambda = (
            -0.5 * math.log(1.0 + ratio)
            + (n * n * tau_sq * z_bar * z_bar)
            / (2.0 * sigma_sq * (sigma_sq + n * tau_sq))
        )
        self._log_lambda = log_lambda

        # Convert to Lambda and p-value
        # Clamp log_lambda to avoid overflow
        lambda_n = math.exp(min(log_lambda, 500.0))
        p_value = 1.0 / max(1.0, lambda_n)

        # One-sided: only consider retirement when mean is BELOW null
        # (strategy performing worse than baseline). When z_bar >= 0,
        # the strategy is at or above baseline — no evidence of decay.
        if z_bar >= 0:
            lambda_n = 1.0
            p_value = 1.0

        # Decision
        if self.n < self.burn_in:
            decision = "INCONCLUSIVE"
        elif p_value < self.alpha:
            decision = "RETIRE"
        else:
            decision = "CONTINUE"

        return SSRTVerdict(
            decision=decision,
            p_value=p_value,
            lambda_n=lambda_n,
            trades_analyzed=self.n,
            regime="unknown",  # caller sets this
            null_mean=self.null_mean,
        )

    def shift_null(self, new_null_mean: float, new_sigma: float | None = None) -> None:
        """Adjust null hypothesis without resetting accumulated evidence.

        Shifts the running statistics to account for a new baseline mean.
        This preserves accumulated evidence (n, sum_z, log_lambda) while
        adjusting for the regime-dependent null.

        Option B approach: when regime changes, we don't lose evidence.

        Args:
            new_null_mean: New baseline mean for null hypothesis.
            new_sigma: New observation std (if None, keep current).
        """
        if self.n == 0:
            # No evidence to preserve — just update parameters
            self.null_mean = new_null_mean
            if new_sigma is not None:
                if new_sigma <= 0:
                    raise ValueError("sigma must be positive")
                self.sigma = new_sigma
            return

        delta = self.null_mean - new_null_mean  # old - new

        # Adjust running statistics
        self.sum_z_sq += 2.0 * delta * self.sum_z + self.n * delta * delta
        self.sum_z += self.n * delta

        # Update null
        self.null_mean = new_null_mean
        if new_sigma is not None:
            if new_sigma <= 0:
                raise ValueError("sigma must be positive")
            self.sigma = new_sigma

        # Recalculate log_lambda from adjusted statistics
        z_bar = self.sum_z / self.n
        sigma_sq = self.sigma ** 2
        tau_sq = self.tau ** 2
        n = self.n
        ratio = n * tau_sq / sigma_sq
        self._log_lambda = (
            -0.5 * math.log(1.0 + ratio)
            + (n * n * tau_sq * z_bar * z_bar)
            / (2.0 * sigma_sq * (sigma_sq + n * tau_sq))
        )

    def reset(self, null_mean: float = 0.0, sigma: float | None = None):
        """Reset state (e.g. when regime changes).

        Args:
            null_mean: New baseline mean for null hypothesis.
            sigma: New observation std (if None, keep current).
        """
        self.null_mean = null_mean
        if sigma is not None:
            if sigma <= 0:
                raise ValueError("sigma must be positive")
            self.sigma = sigma
        self.n = 0
        self.sum_z = 0.0
        self.sum_z_sq = 0.0
        self._log_lambda = 0.0

    def get_state(self) -> dict[str, Any]:
        """Serialize for persistence."""
        return {
            "alpha": self.alpha,
            "tau": self.tau,
            "sigma": self.sigma,
            "null_mean": self.null_mean,
            "burn_in": self.burn_in,
            "n": self.n,
            "sum_z": self.sum_z,
            "sum_z_sq": self.sum_z_sq,
            "log_lambda": self._log_lambda,
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> MixtureSPRT:
        """Restore from serialized state."""
        obj = cls(
            alpha=state["alpha"],
            tau=state["tau"],
            sigma=state["sigma"],
            null_mean=state["null_mean"],
            burn_in=state["burn_in"],
        )
        obj.n = state["n"]
        obj.sum_z = state["sum_z"]
        obj.sum_z_sq = state["sum_z_sq"]
        obj._log_lambda = state["log_lambda"]
        return obj
