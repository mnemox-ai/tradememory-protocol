"""
TradeMemory Protocol - AI Agent Trading Memory & Adaptive Decision Layer
"""

__version__ = "0.2.0"


def main():
    """MCP server entry point."""
    from .mcp_server import main as _main
    _main()
