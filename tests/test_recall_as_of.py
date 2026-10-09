"""Historical recall must be invariant to wall clock and future candidates."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from tradememory.hybrid_recall import hybrid_recall
from tradememory.owm.context import ContextVector
from tradememory.owm.recall import compute_recency, outcome_weighted_recall


CUTOFF = datetime(2020, 2, 1, tzinfo=timezone.utc)
QUERY = ContextVector(symbol="CONTROL")
PAST = {"id": "past", "timestamp": "2020-01-02T00:00:00Z", "pnl": -10,
        "context": {"symbol": "CONTROL"}, "confidence": .5}
FUTURE = {"id": "future", "timestamp": "2030-01-01T00:00:00Z", "pnl": -100000,
          "context": {"symbol": "CONTROL"}, "embedding": [1., 0.]}


class NoWallClock(datetime):
    @classmethod
    def now(cls, tz=None):
        raise AssertionError("historical recall consulted the wall clock")


def test_known_recency_uses_explicit_clock_and_timezone():
    with patch("tradememory.owm.recall.datetime", NoWallClock):
        assert compute_recency(PAST["timestamp"], as_of=CUTOFF) == pytest.approx(2 ** -.5)
        assert compute_recency("2020-02-01T02:00:00+02:00", as_of=CUTOFF) == 1.


@pytest.mark.parametrize("order", ["outcome", "losses_first"])
@pytest.mark.parametrize("embedding", [None, [1., 0.]])
def test_future_data_cannot_change_rank_or_score_or_vector_path(order, embedding):
    with patch("tradememory.owm.recall.datetime", NoWallClock):
        a = hybrid_recall(QUERY, embedding, [PAST], order=order, as_of=CUTOFF)
        b = hybrid_recall(QUERY, embedding, [PAST, FUTURE], order=order, as_of=CUTOFF)
        assert a == b


def test_positive_future_inclusion_control_and_availability():
    assert hybrid_recall(QUERY, None, [PAST, FUTURE], order="losses_first")[0].memory_id == "future"
    delayed = {**PAST, "available_at": "2020-02-02T00:00:00Z"}
    assert outcome_weighted_recall(QUERY, [delayed], as_of=CUTOFF) == []
    assert outcome_weighted_recall(QUERY, [{"id": "unknown"}], as_of=CUTOFF) == []
