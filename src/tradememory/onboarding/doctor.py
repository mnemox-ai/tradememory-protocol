"""Health check system for TradeMemory installation."""

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

# ANSI color codes
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class CheckResult:
    name: str
    status: str  # "pass", "fail", "warn"
    detail: str
    elapsed_ms: float


def _check_python_version() -> CheckResult:
    """Check Python version >= 3.10."""
    start = time.monotonic()
    v = sys.version_info
    ok = v >= (3, 10)
    elapsed = (time.monotonic() - start) * 1000
    return CheckResult(
        name="Python version",
        status="pass" if ok else "fail",
        detail=f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else " (need >= 3.10)"),
        elapsed_ms=elapsed,
    )


def _check_sqlite_database() -> CheckResult:
    """Check SQLite database can be created/opened."""
    start = time.monotonic()
    try:
        data_dir = Path.home() / ".tradememory"
        data_dir.mkdir(parents=True, exist_ok=True)
        import sqlite3
        db_path = data_dir / "tradememory.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("SELECT 1")
        conn.close()
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="SQLite database",
            status="pass",
            detail=str(db_path),
            elapsed_ms=elapsed,
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="SQLite database",
            status="fail",
            detail=str(e),
            elapsed_ms=elapsed,
        )


def _check_mcp_tools() -> CheckResult:
    """Check MCP tools can be loaded."""
    start = time.monotonic()
    try:
        import tradememory.mcp_server  # noqa: F401
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="MCP tools import",
            status="pass",
            detail="tradememory.mcp_server loaded",
            elapsed_ms=elapsed,
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="MCP tools import",
            status="fail",
            detail=str(e),
            elapsed_ms=elapsed,
        )


def _check_write_read_delete() -> CheckResult:
    """Write, read, and delete a test trade to verify DB operations."""
    start = time.monotonic()
    test_id = "__doctor_test__"
    try:
        from tradememory.db import Database

        db = Database()

        # Write — use insert_trade with all schema fields
        db.insert_trade({
            "id": test_id,
            "timestamp": "2000-01-01T00:00:00+00:00",
            "symbol": "DOCTOR_TEST",
            "direction": "long",
            "lot_size": 0.01,
            "strategy": "doctor_check",
            "confidence": 1.0,
            "reasoning": "health check",
            "market_context": {},
            "references": [],
            "tags": [],
            "exit_timestamp": None,
            "exit_price": None,
            "pnl": None,
            "pnl_r": None,
            "hold_duration": None,
            "exit_reasoning": None,
            "slippage": None,
            "execution_quality": None,
            "lessons": None,
            "grade": None,
        })

        # Read
        trade = db.get_trade(test_id)
        if trade is None:
            raise RuntimeError("Stored test trade but could not read it back")

        # Delete (no delete method on Database, use raw SQL)
        conn = db._get_connection()
        try:
            conn.execute("DELETE FROM trade_records WHERE id = ?", (test_id,))
            conn.commit()
        finally:
            conn.close()

        # Verify deletion
        trade_after = db.get_trade(test_id)
        if trade_after is not None:
            raise RuntimeError("Test trade was not deleted properly")

        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="Write/Read/Delete cycle",
            status="pass",
            detail="Store, retrieve, delete OK",
            elapsed_ms=elapsed,
        )
    except Exception as e:
        # Attempt cleanup even on failure
        try:
            from tradememory.db import Database
            db = Database()
            conn = db._get_connection()
            try:
                conn.execute("DELETE FROM trade_records WHERE id = ?", (test_id,))
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="Write/Read/Delete cycle",
            status="fail",
            detail=str(e),
            elapsed_ms=elapsed,
        )


def _check_rest_api() -> CheckResult:
    """Check if REST API is reachable at localhost:8000."""
    start = time.monotonic()
    try:
        import requests
        resp = requests.get("http://localhost:8000/health", timeout=3)
        elapsed = (time.monotonic() - start) * 1000
        if resp.status_code == 200:
            return CheckResult(
                name="REST API (localhost:8000)",
                status="pass",
                detail="Health endpoint OK",
                elapsed_ms=elapsed,
            )
        else:
            return CheckResult(
                name="REST API (localhost:8000)",
                status="warn",
                detail=f"Status {resp.status_code}",
                elapsed_ms=elapsed,
            )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="REST API (localhost:8000)",
            status="warn",
            detail=f"Not running ({type(e).__name__})",
            elapsed_ms=elapsed,
        )


def _check_metatrader5() -> CheckResult:
    """Check if MetaTrader5 Python package is installed."""
    start = time.monotonic()
    try:
        import MetaTrader5  # noqa: F401
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="MetaTrader5 package",
            status="pass",
            detail="Installed",
            elapsed_ms=elapsed,
        )
    except ImportError:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="MetaTrader5 package",
            status="warn",
            detail="Not installed (optional, for MT5 sync)",
            elapsed_ms=elapsed,
        )


def _check_anthropic_key() -> CheckResult:
    """Check if ANTHROPIC_API_KEY environment variable is set."""
    import os
    start = time.monotonic()
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    elapsed = (time.monotonic() - start) * 1000
    if key:
        masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
        return CheckResult(
            name="ANTHROPIC_API_KEY",
            status="pass",
            detail=f"Set ({masked})",
            elapsed_ms=elapsed,
        )
    else:
        return CheckResult(
            name="ANTHROPIC_API_KEY",
            status="warn",
            detail="Not set (optional, for Evolution Engine)",
            elapsed_ms=elapsed,
        )


def _check_evolution_engine() -> CheckResult:
    """Check if Evolution Engine is importable."""
    start = time.monotonic()
    try:
        from tradememory.evolution.engine import EvolutionEngine  # noqa: F401
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="Evolution Engine",
            status="pass",
            detail="Importable",
            elapsed_ms=elapsed,
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="Evolution Engine",
            status="warn",
            detail=f"Not available ({type(e).__name__})",
            elapsed_ms=elapsed,
        )


def run_doctor(full: bool = False) -> List[CheckResult]:
    """Run health checks and return results.

    Args:
        full: If True, run additional checks for external services.

    Returns:
        List of CheckResult with status for each check.
    """
    results = []

    # Core checks (always run)
    results.append(_check_python_version())
    results.append(_check_sqlite_database())
    results.append(_check_mcp_tools())
    results.append(_check_write_read_delete())

    # Full checks (--full only)
    if full:
        results.append(_check_rest_api())
        results.append(_check_metatrader5())
        results.append(_check_anthropic_key())
        results.append(_check_evolution_engine())

    return results


def print_results(results: List[CheckResult]) -> None:
    """Print check results as a formatted list."""
    print(f"\n{BOLD}TradeMemory Doctor{RESET}\n")

    pass_count = 0
    fail_count = 0
    warn_count = 0

    for r in results:
        if r.status == "pass":
            icon = f"{GREEN}[PASS]{RESET}"
            pass_count += 1
        elif r.status == "fail":
            icon = f"{RED}[FAIL]{RESET}"
            fail_count += 1
        else:
            icon = f"{YELLOW}[WARN]{RESET}"
            warn_count += 1

        ms = f"({r.elapsed_ms:.0f}ms)"
        print(f"  {icon} {r.name}: {r.detail} {ms}")

    print()
    summary_parts = [f"{GREEN}{pass_count} passed{RESET}"]
    if fail_count:
        summary_parts.append(f"{RED}{fail_count} failed{RESET}")
    if warn_count:
        summary_parts.append(f"{YELLOW}{warn_count} warnings{RESET}")
    print(f"  {', '.join(summary_parts)}")

    if fail_count:
        print(f"\n  {RED}Some checks failed. Fix issues above before using TradeMemory.{RESET}")
    elif warn_count:
        print(f"\n  {YELLOW}All core checks passed. Warnings are optional features.{RESET}")
    else:
        print(f"\n  {GREEN}All checks passed.{RESET}")
    print()
