"""
Custom exceptions for TradeMemory Protocol.

Hierarchy:
    TradeMemoryError
    ├── TradeMemoryDBError        — database operation failed
    ├── TradeMemoryValidationError — input validation failed
    ├── DatabaseConnectionError   — legacy alias (dashboard API)
    ├── DatabaseQueryError        — legacy alias (dashboard API)
    └── StrategyNotFoundError     — strategy lookup miss
"""


class TradeMemoryError(Exception):
    """Base exception for TradeMemory."""


class TradeMemoryDBError(TradeMemoryError):
    """Database operation failed (insert, update, query)."""


class TradeMemoryValidationError(TradeMemoryError):
    """Input validation failed."""


# Legacy aliases — used by dashboard_api.py / services
class DatabaseConnectionError(TradeMemoryError):
    """Raised when database connection fails."""


class DatabaseQueryError(TradeMemoryError):
    """Raised when a database query fails."""


class StrategyNotFoundError(TradeMemoryError):
    """Raised when a requested strategy does not exist."""
