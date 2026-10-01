<!-- mcp-name: io.github.mnemox-ai/tradememory-protocol -->

<p align="center">
  <img src="../assets/header-zh.png" alt="TradeMemory Protocol" width="600">
</p>

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/tradememory-protocol?style=flat-square&color=blue)](https://pypi.org/project/tradememory-protocol/)
[![Tests](https://img.shields.io/github/actions/workflow/status/mnemox-ai/tradememory-protocol/ci.yml?branch=master&style=flat-square&label=tests)](https://github.com/mnemox-ai/tradememory-protocol/actions/workflows/ci.yml)
[![MCP Tools](https://img.shields.io/badge/MCP_tools-20-blueviolet?style=flat-square)](https://smithery.ai/server/mnemox-ai/tradememory-protocol)
[![Smithery](https://img.shields.io/badge/Smithery-listed-orange?style=flat-square)](https://smithery.ai/server/mnemox-ai/tradememory-protocol)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)

[快速開始](GETTING_STARTED.md) | [應用場景](USE_CASES.md) | [API 參考](API.md) | [OWM 框架](OWM_FRAMEWORK.md) | [限制聲明](../LIMITATIONS.md) | [English](../README.md)

</div>

---

> **專案狀態（2026 年 10 月）：** 記憶層為**維護模式**：bug 與安全性回報仍會處理，不再規劃新的記憶功能。目前主動開發的是下方的券商 proxy。付費服務見[交易紀錄統計分析](#交易紀錄統計分析)。

**你的交易 AI 有失憶症。而券商已經把門打開了。**

它每個 session 都在重複同樣的錯誤。它無法解釋為什麼下單。context window 結束後它忘了一切。2026 年 Robinhood、Alpaca、Interactive Brokers 相繼對交易 agent 開放 MCP 端點，Robinhood 的支援頁面寫明：agent 做出的決策造成的損失，Robinhood 不負責。每家券商只給你它自己的活動紀錄。沒有一家給你的 agent 記憶，沒有一家在下單前放一道由你掌控的煞車，這些紀錄也不會跟著你到下一家券商或下一個框架。

AI 交易堆疊缺少一層。每個 MCP server 都處理執行——下單、取得價格、讀取圖表。**沒有一個處理記憶。**

你的 agent 可以買 100 股 AAPL，但無法回答：*「上次我在這個條件下買 AAPL，發生了什麼？」*

**TradeMemory 就是那個記憶層。** 一個 `pip install`，你的 AI agent 就能記住每一筆交易、每一個結果、每一個錯誤——搭配 SHA-256 可驗竄改的審計軌跡。

一位獨立交易者用它在每次開倉前跑「交易前檢查清單」；另有第一方在 MT5 帳戶上記錄被阻擋與已執行的訊號。哪個是哪個見 USE_CASES.md。

## 功能概覽

- **交易前：** 詢問記憶——上次在這個市場條件下發生了什麼？最後結果如何？
- **交易後：** 一次呼叫記錄一切——五個記憶層自動更新
- **安全護欄：** 信心追蹤、回撤告警、連敗偵測——系統告訴你什麼時候該停下來

相容任何市場（股票、外匯、加密貨幣、期貨）、任何券商、任何 AI 平台。TradeMemory 不執行交易也不碰你的資金——它只負責記錄和回憶。

## 在券商前面裝一道煞車（預覽）

`proxy` extra 讓 TradeMemory 跑在你的 agent 和券商 MCP server 之間。所有工具原樣轉送，只有下單工具會先交給 [Mnemox Control](https://github.com/mnemox-ai/mnemox-control) 用你自己的政策評估，通過才送到券商。每一次評估，不論放行或拒絕，都寫進稽核鏈；記憶由通過的單自動填滿。你原本的 agent 照常運作，只改 MCP 設定裡的一行。

```bash
# 下一版發布前先從分支安裝：
pip install "tradememory-protocol[proxy] @ git+https://github.com/mnemox-ai/tradememory-protocol@master"   # Python 3.12+
tradememory proxy init --account-id <你的 Alpaca 帳號 id> --symbols AAPL,MSFT
tradememory proxy doctor --env-file ~/.secrets/alpaca-paper.env   # 核對上游工具名稱與帳號 id
tradememory proxy config                                           # 印出要換掉的那一行 MCP 設定
```

預設拒絕：清單外的標的、超過單筆或總部位上限的單、沒帶 bracket 停損的進場、觸及當日虧損或回撤上限之後的任何新單、以及你下過 `tradememory proxy halt FULL_HALT` 之後的一切。永遠不擋：平倉。達到 `approval_notional` 的單會等 `tradememory proxy approve <intent_id>`，agent 用同一個 `client_order_id` 重送，proxy 只轉送一次。任何評估不了的情況，例如報價斷線、不認得的標的、政策 v0 不涵蓋的單型，一律拒絕而不是放行。

目前狀態：已對一個有狀態的 Alpaca MCP 假上游跑完端到端測試（`tests/proxy/`），並在 2026 年 10 月 1 日對真實的 Alpaca paper 帳戶跑過一次：三筆拒絕（清單外標的、沒帶停損、超過單筆上限）、一筆放行的一股 bracket 單真的送到券商、一筆用同一個 `client_order_id` 重送的單由紀錄回覆、沒有產生第二張單。假上游的參數名稱與回傳形狀已依那次真實執行修正；`doctor` 會對你的帳戶再核對一次。選擇權、改單、stop-limit 與 trailing 單是拒絕不是評估。券商金鑰只交給 proxy 啟動的券商程序，proxy 本身不保存。

附真實輸出的完整步驟：[docs/recipes/alpaca-brake.md](recipes/alpaca-brake.md)。**你的 agent 已經在對券商下單，想把這道煞車裝在前面？** [開一個 brake-integration issue](https://github.com/mnemox-ai/tradememory-protocol/issues/new?template=brake_integration.yml) 或 [約 30 分鐘](https://calendly.com/johnson90207/30min)。前十個真實環境我們親手幫忙接、不收費，之後要做什麼由他們決定。

## 看看介面長什麼樣

**[tradememory-dashboard.onrender.com](https://tradememory-dashboard.onrender.com)** 是跑在示範資料集上的儀表板，不用安裝任何東西。

這是**介面預覽，不是績效紀錄**：裡面的交易是合成的，畫面上每個數字都有標註。想看記憶層在終端機裡實際做什麼，跑 `pip install tradememory-protocol && tradememory demo --fast`，它會重播 30 筆交易，並展示從中導出的回憶與參數調整。

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
| **核心價值** | 紀律系統——每個決策前先查記憶 | 記錄訊號被阻擋的原因，不只是執行結果 | SHA-256 可驗竄改紀錄供監管提交 |
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
<summary>全部 20 個 MCP 工具 + REST API</summary>

| 類別 | 工具 |
|------|------|
| **核心記憶** | `get_strategy_performance` · `get_trade_reflection` |
| **OWM 認知** | `remember_trade` · `recall_memories` · `get_behavioral_analysis` · `get_agent_state` · `create_trading_plan` · `check_active_plans` |
| **風險與治理** | `check_trade_legitimacy` · `validate_strategy` · `compute_dqs` |
| **Evolution** | `evolution_fetch_market_data` · `evolution_discover_patterns` · `evolution_run_backtest` · `evolution_evolve_strategy` · `evolution_get_log` |
| **審計** | `export_audit_trail` · `verify_audit_hash` · `verify_audit_chain` · `get_daily_root` |

**REST API：** 35+ 端點，涵蓋交易記錄、反思、風險、MT5 同步、OWM、Evolution Engine 和審計。[完整參考 →](API.md)

</details>

## 交易紀錄統計分析

TradeMemory 本身免費、自行架設。維護者提供的付費服務是**針對你自己交易紀錄的統計分析**：匯出 MT4/MT5 歷史紀錄，取得一份描述性統計報告（虧損集中在哪幾筆、虧損後部位如何變化、強制平倉結構、每筆實際承擔的風險），加上一次語音講解。

只描述已發生的交易：不提供進出場訊號、不提供投資建議、不做任何獲利承諾。檔案交付後即刪除。

[dev@mnemox.ai](mailto:dev@mnemox.ai) | [預約通話](https://calendly.com/johnson90207/30min)

## Enterprise 與合規

你的 agent 做的每一個交易決策——包括決定**不交易**——都會被記錄為 Trading Decision Record (TDR)，並在建立時計算 SHA-256 雜湊以進行竄改偵測。

這些義務約束的是投資公司，不是散戶。EU AI Act 附件三的高風險日誌義務已延後至 2027 年 12 月 2 日；ESMA 2026 年 2 月的演算法交易監理簡報寫明，AI 演算法交易目前不在高風險範圍內。下表只說明當這些法規適用於你時，TradeMemory 的哪些功能對得上，不是合規宣稱。

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
- **Local-first。** 唯一的對外呼叫是每日稽核 root 的 RFC 3161 信任時間戳——送出的只是 32 bytes 的雜湊，不含任何交易資料（預設開啟，可用 `TRADEMEMORY_TSA=off` 關閉）。其餘資料不離開你的機器。
- **SHA-256 竄改偵測。** 每筆紀錄在建立時就計算雜湊。可隨時驗證完整性。
- **1,400+ 測試通過。** 完整測試套件與 CI。

## 研究現況

TradeMemory 的 OWM 框架基於認知科學（Tulving 1972）和強化學習（Schaul et al. 2015）。目前狀態：

- **OWM 五因子評分：** 已實作，已測試（1,400+ tests）
- **統計驗證：** DSR、MBL 已實作（Bailey-de Prado 2014）
- **審計軌跡：** SHA-256 可驗竄改 TDR
- **進化引擎：** 研究階段（策略生成可運作，統計門檻通過率仍在優化中）
- **混合召回：** OWM-only 模式啟用中，embedding 設定後可啟用向量融合
- **實證驗證：** 進行中（n=14 筆交易，目標 n>=100 以達統計顯著性；n=14 時信賴區間過寬，不足以下任何結論，見 validation/final_verdict.md）

## 文件

| 文件 | 說明 |
|------|------|
| [快速開始](GETTING_STARTED.md) | 安裝 → 第一筆交易 → 交易前檢查清單 |
| [應用場景](USE_CASES.md) | 3 個使用情境（含第一方與獨立使用者，逐案標註） |
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
