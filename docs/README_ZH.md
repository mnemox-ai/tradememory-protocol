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

**TradeMemory 記得每一筆付過的代價。** 它是開源、資料留在你電腦上的 AI 交易記憶與煞車：把你的成交紀錄同步進來，找出你自己的歷史在哪裡虧錢，在下一張單之前把那些虧損擺到 agent 面前，也可以在單送到券商之前，擋下違反你自訂規則的那一張。

券商已經讓 AI agent 透過 MCP 下單，護欄各不相同：Webull 和 tastytrade 設了單筆或購買力上限，Interactive Brokers 只讓 agent 草擬、由你送出，Robinhood 和 Public 對外部 agent 沒有你能設的上限（[StockBrokers，2026-09-30](https://www.stockbrokers.com/guides/ai-agent-brokers)）。這些上限都是固定數字，沒有一家看你自己過去的交易結果。

## 從你自己的歷史開始

```bash
pip install tradememory-protocol

# Hyperliquid：公開成交紀錄，不需要金鑰
tradememory sync hyperliquid --address 0x你的地址

# Alpaca：用你自己的金鑰做唯讀查詢，金鑰放在本機檔案
tradememory sync alpaca --env-file ~/.secrets/alpaca.env
```

每一筆完成的交易只會存進記憶一次，再跑一次只會加上新的交易。跑完會列出你的歷史在哪裡虧錢。以下是輸出格式，數字是示意：

```
After 2 losses in a row (20 trades):
  9 of them (45%) were 1.5x your usual size or more (across all your trades: 25%).
  That is more often than usual.
  All 20 won 50% and made -$1,500.
  The 9 sized-up trades won 22% and made -$2,100.

Median hold: winners 1.5h, losers 9.0h.

Suggested rule (does nothing until you approve it):
  After 2 losses in a row, orders that take a position to $1,500 or more are held for your approval.
  To turn it on: tradememory rules approve r-3f2a9c1e5b [--max-notional N] (the brake enforces it on its next order)
```

這些是你自己過去交易的描述性統計，不是對下一筆的建議。Hyperliquid 的 API 只提供一個地址近期的成交，不是全部歷史，越早同步，留下的歷史越多。其他交易所：`scripts/` 裡有 MT5 與 Binance 現貨的同步腳本，任何 agent 也都可以用 `remember_trade` 記錄一筆交易。

## 從你自己的歷史學出來的規則

同步只在你的歷史真的有這個習慣時才提出規則：連虧兩筆之後放大部位的比例，比你平常放大部位的比例高（對你自己的比例做單尾二項檢定 p ≤ 0.10，而且至少高 5 個百分點），而且那些放大的交易合計是虧錢的。門檻就是報告裡說的「放大」：你中位數部位的 1.5 倍。大部分人的歷史不會觸發。2026-10-05 抽樣的 18 個高交易量 Hyperliquid 帳戶，沒有一個符合；70 個交易量較小的帳戶（每月 5 千到 20 萬美元）裡，交易筆數夠的 51 個中有 8 個符合，高出 8 到 36 個百分點。

提出來的規則在你核准之前什麼都不做（先看 `tradememory rules list`，再執行 `tradememory rules approve <id>`，也可以用 `--max-notional` 換成你自己的門檻）。核准之後，煞車每張會增加風險的新單都會檢查：帳戶最近兩筆已平倉的交易都是虧損、而且這張單成交後的部位達到門檻，這張單就會跟其他需要核准的單一樣等你同意；如果核准規則時加了 `--action deny`，就直接拒絕。同一個標的拆成兩張小單、加起來部位很大，一樣會被擋。已平倉的交易是當下向券商讀的（透過同一個 MCP server 讀成交紀錄），一分鐘前剛被停損的單不用同步也算得到；讀不到這段歷史時，大到可能觸發規則的單會被拒絕。減倉或平倉永遠不擋，規則不會放行你的政策拒絕的單，規則觸發之前你給過的核准也不算數。規則被手動改過，煞車會拒絕所有單，直到你用 `tradememory rules retire <id>` 停用它；這個檢查擋得住不小心的修改，但不是簽章。

## 下一張單之前

`recall_memories(order="losses_first")` 會把所有虧損的交易排在其他記憶前面，相似條件下虧得越多越前面，並附上部位大小與損益。除了這個商品最近的交易，也會另外找它近期的虧損交易，較早的虧損不會被擠掉。伺服器會告訴連上來的 agent，在提出交易前先呼叫它。預設排序則是結果越好排越前（有記錄 R 的交易按 R 排），並保留至少 20% 的虧損交易。

## 接上你的 agent

```bash
pip install tradememory-protocol
```

加到 Claude Desktop 設定檔（`claude_desktop_config.json`）：

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

然後對 Claude 說：*「記錄我在 $195 做多 AAPL：財報超預期、機構買盤湧入、高信心。」*

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

## 在券商前面裝一道煞車（預覽）

`proxy` extra 讓 TradeMemory 跑在你的 agent 和券商的 MCP server 之間（目前支援 Alpaca）。所有工具原樣轉送，只有下單工具會先交給 [Mnemox Control](https://github.com/mnemox-ai/mnemox-control) 用你自己的政策評估，通過才送到券商。每一次評估，不論放行或拒絕，都會記錄並串進稽核鏈。放行的單回來時，會先附上你在相似條件下虧損的交易；之後用 `tradememory sync alpaca` 補上每一筆轉送出去的交易最後怎麼結束，進場有帶停損的，會換算成幾倍風險（R）。你原本的 agent 照常運作，只改 MCP 設定裡的一行。

```bash
pip install "tradememory-protocol[proxy]"   # Python 3.12+
tradememory proxy init --account-id <你的 Alpaca 帳號 id> --symbols AAPL,MSFT
tradememory proxy doctor --env-file ~/.secrets/alpaca-paper.env   # 核對上游工具名稱與帳號 id
tradememory proxy config                                           # 印出要換掉的那一行 MCP 設定
```

預設拒絕：清單外的標的、超過單筆或總部位上限的單、沒帶 bracket 停損的進場、觸及當日虧損或回撤上限之後的任何新單、取消持倉中的保護停損、煞車還沒分類過的工具，以及你下過 `tradememory proxy halt FULL_HALT` 之後的一切。永遠不擋：平倉。達到 `approval_notional` 的單會等你執行 `tradememory proxy approve <intent_id> --terms <fingerprint>`，核准的就是你看過的那組條件；agent 用同一個 `client_order_id`、同樣的條件重送，proxy 最多只轉送一次。你從自己歷史核准的規則（見[從你自己的歷史學出來的規則](#從你自己的歷史學出來的規則)）也會用同樣的方式擋下新單。`evaluate_order` 只回傳同樣的判斷、不下單，給事前檢查和其他框架的顧問層用。任何評估不了的情況，例如報價斷線、不認得的標的、政策沒涵蓋的單型，一律拒絕而不是放行。

目前狀態：已對一個有狀態的 Alpaca MCP 假上游跑完端到端測試（`tests/proxy/`），並在 2026 年 10 月 1 日對真實的 Alpaca 模擬帳戶跑過：三筆拒絕（清單外標的、沒帶停損、超過單筆上限）、一筆放行的一股 bracket 單真的送到券商、一筆用同一個 `client_order_id` 重送的單由紀錄回覆，沒有產生第二張單。選擇權、改單、stop-limit 與 trailing 單是拒絕不是評估。券商金鑰只交給 proxy 啟動的券商程序，TradeMemory 不保存。

附真實輸出的完整步驟：[docs/recipes/alpaca-brake.md](recipes/alpaca-brake.md)。

## 三種用法

| | 美股交易者 | 外匯 EA 系統 | 稽核軌跡（示意） |
|---|---|---|---|
| **市場** | 股票（AAPL、TSLA 等） | XAUUSD（黃金） | 多資產 |
| **使用方式** | 每次開倉前跑「交易前檢查清單」 | 從 MT5 自動同步 | 有雜湊鏈的決策紀錄 |
| **誰** | 一位獨立使用者（2026 年 3 月） | 維護者自己的 MT5 帳戶 | 範例，不是客戶 |
| **詳細說明** | [閱讀更多](USE_CASES.md#case-1-us-equity-trader--pre-flight-workflow) | [閱讀更多](USE_CASES.md#case-2-forex-ea-system--automated-memory-loop) | [閱讀更多](USE_CASES.md#case-3-compliance-first-fund--audit-trail) |

## 運作方式

<p align="center">
  <img src="../assets/owm-factors-zh.png" alt="OWM 五因子" width="900">
</p>

1. **回憶**：交易前，取回依結果品質、上下文相似度、近期性、信心、情緒狀態加權的歷史交易（[OWM 框架](OWM_FRAMEWORK.md)）
2. **記錄**：交易後，一次呼叫 `remember_trade` 寫入五個記憶層：情節、語義、程序、情感記憶和交易紀錄
3. **反思**：每日、每週、每月覆盤，偵測行為漂移、策略衰退和交易錯誤
4. **稽核**：每個決策在建立時計算 SHA-256 雜湊，並串到前一筆。可隨時匯出審查

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

## 幫你接上

你的 agent 已經在對券商下單，或想把你的歷史同步進來、看懂它？[開一個 brake-integration issue](https://github.com/mnemox-ai/tradememory-protocol/issues/new?template=brake_integration.yml) 或 [約 30 分鐘](https://calendly.com/johnson90207/30min)。幫你接上不收費，之後要做什麼由用的人決定。

## 稽核軌跡

你的 agent 做的每一個交易決策，包括決定**不交易**，都會記成一筆 Trading Decision Record（TDR）。每筆紀錄的 SHA-256 雜湊串成一條往前連的稽核鏈；每個 UTC 日再算一個 Merkle root，這些 root 也一天一天串起來。改動任何一筆歷史紀錄，之後的每一個環節都會對不上。

要求保存決策紀錄的法規約束的是投資公司，不是散戶。EU AI Act 附件三的高風險日誌義務已延後至 2027 年 12 月 2 日；ESMA 2026 年 2 月的演算法交易監理簡報寫明，AI 演算法交易目前不在高風險範圍內。下表只說明當這些法規適用於你時，TradeMemory 的哪些功能對得上，不是合規宣稱。

| 法規 | 要求 | TradeMemory 對應的功能 |
|------|------|---------------------|
| MiFID II 第 17 條 | 記錄每個演算法交易決策因素 | 完整決策鏈：條件、過濾器、指標、執行 |
| EU AI Act 第 14 條 | 高風險 AI 系統的人類監督 | 可解釋的推理，加上每個決策的記憶上下文 |
| EU AI Act 第 12 條 | 系統生命週期內自動、防竄改的日誌 | SHA-256 串鏈加每日 Merkle root（自 0.5.3 起預設以 RFC 3161 時間戳錨定） |

```bash
# 驗證單筆紀錄沒被改過
verify_audit_hash(trade_id="MT5-7047640363")

# 從頭到尾檢查整條鏈（或其中一段）
verify_audit_chain(from_seq=1, to_seq=None)

# 某一天的 Merkle root：涵蓋當天所有 TDR 的 32 bytes 錨點
get_daily_root(date="2026-05-14")

# 批次匯出
GET /audit/export?strategy=VolBreakout&start=2026-03-01&format=jsonl
```

自 0.5.3 起，每日 root 預設會送到 RFC 3161 時間戳機構蓋時間戳。還沒做的：用私鑰簽署紀錄、錨定到公開日誌、證明沒有漏記。見 [LIMITATIONS.md](../LIMITATIONS.md)。

## 安全

- **記憶伺服器（預設）。** 不下單，也不要求券商金鑰。只記錄與回憶，資料存在本機的 SQLite 檔。
- **同步。** `tradememory sync hyperliquid` 讀的是公開資料，不用金鑰。`tradememory sync alpaca` 用你本機檔案裡的金鑰做唯讀查詢。同步進來的交易留在你本機的資料庫。
- **煞車（`proxy` extra）。** 把你的政策允許的單轉送到券商的 MCP server。券商金鑰只交給 proxy 啟動的券商程序，TradeMemory 不保存。
- **對外連線。** 每日稽核 root 的 RFC 3161 時間戳，送出的只是 32 bytes 的雜湊、不含交易資料（預設開啟，`TRADEMEMORY_TSA=off` 可關閉）。`tradememory sync` 只連你指定的交易所。agent 呼叫策略演化工具時，會向 Binance 讀取公開行情（`api.binance.com`）；策略演化只有在你設了 `ANTHROPIC_API_KEY` 時才呼叫 Anthropic API。回放預設呼叫 DeepSeek（也可改用 Anthropic），同樣要你設了該家的金鑰才會連線。如果你另外安裝 `sentence-transformers` 來用混合檢索，第一次使用時會從 Hugging Face 下載模型。`scripts/` 裡的 MT5 與 Binance 同步腳本從你的環境變數讀取登入資料或金鑰；MT5 腳本只有在你設了 `DISCORD_WEBHOOK_URL` 時，才會把交易摘要（商品、價格、損益）送到 Discord webhook。
- **可查核，不是防竄改。** 每筆紀錄都計算雜湊並串到前一筆，另有每日 Merkle root。改一筆紀錄會讓鏈斷掉；能改寫整個資料庫的人，也能把整條鏈重建。

## 研究現況

TradeMemory 的 OWM 框架基於認知科學（Tulving 1972）和強化學習（Schaul et al. 2015）。目前狀態：

- **OWM 五因子評分：** 已實作並有測試（見 CI 徽章）
- **統計驗證：** DSR、MBL 已實作（Bailey-de Prado 2014）
- **稽核軌跡：** SHA-256 可查核的 TDR
- **進化引擎：** 研究階段（策略生成可運作，統計門檻通過率仍在優化中）
- **混合召回：** 預設只用 OWM，設定 embedding 後可啟用向量融合
- **實證驗證：** 進行中（n=14 筆交易，目標 n>=100 才有統計意義；n=14 時信賴區間過寬，不足以下任何結論，見 validation/final_verdict.md）

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

MIT，詳見 [LICENSE](../LICENSE)。選用的 `proxy` extra 會安裝 [Mnemox Control](https://github.com/mnemox-ai/mnemox-control)，它的引擎是 AGPL-3.0-only（另有商業授權）；TradeMemory 本身維持 MIT。僅供教育和研究用途。不構成投資建議。

<div align="center">由 <a href="https://mnemox.ai">Mnemox</a> 打造</div>
