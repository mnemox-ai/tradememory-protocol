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
- `src/daily_reflection.py` — Scheduled reflection runner (daily/weekly/monthly)
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
python daily_reflection.py

# Run weekly/monthly reflection
python daily_reflection.py --weekly
python daily_reflection.py --monthly

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

## Lessons Learned
- 預設分支是 master 不是 main，所有 GitHub URL 都要用 master
- .env.example 不要放真實憑證
- README 不要用過多 emoji 和行銷語調，保持開發者風格
- 不要承諾還沒實作的功能（Phase 2 不打勾）
- CHANGELOG 要誠實，不要假裝多個 sprint
- Before/After 數據如果是模擬的，要在最上面明確標註
- 刪除的檔案如果曾 commit 過敏感資訊，git 歷史裡還是看得到，要用 filter-branch 清除

## Rules
- 每個任務完成前必須跑 pytest 確認沒壞東西
- commit 前用 git diff 檢查改動範圍是否合理
- 不要一次開太多 MCP tools，會吃 context window
- 寫文件用開發者語調，不要用行銷語調
- 所有模擬數據必須標註 "Simulated"
- 簡單方案優先，不要 over-engineer

## Compact Instructions

When compacting, preserve: key design decisions (LLM validation, UTC enforcement, platform-agnostic core), current task progress, security rules, lessons learned, rules.
