"""
Reflection Runner - 產生 daily / weekly / monthly 反思報告
建議排程：daily 23:55, weekly 週日 23:55, monthly 每月最後一天 23:55

Usage:
    python daily_reflection.py              # daily (default)
    python daily_reflection.py --weekly     # weekly
    python daily_reflection.py --monthly    # monthly
"""

import argparse
import os
import requests
from datetime import date, datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TRADEMEMORY_API = os.getenv('TRADEMEMORY_API', 'http://localhost:8000')
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.getenv('REFLECTION_OUTPUT_DIR', os.path.join(_PROJECT_DIR, 'reflections'))


def generate_daily_reflection(target_date: date = None) -> str:
    """
    產生每日反思報告

    Args:
        target_date: 目標日期（預設今天）

    Returns:
        反思報告文字
    """
    if target_date is None:
        target_date = date.today()

    date_str = target_date.isoformat()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Generating daily reflection for {date_str}...")

    try:
        response = requests.post(
            f"{TRADEMEMORY_API}/reflect/run_daily",
            params={"date": date_str},
            timeout=30
        )

        if response.status_code != 200:
            print(f"[ERROR] API request failed: {response.status_code}")
            print(response.text)
            return None

        data = response.json()

        if not data.get('success'):
            print("[ERROR] Reflection generation failed")
            return None

        summary = data.get('summary', '')

        print(f"[OK] Reflection generated ({len(summary)} chars)")
        return summary

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Network error: {e}")
        return None


def generate_weekly_reflection(week_ending: date = None) -> str:
    """
    產生每週反思報告

    Args:
        week_ending: 週結束日期（預設上個週日）

    Returns:
        反思報告文字
    """
    params = {}
    if week_ending:
        params["week_ending"] = week_ending.isoformat()

    label = week_ending.isoformat() if week_ending else "last Sunday"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Generating weekly reflection for {label}...")

    try:
        response = requests.post(
            f"{TRADEMEMORY_API}/reflect/run_weekly",
            params=params,
            timeout=60
        )

        if response.status_code != 200:
            print(f"[ERROR] API request failed: {response.status_code}")
            print(response.text)
            return None

        data = response.json()

        if not data.get('success'):
            print("[ERROR] Weekly reflection generation failed")
            return None

        summary = data.get('summary', '')
        print(f"[OK] Weekly reflection generated ({len(summary)} chars)")
        return summary

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Network error: {e}")
        return None


def generate_monthly_reflection(year: int = None, month: int = None) -> str:
    """
    產生每月反思報告

    Args:
        year: 目標年份
        month: 目標月份

    Returns:
        反思報告文字
    """
    params = {}
    if year:
        params["year"] = year
    if month:
        params["month"] = month

    label = f"{year}-{month:02d}" if year and month else "current month"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Generating monthly reflection for {label}...")

    try:
        response = requests.post(
            f"{TRADEMEMORY_API}/reflect/run_monthly",
            params=params,
            timeout=60
        )

        if response.status_code != 200:
            print(f"[ERROR] API request failed: {response.status_code}")
            print(response.text)
            return None

        data = response.json()

        if not data.get('success'):
            print("[ERROR] Monthly reflection generation failed")
            return None

        summary = data.get('summary', '')
        print(f"[OK] Monthly reflection generated ({len(summary)} chars)")
        return summary

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Network error: {e}")
        return None


def save_reflection(summary: str, filename: str):
    """
    儲存反思報告到檔案

    Args:
        summary: 反思報告文字
        filename: 檔案名稱
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(summary)

    print(f"[OK] Saved to: {filepath}")


def main():
    """Main entry point with CLI argument support."""
    parser = argparse.ArgumentParser(description="TradeMemory Reflection Generator")
    parser.add_argument("--weekly", action="store_true", help="Generate weekly reflection")
    parser.add_argument("--monthly", action="store_true", help="Generate monthly reflection")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD) for daily/weekly")
    parser.add_argument("--year", type=int, help="Target year for monthly")
    parser.add_argument("--month", type=int, help="Target month for monthly")
    args = parser.parse_args()

    print("=" * 60)
    print("TradeMemory Reflection Generator")
    print("=" * 60)
    print(f"API Endpoint: {TRADEMEMORY_API}")
    print(f"Output Directory: {OUTPUT_DIR}")

    if args.weekly:
        print("Mode: WEEKLY")
    elif args.monthly:
        print("Mode: MONTHLY")
    else:
        print("Mode: DAILY")

    print("=" * 60)
    print()

    if args.weekly:
        week_ending = date.fromisoformat(args.date) if args.date else None
        summary = generate_weekly_reflection(week_ending)

        if summary:
            if week_ending:
                fname = f"reflection_weekly_{week_ending.isoformat()}.txt"
            else:
                fname = f"reflection_weekly_{date.today().isoformat()}.txt"
            save_reflection(summary, fname)

    elif args.monthly:
        year = args.year
        month = args.month
        summary = generate_monthly_reflection(year, month)

        if summary:
            y = year or date.today().year
            m = month or date.today().month
            fname = f"reflection_monthly_{y}-{m:02d}.txt"
            save_reflection(summary, fname)

    else:
        target_date = date.fromisoformat(args.date) if args.date else None
        summary = generate_daily_reflection(target_date)

        if summary:
            d = target_date or date.today()
            fname = f"reflection_{d.isoformat()}.txt"
            save_reflection(summary, fname)

    if summary:
        print("\n" + "=" * 60)
        print("REFLECTION REPORT")
        print("=" * 60)
        print(summary)
        print("=" * 60)
    else:
        print("[FAIL] Failed to generate reflection")
        exit(1)


if __name__ == "__main__":
    main()
