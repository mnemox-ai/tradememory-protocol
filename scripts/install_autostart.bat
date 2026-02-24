@echo off
REM ============================================================
REM  Install TradeMemory Auto-Start Task
REM  Registers a Windows Task Scheduler task to start services
REM  on user login.
REM
REM  Run this script as Administrator (right-click > Run as admin)
REM ============================================================

echo Installing TradeMemory auto-start task...

schtasks /create /tn "TradeMemory_AutoStart" /xml "%~dp0TradeMemory_AutoStart.xml" /f

if %errorlevel%==0 (
    echo.
    echo [OK] Task "TradeMemory_AutoStart" installed successfully!
    echo     Services will start automatically 30 seconds after login.
    echo.
    echo To manage:
    echo   - View:    schtasks /query /tn "TradeMemory_AutoStart"
    echo   - Run now: schtasks /run /tn "TradeMemory_AutoStart"
    echo   - Delete:  schtasks /delete /tn "TradeMemory_AutoStart" /f
) else (
    echo.
    echo [ERROR] Failed to install task.
    echo Please run this script as Administrator.
)

pause
