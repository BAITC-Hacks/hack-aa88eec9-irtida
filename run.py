"""One-command local bootstrap. Requires Python 3.11+ and Node.js 22+."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def run(command, cwd=ROOT):
    subprocess.run([str(x) for x in command], cwd=cwd, check=True)


def main():
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11+ required')
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm:
        raise SystemExit('Install Node.js 22+ first (npm was not found).')
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        run([sys.executable, '-m', 'venv', ROOT / '.venv'])
    ready = subprocess.run([str(python), '-c', 'import fastapi, uvicorn, sqlalchemy, openai, dotenv'], capture_output=True).returncode == 0
    if not ready:
        run([python, '-m', 'pip', 'install', '-r', 'server/requirements-dev.txt'])
    if not (ROOT / 'web/node_modules').exists():
        run([npm, 'ci'], ROOT / 'web')
    run([npm, 'run', 'build'], ROOT / 'web')
    print('\nCareer Quest: http://127.0.0.1:8000\nCtrl+C to stop.\n', flush=True)
    run([python, '-m', 'uvicorn', 'app.main:app', '--app-dir', 'server', '--host', '127.0.0.1', '--port', '8000'])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
