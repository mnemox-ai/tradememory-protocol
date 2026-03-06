"""
MT5 Sync Script v2 - Non-invasive trade synchronization
監控本地 MT5 terminal，將交易記錄同步到 TradeMemory

Architecture: NG_Gold EA 不做任何修改，此腳本獨立運行監控交易

v2 improvements (2026-03-03):
- UTC timestamps for MT5 API calls (fixes timezone mismatch)
- Persistent last_synced_ticket via JSON state file (survives crash/restart)
- Threading-based timeout for MT5 API calls (prevents infinite hang on Windows)
- Broader exception handling in sync_trade_to_memory
- MT5 health check before each sync cycle
- Structured error recovery with max consecutive error limit
- Skip position_id=0 (balance operations)
"""

import os
import sys
import time
import json
import logging
import threading
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Discord Webhook helper
# ---------------------------------------------------------------------------

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")


def send_discord(message: str, color: int = 0x00FF00):
    """Send a Discord embed notification. Silently fails if no webhook configured."""
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        payload = {
            "embeds": [{
                "title": "TradeMemory — MT5 Sync",
                "description": message,
                "color": color,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception:
        pass  # Never block sync for a notification failure

# Setup logging to both file and console
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/mt5_sync.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("mt5_sync")

# Reconfigure stdout for Windows UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Load environment variables
load_dotenv()

# Configuration
MT5_LOGIN = int(os.getenv('MT5_LOGIN', '0'))
MT5_PASSWORD = os.getenv('MT5_PASSWORD', '')
MT5_SERVER = os.getenv('MT5_SERVER', '')
TRADEMEMORY_API = os.getenv('TRADEMEMORY_API', 'http://localhost:8000')
SYNC_INTERVAL = int(os.getenv('SYNC_INTERVAL', '60'))  # seconds

# Magic number → strategy name mapping
# Each EA instance on MT5 uses a unique MagicNumber to identify its trades
MAGIC_TO_STRATEGY = {
    0: "Manual",                   # Manual trades (MT5 default, no EA)
    260111: "NG_Gold",             # Default (legacy, before per-strategy magic)
    260112: "VolBreakout",         # NG_Gold.mq5 Strategy_Mode=2
    260113: "IntradayMomentum",    # NG_Gold.mq5 Strategy_Mode=8
    20260217: "Pullback",          # NG_Pullback_Entry.mq5
}

# State file for crash recovery (same directory as script)
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mt5_sync_state.json")

# Timeout for MT5 API calls (seconds)
MT5_API_TIMEOUT = 30

# Max consecutive errors before long wait
MAX_CONSECUTIVE_ERRORS = 10
LONG_WAIT_SECONDS = 300  # 5 minutes


def load_state() -> dict:
    """Load persistent state from JSON file."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            log.info(f"Loaded state: last_synced_ticket={state.get('last_synced_ticket', 0)}")
            return state
    except Exception as e:
        log.warning(f"Could not load state file: {e}")
    return {"last_synced_ticket": 0}


def save_state(last_synced_ticket: int):
    """Save persistent state to JSON file."""
    try:
        state = {
            "last_synced_ticket": last_synced_ticket,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log.warning(f"Could not save state file: {e}")


def init_mt5() -> bool:
    """Initialize MT5 connection."""
    try:
        import MetaTrader5 as MT5

        mt5_path = os.getenv('MT5_PATH', '')
        init_kwargs = dict(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER, timeout=30000)
        if mt5_path:
            init_kwargs['path'] = mt5_path

        if not MT5.initialize(**init_kwargs):
            log.error(f"MT5 initialize() failed: {MT5.last_error()}")
            return False

        account_info = MT5.account_info()
        log.info(f"Connected to MT5: {account_info.name} ({account_info.server})")
        log.info(f"Account: {account_info.login}, Balance: ${account_info.balance:.2f}")

        return True

    except ImportError:
        log.error("MetaTrader5 package not installed. Run: pip install MetaTrader5")
        return False
    except Exception as e:
        log.error(f"MT5 initialization failed: {e}")
        return False


def is_mt5_alive() -> bool:
    """Quick health check — is MT5 Terminal responsive? (with 10s timeout)"""
    try:
        import MetaTrader5 as MT5
        result, timed_out = mt5_api_call_with_timeout(
            lambda: MT5.account_info(),
            timeout_seconds=10
        )
        if timed_out:
            log.warning("MT5 health check timed out after 10s")
            return False
        return result is not None
    except Exception:
        return False


def mt5_api_call_with_timeout(func, timeout_seconds: int = MT5_API_TIMEOUT):
    """
    Execute an MT5 API call with a timeout (Windows-compatible using threading).
    Returns (result, timed_out).
    """
    result_container = {"value": None, "error": None}

    def worker():
        try:
            result_container["value"] = func()
        except Exception as e:
            result_container["error"] = e

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        log.error(f"MT5 API call timed out after {timeout_seconds}s")
        return None, True

    if result_container["error"]:
        raise result_container["error"]

    return result_container["value"], False


def get_new_closed_trades(last_synced_ticket: int) -> Tuple[list, bool]:
    """
    Get newly closed trades since last sync.

    Args:
        last_synced_ticket: Position ID of the last synced trade

    Returns:
        (list_of_closed_positions, timed_out)
    """
    import MetaTrader5 as MT5

    # Use UTC timestamps explicitly — MT5 API expects UTC
    from_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
    to_date = datetime.now(timezone.utc)

    # Call with timeout to prevent infinite hang
    history, timed_out = mt5_api_call_with_timeout(
        lambda: MT5.history_deals_get(from_date, to_date)
    )

    if timed_out:
        return [], True

    if history is None or len(history) == 0:
        return [], False

    # Group by position ticket
    positions = {}
    for deal in history:
        ticket = deal.position_id
        if ticket == 0:
            continue  # Skip balance operations / deposits / withdrawals
        if ticket not in positions:
            positions[ticket] = []
        positions[ticket].append(deal)

    # Filter new closed positions (has both entry and exit)
    new_trades = []
    for ticket, deals in positions.items():
        if ticket <= last_synced_ticket:
            continue  # Already synced

        # Check if position is closed (has exit deal)
        has_entry = any(d.entry == 0 for d in deals)  # DEAL_ENTRY_IN
        has_exit = any(d.entry == 1 for d in deals)   # DEAL_ENTRY_OUT

        if has_entry and has_exit:
            new_trades.append({
                'ticket': ticket,
                'deals': sorted(deals, key=lambda d: d.time)
            })

    return new_trades, False


def sync_trade_to_memory(position: Dict[str, Any]) -> bool:
    """
    Sync one closed position to TradeMemory.

    Args:
        position: Dict with 'ticket' and 'deals'

    Returns:
        True if successful
    """
    ticket = position['ticket']
    deals = position['deals']

    entry_deal = deals[0]
    exit_deal = deals[-1]

    # Extract data
    trade_id = f"MT5-{ticket}"
    symbol = entry_deal.symbol
    lot_size = entry_deal.volume
    direction = "long" if entry_deal.type == 0 else "short"  # 0=BUY, 1=SELL
    entry_price = entry_deal.price
    exit_price = exit_deal.price

    # Resolve strategy from magic number
    magic = entry_deal.magic
    strategy = MAGIC_TO_STRATEGY.get(magic, f"Unknown_Magic_{magic}")
    if magic not in MAGIC_TO_STRATEGY:
        log.warning(f"Unknown magic number {magic} for ticket {ticket}. Update MAGIC_TO_STRATEGY.")

    # Calculate P&L
    pnl = sum(d.profit for d in deals)

    # Timestamps (use UTC)
    entry_time = datetime.fromtimestamp(entry_deal.time, tz=timezone.utc).isoformat()
    exit_time = datetime.fromtimestamp(exit_deal.time, tz=timezone.utc).isoformat()

    # Hold duration (minutes)
    hold_duration = int((exit_deal.time - entry_deal.time) / 60)

    # Market context (use UTC hour for session)
    hour = datetime.fromtimestamp(entry_deal.time, tz=timezone.utc).hour
    if 0 <= hour < 8:
        session = "asian"
    elif 8 <= hour < 16:
        session = "london"
    else:
        session = "newyork"

    market_context = {
        "price": entry_price,
        "session": session,
        "magic_number": magic
    }

    # Record decision + outcome
    try:
        decision_resp = requests.post(
            f"{TRADEMEMORY_API}/trade/record_decision",
            json={
                "trade_id": trade_id,
                "symbol": symbol,
                "direction": direction,
                "lot_size": lot_size,
                "strategy": strategy,
                "confidence": 0.5,  # Default - MT5 doesn't store this
                "reasoning": f"Auto-synced from MT5 (magic={magic})",
                "market_context": market_context,
                "references": []
            },
            timeout=10
        )

        if decision_resp.status_code != 200:
            log.error(f"Failed to record decision for {trade_id}: {decision_resp.status_code} {decision_resp.text[:200]}")
            return False

        # Record outcome
        outcome_resp = requests.post(
            f"{TRADEMEMORY_API}/trade/record_outcome",
            json={
                "trade_id": trade_id,
                "exit_price": exit_price,
                "pnl": pnl,
                "exit_reasoning": "Position closed",
                "hold_duration": hold_duration
            },
            timeout=10
        )

        if outcome_resp.status_code != 200:
            log.error(f"Failed to record outcome for {trade_id}: {outcome_resp.status_code} {outcome_resp.text[:200]}")
            return False

        log.info(f"SYNC {trade_id}: {strategy} {symbol} {direction} {lot_size} lots, P&L: ${pnl:.2f}, Duration: {hold_duration}min")

        # Discord notification
        emoji = "🟢" if pnl >= 0 else "🔴"
        send_discord(
            f"{emoji} **{strategy}** {symbol} {direction.upper()}\n"
            f"Entry: {entry_price:.2f} → Exit: {exit_price:.2f}\n"
            f"P&L: **${pnl:+.2f}** | Lots: {lot_size} | Hold: {hold_duration}min",
            color=0x00FF00 if pnl >= 0 else 0xFF0000,
        )
        return True

    except requests.exceptions.RequestException as e:
        log.error(f"API network error for {trade_id}: {e}")
        return False
    except (ValueError, KeyError) as e:
        log.error(f"API response parsing error for {trade_id}: {e}")
        return False
    except Exception as e:
        log.error(f"Unexpected error syncing {trade_id}: {e}")
        return False


def main_loop():
    """Main synchronization loop — resilient to transient errors."""

    log.info("=" * 60)
    log.info("MT5 → TradeMemory Sync Script v2")
    log.info("=" * 60)
    log.info(f"API Endpoint: {TRADEMEMORY_API}")
    log.info(f"Sync Interval: {SYNC_INTERVAL}s")
    log.info(f"MT5 Account: {MT5_LOGIN} @ {MT5_SERVER}")
    log.info(f"State File: {STATE_FILE}")
    log.info("=" * 60)

    # Load persistent state
    state = load_state()
    last_synced_ticket = state.get("last_synced_ticket", 0)

    # Initial MT5 connection with retry
    mt5_connected = False
    MAX_INIT_RETRIES = 5
    for attempt in range(1, MAX_INIT_RETRIES + 1):
        if init_mt5():
            mt5_connected = True
            break
        wait = min(60 * attempt, 300)
        log.warning(f"MT5 init attempt {attempt}/{MAX_INIT_RETRIES} failed, retry in {wait}s...")
        time.sleep(wait)

    if not mt5_connected:
        log.error(f"Cannot connect to MT5 after {MAX_INIT_RETRIES} attempts. Exiting.")
        return

    log.info(f"Monitoring started. last_synced_ticket={last_synced_ticket}. Press Ctrl+C to stop.")

    # Discord startup notification
    send_discord(
        f"🚀 **MT5 Sync Started**\n"
        f"Account: {MT5_LOGIN} @ {MT5_SERVER}\n"
        f"Interval: {SYNC_INTERVAL}s | Last ticket: {last_synced_ticket}",
        color=0x3498DB,
    )

    consecutive_errors = 0
    heartbeat_counter = 0
    HEARTBEAT_INTERVAL = 10  # Log heartbeat every 10 cycles (~10 min)
    daily_sync_count = 0     # Trades synced today
    daily_pnl = 0.0          # P&L accumulated today
    last_summary_date = datetime.now(timezone.utc).date()  # Track day for daily summary

    try:
        while True:
            try:
                # Health check before scanning
                if not is_mt5_alive():
                    log.warning("MT5 health check failed, attempting reconnect...")
                    try:
                        import MetaTrader5 as MT5
                        MT5.shutdown()
                    except Exception:
                        pass
                    if init_mt5():
                        log.info("MT5 reconnected after health check failure.")
                    else:
                        consecutive_errors += 1
                        log.error(f"MT5 reconnect failed ({consecutive_errors})")
                        raise ConnectionError("MT5 not responsive")

                # Check for new trades (with timeout protection)
                new_trades, timed_out = get_new_closed_trades(last_synced_ticket)

                if timed_out:
                    consecutive_errors += 1
                    log.error(f"MT5 API timed out ({consecutive_errors}), forcing reconnect")
                    try:
                        import MetaTrader5 as MT5
                        MT5.shutdown()
                    except Exception:
                        pass
                    init_mt5()
                    raise TimeoutError("MT5 API call timed out")

                if len(new_trades) > 0:
                    log.info(f"Found {len(new_trades)} new closed trade(s)")
                    synced_count = 0

                    for position in new_trades:
                        if sync_trade_to_memory(position):
                            synced_count += 1
                            last_synced_ticket = max(last_synced_ticket, position['ticket'])

                    # Save state AFTER successful syncs
                    save_state(last_synced_ticket)
                    log.info(f"Sync complete. {synced_count}/{len(new_trades)} synced. Last ticket: {last_synced_ticket}")

                # Track daily stats
                if len(new_trades) > 0:
                    for position in new_trades:
                        pnl_val = sum(d.profit for d in position['deals'])
                        daily_sync_count += 1
                        daily_pnl += pnl_val

                # Daily summary at day change (UTC)
                today_utc = datetime.now(timezone.utc).date()
                if today_utc != last_summary_date:
                    if daily_sync_count > 0:
                        emoji = "📊"
                        send_discord(
                            f"{emoji} **Daily Summary — {last_summary_date}**\n"
                            f"Trades synced: **{daily_sync_count}**\n"
                            f"Total P&L: **${daily_pnl:+.2f}**",
                            color=0xF39C12,
                        )
                        log.info(f"[DAILY SUMMARY] {last_summary_date}: {daily_sync_count} trades, P&L=${daily_pnl:+.2f}")
                    last_summary_date = today_utc
                    daily_sync_count = 0
                    daily_pnl = 0.0

                # Reset error counter on success
                consecutive_errors = 0

                # Heartbeat log
                heartbeat_counter += 1
                if heartbeat_counter >= HEARTBEAT_INTERVAL:
                    log.info(f"[HEARTBEAT] alive, last_ticket={last_synced_ticket}, mt5={is_mt5_alive()}")
                    heartbeat_counter = 0

            except (ConnectionError, TimeoutError):
                # Already logged above, just handle backoff below
                pass
            except Exception as e:
                consecutive_errors += 1
                log.error(f"Sync cycle error ({consecutive_errors}): {e}", exc_info=True)

                # Try to reconnect MT5 after repeated failures
                if consecutive_errors >= 3:
                    log.warning(f"{consecutive_errors} consecutive errors, attempting MT5 reconnect...")
                    try:
                        import MetaTrader5 as MT5
                        MT5.shutdown()
                    except Exception:
                        pass
                    if init_mt5():
                        log.info("MT5 reconnected successfully.")
                        consecutive_errors = 0
                    else:
                        log.error("MT5 reconnect failed, will retry next cycle.")

            # Safety valve: too many errors → long wait
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log.error(f"{MAX_CONSECUTIVE_ERRORS}+ errors. Long wait {LONG_WAIT_SECONDS}s...")
                time.sleep(LONG_WAIT_SECONDS)
                consecutive_errors = 0
                continue

            # Backoff sleep on errors, normal sleep otherwise
            if consecutive_errors > 0:
                sleep_time = min(SYNC_INTERVAL * (2 ** min(consecutive_errors, 4)), 600)
                log.info(f"Backoff sleep: {sleep_time}s (errors: {consecutive_errors})")
                time.sleep(sleep_time)
            else:
                time.sleep(SYNC_INTERVAL)

    except KeyboardInterrupt:
        log.info("Shutting down gracefully...")
        save_state(last_synced_ticket)
        try:
            import MetaTrader5 as MT5
            MT5.shutdown()
        except Exception:
            pass
        log.info(f"Final state saved: last_ticket={last_synced_ticket}. Goodbye!")


if __name__ == "__main__":
    main_loop()
