# TradeMemory Protocol

**A [Mnemox](https://mnemox.ai) Project** — MCP server that gives AI trading agents persistent memory.

AI trading agents are stateless by default. Every session starts from zero. TradeMemory is an MCP (Model Context Protocol) server that stores trade decisions, analyzes patterns via a reflection engine, and persists learned insights across sessions.

[![CI](https://github.com/mnemox-ai/tradememory-protocol/actions/workflows/ci.yml/badge.svg)](https://github.com/mnemox-ai/tradememory-protocol/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](https://github.com/mnemox-ai/tradememory-protocol)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/mnemox-ai/tradememory-protocol)

---

## What It Does

- **Trade journaling** — Records every decision with reasoning, confidence, market context, and outcome
- **Reflection engine** — Analyzes trade history to find session/strategy/confidence patterns (rule-based, with optional LLM)
- **State persistence** — Agent loads its learned patterns and risk constraints when starting a new session
- **3-layer memory** — L1 (active trades), L2 (discovered patterns), L3 (full history in SQLite)

What it does NOT do yet: adaptive risk algorithms, weekly/monthly reflection, multi-agent learning. These are planned for Phase 2.

---

## Quick Start

### Install

```bash
curl -sSL https://raw.githubusercontent.com/mnemox-ai/tradememory-protocol/master/install.sh | bash
```

Or manually:

```bash
git clone https://github.com/mnemox-ai/tradememory-protocol.git
cd tradememory-protocol
pip install -r requirements.txt
cp .env.example .env
```

### Run the Demo

No API key needed. Runs 30 simulated XAUUSD trades through the full pipeline:

```bash
python demo.py
```

Output shows: trade recording (L1) → pattern discovery (L2) → strategy adjustments (L3) → agent reloading state with memory.

> All demo data is simulated. See [Before/After Comparison](docs/BEFORE_AFTER.md) for detailed breakdown.

### Start the Server

```bash
python -m src.tradememory.server
# Runs on http://localhost:8000
```

### Docker

```bash
docker compose up -d

# Or manually:
docker build -t tradememory .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=your-key tradememory
```

### Tutorials

- [English Tutorial](docs/TUTORIAL.md) — Step-by-step from install to using memory in trades
- [中文教學](docs/TUTORIAL_ZH.md) — 完整教學指南

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  AI Trading Agent (Claude / GPT / Custom)                   │
│  Calls TradeMemory MCP tools:                               │
│  - trade.record_decision(reasoning, confidence, ...)        │
│  - trade.record_outcome(pnl, exit_reasoning, ...)           │
│  - state.load() → get learned patterns                      │
└─────────────────────────────┬───────────────────────────────┘
                              │ MCP Protocol
┌─────────────────────────────▼───────────────────────────────┐
│  TradeMemory Protocol Server                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ TradeJournal │→ │ReflectionEng │→ │ StateManager │      │
│  │ Records all  │  │ Analyzes     │  │ Persists     │      │
│  │ decisions &  │  │ patterns,    │  │ learned      │      │
│  │ outcomes     │  │ generates    │  │ insights     │      │
│  │              │  │ insights     │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
│  3-Layer Memory:                                             │
│  L1 (Hot):  Active trades, current session context           │
│  L2 (Warm): Curated insights from reflection engine          │
│  L3 (Cold): Full trade history (SQLite)                      │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow

1. Agent records trade decision (symbol, direction, strategy, confidence, reasoning)
2. Trade closes → agent records outcome (P&L, exit reasoning)
3. Reflection engine runs (daily) → discovers patterns → stores in L2
4. Next session → agent loads state with updated patterns and constraints

---

## MCP Tools

### Trade Journal (implemented)
- `trade.record_decision` — Log entry decision with full context
- `trade.record_outcome` — Log trade result (P&L, exit reason)
- `trade.query_history` — Search past trades by strategy/date/result
- `trade.get_active` — Get current open positions

### Reflection (implemented)
- `reflect.run_daily` — Trigger daily summary (rule-based, or LLM with API key)

### State Management (implemented)
- `state.load` — Load agent state at session start
- `state.save` — Persist current state

### Not Yet Implemented (Phase 2)
- `reflect.run_weekly` — Weekly deep reflection
- `reflect.get_insights` — Query curated insights
- `risk.get_constraints` — Dynamic risk parameters
- `risk.check_trade` — Validate trade against constraints
- Adaptive risk algorithms (dynamic position sizing)
- Agent-to-agent learning

Full API reference: [docs/API.md](docs/API.md)

---

## Project Status

### What Works (Phase 1)
- Core MCP server + TradeJournal
- SQLite storage + Pydantic data models
- MT5 connector (auto-sync trades from MetaTrader 5)
- Daily reflection engine (rule-based + optional LLM)
- State persistence (cross-session memory)
- Streamlit dashboard
- 36 unit tests passing
- Interactive demo (`demo.py`)

### Planned (Phase 2 — Q2 2026)
- Weekly/monthly reflection cycles
- Adaptive risk algorithms
- Multi-strategy portfolio support
- Agent-to-agent learning
- Public beta

### Future (Phase 3 — Q3 2026)
- Cryptocurrency exchange support (Binance/Bybit)
- Stock market support (Alpaca/Interactive Brokers)
- SaaS hosted version

---

## Technical Stack

- **Server:** FastAPI + Python MCP SDK
- **Storage:** SQLite (L3), JSON (L2)
- **Reflection:** Rule-based pattern analysis, optional Claude API for deeper insights
- **Broker Integration:** MT5 Python API (Phase 1)
- **Dashboard:** Streamlit + Plotly
- **Testing:** pytest (36 tests)

---

## Documentation

- [Tutorial (English)](docs/TUTORIAL.md)
- [教學 (中文)](docs/TUTORIAL_ZH.md)
- [Before/After Comparison](docs/BEFORE_AFTER.md) — Simulated impact data
- [Quick Start Guide](docs/QUICK_START.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Data Schema](docs/SCHEMA.md)
- [Reflection Report Format](docs/REFLECTION_FORMAT.md)
- [MT5 Setup Guide](MT5_SYNC_SETUP.md)
- [Daily Reflection Setup](DAILY_REFLECTION_SETUP.md)

---

## Connect to MT5 (Optional)

```bash
# Terminal 1: Start MCP server
python -m src.tradememory.server

# Terminal 2: Start MT5 sync
python mt5_sync.py

# Set up daily reflection at 23:55
# Windows: Import start_daily_reflection.bat into Task Scheduler
# Linux/Mac: 55 23 * * * /path/to/daily_reflection.sh
```

### Recording a Demo GIF

```bash
pip install rich
asciinema rec demo.cast -c "python scripts/record_demo.py"
agg demo.cast demo.gif
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- Star the repo to follow progress
- Report bugs via [GitHub Issues](https://github.com/mnemox-ai/tradememory-protocol/issues)
- Submit PRs for bug fixes or new features
- Join the discussion in [Discussions](https://github.com/mnemox-ai/tradememory-protocol/discussions)

---

## License

MIT — see [LICENSE](LICENSE).

---

## Disclaimer

This software is for **educational and research purposes only**. It does not constitute financial advice. Trading involves substantial risk of loss. You are solely responsible for your trading decisions. The authors accept no liability for losses incurred through use of this software.

---

## Contact

- [GitHub Issues](https://github.com/mnemox-ai/tradememory-protocol/issues)
- [GitHub Discussions](https://github.com/mnemox-ai/tradememory-protocol/discussions)

---

Built by [Mnemox](https://mnemox.ai)
