<!-- mcp-name: io.github.mnemox-ai/tradememory-protocol -->

<p align="center">
  <img src="../assets/header-zh.png" alt="TradeMemory Protocol" width="600">
</p>

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/tradememory-protocol?style=flat-square&color=blue)](https://pypi.org/project/tradememory-protocol/)
[![Tests](https://img.shields.io/badge/tests-1%2C233_passed-brightgreen?style=flat-square)](https://github.com/mnemox-ai/tradememory-protocol/actions)
[![MCP Tools](https://img.shields.io/badge/MCP_tools-17-blueviolet?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
[![Smithery](https://img.shields.io/badge/Smithery-listed-orange?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)

[Tutorial](TUTORIAL.md) | [API Reference](API.md) | [OWM Framework](OWM_FRAMEWORK.md) | [English](../README.md)

</div>

---

TradeMemory Protocol 讓 AI 交易 agent 擁有兩項它們缺乏的能力：合規等級的決策審計軌跡，以及從結果中學習的持久記憶。

每個 AI 交易工具都會執行交易。但沒有一個記錄**為什麼**。TradeMemory 捕捉完整的決策上下文——什麼條件觸發了訊號、哪些過濾器通過或阻擋、當時的市場指標、風險狀態、以及執行細節。每筆紀錄在建立時就計算 SHA-256 雜湊以偵測竄改。而且跨 session 後，你的 agent 記得什麼有效、發現規律、自動調整策略——透過受 ACT-R 認知科學啟發的三層架構實現。

**什麼時候用：** 你正在用 MT5、Binance、Alpaca 或任何平台開發 AI 交易 agent，而你需要它 (1) 證明每個決策的原因，以及 (2) 跨 session 記住什麼有效。

## 運作方式

1. **審計** — 每個決策都記錄完整上下文：評估的條件、檢查的過濾器、當時的指標、風險狀態。建立時即計算 SHA-256 雜湊以偵測竄改。
2. **儲存** — Agent 透過 MCP 工具記錄每筆交易的完整上下文（策略、信心、市場環境）
3. **回憶** — 下一次交易前，Agent 取回相似歷史交易，依結果加權排序（Outcome-Weighted Memory）
4. **進化** — Evolution Engine 跨交易發現規律，產生新策略假設，用 Deflated Sharpe Ratio 驗證

## TradeMemory vs 其他方案

| | TradeMemory | 原生 Mem0/Qdrant | LangChain Memory | 自建 SQLite |
|---|---|---|---|---|
| **決策審計軌跡** | ✅ SHA-256 + TDR | ❌ 無 | ❌ 無 | ❌ 自己寫 |
| **交易專用 schema** | ✅ L1→L2→L3 pipeline | ❌ 通用向量 | ❌ 對話導向 | ❌ 全部自己寫 |
| **結果加權** | ✅ Kelly + ACT-R | ❌ 只有 cosine | ❌ 只有時間衰減 | ❌ 手動實作 |
| **策略進化** | ✅ 內建引擎 | ❌ 不包含 | ❌ 不包含 | ❌ 不包含 |
| **MCP 原生** | ✅ 17 個工具 | ❌ 需自己包裝 | ❌ 需自己包裝 | ❌ 需自己包裝 |
| **統計驗證** | ✅ DSR + walk-forward | ❌ 無 | ❌ 無 | ❌ 無 |

## 最新消息

- [2026-03] **Decision Audit Trail** — Trading Decision Records (TDR)，SHA-256 竄改偵測，4 個審計 REST 端點，2 個 MCP 工具，JSONL 決策上下文接入
- [2026-03] **Onboarding CLI** — `tradememory setup` 引導精靈，`doctor` 健康檢查，8 平台設定生成器
- [2026-03] **v0.5.0** — Evolution Engine + OWM 5 種記憶類型。[Release Notes](https://github.com/mnemox-ai/tradememory-protocol/releases/tag/v0.5.0)
- [2026-03] **統計驗證** — 策略 E 通過 P100% 隨機基線，Walk-forward Sharpe 3.24
- [2026-02] **v0.4.0** — OWM 框架、15 個 MCP 工具、Smithery + Glama 上架

## 架構

<p align="center">
  <img src="../assets/schema-zh.png" alt="架構" width="900">
</p>

## 三層記憶

<p align="center">
  <img src="../assets/memory-pipeline-zh.png" alt="L1 L2 L3 記憶流程" width="900">
</p>

## Decision Audit Trail

你的 agent 做的每一個交易決策——包括決定**不交易**——都會被記錄為 Trading Decision Record (TDR)。每筆紀錄捕捉完整的推理鏈，並在建立時計算 SHA-256 雜湊以偵測竄改。

以下是來自 XAUUSD 交易系統的真實決策事件。AI agent 偵測到 SHORT 突破訊號，但 `sell_allowed` 過濾器阻擋了執行：

```json
{
  "ts": "2026-03-26 07:55:00",
  "strategy": "VolBreakout",
  "decision": "FILTERED",
  "signal_triggered": true,
  "signal_direction": "SHORT",
  "conditions_json": {
    "conditions": [
      {"name": "breakout_high", "passed": false, "current_value": 4462.58, "threshold": 4569.75},
      {"name": "breakout_low", "passed": true, "current_value": 4462.58, "threshold": 4463.11}
    ]
  },
  "filters_json": {
    "filters": [
      {"name": "spread_gate", "passed": true, "current_value": 12.0},
      {"name": "sell_allowed", "passed": false, "blocked": true},
      {"name": "account_risk", "passed": true},
      {"name": "regime_gate", "passed": true}
    ]
  },
  "indicators_json": {
    "atr_d1": 171.16, "atr_m5": 8.53,
    "asia_high": 4544.08, "asia_low": 4488.78, "asia_range": 55.30
  },
  "regime": "TRENDING",
  "consec_losses": 0,
  "cooldown_active": false,
  "risk_daily_pct": 0.0
}
```

監管者或風控經理可以讀這筆紀錄並立即理解：agent 看到了有效的突破，但政策阻擋了 SHORT 方向。不用猜測，沒有黑箱。

### Audit API

```bash
# 取得完整決策紀錄
GET /audit/decision-record/{trade_id}

# 驗證紀錄是否被竄改
GET /audit/verify/{trade_id}
# → {"verified": true, "stored_hash": "a3f8c9...", "computed_hash": "a3f8c9...", "match": true}

# 批次匯出供監管提交
GET /audit/export?strategy=VolBreakout&start=2026-03-01&end=2026-03-31&format=jsonl
```

## 法規對齊

| 法規 | 要求 | TradeMemory 覆蓋範圍 |
|------|------|---------------------|
| MiFID II 第 17 條 | 記錄每個演算法交易決策因素 | 完整決策鏈：條件、過濾器、指標、執行 |
| EU AI Act 第 14 條 | 高風險 AI 系統的人類監督 | 可解釋推理 + 每個決策的記憶上下文 |
| EU AI Act 日誌記錄 | 系統性記錄每個 AI 行動及決策路徑 | 自動逐決策 TDR，結構化 JSON |
| ESMA 2026 Briefing | 演算法必須可區分、可測試、可識別 | 每筆紀錄含 agent_id + model_version + strategy |

## 快速開始

```bash
pip install tradememory-protocol
```

**試試互動 Demo**（不需要 API key）：

```bash
tradememory demo
```

加到 Claude Desktop 設定檔 (`claude_desktop_config.json`)：

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

然後對 Claude 說：*「記錄我在 71,000 做多 BTCUSDT — 動量突破，高信心。」*

<details>
<summary>Claude Code / Cursor / Docker</summary>

```bash
# Claude Code
claude mcp add tradememory -- uvx tradememory-protocol

# 從原始碼安裝
git clone https://github.com/mnemox-ai/tradememory-protocol.git
cd tradememory-protocol && pip install -e . && python -m tradememory

# Docker
docker compose up -d
```

</details>

## 設定與組態

首次引導設定：

```bash
tradememory setup
```

流程包括：
1. **條款接受** — 交易免責聲明與資料儲存政策
2. **平台偵測** — 自動偵測 Claude Desktop、Claude Code、Cursor、Windsurf、Cline
3. **設定生成** — 印出你的平台專屬 JSON 設定片段
4. **健康檢查** — 驗證資料庫、MCP 工具、核心功能

### 平台設定

為任何支援的平台生成設定：

```bash
tradememory config              # 互動式選單
tradememory config claude_code  # 直接：透過 CLI 自動安裝
tradememory config cursor       # 印出 .cursor/mcp.json 片段
tradememory config windsurf     # 印出 Windsurf 設定
tradememory config raw_json     # 通用 MCP JSON
```

支援：Claude Desktop · Claude Code · Cursor · Windsurf · Cline · Smithery · Docker

### 健康檢查

```bash
tradememory doctor        # 核心檢查（~3 秒）
tradememory doctor --full # + REST API、MT5、Anthropic API
```

## MCP 工具（17 個）

| 類別 | 工具 |
|------|------|
| **核心記憶** | `store_trade_memory` · `recall_similar_trades` · `get_strategy_performance` · `get_trade_reflection` |
| **OWM 認知** | `remember_trade` · `recall_memories` · `get_behavioral_analysis` · `get_agent_state` · `create_trading_plan` · `check_active_plans` |
| **Evolution** | `evolution_fetch_market_data` · `evolution_discover_patterns` · `evolution_run_backtest` · `evolution_evolve_strategy` · `evolution_get_log` |
| **審計** | `export_audit_trail` · `verify_audit_hash` |

<details>
<summary>REST API（35+ 端點）</summary>

交易記錄、結果登記、歷史查詢、反思、風險約束、MT5 同步、OWM、進化引擎、決策審計軌跡、完整性驗證。

完整參考：[docs/API.md](API.md)

</details>

## OWM — 結果加權記憶

<p align="center">
  <img src="../assets/owm-factors-zh.png" alt="OWM 五因子" width="900">
</p>

> 完整理論基礎：[OWM Framework](OWM_FRAMEWORK.md)

## Evolution Engine

<p align="center">
  <img src="../assets/evolution-zh.png" alt="Evolution Engine" width="900">
</p>

> 方法論與數據：[Research Log](RESEARCH_LOG.md)

## 應用場景

**加密貨幣** — 從 Binance 匯入 BTC/ETH 交易。Evolution Engine 能發現你永遠找不到的時間規律，市場環境改變時自動調適。

**外匯 + MT5** — 自動同步 MetaTrader 5 的每筆平倉交易。跨 session 持久記憶讓你的 EA 記住亞盤突破只有 10% 勝率 — 然後不再下單。

**開發者** — 用 17 個 MCP 工具 + 35 個 REST 端點建構有記憶的交易 agent。你的 agent 每次啟動都知道自己的信心水準、進行中的計畫、以及哪些策略正在賺錢。

## 安全

- **TradeMemory 絕不碰 API 金鑰。** 它不執行交易、不移動資金、不存取錢包。
- **只讀取和記錄。** Agent 在做出決策後呼叫 TradeMemory，傳入上下文。TradeMemory 儲存它。
- **無外部網路呼叫。** Server 在本地運行。不會將資料傳送給第三方。
- **SHA-256 竄改偵測。** 每筆紀錄在建立時就計算雜湊。可隨時透過 `/audit/verify` 驗證完整性。
- **1,233 測試通過。** 完整測試套件與 CI。

## 文件

| 文件 | 說明 |
|------|------|
| [Architecture](ARCHITECTURE.md) | 系統設計與分層架構 |
| [OWM 框架](OWM_FRAMEWORK.md) | 完整理論基礎 |
| [Tutorial](TUTORIAL.md) | 安裝 → 第一筆交易 → 記憶回憶 |
| [API 參考](API.md) | 所有 REST 端點 |
| [MT5 設定](MT5_SYNC_SETUP.md) | MetaTrader 5 整合 |
| [研究日誌](RESEARCH_LOG.md) | 11 項進化實驗 |
| [Roadmap](ROADMAP.md) | 開發路線圖 |
| [English](../README.md) | 英文版 |

## 貢獻

詳見 [Contributing Guide](../.github/CONTRIBUTING.md) · [Security Policy](../.github/SECURITY.md)

<a href="https://star-history.com/#mnemox-ai/tradememory-protocol&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=mnemox-ai/tradememory-protocol&type=Date&theme=dark" />
   <img alt="Star History" src="https://api.star-history.com/svg?repos=mnemox-ai/tradememory-protocol&type=Date" width="600" />
 </picture>
</a>

---

MIT — 詳見 [LICENSE](../LICENSE)。僅供教育和研究用途。不構成投資建議。

<div align="center">由 <a href="https://mnemox.ai">Mnemox</a> 打造</div>
