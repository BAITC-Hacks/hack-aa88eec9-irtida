@echo off
setlocal
cd /d "%~dp0"

set "CQ_PORT=%~1"
if not defined CQ_PORT set "CQ_PORT=8000"

echo Starting Career Quest. The actual address will appear below.
echo Press Ctrl+C to stop.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" -Port "%CQ_PORT%"

if errorlevel 1 (
  echo.
  echo Career Quest could not start. See the error above.
  pause
  exit /b 1
)
