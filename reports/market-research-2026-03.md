# TradeMemory Protocol — 深度市場調查報告

> **版本**: v1.0 | **日期**: 2026-03-16 | **作者**: Mnemox AI Research
> **資料來源**: GitHub, PyPI, Smithery.ai, Glama.ai, mcp.so, awesome-mcp-servers, OpenClaw, Product Hunt, Reddit, MQL5 Forum, Twitter/X, 學術論文, CFTC/SEC 公告
> **涵蓋範圍**: 19 個 GitHub 競品、15 個 PyPI trading MCP、200+ MCP server、60+ 社群來源、12 個 KOL/社群

---

## 1. Executive Summary

### 五大關鍵發現

1. **記憶層 = 藍海市場**。200+ 個 trading/finance MCP server，100% 都在做「數據查詢」或「交易執行」。**零個**做「交易記憶與學習」。TradeMemory 是唯一佔據此象限的產品。

2. **Forex/MT5 = 被遺忘的金礦**。所有開源 AI trading 框架（49K stars 的 ai-hedge-fund、32K 的 TradingAgents）專注美股和 crypto。整個 MCP 生態 200+ server 只有 ≤5 個做 forex。外匯市場日交易量 $7.5 萬億，是 crypto 的 50 倍。

3. **MCP trading 生態正在爆發**。LSEG（倫敦交易所集團）已發布 MCP 戰略文，Alpaca/altFINS/Alpha Vantage 官方進場，PyPI 最大的 trading MCP（alpaca-mcp-server）月下載 7,882。但整體仍在早期，除了 Alpaca 沒有任何 package 月下載 > 2,000。

4. **用戶最大痛點 = TradeMemory 的核心能力**。社群最痛的五個問題：overfitting（★★★★★）、regime change blindness（★★★★★）、scam 信任危機（★★★★☆）、AI 標籤行銷化（★★★★☆）、不從歷史交易學習（★★★★☆）。TradeMemory 直接解決 #1（L2 pattern + OOS validation）、#2（Evolution Engine）、#5（五層 OWM）。

5. **TradeMemory 上架嚴重不足**。目前只在 Glama.ai（#8）和 PyPI（#6）上架。Smithery.ai（0/40 trading server 做記憶）、mcp.so（0/141）、awesome-mcp-servers、OpenClaw、Product Hunt 均未上架。每一個平台都是零成本的曝光機會。

---

## 2. 競品分析

### 2.1 開源 AI Trading 框架對比

| 維度 | TradingAgents | FinRobot | AI-Trader | FinMem | AgenticTrading | **TradeMemory** |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| **Stars** | 32.3k | 6.4k | 11.8k | 858 | 104 | 91 |
| **狀態** | Active | Active | Active | **Dead (3yr)** | Active | Active |
| **Live Trading** | No | No | Paper | No | No | **Yes (MT5)** |
| **Forex/Gold** | No | No | No | No | No | **Yes** |
| **MCP Protocol** | No | No | No | No | Partial | **Yes (15 tools)** |
| **記憶系統** | 無 | 無 | 無 | 3 層（時間衰減） | Neo4j | **5 類 OWM** |
| **Evolution** | No | No | No | No | No | **Yes** |
| **Broker 連接** | No | No | No | No | No | **MT5 + Binance** |
| **出身** | UCLA+MIT | AI4Finance | HKU | Stevens Inst. | Open-Finance-Lab | Mnemox AI |

**關鍵觀察**：

- **FinMem**（858 stars）是記憶架構概念最接近的競品，但**已死 3 年**。其 3 層記憶（按時間衰減）vs TradeMemory 5 類記憶（按認知功能），且無 MCP、無 forex、無 live trading、無 evolution。TradeMemory 可接下「trading memory」學術關鍵字。
- **AgenticTrading**（104 stars）有 Neo4j Memory Agent + 部分 MCP 支持，是唯一概念重疊的活躍專案。但記憶是其 orchestration 的 sub-feature，不是獨立產品。
- **TradingAgents**（32.3K stars）已被發現 [look-ahead bias](https://github.com/TauricResearch/TradingAgents/issues/203)，且每次決策獨立、無跨 session 學習。

### 2.2 商業產品對比

| 維度 | Walbi | Stoic.ai | Composer | **TradeMemory** |
|------|:---:|:---:|:---:|:---:|
| **市場** | Crypto only | Crypto only | 美股 | **Forex (XAUUSD)** |
| **開源** | No | No | No | **Yes (MIT)** |
| **AI 類型** | GPT-4o | 傳統量化 | AI backtest | **LLM + Evolution** |
| **記憶/學習** | No | No | No | **5-layer OWM** |
| **用戶** | 1M+ 註冊 | 15K+ 付費 | Unknown | Early |
| **定價** | Free | $9-5%/yr | $60-1080/mo | Free (MIT) |
| **可驗證** | No（黑箱） | No（有造假投訴） | Partial | **Yes（開源）** |

### 2.3 記憶架構專題對比

| 專案 | 記憶架構 | 分類邏輯 | 持久化 | 可被外部呼叫 | Live Data |
|------|----------|----------|--------|-------------|-----------|
| FinMem | 3 層（Shallow/Intermediate/Deep） | 時間衰減 | Checkpoint | No（封閉框架） | No |
| FinAgent | 3 類（Market/Low/High-Reflection） | 按功能 | In-memory | No | No |
| AgenticTrading | Neo4j + Vector | Graph 關係 | Neo4j | Partial（MCP） | No |
| **TradeMemory** | **5 類 OWM** | **認知功能** | **SQLite** | **Yes（15 MCP + 30 REST）** | **Yes（MT5 Sync）** |

**TradeMemory 獨特性**：
1. **Outcome-Weighted**：交易結果回頭影響記憶權重
2. **Affective Memory**：唯一追蹤交易情緒/信心的系統
3. **Prospective Memory**：唯一有前瞻性記憶的系統
4. **Protocol-level**：唯一把記憶做成 MCP protocol 的產品
5. **Evolution Engine**：記憶自動 hypothesize → backtest → evolve

### 2.4 真正的威脅

| 威脅 | 風險等級 | 原因 |
|------|----------|------|
| **metatrader-mcp-server**（1,286/mo 下載） | **高** | 如果加上記憶功能，直接搶用戶 |
| **AgenticTrading**（104 stars） | **中** | Neo4j Memory Agent + MCP，概念重疊 |
| **企業級 MCP**（FactSet, LSEG） | **中** | 大廠若做 trading memory 功能，小廠難競爭 |
| **Alpaca MCP**（7,882/mo 下載） | **低** | 純執行層，但如果擴展到記憶... |

---

## 3. MCP 生態系與分發渠道

### 3.1 MCP Trading/Finance 生態全景

| 平台 | Trading/Finance Server 數量 | Forex 專屬 | 做「記憶層」的 |
|------|---------------------------|-----------|-------------|
| Smithery.ai | 40 | 0 | **0** |
| Glama.ai | 61 | 4 | **只有 TradeMemory** |
| mcp.so | 141 | ~2 | **0** |
| awesome-mcp-servers | ~150 | 1 | **0** |
| OpenClaw | 311 | 0 | **0** |
| PyPI | 15 | 3（含 TradeMemory） | **只有 TradeMemory** |
| **合計（去重）** | **200+** | **≤5** | **1（TradeMemory）** |

### 3.2 PyPI Trading MCP 下載排名

| # | Package | 月下載 | 類型 |
|---|---------|--------|------|
| 1 | alpaca-mcp-server | 7,882 | 執行（官方維護） |
| 2 | investor-agent | 1,526 | 數據（已 deprecated） |
| 3 | metatrader-mcp-server | 1,286 | 執行（MT5） |
| 4 | finance-mcp-server | 666 | 數據 |
| 5 | binance-mcp-server | 627 | 執行（Binance） |
| **6** | **tradememory-protocol** | **515** | **記憶（唯一）** |
| 7 | tasty-agent | 507 | 執行 |

- 整個市場早期：除 Alpaca 外沒有 > 2,000/mo
- TradeMemory PyPI 還是 v0.4.0，實際本地已 v0.5.0（1055 tests）

### 3.3 TradeMemory 上架差距

| 平台 | 狀態 | 動作 | 優先級 |
|------|------|------|--------|
| Smithery.ai | **未上架** | 需上架 | P0 |
| mcp.so | **未上架** | 需上架 | P0 |
| awesome-mcp-servers | **未列入** | 需提 PR | P0 |
| Glama.ai | ✅ 已上架（v0.4.0） | 更新 v0.5.0 | P1 |
| PyPI | ✅ 已上架（v0.4.0） | 推 v0.5.0 | P1 |
| OpenClaw | 未上架 | 可考慮 | P2 |
| Product Hunt | 未上架 | 首個 MCP+trading memory launch | P2 |

### 3.4 跨平台曝光度比較

| Server | Smithery | Glama | mcp.so | awesome | PyPI |
|--------|:---:|:---:|:---:|:---:|:---:|
| Alpaca | ✅ | ✅ | ✅ | ✅ | ✅ (7,882/mo) |
| MetaTrader5 | ✅ | ✅ | -- | ✅ | ✅ (1,286/mo) |
| QuantConnect | -- | ✅ | ✅ | ✅ | -- |
| Yahoo Finance | -- | ✅ | ✅ (16個!) | ✅ | -- |
| **TradeMemory** | **❌** | ✅ | **❌** | **❌** | ✅ |

### 3.5 KOL 與社群渠道

| 渠道 | 相關度 | 說明 |
|------|--------|------|
| **Hummingbot Discord** | **最高** | 開源做市 + MCP + algo trading，理念匹配 |
| **aixbt**（@aixbt_agent, 470K followers） | 高 | AI agent + market insights，概念類似 L2 |
| **Lola**（@lola_onchain） | **高** | 「evolving logic and memory capabilities」— 直接映射 TradeMemory |
| Product Hunt | 高 | MCP + Trading 僅 Composer 1 家上架，空白機會 |
| r/algotrading | 中 | 痛點最集中的社群 |
| MQL5 Forum | 中 | EA 開發者聚集地，但轉換慢 |

---

## 4. 目標用戶痛點

### 4.1 五大痛點排名

| # | 痛點 | 嚴重度 | 數據支撐 | TradeMemory 對應能力 |
|---|------|--------|----------|---------------------|
| 1 | **Overfitting / Curve-Fitting** | ★★★★★ | r/algotrading 最熱門話題；參數 > 10 個幾乎確定 overfitting | L2 pattern layer + OOS validation |
| 2 | **Regime Change Blindness** | ★★★★★ | 73% 自動帳戶 6 個月內失敗；趨勢策略在震盪市勝率掉到 39% | Evolution Engine + regime tagging |
| 3 | **Scam / 信任危機** | ★★★★☆ | AI 詐騙暴增 456%（TRM Labs）；SEC 起訴 $14M 案 | 開源 MIT + 不託管資金 |
| 4 | **AI 標籤行銷化** | ★★★★☆ | 一人測試 47 個 forex robot 虧 $11,400；SEC 取締「AI Washing」 | 可審計代碼 + 真實 LLM 能力 |
| 5 | **不從歷史交易學習** | ★★★★☆ | MQL5 開發者明確需求；「set and forget rarely works」 | **五層 OWM — 核心賣點** |

### 4.2 MQL5 EA 開發者特有痛點

| 痛點 | 說明 | TradeMemory 機會 |
|------|------|-----------------|
| 回測不一致 | 相同設定跑多次結果不同 | L2 pattern 追蹤回測差異 |
| Strategy Tester vs Live 差異 | CopyTicks 在 tester 中報錯 | Backtest-to-live 差異追蹤 |
| 數據持久化困難 | MQL5 原生不支持好用方案 | SQLite 持久化 + MCP 存取 |
| 從回測到實盤落差 | 「transitions bring surprises」 | 交叉比對 backtest vs live 表現 |

### 4.3 用戶恐懼排名

| # | 恐懼 | 證據 |
|---|------|------|
| 1 | **虧錢** | 73% 自動帳戶 6 個月內失敗 |
| 2 | **被騙** | AI 詐騙暴增 456%；CFTC 公開警告 |
| 3 | **Overfitting** | 回測完美 → 實盤崩壞（最常見故事） |
| 4 | **Black Box 風險** | 不知道 AI 為什麼做某交易 |
| 5 | **監管風險** | SEC AI Washing 取締；FINRA 要求 human-in-the-loop |

### 4.4 用戶願意付費解決的問題

1. **Regime Detection + Auto-Adaptation** — 最大未滿足需求
2. **Backtest-to-Live Consistency** — walk-forward + OOS 驗證
3. **Trade Memory / Learning** — 「What went wrong in last 50 trades?」的自動回答
4. **Risk Management Automation** — 超越簡單 SL/TP
5. **Open-Source + Auditable** — 可驗證的策略邏輯

---

## 5. SEO 與關鍵字策略

### 5.1 關鍵字矩陣

| 關鍵字 | 預估月搜尋量 | 競爭度 | 策略 |
|--------|-------------|--------|------|
| `AI trading bot` | 100K–500K | **極高** | ❌ 不打。被 affiliate listicle 壟斷 |
| `crypto trading bot` | 100K–500K | **極高** | ❌ 不打。3Commas、Cryptohopper 買廣告 |
| `forex trading bot` | 50K–100K | **高** | ⚠️ 可寫比較文，但不主攻 |
| `AI trading agent` | 10K–50K | **高（上升中）** | ⚠️ 次要目標 |
| `MCP trading` / `MCP server trading` | 5K–20K | **中（快速上升）** | **✅ 主攻。LSEG 進場但內容仍少，搶 first-mover** |
| `LLM trading bot` | 1K–5K | **低中** | **✅ 主攻。技術深度文** |
| `trading memory` | 1K–5K | **低** | **✅ 獨佔 niche，持續強化** |
| `AI trading agent memory` | <500 | **極低** | **✅ 定義這個 category** |
| `trade pattern discovery` | <500 | **極低** | ✅ 配合 Evolution Engine demo |

### 5.2 推薦內容策略

| 內容 | 目標關鍵字 | 難度 | 優先級 |
|------|-----------|------|--------|
| GitHub README 優化（hook + 比較表） | `MCP trading memory` | N/A | P0 |
| "MCP Servers for Trading: The Complete Guide" | `MCP server trading` | 中 | P1 |
| "Building Stateful Trading Agents with LLMs" | `LLM trading agent` | 低 | P1 |
| "Why Your AI Trading Agent Needs Memory" (existing) | `AI trading agent memory` | 極低 | 已有 |
| "Trade Pattern Discovery with AI Reflection" | `trade pattern discovery` | 極低 | P2 |
| "Open Source Trading Memory: TradeMemory vs Building Your Own" | `trading memory open source` | 極低 | P2 |

### 5.3 SEO 戰術

- **不跟 listicle 打**。"X Best AI Trading Bots 2026" 被 StockBrokers.com、Koinly、CoinLedger 壟斷
- **走技術深度路線**。dev.to 系列文已有排名（"Why Your AI Trading Agent Needs Memory"）
- **搶「MCP trading」定義權**。LSEG 進場代表機構認可，但教學內容仍少
- **「trading memory」是獨佔詞**。Google 搜尋第一頁就是 TradeMemory。持續寫內容強化

---

## 6. 定價策略建議

### 6.1 市場定價參考

| 產品類型 | 價格區間 | 代表 |
|----------|----------|------|
| 基礎 trading bot | $5-30/mo | WunderTrading, Coinrule |
| 中階 AI 交易 | $50-70/mo | 3Commas ($50), Cryptohopper ($69) |
| 進階 AI 掃描 | $100-200/mo | TrendSpider ($107), Composer ($60) |
| 機構級工具 | $200-750/mo | 3Commas Enterprise ($749) |

隱藏成本（用戶通常忽略）：VPS $10-100/mo、數據源 $20-50/mo、執行橋接 $40-100/mo。

### 6.2 建議定價結構

| Tier | 價格 | 目標用戶 | 功能 |
|------|------|----------|------|
| **Community** | **Free (MIT)** | 個人開發者、學生 | 15 MCP tools, SQLite, 本地使用, 完整 OWM |
| **Pro** | **$29-49/mo** | Indie trader, 小團隊 | Cloud hosted, multi-agent sync, 進階 reflection, 優先支持 |
| **Team** | **$99-199/mo** | Trading desk, prop firm | 團隊 dashboard, shared memory, API, SLA |
| **Enterprise** | **Custom ($500+/mo)** | 機構、對沖基金 | On-prem 部署, 客製整合, 專屬支持 |

### 6.3 定價原則

1. **Free tier 要強**。開源是 moat 不是 cost center。所有 MCP tools 免費。靠 GitHub stars 和 community 長大。
2. **不對標 crypto bot**。TradeMemory 是 developer infrastructure，對標 QuantConnect 不是 3Commas。
3. **不做 performance fee**。TradeMemory 不執行交易，收績效費不合理。
4. **Team/Enterprise 是真正的 revenue**。機構願意付 $500+/mo 的 infra fee。
5. **Crypto 先行收費**。Crypto 用戶付費意願高、決策快、但 churn 也快。Forex 用戶轉換慢但 LTV 高。

### 6.4 收入模式比較

| 模式 | 適合度 | 原因 |
|------|--------|------|
| **Freemium + Premium**（推薦） | ✅ 最適合 | 開源 moat + 低轉換門檻 + 開發者友好 |
| Subscription | ✅ 輔助 | Pro/Team tier 用月費 |
| Performance Fee | ❌ 不適合 | TradeMemory 不執行交易 |
| Token Model | ❌ 不適合 | 監管風險高、分散注意力 |
| Usage-Based | ⚠️ 可考慮 | 按 API call 計費，但初期太複雜 |

---

## 7. TradeMemory 差異化定位建議

### 7.1 護城河總覽

| 差異化維度 | TradeMemory | 全部競品 |
|-----------|:-:|:-:|
| Trading Memory as a Service (MaaS) | ✅ | ❌ |
| Forex/XAUUSD 支持 | ✅ | 僅 nautilus_trader（非 MCP） |
| Live broker 連接 (MT5) | ✅ | 0 個開源 AI 框架有 |
| 5-type 認知記憶 | ✅ | 最多 3 層 (FinMem, dead) |
| Outcome-weighted recall | ✅ | ❌ |
| LLM-powered evolution | ✅ | ❌ |
| MCP protocol native | ✅ | 僅 AgenticTrading 部分支持 |

### 7.2 建議定位語

**不要說**：「另一個 AI trading bot」
**要說**：「讓你的交易 agent 從每筆交易中學習的記憶層」

**核心訊息框架**：

| 受眾 | 訊息 |
|------|------|
| **開發者** | "The memory layer your trading agent is missing. 15 MCP tools, 5-type cognitive memory, open source." |
| **Quant trader** | "Stop losing the lessons from past trades. TradeMemory turns trade history into actionable patterns." |
| **MQL5 EA 開發者** | "Your EA forgets every trade. TradeMemory doesn't. Persistent memory for MetaTrader 5." |

### 7.3 競爭定位矩陣

```
               交易執行    市場數據    記憶/學習    量化/回測
Alpaca         ████████    ████████    ░░░░░░░░    ░░░░░░░░
MetaTrader MCP ████████    ████████    ░░░░░░░░    ░░░░░░░░
QuantConnect   ░░░░░░░░    ████████    ░░░░░░░░    ████████
System R AI    ░░░░░░░░    ░░░░░░░░    ░░░░░░░░    ████████
Composer       ████████    ████████    ░░░░░░░░    ████████
TradeMemory    ░░░░░░░░    ░░░░░░░░    ████████    ████████
```

### 7.4 戰略建議

1. **強化 metatrader-mcp-server 互補**。他做執行、我做記憶，互補而非競爭。
2. **接下 FinMem 的學術關鍵字**。FinMem 已死 3 年，TradeMemory 繼承「trading memory」學術定位。
3. **擴展到 crypto**。Evolution Engine 已支持 Binance，可攻 Walbi/Stoic 做不到的「從交易學習」市場。
4. **定位為 infrastructure 不是 end-user bot**。賣給 building trading agents 的開發者，不是散戶。

---

## 8. README 重寫方向建議

### 8.1 現狀問題

當前 hook：*"MCP server that gives AI trading agents persistent, outcome-weighted memory"*

- 功能描述精準，但缺乏吸引力
- 沒有 hook 感，不會讓人停下來看

### 8.2 競品 Hook 分析

| 專案 | Hook | Stars | 效果 |
|------|------|-------|------|
| ai-hedge-fund | "An AI Hedge Fund Team" | 49K | 簡短有力 |
| AI-Trader | "Can AI Beat the Market?" | 11.8K | **問句式最有吸引力** |
| MarketSenseAI | "Can Large Language Models Beat Wall Street?" | N/A | 同樣問句式 |
| freqtrade | "Free and open source crypto trading bot" | 47.7K | 直接功能明確 |

### 8.3 建議 Hook 選項

| 風格 | Hook |
|------|------|
| **對比式（推薦）** | "Trading bots forget every trade. TradeMemory doesn't." |
| 問句式 | "What if your trading bot remembered every trade — and actually learned from them?" |
| 數據式 | "From raw trades to pattern discovery — the memory layer your trading agent is missing." |

### 8.4 README 結構建議

```
1. Hook（一句話）
2. 3 個 feature badge（15 MCP Tools | 5-Type Memory | 1055 Tests）
3. "The Problem" — 30 秒說明為什麼需要 trading memory
4. "How It Works" — L1 → L2 → L3 pipeline 圖
5. Quick Start（pip install + 3 行 code）
6. Comparison Table（vs FinMem, vs no-memory）
7. Architecture（簡潔圖）
8. MCP Tools List（摺疊）
9. Demo GIF / Screenshot
10. Links（docs, PyPI, Discord）
```

### 8.5 不要做的事

- ❌ 不要用過多 emoji
- ❌ 不要承諾還沒實作的功能
- ❌ 不要用行銷語調（保持開發者風格）
- ❌ 不要放模擬數據當真實數據

---

## 9. 推廣策略

### 9.1 短期（30 天）— Distribution Sprint

| Week | 動作 | 預期效果 | 成本 |
|------|------|----------|------|
| **W1** | PyPI 推 v0.5.0 | 下載量增長（1055 tests 說服力） | $0 |
| **W1** | 上架 Smithery.ai | 曝光 40 個 trading server 用戶 | $0 |
| **W1** | 上架 mcp.so | 曝光 141 個 finance server 用戶 | $0 |
| **W1** | 提 PR 到 awesome-mcp-servers | Finance & Fintech section 入列 | $0 |
| **W1** | 更新 Glama.ai listing | v0.5.0 + 1055 tests | $0 |
| **W2** | README 重寫（新 hook + 比較表 + quick start） | GitHub 轉換率提升 | $0 |
| **W2** | dev.to: "MCP Servers for Trading: Complete Guide" | 搶 "MCP trading" SEO | $0 |
| **W3** | Hummingbot Discord 介紹 TradeMemory | 最匹配的開源 trading 社群 | $0 |
| **W3** | r/algotrading 發帖（Show HN 風格） | 觸及 overfitting/memory 痛點用戶 | $0 |
| **W4** | 與 metatrader-mcp-server 作者（ariadng）聯繫合作 | 互補整合：執行 + 記憶 | $0 |

**30 天目標**：
- PyPI 月下載 515 → 1,000+
- GitHub stars 91 → 150+
- 5 個 MCP registry 全上架

### 9.2 中期（90 天）— Category Definition

| Month | 動作 | 預期效果 |
|-------|------|----------|
| **M1** | 完成短期所有動作 | 基礎分發到位 |
| **M2** | Product Hunt launch（首個 MCP + trading memory） | 品牌定義性事件 |
| **M2** | dev.to/Medium 系列文（3 篇）：LLM trading, pattern discovery, evolution | SEO 佔位 |
| **M2** | 與 QuantConnect MCP 探索合作（回測 + 記憶） | 擴大 MCP 生態位置 |
| **M3** | Pro tier beta launch（$29/mo, cloud hosted） | 第一筆 revenue |
| **M3** | Evolution Engine demo video（Binance live data） | 展示 crypto 能力 |
| **M3** | Crypto 社群推廣（Discord/Telegram, aixbt 生態） | 開拓 crypto 用戶 |

**90 天目標**：
- PyPI 月下載 > 2,000
- GitHub stars > 300
- Pro tier 10+ beta users
- "trading memory" Google 搜尋第一頁完全壟斷

### 9.3 推廣原則

1. **零成本優先**。所有 MCP registry 上架都是免費的。
2. **技術內容 > 行銷**。走 dev.to 技術深度路線，不跟 listicle 打。
3. **社群 > 廣告**。Hummingbot Discord、r/algotrading、MQL5 Forum 是天然用戶池。
4. **互補 > 競爭**。metatrader-mcp-server 做執行、QuantConnect 做回測、TradeMemory 做記憶。
5. **定義 category**。不是「另一個 trading bot」，是「trading memory」這個全新類別的定義者。
6. **不說 "AI will trade for you"**。說 "AI helps you learn from your trades"。

---

## Appendix: Sources

### GitHub Repositories
- [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (49.1K stars)
- [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) (47.7K stars)
- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) (32.3K stars)
- [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) (21.2K stars)
- [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) (11.8K stars)
- [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) (6.4K stars)
- [pipiku915/FinMem-LLM-StockTrading](https://github.com/pipiku915/FinMem-LLM-StockTrading) (858 stars)
- [Open-Finance-Lab/AgenticTrading](https://github.com/Open-Finance-Lab/AgenticTrading) (104 stars)
- [DVampire/FinAgent](https://github.com/DVampire/FinAgent) (69 stars)

### Academic Papers
- [FinMem (arXiv 2311.13743)](https://arxiv.org/abs/2311.13743) — ICLR 2024, AAAI 2024
- [FinAgent (arXiv 2402.18485)](https://arxiv.org/abs/2402.18485) — KDD 2024
- [FinRobot (arXiv 2405.14767)](https://arxiv.org/abs/2405.14767)
- [MarketSenseAI (arXiv 2401.03737)](https://arxiv.org/abs/2401.03737)

### MCP Registries
- [Smithery.ai](https://smithery.ai/explore)
- [Glama.ai](https://glama.ai/mcp/servers/categories/finance)
- [mcp.so](https://mcp.so)
- [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)
- [OpenClaw](https://openclaw.com)

### Market Research & Community
- [LSEG: MCP Next Frontier for Financial Markets](https://www.lseg.com/en/insights/mcp-the-next-frontier-for-financial-markets)
- [CFTC: AI Won't Turn Trading Bots into Money Machines](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/AITradingBots.html)
- [TRM Labs: AI Crypto Scams +456%](https://www.helpnetsecurity.com/2025/09/18/ai-crypto-scams-dangerous/)
- [DEV.to: Why Your AI Trading Agent Needs a Memory](https://dev.to/mnemox/why-your-ai-trading-agent-needs-a-memory-and-how-we-built-one-kjo)
- [Alpaca MCP Server](https://alpaca.markets/mcp-server)

### Pricing References
- [3Commas](https://3commas.io/) — $29.99-$749/mo
- [Cryptohopper](https://www.cryptohopper.com/) — $15-$160/mo
- [TrendSpider](https://trendspider.com/) — $107-$197/mo
- [Composer](https://www.composer.trade/) — $60-$1,080/mo

---

*Generated by Mnemox AI Research — 2026-03-16. All data verified at time of writing.*
