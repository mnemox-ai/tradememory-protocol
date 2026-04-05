# Amnesia Demo Video — 完整腳本

## 規格

- **時長**: 2:30
- **格式**: 螢幕錄影 + 字幕（不需出鏡）
- **語言**: 英文旁白/字幕，另做中文字幕版
- **工具**: OBS Studio 或 Windows Game Bar
- **解析度**: 1920x1080
- **上傳**: Twitter → YouTube → Reddit → FB

---

## 錄影前準備

1. 開兩個 Claude Desktop window（或用同一個切換）
2. 一個**沒有** TradeMemory MCP config
3. 一個**有** TradeMemory MCP config + demo 資料

```bash
# 載入 demo 資料（30 筆模擬 XAUUSD 交易）
pip install tradememory-protocol
tradememory demo --fast
```

4. Claude Desktop config（有記憶版）：
```json
{
  "mcpServers": {
    "tradememory": {
      "command": "uvx",
      "args": ["tradememory-protocol", "--transport", "stdio"]
    }
  }
}
```

5. OBS 設定：螢幕錄影，1080p，60fps

---

## 腳本

### [0:00-0:20] HOOK — 證明問題存在

**畫面**: Claude Desktop 對話框（沒有 TradeMemory）

**字幕**: "Your AI trading assistant remembers nothing. Watch."

**動作**:
- 打字: `What happened last time I traded XAUUSD during high volatility?`
- Claude 回答: `I don't have access to your previous trading history. I can help you analyze current market conditions if you'd like.`

**字幕**: "It doesn't know. Every session starts from zero."

**停頓 2 秒**

---

### [0:20-0:50] INSTALL — 30 秒安裝

**畫面**: Terminal（清爽的黑底白字）

**字幕**: "Let's fix that. 30 seconds."

**動作**:
```bash
$ pip install tradememory-protocol
# (快轉安裝過程)
Successfully installed tradememory-protocol-0.5.1

$ tradememory demo --fast
Loading 30 simulated XAUUSD trades...
✓ Trade 1: VolBreakout long +$340.20
✓ Trade 2: IntradayMomentum short -$196.38
... (快轉)
✓ 30 trades loaded into memory
```

**字幕**: "30 trades. 30 seconds. Memory installed."

---

### [0:50-1:00] CONFIG — Claude Desktop 設定

**畫面**: VS Code 或 Notepad 編輯 claude_desktop_config.json

**字幕**: "One config change."

**動作**:
- 貼上 MCP config JSON
- 存檔
- 重啟 Claude Desktop（快轉）

**字幕**: "Restart Claude. Done."

---

### [1:00-1:50] AHA MOMENT — 有記憶的 AI

**畫面**: Claude Desktop（已接 TradeMemory）

**字幕**: "Same question. Different answer."

**動作**:
- 打字: `What happened last time I traded XAUUSD during high volatility?`

**Claude 回答**（會呼叫 recall_memories tool）:
```
Based on your trading memory, I found 5 trades during high
volatility periods:

• 3 weeks ago: VolBreakout long → +$1,175 (regime: trending_up,
  ATR was 42.3, you entered on momentum confirmation)
• 5 weeks ago: IntradayMomentum long → -$196 (regime: volatile,
  you chased a fake breakout at London open)
• 6 weeks ago: VolBreakout long → -$233 (regime: ranging,
  similar setup to the -$196 loss)

Pattern detected: Your losses cluster in 'ranging' and 'volatile'
regimes. Your wins come in 'trending_up'. Consider being more
selective when regime is not trending.
```

**字幕**: "It remembers. Not just what happened — but what it learned."

**停頓 2 秒**

**動作**:
- 打字: `Should I go long on XAUUSD right now? Current ATR is 38, market feels choppy.`

**Claude 回答**（呼叫 get_agent_state + recall_similar_trades）:
```
⚠️ Caution recommended.

Your agent state shows:
- Confidence: 0.62 (moderate)
- Recent streak: 1 loss
- Current drawdown: 3.2%

Similar setups in memory:
- ATR ~38 + choppy regime → 2 losses, 1 small win
- Your win rate in this condition: 33%

Recommendation: Skip this trade or reduce position size.
The memory shows you historically underperform in choppy
markets with moderate ATR.
```

**字幕**: "This is what trading AI with memory looks like."

---

### [1:50-2:10] SOCIAL PROOF — 數字說話

**畫面**: 深色背景 + 白字卡片（簡潔設計）

**Card 1** (fade in):
```
Used in production by traders running
pre-flight checklists before every trade
```

**Card 2** (fade in):
```
19 MCP tools | 1,293 tests | MIT License
```

**Card 3** (fade in):
```
The first open-source memory layer
for AI trading agents
```

---

### [2:10-2:30] CTA — 行動呼籲

**畫面**: GitHub repo 頁面（已 star 的狀態，顯示 star 數）

**字幕**: "TradeMemory. Open source. Free forever."

**動作**: 滑鼠移到 Star 按鈕

**字幕**: "Give your trading AI a memory."

**最後畫面**:
```
github.com/mnemox-ai/tradememory-protocol

pip install tradememory-protocol

⭐ Star if this resonated
```

**淡出**

---

## 錄影 SOP

### Step 1: 準備

- [ ] `tradememory demo --fast` 已跑完
- [ ] Claude Desktop 兩個設定都測過
- [ ] OBS 錄影測試過，音頻正常
- [ ] 桌面乾淨，關掉不相關視窗
- [ ] 字體大小調大（Terminal 和 Claude Desktop 都要 16px+）

### Step 2: 錄影

- [ ] 先錄 Hook 段（無記憶版，1-2 take）
- [ ] 再錄 Install 段（可以快轉）
- [ ] 最後錄 AHA Moment 段（有記憶版，可能需要 2-3 take）
- [ ] Social Proof 和 CTA 用後製加文字

### Step 3: 剪輯

- 工具：CapCut（免費）或 DaVinci Resolve
- 加字幕（每段都要）
- 加轉場（簡單 fade 就好）
- 加背景音樂（低音量，LoFi 風格）
- 總長控制在 2:30 以內

### Step 4: 上傳順序

1. **Twitter/X** — 先發，標記 #AITrading #MCP #OpenSource
2. **YouTube** — 標題: "Your Trading AI Has Amnesia — Here's the Fix"
3. **Reddit r/algotrading** — 作為帖子內嵌影片
4. **Facebook** — 中文字幕版，故事型文案搭配

---

## 替代方案（如果不想錄影）

用 `asciinema` 錄 terminal session，轉成 GIF：

```bash
asciinema rec demo.cast
# 跑 demo 流程
asciinema play demo.cast
# 轉 GIF
agg demo.cast demo.gif
```

這個可以先發 Twitter 測反應，再決定要不要錄完整影片。

---

## Awesome-List 手動提交指南

### wong2/awesome-mcp-servers (30K stars)
**不接受 PR**，要去網站提交：
→ https://mcpservers.org/submit

### appcypher/awesome-mcp-servers (6K stars)
1. 去 https://github.com/zychenpeng/awesome-mcp-servers-1
2. 確認 `add-tradememory` branch 有 TradeMemory entry
3. 點 "Contribute" → "Open Pull Request"
4. Base: appcypher/awesome-mcp-servers main
5. PR 標題: "Add TradeMemory to Finance section"

### TensorBlock/awesome-mcp-servers (1K stars)
1. Fork repo
2. 在 `💰 Finance & Crypto` section 加入：
```
- [mnemox-ai/tradememory-protocol](https://github.com/mnemox-ai/tradememory-protocol): Persistent memory layer for AI trading agents. Outcome-weighted recall, behavioral analysis, SHA-256 audit trail. 19 MCP tools, 1293 tests. MIT license.
```
3. 提 PR

### modelcontextprotocol/servers (官方)
1. Fork repo
2. 在 `🤝 Third-Party Servers` section 加入：
```
- **[TradeMemory](https://github.com/mnemox-ai/tradememory-protocol)** – Persistent memory layer for AI trading agents. Outcome-weighted recall, behavioral analysis, and SHA-256 audit trail via MCP.
```
3. 提 PR
