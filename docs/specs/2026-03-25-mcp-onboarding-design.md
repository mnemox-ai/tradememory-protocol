# MCP Onboarding System Design

**Date:** 2026-03-25
**Scope:** tradememory-protocol + idea-reality-mcp
**Status:** Approved

## Overview

Add `setup`, `doctor`, `config` CLI commands to both MCP packages. Goal: reduce friction from `pip install` to working MCP integration, while covering legal disclaimers.

## Commands

### `setup` — Interactive first-time wizard
1. Show terms/disclaimer → `[y/N]` confirm
2. Detect installed AI platforms
3. Optional API key configuration
4. Generate platform config (print snippet, don't auto-write except Claude Code)
5. Run core health check

### `doctor` — Health check
- Default: core checks (DB, MCP tools, write/read/delete test) ~3s
- `--full`: + external services (REST API, MT5, Anthropic, GitHub API)
- Output format: checkmark list with timing

### `config` — Platform config generator
- Interactive menu: Claude Desktop / Claude Code / Cursor / Windsurf / Cline / Smithery / Docker / Raw JSON
- Prints exact config snippet + file path
- Claude Code: uses `claude mcp add` (safe auto-install)
- All others: print-only (user pastes manually)

## First-Run Detection

MCP server stderr hint (non-blocking):
```
💡 First time? Run: tradememory setup
```

Detection: check for `.tradememory_setup_done` marker file in data dir.

## Legal Text

### tradememory-protocol
- NOT financial advice
- Past data ≠ future results
- User responsible for all trading decisions
- Data stored locally (SQLite) by default
- No external transmission unless configured
- Full terms: TERMS.md

### idea-reality-mcp
- Search queries logged anonymously for analytics
- Results from public sources (GitHub, HN, npm, PyPI, PH, SO)
- Scores are algorithmic estimates, not market research
- No personal data via MCP stdio
- REST API logs hashed IPs
- Full terms: TERMS.md

## File Structure (per repo)

```
src/<package>/
├── cli.py              # Click-based CLI entry point
├── onboarding/
│   ├── __init__.py
│   ├── setup_wizard.py # interactive setup
│   ├── doctor.py       # health checks
│   ├── platforms.py    # config templates per platform
│   └── terms.py        # disclaimer text constants
TERMS.md                # full legal terms (EN)
PRIVACY.md              # privacy policy (EN)
```

## Platform Configs (Phase 1)

Claude Desktop, Claude Code, Cursor, Windsurf, Cline, Smithery, Docker, Raw JSON.

## YAGNI

- No GUI installer
- No auto-update check
- No telemetry
- No account registration
- No auto-write to config files (except Claude Code CLI)
