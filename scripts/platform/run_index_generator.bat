@echo off
REM Repo root = two levels up from this script (scripts\platform\)
cd /d "%~dp0..\.."
call .venv\Scripts\activate.bat
python scripts\generate_index.py
