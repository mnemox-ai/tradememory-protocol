# TradeMemory Protocol — 開發路線圖

## 執行說明

這是 Mnemox AI 的主線開發計畫。Claude Code 每次開新 session 時讀取此檔案，找到第一個 ❌ 任務繼續執行。完成後標記 ✅ 並 commit。

**驗證條件**：每個任務完成後必須通過 `python -m pytest tests/ -v`

---

## Phase 1：OpenClaw Skill 包裝 ✅

### Task 1.1：建立 SKILL.md ✅
- 在 `.skills/tradememory/` 建立 SKILL.md
- 遵循 OpenClaw skill 標準 YAML frontmatter
- 包含：Overview、Installation、Available Commands（6 個自然語言指令範例）、3-Layer Architecture 說明、Daily Reflection Setup、Hosted API teaser
- 參考格式：https://github.com/openclaw/skills
- Commit: `feat: add OpenClaw skill packaging (SKILL.md)` → `6e13532`

### Task 1.2：建立安裝腳本 ✅
- `.skills/tradememory/scripts/install.sh`：自動安裝 tradememory-protocol + 依賴
- `.skills/tradememory/scripts/setup_mt5.sh`：互動式引導 MT5 同步設定
- Commit: 同 `6e13532`（與 Task 1.1 合併 commit）

### Task 1.3：更新 README — Claude Desktop 整合 ✅
- README.md Quick Start 已以 Claude Desktop 為首
- Claude Code（`claude mcp add` 指令）已有
- OpenClaw skill 區塊已加入
- Works with badge 已有：Claude Desktop · Claude Code · Cursor · Windsurf · any MCP client
- Commit: `6e13532`

### Task 1.4：更新 Idea Reality Check README ✅
- idea-reality-mcp README 已有 Claude Desktop config 範例
- Claude Code 整合指令已有
- Works with badge 已有
- 無需額外修改

---

## Phase 2：Landing Page + Pricing（本週）

### Task 2.1：建立 TradeMemory Landing Page ✅
- 在 mnemox.ai repo 建立 /tradememory 頁面
- Hero section：「AI Trading Memory for MT5/Forex Traders」
- 功能展示：3-Layer Memory、AI Reflection、Pattern Discovery、Daily Reports
- 示範 GIF 或截圖（可以先用 placeholder）
- Claude Desktop 整合說明
- Commit: `feat: add TradeMemory landing page` → `95cd5a7`

### Task 2.2：建立 Pricing Page ✅
- 在 landing page 下方加入 Pricing section
- 三個方案：Trader $29/月、Pro $79/月、Fund $299/月
- Credit 制 pay-as-you-go 選項（Starter/Growth/Scale packs）
- 「Coming Soon」標記（Hosted API 還沒建好）
- 早鳥註冊表單（收集 email，50% off 前 3 個月）
- Commit: `feat: add pricing page` → `2e28b65`（mnemox-ai.github.io repo）

---

## Phase 3：社群推廣素材（本週）

### Task 3.1：撰寫 Forex Factory 推廣帖 ✅
- 在 repo 建立 `marketing/forex-factory-post.md`
- 標題、內容、截圖說明
- 重點：「First AI trading memory for MT5」
- 語調：交易者對交易者，不是工程師對工程師
- Commit: `docs: add Forex Factory promotional content`

### Task 3.2：撰寫 Reddit/MQL5 推廣帖 ✅
- `marketing/reddit-post.md`
- `marketing/mql5-post.md`
- 每個平台語調略有不同
- Commit: `docs: add Reddit and MQL5 promotional content`

### Task 3.3：撰寫 demo 腳本 ✅
- `marketing/demo-script.md`
- 影片示範的步驟腳本（2-3 分鐘）
- 場景：打開 Claude Desktop → 問交易績效 → 跑 reflection → 收到報告
- Commit: `docs: add demo video script`

---

## Phase 4：Hosted API MVP（本月）

### Task 4.1：設計 API 架構 ✅
- `docs/hosted-api-spec.md`
- REST API 端點定義（L1 store/recall、performance、reflection、L2 patterns、L3 adjustments）
- 認證方式（API Key：`tm_live_*` / `tm_test_*`）
- Rate limiting（sliding window per plan）
- 定價邏輯（Free/Trader/Pro/Fund 月費 + Starter/Growth/Scale credit packs）
- Commit: `docs: add hosted API specification`

### Task 4.2：建立 FastAPI server ✅
- `hosted/server.py`
- 實作基本端點：store_trade、recall_trades、get_performance
- API key 認證（Bearer tm_live_* / tm_test_*）
- SQLite 儲存（account isolation）+ 22 tests
- Commit: `feat: add hosted API server (MVP)` → `1ef9e23`

### Task 4.3：部署到 mcp.mnemox.ai ✅
- Dockerfile（hosted API + HEALTHCHECK）
- docker-compose.yml（API + Caddy reverse proxy, auto-TLS）
- Caddyfile（mcp.mnemox.ai domain config）
- 部署文件（docs/deployment.md）
- Health check endpoint（`/api/v1/health`，已有）
- Commit: `feat: add deployment configuration`

---

## Phase 5：AI Agent Payment Rails 卡位（本月，P2）

### Task 5.1：建立 agent-payment-rails repo ✅
- 在 mnemox-ai org 建立新 repo
- README：願景、定位（Stripe for AI Agents）、與 MeshCore 差異
- Repo: https://github.com/mnemox-ai/agent-payment-rails
- Commit: `feat: initial repo with vision document` → `f87eafc`

### Task 5.2：撰寫 MVP Spec ✅
- `docs/mvp-spec.md`
- Stripe integration plan
- Agent wallet 概念
- Fiat on/off-ramp 流程
- Commit: `docs: add MVP specification` → `4d2339c`

---

## Phase 6：OWM Architecture（Outcome-Weighted Memory） ✅

### Task 6.1：OWM 理論框架 ✅
- `docs/OWM_FRAMEWORK.md`（1,875 行完整規格）
- 5 記憶類型定義（Episodic / Semantic / Procedural / Affective / Prospective）+ 核心公式推導 + 邊界條件 + 收斂性證明
- 金融驗證（ACT-R + Kelly + Bayesian + Prospect Theory + HMM，20+ 參考文獻）
- Commit: `ba10b5a`

### Task 6.2：OWM 實作 ✅
- 5 個 OWM 模組（`src/tradememory/owm/`：context.py / recall.py / kelly.py / migration.py / __init__.py）
- db.py 擴充（5 張新表 + CRUD 方法）
- mcp_server.py 擴充（4 原有 tool 升級 + 6 新 tool = 10 total）
- server.py 擴充（7 個新 REST endpoint）
- 196 新 tests（399 total, 0 failures）
- Commit: `ba10b5a`

---

## Phase 7：Trading Intelligence Dashboard ✅

全端 dashboard，視覺化 OWM 記憶系統、交易績效、策略分析。

### Task 7.1：Docker + PostgreSQL + Alembic ✅
- PostgreSQL 容器（docker-compose.yml）+ SQLAlchemy 2.0 async
- Alembic migration（recall_events 表）
- database.py + db_models.py（JSONB, TIMESTAMPTZ）

### Task 7.2：Scaffold Vite + React + TypeScript ✅
- dashboard/ 目錄結構（api/components/pages/theme/mock/hooks/utils）
- vite.config.ts + proxy 設定 + react-router-dom

### Task 7.3：Mnemox Design System ✅
- CSS variable design tokens（dark mode only）
- PageShell + Sidebar + Nav 佈局組件
- CSS Module，無 inline style，無固定 px 寬度

### Task 7.4：Core Dashboard API ✅
- 分層架構：dashboard_api.py → services/dashboard.py → repositories/trade.py
- Pydantic response models（dashboard_models.py）
- CORS middleware + 自定義例外

### Task 7.5：Time Series + Memory Growth API ✅
- /dashboard/equity-curve、/dashboard/rolling-metrics、/dashboard/memory-growth
- SQLAlchemy ORM 查詢 + Service 層計算邏輯

### Task 7.6：Intelligence + Strategy API ✅
- /dashboard/intelligence/*（OWM score trend、confidence calibration、resonance）
- /dashboard/strategies/{name}（heatmap、adjustment timeline）

### Task 7.7：Reflections + Beliefs + Dreams API ✅
- /dashboard/reflections、/dashboard/beliefs、/dashboard/dreams
- Markdown 解析 + Bayesian confidence 計算

### Task 7.8：Mock Data + API Layer ✅
- SWR hooks（useOverview, useEquityCurve 等）
- VITE_USE_MOCK=true 切換 mock/API
- TypeScript types 對應後端 Pydantic models

### Task 7.9：Overview Page ✅
- MetricCard 組件 + EquityCurveChart（.tsx + .web.tsx 分離）
- Loading skeleton + Error state + Empty state

### Task 7.10：Intelligence Page ✅
- MemoryGrowth、OWMScoreTrend、ConfidenceCalibration、ResonanceGauge
- BayesianBeliefs card + responsive 2-column grid

### Task 7.11：Strategies Page ✅
- Tab 切換（VolBreakout/IntradayMomentum/Pullback）
- StrategyHeatmap + AdjustmentTimeline + monospace 數字

### Task 7.12：Reflections + Dreams Pages ✅
- ReflectionCard + DreamComparison chart
- react-markdown 渲染 + 引導文字 empty state

### Task 7.13：Responsive + Loading + Error States ✅
- 三斷點（640/1024/1025+）+ mobile hamburger menu
- Skeleton shimmer animation + Error retry 按鈕

### Task 7.14：Animations + Tooltips + CSV Export ✅
- IntersectionObserver scroll-reveal + CSS transitions
- ChartTooltip + CSV export utility function

### Task 7.15：Build Integration + Static Serving ✅
- Vite build → dashboard/dist/
- FastAPI static file mount（/assets + SPA catch-all）
- catch-all 排除所有 API prefix
- 576 tests passing，向後相容

---

---

## Phase 8：OWM Completion（補完五種記憶類型） ✅

填補 OWM 已設計但尚未實作的缺口。每項都有 OWM_FRAMEWORK.md 的數學定義。

### Task 8.1：Episodic Memory Decay ✅
- 實作 S(t) = S₀ × (1 + t/τ)^(-d) × boost(n) 衰減函數
- τ=30d, d=0.5, rehearsal boost = 1 + 0.3×ln(1+n)
- recall 時自動計算 current_strength，低於閾值的自動標記 dormant
- 測試：衰減曲線、rehearsal boost、邊界值

### Task 8.2：Semantic Memory Bayesian Update ✅
- Bayesian posterior Beta(α,β) 更新：α += outcome, β += (1-outcome)
- regime_match_factor：不同市場狀態下的語義記憶權重
- τ=180d, d=0.3 衰減（比 episodic 慢）
- 測試：posterior 收斂、regime 切換

### Task 8.3：Auto-Induction ✅
- 從 episodic patterns 自動產生 semantic memory（check_auto_induction）
- 測試：auto-induction trigger、pattern aggregation

### Task 8.4：Procedural Memory Drift Detection ✅
- CUSUM (Cumulative Sum) drift detection 實作（cusum_drift_detect）
- 追蹤 behavioral stats：avg holding time, SL/TP ratio, disposition effect
- 當 drift 超過閾值時，自動觸發 L3 adjustment review
- 測試：drift detection 敏感度、false positive rate

### Task 8.5：Affective State EWMA ✅
- EWMA confidence: C(t) = λ×C(t-1) + (1-λ)×outcome, λ=0.9
- risk_appetite = max(0.1, 1 - (dd/max_dd)²)
- 連動 Kelly criterion position sizing
- 測試：EWMA 收斂、drawdown 風控、Kelly 計算

### Task 8.6：Prospective Memory Trigger Evaluation ✅
- 條件計畫的 trigger 匹配引擎（evaluate_trigger, record_outcome）
- 每次新交易進來時，檢查所有 active plans 的 trigger 條件
- 命中時自動建立 notification（不自動執行）
- outcome tracking：plan 的預測 vs 實際結果
- 測試：trigger 匹配、多條件 AND/OR、outcome tracking

---

## Phase 9：Platform-Agnostic Data Layer

進化引擎的數據基礎。DataSource Protocol + Binance/MT5 adapter。

### Task 9.1：DataSource Protocol ✅
- `src/tradememory/data/` 模組：OHLCV model、Timeframe enum、OHLCVSeries
- DataSource Protocol（runtime_checkable）：fetch_ohlcv(), available_symbols()
- Exception hierarchy：DataSourceError → RateLimitError / SymbolNotFoundError
- OHLCVSeries.split() for IS/OOS validation
- 27 tests passing

### Task 9.2：Binance Historical Data Adapter ✅
- `src/tradememory/data/binance.py`：實作 DataSource Protocol
- Binance REST API /klines endpoint（無需 API key for public data）
- Rate limiting（respect 1200 req/min）
- Local parquet cache（~/.tradememory/cache/binance/）
- async httpx client
- 測試：mock API response、cache hit/miss、rate limit handling

### Task 9.3：Context Builder ✅
- 從 OHLCVSeries 計算 ContextVector（for OWM recall）
- 指標：ATR, trend direction, volatility regime, time-of-day bucket
- Pure function，不依賴外部狀態
- 測試：各指標計算、邊界值

### Task 9.4：MT5 CSV Adapter ✅
- Wrap 現有 `replay/data_loader.py` 的 `parse_mt5_csv()` into DataSource Protocol
- 讀取本地 CSV 檔案，轉換為 OHLCVSeries
- 測試：CSV 解析、tab/comma auto-detect

---

## Phase 10：Evolution Engine Core

自動化的觀察→假說→回測→淘汰 loop。`src/tradememory/evolution/` 獨立模組。

### Task 10.1：Evolution Models + Pattern Discovery ✅
- `src/tradememory/evolution/` 模組：LLMClient Protocol, AnthropicClient, MockLLMClient
- CandidatePattern（structured JSON schema）, Hypothesis lifecycle, FitnessMetrics, EvolutionRun
- Pattern discovery: LLM-powered with prompt templates, graveyard avoidance
- Mutation: generate variations of promising hypotheses
- 49 tests (mock LLM, no real API calls) + 1 integration test (@pytest.mark.integration)

### Task 10.2：Vectorized Backtester ✅
- `src/tradememory/evolution/backtester.py`
- Pure Python vectorized backtester（擴展 replay/ 概念）
- 輸入：OHLCVSeries + Hypothesis → FitnessMetrics
- 支援 long/short、SL/TP、time-based exit
- 不用外部 backtest library（保持輕量）
- 測試：known-outcome trades、edge cases

### Task 10.3：Hypothesis Generator ✅
- `src/tradememory/evolution/generator.py`
- LLM-powered（Sonnet）：給定 OHLCVSeries 統計摘要，產生交易假說
- Prompt engineering：結構化輸出（JSON schema）
- Temperature 控制：exploration vs exploitation
- 測試：mock LLM response、schema validation

### Task 10.4：Selection & Elimination ✅
- `src/tradememory/evolution/selector.py`
- IS fitness → 排名 → top N 進 OOS validation
- OOS validation：Sharpe > 1.0, trade_count > 30, max_dd < 20%
- 存活策略 → OWM semantic memory（auto-induction）
- 淘汰策略 → Strategy Graveyard（保留學習）
- 測試：selection 邏輯、OOS filter、edge cases

### Task 10.5：Evolution Orchestrator ✅
- `src/tradememory/evolution/engine.py`
- 完整 loop：fetch data → generate hypotheses → backtest IS → select → validate OOS → store
- Configurable：generations, population_size, mutation_rate
- 結果寫入 OWM：semantic（pattern）、prospective（plan）
- 測試：end-to-end with mock data

---

## Phase 11：Evolution MCP Tools ✅

讓 AI agent 透過 MCP 觸發和監控進化。

### Task 11.1：fetch_market_data MCP Tool Function ✅
- DataSource Protocol 整合到 MCP context
- 測試：mock data fetch

### Task 11.2：discover_patterns MCP Tool Function ✅
- LLM-powered pattern discovery via MCP
- 測試：mock LLM response

### Task 11.3：run_backtest MCP Tool Function ✅
- Backtest execution via MCP interface
- 測試：mock backtest run

### Task 11.4：evolve_strategy MCP Tool ✅
- 新 MCP tool：觸發一輪進化
- 參數：symbol, timeframe, generations, population_size
- 回傳：top strategies + fitness metrics
- 測試：tool schema、mock evolution run

### Task 11.5：get_evolution_log MCP Tool ✅
- 查詢進化歷史 + 策略墓園
- 用於 LLM 學習「什麼不 work」
- 測試：log query、graveyard query

### Task 11.6：Evolution REST Endpoints + Pydantic Models ✅
- 5 MCP tools + 4 REST endpoints + 3 Pydantic models
- POST /evolution/run — 觸發進化
- GET /evolution/runs — 列出歷史 run
- GET /evolution/runs/{id} — 單次 run 詳情
- GET /evolution/graveyard — 策略墓園
- 測試：API endpoints、model validation

---

## Phase 12：Integration & Validation ✅

端對端整合 + P1 結果復現。

### Task 12.1：Evolution Demo Script ✅
- Mock BTC 1H data + 3-generation evolution + text equity curve
- 驗證引擎能自動發現正期望值策略
- 12 new tests

### Task 12.2：Dashboard Evolution Page ✅
- Surviving/graveyard tables, fitness trend, run summary
- Dashboard 整合進化引擎視覺化
- 9 new tests

### Task 12.3：Research Log Auto-Write ✅
- research_log.py auto-write（EXP-00X format）
- 進化結果自動寫入研究日誌
- Documentation updates

---

## Phase 13：Statistical Validation ✅

確保 Evolution Engine 發現的策略有真正的 edge，不是隨機噪音。

### Task 13.1：Random Baseline Generator ✅
- `scripts/research/random_baseline_demo.py`：合成 OHLCV + 200 random strategies + percentile ranking
- 函數：generate_random_ohlcv, compute_sharpe, random_strategy_sharpe, run_random_baseline, percentile_rank
- Demo：Strategy C (Sharpe 2.0) vs random distribution

### Task 13.2：Random Baseline Tests ✅
- Unit tests for all baseline functions
- Edge cases: empty data, zero-std returns, boundary percentiles

### Task 13.3：Validation Results Template ✅
- `VALIDATION_RESULTS.md`：4-step validation framework
- Step 1 Random Baseline / Step 2 Walk-Forward / Step 3 Time Bias / Step 4 Extended OOS
- Placeholder for real Binance data results

### Task 13.4：Demo Script ✅
- `scripts/research/random_baseline_demo.py` with `if __name__=="__main__"`
- Prints distribution stats (mean, std, p5, p50, p95) + Strategy C ranking + pass/fail

---

## Phase 14：Cross-Asset Validation ✅

### Task 14.1：B1 Stability Test ✅
- CONDITIONAL PASS — Strategy E stability across multiple runs
- Report: `validation/b1_stability_report.md`

### Task 14.2：B2 Cross-Asset Transfer ✅
- PASS — Strategy E transferred to ETHUSDT (P100)
- Report: `validation/b2_transfer_report.md`

---

## Phase 15：Re-Evolution Validation ✅ (STOP)

### Task 15.1：Batch A — Statistical Gates ✅
- `regime_detector.py` + `statistical_gates.py` — 46 tests
- Regime Decay Detector: triple-confirmation (Bayesian + DD + Mahalanobis OOD)
- Commit: `3f96b6a`

### Task 15.2：Batch B — Grid WFO ✅
- `re_evolution.py` + `strategy_registry.py` + `run_grid_wfo.py` — 45 tests
- **Layer 1 Gate: FAIL (3/3)** — DSR 0/23 pass
- Root cause: M=19,200 + 30-50 trades = mathematically impossible
- Report: `validation/reevolution_report.md`

### Task 15.3：Batch C — LLM vs Grid H2H ✅ (STOP)
- `run_llm_wfo.py` + `run_llm_step0.py`
- **Layer 2 Gate: FAIL (2/3)** — Cohen's d=0.000, graduation rate=0%
- Structural novelty confirmed (LLM used 6 features outside grid space)
- **Conclusion**: 1H timeframe + 3mo window 交易數不夠通過 DSR gate。瓶頸是 trade count，不是 search method。Evolution Engine 驗證延後到更高頻設定。

---

## Post-ROADMAP：Compliance & Trust Sprint ✅

### Phase 0：Enriched Sync Pipeline ✅ (2026-03-25)
- EventLogReader, dynamic confidence, pnl_r, exit reasoning, references, regime context
- mt5_sync_v3.py 全面升級
- 17 new tests, 1199 total

### Phase 2：TDR Audit Schema ✅ (2026-03-25)
- `domain/tdr.py` (MiFID II / EU AI Act inspired)
- 4 REST endpoints + 2 MCP tools (export_audit_trail, verify_audit_hash)
- SHA256 tamper detection
- 15 new tests, 1214 total

### Phase 3：Open Source Materials — PARTIAL
- TDR Spec v1.0 ✅ (`docs/TDR_SPEC_v1.md`)
- anti-resonance v0.2.0 code ✅ — **PyPI publish pending**
- MQL5 article DRAFT — blocked on Phase 1 real data
- Blog post — blocked on Phase 1 real data

### Trust Sprint (2026-03-27 ~ 03-30) ✅
- README 重寫 — audit + memory dual core positioning
- DecisionLogReader — JSONL decision context for rich reasoning
- Pipeline fixes — strategy_map, TDR JSONL path, corruption handler
- v0.5.1 bump + GitHub Release
- P0 trust sprint — tool names alignment, tutorial imports, demo CLI, dead code cleanup
- 1233 tests, CI green

---

## 待處理（Pending Items）

| # | 項目 | 狀態 | 備註 |
|---|------|------|------|
| 1 | ~~v0.5.1 PyPI publish~~ | ✅ 已發 | PyPI + GitHub Release 2026-03-27 |
| 2 | PR #2 (Fronteir AI hosted) | 🔍 待 review | ElishaKay 外部貢獻，README 加 hosted link |
| 3 | mt5_sync_v3 close retry 邏輯 | 🔧 未 commit | 5 次重試 + abandon，改善 closed trade sync 穩定性 |
| 4 | CHANGELOG v0.5.1 | ❌ 未寫 | CHANGELOG.md 停在 v0.5.0 |
| 5 | Phase 1 Real Data | ⏳ 等數據 | NG_Gold demo running，等 4-6 週交易數據 |
| 6 | anti-resonance PyPI | ❌ 未 publish | v0.2.0 code done in separate repo |
| 7 | MQL5 article Section 6 | ⏳ blocked | 等 Phase 1 real data |
| 8 | PDF Report (Phase 2.5) | 🔄 DEFERRED | Sean 決策延後 |
| 9 | Live Executor monitoring | ⚠️ 無 alert | GH Actions 每小時跑 Strategy E，但無失敗通知 |

---

## 進度追蹤

| Phase | 狀態 | 完成日期 |
|-------|------|----------|
| Phase 1：OpenClaw Skill | ✅ 完成 | 2026-03-03 |
| Phase 2：Landing Page | ✅ 完成 | 2026-03-03 |
| Phase 3：推廣素材 | ✅ 完成 | 2026-03-03 |
| Phase 4：Hosted API | ✅ 完成 | 2026-03-03 |
| Phase 5：Payment Rails | ✅ 完成 | 2026-03-03 |
| Phase 6：OWM Architecture | ✅ 完成 | 2026-03-05 |
| Phase 7：Trading Intelligence Dashboard | ✅ 完成 | 2026-03-11 |
| Phase 8：OWM Completion | ✅ 完成 | 2026-03-16 |
| Phase 9：Data Layer | ✅ 完成 | 2026-03-15 |
| Phase 10：Evolution Engine | ✅ 完成 | 2026-03-16 |
| Phase 11：Evolution MCP Tools | ✅ 完成 | 2026-03-16 |
| Phase 12：Integration & Validation | ✅ 完成 | 2026-03-16 |
| Phase 13：Statistical Validation | ✅ 完成 | 2026-03-17 |
| Phase 14：Cross-Asset Validation | ✅ 完成 | 2026-03-19 |
| Phase 15：Re-Evolution | ✅ STOP | 2026-03-21 |
| Post：Compliance & Trust | ✅ 完成 | 2026-03-30 |
