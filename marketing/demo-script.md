# Demo Video Script — TradeMemory Protocol

## Video Info

- **Length:** 2-3 minutes
- **Format:** Screen recording (Claude Desktop) + voiceover
- **Audience:** MT5/Forex traders who use AI agents
- **Data:** Simulated trades (label clearly at start)
- **Music:** Lo-fi / ambient background (low volume)

---

## Scene 1: Hook (0:00 - 0:15)

**Screen:** Black background with text fade-in

> "Your AI trading assistant forgets everything. Every. Single. Session."

**Voiceover:**
"You ask Claude to analyze your trades. It gives great insights. Next day? Gone. It starts from zero. What if it could remember?"

**Screen:** TradeMemory Protocol logo + tagline: "AI Trading Memory for MT5"

---

## Scene 2: Open Claude Desktop (0:15 - 0:40)

**Screen:** Open Claude Desktop. TradeMemory MCP server is connected (visible in MCP tool list).

**Voiceover:**
"TradeMemory is an MCP server that plugs directly into Claude Desktop. No dashboard, no SaaS — it runs locally alongside your MT5."

**Action:** Type into Claude Desktop:

> "How are my XAUUSD trades performing this week?"

**Claude responds** (using `recall_trade_memories` tool):

```
Found 30 trades this week for XAUUSD:
- Total P&L: +$486.50
- Win rate: 60% (18W / 12L)
- Best strategy: VolBreakout (+$432.50, 75% WR)
- Worst session: Asian (-$106.00, 25% WR)
```

**Voiceover:**
"The agent pulls your actual trade history — synced automatically from MT5 every 60 seconds. No manual journaling."

---

## Scene 3: Ask for Performance Breakdown (0:40 - 1:10)

**Action:** Type:

> "Break down my performance by session and strategy."

**Claude responds** (using `get_trade_performance` tool):

```
Performance by Session:
  London:   14 trades | 79% WR | +$438.50 | Avg R: +2.1
  New York:  8 trades | 50% WR | +$57.00  | Avg R: +0.4
  Asian:     8 trades | 25% WR | -$106.00 | Avg R: -0.8

Performance by Strategy:
  VolBreakout: 16 trades | 75% WR | +$432.50 | PF: 3.2
  Pullback:    14 trades | 43% WR | -$43.00  | PF: 0.8
```

**Voiceover:**
"This is Layer 1 and Layer 2 — raw trade data and pattern discovery. The system found that London VolBreakout is your edge, while Asian Pullback is bleeding money."

**Screen:** Highlight the contrast: London 79% WR vs Asian 25% WR

---

## Scene 4: Run Reflection (1:10 - 1:50)

**Action:** Type:

> "Run a reflection on my recent trades and suggest adjustments."

**Claude responds** (using `run_trade_reflection` tool):

```
Reflection Report — 2026-03-03

Patterns Confirmed:
  1. London VolBreakout: 79% WR over 14 trades — HIGH EDGE
  2. Asian session: 25% WR, consistent losses — WEAK
  3. Trades with confidence > 0.75: 85% WR vs < 0.55: 17% WR

Recommended Adjustments:
  Parameter              | Current | Proposed | Reason
  asian_max_lot          | 0.05    | 0.025    | Asian WR 25% — cut exposure 50%
  london_max_lot         | 0.05    | 0.08     | London WR 79% — earned room
  min_confidence         | 0.40    | 0.55     | Low-conf trades lose 83%
  pullback_enabled       | true    | false     | Pullback PF 0.8 — disable

Status: 4 adjustments proposed. Apply with approval.
```

**Voiceover:**
"This is Layer 3 — the system converts patterns into concrete parameter changes. Not vibes, not 'consider adjusting.' Exact numbers, with the data behind them."

**Screen:** Zoom into the adjustment table

---

## Scene 5: The Memory Persists (1:50 - 2:15)

**Screen:** Close Claude Desktop. Reopen it.

**Action:** Type:

> "What did we learn about Asian session trades?"

**Claude responds:**

```
From your recent analysis:
- Asian session: 25% WR (2W/6L), net -$106.00
- Proposed adjustment: reduce lot size from 0.05 to 0.025
- Status: awaiting your approval
- This pattern was discovered on 2026-03-03 from 30 trades
```

**Voiceover:**
"Close the app, come back tomorrow — the memory is still there. Your AI assistant now has a trading journal that it actually reads."

---

## Scene 6: How It Works (2:15 - 2:35)

**Screen:** Architecture diagram (simple, 3 boxes)

```
MT5 Terminal          TradeMemory            Claude Desktop
  [4 EAs] ──sync──▶ [L1 → L2 → L3] ◀──MCP──▶ [AI Agent]
  every 60s          SQLite local             4 tools
```

**Voiceover:**
"MT5 syncs trades automatically. TradeMemory stores, analyzes, and learns. Claude connects via MCP — four tools: store, recall, performance, reflection. Everything runs on your machine."

---

## Scene 7: CTA (2:35 - 2:50)

**Screen:** GitHub page with star count

**Text overlay:**

```
Open source. MIT license. Zero cost.

pip install tradememory-protocol

github.com/mnemox-ai/tradememory-protocol
```

**Voiceover:**
"TradeMemory Protocol. Open source, MIT license. Install in 30 seconds. Link in description."

---

## Production Notes

- All trade data shown is **simulated** — add watermark or text overlay: "Simulated Data"
- Screen recording tool: OBS Studio
- Resolution: 1920x1080, 30fps
- Claude Desktop should have TradeMemory MCP server connected before recording
- Rehearse the prompts — Claude's actual responses will vary, may need retakes
- Keep voiceover pace steady, ~150 words/minute
- Total script word count: ~400 words voiceover
