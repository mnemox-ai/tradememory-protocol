"""scripts/mt5_sync.py has to start the way the docs say: python scripts/mt5_sync.py.

Launched like that, only scripts/ is on sys.path, and trade_advisor has lived in
scripts/research/ since the 2026-03-19 reorg. Each case imports the script in a
fresh interpreter: other test modules leave scripts/research/ on this process's
sys.path, so an in-process import would pass with the bug, and importing the
script configures logging and creates logs/ in the working directory.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
WEBHOOK = "https://discord.invalid/webhook"

# Imports mt5_sync with scripts/ first on sys.path, as the launch does (main_loop
# does not run), and records Discord posts instead of sending them.
PROBE = """
import importlib.util, inspect, json, sys
import requests

sys.path.insert(0, sys.argv[1])
preloaded = importlib.util.find_spec("trade_advisor") is not None
posts = []
requests.post = lambda url, **kwargs: posts.append(url)

import mt5_sync

mt5_sync.send_discord("trade summary")
mt5_sync.send_discord_alert("advisor warning")
print(json.dumps({
    "preloaded": preloaded,
    "advisor": inspect.getfile(mt5_sync.advise_on_open),
    "posts": posts,
}))
"""


@pytest.mark.parametrize("webhook_from", [None, "environment", "dotenv"])
def test_starts_from_scripts_dir_and_posts_only_with_webhook(tmp_path, webhook_from):
    env = {k: v for k, v in os.environ.items() if k != "DISCORD_WEBHOOK_URL"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if webhook_from == "environment":
        env["DISCORD_WEBHOOK_URL"] = WEBHOOK
    # Under python -c, python-dotenv looks for .env from the working directory up;
    # a file here, even an empty one, keeps it from reading anything above tmp_path.
    dotenv = f"DISCORD_WEBHOOK_URL={WEBHOOK}\n" if webhook_from == "dotenv" else ""
    (tmp_path / ".env").write_text(dotenv)

    result = subprocess.run(
        [sys.executable, "-c", PROBE, str(SCRIPTS_DIR)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    probe = json.loads(result.stdout.splitlines()[-1])
    assert not probe["preloaded"], "trade_advisor importable before mt5_sync set up sys.path"
    assert Path(probe["advisor"]) == SCRIPTS_DIR / "research" / "trade_advisor.py"
    assert probe["posts"] == ([WEBHOOK, WEBHOOK] if webhook_from else [])
