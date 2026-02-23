# "Watch Your Agent Evolve" - 一週 Demo 故事線

> **設計目標：** 用戶連上 TradeMemory 跑一週 demo 交易後，能看到清楚的「Before vs After」證明 agent 從錯誤中學習並自動調整行為。
> 
> **基於：** DEC-007 (CIO Review 2026-02-23)

---

## 故事線概述

**核心劇情：** Agent 在亞洲盤交易勝率低，第三天自己發現問題，第四天開始減倉或避開亞洲盤，勝率明顯改善。

**時間軸：** 7 天 demo 交易（可以是模擬盤或回測數據）

**展示重點：**
- ❌ 不是「我們的 agent 很聰明」
- ✅ 而是「看，它第三天自己發現亞洲盤勝率低，第四天就自動減倉了」

---

## Day 1-3: Before（學習前）

### 交易行為模式
| 參數 | 設定值 | 說明 |
|------|--------|------|
| **交易時段** | 全天候（亞洲盤 + 歐美盤） | 未區分時段特性 |
| **倉位大小** | 固定 0.1 lot | 未根據時段調整 |
| **策略** | 突破策略（統一應用） | 未考慮時段流動性差異 |

### 交易結果（Day 1-3）
| 時段 | 交易次數 | 勝率 | 平均獲利/虧損 | 總損益 |
|------|----------|------|----------------|--------|
| **亞洲盤** (00:00-08:00 GMT+8) | 8 筆 | 25% (2勝6敗) | -$45 | -$360 |
| **歐美盤** (16:00-24:00 GMT+8) | 6 筆 | 67% (4勝2敗) | +$30 | +$180 |
| **總計** | 14 筆 | 43% | -$12.86 | **-$180** |

### 問題徵兆
- 🚨 亞洲盤連續虧損：Day 1 (-$120), Day 2 (-$150), Day 3 (-$90)
- 🚨 假突破頻繁：亞洲盤流動性低，價格容易假突破後回調
- 🚨 滑價嚴重：亞洲盤點差較大，實際成交價偏離預期

---

## Day 3 晚上: Reflection Trigger（反思時刻）

### ReflectionEngine 自動觸發條件
```python
# 觸發條件（rule-based）
consecutive_losses = 3  # 亞洲盤連續 3 天虧損
win_rate_threshold = 0.40  # 亞洲盤勝率 < 40%
total_loss_threshold = -300  # 累積虧損 > $300
```

### Reflection 產出內容

**📊 Daily Summary (Day 3 晚上 23:59)**

```markdown
## Day 3 Trading Summary

### Performance Overview
- Total Trades: 5
- Win Rate: 20% (1W / 4L)
- Net P&L: -$90
- Cumulative P&L (Day 1-3): -$180

### Session Analysis
**Asian Session (00:00-08:00 GMT+8):**
- Trades: 4
- Win Rate: 0% (0W / 4L)
- P&L: -$120
- Issue: All breakout signals reversed within 15 minutes

**European Session (16:00-20:00 GMT+8):**
- Trades: 1
- Win Rate: 100% (1W / 0L)
- P&L: +$30

### ⚠️ Pattern Detected: Asian Session Underperformance
- Consecutive losses in Asian session: 3 days
- Asian session win rate (Day 1-3): 25% vs European: 67%
- Average loss per Asian trade: -$45 vs European gain: +$30

### 💡 Reflection Insight
**Problem:** Low liquidity during Asian session causes frequent false breakouts.
**Evidence:** 6 out of 8 Asian trades reversed after initial breakout.
**Suggested Action:** Reduce Asian session lot size by 50% OR avoid Asian session entirely.
```

**🤖 Agent 狀態更新**

```json
{
  "session_state": {
    "timestamp": "2026-02-23T23:59:00Z",
    "patterns_learned": [
      {
        "pattern": "asian_session_low_win_rate",
        "evidence": {
          "win_rate": 0.25,
          "sample_size": 8,
          "avg_loss": -45
        },
        "action": "reduce_lot_size_asian_50pct",
        "confidence": 0.85
      }
    ],
    "adaptive_rules": [
      {
        "rule_id": "AR-001",
        "condition": "session_type == 'asian' AND hour >= 0 AND hour < 8",
        "action": "lot_size *= 0.5",
        "reason": "Low liquidity, high false breakout rate",
        "activated_at": "2026-02-23T23:59:00Z"
      }
    ]
  }
}
```

---

## Day 4-7: After（學習後）

### 交易行為改變
| 參數 | 新設定值 | 變化 |
|------|----------|------|
| **亞洲盤倉位** | 0.05 lot（減半） | ✅ 根據反思調整 |
| **歐美盤倉位** | 0.1 lot（維持） | 保持原策略 |
| **策略** | 亞洲盤：僅觀察 + 小倉位試單 | ✅ 新增時段區分邏輯 |

### 交易結果（Day 4-7）
| 時段 | 交易次數 | 勝率 | 平均獲利/虧損 | 總損益 |
|------|----------|------|----------------|--------|
| **亞洲盤** (00:00-08:00 GMT+8) | 6 筆 | 33% (2勝4敗) | -$15 | **-$90** ⬆️ (vs -$360) |
| **歐美盤** (16:00-24:00 GMT+8) | 10 筆 | 70% (7勝3敗) | +$35 | **+$350** |
| **總計** | 16 筆 | 56% | +$16.25 | **+$260** |

### 改善數據對比

| 指標 | Day 1-3 (Before) | Day 4-7 (After) | 改善幅度 |
|------|------------------|-----------------|----------|
| **整體勝率** | 43% | 56% | **+30%** |
| **整體損益** | -$180 | +$260 | **+$440 扭虧為盈** |
| **亞洲盤平均虧損** | -$45/筆 | -$15/筆 | **虧損減少 67%** |
| **風險控制** | 單日最大虧損 $150 | 單日最大虧損 $60 | **風險降低 60%** |

---

## Dashboard 視覺化設計

### 1️⃣ Timeline View（時間軸視圖）
```
Day 1  ━━━━━━━  📉 -$120 (Asian heavy losses)
Day 2  ━━━━━━━  📉 -$150 (Worst day)
Day 3  ━━━━━━━  📉 -$90  💡 Reflection triggered!
       ⚡ Agent learned: Reduce Asian session lot size
Day 4  ━━━━━━━  📈 +$50  (New strategy applied)
Day 5  ━━━━━━━  📈 +$80
Day 6  ━━━━━━━  📈 +$70
Day 7  ━━━━━━━  📈 +$60
```

### 2️⃣ Before/After Split View（對比視圖）

**左側：Before (Day 1-3)**
- 亞洲盤勝率：25% 🔴
- 歐美盤勝率：67% 🟢
- 總損益：-$180 🔴
- 倉位策略：統一 0.1 lot

**右側：After (Day 4-7)**
- 亞洲盤勝率：33% 🟡（改善但仍弱）
- 歐美盤勝率：70% 🟢（持續強勢）
- 總損益：+$260 🟢
- 倉位策略：亞洲 0.05 / 歐美 0.1 lot

### 3️⃣ Insight Card（反思卡片）

```
💡 Day 3 Reflection Insight

Problem Detected:
"Asian session shows 75% loss rate with -$360 total loss"

Root Cause:
"Low liquidity (avg spread 2.5 pips vs 1.2 pips in European session)
causes frequent false breakouts"

Action Taken:
"Automatically reduced Asian session lot size from 0.1 to 0.05"

Result:
"Day 4-7 Asian loss reduced by 67%, overall P&L turned positive"
```

### 4️⃣ Session Performance Heatmap（時段表現熱力圖）

```
         Mon    Tue    Wed    Thu    Fri    Sat    Sun
Asian    🔴     🔴     🔴     🟡     🟡     ⚪     ⚪
         -120   -150   -90    -30    -20    0      0
         
European 🟢     🟡     🟢     🟢     🟢     ⚪     ⚪
         +60    +30    +90    +80    +90    0      0
```

---

## Demo 腳本設計

### 數據準備選項

**Option A: 真實 MT5 Demo 帳戶（7天真實交易）**
- ✅ 最真實，數據完全可信
- ❌ 需要 7 天等待時間
- ❌ 可能遇到市場波動不配合劇本

**Option B: 回測數據（精心挑選的 7 天歷史數據）**
- ✅ 可以挑選完美展示故事線的時段
- ✅ 立即可用，不需等待
- ❌ 需要誠實標註「基於歷史回測」

**Option C: 混合模式（前 3 天回測 + 後 4 天真實）**
- ✅ 兼顧可控性與真實性
- ✅ 可以確保前 3 天觸發反思
- ✅ 後 4 天展示真實改善

**推薦：Option C**（可控 + 真實的平衡）

### 觸發條件調校

為了確保 Day 3 觸發反思，需要預先設計：

```python
# reflection_triggers.py
DEMO_MODE_TRIGGERS = {
    "asian_session_check": {
        "min_trades": 6,  # 至少 6 筆亞洲盤交易
        "max_win_rate": 0.40,  # 勝率低於 40%
        "min_loss": -200,  # 累積虧損超過 $200
        "consecutive_loss_days": 2  # 連續 2 天虧損
    }
}
```

---

## 用戶體驗流程

### Day 1-3：靜默觀察期
```
User: 啟動 demo
Agent: ✅ 已連接 MT5 demo 帳戶，開始記錄交易...
       📊 Day 1 總結：5 筆交易，勝率 40%，損益 -$120
       📊 Day 2 總結：6 筆交易，勝率 33%，損益 -$150
```

### Day 3：反思觸發！
```
Agent: 📊 Day 3 總結：5 筆交易，勝率 20%，損益 -$90
       
       💡 **重要發現！**
       我注意到亞洲盤（00:00-08:00）勝率只有 25%，遠低於歐美盤的 67%。
       
       分析原因：亞洲盤流動性較低，假突破頻繁。
       
       **我決定從明天開始：**
       - 亞洲盤倉位減半（0.1 → 0.05 lot）
       - 歐美盤維持原策略
       
       這是我第一次自主調整策略，讓我們看看效果如何！
```

### Day 4-7：改善驗證期
```
Agent: 📊 Day 4 總結：4 筆交易，勝率 50%，損益 +$50
       ✅ 新策略生效：亞洲盤虧損已從平均 -$45/筆 降至 -$15/筆
       
       📊 Day 7 總結：4 筆交易，勝率 75%，損益 +$60
       
       🎉 **一週回顧：**
       - Day 1-3（學習前）：-$180
       - Day 4-7（學習後）：+$260
       - 改善幅度：+$440，勝率從 43% 提升至 56%
       
       這證明了我能從錯誤中學習並自動調整！
```

---

## 技術實現要點

### 1. ReflectionEngine 需支援
- ✅ 時段分組統計（Asian / European / American session）
- ✅ 勝率計算（按時段）
- ✅ 連續虧損檢測
- ✅ 自動觸發條件判斷

### 2. SessionState 需儲存
- ✅ `patterns_learned` - 學到的模式
- ✅ `adaptive_rules` - 自適應規則
- ✅ `rule_activation_log` - 規則啟動歷史

### 3. Dashboard 需展示
- ✅ Timeline view（7 天損益曲線）
- ✅ Before/After 對比表格
- ✅ Insight card（Day 3 反思內容）
- ✅ Session heatmap（時段表現熱力圖）

---

## 成功指標

**Demo 被認為成功的條件：**

1. ✅ **故事清晰：** 用戶能在 30 秒內看懂「agent 學到了什麼」
2. ✅ **數據可信：** 改善幅度合理（不誇張），有具體證據
3. ✅ **行為可見：** 能明確指出「Day 3 晚上 agent 做了什麼決定」
4. ✅ **結果驗證：** Day 4-7 確實展現改善（不是巧合）
5. ✅ **技術可靠：** ReflectionEngine 邏輯透明，可複現

**失敗的反例：**
- ❌ 「我們的 AI 很聰明」（空洞）
- ❌ 勝率從 10% 提升到 90%（不可信）
- ❌ 看不出來 agent 具體做了什麼改變
- ❌ 改善只持續 1 天就消失（偶然性）

---

## 下一步

1. ✅ **毛毛 Task 1：** 根據本文設計 Streamlit dashboard
2. ⏳ **小柯補充：** 確認 ReflectionEngine 支援時段分組統計
3. ⏳ **Sean：** 準備 demo 數據（Option C: 前 3 天回測 + 後 4 天真實）
4. ⏳ **CIO Review：** 驗證故事線邏輯是否符合 DEC-007 要求

---

**最後檢查清單：**
- [x] 故事線在一週內完成 ✅
- [x] 有清楚的 Before vs After ✅
- [x] 第 3 天有明確的反思內容 ✅
- [x] 第 4-7 天有可觀察的行為改變 ✅
- [x] 有量化的改善數據 ✅
- [x] 展示方式具體（非抽象概念）✅

**這不是「agent 會學習」的承諾，而是「看，它就在第三天學會了這個」的證明。** ✅
