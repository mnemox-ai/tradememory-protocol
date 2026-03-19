#!/usr/bin/env python3
"""
generate_index.py — 讀取 Mnemox 各專案資料來源，生成 ~/.claude/INDEX.md
只用 stdlib，任何 source 失敗不 crash。
"""

import json
import os
import re
import sqlite3
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_PATH = Path.home() / ".claude" / "INDEX.md"

# ---------------------------------------------------------------------------
# Data Sources
# ---------------------------------------------------------------------------

DATA_SOURCES = {
    "tradememory_db": {
        "type": "sqlite",
        "path": Path.home() / "projects" / "tradememory-protocol" / "data" / "tradememory.db",
        "parser": "parse_tradememory_db",
    },
    "mt5_sync_db": {
        "type": "sqlite",
        "path": Path.home() / "projects" / "tradememory-protocol" / "scripts" / "mt5_sync_v3.db",
        "parser": "parse_mt5_sync_db",
    },
    "mt5_sync_state": {
        "type": "json",
        "path": Path.home() / "projects" / "tradememory-protocol" / "scripts" / "mt5_sync_state.json",
        "parser": "parse_mt5_sync_state",
    },
    "idea_reality_db": {
        "type": "sqlite",
        "path": Path.home() / "projects" / "idea-reality-mcp" / "score_history.db",
        "parser": "parse_idea_reality_db",
    },
    "ng_gold_memory": {
        "type": "file",
        "path": Path("C:/OpenClawWork/repos/NG_Gold/.claude/memory/MEMORY.md"),
        "parser": "parse_ng_gold_memory",
    },
    "active_todos": {
        "type": "file",
        "path": Path.home() / ".claude" / "projects" / "C--Users-johns-projects" / "memory" / "MEMORY.md",
        "parser": "parse_active_todos",
    },
    "tradememory_roadmap": {
        "type": "file",
        "path": Path.home() / "projects" / "tradememory-protocol" / "docs" / "ROADMAP.md",
        "parser": "parse_tradememory_roadmap",
    },
    "tradememory_health": {
        "type": "sqlite",
        "path": Path.home() / "projects" / "tradememory-protocol" / "data" / "tradememory.db",
        "parser": "parse_tradememory_health",
    },
    "mt5_sync_live": {
        "type": "http",
        "path": "http://localhost:9001/health",
        "parser": "parse_mt5_sync_live",
    },
}

# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _query(db_path: str, sql: str) -> list:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def parse_tradememory_db(src: dict) -> str:
    db = str(src["path"])
    lines = ["## TradeMemory DB", ""]

    # trade_records summary
    trades = _query(db, "SELECT COUNT(*) as cnt FROM trade_records")
    total = trades[0]["cnt"]
    pnl_rows = _query(db, "SELECT SUM(pnl) as total_pnl, AVG(pnl) as avg_pnl FROM trade_records WHERE pnl IS NOT NULL")
    total_pnl = pnl_rows[0]["total_pnl"] or 0
    avg_pnl = pnl_rows[0]["avg_pnl"] or 0

    lines.append(f"- **Trade Records**: {total} 筆 | Total PnL: ${total_pnl:+.2f} | Avg: ${avg_pnl:+.2f}")

    # recent 5 trades
    recent = _query(db, """
        SELECT symbol, direction, strategy, pnl, exit_timestamp
        FROM trade_records ORDER BY exit_timestamp DESC LIMIT 5
    """)
    if recent:
        lines.append("- **Recent Trades**:")
        for t in recent:
            ts = (t["exit_timestamp"] or "")[:10]
            pnl_str = f"${t['pnl']:+.2f}" if t["pnl"] is not None else "open"
            lines.append(f"  - {ts} {t['strategy']} {t['direction']} {t['symbol']} → {pnl_str}")

    # episodic / semantic / procedural counts
    for table in ["episodic_memory", "semantic_memory", "procedural_memory"]:
        cnt = _query(db, f"SELECT COUNT(*) as cnt FROM {table}")[0]["cnt"]
        lines.append(f"- **{table}**: {cnt} 筆")

    # affective state
    af = _query(db, "SELECT * FROM affective_state LIMIT 1")
    if af:
        a = af[0]
        dd = a.get("drawdown_state", 0) or 0
        lines.append(f"- **Affective State**: confidence={a.get('confidence_level', '?')}, "
                      f"drawdown={dd:.1%}, "
                      f"wins={a.get('consecutive_wins', 0)}/losses={a.get('consecutive_losses', 0)}")

    return "\n".join(lines)


def parse_mt5_sync_db(src: dict) -> str:
    db = str(src["path"])
    lines = ["## MT5 Sync V3", ""]

    # sync_state
    state = _query(db, "SELECT * FROM sync_state LIMIT 1")
    if state:
        s = state[0]
        lines.append(f"- **Last Ticket**: {s.get('last_ticket', '?')}")
        lines.append(f"- **Last Heartbeat**: {s.get('last_heartbeat', '?')}")
        lines.append(f"- **Consecutive Errors**: {s.get('consecutive_errors', 0)}")

    # open positions
    positions = _query(db, "SELECT * FROM open_positions")
    lines.append(f"- **Open Positions**: {len(positions)}")
    for p in positions:
        lines.append(f"  - {p.get('symbol')} {p.get('direction')} @ {p.get('entry_price')} "
                      f"({p.get('strategy')}, lot={p.get('lot_size')})")

    # recent sync_log
    logs = _query(db, "SELECT timestamp, event_type, message FROM sync_log ORDER BY timestamp DESC LIMIT 3")
    if logs:
        lines.append("- **Recent Sync Log**:")
        for l in logs:
            lines.append(f"  - [{l['timestamp']}] {l['event_type']}: {l['message']}")

    return "\n".join(lines)


def parse_mt5_sync_state(src: dict) -> str:
    with open(src["path"], "r", encoding="utf-8") as f:
        data = json.load(f)
    lines = ["## MT5 Sync State (JSON)", ""]
    lines.append(f"- **Last Synced Ticket**: {data.get('last_synced_ticket', '?')}")
    lines.append(f"- **Updated At**: {data.get('updated_at', '?')}")
    return "\n".join(lines)


def parse_idea_reality_db(src: dict) -> str:
    db = str(src["path"])
    lines = ["## Idea Reality MCP", ""]

    # counts
    for table, label in [
        ("query_log", "API Queries"),
        ("score_history", "Score History"),
        ("subscribers", "Subscribers"),
        ("page_views", "Page Views"),
    ]:
        cnt = _query(db, f"SELECT COUNT(*) as cnt FROM {table}")[0]["cnt"]
        lines.append(f"- **{label}**: {cnt}")

    # recent queries with scores
    recent = _query(db, """
        SELECT idea_text, score, depth, created_at
        FROM score_history ORDER BY created_at DESC LIMIT 5
    """)
    if recent:
        lines.append("- **Recent Checks**:")
        for r in recent:
            ts = (r["created_at"] or "")[:10]
            text = (r["idea_text"] or "")[:60]
            lines.append(f"  - [{ts}] score={r['score']} depth={r['depth']} — {text}")

    # country breakdown from query_log
    countries = _query(db, """
        SELECT country, COUNT(*) as cnt
        FROM query_log WHERE country IS NOT NULL AND country != ''
        GROUP BY country ORDER BY cnt DESC LIMIT 10
    """)
    if countries:
        parts = [f"{c['country']}({c['cnt']})" for c in countries]
        lines.append(f"- **Top Countries**: {', '.join(parts)}")

    return "\n".join(lines)


def parse_ng_gold_memory(src: dict) -> str:
    text = Path(src["path"]).read_text(encoding="utf-8")
    lines = ["## NG_Gold Status", ""]

    # Extract key sections
    for marker, label in [
        ("## 專案狀態", "專案狀態"),
        ("## 待辦", "待辦"),
    ]:
        if marker in text:
            start = text.index(marker)
            # find next ## or end
            rest = text[start + len(marker):]
            end_idx = rest.find("\n## ")
            section = rest[:end_idx].strip() if end_idx != -1 else rest.strip()
            # limit to 15 lines
            section_lines = section.split("\n")[:15]
            lines.append(f"### {label}")
            lines.extend(section_lines)
            lines.append("")

    return "\n".join(lines)


def _table_exists(db_path: str, table: str) -> bool:
    rows = _query(db_path, f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
    return len(rows) > 0


def _safe_count(db_path: str, table: str) -> str:
    """Return count string; shows '0 (表不存在)' if table missing."""
    if not _table_exists(db_path, table):
        return "0 (表不存在)"
    cnt = _query(db_path, f"SELECT COUNT(*) as cnt FROM {table}")[0]["cnt"]
    return str(cnt)


def parse_tradememory_health(src: dict) -> str:
    db = str(src["path"])
    lines = ["## TradeMemory 健康度", ""]

    # --- trade_records ---
    if _table_exists(db, "trade_records"):
        total = _query(db, "SELECT COUNT(*) as cnt FROM trade_records")[0]["cnt"]
        last_ts_row = _query(db, "SELECT MAX(timestamp) as ts FROM trade_records")
        last_ts = last_ts_row[0]["ts"] if last_ts_row and last_ts_row[0]["ts"] else "N/A"
        lines.append(f"| 指標 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 總交易數 | {total} |")
        lines.append(f"| 最後交易時間 | {last_ts} |")

        # per-strategy breakdown
        strats = _query(db, """
            SELECT strategy, COUNT(*) as cnt, AVG(pnl) as avg_pnl
            FROM trade_records
            GROUP BY strategy ORDER BY cnt DESC
        """)
        if strats:
            lines.append("")
            lines.append("| 策略 | 交易數 | 平均 PnL |")
            lines.append("|------|--------|----------|")
            for s in strats:
                avg = f"${s['avg_pnl']:+.2f}" if s["avg_pnl"] is not None else "N/A"
                lines.append(f"| {s['strategy'] or 'unknown'} | {s['cnt']} | {avg} |")
    else:
        lines.append("| 指標 | 值 |")
        lines.append("|------|-----|")
        lines.append("| 總交易數 | 0 (表不存在) |")

    # --- OWM / memory tables ---
    # Check owm_episodic first, fallback to episodic_memory
    episodic_table = "owm_episodic" if _table_exists(db, "owm_episodic") else "episodic_memory"
    semantic_table = "owm_semantic" if _table_exists(db, "owm_semantic") else "semantic_memory"

    lines.append("")
    lines.append("| 記憶層 | 筆數 |")
    lines.append("|--------|------|")
    lines.append(f"| Episodic ({episodic_table}) | {_safe_count(db, episodic_table)} |")
    lines.append(f"| Semantic ({semantic_table}) | {_safe_count(db, semantic_table)} |")
    lines.append(f"| Patterns | {_safe_count(db, 'patterns')} |")
    lines.append(f"| L3 策略調整 | {_safe_count(db, 'strategy_adjustments')} |")

    return "\n".join(lines)


def parse_mt5_sync_live(src: dict) -> str:
    lines = ["## MT5 Sync Live (HTTP)", ""]

    # --- /health ---
    try:
        req = urllib.request.Request("http://localhost:9001/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            health = json.loads(resp.read().decode())
        lines.append(f"- **Status**: {health.get('status', '?')}")
        lines.append(f"- **Last Sync**: {health.get('last_sync', '?')}")
        open_count = health.get("open_positions", "?")
        lines.append(f"- **Open Positions**: {open_count}")
        lines.append(f"- **Consecutive Errors**: {health.get('consecutive_errors', 0)}")
    except (urllib.error.URLError, OSError):
        lines.append("⚠️ MT5 Sync 未運行")
        return "\n".join(lines)

    # --- /open-positions ---
    try:
        req = urllib.request.Request("http://localhost:9001/open-positions")
        with urllib.request.urlopen(req, timeout=3) as resp:
            positions = json.loads(resp.read().decode())
        if positions:
            lines.append("")
            lines.append("| Ticket | Symbol | Direction | Entry Price | Strategy |")
            lines.append("|--------|--------|-----------|-------------|----------|")
            for p in positions:
                lines.append(
                    f"| {p.get('ticket', '?')} "
                    f"| {p.get('symbol', '?')} "
                    f"| {p.get('direction', '?')} "
                    f"| {p.get('entry_price', '?')} "
                    f"| {p.get('strategy', '?')} |"
                )
    except (urllib.error.URLError, OSError):
        lines.append("- ⚠️ 開倉列表讀取失敗")

    return "\n".join(lines)


def parse_active_todos(src: dict) -> str:
    text = Path(src["path"]).read_text(encoding="utf-8")
    lines = ["## 活躍待辦", ""]
    todos = [line.strip() for line in text.split("\n") if re.match(r"^\s*- \[ \]", line)]
    if todos:
        for t in todos:
            lines.append(t)
    else:
        lines.append("*無待辦項目*")
    return "\n".join(lines)


def parse_tradememory_roadmap(src: dict) -> str:
    text = Path(src["path"]).read_text(encoding="utf-8")
    lines = ["## TradeMemory Roadmap Progress", ""]

    done = text.count("✅")
    todo = text.count("❌")
    lines.append(f"- **Completed**: {done} tasks")
    lines.append(f"- **Remaining**: {todo} tasks")

    # extract next pending task (skip non-heading lines that mention ❌)
    for line in text.split("\n"):
        stripped = line.strip()
        if "❌" in stripped and stripped.startswith(("#", "- [")):
            lines.append(f"- **Next**: {stripped}")
            break

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Git Status
# ---------------------------------------------------------------------------

GIT_PROJECTS = [
    {
        "name": "tradememory-protocol",
        "path": Path.home() / "projects" / "tradememory-protocol",
        "version_source": "pyproject",
    },
    {
        "name": "idea-reality-mcp",
        "path": Path.home() / "projects" / "idea-reality-mcp",
        "version_source": "pyproject",
    },
    {
        "name": "NG_Gold",
        "path": Path("C:/OpenClawWork/repos/NG_Gold"),
        "version_source": "fixed",
    },
]


def _get_version(project: dict) -> str:
    if project["version_source"] == "fixed":
        return "N/A"
    toml_path = project["path"] / "pyproject.toml"
    if not toml_path.exists():
        return "?"
    text = toml_path.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else "?"


def _run_git(args: list, cwd: Path) -> str:
    """Run a git command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, cwd=str(cwd), timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def generate_git_status() -> str:
    lines = ["## 專案 Git 狀態", ""]
    lines.append("| 專案 | 版本 | 最後 Commit | 狀態 |")
    lines.append("|------|------|-------------|------|")

    for proj in GIT_PROJECTS:
        name = proj["name"]
        path = proj["path"]

        if not path.exists():
            lines.append(f"| {name} | ? | ⚠️ 目錄不存在 | ? |")
            continue

        version = _get_version(proj)

        # Last commit
        log_out = _run_git(["log", "--oneline", "-1"], path)
        if log_out:
            # format: "abc1234 commit message here"
            parts = log_out.split(" ", 1)
            commit_hash = parts[0]
            commit_msg = parts[1][:50] if len(parts) > 1 else ""
            last_commit = f"`{commit_hash}` {commit_msg}"
        else:
            last_commit = "?"

        # Dirty check
        status_out = _run_git(["status", "--porcelain"], path)
        dirty = "⚠️ dirty" if status_out else "✅ clean"

        lines.append(f"| {name} | {version} | {last_commit} | {dirty} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [f"# Mnemox Status — Auto-generated {now}", ""]

    for name, src in DATA_SOURCES.items():
        parser_name = src["parser"]
        parser_fn = globals().get(parser_name)
        if parser_fn is None:
            parts.append(f"## {name}\n\n⚠️ Parser `{parser_name}` not found\n")
            continue

        try:
            if src["type"] != "http" and not os.path.exists(src["path"]):
                parts.append(f"## {name}\n\n⚠️ 讀取失敗：file not found ({src['path']})\n")
                continue
            result = parser_fn(src)
            parts.append(result)
            parts.append("")
        except Exception as e:
            parts.append(f"## {name}\n\n⚠️ 讀取失敗：{type(e).__name__}: {e}\n")

    # Git status for all projects
    try:
        parts.append(generate_git_status())
        parts.append("")
    except Exception as e:
        parts.append(f"## 專案 Git 狀態\n\n⚠️ 讀取失敗：{type(e).__name__}: {e}\n")

    parts.append("---")
    parts.append(f"*`generate_index.py` 自動生成，不要手動編輯*")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(parts), encoding="utf-8")
    print(f"INDEX.md written to {OUTPUT_PATH} ({len(parts)} sections)")


if __name__ == "__main__":
    main()
