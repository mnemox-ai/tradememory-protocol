#!/usr/bin/env python3
"""Generate validation charts for VALIDATION_RESULTS.md.

Outputs 3 PNGs to docs/validation/:
  1. baseline_distribution.png — Random baseline Sharpe distribution + strategy markers
  2. walk_forward_windows.png — OOS Sharpe per window for C and E
  3. ablation_comparison.png  — Full vs no-trend percentile comparison

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/generate_validation_charts.py
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / "docs" / "validation"
OUT_DIR.mkdir(exist_ok=True)

# Mnemox brand colors
CYAN = "#00b4ff"
DARK_BG = "#0d1117"
CARD_BG = "#161b22"
TEXT = "#c9d1d9"
GREEN = "#3fb950"
RED = "#f85149"
ORANGE = "#d29922"
PURPLE = "#bc8cff"

plt.rcParams.update({
    "figure.facecolor": DARK_BG,
    "axes.facecolor": CARD_BG,
    "axes.edgecolor": "#30363d",
    "axes.labelcolor": TEXT,
    "text.color": TEXT,
    "xtick.color": TEXT,
    "ytick.color": TEXT,
    "grid.color": "#21262d",
    "grid.alpha": 0.5,
    "font.size": 11,
    "font.family": "sans-serif",
})


def load_step1():
    with open(ROOT / "validation_step1_results.json", encoding="utf-8") as f:
        return json.load(f)


def load_step2():
    with open(ROOT / "validation_step2_results.json", encoding="utf-8") as f:
        return json.load(f)


def chart_baseline_distribution(step1: dict):
    """Chart 1: Random baseline Sharpe distribution with strategy markers."""
    bl = step1["baseline"]
    mean, std = bl["mean_sharpe"], bl["std_sharpe"]
    p95 = bl["p95"]

    # Generate normal distribution curve (approximation of actual distribution)
    x = np.linspace(mean - 4 * std, mean + 4 * std, 500)
    y = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / std) ** 2)

    fig, ax = plt.subplots(figsize=(10, 5))

    # Distribution curve
    ax.fill_between(x, y, alpha=0.3, color=CYAN)
    ax.plot(x, y, color=CYAN, linewidth=2, label=f"Random baseline (n=1000)\nmean={mean:.2f}, std={std:.2f}")

    # P95 threshold
    ax.axvline(p95, color=ORANGE, linewidth=2, linestyle="--", label=f"P95 = {p95:.2f}")

    # Strategy markers
    strats = step1["strategies"]
    c_sharpe = strats["Strategy C (full)"]["sharpe"]
    e_sharpe = strats["Strategy E (full)"]["sharpe"]

    ax.axvline(c_sharpe, color=GREEN, linewidth=2.5, label=f"Strategy C = {c_sharpe:.2f} (P{strats['Strategy C (full)']['percentile']})")
    ax.axvline(e_sharpe, color=PURPLE, linewidth=2.5, label=f"Strategy E = {e_sharpe:.2f} (P{strats['Strategy E (full)']['percentile']})")

    ax.set_xlabel("Sharpe Ratio")
    ax.set_ylabel("Density")
    ax.set_title("Step 1: Random Baseline Distribution (1,000 strategies)", fontsize=14, fontweight="bold")
    ax.legend(loc="upper left", fontsize=9, facecolor=CARD_BG, edgecolor="#30363d")
    ax.grid(True, axis="y")
    ax.set_xlim(mean - 3.5 * std, max(e_sharpe + 1, mean + 3.5 * std))

    fig.tight_layout()
    out = OUT_DIR / "baseline_distribution.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved {out}")


def chart_walk_forward(step2: dict):
    """Chart 2: Walk-forward OOS Sharpe per window."""
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    for idx, (name, data) in enumerate(step2["strategies"].items()):
        ax = axes[idx]
        windows = data["windows"]
        x = list(range(1, len(windows) + 1))
        oos_sharpes = [w["oos_sharpe"] for w in windows]
        labels = [w["test_period"] for w in windows]

        colors = [GREEN if s > 0 else RED for s in oos_sharpes]
        bars = ax.bar(x, oos_sharpes, color=colors, width=0.7, edgecolor="#30363d", linewidth=0.5)

        # Zero line
        ax.axhline(0, color=TEXT, linewidth=0.8, alpha=0.5)

        # Mean line
        mean_s = data["summary"]["mean_oos_sharpe"]
        ax.axhline(mean_s, color=CYAN, linewidth=1.5, linestyle="--",
                    label=f"Mean OOS Sharpe = {mean_s:.2f}")

        # Stats annotation
        pct_pos = data["summary"]["pct_positive_sharpe"]
        n_pos = data["summary"]["n_positive_sharpe"]
        n_win = data["summary"]["n_windows"]
        ax.text(0.98, 0.95,
                f"{n_pos}/{n_win} positive ({pct_pos:.0f}%)\nMean = {mean_s:.2f}",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=10, color=TEXT,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=CARD_BG, edgecolor="#30363d"))

        ax.set_ylabel("OOS Sharpe")
        ax.set_title(name, fontsize=12, fontweight="bold")
        ax.legend(loc="upper left", fontsize=9, facecolor=CARD_BG, edgecolor="#30363d")
        ax.grid(True, axis="y")

        # X labels
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)

    axes[-1].set_xlabel("Test Period (1-month OOS window)")
    fig.suptitle("Step 2: Walk-Forward OOS Sharpe (3M train / 1M test)", fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()
    out = OUT_DIR / "walk_forward_windows.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out}")


def chart_ablation(step1: dict):
    """Chart 3: Full vs No-Trend ablation comparison."""
    strats = step1["strategies"]

    labels = ["Strategy C", "Strategy E"]
    full_pcts = [strats["Strategy C (full)"]["percentile"], strats["Strategy E (full)"]["percentile"]]
    notrend_pcts = [strats["Strategy C (no trend)"]["percentile"], strats["Strategy E (no trend)"]["percentile"]]
    full_sharpes = [strats["Strategy C (full)"]["sharpe"], strats["Strategy E (full)"]["sharpe"]]
    notrend_sharpes = [strats["Strategy C (no trend)"]["sharpe"], strats["Strategy E (no trend)"]["sharpe"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Left: Percentile
    x = np.arange(len(labels))
    w = 0.35
    b1 = ax1.bar(x - w / 2, full_pcts, w, label="Full (with trend filter)", color=CYAN, edgecolor="#30363d")
    b2 = ax1.bar(x + w / 2, notrend_pcts, w, label="No trend filter", color=RED, alpha=0.7, edgecolor="#30363d")

    ax1.axhline(95, color=ORANGE, linewidth=2, linestyle="--", label="P95 threshold")
    ax1.set_ylabel("Percentile Rank")
    ax1.set_title("Percentile vs Random Baseline", fontsize=12, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_ylim(0, 110)
    ax1.legend(fontsize=9, facecolor=CARD_BG, edgecolor="#30363d")
    ax1.grid(True, axis="y")

    # Value labels
    for bar, val in zip(b1, full_pcts):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                 f"{val}%", ha="center", va="bottom", fontsize=10, fontweight="bold")
    for bar, val in zip(b2, notrend_pcts):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                 f"{val}%", ha="center", va="bottom", fontsize=10)

    # Right: Sharpe
    b3 = ax2.bar(x - w / 2, full_sharpes, w, label="Full (with trend filter)", color=CYAN, edgecolor="#30363d")
    b4 = ax2.bar(x + w / 2, notrend_sharpes, w, label="No trend filter", color=RED, alpha=0.7, edgecolor="#30363d")

    ax2.axhline(0, color=TEXT, linewidth=0.8, alpha=0.5)
    ax2.set_ylabel("Sharpe Ratio")
    ax2.set_title("Sharpe Ratio Comparison", fontsize=12, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)
    ax2.legend(fontsize=9, facecolor=CARD_BG, edgecolor="#30363d")
    ax2.grid(True, axis="y")

    for bar, val in zip(b3, full_sharpes):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15,
                 f"{val:.2f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
    for bar, val in zip(b4, notrend_sharpes):
        y = bar.get_height() + 0.15 if bar.get_height() >= 0 else bar.get_height() - 0.3
        ax2.text(bar.get_x() + bar.get_width() / 2, y,
                 f"{val:.2f}", ha="center", va="bottom", fontsize=10)

    fig.suptitle("Ablation: Trend Filter Contribution", fontsize=14, fontweight="bold")
    fig.tight_layout()
    out = OUT_DIR / "ablation_comparison.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out}")


def main():
    print("Generating validation charts...")
    step1 = load_step1()
    step2 = load_step2()

    chart_baseline_distribution(step1)
    chart_walk_forward(step2)
    chart_ablation(step1)

    print("\nDone! 3 charts saved to docs/validation/")


if __name__ == "__main__":
    main()
