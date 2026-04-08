"""
Bayesian Online Changepoint Detection (Adams & MacKay 2007).

Detects behavioral regime changes in trading agent observations using
conjugate models: Beta-Bernoulli for win/loss, Normal-Inverse-Gamma
for continuous signals (pnl_r, hold_seconds, lot_vs_kelly).

Zero external dependencies — pure Python + math module.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChangePointResult:
    """Result from a single changepoint update step."""

    changepoint_probability: float  # P(r_t = 0 | x_1:t)
    max_run_length: int  # argmax of run length posterior
    observation_count: int
    signal_posteriors: Dict[str, Dict[str, float]]  # per-signal posterior summaries
    cusum_alert: bool = False  # True if CUSUM detected gradual drift
    cusum_value: float = 0.0  # current CUSUM statistic


# ---------------------------------------------------------------------------
# Conjugate model helpers (pure functions, no scipy)
# ---------------------------------------------------------------------------

def _beta_bernoulli_logpred(x: float, alpha: float, beta: float) -> float:
    """Log predictive probability of Bernoulli observation under Beta prior.

    P(x=1 | alpha, beta) = alpha / (alpha + beta)
    P(x=0 | alpha, beta) = beta  / (alpha + beta)
    """
    if x > 0.5:
        return math.log(alpha / (alpha + beta))
    return math.log(beta / (alpha + beta))


def _beta_bernoulli_update(x: float, alpha: float, beta: float) -> tuple:
    """Update Beta posterior with Bernoulli observation."""
    if x > 0.5:
        return (alpha + 1.0, beta)
    return (alpha, beta + 1.0)


def _nig_logpred(x: float, mu: float, kappa: float, alpha: float, beta: float) -> float:
    """Log predictive probability of observation under Normal-Inverse-Gamma prior.

    The predictive distribution is Student-t with:
        nu = 2*alpha degrees of freedom
        loc = mu
        scale^2 = beta * (kappa + 1) / (alpha * kappa)
    """
    nu = 2.0 * alpha
    scale_sq = beta * (kappa + 1.0) / (alpha * kappa)
    if scale_sq <= 0:
        return -50.0  # guard

    # Student-t log pdf:
    # log Gamma((nu+1)/2) - log Gamma(nu/2) - 0.5*log(nu*pi*s^2)
    #   - ((nu+1)/2) * log(1 + (x-mu)^2 / (nu*s^2))
    z = (x - mu)
    numer = z * z / (nu * scale_sq)

    log_pdf = (
        math.lgamma((nu + 1.0) / 2.0)
        - math.lgamma(nu / 2.0)
        - 0.5 * math.log(nu * math.pi * scale_sq)
        - ((nu + 1.0) / 2.0) * math.log(1.0 + numer)
    )
    return log_pdf


def _nig_update(
    x: float, mu: float, kappa: float, alpha: float, beta: float
) -> tuple:
    """Update Normal-Inverse-Gamma posterior with a single observation."""
    new_kappa = kappa + 1.0
    new_mu = (kappa * mu + x) / new_kappa
    new_alpha = alpha + 0.5
    new_beta = beta + 0.5 * kappa * (x - mu) ** 2 / new_kappa
    return (new_mu, new_kappa, new_alpha, new_beta)


# ---------------------------------------------------------------------------
# Signal model wrappers
# ---------------------------------------------------------------------------

class _BetaBernoulliSignal:
    """Tracks one Beta-Bernoulli signal across run lengths."""

    def __init__(self, prior_alpha: float = 1.0, prior_beta: float = 1.0):
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        # Per-run-length sufficient statistics: list of (alpha, beta)
        self.params: List[tuple] = [(prior_alpha, prior_beta)]

    def logpred(self, x: float) -> List[float]:
        """Log predictive for each run length."""
        return [_beta_bernoulli_logpred(x, a, b) for a, b in self.params]

    def update(self, x: float):
        """Update all run lengths and prepend prior for new run."""
        self.params = [
            _beta_bernoulli_update(x, a, b) for a, b in self.params
        ]
        # Prepend prior for new run (changepoint → reset)
        self.params.insert(0, (self.prior_alpha, self.prior_beta))

    def get_state(self) -> Dict[str, Any]:
        return {
            "type": "beta_bernoulli",
            "prior_alpha": self.prior_alpha,
            "prior_beta": self.prior_beta,
            "params": self.params,
        }

    @classmethod
    def from_state(cls, state: Dict[str, Any]) -> "_BetaBernoulliSignal":
        sig = cls(state["prior_alpha"], state["prior_beta"])
        sig.params = [tuple(p) for p in state["params"]]
        return sig

    def posterior_summary(self) -> Dict[str, float]:
        """Summary from the longest run length."""
        if len(self.params) <= 1:
            a, b = self.prior_alpha, self.prior_beta
        else:
            a, b = self.params[-1]
        return {"alpha": a, "beta": b, "mean": a / (a + b)}


class _NIGSignal:
    """Tracks one Normal-Inverse-Gamma signal across run lengths."""

    def __init__(
        self,
        prior_mu: float = 0.0,
        prior_kappa: float = 1.0,
        prior_alpha: float = 1.0,
        prior_beta: float = 1.0,
    ):
        self.prior = (prior_mu, prior_kappa, prior_alpha, prior_beta)
        # Per-run-length: list of (mu, kappa, alpha, beta)
        self.params: List[tuple] = [self.prior]

    def logpred(self, x: float) -> List[float]:
        return [_nig_logpred(x, mu, k, a, b) for mu, k, a, b in self.params]

    def update(self, x: float):
        self.params = [
            _nig_update(x, mu, k, a, b) for mu, k, a, b in self.params
        ]
        self.params.insert(0, self.prior)

    def get_state(self) -> Dict[str, Any]:
        return {
            "type": "nig",
            "prior": list(self.prior),
            "params": [list(p) for p in self.params],
        }

    @classmethod
    def from_state(cls, state: Dict[str, Any]) -> "_NIGSignal":
        sig = cls(*state["prior"])
        sig.params = [tuple(p) for p in state["params"]]
        return sig

    def posterior_summary(self) -> Dict[str, float]:
        if len(self.params) <= 1:
            mu, kappa, alpha, beta = self.prior
        else:
            mu, kappa, alpha, beta = self.params[-1]
        return {"mu": mu, "kappa": kappa, "alpha": alpha, "beta": beta}


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class BayesianChangepoint:
    """Bayesian Online Changepoint Detection for trading agent behavior.

    Maintains run length posterior across multiple behavioral signals.
    Each update returns a ChangePointResult with the probability that
    the most recent observation is a changepoint (run length reset to 0).

    Args:
        hazard_lambda: Expected run length between changepoints.
            Higher = changepoints less frequent. Default 50.
        truncation_threshold: Discard run lengths with P < this. Default 1e-6.
    """

    def __init__(
        self,
        hazard_lambda: float = 50.0,
        truncation_threshold: float = 1e-6,
    ):
        self.hazard_lambda = hazard_lambda
        self.truncation_threshold = truncation_threshold

        # Constant hazard: h = 1/lambda
        self._log_h = math.log(1.0 / hazard_lambda)
        self._log_1_minus_h = math.log(1.0 - 1.0 / hazard_lambda)

        # Run length log-posterior: log P(r_t | x_1:t)
        # Start with r_0 = 0 with probability 1
        self._log_run_probs: List[float] = [0.0]  # log(1.0) = 0.0

        # Signals
        self._signals: Dict[str, Any] = {
            "won": _BetaBernoulliSignal(prior_alpha=1.0, prior_beta=1.0),
            "pnl_r": _NIGSignal(prior_mu=0.0, prior_kappa=1.0, prior_alpha=1.0, prior_beta=1.0),
            "hold_seconds": _NIGSignal(prior_mu=3600.0, prior_kappa=0.5, prior_alpha=1.0, prior_beta=5000.0),
            "lot_vs_kelly": _NIGSignal(prior_mu=1.0, prior_kappa=1.0, prior_alpha=1.0, prior_beta=0.5),
        }

        self._observation_count = 0

        # CUSUM complementary detector for gradual shifts
        self._cusum_s: float = 0.0  # CUSUM statistic (downward drift)
        self._cusum_target_wr: float = 0.5  # expected win rate
        self._cusum_threshold: float = 4.0

    def update(self, observation: Dict[str, Any]) -> ChangePointResult:
        """Process one observation and update run length posterior.

        Args:
            observation: Dict with keys:
                - won (bool): required — trade was profitable
                - pnl_r (float): required — risk-adjusted return
                - hold_seconds (int, optional): hold duration
                - lot_vs_kelly (float, optional): actual lot / kelly lot

        Returns:
            ChangePointResult with changepoint probability and diagnostics.
        """
        # Compute joint log predictive across all present signals
        # For each run length r, compute log P(x_t | params_r)
        n = len(self._log_run_probs)
        log_pred = [0.0] * n  # per-run-length predictive
        log_prior_pred = 0.0  # prior predictive (for changepoint term)

        # won (required)
        won_val = 1.0 if observation.get("won", False) else 0.0
        lp = self._signals["won"].logpred(won_val)
        for i in range(n):
            log_pred[i] += lp[i]
        # Prior predictive: Beta(1,1) → P(x) = 0.5
        log_prior_pred += _beta_bernoulli_logpred(won_val, 1.0, 1.0)

        # pnl_r (required)
        if "pnl_r" in observation and observation["pnl_r"] is not None:
            pnl_val = float(observation["pnl_r"])
            lp = self._signals["pnl_r"].logpred(pnl_val)
            for i in range(n):
                log_pred[i] += lp[i]
            log_prior_pred += _nig_logpred(pnl_val, 0.0, 1.0, 1.0, 1.0)

        # hold_seconds (optional)
        if observation.get("hold_seconds") is not None:
            hold_val = float(observation["hold_seconds"])
            lp = self._signals["hold_seconds"].logpred(hold_val)
            for i in range(n):
                log_pred[i] += lp[i]
            log_prior_pred += _nig_logpred(hold_val, 3600.0, 0.5, 1.0, 5000.0)

        # lot_vs_kelly (optional)
        if observation.get("lot_vs_kelly") is not None:
            lot_val = float(observation["lot_vs_kelly"])
            lp = self._signals["lot_vs_kelly"].logpred(lot_val)
            for i in range(n):
                log_pred[i] += lp[i]
            log_prior_pred += _nig_logpred(lot_val, 1.0, 1.0, 1.0, 0.5)

        # Run length update (in log space)
        # Growth: P(r_t = r_{t-1}+1) ∝ P(x_t | params_r) * (1-h) * P(r_{t-1})
        new_log_probs = []
        for i in range(n):
            new_log_probs.append(
                self._log_run_probs[i] + log_pred[i] + self._log_1_minus_h
            )

        # Changepoint: P(r_t = 0) ∝ π_prior(x_t) * h * Σ P(r_{t-1})
        # After a changepoint, x_t is evaluated under the PRIOR predictive
        log_sum_prev = _logsumexp(self._log_run_probs)
        log_cp = log_prior_pred + self._log_h + log_sum_prev

        # Insert changepoint at position 0
        new_log_probs.insert(0, log_cp)

        # Normalize
        log_total = _logsumexp(new_log_probs)
        new_log_probs = [lp - log_total for lp in new_log_probs]

        # Truncate small run lengths
        keep_indices = []
        for i, lp in enumerate(new_log_probs):
            if math.exp(lp) >= self.truncation_threshold:
                keep_indices.append(i)

        if not keep_indices:
            keep_indices = [0]  # always keep at least the changepoint

        self._log_run_probs = [new_log_probs[i] for i in keep_indices]

        # Update signal sufficient statistics
        self._signals["won"].update(won_val)
        if "pnl_r" in observation and observation["pnl_r"] is not None:
            self._signals["pnl_r"].update(float(observation["pnl_r"]))
        if observation.get("hold_seconds") is not None:
            self._signals["hold_seconds"].update(float(observation["hold_seconds"]))
        if observation.get("lot_vs_kelly") is not None:
            self._signals["lot_vs_kelly"].update(float(observation["lot_vs_kelly"]))

        # Truncate signal params to match run length array
        self._truncate_signals(keep_indices)

        self._observation_count += 1

        # Changepoint probability = P(r_t = 0)
        cp_prob = math.exp(self._log_run_probs[0])

        # Max run length
        max_idx = 0
        max_val = self._log_run_probs[0]
        for i, lp in enumerate(self._log_run_probs):
            if lp > max_val:
                max_val = lp
                max_idx = i

        # CUSUM complementary detector (detects gradual downward drift)
        # Tracks negative deviation: loss = 0, win = 1
        cusum_x = 1.0 if won_val > 0.5 else 0.0
        # Detect degradation: accumulate negative deviations
        self._cusum_s = max(0.0, self._cusum_s + (self._cusum_target_wr - cusum_x))
        cusum_alert = self._cusum_s > self._cusum_threshold

        return ChangePointResult(
            changepoint_probability=cp_prob,
            max_run_length=max_idx,
            observation_count=self._observation_count,
            signal_posteriors={
                name: sig.posterior_summary()
                for name, sig in self._signals.items()
            },
            cusum_alert=cusum_alert,
            cusum_value=round(self._cusum_s, 4),
        )

    def _truncate_signals(self, keep_indices: List[int]):
        """Keep only the signal params at the given indices."""
        for sig in self._signals.values():
            sig.params = [sig.params[i] for i in keep_indices if i < len(sig.params)]
            # If truncation removed everything, re-add prior
            if not sig.params:
                if isinstance(sig, _BetaBernoulliSignal):
                    sig.params = [(sig.prior_alpha, sig.prior_beta)]
                else:
                    sig.params = [sig.prior]

    def get_state(self) -> Dict[str, Any]:
        """Serialize full detector state for persistence."""
        return {
            "hazard_lambda": self.hazard_lambda,
            "truncation_threshold": self.truncation_threshold,
            "log_run_probs": self._log_run_probs,
            "signals": {
                name: sig.get_state() for name, sig in self._signals.items()
            },
            "observation_count": self._observation_count,
            "cusum_s": self._cusum_s,
            "cusum_target_wr": self._cusum_target_wr,
            "cusum_threshold": self._cusum_threshold,
        }

    @classmethod
    def from_state(cls, state: Dict[str, Any]) -> "BayesianChangepoint":
        """Restore detector from serialized state."""
        detector = cls(
            hazard_lambda=state["hazard_lambda"],
            truncation_threshold=state["truncation_threshold"],
        )
        detector._log_run_probs = state["log_run_probs"]
        detector._observation_count = state["observation_count"]
        detector._cusum_s = state.get("cusum_s", 0.0)
        detector._cusum_target_wr = state.get("cusum_target_wr", 0.5)
        detector._cusum_threshold = state.get("cusum_threshold", 4.0)

        for name, sig_state in state["signals"].items():
            if sig_state["type"] == "beta_bernoulli":
                detector._signals[name] = _BetaBernoulliSignal.from_state(sig_state)
            elif sig_state["type"] == "nig":
                detector._signals[name] = _NIGSignal.from_state(sig_state)

        return detector


def _logsumexp(log_values: List[float]) -> float:
    """Numerically stable log-sum-exp. Pure Python, no scipy."""
    if not log_values:
        return float("-inf")
    max_val = max(log_values)
    if max_val == float("-inf"):
        return float("-inf")
    total = sum(math.exp(v - max_val) for v in log_values)
    return max_val + math.log(total)
