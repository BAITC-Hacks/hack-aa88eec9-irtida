@echo off
REM Career Quest — запуск одной командой на Windows: run.bat
setlocal

cd /d "%~dp0"

if not exist ".venv" (
    echo Создаю виртуальное окружение...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Устанавливаю зависимости...
pip install -q -r requirements.txt

cd backend

if not exist "..\data\employees.json" (
    echo Генерирую стартовый датасет...
    python generate_data.py
)

echo.
echo Career Quest запускается на http://localhost:8000
echo Останови сервер клавишами Ctrl+C
echo.

start "" http://localhost:8000
python app.py

pause
