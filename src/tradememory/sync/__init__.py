"""Pull a trader's fill history from a venue into TradeMemory.

``fills`` rebuilds finished trades from fills, ``store`` writes them into
memory once each, ``report`` describes where the history loses money, and
one module per venue fetches and normalises its fills.
"""
