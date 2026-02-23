# TradeMemory Protocol

A platform-agnostic memory layer for AI-assisted trading systems. TradeMemory does NOT connect to trading platforms directly — it accepts standardized trade data from any source (MT5, Binance, Alpaca) and provides structured memory with reflection capabilities.

## Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI + MCP (Model Context Protocol)
- **Database:** SQLite (dev), PostgreSQL (prod-ready)
- **MT5 Connection:** `ariadng/metatrader-mcp-server` (external, not our code)
- **LLM:** Claude API for ReflectionEngine
- **Testing:** pytest
- **Package Manager:** pip with requirements.txt

## Architecture

```
External Data Sources (MT5, Binance, Alpaca...)
    ↓ Standardized TradeRecord format
TradeMemory Protocol (this repo)
    ├── TradeJournal      ← Structured trade storage (L1: raw, L2: patterns, L3: strategy)
    ├── ReflectionEngine  ← Analyzes journal, generates insights (Reflexion framework)
    ├── AdaptiveRisk      ← Dynamic position sizing based on memory
    └── StateManager      ← Cross-session persistence
```

## Key Files

- `src/trade_adapter.py` — Converts external trade data → TradeRecord format
- `src/trade_journal.py` — L1/L2/L3 memory storage
- `src/reflection_engine.py` — LLM-powered trade analysis
- `src/adaptive_risk.py` — Dynamic risk management
- `src/mt5_sync.py` — Polls MT5 for closed trades (60s interval)
- `src/daily_reflection.py` — Scheduled reflection runner (23:55 daily)
- `dashboard/` — Streamlit monitoring dashboard

## Commands

```bash
# Run tests
pytest tests/ -v

# Start MCP server
python -m src.server

# Run MT5 sync (Windows only, requires MT5 terminal running)
python src/mt5_sync.py

# Run daily reflection manually
python src/daily_reflection.py

# Start dashboard
streamlit run dashboard/app.py
```

## Development Rules

- NEVER hardcode credentials. All secrets via `.env` or environment variables.
- NEVER commit `.env`, `*.sqlite`, or files containing API keys.
- All trade data input must go through `TradeRecord` schema validation.
- LLM outputs (ReflectionEngine) MUST be validated with fallback to structured defaults if parsing fails.
- MT5-specific code stays isolated in `mt5_sync.py` and `trade_adapter.py` — core TradeMemory must remain platform-agnostic.
- Use UTC for all timestamps. MT5 API requires explicit UTC timezone.

## Git Workflow

- Branch per feature: `feat/description`, `fix/description`
- Commit messages: conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`)
- Always run `pytest` before committing.

## Current Status

- v0.1.0 released. Core pipeline operational: NG_Gold EA → mt5_sync.py → TradeJournal → daily_reflection.py → reflections/
- 36 unit tests passing.
- Open-source repo live at github.com/mnemox-ai/tradememory-protocol
- Default branch is `master` (not main). All URLs use `/master/`.

## Completed Promotion & Infrastructure (2026-02-23)

- mnemox.ai landing page live (GitHub Pages + custom domain)
- Listed on mcpservers.org (approved), mcp.so, punkpeye/awesome-mcp-servers PR #2312
- Dev.to article published
- HN Show HN posted
- CI pipeline (GitHub Actions) enabled — Python 3.10/3.11/3.12 matrix
- Docker + GitHub Codespaces support added
- English + Chinese tutorials, Before/After doc, demo.py, install.sh all complete
- GitHub Discussions enabled (Ideas, Show & Tell, Q&A templates)

## Compact Instructions

When compacting, preserve: key design decisions (LLM validation, UTC enforcement, platform-agnostic core), current task progress, security rules.
