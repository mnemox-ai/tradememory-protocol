@echo off
REM ============================================================
REM  MT5 Sync Watchdog
REM  Keeps mt5_sync.py alive — restarts on crash/exit.
REM  Usage: Run this instead of mt5_sync.py directly.
REM         Minimized window stays open, process auto-restarts.
REM ============================================================

setlocal

REM Repo root = two levels up from this script (scripts\platform\)
for %%I in ("%~dp0..\..") do set "PROJECT_DIR=%%~fI"
REM Python: PYTHON env var if set, else .venv\Scripts\python.exe in the repo, else python on PATH
if not defined PYTHON if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"
set SCRIPT=%PROJECT_DIR%\scripts\mt5_sync.py
set LOG_DIR=%PROJECT_DIR%\logs
set RESTART_DELAY=30

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

title MT5 Sync Watchdog

:loop
echo [%date% %time%] Starting mt5_sync.py with "%PYTHON%"... >> "%LOG_DIR%\watchdog.log"
echo [%date% %time%] Starting mt5_sync.py with "%PYTHON%"...

cd /d "%PROJECT_DIR%"
"%PYTHON%" -u "%SCRIPT%"

echo [%date% %time%] mt5_sync.py exited (code: %ERRORLEVEL%). Restarting in %RESTART_DELAY%s... >> "%LOG_DIR%\watchdog.log"
echo [%date% %time%] mt5_sync.py exited. Restarting in %RESTART_DELAY%s...

timeout /t %RESTART_DELAY% /nobreak > nul
goto loop
