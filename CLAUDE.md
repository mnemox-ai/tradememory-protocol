# TradeMemory Protocol — Claude Code 指令

## 專案概述

TradeMemory Protocol 是 Mnemox AI 的核心產品。MT5/forex 交易記憶層，3 層架構（L1 原始交易 → L2 模式發現 → L3 策略調整），MCP server。

- GitHub: mnemox-ai/tradememory-protocol
- PyPI: tradememory-protocol
- 版本: v0.5.0
- Tests: 1055 tests passing
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
- [2026-03-16] RESEARCH_LOG.md finalized: 10 experiments, model comparison table (Haiku vs Sonnet), pattern library, strategy graveyard
- [2026-03-16] Evolution robustness: P0 parser (Haiku format), P1 min bars, P2 Sharpe guard. Binance live test passed (2160 bars, 2 graduated). 1055 tests
- [2026-03-16] **v0.5.0 Release** — Evolution Engine + OWM Completion. 1026 tests, all 12 phases complete
- [2026-03-16] Phase 8: OWM Decay + Auto-induction + CUSUM drift + Affective EWMA + Prospective feedback (6 tasks, 78 new tests)
- [2026-03-16] Phase 10: Evolution Engine Core — models, vectorized backtester, generator, selector, orchestrator (5 tasks, 147 new tests)
- [2026-03-16] Phase 11: Evolution MCP Tools — 5 MCP tools + 4 REST endpoints + Pydantic models (6 tasks, 36 new tests)
- [2026-03-16] Phase 12: Integration — evolution demo, dashboard evolution page, research log (3 tasks, 21 new tests)
- [2026-03-16] Import fix: 180+ `from src.tradememory` → `from tradememory`
- [2026-03-15] Phase 9: DataSource Protocol + Binance + Context Builder + MT5 CSV (4 tasks, 144 new tests)
- [2026-03-15] 修復 mt5_sync_v3.py 關鍵 bug：DELETE open_positions 在 sync 前執行導致資料遺失
- [2026-03-15] 建立 Jarvis 系統：/morning 每日掃描、/wrap-up session handoff

## Current Status
- **v0.5.0**, 1055 tests passing, 1 skipped
- **All 12 phases complete** — P1: 42/42, P2: 20/20, total 62/62 tasks
- Evolution Engine: discover → hypothesize → backtest → select → evolve (LLM-powered)
- OWM 5 memory types fully implemented (episodic, semantic, procedural, affective, prospective)
- 15 MCP tools, 30+ REST endpoints
- MT5 Sync V3 running, 14 trades, PnL +$2,200

## Compact Instructions

When compacting, preserve: ROADMAP.md progress, key design decisions (LLM validation, UTC enforcement, platform-agnostic core), current task progress, security rules, lessons learned, rules.
