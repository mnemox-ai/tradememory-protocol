@echo off
REM ============================================================
REM  MT5 Sync Watchdog
REM  Keeps mt5_sync.py alive — restarts on crash/exit.
REM  Usage: Run this instead of mt5_sync.py directly.
REM         Minimized window stays open, process auto-restarts.
REM ============================================================

setlocal

set PYTHON=C:\Users\johns\AppData\Local\Python312\python.exe
REM Repo root = two levels up from this script (scripts\platform\)
for %%I in ("%~dp0..\..") do set "PROJECT_DIR=%%~fI"
set SCRIPT=%PROJECT_DIR%\scripts\mt5_sync.py
set LOG_DIR=%PROJECT_DIR%\logs
set RESTART_DELAY=30

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

title MT5 Sync Watchdog

:loop
echo [%date% %time%] Starting mt5_sync.py... >> "%LOG_DIR%\watchdog.log"
echo [%date% %time%] Starting mt5_sync.py...

cd /d "%PROJECT_DIR%"
"%PYTHON%" -u "%SCRIPT%"

echo [%date% %time%] mt5_sync.py exited (code: %ERRORLEVEL%). Restarting in %RESTART_DELAY%s... >> "%LOG_DIR%\watchdog.log"
echo [%date% %time%] mt5_sync.py exited. Restarting in %RESTART_DELAY%s...

timeout /t %RESTART_DELAY% /nobreak > nul
goto loop
