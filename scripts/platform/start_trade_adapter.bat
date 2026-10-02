@echo off
REM Start trade_adapter.py in background
REM Repo root = two levels up from this script (scripts\platform\)
cd /d "%~dp0..\.."

REM Create logs directory
if not exist logs mkdir logs

REM Start adapter (redirect to log file)
python scripts/trade_adapter.py >> logs\trade_adapter.log 2>&1
