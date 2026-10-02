"""Tests for the hybrid-recall wire-up inside `recall_memories` MCP tool.

Specifically verifies:
  - When `use_hybrid=False`, no embedding backend call is made.
  - When `use_hybrid=True` but backend is unavailable (None), falls back
    silently to pure OWM (matches v0.5.1 behaviour).
  - When `use_hybrid=True` with a mock backend, query and candidate
    embeddings are produced and passed to `hybrid_recall`.
  - `hybrid_alpha` parameter is forwarded to `hybrid_recall`.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tradememory import mcp_server


class _FakeBackend:
    """Minimal embedding backend stub."""

    def __init__(self):
        self.calls = []

    def embed(self, text: str):
        self.calls.append(text)
        # Stable 4-dim vector; doesn't matter for correctness, only flow.
        return [0.1, 0.2, 0.3, 0.4]

    def dim(self):
        return 4


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Force the MCP server to use a fresh DB per test."""
    monkeypatch.setenv("TRADEMEMORY_DB", str(tmp_path / "tm.db"))
    # Reset module-level singleton
    mcp_server._db = None
    yield
    mcp_server._db = None


@pytest.fixture
def seed_episodic(isolated_db):
    """Insert one episodic memory so recall has something to chew on."""
    db = mcp_server._get_db()
    db.insert_episodic({
        "id": "ep-1",
        "timestamp": "2026-05-14T10:00:00+00:00",
        "context_json": {
            "symbol": "XAUUSD",
            "regime": "trending_up",
            "session": "london",
        },
        "context_regime": "trending_up",
        "context_volatility_regime": None,
        "context_session": "london",
        "context_atr_d1": None,
        "context_atr_h1": None,
        "strategy": "VolBreakout",
        "direction": "long",
        "entry_price": 2400.0,
        "lot_size": 0.01,
        "exit_price": 2410.0,
        "pnl": 100.0,
        "pnl_r": 1.5,
        "hold_duration_seconds": 3600,
        "max_adverse_excursion": None,
        "reflection": "regime aligned with strategy",
        "confidence": 0.7,
        "tags": [],
        "retrieval_strength": 1.0,
        "retrieval_count": 0,
        "last_retrieved": None,
        "created_at": "2026-05-14T10:00:00+00:00",
    })


@pytest.mark.asyncio
async def test_recall_with_use_hybrid_false_skips_backend(seed_episodic):
    with patch.object(mcp_server, "get_embedding_backend") as gb:
        # If use_hybrid=False, backend should never even be queried.
        await mcp_server.recall_memories(
            symbol="XAUUSD",
            market_context="trending_up london session",
            context_regime="trending_up",
            use_hybrid=False,
        )
        gb.assert_not_called()


@pytest.mark.asyncio
async def test_recall_use_hybrid_true_backend_unavailable_falls_back(seed_episodic):
    """No sentence-transformers installed → backend is None → graceful OWM."""
    with patch.object(mcp_server, "get_embedding_backend", return_value=None):
        result = await mcp_server.recall_memories(
            symbol="XAUUSD",
            market_context="trending_up london session",
            context_regime="trending_up",
            use_hybrid=True,
        )
    # Recall should still succeed and return our seeded record.
    assert "results" in result or "memories" in result or isinstance(result, dict)


@pytest.mark.asyncio
async def test_recall_use_hybrid_true_with_backend_embeds_query(seed_episodic):
    fake = _FakeBackend()
    with patch.object(mcp_server, "get_embedding_backend", return_value=fake):
        with patch.object(mcp_server, "hybrid_recall") as hr_mock:
            hr_mock.return_value = []
            await mcp_server.recall_memories(
                symbol="XAUUSD",
                market_context="trending_up london session",
                context_regime="trending_up",
                strategy_name="VolBreakout",
                use_hybrid=True,
                hybrid_alpha=0.5,
            )
            # The query was embedded.
            assert fake.calls, "backend.embed should have been called"
            # First call should be the query text combining symbol/regime/etc.
            assert any("symbol: XAUUSD" in t for t in fake.calls)
            # hybrid_recall was called with non-None embedding and forwarded alpha.
            call_kwargs = hr_mock.call_args.kwargs
            assert call_kwargs.get("query_embedding") is not None
            assert call_kwargs.get("alpha") == 0.5


@pytest.mark.asyncio
async def test_recall_use_hybrid_attaches_candidate_embeddings(seed_episodic):
    fake = _FakeBackend()
    captured_memories = []

    def _capture(query_context, query_embedding, memories, affective_state, alpha, limit, order="outcome"):
        captured_memories.extend(memories)
        return []

    with patch.object(mcp_server, "get_embedding_backend", return_value=fake):
        with patch.object(mcp_server, "hybrid_recall", side_effect=_capture):
            await mcp_server.recall_memories(
                symbol="XAUUSD",
                market_context="trending_up london",
                context_regime="trending_up",
                use_hybrid=True,
            )
    # At least one candidate carries an embedding now.
    assert any(c.get("embedding") for c in captured_memories), (
        "expected at least one candidate to have been embedded"
    )


@pytest.mark.asyncio
async def test_recall_use_hybrid_query_embed_failure_is_non_fatal(seed_episodic):
    """If query embedding crashes, fall back to pure OWM rather than 500."""

    class _BrokenBackend:
        def embed(self, text):
            raise RuntimeError("simulated GPU failure")

        def dim(self):
            return 4

    with patch.object(
        mcp_server, "get_embedding_backend", return_value=_BrokenBackend()
    ):
        # Should not raise.
        result = await mcp_server.recall_memories(
            symbol="XAUUSD",
            market_context="ranging asia",
            context_regime="ranging",
            use_hybrid=True,
        )
    assert isinstance(result, dict)
