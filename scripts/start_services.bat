@echo off
REM ============================================================
REM  TradeMemory Services Launcher
REM  Starts: tradememory FastAPI server + mt5_sync.py
REM  Usage:  Run manually or register with Task Scheduler
REM ============================================================

setlocal

REM --- Configuration ---
set PYTHON=C:\Users\johns\AppData\Local\Python312\python.exe
set PROJECT_DIR=C:\Users\johns\projects\tradememory-protocol
set LOG_DIR=%PROJECT_DIR%\logs

REM --- Create log directory ---
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM --- Timestamp for log ---
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set DATESTAMP=%%a-%%b-%%c
echo [%date% %time%] Starting TradeMemory services... >> "%LOG_DIR%\startup.log"

REM --- Start tradememory FastAPI server (background) ---
echo Starting tradememory server on port 8000...
start /B "" "%PYTHON%" -c "import sys; sys.path.insert(0, 'src'); from tradememory.server import main; main()" >> "%LOG_DIR%\server.log" 2>&1

REM --- Wait for server to be ready ---
timeout /t 5 /nobreak > nul

REM --- Start mt5_sync.py (background) ---
echo Starting mt5_sync.py...
start /B "" "%PYTHON%" -u "%PROJECT_DIR%\mt5_sync.py" >> "%LOG_DIR%\mt5_sync.log" 2>&1

echo [%date% %time%] All services started. >> "%LOG_DIR%\startup.log"
echo.
echo TradeMemory services started:
echo   - tradememory server (localhost:8000)
echo   - mt5_sync.py (sync every 60s)
echo.
echo Logs: %LOG_DIR%\
echo Press any key to exit this window (services continue running)...
pause > nul
