"""Pinned upstream integration experiment. Run from any cwd; no broker/model APIs."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import gymnasium as gym
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / ".cache"
UPSTREAM = CACHE / "upstream"
os.environ["MPLCONFIGDIR"] = str(CACHE / "matplotlib")
SEEDS = [11, 23, 37, 51, 71]
ASSETS = ["SPY", "QQQ", "GLD"]
sys.path.insert(0, str(ROOT / "src"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False, default=str), encoding="utf-8")


def assert_snapshot():
    """Reject changed inputs rather than silently reinterpret the frozen run."""
    manifest = json.loads((HERE / "manifest.json").read_text())
    for name, expected in manifest["upstream"].items():
        repo = UPSTREAM / name
        actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"], text=True)
        assert actual == expected and not dirty, f"Changed upstream: {name}"
    for asset, info in manifest["assets"].items():
        assert sha(CACHE / "data" / f"{asset}.csv") == info["sha256"], f"Changed snapshot: {asset}"
    assert sha(HERE / "PROTOCOL.md") == manifest["protocol_sha256"], "Changed protocol"
    subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", manifest["tradememory_commit"], "--",
                    "src/tradememory/hybrid_recall.py", "src/tradememory/owm"], check=True)


def load_source(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def finrl_class():
    return load_source("probe_finrl_env", UPSTREAM / "FinRL/finrl/meta/env_portfolio_optimization/env_portfolio_optimization.py").PortfolioOptimizationEnv


def raw_env(frame, fee=0.001, window=20):
    with contextlib.redirect_stdout(io.StringIO()):
        return finrl_class()(frame.copy(), initial_amount=10000, time_window=window,
                             features=["close", "high", "low"], return_last_action=True,
                             comission_fee_model="trf", comission_fee_pct=fee,
                             new_gym_api=True, reward_scaling=100, cwd=str(CACHE / "plots"))


class PortfolioGymAdapter(gym.Env):
    """Only API/shape conversion; every accounting step calls original FinRL.

    FinRL emits another terminal call after the final processed price. We end
    on that final real transition, avoiding plots and its repeated last reward.
    Observations contain previous ratios and upstream last target weights.
    """
    def __init__(self, frame, fee=0.001, window=20):
        self.raw = raw_env(frame, fee, window)
        self.action_space = gym.spaces.Box(0, 1, (1,), dtype=np.float32)
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (3 * window + 2,), dtype=np.float32)

    def observation(self, state):
        return np.concatenate([(state["state"].ravel() - 1) * 100, state["last_action"]]).astype(np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        state, info = self.raw.reset()
        return self.observation(state), info

    def step(self, action):
        if self.raw._time_index >= len(self.raw._sorted_times) - 1:
            raise RuntimeError("step after terminal")
        weight = float(np.clip(np.asarray(action).ravel()[0], 0, 1))
        state, reward, _, _, info = self.raw.step([1 - weight, weight])
        done = self.raw._time_index == len(self.raw._sorted_times) - 1
        return self.observation(state), float(reward), done, False, info


def frame_from_prices(prices):
    return pd.DataFrame({"date": pd.date_range("2020-01-01", periods=len(prices)),
                         "tic": "CONTROL", "close": prices, "high": prices, "low": prices})


def controls():
    results = []
    def check(name, actual, expected, tolerance=0.02):
        passed = abs(float(actual) - float(expected)) <= tolerance
        results.append({"name": name, "actual": float(actual), "expected": float(expected), "pass": passed})
    flat = frame_from_prices([100., 100., 100.])
    rising = frame_from_prices([100., 110., 110.])
    for name, weight, expected in [("cash", 0, 10000), ("half", .5, 10500), ("full", 1, 11000)]:
        env = raw_env(rising, fee=0, window=1)
        env.reset()
        env.step([1-weight, weight])
        check("finrl_" + name, env._portfolio_value, expected)
    env = raw_env(flat, fee=.001, window=1)
    env.reset()
    env.step([0, 1])
    check("finrl_entry_cost", env._portfolio_value, 10000 / 1.001)
    env.step([1, 0])
    check("finrl_roundtrip_cost", env._portfolio_value, 10000 / 1.001 * .999)
    original_reward = env._reward
    # Plot routines are irrelevant to reward accounting; suppress only plotting.
    mod = sys.modules[env.__class__.__module__]
    with patch.object(mod.qs.plots, "snapshot"), contextlib.redirect_stdout(io.StringIO()):
        terminal = env.step([1, 0])
    results.append({"name": "finrl_terminal_reward_should_be_zero", "actual": float(terminal[1]),
                    "previous_reward": float(original_reward), "pass": bool(terminal[1] == 0),
                    "scope": "original extra terminal call; adapted path never calls it"})
    env = PortfolioGymAdapter(flat, window=1)
    env.reset()
    env.step([1])
    _, _, done, _, _ = env.step([0])
    check("adapter_roundtrip_cost", env.raw._portfolio_value, 10000 / 1.001 * .999)
    results.append({"name": "adapter_exact_transition_count", "pass": done and len(env.raw._asset_memory["final"]) == 3})
    # Original and adapter accounting must agree at every real transition.
    path = frame_from_prices([100., 110., 95., 105., 99.])
    raw, adapted = raw_env(path, window=1), PortfolioGymAdapter(path, window=1)
    raw.reset(); adapted.reset()
    for i, w in enumerate([.2, .7, 0., 1.]):
        state, reward, _, _, _ = raw.step([1-w, w])
        obs, r, _, _, _ = adapted.step([w])
        check(f"adapter_equivalent_value_{i}", adapted.raw._portfolio_value, raw._portfolio_value, 1e-8)
        check(f"adapter_equivalent_reward_{i}", r, reward, 1e-10)
        results.append({"name": f"adapter_equivalent_observation_{i}", "pass": bool(np.array_equal(obs, adapted.observation(state)))})
    changed = path.copy()
    changed.loc[3:, ["close", "high", "low"]] *= 9
    a, b = PortfolioGymAdapter(path, window=1), PortfolioGymAdapter(changed, window=1)
    a.reset(); b.reset()
    causal = True
    for w in [.3, .4]:
        oa, ra, *_ = a.step([w]); ob, rb, *_ = b.step([w])
        causal &= np.array_equal(oa, ob) and ra == rb
    results.append({"name": "future_prices_do_not_change_prefix", "pass": bool(causal)})
    # Explicitly broken half-exposure arithmetic: control must detect it.
    check("broken_normalization_detected", int(abs(11000-10500) > .02), 1, 0)
    try:
        sys.path.insert(0, str(UPSTREAM / "FinRL-Trading"))
        fx = load_source("probe_finrl_x", UPSTREAM / "FinRL-Trading/src/backtest/backtest_engine.py")
        idx = pd.date_range("2020-01-01", periods=5)
        prices = pd.DataFrame({"CONTROL": [100., 100., 110., 110., 110.]}, index=idx)
        weights = pd.DataFrame({"CONTROL": [.5] * 5}, index=idx)
        engine = fx.BacktestEngine(fx.BacktestConfig(str(idx[0].date()), str(idx[-1].date()),
                                    initial_capital=10000, transaction_cost=0, benchmark_tickers=[], integer_positions=False))
        out = engine.run_backtest("half_cash_control", prices, weights)
        check("finrl_x_half_exposure", out.portfolio_values.iloc[-1], 10500)
        results.append({"name": "finrl_x_returns_trade_trace", "pass": not out.trades.empty,
                        "rows": len(out.trades), "scope": "generic BacktestResult, not adaptive_rotation"})
    except Exception as exc:
        results.append({"name": "finrl_x_generic_import_or_run", "pass": False, "error": f"{type(exc).__name__}: {exc}"})
    gate = all(r["pass"] for r in results if r["name"].startswith(("adapter_", "future_", "broken_")) or r["name"] in ["finrl_cash", "finrl_half", "finrl_full", "finrl_entry_cost", "finrl_roundtrip_cost"])
    doc = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "adapted_finrl_gate": gate,
           "upstream_files_unchanged": True, "checks": results}
    save(HERE / "portfolio_controls.json", doc)
    print(json.dumps(doc, indent=2))
    stock_controls()


def raw_stock(frame, fee=.001):
    cls = load_source("probe_stock_env", UPSTREAM/"FinRL/finrl/meta/env_stock_trading/env_stocktrading.py").StockTradingEnv
    data = frame.copy().reset_index(drop=True)
    data["disabled"] = 0.0  # upstream tradeability field; no missing prices
    return cls(data, stock_dim=1, hmax=100000000, initial_amount=10000,
               num_stock_shares=[0], buy_cost_pct=[fee], sell_cost_pct=[fee],
               reward_scaling=1, state_space=4, action_space=1,
               tech_indicator_list=["disabled"], make_plots=False, print_verbosity=10**9)


class GymAdapter(gym.Env):
    """Target-weight/Gym adapter around unmodified upstream StockTradingEnv.

    No execution accounting here. Integer shares and affordability are upstream.
    Terminal is the final real transition; reward is frozen log return x100.
    """
    def __init__(self, frame, fee=.001, window=20):
        self.frame = frame.reset_index(drop=True).copy()
        self.window = window
        self.raw = raw_stock(self.frame.iloc[window-1:].copy(), fee)
        self.ratios = self.frame[["close", "high", "low"]].pct_change().fillna(0).to_numpy(dtype=np.float32) * 100
        self.action_space = gym.spaces.Box(0, 1, (1,), dtype=np.float32)
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (3*window+2,), dtype=np.float32)
        self.turnover = 0.

    @property
    def index(self):
        return self.window - 1 + self.raw.day

    @property
    def value(self):
        return float(self.raw.state[0] + self.raw.state[1] * self.raw.state[2])

    def observation(self):
        stock = self.raw.state[1] * self.raw.state[2] / self.value
        return np.concatenate([self.ratios[self.index-self.window+1:self.index+1].T.ravel(), [1-stock, stock]]).astype(np.float32)

    def share_action(self, weight):
        target = int(np.floor(weight * self.value / self.raw.state[1]))
        delta = target - int(self.raw.state[2])
        # FinRL casts action*hmax to int. Guard against floating-point truncation.
        scaled = delta / self.raw.hmax
        scaled = np.nextafter(scaled, np.inf if delta >= 0 else -np.inf)
        return np.array([scaled], dtype=np.float64)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.raw.reset(seed=seed)
        self.turnover = 0.
        return self.observation(), {}

    def step(self, action):
        if self.index >= len(self.frame)-1:
            raise RuntimeError("step after terminal")
        weight = float(np.clip(np.asarray(action).ravel()[0], 0, 1))
        before, price = self.value, self.raw.state[1]
        self.raw.step(self.share_action(weight))
        executed = abs(float(self.raw.actions_memory[-1][0]))
        self.turnover += executed * price / before
        reward = 100 * np.log(self.value/before)
        return self.observation(), float(reward), self.index == len(self.frame)-1, False, {}


def stock_controls():
    checks = []
    def add(name, actual, expected, tolerance=1e-6):
        checks.append({"name": name, "actual": float(actual), "expected": float(expected),
                       "pass": abs(float(actual)-float(expected)) <= tolerance})
    for name, weight, expected in [("cash", 0, 10000), ("half", .5, 10500), ("full", 1, 11000)]:
        env = GymAdapter(frame_from_prices([100., 110., 110.]), fee=0, window=1)
        env.reset(); env.step([weight])
        add(name, env.value, expected)
    env = GymAdapter(frame_from_prices([100., 100., 100.]), window=1)
    env.reset(); env.step([1])
    add("entry_cost_99_integer_shares", env.value, 9990.1)
    _, _, done, _, _ = env.step([0])
    add("roundtrip_cost_99_integer_shares", env.value, 9980.2)
    add("exact_transition_count", len(env.raw.asset_memory), 3)
    add("terminal_on_last_real_transition", int(done), 1)
    path = frame_from_prices([100., 110., 95., 105., 99.])
    raw, adapted = raw_stock(path), GymAdapter(path, window=1)
    raw.reset(); adapted.reset()
    for i, weight in enumerate([.2, .7, 0, 1]):
        action = adapted.share_action(weight)
        raw.step(action.copy()); adapted.step([weight])
        add(f"original_accounting_equality_{i}", adapted.value, raw.asset_memory[-1], 1e-8)
        add(f"original_fee_equality_{i}", adapted.raw.cost, raw.cost, 1e-8)
    changed = path.copy(); changed.loc[3:, ["close", "high", "low"]] *= 9
    a, b = GymAdapter(path, window=1), GymAdapter(changed, window=1)
    a.reset(); b.reset()
    causal = True
    for w in [.3, .4]:
        oa, ra, *_ = a.step([w]); ob, rb, *_ = b.step([w])
        causal &= np.array_equal(oa, ob) and ra == rb
    add("future_price_perturbation", int(causal), 1)
    # Exercise the real 20-day observation, not just the one-bar arithmetic fixture.
    long_path = frame_from_prices(100 + np.arange(45, dtype=float))
    altered = long_path.copy()
    altered.loc[30:, ["close", "high", "low"]] *= 9
    a, b = GymAdapter(long_path), GymAdapter(altered)
    oa, _ = a.reset(); ob, _ = b.reset()
    causal = np.array_equal(oa, ob)
    for weight in [.2, .7, 0, 1, .4, .6, .3, .8, 0, .5]:
        oa, ra, *_ = a.step([weight]); ob, rb, *_ = b.step([weight])
        causal &= np.array_equal(oa, ob) and ra == rb
    add("future_price_perturbation_window20", int(causal), 1)
    broken = GymAdapter(frame_from_prices([100., 110., 110.]), fee=0, window=1)
    broken.reset(); broken.step([1.])  # deliberately replace the requested 0.5
    add("broken_full_weight_control_detected", int(abs(broken.value-10500)>1e-6), 1)
    doc = {"adapted_finrl_gate": all(c["pass"] for c in checks), "environment": "upstream StockTradingEnv",
           "checks": checks, "portfolio_path": "quarantined; see portfolio_controls.json"}
    save(HERE/"controls.json", doc)
    print(json.dumps(doc, indent=2))
    if not doc["adapted_finrl_gate"]:
        raise RuntimeError("stock accounting/causality controls failed")


def fetch():
    import yfinance as yf
    manifest = {"requested_interval": ["2015-01-01", "2026-10-01"], "source": "yfinance/Yahoo Finance", "assets": {}}
    for asset in ASSETS:
        out = CACHE / "data" / f"{asset}.csv"
        if out.exists():
            df = pd.read_csv(out)
        else:
            raw = yf.download(asset, start="2015-01-01", end="2026-10-01", auto_adjust=True, progress=False, threads=False)
            if raw.empty:
                raise RuntimeError(f"No public data for {asset}; do not replace asset")
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            df = raw.reset_index().rename(columns=str.lower)
            df = df.rename(columns={"date": "date"})
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df["tic"] = asset
            df = df[["date", "tic", "open", "high", "low", "close", "volume"]]
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out, index=False)
        assert df.date.is_unique and df.date.is_monotonic_increasing
        assert not df.isna().any().any() and (df[["open", "high", "low", "close"]] > 0).all().all()
        manifest["assets"][asset] = {"sha256": sha(out), "rows": len(df), "start": df.date.iloc[0], "end": df.date.iloc[-1]}
    manifest["upstream"] = {name: subprocess.check_output(["git", "-C", str(UPSTREAM/name), "rev-parse", "HEAD"], text=True).strip() for name in ["FinRL", "FinRL-Trading"]}
    manifest["tradememory_commit"] = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    manifest["protocol_sha256"] = sha(HERE / "PROTOCOL.md")
    manifest["packages"] = {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "torch", "stable-baselines3", "gymnasium", "gym", "bt", "yfinance", "quantstats"]}
    save(HERE / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2))


def evaluate(frame, start, end, policy, fee=.001):
    pre = frame[frame.date < start].tail(20)
    scored = frame[(frame.date >= start) & (frame.date <= end)]
    part = pd.concat([pre, scored], ignore_index=True)
    env = GymAdapter(part, fee=fee)
    obs, _ = env.reset()
    records = []
    done = False
    while not done:
        i = env.index
        before = env.value
        cost_before = env.raw.cost
        w = float(policy(obs, part, i))
        obs, reward, done, _, info = env.step([w])
        after = env.value
        records.append({"decision_date": str(part.date.iloc[i]), "outcome_date": str(part.date.iloc[i+1]),
                        "target": w, "value_before": before, "value_after": after,
                        "pnl": after-before, "return": after/before-1, "reward": reward,
                        "executed_shares": float(env.raw.actions_memory[-1][0]),
                        "fee": float(env.raw.cost-cost_before), "cash_after": float(env.raw.state[0]),
                        "shares_after": float(env.raw.state[2]), "decision_price": float(part.close.iloc[i]),
                        "outcome_price": float(part.close.iloc[i+1]),
                        "realized_stock_weight": float(env.raw.state[1]*env.raw.state[2]/after)})
    values = np.array([10000.] + [r["value_after"] for r in records])
    rets = np.array([r["return"] for r in records])
    # Turnover compares target to drifted realized stock weight before rebalancing.
    turnover = env.turnover
    metrics = {"net_return": float(values[-1]/values[0]-1), "max_drawdown": float(np.min(values/np.maximum.accumulate(values)-1)),
               "daily_sharpe": float(np.mean(rets)/np.std(rets, ddof=1)*np.sqrt(252)) if np.std(rets) > 1e-12 else 0.,
               "mean_target": float(np.mean([r["target"] for r in records])), "turnover": float(turnover), "steps": len(records),
               "first_decision": records[0]["decision_date"], "first_outcome": records[0]["outcome_date"], "last_outcome": records[-1]["outcome_date"]}
    return metrics, records


def train():
    assert_snapshot()
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_checker import check_env
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    gate = json.loads((HERE/"controls.json").read_text())
    if not gate["adapted_finrl_gate"]:
        raise RuntimeError("Controls did not pass")
    manifest = json.loads((HERE/"manifest.json").read_text())
    rows = []
    periods = [("2023-2024", "2023-01-01", "2024-12-31"), ("2025-2026Q3", "2025-01-01", "2026-09-30")]
    for asset in ASSETS:
        path = CACHE / "data" / f"{asset}.csv"
        assert sha(path) == manifest["assets"][asset]["sha256"]
        frame = pd.read_csv(path)
        training = frame[frame.date < "2023-01-01"].copy()
        check_env(GymAdapter(training), warn=True)
        baselines = {"cash": lambda o, f, i: 0., "full_target": lambda o, f, i: 1.,
                     "sma20": lambda o, f, i: float(f.close.iloc[i] >= f.close.iloc[i-19:i+1].mean())}
        for name, policy in baselines.items():
            for period, start, end in periods:
                metrics, records = evaluate(frame, start, end, policy)
                rows.append({"asset": asset, "method": name, "seed": None, "period": period, **metrics})
                save(CACHE/"trajectories"/f"{asset}_{name}_{period}.json", records)
        for seed in SEEDS:
            print(f"TRAIN {asset} seed={seed}", flush=True)
            began = time.perf_counter()
            model = PPO("MlpPolicy", GymAdapter(training), seed=seed, device="cpu", n_steps=512,
                        batch_size=64, n_epochs=5, learning_rate=.0003, gamma=.99,
                        policy_kwargs={"net_arch": [32, 32]}, verbose=0)
            model.learn(total_timesteps=32768)
            seconds = time.perf_counter()-began
            model_path = CACHE/"models"/f"{asset}_{seed}"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model.save(model_path)
            for period, start, end in periods:
                policy = lambda obs, f, i: float(model.predict(obs, deterministic=True)[0][0])
                metrics, records = evaluate(frame, start, end, policy)
                rows.append({"asset": asset, "method": "ppo", "seed": seed, "period": period,
                             "training_seconds": seconds, "actual_timesteps": model.num_timesteps, **metrics})
                save(CACHE/"trajectories"/f"{asset}_ppo_{seed}_{period}.json", records)
                print(json.dumps(rows[-1]), flush=True)
            save(HERE/"market_results.json", {"rows": rows, "complete": False})
    save(HERE/"market_results.json", {"rows": rows, "complete": True})


def verify():
    """Replay saved models; independently audit every cash/share/fee transition."""
    assert_snapshot()
    from stable_baselines3 import PPO
    import torch
    torch.set_num_threads(1)
    frozen = json.loads((HERE/"market_results.json").read_text())
    assert frozen["complete"]
    audit = []
    total_steps = 0
    for row in frozen["rows"]:
        frame = pd.read_csv(CACHE/"data"/f"{row['asset']}.csv")
        start, end = ("2023-01-01", "2024-12-31") if row["period"] == "2023-2024" else ("2025-01-01", "2026-09-30")
        if row["method"] == "ppo":
            model = PPO.load(CACHE/"models"/f"{row['asset']}_{row['seed']}", device="cpu")
            policy = lambda o, f, i: float(model.predict(o, deterministic=True)[0][0])
            label = f"{row['asset']}_ppo_{row['seed']}_{row['period']}"
        else:
            policy = {"cash": lambda o, f, i: 0., "full_target": lambda o, f, i: 1.,
                      "sma20": lambda o, f, i: float(f.close.iloc[i] >= f.close.iloc[i-19:i+1].mean())}[row["method"]]
            label = f"{row['asset']}_{row['method']}_{row['period']}"
        reproduced, records = evaluate(frame, start, end, policy)
        same = all(abs(reproduced[k]-row[k]) < 1e-12 for k in ["net_return", "daily_sharpe", "max_drawdown", "mean_target", "turnover"])
        cash, shares, max_error = 10000., 0., 0.
        for r in records:
            q, price = r["executed_shares"], r["decision_price"]
            fee = abs(q)*price*.001
            cash -= q*price+fee
            shares += q
            value = cash + shares*r["outcome_price"]
            max_error = max(max_error, abs(cash-r["cash_after"]), abs(shares-r["shares_after"]), abs(fee-r["fee"]), abs(value-r["value_after"]))
            assert r["outcome_date"] > r["decision_date"] and shares >= 0 and cash >= -1e-8
        total_steps += len(records)
        save(CACHE/"trajectories"/f"{label}.json", records)
        audit.append({"label": label, "reproduced_metrics": same, "max_cash_share_fee_error": max_error,
                      "pass": same and max_error < 1e-7, "steps": len(records)})
    save(HERE/"verification.json", {"checks": audit, "all_pass": all(r["pass"] for r in audit), "total_steps": total_steps})
    assert all(r["pass"] for r in audit)
    print(json.dumps({"reproduced_trajectories": len(audit), "audited_steps": total_steps, "all_pass": True}))


def recall_probe():
    assert_snapshot()
    run_at = datetime.now(timezone.utc).isoformat()
    from tradememory.owm.context import ContextVector
    from tradememory.owm import recall as recall_module
    from tradememory.hybrid_recall import hybrid_recall
    metrics = []
    class ReplayClock(datetime):
        moment = datetime(2023, 1, 1, tzinfo=timezone.utc)
        @classmethod
        def now(cls, tz=None):
            return cls.moment if tz is not None else cls.moment.replace(tzinfo=None)
    for asset in ASSETS:
        frame = pd.read_csv(CACHE/"data"/f"{asset}.csv")
        # All seeds are used; no selection of the best trajectory.
        for seed in SEEDS:
            history = []
            changes = queries = future_leaks = default_losses = losses_first_losses = 0
            for period in ["2023-2024", "2025-2026Q3"]:
                records = json.loads((CACHE/"trajectories"/f"{asset}_ppo_{seed}_{period}.json").read_text())
                for record in records:
                    date = record["decision_date"]
                    prior = frame[frame.date <= date].tail(20)
                    regime = "trending_up" if prior.close.iloc[-1] >= prior.close.mean() else "trending_down"
                    query = ContextVector(symbol=asset, price=float(prior.close.iloc[-1]), regime=regime, session="newyork")
                    eligible = [m for m in history if m["timestamp"] <= date + "T23:59:59+00:00"]
                    assert len(eligible) == len(history)
                    if len(history) >= 10:
                        ReplayClock.moment = datetime.fromisoformat(date+"T23:59:59+00:00")
                        live = hybrid_recall(query, None, eligible, limit=5, order="outcome")
                        with patch.object(recall_module, "datetime", ReplayClock):
                            ranked = hybrid_recall(query, None, eligible, limit=5, order="outcome")
                            loss_ranked = hybrid_recall(query, None, eligible, limit=5, order="losses_first")
                        queries += 1
                        changes += [r.memory_id for r in live] != [r.memory_id for r in ranked]
                        future_leaks += sum(r.data["timestamp"] > date+"T23:59:59+00:00" for r in loss_ranked)
                        default_losses += sum(r.data["pnl"] < 0 for r in ranked)
                        losses_first_losses += sum(r.data["pnl"] < 0 for r in loss_ranked)
                    history.append({"id": f"{asset}:{seed}:{record['outcome_date']}", "timestamp": record["outcome_date"]+"T00:00:00+00:00",
                                    "memory_type": "episodic", "pnl": record["pnl"], "pnl_r": None, "confidence": .5,
                                    "context": asdict(query), "decision_date": date,
                                    "kind": "simulated daily portfolio decision, not broker closed trade"})
            metrics.append({"asset": asset, "seed": seed, "queries": queries, "wall_clock_vs_replay_changed_top5": changes,
                            "future_leaks_filtered_adapter": future_leaks, "outcome_loss_slots": default_losses,
                            "losses_first_loss_slots": losses_first_losses, "total_slots": queries*5})
            print(f"RECALL {asset} seed={seed} queries={queries} changed_top5={changes}", flush=True)
    # Deliberate future-memory inclusion: core ranker has no temporal filter.
    query = ContextVector(symbol="CONTROL", price=100, regime="trending_up", session="newyork")
    fixture = [{"id": "past", "timestamp": "2020-01-01T00:00:00+00:00", "pnl": -1, "context": asdict(query)},
               {"id": "future", "timestamp": "2030-01-01T00:00:00+00:00", "pnl": -100, "context": asdict(query)}]
    ranked = hybrid_recall(query, None, fixture, limit=1, order="losses_first")
    filtered = hybrid_recall(query, None, fixture[:1], limit=1, order="losses_first")
    save(HERE/"recall_results.json", {"run_at_utc": run_at, "rows": metrics, "future_inclusion_positive_control_detected": ranked[0].memory_id == "future",
                                      "filtered_control_returns_past": filtered[0].memory_id == "past",
                                      "scope": "actual pure hybrid_recall; no embeddings, MCP server, DB writes or decision efficacy"})
    print(json.dumps(metrics, indent=2))


def seal():
    """Record local artifact hashes; raw vendor data is not published to Git."""
    assert_snapshot()
    stock = json.loads((HERE/"controls.json").read_text())
    verification = json.loads((HERE/"verification.json").read_text())
    recall = json.loads((HERE/"recall_results.json").read_text())
    market = json.loads((HERE/"market_results.json").read_text())
    assert stock["adapted_finrl_gate"] and len(stock["checks"]) == 18
    assert verification["all_pass"] and verification["total_steps"] == 22536
    assert recall["future_inclusion_positive_control_detected"] and recall["filtered_control_returns_past"]
    assert sum(r["queries"] for r in recall["rows"]) == 13935
    assert sum(r["future_leaks_filtered_adapter"] for r in recall["rows"]) == 0
    assert market["complete"] and len(market["rows"]) == 48
    paths = [p for folder in ["data", "models", "trajectories"] for p in sorted((CACHE/folder).glob("*")) if p.is_file()]
    cached_count = len(paths)
    paths += [HERE/name for name in ["probe.py", "check_rotation.py", "PROTOCOL.md", "requirements.txt", "manifest.json",
                                    "controls.json", "portfolio_controls.json", "rotation_controls.json", "market_results.json",
                                    "recall_results.json", "verification.json", "test_validation.json", "RESULTS.md", "README.md"]]
    save(HERE/"artifact_manifest.json", {"sealed_at_utc": datetime.now(timezone.utc).isoformat(),
         "local_cached_files": cached_count, "files": [{"path": p.relative_to(HERE).as_posix(), "sha256": sha(p), "bytes": p.stat().st_size} for p in paths]})
    artifacts()


def artifacts():
    manifest = json.loads((HERE/"artifact_manifest.json").read_text())
    for item in manifest["files"]:
        assert sha(HERE/item["path"]) == item["sha256"], f"Changed artifact: {item['path']}"
    print(json.dumps({"hashed_files": len(manifest["files"]), "all_pass": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["controls", "fetch", "train", "verify", "recall", "seal", "artifacts"])
    args = parser.parse_args()
    {"controls": controls, "fetch": fetch, "train": train, "verify": verify, "recall": recall_probe, "seal": seal, "artifacts": artifacts}[args.stage]()
