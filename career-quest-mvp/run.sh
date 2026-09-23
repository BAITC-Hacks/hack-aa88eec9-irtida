#!/usr/bin/env bash
# Career Quest — запуск одной командой: ./run.sh
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

cd backend
if [ ! -f "../data/employees.json" ]; then
  echo "Генерирую стартовый датасет..."
  python3 generate_data.py
fi

echo "Career Quest запускается на http://localhost:8000  (Ctrl+C — остановить)"
python3 app.py
