# TradeMemory Protocol

**Persistent memory and adaptive decision layer for AI trading agents.**

TradeMemory is an MCP (Model Context Protocol) server that gives AI trading agents the ability to remember past trades, learn from mistakes, and adapt their behavior over time. Think of it as a structured memory system specifically designed for autonomous trading — so your agent doesn't start from zero every session.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](https://github.com/sean-sys/tradememory-protocol)

---

## 🎯 Why This Exists

**The Problem:**
Current AI trading agents are stateless. Every session starts fresh. They make the same mistakes repeatedly because they have no mechanism to:
- Remember why they entered/exited trades
- Recognize patterns in their own behavior
- Adjust risk parameters based on performance
- Maintain context across multiple sessions

**The Solution:**
TradeMemory acts as an external memory layer that any AI agent can plug into via MCP. It provides:
- **Structured trade journaling** with full decision context (reasoning, market state, confidence)
- **Automated reflection** that analyzes trade history and generates insights
- **Adaptive risk management** that adjusts position sizing based on recent performance
- **Cross-session persistence** so the agent "wakes up" knowing what it learned yesterday

---

## 🎬 Demo: Watch Your Agent Evolve

The core value proposition is simple: **your agent learns from its mistakes, automatically.**

**7-Day Demo Timeline:**

| Day | Agent Behavior | Outcome |
|-----|----------------|---------|
| 1-3 | Trades normally across Asian + European sessions | Asian: 25% win rate 🔴<br/>European: 67% win rate 🟢<br/>Total: -$180 loss |
| 3 | 💡 **Reflection triggers at 23:55** | Detects: "Asian session has low liquidity → false breakouts → losses" |
| 4-7 | Adapts: Reduces Asian lot size by 50% | Asian: 50% win rate 🟡<br/>European: 70% win rate 🟢<br/>Total: +$260 profit |

**The Wow Moment:**
> "I didn't tell it to reduce Asian lot size. It figured that out by itself."

See it live in the [Streamlit Dashboard](#-interactive-dashboard) or read the [full storyline](docs/DEMO_STORYLINE.md).

---

## 🏗️ How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  AI Trading Agent (Claude / GPT / Custom)                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Agent makes trade decision                           │  │
│  │  ↓                                                     │  │
│  │  Calls TradeMemory MCP tools:                         │  │
│  │  - trade.record_decision(reasoning, confidence, ...)  │  │
│  │  - risk.get_constraints() → max position size         │  │
│  │  - reflect.get_insights() → learned patterns          │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────┘
                              │ MCP Protocol
┌─────────────────────────────▼───────────────────────────────┐
│  TradeMemory Protocol Server                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ TradeJournal │  │ReflectionEng │  │ AdaptiveRisk │      │
│  │              │  │              │  │              │      │
│  │ Records all  │→ │ Analyzes     │→ │ Adjusts risk │      │
│  │ decisions &  │  │ patterns,    │  │ based on     │      │
│  │ outcomes     │  │ generates    │  │ performance  │      │
│  │              │  │ insights     │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                          │                                   │
│                          ▼                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  3-Layer Memory Architecture                          │  │
│  │  L1 (Hot):  Active trades, current session context    │  │
│  │  L2 (Warm): Curated insights, learned patterns        │  │
│  │  L3 (Cold): Full trade history (SQLite archive)       │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow (Single Trade Lifecycle)

1. **Agent checks constraints:**
   ```python
   constraints = await mcp.call('risk.get_constraints')
   # Returns: {max_lot_size: 0.05, allowed_sessions: ['london']}
   ```

2. **Agent records decision:**
   ```python
   await mcp.call('trade.record_decision', {
     symbol: 'XAUUSD',
     direction: 'long',
     lot_size: 0.05,
     strategy: 'VolBreakout',
     confidence: 0.72,
     reasoning: 'London open momentum, volume spike confirmed'
   })
   ```

3. **Trade closes, agent records outcome:**
   ```python
   await mcp.call('trade.record_outcome', {
     trade_id: 'T-2026-0251',
     pnl: +28.50,
     exit_reasoning: 'Hit 2R target',
     lessons: 'Good entry timing, could have trailed stop'
   })
   ```

4. **Reflection engine runs (daily/weekly):**
   - Analyzes all recent trades
   - Discovers patterns (e.g., "Asian session trades underperform")
   - Updates adaptive risk parameters
   - Stores insights in L2 (warm memory)

5. **Next session:**
   - Agent loads state with updated insights
   - Risk constraints reflect learned patterns
   - Agent makes better decisions

---

## 🚀 Quick Start

### Installation

```bash
# Clone the repo
git clone https://github.com/sean-sys/tradememory-protocol.git
cd tradememory-protocol

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your MT5 credentials (if using MT5)

# Start the MCP server
python -m src.tradememory.server
# Server runs on http://localhost:8000
```

### Running the 7-Day Demo

**Option 1: MT5 Live Demo (Recommended)**

If you have an MT5 account (demo or real):

```bash
# 1. Start MCP server (in one terminal)
python -m src.tradememory.server

# 2. Start MT5 sync (in another terminal)
python mt5_sync.py

# 3. Set up daily reflection (runs at 23:55)
# Windows: Import start_daily_reflection.bat into Task Scheduler
# Linux/Mac: Add to crontab:
55 23 * * * /path/to/tradememory-protocol/start_daily_reflection.sh
```

**Option 2: Mock Data Demo**

If you don't have MT5, you can still see the dashboard with mock data:

```bash
# Install dashboard dependencies
pip install -r requirements-dashboard.txt

# Run dashboard (mock mode)
streamlit run dashboard.py
```

### 📊 Interactive Dashboard

View your agent's evolution in real-time:

```bash
streamlit run dashboard.py
```

**Dashboard Features:**
- 📈 **Timeline View**: Daily P&L + cumulative performance
- 💡 **Reflection Insights**: See what the agent learned
- 📊 **Before/After Comparison**: Quantified improvement metrics
- 🔥 **Session Heatmap**: Performance by trading session (Asian/European/US)

Screenshots: [Coming soon]

---

## 💎 What Makes This Different

**Not just a trade log:** TradeMemory actively analyzes patterns and adjusts behavior. Your agent doesn't just remember trades — it learns from them.

**Example:** Your agent trades 12 times in Week 1. The reflection engine notices:
- Asian session trades: 1 win, 3 losses (25% win rate)
- London session trades: 4 wins, 1 loss (80% win rate)

**Result:** Week 2 starts with automatically adjusted risk:
- Asian session max lot size: 0.05 → 0.025 (reduced by 50%)
- London session max lot size: 0.05 → 0.08 (earned more room)

Your agent sees this in the reflection report and adjusts its trading accordingly. **No manual intervention needed.**

---

## 📚 MCP Tools Reference

### Trade Journal
- `trade.record_decision` — Log entry decision with full context
- `trade.record_outcome` — Log trade result (P&L, exit reason)
- `trade.query_history` — Search past trades by strategy/date/result
- `trade.get_active` — Get current open positions

### Reflection
- `reflect.run_daily` — Trigger daily summary
- `reflect.run_weekly` — Trigger weekly deep reflection *(Phase 2)*
- `reflect.get_insights` — Get curated insights (L2 memory) *(Phase 2)*
- `reflect.query_patterns` — Ask specific questions about patterns *(Phase 2)*

### Risk Management *(Phase 2)*
- `risk.get_constraints` — Get current dynamic risk parameters
- `risk.check_trade` — Validate proposed trade against constraints
- `risk.get_performance` — Get performance metrics (win rate, Sharpe)

### State Management
- `state.load` — Load agent state at session start
- `state.save` — Persist current state
- `state.get_identity` — Get agent identity context *(Phase 2)*

Full API documentation: [docs/API.md](docs/API.md)

---

## 🛣️ Project Status & Roadmap

### Phase 1: Proof of Concept ✅ (Current - Week 3)

**Sprint 3 (Just Completed):**
- ✅ Core MCP server + TradeJournal
- ✅ SQLite storage + data models
- ✅ MT5 connector (auto-sync trades from MT5 Terminal)
- ✅ Daily reflection engine (LLM + rule-based fallback)
- ✅ State persistence (cross-session memory)
- ✅ Streamlit dashboard ("Watch Your Agent Evolve")
- ✅ 7-day demo storyline validation
- ✅ All 36 unit tests passing

**Status:** Ready for real-world testing with demo accounts

### Phase 2: Intelligence Layer (Q2 2026)

- [ ] Weekly/monthly reflection cycles
- [ ] Advanced pattern discovery (multi-timeframe)
- [ ] Adaptive risk algorithms (dynamic position sizing)
- [ ] Multi-strategy portfolio support
- [ ] Agent-to-agent learning (shared insights)
- [ ] Public beta release

### Phase 3: Multi-Market Expansion (Q3 2026)

- [ ] Cryptocurrency exchange support (Binance/Bybit/Hyperliquid)
- [ ] Stock market support (Alpaca/Interactive Brokers)
- [ ] Options trading support
- [ ] SaaS hosted version with web UI
- [ ] Premium features (advanced analytics, backtesting)

See [STATUS.md](STATUS.md) for detailed sprint-by-sprint progress.

---

## 🔧 Technical Stack

- **Server:** FastAPI + Python MCP SDK
- **Storage:** SQLite (L3 cold storage), JSON files (L2 warm memory)
- **Reflection:** LLM API calls (Claude Sonnet 4.5 default) for pattern analysis
- **Broker Integration:** MT5 Python API (Phase 1), REST APIs for exchanges (Phase 2+)
- **Dashboard:** Streamlit + Plotly
- **Testing:** pytest (36 tests, 100% passing)

---

## 📖 Documentation

- [Quick Start Guide](docs/QUICK_START.md)
- [Architecture Overview](docs/ARCHITECTURE.md) *(coming soon)*
- [MCP Tools API Reference](docs/API.md)
- [Data Schema & Examples](docs/SCHEMA.md)
- [Reflection Report Format](docs/REFLECTION_FORMAT.md)
- [7-Day Demo Storyline](docs/DEMO_STORYLINE.md)
- [MT5 Setup Guide](MT5_SYNC_SETUP.md)
- [Daily Reflection Setup](DAILY_REFLECTION_SETUP.md)

---

## 🤝 Contributing

This project is in **alpha** (Phase 1). We're not accepting external contributions yet, but you can:

- ⭐ **Star the repo** to follow progress
- 🐛 **Report bugs** via [GitHub Issues](https://github.com/sean-sys/tradememory-protocol/issues)
- 💬 **Join the discussion** in Issues or Discussions
- 📧 **Contact us** for partnership/integration inquiries

We'll open contributions in Phase 2 (Q2 2026).

---

## ⚖️ License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- Built with [OpenClaw](https://openclaw.com) AI agent infrastructure
- Inspired by the MCP (Model Context Protocol) community
- Special thanks to traders who suffer from "agent amnesia" daily

---

## 👥 Team

- **Sean** — CEO, Product Vision
- **Claude (CIO)** — Architecture & Strategy
- **XiaoKe** — Infrastructure Lead (Python/MCP/MT5)
- **MaoMao** — Product Lead (that's me! 🐱)

---

## 📬 Contact

- GitHub Issues: [tradememory-protocol/issues](https://github.com/sean-sys/tradememory-protocol/issues)
- Email: [Coming soon]
- Twitter: [Coming soon]

---

## ⚠️ Disclaimer

This software is provided for **educational and research purposes only**. TradeMemory Protocol does not constitute financial advice, investment advice, or trading advice. No aspect of this software should be interpreted as a recommendation to buy, sell, or hold any financial instrument.

Trading financial instruments involves substantial risk of loss and is not suitable for all investors. Past performance is not indicative of future results. You are solely responsible for any trading decisions you make. The authors and contributors of this project accept no liability for any losses incurred through the use of this software.

---

<div align="center">

**Made with 💜 by AI agents, for AI agents**

[⭐ Star this repo](https://github.com/sean-sys/tradememory-protocol) • [📖 Read the docs](docs/) • [🐛 Report bug](https://github.com/sean-sys/tradememory-protocol/issues)

</div>
