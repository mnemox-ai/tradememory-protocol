"""Shared test configuration.

Tests must never make outbound network calls: RFC 3161 timestamping is
on by default since v0.5.3, so force it off for the whole suite. Tests
that exercise the TSA client itself mock the transport and re-enable
explicitly.
"""

import os

os.environ.setdefault("TRADEMEMORY_TSA", "off")
