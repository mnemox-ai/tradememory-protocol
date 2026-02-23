"""
Daily Reflection Script - 每天結束時自動產生反思報告
建議執行時間：每天 23:55（交易日結束後）
"""

import os
import requests
from datetime import date, datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TRADEMEMORY_API = os.getenv('TRADEMEMORY_API', 'http://localhost:8000')
OUTPUT_DIR = os.getenv('REFLECTION_OUTPUT_DIR', 'reflections')


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
            json={"date": date_str} if target_date else {},
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"[ERROR] API request failed: {response.status_code}")
            print(response.text)
            return None
        
        data = response.json()
        
        if not data.get('success'):
            print(f"[ERROR] Reflection generation failed")
            return None
        
        summary = data.get('summary', '')
        
        print(f"[OK] Reflection generated ({len(summary)} chars)")
        return summary
    
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Network error: {e}")
        return None


def save_reflection(summary: str, target_date: date = None):
    """
    儲存反思報告到檔案
    
    Args:
        summary: 反思報告文字
        target_date: 目標日期（預設今天）
    """
    if target_date is None:
        target_date = date.today()
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Filename: reflection_2026-02-23.txt
    filename = f"reflection_{target_date.isoformat()}.txt"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(summary)
    
    print(f"[OK] Saved to: {filepath}")


def main():
    """Main entry point"""
    print("=" * 60)
    print("Daily Reflection Generator")
    print("=" * 60)
    print(f"API Endpoint: {TRADEMEMORY_API}")
    print(f"Output Directory: {OUTPUT_DIR}")
    print("=" * 60)
    print()
    
    # Generate reflection for today
    summary = generate_daily_reflection()
    
    if summary:
        # Save to file
        save_reflection(summary)
        
        # Print summary
        print("\n" + "=" * 60)
        print("DAILY REFLECTION")
        print("=" * 60)
        print(summary)
        print("=" * 60)
    else:
        print("[FAIL] Failed to generate reflection")
        exit(1)


if __name__ == "__main__":
    main()
