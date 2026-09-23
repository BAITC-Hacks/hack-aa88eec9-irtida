@echo off
setlocal
cd /d "%~dp0"

set "CQ_PORT=%~1"
if not defined CQ_PORT set "CQ_PORT=8000"

if not defined ALLOWED_ORIGINS (
  set "ALLOWED_ORIGINS=http://localhost:%CQ_PORT%,http://127.0.0.1:%CQ_PORT%"
)

echo Starting Career Quest at http://127.0.0.1:%CQ_PORT%
echo Press Ctrl+C to stop.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" -Port %CQ_PORT%

if errorlevel 1 (
  echo.
  echo Career Quest could not start. See the error above.
  pause
  exit /b 1
)
