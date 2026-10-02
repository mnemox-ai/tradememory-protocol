# MT5 Sync Script 設定指南

## 概述

`mt5_sync.py` 是非侵入式監控腳本，獨立運行於 NG_Gold EA 之外。

**架構**：
```
NG_Gold EA (不做任何修改)
    ↓
MT5 Terminal (正常交易)
    ↓
MT5 Python API 讀取交易紀錄
    ↓
mt5_sync.py (每 60 秒輪詢)
    ↓
TradeMemory MCP Server (FastAPI)
    ↓
SQLite Database
```

**優點**：
- ✅ 不修改 NG_Gold EA 代碼（零風險）
- ✅ NG_Gold 完全不知道被監控
- ✅ 獨立運行，互不干擾
- ✅ 可隨時啟動/停止

---

## 安裝步驟

### 1. 安裝依賴

```bash
pip install MetaTrader5 python-dotenv requests
```

### 2. 設定 Credentials

```bash
# 複製範本
copy .env.example .env

# 編輯 .env（填入真實密碼）
notepad .env
```

**重要**：`.env` 檔案已在 `.gitignore` 中，不會被 commit 到 Git。

### 3. 啟動 TradeMemory Server

確保 MCP Server 正在運行：

```bash
python -m tradememory
```

應該看到：
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 4. 啟動 MT5 Terminal

打開 MetaTrader 5，確保：
- ✅ 已登入使用 MEMORY.md 中的 MT5 credentials
- ✅ NG_Gold EA 正在運行
- ✅ Terminal 保持開啟狀態

---

## 運行 Sync Script

### 方式 A：命令列直接運行（測試用）

```bash
python scripts/mt5_sync.py
```

輸出範例：
```
============================================================
MT5 → TradeMemory Sync Script
============================================================
API Endpoint: http://localhost:8000
Sync Interval: 60s
MT5 Account: your_login_here @ YourBroker-Server
============================================================

[OK] Connected to MT5: REDACTED_NAME (YourBroker-Server)
[OK] Account: your_login_here, Balance: $10000.00

[OK] Monitoring started. Press Ctrl+C to stop.

[SCAN] Found 1 new closed trade(s)
[SYNC] MT5-12345: XAUUSD long 0.05 lots, P&L: $25.50, Duration: 127min
[OK] Sync complete. Last ticket: 12345
```

**停止**：按 `Ctrl+C`

### 方式 B：Windows Task Scheduler（自動運行）

#### 1. 建立批次檔 `start_mt5_sync.bat`

```batch
@echo off
cd /d C:\Users\<你的使用者名稱>\projects\tradememory-protocol
python scripts/mt5_sync.py
pause
```

#### 2. 設定 Task Scheduler

1. 開啟「工作排程器」(Task Scheduler)
2. 「建立基本工作」
3. 名稱：`MT5 TradeMemory Sync`
4. 觸發程序：「當電腦啟動時」
5. 動作：「啟動程式」
   - 程式：`C:\Users\<你的使用者名稱>\projects\tradememory-protocol\start_mt5_sync.bat`
6. 完成

**注意**：確保 Windows 登入後自動啟動 MT5 Terminal。

### 方式 C：用 repo 附的啟動器（`scripts\platform\`）

- `start_services.bat`：啟動 TradeMemory server，再開 `watchdog_mt5_sync.bat` 跑 `scripts\mt5_sync.py`（程式結束後 30 秒自動重啟）
- `install_autostart.bat`：以系統管理員身分執行，把 `TradeMemory_AutoStart.xml` 註冊成登入 30 秒後自動執行 `start_services.bat`
- `start_tradememory.pyw`：不開視窗的版本，跑 server 和 `mt5_sync.py`，另外排好每日／每週的 `daily_reflection.py`。要開機自動跑，就在「啟動」資料夾放它的捷徑（不要放複本）

bat 檔會從自己所在的位置找到 repo 根目錄，不用改路徑。`TradeMemory_AutoStart.xml` 裡的路徑寫成 `%USERPROFILE%\projects\tradememory-protocol`，repo 不在這個位置的話，註冊前先改 XML 的 `<Arguments>` 和 `<WorkingDirectory>` 兩行。

用哪個 Python 也不用改檔案，`start_services.bat`、`watchdog_mt5_sync.bat`、`start_tradememory.pyw` 都照同一個順序找：

1. 有設環境變數 `PYTHON`，就用它（值是 `python.exe` 的完整路徑）
2. 沒設的話，repo 根目錄有 `.venv\Scripts\python.exe` 就用它
3. 都沒有，就用 PATH 上的 `python`

實際用了哪一個，會寫在 `logs\startup.log` 和 `logs\watchdog.log`。沒設 `PYTHON` 的話，repo 裡只要有 `.venv` 就會用它，所以 `.venv` 要裝齊：

```batch
.venv\Scripts\python -m pip install -e . MetaTrader5
```

`start_tradememory.pyw` 自己排每日／每週的 reflection，要用到 `schedule` 套件，而且要裝在執行 .pyw 的那個 Python 裡。從「啟動」資料夾的捷徑開啟時，執行它的是副檔名關聯的 `pythonw.exe`，不一定是上面選到的那個。最簡單的做法是把捷徑目標設成 `<repo>\.venv\Scripts\pythonw.exe <repo>\scripts\platform\start_tradememory.pyw`，再把 `schedule` 裝進 `.venv`。沒裝的話，server 和 `mt5_sync.py` 照常啟動，只有 reflection 排程不跑，原因會寫在 `logs\startup.log`。不想用 `.venv`，就把 `PYTHON` 設成要用的 `python.exe`，例如 `setx PYTHON "C:\Users\<你的使用者名稱>\AppData\Local\Programs\Python\Python313\python.exe"`（`setx` 會拿掉外層引號；在「環境變數」視窗手動填的話，值不要加引號）。`setx` 只影響之後新開的程式，已經開著的視窗要重開。

---

## 驗證同步

### 1. 檢查腳本輸出

應該看到 `[SYNC]` 訊息：
```
[SYNC] MT5-12345: XAUUSD long 0.05 lots, P&L: $25.50, Duration: 127min
```

### 2. 查詢 TradeMemory API

```bash
curl http://localhost:8000/trade/get_active
```

或用 Python：
```python
import requests
r = requests.get('http://localhost:8000/trade/get_active')
print(r.json())
```

### 3. 檢查 SQLite Database

```bash
sqlite3 data/tradememory.db "SELECT id, symbol, pnl FROM trade_records ORDER BY timestamp DESC LIMIT 5;"
```

---

## 設定檔說明

### .env

```bash
# MT5 帳戶資訊（從 MEMORY.md 取得）
MT5_LOGIN=your_login_here
MT5_PASSWORD=your_password_here
MT5_SERVER=YourBroker-Server

# TradeMemory API endpoint
TRADEMEMORY_API=http://localhost:8000

# 輪詢間隔（秒）
SYNC_INTERVAL=60
```

**調整建議**：
- Demo 測試：60 秒（預設）
- 生產環境：30 秒（更即時）
- 低頻交易：120 秒（減少 API 呼叫）

---

## 疑難排解

### Q: `MetaTrader5 package not installed`

**解決**：
```bash
pip install MetaTrader5
```

用方式 C 的啟動器時，要裝進它選到的那個 Python（看 `logs\startup.log` 或 `logs\watchdog.log`），例如 `.venv\Scripts\python -m pip install MetaTrader5`。

### Q: `MT5 initialize() failed`

**可能原因**：
1. MT5 Terminal 未安裝
2. MT5 Terminal 未運行
3. 防毒軟體阻擋 Python 存取 MT5

**解決**：
1. 確認 MT5 Terminal 已開啟
2. 以管理員權限運行 `mt5_sync.py`
3. 防毒軟體白名單加入 `python.exe`

### Q: `MT5 login failed`

**檢查**：
1. `.env` 中的 `MT5_LOGIN`、`MT5_PASSWORD`、`MT5_SERVER` 是否正確
2. 使用 MEMORY.md 中的 credentials
3. 確認 MT5 Terminal 已手動登入過（第一次需要手動登入）

### Q: `API request failed`

**檢查**：
1. TradeMemory server 是否運行？(`http://localhost:8000/health`)
2. 防火牆是否阻擋 localhost 連線？
3. `.env` 中的 `TRADEMEMORY_API` 是否正確？

### Q: 交易已關閉但沒有同步

**可能原因**：
1. 腳本尚未輪詢到（等待下一個 60 秒週期）
2. 交易 ticket 小於 `last_synced_ticket`（腳本重啟會重置）

**解決**：
- 重啟腳本會重新同步所有歷史交易
- 檢查 console 是否有 `[SYNC]` 訊息

---

## 自動啟動檢查清單

**開機自動運行需要**：
- ✅ MT5 Terminal 自動啟動並登入
- ✅ Task Scheduler 已設定 `start_mt5_sync.bat`
- ✅ TradeMemory server 也設定自動啟動（或手動啟動）

**測試方式**：
1. 重啟電腦
2. 確認 MT5 Terminal 已開啟
3. 確認 `mt5_sync.py` 在背景運行（Task Manager 可見）
4. 手動下單測試，60 秒後檢查是否同步

---

## 已知限制

1. **Reasoning 欄位**：MT5 無法記錄 EA 的決策理由，統一填 `"Auto-synced from MT5 - reasoning not captured"`
2. **Confidence 分數**：MT5 無法記錄 EA 的信心分數，統一填 `0.5`
3. **歷史交易**：腳本重啟後會重新掃描所有歷史交易（可能產生重複，TradeMemory 會檢查 `trade_id` 去重）

---

**最後更新**：2026-02-23  
**Maintainer**: Sean / Mnemox AI
