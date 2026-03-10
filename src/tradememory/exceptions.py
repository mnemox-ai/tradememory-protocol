"""
Custom exceptions for TradeMemory dashboard API.
"""


class DatabaseConnectionError(Exception):
    """Raised when database connection fails."""
    pass


class DatabaseQueryError(Exception):
    """Raised when a database query fails."""
    pass


class StrategyNotFoundError(Exception):
    """Raised when a requested strategy does not exist."""
    pass
