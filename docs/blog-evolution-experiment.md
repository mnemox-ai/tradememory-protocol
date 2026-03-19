# I Let AI Invent Its Own Trading Strategies From Scratch. Here's What Happened.

*By Sean, CEO of Mnemox AI | March 2026*

---

Every AI trading bot has the same fatal flaw: amnesia.

There are 200+ trading MCP servers on GitHub right now. They can execute trades, pull market data, calculate indicators. But not a single one remembers what happened yesterday. Every session starts from zero. Every mistake gets repeated. Every lesson gets lost.

I spent two days building a system that fixes this — and what I found was far more interesting than I expected.

## The Deeper Question

The memory problem is real, but it's actually the *second* problem. The first one is more fundamental: why are we teaching AI how to trade at all?

Think about it. Every trading bot — from simple moving average crossovers to sophisticated ML systems — starts with a human saying "here's a strategy, go execute it." The human does the thinking. The AI does the labor. And when the strategy stops working (which it always does), the human has to go back, analyze what went wrong, redesign the strategy, and re-deploy.

What if we skipped the human part entirely?

Not "use machine learning to optimize parameters." I mean: give AI raw price data, give it persistent memory, give it *no* strategies whatsoever, and see if it can invent its own from scratch.

The idea isn't new. Google's AlphaEvolve uses evolutionary algorithms to discover novel solutions. The Ouroboros paper explored self-modifying agents. AZR (Absolute Zero Reasoner) showed that AI can bootstrap its own training data. DGM proposed Darwinian selection for agent populations. But nobody had applied this loop — observe, hypothesize, test, eliminate, evolve — to trading with persistent memory across sessions.

My hypothesis: **an AI with memory and the freedom to fail will converge on real market structure faster than any hand-coded strategy.**

## The $0 Experiment

I started with the cheapest possible test. Three months of BTC/USDT hourly candles (2,184 bars, December 2025 to March 2026). A bear market — BTC dropped 16% during this period.

I fed this raw data to Claude with a single instruction: *"You don't know any technical indicators. Describe what you see in your own words."*

No RSI. No MACD. No Bollinger Bands. Just price, volume, open, high, low, close.

It came back with seven patterns, each with its own name:

- **Breathing** (呼吸) — periodic expansion/contraction cycles
- **Giant Wave** (巨浪) — outsized candles that appear at turning points
- **Staircase** (階梯) — sequential directional moves
- **Fake Door** (假門) — false breakouts that reverse
- **Exhaustion** (枯竭) — declining momentum at trend ends
- **Tide** (潮汐) — time-of-day price flow patterns
- **Echo** (回聲) — price returning to prior levels

What made this interesting wasn't the patterns themselves — experienced traders would recognize most of these. What was interesting was what the AI did next: it scored each pattern for tradability and killed the weak ones. Staircase got 3/10. Fake Door got 4/10. Gone.

Nobody told it to do this. The prompt didn't mention anything about scoring or elimination. It just... decided some patterns weren't worth pursuing.

Then it combined the surviving patterns into a trading strategy.

## Round 1: Failure

The AI's first strategy was called "Giant Wave Reversal" (巨浪逆行): when an abnormally large candle appears, trade in the opposite direction.

Intuitively, this makes sense. After a big move, you'd expect a pullback. Hundreds of retail traders trade this exact pattern.

The backtest results:

| Metric | Result |
|--------|--------|
| Trades | 39 |
| Win Rate | 30.8% |
| Sharpe Ratio | -1.20 |
| Return | -0.21% |

Terrible. The strategy lost money.

But here's what matters: the system didn't just fail — it *analyzed* why it failed. Three specific causes:

1. **Momentum continuation** — big candles often signal the *start* of a trend, not the end
2. **Stop loss structure** — fixed-point stops were too tight for the volatility
3. **Counter-trend bias** — fighting the trend is statistically unfavorable

No human provided this analysis. The AI looked at its own results, examined the losing trades, and identified structural flaws.

## Round 2: Evolution

I fed the failure analysis back into the system with the same raw data. "You tried counter-trend. It failed for these reasons. Look at the data again."

This time, three candidate strategies emerged:

| Strategy | Trades | Win Rate | Sharpe | Status |
|----------|--------|----------|--------|--------|
| A: Ceiling Rejection | 6 | 50% | 0.74 | Sample too small |
| B: Trend Momentum | 67 | 35.8% | -1.40 | Eliminated |
| **C: US Session Drain** | **21** | **47.6%** | **1.90** | **Survived** |

Strategy C — which the AI named "美盤洩洪" (US Session Drain) — was a breakthrough. The rules:

- **Entry**: 16:00 UTC, when the 12-hour trend is down → go short
- **Exit**: Take profit at +0.5%, stop loss at -0.25%, max hold 6 hours
- **Risk/Reward**: 2:1

Sharpe went from -1.20 to 1.90 in a single evolutionary cycle.

But any quant will tell you: in-sample results mean nothing. You can curve-fit garbage to look profitable on historical data. The real test is out-of-sample.

### Out-of-Sample Validation

I ran Strategy C on a completely different 3-month period (August to November 2025) that the AI had never seen:

| Metric | In-Sample | Out-of-Sample |
|--------|-----------|---------------|
| Trades | 21 | 27 |
| Win Rate | 47.6% | 59.3% |
| Sharpe | 1.90 | 4.09 |
| Profit Factor | 1.53 | 2.25 |

The out-of-sample results were *better* than in-sample. Every metric improved. This is the opposite of overfitting — it suggests the strategy captured a genuine market structure, not noise.

## Can It Work in Bull Markets Too?

One strategy in one market regime proves nothing. So I ran the same process on bull market data: BTC going from $60K to $105K over four months (October 2024 to January 2025).

Same rules: raw data, no indicators, no guidance. Just "look and learn."

The AI discovered different patterns this time — waterfalls, valley springs, Asian fountains. But one stood out: **Afternoon Engine** (午後引擎). At 14:00 UTC, something happens. Price accumulated +14.9% at that single hour over the test period, far more than any other hour.

Strategy E's rules:
- **Entry**: 14:00 UTC, when the 12-hour trend is up → go long
- **Exit**: TP +0.5%, SL -0.25%, max hold 6 hours
- **Risk/Reward**: 2:1

First-round results: **70 trades, 50% win rate, Sharpe 4.97.**

It didn't need a second round. The bull market has stronger structural bias, so the AI hit on the first try.

### The Surprising Part

I validated Strategy E on a *downtrending* market (June to September 2024, BTC -6.2%). The 14:00 UTC hour actually *lost* money during this period (-5.84% cumulative). The raw time-of-day edge disappeared.

But Strategy E still profited: **57 trades, 56.1% win rate, Sharpe 6.06.**

Why? Because the 12-hour trend filter blocked almost all counter-trend signals. The edge isn't "trade at 14:00 UTC." The edge is "trade at 14:00 UTC *when the trend agrees*." The trend filter is the alpha source, not the time window.

The AI figured this out without being told. It didn't just discover a correlation — it discovered the *mechanism*.

## The Meta-Pattern

Here's where it gets genuinely interesting.

Strategy C and Strategy E were invented independently, from different datasets, in different market regimes (bear vs. bull). Yet they converged on the same structural template:

1. **Time-of-day bias** — specific UTC hours carry persistent directional edge
2. **Trend filter** — 12-hour trend confirmation before entry
3. **Short holding period** — max 6 hours, in-and-out
4. **Asymmetric risk/reward** — 2:1 TP/SL guarantees positive expectancy at 50% win rate

This meta-pattern was not programmed. It was not suggested. It emerged from two independent evolution cycles. When two completely separate experiments converge on the same solution, that's strong evidence of underlying structure.

## The Combined System

Running both strategies together over 22 months (June 2024 to March 2026), spanning a complete bull-to-bear cycle:

| System | Trades | Win Rate | Sharpe | Return | Max Drawdown |
|--------|--------|----------|--------|--------|--------------|
| C Only (SHORT) | 157 | 42.7% | 0.70 | +0.37% | 0.45% |
| E Only (LONG) | 320 | 49.4% | 4.10 | +3.65% | 0.27% |
| **C+E Combined** | **477** | **47.2%** | **3.84** | **+4.04%** | **0.22%** |

Key findings:

- **91% of months were profitable** (20 out of 22)
- **Max drawdown 0.22%** — lower than either strategy alone (natural hedging)
- **Zero human strategy input.** Every rule was discovered from raw candles
- Strategy E is the engine (90% of profit). Strategy C is a diversifier

The long/short combination creates a natural hedge. When the market trends up, E captures profits going long. When it trends down, C captures profits going short. Drawdown *improves* when combined.

## From Experiment to Product

The manual process — give AI data, analyze patterns, backtest, evolve — took about a day of hands-on work per strategy. Interesting as a research exercise, but not scalable.

So I automated the entire loop into what I call the **Evolution Engine**:

1. **Discover** — LLM analyzes raw price data, proposes candidate strategies
2. **Backtest** — vectorized engine tests each candidate (ATR-based stops, long/short, time-based exit)
3. **Select** — in-sample ranking, then out-of-sample validation (Sharpe > 1.0, trades > 30, max DD < 20%)
4. **Evolve** — survivors get mutated, failures go to the graveyard (but their lessons persist). Next generation. Repeat.

The Evolution Engine runs on top of **Outcome-Weighted Memory (OWM)** — a five-layer cognitive memory architecture that gives the AI agent persistent, context-aware recall:

- **Episodic** — specific trade memories ("that March 2nd breakout trade")
- **Semantic** — general knowledge ("breakouts work better in trending markets")
- **Procedural** — learned habits ("check the trend filter before entry")
- **Prospective** — future intentions ("if NFP beats, buy the dip")
- **Affective** — emotional state tracking (confidence, drawdown anxiety, streak awareness)

Every memory gets scored by five factors when recalled: outcome quality, context similarity, recency decay, confidence level, and affective state. It's inspired by ACT-R cognitive architecture and Kelly criterion — the same math that professional gamblers use to size bets.

### Model Comparison

I ran the automated pipeline with three Claude models on real Binance data:

| Model | Cost/Run | Speed | Strategies Graduated | Verdict |
|-------|----------|-------|---------------------|---------|
| **Haiku** | **$0.016** | **34.7s** | **2** | **Best** |
| Sonnet | $0.013 | 51.9s | 1 | Good |
| Opus | $0.013 | 72.4s | 1 | Worst |

The most expensive, most capable model performed worst. High reasoning ability doesn't help with creative pattern discovery — speed and diversity do. A full evolution cycle costs less than two cents.

The most compelling finding: the automated pipeline independently rediscovered 16:00 UTC as a key trading hour — the same edge that the manual experiments found. Convergent validation from a completely different process.

### Known Bottlenecks

The system isn't perfect. Two issues I'm actively working on:

1. **Prompt over-concretization** — all three models tend to lock onto very specific conditions (e.g., "hour_utc == 16 AND atr > 2.5"). This produces strategies that trigger too rarely for statistical significance. The graduated strategies had only 2 trades in out-of-sample, far below the 30-trade minimum for confidence.

2. **Graveyard feedback depth** — eliminated strategies get stored, but the feedback loop from graveyard → next generation isn't rich enough yet. The AI knows *that* a strategy failed, but doesn't fully leverage *why*.

## What I Learned

**1. AI doesn't need to be taught strategies. It needs memory and permission to fail.**

The biggest bottleneck in AI trading isn't model capability — it's the assumption that humans must provide the strategy. Give the AI raw data and a feedback loop, and it finds structure faster than any hand-designed system.

**2. Objective feedback (P&L) beats prompt engineering.**

I tried various prompt strategies for pattern discovery. None of them mattered as much as simply feeding back the backtest results. "$-0.21% return, Sharpe -1.20" is more useful than ten paragraphs of trading wisdom.

**3. The speed of evolution depends on the quality of failure, not the quantity of success.**

Strategy C only exists because Strategy "Giant Wave Reversal" failed spectacularly and the AI could analyze *why*. A clean failure with clear attribution is more valuable than a marginal success.

**4. Meta-patterns are the real prize.**

Individual strategies are nice. But the discovery that two independent evolution cycles converged on the same structural template (time bias + trend filter + short hold + asymmetric RR) — that's worth more than any single strategy. It suggests a universal regularity in how markets behave.

**5. One person + Claude Code can go from hypothesis to working product in a day.**

The entire pipeline — research, backtest, analysis, Evolution Engine code, OWM memory architecture, 1,055 tests, MCP server, open source release — was built in 48 hours by one person with an AI coding assistant. The leverage is absurd.

## Try It Yourself

TradeMemory Protocol is open source. The Evolution Engine, OWM memory architecture, and all 11 experiments documented in `RESEARCH_LOG.md` are available today.

```bash
pip install tradememory-protocol
```

The full research log with every backtest number, every eliminated strategy, and every lesson learned is in the repo.

I'm not claiming this is a finished product. The over-concretization problem is real. The automated pipeline needs more diverse hypothesis generation. But the core insight — that AI can discover its own trading strategies through evolutionary memory — is validated.

If you're building AI agents that make decisions in uncertain environments, the memory problem is yours too. Trading is just the most measurable version of it.


---

**Update (2026-03-17):** Ran statistical validation against 1,000 random strategies. Both Strategy C (P96.9%) and E (P100%) beat the 95th percentile. [Full results](https://github.com/mnemox-ai/tradememory-protocol/blob/master/docs/VALIDATION_RESULTS.md).

---

*TradeMemory Protocol: [github.com/mnemox-ai/tradememory-protocol](https://github.com/mnemox-ai/tradememory-protocol)*

*Full research data: [RESEARCH_LOG.md](https://github.com/mnemox-ai/tradememory-protocol/blob/master/docs/RESEARCH_LOG.md)*

*Built by [Mnemox AI](https://mnemox.ai) — persistent memory for AI agents.*
