"""
TradeMemory Services Launcher (silent, for Startup folder)
Starts: tradememory FastAPI server + mt5_sync.py + daily_reflection scheduler.
No console window (uses .pyw extension).
"""
import subprocess
import os
import sys
import time
import threading
import schedule
from pathlib import Path
from datetime import datetime

PROJECT = Path(r"C:\Users\johns\projects\tradememory-protocol")
PYTHON = r"C:\Users\johns\AppData\Local\Python312\python.exe"
LOGS = PROJECT / "logs"
LOGS.mkdir(exist_ok=True)


def log(msg):
    """Append to startup.log."""
    with open(LOGS / "startup.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {msg}\n")


def start_detached(cmd, log_name):
    """Start a process detached from this script."""
    log_file = open(LOGS / log_name, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=0x00000008 | 0x00000200,  # DETACHED + NEW_PROCESS_GROUP
    )
    return proc.pid


def run_reflection(mode="daily"):
    """Run daily_reflection.py."""
    args = [PYTHON, str(PROJECT / "daily_reflection.py")]
    if mode == "weekly":
        args.append("--weekly")
    elif mode == "monthly":
        args.append("--monthly")

    log_file = open(LOGS / "reflection.log", "a", encoding="utf-8")
    log_file.write(f"\n--- {mode} reflection @ {datetime.now()} ---\n")
    result = subprocess.run(
        args, cwd=str(PROJECT),
        stdout=log_file, stderr=subprocess.STDOUT, timeout=120
    )
    log(f"Reflection ({mode}) completed, exit code: {result.returncode}")


def reflection_scheduler():
    """Background thread: run daily reflection at 23:55, weekly on Sunday."""
    schedule.every().day.at("23:55").do(run_reflection, mode="daily")
    schedule.every().sunday.at("23:50").do(run_reflection, mode="weekly")

    log("Reflection scheduler started (daily 23:55, weekly Sun 23:50)")

    while True:
        schedule.run_pending()
        time.sleep(60)


# --- Main ---

# Start tradememory FastAPI server
server_pid = start_detached(
    [PYTHON, "-c",
     "import sys; sys.path.insert(0, 'src'); from tradememory.server import main; main()"],
    "server.log"
)
log(f"Server started, PID={server_pid}")

# Wait for server to be ready
time.sleep(5)

# Start mt5_sync.py
sync_pid = start_detached(
    [PYTHON, "-u", str(PROJECT / "mt5_sync.py")],
    "mt5_sync.log"
)
log(f"mt5_sync started, PID={sync_pid}")

# Start reflection scheduler in background thread
t = threading.Thread(target=reflection_scheduler, daemon=True)
t.start()

log(f"All services started: server={server_pid}, sync={sync_pid}, scheduler=thread")

# Keep this process alive (scheduler needs it)
try:
    while True:
        time.sleep(300)  # Wake every 5 min to keep process alive
except KeyboardInterrupt:
    log("Launcher stopped by user")
