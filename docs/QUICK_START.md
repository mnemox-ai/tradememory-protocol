# Quick Start Guide

Get TradeMemory Protocol running in 5 minutes.

---

## Prerequisites

- Python 3.11+
- pip

## 1. Clone & Install

```bash
git clone https://github.com/mnemox-ai/tradememory-protocol.git
cd tradememory-protocol
pip install -r requirements.txt
```

## 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings. At minimum, set your Claude API key for the reflection engine:

```
ANTHROPIC_API_KEY=sk-ant-...
```

If using MT5 (optional, Windows only):

```
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=YourBroker-Server
```

## 3. Start the MCP Server

```bash
python -m src.tradememory.server
```

The server starts on `http://localhost:8000`. Your AI agent can now connect via MCP.

## 4. Record Your First Trade

Use any MCP-compatible client, or call the API directly:

```python
import requests

API = "http://localhost:8000"

# Record a trade decision
requests.post(f"{API}/trade/record_decision", json={
    "trade_id": "T-2026-0001",
    "symbol": "XAUUSD",
    "direction": "long",
    "lot_size": 0.05,
    "strategy": "VolBreakout",
    "confidence": 0.72,
    "reasoning": "London open momentum, volume spike confirmed",
    "market_context": {"price": 2891.50, "session": "london"},
    "references": []
})

# Record the outcome
requests.post(f"{API}/trade/record_outcome", json={
    "trade_id": "T-2026-0001",
    "exit_price": 2920.00,
    "pnl": 28.50,
    "exit_reasoning": "Hit 2R target",
    "hold_duration": 45
})
```

## 5. Run Daily Reflection

```bash
python daily_reflection.py
```

This analyzes all trades from today and generates a structured reflection report in `reflections/`.

## 6. View the Dashboard (Optional)

```bash
pip install -r requirements-dashboard.txt
streamlit run dashboard.py
```

---

## Next Steps

- **MT5 users:** See [MT5_SYNC_SETUP.md](../MT5_SYNC_SETUP.md) to auto-sync trades from MetaTrader 5
- **Automate reflections:** See [DAILY_REFLECTION_SETUP.md](../DAILY_REFLECTION_SETUP.md) to schedule nightly analysis
- **API reference:** See [API.md](API.md) for full MCP tool documentation
- **Data schema:** See [SCHEMA.md](SCHEMA.md) for TradeRecord format details
