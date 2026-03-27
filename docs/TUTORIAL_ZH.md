# TradeMemory Protocol — 完整教學

**所需時間：** 約 10 分鐘
**前置需求：** Python 3.10+、git
**是否需要 API key：** 不需要（demo 使用模擬資料）

---

## 你會做出什麼

一個有記憶的 AI 交易助手，能**記住每筆交易、自動發現規律、並隨時間進化策略**。

完成這個教學後，你會看到一個 AI agent 從「無狀態計算機」變成「有盤感的交易員」— 全程不到 10 分鐘。

---

## 第一步：安裝（2 分鐘）

### 方案 A：一行安裝

```bash
curl -sSL https://raw.githubusercontent.com/mnemox-ai/tradememory-protocol/master/scripts/platform/install.sh | bash
cd tradememory-protocol
```

### 方案 B：手動安裝

```bash
git clone https://github.com/mnemox-ai/tradememory-protocol.git
cd tradememory-protocol

python -m venv venv
source venv/bin/activate    # Linux/Mac
# venv\Scripts\activate     # Windows

pip install -r requirements.txt
cp .env.example .env
```

驗證安裝：

```bash
python -m pytest tests/ -q
# 預期結果：1,233 passed
```

---

## 第二步：執行 Demo（2 分鐘）

```bash
python scripts/demo.py
```

這會跑 30 筆模擬的 XAUUSD 交易，走完整個 pipeline。不需要 API key。

**你會看到：**

1. **L1 — 記錄交易**：30 筆交易，包含時段、策略、信心度、盈虧
2. **L2 — 發現規律**：反思引擎自動找出：
   - 倫敦盤：約 100% 勝率（強勢）
   - 亞洲盤：約 10% 勝率（弱勢）
   - 高信心度交易遠優於低信心度交易
3. **L3 — 策略調整**：自動產生規則：
   - 亞洲盤倉位減半（績效差）
   - 倫敦盤倉位增加 60%（績效好）
   - 最低信心度門檻提高

---

## 第三步：理解三層記憶架構

TradeMemory 使用三層架構：

| 層級 | 名稱 | 儲存內容 | 範例 |
|------|------|---------|------|
| **L1** | 熱記憶 | 進行中的交易、當前 session | "XAUUSD 做多 @ 2847, 信心 0.78" |
| **L2** | 溫記憶 | 發現的規律、洞察 | "倫敦盤突破：73% 勝率" |
| **L3** | 冷記憶 | 完整交易歷史（SQLite） | 全部 30 筆交易的完整上下文 |

**關鍵洞察：** 大多數 AI agent 只有 L1（當前上下文）。TradeMemory 加上了 L2 和 L3，讓 agent 能隨時間累積知識。

---

## 第四步：OWM 認知記憶

TradeMemory v0.5 新增了 **OWM（Outcome-Weighted Memory）** — 五層記憶架構，模擬交易員的大腦運作方式：

| 記憶層 | 功能 |
|--------|------|
| **情景記憶（Episodic）** | 儲存每筆交易的完整上下文（價格、市場狀態、反思） |
| **語義記憶（Semantic）** | 貝葉斯信念，每筆交易後更新（「趨勢市場 VolBreakout：72% 優勢」） |
| **程序記憶（Procedural）** | 每個策略的滾動績效統計 — 什麼真正有效 |
| **情感記憶（Affective）** | EWMA 信心追蹤、連勝/連虧、回撤狀態 |
| **前瞻記憶（Prospective）** | 交易計畫，含進出場條件與到期時間 |

### 透過 MCP 記錄交易

對你的 Claude agent 說：

> 「記錄我的 XAUUSD 做多交易：5180 進場，5210 出場，賺了 $90，用 VolBreakout 策略。市場趨勢向上，倫敦盤動能強勁。ATR 是 $155。信心度 0.8。」

這會呼叫 `remember_trade`，同時寫入五層記憶。

### 透過 MCP 回憶記憶

進場前，問你的 agent：

> 「我的記憶對在趨勢市場交易 XAUUSD 有什麼看法？我在考慮 VolBreakout。」

這會呼叫 `recall_memories`，使用結果加權評分 — 績效更好、上下文匹配、信心更高的交易排名更前。

### 其他 OWM 工具

- `get_behavioral_analysis` — 「顯示我的行為模式」→ 各市場狀態勝率、過度交易偵測、信心校準
- `get_agent_state` — 「我目前的狀態如何？」→ 情感狀態、回撤、連勝/連虧資訊
- `create_trading_plan` — 「建立計畫：如果 XAUUSD 回調到 20 EMA，在 5150 做多」
- `check_active_plans` — 「我有沒有進行中的交易計畫？」

---

## 第五步：進化引擎

進化引擎使用 Claude 從**原始價格數據中發現交易策略**，然後回測並在多代之間篩選存活者。

### 執行完整進化

對你的 Claude agent 說：

> 「用 BTCUSDT 1 小時數據跑 3 代進化，每代 10 個候選策略。」

這會呼叫 `evolution_evolve_strategy`，執行流程：
1. 從 Binance 抓取 OHLCV 數據
2. 使用 Claude 生成候選交易模式
3. 回測每個模式（向量化，不需 API 呼叫）
4. 淘汰弱假設（Sharpe < 門檻值）
5. 重複 N 代
6. 用樣本外數據驗證存活者

### 逐步執行

你也可以一步一步跑：

```
# 1. 抓取數據
> 「抓取 90 天的 BTCUSDT 1 小時數據來做進化」
# 呼叫：evolution_fetch_market_data

# 2. 發現模式
> 「從 BTCUSDT 數據中發現 5 個交易模式」
# 呼叫：evolution_discover_patterns

# 3. 回測模式
> 「回測第一個模式」
# 呼叫：evolution_run_backtest

# 4. 查看紀錄
> 「顯示進化紀錄」
# 呼叫：evolution_get_log
```

**需要：** `.env` 中設定 `ANTHROPIC_API_KEY`（Claude 負責生成模式假設）。

---

## 第六步：記錄你自己的交易（1 分鐘）

啟動 MCP server：

```bash
python -m tradememory
# Server 在 http://localhost:8000 運行
```

在另一個終端，記錄一筆交易：

```bash
curl -X POST http://localhost:8000/trade/record_decision \
  -H "Content-Type: application/json" \
  -d '{
    "trade_id": "MY-001",
    "symbol": "XAUUSD",
    "direction": "long",
    "lot_size": 0.05,
    "strategy": "VolBreakout",
    "confidence": 0.75,
    "reasoning": "倫敦開盤，2850 上方動能強勁"
  }'
```

記錄交易結果：

```bash
curl -X POST http://localhost:8000/trade/record_outcome \
  -H "Content-Type: application/json" \
  -d '{
    "trade_id": "MY-001",
    "exit_price": 2858.50,
    "pnl": 42.50,
    "pnl_r": 2.1,
    "exit_reasoning": "達到 2R 目標"
  }'
```

---

## 第七步：啟動反思引擎（2 分鐘）

記錄幾筆交易後，觸發反思引擎：

```bash
python -m src.daily_reflection
```

**沒有 API key（規則引擎）：** 計算勝率、時段模式、策略績效。

**有 Claude API key：** 在 `.env` 中加入：
```
ANTHROPIC_API_KEY=sk-ant-...
```

反思引擎就會用 Claude 產生更深入的洞察，例如：
- 「你在倫敦盤突破的進場時機很好，但出場太早 — 考慮使用追蹤止損」
- 「亞洲盤虧損與 UTC 02:00 前的低成交量時段相關」

---

## 第八步：在下一筆交易中使用記憶

Agent 下次啟動時，會載入它的狀態：

```python
from src.tradememory.state import StateManager
from src.tradememory.db import Database

db = Database("data/tradememory.db")
state = StateManager(db=db)

agent_state = state.load_state("my-agent")
print(agent_state.warm_memory)       # 學到的規律
print(agent_state.risk_constraints)  # 調整後的風控參數
```

Agent 現在知道：
- 哪些交易時段表現最好
- 哪些策略有優勢
- 該用什麼信心度門檻
- 如何根據歷史績效調整倉位大小

---

## 剛才發生了什麼？

你的 AI 從**「無狀態計算機」**變成了**「有盤感的交易員」**。

| 之前 | 之後 |
|------|------|
| 每次 session 從零開始 | Agent 載入學到的規律 |
| 重複犯同樣的錯 | 偵測到模式，自動調整行為 |
| 不知道自己的勝率 | 按時段、策略、時間知道勝率 |
| 固定倉位大小 | 根據績效動態調整倉位 |
| session 之間沒有上下文 | 完整的跨 session 記憶持久化 |

---

## MCP 工具參考

TradeMemory 提供 17 個 MCP 工具，分為四大類：

### 核心記憶（4 個工具）

| 工具 | 說明 |
|------|------|
| `store_trade_memory` | 記錄交易決策，含策略、信心度、推理 |
| `recall_similar_trades` | 根據標的、策略或上下文查找過去交易 |
| `get_strategy_performance` | 各策略的勝率、平均盈虧、交易次數 |
| `get_trade_reflection` | 取得 AI 生成的近期交易反思 |

### OWM 認知記憶（6 個工具）

| 工具 | 說明 |
|------|------|
| `remember_trade` | 將交易寫入 5 層 OWM 記憶（情景 → 語義 → 程序 → 情感） |
| `recall_memories` | 結果加權回憶，含上下文匹配與時間衰減評分 |
| `get_behavioral_analysis` | 各市場狀態勝率、過度交易偵測、信心校準 |
| `get_agent_state` | 目前情感狀態 — 信心、回撤、連勝/連虧 |
| `create_trading_plan` | 建立前瞻計畫，含進出場條件與到期時間 |
| `check_active_plans` | 列出進行中的計畫，檢查是否觸發 |

### 進化引擎（5 個工具）

| 工具 | 說明 |
|------|------|
| `evolution_fetch_market_data` | 從 Binance 抓取 OHLCV 數據用於回測 |
| `evolution_discover_patterns` | LLM 驅動的交易模式生成 |
| `evolution_run_backtest` | 候選模式的向量化回測 |
| `evolution_evolve_strategy` | 完整進化循環 — 生成、回測、篩選、重複 |
| `evolution_get_log` | 查看歷史進化紀錄與畢業策略 |

### 決策審計追蹤（2 個工具）

| 工具 | 說明 |
|------|------|
| `export_audit_trail` | 匯出交易決策記錄，含 SHA-256 防竄改驗證 |
| `verify_audit_hash` | 驗證決策記錄完整性，重新計算 SHA-256 雜湊 |

---

## 下一步

- **連接 MT5**：參考 [MT5 設定指南](../MT5_SYNC_SETUP.md) 同步真實交易
- **設定每日反思**：參考 [每日反思設定](../DAILY_REFLECTION_SETUP.md)
- **閱讀架構文件**：參考 [架構總覽](ARCHITECTURE.md)
- **API 參考文件**：參考 [API 文件](API.md)

---

## 疑難排解

**測試失敗？**
```bash
python -m pytest tests/ -v  # 查看哪個測試失敗
```

**Server 無法啟動？**
```bash
pip install -r requirements.txt  # 確認所有套件已安裝
```

**demo.py 顯示編碼錯誤？**
```bash
# 在 Windows 上，確保 UTF-8：
set PYTHONIOENCODING=utf-8
python scripts/demo.py
```

---

**有問題？** 開一個 issue：[GitHub Issues](https://github.com/mnemox-ai/tradememory-protocol/issues)

由 [Mnemox](https://mnemox.ai) 用心打造 — AI 記憶基礎設施。
