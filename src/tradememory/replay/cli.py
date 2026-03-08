"""CLI entry point for the XAUUSD LLM Trading Agent Replay Engine."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.tradememory.replay.engine import ReplayEngine, run_replay
from src.tradememory.replay.models import ReplayConfig


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="XAUUSD LLM Trading Agent Replay Engine",
        prog="tradememory.replay",
    )
    parser.add_argument("--config", type=str, help="Path to YAML config file")
    parser.add_argument(
        "--data", type=str, help="Path to MT5 CSV file (overrides config)"
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["deepseek", "claude"],
        help="LLM provider (overrides config)",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="LLM model name (e.g. claude-3-5-haiku-20241022, deepseek-chat)",
    )
    parser.add_argument(
        "--max-decisions",
        type=int,
        default=0,
        help="Stop after N decisions (0 = unlimited, useful for cost control)",
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume from last checkpoint"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse CSV + compute indicators only, no LLM calls",
    )
    return parser.parse_args(argv)


def load_config(args: argparse.Namespace) -> ReplayConfig:
    """Build ReplayConfig from CLI args and optional YAML file."""
    config_dict: Dict[str, Any] = {}

    if args.config:
        path = Path(args.config)
        with open(path) as f:
            config_dict = yaml.safe_load(f) or {}

    if args.data:
        config_dict["data_path"] = args.data
    if args.provider:
        config_dict["llm_provider"] = args.provider
    if hasattr(args, "model") and args.model:
        config_dict["llm_model"] = args.model
    if hasattr(args, "max_decisions") and args.max_decisions:
        config_dict["max_decisions"] = args.max_decisions

    if "data_path" not in config_dict:
        print("Error: --data or config.data_path is required", file=sys.stderr)
        sys.exit(1)

    config = ReplayConfig(**config_dict)

    # Handle resume
    if args.resume:
        checkpoint_path = Path(config.data_path).with_suffix(".checkpoint.json")
        if checkpoint_path.exists():
            cp = json.loads(checkpoint_path.read_text())
            config.resume_from_bar = cp.get("bar_idx", 0) + 1
            print(f"Resuming from bar {config.resume_from_bar}")

    return config


def main(argv: Optional[List[str]] = None) -> Dict[str, Any]:
    args = parse_args(argv)
    config = load_config(args)

    summary = run_replay(config, dry_run=args.dry_run)

    print("\n=== Replay Summary ===")
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
