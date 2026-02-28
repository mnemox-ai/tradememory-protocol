"""
Unit tests for L2 Pattern Discovery (patterns table + auto-discovery).
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone

from src.tradememory.db import Database
from src.tradememory.journal import TradeJournal
from src.tradememory.reflection import ReflectionEngine


# ========== Fixtures ==========

@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(str(db_path))
        yield db


@pytest.fixture
def journal(temp_db):
    """Create a TradeJournal with temp database"""
    return TradeJournal(db=temp_db)


@pytest.fixture
def reflection(journal):
    """Create a ReflectionEngine with temp journal"""
    return ReflectionEngine(journal=journal)


# ========== Helpers ==========

def _insert_backtest_trade(db, variant_tag, idx, pnl, strategy, symbol,
                           direction_filter, session="london",
                           lot_size=0.1, timestamp="2025-06-15T10:00:00"):
    """Insert a backtest trade with proper tags and ID format."""
    trade_id = f"BT-{variant_tag}-{idx:04d}"
    tags = ["backtest", strategy, symbol, direction_filter, session,
            f"params:{variant_tag.split('_', 3)[-1] if '_' in variant_tag else ''}"]
    db.insert_trade({
        'id': trade_id,
        'timestamp': timestamp,
        'symbol': symbol,
        'direction': 'long' if direction_filter == 'BUY' else 'long',
        'lot_size': lot_size,
        'strategy': strategy,
        'confidence': 0.5,
        'reasoning': f"Backtest: {variant_tag}",
        'market_context': {'price': 2500.0, 'session': session},
        'references': [],
        'exit_timestamp': "2025-06-15T12:00:00",
        'exit_price': 2510.0 if pnl > 0 else 2490.0,
        'pnl': pnl,
        'pnl_r': None,
        'hold_duration': 120,
        'exit_reasoning': "Backtest exit",
        'slippage': None,
        'execution_quality': None,
        'lessons': None,
        'tags': tags,
        'grade': None,
    })


def _seed_multi_strategy_data(db):
    """Seed data with multiple strategies for comprehensive testing."""
    # IM XAUUSD BUY — profitable (4 trades)
    for i in range(4):
        pnl = 500.0 if i < 3 else -200.0  # 75% WR
        _insert_backtest_trade(db, "IM_XAUUSD_BUY_RR3_TH0.5", i, pnl,
                               "IntradayMomentum", "XAUUSD", "BUY",
                               timestamp=f"2025-06-{15+i:02d}T10:00:00")

    # IM XAUUSD BOTH — less profitable (4 trades)
    for i in range(4):
        pnl = 300.0 if i < 2 else -250.0  # 50% WR
        _insert_backtest_trade(db, "IM_XAUUSD_BOTH_RR3_TH0.5", i, pnl,
                               "IntradayMomentum", "XAUUSD", "BOTH",
                               timestamp=f"2025-06-{15+i:02d}T11:00:00")

    # IM EURUSD BUY — slightly positive (4 trades)
    for i in range(4):
        pnl = 100.0 if i < 2 else -80.0
        _insert_backtest_trade(db, "IM_EURUSD_BUY_RR3_TH0.5", i, pnl,
                               "IntradayMomentum", "EURUSD", "BUY",
                               timestamp=f"2025-06-{15+i:02d}T12:00:00")

    # VB XAUUSD BUY — profitable (4 trades)
    for i in range(4):
        pnl = 400.0 if i < 3 else -100.0
        _insert_backtest_trade(db, "VB_XAUUSD_BUY_RR3_BUF0.1", i, pnl,
                               "VolBreakout", "XAUUSD", "BUY",
                               timestamp=f"2025-06-{15+i:02d}T13:00:00")

    # VB EURUSD BUY — unprofitable (4 trades)
    for i in range(4):
        pnl = -200.0 if i < 3 else 50.0
        _insert_backtest_trade(db, "VB_EURUSD_BUY_RR3_BUF0.1", i, pnl,
                               "VolBreakout", "EURUSD", "BUY",
                               timestamp=f"2025-06-{15+i:02d}T14:00:00")

    # MR XAUUSD BUY — unprofitable (4 trades)
    for i in range(4):
        pnl = -300.0 if i < 3 else 100.0
        _insert_backtest_trade(db, "MR_XAUUSD_BUY_BB2_RSI30", i, pnl,
                               "MeanReversion", "XAUUSD", "BUY",
                               timestamp=f"2025-06-{15+i:02d}T15:00:00")

    # MR XAUUSD BOTH — very unprofitable (4 trades)
    for i in range(4):
        pnl = -400.0
        _insert_backtest_trade(db, "MR_XAUUSD_BOTH_BB2_RSI30", i, pnl,
                               "MeanReversion", "XAUUSD", "BOTH",
                               timestamp=f"2025-06-{15+i:02d}T16:00:00")


# ========== DB CRUD Tests ==========

class TestPatternsCRUD:
    """Test patterns table CRUD operations."""

    def test_insert_pattern(self, temp_db):
        pattern = {
            'pattern_id': 'TEST-001',
            'pattern_type': 'strategy_ranking',
            'description': 'Test pattern',
            'confidence': 0.7,
            'sample_size': 100,
            'date_range': '2025-01-01 to 2025-12-31',
            'strategy': 'VolBreakout',
            'symbol': 'XAUUSD',
            'metrics': {'pnl_pct': 10.5, 'win_rate': 55.0},
            'source': 'backtest_auto',
            'validation_status': 'IN_SAMPLE',
            'discovered_at': '2026-02-28T12:00:00+00:00',
        }
        assert temp_db.insert_pattern(pattern) is True

        result = temp_db.get_pattern('TEST-001')
        assert result is not None
        assert result['pattern_type'] == 'strategy_ranking'
        assert result['confidence'] == 0.7
        assert result['metrics']['pnl_pct'] == 10.5

    def test_insert_pattern_replace(self, temp_db):
        pattern = {
            'pattern_id': 'TEST-001',
            'pattern_type': 'strategy_ranking',
            'description': 'Original',
            'confidence': 0.5,
            'sample_size': 50,
            'date_range': '2025-01-01 to 2025-06-30',
            'strategy': None,
            'symbol': None,
            'metrics': {},
            'source': 'backtest_auto',
            'validation_status': 'IN_SAMPLE',
            'discovered_at': '2026-02-28T12:00:00+00:00',
        }
        temp_db.insert_pattern(pattern)

        # Update with same ID
        pattern['description'] = 'Updated'
        pattern['confidence'] = 0.8
        temp_db.insert_pattern(pattern)

        result = temp_db.get_pattern('TEST-001')
        assert result['description'] == 'Updated'
        assert result['confidence'] == 0.8

    def test_query_patterns_by_strategy(self, temp_db):
        for i, strat in enumerate(['VolBreakout', 'IntradayMomentum', 'VolBreakout']):
            temp_db.insert_pattern({
                'pattern_id': f'TEST-{i:03d}',
                'pattern_type': 'strategy_ranking',
                'description': f'{strat} pattern',
                'confidence': 0.7,
                'sample_size': 100,
                'date_range': '2025-01-01 to 2025-12-31',
                'strategy': strat,
                'symbol': None,
                'metrics': {},
                'source': 'backtest_auto',
                'validation_status': 'IN_SAMPLE',
                'discovered_at': '2026-02-28T12:00:00+00:00',
            })

        results = temp_db.query_patterns(strategy='VolBreakout')
        assert len(results) == 2

    def test_query_patterns_by_type(self, temp_db):
        for i, ptype in enumerate(['strategy_ranking', 'direction_bias', 'strategy_ranking']):
            temp_db.insert_pattern({
                'pattern_id': f'TEST-{i:03d}',
                'pattern_type': ptype,
                'description': f'{ptype} pattern',
                'confidence': 0.7,
                'sample_size': 100,
                'date_range': '2025-01-01 to 2025-12-31',
                'strategy': None,
                'symbol': None,
                'metrics': {},
                'source': 'backtest_auto',
                'validation_status': 'IN_SAMPLE',
                'discovered_at': '2026-02-28T12:00:00+00:00',
            })

        results = temp_db.query_patterns(pattern_type='direction_bias')
        assert len(results) == 1

    def test_get_pattern_not_found(self, temp_db):
        result = temp_db.get_pattern('NONEXISTENT')
        assert result is None


# ========== Confidence Tests ==========

class TestConfidence:
    """Test confidence calculation from sample size."""

    def test_confidence_low_n(self):
        assert ReflectionEngine._confidence_from_n(5) == 0.3
        assert ReflectionEngine._confidence_from_n(9) == 0.3

    def test_confidence_medium_n(self):
        assert ReflectionEngine._confidence_from_n(10) == 0.5
        assert ReflectionEngine._confidence_from_n(50) == 0.5

    def test_confidence_high_n(self):
        assert ReflectionEngine._confidence_from_n(51) == 0.7
        assert ReflectionEngine._confidence_from_n(200) == 0.7

    def test_confidence_very_high_n(self):
        assert ReflectionEngine._confidence_from_n(201) == 0.85
        assert ReflectionEngine._confidence_from_n(10000) == 0.85

    def test_confidence_consistency_bonus(self):
        assert ReflectionEngine._confidence_from_n(100, consistency_bonus=True) == 0.8
        assert ReflectionEngine._confidence_from_n(300, consistency_bonus=True) == 0.95


# ========== Detector Tests ==========

class TestStrategyRanking:
    """Test strategy ranking detector."""

    def test_detect_strategy_ranking(self, temp_db, journal, reflection):
        _seed_multi_strategy_data(temp_db)
        conn = temp_db._get_connection()
        try:
            patterns = reflection._detect_strategy_ranking(conn, 10000.0, "2025-06-15 to 2025-06-18")
        finally:
            conn.close()

        assert len(patterns) == 3  # IM, VB, MR
        # Should be sorted by total_pnl DESC
        assert patterns[0]['strategy'] == 'IntradayMomentum'
        assert patterns[0]['pattern_type'] == 'strategy_ranking'
        assert patterns[0]['metrics']['pnl_pct'] > 0
        # MR should be last (most negative)
        assert patterns[-1]['strategy'] == 'MeanReversion'
        assert patterns[-1]['metrics']['pnl_pct'] < 0


class TestDirectionBias:
    """Test direction bias detector."""

    def test_detect_direction_bias(self, temp_db, journal, reflection):
        _seed_multi_strategy_data(temp_db)
        conn = temp_db._get_connection()
        try:
            patterns = reflection._detect_direction_bias(conn, 10000.0, "2025-06-15 to 2025-06-18")
        finally:
            conn.close()

        # Should detect MR direction bias (BUY vs BOTH significant delta)
        mr_patterns = [p for p in patterns if p['strategy'] == 'MeanReversion']
        assert len(mr_patterns) > 0
        mr_p = mr_patterns[0]
        assert mr_p['pattern_type'] == 'direction_bias'
        # MR BOTH is worse (-16.0%) than BUY (-8.0%), delta should be significant
        assert mr_p['metrics']['delta'] > 0  # BUY-only better


class TestSymbolFit:
    """Test symbol fit detector."""

    def test_detect_symbol_fit(self, temp_db, journal, reflection):
        _seed_multi_strategy_data(temp_db)
        conn = temp_db._get_connection()
        try:
            patterns = reflection._detect_symbol_fit(conn, 10000.0, "2025-06-15 to 2025-06-18")
        finally:
            conn.close()

        # VB should show XAUUSD >> EURUSD
        vb_patterns = [p for p in patterns if p['strategy'] == 'VolBreakout']
        assert len(vb_patterns) > 0
        vb_p = vb_patterns[0]
        assert vb_p['metrics']['best_symbol'] == 'XAUUSD'
        assert vb_p['metrics']['worst_symbol'] == 'EURUSD'


class TestMRAnalysis:
    """Test MeanReversion-specific analysis."""

    def test_detect_mr_analysis(self, temp_db, journal, reflection):
        _seed_multi_strategy_data(temp_db)
        conn = temp_db._get_connection()
        try:
            patterns = reflection._detect_mr_analysis(conn, 10000.0, "2025-06-15 to 2025-06-18")
        finally:
            conn.close()

        assert len(patterns) >= 1
        # AUTO-MR-001: overall assessment
        mr001 = patterns[0]
        assert mr001['pattern_id'] == 'AUTO-MR-001'
        assert mr001['metrics']['avg_pnl_pct'] < 0  # MR is negative overall
        assert mr001['metrics']['variants_total'] == 2

        # AUTO-MR-002: BUY vs BOTH comparison
        if len(patterns) >= 2:
            mr002 = patterns[1]
            assert mr002['pattern_id'] == 'AUTO-MR-002'
            assert mr002['metrics']['delta'] > 0  # BUY-only less negative


class TestTopVariants:
    """Test top/bottom variant detector."""

    def test_detect_top_variants_min_trades(self, temp_db, journal, reflection):
        """With only 4 trades per variant (< 10 threshold), no patterns should be generated."""
        _seed_multi_strategy_data(temp_db)
        conn = temp_db._get_connection()
        try:
            patterns = reflection._detect_top_variants(conn, 10000.0, "2025-06-15 to 2025-06-18")
        finally:
            conn.close()

        # Each variant in seed data has only 4 trades, all below n>=10 threshold
        assert len(patterns) == 0

    def test_detect_top_variants_with_enough_data(self, temp_db, journal, reflection):
        """With 12 trades per variant, should generate top/bottom patterns."""
        # Insert 12 trades per variant (above n>=10 threshold)
        for i in range(12):
            _insert_backtest_trade(temp_db, "IM_XAUUSD_BUY_RR3_TH0.5", i, 500.0,
                                   "IntradayMomentum", "XAUUSD", "BUY",
                                   timestamp=f"2025-06-{(i % 28) + 1:02d}T10:00:00")
            _insert_backtest_trade(temp_db, "MR_XAUUSD_BUY_BB2_RSI30", i, -300.0,
                                   "MeanReversion", "XAUUSD", "BUY",
                                   timestamp=f"2025-06-{(i % 28) + 1:02d}T11:00:00")

        conn = temp_db._get_connection()
        try:
            patterns = reflection._detect_top_variants(conn, 10000.0, "2025-06-01 to 2025-06-28")
        finally:
            conn.close()

        assert len(patterns) == 2  # TOP + BOT
        top = [p for p in patterns if p['pattern_id'] == 'AUTO-TOP-001']
        bot = [p for p in patterns if p['pattern_id'] == 'AUTO-BOT-001']
        assert len(top) == 1
        assert len(bot) == 1
        # IM should be top, MR should be bottom
        assert top[0]['metrics']['ranking'][0]['strategy'] == 'IntradayMomentum'
        assert bot[0]['metrics']['ranking'][-1]['strategy'] == 'MeanReversion'


class TestDiscoverNoData:
    """Test discovery with empty database."""

    def test_discover_empty_db(self, temp_db, journal, reflection):
        patterns = reflection.discover_patterns_from_backtest(db=temp_db)
        assert patterns == []


# ========== Integration Tests ==========

class TestIntegration:
    """Test end-to-end pattern discovery + storage."""

    def test_discover_stores_to_db(self, temp_db, journal, reflection):
        _seed_multi_strategy_data(temp_db)
        patterns = reflection.discover_patterns_from_backtest(db=temp_db)

        assert len(patterns) > 0

        # Verify patterns are queryable from DB
        stored = temp_db.query_patterns()
        assert len(stored) == len(patterns)

        # Verify specific pattern types exist
        types = {p['pattern_type'] for p in stored}
        assert 'strategy_ranking' in types
        assert 'mr_analysis' in types

    def test_discover_idempotent(self, temp_db, journal, reflection):
        _seed_multi_strategy_data(temp_db)

        # Run twice
        patterns1 = reflection.discover_patterns_from_backtest(db=temp_db)
        patterns2 = reflection.discover_patterns_from_backtest(db=temp_db)

        # Same number of patterns (INSERT OR REPLACE)
        assert len(patterns1) == len(patterns2)

        # DB should still have same count (not doubled)
        stored = temp_db.query_patterns()
        assert len(stored) == len(patterns1)
