"""Shared test configuration.

Tests must never make outbound network calls: RFC 3161 timestamping is
on by default since v0.5.3, so force it off for the whole suite. Tests
that exercise the TSA client itself mock the transport and re-enable
explicitly.
"""

import os

# Unconditional (not setdefault): a developer machine or CI with
# TRADEMEMORY_TSA=on in the environment must still never hit a real TSA
# from the test suite.
os.environ["TRADEMEMORY_TSA"] = "off"
