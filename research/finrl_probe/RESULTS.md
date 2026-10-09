# FinRL / FinRL-X 對 Sean 實驗的實測判斷

日期：2026-10-10。**generic FinRL-X 與最初 portfolio 成本路徑未通過必要檢查；可重用的是另行驗過的 StockTradingEnv + SB3。** 本次沒有量出值得部署的 PPO 優勢，也沒有測到 LLM 記憶的決策效果。保留下來的價值是經核算的研究環境與決策軌跡，不是新策略。

## 對目前工作的用處

| 工作 | 此次判斷 | 根據／邊界 |
|---|---|---|
| TradeMemory 的 controlled experiment | 有工程用途 | 15 個固定 seed 模型、48 條含成本回放可作測試材料；原 recall 已實測。尚無 memory-on/off 決策比較 |
| NG_Gold / MT5 EA | 尚不足以直接採用 | GLD 是 ETF；本試驗無 XAUUSD lot、leverage、spread、swap、tick fill 與 broker reconciliation，沒有 EA alpha 證據 |
| 已結案 AS1 / alpha-factory 研究 | 不因 FinRL 名字重新開題 | 此次沒有重跑 selector，也沒有新資料推翻原判決；資料／問題／決策者須有實質差異才算新試驗 |
| LLM + trading memory | 重用既有 replay，避免再造框架 | TradeMemory 本來已有 replay / prompt memory；FinMem、FinAgent 等先前工作已涵蓋此類機制，工程接通不構成新貢獻 |
| FinRL-X production stack | 本次僅能定位個別接口問題 | 沒有測 Alpaca、broker、strategy generator 全流程；不能從下述兩個函式推論整套系統 |

## 設計先凍結，失敗路徑留證據

原版來源：FinRL `00f3596…`、FinRL-Trading `4409abe…`；TradeMemory `c87372a…`（v0.5.6）。upstream checkout 的 tracked source 未修改。原計畫和市場試驗前的校準 amendment 見 [PROTOCOL.md](PROTOCOL.md)，市場／seed／費用／budget 沒因結果更換。

| 被測接口 | 已知答案對照 | 實際結果 | 採用決定 |
|---|---|---|---|
| FinRL PortfolioOptimizationEnv，`trf` | 平價買入也應付 10 bps | 首筆全倉後仍為 $10,000；指定買入成本 convention 應為 $9,990.00999 | 隔離；未拿去產生市場結果 |
| 同一 portfolio 接口 | 額外 terminal call 不應再次獎勵同一轉移 | 回傳前一次 reward −0.200305… | adapter 應在最後真實價格轉移結束 |
| FinRL-X generic BacktestEngine | 50% ETF、50% cash，價格漲 10% ⇒ portfolio 漲 5% | 結果漲 10%；權重被 normalize 為全倉；BacktestResult 沒有 trade trace | 不直接接 target-weight + cash 試驗 |
| adaptive-rotation 原報表函式 | 同上 half-cash 對照 | 漲 5%，通過 | 不把 generic 引擎問題套到此路徑 |
| adaptive-rotation 原報表函式 | 平價買賣應有成本損失 | 報表為 0%；該函式沒有費用參數／扣款 | 屬 gross report，不作 net-performance 裁判 |
| FinRL StockTradingEnv + adapter | 現金、半倉、全倉、整數股費用、原帳務等價、因果與故障注入 | 18 / 18 通過 | 本次唯一用於市場測試的 accounting 路徑 |

Portfolio roundtrip 差異另存原 JSON；約 $0.031 的誤差本身不是核心拒絕理由，首筆成本漏扣與重複 terminal reward 已足以擋住直接採用。未修改 upstream 讓失敗案例變成通過。

StockTradingEnv 的 target → integer-share action、20-bar 因果 OHLC observation、log-return reward ×100 由薄 adapter 提供。它沿用原版成交與可負擔股數，並省略額外 terminal 呼叫。不是拿 untouched default env 的 reward/observation 直接訓練；上述差異有明列。

## 固定 PPO 試跑

SPY / QQQ / GLD，Yahoo adjusted OHLC，各 2,953 日（2015-01-02～2026-09-30）。2015～2022 訓練；同一模型分別報告 2023～2024、2025～2026 Q3。每資產只配該 ETF 與 cash；起始 $10,000；每側 10 bps；整數股；決策 close_t、結果 close_(t+1)。五個預定 seeds：[11,23,37,51,71]，每個 32,768 timesteps，合計 491,520。沒有挑 seed、參數 sweep 或 test tuning。

下表是**扣模擬成本後的期間報酬，不是年化報酬**；PPO 列五 seed 中位數與完整範圍。cash baseline 全期均 0%，Sharpe / drawdown 均 0；full-target 每日以 100% 為目標，也受整數股與成本限制。

| Asset | Window | PPO 中位數 | PPO 五 seed 範圍 | Full-target | SMA20 |
|---|---|---:|---:|---:|---:|
| SPY | 2023-2024 | +8.22% | +4.86%～+15.47% | +56.61% | +25.57% |
| SPY | 2025-2026Q3 | +3.18% | -4.01%～+4.84% | +31.84% | +4.08% |
| QQQ | 2023-2024 | +14.27% | +11.45%～+24.15% | +93.48% | +45.79% |
| QQQ | 2025-2026Q3 | +10.62% | +3.43%～+26.64% | +44.14% | +9.40% |
| GLD | 2023-2024 | +0.92% | -10.69%～+2.52% | +41.95% | +9.34% |
| GLD | 2025-2026Q3 | -5.62% | -14.93%～+18.15% | +56.77% | +18.09% |

各 PPO 診斷欄分別取五 seed 中位數，不代表同一個 seed。Sharpe 使用日報酬、252 日年化、risk-free=0；turnover 為累計成交名目／成交前 equity，單位是倍。

| Asset | Window | PPO Sharpe | Full Sharpe | SMA Sharpe | PPO 最大回撤 | PPO target exposure | PPO turnover |
|---|---|---:|---:|---:|---:|---:|---:|
| SPY | 2023-2024 | 0.689 | 1.842 | 1.260 | -6.86% | 19.06% | 92.08 |
| SPY | 2025-2026Q3 | 0.244 | 1.038 | 0.286 | -8.87% | 19.94% | 98.27 |
| QQQ | 2023-2024 | 0.750 | 1.948 | 1.432 | -9.38% | 34.84% | 156.82 |
| QQQ | 2025-2026Q3 | 0.494 | 1.084 | 0.462 | -10.30% | 34.06% | 151.60 |
| GLD | 2023-2024 | 0.288 | 1.323 | 0.441 | -5.15% | 15.48% | 96.17 |
| GLD | 2025-2026Q3 | -0.327 | 1.155 | 0.587 | -14.36% | 17.64% | 88.87 |

實際判斷：這個 budget / observation / reward 設定未提供優於簡單基準的穩定證據。PPO 暴露較低，不能只按報酬低就宣稱「完全沒有 timing 能力」；Sharpe、drawdown、turnover 與 exposure 一起看。五個 seed 是同一段市場的訓練隨機性，不是五份獨立市場證據。近期 QQQ 有正結果，GLD 則有明顯 seed 分歧；沒有 best-seed 推薦。

48 組原 metrics 見 [market_results.json](market_results.json)。保存模型重新跑出完全相同的五項 metrics，再逐筆獨立核算 cash -= quantity × decision_price + fee、shares += quantity、value = cash + shares × next_close，**22,536 / 22,536 步通過**；最大容許差為 1e-7 美元。證據：[verification.json](verification.json)。這驗的是模擬帳務，不是成交可執行性。

## TradeMemory recall：有接通，但還不是 efficacy

用全部 15 個 PPO 歷史，每個 seed 分開存放，至少 10 筆歷史後才查詢。只輸入決策時已知的 context，outcome 次日才可加入記憶；沒有冒充 broker closed trade，也沒有捏造 pnl_r。直接呼叫目前原 `hybrid_recall`，embedding=None。

| 檢查 | 結果 |
|---|---:|
| top-5 queries | 13,935 |
| wall clock vs replay clock，top-5 次序／內容改變 | 3,629 / 13,935（26.04%） |
| outcome 排序的負 pnl slots | 27,427 / 69,675（39.36%） |
| losses-first 的負 pnl slots | 69,207 / 69,675（99.33%） |
| adapter 過濾後 future leaks | 0 |
| 故意輸入未來記憶：raw ranker 能否召回它 | 是，故障對照被檢出 |
| 去掉未來候選後是否回到過去記憶 | 是 |

意義：歷史實驗若直接使用今天的 wall clock，排名會變，必須指定 replay clock。raw ranker 不負責候選記憶的 as-of 過濾；注入 2030 年大虧損記憶會真的召回它，caller 必須先限制可用時間。過濾後零 future leak 是設計與已知答案檢查的結果，不是市場上的風控績效。

losses-first 的高負例比例主要由它的排序規則決定，不能把召回平均 pnl 當 expected return。這也修正初次基於舊 checkout 的判斷：本次已更新至 v0.5.6，並確認它已有 losses-first / pnl-only 支援，沒有重新實作。

本次沒有讓實際 LLM 根據記憶重新選動作。既有 replay 支援 LLM memory prompt，後續要用同一 decision-maker 對照 no-memory、等資訊簡單記憶、TradeMemory、shuffled/irrelevant memory，才能判斷「記憶是否幫助決策」。本次不拿檢索成功代替答案。

## 查過的現成工作及本次邊界

[FinRL 原環境](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/finrl/meta/env_stock_trading/env_stocktrading.py)、[FinRL-X generic 引擎](https://github.com/AI4Finance-Foundation/FinRL-Trading/blob/4409abe925c904e570be78ebfb5e77ac3491dff8/src/backtest/backtest_engine.py) 與 [rotation 報表原碼](https://github.com/AI4Finance-Foundation/FinRL-Trading/blob/4409abe925c904e570be78ebfb5e77ac3491dff8/src/strategies/run_adaptive_rotation_strategy.py) 是實際被執行的來源；沒有把 README 的 production 描述視為通過證據。

[FinMem 作者 repo](https://github.com/pipiku915/FinMem-LLM-StockTrading)、[FinAgent 原論文](https://arxiv.org/html/2402.18485v2)、[META 原論文](https://arxiv.org/html/2609.28771v1) 已把金融 agent、記憶與反思納入研究。本次用途是 reuse / integration measurement，沒有宣稱提出新 memory architecture，也沒有復現這些論文的績效。多 seed 與獨立評估依循 [SB3 官方建議](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html)。

限制：adjusted vendor snapshot 不是當時發布版本的完整 point-in-time database；same-close fill 是理想化 convention；未含 spread、slippage、稅、cash yield、borrow 或 broker 拒單。兩個 window 各自重置資金，雖然共用已訓練模型，但不是連續實盤。GLD 不能代替 MT5 黃金帳務。有限 CPU budget、單資產與這組 observation 不能代表所有 RL 設定；不作統計 alpha、promote 或 deploy 判決。

驗證：現有四組 recall / MCP tests 共 80 通過，沒有改 assertions。最初 sandbox 測試卡在 Windows asyncio socketpair（faulthandler 堆疊確認），開啟本機 socket 權限後通過；並非 embedding model 問題。詳見 [test_validation.json](test_validation.json)。來源 commits、資料 hashes、package versions 與保存物檢查入口見 [README.md](README.md)；模型、vendor snapshot、逐步回放均保留本機，不隨 Git 發布。

pending: 決策 efficacy 尚未測；要做時沿用現有 replay，先固定模型及等資訊 controls。本次足以支持小範圍重用 accounting / trajectory 工具，不足以支持改 EA 或導入整套 FinRL-X。
