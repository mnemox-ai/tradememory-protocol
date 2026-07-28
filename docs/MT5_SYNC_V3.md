# MT5 Sync v3 設定指南

## 概述

`mt5_sync_v3.py` 是 v2 的 FastAPI 重構版。內建 web dashboard、background poller、trade advisor Discord 通知。

**架構**：
```
MT5 Terminal
    ↓ (positions_get / history_deals_get)
MT5Poller (daemon thread, 每 60s)
    ↓
SQLite (open_positions, sync_state, sync_log)
    ↓
FastAPI (port 9001)
    ├── GET /         → HTML dashboard (auto-refresh 10s)
    ├── GET /health   → JSON status
    ├── GET /open-positions → JSON
    └── GET /recent-trades  → JSON
    ↓
TradeMemory API (record_decision + record_outcome)
    ↓
Discord webhook (open/close/advisor alerts)
```

---

## 前置需求

- Python 3.10+ (venv 已裝在 `.venv/`)
- MetaTrader5 Python package
- `.env` 設好 MT5 credentials（見下方）

## 安裝

```bash
cd C:\Users\<你的使用者名稱>\projects\tradememory-protocol
.venv\Scripts\activate
pip install MetaTrader5 python-dotenv requests fastapi uvicorn
```

## .env 設定

確認 `C:\Users\<你的使用者名稱>\projects\tradememory-protocol\.env` 包含：

```env
MT5_LOGIN=你的帳號
MT5_PASSWORD=你的密碼
MT5_SERVER=你的伺服器
MT5_PATH=C:\Program Files\FXTM MT5\terminal64.exe
TRADEMEMORY_API=http://localhost:8000
SYNC_INTERVAL=60
DISCORD_WEBHOOK_URL=你的webhook
```

---

## 手動啟動

```bash
cd C:\Users\<你的使用者名稱>\projects\tradememory-protocol
.venv\Scripts\activate
uvicorn scripts.mt5_sync_v3:app --port 9001 --host 0.0.0.0
```

或用 bat 檔（含 watchdog 自動重啟）：
```bash
scripts\start_mt5_sync_v3.bat
```

啟動後開瀏覽器 http://localhost:9001 看 dashboard。

---

## 開機自動啟動（Task Scheduler）

### 方法 1：匯入 XML

```powershell
schtasks /create /tn "MT5SyncV3_AutoStart" /xml "C:\Users\<你的使用者名稱>\projects\tradememory-protocol\scripts\MT5SyncV3_AutoStart.xml"
```

### 方法 2：手動建立

1. 開啟 Task Scheduler (`taskschd.msc`)
2. Create Task（不是 Create Basic Task）
3. **General**：
   - Name: `MT5SyncV3_AutoStart`
   - Run only when user is logged on
4. **Triggers**：
   - At log on → Delay task for **30 seconds**（等 MT5 啟動）
5. **Actions**：
   - Program: `cmd.exe`
   - Arguments: `/c "C:\Users\<你的使用者名稱>\projects\tradememory-protocol\scripts\start_mt5_sync_v3.bat"`
   - Start in: `C:\Users\<你的使用者名稱>\projects\tradememory-protocol`
6. **Settings**：
   - Allow task to be run on demand: ✅
   - If the task is already running: Do not start a new instance
   - Do not limit execution time（設 0）

### 移除排程

```powershell
schtasks /delete /tn "MT5SyncV3_AutoStart" /f
```

---

## 驗證

| 項目 | 方法 |
|------|------|
| Dashboard | http://localhost:9001 |
| Health check | `curl http://localhost:9001/health` |
| Open positions | `curl http://localhost:9001/open-positions` |
| Logs | `logs/mt5_sync_v3.log` |
| Startup log | `logs/mt5_sync_v3_start.log` |

## 狀態說明

| Status | 意義 |
|--------|------|
| **RUNNING** | MT5 連線正常，正在同步 |
| **ERROR** | MT5 斷線或有錯誤，正在嘗試重連 |
| **PAUSED** | 連續錯誤超過上限（10 次），等待 5 分鐘後重試 |

MT5 未連接時不會 crash，會顯示 PAUSED/ERROR 並持續嘗試重連。

---

## 與舊版共存

- v1 (`mt5_sync.py`) 用 polling script，無 web UI
- v3 (`mt5_sync_v3.py`) 有 FastAPI dashboard + trade advisor
- 兩者 **不要同時跑**，會重複 sync 交易到 TradeMemory
- 切換：停掉舊的 watchdog，改用 `start_mt5_sync_v3.bat`
