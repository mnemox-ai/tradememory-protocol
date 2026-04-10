"""SSRT -- Sequential Strategy Retirement Testing.

Provides statistically rigorous strategy retirement decisions using
mSPRT (Mixture Sequential Probability Ratio Test) with regime-aware
null hypotheses.
"""

from tradememory.ssrt.models import TradeResult, SSRTVerdict, RegimeBaseline, RetirementReport
from tradememory.ssrt.core import MixtureSPRT
from tradememory.ssrt.regime import RegimeAwareNull
