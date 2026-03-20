"""Strategy Registry — version management for live strategies.

Tracks the lifecycle of deployed strategies: deploy, retire, query history.
Persists to a JSON file (strategy_registry.json).

Usage:
    registry = StrategyRegistry("path/to/strategy_registry.json")
    registry.load()
    registry.deploy("V1", pattern_dict, fitness_dict, reason="initial grid search")
    registry.retire("V1", reason="decay detected")
    registry.deploy("V2", new_pattern, new_fitness, reason="re-evolution after decay")
    registry.save()
    history = registry.get_history()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StrategyVersion:
    """A single version entry in the strategy registry."""

    version_id: str
    pattern: Dict[str, Any]  # CandidatePattern as dict
    fitness: Dict[str, Any]  # FitnessMetrics as dict
    deploy_date: str  # ISO format UTC
    retire_date: Optional[str] = None  # ISO format UTC, None if active
    reason: str = ""  # why deployed or retired
    num_trials: int = 0  # M tested combinations for DSR calculation
    dsr: Optional[float] = None  # Deflated Sharpe Ratio at deploy time
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "pattern": self.pattern,
            "fitness": self.fitness,
            "deploy_date": self.deploy_date,
            "retire_date": self.retire_date,
            "reason": self.reason,
            "num_trials": self.num_trials,
            "dsr": self.dsr,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> StrategyVersion:
        return cls(
            version_id=d["version_id"],
            pattern=d.get("pattern", {}),
            fitness=d.get("fitness", {}),
            deploy_date=d["deploy_date"],
            retire_date=d.get("retire_date"),
            reason=d.get("reason", ""),
            num_trials=d.get("num_trials", 0),
            dsr=d.get("dsr"),
            metadata=d.get("metadata", {}),
        )

    @property
    def is_active(self) -> bool:
        return self.retire_date is None


class StrategyRegistry:
    """Manages strategy version history with JSON persistence."""

    def __init__(self, path: Optional[str] = None):
        """Initialize registry.

        Args:
            path: Path to JSON file. If None, operates in-memory only.
        """
        self._path = Path(path) if path else None
        self._versions: List[StrategyVersion] = []
        self._cumulative_trials: int = 0  # total M across all re-evolutions

    def load(self) -> None:
        """Load registry from JSON file. No-op if path is None or file missing."""
        if self._path is None or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._versions = [
                StrategyVersion.from_dict(v) for v in data.get("versions", [])
            ]
            self._cumulative_trials = data.get("cumulative_trials", 0)
            logger.info(
                f"Loaded {len(self._versions)} versions from {self._path}"
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to load registry from {self._path}: {e}")
            self._versions = []
            self._cumulative_trials = 0

    def save(self) -> None:
        """Save registry to JSON file. No-op if path is None."""
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cumulative_trials": self._cumulative_trials,
            "versions": [v.to_dict() for v in self._versions],
        }
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(f"Saved {len(self._versions)} versions to {self._path}")

    def deploy(
        self,
        version_id: str,
        pattern: Dict[str, Any],
        fitness: Dict[str, Any],
        reason: str = "",
        num_trials: int = 0,
        dsr: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StrategyVersion:
        """Deploy a new strategy version.

        Automatically retires any currently active version.

        Args:
            version_id: Unique identifier (e.g. "V1", "V2").
            pattern: CandidatePattern as dict.
            fitness: FitnessMetrics as dict (OOS metrics).
            reason: Why this version was deployed.
            num_trials: Number of combinations tested in this round (M).
            dsr: Deflated Sharpe Ratio at deploy time.
            metadata: Additional data (e.g. regime period, window dates).

        Returns:
            The newly created StrategyVersion.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Retire any active version
        active = self.get_active()
        if active is not None:
            active.retire_date = now
            active.reason = (
                f"{active.reason}; retired for {version_id}"
                if active.reason
                else f"retired for {version_id}"
            )

        # Accumulate trials
        self._cumulative_trials += num_trials

        version = StrategyVersion(
            version_id=version_id,
            pattern=pattern,
            fitness=fitness,
            deploy_date=now,
            reason=reason,
            num_trials=num_trials,
            dsr=dsr,
            metadata=metadata or {},
        )
        self._versions.append(version)
        logger.info(f"Deployed {version_id}: {reason}")
        return version

    def retire(self, version_id: str, reason: str = "") -> Optional[StrategyVersion]:
        """Retire a specific version by ID.

        Args:
            version_id: The version to retire.
            reason: Why it was retired.

        Returns:
            The retired version, or None if not found.
        """
        for v in self._versions:
            if v.version_id == version_id and v.is_active:
                v.retire_date = datetime.now(timezone.utc).isoformat()
                if reason:
                    v.reason = f"{v.reason}; {reason}" if v.reason else reason
                logger.info(f"Retired {version_id}: {reason}")
                return v
        return None

    def get_active(self) -> Optional[StrategyVersion]:
        """Get the currently active (deployed) strategy version."""
        for v in reversed(self._versions):
            if v.is_active:
                return v
        return None

    def get_version(self, version_id: str) -> Optional[StrategyVersion]:
        """Get a specific version by ID."""
        for v in self._versions:
            if v.version_id == version_id:
                return v
        return None

    def get_history(self) -> List[StrategyVersion]:
        """Get all versions in deployment order."""
        return list(self._versions)

    @property
    def cumulative_trials(self) -> int:
        """Total number of strategy combinations tested across all re-evolutions."""
        return self._cumulative_trials

    @cumulative_trials.setter
    def cumulative_trials(self, value: int) -> None:
        self._cumulative_trials = value

    @property
    def version_count(self) -> int:
        return len(self._versions)

    def summary(self) -> Dict[str, Any]:
        """Return a summary dict of the registry state."""
        active = self.get_active()
        return {
            "total_versions": self.version_count,
            "cumulative_trials": self._cumulative_trials,
            "active_version": active.version_id if active else None,
            "active_since": active.deploy_date if active else None,
            "versions": [
                {
                    "id": v.version_id,
                    "active": v.is_active,
                    "deploy": v.deploy_date,
                    "retire": v.retire_date,
                    "sharpe": v.fitness.get("sharpe_ratio"),
                    "dsr": v.dsr,
                }
                for v in self._versions
            ],
        }
