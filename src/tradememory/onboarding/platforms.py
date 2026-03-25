"""Platform configuration templates and detection for MCP clients."""

import os
import platform
import shutil
from pathlib import Path
from typing import Dict, List, Optional

# ANSI color codes
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"

MCP_COMMAND = "uvx tradememory-protocol"
MCP_FALLBACK = "python -m tradememory"

MCPSERVERS_SNIPPET = {
    "tradememory": {
        "command": "uvx",
        "args": ["tradememory-protocol"],
    }
}


def _get_claude_desktop_config_path() -> str:
    """Return platform-specific Claude Desktop config path."""
    system = platform.system()
    if system == "Darwin":
        return "~/Library/Application Support/Claude/claude_desktop_config.json"
    elif system == "Windows":
        return "%APPDATA%/Claude/claude_desktop_config.json"
    else:
        return "~/.config/claude/claude_desktop_config.json"


PLATFORMS: Dict[str, dict] = {
    "claude_desktop": {
        "name": "Claude Desktop",
        "config_path": _get_claude_desktop_config_path(),
        "snippet": {
            "mcpServers": MCPSERVERS_SNIPPET,
        },
        "auto_install_cmd": None,
        "instructions": [
            "1. Open Claude Desktop settings (gear icon)",
            "2. Go to 'Developer' tab",
            "3. Click 'Edit Config'",
            "4. Add the following to your config file:",
        ],
    },
    "claude_code": {
        "name": "Claude Code",
        "config_path": None,
        "snippet": None,
        "auto_install_cmd": "claude mcp add tradememory -- uvx tradememory-protocol",
        "instructions": [
            "Run the following command in your terminal:",
            "  claude mcp add tradememory -- uvx tradememory-protocol",
        ],
    },
    "cursor": {
        "name": "Cursor",
        "config_path": ".cursor/mcp.json",
        "snippet": {
            "mcpServers": MCPSERVERS_SNIPPET,
        },
        "auto_install_cmd": None,
        "instructions": [
            "1. Create .cursor/mcp.json in your project root",
            "2. Add the following configuration:",
        ],
    },
    "windsurf": {
        "name": "Windsurf",
        "config_path": "~/.codeium/windsurf/mcp_config.json",
        "snippet": {
            "mcpServers": MCPSERVERS_SNIPPET,
        },
        "auto_install_cmd": None,
        "instructions": [
            "1. Open or create ~/.codeium/windsurf/mcp_config.json",
            "2. Add the following configuration:",
        ],
    },
    "cline": {
        "name": "Cline (VS Code)",
        "config_path": ".cline/mcp.json",
        "snippet": {
            "mcpServers": MCPSERVERS_SNIPPET,
        },
        "auto_install_cmd": None,
        "instructions": [
            "1. Create .cline/mcp.json in your project root (or add to VS Code settings)",
            "2. Add the following configuration:",
        ],
    },
    "smithery": {
        "name": "Smithery",
        "config_path": None,
        "snippet": None,
        "auto_install_cmd": "npx -y @smithery/cli install tradememory-protocol",
        "instructions": [
            "Run the following command:",
            "  npx -y @smithery/cli install tradememory-protocol",
        ],
    },
    "docker": {
        "name": "Docker",
        "config_path": None,
        "snippet": None,
        "auto_install_cmd": None,
        "instructions": [
            "Run TradeMemory in a container:",
            "  docker run -it --rm -v tradememory-data:/root/.tradememory ghcr.io/mnemox-ai/tradememory-protocol",
            "",
            "Or add to your MCP client config:",
        ],
    },
    "raw_json": {
        "name": "Raw JSON (any MCP client)",
        "config_path": None,
        "snippet": MCPSERVERS_SNIPPET,
        "auto_install_cmd": None,
        "instructions": [
            "Add this to your MCP client's mcpServers configuration:",
        ],
    },
}


def detect_platforms() -> List[str]:
    """Detect which MCP platforms are installed by checking config dirs/binaries.

    Returns list of platform keys that appear to be installed.
    """
    detected = []

    # Claude Desktop — check config directory existence
    system = platform.system()
    if system == "Darwin":
        claude_dir = Path.home() / "Library" / "Application Support" / "Claude"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        claude_dir = Path(appdata) / "Claude" if appdata else None
    else:
        claude_dir = Path.home() / ".config" / "claude"

    if claude_dir and claude_dir.is_dir():
        detected.append("claude_desktop")

    # Claude Code — check binary
    if shutil.which("claude"):
        detected.append("claude_code")

    # Cursor — check binary or config dir
    if shutil.which("cursor") or Path(".cursor").is_dir():
        detected.append("cursor")

    # Windsurf — check config dir
    windsurf_dir = Path.home() / ".codeium" / "windsurf"
    if windsurf_dir.is_dir():
        detected.append("windsurf")

    # Cline — check project-level config
    if Path(".cline").is_dir():
        detected.append("cline")

    # Smithery — check npx availability
    if shutil.which("npx"):
        detected.append("smithery")

    # Docker
    if shutil.which("docker"):
        detected.append("docker")

    return detected


def _format_snippet(snippet: dict) -> str:
    """Format a config snippet as indented JSON."""
    import json
    return json.dumps(snippet, indent=2)


def show_config_for_platform(platform_key: str) -> None:
    """Print configuration instructions for a specific platform."""
    if platform_key not in PLATFORMS:
        print(f"{YELLOW}Unknown platform: {platform_key}{RESET}")
        print(f"Available: {', '.join(PLATFORMS.keys())}")
        return

    p = PLATFORMS[platform_key]
    print(f"\n{BOLD}{CYAN}=== {p['name']} ==={RESET}\n")

    for line in p["instructions"]:
        print(f"  {line}")

    if p.get("auto_install_cmd"):
        print(f"\n  {GREEN}$ {p['auto_install_cmd']}{RESET}")

    if p.get("snippet"):
        print(f"\n{_format_snippet(p['snippet'])}")

    if p.get("config_path"):
        path = p["config_path"]
        print(f"\n  Config file: {path}")

    print()


def show_config_menu(platform_key: Optional[str] = None) -> None:
    """Show config for a specific platform or list all platforms."""
    if platform_key:
        show_config_for_platform(platform_key)
        return

    print(f"\n{BOLD}Available platforms:{RESET}\n")
    for key, p in PLATFORMS.items():
        print(f"  {CYAN}{key:<18}{RESET} {p['name']}")

    print(f"\nUsage: tradememory config <platform>")
    print(f"Example: tradememory config claude_code\n")

    detected = detect_platforms()
    if detected:
        print(f"{GREEN}Detected on this system:{RESET} {', '.join(detected)}")
    print()
