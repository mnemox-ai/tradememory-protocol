# Adding Memory to Your EA: A Practical Guide

**Target**: MQL5 Forum article + Medium cross-post
**Audience**: MQL5 EA developers (intermediate+)
**Language**: English (zh-TW version separate)
**Word count target**: 1500-2000 words

---

## Hook

Your EA executes the same strategy parameters regardless of whether it lost 5 trades in a row last week or hit a new equity high yesterday. It has no memory.

What if your EA could remember every decision it made, why it made it, and what happened afterward — then use that context to inform the next trade?

This article shows how to connect any MQL5 EA to a structured memory layer using TradeMemory Protocol.

---

## Section 1: The Problem with Memoryless EAs

Every EA developer knows this cycle:
1. Optimize parameters on historical data
2. Deploy to demo/live
3. Watch it trade through regime changes it wasn't optimized for
4. Re-optimize with new data
5. Repeat

The EA never *learns* from its own live experience. It doesn't know that:
- VolBreakout lost 4/5 trades during last week's ranging market
- IntradayMomentum performs 2x better during London session
- Spread was 45pts during the last SL hit (vs normal 15pts)

This information exists in your trade history. But it's not accessible to the EA at decision time.

## Section 2: What is a Trading Memory Layer?

A memory layer sits between your EA and a database, providing:

1. **Episodic Memory** — Raw record of every trade with full context (WHY did the EA enter?)
2. **Semantic Memory** — Learned beliefs updated over time ("VolBreakout in trending regime: 72% profitable")
3. **Anti-Resonance** — Forced recall of losing trades to prevent overconfidence

The key innovation is **Outcome-Weighted Memory (OWM)** — memories are scored not just by relevance, but by how informative their outcomes were.

## Section 3: Architecture (Diagram)

```
MT5 Terminal
    │
    ├── EA executes trade → event_log CSV (with reasoning)
    │
    ├── mt5_sync polls every 60s
    │       │
    │       ├── Detects closed positions
    │       ├── Reads event_log for entry context
    │       └── POSTs to TradeMemory API:
    │           ├── record_decision (entry + reasoning + confidence)
    │           └── record_outcome (exit + P&L + R-multiple)
    │
    └── On new trade signal:
            ├── recall_similar() → top 5 similar past trades
            ├── query_beliefs() → Bayesian confidence for strategy
            └── Agent decides: GO / NO_GO
```

## Section 4: Implementation (Code Samples)

### Step 1: EA writes event_log CSV

```mql5
// In your EA's OnTick() or signal function:
void LogTradeEvent(string evt, string reason, double score) {
    string line = StringFormat("%s,%s,%s,%s,%.2f",
        TimeToString(TimeCurrent()), _Symbol, evt, reason, score);
    int handle = FileOpen("NG_Gold/event_log.csv", FILE_CSV|FILE_WRITE|FILE_COMMON);
    FileSeek(handle, 0, SEEK_END);
    FileWriteString(handle, line + "\n");
    FileClose(handle);
}
```

### Step 2: Python sync reads event_log + MT5 API

```python
# mt5_sync reads the CSV, matches by position_id, sends to TradeMemory
context = event_log_reader.find_entry_context(
    symbol="XAUUSD",
    magic=260112,
    position_id=ticket,
    entry_time=deal.time,
)
# Returns: reasoning, confidence, market_data (ATR, EMA, spread)
```

### Step 3: Query memory before new trades

```python
# Before entering a new trade:
similar = recall_similar("XAUUSD", "VolBreakout", "london")
# Returns: 5 most similar past trades with outcomes

beliefs = query_beliefs(strategy="VolBreakout")
# Returns: Bayesian confidence (e.g., 0.72 for trending regime)
```

## Section 5: What You Get — Trading Decision Record

Every trade produces a complete audit record:

```json
{
  "record_id": "MT5-7047640363",
  "strategy": "VolBreakout",
  "confidence_score": 0.7,
  "signal_source": "SELL entry. ATR(M5)=13.62. H1 EMA bearish",
  "memory": {
    "similar_trades": ["T-2026-0001", "T-2026-0005"],
    "anti_resonance_applied": true,
    "negative_ratio": 0.25
  },
  "pnl": 117.80,
  "pnl_r": 0.85,
  "data_hash": "a3f2b8c9..."
}
```

The `data_hash` provides tamper detection — if anyone modifies the record, the hash won't match.

## Section 6: Results from NG_Gold (Real Data)

*[To be filled after Phase 1 baseline collection — 4 weeks]*

Before/after comparison:
- Memory-augmented vs memoryless decision accuracy
- Anti-resonance effect on risk calibration
- Belief convergence rate across market regimes

## Section 7: Getting Started

```bash
pip install tradememory-protocol
python -m tradememory  # starts MCP + REST server on port 8000
```

Connect your EA in 3 steps:
1. Write event_log CSV from MQL5 (10 lines of code)
2. Run mt5_sync_v3.py (provided, zero config)
3. Query `/owm/recall` before new trades

GitHub: [mnemox-ai/tradememory-protocol](https://github.com/mnemox-ai/tradememory-protocol)

---

## Call to Action

- Star the repo if this is useful
- Open an issue if you want help connecting your EA
- The TDR spec is open — contributions welcome

---

## zh-TW 版本大綱

標題：**讓你的 EA 學會記憶：交易記憶層實戰指南**

同樣結構，但：
- 用繁體中文
- 技術術語保留英文（MQL5, ATR, OWM, API）
- 強調「這不是又一個指標，是讓 EA 從自己的交易中學習」
- MQL5 Forum 中文區投稿
