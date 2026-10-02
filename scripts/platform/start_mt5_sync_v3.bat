@echo off
REM ============================================================
REM  MT5 Sync v3 Launcher
REM  Starts uvicorn on port 9001 with the Python picked below.
REM  Usage: Run manually or via Task Scheduler (MT5SyncV3_AutoStart.xml)
REM ============================================================

setlocal

REM Repo root = two levels up from this script (scripts\platform\)
for %%I in ("%~dp0..\..") do set "PROJECT_DIR=%%~fI"
REM Python: PYTHON env var if set, else .venv\Scripts\python.exe in the repo, else python on PATH
if not defined PYTHON if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"
set LOG_DIR=%PROJECT_DIR%\logs

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

title MT5 Sync v3

echo [%date% %time%] Starting MT5 Sync v3 with "%PYTHON%"... >> "%LOG_DIR%\mt5_sync_v3_start.log"

cd /d "%PROJECT_DIR%"

:loop
echo [%date% %time%] Launching uvicorn scripts.mt5_sync_v3:app ...
echo [%date% %time%] Launching uvicorn ... >> "%LOG_DIR%\mt5_sync_v3_start.log"

"%PYTHON%" -m uvicorn scripts.mt5_sync_v3:app --port 9001 --host 0.0.0.0

echo [%date% %time%] uvicorn exited (code: %ERRORLEVEL%). Restarting in 30s... >> "%LOG_DIR%\mt5_sync_v3_start.log"
echo [%date% %time%] uvicorn exited. Restarting in 30s...

timeout /t 30 /nobreak > nul
goto loop
