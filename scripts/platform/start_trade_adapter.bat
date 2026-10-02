@echo off
REM Start trade_adapter.py in background
setlocal
REM Repo root = two levels up from this script (scripts\platform\)
for %%I in ("%~dp0..\..") do set "PROJECT_DIR=%%~fI"
REM Python: PYTHON env var if set, else .venv\Scripts\python.exe in the repo, else python on PATH
if not defined PYTHON if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"
cd /d "%PROJECT_DIR%"

REM Create logs directory
if not exist logs mkdir logs

REM Start adapter (redirect to log file)
echo [%date% %time%] trade_adapter.py with "%PYTHON%" >> logs\trade_adapter.log
"%PYTHON%" scripts/trade_adapter.py >> logs\trade_adapter.log 2>&1
