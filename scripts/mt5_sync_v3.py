"""
MT5 Sync v3 — FastAPI + background MT5 poller

Architecture:
  - FastAPI on port 9001 (GET /health, /open-positions, /recent-trades)
  - MT5Poller runs in daemon thread, polls every SYNC_INTERVAL (default 60s)
  - SQLite for state: open_positions, sync_state, sync_log
  - Closed trades → TradeMemory API (record_decision + record_outcome)

啟動: python scripts/mt5_sync_v3.py
  or: uvicorn scripts.mt5_sync_v3:app --port 9001
"""

import csv
import json
import os
import re
import sys
import time
import logging
import sqlite3
import threading
import requests
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# Add scripts/research/ to path for trade_advisor (moved during 2026-03-19 repo reorg)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "research"))
from trade_advisor import advise_on_open, send_discord_alert, recall_similar, get_behavioral

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/mt5_sync_v3.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("mt5_sync_v3")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Config (.env)
# ---------------------------------------------------------------------------

load_dotenv()

MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")
MT5_PATH = os.getenv("MT5_PATH", "")
TRADEMEMORY_API = os.getenv("TRADEMEMORY_API", "http://localhost:8000")
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "60"))
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

MAGIC_TO_STRATEGY = {
    0: "Manual",
    260111: "NG_Gold",             # Mode 0: Impulse-Retrace-Continuation
    260112: "VolBreakout",         # Mode 2
    260113: "MeanReversion",       # Mode 3 (DISABLED)
    260115: "LondonMomentum",      # Mode 5 (DISABLED)
    260118: "IntradayMomentum",    # Mode 8
    20260217: "Pullback",          # Separate EA
}

MT5_API_TIMEOUT = 30
MAX_CONSECUTIVE_ERRORS = 10
LONG_WAIT_SECONDS = 300

# Event log directory (EA writes to Common/Files/NG_Gold/)
EVENT_LOG_DIR = Path(os.getenv(
    "EVENT_LOG_DIR",
    r"C:\Users\johns\AppData\Roaming\MetaQuotes\Terminal\Common\Files\NG_Gold",
))


# ---------------------------------------------------------------------------
# EventLogReader — extract entry context from EA event_log CSVs
# ---------------------------------------------------------------------------

class EventLogReader:
    """Reads NG_Gold event_log CSVs to extract trade entry context.

    Matching: position_id from MT5 deal == pos_id in TRADE_OPEN event.
    Falls back to timestamp proximity if pos_id not found.
    """

    def __init__(self, event_log_dir: Path = EVENT_LOG_DIR):
        self.dir = event_log_dir

    def find_entry_context(
        self, symbol: str, magic: int, position_id: int, entry_time: int
    ) -> dict:
        """Look up entry context from event_log CSV.

        Args:
            symbol: e.g. "XAUUSD"
            magic: EA magic number (260112, 260118, etc.)
            position_id: MT5 position_id (matches pos_id in event_log)
            entry_time: Unix timestamp of entry deal

        Returns:
            dict with keys: reasoning, confidence, market_data, matched
        """
        if not self.dir.exists():
            return self._fallback(magic, "event_log_dir not found")

        # Find CSVs matching symbol and magic from filename pattern
        # Pattern: event_log_*_{symbol}_PERIOD_M5_M{magic}_*.csv
        pattern = f"event_log_*_{symbol}_PERIOD_M5_M{magic}_*.csv"
        csv_files = sorted(self.dir.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)

        if not csv_files:
            return self._fallback(magic, f"no event_log for {symbol}/M{magic}")

        # Search for TRADE_OPEN with matching pos_id (most recent files first)
        pos_id_str = str(position_id)
        for csv_path in csv_files[:20]:  # limit to 20 most recent files
            match = self._search_csv_for_position(csv_path, pos_id_str, entry_time)
            if match:
                return match

        # Fallback: no match found
        return self._fallback(magic, f"pos_id={position_id} not found in event_logs")

    def _search_csv_for_position(
        self, csv_path: Path, pos_id_str: str, entry_time: int
    ) -> Optional[dict]:
        """Search a single CSV for TRADE_OPEN with matching pos_id."""
        try:
            with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                trade_open_row = None
                decision_row = None

                for row in reader:
                    evt = (row.get("evt") or "").strip()
                    reason = (row.get("reason") or "").strip()

                    # Match TRADE_OPEN by pos_id
                    if evt == "TRADE_OPEN" and f"pos_id={pos_id_str}" in reason:
                        trade_open_row = row

                    # Collect DECISION events near the entry time
                    if evt == "DECISION" and row.get("score_total"):
                        ts_str = (row.get("ts") or "").strip()
                        row_time = self._parse_ts(ts_str)
                        if row_time and abs(row_time - entry_time) < 600:  # within 10 min
                            decision_row = row

                if trade_open_row:
                    return self._build_context(trade_open_row, decision_row)

        except Exception as e:
            log.warning(f"EventLogReader: error reading {csv_path.name}: {e}")
        return None

    def _build_context(self, trade_open: dict, decision: Optional[dict]) -> dict:
        """Build rich context from event_log rows."""
        direction = (trade_open.get("decision") or "").strip()
        atr_m5 = self._safe_float(trade_open.get("atr_m5"))
        spread_pts = self._safe_int(trade_open.get("spread_points"))
        bid = self._safe_float(trade_open.get("bid"))
        ask = self._safe_float(trade_open.get("ask"))
        ema_fast_h1 = self._safe_float(trade_open.get("ema_fast_h1"))
        ema_slow_h1 = self._safe_float(trade_open.get("ema_slow_h1"))
        ema_fast_m30 = self._safe_float(trade_open.get("ema_fast_m30"))
        ema_slow_m30 = self._safe_float(trade_open.get("ema_slow_m30"))

        # Build reasoning string
        parts = [f"{direction} entry"]

        if decision:
            # Rich context from DECISION event
            score_bd = (decision.get("score_breakdown") or "").strip()
            dec_reason = (decision.get("reason") or "").strip()
            if score_bd:
                parts.append(f"Score: {score_bd}")
            if dec_reason:
                parts.append(f"Signal: {dec_reason}")
        else:
            # Context from TRADE_OPEN market data
            if atr_m5 and atr_m5 > 0:
                parts.append(f"ATR(M5)={atr_m5:.2f}")
            if spread_pts is not None:
                parts.append(f"Spread={spread_pts}pts")
            if ema_fast_h1 and ema_slow_h1:
                trend = "bullish" if ema_fast_h1 > ema_slow_h1 else "bearish"
                parts.append(f"H1 EMA {trend} (fast={ema_fast_h1:.1f} slow={ema_slow_h1:.1f})")

        reasoning = ". ".join(parts)

        # Dynamic confidence
        if decision:
            score_total = self._safe_float(decision.get("score_total"))
            confidence = min(score_total / 100.0, 1.0) if score_total and score_total > 0 else 0.6
        else:
            # Derive from market data quality: confirmed EA entry = 0.6 base
            confidence = 0.6
            if spread_pts is not None and atr_m5 and atr_m5 > 0:
                # Higher confidence if spread is low relative to ATR
                spread_price = self._safe_float(trade_open.get("spread_price")) or 0
                if atr_m5 > 0 and spread_price > 0:
                    spread_ratio = spread_price / atr_m5
                    if spread_ratio < 0.05:
                        confidence = 0.7
                    elif spread_ratio > 0.15:
                        confidence = 0.5

        return {
            "reasoning": reasoning,
            "confidence": round(confidence, 2),
            "market_data": {
                "atr_m5": atr_m5,
                "spread_points": spread_pts,
                "bid": bid,
                "ask": ask,
                "ema_fast_h1": ema_fast_h1,
                "ema_slow_h1": ema_slow_h1,
                "ema_fast_m30": ema_fast_m30,
                "ema_slow_m30": ema_slow_m30,
            },
            "matched": True,
        }

    def _fallback(self, magic: int, reason: str) -> dict:
        log.debug(f"EventLogReader fallback: {reason}")
        return {
            "reasoning": f"Auto-synced from MT5 (magic={magic})",
            "confidence": 0.5,
            "market_data": {},
            "matched": False,
        }

    @staticmethod
    def _parse_ts(ts_str: str) -> Optional[int]:
        """Parse event_log timestamp '2026.03.24 07:55:05' to unix timestamp."""
        try:
            dt = datetime.strptime(ts_str, "%Y.%m.%d %H:%M:%S")
            return int(dt.replace(tzinfo=timezone.utc).timestamp())
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        try:
            v = float(val)
            return v if v != 0.0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(val) -> Optional[int]:
        try:
            return int(val)
        except (TypeError, ValueError):
            return None


# Global reader instance
event_log_reader = EventLogReader()


# ---------------------------------------------------------------------------
# DecisionLogReader — extract rich context from EA decision_log JSONL files
# ---------------------------------------------------------------------------

class DecisionLogReader:
    """Reads NG_Gold decision_log JSONL files for rich trade decision context.

    JSONL files written by NG_DecisionLogger.mqh contain full decision context:
    conditions, filters, indicators, execution details, regime, risk state.

    Priority: JSONL > event_log CSV (JSONL has structured JSON fields that CSV lacks).
    """

    def __init__(self, decision_log_dir: Path = EVENT_LOG_DIR):
        self.dir = decision_log_dir

    def find_decision_for_trade(
        self, strategy: str, entry_time: int, exec_ticket: int = 0
    ) -> Optional[dict]:
        """Find the EXECUTED decision event matching a trade.

        Args:
            strategy: Strategy name (e.g. "VolBreakout")
            entry_time: Unix timestamp of entry deal
            exec_ticket: MT5 position ticket (matches exec_ticket in JSONL)

        Returns:
            dict with keys: reasoning, confidence, market_data, decision_raw, matched
            or None if no JSONL files or no match found.
        """
        if not self.dir.exists():
            return None

        # Strategy names in JSONL match TradeMemory strategy names directly
        # EA writes: "VolBreakout", "IntradayMomentum", "Pullback"
        known_strategies = {"VolBreakout", "IntradayMomentum", "Pullback"}
        if strategy not in known_strategies:
            return None
        ea_strategy = strategy

        # Find JSONL files sorted by recency
        jsonl_files = sorted(
            self.dir.glob("decision_log_*.jsonl"),
            key=lambda f: f.name,
            reverse=True,
        )
        if not jsonl_files:
            return None

        # Search recent files for EXECUTED event matching ticket or timestamp
        for jsonl_path in jsonl_files[:7]:  # last 7 days
            match = self._search_jsonl(jsonl_path, ea_strategy, entry_time, exec_ticket)
            if match:
                return match

        return None

    def _search_jsonl(
        self, path: Path, ea_strategy: str, entry_time: int, exec_ticket: int
    ) -> Optional[dict]:
        """Search a single JSONL file for matching EXECUTED decision."""
        best_match = None
        best_time_diff = float("inf")

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    # Handle concurrent write corruption: split merged JSON objects
                    # e.g. '{"ts":"..."}{"ts":"..."}' → two separate objects
                    segments = line.replace("}{", "}\n{").split("\n") if "}{" in line else [line]
                    for segment in segments:
                        segment = segment.strip()
                        if not segment:
                            continue
                        try:
                            evt = json.loads(segment)
                        except json.JSONDecodeError:
                            continue

                        # Only match EXECUTED or SIGNAL_* events
                        decision = evt.get("decision", "")
                        if decision not in ("EXECUTED", "SIGNAL_LONG", "SIGNAL_SHORT"):
                            continue

                        if evt.get("strategy") != ea_strategy:
                            continue

                        # Match by exec_ticket (strongest match)
                        if exec_ticket and evt.get("exec_ticket") == exec_ticket:
                            return self._build_rich_context(evt)

                        # Match by timestamp proximity (within 5 min)
                        evt_time = self._parse_ts(evt.get("ts", ""))
                        if evt_time:
                            diff = abs(evt_time - entry_time)
                            if diff < 300 and diff < best_time_diff:
                                best_time_diff = diff
                                best_match = evt

        except Exception as e:
            log.warning(f"DecisionLogReader: error reading {path.name}: {e}")

        if best_match:
            return self._build_rich_context(best_match)
        return None

    def _build_rich_context(self, evt: dict) -> dict:
        """Build rich reasoning from JSONL decision event."""
        parts = []

        # Direction
        direction = evt.get("signal_direction", "NONE")
        decision = evt.get("decision", "")
        parts.append(f"{direction} {decision}")

        # Strategy + timeframe
        parts.append(f"Strategy: {evt.get('strategy')}/{evt.get('timeframe')}")

        # Signal strength
        strength = evt.get("signal_strength")
        if strength is not None:
            parts.append(f"Signal strength: {strength:.4f}")

        # Conditions (the WHY)
        conditions = evt.get("conditions_json")
        if conditions and isinstance(conditions, dict):
            cond_list = conditions.get("conditions", [])
            if cond_list:
                parts.append(f"Conditions: {', '.join(str(c) for c in cond_list)}")

        # Filters
        filters = evt.get("filters_json")
        if filters and isinstance(filters, dict):
            filter_list = filters.get("filters", [])
            if filter_list:
                parts.append(f"Filters passed: {', '.join(str(f) for f in filter_list)}")

        # Indicators snapshot
        indicators = evt.get("indicators_json")
        if indicators and isinstance(indicators, dict):
            ind_parts = [f"{k}={v}" for k, v in indicators.items() if v is not None]
            if ind_parts:
                parts.append(f"Indicators: {', '.join(ind_parts)}")

        # Execution details
        if evt.get("exec_ticket"):
            exec_parts = []
            exec_parts.append(f"price={evt.get('exec_price')}")
            if evt.get("exec_slippage") is not None:
                exec_parts.append(f"slippage={evt.get('exec_slippage')}pts")
            if evt.get("exec_latency_ms") is not None:
                exec_parts.append(f"latency={evt.get('exec_latency_ms')}ms")
            parts.append(f"Execution: {', '.join(exec_parts)}")

        # Regime
        regime = evt.get("regime")
        if regime:
            ratio = evt.get("regime_ratio", 0)
            parts.append(f"Regime: {regime} (ratio={ratio:.3f})")

        # Risk state
        risk_parts = []
        if evt.get("consec_losses", 0) > 0:
            risk_parts.append(f"consec_losses={evt['consec_losses']}")
        if evt.get("cooldown_active"):
            risk_parts.append("COOLDOWN")
        if evt.get("risk_daily_pct", 0) != 0:
            risk_parts.append(f"daily_risk={evt['risk_daily_pct']:.3f}%")
        if risk_parts:
            parts.append(f"Risk: {', '.join(risk_parts)}")

        # Confidence from signal_strength (0-1 scale)
        confidence = 0.7  # base for EXECUTED
        if strength is not None and strength > 0:
            confidence = min(strength, 1.0)

        # Market data for context enrichment
        market_data = {
            "bar_close": evt.get("bar_close"),
            "spread_points": evt.get("spread_points"),
            "account_balance": evt.get("account_balance"),
            "account_equity": evt.get("account_equity"),
            "open_positions": evt.get("open_positions"),
            "daily_pnl": evt.get("daily_pnl"),
        }
        if indicators and isinstance(indicators, dict):
            market_data["indicators"] = indicators

        return {
            "reasoning": ". ".join(parts),
            "confidence": round(confidence, 2),
            "market_data": market_data,
            "decision_raw": evt,  # full JSONL event for audit
            "matched": True,
        }

    @staticmethod
    def _parse_ts(ts_str: str) -> Optional[int]:
        """Parse JSONL timestamp '2026-03-26 20:39:13' to unix timestamp."""
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S"):
            try:
                dt = datetime.strptime(ts_str, fmt)
                return int(dt.replace(tzinfo=timezone.utc).timestamp())
            except (ValueError, AttributeError):
                continue
        return None


# Global decision log reader instance
decision_log_reader = DecisionLogReader()


# ---------------------------------------------------------------------------
# RegimeReader — read NG_Regime.dat binary file (Task 0.6)
# ---------------------------------------------------------------------------

import struct

MT5_TERMINAL_ID = "5B52BD5C4A58F66C26AE407260A02BE6"
MT5_FILES_DIR = Path(os.getenv(
    "MT5_FILES_DIR",
    rf"C:\Users\johns\AppData\Roaming\MetaQuotes\Terminal\{MT5_TERMINAL_ID}\MQL5\Files",
))

REGIME_LABELS = {0: "UNKNOWN", 1: "TRENDING", 2: "RANGING", 3: "TRANSITIONING"}
REGIME_FMT = "<i3diqi"
REGIME_SIZE = struct.calcsize(REGIME_FMT)  # 44 bytes


def read_regime() -> Optional[dict]:
    """Read current regime from NG_Regime.dat binary file."""
    path = MT5_FILES_DIR / "NG_Regime.dat"
    if not path.exists():
        return None
    try:
        data = path.read_bytes()
        if len(data) < REGIME_SIZE:
            return None
        vals = struct.unpack(REGIME_FMT, data[:REGIME_SIZE])
        magic, atr_h1, atr_d1, ratio, label, last_update, count = vals
        if magic != 0x5247:
            return None
        return {
            "regime": REGIME_LABELS.get(label, f"UNKNOWN({label})"),
            "atr_h1": round(atr_h1, 2),
            "atr_d1": round(atr_d1, 2),
            "atr_ratio": round(ratio, 4),
        }
    except Exception as e:
        log.debug(f"read_regime error: {e}")
        return None

# ---------------------------------------------------------------------------
# pnl_r helpers — extract SL for real R-multiple calculation (Task 0.3 revised)
# ---------------------------------------------------------------------------

# Regex to parse [sl XXXX.XX] or [tp XXXX.XX] from deal/order comment
_SL_COMMENT_RE = re.compile(r'\[sl\s+([\d.]+)\]', re.IGNORECASE)
_TP_COMMENT_RE = re.compile(r'\[tp\s+([\d.]+)\]', re.IGNORECASE)

# Contract sizes for common symbols (fallback if MT5 not available)
_CONTRACT_SIZES = {
    "XAUUSD": 100,   # 100 oz per lot
    "XAGUSD": 5000,  # 5000 oz per lot
    "EURUSD": 100000, # standard forex
    "GBPUSD": 100000,
}


def _extract_sl_from_comment(comment: str) -> Optional[float]:
    """Extract SL price from deal comment like '[sl 4385.04]'."""
    if not comment:
        return None
    m = _SL_COMMENT_RE.search(comment)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _get_sl_from_orders(position_id: int) -> Optional[float]:
    """Try to get SL from MT5 history_orders for this position."""
    try:
        import MetaTrader5 as MT5
        from_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
        to_date = datetime.now(timezone.utc)
        orders = MT5.history_orders_get(from_date, to_date)
        if not orders:
            return None
        for order in orders:
            if order.position_id == position_id and order.sl > 0:
                return order.sl
        # Also check close order comment for [sl XXXX]
        for order in orders:
            if order.position_id == position_id:
                sl = _extract_sl_from_comment(getattr(order, 'comment', '') or '')
                if sl:
                    return sl
    except Exception as e:
        log.debug(f"_get_sl_from_orders error: {e}")
    return None


def _get_contract_size(symbol: str) -> float:
    """Get contract size from MT5 symbol info, fallback to hardcoded."""
    try:
        import MetaTrader5 as MT5
        info = MT5.symbol_info(symbol)
        if info and info.trade_contract_size > 0:
            return info.trade_contract_size
    except Exception:
        pass
    return _CONTRACT_SIZES.get(symbol, 100000)


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mt5_sync_v3.db")


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS open_positions (
                ticket      INTEGER PRIMARY KEY,
                symbol      TEXT NOT NULL,
                direction   TEXT NOT NULL,
                entry_price REAL NOT NULL,
                entry_time  TEXT NOT NULL,
                strategy    TEXT NOT NULL,
                magic       INTEGER NOT NULL,
                lot_size    REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                id                  INTEGER PRIMARY KEY CHECK (id = 1),
                last_ticket         INTEGER NOT NULL DEFAULT 0,
                last_heartbeat      TEXT NOT NULL,
                consecutive_errors  INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                message     TEXT NOT NULL
            );

            INSERT OR IGNORE INTO sync_state (id, last_ticket, last_heartbeat, consecutive_errors)
            VALUES (1, 0, '', 0);
        """)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(conn: sqlite3.Connection, event_type: str, message: str):
    conn.execute(
        "INSERT INTO sync_log (timestamp, event_type, message) VALUES (?, ?, ?)",
        (_now_iso(), event_type, message),
    )


# ---------------------------------------------------------------------------
# Discord helper
# ---------------------------------------------------------------------------

def send_discord(message: str, color: int = 0x00FF00):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        payload = {
            "embeds": [{
                "title": "TradeMemory — MT5 Sync v3",
                "description": message,
                "color": color,
                "timestamp": _now_iso(),
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# MT5Poller — background thread that polls MT5 every SYNC_INTERVAL
# ---------------------------------------------------------------------------

class MT5Poller:
    """Polls MT5 terminal in a daemon thread. Writes results to SQLite."""

    def __init__(self):
        self._mt5_alive = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._was_disconnected = False  # throttle disconnect Discord notifications

    @property
    def mt5_alive(self) -> bool:
        return self._mt5_alive

    # --- MT5 connection (from mt5_sync.py) ---

    def _mt5_api_call_with_timeout(self, func, timeout_seconds: int = MT5_API_TIMEOUT):
        """Execute MT5 API call with threading-based timeout. Returns (result, timed_out)."""
        result_container = {"value": None, "error": None}

        def worker():
            try:
                result_container["value"] = func()
            except Exception as e:
                result_container["error"] = e

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout=timeout_seconds)

        if t.is_alive():
            log.error(f"MT5 API call timed out after {timeout_seconds}s")
            return None, True

        if result_container["error"]:
            raise result_container["error"]

        return result_container["value"], False

    def init_mt5(self) -> bool:
        """Initialize MT5 connection.
        
        Strategy: first try parameterless init (attaches to running terminal),
        then fall back to full credentials (launches new terminal).
        """
        try:
            import MetaTrader5 as MT5

            # Attempt 1: attach to already-running terminal (no credentials)
            if MT5.initialize():
                info = MT5.account_info()
                if info:
                    log.info(f"Connected (attach): {info.name} ({info.server}), Balance: ${info.balance:.2f}")
                    self._mt5_alive = True
                    return True

            # Attempt 2: full credentials (launches terminal if needed)
            log.info("Parameterless init failed, trying with credentials...")
            init_kwargs = dict(
                login=MT5_LOGIN,
                password=MT5_PASSWORD,
                server=MT5_SERVER,
                timeout=30000,
            )
            if MT5_PATH:
                init_kwargs["path"] = MT5_PATH

            if not MT5.initialize(**init_kwargs):
                log.error(f"MT5 initialize() failed: {MT5.last_error()}")
                self._mt5_alive = False
                return False

            info = MT5.account_info()
            log.info(f"Connected (credentials): {info.name} ({info.server}), Balance: ${info.balance:.2f}")
            self._mt5_alive = True
            return True

        except ImportError:
            log.error("MetaTrader5 package not installed. pip install MetaTrader5")
            return False
        except Exception as e:
            log.error(f"MT5 init failed: {e}")
            self._mt5_alive = False
            return False

    def is_mt5_alive(self) -> bool:
        """Quick health check with 10s timeout."""
        try:
            import MetaTrader5 as MT5
            result, timed_out = self._mt5_api_call_with_timeout(
                lambda: MT5.account_info(), timeout_seconds=10
            )
            if timed_out:
                log.warning("MT5 health check timed out")
                self._mt5_alive = False
                return False
            alive = result is not None
            self._mt5_alive = alive
            return alive
        except Exception:
            self._mt5_alive = False
            return False

    def _reconnect(self):
        """Shutdown + re-init MT5."""
        try:
            import MetaTrader5 as MT5
            MT5.shutdown()
        except Exception:
            pass
        return self.init_mt5()

    # --- Open positions → SQLite ---

    def _sync_open_positions(self):
        """
        Fetch positions_get(), upsert into open_positions table.
        Detect new opens → sync_log + trade advisor.
        Detect closes → remove from table + sync to TradeMemory.
        """
        import MetaTrader5 as MT5

        positions, timed_out = self._mt5_api_call_with_timeout(
            MT5.positions_get, timeout_seconds=10
        )
        if timed_out or positions is None:
            positions = ()  # treat as empty on timeout (don't wipe DB)

        mt5_tickets = {p.ticket for p in positions}

        with get_db() as conn:
            # Current DB tickets
            db_rows = conn.execute("SELECT ticket FROM open_positions").fetchall()
            db_tickets = {r["ticket"] for r in db_rows}

            # --- New opens ---
            new_tickets = mt5_tickets - db_tickets
            for pos in positions:
                if pos.ticket not in new_tickets:
                    continue

                strategy = MAGIC_TO_STRATEGY.get(pos.magic, f"Unknown_{pos.magic}")
                direction = "long" if pos.type == 0 else "short"
                entry_time = datetime.fromtimestamp(pos.time, tz=timezone.utc).isoformat()

                conn.execute(
                    "INSERT OR REPLACE INTO open_positions "
                    "(ticket, symbol, direction, entry_price, entry_time, strategy, magic, lot_size) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (pos.ticket, pos.symbol, direction, pos.price_open,
                     entry_time, strategy, pos.magic, pos.volume),
                )

                _log_event(conn, "POSITION_OPEN",
                           f"{strategy} {pos.symbol} {direction} {pos.volume} lots @ {pos.price_open:.2f}")

                log.info(f"[OPEN] {strategy} {pos.symbol} {direction} @ {pos.price_open:.2f}")

                # Trade advisor (non-blocking)
                self._run_trade_advisor(pos, strategy, direction)

            # --- Closed (in DB but not in MT5 anymore) ---
            closed_tickets = db_tickets - mt5_tickets
            for ticket in closed_tickets:
                row = conn.execute(
                    "SELECT * FROM open_positions WHERE ticket = ?", (ticket,)
                ).fetchone()

                if row:
                    _log_event(conn, "POSITION_CLOSED",
                               f"ticket={ticket} {row['strategy']} {row['symbol']} {row['direction']}")
                    log.info(f"[CLOSED] ticket={ticket} {row['strategy']} {row['symbol']}")

                # NOTE: Do NOT delete here — only after successful sync to TradeMemory

            closed_data = list(closed_tickets)

        # Sync closed trades to TradeMemory (after DB commit)
        if closed_data:
            synced_tickets = self._sync_closed_trades_to_memory(closed_data)
            # Only delete successfully synced tickets from open_positions
            if synced_tickets:
                with get_db() as conn:
                    for ticket in synced_tickets:
                        conn.execute("DELETE FROM open_positions WHERE ticket = ?", (ticket,))
                    log.info(f"Cleaned up {len(synced_tickets)} synced positions from open_positions")

    def _run_trade_advisor(self, pos, strategy: str, direction: str):
        """Send new-open Discord embed + run trade advisor warnings."""
        try:
            hour = datetime.now(timezone.utc).hour
            if 0 <= hour < 8:
                session = "asian"
            elif 8 <= hour < 16:
                session = "london"
            else:
                session = "newyork"

            # --- Fetch recall + behavioral for Discord embed ---
            recall_text = "No similar trades found"
            behavioral_text = "N/A"

            try:
                memories = recall_similar(pos.symbol, strategy, session)
                relevant = [m for m in memories if m.get("score", 0) >= 0.2]
                if relevant:
                    pnls = [m.get("pnl", 0) for m in relevant if m.get("pnl") is not None]
                    if pnls:
                        avg_pnl = sum(pnls) / len(pnls)
                        win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
                        recall_text = f"{len(pnls)} similar: avg ${avg_pnl:+.0f}, WR {win_rate:.0%}"
            except Exception as e:
                log.warning(f"[ADVISOR] recall_similar failed: {e}")

            try:
                behavioral = get_behavioral()
                if behavioral:
                    disp = behavioral.get("disposition_ratio")
                    if disp is not None:
                        behavioral_text = f"Disposition ratio: {disp:.2f}"
                    else:
                        behavioral_text = "No patterns detected"
            except Exception as e:
                log.warning(f"[ADVISOR] get_behavioral failed: {e}")

            # --- (1) New open Discord embed (always send) ---
            send_discord(
                f"\U0001f4ca **New Position**\n"
                f"**{strategy}** {pos.symbol} {direction.upper()}\n"
                f"Entry: {pos.price_open:.2f} | Lots: {pos.volume}\n"
                f"Session: {session.capitalize()}\n"
                f"\u2500\u2500\u2500\n"
                f"\U0001f9e0 **Recall:** {recall_text}\n"
                f"\U0001f4a1 **Behavioral:** {behavioral_text}",
                color=0x2ECC71 if direction == "long" else 0xE74C3C,
            )

            # --- Trade advisor warning check ---
            warning = advise_on_open(
                symbol=pos.symbol,
                direction=direction,
                strategy=strategy,
                entry_price=pos.price_open,
                lot_size=pos.volume,
                session=session,
                ticket=pos.ticket,
            )

            if warning:
                log.info(f"[ADVISOR] Warning for ticket {pos.ticket}")
                send_discord_alert(warning)
            else:
                log.info(f"[ADVISOR] All clear for ticket {pos.ticket}")

        except Exception as e:
            log.error(f"[ADVISOR] Error for ticket {pos.ticket}: {e}")

    # --- pnl_r helpers (Task 0.3 revised) ---

    @staticmethod
    def _extract_sl_comment(comment: str) -> Optional[float]:
        """Extract SL price from deal comment like '[sl 4385.04]'."""
        return _extract_sl_from_comment(comment)

    # --- Closed trade sync (history-based, same as v2) ---

    def _sync_closed_trades_to_memory(self, closed_tickets: list[int]) -> list[int]:
        """
        For each closed ticket, look up in MT5 history_deals_get
        and POST to TradeMemory record_decision + record_outcome.
        Returns list of successfully synced ticket numbers.
        """
        import MetaTrader5 as MT5

        synced: list[int] = []

        from_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
        to_date = datetime.now(timezone.utc)

        history, timed_out = self._mt5_api_call_with_timeout(
            lambda: MT5.history_deals_get(from_date, to_date)
        )
        if timed_out or history is None:
            log.error("Cannot fetch deal history for closed trade sync")
            return synced

        # Group deals by position_id
        deal_map: dict[int, list] = {}
        for deal in history:
            pid = deal.position_id
            if pid == 0:
                continue
            deal_map.setdefault(pid, []).append(deal)

        with get_db() as conn:
            for ticket in closed_tickets:
                deals = deal_map.get(ticket)
                if not deals:
                    log.warning(f"No deal history found for closed ticket {ticket}")
                    continue

                deals_sorted = sorted(deals, key=lambda d: d.time)
                has_entry = any(d.entry == 0 for d in deals_sorted)
                has_exit = any(d.entry == 1 for d in deals_sorted)

                if not (has_entry and has_exit):
                    log.warning(f"Ticket {ticket} missing entry/exit deals, skip")
                    continue

                success = self._post_trade_to_memory(ticket, deals_sorted)

                if success:
                    synced.append(ticket)
                    # Update last_ticket
                    conn.execute(
                        "UPDATE sync_state SET last_ticket = MAX(last_ticket, ?) WHERE id = 1",
                        (ticket,),
                    )
                    _log_event(conn, "TRADE_CLOSED",
                               f"ticket={ticket} synced to TradeMemory")

        return synced

    def _post_trade_to_memory(self, ticket: int, deals: list) -> bool:
        """POST record_decision + record_outcome to TradeMemory API."""
        entry_deal = deals[0]
        exit_deal = deals[-1]

        trade_id = f"MT5-{ticket}"
        symbol = entry_deal.symbol
        lot_size = entry_deal.volume
        direction = "long" if entry_deal.type == 0 else "short"
        entry_price = entry_deal.price
        exit_price = exit_deal.price
        magic = entry_deal.magic
        strategy = MAGIC_TO_STRATEGY.get(magic, f"Unknown_{magic}")
        pnl = sum(d.profit for d in deals)
        hold_duration = int((exit_deal.time - entry_deal.time) / 60)

        # --- Decision context: prefer JSONL (rich) over CSV (basic) ---
        # 1. Try JSONL decision log first (has conditions, filters, indicators)
        decision_ctx = decision_log_reader.find_decision_for_trade(
            strategy=strategy,
            entry_time=entry_deal.time,
            exec_ticket=ticket,
        )
        if decision_ctx and decision_ctx["matched"]:
            reasoning = decision_ctx["reasoning"]
            confidence = decision_ctx["confidence"]
            log.info(f"DecisionLog JSONL matched for {trade_id}: confidence={confidence}")
        else:
            # 2. Fallback to event_log CSV (Task 0.1 + 0.2)
            entry_ctx = event_log_reader.find_entry_context(
                symbol=symbol,
                magic=magic,
                position_id=ticket,
                entry_time=entry_deal.time,
            )
            reasoning = entry_ctx["reasoning"]
            confidence = entry_ctx["confidence"]
            decision_ctx = entry_ctx  # use CSV context for market_data merge
            if entry_ctx["matched"]:
                log.info(f"EventLog CSV matched for {trade_id}: confidence={confidence}")

        # Session from entry time
        hour = datetime.fromtimestamp(entry_deal.time, tz=timezone.utc).hour
        if 0 <= hour < 8:
            session = "asian"
        elif 8 <= hour < 16:
            session = "london"
        else:
            session = "newyork"

        market_context = {
            "description": (
                f"{symbol} {direction} entry at {entry_price:.2f} during {session} session. "
                f"Strategy: {strategy}. Hold: {hold_duration}min."
            ),
            "price": entry_price,
            "session": session,
            "magic_number": magic,
        }
        # Merge decision context market data
        if decision_ctx.get("market_data"):
            market_context["decision_data"] = decision_ctx["market_data"]
        # Include full JSONL decision event for audit trail (if from JSONL)
        if decision_ctx.get("decision_raw"):
            market_context["decision_event"] = decision_ctx["decision_raw"]
        # Task 0.6: Regime context from binary file
        regime = read_regime()
        if regime:
            market_context["regime"] = regime

        # --- (2) Close Discord embed (fire before TradeMemory API) ---
        emoji = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
        send_discord(
            f"{emoji} **Position Closed**\n"
            f"**{strategy}** {symbol} {direction.upper()}\n"
            f"Entry: {entry_price:.2f} \u2192 Exit: {exit_price:.2f}\n"
            f"P&L: **${pnl:+.2f}** | Lots: {lot_size} | Hold: {hold_duration}min",
            color=0x00FF00 if pnl >= 0 else 0xFF0000,
        )

        try:
            # Task 0.5: References backfill — recall similar trades before recording
            references = []
            try:
                similar = recall_similar(symbol, strategy, session)
                references = [
                    f"{m.get('id', 'unknown')} ({m.get('direction', '?')} "
                    f"pnl={m.get('pnl', 0):.2f})"
                    for m in similar[:5]  # top 5
                ]
            except Exception as e:
                log.debug(f"recall_similar failed for {trade_id}: {e}")

            # 1. record_decision
            resp1 = requests.post(
                f"{TRADEMEMORY_API}/trade/record_decision",
                json={
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "direction": direction,
                    "lot_size": lot_size,
                    "strategy": strategy,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "market_context": market_context,
                    "references": references,
                },
                timeout=10,
            )
            if resp1.status_code != 200:
                log.error(f"record_decision failed for {trade_id}: {resp1.status_code}")
                return False

            # 2. record_outcome (Task 0.3: pnl_r + Task 0.4: exit_reasoning)
            # pnl_r = PnL / initial risk, where risk = |entry - SL| * lots * contract_size
            exit_comment = getattr(exit_deal, 'comment', '') or ''
            sl_price = _extract_sl_from_comment(exit_comment)
            pnl_r = None
            sl_source = None

            if sl_price and sl_price > 0 and entry_price > 0:
                # Source 1: SL price from exit deal comment [sl XXXX.XX]
                sl_distance = abs(entry_price - sl_price)
                sl_source = "deal_comment"
            else:
                # Source 2: Try MT5 history_orders for the position
                sl_from_order = _get_sl_from_orders(ticket)
                if sl_from_order and sl_from_order > 0 and entry_price > 0:
                    sl_distance = abs(entry_price - sl_from_order)
                    sl_source = "order_history"
                    sl_price = sl_from_order
                else:
                    # Source 3: Estimate from ATR(M5) in event_log
                    atr_m5 = (entry_ctx.get("market_data") or {}).get("atr_m5")
                    if atr_m5 and atr_m5 > 0:
                        # VB uses ~1.5x ATR for SL, IM uses ~1.0x ATR
                        sl_mult = 1.5 if strategy == "VolBreakout" else 1.0
                        sl_distance = atr_m5 * sl_mult
                        sl_source = "atr_estimate"
                    else:
                        sl_distance = 0

            if sl_distance > 0 and lot_size > 0:
                # XAUUSD contract_size = 100 oz
                contract_size = _get_contract_size(symbol)
                risk_dollars = sl_distance * lot_size * contract_size
                if risk_dollars > 0:
                    pnl_r = round(pnl / risk_dollars, 4)
                    log.info(
                        f"pnl_r={pnl_r:.4f} for {trade_id} "
                        f"(sl_dist={sl_distance:.2f}, source={sl_source})"
                    )

            # Exit reasoning: determine from deal properties
            exit_reason_parts = []
            if 'sl' in exit_comment.lower():
                exit_reason_parts.append(f"SL hit at {sl_price:.2f}" if sl_price else "SL hit")
            elif 'tp' in exit_comment.lower():
                exit_reason_parts.append("TP hit")
            elif hold_duration >= 1440:  # 24h = 1440 min (MaxHoldingBars=288 * 5min)
                exit_reason_parts.append("Timeout (max holding bars)")
            else:
                exit_reason_parts.append("Manual or EA close")

            if pnl >= 0:
                exit_reason_parts.append(f"Profit ${pnl:+.2f}")
            else:
                exit_reason_parts.append(f"Loss ${pnl:+.2f}")
            if pnl_r is not None:
                exit_reason_parts.append(f"R={pnl_r:+.2f}")
            exit_reasoning = ". ".join(exit_reason_parts)

            resp2 = requests.post(
                f"{TRADEMEMORY_API}/trade/record_outcome",
                json={
                    "trade_id": trade_id,
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "pnl_r": pnl_r,
                    "exit_reasoning": exit_reasoning,
                    "hold_duration": hold_duration,
                },
                timeout=10,
            )
            if resp2.status_code != 200:
                log.error(f"record_outcome failed for {trade_id}: {resp2.status_code}")
                return False

            log.info(
                f"SYNC {trade_id}: {strategy} {symbol} {direction} "
                f"{lot_size} lots, P&L: ${pnl:.2f}, Hold: {hold_duration}min"
            )
            return True

        except requests.exceptions.RequestException as e:
            log.error(f"Network error syncing {trade_id}: {e}")
            return False
        except Exception as e:
            log.error(f"Unexpected error syncing {trade_id}: {e}")
            return False

    # --- Heartbeat ---

    def _update_heartbeat(self, consecutive_errors: int):
        with get_db() as conn:
            conn.execute(
                "UPDATE sync_state SET last_heartbeat = ?, consecutive_errors = ? WHERE id = 1",
                (_now_iso(), consecutive_errors),
            )

    # --- Main poll loop (runs in daemon thread) ---

    def _poll_loop(self):
        """Main loop: init MT5, then poll every SYNC_INTERVAL."""
        log.info("=" * 60)
        log.info("MT5Poller starting...")
        log.info(f"Account: {MT5_LOGIN} @ {MT5_SERVER}")
        log.info(f"Interval: {SYNC_INTERVAL}s | API: {TRADEMEMORY_API}")
        log.info("=" * 60)

        # Check if already connected (pre-init from main thread)
        connected = self._mt5_alive
        if not connected:
            for attempt in range(1, 6):
                if self._stop_event.is_set():
                    return
                if self.init_mt5():
                    connected = True
                    break
                wait = min(10 * attempt, 60)  # shorter waits: 10, 20, 30, 40, 60
                log.warning(f"MT5 init attempt {attempt}/5 failed, retry in {wait}s")
                self._stop_event.wait(wait)

        if not connected:
            log.error("Cannot connect to MT5 after 5 attempts. Poller stopped.")
            send_discord(
                "\u274c **MT5 Connection Failed**\n"
                f"Cannot connect after 5 attempts.\n"
                f"Account: {MT5_LOGIN} @ {MT5_SERVER}",
                color=0xFF0000,
            )
            self._update_heartbeat(MAX_CONSECUTIVE_ERRORS)
            return

        send_discord(
            f"\U0001f680 **MT5 Sync v3 Started**\n"
            f"Account: {MT5_LOGIN} @ {MT5_SERVER}\n"
            f"Interval: {SYNC_INTERVAL}s",
            color=0x3498DB,
        )

        with get_db() as conn:
            _log_event(conn, "POLLER_START", f"MT5 connected, polling every {SYNC_INTERVAL}s")

        consecutive_errors = 0
        heartbeat_counter = 0

        while not self._stop_event.is_set():
            try:
                # Health check
                if not self.is_mt5_alive():
                    # (3) MT5 disconnect Discord (once, not every cycle)
                    if not self._was_disconnected:
                        self._was_disconnected = True
                        send_discord(
                            "\u26a0\ufe0f **MT5 Connection Lost**\n"
                            f"Account: {MT5_LOGIN} @ {MT5_SERVER}\n"
                            "Attempting reconnection...",
                            color=0xFF0000,
                        )

                    log.warning("MT5 health check failed, reconnecting...")
                    if self._reconnect():
                        log.info("MT5 reconnected.")
                        # (4) MT5 reconnect Discord
                        self._was_disconnected = False
                        send_discord(
                            "\u2705 **MT5 Reconnected**\n"
                            f"Account: {MT5_LOGIN} @ {MT5_SERVER}",
                            color=0x2ECC71,
                        )
                    else:
                        consecutive_errors += 1
                        log.error(f"MT5 reconnect failed ({consecutive_errors})")
                        self._update_heartbeat(consecutive_errors)
                        self._backoff_wait(consecutive_errors)
                        continue

                # Core: sync open positions (detects opens + closes)
                self._sync_open_positions()

                consecutive_errors = 0
                self._update_heartbeat(0)

                # Heartbeat log every ~10 cycles
                heartbeat_counter += 1
                if heartbeat_counter >= 10:
                    log.info(f"[HEARTBEAT] alive, mt5={self._mt5_alive}")
                    heartbeat_counter = 0

            except Exception as e:
                consecutive_errors += 1
                log.error(f"Poll cycle error ({consecutive_errors}): {e}", exc_info=True)
                self._update_heartbeat(consecutive_errors)

                if consecutive_errors >= 3:
                    log.warning("3+ errors, attempting reconnect...")
                    if self._reconnect():
                        consecutive_errors = 0
                        if self._was_disconnected:
                            self._was_disconnected = False
                            send_discord(
                                "\u2705 **MT5 Reconnected**\n"
                                f"Account: {MT5_LOGIN} @ {MT5_SERVER}",
                                color=0x2ECC71,
                            )

            # Wait
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log.error(f"{MAX_CONSECUTIVE_ERRORS}+ errors, long wait {LONG_WAIT_SECONDS}s")
                self._stop_event.wait(LONG_WAIT_SECONDS)
                consecutive_errors = 0
            elif consecutive_errors > 0:
                self._backoff_wait(consecutive_errors)
            else:
                self._stop_event.wait(SYNC_INTERVAL)

        log.info("MT5Poller stopped.")

    def _backoff_wait(self, consecutive_errors: int):
        sleep_time = min(SYNC_INTERVAL * (2 ** min(consecutive_errors, 4)), 600)
        log.info(f"Backoff: {sleep_time}s (errors: {consecutive_errors})")
        self._stop_event.wait(sleep_time)

    # --- Thread control ---

    def start(self):
        if self._thread and self._thread.is_alive():
            log.warning("MT5Poller already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="mt5-poller")
        self._thread.start()
        log.info("MT5Poller thread started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        log.info("MT5Poller thread stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="MT5 Sync v3", version="3.0.0")
poller = MT5Poller()


@app.on_event("startup")
def startup():
    init_db()
    with get_db() as conn:
        conn.execute(
            "UPDATE sync_state SET last_heartbeat = ? WHERE id = 1",
            (_now_iso(),),
        )
        _log_event(conn, "STARTUP", "mt5_sync_v3 started")
    # Pre-init MT5 in main thread (MT5 API is not thread-safe for init)
    if poller.init_mt5():
        log.info("MT5 pre-initialized in main thread")
    else:
        log.warning("MT5 pre-init failed (will retry in poller)")
    poller.start()


@app.on_event("shutdown")
def shutdown():
    poller.stop()


# --- GET /health ---

@app.get("/health")
def health() -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sync_state WHERE id = 1").fetchone()
        pos_count = conn.execute("SELECT COUNT(*) FROM open_positions").fetchone()[0]

    return {
        "status": "running",
        "last_sync": row["last_heartbeat"] if row else "",
        "mt5_alive": poller.mt5_alive,
        "open_positions": pos_count,
        "consecutive_errors": row["consecutive_errors"] if row else 0,
    }


# --- GET / (Dashboard) ---

@app.get("/", response_class=HTMLResponse)
def dashboard():
    with get_db() as conn:
        state = conn.execute("SELECT * FROM sync_state WHERE id = 1").fetchone()
        positions = conn.execute(
            "SELECT * FROM open_positions ORDER BY entry_time DESC"
        ).fetchall()
        logs = conn.execute(
            "SELECT * FROM sync_log ORDER BY id DESC LIMIT 5"
        ).fetchall()

    errors = state["consecutive_errors"] if state else 0
    last_hb = state["last_heartbeat"] if state else ""
    mt5_alive = poller.mt5_alive

    if errors >= MAX_CONSECUTIVE_ERRORS:
        status_text, status_color = "PAUSED", "#ff9800"
    elif not mt5_alive or errors > 0:
        status_text, status_color = "ERROR", "#ff4444"
    else:
        status_text, status_color = "RUNNING", "#00e676"

    # Build positions rows
    pos_rows = ""
    if positions:
        for p in positions:
            pos_rows += (
                f"<tr>"
                f"<td>{p['symbol']}</td>"
                f"<td class='dir-{p['direction']}'>{p['direction'].upper()}</td>"
                f"<td>{p['entry_price']:.2f}</td>"
                f"<td>{p['entry_time'][:19].replace('T',' ')}</td>"
                f"<td>{p['strategy']}</td>"
                f"</tr>"
            )
    else:
        pos_rows = "<tr><td colspan='5' class='empty'>No open positions</td></tr>"

    # Build log rows
    log_rows = ""
    if logs:
        for entry in logs:
            log_rows += (
                f"<tr>"
                f"<td>{entry['timestamp'][:19].replace('T',' ')}</td>"
                f"<td><span class='badge'>{entry['event_type']}</span></td>"
                f"<td>{entry['message']}</td>"
                f"</tr>"
            )
    else:
        log_rows = "<tr><td colspan='3' class='empty'>No log entries</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MT5 Sync v3 — Mnemox</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a0a;color:#e0e0e0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;padding:24px;max-width:960px;margin:0 auto}}
h1{{font-size:1.1rem;color:#888;font-weight:400;margin-bottom:24px;letter-spacing:0.5px}}
h1 span{{color:#00b4ff}}
.status-box{{text-align:center;padding:32px 0;margin-bottom:32px;border:1px solid #1a1a1a;border-radius:8px;background:#111}}
.status-label{{font-size:0.75rem;text-transform:uppercase;letter-spacing:2px;color:#666;margin-bottom:8px}}
.status-text{{font-size:2.8rem;font-weight:700;color:{status_color};letter-spacing:2px}}
.meta{{display:flex;justify-content:center;gap:32px;margin-top:16px;font-size:0.85rem;color:#888}}
.meta .val{{color:#e0e0e0;font-weight:500}}
#ago{{color:#00b4ff}}
section{{margin-bottom:28px}}
section h2{{font-size:0.8rem;text-transform:uppercase;letter-spacing:1.5px;color:#555;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #1a1a1a}}
table{{width:100%;border-collapse:collapse;font-size:0.85rem}}
th{{text-align:left;color:#555;font-weight:500;padding:8px 10px;border-bottom:1px solid #1a1a1a;font-size:0.75rem;text-transform:uppercase;letter-spacing:0.5px}}
td{{padding:8px 10px;border-bottom:1px solid #111}}
tr:hover td{{background:#0d0d0d}}
.dir-long{{color:#00e676;font-weight:600}}
.dir-short{{color:#ff5252;font-weight:600}}
.empty{{color:#444;text-align:center;padding:20px;font-style:italic}}
.badge{{background:#1a1a2e;color:#00b4ff;padding:2px 8px;border-radius:3px;font-size:0.75rem;font-family:monospace}}
.footer{{text-align:center;margin-top:40px;color:#333;font-size:0.7rem}}
</style>
</head>
<body>

<h1><span>MNEMOX</span> &middot; MT5 Sync v3</h1>

<div class="status-box">
  <div class="status-label">System Status</div>
  <div class="status-text">{status_text}</div>
  <div class="meta">
    <div>Last sync: <span class="val">{last_hb[:19].replace('T',' ') if last_hb else 'N/A'}</span> UTC</div>
    <div>(<span id="ago">—</span>s ago)</div>
    <div>Errors: <span class="val">{errors}</span></div>
  </div>
</div>

<section>
  <h2>Open Positions ({len(positions)})</h2>
  <table>
    <thead><tr><th>Symbol</th><th>Direction</th><th>Entry Price</th><th>Entry Time</th><th>Strategy</th></tr></thead>
    <tbody>{pos_rows}</tbody>
  </table>
</section>

<section>
  <h2>Recent Sync Log</h2>
  <table>
    <thead><tr><th>Timestamp</th><th>Event</th><th>Message</th></tr></thead>
    <tbody>{log_rows}</tbody>
  </table>
</section>

<div class="footer">auto-refresh 10s &middot; MT5 Sync v3</div>

<script>
(function(){{
  var hb="{last_hb}";
  function updateAgo(){{
    if(!hb){{document.getElementById("ago").textContent="N/A";return}}
    var d=new Date(hb.endsWith("Z")?hb:hb+"Z");
    var s=Math.round((Date.now()-d.getTime())/1000);
    var el=document.getElementById("ago");
    el.textContent=s>=0?s:"0";
    if(s>120)el.style.color="#ff4444";
    else el.style.color="#00b4ff";
  }}
  updateAgo();
  setInterval(updateAgo,1000);
  setTimeout(function(){{location.reload()}},10000);
}})();
</script>

</body>
</html>"""
    return HTMLResponse(content=html)


# --- GET /open-positions ---

@app.get("/open-positions")
def open_positions_endpoint() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM open_positions ORDER BY entry_time DESC").fetchall()
    return [dict(r) for r in rows]


# --- GET /recent-trades ---

@app.get("/recent-trades")
def recent_trades() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sync_log WHERE event_type = 'TRADE_CLOSED' "
            "ORDER BY timestamp DESC LIMIT 10"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9001, reload=False)
