"""Tests for StrategyRegistry — version management for live strategies."""

import json
import tempfile
from pathlib import Path

import pytest

from tradememory.evolution.strategy_registry import StrategyRegistry, StrategyVersion


# --- StrategyVersion unit tests ---


class TestStrategyVersion:
    def test_to_dict_roundtrip(self):
        v = StrategyVersion(
            version_id="V1",
            pattern={"name": "test"},
            fitness={"sharpe_ratio": 2.5},
            deploy_date="2025-01-01T00:00:00+00:00",
            reason="initial",
            num_trials=100,
            dsr=1.5,
        )
        d = v.to_dict()
        v2 = StrategyVersion.from_dict(d)
        assert v2.version_id == "V1"
        assert v2.fitness == {"sharpe_ratio": 2.5}
        assert v2.dsr == 1.5
        assert v2.num_trials == 100

    def test_is_active_when_no_retire_date(self):
        v = StrategyVersion(
            version_id="V1",
            pattern={},
            fitness={},
            deploy_date="2025-01-01T00:00:00+00:00",
        )
        assert v.is_active is True

    def test_not_active_when_retired(self):
        v = StrategyVersion(
            version_id="V1",
            pattern={},
            fitness={},
            deploy_date="2025-01-01T00:00:00+00:00",
            retire_date="2025-06-01T00:00:00+00:00",
        )
        assert v.is_active is False

    def test_from_dict_minimal(self):
        d = {"version_id": "V1", "deploy_date": "2025-01-01T00:00:00+00:00"}
        v = StrategyVersion.from_dict(d)
        assert v.version_id == "V1"
        assert v.pattern == {}
        assert v.fitness == {}
        assert v.dsr is None


# --- StrategyRegistry unit tests ---


class TestStrategyRegistry:
    def test_deploy_creates_version(self):
        reg = StrategyRegistry()
        v = reg.deploy("V1", {"name": "test"}, {"sharpe_ratio": 2.0}, reason="first")
        assert v.version_id == "V1"
        assert v.is_active is True
        assert reg.version_count == 1

    def test_deploy_retires_previous(self):
        reg = StrategyRegistry()
        reg.deploy("V1", {}, {"sharpe_ratio": 1.0}, reason="first")
        reg.deploy("V2", {}, {"sharpe_ratio": 2.0}, reason="second")

        v1 = reg.get_version("V1")
        v2 = reg.get_version("V2")
        assert v1.is_active is False
        assert v1.retire_date is not None
        assert v2.is_active is True
        assert reg.version_count == 2

    def test_get_active_returns_latest_active(self):
        reg = StrategyRegistry()
        reg.deploy("V1", {}, {})
        reg.deploy("V2", {}, {})
        active = reg.get_active()
        assert active.version_id == "V2"

    def test_get_active_none_when_empty(self):
        reg = StrategyRegistry()
        assert reg.get_active() is None

    def test_retire_by_id(self):
        reg = StrategyRegistry()
        reg.deploy("V1", {}, {})
        result = reg.retire("V1", reason="decay detected")
        assert result is not None
        assert result.is_active is False
        assert reg.get_active() is None

    def test_retire_nonexistent_returns_none(self):
        reg = StrategyRegistry()
        assert reg.retire("V999") is None

    def test_retire_already_retired_returns_none(self):
        reg = StrategyRegistry()
        reg.deploy("V1", {}, {})
        reg.retire("V1")
        assert reg.retire("V1") is None

    def test_get_version(self):
        reg = StrategyRegistry()
        reg.deploy("V1", {"a": 1}, {})
        reg.deploy("V2", {"b": 2}, {})
        v1 = reg.get_version("V1")
        assert v1.pattern == {"a": 1}

    def test_get_version_not_found(self):
        reg = StrategyRegistry()
        assert reg.get_version("V999") is None

    def test_get_history(self):
        reg = StrategyRegistry()
        reg.deploy("V1", {}, {})
        reg.deploy("V2", {}, {})
        reg.deploy("V3", {}, {})
        history = reg.get_history()
        assert len(history) == 3
        assert [v.version_id for v in history] == ["V1", "V2", "V3"]

    def test_cumulative_trials(self):
        reg = StrategyRegistry()
        reg.deploy("V1", {}, {}, num_trials=19200)
        reg.deploy("V2", {}, {}, num_trials=19200)
        assert reg.cumulative_trials == 38400

    def test_cumulative_trials_setter(self):
        reg = StrategyRegistry()
        reg.cumulative_trials = 5000
        assert reg.cumulative_trials == 5000

    def test_summary(self):
        reg = StrategyRegistry()
        reg.deploy("V1", {}, {"sharpe_ratio": 1.5}, num_trials=100, dsr=0.8)
        s = reg.summary()
        assert s["total_versions"] == 1
        assert s["active_version"] == "V1"
        assert s["cumulative_trials"] == 100
        assert s["versions"][0]["dsr"] == 0.8

    def test_deploy_with_metadata(self):
        reg = StrategyRegistry()
        v = reg.deploy("V1", {}, {}, metadata={"window": "2020-01 to 2020-04"})
        assert v.metadata == {"window": "2020-01 to 2020-04"}


# --- Persistence tests ---


class TestStrategyRegistryPersistence:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "registry.json")

            reg = StrategyRegistry(path)
            reg.deploy("V1", {"name": "test"}, {"sharpe_ratio": 2.0}, num_trials=100)
            reg.deploy("V2", {"name": "test2"}, {"sharpe_ratio": 3.0}, num_trials=200)
            reg.save()

            # Load in new instance
            reg2 = StrategyRegistry(path)
            reg2.load()
            assert reg2.version_count == 2
            assert reg2.cumulative_trials == 300
            assert reg2.get_active().version_id == "V2"
            v1 = reg2.get_version("V1")
            assert v1.is_active is False

    def test_load_missing_file(self):
        reg = StrategyRegistry("/nonexistent/path/registry.json")
        reg.load()  # should not raise
        assert reg.version_count == 0

    def test_load_corrupt_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "registry.json"
            path.write_text("not json", encoding="utf-8")

            reg = StrategyRegistry(str(path))
            reg.load()  # should not raise
            assert reg.version_count == 0

    def test_save_no_path(self):
        reg = StrategyRegistry()  # no path
        reg.deploy("V1", {}, {})
        reg.save()  # should not raise

    def test_load_no_path(self):
        reg = StrategyRegistry()
        reg.load()  # should not raise

    def test_save_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "sub" / "dir" / "registry.json")
            reg = StrategyRegistry(path)
            reg.deploy("V1", {}, {})
            reg.save()
            assert Path(path).exists()

    def test_json_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "registry.json"
            reg = StrategyRegistry(str(path))
            reg.deploy("V1", {"x": 1}, {"sharpe_ratio": 1.0}, num_trials=50, dsr=0.5)
            reg.save()

            data = json.loads(path.read_text(encoding="utf-8"))
            assert "cumulative_trials" in data
            assert "versions" in data
            assert len(data["versions"]) == 1
            assert data["versions"][0]["version_id"] == "V1"
            assert data["versions"][0]["dsr"] == 0.5
