# TradeMemory Protocol — Claude Code 指令

## 專案概述

TradeMemory Protocol 是 Mnemox AI 的核心產品。MT5/forex 交易記憶層，3 層架構（L1 原始交易 → L2 模式發現 → L3 策略調整），MCP server。

- GitHub: mnemox-ai/tradememory-protocol
- PyPI: tradememory-protocol
- 版本: v0.5.1
- Tests: 1293 tests passing (1233 + 60 strategy validator)
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
- FastAPI REST server：`src/tradememory/server.py`（35+ REST endpoints）
- MT5 同步：`docs/MT5_SYNC_SETUP.md` + `scripts/mt5_sync.py`
- 每日反思：`scripts/daily_reflection.py`
- Demo：`src/tradememory/demo.py`（`tradememory demo [--fast]`，30 筆模擬交易跑完整 L1→L2→L3 pipeline）
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

## Recent Changes (latest 10)
- [2026-04-09] feat: [Phase 3] Agent Simulation Framework — BaseAgent/CalibratedAgent A/B, ABExperiment IS/OOS, 4-variant ablation, 3 preset strategies, ExperimentRunner, 10 tests
- [2026-04-09] fix: DQS continuous scoring (was discrete), CUSUM complementary detector, 4-tier system (go/proceed/caution/skip)
- [2026-04-09] feat: [Phase 1] Bayesian Online Changepoint Detection — Adams & MacKay 2007 BOCPD, Beta-Bernoulli + NIG conjugate models, DB persistence, integrated into semantic update flow, 8 tests
- [2026-04-09] feat: [Phase 2] Decision Quality Score — 5-factor process-oriented pre-trade evaluation + compute_dqs MCP tool + calibrate() + 10 tests
- [2026-04-08] **深度重構 — 審計行動計劃全部完成**：
  - Phase A: 刪除 store_trade_memory + recall_similar_trades（19→17 tools），修正行銷語言，加 Research Status
  - Phase B: 記憶層互通 — Semantic 讀 Episodic（drift detection >15%），Procedural 補完（hold time, Kelly, disposition），Affective 讀 Procedural（behavioral risk adjustment）
  - Phase C: db.py 錯誤處理改 raise TradeMemoryDBError（18→2 個 return False），加 get_connection context manager
  - Phase D: 12 property-based tests (hypothesis) + 5 integration tests（no mocks）
  - Phase E: 4 ADR + OWM 技術文章草稿
- [2026-04-05] docs: README 商業化重寫 — hook + pricing + enterprise section + use cases + getting started 雙軌
- [2026-04-04] feat: Decision Legitimacy Gate — 5-factor pre-trade confidence check
- [2026-04-04] feat: ΔS Context Drift Monitor — Jaccard-based drift scoring on recall tools
- [2026-04-03] feat: Strategy Validator Claude Code skill — Layer 2 product
- [2026-04-02] feat: validate_strategy MCP tool — DSR + Walk-Forward + Regime + CPCV
- [2026-03-30] fix: P0 trust sprint — tool names 對齊, tutorial imports, demo CLI
- [2026-03-27] release: v0.5.1 bump + GitHub Release
- [2026-03-27] fix: pipeline P0-P2 — strategy_map, TDR JSONL path
- [2026-03-25] feat: Phase 0+2 complete — enriched sync pipeline + TDR audit schema

## Current Status
- **v0.5.1** — PyPI + GitHub Release 已發（2026-03-27）
- **1370 tests passing** (1253 + 60 strategy validator + 11 legitimacy + 12 property-based + 5 integration + 10 DQS + 8 changepoint + 10 simulation - 9 removed), 1 skipped
- **18 MCP tools** (+compute_dqs), 35+ REST endpoints
- **Agent Simulation Framework**: BaseAgent vs CalibratedAgent A/B, IS/OOS walk-forward, 4-variant ablation, 3 preset strategies, full experiment runner
- **Bayesian Changepoint Detection**: BOCPD + CUSUM complementary detector, 4 behavioral signals, DB-persisted, cusum_alert in ChangePointResult
- **DQS Engine**: 5 continuous factors + 4-tier system (go/proceed/caution/skip) + calibrate() + integrated into remember_trade
- **5 層記憶真正互通**：Semantic↔Episodic（drift detection → BOCPD），Procedural（hold time/Kelly/disposition），Affective←Procedural（behavioral risk）
- **db.py 重構**：TradeMemoryDBError 階層 + get_connection() context manager + 18→2 return False
- **4 ADR** in docs/adr/ — OWM scoring, SQLite, MCP protocol, Evolution gates
- **OWM 技術文章**草稿 in docs/research/owm-technical-article.md
- **Strategy Validator 三層完成**：L1 MCP Tool + L2 Claude Code Skill + L3 Web UI (mnemox.ai/validate)
- **PR #2 open** — ElishaKay: Fronteir AI hosted deployment link（外部貢獻，待 review）
- **Uncommitted** — `scripts/mt5_sync_v3.py` close retry 邏輯
- **CHANGELOG** — 停在 v0.5.0，v0.5.1 section 未寫
- **Waiting on**: NG_Gold demo 交易數據、anti-resonance PyPI publish
- **方向**: Trading AI Service 接案→數據驗證→SaaS
- **行銷啟動（2026-04-05）**：README CTA、Reddit 草稿、Demo Video 腳本、Awesome-list 指南

## Compact Instructions

When compacting, preserve: docs/ROADMAP.md progress, key design decisions (LLM validation, UTC enforcement, platform-agnostic core), current task progress, security rules, lessons learned, rules.
