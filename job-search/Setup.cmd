@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0browsers"
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 exit /b 1
echo Setup complete. Run Start.cmd to open JobPilot.
pause
