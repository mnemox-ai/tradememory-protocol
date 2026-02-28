"""
Parse all batch backtest reports and generate structured analysis.

Usage:
    python scripts/parse_batch_results.py [report_dir]

Default report_dir: batch_v1 in MT5 Terminal B reports directory
"""
import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

from src.tradememory.backtest_importer import (
    parse_mt5_report,
    parse_variant_tag,
    build_trade_records,
)

DEFAULT_REPORT_DIR = (
    r"C:\Users\johns\AppData\Roaming\MetaQuotes\Terminal"
    r"\D0E8209F77C8CF37AD8BF550E51FF075\reports\batch_v1"
)


def parse_all_reports(report_dir: str) -> list:
    """Parse all *_report.htm files and return structured results."""
    from pathlib import Path

    results = []
    report_files = sorted(Path(report_dir).glob('*_report.htm'))

    print(f"Found {len(report_files)} report files in {report_dir}")

    for report_path in report_files:
        tag = report_path.stem.replace('_report', '')
        variant = parse_variant_tag(tag)
        trades = parse_mt5_report(str(report_path))

        if not trades:
            results.append({
                'tag': tag,
                'strategy': variant['strategy'],
                'symbol': variant['symbol'],
                'direction': variant['direction_filter'],
                'params': variant['params'],
                'n_trades': 0,
                'pnl': 0.0,
                'pnl_pct': 0.0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'rr': 0.0,
                'max_dd_pct': 0.0,
                'empty': True,
            })
            continue

        # Calculate stats
        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] < 0]
        n = len(wins) + len(losses)

        gross_profit = sum(t['pnl'] for t in wins) if wins else 0
        gross_loss = sum(t['pnl'] for t in losses) if losses else 0
        net_pnl = gross_profit + gross_loss

        win_rate = (len(wins) / n * 100) if n > 0 else 0
        pf = abs(gross_profit / gross_loss) if gross_loss != 0 else (999 if gross_profit > 0 else 0)
        avg_win = gross_profit / len(wins) if wins else 0
        avg_loss = abs(gross_loss / len(losses)) if losses else 0
        rr = avg_win / avg_loss if avg_loss > 0 else 0

        # Max drawdown from equity curve
        balance = 10000.0
        peak = 10000.0
        max_dd = 0.0
        for t in trades:
            balance += t['pnl']
            if balance > peak:
                peak = balance
            dd = peak - balance
            if dd > max_dd:
                max_dd = dd
        max_dd_pct = (max_dd / peak * 100) if peak > 0 else 0

        results.append({
            'tag': tag,
            'strategy': variant['strategy'],
            'symbol': variant['symbol'],
            'direction': variant['direction_filter'],
            'params': variant['params'],
            'n_trades': n,
            'pnl': round(net_pnl, 2),
            'pnl_pct': round(net_pnl / 100, 2),  # of $10k
            'win_rate': round(win_rate, 1),
            'profit_factor': round(pf, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'rr': round(rr, 2),
            'max_dd_pct': round(max_dd_pct, 1),
            'empty': False,
        })

    return results


def print_summary_table(results: list):
    """Print formatted summary table."""
    print("\n" + "=" * 120)
    print("=== BATCH BACKTEST RESULTS (97 combos) ===")
    print("=" * 120)

    header = f"{'Tag':<40} {'n':>5} {'PnL':>10} {'PnL%':>7} {'WR%':>6} {'PF':>6} {'AvgW':>8} {'AvgL':>8} {'RR':>5} {'DD%':>6}"
    print(header)
    print("-" * 120)

    for r in results:
        if r['empty']:
            print(f"{r['tag']:<40} {'EMPTY':>5}")
            continue
        print(f"{r['tag']:<40} {r['n_trades']:>5} ${r['pnl']:>9.2f} {r['pnl_pct']:>6.1f}% {r['win_rate']:>5.1f} {r['profit_factor']:>6.2f} ${r['avg_win']:>7.2f} ${r['avg_loss']:>7.2f} {r['rr']:>5.2f} {r['max_dd_pct']:>5.1f}%")


def print_strategy_analysis(results: list):
    """Print per-strategy summary."""
    print("\n" + "=" * 80)
    print("=== BY STRATEGY ===")
    print("=" * 80)

    strategies = {}
    for r in results:
        s = r['strategy']
        if s not in strategies:
            strategies[s] = []
        strategies[s].append(r)

    for s, variants in sorted(strategies.items()):
        active = [v for v in variants if not v['empty'] and v['n_trades'] > 0]
        if not active:
            print(f"\n{s}: ALL EMPTY")
            continue

        avg_pnl = sum(v['pnl_pct'] for v in active) / len(active)
        avg_wr = sum(v['win_rate'] for v in active) / len(active)
        avg_pf = sum(v['profit_factor'] for v in active) / len(active)
        total_n = sum(v['n_trades'] for v in active)
        best = max(active, key=lambda v: v['pnl_pct'])
        worst = min(active, key=lambda v: v['pnl_pct'])
        profitable = sum(1 for v in active if v['pnl'] > 0)

        print(f"\n{s} ({len(active)} variants, {total_n} total trades):")
        print(f"  Avg PnL: {avg_pnl:+.2f}%  |  Avg WR: {avg_wr:.1f}%  |  Avg PF: {avg_pf:.2f}")
        print(f"  Profitable variants: {profitable}/{len(active)} ({profitable/len(active)*100:.0f}%)")
        print(f"  BEST:  {best['tag']} → {best['pnl_pct']:+.1f}% (n={best['n_trades']}, WR={best['win_rate']}%, PF={best['profit_factor']})")
        print(f"  WORST: {worst['tag']} → {worst['pnl_pct']:+.1f}% (n={worst['n_trades']}, WR={worst['win_rate']}%, PF={worst['profit_factor']})")


def print_symbol_analysis(results: list):
    """Print per-symbol summary."""
    print("\n" + "=" * 80)
    print("=== BY SYMBOL ===")
    print("=" * 80)

    symbols = {}
    for r in results:
        sym = r['symbol']
        if sym not in symbols:
            symbols[sym] = []
        symbols[sym].append(r)

    for sym, variants in sorted(symbols.items()):
        active = [v for v in variants if not v['empty'] and v['n_trades'] > 0]
        if not active:
            print(f"\n{sym}: ALL EMPTY")
            continue

        avg_pnl = sum(v['pnl_pct'] for v in active) / len(active)
        total_n = sum(v['n_trades'] for v in active)
        profitable = sum(1 for v in active if v['pnl'] > 0)

        print(f"\n{sym} ({len(active)} variants, {total_n} total trades):")
        print(f"  Avg PnL: {avg_pnl:+.2f}%  |  Profitable: {profitable}/{len(active)}")


def print_top_bottom(results: list, n=10):
    """Print top N and bottom N variants."""
    active = [r for r in results if not r['empty'] and r['n_trades'] > 10]  # min 10 trades
    ranked = sorted(active, key=lambda r: r['pnl_pct'], reverse=True)

    print(f"\n{'=' * 80}")
    print(f"=== TOP {n} VARIANTS (min 10 trades) ===")
    print(f"{'=' * 80}")
    for r in ranked[:n]:
        print(f"  {r['pnl_pct']:>+7.1f}%  PF={r['profit_factor']:<5}  WR={r['win_rate']:<5}  RR={r['rr']:<5}  n={r['n_trades']:<4}  {r['tag']}")

    print(f"\n{'=' * 80}")
    print(f"=== BOTTOM {n} VARIANTS (min 10 trades) ===")
    print(f"{'=' * 80}")
    for r in ranked[-n:]:
        print(f"  {r['pnl_pct']:>+7.1f}%  PF={r['profit_factor']:<5}  WR={r['win_rate']:<5}  RR={r['rr']:<5}  n={r['n_trades']:<4}  {r['tag']}")


def validate_ground_truth(results: list):
    """
    L2 Validation: Check if batch results confirm/contradict existing findings.

    Ground truth from MEMORY.md:
    - MR-001: MR BUY-only in uptrend market unprofitable
    - MR-002: MR lot sizing too small at high ATR
    - FX-001: IM is the only profitable strategy on forex pairs
    - FX-002: VB RR on forex is fundamentally too low (0.43-0.54)
    """
    print(f"\n{'=' * 80}")
    print("=== L2 GROUND TRUTH VALIDATION ===")
    print(f"{'=' * 80}")

    # --- MR-001: MR BUY-only in uptrend unprofitable ---
    mr_buy = [r for r in results if r['strategy'] == 'MeanReversion' and r['direction'] == 'BUY']
    mr_both = [r for r in results if r['strategy'] == 'MeanReversion' and r['direction'] == 'BOTH']

    if mr_buy:
        active_mr_buy = [r for r in mr_buy if not r['empty'] and r['n_trades'] > 0]
        if active_mr_buy:
            avg_pnl_buy = sum(r['pnl_pct'] for r in active_mr_buy) / len(active_mr_buy)
            profitable_buy = sum(1 for r in active_mr_buy if r['pnl'] > 0)
            print(f"\n[MR-001] MR BUY-only in uptrend market:")
            print(f"  Variants: {len(active_mr_buy)}  |  Avg PnL: {avg_pnl_buy:+.2f}%  |  Profitable: {profitable_buy}/{len(active_mr_buy)}")
            if avg_pnl_buy < 0 and profitable_buy == 0:
                print(f"  → CONFIRMED: MR BUY-only all negative in bull market ✅")
            elif avg_pnl_buy < 0:
                print(f"  → MOSTLY CONFIRMED: avg negative, some profitable variants ⚠️")
            else:
                print(f"  → INVALIDATED: avg positive! MR-001 needs revision ❌")

    if mr_both:
        active_mr_both = [r for r in mr_both if not r['empty'] and r['n_trades'] > 0]
        if active_mr_both:
            avg_pnl_both = sum(r['pnl_pct'] for r in active_mr_both) / len(active_mr_both)
            profitable_both = sum(1 for r in active_mr_both if r['pnl'] > 0)
            print(f"\n  MR BOTH for comparison:")
            print(f"  Variants: {len(active_mr_both)}  |  Avg PnL: {avg_pnl_both:+.2f}%  |  Profitable: {profitable_both}/{len(active_mr_both)}")
            if active_mr_buy:
                active_mr_buy2 = [r for r in mr_buy if not r['empty'] and r['n_trades'] > 0]
                avg_buy = sum(r['pnl_pct'] for r in active_mr_buy2) / len(active_mr_buy2)
                delta = avg_pnl_both - avg_buy
                print(f"  → BOTH vs BUY-only delta: {delta:+.2f}% ({'BOTH better' if delta > 0 else 'BUY-only better'})")

    # --- FX-001: IM is the only profitable strategy on forex ---
    # This batch only has XAUUSD and EURUSD, so check EURUSD results
    eurusd = [r for r in results if r['symbol'] == 'EURUSD' and not r['empty'] and r['n_trades'] > 0]
    if eurusd:
        print(f"\n[FX-001] Strategy performance on EURUSD:")
        strats_eurusd = {}
        for r in eurusd:
            s = r['strategy']
            if s not in strats_eurusd:
                strats_eurusd[s] = []
            strats_eurusd[s].append(r)

        for s, variants in sorted(strats_eurusd.items()):
            avg_pnl = sum(v['pnl_pct'] for v in variants) / len(variants)
            profitable = sum(1 for v in variants if v['pnl'] > 0)
            print(f"  {s}: Avg PnL={avg_pnl:+.2f}%, Profitable={profitable}/{len(variants)}")

        im_eurusd = strats_eurusd.get('IntradayMomentum', [])
        non_im = [r for r in eurusd if r['strategy'] != 'IntradayMomentum']
        if im_eurusd and non_im:
            im_avg = sum(v['pnl_pct'] for v in im_eurusd) / len(im_eurusd)
            non_im_avg = sum(v['pnl_pct'] for v in non_im) / len(non_im)
            if im_avg > 0 and non_im_avg < 0:
                print(f"  → CONFIRMED: IM positive ({im_avg:+.2f}%), others negative ({non_im_avg:+.2f}%) ✅")
            elif im_avg > non_im_avg:
                print(f"  → PARTIALLY CONFIRMED: IM best ({im_avg:+.2f}%), others ({non_im_avg:+.2f}%) ⚠️")
            else:
                print(f"  → INVALIDATED: IM not best on EURUSD ❌")

    # --- FX-002: VB RR too low on forex ---
    vb_xauusd = [r for r in results if r['strategy'] == 'VolBreakout' and r['symbol'] == 'XAUUSD' and not r['empty'] and r['n_trades'] > 0]
    vb_eurusd = [r for r in results if r['strategy'] == 'VolBreakout' and r['symbol'] == 'EURUSD' and not r['empty'] and r['n_trades'] > 0]

    # VB is XAUUSD-only in this batch, so validate RR range on XAUUSD
    if vb_xauusd:
        avg_rr = sum(r['rr'] for r in vb_xauusd) / len(vb_xauusd)
        avg_pf = sum(r['profit_factor'] for r in vb_xauusd) / len(vb_xauusd)
        profitable_vb = sum(1 for r in vb_xauusd if r['pnl'] > 0)
        print(f"\n[FX-002] VB on XAUUSD (baseline — forex comparison from FX-001):")
        print(f"  Variants: {len(vb_xauusd)}  |  Avg RR: {avg_rr:.2f}  |  Avg PF: {avg_pf:.2f}  |  Profitable: {profitable_vb}/{len(vb_xauusd)}")
        print(f"  → Previous forex VB RR was 0.43-0.54 (FX-001). XAUUSD RR should be much higher.")
        if avg_rr > 1.5:
            print(f"  → CONFIRMED: XAUUSD VB RR ({avg_rr:.2f}) >> forex VB RR (0.43-0.54) ✅")
        else:
            print(f"  → NEEDS INVESTIGATION: XAUUSD VB RR ({avg_rr:.2f}) lower than expected ⚠️")

    # --- Direction analysis: BUY vs BOTH across strategies ---
    print(f"\n{'=' * 80}")
    print("=== DIRECTION ANALYSIS: BUY-only vs BOTH ===")
    print(f"{'=' * 80}")

    for strat in ['VolBreakout', 'IntradayMomentum', 'MeanReversion']:
        buy_only = [r for r in results if r['strategy'] == strat and r['direction'] == 'BUY' and not r['empty'] and r['n_trades'] > 0]
        both = [r for r in results if r['strategy'] == strat and r['direction'] == 'BOTH' and not r['empty'] and r['n_trades'] > 0]

        if buy_only and both:
            avg_buy = sum(r['pnl_pct'] for r in buy_only) / len(buy_only)
            avg_both = sum(r['pnl_pct'] for r in both) / len(both)
            print(f"\n  {strat}:")
            print(f"    BUY-only: {avg_buy:+.2f}% avg ({len(buy_only)} variants)")
            print(f"    BOTH:     {avg_both:+.2f}% avg ({len(both)} variants)")
            delta = avg_both - avg_buy
            print(f"    Delta:    {delta:+.2f}% ({'BOTH better' if delta > 0 else 'BUY-only better'})")


def export_json(results: list, output_path: str):
    """Export results as JSON for tradememory import."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nJSON exported to: {output_path}")


def main():
    report_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPORT_DIR

    if not os.path.isdir(report_dir):
        print(f"ERROR: Report directory not found: {report_dir}")
        sys.exit(1)

    results = parse_all_reports(report_dir)

    if not results:
        print("No reports found!")
        sys.exit(1)

    print_summary_table(results)
    print_strategy_analysis(results)
    print_symbol_analysis(results)
    print_top_bottom(results)
    validate_ground_truth(results)

    # Export JSON
    json_path = os.path.join(report_dir, 'batch_results.json')
    export_json(results, json_path)

    # Summary stats
    active = [r for r in results if not r['empty']]
    empty = [r for r in results if r['empty']]
    profitable = [r for r in active if r['pnl'] > 0]

    print(f"\n{'=' * 80}")
    print("=== FINAL SUMMARY ===")
    print(f"{'=' * 80}")
    print(f"Total variants: {len(results)}")
    print(f"Active (>0 trades): {len(active)}")
    print(f"Empty (0 trades): {len(empty)}")
    print(f"Profitable: {len(profitable)}/{len(active)} ({len(profitable)/len(active)*100:.0f}%)" if active else "No active variants")

    if active:
        total_trades = sum(r['n_trades'] for r in active)
        overall_avg_pnl = sum(r['pnl_pct'] for r in active) / len(active)
        print(f"Total trades across all variants: {total_trades}")
        print(f"Overall avg PnL: {overall_avg_pnl:+.2f}%")


if __name__ == '__main__':
    main()
