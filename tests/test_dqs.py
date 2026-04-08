"""Tests for Decision Quality Score (DQS) engine.

Covers: no-history neutral, good conditions, regime mismatch, oversized
position, drawdown state, calibrate, MCP tool, and property-based bounds.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone

import pytest

_tmpdir = tempfile.mkdtemp()
_test_db = os.path.join(_tmpdir, "test_dqs.db")


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch):
    """Use a fresh temp database for each test."""
    import tradememory.mcp_server as mod
    from tradememory.db import Database

    db = Database(db_path=_test_db)
    mod._db = db
    yield
    mod._db = None
    if os.path.exists(_test_db):
        os.remove(_test_db)


def _get_db():
    """Get the current test DB instance."""
    import tradememory.mcp_server as mod
    return mod._db


def _insert_trade(db, trade_id, strategy, pnl, pnl_r=None, regime=None, confidence=0.5):
    """Helper to insert a trade into episodic + trade_records."""
    ts = datetime.now(timezone.utc).isoformat()
    ctx = {"symbol": "XAUUSD", "regime": regime, "price": 2650.0, "atr_d1": 30.0}
    db.insert_episodic({
        "id": trade_id,
        "timestamp": ts,
        "context_json": ctx,
        "context_regime": regime,
        "context_volatility_regime": None,
        "context_session": None,
        "context_atr_d1": 30.0,
        "context_atr_h1": None,
        "strategy": strategy,
        "direction": "long",
        "entry_price": 2650.0,
        "lot_size": 0.1,
        "exit_price": 2680.0 if pnl > 0 else 2620.0,
        "pnl": pnl,
        "pnl_r": pnl_r,
        "hold_duration_seconds": 3600,
        "max_adverse_excursion": None,
        "reflection": None,
        "confidence": confidence,
        "tags": [],
        "retrieval_strength": 1.0,
        "retrieval_count": 0,
        "last_retrieved": None,
    })


# -----------------------------------------------------------------------
# Test 1: No history — neutral scores (~5/10)
# -----------------------------------------------------------------------

def test_dqs_no_history():
    """With no trade history, DQS should return neutral scores around 5.0."""
    from tradememory.owm.dqs import DQSEngine

    db = _get_db()
    engine = DQSEngine(db)
    result = engine.compute(
        symbol="XAUUSD",
        strategy_name="VolBreakout",
        direction="long",
        proposed_lot_size=0.1,
    )

    assert 4.0 <= result.score <= 6.0, f"Expected neutral ~5, got {result.score}"
    assert result.tier in ("proceed", "caution"), f"Expected proceed/caution, got {result.tier}"
    assert result.position_multiplier in (0.3, 0.7)
    # All factors should be neutral (1.0/2.0)
    for name, info in result.factors.items():
        assert info["score"] >= 0.5, f"Factor {name} too low: {info['score']}"


# -----------------------------------------------------------------------
# Test 2: Good conditions — high score
# -----------------------------------------------------------------------

def test_dqs_good_conditions():
    """Good regime + low drawdown + proper sizing → high score."""
    from tradememory.owm.dqs import DQSEngine

    db = _get_db()

    # Insert 10 winning trades in trending_up regime
    for i in range(10):
        _insert_trade(db, f"good-{i}", "VolBreakout", pnl=200.0, pnl_r=1.5,
                       regime="trending_up", confidence=0.8)

    # Set good affective state
    db.init_affective(peak_equity=10000.0, current_equity=10000.0)

    engine = DQSEngine(db)
    result = engine.compute(
        symbol="XAUUSD",
        strategy_name="VolBreakout",
        direction="long",
        proposed_lot_size=0.1,
        context_regime="trending_up",
        context_atr_d1=30.0,
    )

    assert result.score >= 7.0, f"Expected high score, got {result.score}"
    assert result.tier == "go"
    assert result.position_multiplier == 1.0


# -----------------------------------------------------------------------
# Test 3: Regime mismatch — low regime score
# -----------------------------------------------------------------------

def test_dqs_regime_mismatch():
    """Strategy mostly wins in trending_up but current regime is ranging."""
    from tradememory.owm.dqs import DQSEngine

    db = _get_db()

    # 8 wins in trending_up
    for i in range(8):
        _insert_trade(db, f"up-{i}", "VolBreakout", pnl=200.0, pnl_r=1.0,
                       regime="trending_up")

    # 5 losses in ranging
    for i in range(5):
        _insert_trade(db, f"range-{i}", "VolBreakout", pnl=-150.0, pnl_r=-1.0,
                       regime="ranging")

    engine = DQSEngine(db)
    result = engine.compute(
        symbol="XAUUSD",
        strategy_name="VolBreakout",
        direction="long",
        context_regime="ranging",
    )

    # Regime match factor should be low
    regime_score = result.factors["regime_match"]["score"]
    assert regime_score < 1.0, f"Expected low regime score, got {regime_score}"


# -----------------------------------------------------------------------
# Test 4: Oversized position — low sizing score
# -----------------------------------------------------------------------

def test_dqs_oversized_position():
    """Proposed lot >> Kelly fraction → sizing factor low."""
    from tradememory.owm.dqs import DQSEngine

    db = _get_db()

    # Insert procedural memory with Kelly fraction
    db.upsert_procedural({
        "id": "proc-vb-xau",
        "strategy": "VolBreakout",
        "symbol": "XAUUSD",
        "behavior_type": "sizing",
        "sample_size": 20,
        "avg_hold_winners": 3600,
        "avg_hold_losers": 1800,
        "disposition_ratio": 2.0,
        "actual_lot_mean": 0.1,
        "actual_lot_variance": 0.001,
        "kelly_fraction_suggested": 0.05,
        "lot_vs_kelly_ratio": 2.0,
    })

    engine = DQSEngine(db)
    result = engine.compute(
        symbol="XAUUSD",
        strategy_name="VolBreakout",
        direction="long",
        proposed_lot_size=0.5,  # 10x Kelly of 0.05
    )

    sizing_score = result.factors["position_sizing"]["score"]
    assert sizing_score == 0.0, f"Expected 0 for 10x Kelly, got {sizing_score}"


# -----------------------------------------------------------------------
# Test 5: During drawdown — low risk state score
# -----------------------------------------------------------------------

def test_dqs_during_drawdown():
    """High drawdown + consecutive losses → risk state factor low."""
    from tradememory.owm.dqs import DQSEngine

    db = _get_db()

    # Set bad affective state: 25% drawdown, 5 consecutive losses
    db.init_affective(peak_equity=10000.0, current_equity=7500.0)
    state = db.load_affective()
    state["consecutive_losses"] = 5
    state["confidence_level"] = 0.2
    state["drawdown_state"] = 0.25  # 25%
    db.save_affective(state)

    engine = DQSEngine(db)
    result = engine.compute(
        symbol="XAUUSD",
        strategy_name="VolBreakout",
        direction="long",
    )

    risk_score = result.factors["risk_state"]["score"]
    assert risk_score == 0.0, f"Expected 0 for severe drawdown, got {risk_score}"


# -----------------------------------------------------------------------
# Test 6: Calibrate with sufficient data
# -----------------------------------------------------------------------

def test_dqs_calibrate_with_data():
    """50+ trades should produce valid calibration weights."""
    from tradememory.owm.dqs import DQSEngine

    db = _get_db()

    # Insert 60 trades: 40 wins, 20 losses
    for i in range(40):
        _insert_trade(db, f"cal-win-{i}", "VolBreakout", pnl=200.0, pnl_r=1.0,
                       regime="trending_up", confidence=0.8)
    for i in range(20):
        _insert_trade(db, f"cal-loss-{i}", "VolBreakout", pnl=-100.0, pnl_r=-0.5,
                       regime="ranging", confidence=0.4)

    db.init_affective(peak_equity=10000.0, current_equity=10000.0)

    engine = DQSEngine(db)
    cal_result = engine.calibrate(min_trades=50)

    assert cal_result["status"] == "calibrated"
    assert cal_result["sample_size"] == 60
    assert cal_result["learned_weights"] is not None
    assert len(cal_result["learned_weights"]) == 5
    assert "r_squared" in cal_result

    # Weights should be positive
    for name, w in cal_result["learned_weights"].items():
        assert w > 0, f"Weight {name} should be positive, got {w}"


def test_dqs_calibrate_insufficient_data():
    """Fewer than min_trades should return insufficient_data."""
    from tradememory.owm.dqs import DQSEngine

    db = _get_db()

    for i in range(10):
        _insert_trade(db, f"few-{i}", "VolBreakout", pnl=100.0)

    engine = DQSEngine(db)
    result = engine.calibrate(min_trades=50)

    assert result["status"] == "insufficient_data"
    assert result["sample_size"] == 10
    assert result["learned_weights"] is None


# -----------------------------------------------------------------------
# Test 7: MCP tool returns correct format
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dqs_mcp_tool():
    """compute_dqs MCP tool should return dict with expected keys."""
    from tradememory.mcp_server import compute_dqs

    result = await compute_dqs(
        symbol="XAUUSD",
        strategy_name="VolBreakout",
        direction="long",
        proposed_lot_size=0.1,
        market_context="London open",
        context_regime="trending_up",
    )

    assert "dqs_score" in result
    assert "tier" in result
    assert "position_multiplier" in result
    assert "factors" in result
    assert "recommendation" in result
    assert "context" in result

    assert isinstance(result["dqs_score"], float)
    assert result["tier"] in ("go", "proceed", "caution", "skip")
    assert result["position_multiplier"] in (0.0, 0.3, 0.7, 1.0)
    assert 0 <= result["dqs_score"] <= 10

    # Context should reflect input
    assert result["context"]["symbol"] == "XAUUSD"
    assert result["context"]["strategy"] == "VolBreakout"
    assert result["context"]["direction"] == "long"


# -----------------------------------------------------------------------
# Test 8: Property-based — DQS always in [0, 10]
# -----------------------------------------------------------------------

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    @given(
        proposed_lot=st.floats(min_value=0.001, max_value=100.0),
        regime=st.sampled_from([None, "trending_up", "trending_down", "ranging", "volatile"]),
        atr=st.one_of(st.none(), st.floats(min_value=1.0, max_value=200.0)),
    )
    @settings(max_examples=50)
    def test_property_dqs_bounded(proposed_lot, regime, atr):
        """DQS score should always be in [0, 10] regardless of inputs."""
        from tradememory.owm.dqs import DQSEngine
        from tradememory.db import Database

        # Use a fresh DB for each example
        prop_db_path = os.path.join(_tmpdir, "prop_test.db")
        try:
            db = Database(db_path=prop_db_path)
            engine = DQSEngine(db)
            result = engine.compute(
                symbol="XAUUSD",
                strategy_name="TestStrategy",
                direction="long",
                proposed_lot_size=proposed_lot,
                context_regime=regime,
                context_atr_d1=atr,
            )
            assert 0.0 <= result.score <= 10.0, f"DQS out of bounds: {result.score}"
            assert result.tier in ("go", "proceed", "caution", "skip")
            assert result.position_multiplier in (0.0, 0.3, 0.7, 1.0)
        finally:
            if os.path.exists(prop_db_path):
                os.remove(prop_db_path)

except ImportError:
    # hypothesis not installed — skip property-based test
    def test_property_dqs_bounded():
        pytest.skip("hypothesis not installed")


# -----------------------------------------------------------------------
# Test 9: DQS stored in remember_trade context_json
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dqs_stored_in_remember_trade():
    """remember_trade should store dqs_score and dqs_tier in context_json."""
    from tradememory.mcp_server import remember_trade

    db = _get_db()

    result = await remember_trade(
        symbol="XAUUSD",
        direction="long",
        entry_price=2650.0,
        exit_price=2680.0,
        pnl=300.0,
        strategy_name="VolBreakout",
        market_context="London open breakout",
        context_regime="trending_up",
        confidence=0.8,
        trade_id="dqs-integ-001",
    )

    assert result["status"] == "stored"

    # Query the stored episodic memory and check context_json
    episodes = db.query_episodic(strategy="VolBreakout", limit=1)
    assert len(episodes) >= 1

    ctx = episodes[0].get("context_json")
    if isinstance(ctx, str):
        ctx = json.loads(ctx)

    assert "dqs_score" in ctx, "dqs_score not found in context_json"
    assert "dqs_tier" in ctx, "dqs_tier not found in context_json"
    # Score should be a number or None
    if ctx["dqs_score"] is not None:
        assert 0 <= ctx["dqs_score"] <= 10
        assert ctx["dqs_tier"] in ("go", "proceed", "caution", "skip")
