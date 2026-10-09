# Historical memory decision probe — current evidence

2026-10-10。**pending: 模型比較未執行。Claude Code OAuth 已過期且 refresh 失敗，沒有有效模型回答，不能下 efficacy 結論。**

## 已驗證的 correctness

| 檢查 | 結果 |
|---|---|
| Explicit historical clock，不可讀 wall clock | 通過；fault control 將 `datetime.now` 設成拋錯 |
| 未來 memory／極端 loss／embedding 不得改變當時 ranking | 通過；原始未截斷 query 能取出未來記憶作 positive control |
| Closed outcome availability，filter before limit | 通過；entry / exit、timezone、1 微秒、malformed metadata、open outcome 邊界 |
| Import timestamp 不重複加持有期間 | 通過；使用 native store 寫入後比對 |
| Capped replay 不使用停止後行情 | 通過；改動未來 prices 不改 equity，稀疏 decision interval 也在最後決策結算 |
| 每組獨立 DB／checkpoint／log | 通過；改寫 arm A 後 seed / arm B 不變，重複 output 被拒絕 |
| 錯誤 PnL 負對照無未來值 | 通過；只重配當時 eligible top-5，DB 不變 |
| 非法第一筆模型回覆保留錯誤、停止 | 通過；mock 僅驗 runner 故障行為，未當 efficacy |
| 最終 prompt dry-run | 120/120 prepared；20 個獨立 arm × repeat outputs，0 模型呼叫 |

最終完整不連外 regression：**1,612 passed、6 skipped、5 warnings**，50.09 秒。四個直接相關測試檔：48 passed。另一次完整執行為 1,608 passed、5 skipped、1 failed；唯一失敗是既有 `test_real_discovery` 真 API 收到 `401 invalid x-api-key`。第一次移除程序 key 後，MT5 module import 的 dotenv 又補回 key，第二次同樣 401；根因確認後改為程序內空 key，保留 `.env` 與測試原本 skip 邏輯，才得到上述不連外結果。這不代表 live API gate 通過。

最後補上 unknown duration 的保守排除時，9 個 fixture tests 曾失敗：原 fixture 將持有期間省略成 NULL，卻期待結果立即可用；新增測試也缺少 query / JSON import。已補齊 import、讓 fixture 明確給 known zero duration，另以 NULL fault control 驗證確實排除；所有原 assertion 保留。該失敗 XML 與最終通過證據都有 SHA 紀錄，沒有把失敗 run 當成最終通過結果。

## 凍結材料

重用六份公開 Hyperliquid archive，12,000 個去重 fill records；既有 FIFO importer 還原 **200 個 fees_complete 的 closed round trips**，4 段因 history holes 被捨棄，spot skipped=0。它是有限保留歷史，沒有宣稱全帳戶完整性。資料 request type / address 已檢查，原始 pages SHA 保留；沒有讀取 MT5 私密交易資料或 credentials。

來源契約為官方 [Info endpoint / userFillsByTime](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint#retrieve-a-users-fills-by-time)：query 使用地址與時間範圍。公開 archive 在本輪前已存在，沒有重新挑帳戶或替換 source。

事前固定最早 5 / 10 / 20 closed trades 的三個 cutoff，各配 median notional ×0.75 / ×2，共六題，五次 repeat，四個 arms。實際六題 oracle **全部 allow、warn=0**；這批不能估 warn 敏感度或風險改善，只能校準數字、引用、誤報、insufficient 與成本。沒有為補正例重挑本輪題目。

raw CSV 包含完整 eligible 歷史；TM 是原 losses-first top-5，可能省略最近三筆或 median 所需資料。若 TM 回答 insufficient，那是 coverage 限制，不能寫成更安全；若答出正確 allow，也可能只是樣本全部 allow。必須連同數字與引用一起看。

## 模型與外送 gate

已修正 Claude Code 2.1.283 Windows native executable 的 resolver。只送固定 JSON 題目的實際預檢：`trade_rows_sent=0`，CLI exit=1，`Failed to authenticate: OAuth session expired and could not be refreshed`，modelUsage 空，reported tokens / cost 為 0。

自動審核另拒絕 combined「預檢通過即跑 comparison」命令，理由是未明確批准交易 payload 外送至 Claude 及後續 120 次呼叫。該命令未執行；改成無交易資料的獨立 calibration 後獲准，仍因 OAuth 失敗停止。已備好四組 [prompt preview](PROMPT_PREVIEW.md) 和完整本機 dry-run，pending: 使用者選擇／批准 Claude 的公開資料對照或本機模型方案；尚未切換模型。

## 後續判斷

next: 登入及外送範圍確認後，沿用凍結材料先跑數字／引用 calibration，不據此做 trading efficacy 決定。若要測風險辨識，另凍結未使用帳戶、正負情境與效果門檻，不把這六題拿來調參後當驗證集。沒有贏過完整 CSV baseline 時，不宣稱 OWM 有額外效果。

原 FinRL probe 的 source / models / accounting results 沒有改動。該 probe 的 core fingerprint 綁定舊 revision `c7f8967`；本輪 core 已改變，重現舊結果須在該 revision 執行。新的程式指紋、測試與材料 hashes 記錄於 [validation.json](validation.json)。
