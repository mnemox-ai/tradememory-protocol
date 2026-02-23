@echo off
REM Start trade_adapter.py in background
cd /d C:\OpenClawWork\tradememory-protocol

REM Create logs directory
if not exist logs mkdir logs

REM Start adapter (redirect to log file)
python trade_adapter.py >> logs\trade_adapter.log 2>&1
