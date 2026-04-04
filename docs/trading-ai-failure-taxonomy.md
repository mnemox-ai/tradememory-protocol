# Trading AI Failure Taxonomy

> **Version**: 1.0 | **Date**: 2026-04-04 | **Author**: Mnemox AI Research
>
> A systematic classification of failure modes in AI-driven trading systems, based on 7+ rigorous experiments conducted by Mnemox AI across XAUUSD, BTCUSDT, and multi-strategy portfolios from 2024 to 2026.

## Why This Exists

RAG systems have WFGY's 16 failure modes (adopted by LlamaIndex, RAGFlow). Trading AI has no equivalent — despite failure rates being far higher and financial consequences being real.

Every failure mode below is backed by actual experiment data: Sharpe ratios, p-values, trade counts, and DSR (Deflated Sharpe Ratio) gates. No simulated scenarios. No hypothetical examples.

**Data sources**: Sulci Phase 1-2 (M=7, 35,813 bars), Phase 15 Re-Evolution (M=19,200 grid + M=30 LLM), Memory Injection Experiment (4 OOS windows), Permutation Test (1,000 random shuffles), TradeDream Experiment (247 trades / 27 months), Phase 15 Sharpe Bug analysis.

---

## T1: Backtest Hallucination

**Category**: Backtesting
**Severity**: Critical
**Detection Difficulty**: Hard

### Description
回測表現漂亮但無法在 out-of-sample 上複製。模型捕捉到的是 in-sample 的統計噪音，不是真實的市場結構。

### Real Evidence
Sulci Phase 1: LightGBM 在 XAUUSD 1H (35,813 bars, 5 年) 上取得 DSR 4.47, p=0.0000 — 統計上極度顯著。但 Sharpe 只有 0.024, win rate 51.6%, PF 1.10, drawdown -67%。年化 Sharpe 看起來是 1.87 (0.024 x sqrt(252x24))，但 -67% drawdown 代表風險調整後根本不可行。

### Symptoms
- 年化 Sharpe > 1.5 但 max drawdown > 50%
- DSR pass 但 raw Sharpe < 0.05
- 大量樣本 (T=35,709) 讓微小 edge 也能通過統計檢定

### Root Cause
大 T (樣本數) 讓統計檢定的 power 極高，即使 effect size 趨近零也能 reject null hypothesis。這是數學事實，不是 bug。

### Fix Direction
同時檢查 statistical significance (DSR) 和 practical significance (raw Sharpe, drawdown, cost boundary)。設定 cost boundary: Sulci 在 cost 0.0001 PASS, cost 0.0005 FAIL, 而實盤 XAUUSD spread ~ 0.0003，剛好在生死線上。

### Misrepair Risk
如果只加 cost filter 而不改驗證框架，會漏掉其他形式的 in-sample overfitting。需要 CPCV + walk-forward + cost sweep 三重驗證。

---

## T2: Regime Blindness

**Category**: Memory
**Severity**: Critical
**Detection Difficulty**: Very Hard

### Description
策略只在特定 market regime 有效，regime 切換後失效。大多數 Trading AI 不偵測 regime，導致在錯誤環境下持續交易。

### Real Evidence
Memory Injection Experiment, 4 個 OOS windows:
- W1 (2024 H1->H2): FAIL (Sharpe -4.25 fixed / -1.96 re-search)
- W2 (2024 H2->2025 H1): FAIL (-8.04 / -2.76)
- W3 (2025 H1->H2): FAIL/PASS (-10.01 / +1.56)
- W4 (2025 H2->2026): PASS/PASS (+6.26 / +6.26)

固定配置 1/4 pass, 重新搜尋 2/4 pass。結論：REGIME-SPECIFIC。Phase 13 Evolution Engine 也驗證了相同結論 — 策略在 2024-2026 有效，extended OOS FAIL。

### Symptoms
- 策略在某些半年表現極好 (Sharpe > 3)，其他半年虧損
- Walk-forward 的 OOS 表現高度不穩定
- 記憶配置需要隨市場重新調整才有效

### Root Cause
金融市場存在 regime switching (trending / ranging / volatile)。單一策略對 regime 變化不具 robustness。進場前的 context 無法預測 regime 何時切換。

### Fix Direction
建立 regime detection layer (HMM regime probability 在 Sulci 所有 45 folds 中排名 feature importance #1)，根據 regime 選擇策略組合而非用固定策略。

### Misrepair Risk
過度 regime detection 會變成另一種 overfitting — 為每個 regime 量身定制策略等於 curve fitting with extra steps。

---

## T3: Memory Poisoning

**Category**: Memory
**Severity**: High
**Detection Difficulty**: Very Hard

### Description
將歷史交易記憶作為 features 注入模型，不但沒有改善反而惡化表現。模型在記憶噪音上 overfit。

### Real Evidence
Sulci Experiment C (Memory-Augmented, M=7): 加入 6 個 memory features (18-dim: mem_available, avg_pnl, win_rate, similarity_pctl, count, regime_agreement) 後：
- Sharpe 從 baseline 0.024 變成 **-0.0020** (變負)
- DSR -1.55, p=0.94
- PF 0.99, Win 49.9%, Drawdown -210%
- Column_13 (mem_avg_pnl_r) 進入 top-5 feature importance — 模型確實在用記憶特徵，但學到了錯誤的方向

### Symptoms
- 加入 memory features 後 Sharpe 下降或轉負
- Memory feature 在 feature importance 中排名高但模型表現更差
- Drawdown 大幅惡化 (從 -67% 到 -210%)

### Root Cause
Phase 15 排列測試已證明 OWM-derived features 在統計上是噪音 (0/4 windows significant)。模型能「看到」記憶特徵並賦予權重，但這些特徵不含有效信號，等於學習了更精緻的噪音。

### Fix Direction
Memory 不應作為 ML feature 注入模型。有效的使用方式是：(1) regime detection 輔助，(2) position sizing 調整，(3) 團隊知識管理。不要把 recall 結果當作 predictive signal。

### Misrepair Risk
如果改為「更好的 memory encoding」(e.g. embedding, attention)，可能只是讓 overfitting 更精緻。根本問題是 entry context similarity 不具 outcome 預測力。

---

## T4: Statistical Mirage

**Category**: Statistical
**Severity**: Critical
**Detection Difficulty**: Very Hard

### Description
看起來有顯著 edge 的策略，在 permutation test 下被證明不比隨機好。

### Real Evidence
Memory injection 最佳配置 (majority_negative skip logic) 在原始窗口 Sharpe 從 3.31 提升到 9.57。但 1,000 次隨機 skip 同比例交易的 permutation test:
- W1: P60.9 (不顯著)
- W2: P10.5 (比隨機差)
- W3: P2.4 (比隨機差)
- W4: P87.4 (有信號但未達 P95 門檻)

**0/4 windows significant。Memory-based trade filtering 不比隨機好。** Sharpe 9.57 是幻覺。

### Symptoms
- 策略改善看起來很大 (Sharpe 3x 提升) 但沒做 permutation test
- 所有 entry context 長得一樣 (e.g. Strategy E: H14 + trend>0)，similarity 無法區分贏輸
- 文件宣稱 "+30% PnL improvement" 但標注 "Simulated"

### Root Cause
Trade filtering (skip/no-skip) 改變了 trade composition。如果 75% 交易被跳過，隨機跳 75% 也可能產生類似效果。Permutation test 是唯一能分離「smart selection」和「random luck」的方法。

### Fix Direction
任何 trade filtering 改善都必須通過 permutation test (P >= 95)。不是可選的 robustness check，是必要的因果驗證。

### Misrepair Risk
如果只提高 filter 門檻 (e.g. P99)，可能把真正有效的弱信號也擋掉。正確做法是承認 entry context similarity 沒有 outcome 預測力，改用其他維度做決策。

---

## T5: Filter Overcorrection

**Category**: Backtesting
**Severity**: High
**Detection Difficulty**: Easy

### Description
為了提升勝率或品質而加入過嚴的 filter，導致交易量從數萬筆暴跌到兩位數，完全喪失統計驗證的可能。

### Real Evidence
Sulci Experiment A (Selective Filter, M=5): min_confidence=0.6 + min_regime_prob=0.7 過濾條件，交易量從 27,381 筆暴跌到 53 筆 (99.8% 被過濾)。
- Sharpe 0.0023, DSR -0.53, p=0.70
- PF 1.19, Win 37.7%

53 筆交易不足以做任何統計推斷。LightGBM 的 max probability 不是好的 trade filter — 高信心預測不等於高品質預測。

### Symptoms
- 過濾後交易量下降 > 90%
- 剩餘交易量不足以計算可靠的 Sharpe / DSR
- 高 confidence threshold 反而降低了 win rate

### Root Cause
ML 分類器的 probability output 是 calibrated 的 class probability，不是 trade quality score。高 probability 只代表模型「比較確定」這個方向，不代表這個方向的 edge 比較大。

### Fix Direction
先確認 trade filter 的 T 在過濾後仍足夠 (建議 T >= 100)，再評估 filter 效果。或者不做 binary filter，改用 continuous sizing。

### Misrepair Risk
放寬 filter (e.g. 0.6 降到 0.55) 是在做 hyperparameter tuning without M increment — 本質上是 data snooping。任何 filter 調整都應計入 M counter。

---

## T6: Sample Starvation

**Category**: Statistical
**Severity**: High
**Detection Difficulty**: Easy

### Description
交易量不足以支撐任何統計驗證。在 low-frequency 策略中特別致命。

### Real Evidence
TradeDream Experiment: 3 策略 (VB 102 trades, IM 112, PB 33) 合計 247 trades / 27 months = ~9 trades/month。原始計畫假設 200-500 trades/month，實際差 20 倍。OOS window T >= 100 的門檻不可能達到 — 每月 OOS 只有 2-17 trades。

Phase 15 Grid WFO 也有類似問題: M=19,200 + 30-50 trades/period → DSR threshold ~0.7 raw Sharpe → 數學上不可能通過。

### Symptoms
- 每月交易量 < 30 筆
- Walk-forward OOS 窗口 trade count < 100
- DSR threshold 因為高 M 值而變得不可達

### Root Cause
Low-frequency 策略 (daily/4H bars) 天然產生少量交易。加上 filter 和 entry conditions，可用樣本更少。統計驗證需要 N，N 買不到。

### Fix Direction
四個方向: (1) 放寬統計門檻 T >= 20-30 (犧牲 power), (2) 擴大 OOS window (IS 6mo + OOS 3mo), (3) 跨資產增加樣本 (但偏離原始場景), (4) 改用 bootstrap/permutation 在全部樣本上做。

### Misrepair Risk
放寬統計門檻 (T >= 20) 會讓 false positive rate 上升。這不是修復，是 tradeoff。最誠實的做法可能是承認「這個頻率下無法統計驗證」。

---

## T7: Evolution Graveyard

**Category**: Evolution
**Severity**: High
**Detection Difficulty**: Hard

### Description
策略演化系統的 graduation rate = 0%。所有候選策略都無法通過統計 gate。

### Real Evidence
Phase 15 Re-Evolution:
- **Grid WFO (Exp 4a)**: M=19,200, Layer 1 Gate FAIL 3/3, DSR 0/23 pass, mean Sharpe = 0.0
- **LLM Evolution (Exp 4b)**: M=30, Layer 2 Gate FAIL 2/3, Cohen's d = 0.000 → STOP
- LLM 有 structural novelty (6 種 grid 之外的 features)，但 graduation rate = 0% 使比較無意義

條件限制: 1H timeframe + 3-month rolling window + single-hour entry strategies。

### Symptoms
- 大量候選策略全部被 DSR gate 擋住
- Grid search 的 M 值爆炸 (19,200) 導致 DSR threshold 不可達
- 即使 LLM 產生了新穎策略，在統計上仍然不顯著

### Root Cause
Grid search 的 multiple testing penalty 太重 (M=19,200 → threshold ~0.7 raw Sharpe)。在 30-50 trades/period 的條件下，0.7 Sharpe 數學上不可能。不是演化概念失敗，是 search space 太大而 evidence 太少。

### Fix Direction
LLM evolution 的 M ~ 30 → DSR threshold ~ 0.42 → achievable。**LLM 的價值不是找到更好的策略，而是用更少測試找到 DSR-defensible 的策略。** Search efficiency = statistical survival advantage。

### Misrepair Risk
降低 DSR threshold (e.g. 用更寬鬆的 alpha) 等於放水 — false positive rate 上升。正確方向是減少 M，不是降低門檻。

---

## T8: Sharpe Annualization Trap

**Category**: Infrastructure
**Severity**: Critical
**Detection Difficulty**: Easy

### Description
錯誤的 Sharpe ratio 年化公式，導致數值膨脹 6-8 倍，讓失敗策略看起來像成功。

### Real Evidence
Phase 15 Sharpe Bug: `backtester.py` 用 `sqrt(6048)` 年化 trade-level PnLs — over-annualize ~6-8x。修正前 Grid WFO 顯示 "G > A 91.3%"（看起來 grid 比 random 好），修正後 **0/23 DSR gate pass, mean Sharpe = 0.0**。

前一版結論是「grid search 有效」，修正後結論是「grid search 完全失敗」。一個年化公式 bug 翻轉了整個實驗結論。

### Symptoms
- Trade-level Sharpe 被乘以 sqrt(N) 而 N 是年化的交易次數而非時間週期
- 同窗口比較不應年化 (用 raw Sharpe)
- 修正前後結論完全相反

### Root Cause
年化因子 sqrt(N) 中的 N 應該是「每年的獨立觀察次數」。如果用 trade count (e.g. 6048 trades/year) 而不是 time periods (e.g. 252 trading days)，會嚴重高估。且 trade-level returns 不是等間隔的，sqrt(N) annualization 的前提不成立。

### Fix Direction
同窗口比較一律用 raw Sharpe。跨窗口比較才年化，且用 calendar-based periods (sqrt(252) for daily, sqrt(52) for weekly)，不用 trade count。

### Misrepair Risk
完全不年化也有問題 — 無法比較不同長度的回測。正確做法是明確標注 raw vs annualized，並在 code 層面用 `annualize=False` 作為 default。

---

## T9: Overfitting via Complexity

**Category**: Backtesting
**Severity**: High
**Detection Difficulty**: Hard

### Description
增加模型複雜度 (更多 features, 更多 layers, 更精緻的出場邏輯) 不但沒有改善，反而全部失敗。

### Real Evidence
Sulci Phase 2: 三條獨立的改善路線全部 FAIL:
1. **Selective Filter (Exp A)**: 後端過濾 → Sharpe 0.0023, DSR -0.53 (FAIL)
2. **SL/TP Bar-by-Bar (Exp B)**: 出場工程 (SL 1.5xATR, TP 3.0xATR) → Sharpe 0.0002, DSR -1.04, Win 42.1% (FAIL)
3. **Memory-Augmented (Exp C)**: 記憶增強 (6 features, 18-dim) → Sharpe -0.0020, DSR -1.55 (FAIL, 比 baseline 更差)
4. **Combined (Exp D)**: SKIPPED — 沒有任何單項通過，組合無意義

Phase 1 的 Sharpe 0.024 來自 12 base features + regime detection。**Edge 不可再厚化。**

### Symptoms
- 增加 features 後 Sharpe 下降或持平
- SL/TP 加入後 win rate 下降 (42.1% vs baseline 51.6%) 因為 SL 比 TP 更常被觸發
- 2:1 reward-risk ratio 被低勝率完全抵消

### Root Cause
Phase 1 model 沒有 timing precision — 它知道方向但不知道「什麼時候」會到。SL/TP 需要精確的 timing，filter 需要品質區分能力，memory 需要 context 差異性。三者都不存在。

### Fix Direction
接受 edge 上限。改從 cost reduction / execution optimization 下手，而不是加複雜度。或者換到更高頻率的 timeframe 以獲得更多 timing information。

### Misrepair Risk
換更複雜的模型 (e.g. deep learning, transformer) 只是用更強的 approximator 去 fit 同樣的噪音。如果信號本身只有 Sharpe 0.024，模型能捕捉的上限就是 0.024。

---

## T10: Survivorship Bias in Memory

**Category**: Memory
**Severity**: Medium
**Detection Difficulty**: Very Hard

### Description
記憶系統的 scoring mechanism 偏向正面記憶，導致 recall 永遠回傳贏的交易，系統無法從失敗中學習。

### Real Evidence
Memory Injection Experiment 發現 OWM recall 設計缺陷: `outcome_weight` 使用 sigmoid 函數偏向正面記憶 (positive PnL)，導致 recall 永遠抓到贏的交易 → 永遠不觸發 skip logic。

修正方案: 改用純 cosine similarity 排序 (不看結果好壞)，再看 outcome 分布。修正後的 majority_negative skip logic (7 個最相似記憶中超過半數虧損就跳過) 在原始窗口 Sharpe 從 3.31 提升到 9.57 — 但後續被 permutation test 否定 (0/4 significant)。

### Symptoms
- Memory recall 結果偏向正面 (高 PnL trades)
- Skip logic 幾乎不觸發因為 recalled trades 都是贏的
- 系統在連續虧損後仍然 "confident" 因為記憶裡都是好結果

### Root Cause
OWM 的 outcome_weight sigmoid 是 monotonically increasing — PnL 越高 weight 越大。這在「找最好的參考」場景合理，但在「評估風險」場景完全反向。

### Fix Direction
分離 recall 和 scoring。Recall 用純 similarity (cosine)，scoring 根據使用場景決定: 風險評估看 negative outcomes，信心評估看 distribution，不要一個 sigmoid 打全部。

### Misrepair Risk
如果改成偏向負面記憶 (inverse sigmoid)，會變成另一個極端 — 系統過度保守，永遠不交易。正確做法是 unweighted recall + context-dependent scoring。

---

## T11: Cross-Asset Hallucination

**Category**: Backtesting
**Severity**: Medium
**Detection Difficulty**: Hard

### Description
假設一個資產上有效的 pipeline 可以直接遷移到另一個資產，但 alpha 來源是 asset-specific 的。

### Real Evidence
Sulci 跨資產研究 (非正式): BTCUSDT 1H (18,000 bars, 2024-03 to 2026-04) → DSR -0.28, p=0.61 (FAIL)。

Win rate 跟 XAUUSD 幾乎一樣 (51.7% vs 51.6%)，但差異在 return size: XAUUSD PF=1.10 (贏的比輸的大), BTCUSDT PF=0.99 (一樣大)。regime_prob 在兩個 asset 都是 #2 feature，但只有 gold 能把 regime awareness 變成 alpha。

Signal 是 gold-specific，可能跟央行行為、London fix、實體需求有關。

### Symptoms
- 同一 pipeline 在不同資產上的 PF 差異顯著 (1.10 vs 0.99)
- Win rate 相同但 return asymmetry 不同
- Regime feature 重要性類似但 alpha 轉化率不同

### Root Cause
Edge 來自 return asymmetry (贏的比輸的大)，不是方向準確率。不同資產的 return distribution 特性不同，同一 feature set 無法捕捉 asset-specific 的 microstructure。

### Fix Direction
每個資產需要獨立的 feature engineering (e.g. BTC 可能需要 funding rate, open interest, exchange flows)。不要用同樣的 pipeline 追跨資產。

### Misrepair Risk
如果加入 asset-specific features 但不增加 M counter，等於在新 asset 上做 free exploration — 回到 T7 (Evolution Graveyard) 問題。

---

## Summary Table

| ID | Name | Category | Severity | Detection | Key Metric |
|----|------|----------|----------|-----------|------------|
| T1 | Backtest Hallucination | Backtesting | Critical | Hard | Sharpe 0.024, DD -67%, 看似顯著但不可行 |
| T2 | Regime Blindness | Memory | Critical | Very Hard | OOS 1/4 pass (fixed), 2/4 pass (re-search) |
| T3 | Memory Poisoning | Memory | High | Very Hard | Sharpe 0.024 → -0.0020, DD -67% → -210% |
| T4 | Statistical Mirage | Statistical | Critical | Very Hard | Sharpe 9.57 幻覺, permutation 0/4 significant |
| T5 | Filter Overcorrection | Backtesting | High | Easy | 27,381 trades → 53 trades (99.8% 被過濾) |
| T6 | Sample Starvation | Statistical | High | Easy | 247 trades / 27mo = 9/mo, 需要 200-500/mo |
| T7 | Evolution Graveyard | Evolution | High | Hard | M=19,200, graduation rate 0%, DSR 0/23 pass |
| T8 | Sharpe Annualization Trap | Infrastructure | Critical | Easy | 6-8x over-annualize, 翻轉整個實驗結論 |
| T9 | Overfitting via Complexity | Backtesting | High | Hard | Phase 2 三條路線全 FAIL, edge 不可厚化 |
| T10 | Survivorship Bias in Memory | Memory | Medium | Very Hard | sigmoid 偏向正面記憶, skip logic 不觸發 |
| T11 | Cross-Asset Hallucination | Backtesting | Medium | Hard | XAUUSD PF=1.10 vs BTCUSDT PF=0.99, 同 pipeline |

---

## Category Distribution

| Category | Count | Critical | High | Medium |
|----------|-------|----------|------|--------|
| Backtesting | 4 | 1 | 2 | 1 |
| Memory | 3 | 1 | 1 | 1 |
| Statistical | 2 | 1 | 1 | 0 |
| Evolution | 1 | 0 | 1 | 0 |
| Infrastructure | 1 | 1 | 0 | 0 |

---

## How to Use This Taxonomy

1. **Before building**: Check which failure modes your system is susceptible to
2. **During development**: Use the Symptoms section as a checklist
3. **After backtest**: Run through T1, T4, T8 before celebrating any results
4. **Before live**: Ensure T2 (regime), T5 (filter), T6 (sample) are addressed

**The single most important lesson from 7+ experiments**: Statistical significance is necessary but not sufficient. Permutation tests are the only way to establish causation in trade filtering. And edge, once found, resists all attempts to be made thicker.
