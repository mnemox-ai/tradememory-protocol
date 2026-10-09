"""Run upstream report helper in isolation; avoid strategy/data/API side effects.

Extract exactly one upstream AST function, unchanged. This tests the report
helper, not strategy generation, live broker execution or the paper's results.
"""
import ast
import contextlib
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from probe import HERE, CACHE, UPSTREAM, save, sha

source = UPSTREAM/"FinRL-Trading/src/strategies/run_adaptive_rotation_strategy.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_generate_performance_report")
module = ast.Module(body=[node], type_ignores=[])
ns = {"pd": pd, "np": np, "Path": Path}
exec(compile(module, str(source), "exec"), ns)
function = ns[node.name]
data_dir = CACHE/"rotation_control"
data_dir.mkdir(parents=True, exist_ok=True)
dates = pd.to_datetime(["2020-01-03", "2020-01-10", "2020-01-17"])
captured = {}


def trace(frame, event, arg):
    if event == "return" and frame.f_code is function.__code__:
        captured["portfolio"] = frame.f_locals["equity"]["portfolio"].tolist()
        captured["total_ret"] = float(frame.f_locals["total_ret"])
    return trace


checks = []
for label, prices, weights in [
    ("half_cash_preserved", [100., 110., 110.], [.5, .5, .5]),
    ("flat_roundtrip_cost_not_charged", [100., 100., 100.], [1., 0., 0.]),
]:
    pd.DataFrame({"date": dates, "close": prices}).to_csv(data_dir/"CONTROL_daily.csv", index=False)
    frame = pd.DataFrame({"date": dates, "cash": 1-np.array(weights), "regime": "control", "CONTROL": weights})
    output = io.StringIO()
    sys.settrace(trace)
    try:
        with contextlib.redirect_stdout(output):
            function(frame, "2020-01-03", "2020-01-17", str(data_dir), str(data_dir))
    finally:
        sys.settrace(None)
    (data_dir/f"{label}.txt").write_text(output.getvalue(), encoding="utf-8")
    expected = .05 if label == "half_cash_preserved" else 1/1.001*.999-1
    checks.append({"name": label, "actual_return": captured["total_ret"], "expected_net_return": expected,
                   "pass": abs(captured["total_ret"]-expected)<1e-8, "portfolio": captured["portfolio"]})
save(HERE/"rotation_controls.json", {"scope": "exact upstream _generate_performance_report only", "source_sha256": sha(source), "checks": checks})
print(json.dumps(checks, indent=2))
