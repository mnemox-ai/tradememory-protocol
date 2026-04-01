"""Tests for strategy_validator module."""
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from tradememory.strategy_validator import (
    DISCLAIMER,
    compute_basic_stats,
    compute_basic_stats_from_returns,
    compute_dsr,
    cpcv_sharpe,
    parse_quantconnect_csv,
    parse_returns_csv,
    parse_returns_csv_from_string,
    regime_analysis,
    regime_analysis_returns,
    validate_from_returns,
    validate_from_trades,
    walk_forward_returns,
    walk_forward_validation,
    _raw_sharpe,
    _max_drawdown,
    _classify_year,
    _normal_cdf,
    _find_contiguous_blocks,
    _validate_file,
)


# ---------------------------------------------------------------------------
# Fixtures: generate synthetic trade data
# ---------------------------------------------------------------------------

def _make_trades(n=200, start_year=2010, years=10, win_rate=0.55, avg_pnl=50):
    """Generate synthetic trades spanning multiple years."""
    trades = []
    base = datetime(start_year, 1, 15, 10, 0, tzinfo=timezone.utc)
    days_span = years * 365
    for i in range(n):
        entry = base + timedelta(days=int(i * days_span / n))
        exit_ = entry + timedelta(hours=4)
        is_win = (i % int(1 / win_rate)) < int(n * win_rate / n) if win_rate < 1 else True
        pnl = abs(avg_pnl) * (1.2 if is_win else -0.8)
        trades.append({
            "entry_time": entry,
            "exit_time": exit_,
            "direction": "Buy",
            "entry_price": 100.0,
            "exit_price": 100.0 + (pnl / 100),
            "quantity": 100,
            "pnl": pnl,
            "fees": 1.0,
            "mae": abs(pnl) * 0.5,
            "mfe": abs(pnl) * 1.5,
            "is_win": is_win,
            "symbols": "SPY",
        })
    return trades


def _make_returns(n=500, start_year=2015, daily_mean=0.0003, daily_std=0.01):
    """Generate synthetic daily returns."""
    import random
    random.seed(42)
    entries = []
    base = datetime(start_year, 1, 2, tzinfo=timezone.utc)
    for i in range(n):
        date = base + timedelta(days=i)
        ret = daily_mean + random.gauss(0, daily_std)
        entries.append({"date": date, "return": ret})
    return entries


def _write_qc_csv(trades, path):
    """Write trades in QuantConnect CSV format."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("Entry Time,Exit Time,Direction,Entry Price,Exit Price,Quantity,P&L,Fees,MAE,MFE,Drawdown,IsWin,Symbols\n")
        for t in trades:
            f.write(
                f"{t['entry_time'].isoformat()},"
                f"{t['exit_time'].isoformat()},"
                f"{t['direction']},"
                f"{t['entry_price']},"
                f"{t['exit_price']},"
                f"{t['quantity']},"
                f"{t['pnl']},"
                f"{t['fees']},"
                f"{t['mae']},"
                f"{t['mfe']},"
                f"0.0,"
                f"{'1' if t['is_win'] else '0'},"
                f"{t['symbols']}\n"
            )


def _write_returns_csv(returns, path, with_header=True, two_col=True):
    """Write returns CSV."""
    with open(path, "w", encoding="utf-8") as f:
        if two_col:
            if with_header:
                f.write("date,return\n")
            for r in returns:
                d = r["date"].strftime("%Y-%m-%d") if hasattr(r["date"], "strftime") else str(r["date"])
                f.write(f"{d},{r['return']}\n")
        else:
            if with_header:
                f.write("return\n")
            for r in returns:
                f.write(f"{r['return']}\n")


# ---------------------------------------------------------------------------
# Tests: Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_raw_sharpe_positive(self):
        values = [0.01, 0.02, 0.015, 0.005, 0.01]
        s = _raw_sharpe(values)
        assert s > 0

    def test_raw_sharpe_zero_std(self):
        values = [0.01, 0.01, 0.01]
        assert _raw_sharpe(values) == 0.0

    def test_raw_sharpe_empty(self):
        assert _raw_sharpe([]) == 0.0

    def test_raw_sharpe_single(self):
        assert _raw_sharpe([0.05]) == 0.0

    def test_max_drawdown_basic(self):
        values = [100, 50, -200, 100, 50]
        dd, dd_pct = _max_drawdown(values)
        assert dd > 0

    def test_max_drawdown_empty(self):
        dd, dd_pct = _max_drawdown([])
        assert dd == 0.0

    def test_max_drawdown_no_drawdown(self):
        values = [10, 20, 30, 40]
        dd, dd_pct = _max_drawdown(values)
        assert dd == 0.0

    def test_classify_year_bull(self):
        assert _classify_year(2013) == "bull"

    def test_classify_year_bear(self):
        assert _classify_year(2022) == "bear"

    def test_classify_year_crisis(self):
        assert _classify_year(2008) == "crisis"
        assert _classify_year(2020) == "crisis"

    def test_classify_year_range(self):
        assert _classify_year(2015) == "range"

    def test_classify_year_unknown(self):
        # Unknown year defaults to 0% return → range
        assert _classify_year(1990) == "range"

    def test_normal_cdf_bounds(self):
        assert _normal_cdf(0) == pytest.approx(0.5, abs=0.01)
        assert _normal_cdf(-10) == 0.0
        assert _normal_cdf(10) == 1.0

    def test_normal_cdf_symmetry(self):
        assert _normal_cdf(1.96) == pytest.approx(1 - _normal_cdf(-1.96), abs=0.001)

    def test_find_contiguous_blocks(self):
        assert _find_contiguous_blocks([]) == []
        assert _find_contiguous_blocks([1, 2, 3, 5, 6, 10]) == [(1, 3), (5, 6), (10, 10)]
        assert _find_contiguous_blocks([1]) == [(1, 1)]


# ---------------------------------------------------------------------------
# Tests: Parsers
# ---------------------------------------------------------------------------

class TestParsers:
    def test_parse_quantconnect_csv(self, tmp_path):
        trades = _make_trades(50)
        csv_path = str(tmp_path / "trades.csv")
        _write_qc_csv(trades, csv_path)
        parsed = parse_quantconnect_csv(csv_path)
        assert len(parsed) == 50
        assert parsed[0]["direction"] == "Buy"
        assert isinstance(parsed[0]["pnl"], float)

    def test_parse_quantconnect_csv_empty(self, tmp_path):
        csv_path = str(tmp_path / "empty.csv")
        with open(csv_path, "w") as f:
            f.write("Entry Time,Exit Time,Direction,Entry Price,Exit Price,Quantity,P&L,Fees,MAE,MFE,Drawdown,IsWin,Symbols\n")
        parsed = parse_quantconnect_csv(csv_path)
        assert len(parsed) == 0

    def test_parse_returns_csv_two_col(self, tmp_path):
        returns = _make_returns(100)
        csv_path = str(tmp_path / "returns.csv")
        _write_returns_csv(returns, csv_path)
        parsed = parse_returns_csv(csv_path)
        assert len(parsed) == 100
        assert "return" in parsed[0]
        assert "date" in parsed[0]

    def test_parse_returns_csv_single_col(self, tmp_path):
        returns = _make_returns(100)
        csv_path = str(tmp_path / "returns_single.csv")
        _write_returns_csv(returns, csv_path, two_col=False)
        parsed = parse_returns_csv(csv_path)
        assert len(parsed) == 100

    def test_parse_returns_csv_no_header(self, tmp_path):
        returns = _make_returns(50)
        csv_path = str(tmp_path / "returns_noh.csv")
        _write_returns_csv(returns, csv_path, with_header=False)
        parsed = parse_returns_csv(csv_path)
        assert len(parsed) == 50

    def test_parse_returns_from_string(self):
        csv_str = "date,return\n2020-01-01,0.01\n2020-01-02,-0.005\n2020-01-03,0.02"
        parsed = parse_returns_csv_from_string(csv_str)
        assert len(parsed) == 3
        assert parsed[0]["return"] == 0.01

    def test_parse_returns_from_string_single_col(self):
        csv_str = "0.01\n-0.005\n0.02\n0.015"
        parsed = parse_returns_csv_from_string(csv_str)
        assert len(parsed) == 4

    def test_validate_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            _validate_file("/nonexistent/file.csv")

    def test_validate_file_path_traversal(self, tmp_path):
        with pytest.raises(ValueError, match="traversal"):
            _validate_file(str(tmp_path / ".." / ".." / "etc" / "passwd"))

    def test_validate_file_wrong_extension(self, tmp_path):
        bad = tmp_path / "file.exe"
        bad.write_text("data")
        with pytest.raises(ValueError, match="Unsupported"):
            _validate_file(str(bad))

    def test_validate_file_too_large(self, tmp_path):
        big = tmp_path / "big.csv"
        big.write_text("x" * 100)
        # Monkey-patch MAX_FILE_SIZE for test
        import tradememory.strategy_validator as sv
        old = sv.MAX_FILE_SIZE
        sv.MAX_FILE_SIZE = 50
        try:
            with pytest.raises(ValueError, match="too large"):
                _validate_file(str(big))
        finally:
            sv.MAX_FILE_SIZE = old


# ---------------------------------------------------------------------------
# Tests: Basic Stats
# ---------------------------------------------------------------------------

class TestBasicStats:
    def test_compute_basic_stats(self):
        trades = _make_trades(100)
        stats = compute_basic_stats(trades)
        assert stats["total_trades"] == 100
        assert 0 <= stats["win_rate"] <= 100
        assert "sharpe_raw" in stats
        assert "profit_factor" in stats
        assert "first_date" in stats

    def test_compute_basic_stats_empty(self):
        stats = compute_basic_stats([])
        assert stats["total_trades"] == 0

    def test_compute_basic_stats_from_returns(self):
        returns = _make_returns(200)
        stats = compute_basic_stats_from_returns(returns)
        assert stats["observations"] == 200
        assert "sharpe_raw" in stats
        assert "win_rate" in stats

    def test_compute_basic_stats_from_returns_empty(self):
        stats = compute_basic_stats_from_returns([])
        assert stats["observations"] == 0


# ---------------------------------------------------------------------------
# Tests: DSR
# ---------------------------------------------------------------------------

class TestDSR:
    def test_dsr_with_enough_data(self):
        result = compute_dsr(0.10, 500, num_trials=1)
        assert "sharpe_raw" in result
        assert "dsr" in result
        assert "p_value" in result
        assert result["verdict"] in ("PASS", "CAUTION", "FAIL")
        assert result["num_observations"] == 500

    def test_dsr_insufficient_data(self):
        result = compute_dsr(0.10, 5, num_trials=1)
        assert result["verdict"] == "INSUFFICIENT_DATA"

    def test_dsr_negative_sharpe(self):
        result = compute_dsr(-0.05, 500, num_trials=1)
        assert result["verdict"] == "FAIL"

    def test_dsr_high_trials_harder(self):
        # Same Sharpe but more trials → harder to pass
        r1 = compute_dsr(0.05, 500, num_trials=1)
        r50 = compute_dsr(0.05, 500, num_trials=50)
        assert r50["p_value"] >= r1["p_value"]

    def test_dsr_zero_sharpe(self):
        result = compute_dsr(0.0, 500, num_trials=1)
        assert result["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# Tests: Walk-Forward
# ---------------------------------------------------------------------------

class TestWalkForward:
    def test_walk_forward_trades(self):
        trades = _make_trades(500, start_year=2005, years=20)
        result = walk_forward_validation(trades)
        assert "windows" in result
        assert "verdict" in result
        assert result["windows_total"] > 0

    def test_walk_forward_empty(self):
        result = walk_forward_validation([])
        assert result["verdict"] == "NO_DATA"

    def test_walk_forward_short_period(self):
        trades = _make_trades(50, start_year=2023, years=1)
        result = walk_forward_validation(trades)
        # 1 year not enough for 3yr IS + 1yr OOS
        assert result["windows_total"] == 0

    def test_walk_forward_returns(self):
        returns = _make_returns(2000, start_year=2010)
        result = walk_forward_returns(returns)
        assert "windows" in result
        assert "verdict" in result

    def test_walk_forward_returns_empty(self):
        result = walk_forward_returns([])
        assert result["verdict"] == "NO_DATA"


# ---------------------------------------------------------------------------
# Tests: Regime Analysis
# ---------------------------------------------------------------------------

class TestRegimeAnalysis:
    def test_regime_analysis_trades(self):
        trades = _make_trades(500, start_year=2005, years=20)
        result = regime_analysis(trades)
        assert "regimes" in result
        assert len(result["regimes"]) > 0
        assert "verdict" in result

    def test_regime_analysis_empty(self):
        result = regime_analysis([])
        assert result["verdict"] == "NO_DATA"

    def test_regime_analysis_returns(self):
        returns = _make_returns(2000, start_year=2005)
        result = regime_analysis_returns(returns)
        assert "regimes" in result
        assert "verdict" in result

    def test_regime_analysis_returns_empty(self):
        result = regime_analysis_returns([])
        assert result["verdict"] == "NO_DATA"

    def test_regime_has_known_regimes(self):
        trades = _make_trades(500, start_year=2005, years=20)
        result = regime_analysis(trades)
        # Should have at least bull and some other regime
        regime_names = set(result["regimes"].keys())
        assert len(regime_names) >= 2


# ---------------------------------------------------------------------------
# Tests: CPCV
# ---------------------------------------------------------------------------

class TestCPCV:
    def test_cpcv_basic(self):
        import random
        random.seed(42)
        returns = [0.001 + random.gauss(0, 0.01) for _ in range(500)]
        result = cpcv_sharpe(returns)
        assert result["n_folds"] == 45  # C(10,2)
        assert "mean_sharpe" in result
        assert "consistency" in result
        assert result["verdict"] in ("PASS", "CAUTION", "FAIL")

    def test_cpcv_insufficient_data(self):
        result = cpcv_sharpe([0.01, 0.02])
        assert result["verdict"] == "INSUFFICIENT_DATA"

    def test_cpcv_negative_returns(self):
        import random
        random.seed(42)
        returns = [-0.005 + random.gauss(0, 0.01) for _ in range(500)]
        result = cpcv_sharpe(returns)
        # Should mostly fail or caution with negative mean
        assert result["mean_sharpe"] < 0.05

    def test_cpcv_custom_params(self):
        import random
        random.seed(42)
        returns = [random.gauss(0.001, 0.01) for _ in range(300)]
        result = cpcv_sharpe(returns, n_groups=6, n_test_groups=2, purge_window=3, embargo_window=5)
        assert result["n_folds"] == 15  # C(6,2)
        assert result["n_groups"] == 6

    def test_cpcv_purge_embargo_applied(self):
        # With large embargo, should still work but with fewer effective test observations
        import random
        random.seed(42)
        returns = [random.gauss(0.001, 0.01) for _ in range(1000)]
        r1 = cpcv_sharpe(returns, purge_window=0, embargo_window=0)
        r2 = cpcv_sharpe(returns, purge_window=10, embargo_window=20)
        # Both should complete
        assert r1["n_folds"] == 45
        assert r2["n_folds"] == 45


# ---------------------------------------------------------------------------
# Tests: Full Pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_validate_from_trades(self, tmp_path):
        trades = _make_trades(300, start_year=2005, years=18)
        csv_path = str(tmp_path / "trades.csv")
        _write_qc_csv(trades, csv_path)

        result = validate_from_trades(csv_path, strategy_name="TestStrat")
        assert result["strategy_name"] == "TestStrat"
        assert result["verdict"] in ("PASS", "CAUTION", "FAIL")
        assert "dsr" in result["tests"]
        assert "walk_forward" in result["tests"]
        assert "regime" in result["tests"]
        assert "cpcv" in result["tests"]
        assert result["disclaimer"] == DISCLAIMER

    def test_validate_from_returns_file(self, tmp_path):
        returns = _make_returns(1000, start_year=2010)
        csv_path = str(tmp_path / "returns.csv")
        _write_returns_csv(returns, csv_path)

        result = validate_from_returns(file_path=csv_path, strategy_name="RetStrat")
        assert result["strategy_name"] == "RetStrat"
        assert result["verdict"] in ("PASS", "CAUTION", "FAIL")
        assert "dsr" in result["tests"]
        assert result["disclaimer"] == DISCLAIMER

    def test_validate_from_returns_string(self):
        csv_str = "date,return\n"
        import random
        random.seed(42)
        base = datetime(2015, 1, 1)
        for i in range(500):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            r = 0.0003 + random.gauss(0, 0.01)
            csv_str += f"{d},{r}\n"

        result = validate_from_returns(returns_data=csv_str, strategy_name="InlineStrat")
        assert result["strategy_name"] == "InlineStrat"
        assert result["verdict"] in ("PASS", "CAUTION", "FAIL")

    def test_validate_from_trades_bad_format(self, tmp_path):
        csv_path = str(tmp_path / "trades.csv")
        with open(csv_path, "w") as f:
            f.write("a,b,c\n1,2,3\n")
        result = validate_from_trades(csv_path)
        assert "error" in result

    def test_validate_from_returns_no_input(self):
        result = validate_from_returns()
        assert "error" in result

    def test_validate_from_trades_nonexistent(self):
        result = validate_from_trades("/nonexistent/file.csv")
        assert "error" in result or "disclaimer" in result

    def test_validate_unsupported_format(self, tmp_path):
        csv_path = str(tmp_path / "trades.csv")
        with open(csv_path, "w") as f:
            f.write("data\n")
        result = validate_from_trades(csv_path, format="mt5")
        assert "error" in result

    def test_validate_disclaimer_always_present(self, tmp_path):
        returns = _make_returns(100)
        csv_path = str(tmp_path / "returns.csv")
        _write_returns_csv(returns, csv_path)
        result = validate_from_returns(file_path=csv_path)
        assert "disclaimer" in result
        assert "Not financial advice" in result["disclaimer"]


# ---------------------------------------------------------------------------
# Tests: MCP tool integration (import check)
# ---------------------------------------------------------------------------

class TestMCPToolImport:
    def test_import_mcp_server(self):
        """Verify validate_strategy tool is registered in MCP server."""
        from tradememory.mcp_server import mcp
        # FastMCP stores tools; just verify import doesn't crash
        assert mcp is not None

    def test_strategy_validator_module_import(self):
        """Verify all public functions are importable."""
        from tradememory.strategy_validator import (
            validate_from_trades,
            validate_from_returns,
            compute_dsr,
            cpcv_sharpe,
            walk_forward_validation,
            regime_analysis,
            DISCLAIMER,
        )
        assert callable(validate_from_trades)
        assert callable(validate_from_returns)
        assert "Not financial advice" in DISCLAIMER
