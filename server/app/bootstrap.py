"""Load the local hackathon kit once; never overwrite progress on restart."""
import os
from pathlib import Path

from sqlalchemy import select

from .db import Catalog, ImportRecord
from .import_service import load_kit

KIT_FILES = ('employees.json', 'events.json', 'skills.json', 'activity_history.csv')


def bootstrap_data(sessions, settings):
    if os.getenv('CAREER_QUEST_AUTO_IMPORT', '').lower() != 'true':
        return None
    directory = os.getenv('CAREER_QUEST_KIT_DIR', '').strip()
    if not directory:
        return None
    with sessions() as db:
        # Already initialized: keep jury imports, accounts and completed quests.
        if db.scalar(select(ImportRecord).where(ImportRecord.source == 'metadata').limit(1)):
            return None
        catalog = db.get(Catalog, 1)
        replace_demo = catalog is not None
    folder = Path(directory).resolve()
    missing = [name for name in KIT_FILES if not (folder / name).is_file()]
    if missing:
        raise RuntimeError('Incomplete Career Quest Kit: ' + ', '.join(missing))
    files = {name: (folder / name).read_bytes() for name in KIT_FILES}
    with sessions() as db:
        result = load_kit(db, files, replace_demo=replace_demo)
    print(f"Career Quest Kit loaded: {result['employees_added']} employees, "
          f"{result['events_added']} events, {result['skills_added']} skills, "
          f"{result['history_added']} history records.", flush=True)
    return result
