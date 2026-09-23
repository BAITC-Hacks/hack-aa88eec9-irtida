"""Import an original kit directory locally, without uploading it anywhere."""
import argparse
import json
from pathlib import Path

from .config import Settings
from .db import connect
from .import_service import load_kit
from .ingest import ImportValidationError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--replace-demo', action='store_true')
    args = parser.parse_args()
    files = {name: (args.directory / name).read_bytes() for name in (
        'employees.json', 'events.json', 'skills.json', 'activity_history.csv'
    ) if (args.directory / name).is_file()}
    engine, sessions = connect(Settings().database_url)
    try:
        with sessions() as db:
            try:
                result = load_kit(db, files, dry_run=args.dry_run, replace_demo=args.replace_demo)
            except ImportValidationError as exc:
                print(json.dumps({'detail': str(exc), 'errors': [exc.as_dict()]}, ensure_ascii=False))
                return 2
            print(json.dumps(result, ensure_ascii=False))
            return 0
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
