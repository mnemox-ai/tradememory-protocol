"""Broker MCP proxy: a brake in front of any broker MCP server, with memory as a side-effect.

The agent points at this server instead of the broker's MCP server. Every tool
is forwarded unchanged except order-placing tools, which are evaluated by
Mnemox Control against the owner's policy before they reach the broker. Every
evaluation is recorded in TradeMemory and chained into its audit log.

Requires the "proxy" extra (Python >= 3.12, mnemox-control).
"""
