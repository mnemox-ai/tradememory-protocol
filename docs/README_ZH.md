<!-- mcp-name: io.github.mnemox-ai/tradememory-protocol -->

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/hero-zh-dark.png">
  <img src="assets/hero-zh-light.png" alt="TradeMemory Protocol" width="720">
</picture>

**如果你的交易機器人能從每次失敗中學習，還能自己發明更好的策略呢？**

200 多個交易 MCP Server 都在執行交易，沒有一個記得發生了什麼。

TradeMemory 是改變這一切的記憶層。

[![PyPI](https://img.shields.io/pypi/v/tradememory-protocol?style=flat-square&color=blue)](https://pypi.org/project/tradememory-protocol/)
[![Tests](https://img.shields.io/badge/tests-1%2C055_passed-brightgreen?style=flat-square)](https://github.com/mnemox-ai/tradememory-protocol/actions)
[![MCP Tools](https://img.shields.io/badge/MCP_tools-15-blueviolet?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)
[![Smithery](https://img.shields.io/badge/Smithery-listed-orange?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)

</div>

---

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/before-after-zh-dark.png">
  <img src="assets/before-after-zh-light.png" alt="使用前後對比" width="720">
</picture>

</div>

---

## 為什麼需要 TradeMemory？

**「為什麼我的機器人一直犯同樣的錯？」**

持久記憶完整記錄每筆交易的上下文 — 進場理由、市場環境、信心水準、最終結果。模式發現引擎能找到你肉眼看不到的規律。

**「我的策略跑了好幾個月，突然就失效了。」**

結果加權回憶會自動降低舊市場環境下的模式權重。你的機器人能自動適應，不需要你重寫任何規則。

**「怎麼知道它不是在過擬合？」**

每個模式都帶有貝氏信心度和樣本數量。內建樣本外驗證機制。可疑模式會被標記，不會盲目跟隨。

**「我只想讓它自己找出什麼有效。」**

Evolution Engine：只需餵入原始價格數據。不用指標，不用手寫規則。它會自動發現、回測、淘汰、進化。

> 22 個月 BTC 數據。**Sharpe 3.84。** 477 筆交易。91% 月份正報酬。零人工策略輸入。

---

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

然後對 Claude 說：

> *「記錄我在 71,000 做多 BTCUSDT — 動量突破，高信心。」*

<details>
<summary>Claude Code / Cursor / 其他 MCP 客戶端</summary>

**Claude Code:**
```bash
claude mcp add tradememory -- uvx tradememory-protocol
```

**Cursor / Windsurf / 任何 MCP 客戶端** — 加到 MCP 設定檔：
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

</details>

<details>
<summary>從原始碼安裝 / Docker</summary>

```bash
git clone https://github.com/mnemox-ai/tradememory-protocol.git
cd tradememory-protocol
pip install -e .
python -m tradememory
# 伺服器運行在 http://localhost:8000
```

```bash
docker compose up -d
```

</details>

---

## 應用場景

**加密貨幣** — 從 Binance 匯入 BTC/ETH 交易。Evolution Engine 能發現你永遠找不到的時間規律，市場環境改變時自動調適。

**外匯 + MT5** — 自動同步 MetaTrader 5 的每筆平倉交易。跨 session 持久記憶讓你的 EA 記住亞盤突破只有 10% 勝率 — 然後不再下單。

**開發者** — 用 15 個 MCP 工具 + 30 個 REST 端點建構有記憶的交易 agent。你的 agent 每次啟動都知道自己的信心水準、進行中的計畫、以及哪些策略正在賺錢。

---

## 架構

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/owm-architecture-zh-dark.png">
  <img src="assets/owm-architecture-zh-light.png" alt="OWM 架構" width="720">
</picture>

</div>

每筆記憶被回憶時，透過五個因子評分：

| 因子 | 功能 |
|------|------|
| **Q** — 品質 | 將交易結果映射到 (0,1)。+3R 的贏家得 0.98。-3R 的輸家得 0.02 — 但永遠不為零，因為虧損記憶會作為警告被召回。 |
| **Sim** — 相似度 | 當前市場環境和記憶形成時有多相似？不相關的記憶會被抑制。 |
| **Rec** — 時效性 | 冪律衰減。30 天前的記憶保留 71% 強度。1 年前保留 28%。比指數衰減更溫和 — 與當前環境相關的舊記憶仍可檢索。 |
| **Conf** — 信心度 | 高信心狀態下形成的記憶得分更高。最低 0.5，避免早期記憶被忽略。 |
| **Aff** — 情緒 | 回撤期間，警示記憶會浮現。連勝期間，過度自信檢查會啟動。 |

> 理論基礎：ACT-R (Anderson 2007)、Kelly 準則 (1956)、Tulving 記憶分類法 (1972)、Damasio 體感標記假說 (1994)。完整規格：[OWM_FRAMEWORK.md](docs/OWM_FRAMEWORK.md)

---

<details>
<summary><strong>Evolution Engine — 隱藏王牌</strong></summary>

Evolution Engine 從原始價格數據中發現交易策略。不用指標，不用人工規則。純 LLM 驅動的假設生成 + 向量化回測 + 達爾文式篩選。

### 運作方式

1. **發現** — LLM 分析價格數據，提出候選策略
2. **回測** — 向量化引擎測試每個候選策略（ATR-based SL/TP，多空，時間型出場）
3. **篩選** — 樣本內排名 → 樣本外驗證（Sharpe > 1.0，交易數 > 30，最大回撤 < 20%）
4. **進化** — 存活者被變異。下一代。重複。

### 實測結果：BTC/USDT 1H，22 個月（2024-06 至 2026-03）

| 系統 | 交易數 | 勝率 | RR | 利潤因子 | Sharpe | 報酬 | 最大回撤 |
|------|--------|------|----|----------|--------|------|----------|
| 策略 C (做空) | 157 | 42.7% | 1.57 | 1.17 | 0.70 | +0.37% | 0.45% |
| 策略 E (做多) | 320 | 49.4% | 1.95 | 1.91 | 4.10 | +3.65% | 0.27% |
| **C+E 組合** | **477** | **47.2%** | **1.84** | **1.64** | **3.84** | **+4.04%** | **0.22%** |

- 91% 月份正報酬（22 個月中 20 個月）
- 最大回撤 0.22% — 比任何單一策略都低
- 零人工策略輸入。LLM 從原始 K 線中自行發現這些策略。

> 數據來源：[RESEARCH_LOG.md](../docs/RESEARCH_LOG.md)。11 項實驗，完整方法論，模型比較（Haiku vs Sonnet vs Opus）。

</details>

---

## MCP 工具

### 核心記憶（4 個工具）
| 工具 | 說明 |
|------|------|
| `store_trade_memory` | 儲存交易及完整上下文 |
| `recall_similar_trades` | 尋找相似市場環境的歷史交易（有 OWM 數據時自動升級） |
| `get_strategy_performance` | 各策略匯總績效 |
| `get_trade_reflection` | 深入分析單筆交易的推理與教訓 |

### OWM 認知記憶（6 個工具）
| 工具 | 說明 |
|------|------|
| `remember_trade` | 同時寫入五層記憶 |
| `recall_memories` | 結果加權回憶，附完整評分拆解 |
| `get_behavioral_analysis` | 持倉時間、處置效應比率、Kelly 比較 |
| `get_agent_state` | 當前信心、風險偏好、回撤、連勝/連敗 |
| `create_trading_plan` | 前瞻記憶中的條件式計畫 |
| `check_active_plans` | 將進行中計畫與當前市場比對 |

### Evolution Engine（5 個工具）
| 工具 | 說明 |
|------|------|
| `evolution_run` | 執行完整的發現 → 回測 → 篩選循環 |
| `evolution_status` | 查看進化進度 |
| `evolution_results` | 取得畢業策略及完整指標 |
| `evolution_compare` | 跨世代比較 |
| `evolution_config` | 查看/修改進化參數 |

<details>
<summary>REST API（30+ 端點）</summary>

交易記錄、結果登記、歷史查詢、日/週/月反思、風險約束、MT5 同步、OWM CRUD、進化引擎調度等。

完整參考：[docs/API.md](docs/API.md)

</details>

---

## Star History

<a href="https://star-history.com/#mnemox-ai/tradememory-protocol&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=mnemox-ai/tradememory-protocol&type=Date&theme=dark" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=mnemox-ai/tradememory-protocol&type=Date" />
 </picture>
</a>

---

## 貢獻

詳見 [CONTRIBUTING.md](../.github/CONTRIBUTING.md)。

- 給個 Star 追蹤進度
- 透過 [GitHub Issues](https://github.com/mnemox-ai/tradememory-protocol/issues) 回報問題
- 提交 PR 修 bug 或新增功能

---

## 文件

| 文件 | 說明 |
|------|------|
| [OWM 框架](docs/OWM_FRAMEWORK.md) | 完整理論基礎（1,875 行） |
| [Tutorial (EN)](docs/TUTORIAL.md) | 英文教學 |
| [教學 (中文)](docs/TUTORIAL_ZH.md) | 完整中文教學指南 |
| [API 參考](docs/API.md) | 所有 REST 端點 |
| [MT5 設定](docs/MT5_SYNC_SETUP.md) | MetaTrader 5 整合 |
| [研究日誌](RESEARCH_LOG.md) | 11 項進化實驗的完整數據 |

---

## 授權

MIT — 詳見 [LICENSE](LICENSE)。

**免責聲明：** 本軟體僅供教育和研究用途。不構成投資建議。交易涉及重大虧損風險。

---

<div align="center">

由 [Mnemox](https://mnemox.ai) 打造

</div>
