@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Python environment is missing. Run start.bat once to install the project, then retry.
  pause
  exit /b 1
)

echo Career Quest: create a local HR account.
echo The password is entered in this window and is not saved in a command.
".venv\Scripts\python.exe" -m server.app.create_hr_account
set "CQ_RESULT=%ERRORLEVEL%"
if not "%CQ_RESULT%"=="0" echo HR account was not created. See the message above.
pause
exit /b %CQ_RESULT%
