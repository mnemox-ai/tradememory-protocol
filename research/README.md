# Research: Behavioral Drift Detection for AI Trading Agents

Reproduction package for the paper:

> **Behavioral Drift Detection for AI Trading Agents: A Statistical Process Control Approach**
> Syuan Wei Peng, Mnemox AI (2026)

## Prerequisites

```bash
cd tradememory-protocol
pip install -e .                          # install tradememory
pip install -r research/requirements.txt  # scipy, etc.
```

## Reproduction Steps

### Level 2: Multi-Strategy Validation (main experiment)

```bash
# 1. Run the full 200-strategy matrix (~30 min, needs Binance API)
cd research/level2
python run_matrix.py

# 2. Statistical analysis → RESULTS.md
python analyze.py

# 3. Robustness check without BTCUSDT 1h
python robustness_without_btc1h.py

# 4. Threshold sensitivity analysis (h = 2,3,4,5,6)
python h_sensitivity.py

# 5. Comparison with MaxDDStop baseline
python compare_maxdd.py
```

### Output Files

| File | Description |
|------|-------------|
| `results.json` | Raw per-strategy results (200 entries, 5 agents each) |
| `RESULTS.md` | Human-readable analysis report |
| `robustness_no_btc1h.json` | Stats without BTCUSDT 1h segment |
| `h_sensitivity.json` | CUSUM threshold sweep results |
| `compare_maxdd.json` | CUSUM vs MaxDDStop comparison |

### Key Scripts

| Script | Purpose |
|--------|---------|
| `run_matrix.py` | Main experiment: 5 agents x 200 strategies |
| `analyze.py` | Statistical analysis (t-test, bootstrap, Cohen's d) |
| `cusum_agent.py` | CUSUMOnlyAgent implementation |
| `baselines_clean.py` | 3 naive baselines (Periodic, Random, SimpleWR) |
| `maxdd_baseline.py` | MaxDDStop standard risk management baseline |

## Data

All experiments use Binance OHLCV data (BTCUSDT, ETHUSDT), fetched via API.
Data period: 1095 days (3 years), walk-forward split 67%/33%.

## Notes

- Random seed is fixed (42) for reproducibility
- Strategy grid generates 243 combinations, filtered to ~150 valid
- Each market segment uses the first 50 qualifying strategies
- CUSUM threshold h=4.0, lot reduction x0.5 (same for all agents)
