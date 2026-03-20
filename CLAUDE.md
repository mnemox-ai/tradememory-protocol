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

## Current Task: Phase 15 Batch B — Re-Evolution Pipeline + Grid WFO

**完整計畫**：`~/.claude/plans/cheeky-wishing-dawn.md`

### Batch A ✅ COMPLETE (2026-03-21)
- `regime_detector.py` — triple-confirmation decay detector (18 tests)
- `statistical_gates.py` — DSR + MinBTL + BH-FDR (28 tests)
- 1133 tests total, commit `3f96b6a`

### Batch B Scope

兩個 deliverable：Exp 2（Re-Evolution Pipeline）+ Exp 4a（Grid WFO Baseline）

#### 1. Re-Evolution Pipeline（Exp 2）

**檔案**：
- `src/tradememory/evolution/re_evolution.py` — ReEvolutionPipeline class
- `src/tradememory/evolution/strategy_registry.py` — 策略版本管理
- `tests/test_re_evolution.py`
- `tests/test_strategy_registry.py`

**ReEvolutionPipeline 設計**：
1. Decay detected（from `regime_detector.py`）→ 收集最近 N 個月 OHLCV data（rolling window）
2. 跑 `EvolutionEngine.evolve()` 或 grid search on rolling window
3. 新 graduated strategies 必須通過 statistical gate（`statistical_gates.py` 的 DSR > 0）
4. 通過 → 替換 live strategy；未通過 → 暫停交易（cash position）

**關鍵設計**：
- Rolling window：3 個月 IS + 1 個月 OOS（跟 Phase 13 walk-forward 一致）
- 每次 re-evolution 記錄 M（tested combinations），累積到 DSR 計算
- Strategy Registry：`strategy_registry.json` 追蹤版本歷史（deploy_date, retire_date, fitness, reason）

**Input files**：
- `src/tradememory/evolution/regime_detector.py`（Batch A 產出）
- `src/tradememory/evolution/statistical_gates.py`（Batch A 產出）
- `src/tradememory/evolution/engine.py`（EvolutionEngine）
- `src/tradememory/evolution/backtester.py`（fast_backtest）
- `src/tradememory/evolution/models.py`（FitnessMetrics, Hypothesis, CandidatePattern）
- `src/tradememory/evolution/selector.py`（SelectionConfig）

#### 2. Grid WFO Baseline（Exp 4a）

**檔案**：
- `scripts/research/run_grid_wfo.py` — 完整 Grid WFO 模擬器
- `validation/grid_wfo_results.json` — 結果輸出

**實驗設計**（嚴格避免 look-ahead bias）：
```
Timeline: 2020-01 → 2026-03
Step 1: Grid search on [2020-01, 2020-04] → Best Grid Strategy V1
Step 2: Deploy V1 on [2020-04, 2020-07]
Step 3: Monitor decay signals (regime_detector)
Step 4: If decay → grid re-search on [2020-04, 2020-07] → V2
Step 5: Deploy V2 on [2020-07, 2020-10]
... repeat until 2026-03
```

**Grid search space**（fixed）：
- `hour_utc`: [0-23]（24 values）
- `direction`: [LONG, SHORT]（2 values）
- `trend_12h_pct threshold`: [-0.5, -0.3, 0, 0.3, 0.5]（5 values）
- `SL_atr`: [0.5, 1.0, 1.5, 2.0]（4 values）
- `TP_atr`: [1.0, 1.5, 2.0, 3.0, 4.0]（5 values）
- `max_holding_bars`: [4, 6, 8, 12]（4 values）
- Total: 24 × 2 × 5 × 4 × 5 × 4 = **19,200 combinations** per re-evolution

**對照組（全部跑）**：
| Arm | Description |
|-----|-------------|
| Arm G | Grid WFO with decay detection |
| Control A | Static Strategy E（2024 frozen） |
| Control B | Buy & Hold |
| Control C | Random（每 3 月隨機選） |

**統計檢定**：
- Paired Wilcoxon signed-rank test per regime period
- 需 ≥6 regime transitions

**數據**：BTCUSDT 1H via BinanceDataSource（parquet cache）

**Input files**：
- `src/tradememory/evolution/re_evolution.py`（本 batch 產出）
- `src/tradememory/evolution/regime_detector.py`（Batch A）
- `src/tradememory/evolution/statistical_gates.py`（Batch A）
- `scripts/research/run_walk_forward.py`（walk-forward infrastructure）
- `scripts/research/run_real_baseline.py`（fast_backtest, precompute_contexts/atrs）
- `scripts/strategy_definitions.py`（build_strategy_e for Control A）

### 驗收標準
1. `python -m pytest tests/ -v` 全過（現有 1133 不能壞）
2. `strategy_registry.py` 能 load/save/query 策略版本歷史
3. `run_grid_wfo.py` 跑完，`validation/grid_wfo_results.json` 有結構化結果
4. JSON 包含：每個 regime period 的 Arm G / Control A / Control B / Control C OOS Sharpe
5. **停在這裡。Sean 親自做 Layer 1 Gate 判定。**

### Layer 1 Gate 標準（Pre-Registered）
**PASS（全部滿足）**：
1. Arm G Sharpe > Control A in ≥60% of regime periods, Wilcoxon p < 0.10
2. Arm G Sharpe > Control C in ≥60% of periods, p < 0.10
3. DSR gate survive rate ≥ 50%

**FAIL（任一觸發）**：
1. Arm G ≤ Control C → re-evolution 無方向性價值
2. DSR gate 淘汰 >80% → 全是 noise
3. MinBTL > available data → 數據不夠下結論

---

## Current Status
- **v0.5.0**, 1133 tests passing, 2 skipped, 0 warnings
- **Phase 15 Batch A COMPLETE**: Regime Detector + Statistical Gates committed
- **Phase 14 Validation COMPLETE**: B1 CONDITIONAL PASS, B2 PASS (P100 ETHUSDT)
- **OWM filtering INVALIDATED**: Permutation test 0/4 significant
- **Strategic pivot**: OWM = free infra, Evolution Engine = paid product (pending validation)
- **Phase 13 COMPLETE**: E has real edge (P100%), but regime-specific
- All 12 phases complete — P1: 42/42, P2: 20/20, total 62/62 tasks
- 15 MCP tools, 30+ REST endpoints, Evolution Engine + OWM 5 memory types

## Compact Instructions

When compacting, preserve: docs/ROADMAP.md progress, key design decisions (LLM validation, UTC enforcement, platform-agnostic core), current task progress, security rules, lessons learned, rules.
