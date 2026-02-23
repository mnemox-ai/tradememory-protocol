@echo off
REM Daily Reflection - Run at 23:55 every day
cd /d C:\OpenClawWork\tradememory-protocol
python daily_reflection.py >> logs\reflection.log 2>&1
