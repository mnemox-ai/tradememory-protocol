# TradeMemory Protocol — Claude Code 指令

## 專案概述

TradeMemory Protocol 是 Mnemox AI 的核心產品。MT5/forex 交易記憶層，3 層架構（L1 原始交易 → L2 模式發現 → L3 策略調整），MCP server。

- GitHub: mnemox-ai/tradememory-protocol
- PyPI: tradememory-protocol
- 版本: v0.5.0
- Tests: 1073 tests passing
- Default branch: `master`（不是 main）

## 開發規範

- Python 3.10+
- 測試：`python -m pytest tests/ -v`（每個任務完成後必須跑，確認沒新增 fail）
- Linting：遵循現有 code style
- Commit message 格式：`type: description`（feat/fix/docs/chore）
- 每完成一個 ROADMAP 任務就 commit + push
- 不要修改核心 MCP tools（src/tradememory/mcp_server.py），除非 ROADMAP 明確要求

## 任務執行流程

1. 開始新 session 時，先讀 docs/ROADMAP.md 確認當前進度
2. 找到第一個未完成（❌）的任務
3. 執行該任務
4. 跑 tests 驗證
5. Commit + push
6. 在 docs/ROADMAP.md 標記 ✅
7. 繼續下一個任務
8. 如果 context 快滿了，先更新 docs/ROADMAP.md 進度，然後結束 session

## 重要文件位置

- MCP tools 定義：`src/tradememory/mcp_server.py`（4 個 MCP tools：store/recall/performance/reflection）
- FastAPI REST server：`src/tradememory/server.py`（30+ REST endpoints）
- MT5 同步：`docs/MT5_SYNC_SETUP.md` + `scripts/mt5_sync.py`
- 每日反思：`scripts/daily_reflection.py`
- Demo：`scripts/demo.py`（30 筆模擬交易跑完整 L1→L2→L3 pipeline）
- 測試：`tests/`
- OpenClaw Skill：`.skills/tradememory/SKILL.md`
- 開發路線圖：`docs/ROADMAP.md`
- Scripts 結構：`scripts/`（user-facing）、`scripts/research/`（回測/驗證/遷移）、`scripts/platform/`（.bat/.xml/.sh/.pyw）

## Lessons Learned

- 預設分支是 master 不是 main，所有 GitHub URL 都要用 master
- .env.example 不要放真實憑證
- README 不要用過多 emoji 和行銷語調，保持開發者風格
- 不要承諾還沒實作的功能（Phase 2 不打勾）
- CHANGELOG 要誠實，不要假裝多個 sprint
- Before/After 數據如果是模擬的，要在最上面明確標註
- 刪除的檔案如果曾 commit 過敏感資訊，git 歷史裡還是看得到，要用 filter-branch 清除

## Rules

- 每個任務完成前必須跑 pytest 確認沒壞東西
- commit 前用 git diff 檢查改動範圍是否合理
- 不要一次開太多 MCP tools，會吃 context window
- 寫文件用開發者語調，不要用行銷語調
- 所有模擬數據必須標註 "Simulated"
- 簡單方案優先，不要 over-engineer
- NEVER hardcode credentials. All secrets via `.env` or environment variables
- Use UTC for all timestamps

## Recent Changes
- [2026-03-25] feat: Phase 2 complete — TDR schema + 4 audit REST endpoints + 2 MCP tools + SHA256 tamper detection. 1214 tests.
- [2026-03-25] feat: Phase 0 complete — mt5_sync_v3 now sends rich context (EventLogReader + dynamic confidence + pnl_r + exit_reasoning + references + regime). 1199 tests.
- [2026-03-23] feat: Phase 15 Batch C scripts + DeFi assets committed
- [2026-03-23] fix: mt5_sync_v3 import path + MAGIC_TO_STRATEGY mapping
- [2026-03-22] GEO: README + README_ZH 加 FAQ 式開頭、When to use、How it works、Comparison table
- [2026-03-21] deflated-sharpe v0.1.0 published to PyPI + GitHub (mnemox-ai/deflated-sharpe). DSR/MinBTL/BH-FDR/RegimeDecayDetector extracted as standalone package. 27 tests.
- [2026-03-21] Phase 15 Batch C: LLM WFO pilot FAIL — 0/150 graduated (5 periods × 30 hypotheses), Cohen's d=0.000 vs Grid. Structural novelty PASS (6 novel fields). Bottleneck is EvolutionEngine graduation, not DSR. STOP decision.
- [2026-03-21] fix: cumulative_trials bug — re_evolution.py now increments M on ALL outcomes (not just DSR pass). 3 new tests, 1181 total.
- [2026-03-21] fix: Sharpe annualization bug — backtester.py `annualize=False` param, Grid WFO rerun with raw Sharpe. Layer 1 Gate: 3/3 FAIL (DSR 0/23 pass). Root cause: M=19200 incompatible with 30-50 trades. Report: validation/reevolution_report.md
- [2026-03-21] feat: Phase 15 Batch B — Grid WFO complete. strategy_registry.py (25 tests) + re_evolution.py (20 tests) + run_grid_wfo.py (23 periods × 19200 combos × 4 arms). 1178 tests total.
- [2026-03-21] feat: Phase 15 Batch A — Regime Decay Detector (triple-confirmation: Bayesian win rate + DD exceedance + Mahalanobis OOD) + Statistical Gates (DSR + MinBTL + BH-FDR). 46 new tests, 1133 total.
- [2026-03-20] feat: compare_defi_fingerprints.py — 多錢包指紋比對（session cosine、token Jaccard、tempo分類、Aave ratio、gas sensitivity），Abraxas vs 0x7a16fF 完成
- [2026-03-20] feat: USD value estimation — half-year ETH/BTC price lookup, $40.5B total volume (98.1% coverage), monthly breakdown
- [2026-03-20] refactor: DeFi token 分類擴充（other 從 19.7%→3.8%），新增 farming_lp/governance/wrapped_btc/ethena/pendle/spark 6 類
- [2026-03-20] feat: analyze_defi_behavior.py — Abraxas Capital 5 維行為指紋（Aave 流向、token 偏好、操作節奏、時段偏好、gas 敏感度），1,945 swaps 分析完成
- [2026-03-19] feat: Etherscan V2 whale fetcher + Abraxas Capital 1,945 swaps extracted, DeFi 行為指紋 POC
- [2026-03-19] fix: datetime.utcnow() → datetime.now(timezone.utc)，12 處，消除 Python 3.12 deprecation warning
- [2026-03-19] 視覺完善：schema 白底、文字加粗加深、5 張中文版 PNG、README_ZH 重寫（News+架構圖）
- [2026-03-19] README 視覺大升級：5 張 HTML→PNG 圖表（header/schema/L1L2L3/OWM/Evolution），透明背景，News 區塊，Playwright 自動生成，學 TradingAgents DX 設計
- [2026-03-19] Repo 大改造：根目錄從 31 files 降到 ~20，scripts/ 分為 user-facing + research/，文件重組到 docs/ 和 .github/，README 291→139 行
- [2026-03-19] scripts/ 重組：user-facing 留根目錄，30 個 research scripts 移到 scripts/research/，13 個 platform scripts 移到 scripts/platform/
- [2026-03-19] Phase 14 Validation: B1 stability CONDITIONAL PASS, B2 cross-asset transfer, analyze_trader.py product prototype
- [2026-03-19] Strategy C added to shared definitions + export/seed CLI --strategy c/e + 337 trades seeded to Supabase
- [2026-03-18] GH Actions live executor WORKING: 5 iterations to fix (editable install, Binance US geo-restriction, env var strip, supabase-py maybe_single compat). Cron hourly at :05.
- [2026-03-18] Code health fixes: shared strategy_definitions.py, ruff auto-fix (43 lint), batch seed insert, live_executor tests, backtester public API, GH Actions cache+notify
- [2026-03-18] refactor: make backtester _check_exit/_force_close/_open_position public API with backward compat aliases
- [2026-03-18] test: 14 unit tests for live_executor check_exit (SL/TP/timeout/boundary/priority/PnL), 1087 tests passing
- [2026-03-18] refactor: extract build_strategy_e() into scripts/strategy_definitions.py (shared module)
- [2026-03-18] Live dashboard backend: 16-task architecture (PostgreSQL + Vite + React + pgvector hybrid recall), 1073 tests passing
- [2026-03-18] scripts/seed_backtest_trades.py — Seed backtest JSON into Supabase live_trades (DELETE+INSERT, strategy_e)
- [2026-03-18] scripts/export_backtest_trades.py — Export Strategy E backtest trades to JSON (fast_backtest_with_trades + trade_to_dict + 8 tests)
- [2026-03-18] scripts/live_executor.py — Strategy E paper trading executor (Binance + Supabase + GH Actions hourly)
- [2026-03-17] Phase 13 Steps 3-4: Time bias (US session H14-H16 is alpha), Extended OOS FAIL (regime-specific)
- [2026-03-17] Phase 13 Step 2 walk-forward: E passes 2/3 (mean OOS Sharpe 3.24), C fails (0.24)
- [2026-03-17] Phase 13 Step 1 real data validation: C=P96.9%, E=P100%, both PASS random baseline
- [2026-03-17] Phase 13 Step 1: Random baseline generator + tests + demo
- [2026-03-16] tradememory-plugin 獨立 repo 上線（mnemox-ai/tradememory-plugin），結構對齊 Anthropic plugin spec，主 repo README 加 Plugin 安裝區塊
- [2026-03-16] tradememory-plugin/ 重構：Anthropic plugin 標準結構（5 commands + 3 skills + MCP config + README）
- [2026-03-16] **v0.5.0 產品化大整頓**（3 批次 auto-claude + 手動補修）：TUTORIAL/CONTRIBUTING/SKILL.md 更新，GitHub Release v0.5.0，Org profile README（3 產品卡片），mnemox.ai 網站加 Evolution Engine + SEO，全 repo src.tradememory.server 引用清除
- [2026-03-16] README 視覺重設計：6 PNG（hero/before-after/architecture × light/dark）+ 中文版 6 張，490→280 行
- [2026-03-16] CI green + Distribution sprint: Smithery + mcp.so + mcpservers.org + Glama
- [2026-03-16] **v0.5.0 Release** — Evolution Engine + OWM Completion. 1055 tests, 12 phases complete
- [2026-03-15] Phase 9: DataSource Protocol + Binance + Context Builder + MT5 CSV
- [2026-03-15] 建立 Jarvis 系統：/morning 每日掃描、/wrap-up session handoff

## Completed: Phase 15 Batches A + B

### Batch A ✅ (2026-03-21)
- `regime_detector.py` + `statistical_gates.py` — 46 tests, commit `3f96b6a`

### Batch B ✅ (2026-03-21)
- `re_evolution.py` + `strategy_registry.py` + `run_grid_wfo.py` — 45 tests
- **Grid WFO Layer 1 Gate: FAIL (3/3)** — DSR 0/23 pass. Root cause: M=19200 + 30-50 trades = mathematically impossible. Report: `validation/reevolution_report.md`

---

## Current Task: Phase 15 Batch C — LLM vs Grid H2H (Exp 4b)

### Core Hypothesis

LLM evolution (M≈30/round) has 640x lower DSR statistical burden than grid search (M=19,200). The value is not "better strategies" but "defensible strategies with lower multiple-testing penalty." Exp 4b tests this directly.

### Step 0: Manual Single Transition (DO FIRST)

跑 1 個 IS window 的 EvolutionEngine.evolve()，觀察：
1. **LLM hypothesis 結構** — 有幾個 entry conditions？用了哪些 features？
   - Grid 只用 `hour_utc` + `trend_12h_pct`（2 conditions）
   - LLM 能否用 `volatility_regime`、`session`、`atr_percentile`（BETWEEN）等 grid 之外的 features？
   - 如果 LLM 回來的策略跟 grid 一樣只有 hour + trend → Layer 2 structural novelty 從一開始就注定 FAIL
2. **實際 M** — `run.total_backtests` 和 `len(run.hypotheses)` 的值
3. **API 成本** — `run.total_llm_tokens`，估算 23 periods 的總 cost
4. **raw Sharpe 量級** — LLM 策略在 IS window 的 raw Sharpe 跟 grid top candidates 比

**怎麼跑**：
```python
# 用第一個 period 的 IS data (2020-01 to 2020-04)
# 需要 ANTHROPIC_API_KEY
from tradememory.evolution.engine import EvolutionEngine, EngineConfig
from tradememory.evolution.llm import AnthropicClient
from tradememory.evolution.models import EvolutionConfig

llm = AnthropicClient()  # uses ANTHROPIC_API_KEY env
config = EngineConfig(
    evolution=EvolutionConfig(
        symbol="BTCUSDT", timeframe="1h",
        generations=3, population_size=10,
    )
)
engine = EvolutionEngine(llm, config)
run = await engine.evolve(is_series)  # is_series = 2020-01 to 2020-04
# 觀察 run.hypotheses, run.graduated, run.total_backtests, run.total_llm_tokens
```

**Step 0 Gate**：如果 LLM hypotheses 全部只有 hour + trend（跟 grid 一樣），STOP。Layer 2 不用跑了。

### Exp 4b: LLM WFO Experiment

**檔案**：
- `scripts/research/run_llm_wfo.py` — LLM WFO 模擬器（新建）
- `validation/llm_wfo_results.json` — 結果輸出

**Arms**（跟 Exp 4a 同 controls，只換 treatment）：

| Arm | Description | M per round |
|-----|-------------|-------------|
| Arm L | LLM WFO + DSR gate | ~30 (from EvolutionEngine) |
| Arm G | Grid WFO + DSR gate (Exp 4a data, already have) | 19,200 |
| Control A | Static Strategy E | 1 |
| Control B | Buy & Hold | 0 |

**設計**：
- 同 Exp 4a timeline: 23 periods, 3mo IS + 3mo OOS
- LLM arm: `EvolutionEngine.evolve()` on IS → graduated strategies → backtest OOS → DSR gate
- **所有 Sharpe 用 raw（annualize=False）**
- Controls A/B 直接從 Exp 4a `grid_wfo_results.json` 讀取（不重跑）

### DSR M 累積（關鍵）

這是整個假設的核心。確認以下邏輯：
1. `EvolutionEngine.evolve()` 回傳 `run.total_backtests`（IS + OOS backtests 總和）
2. **M = total IS hypotheses tested**（不含 OOS，因為 OOS 只跑 ranked survivors）
3. 每個 period 的 M = `len(run.hypotheses)` ≈ 30
4. **M 跨期累加**：Period 1 M=30, Period 2 M=60, ... Period 23 M=690
5. 累加邏輯在 `StrategyRegistry.cumulative_trials` — `deploy()` 時 `+= num_trials`
6. **即使 DSR gate FAIL（沒 deploy），M 也要累加**（因為你已經測過了）

⚠️ 現在 `ReEvolutionPipeline.run()` 裡 `registry.deploy()` 在 DSR pass 時才 call，所以 FAIL 時 `cumulative_trials` 沒加。**這是 bug，必須修**。正確做法：不管 pass/fail，都要 `registry.cumulative_trials += result.num_tested`。

### LLMReEvolutionPipeline（新 class 或修改現有）

Option A：修改 `ReEvolutionPipeline` 接受 `EvolutionEngine` 替代 grid
Option B：新建 `LLMReEvolutionPipeline`

**建議 Option B**（避免破壞 Exp 4a 的 code path）。

簽名：
```python
class LLMReEvolutionPipeline:
    def __init__(self, llm: LLMClient, engine_config: EngineConfig, ...):
        ...
    async def run(self, is_series: OHLCVSeries, oos_bars, oos_contexts, oos_atrs,
                  registry, ...) -> LLMReEvolutionResult:
        # 1. engine.evolve(is_series) → run
        # 2. Best graduated strategy → backtest OOS (raw Sharpe)
        # 3. DSR gate with M = len(run.hypotheses)
        # 4. Record M to registry (always, not just on pass)
```

### Pilot Protocol (5 transitions)

1. 跑前 5 個 periods（P1-P5）
2. 停下來算 **Cohen's d**：`d = (mean_L - mean_G) / pooled_std`
3. 預估 23 periods 的 power
4. 如果 d < 0.2（small effect），考慮是否值得跑完剩下 18 個（API 成本 vs 資訊價值）
5. Sean 看過 pilot 結果後決定：繼續 / 停止 / 調整

### Cost Estimate

- Sonnet 4: ~$3/MTok input, ~$15/MTok output
- 每次 evolve(): ~3 LLM calls × ~2K tokens = ~6K tokens ≈ $0.02-0.05
- 23 periods: ~$0.50-1.15 total
- 如果用 Haiku 4.5: ~10x cheaper

### 驗收標準

1. Step 0 完成：LLM hypothesis 結構分析 + API cost per evolution
2. `run_llm_wfo.py` pilot 5 periods 跑完
3. Cohen's d 計算完成
4. **停在這裡。Sean 決定是否繼續跑 full 23 periods。**
5. 不管結果，更新 `validation/reevolution_report.md` 加 Exp 4b section

### Layer 2 Gate 標準（Pre-Registered）

**L > G（LLM beats Grid）**：
1. Arm L DSR survive rate > Arm G DSR survive rate（即 >0%，因為 G=0%）
2. Arm L OOS Sharpe > Control A in ≥50% periods, Wilcoxon p < 0.10
3. Arm L 有 ≥1 個 hypothesis 用了 grid 搜索空間之外的 feature（structural novelty）

**FAIL 標準**：
1. L DSR survive = 0% → LLM 也救不了
2. L hypotheses 全部只有 hour + trend → 沒有 structural novelty
3. Cohen's d < 0.2 after pilot → effect 太小不值得跑完

### Input Files

- `src/tradememory/evolution/engine.py` — EvolutionEngine
- `src/tradememory/evolution/llm.py` — AnthropicClient
- `src/tradememory/evolution/generator.py` — HypothesisGenerator
- `src/tradememory/evolution/re_evolution.py` — ReEvolutionPipeline（reference）
- `src/tradememory/evolution/backtester.py` — backtest + _compute_fitness（annualize=False）
- `scripts/research/run_grid_wfo.py` — 參考架構
- `scripts/research/run_real_baseline.py` — fast_backtest, precompute_contexts/atrs
- `validation/grid_wfo_results.json` — Exp 4a controls data（直接讀取，不重跑）

---

## Current Status
- **v0.5.0**, 1214 tests passing, 1 skipped
- **Phase 2 COMPLETE**: TDR audit schema + REST endpoints + MCP tools + data_hash. See `docs/EXECUTION_LOG.md`.
- **Phase 0 COMPLETE**: mt5_sync_v3 enriched with full trade context pipeline.
- **Phase 15 COMPLETE** — 結論：1H timeframe + 3mo window + single-hour entry 條件下，grid 和 LLM 都無法產出通過 DSR gate 的策略。瓶頸是 trade count，不是 search method。Evolution Engine 驗證延後到更高交易頻率的設定。
- Exp 4a Layer 1 Gate: FAIL (3/3). Exp 4b Layer 2 Gate: FAIL (2/3, Cohen's d=0.000 → STOP).
- Structural novelty confirmed (LLM 用了 6 種 grid 之外的 features)，但 graduation rate=0% 使比較無意義。
- **Phase 15 Batch A COMPLETE**: Regime Detector + Statistical Gates committed
- **Phase 14 Validation COMPLETE**: B1 CONDITIONAL PASS, B2 PASS (P100 ETHUSDT)
- **OWM filtering INVALIDATED**: Permutation test 0/4 significant
- **Strategic pivot**: OWM = free infra, Evolution Engine = paid product (pending validation)
- **Phase 13 COMPLETE**: E has real edge (P100%), but regime-specific
- All 12 phases complete — P1: 42/42, P2: 20/20, total 62/62 tasks
- 15 MCP tools, 30+ REST endpoints, Evolution Engine + OWM 5 memory types

## Compact Instructions

When compacting, preserve: docs/ROADMAP.md progress, key design decisions (LLM validation, UTC enforcement, platform-agnostic core), current task progress, security rules, lessons learned, rules.
