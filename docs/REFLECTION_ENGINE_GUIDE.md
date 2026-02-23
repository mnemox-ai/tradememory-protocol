# ReflectionEngine 使用指南

## 概述

ReflectionEngine 是 TradeMemory Protocol 的核心模組，負責分析交易記錄並產生 AI 驅動的每日反思報告。

**關鍵特性：**
- ✅ LLM-agnostic 設計（支援任何 LLM provider）
- ✅ Rule-based fallback（無 LLM 依賴也能運作）
- ✅ 輸出格式驗證（DEC-010：防止垃圾進入 L2 記憶）
- ✅ UTC 時區一致性
- ✅ 成本效益（~$0.007/day）

---

## 快速開始

### 基本使用（Rule-based 模式）

```python
from tradememory.reflection import ReflectionEngine
from datetime import date

# 初始化
engine = ReflectionEngine()

# 產生今日摘要（rule-based）
summary = engine.generate_daily_summary()
print(summary)
```

### 使用 LLM（推薦）

```python
from tradememory.reflection import ReflectionEngine

# 定義 LLM provider function
def my_llm_provider(model: str, prompt: str) -> str:
    # 呼叫你的 LLM API（OpenClaw, Anthropic, OpenAI 等）
    response = your_llm_api.call(model=model, prompt=prompt)
    return response.text

# 初始化並使用 LLM
engine = ReflectionEngine()
summary = engine.generate_daily_summary(llm_provider=my_llm_provider)
print(summary)
```

### 分析特定日期

```python
from datetime import date

target_date = date(2026, 2, 22)
summary = engine.generate_daily_summary(
    target_date=target_date,
    llm_provider=my_llm_provider
)
```

---

## LLM Provider 規格

### Function Signature

```python
def llm_provider(model: str, prompt: str) -> str:
    """
    Args:
        model: 模型名稱 (預設: "claude-sonnet-4-5")
        prompt: CIO 提供的結構化 prompt
    
    Returns:
        str: LLM 回應文字
    
    Raises:
        Exception: 任何錯誤（會自動 fallback 到 rule-based）
    """
    pass
```

### OpenClaw 整合範例

```python
# 在 OpenClaw agent session 中
def openclaw_llm_provider(model, prompt):
    # OpenClaw 會自動路由到配置的 LLM
    from openclaw import llm
    response = llm.chat(model=model, messages=[{"role": "user", "content": prompt}])
    return response.content

engine = ReflectionEngine()
summary = engine.generate_daily_summary(llm_provider=openclaw_llm_provider)
```

---

## 輸出格式

### 標準格式（Template）

```
=== DAILY SUMMARY: YYYY-MM-DD ===

PERFORMANCE:
Trades: N | Winners: W | Losers: L
Net P&L: $XXX.XX | Win Rate: XX.X% | Avg R: X.XX

KEY OBSERVATIONS:
- [最多 3 條可執行洞察]
- [基於數據的觀察]

MISTAKES:
- [高信心但失敗的交易]
- [錯誤原因分析]

TOMORROW:
- [基於今日觀察的建議]
```

### 輸出驗證（DEC-010）

ReflectionEngine 會自動驗證 LLM 輸出：

**必要元素：**
- `=== DAILY SUMMARY: {date} ===` (正確日期)
- `PERFORMANCE:`
- `Trades:`
- `Win Rate:`

**至少 2 個選填區塊：**
- `KEY OBSERVATIONS:`
- `MISTAKES:`
- `TOMORROW:`

**如果驗證失敗：**
- 自動降級到 rule-based summary
- 附註 `(LLM output failed validation, using rule-based fallback)`

---

## Rule-based Fallback

當 LLM 不可用或驗證失敗時，自動使用 rule-based 邏輯：

**自動分析：**
- 勝率、平均 R-multiple、平均信心分數
- 高信心但虧損的交易（標記為 MISTAKES）
- 建議（基於勝率和 R-multiple）

**觸發條件：**
1. `llm_provider=None`（主動使用 rule-based）
2. LLM API 拋出異常
3. LLM 回傳格式不符合 template

**優點：**
- 零 LLM 成本
- 無網路依賴
- 確保系統永遠能產出摘要

---

## API 成本估算

### Claude Sonnet 4.5

**每次 daily_summary 呼叫：**
- Input: 500-1500 tokens (~$0.0015-0.0045)
- Output: 150-300 tokens (~$0.0023-0.0045)
- **Total: ~$0.004-0.014**（平均 $0.007）

**每月成本（30 天）：**
- 30 天 × $0.007 = ~**$0.21 USD**

**優化建議：**
- 交易少於 3 筆時使用 rule-based（成本 = $0）
- 只在交易日使用 LLM（非交易日檢查 trades=0 自動 skip）

---

## 進階：自訂分析邏輯

### 自訂 Prompt

如果需要不同的反思風格，可以繼承 `ReflectionEngine`：

```python
from tradememory.reflection import ReflectionEngine

class CustomReflection(ReflectionEngine):
    def _generate_llm_summary(self, target_date, trades, metrics, llm_provider):
        # 自訂 prompt
        custom_prompt = f"""
        你是激進的交易教練。分析這些交易，直接指出錯誤。
        
        Data: {trades}
        
        用一段話總結今天的表現。
        """
        
        response = llm_provider("gpt-4", custom_prompt)
        return response
```

### 自訂驗證規則

```python
class StrictReflection(ReflectionEngine):
    def _validate_llm_output(self, output, target_date):
        # 更嚴格的驗證
        if len(output) < 200:
            return False
        if "具體建議" not in output:
            return False
        return super()._validate_llm_output(output, target_date)
```

---

## 測試

### 單元測試覆蓋

- ✅ `test_daily_summary_no_trades` - 無交易日處理
- ✅ `test_daily_summary_with_trades` - 正常交易日
- ✅ `test_daily_summary_insufficient_data` - 數據不足警告
- ✅ `test_metrics_calculation` - 指標計算正確性
- ✅ `test_high_confidence_mistakes_detected` - 錯誤偵測
- ✅ `test_validate_valid_llm_output` - 格式驗證（9 個測試）

### 執行測試

```bash
pytest tests/test_reflection.py -v
pytest tests/test_llm_validation.py -v
```

---

## 架構決策記錄

### DEC-008: UTC Timezone + Dual Mode
- 使用 UTC 時區避免跨系統不一致
- LLM + rule-based 雙模式確保可靠性
- Phase 1 只做 daily summary（weekly/monthly 在 Phase 2）

### DEC-009: LLM-Agnostic Design
- 不綁定特定 LLM 函式庫
- 透過 callback function 注入 LLM
- 未來切換 provider 不需改核心代碼

### DEC-010: Output Validation
- LLM 回傳必須通過格式驗證
- 不合格輸出自動 fallback
- **CIO 原則：垃圾進 L2 比沒有 L2 更危險**

---

## 疑難排解

### Q: LLM 呼叫總是失敗

**檢查清單：**
1. `llm_provider` function 是否正確回傳 `str`？
2. 是否拋出未捕捉的異常？
3. 檢查 console 輸出：`(LLM failed: ...)`

**解決方案：**
- 確保 `llm_provider` 實作正確
- 檢查 API key 和網路連線
- 驗證 model 名稱正確（e.g., `claude-sonnet-4-5`）

### Q: 為什麼總是用 rule-based？

**可能原因：**
1. 未傳入 `llm_provider` 參數
2. LLM 回傳格式不符合 template（驗證失敗）
3. LLM API 異常

**檢查方法：**
- 檢查 summary 是否包含 `(using rule-based fallback)`
- 檢查 `failed validation` 訊息

### Q: 如何減少 LLM 成本？

**建議：**
```python
# 只在交易數 >= 3 時使用 LLM
trades = engine._get_trades_for_date(target_date)
if len(trades) >= 3:
    summary = engine.generate_daily_summary(llm_provider=my_llm)
else:
    summary = engine.generate_daily_summary()  # rule-based
```

---

## 下一步

- **Sprint 3:** 整合到 NG_Gold 真實 demo 交易流
- **Phase 2:** Weekly/Monthly reflection reports
- **Phase 3:** Pattern discovery + automated learning

---

**最後更新**：2026-02-23  
**維護者**：小柯 (XiaoKe)
