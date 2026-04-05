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
- [2026-04-05] docs: README 商業化重寫 — hook + pricing + enterprise section + use cases + getting started 雙軌
- [2026-04-04] feat: Decision Legitimacy Gate — 5-factor pre-trade confidence check（sample sufficiency, memory quality, regime confidence, streak, drawdown）。新 MCP tool check_trade_legitimacy + owm/legitimacy.py。11 new tests（1324 total）。
- [2026-04-04] feat: ΔS Context Drift Monitor — Jaccard-based drift scoring on recall tools。每筆 recalled memory 加 context_drift {delta_s, zone, warning} + drift_summary。20 new tests（1313 total）。
- [2026-04-03] feat: Strategy Validator Claude Code skill — Layer 2 product，5-step rigid workflow，plain-language 解釋四層驗證。
- [2026-04-02] feat: validate_strategy MCP tool — DSR + Walk-Forward + Regime + CPCV 四層統計驗證。支援 QuantConnect CSV + returns CSV。60 new tests。自帶法規免責聲明。
- [2026-03-30] fix: P0 trust sprint — tool names 對齊, tutorial imports, demo CLI, dead code cleanup。1233 tests。
- [2026-03-30] docs: ROADMAP 更新 — 補齊 Phase 14-15 + Post-ROADMAP compliance sprint + 待處理清單
- [2026-03-27] docs: README 重寫 — audit + memory 雙核心定位
- [2026-03-27] release: v0.5.1 bump + GitHub Release（PyPI publish 待確認）
- [2026-03-27] fix: pipeline P0-P2 — strategy_map, TDR JSONL path, corruption handler
- [2026-03-27] feat: DecisionLogReader — JSONL decision context for rich reasoning
- [2026-03-25] feat: Phase 0+2 complete — enriched sync pipeline + TDR audit schema
- [2026-03-25] security: path traversal, audit hash, recall_events, bind local
- [2026-03-21] Phase 15 Batch C STOP — LLM WFO Cohen's d=0.000, graduation rate=0%
- [2026-03-21] Phase 15 Batch A+B — statistical gates + grid WFO, DSR 0/23 FAIL

## Current Status
- **v0.5.1** — PyPI + GitHub Release 已發（2026-03-27）
- **1324 tests passing** (1253 + 60 strategy validator + 11 legitimacy), 2 skipped（最後 push `0fd4a84` 2026-04-04）
- **Strategy Validator 三層完成**：L1 MCP Tool + L2 Claude Code Skill + L3 Web UI (mnemox.ai/validate)
- **Live Executor** — GH Actions 每小時跑 Strategy E paper trading，最近 run 全 success
- **PR #2 open** — ElishaKay: Fronteir AI hosted deployment link（外部貢獻，待 review）
- **Uncommitted** — `scripts/mt5_sync_v3.py` close retry 邏輯（5 次重試 + abandon）
- **CHANGELOG** — 停在 v0.5.0，v0.5.1 section 未寫
- **19 MCP tools** (新增 check_trade_legitimacy), 35+ REST endpoints, Evolution Engine + OWM 5 memory types
- **All ROADMAP phases complete** — Phase 1-13 ✅ + Phase 14-15 ✅(STOP) + Trust Sprint ✅
- **Waiting on**: NG_Gold demo 交易數據（Phase 1 Real Data Validation）、anti-resonance PyPI publish
- **Strategic pivot**: OWM = free infra, Evolution Engine = paid product (pending validation at higher frequency)
- **方向**: Trading AI Service 接案→數據驗證→SaaS（等 NexusOS 完成後啟動）
- **README 重寫完成**：商業定位（hook + pricing Free/$29/Enterprise + use cases + getting started 雙軌）。舊 README 備份在 docs/README_OLD_2026-04-05.md
- **P1 待做**：README_ZH.md 中文版更新、mnemox.ai/tradememory landing page

## Compact Instructions

When compacting, preserve: docs/ROADMAP.md progress, key design decisions (LLM validation, UTC enforcement, platform-agnostic core), current task progress, security rules, lessons learned, rules.
