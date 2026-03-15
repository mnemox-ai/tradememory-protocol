"""Prompt templates for the Evolution Engine.

P1 baseline prompts adapted for structured JSON output.
Separating prompts from logic for easy iteration.
"""

SYSTEM_PROMPT = """You are a quantitative trading researcher analyzing historical price data.
Your task is to discover repeatable trading patterns from OHLCV data.

RULES:
1. Focus on TIME-OF-DAY + TREND DIRECTION combinations (these have the strongest edge in crypto/forex)
2. Every pattern must have clear, programmable entry conditions
3. Prefer asymmetric risk/reward (RR >= 2:1)
4. Short holding periods (1-12 bars) to reduce exposure
5. Each pattern must specify when it does NOT work (validity_conditions)
6. Be specific about hour_utc (14:00 and 16:00 UTC are different strategies)
7. Output valid JSON only — no explanations outside the JSON"""

DISCOVERY_PROMPT = """Analyze this {timeframe} OHLCV data for {symbol} and discover {count} trading patterns.

## Data Summary
- Period: {start_date} to {end_date}
- Bars: {bar_count}
- Price range: {price_low:.2f} - {price_high:.2f}
- Average range per bar: {avg_range:.2f}
- Current ATR(14): {atr:.2f}

## Hourly Statistics (UTC)
{hourly_stats}

## Trend Analysis
- 12H trend: {trend_12h:+.2f}%
- 24H trend: {trend_24h:+.2f}%
- Regime: {regime}
- Volatility: {volatility_regime}

## Known Graveyard (strategies that already failed — do NOT reinvent these)
{graveyard_summary}

## Output Format
Return a JSON array of patterns. Each pattern MUST follow this exact schema:
```json
[
  {{
    "name": "Descriptive Strategy Name",
    "description": "2-3 sentence explanation of the edge and why it works",
    "entry_condition": {{
      "direction": "long" or "short",
      "conditions": [
        {{"field": "hour_utc", "op": "eq", "value": 14}},
        {{"field": "trend_12h_pct", "op": "gt", "value": 0.5}}
      ],
      "description": "Human readable entry logic"
    }},
    "exit_condition": {{
      "stop_loss_atr": 1.5,
      "take_profit_atr": 3.0,
      "max_holding_bars": 8
    }},
    "validity_conditions": {{
      "regime": "trending_up" or null,
      "volatility_regime": "normal" or null,
      "session": null,
      "min_atr_d1": null,
      "max_atr_d1": null
    }},
    "confidence": 0.6,
    "sample_count": 45
  }}
]
```

Available condition fields: hour_utc, day_of_week, session, regime, volatility_regime,
trend_12h_pct, trend_24h_pct, atr_percentile, atr_h1, atr_d1, price.

Available operators: gt, gte, lt, lte, eq, neq, between, in.

Return ONLY the JSON array. No markdown, no explanation."""

MUTATION_PROMPT = """You are given a trading pattern that showed some promise but needs improvement.

## Original Pattern
{pattern_json}

## Fitness Results (In-Sample)
- Sharpe: {sharpe:.2f}
- Win Rate: {win_rate:.1%}
- Profit Factor: {profit_factor:.2f}
- Trade Count: {trade_count}
- Max Drawdown: {max_dd:.1f}%

## Task
Generate {count} mutations of this pattern. Try:
1. Tighten or loosen entry conditions
2. Adjust SL/TP ratios
3. Add or remove time/regime filters
4. Flip direction if original was weak

Return a JSON array of {count} mutated patterns using the same schema as the original.
Return ONLY the JSON array."""
