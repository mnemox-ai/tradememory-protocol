import sys
from pathlib import Path

# Make the fake upstream importable as a plain module without turning tests/ into a package.
sys.path.insert(0, str(Path(__file__).parent))

import pytest


@pytest.fixture(autouse=True)
def _restore_memory_tool_database():
    """build_proxy points the memory tools' module-global database at the test's
    temporary file; put the previous value back so later tests never see a path
    that no longer exists."""
    import tradememory.mcp_server as mcp_server

    previous = mcp_server._db
    yield
    mcp_server._db = previous
