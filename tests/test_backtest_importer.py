"""Tests for backtest_importer module."""

import os
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.tradememory.backtest_importer import (
    classify_session,
    parse_mt5_report,
    parse_variant_tag,
    build_trade_records,
)


class TestClassifySession:
    def test_asian_session(self):
        assert classify_session(0) == "asian"
        assert classify_session(3) == "asian"
        assert classify_session(7) == "asian"

    def test_london_session(self):
        assert classify_session(8) == "london"
        assert classify_session(12) == "london"
        assert classify_session(15) == "london"

    def test_newyork_session(self):
        assert classify_session(16) == "newyork"
        assert classify_session(20) == "newyork"
        assert classify_session(23) == "newyork"


class TestParseVariantTag:
    def test_vb_tag(self):
        result = parse_variant_tag("VB_XAUUSD_BUY_RR3_BUF0.1")
        assert result['strategy'] == 'VolBreakout'
        assert result['symbol'] == 'XAUUSD'
        assert result['direction_filter'] == 'BUY'
        assert 'RR3' in result['params']

    def test_im_tag(self):
        result = parse_variant_tag("IM_EURUSD_BOTH_RR2.5_TH0.55")
        assert result['strategy'] == 'IntradayMomentum'
        assert result['symbol'] == 'EURUSD'
        assert result['direction_filter'] == 'BOTH'

    def test_mr_tag(self):
        result = parse_variant_tag("MR_XAUUSD_BUY_BB2.0_RSI30")
        assert result['strategy'] == 'MeanReversion'
        assert result['symbol'] == 'XAUUSD'

    def test_pb_tag(self):
        result = parse_variant_tag("PB_XAUUSD_BUY_RR2_PCT0.6")
        assert result['strategy'] == 'PullbackEntry'


class TestParseMT5Report:
    @pytest.fixture
    def sample_report(self, tmp_path):
        """Create a minimal MT5-style HTML report (UTF-16LE)."""
        html = """<!DOCTYPE html>
<html><body>
<table>
   <tr bgcolor="#F7F7F7" align=right><td>2024.01.03 15:15:00</td><td>2</td><td>XAUUSD</td><td>buy</td><td>in</td><td>0.05</td><td>2050.50</td><td>2</td><td>0.00</td><td>0.00</td><td>0.00</td><td>10000.00</td><td>NG_Gold v1</td></tr>
   <tr bgcolor="#FFFFFF" align=right><td>2024.01.03 16:30:00</td><td>3</td><td>XAUUSD</td><td>sell</td><td>out</td><td>0.05</td><td>2055.00</td><td>3</td><td>0.00</td><td>0.00</td><td>22.50</td><td>10022.50</td><td></td></tr>
   <tr bgcolor="#F7F7F7" align=right><td>2024.01.05 10:00:00</td><td>4</td><td>XAUUSD</td><td>sell</td><td>in</td><td>0.03</td><td>2060.00</td><td>4</td><td>0.00</td><td>0.00</td><td>0.00</td><td>10022.50</td><td>NG_Gold v1</td></tr>
   <tr bgcolor="#FFFFFF" align=right><td>2024.01.05 14:00:00</td><td>5</td><td>XAUUSD</td><td>buy</td><td>out</td><td>0.03</td><td>2065.00</td><td>5</td><td>0.00</td><td>0.00</td><td>-15.00</td><td>10007.50</td><td></td></tr>
</table>
</body></html>"""
        report_file = tmp_path / "test_report.htm"
        report_file.write_text(html, encoding='utf-16-le')
        return str(report_file)

    def test_parse_two_trades(self, sample_report):
        trades = parse_mt5_report(sample_report)
        assert len(trades) == 2

    def test_first_trade_long(self, sample_report):
        trades = parse_mt5_report(sample_report)
        t = trades[0]
        assert t['direction'] == 'long'
        assert t['entry_price'] == 2050.50
        assert t['exit_price'] == 2055.00
        assert t['pnl'] == 22.50
        assert t['volume'] == 0.05
        assert t['symbol'] == 'XAUUSD'

    def test_second_trade_short(self, sample_report):
        trades = parse_mt5_report(sample_report)
        t = trades[1]
        assert t['direction'] == 'short'
        assert t['entry_price'] == 2060.00
        assert t['exit_price'] == 2065.00
        assert t['pnl'] == -15.00
        assert t['volume'] == 0.03

    def test_hold_duration(self, sample_report):
        trades = parse_mt5_report(sample_report)
        # First trade: 15:15 to 16:30 = 75 min
        assert trades[0]['hold_duration_min'] == 75
        # Second trade: 10:00 to 14:00 = 240 min
        assert trades[1]['hold_duration_min'] == 240

    def test_empty_report(self, tmp_path):
        html = "<!DOCTYPE html><html><body><table></table></body></html>"
        report_file = tmp_path / "empty_report.htm"
        report_file.write_text(html, encoding='utf-16-le')
        trades = parse_mt5_report(str(report_file))
        assert len(trades) == 0

    def test_nonexistent_file(self):
        trades = parse_mt5_report("/nonexistent/path/report.htm")
        assert len(trades) == 0


class TestBuildTradeRecords:
    def test_builds_correct_records(self):
        trades = [{
            'entry_time': datetime(2024, 1, 3, 10, 0, 0, tzinfo=timezone.utc),
            'exit_time': datetime(2024, 1, 3, 14, 0, 0, tzinfo=timezone.utc),
            'symbol': 'XAUUSD',
            'direction': 'long',
            'volume': 0.05,
            'entry_price': 2050.50,
            'exit_price': 2055.00,
            'pnl': 22.50,
            'hold_duration_min': 240,
        }]

        records = build_trade_records(trades, "VB_XAUUSD_BUY_RR3_BUF0.1")
        assert len(records) == 1

        r = records[0]
        assert r['id'] == 'BT-VB_XAUUSD_BUY_RR3_BUF0.1-0001'
        assert r['symbol'] == 'XAUUSD'
        assert r['direction'] == 'long'
        assert r['lot_size'] == 0.05
        assert r['strategy'] == 'VolBreakout'
        assert r['confidence'] == 0.5
        assert r['pnl'] == 22.50
        assert r['hold_duration'] == 240
        assert 'backtest' in r['tags']
        assert 'Backtest' in r['reasoning']
        assert r['market_context']['session'] == 'london'

    def test_trade_id_format(self):
        trades = [
            {'entry_time': datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc),
             'exit_time': datetime(2024, 1, 1, 2, 0, tzinfo=timezone.utc),
             'symbol': 'EURUSD', 'direction': 'short', 'volume': 0.1,
             'entry_price': 1.1, 'exit_price': 1.09, 'pnl': 10,
             'hold_duration_min': 60}
        ] * 3

        records = build_trade_records(trades, "IM_EURUSD_BOTH_RR2.5_TH0.55")
        ids = [r['id'] for r in records]
        assert ids == [
            'BT-IM_EURUSD_BOTH_RR2.5_TH0.55-0001',
            'BT-IM_EURUSD_BOTH_RR2.5_TH0.55-0002',
            'BT-IM_EURUSD_BOTH_RR2.5_TH0.55-0003',
        ]

    def test_session_classification_in_records(self):
        # Asian session trade (hour 3)
        trades = [{
            'entry_time': datetime(2024, 1, 1, 3, 0, tzinfo=timezone.utc),
            'exit_time': datetime(2024, 1, 1, 5, 0, tzinfo=timezone.utc),
            'symbol': 'XAUUSD', 'direction': 'long', 'volume': 0.01,
            'entry_price': 2000, 'exit_price': 2010, 'pnl': 10,
            'hold_duration_min': 120}]

        records = build_trade_records(trades, "MR_XAUUSD_BUY_BB2.0_RSI30")
        assert records[0]['market_context']['session'] == 'asian'


class TestWithRealReports:
    """Test with actual MT5 reports if available."""

    REPORT_DIR = r"C:\Users\johns\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\reports"

    @pytest.fixture
    def real_report(self):
        """Get a real report if available (skip if not on Windows with reports)."""
        report_path = os.path.join(self.REPORT_DIR, "VB_GBPUSD_report.htm")
        if not os.path.exists(report_path):
            pytest.skip("Real MT5 reports not available")
        return report_path

    def test_parse_real_vb_gbpusd(self, real_report):
        trades = parse_mt5_report(real_report)
        assert len(trades) > 100  # VB GBPUSD had 503 trades
        # All trades should have required fields
        for t in trades[:10]:
            assert t['symbol'] == 'GBPUSD'
            assert t['direction'] in ('long', 'short')
            assert t['volume'] > 0
            assert t['hold_duration_min'] >= 1

    def test_build_records_from_real(self, real_report):
        trades = parse_mt5_report(real_report)
        records = build_trade_records(trades[:5], "VB_GBPUSD_BOTH_RR3.5_BUF0.15")
        assert len(records) == 5
        for r in records:
            assert r['id'].startswith('BT-')
            assert r['strategy'] == 'VolBreakout'
            assert r['confidence'] == 0.5
            assert 'backtest' in r['tags']
