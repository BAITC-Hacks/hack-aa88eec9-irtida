"""One-command local bootstrap. Requires Python 3.11+ and Node.js 22+."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def run(command, cwd=ROOT):
    subprocess.run([str(x) for x in command], cwd=cwd, check=True)


def port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if os.name == 'nt':
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def choose_port(requested, strict=False):
    for port in range(requested, min(65536, requested + (1 if strict else 50))):
        if port_available(port):
            if port != requested:
                print(f'Port {requested} is already in use. Using free port {port}; existing processes are unchanged.', flush=True)
            return port
    raise SystemExit(f'No free port available from {requested}. Close the old server with Ctrl+C or run start.bat with another port.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000, help='Local HTTP port (1-65535; default: 8000).')
    parser.add_argument('--strict-port', action='store_true', help='Fail instead of selecting the next free port.')
    parser.add_argument('--open-browser', action='store_true', help='Open the app after startup.')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11+ required')
    port = choose_port(args.port, args.strict_port)
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm:
        raise SystemExit('Install Node.js 22+ first (npm was not found).')
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        run([sys.executable, '-m', 'venv', ROOT / '.venv'])
    ready = subprocess.run([str(python), '-c', 'import fastapi, uvicorn, sqlalchemy, openai, dotenv, python_multipart'], capture_output=True).returncode == 0
    if not ready:
        run([python, '-m', 'pip', 'install', '-r', 'server/requirements-dev.txt'])
    if not (ROOT / 'web/node_modules').exists():
        run([npm, 'ci'], ROOT / 'web')
    run([npm, 'run', 'build'], ROOT / 'web')
    # Dependency installation/build can take time; check again before binding.
    port = choose_port(port, args.strict_port)
    print(f'\nCareer Quest: http://127.0.0.1:{port}\nCtrl+C to stop.\n', flush=True)
    run([python, '-m', 'server.app.local_server', '--port', str(port), *(['--open-browser'] if args.open_browser else [])])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
