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
- **3-layer memory** — L1 (active trades), L2 (discovered patterns), L3 (strategy adjustments in SQLite)
- **Strategy adjustments (L3)** — Rule-based tuning from L2 patterns: disable losing strategies, prefer winners, adjust lot sizes, restrict directions

What it does NOT do yet: multi-agent learning, cryptocurrency exchange support. These are planned for future phases.

---

## Quick Start

### As MCP Server (Claude Desktop / Claude Code / Cursor)

```bash
uvx tradememory-protocol
```

Add to your MCP client config:
```json
{
  "mcpServers": {
    "tradememory": {
      "command": "uvx",
      "args": ["tradememory-protocol"]
    }
  }
}
```

### From Source

```bash
git clone https://github.com/mnemox-ai/tradememory-protocol.git
cd tradememory-protocol
pip install -e .
```

### Run the Demo

No API key needed. Runs 30 simulated XAUUSD trades through the full pipeline:

```bash
python demo.py
```

Output shows: trade recording (L1) → pattern discovery (L2) → strategy adjustments (L3) → agent reloading state with memory.

<details>
<summary>Demo output preview (click to expand)</summary>

```
┌───────────────────────────────────────────────┐
│                                               │
│    TradeMemory Protocol                       │
│    Persistent memory for AI trading agents    │
│                                               │
└───────────────────────────────────────────────┘

── Step 1: L1 — Recording trades to TradeJournal ──

  # │ Result │ Session │ Strategy    │ P&L      │ R
  1 │ LOSS   │ Asia    │ Pullback    │ $-15.00  │ -1.0
  2 │ WIN    │ London  │ VolBreakout │ $+42.00  │ +2.1
  3 │ WIN    │ London  │ VolBreakout │ $+28.50  │ +1.5
  ...
  30 │ WIN   │ London  │ Pullback    │ $+28.00  │ +1.4

  Total: 30 trades | Winners: 19 | Win rate: 63% | Net P&L: $+499.50

── Step 2: L2 — Reflection Engine discovers patterns ──

  Pattern             │ Win Rate │ Record    │ Net P&L   │ Assessment
  London session      │     100% │ 14W / 0L  │ $+608.50  │ HIGH EDGE
  Asian session       │      10% │  1W / 9L  │ $-156.00  │ WEAK
  VolBreakout strategy│      73% │ 11W / 4L  │ $+429.50  │ HIGH EDGE

  Confidence correlation:
    High (>0.75): 100% win rate
    Low  (<0.55):   0% win rate

── Step 3: L3 — Strategy adjustments generated ──

  Parameter                │ Old  │ New  │ Reason
  london_max_lot           │ 0.05 │ 0.08 │ London WR 100% — earned more room
  asian_max_lot            │ 0.05 │ 0.025│ Asian WR 10% — reduce exposure
  min_confidence_threshold │ 0.40 │ 0.55 │ Trades below 0.55 have 0% WR
```

</details>

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

## MCP Tools (v0.2.0)

### Core Memory Tools (MCP — via `uvx tradememory-protocol`)
- `store_trade_memory` — Store a trade decision with full context into memory
- `recall_similar_trades` — Find past trades with similar market context
- `get_strategy_performance` — Aggregate performance stats per strategy
- `get_trade_reflection` — Deep-dive into a specific trade's reasoning and lessons

### REST API (FastAPI — via `tradememory-api`)
- `POST /trade/record_decision` — Log entry decision with full context
- `POST /trade/record_outcome` — Log trade result (P&L, exit reason)
- `POST /trade/query_history` — Search past trades by strategy/date/result
- `POST /reflect/run_daily` — Trigger daily summary (rule-based, or LLM with API key)
- `POST /reflect/run_weekly` — Weekly deep reflection
- `POST /reflect/run_monthly` — Monthly reflection
- `POST /risk/get_constraints` — Dynamic risk parameters
- `POST /risk/check_trade` — Validate trade against constraints
- `POST /mt5/sync` — Sync trades from MetaTrader 5
- `POST /reflect/generate_adjustments` — Generate L3 strategy adjustments from L2 patterns
- `GET /adjustments/query` — Query strategy adjustments by status/type
- `POST /adjustments/update_status` — Update adjustment lifecycle (proposed→approved→applied)

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
- 181 unit tests passing
- Interactive demo (`demo.py`)
- Weekly/monthly reflection cycles
- Adaptive risk algorithms

### Planned (Phase 2 — Q2 2026)
- Multi-strategy portfolio support
- Agent-to-agent learning
- Public beta

### Future (Phase 3 — Q3 2026)
- Cryptocurrency exchange support (Binance/Bybit)
- Stock market support (Alpaca/Interactive Brokers)
- SaaS hosted version

---

## Technical Stack

- **MCP Server:** FastMCP 3.x (stdio transport)
- **REST API:** FastAPI + uvicorn
- **Storage:** SQLite (L3), JSON (L2)
- **Reflection:** Rule-based pattern analysis, optional Claude API for deeper insights
- **Broker Integration:** MT5 Python API (Phase 1)
- **Dashboard:** Streamlit + Plotly
- **Testing:** pytest (181 tests)

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

Sync live trades from MetaTrader 5 into TradeMemory automatically.

### Prerequisites

1. **MetaTrader 5** running with your broker account
2. **Python 3.12** (system Python 3.13+ is not supported by the MT5 package)
3. **Enable API access** in MT5: `Tools → Options → Expert Advisors → Allow Algo Trading`
   - Also set `Api=1` in `common.ini` under `[Experts]` section

### Quick Start

```bash
# 1. Install dependencies
pip install MetaTrader5 python-dotenv requests fastapi uvicorn pydantic

# 2. Configure .env
cp .env.example .env
# Edit .env with your MT5 credentials

# 3. Start both services
scripts/start_services.bat
```

### Auto-Start on Login (Windows)

```bash
# Run as Administrator:
scripts\install_autostart.bat
```

This registers a Windows Task Scheduler task that starts the tradememory server and mt5_sync.py 30 seconds after login.

```
scripts/
├── start_services.bat       # Start tradememory server + mt5_sync.py
├── stop_services.bat        # Stop all services
├── install_autostart.bat    # Register auto-start task (run as admin)
└── TradeMemory_AutoStart.xml # Task Scheduler config
```

### Manual Start

```bash
# Terminal 1: Start API server
python -c "import sys; sys.path.insert(0, 'src'); from tradememory.server import main; main()"
# Runs on http://localhost:8000

# Terminal 2: Start MT5 sync (scans every 60s)
python mt5_sync.py
```

### Daily Reflection

```bash
# Windows: Import start_daily_reflection.bat into Task Scheduler (23:55 daily)
# Linux/Mac: 55 23 * * * /path/to/daily_reflection.sh
```

See [MT5 Setup Guide](MT5_SYNC_SETUP.md) for detailed configuration.

---

## FAQ

**Does TradeMemory connect directly to my broker?**
No. TradeMemory is a memory layer, not a trading platform connector. It accepts standardized trade data from any source. For MT5 users, `mt5_sync.py` automatically polls and syncs closed trades every 60 seconds.

**What trading platforms are supported?**
Any platform that can output trade data. Built-in support exists for MetaTrader 5 via mt5_sync.py. For other platforms (Binance, Alpaca, Interactive Brokers), you send trades through the MCP `store_trade` tool or REST API using a standardized format.

**What data does it store?**
Three layers: L1 stores raw trade records (symbol, direction, lots, entry/exit price, PnL, timestamps). L2 stores discovered patterns (win rate by session, drawdown sequences). L3 stores strategy-level insights from LLM reflection.

**Is it free to use?**
Yes. MIT license, fully open source. The LLM reflection feature requires a Claude API key, but the core trade storage and performance analysis work without any API keys.

**Can I use it without MetaTrader 5?**
Yes. MT5 is just one data source. You can manually store trades via the MCP `store_trade` tool, send them through the REST API, or write a custom sync script for your platform.

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
