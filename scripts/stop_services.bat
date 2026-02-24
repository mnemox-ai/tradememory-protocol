@echo off
REM ============================================================
REM  TradeMemory Services Stopper
REM  Stops: tradememory FastAPI server + mt5_sync.py
REM ============================================================

echo Stopping TradeMemory services...

REM --- Find and kill Python processes on port 8000 ---
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Killing tradememory server (PID %%p)...
    taskkill /F /PID %%p 2>nul
)

REM --- Kill mt5_sync.py (find by window title or command line) ---
wmic process where "commandline like '%%mt5_sync%%'" get processid 2>nul | findstr /r "[0-9]" > nul
if %errorlevel%==0 (
    for /f "tokens=1" %%p in ('wmic process where "commandline like '%%mt5_sync%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
        echo Killing mt5_sync.py (PID %%p)...
        taskkill /F /PID %%p 2>nul
    )
) else (
    echo mt5_sync.py not found running.
)

echo [%date% %time%] Services stopped. >> "%~dp0..\logs\startup.log"
echo Done.
pause
