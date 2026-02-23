"""Tests for MT5Connector with mocked MetaTrader5 library."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.tradememory.db import Database
from src.tradememory.journal import TradeJournal
from src.tradememory.state import StateManager
from src.tradememory.mt5_connector import MT5Connector


@pytest.fixture
def db(tmp_path):
    """Create a temp database."""
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def connector(db):
    """Create an MT5Connector with real journal/state but no MT5."""
    journal = TradeJournal(db=db)
    state_mgr = StateManager(db=db)
    conn = MT5Connector(journal=journal, state_manager=state_mgr)
    return conn


class TestMT5Init:
    """Tests for MT5Connector initialization."""

    def test_init_without_mt5_library(self, db):
        """MT5Connector initializes with mt5=None when library is unavailable."""
        with patch("src.tradememory.mt5_connector.MT5Connector._init_mt5"):
            conn = MT5Connector(journal=TradeJournal(db=db), state_manager=StateManager(db=db))
            # _init_mt5 was mocked so mt5 stays None (default from __init__)
            assert conn.mt5 is None

    def test_init_creates_journal_and_state(self):
        """MT5Connector creates default journal and state manager if not provided."""
        conn = MT5Connector()
        assert conn.journal is not None
        assert conn.state_manager is not None


class TestConnect:
    """Tests for MT5Connector.connect()."""

    def test_connect_without_mt5_raises(self, connector):
        """connect() raises RuntimeError when MT5 library is not installed."""
        connector.mt5 = None
        with pytest.raises(RuntimeError, match="MetaTrader5 library not installed"):
            connector.connect(login=12345, password="pass", server="Demo")

    def test_connect_with_mt5_success(self, connector):
        """connect() returns True when MT5 init and login succeed."""
        mock_mt5 = MagicMock()
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        connector.mt5 = mock_mt5

        result = connector.connect(login=12345, password="pass", server="Demo")
        assert result is True
        mock_mt5.initialize.assert_called_once()
        mock_mt5.login.assert_called_once_with(
            login=12345, password="pass", server="Demo"
        )

    def test_connect_with_path(self, connector):
        """connect() passes path to MT5 initialize when provided."""
        mock_mt5 = MagicMock()
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        connector.mt5 = mock_mt5

        connector.connect(login=1, password="p", server="S", path="/mt5/terminal.exe")
        mock_mt5.initialize.assert_called_once_with(path="/mt5/terminal.exe")

    def test_connect_init_fails(self, connector):
        """connect() returns False when MT5 initialize fails."""
        mock_mt5 = MagicMock()
        mock_mt5.initialize.return_value = False
        connector.mt5 = mock_mt5

        result = connector.connect(login=1, password="p", server="S")
        assert result is False

    def test_connect_login_fails(self, connector):
        """connect() returns False and shuts down when login fails."""
        mock_mt5 = MagicMock()
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = False
        connector.mt5 = mock_mt5

        result = connector.connect(login=1, password="p", server="S")
        assert result is False
        mock_mt5.shutdown.assert_called_once()


class TestDisconnect:
    """Tests for MT5Connector.disconnect()."""

    def test_disconnect_with_mt5(self, connector):
        """disconnect() calls mt5.shutdown() when MT5 is available."""
        mock_mt5 = MagicMock()
        connector.mt5 = mock_mt5
        connector.disconnect()
        mock_mt5.shutdown.assert_called_once()

    def test_disconnect_without_mt5(self, connector):
        """disconnect() does nothing when MT5 is None."""
        connector.mt5 = None
        connector.disconnect()  # Should not raise


class TestSyncTrades:
    """Tests for MT5Connector.sync_trades()."""

    def test_sync_without_mt5_raises(self, connector):
        """sync_trades() raises RuntimeError when MT5 is not connected."""
        connector.mt5 = None
        with pytest.raises(RuntimeError, match="MT5 not connected"):
            connector.sync_trades()

    def test_sync_no_history(self, connector):
        """sync_trades() returns error stats when history_deals_get returns None."""
        mock_mt5 = MagicMock()
        mock_mt5.history_deals_get.return_value = None
        connector.mt5 = mock_mt5

        result = connector.sync_trades()
        assert result == {"synced": 0, "skipped": 0, "errors": 1}

    def test_sync_empty_history(self, connector):
        """sync_trades() returns zero stats when no deals found."""
        mock_mt5 = MagicMock()
        mock_mt5.history_deals_get.return_value = ()
        connector.mt5 = mock_mt5

        result = connector.sync_trades()
        assert result["synced"] == 0
        assert result["skipped"] == 0

    def test_sync_one_complete_trade(self, connector):
        """sync_trades() records decision and outcome for a complete position."""
        # Create mock deals
        entry_deal = MagicMock()
        entry_deal.position_id = 1001
        entry_deal.symbol = "XAUUSD"
        entry_deal.volume = 0.05
        entry_deal.type = 0  # BUY
        entry_deal.price = 2890.0
        entry_deal.profit = -5.0
        entry_deal.time = int(datetime(2026, 2, 23, 9, 0).timestamp())

        exit_deal = MagicMock()
        exit_deal.position_id = 1001
        exit_deal.symbol = "XAUUSD"
        exit_deal.volume = 0.05
        exit_deal.type = 1  # SELL
        exit_deal.price = 2900.0
        exit_deal.profit = 50.0
        exit_deal.time = int(datetime(2026, 2, 23, 10, 30).timestamp())

        mock_mt5 = MagicMock()
        mock_mt5.history_deals_get.return_value = (entry_deal, exit_deal)
        connector.mt5 = mock_mt5

        result = connector.sync_trades()
        assert result["synced"] == 1
        assert result["skipped"] == 0
        assert result["errors"] == 0

        # Verify trade was recorded
        trade = connector.journal.get_trade("MT5-1001")
        assert trade is not None
        assert trade.symbol == "XAUUSD"
        assert trade.direction.value == "long"
        assert trade.pnl == 45.0  # -5 + 50

    def test_sync_skips_already_synced(self, connector):
        """sync_trades() skips trades that were already recorded."""
        entry_deal = MagicMock()
        entry_deal.position_id = 2001
        entry_deal.symbol = "XAUUSD"
        entry_deal.volume = 0.05
        entry_deal.type = 0
        entry_deal.price = 2890.0
        entry_deal.profit = 50.0
        entry_deal.time = int(datetime(2026, 2, 23, 9, 0).timestamp())

        mock_mt5 = MagicMock()
        mock_mt5.history_deals_get.return_value = (entry_deal,)
        connector.mt5 = mock_mt5

        # First sync
        connector.sync_trades()
        # Second sync — should skip
        result = connector.sync_trades()
        assert result["skipped"] == 1
        assert result["synced"] == 0


class TestDetectSession:
    """Tests for MT5Connector._detect_session()."""

    def test_asian_session(self, connector):
        """Hours 0-7 are detected as asian session."""
        ts = datetime(2026, 2, 23, 3, 0, 0)
        assert connector._detect_session(ts) == "asian"

    def test_london_session(self, connector):
        """Hours 8-15 are detected as london session."""
        ts = datetime(2026, 2, 23, 10, 30, 0)
        assert connector._detect_session(ts) == "london"

    def test_newyork_session(self, connector):
        """Hours 16-23 are detected as newyork session."""
        ts = datetime(2026, 2, 23, 18, 0, 0)
        assert connector._detect_session(ts) == "newyork"


class TestExtractTradeData:
    """Tests for MT5Connector._extract_trade_data()."""

    def test_empty_deals(self, connector):
        """Empty deal list returns None."""
        assert connector._extract_trade_data([]) is None

    def test_single_deal_no_exit(self, connector):
        """Single deal (no exit) returns data with exit_price=None."""
        deal = MagicMock()
        deal.symbol = "GBPUSD"
        deal.volume = 0.10
        deal.type = 1  # SELL
        deal.price = 1.2500
        deal.profit = 0.0
        deal.time = int(datetime(2026, 2, 23, 14, 0).timestamp())

        data = connector._extract_trade_data([deal])
        assert data is not None
        assert data["symbol"] == "GBPUSD"
        assert data["direction"] == "short"
        assert data["lot_size"] == 0.10
        assert data["exit_price"] is None

    def test_two_deals_complete_trade(self, connector):
        """Two deals (entry + exit) extracts full trade data."""
        entry = MagicMock()
        entry.symbol = "XAUUSD"
        entry.volume = 0.05
        entry.type = 0  # BUY
        entry.price = 2890.0
        entry.profit = -2.0
        entry.time = int(datetime(2026, 2, 23, 9, 0).timestamp())

        exit_d = MagicMock()
        exit_d.symbol = "XAUUSD"
        exit_d.volume = 0.05
        exit_d.type = 1  # SELL
        exit_d.price = 2900.0
        exit_d.profit = 48.0
        exit_d.time = int(datetime(2026, 2, 23, 10, 0).timestamp())

        data = connector._extract_trade_data([entry, exit_d])
        assert data["exit_price"] == 2900.0
        assert data["pnl"] == 46.0  # -2 + 48
        assert data["hold_duration"] == 60  # 1 hour = 60 min
        assert data["market_context"]["session"] == "london"
