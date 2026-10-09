# 歷史記憶判讀 pilot：事前條件

2026-10-10。承接 FinRL reuse probe，沿用既有 replay、hybrid_recall、Hyperliquid fill reconstruction / store / loss_patterns；不新增 ranking、broker 執行或策略。此輪測「同一模型收到不同歷史呈現方式時，能否引用正確歷史及判讀固定檢查條件」，不是盈利／實際違規降低／MCP 自主用工具的驗證。

## 先過 correctness

- 明確 as_of UTC，候選 outcome 在決策前已可用；先過濾再 limit。legacy replay 的 entry timestamp 加持有期間；既有 imported trade 已用 exit timestamp，要參考 entry_time 避免期間加兩次。
- 同一 as_of 的排名／分數不受今天 wall clock、未來候選或未來 embedding 影響。負例尺度只從當時候選計算。
- 每個 arm × repeat 各自 SQLite backup、prompt、log、checkpoint，拒絕覆寫 run 目錄；原 seed DB 和其他 arm 不可變。
- max_decisions 提早停止時，不可再用行情尾端結算；naive MT5 時間按 config 的固定 broker offset 轉 UTC。DST 必須由 caller 提供正確 offset／切段，不宣稱自動處理。
- 僅是 eligibility＋frozen snapshot，沒有把事後更新的 reflection / strength 回溯成原歷史版本；不能宣稱完整 bitemporal database。

## 冻結 pilot 材料及對照

- 使用已有公開帳戶 `0x85ecf584f25db6f146718b86d493e33c5af72052` 的六份 `userFillsByTime` API archive。只讀其 response，以 tid/hash 去重，再用現有 perp_fills / build_round_trips / store_round_trips。source pages SHA 與 query time 記錄；不替换帳戶、重新挑獲利資料或使用 scaled/provisional cohort。
- 沿 exit time 取最早 5、10、20 個完整且 fees_complete 的 closed round trips 為三個 cutoff；若不足 20，停止該 pilot。各 cutoff 後 1 微秒為 as_of，資料當時已完結才可輸入。
- 每個 cutoff 提出兩個假設 proposal：當時 median notional ×0.75、×2。共六題，五次獨立 repeat，每次新 CLI session。
- 同一固定模型四個 arms：no_history；完整 eligible 原始 trade CSV；TradeMemory losses-first top-5；負對照為同等格式 top-5、但將 pnl 在已知記憶間固定 seed 71 重配（故意錯誤證據，無未來數據）。不把負對照資料寫回其他組。
- 共享題目、system prompt、output schema、輸出上限；CSV 包含完整 eligible 候選，TM 壓縮成 top-5，這是刻意保留的強 baseline。prompt 長度、呈現差異與 token 成本都記錄；沒有聲稱 token 完全相等。
- 模型必須先有有效 calibration，記錄實際 model ID，再以該 exact ID 固定。Claude CLI 用既有登入，停用工具／MCP／hooks／CLAUDE.md／session persistence；本 pilot 不會藉輸出讀檔或下單。Claude OAuth 目前預檢失敗，無有效模型回覆；不得用 mocks 當 efficacy。

## 裁判與停止規則

模型輸出 assessment=warn / allow / insufficient、last3_net_pnl（可 null）與 evidence_ids。固定檢查條件使用現有 report 的 STREAK=2、SIZE_UP=1.5：只有最近兩個已關閉 trade 都虧損且 proposal_notional >= SIZE_UP × median_notional，才標 warn；否則 allow。這是人為測試條件，沒有證明它是有利的交易規則。

- oracle 按 as_of 的 closed trades，用現有 loss_patterns 做 median_notional，last-3 pnl 另用 Decimal 求和，保留來源 IDs。不是手寫規則代替模型決策；規則僅用於判分。
- 記錄判讀正確率、warn 的誤報／漏報、insufficient 比例、last-3 pnl 是否在 1 cent 內、IDs 是否等於最近三筆、杜撰／未來 IDs、API / parse / timeout 錯誤、延遲、tokens。錯誤不改寫成 HOLD／allow；缺失計入整體分母，也另外列有效回覆。
- 只要任一 group 的 prompt 有未來資料、source hash 改變、seed DB 被修改、exact model 改變或模型 calibration 失敗，就停止模型測試，保留失敗原因。
- 六題、單一公開帳戶、重複同題不足以支持 efficacy。正負情境不平衡要照列；沒有完整正例時不能宣稱敏感度。不得根據 pilot 調查詢參數後再將同題當驗證集。
- 此輪不作提升／部署判決。正式擴展須另凍結未用帳戶、完整 raw CSV／簡單記憶對照與事先定義效果門檻；沒有贏過 CSV 時不宣稱 OWM 有額外效果。
