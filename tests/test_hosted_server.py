"""Tests for the hosted API server."""

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def hosted_db(tmp_path):
    """Create a HostedDB with a temp database."""
    db_path = str(tmp_path / "test_hosted.db")
    from hosted.server import HostedDB
    return HostedDB(db_path)


@pytest.fixture
def client_and_key(tmp_path, monkeypatch):
    """Create a test client with a seeded API key."""
    db_path = str(tmp_path / "test_hosted.db")
    monkeypatch.setenv("TM_HOSTED_DB", db_path)

    # Reset singleton so it picks up new DB path
    import hosted.server as srv
    srv._db = None
    srv.DB_PATH = db_path

    db = srv.get_db()
    api_key = db.create_api_key("test-account", "trader")

    client = TestClient(srv.app)
    yield client, api_key

    srv._db = None


def auth_header(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


# ========== Health ==========


class TestHealth:
    def test_health_no_auth(self, client_and_key):
        client, _ = client_and_key
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.3.0"


# ========== Auth ==========


class TestAuth:
    def test_missing_auth(self, client_and_key):
        client, _ = client_and_key
        resp = client.get("/api/v1/trades")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "unauthorized"

    def test_invalid_format(self, client_and_key):
        client, _ = client_and_key
        resp = client.get("/api/v1/trades", headers={"Authorization": "Basic abc"})
        assert resp.status_code == 401

    def test_invalid_key_prefix(self, client_and_key):
        client, _ = client_and_key
        resp = client.get("/api/v1/trades", headers={"Authorization": "Bearer bad_key_123"})
        assert resp.status_code == 401

    def test_nonexistent_key(self, client_and_key):
        client, _ = client_and_key
        resp = client.get("/api/v1/trades", headers={"Authorization": "Bearer tm_live_nonexistent"})
        assert resp.status_code == 401


# ========== Store Trade ==========


class TestStoreTrade:
    def _trade_payload(self, **overrides):
        base = {
            "symbol": "XAUUSD",
            "direction": "long",
            "entry_price": 5175.50,
            "strategy_name": "VolBreakout",
            "market_context": "Asia range breakout, ATR(D1)=150",
        }
        base.update(overrides)
        return base

    def test_store_minimal(self, client_and_key):
        client, key = client_and_key
        resp = client.post("/api/v1/trades", json=self._trade_payload(), headers=auth_header(key))
        assert resp.status_code == 201
        data = resp.json()
        assert data["symbol"] == "XAUUSD"
        assert data["direction"] == "long"
        assert data["strategy"] == "VolBreakout"
        assert data["status"] == "stored"
        assert data["has_outcome"] is False
        assert data["memory_id"].startswith("tm-")

    def test_store_with_outcome(self, client_and_key):
        client, key = client_and_key
        resp = client.post(
            "/api/v1/trades",
            json=self._trade_payload(exit_price=5210.0, pnl=345.0, reflection="Clean breakout"),
            headers=auth_header(key),
        )
        assert resp.status_code == 201
        assert resp.json()["has_outcome"] is True

    def test_store_custom_id(self, client_and_key):
        client, key = client_and_key
        resp = client.post(
            "/api/v1/trades",
            json=self._trade_payload(trade_id="MT5-123456"),
            headers=auth_header(key),
        )
        assert resp.status_code == 201
        assert resp.json()["memory_id"] == "MT5-123456"

    def test_store_duplicate_id(self, client_and_key):
        client, key = client_and_key
        payload = self._trade_payload(trade_id="DUP-001")
        client.post("/api/v1/trades", json=payload, headers=auth_header(key))
        resp = client.post("/api/v1/trades", json=payload, headers=auth_header(key))
        assert resp.status_code == 409

    def test_store_invalid_direction(self, client_and_key):
        client, key = client_and_key
        resp = client.post(
            "/api/v1/trades",
            json=self._trade_payload(direction="sideways"),
            headers=auth_header(key),
        )
        assert resp.status_code == 422

    def test_store_symbol_uppercased(self, client_and_key):
        client, key = client_and_key
        resp = client.post(
            "/api/v1/trades",
            json=self._trade_payload(symbol="xauusd"),
            headers=auth_header(key),
        )
        assert resp.status_code == 201
        assert resp.json()["symbol"] == "XAUUSD"


# ========== Recall Trades ==========


class TestRecallTrades:
    def _seed_trades(self, client, key):
        """Seed 3 trades for testing."""
        trades = [
            {"symbol": "XAUUSD", "direction": "long", "entry_price": 5100, "strategy_name": "VolBreakout", "market_context": "breakout", "pnl": 100, "exit_price": 5200, "trade_id": "T-001"},
            {"symbol": "XAUUSD", "direction": "short", "entry_price": 5200, "strategy_name": "MeanReversion", "market_context": "overbought", "pnl": -50, "exit_price": 5250, "trade_id": "T-002"},
            {"symbol": "EURUSD", "direction": "long", "entry_price": 1.08, "strategy_name": "VolBreakout", "market_context": "london open", "pnl": 30, "exit_price": 1.09, "trade_id": "T-003"},
        ]
        for t in trades:
            client.post("/api/v1/trades", json=t, headers=auth_header(key))

    def test_recall_all(self, client_and_key):
        client, key = client_and_key
        self._seed_trades(client, key)
        resp = client.get("/api/v1/trades", headers=auth_header(key))
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert data["total"] == 3

    def test_recall_filter_symbol(self, client_and_key):
        client, key = client_and_key
        self._seed_trades(client, key)
        resp = client.get("/api/v1/trades?symbol=XAUUSD", headers=auth_header(key))
        assert resp.json()["count"] == 2

    def test_recall_filter_strategy(self, client_and_key):
        client, key = client_and_key
        self._seed_trades(client, key)
        resp = client.get("/api/v1/trades?strategy=VolBreakout", headers=auth_header(key))
        assert resp.json()["count"] == 2

    def test_recall_pagination(self, client_and_key):
        client, key = client_and_key
        self._seed_trades(client, key)
        resp = client.get("/api/v1/trades?limit=2&offset=0", headers=auth_header(key))
        data = resp.json()
        assert data["count"] == 2
        assert data["total"] == 3
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_recall_empty(self, client_and_key):
        client, key = client_and_key
        resp = client.get("/api/v1/trades", headers=auth_header(key))
        assert resp.json()["count"] == 0
        assert resp.json()["total"] == 0


# ========== Performance ==========


class TestPerformance:
    def _seed_trades(self, client, key):
        trades = [
            {"symbol": "XAUUSD", "direction": "long", "entry_price": 5100, "strategy_name": "VolBreakout", "market_context": "breakout", "pnl": 200, "exit_price": 5200, "trade_id": "P-001"},
            {"symbol": "XAUUSD", "direction": "long", "entry_price": 5150, "strategy_name": "VolBreakout", "market_context": "breakout", "pnl": -80, "exit_price": 5070, "trade_id": "P-002"},
            {"symbol": "XAUUSD", "direction": "short", "entry_price": 5200, "strategy_name": "MeanReversion", "market_context": "overbought", "pnl": -50, "exit_price": 5250, "trade_id": "P-003"},
            {"symbol": "XAUUSD", "direction": "long", "entry_price": 5000, "strategy_name": "VolBreakout", "market_context": "breakout", "trade_id": "P-004"},  # no pnl = open trade
        ]
        for t in trades:
            client.post("/api/v1/trades", json=t, headers=auth_header(key))

    def test_performance_all(self, client_and_key):
        client, key = client_and_key
        self._seed_trades(client, key)
        resp = client.get("/api/v1/performance", headers=auth_header(key))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_closed_trades"] == 3  # P-004 excluded (no pnl)
        assert "VolBreakout" in data["strategies"]
        assert "MeanReversion" in data["strategies"]

    def test_performance_vb_stats(self, client_and_key):
        client, key = client_and_key
        self._seed_trades(client, key)
        resp = client.get("/api/v1/performance?strategy=VolBreakout", headers=auth_header(key))
        data = resp.json()
        vb = data["strategies"]["VolBreakout"]
        assert vb["trade_count"] == 2
        assert vb["win_rate"] == 50.0
        assert vb["total_pnl"] == 120.0
        assert vb["best_trade"]["pnl"] == 200
        assert vb["worst_trade"]["pnl"] == -80

    def test_performance_empty(self, client_and_key):
        client, key = client_and_key
        resp = client.get("/api/v1/performance", headers=auth_header(key))
        data = resp.json()
        assert data["total_closed_trades"] == 0
        assert data["strategies"] == {}

    def test_performance_filter_symbol(self, client_and_key):
        client, key = client_and_key
        self._seed_trades(client, key)
        resp = client.get("/api/v1/performance?symbol=EURUSD", headers=auth_header(key))
        assert resp.json()["total_closed_trades"] == 0


# ========== Account Isolation ==========


class TestAccountIsolation:
    def test_trades_scoped_to_account(self, tmp_path, monkeypatch):
        """Trades from one account are invisible to another."""
        db_path = str(tmp_path / "iso_test.db")
        monkeypatch.setenv("TM_HOSTED_DB", db_path)

        import hosted.server as srv
        srv._db = None
        srv.DB_PATH = db_path

        db = srv.get_db()
        key_a = db.create_api_key("account-a", "trader")
        key_b = db.create_api_key("account-b", "trader")

        client = TestClient(srv.app)

        # Account A stores a trade
        client.post(
            "/api/v1/trades",
            json={"symbol": "XAUUSD", "direction": "long", "entry_price": 5000, "strategy_name": "VB", "market_context": "test"},
            headers=auth_header(key_a),
        )

        # Account A sees it
        resp_a = client.get("/api/v1/trades", headers=auth_header(key_a))
        assert resp_a.json()["count"] == 1

        # Account B does not
        resp_b = client.get("/api/v1/trades", headers=auth_header(key_b))
        assert resp_b.json()["count"] == 0

        srv._db = None


# ========== DB Seed from Env ==========


class TestEnvSeed:
    def test_seed_api_keys_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TM_API_KEYS", "tm_live_abc123:sean:trader,tm_test_xyz:demo:free")
        db_path = str(tmp_path / "seed_test.db")

        from hosted.server import HostedDB
        db = HostedDB(db_path)

        acct = db.validate_key("tm_live_abc123")
        assert acct is not None
        assert acct["account_id"] == "sean"
        assert acct["plan"] == "trader"

        acct2 = db.validate_key("tm_test_xyz")
        assert acct2 is not None
        assert acct2["account_id"] == "demo"
