import json

from sqlalchemy import delete, select

from .config import ROOT
from .db import Activity, Catalog, Employee, ImportRecord, LoginSession, Recommendation
from .ingest import ImportValidationError


def remove_pristine_demo(db):
    """Explicit HR transition only; user imports and progress are never erased."""
    seed = json.loads((ROOT / 'examples/demo.json').read_text(encoding='utf-8'))
    catalog = db.get(Catalog, 1)
    expected_catalog = {key: seed[key] for key in ('skills', 'events', 'grade_rules')}
    employees = list(db.scalars(select(Employee)))
    history = list(db.scalars(select(Activity)))
    expected_employees = {e['id']: e for e in seed['employees']}
    actual_history = [{'id': h.id, 'employee_id': h.employee_id, 'event_id': h.event_id,
                       'status': h.status, 'occurred_at': h.occurred_at} for h in history]
    pristine = (
        catalog is not None and catalog.payload == expected_catalog
        and len(employees) == len(expected_employees)
        and all(e.profile == expected_employees.get(e.id) and e.revision == 0 for e in employees)
        and sorted(actual_history, key=lambda h: h['id']) == sorted(seed['history'], key=lambda h: h['id'])
        and all(h.changes is None for h in history)
        and db.scalar(select(ImportRecord).limit(1)) is None
    )
    if not pristine:
        raise ImportValidationError('$', 'replace_demo requires the unchanged original synthetic demo; use a fresh database to preserve existing progress', 'request')
    db.execute(delete(LoginSession).where(LoginSession.employee_id.is_not(None)))
    db.execute(delete(Recommendation))
    db.execute(delete(Activity))
    db.execute(delete(Employee))
    db.delete(catalog)
    db.flush()


def load_kit(db, files, *, dry_run=False, replace_demo=False):
    from .kit_import import import_kit

    db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    try:
        if replace_demo:
            if set(files) != {'employees.json', 'skills.json', 'events.json', 'activity_history.csv'}:
                raise ImportValidationError('$', 'replace_demo requires all four original files', 'request')
            remove_pristine_demo(db)
        result = import_kit(db, files, dry_run=dry_run)
        if dry_run:
            db.rollback()
        return {**result, 'demo_replaced': replace_demo and not dry_run}
    except Exception:
        db.rollback()
        raise
