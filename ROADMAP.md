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

### Task 4.1：設計 API 架構 ❌
- `docs/hosted-api-spec.md`
- REST API 端點定義
- 認證方式（API Key）
- Rate limiting
- 定價邏輯（credit 制 + 月費制）
- Commit: `docs: add hosted API specification`

### Task 4.2：建立 FastAPI server ❌
- `hosted/server.py`
- 實作基本端點：store_trade、recall_trades、get_performance
- API key 認證
- SQLite → PostgreSQL migration plan
- Commit: `feat: add hosted API server (MVP)`

### Task 4.3：部署到 mcp.mnemox.ai ❌
- Dockerfile
- docker-compose.yml
- 部署文件
- Health check endpoint
- Commit: `feat: add deployment configuration`

---

## Phase 5：AI Agent Payment Rails 卡位（本月，P2）

### Task 5.1：建立 agent-payment-rails repo ❌
- 在 mnemox-ai org 建立新 repo
- README：願景、定位（Stripe for AI Agents）、與 MeshCore 差異
- Commit: `feat: initial repo with vision document`

### Task 5.2：撰寫 MVP Spec ❌
- `docs/mvp-spec.md`
- Stripe integration plan
- Agent wallet 概念
- Fiat on/off-ramp 流程
- Commit: `docs: add MVP specification`

---

## 進度追蹤

| Phase | 狀態 | 完成日期 |
|-------|------|----------|
| Phase 1：OpenClaw Skill | ✅ 完成 | 2026-03-03 |
| Phase 2：Landing Page | ✅ 完成 | 2026-03-03 |
| Phase 3：推廣素材 | ✅ 完成 | 2026-03-03 |
| Phase 4：Hosted API | ❌ 未開始 | - |
| Phase 5：Payment Rails | ❌ 未開始 | - |
