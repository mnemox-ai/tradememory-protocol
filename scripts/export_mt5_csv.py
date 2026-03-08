"""Export XAUUSD M15 historical data from MetaTrader 5 to CSV.

Usage:
    python scripts/export_mt5_csv.py
    python scripts/export_mt5_csv.py --months 6
    python scripts/export_mt5_csv.py --from 2024-01-01 --to 2026-03-01

Requires: MetaTrader5 pip package + running MT5 terminal.
Output: data/xauusd_m15_YYYYMMDD.csv (tab-separated, MT5 format)
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: pip install MetaTrader5")
    sys.exit(1)


def export(symbol: str, from_date: datetime, to_date: datetime, output_dir: str) -> str:
    """Export M15 bars from MT5 and save as tab-separated CSV."""

    if not mt5.initialize():
        print(f"ERROR: MT5 initialize failed. Error: {mt5.last_error()}")
        print("Make sure MetaTrader 5 terminal is running.")
        sys.exit(1)

    print(f"MT5 connected: {mt5.terminal_info().name}")
    print(f"Account: {mt5.account_info().login}")
    print(f"Requesting {symbol} M15 from {from_date.date()} to {to_date.date()}...")

    # Request M15 bars
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, from_date, to_date)

    if rates is None or len(rates) == 0:
        print(f"ERROR: No data returned. Check symbol '{symbol}' exists.")
        print(f"Last error: {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)

    print(f"Got {len(rates)} bars")

    # Build output path
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    filename = f"xauusd_m15_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.csv"
    outpath = outdir / filename

    # Write tab-separated CSV in MT5 format
    with open(outpath, "w", encoding="utf-8") as f:
        f.write("Date\tTime\tOpen\tHigh\tLow\tClose\tTickvol\tVolume\tSpread\n")
        for r in rates:
            dt = datetime.fromtimestamp(r["time"])
            date_str = dt.strftime("%Y.%m.%d")
            time_str = dt.strftime("%H:%M")
            f.write(
                f"{date_str}\t{time_str}\t"
                f"{r['open']:.2f}\t{r['high']:.2f}\t{r['low']:.2f}\t{r['close']:.2f}\t"
                f"{r['tick_volume']}\t{r['real_volume']}\t{r['spread']}\n"
            )

    mt5.shutdown()

    # Stats
    first_dt = datetime.fromtimestamp(rates[0]["time"])
    last_dt = datetime.fromtimestamp(rates[-1]["time"])
    trading_days = len(set(datetime.fromtimestamp(r["time"]).date() for r in rates))

    print(f"\nExported: {outpath}")
    print(f"Bars: {len(rates)}")
    print(f"Period: {first_dt.date()} to {last_dt.date()}")
    print(f"Trading days: {trading_days}")
    print(f"File size: {outpath.stat().st_size / 1024:.1f} KB")

    return str(outpath)


def main():
    parser = argparse.ArgumentParser(description="Export XAUUSD M15 data from MT5")
    parser.add_argument("--symbol", default="XAUUSD", help="Symbol (default: XAUUSD)")
    parser.add_argument("--months", type=int, default=3, help="Months of history (default: 3)")
    parser.add_argument("--from", dest="from_date", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", type=str, help="End date YYYY-MM-DD")
    parser.add_argument("--output", default="data", help="Output directory (default: data/)")
    args = parser.parse_args()

    if args.from_date:
        from_dt = datetime.strptime(args.from_date, "%Y-%m-%d")
    else:
        from_dt = datetime.now() - timedelta(days=args.months * 30)

    if args.to_date:
        to_dt = datetime.strptime(args.to_date, "%Y-%m-%d")
    else:
        to_dt = datetime.now()

    export(args.symbol, from_dt, to_dt, args.output)


if __name__ == "__main__":
    main()
