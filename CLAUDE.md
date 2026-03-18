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

1. 開始新 session 時，先讀 ROADMAP.md 確認當前進度
2. 找到第一個未完成（❌）的任務
3. 執行該任務
4. 跑 tests 驗證
5. Commit + push
6. 在 ROADMAP.md 標記 ✅
7. 繼續下一個任務
8. 如果 context 快滿了，先更新 ROADMAP.md 進度，然後結束 session

## 重要文件位置

- MCP tools 定義：`src/tradememory/mcp_server.py`（4 個 MCP tools：store/recall/performance/reflection）
- FastAPI REST server：`src/tradememory/server.py`（30+ REST endpoints）
- MT5 同步：`docs/MT5_SYNC_SETUP.md` + `scripts/mt5_sync.py`
- 每日反思：`scripts/daily_reflection.py`
- Demo：`scripts/demo.py`（30 筆模擬交易跑完整 L1→L2→L3 pipeline）
- 測試：`tests/`
- OpenClaw Skill：`.skills/tradememory/SKILL.md`
- 開發路線圖：`ROADMAP.md`

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

## Current Status
- **v0.5.0**, 1087 tests passing, 2 skipped
- **Live Dashboard Session 1 COMPLETE**: executor + export + seed + GH Actions all working
- **Phase 13 COMPLETE** -- 4 steps done. E has real edge in 2024-2026 (P100%, walk-forward 3.24). Both FAIL extended OOS (regime-specific). Conclusion: Evolution Engine finds real patterns, but they need periodic re-evolution.
- **Phase 13 Step 1 PASS** -- Strategy C (Sharpe=3.40, P96.9%) and E (Sharpe=4.42, P100%) beat 1000 random strategies
- **All 12 phases complete** — P1: 42/42, P2: 20/20, total 62/62 tasks
- GitHub Release v0.5.0 已建立，Org profile + 3 產品卡片上線
- 15 MCP tools, 30+ REST endpoints, Evolution Engine + OWM 5 memory types
- mnemox.ai 網站已更新（Evolution Engine + SEO metadata）
- 全文件一致性掃描完成，所有 src.tradememory.server 引用已清除
- MT5 Sync V3 running, 14 trades, PnL +$2,200

## Compact Instructions

When compacting, preserve: ROADMAP.md progress, key design decisions (LLM validation, UTC enforcement, platform-agnostic core), current task progress, security rules, lessons learned, rules.
