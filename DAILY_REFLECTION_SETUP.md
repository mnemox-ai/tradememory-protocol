# Daily Reflection 自動化設定指南

## 概述

每天 23:55 自動產生每日交易反思報告。

---

## 設定步驟

### 1. Windows Task Scheduler 設定

#### 方式 A：手動設定

1. 開啟「工作排程器」(Task Scheduler)
2. 「建立基本工作」
3. 設定：
   - **名稱**：`TradeMemory Daily Reflection`
   - **觸發程序**：每天
   - **時間**：23:55
   - **動作**：啟動程式
     - 程式：`C:\OpenClawWork\tradememory-protocol\start_daily_reflection.bat`
   - **條件**：取消勾選「只有在電腦使用 AC 電源時才啟動工作」

#### 方式 B：命令列設定

```powershell
# 以管理員權限執行 PowerShell
schtasks /create /tn "TradeMemory Daily Reflection" /tr "C:\OpenClawWork\tradememory-protocol\start_daily_reflection.bat" /sc daily /st 23:55 /ru SYSTEM
```

### 2. 測試執行

手動執行腳本測試：

```bash
python daily_reflection.py
```

預期輸出：
```
============================================================
Daily Reflection Generator
============================================================
API Endpoint: http://localhost:8000
Output Directory: reflections
============================================================

[23:55:01] Generating daily reflection for 2026-02-23...
[OK] Reflection generated (487 chars)
[OK] Saved to: reflections\reflection_2026-02-23.txt

============================================================
DAILY REFLECTION
============================================================
=== DAILY SUMMARY: 2026-02-23 ===

PERFORMANCE:
Trades: 3 | Winners: 2 | Losers: 1
Net P&L: $75.50 | Win Rate: 66.7% | Avg R: 1.5

KEY OBSERVATIONS:
- Win rate above 60% indicates edge is present
- London session trades outperformed Asian session

TOMORROW:
- Continue current strategy, watch for reversal signals
============================================================
```

### 3. 確認輸出檔案

檢查 `reflections/` 目錄：
```
reflections/
├── reflection_2026-02-21.txt
├── reflection_2026-02-22.txt
└── reflection_2026-02-23.txt
```

---

## 整合 LLM（可選）

### OpenClaw Agent 整合

如果要使用 LLM 而非 rule-based，需要在 OpenClaw agent session 中註冊 callback：

```python
# 在 OpenClaw agent 中
def openclaw_llm_provider(model, prompt):
    from openclaw import llm
    response = llm.chat(model=model, messages=[{"role": "user", "content": prompt}])
    return response.content

# 傳遞給 TradeMemory server（需要修改 server.py）
```

**Phase 1 預設**：使用 rule-based summary（成本 = $0）  
**Phase 2**：整合 LLM callback（成本 ~$0.007/day）

---

## 檢查清單

**每日自動化運行需要**：
- ✅ TradeMemory server 正在運行（port 8000）
- ✅ Windows Task Scheduler 已設定 23:55 執行
- ✅ `.env` 設定正確（TRADEMEMORY_API）
- ✅ `reflections/` 目錄可寫入

**測試方式**：
1. 手動執行 `python daily_reflection.py`
2. 檢查 `reflections/` 是否產生檔案
3. 檢查 Task Scheduler 執行歷史（是否成功）

---

## 進階：整合到 Dashboard

毛毛可以在 Dashboard 中顯示最近 7 天的 reflection：

```python
import os
from datetime import date, timedelta

def load_recent_reflections(days=7):
    reflections = []
    for i in range(days):
        target_date = date.today() - timedelta(days=i)
        filename = f"reflections/reflection_{target_date.isoformat()}.txt"
        
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                reflections.append({
                    'date': target_date,
                    'content': f.read()
                })
    
    return reflections
```

---

## 疑難排解

### Q: Task Scheduler 沒有執行

**檢查**：
1. Task Scheduler 執行歷史（是否有錯誤）
2. 批次檔路徑是否正確
3. 權限是否足夠（改用 SYSTEM 帳戶執行）

### Q: API request failed

**檢查**：
1. TradeMemory server 是否運行？
2. Port 8000 是否被占用？
3. 防火牆是否阻擋？

**解決**：
```bash
# 檢查 server 是否運行
curl http://localhost:8000/health

# 應回傳
{"status":"healthy","service":"TradeMemory Protocol","version":"0.1.0"}
```

### Q: 檔案未產生

**檢查**：
1. `reflections/` 目錄是否存在且可寫入
2. 執行帳戶權限是否足夠
3. 檢查 `logs/reflection.log`（如果有錯誤會記錄）

---

**最後更新**：2026-02-23  
**維護者**：小柯 (XiaoKe)
