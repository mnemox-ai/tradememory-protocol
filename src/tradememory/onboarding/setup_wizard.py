"""Interactive first-time setup wizard for TradeMemory."""

import json
import os
import subprocess
import sys
from pathlib import Path

from .terms import TRADEMEMORY_DISCLAIMER, TRADEMEMORY_ACCEPT_PROMPT
from .platforms import PLATFORMS, detect_platforms, show_config_for_platform
from .doctor import run_doctor, print_results

# ANSI color codes
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"

BANNER = f"""
{CYAN}{BOLD}================================================
  TradeMemory Protocol - First-Time Setup
  AI Trading Memory & Adaptive Decision Layer
================================================{RESET}
"""

DATA_DIR = Path.home() / ".tradememory"
SETUP_MARKER = DATA_DIR / ".setup_done"


def _ask_yes_no(prompt: str, default: bool = False) -> bool:
    """Ask a yes/no question. Returns True for yes."""
    answer = input(prompt).strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _step_terms() -> bool:
    """Step 1: Show terms and ask for acceptance."""
    print(TRADEMEMORY_DISCLAIMER)
    return _ask_yes_no(TRADEMEMORY_ACCEPT_PROMPT, default=False)


def _step_detect_platforms() -> list:
    """Step 2: Detect installed platforms and let user choose."""
    print(f"\n{BOLD}Step 2: Platform Detection{RESET}\n")

    detected = detect_platforms()

    if detected:
        print(f"  {GREEN}Detected platforms:{RESET}")
        for i, key in enumerate(detected, 1):
            name = PLATFORMS[key]["name"]
            print(f"    {i}. {name}")
    else:
        print(f"  {YELLOW}No platforms auto-detected.{RESET}")

    print(f"\n  Available platforms:")
    all_keys = list(PLATFORMS.keys())
    for i, key in enumerate(all_keys, 1):
        marker = " *" if key in detected else ""
        print(f"    {i}. {PLATFORMS[key]['name']}{marker}")

    print(f"\n  Enter numbers separated by commas, 'all' for detected, or 'skip':")
    choice = input("  > ").strip().lower()

    if choice == "skip" or not choice:
        return []
    elif choice == "all":
        return detected
    else:
        selected = []
        for part in choice.split(","):
            part = part.strip()
            try:
                idx = int(part) - 1
                if 0 <= idx < len(all_keys):
                    selected.append(all_keys[idx])
            except ValueError:
                # Try matching by name
                if part in PLATFORMS:
                    selected.append(part)
        return selected


def _step_configure_platforms(selected: list) -> None:
    """Step 3: Configure each selected platform."""
    if not selected:
        print(f"\n  {YELLOW}Skipping platform configuration.{RESET}")
        return

    print(f"\n{BOLD}Step 3: Platform Configuration{RESET}")

    for key in selected:
        p = PLATFORMS[key]
        print(f"\n  {CYAN}--- {p['name']} ---{RESET}")

        if p.get("auto_install_cmd"):
            if _ask_yes_no(f"  Auto-install with: {p['auto_install_cmd']}? [Y/n]: ", default=True):
                print(f"  Running: {p['auto_install_cmd']}")
                try:
                    result = subprocess.run(
                        p["auto_install_cmd"],
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode == 0:
                        print(f"  {GREEN}Done.{RESET}")
                    else:
                        print(f"  {YELLOW}Command returned code {result.returncode}{RESET}")
                        if result.stderr:
                            print(f"  {result.stderr[:200]}")
                except Exception as e:
                    print(f"  {YELLOW}Failed: {e}{RESET}")
                continue
            # If user said no to auto-install, show manual instructions
            show_config_for_platform(key)
        else:
            show_config_for_platform(key)


def _step_env_vars() -> None:
    """Step 4: Optional environment variable configuration."""
    print(f"\n{BOLD}Step 4: Optional Configuration{RESET}")
    print(f"  Press Enter to skip any prompt.\n")

    anthropic_key = input("  ANTHROPIC_API_KEY (for Evolution Engine): ").strip()

    if anthropic_key:
        env_path = DATA_DIR / ".env"
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Read existing .env if present
        existing = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip()

        existing["ANTHROPIC_API_KEY"] = anthropic_key

        with open(env_path, "w") as f:
            for k, v in existing.items():
                f.write(f"{k}={v}\n")

        print(f"  {GREEN}Saved to {env_path}{RESET}")
    else:
        print(f"  {YELLOW}Skipped. You can set this later in ~/.tradememory/.env{RESET}")


def _step_health_check() -> None:
    """Step 5: Run core health checks."""
    print(f"\n{BOLD}Step 5: Health Check{RESET}")
    results = run_doctor(full=False)
    print_results(results)


def _step_done() -> None:
    """Step 6: Write marker file and show success message."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETUP_MARKER.write_text("setup_done\n")

    print(f"{GREEN}{BOLD}Setup complete!{RESET}\n")
    print(f"  Try asking your AI agent:")
    print(f"  {CYAN}\"Store a trade: bought XAUUSD at 2650, sold at 2680, +$300\"{RESET}")
    print(f"  {CYAN}\"What patterns do you see in my recent trades?\"{RESET}")
    print()
    print(f"  For full diagnostic: {BOLD}tradememory doctor --full{RESET}")
    print()


def run_setup() -> None:
    """Run the interactive setup wizard."""
    print(BANNER)

    # Step 1: Terms
    print(f"{BOLD}Step 1: Terms & Disclaimer{RESET}")
    if not _step_terms():
        print(f"\n  {YELLOW}Setup cancelled. You must accept the terms to use TradeMemory.{RESET}\n")
        return

    print(f"  {GREEN}Terms accepted.{RESET}")

    # Step 2: Detect platforms
    selected = _step_detect_platforms()

    # Step 3: Configure platforms
    _step_configure_platforms(selected)

    # Step 4: Env vars
    _step_env_vars()

    # Step 5: Health check
    _step_health_check()

    # Step 6: Done
    _step_done()
