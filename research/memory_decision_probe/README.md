# Historical memory decision probe

2026-10-10。承接 FinRL 調查，重用既有 replay、hybrid_recall、Hyperliquid importer 和 loss_patterns。結果見 [RESULTS.md](RESULTS.md)，事前條件見 [PROTOCOL.md](PROTOCOL.md)。這輪是 prompt 判讀校準；不是交易收益、風險改善或自主 MCP agent 的實驗。

## 本輪實作

- OWM / hybrid_recall 接受 optional `as_of`，在 score、PnL scale、vector 路徑與 limit 前排除未知／未來記憶，recency 使用該時鐘。未提供 `as_of` 時沿用 live 行為。
- SQLite replay query 以 readonly connection 讀 frozen snapshot，先檢查 closed outcome 的 `available_at` 再 limit。native imported trade 的 timestamp 是 exit；legacy replay timestamp 是 entry，以持有期間推導 outcome 可用時間。legacy 若 duration 未知且無明確 `available_at` 則排除，不能假設 0 秒。新 replay 寫入 UTC 與明確 `available_at`，不改 schema。
- `ReplayEngine` 傳 UTC decision time 給 recall；`max_decisions` 停止後不再以 CSV 尾端行情結算。可設定每組獨立 `checkpoint_path`；caller 也要指定獨立 DB 與 log 路徑。
- pilot 重用 native FIFO reconstruction / store 與原 ranking，四組為 no_history、完整 raw CSV、TradeMemory losses-first top-5、已知 top-5 間的錯誤 PnL 重配。每組每次 repeat 使用獨立 SQLite backup、prompt、checkpoint。

## 重現與模型執行

在 repository root：

```powershell
python research/memory_decision_probe/run_probe.py prepare
python research/memory_decision_probe/run_probe.py run --dry-run --output research/memory_decision_probe/.cache/new-dry-run
python research/memory_decision_probe/run_probe.py calibrate --output research/memory_decision_probe/.cache/new-auth-check
```

`prepare` 預設重用本機 `research/hyperliquid/_archive/0x85ecf584f25db6f146718b86d493e33c5af72052/` 六份 archive；也可指定 `--source`。原始 archive、seed DB、完整 prompts / CLI receipts 均在本機，cache ignored。已存在 manifest 時會驗證 source pages、seed、cases、protocol SHA，不覆寫。每次 output 必須是新目錄。保留舊 archive：現行 API 的有限保留窗不保證能重新取得同一歷史，重新抓取不算本輪重現。

`calibrate` 只送固定 JSON 題目，`trade_rows_sent=0`，不讀交易資料、不接續 comparison。模型 schema／實際 model ID 校準通過後，以 exact ID 固定；停用 tools、MCP、hooks、project instructions 與 session persistence。CLI JSON receipt 保存於該 run，非法 JSON／timeout／model change 會停止，不轉成 allow 或 HOLD。

next: 恢復 Claude 登入，確認模型對照的外送範圍後，才執行：

```powershell
claude auth login
python research/memory_decision_probe/run_probe.py run --output research/memory_decision_probe/.cache/new-model-run
```

comparison 預計 120 次＋1 次 calibration，使用既有 Claude Code 登入；實際 tokens／CLI reported cost 記錄，不預設訂閱計費。樣本外送欄位見 [PROMPT_PREVIEW.md](PROMPT_PREVIEW.md)；題目及 provenance 見 [validation.json](validation.json)。沒有讀取 Sean 的 MT5、其他研究 DB、private key 或 credentials。

## 相容性與邊界

自訂 `memory_recall_fn` 必須接受 keyword `as_of` 並使用它；舊 callback 會明確 TypeError，不能默默退回無時鐘 query。可用 `build_memory_context` 或 `build_hybrid_memory_context` 作 adapter。建立每個 arm 的目錄後設定 `db_path`、`log_path`、`checkpoint_path`；不依靠共享 CSV 的預設 checkpoint 名稱。

無 timezone 的記憶 timestamp 按 UTC 解讀。舊 replay DB 若存的是 naive broker time，需要先對 snapshot 做明確時區轉換；不能自動辨識。MT5 CSV 的 naive time 依 `broker_utc_offset` 固定轉 UTC；跨 DST 要由 caller 切段／提供正確 offset。這輪沒有做自動 migration。

這是 outcome eligibility 與 frozen metadata 的隔離。後來更新的 reflection／retrieval_strength 並未重建成歷史版本；不宣稱完整 point-in-time／bitemporal database。pilot 也沒有透過模型驗證完整 ReplayEngine 交易 loop。

## 驗證

```powershell
python -c "import os,sys;os.environ['ANTHROPIC_API_KEY']='';sys.path.insert(0,'src');import pytest;raise SystemExit(pytest.main(['tests/','-q']))"
```

空值僅存在該程序，保留現有 `.env`；`load_dotenv(override=False)` 不會把 key 補回，既有 live integration test 依原 skip 條件跳過。Windows asyncio 測試需要允許本機 socket。原 live test 的 401 失敗仍記錄於 RESULTS / validation，沒有修改 assertion 或聲稱已驗過真實 API。
