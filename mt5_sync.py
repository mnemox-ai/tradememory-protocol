"""
MT5 Sync Script - Non-invasive trade synchronization
監控本地 MT5 terminal，將交易記錄同步到 TradeMemory

Architecture: NG_Gold EA 不做任何修改，此腳本獨立運行監控交易
"""

import os
import sys
import time
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv

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

# State tracking
last_synced_ticket = 0


def init_mt5() -> bool:
    """Initialize MT5 connection"""
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


def get_new_closed_trades() -> list:
    """
    Get newly closed trades since last sync.
    
    Returns:
        List of closed positions (grouped deals)
    """
    import MetaTrader5 as MT5
    global last_synced_ticket
    
    # Get history from last sync time
    from_date = datetime(2020, 1, 1)  # Far enough back to catch all
    to_date = datetime.now()
    
    history = MT5.history_deals_get(from_date, to_date)
    
    if history is None or len(history) == 0:
        return []
    
    # Group by position ticket
    positions = {}
    for deal in history:
        ticket = deal.position_id
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
    
    return new_trades


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

    # Timestamps
    entry_time = datetime.fromtimestamp(entry_deal.time).isoformat()
    exit_time = datetime.fromtimestamp(exit_deal.time).isoformat()

    # Hold duration (minutes)
    hold_duration = int((exit_deal.time - entry_deal.time) / 60)

    # Market context
    hour = datetime.fromtimestamp(entry_deal.time).hour
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
    
    # Record decision
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
            timeout=5
        )
        
        if decision_resp.status_code != 200:
            log.error(f"Failed to record decision for {trade_id}: {decision_resp.text}")
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
            timeout=5
        )
        
        if outcome_resp.status_code != 200:
            log.error(f"Failed to record outcome for {trade_id}: {outcome_resp.text}")
            return False
        
        log.info(f"SYNC {trade_id}: {strategy} {symbol} {direction} {lot_size} lots, P&L: ${pnl:.2f}, Duration: {hold_duration}min")
        return True
    
    except requests.exceptions.RequestException as e:
        log.error(f"API request failed for {trade_id}: {e}")
        return False


def main_loop():
    """Main synchronization loop — resilient to transient errors."""
    global last_synced_ticket

    log.info("=" * 60)
    log.info("MT5 → TradeMemory Sync Script")
    log.info("=" * 60)
    log.info(f"API Endpoint: {TRADEMEMORY_API}")
    log.info(f"Sync Interval: {SYNC_INTERVAL}s")
    log.info(f"MT5 Account: {MT5_LOGIN} @ {MT5_SERVER}")
    log.info("=" * 60)

    # Initial MT5 connection with retry
    mt5_connected = False
    MAX_INIT_RETRIES = 5
    for attempt in range(1, MAX_INIT_RETRIES + 1):
        if init_mt5():
            mt5_connected = True
            break
        wait = min(60 * attempt, 300)  # 60s, 120s, 180s, 240s, 300s
        log.warning(f"MT5 init attempt {attempt}/{MAX_INIT_RETRIES} failed, retry in {wait}s...")
        time.sleep(wait)

    if not mt5_connected:
        log.error(f"Cannot connect to MT5 after {MAX_INIT_RETRIES} attempts. Exiting.")
        return

    log.info("Monitoring started. Press Ctrl+C to stop.")

    consecutive_errors = 0
    heartbeat_counter = 0
    HEARTBEAT_INTERVAL = 10  # Log heartbeat every 10 cycles (~10 min)

    try:
        while True:
            try:
                # Check for new trades
                new_trades = get_new_closed_trades()

                if len(new_trades) > 0:
                    log.info(f"Found {len(new_trades)} new closed trade(s)")

                    for position in new_trades:
                        sync_trade_to_memory(position)
                        last_synced_ticket = max(last_synced_ticket, position['ticket'])

                    log.info(f"Sync complete. Last ticket: {last_synced_ticket}")

                # Reset error counter on success
                consecutive_errors = 0

                # Heartbeat log
                heartbeat_counter += 1
                if heartbeat_counter >= HEARTBEAT_INTERVAL:
                    log.info(f"[HEARTBEAT] alive, last_ticket={last_synced_ticket}")
                    heartbeat_counter = 0

            except Exception as e:
                consecutive_errors += 1
                log.error(f"Sync cycle error ({consecutive_errors}): {e}")

                # Try to reconnect MT5 after repeated failures
                if consecutive_errors >= 3:
                    log.warning("3+ consecutive errors, attempting MT5 reconnect...")
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

            # Backoff sleep on errors, normal sleep otherwise
            if consecutive_errors > 0:
                sleep_time = min(SYNC_INTERVAL * (2 ** consecutive_errors), 600)
                log.info(f"Backoff sleep: {sleep_time}s")
                time.sleep(sleep_time)
            else:
                time.sleep(SYNC_INTERVAL)

    except KeyboardInterrupt:
        log.info("Shutting down gracefully...")
        try:
            import MetaTrader5 as MT5
            MT5.shutdown()
        except Exception:
            pass
        log.info("Disconnected from MT5. Goodbye!")


if __name__ == "__main__":
    main_loop()
