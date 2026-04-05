<!-- mcp-name: io.github.mnemox-ai/tradememory-protocol -->

<p align="center">
  <img src="../assets/header-zh.png" alt="TradeMemory Protocol" width="600">
</p>

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/tradememory-protocol?style=flat-square&color=blue)](https://pypi.org/project/tradememory-protocol/)
[![Tests](https://img.shields.io/badge/tests-1%2C324_passed-brightgreen?style=flat-square)](https://github.com/mnemox-ai/tradememory-protocol/actions)
[![MCP Tools](https://img.shields.io/badge/MCP_tools-19-blueviolet?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
[![Smithery](https://img.shields.io/badge/Smithery-listed-orange?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)

[快速開始](GETTING_STARTED.md) | [應用場景](USE_CASES.md) | [API 參考](API.md) | [OWM 框架](OWM_FRAMEWORK.md) | [English](../README.md)

</div>

---

**你的交易 AI 有失憶症。監管機構開始注意到了。**

它每個 session 都在重複同樣的錯誤。它無法解釋為什麼下單。context window 結束後它忘了一切。與此同時，MiFID II 正在提高演算法決策文件的標準（[第 17 條](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32014L0065)）。EU AI Act 要求系統性記錄 AI 行動（[第 14 條](https://eur-lex.europa.eu/eli/reg/2024/1689)）。你競爭對手的 agent 正在從每筆交易中學習。

AI 交易堆疊缺少一層。每個 MCP server 都處理執行——下單、取得價格、讀取圖表。**沒有一個處理記憶。**

你的 agent 可以買 100 股 AAPL，但無法回答：*「上次我在這個條件下買 AAPL，發生了什麼？」*

**TradeMemory 就是那個記憶層。** 一個 `pip install`，你的 AI agent 就能記住每一筆交易、每一個結果、每一個錯誤——搭配 SHA-256 防竄改的審計軌跡。

已在生產環境中被交易者使用：每次開倉前跑「交易前檢查清單」，以及每日記錄數千個決策的 EA 系統。

## 功能概覽

- **交易前：** 詢問記憶——上次在這個市場條件下發生了什麼？最後結果如何？
- **交易後：** 一次呼叫記錄一切——五個記憶層自動更新
- **安全護欄：** 信心追蹤、回撤告警、連敗偵測——系統告訴你什麼時候該停下來

相容任何市場（股票、外匯、加密貨幣、期貨）、任何券商、任何 AI 平台。TradeMemory 不執行交易也不碰你的資金——它只負責記錄和回憶。

## 快速開始

```bash
pip install tradememory-protocol
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

然後對 Claude 說：*「記錄我在 $195 做多 AAPL——財報超預期、機構買盤湧入、高信心。」*

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

**完整教學：** [快速開始](GETTING_STARTED.md)（交易者軌道 + 開發者軌道）

## 誰在用 TradeMemory

| | 美股交易者 | 外匯 EA 系統 | 合規團隊 |
|---|---|---|---|
| **市場** | 股票（AAPL、TSLA…） | XAUUSD（黃金） | 多資產 |
| **使用方式** | 每次開倉前跑「交易前檢查清單」 | 從 MT5 自動同步 | 完整決策審計軌跡 |
| **核心價值** | 紀律系統——每個決策前先查記憶 | 記錄訊號被阻擋的原因，不只是執行結果 | SHA-256 防竄改紀錄供監管提交 |
| **詳細說明** | [閱讀更多 →](USE_CASES.md#case-1-us-equity-trader--pre-flight-workflow) | [閱讀更多 →](USE_CASES.md#case-2-forex-ea-system--automated-memory-loop) | [閱讀更多 →](USE_CASES.md#case-3-compliance-first-fund--audit-trail) |

## 運作方式

<p align="center">
  <img src="../assets/owm-factors-zh.png" alt="OWM 五因子" width="900">
</p>

1. **回憶** — 交易前，取回依結果品質、上下文相似度、近期性、信心、情緒狀態加權的歷史交易（[OWM 框架](OWM_FRAMEWORK.md)）
2. **記錄** — 交易後，一次呼叫 `remember_trade` 寫入五個記憶層：情節記憶、語義記憶、程序記憶、情感記憶和交易紀錄
3. **反思** — 每日/每週/每月覆盤，偵測行為漂移、策略衰退和交易錯誤
4. **審計** — 每個決策在建立時即計算 SHA-256 雜湊。可隨時匯出供審查或法規提交

### MCP 工具

| 類別 | 工具 | 說明 |
|------|------|------|
| **記憶** | `remember_trade` · `recall_memories` | 以結果加權評分記錄和回憶交易 |
| **狀態** | `get_agent_state` · `get_behavioral_analysis` | 信心、回撤、連勝/連敗、行為模式 |
| **計畫** | `create_trading_plan` · `check_active_plans` | 附條件觸發的前瞻性計畫 |
| **風險** | `check_trade_legitimacy` | 五因子交易前審核（完整 / 縮減 / 跳過） |
| **審計** | `export_audit_trail` · `verify_audit_hash` | SHA-256 竄改偵測 + 批次匯出 |

<details>
<summary>全部 19 個 MCP 工具 + REST API</summary>

| 類別 | 工具 |
|------|------|
| **核心記憶** | `store_trade_memory` · `recall_similar_trades` · `get_strategy_performance` · `get_trade_reflection` |
| **OWM 認知** | `remember_trade` · `recall_memories` · `get_behavioral_analysis` · `get_agent_state` · `create_trading_plan` · `check_active_plans` |
| **風險與治理** | `check_trade_legitimacy` · `validate_strategy` |
| **Evolution** | `evolution_fetch_market_data` · `evolution_discover_patterns` · `evolution_run_backtest` · `evolution_evolve_strategy` · `evolution_get_log` |
| **審計** | `export_audit_trail` · `verify_audit_hash` |

**REST API：** 35+ 端點，涵蓋交易記錄、反思、風險、MT5 同步、OWM、Evolution Engine 和審計。[完整參考 →](API.md)

</details>

## 定價

| | Community | Pro | Enterprise |
|---|---|---|---|
| **價格** | **免費** | **$29/月**（即將推出） | **洽詢我們** |
| MCP 工具 | 19 個工具 | 19 個工具 | 19 個工具 |
| 儲存 | SQLite，自架 | Hosted API | 私有部署 |
| Dashboard | — | Web dashboard | 客製化 dashboard |
| 合規 | 審計軌跡含括 | 審計軌跡含括 | 合規報告 + SLA |
| 支援 | GitHub Issues | 優先支援 | 專屬支援 |
| | [立即開始 →](GETTING_STARTED.md) | *即將推出* | [dev@mnemox.ai](mailto:dev@mnemox.ai) |

### 需要整合協助？

正在建立交易 AI agent，想要經過實戰驗證的記憶架構？

**免費 30 分鐘策略諮詢** — 我們會為你的 agent 規劃記憶需求，設計適合你工作流程的護欄。

[dev@mnemox.ai](mailto:dev@mnemox.ai) | [預約通話](https://calendly.com/mnemox)

> *我們已協助交易者建立交易前檢查清單、串接 MT5/Binance，並為外匯、美股、加密貨幣設計客製化護欄。*

## Enterprise 與合規

你的 agent 做的每一個交易決策——包括決定**不交易**——都會被記錄為 Trading Decision Record (TDR)，並在建立時計算 SHA-256 雜湊以進行竄改偵測。

| 法規 | 要求 | TradeMemory 覆蓋範圍 |
|------|------|---------------------|
| MiFID II 第 17 條 | 記錄每個演算法交易決策因素 | 完整決策鏈：條件、過濾器、指標、執行 |
| EU AI Act 第 14 條 | 高風險 AI 系統的人類監督 | 可解釋推理 + 每個決策的記憶上下文 |
| EU AI Act 日誌記錄 | 系統性記錄每個 AI 行動及決策路徑 | 自動逐決策 TDR，結構化 JSON |

```bash
# 驗證任何紀錄是否被竄改
GET /audit/verify/{trade_id}
# → {"verified": true, "stored_hash": "a3f8c9...", "computed_hash": "a3f8c9..."}

# 批次匯出供監管提交
GET /audit/export?strategy=VolBreakout&start=2026-03-01&format=jsonl
```

**需要為你的基金客製化部署？** → [dev@mnemox.ai](mailto:dev@mnemox.ai)

## 安全

- **絕不碰 API 金鑰。** TradeMemory 不執行交易、不移動資金、不存取錢包。
- **只讀取和記錄。** 你的 agent 把決策上下文傳給 TradeMemory。它儲存它。就這樣。
- **無外部網路呼叫。** Server 在本地運行。不會將資料傳送給第三方。
- **SHA-256 竄改偵測。** 每筆紀錄在建立時就計算雜湊。可隨時驗證完整性。
- **1,324 測試通過。** 完整測試套件與 CI。

## 文件

| 文件 | 說明 |
|------|------|
| [快速開始](GETTING_STARTED.md) | 安裝 → 第一筆交易 → 交易前檢查清單 |
| [應用場景](USE_CASES.md) | 3 個真實生產環境案例 |
| [API 參考](API.md) | 所有 REST 端點 |
| [OWM 框架](OWM_FRAMEWORK.md) | Outcome-Weighted Memory 理論基礎 |
| [架構](ARCHITECTURE.md) | 系統設計與分層架構 |
| [Tutorial](TUTORIAL.md) | 詳細操作教學 |
| [MT5 設定](MT5_SYNC_SETUP.md) | MetaTrader 5 整合 |
| [研究日誌](RESEARCH_LOG.md) | Evolution 實驗與數據 |
| [Failure Taxonomy](trading-ai-failure-taxonomy.md) | 11 種交易 AI 失敗模式 |
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
