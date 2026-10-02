@echo off
REM Daily Reflection - Run at 23:55 every day
setlocal
REM Repo root = two levels up from this script (scripts\platform\)
for %%I in ("%~dp0..\..") do set "PROJECT_DIR=%%~fI"
REM Python: PYTHON env var if set, else .venv\Scripts\python.exe in the repo, else python on PATH
if not defined PYTHON if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"
cd /d "%PROJECT_DIR%"
if not exist logs mkdir logs
echo [%date% %time%] daily_reflection.py with "%PYTHON%" >> logs\reflection.log
"%PYTHON%" scripts/daily_reflection.py >> logs\reflection.log 2>&1
