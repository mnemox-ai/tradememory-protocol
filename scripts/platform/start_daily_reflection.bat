@echo off
REM Daily Reflection - Run at 23:55 every day
REM Repo root = two levels up from this script (scripts\platform\)
cd /d "%~dp0..\.."
python scripts/daily_reflection.py >> logs\reflection.log 2>&1
