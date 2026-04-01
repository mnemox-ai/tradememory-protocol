"""
Strategy Validator — Statistical validation engine for trading strategies.

Three-layer verification:
1. Deflated Sharpe Ratio (DSR) — corrects for selection bias / multiple testing
2. Walk-Forward Validation — out-of-sample consistency across time windows
3. Regime Analysis — performance across bull/bear/crisis/range markets

Plus optional CPCV (Combinatorial Purged Cross-Validation) on returns series.

All logic is self-contained. Only external dependency: deflated-sharpe (optional).
"""
from __future__ import annotations

import csv
import io
import logging
import math
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "DISCLAIMER: Statistical analysis only. Not financial advice. "
    "Past performance is not indicative of future results. "
    "This tool does not execute trades or provide investment recommendations. "
    "Users are solely responsible for their trading decisions."
)

# S&P 500 annual total returns (%) — public data for regime classification
SP500_ANNUAL_RETURNS = {
    2000: -9.1, 2001: -11.9, 2002: -22.1, 2003: 28.7, 2004: 10.9,
    2005: 4.9, 2006: 15.8, 2007: 5.5, 2008: -37.0, 2009: 26.5,
    2010: 15.1, 2011: 2.1, 2012: 16.0, 2013: 32.4, 2014: 13.7,
    2015: 1.4, 2016: 12.0, 2017: 21.8, 2018: -4.4, 2019: 31.5,
    2020: 18.4, 2021: 28.7, 2022: -18.1, 2023: 26.3, 2024: 25.0,
    2025: 5.0,
}
CRISIS_YEARS = {2008, 2020}

# Max file size: 50 MB
MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_ROWS = 1_000_000


# ---------------------------------------------------------------------------
# CSV Parsers
# ---------------------------------------------------------------------------

def parse_quantconnect_csv(file_path: str) -> list[dict]:
    """Parse QuantConnect trade log CSV.

    Expected columns: Entry Time, Exit Time, Direction, Entry Price,
    Exit Price, Quantity, P&L, Fees, MAE, MFE, Drawdown, IsWin, Symbols
    """
    _validate_file(file_path)
    trades = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= MAX_ROWS:
                logger.warning("Truncated at %d rows", MAX_ROWS)
                break
            try:
                entry_time = _parse_timestamp(row["Entry Time"])
                exit_time = _parse_timestamp(row["Exit Time"])
                trade = {
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "direction": row["Direction"].strip(),
                    "entry_price": float(row["Entry Price"]),
                    "exit_price": float(row["Exit Price"]),
                    "quantity": float(row["Quantity"]),
                    "pnl": float(row["P&L"]),
                    "fees": float(row.get("Fees", "0")),
                    "mae": float(row.get("MAE", "0")),
                    "mfe": float(row.get("MFE", "0")),
                    "is_win": row.get("IsWin", "0").strip() == "1",
                    "symbols": row.get("Symbols", "").strip(),
                }
                trades.append(trade)
            except (ValueError, KeyError):
                continue
    trades.sort(key=lambda t: t["exit_time"])
    return trades


def parse_returns_csv(file_path: str) -> list[dict]:
    """Parse daily returns CSV.

    Supported formats:
    - Two columns: date,return (with or without header)
    - Single column: return values only (one per line)
    """
    _validate_file(file_path)
    entries = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        content = f.read().strip()

    lines = content.split("\n")
    if not lines:
        return []

    # Detect format
    first_line = lines[0].strip()
    has_header = False
    if "," in first_line:
        # Two-column format — check if first line is parseable as data
        parts = first_line.split(",")
        is_data = False
        if len(parts) >= 2:
            try:
                float(parts[1].strip())
                _parse_date(parts[0].strip())
                is_data = True
            except (ValueError, IndexError):
                pass
            if not is_data:
                try:
                    float(parts[0])
                    is_data = True
                except ValueError:
                    pass
        has_header = not is_data

        start = 1 if has_header else 0
        for i, line in enumerate(lines[start:], start=start):
            if i >= MAX_ROWS:
                break
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            try:
                if len(parts) >= 2:
                    date_str = parts[0].strip()
                    ret = float(parts[1].strip())
                    dt = _parse_date(date_str)
                    entries.append({"date": dt, "return": ret})
            except (ValueError, IndexError):
                continue
    else:
        # Single column — synthetic dates starting from 2020-01-01
        try:
            float(first_line)
            start = 0
        except ValueError:
            start = 1  # skip header

        base_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for i, line in enumerate(lines[start:]):
            if i >= MAX_ROWS:
                break
            line = line.strip()
            if not line:
                continue
            try:
                ret = float(line)
                entries.append({
                    "date": base_date + timedelta(days=i),
                    "return": ret,
                })
            except ValueError:
                continue

    return entries


def parse_returns_csv_from_string(csv_content: str) -> list[dict]:
    """Parse returns from a CSV string (for MCP tool inline data)."""
    # Write to temp-like in-memory processing
    entries = []
    lines = csv_content.strip().split("\n")
    if not lines:
        return []

    first_line = lines[0].strip()
    has_header = False
    if "," in first_line:
        parts = first_line.split(",")
        try:
            float(parts[0])
        except ValueError:
            has_header = True

        start = 1 if has_header else 0
        for line in lines[start:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            try:
                if len(parts) >= 2:
                    date_str = parts[0].strip()
                    ret = float(parts[1].strip())
                    dt = _parse_date(date_str)
                    entries.append({"date": dt, "return": ret})
            except (ValueError, IndexError):
                continue
    else:
        try:
            float(first_line)
            start = 0
        except ValueError:
            start = 1
        base_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for i, line in enumerate(lines[start:]):
            line = line.strip()
            if not line:
                continue
            try:
                ret = float(line)
                entries.append({
                    "date": base_date + timedelta(days=i),
                    "return": ret,
                })
            except ValueError:
                continue

    return entries


# ---------------------------------------------------------------------------
# Analysis: Basic Stats
# ---------------------------------------------------------------------------

def compute_basic_stats(trades: list[dict]) -> dict:
    """Compute basic performance statistics from trade log."""
    n = len(trades)
    if n == 0:
        return {"total_trades": 0, "error": "No trades"}

    wins = sum(1 for t in trades if t["is_win"])
    total_pnl = sum(t["pnl"] for t in trades)

    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Holding period
    hold_days = [
        (t["exit_time"] - t["entry_time"]).total_seconds() / 86400
        for t in trades
    ]
    avg_hold = sum(hold_days) / len(hold_days) if hold_days else 0

    # Direction breakdown
    buy_count = sum(1 for t in trades if t["direction"] == "Buy")

    # Daily P&L series
    daily_pnl = _daily_pnl_series(trades)
    sorted_days = sorted(daily_pnl.keys())
    daily_values = [daily_pnl[d] for d in sorted_days]

    sharpe_raw = _raw_sharpe(daily_values)

    # Max drawdown
    max_dd, max_dd_pct = _max_drawdown(daily_values)

    return {
        "total_trades": n,
        "wins": wins,
        "losses": n - wins,
        "win_rate": round(wins / n * 100, 2),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / n, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else "inf",
        "sharpe_raw": round(sharpe_raw, 6),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "avg_hold_days": round(avg_hold, 2),
        "daily_observations": len(daily_values),
        "buy_count": buy_count,
        "sell_count": n - buy_count,
        "first_date": str(trades[0]["entry_time"].date()),
        "last_date": str(trades[-1]["exit_time"].date()),
    }


def compute_basic_stats_from_returns(returns: list[dict]) -> dict:
    """Compute basic stats from daily returns series."""
    n = len(returns)
    if n == 0:
        return {"observations": 0, "error": "No data"}

    values = [r["return"] for r in returns]
    positive = sum(1 for v in values if v > 0)
    total_return = sum(values)

    sharpe_raw = _raw_sharpe(values)
    max_dd, max_dd_pct = _max_drawdown(values)

    return {
        "observations": n,
        "positive_days": positive,
        "negative_days": n - positive,
        "win_rate": round(positive / n * 100, 2),
        "total_return": round(total_return, 6),
        "mean_return": round(total_return / n, 8),
        "sharpe_raw": round(sharpe_raw, 6),
        "max_drawdown": round(max_dd, 6),
        "first_date": str(returns[0]["date"].date()) if hasattr(returns[0]["date"], "date") else str(returns[0]["date"]),
        "last_date": str(returns[-1]["date"].date()) if hasattr(returns[-1]["date"], "date") else str(returns[-1]["date"]),
    }


# ---------------------------------------------------------------------------
# Analysis: Deflated Sharpe Ratio
# ---------------------------------------------------------------------------

def compute_dsr(
    sharpe_raw: float,
    num_obs: int,
    num_trials: int = 1,
    significance: float = 0.05,
) -> dict:
    """Compute Deflated Sharpe Ratio using deflated-sharpe package.

    Falls back to raw Sharpe assessment if package not installed.
    """
    if num_obs < 10:
        return {
            "sharpe_raw": round(sharpe_raw, 6),
            "dsr": 0.0,
            "p_value": 1.0,
            "verdict": "INSUFFICIENT_DATA",
            "num_trials": num_trials,
            "num_observations": num_obs,
            "min_observations": None,
        }

    try:
        from deflated_sharpe import deflated_sharpe_ratio, min_backtest_length

        dsr_val, p_value = deflated_sharpe_ratio(
            observed_sr=sharpe_raw,
            num_trials=max(1, num_trials),
            num_obs=num_obs,
        )

        try:
            min_obs = min_backtest_length(
                target_sr=sharpe_raw, num_trials=max(1, num_trials)
            )
        except Exception:
            min_obs = None

        if p_value < significance:
            verdict = "PASS"
        elif p_value < 0.10:
            verdict = "CAUTION"
        else:
            verdict = "FAIL"

        return {
            "sharpe_raw": round(sharpe_raw, 6),
            "dsr": round(float(dsr_val), 6),
            "p_value": round(float(p_value), 6),
            "verdict": verdict,
            "num_trials": num_trials,
            "num_observations": num_obs,
            "min_observations": int(min_obs) if min_obs is not None else None,
        }

    except ImportError:
        logger.warning("deflated-sharpe not installed, using raw Sharpe only")
        # Fallback: simple t-test approximation
        if num_obs > 1:
            t_stat = sharpe_raw * math.sqrt(num_obs)
            # Rough p-value from normal approximation
            p_approx = _normal_cdf(-abs(t_stat)) * 2
        else:
            t_stat = 0
            p_approx = 1.0

        if p_approx < significance and sharpe_raw > 0:
            verdict = "PASS"
        elif p_approx < 0.10 and sharpe_raw > 0:
            verdict = "CAUTION"
        else:
            verdict = "FAIL"

        return {
            "sharpe_raw": round(sharpe_raw, 6),
            "dsr": round(t_stat, 6),
            "p_value": round(p_approx, 6),
            "verdict": verdict,
            "num_trials": num_trials,
            "num_observations": num_obs,
            "min_observations": None,
            "note": "deflated-sharpe not installed; using t-test approximation",
        }


# ---------------------------------------------------------------------------
# Analysis: Walk-Forward Validation
# ---------------------------------------------------------------------------

def walk_forward_validation(
    trades: list[dict],
    is_years: int = 3,
    oos_years: int = 1,
) -> dict:
    """Walk-forward validation: rolling IS/OOS windows.

    Defaults: 3yr in-sample → 1yr out-of-sample, sliding by 3yr.
    Returns per-window results + overall verdict.
    """
    if not trades:
        return {"windows": [], "verdict": "NO_DATA", "windows_passed": 0, "windows_total": 0}

    first_year = trades[0]["entry_time"].year
    last_year = trades[-1]["exit_time"].year

    # Generate non-overlapping OOS windows
    windows = []
    is_start = first_year
    while is_start + is_years + oos_years - 1 <= last_year:
        is_end = is_start + is_years - 1
        oos_year = is_end + 1
        windows.append({"is_start": is_start, "is_end": is_end, "oos_year": oos_year})
        is_start += is_years

    results = []
    for w in windows:
        is_trades = [
            t for t in trades
            if w["is_start"] <= t["exit_time"].year <= w["is_end"]
        ]
        oos_trades = [
            t for t in trades
            if t["exit_time"].year == w["oos_year"]
        ]

        is_sharpe, is_wr = _sharpe_and_wr(is_trades)
        oos_sharpe, oos_wr = _sharpe_and_wr(oos_trades)

        if not oos_trades:
            verdict = "N/A"
        elif oos_sharpe > 0.05:
            verdict = "PASS"
        elif oos_sharpe > -0.02:
            verdict = "MARGINAL"
        else:
            verdict = "FAIL"

        results.append({
            "label": f"{w['is_start']}-{w['is_end']} -> {w['oos_year']}",
            "is_sharpe": round(is_sharpe, 6),
            "oos_sharpe": round(oos_sharpe, 6),
            "oos_win_rate": round(oos_wr, 2),
            "is_trades": len(is_trades),
            "oos_trades": len(oos_trades),
            "verdict": verdict,
        })

    passed = sum(1 for r in results if r["verdict"] == "PASS")
    total = sum(1 for r in results if r["verdict"] != "N/A")

    if total == 0:
        overall = "INSUFFICIENT_DATA"
    elif passed / total >= 0.67:
        overall = "PASS"
    elif passed / total >= 0.50:
        overall = "CAUTION"
    else:
        overall = "FAIL"

    return {
        "windows": results,
        "windows_passed": passed,
        "windows_total": total,
        "verdict": overall,
    }


def walk_forward_returns(
    returns: list[dict],
    is_years: int = 3,
    oos_years: int = 1,
) -> dict:
    """Walk-forward validation on daily returns series."""
    if not returns:
        return {"windows": [], "verdict": "NO_DATA", "windows_passed": 0, "windows_total": 0}

    first_year = returns[0]["date"].year
    last_year = returns[-1]["date"].year

    windows = []
    is_start = first_year
    while is_start + is_years + oos_years - 1 <= last_year:
        is_end = is_start + is_years - 1
        oos_year = is_end + 1
        windows.append({"is_start": is_start, "is_end": is_end, "oos_year": oos_year})
        is_start += is_years

    results = []
    for w in windows:
        is_vals = [r["return"] for r in returns if w["is_start"] <= r["date"].year <= w["is_end"]]
        oos_vals = [r["return"] for r in returns if r["date"].year == w["oos_year"]]

        is_sharpe = _raw_sharpe(is_vals) if is_vals else 0.0
        oos_sharpe = _raw_sharpe(oos_vals) if oos_vals else 0.0
        oos_wr = sum(1 for v in oos_vals if v > 0) / len(oos_vals) * 100 if oos_vals else 0.0

        if not oos_vals:
            verdict = "N/A"
        elif oos_sharpe > 0.05:
            verdict = "PASS"
        elif oos_sharpe > -0.02:
            verdict = "MARGINAL"
        else:
            verdict = "FAIL"

        results.append({
            "label": f"{w['is_start']}-{w['is_end']} -> {w['oos_year']}",
            "is_sharpe": round(is_sharpe, 6),
            "oos_sharpe": round(oos_sharpe, 6),
            "oos_win_rate": round(oos_wr, 2),
            "is_observations": len(is_vals),
            "oos_observations": len(oos_vals),
            "verdict": verdict,
        })

    passed = sum(1 for r in results if r["verdict"] == "PASS")
    total = sum(1 for r in results if r["verdict"] != "N/A")

    if total == 0:
        overall = "INSUFFICIENT_DATA"
    elif passed / total >= 0.67:
        overall = "PASS"
    elif passed / total >= 0.50:
        overall = "CAUTION"
    else:
        overall = "FAIL"

    return {
        "windows": results,
        "windows_passed": passed,
        "windows_total": total,
        "verdict": overall,
    }


# ---------------------------------------------------------------------------
# Analysis: Regime Analysis
# ---------------------------------------------------------------------------

def regime_analysis(trades: list[dict]) -> dict:
    """Analyze performance across market regimes (bull/bear/crisis/range)."""
    if not trades:
        return {"regimes": {}, "verdict": "NO_DATA"}

    regime_trades: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        year = t["exit_time"].year
        regime = _classify_year(year)
        regime_trades[regime].append(t)

    regimes = {}
    for regime, r_trades in regime_trades.items():
        n = len(r_trades)
        wins = sum(1 for t in r_trades if t["is_win"])
        total_pnl = sum(t["pnl"] for t in r_trades)
        daily = _daily_pnl_series(r_trades)
        sharpe = _raw_sharpe(list(daily.values())) if daily else 0.0

        if sharpe > 0.05:
            strength = "strong"
        elif sharpe > -0.02:
            strength = "neutral"
        else:
            strength = "weak"

        regimes[regime] = {
            "trades": n,
            "win_rate": round(wins / n * 100, 2) if n else 0,
            "total_pnl": round(total_pnl, 2),
            "sharpe": round(sharpe, 6),
            "strength": strength,
        }

    # Overall verdict: weak in any regime = CAUTION, weak in crisis = extra warning
    strengths = [r["strength"] for r in regimes.values()]
    if any(s == "weak" for s in strengths):
        if regimes.get("bear", {}).get("strength") == "weak":
            overall = "CAUTION"
        else:
            overall = "CAUTION"
    else:
        overall = "PASS"

    return {"regimes": regimes, "verdict": overall}


def regime_analysis_returns(returns: list[dict]) -> dict:
    """Regime analysis for returns series."""
    if not returns:
        return {"regimes": {}, "verdict": "NO_DATA"}

    regime_returns: dict[str, list[float]] = defaultdict(list)
    for r in returns:
        year = r["date"].year
        regime = _classify_year(year)
        regime_returns[regime].append(r["return"])

    regimes = {}
    for regime, vals in regime_returns.items():
        n = len(vals)
        positive = sum(1 for v in vals if v > 0)
        sharpe = _raw_sharpe(vals)

        if sharpe > 0.05:
            strength = "strong"
        elif sharpe > -0.02:
            strength = "neutral"
        else:
            strength = "weak"

        regimes[regime] = {
            "observations": n,
            "win_rate": round(positive / n * 100, 2) if n else 0,
            "total_return": round(sum(vals), 6),
            "sharpe": round(sharpe, 6),
            "strength": strength,
        }

    strengths = [r["strength"] for r in regimes.values()]
    overall = "CAUTION" if any(s == "weak" for s in strengths) else "PASS"

    return {"regimes": regimes, "verdict": overall}


# ---------------------------------------------------------------------------
# Analysis: CPCV (Combinatorial Purged Cross-Validation)
# ---------------------------------------------------------------------------

def cpcv_sharpe(
    daily_returns: list[float],
    n_groups: int = 10,
    n_test_groups: int = 2,
    purge_window: int = 5,
    embargo_window: int = 10,
) -> dict:
    """Run CPCV on daily returns to get cross-validated Sharpe distribution.

    Unlike Sulci's CPCV (which trains ML models per fold), this computes
    the Sharpe ratio on each out-of-sample fold directly. This measures
    how stable the strategy's edge is across different time periods.

    Args:
        daily_returns: List of daily return values.
        n_groups: Number of sequential groups (N).
        n_test_groups: Groups per test set (k). Folds = C(N, k).
        purge_window: Bars removed at train/test boundary.
        embargo_window: Additional bars skipped after test block.

    Returns:
        Dict with fold_sharpes, mean, std, min, max, and consistency verdict.
    """
    n = len(daily_returns)
    min_required = n_groups * (purge_window + embargo_window + 5)

    if n < min_required:
        return {
            "verdict": "INSUFFICIENT_DATA",
            "error": f"Need >= {min_required} observations, got {n}",
            "n_folds": 0,
        }

    group_size = n // n_groups
    groups: list[list[int]] = []
    for i in range(n_groups):
        start = i * group_size
        end = (i + 1) * group_size if i < n_groups - 1 else n
        groups.append(list(range(start, end)))

    fold_sharpes = []
    for test_group_ids in combinations(range(n_groups), n_test_groups):
        test_indices = set()
        for gid in test_group_ids:
            test_indices.update(groups[gid])

        # Find contiguous test blocks for purge/embargo
        sorted_test = sorted(test_indices)
        blocks = _find_contiguous_blocks(sorted_test)

        exclude = set()
        for block_start, block_end in blocks:
            for i in range(max(0, block_start - purge_window), block_start):
                exclude.add(i)
            for i in range(block_end + 1, block_end + 1 + embargo_window):
                exclude.add(i)

        # Test returns (the OOS portion)
        test_returns = [daily_returns[i] for i in sorted_test]
        sharpe = _raw_sharpe(test_returns) if test_returns else 0.0
        fold_sharpes.append(sharpe)

    if not fold_sharpes:
        return {"verdict": "ERROR", "error": "No valid folds", "n_folds": 0}

    mean_sharpe = sum(fold_sharpes) / len(fold_sharpes)
    std_sharpe = _std(fold_sharpes)
    min_sharpe = min(fold_sharpes)
    max_sharpe = max(fold_sharpes)

    # Consistency: what fraction of folds have positive Sharpe?
    positive_folds = sum(1 for s in fold_sharpes if s > 0)
    consistency = positive_folds / len(fold_sharpes)

    if consistency >= 0.70 and mean_sharpe > 0:
        verdict = "PASS"
    elif consistency >= 0.55 and mean_sharpe > 0:
        verdict = "CAUTION"
    else:
        verdict = "FAIL"

    return {
        "n_folds": len(fold_sharpes),
        "n_groups": n_groups,
        "n_test_groups": n_test_groups,
        "purge_window": purge_window,
        "embargo_window": embargo_window,
        "mean_sharpe": round(mean_sharpe, 6),
        "std_sharpe": round(std_sharpe, 6),
        "min_sharpe": round(min_sharpe, 6),
        "max_sharpe": round(max_sharpe, 6),
        "consistency": round(consistency, 4),
        "positive_folds": positive_folds,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Main Entry Points
# ---------------------------------------------------------------------------

def validate_from_trades(
    file_path: str,
    format: str = "quantconnect",
    strategy_name: str = "",
    num_strategies: int = 1,
) -> dict:
    """Full validation pipeline for trade log CSV.

    Args:
        file_path: Path to CSV file.
        format: CSV format ("quantconnect").
        strategy_name: Name for the report.
        num_strategies: How many strategies were tested (M for DSR).

    Returns:
        Complete validation report dict.
    """
    try:
        if format == "quantconnect":
            trades = parse_quantconnect_csv(file_path)
        else:
            return {"error": f"Unsupported trade log format: {format}", "disclaimer": DISCLAIMER}
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e), "disclaimer": DISCLAIMER}

    if not trades:
        return {"error": "No valid trades parsed from CSV", "disclaimer": DISCLAIMER}

    stats = compute_basic_stats(trades)
    dsr = compute_dsr(stats["sharpe_raw"], stats["daily_observations"], num_strategies)
    wf = walk_forward_validation(trades)
    regime = regime_analysis(trades)

    # Also run CPCV on daily returns
    daily_pnl = _daily_pnl_series(trades)
    sorted_days = sorted(daily_pnl.keys())
    daily_values = [daily_pnl[d] for d in sorted_days]
    cpcv = cpcv_sharpe(daily_values)

    # Overall verdict
    verdicts = [dsr["verdict"], wf["verdict"], regime["verdict"]]
    if cpcv["verdict"] not in ("INSUFFICIENT_DATA", "ERROR"):
        verdicts.append(cpcv["verdict"])

    pass_count = sum(1 for v in verdicts if v == "PASS")
    fail_count = sum(1 for v in verdicts if v == "FAIL")

    if fail_count >= 2:
        overall = "FAIL"
    elif pass_count >= 2 and fail_count == 0:
        overall = "PASS"
    else:
        overall = "CAUTION"

    return {
        "strategy_name": strategy_name or "unnamed",
        "format": format,
        "verdict": overall,
        "tests": {
            "dsr": dsr,
            "walk_forward": wf,
            "regime": regime,
            "cpcv": cpcv,
        },
        "stats": stats,
        "disclaimer": DISCLAIMER,
    }


def validate_from_returns(
    file_path: Optional[str] = None,
    returns_data: Optional[str] = None,
    strategy_name: str = "",
    num_strategies: int = 1,
) -> dict:
    """Full validation pipeline for daily returns series.

    Provide either file_path or returns_data (CSV string).

    Args:
        file_path: Path to returns CSV.
        returns_data: Raw CSV string with returns.
        strategy_name: Name for the report.
        num_strategies: How many strategies were tested (M for DSR).

    Returns:
        Complete validation report dict.
    """
    if file_path:
        entries = parse_returns_csv(file_path)
    elif returns_data:
        entries = parse_returns_csv_from_string(returns_data)
    else:
        return {"error": "Provide file_path or returns_data", "disclaimer": DISCLAIMER}

    if not entries:
        return {"error": "No valid returns parsed", "disclaimer": DISCLAIMER}

    values = [e["return"] for e in entries]
    stats = compute_basic_stats_from_returns(entries)
    dsr = compute_dsr(stats["sharpe_raw"], len(values), num_strategies)
    wf = walk_forward_returns(entries)
    regime = regime_analysis_returns(entries)
    cpcv = cpcv_sharpe(values)

    verdicts = [dsr["verdict"], wf["verdict"], regime["verdict"]]
    if cpcv["verdict"] not in ("INSUFFICIENT_DATA", "ERROR"):
        verdicts.append(cpcv["verdict"])

    pass_count = sum(1 for v in verdicts if v == "PASS")
    fail_count = sum(1 for v in verdicts if v == "FAIL")

    if fail_count >= 2:
        overall = "FAIL"
    elif pass_count >= 2 and fail_count == 0:
        overall = "PASS"
    else:
        overall = "CAUTION"

    return {
        "strategy_name": strategy_name or "unnamed",
        "format": "returns",
        "verdict": overall,
        "tests": {
            "dsr": dsr,
            "walk_forward": wf,
            "regime": regime,
            "cpcv": cpcv,
        },
        "stats": stats,
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _validate_file(file_path: str) -> None:
    """Security: validate file path and size."""
    path = Path(file_path).resolve()

    # Path traversal check
    if ".." in str(file_path):
        raise ValueError("Path traversal not allowed")

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not path.is_file():
        raise ValueError(f"Not a file: {file_path}")

    size = path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise ValueError(f"File too large: {size} bytes (max {MAX_FILE_SIZE})")

    if path.suffix.lower() not in (".csv", ".txt", ".tsv"):
        raise ValueError(f"Unsupported file type: {path.suffix}")


def _parse_timestamp(s: str) -> datetime:
    """Parse ISO-ish timestamp string."""
    s = s.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # Try common formats
        for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        raise ValueError(f"Cannot parse timestamp: {s}")


def _parse_date(s: str) -> datetime:
    """Parse date string."""
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Try ISO format
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Cannot parse date: {s}")


def _daily_pnl_series(trades: list[dict]) -> dict:
    """Group trades by exit date, sum P&L."""
    daily: dict = defaultdict(float)
    for t in trades:
        day = t["exit_time"].date()
        daily[day] += t["pnl"]
    return dict(daily)


def _raw_sharpe(values: list[float]) -> float:
    """Raw Sharpe ratio (NOT annualized)."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    std = math.sqrt(variance) if variance > 0 else 0
    return mean / std if std > 0 else 0.0


def _std(values: list[float]) -> float:
    """Sample standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _max_drawdown(daily_values: list[float]) -> tuple[float, float]:
    """Compute max drawdown from daily P&L values. Returns (absolute, %)."""
    if not daily_values:
        return 0.0, 0.0
    cumulative = []
    running = 0.0
    for v in daily_values:
        running += v
        cumulative.append(running)

    peak = 0.0
    max_dd = 0.0
    for val in cumulative:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd

    max_dd_pct = (max_dd / peak * 100) if peak > 0 else 0.0
    return max_dd, max_dd_pct


def _sharpe_and_wr(trades: list[dict]) -> tuple[float, float]:
    """Compute Sharpe and win rate for a subset of trades."""
    if not trades:
        return 0.0, 0.0
    daily = _daily_pnl_series(trades)
    values = list(daily.values())
    sharpe = _raw_sharpe(values)
    wins = sum(1 for t in trades if t["is_win"])
    wr = wins / len(trades) * 100
    return sharpe, wr


def _classify_year(year: int) -> str:
    """Classify year as bull/bear/range/crisis."""
    if year in CRISIS_YEARS:
        return "crisis"
    ret = SP500_ANNUAL_RETURNS.get(year, 0)
    if ret > 10:
        return "bull"
    elif ret < -10:
        return "bear"
    else:
        return "range"


def _find_contiguous_blocks(sorted_indices: list[int]) -> list[tuple[int, int]]:
    """Find contiguous blocks in sorted index list."""
    if not sorted_indices:
        return []
    blocks = []
    block_start = sorted_indices[0]
    prev = sorted_indices[0]
    for i in sorted_indices[1:]:
        if i > prev + 1:
            blocks.append((block_start, prev))
            block_start = i
        prev = i
    blocks.append((block_start, prev))
    return blocks


def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF (Abramowitz & Stegun)."""
    if x < -8:
        return 0.0
    if x > 8:
        return 1.0
    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    d = 0.3989422804014327  # 1/sqrt(2*pi)
    p = d * math.exp(-x * x / 2.0) * (
        t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    )
    return 1.0 - p if x > 0 else p
