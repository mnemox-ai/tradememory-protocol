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
python -m src.tradememory.server
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
python mt5_sync.py
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

[OK] Connected to MT5: Chung Cheng Peng (YourBroker-Server)
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
cd /d C:\OpenClawWork\tradememory-protocol
python mt5_sync.py
pause
```

#### 2. 設定 Task Scheduler

1. 開啟「工作排程器」(Task Scheduler)
2. 「建立基本工作」
3. 名稱：`MT5 TradeMemory Sync`
4. 觸發程序：「當電腦啟動時」
5. 動作：「啟動程式」
   - 程式：`C:\OpenClawWork\tradememory-protocol\start_mt5_sync.bat`
6. 完成

**注意**：確保 Windows 登入後自動啟動 MT5 Terminal。

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
MT5_PASSWORD=R*M4SoYe
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
**維護者**：小柯 (XiaoKe)
