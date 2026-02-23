# Reflection Report Format Design

This document defines the output format for TradeMemory's reflection reports. These reports are what users see when their agent "reflects" on its trading performance.

---

## Design Philosophy

**Goal:** Make the reflection report feel like a human trader's journal entry — insightful, actionable, and honest about mistakes.

**NOT like this (bad):**
```
Performance: 66.7% win rate, 1.24R average
Trade count: 12
Winners: 8
Losers: 4
```
*This is just data. No insight. No story.*

**Like this (good):**
```
This week I made some mistakes, but I also learned something important:

Asian session isn't working. I took 4 trades there and lost 3 of them. 
The problem? Low volatility leads to false breakouts. I'm going to 
reduce my position size by 50% for Asian session until this changes.

London session, on the other hand, is performing beautifully. 5 out of 5 
wins on VolBreakout strategy. I've earned the right to increase my 
position size there.
```
*This tells a story. Shows learning. Explains the "why."*

---

## Report Types & Cadence

| Type | Frequency | Purpose | Length |
|------|-----------|---------|--------|
| **Daily Summary** | End of each trading day | Quick performance check, immediate adjustments | ~150 words |
| **Weekly Review** | End of trading week | Pattern discovery, strategy analysis, risk parameter updates | ~500 words |
| **Monthly Deep Dive** | End of month | Strategic evolution, portfolio-level insights | ~1000 words |
| **Incident Review** | Triggered by large loss | Root cause analysis, preventive measures | ~300 words |

---

## Format Specification

### Daily Summary

**Trigger:** End of trading day (or when `reflect.run_daily` is called)

**Structure:**

```markdown
# Daily Trading Summary — [Date]

## Today's Performance
- Trades: [N] ([W] wins / [L] losses)
- Net P&L: [+/-$XX.XX] ([+/-R.RR]R)
- Win rate: [XX%]

## Notable Events
[2-3 bullet points about interesting trades or market conditions]

## Immediate Adjustments
[Any parameter changes made based on today's data]

---
*Next review: [Tomorrow's date]*
```

**Example:**

```markdown
# Daily Trading Summary — February 23, 2026

## Today's Performance
- Trades: 3 (2 wins / 1 loss)
- Net P&L: +$42.30 (+1.8R)
- Win rate: 66.7%

## Notable Events
- ✅ Excellent London open trade on XAUUSD (T-2026-0251) — caught the momentum early, 2.1R gain
- ✅ Pullback strategy working well on high timeframe support
- ❌ Asian session breakout failed again (T-2026-0252) — same pattern as last week

## Immediate Adjustments
None today. Watching Asian session pattern — if this continues tomorrow, 
will trigger risk parameter adjustment.

---
*Next review: February 24, 2026*
```

---

### Weekly Review (Primary Format)

**Trigger:** End of trading week (Friday close or Monday morning)

**Structure:**

```markdown
# Weekly Reflection — Week [N], [Year]
*[Start Date] to [End Date]*

---

## Executive Summary
[2-3 sentence overview: overall performance + key learnings]

---

## Performance Snapshot

| Metric | This Week | Last Week | Change |
|--------|-----------|-----------|--------|
| Total Trades | [N] | [N] | [+/-N] |
| Winners | [N] | [N] | [+/-N] |
| Losers | [N] | [N] | [+/-N] |
| Win Rate | [XX%] | [XX%] | [+/-XX%] |
| Net P&L | [+/-$XXX] | [+/-$XXX] | [+/-$XXX] |
| Avg R | [X.XX]R | [X.XX]R | [+/-X.XX]R |

---

## What I Learned This Week

### What's Working
[List of positive patterns discovered]

**Example:**
> London session VolBreakout strategy is performing exceptionally — 5 out 
> of 5 wins this week. The key seems to be waiting for volume confirmation 
> at the session open. Trades with confidence > 0.7 in this setup have 
> an 80% win rate.
>
> *Evidence: T-2026-0241, T-2026-0243, T-2026-0247, T-2026-0249, T-2026-0251*

### What's Not Working
[List of negative patterns discovered]

**Example:**
> Asian session continues to be a problem. 3 out of 4 losses this week 
> happened during Asian session. The issue is clear: low volatility leads 
> to false breakouts. I keep getting stopped out before the real move happens.
>
> *Evidence: T-2026-0238, T-2026-0242, T-2026-0245*
>
> **My decision:** I'm reducing Asian session position size by 50% starting 
> next week. If the pattern doesn't improve in 2 weeks, I'll stop trading 
> Asian session entirely.

### Things to Test
[Hypotheses to explore next week]

**Example:**
> I noticed that holding winners past 45 minutes improved my average R from 
> 1.1 to 1.8. My current exit strategy might be too aggressive. Next week 
> I want to test a trailing stop approach on strong momentum trades.

---

## Risk Parameter Updates

[Table showing what changed and why]

| Parameter | Old Value | New Value | Reason |
|-----------|-----------|-----------|--------|
| Asian session max lot | 0.05 | 0.025 | Poor performance (25% win rate) |
| London VolBreakout max lot | 0.05 | 0.08 | Earned more room (100% win rate) |

---

## Action Items for Next Week

- [ ] Monitor Asian session pattern — stop trading there if performance doesn't improve
- [ ] Test trailing stop implementation on London momentum trades
- [ ] Watch for NFP announcement Friday — high volatility expected

---

## Top Trades of the Week

**Best Trade: T-2026-0251**
- **Strategy:** VolBreakout
- **P&L:** +$28.50 (+2.1R)
- **What went right:** Perfect entry on London open, volume confirmation, exited at 2R target
- **Lesson:** This is the template for a great trade

**Worst Trade: T-2026-0245**
- **Strategy:** VolBreakout
- **P&L:** -$15.20 (-1.0R)
- **What went wrong:** Asian session false breakout, stopped out before reversal
- **Lesson:** Stop trading Asian breakouts until volatility returns

---

*Report generated: [Timestamp]*
*Next review: [Next week's date]*
```

---

### Example: Full Weekly Review

```markdown
# Weekly Reflection — Week 8, 2026
*February 17-21, 2026*

---

## Executive Summary

Strong week overall with 66.7% win rate and +$187.30 net P&L. The big 
insight: London session is my bread and butter, but Asian session is 
actively hurting my performance. Making significant risk adjustments.

---

## Performance Snapshot

| Metric | This Week | Last Week | Change |
|--------|-----------|-----------|--------|
| Total Trades | 12 | 14 | -2 |
| Winners | 8 | 7 | +1 |
| Losers | 4 | 7 | -3 |
| Win Rate | 66.7% | 50.0% | +16.7% |
| Net P&L | +$187.30 | +$92.50 | +$94.80 |
| Avg R | 1.24R | 0.85R | +0.39R |

---

## What I Learned This Week

### What's Working

**London session VolBreakout is exceptionally strong**

I went 5 for 5 on London session breakout trades this week. The pattern 
is clear: when I wait for volume confirmation at the London open (09:00-09:15), 
and price breaks a key level with conviction, the trade almost always works.

There's also a strong confidence correlation: my trades with confidence > 0.7 
had an 80% win rate, while trades with confidence < 0.5 only had a 40% win rate. 
This tells me I should trust my gut on these setups.

*Evidence: T-2026-0241, T-2026-0243, T-2026-0247, T-2026-0249, T-2026-0251*

**My decision:** I'm increasing my max lot size for London VolBreakout 
trades from 0.05 to 0.08. I've earned this.

---

### What's Not Working

**Asian session is killing me**

3 out of my 4 losses this week happened during Asian session. The problem 
is consistent: low volatility leads to false breakouts. I enter on what 
looks like a breakout, get stopped out 10-15 pips later, and then the 
market actually moves in my direction — but I'm already out.

This isn't bad luck. This is a systematic problem with my strategy in 
low-volatility environments. Asian session just doesn't have the momentum 
I need for breakout trades.

*Evidence: T-2026-0238, T-2026-0242, T-2026-0245*

**My decision:** Starting next week, I'm cutting my Asian session position 
size in half (0.05 → 0.025). If the pattern continues for another 2 weeks, 
I'll stop trading Asian session entirely.

---

### Things to Test

**Exit timing might be too aggressive**

I noticed something interesting: the two trades where I held past 45 minutes 
(T-2026-0247 and T-2026-0249) had an average R of 1.8, while my quick exits 
averaged only 1.1R.

My current exit strategy is to take profit at 2R or if momentum fades. But 
"momentum fading" might be too subjective. Maybe I'm exiting too early on 
strong trending moves.

**Hypothesis:** A trailing stop approach might capture more of the move 
on strong momentum trades.

**Test plan:** Next week, on London session trades with confidence > 0.75, 
I'll use a 15-pip trailing stop instead of a fixed 2R target. Let's see 
if this improves my average R.

---

## Risk Parameter Updates

| Parameter | Old Value | New Value | Reason |
|-----------|-----------|-----------|--------|
| Asian session max lot | 0.05 | 0.025 | 25% win rate this week — reducing exposure |
| London VolBreakout max lot | 0.05 | 0.08 | 100% win rate — earned more room |
| Risk per trade | 1.0% | 1.0% | No change — comfortable at this level |

---

## Action Items for Next Week

- [ ] Monitor Asian session performance with new reduced lot size
- [ ] Test trailing stop approach on London momentum trades (confidence > 0.75)
- [ ] Watch for NFP announcement on Friday — expect high volatility, adjust accordingly
- [ ] Review exit timing data at end of week to validate trailing stop hypothesis

---

## Top Trades of the Week

**Best Trade: T-2026-0251**
- **Date:** February 21, 09:03
- **Strategy:** VolBreakout (London session)
- **P&L:** +$28.50 (+2.1R)
- **Entry reasoning:** "London session open with strong momentum above 20-period high. Volume spike confirmed at 09:03. Price broke 2890 resistance with conviction."
- **What went right:** Perfect timing on volume confirmation. High confidence (0.72) was justified. Exited at 2R target as planned.
- **Lesson:** This is the template for my best setups. Wait for the confirmation, trust high confidence, execute cleanly.

**Worst Trade: T-2026-0245**
- **Date:** February 20, 02:47
- **Strategy:** VolBreakout (Asian session)
- **P&L:** -$15.20 (-1.0R)
- **Entry reasoning:** "Breakout above 2885 with moderate momentum. Similar to previous Asian session trades."
- **What went wrong:** False breakout due to low volatility. Stopped out 12 pips later. Price eventually moved up, but I was already out.
- **Lesson:** Stop trading Asian breakouts. The volatility isn't there. This is the third time this pattern has happened.

---

*Report generated: February 22, 2026 at 00:15 UTC*
*Next review: February 29, 2026*
```

---

## Formatting Guidelines for LLM Generation

When generating reflection reports via LLM (Claude/GPT), use these prompts:

### Daily Summary Prompt

```
You are a trading agent reflecting on today's performance. 

Review the following trades from today:
[Insert trade data]

Write a brief daily summary (150 words max) that covers:
1. Performance metrics (trades, win/loss, P&L)
2. 2-3 notable events or interesting trades
3. Any immediate adjustments needed

Write in first person. Be honest about mistakes. Focus on learning.
Use markdown format.
```

### Weekly Review Prompt

```
You are a trading agent reflecting on this week's performance.

Review the following trades from this week:
[Insert trade data from the week]

Previous week's performance:
[Insert comparison data]

Write a weekly reflection report (500 words) that:
1. Summarizes performance with a comparison table
2. Identifies patterns (what's working, what's not)
3. Proposes testable hypotheses for next week
4. Updates risk parameters with clear reasoning
5. Highlights best and worst trades

Write in first person. Be analytical but conversational. Make specific,
actionable recommendations. Use the markdown template provided in
REFLECTION_FORMAT.md.
```

---

## Output Destinations

Reflection reports should be:
1. **Stored** in `data/reflections/YYYY-MM-DD_[type].md`
2. **Displayed** to the user via dashboard/CLI
3. **Accessible** via `reflect.get_insights` MCP tool
4. **Used** by AdaptiveRisk to update risk parameters

---

## Human Override Option

Users should be able to:
- Mark a reflection as "reviewed"
- Add their own notes to a reflection
- Override risk parameter changes (with audit trail)

This is handled by `risk.override` MCP tool (requires authentication).

---

## See Also

- [SCHEMA.md](SCHEMA.md) — Data structure reference
- [README.md](../README.md) — Project overview
- [Reflection Engine Guide](REFLECTION_ENGINE_GUIDE.md) — Implementation details
