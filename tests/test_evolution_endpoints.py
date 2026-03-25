"""Tests for evolution REST endpoints in server.py.

Uses FastAPI TestClient + mocked evolution functions — no real API/LLM calls.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient

from tradememory.server import app


client = TestClient(app)


# --- Helpers ---


def _mock_discover_result(count: int = 2) -> dict:
    return {
        "patterns": [
            {
                "name": f"Pattern_{i}",
                "description": f"Test pattern {i}",
                "entry_condition": {
                    "direction": "long",
                    "conditions": [{"field": "hour_utc", "op": "eq", "value": 10}],
                },
                "exit_condition": {
                    "stop_loss_atr": 1.5,
                    "take_profit_atr": 3.0,
                    "max_holding_bars": 24,
                },
                "confidence": 0.7,
            }
            for i in range(count)
        ],
        "tokens_used": 500,
        "count": count,
        "errors": [],
    }


def _mock_backtest_result() -> dict:
    return {
        "pattern_id": "PAT-001",
        "pattern_name": "TestPattern",
        "sharpe_ratio": 1.2,
        "win_rate": 0.55,
        "trade_count": 20,
        "total_pnl": 150.0,
        "max_drawdown_pct": 0.08,
    }


def _mock_evolve_result() -> dict:
    return {
        "run_id": "EVO-abc123",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "generations": 2,
        "population_size": 5,
        "per_generation": [
            {"generation": 0, "hypotheses_count": 5, "graduated_count": 1, "eliminated_count": 4},
            {"generation": 1, "hypotheses_count": 5, "graduated_count": 2, "eliminated_count": 3},
        ],
        "graduated": [{"hypothesis_id": "HYP-1", "pattern_name": "Winner", "generation": 0}],
        "graveyard": [{"hypothesis_id": "HYP-2", "pattern_name": "Loser", "generation": 0, "elimination_reason": "low_sharpe"}],
        "total_graduated": 1,
        "total_graveyard": 1,
        "total_tokens": 1000,
        "total_backtests": 10,
        "started_at": "2025-01-01T00:00:00+00:00",
        "completed_at": "2025-01-01T00:05:00+00:00",
    }


# --- POST /evolution/discover ---


class TestEvolutionDiscover:
    @patch("tradememory.evolution.mcp_tools.discover_patterns", new_callable=AsyncMock)
    @patch("tradememory.evolution.llm.AnthropicClient")
    def test_discover_success(self, mock_client_cls, mock_discover):
        mock_discover.return_value = _mock_discover_result(3)

        resp = client.post("/evolution/discover", json={
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "count": 3,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert len(data["patterns"]) == 3
        assert "tokens_used" in data

    @patch("tradememory.evolution.mcp_tools.discover_patterns", new_callable=AsyncMock)
    @patch("tradememory.evolution.llm.AnthropicClient")
    def test_discover_defaults(self, mock_client_cls, mock_discover):
        mock_discover.return_value = _mock_discover_result(5)

        resp = client.post("/evolution/discover", json={"symbol": "ETHUSDT"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 5

    @patch("tradememory.evolution.mcp_tools.discover_patterns", new_callable=AsyncMock)
    @patch("tradememory.evolution.llm.AnthropicClient")
    def test_discover_error(self, mock_client_cls, mock_discover):
        mock_discover.side_effect = RuntimeError("LLM API down")

        resp = client.post("/evolution/discover", json={"symbol": "BTCUSDT"})

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Internal server error"


# --- POST /evolution/backtest ---


class TestEvolutionBacktest:
    @patch("tradememory.evolution.mcp_tools.run_backtest", new_callable=AsyncMock)
    def test_backtest_success(self, mock_bt):
        mock_bt.return_value = _mock_backtest_result()

        resp = client.post("/evolution/backtest", json={
            "pattern_dict": {
                "name": "TestPattern",
                "entry_condition": {"direction": "long", "conditions": []},
                "exit_condition": {"stop_loss_atr": 1.5, "take_profit_atr": 3.0},
            },
            "symbol": "BTCUSDT",
            "timeframe": "1h",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["sharpe_ratio"] == 1.2
        assert data["win_rate"] == 0.55
        assert data["trade_count"] == 20

    @patch("tradememory.evolution.mcp_tools.run_backtest", new_callable=AsyncMock)
    def test_backtest_error(self, mock_bt):
        mock_bt.side_effect = RuntimeError("Invalid pattern")

        resp = client.post("/evolution/backtest", json={
            "pattern_dict": {"bad": "data"},
        })

        assert resp.status_code == 500

    def test_backtest_missing_pattern(self):
        resp = client.post("/evolution/backtest", json={})

        assert resp.status_code == 422  # Pydantic validation error


# --- POST /evolution/evolve ---


class TestEvolutionEvolve:
    @patch("tradememory.evolution.mcp_tools.evolve_strategy", new_callable=AsyncMock)
    @patch("tradememory.evolution.llm.AnthropicClient")
    def test_evolve_success(self, mock_client_cls, mock_evolve):
        mock_evolve.return_value = _mock_evolve_result()

        resp = client.post("/evolution/evolve", json={
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "generations": 2,
            "population_size": 5,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "EVO-abc123"
        assert data["total_graduated"] == 1
        assert data["total_graveyard"] == 1
        assert len(data["per_generation"]) == 2

    @patch("tradememory.evolution.mcp_tools.evolve_strategy", new_callable=AsyncMock)
    @patch("tradememory.evolution.llm.AnthropicClient")
    def test_evolve_error(self, mock_client_cls, mock_evolve):
        mock_evolve.side_effect = RuntimeError("Engine crash")

        resp = client.post("/evolution/evolve", json={"symbol": "BTCUSDT"})

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Internal server error"


# --- GET /evolution/log ---


class TestEvolutionLog:
    @patch("tradememory.evolution.mcp_tools.get_evolution_log")
    def test_log_empty(self, mock_log):
        mock_log.return_value = {"runs": [], "total_runs": 0}

        resp = client.get("/evolution/log")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 0
        assert data["runs"] == []

    @patch("tradememory.evolution.mcp_tools.get_evolution_log")
    def test_log_with_runs(self, mock_log):
        mock_log.return_value = {
            "runs": [_mock_evolve_result()],
            "total_runs": 1,
        }

        resp = client.get("/evolution/log")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 1
        assert data["runs"][0]["run_id"] == "EVO-abc123"
