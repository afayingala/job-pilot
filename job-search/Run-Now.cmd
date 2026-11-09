@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" jobpilot.py --run-once
pause
