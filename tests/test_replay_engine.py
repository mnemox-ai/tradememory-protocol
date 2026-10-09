"""Tests for ReplayEngine — full replay loop with mock LLM."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from tradememory.replay.engine import ReplayEngine, run_replay
from tradememory.replay.models import (
    AgentDecision,
    Bar,
    DecisionType,
    PositionState,
    ReplayConfig,
)

SAMPLE_CSV = os.path.join(
    os.path.dirname(__file__), "..", "data", "sample_xauusd_m15.csv"
)


def _make_bars(n: int, base_price: float = 2300.0, trend: float = 0.5) -> List[Bar]:
    """Generate synthetic M15 bars."""
    bars = []
    price = base_price
    for i in range(n):
        bars.append(
            Bar(
                timestamp=datetime(2025, 1, 1) + timedelta(minutes=15 * i),
                open=price,
                high=price + 3.0,
                low=price - 2.0,
                close=price + trend,
                tick_volume=100,
                spread=20,
            )
        )
        price += trend
    return bars


def _write_csv(bars: List[Bar], path: str) -> None:
    """Write bars to MT5-format CSV."""
    with open(path, "w") as f:
        f.write("Date\tTime\tOpen\tHigh\tLow\tClose\tTickvol\tVolume\tSpread\n")
        for b in bars:
            date_str = b.timestamp.strftime("%Y.%m.%d")
            time_str = b.timestamp.strftime("%H:%M")
            f.write(
                f"{date_str}\t{time_str}\t{b.open:.2f}\t{b.high:.2f}\t"
                f"{b.low:.2f}\t{b.close:.2f}\t{b.tick_volume}\t0\t{b.spread}\n"
            )


def _hold_decision() -> AgentDecision:
    """Return a HOLD decision."""
    return AgentDecision(
        market_observation="No signal",
        reasoning_trace="No setup detected",
        decision=DecisionType.HOLD,
        confidence=0.3,
    )


def _buy_decision(
    entry: float = 2300.0, sl: float = 2290.0, tp: float = 2320.0
) -> AgentDecision:
    """Return a BUY decision."""
    return AgentDecision(
        market_observation="Breakout detected",
        reasoning_trace="Price broke above resistance",
        decision=DecisionType.BUY,
        confidence=0.8,
        strategy_used="VolBreakout",
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
    )


class TestDryRun:
    def test_dry_run_no_llm_calls(self):
        """Dry run should parse CSV and compute indicators without calling LLM."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            bars = _make_bars(120)  # enough for window_size=96
            _write_csv(bars, csv_path)

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,
                decision_interval=4,
                store_to_memory=False,
            )
            engine = ReplayEngine(config)
            summary = engine.run(dry_run=True)

            assert summary["total_bars"] == 120
            assert summary["decisions"] > 0
            assert summary["trades"] == 0
            assert summary["tokens"] == 0
            assert summary["cost"] == 0.0

    def test_dry_run_decisions_contain_indicators(self):
        """Dry-run decisions should include indicator snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            bars = _make_bars(120)
            _write_csv(bars, csv_path)

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,
                decision_interval=4,
                store_to_memory=False,
            )
            engine = ReplayEngine(config)
            engine.run(dry_run=True)

            assert len(engine.decisions) > 0
            d = engine.decisions[0]
            assert d["decision"] == "DRY_RUN"
            assert "indicators" in d
            assert "atr_m15" in d["indicators"]


class TestHoldOnly:
    @patch("tradememory.replay.engine.LLMClient")
    def test_all_holds_no_trades(self, MockLLMClient):
        """If LLM always returns HOLD, no trades should open."""
        mock_llm = MagicMock()
        mock_llm.decide.return_value = _hold_decision()
        mock_llm.total_tokens_used = 100
        mock_llm.total_cost_usd = 0.01
        MockLLMClient.return_value = mock_llm

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            bars = _make_bars(120)
            _write_csv(bars, csv_path)

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,
                decision_interval=4,
                store_to_memory=False,
            )
            engine = ReplayEngine(config)
            summary = engine.run()

            assert summary["trades"] == 0
            assert summary["equity"] == config.initial_equity
            assert mock_llm.decide.call_count > 0


class TestSingleTradeSL:
    @patch("tradememory.replay.engine.LLMClient")
    def test_buy_then_sl_hit(self, MockLLMClient):
        """BUY on first decision, then SL hit on intermediate bar."""
        # Create bars where price drops below SL after entry
        bars = []
        price = 2300.0
        for i in range(120):
            if i < 100:
                bars.append(
                    Bar(
                        timestamp=datetime(2025, 1, 1) + timedelta(minutes=15 * i),
                        open=price,
                        high=price + 3.0,
                        low=price - 2.0,
                        close=price + 0.5,
                        tick_volume=100,
                        spread=20,
                    )
                )
                price += 0.5
            else:
                # Price crashes — SL at 2290 should be hit
                bars.append(
                    Bar(
                        timestamp=datetime(2025, 1, 1) + timedelta(minutes=15 * i),
                        open=price,
                        high=price + 1.0,
                        low=2285.0,  # below SL of 2290
                        close=2286.0,
                        tick_volume=200,
                        spread=30,
                    )
                )
                price = 2286.0

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # TP set very high so it won't be hit before SL
                return _buy_decision(entry=2300.0, sl=2290.0, tp=2500.0)
            return _hold_decision()

        mock_llm = MagicMock()
        mock_llm.decide.side_effect = side_effect
        mock_llm.total_tokens_used = 200
        mock_llm.total_cost_usd = 0.02
        MockLLMClient.return_value = mock_llm

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            _write_csv(bars, csv_path)

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,
                decision_interval=4,
                store_to_memory=False,
            )
            engine = ReplayEngine(config)
            summary = engine.run()

            assert summary["trades"] >= 1
            closed = engine.tracker.closed_positions
            assert any(p.state == PositionState.CLOSED_SL for p in closed)


class TestMemoryStorage:
    @patch("tradememory.replay.engine.LLMClient")
    @patch("tradememory.db.Database")
    def test_closed_trade_stored_to_db(self, MockDatabase, MockLLMClient):
        """Closed trades should be stored via db.insert_episodic()."""
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Wide SL/TP so only EOD close triggers
                return _buy_decision(entry=2348.0, sl=2200.0, tp=2500.0)
            return _hold_decision()

        mock_llm = MagicMock()
        mock_llm.decide.side_effect = side_effect
        mock_llm.total_tokens_used = 200
        mock_llm.total_cost_usd = 0.02
        MockLLMClient.return_value = mock_llm

        mock_db = MagicMock()
        mock_db.insert_episodic.return_value = True
        MockDatabase.return_value = mock_db

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            bars = _make_bars(120, trend=0.1)
            _write_csv(bars, csv_path)

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,
                decision_interval=4,
                store_to_memory=True,
                db_path=os.path.join(tmpdir, "test.db"),
            )
            engine = ReplayEngine(config)
            engine.run()

        # Position was opened, so EOD close should trigger insert_episodic
        assert mock_db.insert_episodic.called
        call_args = mock_db.insert_episodic.call_args[0][0]
        assert "replay_" in call_args["id"]
        assert call_args["strategy"] == "VolBreakout"
        assert "replay" in call_args["tags"]


class TestEquityTracking:
    @patch("tradememory.replay.engine.LLMClient")
    def test_equity_changes_after_trade(self, MockLLMClient):
        """Equity should change after a trade closes."""
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # BUY with tight TP that will hit on uptrending bars
                return _buy_decision(entry=2348.0, sl=2290.0, tp=2354.0)
            return _hold_decision()

        mock_llm = MagicMock()
        mock_llm.decide.side_effect = side_effect
        mock_llm.total_tokens_used = 100
        mock_llm.total_cost_usd = 0.01
        MockLLMClient.return_value = mock_llm

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            # Uptrending bars — TP should be hit
            bars = _make_bars(120, base_price=2300.0, trend=1.0)
            _write_csv(bars, csv_path)

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,
                decision_interval=4,
                initial_equity=10000.0,
                store_to_memory=False,
            )
            engine = ReplayEngine(config)
            summary = engine.run()

            # Equity should differ from initial after trade
            if summary["trades"] > 0:
                assert summary["equity"] != 10000.0


class TestMaxOnePosition:
    @patch("tradememory.replay.engine.LLMClient")
    def test_second_buy_ignored_while_position_open(self, MockLLMClient):
        """Only 1 position allowed — second BUY should be ignored."""
        mock_llm = MagicMock()
        # Always return BUY
        mock_llm.decide.return_value = _buy_decision(
            entry=2348.0, sl=2200.0, tp=2500.0
        )
        mock_llm.total_tokens_used = 100
        mock_llm.total_cost_usd = 0.01
        MockLLMClient.return_value = mock_llm

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            # Flat bars — no SL/TP hit
            bars = _make_bars(120, base_price=2300.0, trend=0.1)
            _write_csv(bars, csv_path)

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,
                decision_interval=4,
                store_to_memory=False,
            )
            engine = ReplayEngine(config)
            engine.run()

            # Multiple BUY calls but only 1 position opened (closed at EOD = 1 trade)
            assert len(engine.tracker.closed_positions) <= 1


class TestEODClose:
    @patch("tradememory.replay.engine.LLMClient")
    def test_open_position_closed_at_end(self, MockLLMClient):
        """Open position at end of data should be force-closed as EOD."""
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Wide SL/TP that won't be hit
                return _buy_decision(entry=2348.0, sl=2200.0, tp=2500.0)
            return _hold_decision()

        mock_llm = MagicMock()
        mock_llm.decide.side_effect = side_effect
        mock_llm.total_tokens_used = 100
        mock_llm.total_cost_usd = 0.01
        MockLLMClient.return_value = mock_llm

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            bars = _make_bars(120, base_price=2300.0, trend=0.1)
            _write_csv(bars, csv_path)

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,
                decision_interval=4,
                store_to_memory=False,
            )
            engine = ReplayEngine(config)
            engine.run()

            assert len(engine.tracker.closed_positions) == 1
            assert (
                engine.tracker.closed_positions[0].state == PositionState.CLOSED_EOD
            )
            assert engine.tracker.current_position is None


class TestPrecomputedD1ATR:
    def test_dry_run_uses_precomputed_d1_atr(self):
        """D1 ATR should be available even with small window if enough total bars."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            # 20 days of data (20 * 96 = 1920 M15 bars) — enough for D1 ATR(14)
            bars = _make_bars(20 * 96, base_price=2300.0, trend=0.5)
            _write_csv(bars, csv_path)

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,  # only 1 day window — normally can't compute D1 ATR
                decision_interval=96,
                store_to_memory=False,
            )
            engine = ReplayEngine(config)
            engine.run(dry_run=True)

            # Pre-computed D1 ATR lookup should be populated
            assert len(engine._d1_atr_lookup) > 0

            # Later decisions should have non-None atr_d1
            later_decisions = [
                d for d in engine.decisions
                if d["indicators"]["atr_d1"] is not None
            ]
            assert len(later_decisions) > 0

    def test_d1_atr_lookup_helper(self):
        """_lookup_d1_atr should find the most recent available date."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            bars = _make_bars(120)
            _write_csv(bars, csv_path)

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,
                store_to_memory=False,
            )
            engine = ReplayEngine(config)
            # Manually populate lookup
            from datetime import date
            engine._d1_atr_lookup = {
                date(2025, 1, 3): 15.0,
                date(2025, 1, 5): 18.0,
            }

            # Exact match
            assert engine._lookup_d1_atr(datetime(2025, 1, 5, 12, 0)) == 18.0
            # Falls back to Jan 5 (Jan 6 not in lookup)
            assert engine._lookup_d1_atr(datetime(2025, 1, 6, 12, 0)) == 18.0
            # Falls back to Jan 3 (before Jan 5)
            assert engine._lookup_d1_atr(datetime(2025, 1, 4, 12, 0)) == 15.0
            # No data available
            assert engine._lookup_d1_atr(datetime(2024, 12, 1, 12, 0)) is None


class TestSummaryFormat:
    def test_summary_has_all_fields(self):
        """_build_summary() should return all required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            bars = _make_bars(120)
            _write_csv(bars, csv_path)

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,
                decision_interval=4,
                store_to_memory=False,
            )
            engine = ReplayEngine(config)
            summary = engine.run(dry_run=True)

            expected_keys = {
                "total_bars",
                "decisions",
                "trades",
                "equity",
                "win_rate",
                "profit_factor",
                "tokens",
                "cost",
                "memory_recalls_count",
            }
            assert set(summary.keys()) == expected_keys

    def test_summary_empty_data(self):
        """Summary on empty CSV should return zeros."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "empty.csv")
            with open(csv_path, "w") as f:
                f.write(
                    "Date\tTime\tOpen\tHigh\tLow\tClose\tTickvol\tVolume\tSpread\n"
                )

            config = ReplayConfig(
                data_path=csv_path,
                window_size=96,
                decision_interval=4,
                store_to_memory=False,
            )
            engine = ReplayEngine(config)
            summary = engine.run(dry_run=True)

            assert summary["total_bars"] == 0
            assert summary["decisions"] == 0
            assert summary["trades"] == 0

class TestHistoricalIsolation:
    @pytest.mark.parametrize("interval", [4, 128])
    @patch("tradememory.replay.engine.LLMClient")
    def test_cap_ends_at_decision_even_without_next_scheduled_decision(self, MockLLMClient, interval, tmp_path):
        csv = tmp_path/"prices.csv"
        bars = _make_bars(120)
        _write_csv(bars, str(csv))
        mock = MagicMock()
        mock.decide.return_value = _buy_decision(entry=2348., sl=2200., tp=2500.)
        mock.total_tokens_used = 0
        mock.total_cost_usd = 0.
        MockLLMClient.return_value = mock
        engine = ReplayEngine(ReplayConfig(data_path=str(csv), decision_interval=interval,
                                          max_decisions=1, store_to_memory=False, log_path=None))
        engine.run()
        assert engine.tracker.closed_positions[0].exit_time == bars[95].timestamp

    @patch("tradememory.replay.engine.LLMClient")
    def test_stored_outcome_is_unavailable_until_exit(self, MockLLMClient, tmp_path):
        from datetime import timezone
        from tradememory.replay.memory_recall import query_replay_memories
        mock = MagicMock()
        mock.decide.side_effect = [_buy_decision(entry=2348., sl=2200., tp=2500.), _hold_decision()]
        mock.total_tokens_used = 0
        mock.total_cost_usd = 0.
        MockLLMClient.return_value = mock
        csv = tmp_path/"prices.csv"
        _write_csv(_make_bars(120), str(csv))
        db_path = str(tmp_path/"memory.db")
        engine = ReplayEngine(ReplayConfig(data_path=str(csv), db_path=db_path, max_decisions=2,
                                          log_path=None, checkpoint_path=str(tmp_path/"checkpoint.json")))
        engine.run()
        trade = engine.tracker.closed_positions[0]
        exit_utc = (trade.exit_time-timedelta(hours=2)).replace(tzinfo=timezone.utc)
        assert query_replay_memories(db_path, as_of=exit_utc-timedelta(microseconds=1)) == []
        known = query_replay_memories(db_path, as_of=exit_utc)
        assert len(known) == 1
        assert datetime.fromisoformat(known[0]["available_at"]) == exit_utc
        assert json.loads(known[0]["context_json"])["symbol"] == "XAUUSD"

    @patch("tradememory.replay.engine.LLMClient")
    def test_legacy_callback_cannot_silently_ignore_clock(self, MockLLMClient, tmp_path):
        csv = tmp_path/"prices.csv"
        _write_csv(_make_bars(120), str(csv))
        def old_callback(db_path, strategy, regime, session, atr_d1):
            return "unsafe history"
        engine = ReplayEngine(ReplayConfig(data_path=str(csv), store_to_memory=False,
                                          use_memory_recall=True, memory_recall_fn=old_callback))
        with pytest.raises(TypeError, match="as_of"):
            engine.run()

    @patch("tradememory.replay.engine.LLMClient")
    def test_callback_receives_utc_and_outputs_have_distinct_paths(self, MockLLMClient, tmp_path):
        from datetime import timezone
        mock = MagicMock()
        mock.decide.return_value = _hold_decision()
        mock.total_tokens_used = 0
        mock.total_cost_usd = 0.
        MockLLMClient.return_value = mock
        bars = _make_bars(120)
        csv = tmp_path / "shared.csv"
        _write_csv(bars, str(csv))
        seen = []
        def recall(**kwargs):
            seen.append(kwargs["as_of"])
            return ""
        for arm in ["a", "b"]:
            folder = tmp_path / arm
            folder.mkdir()
            config = ReplayConfig(data_path=str(csv), max_decisions=1,
                                  store_to_memory=False, use_memory_recall=True,
                                  memory_recall_fn=recall, db_path=str(folder/"memory.db"),
                                  checkpoint_path=str(folder/"checkpoint.json"), log_path=str(folder/"decisions.jsonl"))
            ReplayEngine(config).run()
        expected = (bars[95].timestamp - timedelta(hours=2)).replace(tzinfo=timezone.utc)
        assert seen == [expected, expected]
        assert (tmp_path/"a/checkpoint.json").exists() and (tmp_path/"b/checkpoint.json").exists()
        assert not csv.with_suffix(".checkpoint.json").exists()

    @patch("tradememory.replay.engine.LLMClient")
    def test_future_prices_cannot_change_capped_run_outcome(self, MockLLMClient, tmp_path):
        results = []
        for changed in [False, True]:
            bars = _make_bars(120)
            if changed:
                for bar in bars[100:]:
                    bar.high = 10000.; bar.low = 1.; bar.close = 9000.
            csv = tmp_path / f"{changed}.csv"
            _write_csv(bars, str(csv))
            mock = MagicMock()
            mock.decide.side_effect = [_buy_decision(entry=2348., sl=2200., tp=2500.), _hold_decision()]
            mock.total_tokens_used = 0
            mock.total_cost_usd = 0.
            MockLLMClient.return_value = mock
            config = ReplayConfig(data_path=str(csv), max_decisions=2, store_to_memory=False,
                                  log_path=None, checkpoint_path=str(tmp_path/f"{changed}.checkpoint.json"))
            engine = ReplayEngine(config)
            summary = engine.run()
            assert engine.tracker.closed_positions[0].exit_time == bars[99].timestamp
            results.append(summary["equity"])
        assert results[0] == results[1]

    def test_dry_run_obeys_same_decision_cap(self, tmp_path):
        csv = tmp_path/"prices.csv"
        _write_csv(_make_bars(120), str(csv))
        engine = ReplayEngine(ReplayConfig(data_path=str(csv), max_decisions=2, store_to_memory=False))
        assert engine.run(dry_run=True)["decisions"] == 2
