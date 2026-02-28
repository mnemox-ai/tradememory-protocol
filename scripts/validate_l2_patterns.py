"""
Validate auto-discovered L2 patterns against manually curated findings.

Compares patterns in the patterns table (source='backtest_auto') against
the 5 manual L2 findings from MEMORY.md: MR-001, MR-002, FX-001, FX-002, BATCH-001.

Usage:
    python scripts/validate_l2_patterns.py [db_path]

Default db_path: data/backtest_v1.db
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

from src.tradememory.db import Database
from src.tradememory.journal import TradeJournal
from src.tradememory.reflection import ReflectionEngine


def validate(db_path: str):
    """Run pattern discovery and validate against manual L2."""
    db = Database(db_path)
    journal = TradeJournal(db=db)
    engine = ReflectionEngine(journal=journal)

    print(f"Database: {db_path}")
    print("Running pattern discovery...")
    discovered = engine.discover_patterns_from_backtest(db=db)
    print(f"Discovered {len(discovered)} patterns\n")

    # Re-read from DB to get properly deserialized metrics
    patterns = db.query_patterns(limit=500)

    # Index patterns by type
    by_type = {}
    for p in patterns:
        by_type.setdefault(p['pattern_type'], []).append(p)

    results = []

    # --- MR-001: MR overall unprofitable with exceptions ---
    mr_patterns = by_type.get('mr_analysis', [])
    mr001_match = None
    for p in mr_patterns:
        if p['pattern_id'] == 'AUTO-MR-001':
            mr001_match = p
            break

    if mr001_match:
        m = mr001_match['metrics']
        avg_neg = m['avg_pnl_pct'] < 0
        has_exceptions = m['variants_profitable'] > 0
        status = 'CONFIRMED' if (avg_neg and has_exceptions) else 'PARTIAL'
        notes = (
            f"avg {m['avg_pnl_pct']:+.1f}%, "
            f"{m['variants_profitable']}/{m['variants_total']} profitable"
        )
    else:
        status = 'NOT_FOUND'
        notes = 'No MR analysis pattern found'
    results.append(('MR-001', mr001_match['pattern_id'] if mr001_match else '-', status, notes))

    # --- MR-002: MR lot sizing too small at high ATR ---
    # This requires ATR data not in DB. Mark as PARTIAL if MR analysis exists.
    status = 'PARTIAL' if mr_patterns else 'NOT_FOUND'
    notes = 'Lot size/ATR analysis not available in trade_records (needs external data)'
    results.append(('MR-002', '-', status, notes))

    # --- FX-001: IM is only profitable strategy on forex (EURUSD) ---
    sym_patterns = by_type.get('symbol_fit', [])
    fx001_match = None
    for p in sym_patterns:
        if p['strategy'] == 'IntradayMomentum' and p['metrics'].get('symbols', {}).get('EURUSD'):
            fx001_match = p
            break

    if fx001_match:
        eurusd = fx001_match['metrics']['symbols'].get('EURUSD', {})
        if eurusd.get('pnl_pct', 0) > 0:
            status = 'CONFIRMED'
            notes = f"IM EURUSD {eurusd['pnl_pct']:+.1f}%, best symbol"
        else:
            status = 'PARTIAL'
            notes = f"IM found but EURUSD not positive: {eurusd.get('pnl_pct', 'N/A')}"
    else:
        # Check if IM has single symbol (no cross-symbol comparison possible)
        rank_im = [p for p in by_type.get('strategy_ranking', []) if p['strategy'] == 'IntradayMomentum']
        if rank_im:
            status = 'PARTIAL'
            notes = 'IM exists but no multi-symbol comparison available'
        else:
            status = 'NOT_FOUND'
            notes = 'No IntradayMomentum symbol fit pattern'
    results.append(('FX-001', fx001_match['pattern_id'] if fx001_match else '-', status, notes))

    # --- FX-002: VB XAUUSD RR >> forex RR ---
    fx002_match = None
    for p in sym_patterns:
        if p['strategy'] == 'VolBreakout':
            fx002_match = p
            break

    if fx002_match:
        symbols = fx002_match['metrics'].get('symbols', {})
        xauusd = symbols.get('XAUUSD', {})
        # Check if XAUUSD RR is higher than other symbols
        other_rrs = [s['rr'] for sym, s in symbols.items() if sym != 'XAUUSD' and 'rr' in s]
        xauusd_rr = xauusd.get('rr', 0)
        if xauusd_rr > 0 and other_rrs and xauusd_rr > max(other_rrs):
            status = 'CONFIRMED'
            notes = f"XAUUSD RR={xauusd_rr:.2f} > forex RR={max(other_rrs):.2f}"
        elif xauusd_rr > 0:
            status = 'PARTIAL'
            notes = f"XAUUSD RR={xauusd_rr:.2f}, comparison incomplete"
        else:
            status = 'PARTIAL'
            notes = 'VB symbol fit found but RR data incomplete'
    else:
        status = 'NOT_FOUND'
        notes = 'No VolBreakout symbol fit pattern'
    results.append(('FX-002', fx002_match['pattern_id'] if fx002_match else '-', status, notes))

    # --- BATCH-001: Strategy ranking IM > PB > VB >> MR ---
    rank_patterns = by_type.get('strategy_ranking', [])
    if rank_patterns:
        # Patterns are already sorted by total_pnl DESC
        ranking_order = [p['strategy'] for p in rank_patterns]
        # Check if IM is first and MR is last
        im_first = ranking_order[0] == 'IntradayMomentum' if ranking_order else False
        mr_last = ranking_order[-1] == 'MeanReversion' if ranking_order else False

        if im_first and mr_last:
            status = 'CONFIRMED'
            notes = f"Ranking: {' > '.join(ranking_order)}"
        elif im_first or mr_last:
            status = 'PARTIAL'
            notes = f"Ranking: {' > '.join(ranking_order)} (partial match)"
        else:
            status = 'PARTIAL'
            notes = f"Ranking: {' > '.join(ranking_order)} (different order)"
        match_id = ', '.join(p['pattern_id'] for p in rank_patterns)
    else:
        status = 'NOT_FOUND'
        notes = 'No strategy ranking patterns'
        match_id = '-'
    results.append(('BATCH-001', match_id, status, notes))

    # Print results table
    print("=" * 100)
    print("L2 VALIDATION: Auto-Discovered vs Manual Patterns")
    print("=" * 100)
    print(f"{'Manual ID':<12} {'Auto Match':<25} {'Status':<12} {'Notes'}")
    print("-" * 100)
    for manual_id, auto_id, status, notes in results:
        emoji = {'CONFIRMED': '✅', 'PARTIAL': '⚠️', 'NOT_FOUND': '❌'}.get(status, '?')
        print(f"{manual_id:<12} {auto_id:<25} {emoji} {status:<10} {notes}")

    print("-" * 100)
    confirmed = sum(1 for _, _, s, _ in results if s == 'CONFIRMED')
    partial = sum(1 for _, _, s, _ in results if s == 'PARTIAL')
    not_found = sum(1 for _, _, s, _ in results if s == 'NOT_FOUND')
    print(f"CONFIRMED: {confirmed}/5 | PARTIAL: {partial}/5 | NOT_FOUND: {not_found}/5")

    # Print all discovered patterns for reference
    print(f"\n{'=' * 100}")
    print("ALL DISCOVERED PATTERNS")
    print(f"{'=' * 100}")
    for p in patterns:
        print(f"\n[{p['pattern_id']}] ({p['pattern_type']}) confidence={p['confidence']}")
        print(f"  {p['description']}")

    return confirmed, partial, not_found


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/backtest_v1.db"

    if not os.path.isfile(db_path):
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    confirmed, partial, not_found = validate(db_path)

    if confirmed >= 3:
        print(f"\n✅ PASS: {confirmed}/5 manual patterns confirmed by auto-discovery")
    else:
        print(f"\n⚠️ LOW MATCH: Only {confirmed}/5 confirmed. Review detector logic.")


if __name__ == '__main__':
    main()
