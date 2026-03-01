"""
Unit tests for L3 Strategy Adjustments (table CRUD + rule-based generator).
"""

import pytest
import tempfile
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

def _make_adjustment(
    adj_id="ADJ-TEST-001",
    adj_type="strategy_disable",
    parameter="MeanReversion.enabled",
    old_value="true",
    new_value="false",
    reason="Test reason",
    source_pattern_id="AUTO-RANK-001",
    confidence=0.7,
    status="proposed",
):
    """Create a test adjustment dict."""
    return {
        'adjustment_id': adj_id,
        'adjustment_type': adj_type,
        'parameter': parameter,
        'old_value': old_value,
        'new_value': new_value,
        'reason': reason,
        'source_pattern_id': source_pattern_id,
        'confidence': confidence,
        'status': status,
        'created_at': '2026-03-01T12:00:00+00:00',
        'applied_at': None,
    }


def _insert_pattern(db, pattern_id, pattern_type, strategy, confidence, metrics):
    """Insert a pattern for testing L3 generation."""
    db.insert_pattern({
        'pattern_id': pattern_id,
        'pattern_type': pattern_type,
        'description': f'Test pattern {pattern_id}',
        'confidence': confidence,
        'sample_size': 100,
        'date_range': '2024-01-01 to 2026-02-28',
        'strategy': strategy,
        'symbol': 'XAUUSD',
        'metrics': metrics,
        'source': 'backtest_auto',
        'validation_status': 'IN_SAMPLE',
        'discovered_at': '2026-03-01T12:00:00+00:00',
    })


# ========== CRUD Tests ==========

class TestAdjustmentCRUD:
    """Test strategy_adjustments table CRUD operations."""

    def test_insert_adjustment(self, temp_db):
        adj = _make_adjustment()
        assert temp_db.insert_adjustment(adj) is True

        results = temp_db.query_adjustments()
        assert len(results) == 1
        assert results[0]['adjustment_id'] == 'ADJ-TEST-001'
        assert results[0]['adjustment_type'] == 'strategy_disable'
        assert results[0]['status'] == 'proposed'

    def test_insert_adjustment_replace(self, temp_db):
        adj = _make_adjustment()
        temp_db.insert_adjustment(adj)

        # Replace with updated reason
        adj['reason'] = 'Updated reason'
        temp_db.insert_adjustment(adj)

        results = temp_db.query_adjustments()
        assert len(results) == 1
        assert results[0]['reason'] == 'Updated reason'

    def test_query_adjustments_by_status(self, temp_db):
        temp_db.insert_adjustment(_make_adjustment(adj_id='ADJ-001', status='proposed'))
        temp_db.insert_adjustment(_make_adjustment(adj_id='ADJ-002', status='approved'))
        temp_db.insert_adjustment(_make_adjustment(adj_id='ADJ-003', status='proposed'))

        proposed = temp_db.query_adjustments(status='proposed')
        assert len(proposed) == 2

        approved = temp_db.query_adjustments(status='approved')
        assert len(approved) == 1

    def test_query_adjustments_by_type(self, temp_db):
        temp_db.insert_adjustment(_make_adjustment(
            adj_id='ADJ-001', adj_type='strategy_disable'))
        temp_db.insert_adjustment(_make_adjustment(
            adj_id='ADJ-002', adj_type='strategy_prefer'))
        temp_db.insert_adjustment(_make_adjustment(
            adj_id='ADJ-003', adj_type='strategy_disable'))

        disable = temp_db.query_adjustments(adjustment_type='strategy_disable')
        assert len(disable) == 2

        prefer = temp_db.query_adjustments(adjustment_type='strategy_prefer')
        assert len(prefer) == 1

    def test_update_adjustment_status(self, temp_db):
        temp_db.insert_adjustment(_make_adjustment())

        success = temp_db.update_adjustment_status(
            'ADJ-TEST-001', 'approved')
        assert success is True

        results = temp_db.query_adjustments()
        assert results[0]['status'] == 'approved'
        assert results[0]['applied_at'] is None

    def test_update_adjustment_status_with_applied_at(self, temp_db):
        temp_db.insert_adjustment(_make_adjustment())
        applied_time = '2026-03-01T15:00:00+00:00'

        success = temp_db.update_adjustment_status(
            'ADJ-TEST-001', 'applied', applied_at=applied_time)
        assert success is True

        results = temp_db.query_adjustments()
        assert results[0]['status'] == 'applied'
        assert results[0]['applied_at'] == applied_time

    def test_update_nonexistent_adjustment(self, temp_db):
        success = temp_db.update_adjustment_status('NONEXISTENT', 'approved')
        assert success is False


# ========== Rule Tests ==========

class TestRule1StrategyDisable:
    """Rule 1: Disable strategies with pnl_pct < -5.0 and confidence >= 0.7."""

    def test_fires_on_negative_pnl(self, temp_db, journal, reflection):
        _insert_pattern(temp_db, 'AUTO-RANK-001', 'strategy_ranking',
                        'MeanReversion', 0.7,
                        {'pnl_pct': -13.7, 'win_rate': 30.0, 'profit_factor': 0.8,
                         'total_pnl': -1370, 'variants_total': 36, 'variants_profitable': 3})

        adjustments = reflection.generate_l3_adjustments(db=temp_db)
        disable = [a for a in adjustments if a['adjustment_type'] == 'strategy_disable']
        assert len(disable) == 1
        assert disable[0]['parameter'] == 'MeanReversion.enabled'
        assert disable[0]['new_value'] == 'false'
        assert 'MeanReversion' in disable[0]['reason']

    def test_skips_low_confidence(self, temp_db, journal, reflection):
        _insert_pattern(temp_db, 'AUTO-RANK-001', 'strategy_ranking',
                        'MeanReversion', 0.5,  # confidence < 0.7
                        {'pnl_pct': -13.7, 'win_rate': 30.0, 'profit_factor': 0.8,
                         'total_pnl': -1370, 'variants_total': 36, 'variants_profitable': 3})

        adjustments = reflection.generate_l3_adjustments(db=temp_db)
        disable = [a for a in adjustments if a['adjustment_type'] == 'strategy_disable']
        assert len(disable) == 0


class TestRule2StrategyPrefer:
    """Rule 2: Prefer strategies with pnl_pct > 0 and confidence >= 0.7."""

    def test_fires_on_positive_pnl(self, temp_db, journal, reflection):
        _insert_pattern(temp_db, 'AUTO-RANK-001', 'strategy_ranking',
                        'IntradayMomentum', 0.85,
                        {'pnl_pct': 47.0, 'win_rate': 55.0, 'profit_factor': 1.89,
                         'total_pnl': 4700, 'variants_total': 36, 'variants_profitable': 34})

        adjustments = reflection.generate_l3_adjustments(db=temp_db)
        prefer = [a for a in adjustments if a['adjustment_type'] == 'strategy_prefer']
        assert len(prefer) == 1
        assert prefer[0]['parameter'] == 'IntradayMomentum.priority'
        assert prefer[0]['new_value'] == 'high'


class TestRule3SessionReduce:
    """Rule 3: Reduce exposure when worst direction WR < 35%."""

    def test_fires_on_low_wr(self, temp_db, journal, reflection):
        _insert_pattern(temp_db, 'AUTO-DIR-001', 'direction_bias',
                        'MeanReversion', 0.7,
                        {'buy_pnl_pct': -6.6, 'both_pnl_pct': -20.9,
                         'delta': 14.3, 'buy_n': 20, 'both_n': 20,
                         'buy_wr': 31.6, 'both_wr': 25.0})

        adjustments = reflection.generate_l3_adjustments(db=temp_db)
        reduce = [a for a in adjustments if a['adjustment_type'] == 'session_reduce']
        assert len(reduce) == 1
        assert '0.5' in reduce[0]['new_value']

    def test_skips_insufficient_n(self, temp_db, journal, reflection):
        _insert_pattern(temp_db, 'AUTO-DIR-001', 'direction_bias',
                        'MeanReversion', 0.7,
                        {'buy_pnl_pct': -6.6, 'both_pnl_pct': -20.9,
                         'delta': 14.3, 'buy_n': 10, 'both_n': 10,  # total=20 < 30
                         'buy_wr': 31.6, 'both_wr': 25.0})

        adjustments = reflection.generate_l3_adjustments(db=temp_db)
        reduce = [a for a in adjustments if a['adjustment_type'] == 'session_reduce']
        assert len(reduce) == 0


class TestRule4SessionIncrease:
    """Rule 4: Increase exposure when best direction WR > 60%."""

    def test_fires_on_high_wr(self, temp_db, journal, reflection):
        _insert_pattern(temp_db, 'AUTO-DIR-001', 'direction_bias',
                        'IntradayMomentum', 0.7,
                        {'buy_pnl_pct': 55.0, 'both_pnl_pct': 39.0,
                         'delta': 16.0, 'buy_n': 20, 'both_n': 20,
                         'buy_wr': 65.0, 'both_wr': 55.0})

        adjustments = reflection.generate_l3_adjustments(db=temp_db)
        increase = [a for a in adjustments if a['adjustment_type'] == 'session_increase']
        assert len(increase) == 1
        assert '1.5' in increase[0]['new_value']


class TestRule5DirectionRestrict:
    """Rule 5: Restrict to BUY-only when SELL direction drags down performance."""

    def test_fires_on_significant_delta(self, temp_db, journal, reflection):
        _insert_pattern(temp_db, 'AUTO-DIR-001', 'direction_bias',
                        'MeanReversion', 0.7,
                        {'buy_pnl_pct': -6.6, 'both_pnl_pct': -20.9,
                         'delta': 14.3, 'buy_n': 20, 'both_n': 20,
                         'buy_wr': 31.6, 'both_wr': 25.0})

        adjustments = reflection.generate_l3_adjustments(db=temp_db)
        restrict = [a for a in adjustments if a['adjustment_type'] == 'direction_restrict']
        assert len(restrict) == 1
        assert restrict[0]['new_value'] == 'BUY'
        assert 'BUY-only' in restrict[0]['reason']

    def test_skips_when_both_pnl_zero(self, temp_db, journal, reflection):
        _insert_pattern(temp_db, 'AUTO-DIR-001', 'direction_bias',
                        'MeanReversion', 0.7,
                        {'buy_pnl_pct': 5.0, 'both_pnl_pct': 0.0,
                         'delta': 5.0, 'buy_n': 20, 'both_n': 20,
                         'buy_wr': 55.0, 'both_wr': 50.0})

        adjustments = reflection.generate_l3_adjustments(db=temp_db)
        restrict = [a for a in adjustments if a['adjustment_type'] == 'direction_restrict']
        assert len(restrict) == 0  # both_pnl=0 → division guard


# ========== Edge Case Tests ==========

class TestEdgeCases:
    """Edge cases for L3 generation."""

    def test_empty_patterns(self, temp_db, journal, reflection):
        adjustments = reflection.generate_l3_adjustments(db=temp_db)
        assert adjustments == []

    def test_non_backtest_patterns_ignored(self, temp_db, journal, reflection):
        """Patterns with source != 'backtest_auto' should not generate adjustments."""
        temp_db.insert_pattern({
            'pattern_id': 'MANUAL-001',
            'pattern_type': 'strategy_ranking',
            'description': 'Manual pattern',
            'confidence': 0.9,
            'sample_size': 200,
            'date_range': '2024-01-01 to 2026-02-28',
            'strategy': 'MeanReversion',
            'symbol': None,
            'metrics': {'pnl_pct': -15.0, 'win_rate': 25.0, 'profit_factor': 0.5,
                        'total_pnl': -1500, 'variants_total': 1, 'variants_profitable': 0},
            'source': 'manual',  # Not backtest_auto
            'validation_status': 'IN_SAMPLE',
            'discovered_at': '2026-03-01T12:00:00+00:00',
        })

        adjustments = reflection.generate_l3_adjustments(db=temp_db)
        assert adjustments == []

    def test_idempotent_generation(self, temp_db, journal, reflection):
        """Running generate_l3_adjustments twice produces same count (INSERT OR REPLACE)."""
        _insert_pattern(temp_db, 'AUTO-RANK-001', 'strategy_ranking',
                        'MeanReversion', 0.7,
                        {'pnl_pct': -13.7, 'win_rate': 30.0, 'profit_factor': 0.8,
                         'total_pnl': -1370, 'variants_total': 36, 'variants_profitable': 3})

        adj1 = reflection.generate_l3_adjustments(db=temp_db)
        adj2 = reflection.generate_l3_adjustments(db=temp_db)

        assert len(adj1) == len(adj2)
        # DB should not have doubled entries
        stored = temp_db.query_adjustments()
        assert len(stored) == len(adj1)


# ========== Integration Tests ==========

class TestL3Integration:
    """Test L2 pattern discovery → L3 adjustment generation pipeline."""

    def test_full_pipeline_l2_to_l3(self, temp_db, journal, reflection):
        """Seed trades -> discover L2 patterns -> generate L3 adjustments.

        Needs n > 50 per strategy to reach confidence >= 0.7 threshold.
        """
        from tests.test_patterns import _insert_backtest_trade

        # Seed 60 IM trades (profitable) and 60 MR trades (unprofitable)
        # so strategy_ranking patterns get confidence >= 0.7
        for i in range(60):
            # IM XAUUSD BUY - profitable (80% WR)
            pnl = 500.0 if i % 5 != 0 else -200.0
            _insert_backtest_trade(
                temp_db, "IM_XAUUSD_BUY_RR3_TH0.5", i, pnl,
                "IntradayMomentum", "XAUUSD", "BUY",
                timestamp=f"2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T10:00:00")

            # MR XAUUSD BUY - unprofitable (20% WR)
            pnl = -300.0 if i % 5 != 0 else 100.0
            _insert_backtest_trade(
                temp_db, "MR_XAUUSD_BUY_BB2_RSI30", i, pnl,
                "MeanReversion", "XAUUSD", "BUY",
                timestamp=f"2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T11:00:00")

        # L2: discover patterns
        patterns = reflection.discover_patterns_from_backtest(db=temp_db)
        assert len(patterns) > 0

        # L3: generate adjustments from patterns
        adjustments = reflection.generate_l3_adjustments(db=temp_db)

        # Should have at least some adjustments
        # (IM is profitable -> Rule 2, MR is unprofitable -> Rule 1)
        assert len(adjustments) > 0

        # Verify adjustments are stored in DB
        stored = temp_db.query_adjustments()
        assert len(stored) == len(adjustments)

        # All should be proposed
        assert all(a['status'] == 'proposed' for a in stored)

        # Verify source_pattern_ids reference actual patterns
        pattern_ids = {p['pattern_id'] for p in patterns}
        for adj in stored:
            assert adj['source_pattern_id'] in pattern_ids

    def test_approve_and_apply_workflow(self, temp_db):
        """Test the proposed → approved → applied lifecycle."""
        adj = _make_adjustment()
        temp_db.insert_adjustment(adj)

        # Step 1: approve
        temp_db.update_adjustment_status('ADJ-TEST-001', 'approved')
        result = temp_db.query_adjustments(status='approved')
        assert len(result) == 1

        # Step 2: apply
        applied_time = '2026-03-01T18:00:00+00:00'
        temp_db.update_adjustment_status('ADJ-TEST-001', 'applied',
                                         applied_at=applied_time)
        result = temp_db.query_adjustments(status='applied')
        assert len(result) == 1
        assert result[0]['applied_at'] == applied_time

    def test_reject_workflow(self, temp_db):
        """Test the proposed → rejected lifecycle."""
        adj = _make_adjustment()
        temp_db.insert_adjustment(adj)

        temp_db.update_adjustment_status('ADJ-TEST-001', 'rejected')
        result = temp_db.query_adjustments(status='rejected')
        assert len(result) == 1
        assert result[0]['applied_at'] is None
