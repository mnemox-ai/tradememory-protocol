# FinRL / TradeMemory reuse probe

2026-10-10，Sean 授權研究及本機試驗。先看 [RESULTS.md](RESULTS.md)，事前條件與校準修改在 [PROTOCOL.md](PROTOCOL.md)。只改研究目錄與專案狀態；沒有交易下單、付費模型呼叫或 production 邏輯改動。

## 實際重用的元件

FinRL 原始 `StockTradingEnv` 負責成交、整數股、現金與費用；Stable-Baselines3 原始 PPO 負責學習；TradeMemory 原始 `hybrid_recall` 負責排名。新增程式處理 target weight → share action、Gym API、因果觀察、log-return reward、批次流程與獨立核算。沒有自製 RL、backtest engine 或 ranking。

另兩條未通過的路徑保留原始量測：FinRL `PortfolioOptimizationEnv` 的 `trf`、FinRL-X generic `BacktestEngine`。`check_rotation.py` 以 AST 原樣抽出 adaptive-rotation 的報表函式，避免 import 時觸發資料與 broker 副作用；不是整套 strategy replication。

## 重跑（PowerShell，repo root）

本機已有 `.venv`、原始碼 checkout、資料 snapshot、15 個模型及 48 條回放，均放在此目錄的 `.cache`。先驗證保存物，再重播，不必重新訓練：

```powershell
$probePython = '.\research\finrl_probe\.venv\Scripts\python.exe'
& $probePython research/finrl_probe/probe.py artifacts
& $probePython research/finrl_probe/probe.py verify
```

在新 checkout 建環境及取得同一版 upstream：

```powershell
python -m venv research/finrl_probe/.venv
$probePython = '.\research\finrl_probe\.venv\Scripts\python.exe'
& $probePython -m pip install -r research/finrl_probe/requirements.txt
New-Item -ItemType Directory -Force research/finrl_probe/.cache/upstream | Out-Null
git clone https://github.com/AI4Finance-Foundation/FinRL.git research/finrl_probe/.cache/upstream/FinRL
git -C research/finrl_probe/.cache/upstream/FinRL checkout 00f3596facd01cced5217d875d8c1fc413a31665
git clone https://github.com/AI4Finance-Foundation/FinRL-Trading.git research/finrl_probe/.cache/upstream/FinRL-Trading
git -C research/finrl_probe/.cache/upstream/FinRL-Trading checkout 4409abe925c904e570be78ebfb5e77ac3491dff8
& $probePython research/finrl_probe/probe.py controls
& $probePython research/finrl_probe/check_rotation.py
```

新下載 Yahoo 資料可能被修訂；**不能把新 snapshot 稱為原結果的精確重現**。原 `manifest.json` 記錄 CSV SHA-256；原始 vendor 資料、模型與逐筆回放保留本機，沒有隨 Git 發布。若可取得原本 `.cache/data` 與 `.cache/models`，先比對 hash 再執行 `verify`。全新探索 run 應另存此目錄及原 manifest/results，依序跑 `fetch`、`train`、`verify`、`recall`，避免覆寫本次證據。

`train/verify/recall` 會拒絕 upstream commit、tracked source、protocol 或 CSV hash 變動。新環境的 direct dependency versions 有固定；原環境使用 `--system-site-packages`，本檔不是完整 transitive lock，也沒有宣稱另一部機器已成功重現。

## 證據

| 檔案 | 用途 |
|---|---|
| `controls.json` | 可用 StockTradingEnv 路徑的 18 個帳務／因果／故障對照 |
| `portfolio_controls.json` | 最初失敗路徑，保留而未修成綠燈 |
| `rotation_controls.json` | adaptive-rotation 原報表函式的兩個已知答案測試 |
| `market_results.json` | 48 組 asset × method/seed × window，完整列出 |
| `verification.json` | 保存模型重播及 22,536 步獨立現金／持股／費用核算 |
| `recall_results.json` | 13,935 次 pure recall，比較 replay clock 與 losses-first |
| `manifest.json` | 資料 hash、原始碼 commits、主要 package versions |
| `artifact_manifest.json` | 66 個本機 cache 產物與本次研究檔的 hash |
| `test_validation.json` | 現有 80 個 recall / MCP 測試結果與環境限制 |

`recall` 用的是模擬每日 portfolio decision，不是 broker closed trade。它沒有 embedding，也沒有讓 LLM 根據記憶重新下決策。losses-first 的虧損比例與 caller 過濾後的零 future leak 都受設計約束，不能當成盈利或風控有效性的證據。

pending: 若要判斷 TradeMemory 是否改善決策，沿用現有 `src/tradememory/replay/`，先固定實際模型，再比較 no-memory、等資訊簡單記憶、TradeMemory 與 shuffled/irrelevant-memory 對照；不得用手寫 veto 代替模型實驗。本次未執行該 efficacy 比較。
