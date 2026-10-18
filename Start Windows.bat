@echo off
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  python scripts\run_local.py
) else (
  py -3.12 scripts\run_local.py
)
pause
