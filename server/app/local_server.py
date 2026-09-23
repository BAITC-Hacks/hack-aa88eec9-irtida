"""Local launcher configuration, executed in the project's Python environment."""
import argparse
from http.client import HTTPException
import os
import threading
import time
import urllib.request
import webbrowser

from .config import ROOT  # Load .env before filling local-launch defaults.


def configure_local(port):
    kit = os.getenv('CAREER_QUEST_KIT_DIR', '').strip()
    bundled = ROOT / 'career_quest_dataset/case_1/career_quest_dataset'
    if not kit and bundled.is_dir():
        kit = str(bundled)
        os.environ['CAREER_QUEST_KIT_DIR'] = kit
    if kit:
        # Preserve the old three-person demo database and all its progress.
        os.environ.setdefault('DATABASE_URL', f'sqlite:///{(ROOT / "data/career-quest-kit.db").as_posix()}')
        os.environ['CAREER_QUEST_AUTO_IMPORT'] = 'true'
    os.environ.setdefault('DEMO_MODE', 'false')
    origins = [x.strip() for x in os.getenv('ALLOWED_ORIGINS', '').split(',') if x.strip()]
    for host in ('localhost', '127.0.0.1'):
        origin = f'http://{host}:{port}'
        if origin not in origins:
            origins.append(origin)
    os.environ['ALLOWED_ORIGINS'] = ','.join(origins)
    return kit


def open_when_ready(url):
    # Loopback readiness must not be sent through a corporate HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(100):
        try:
            with opener.open(url + '/api/v1/health', timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except (OSError, HTTPException):
            time.sleep(0.2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    kit = configure_local(args.port)
    print('Local Kit found; existing imported data will be preserved.' if kit else
          'No local Kit found. Sign in as HR to import the supplied dataset.', flush=True)
    url = f'http://127.0.0.1:{args.port}'
    print(f'\nCareer Quest: {url}\nCtrl+C to stop.\n', flush=True)
    if args.open_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    import uvicorn
    uvicorn.run('server.app.main:app', host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
