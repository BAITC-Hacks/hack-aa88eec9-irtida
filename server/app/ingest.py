from sqlalchemy import select

from .db import Activity, Catalog, Employee
from .schemas import DatasetBundle


class ImportValidationError(ValueError):
    """A safe, source-located error, without echoing employee records."""

    def __init__(self, path: str, reason: str, source: str = 'body'):
        self.source, self.path, self.reason = source, path, reason
        super().__init__(f'{source}: {path}: {reason}')

    def as_dict(self):
        return {'source': self.source, 'path': self.path, 'reason': self.reason}


def _record_key(name, row):
    return (row['role'], row['grade']) if name == 'grade_rules' else row['id']


def _unique_rows(name, rows):
    """Preserve the original JSON paths even when duplicate rows are skipped."""
    unique = {}
    for index, row in enumerate(rows):
        key = _record_key(name, row)
        path = f'$.{name}[{index}]'
        if key in unique:
            previous, previous_path = unique[key]
            if row != previous:
                raise ImportValidationError(path, f'Conflicting duplicate record; first occurrence is {previous_path}')
        else:
            unique[key] = (row, path)
    return list(unique.values())


def _history_by_id(db, ids):
    # A full history may exceed SQLite's parameter limit. Fetch only rows being
    # imported, in bounded batches, rather than one SQL query per activity.
    existing = {}
    for offset in range(0, len(ids), 500):
        for row in db.scalars(select(Activity).where(Activity.id.in_(ids[offset:offset + 500]))):
            existing[row.id] = row
    return existing


def import_bundle(db, bundle: DatasetBundle, dry_run=False):
    """Append-only demo-v1 import; caller holds the database write transaction.

    Official kit formats and snapshot/repetition semantics must be implemented
    only after its README is supplied. In demo-v1 profiles are current snapshots:
    importing completed history never replays gains on employee skills.
    """
    data = bundle.model_dump(mode='json')
    rows = {name: _unique_rows(name, data[name]) for name in ('employees', 'skills', 'events', 'grade_rules', 'history')}
    catalog_row = db.get(Catalog, 1)
    if catalog_row and catalog_row.payload.get('source_format') == 'kit-v1':
        raise ImportValidationError('$', 'This database uses kit-v1 assessment/history rules; import original kit files through /api/v1/imports/kit')
    catalog = catalog_row.payload if catalog_row else {'skills': [], 'events': [], 'grade_rules': []}
    merged = {}
    for name in ('skills', 'events', 'grade_rules'):
        entries = {_record_key(name, row): row for row in catalog[name]}
        for row, path in rows[name]:
            key = _record_key(name, row)
            if key in entries and entries[key] != row:
                raise ImportValidationError(path, 'Existing record has different data; it was not overwritten')
            entries[key] = row
        merged[name] = list(entries.values())

    skill_ids = {row['id'] for row in merged['skills']}
    event_ids = {row['id'] for row in merged['events']}
    employees = {row.id: row for row in db.scalars(select(Employee))}
    employee_ids = employees.keys() | {row['id'] for row, _ in rows['employees']}
    for row, path in rows['employees']:
        for skill_id in row['skills']:
            if skill_id not in skill_ids:
                raise ImportValidationError(f'{path}.skills.{skill_id}', 'Unknown skill reference')
        previous = employees.get(row['id'])
        if previous and previous.profile != row:
            raise ImportValidationError(path, 'Existing employee has different data; it was not overwritten')
    for name, field in (('events', 'effects'), ('grade_rules', 'requirements')):
        for row, path in rows[name]:
            for skill_id in row[field]:
                if skill_id not in skill_ids:
                    raise ImportValidationError(f'{path}.{field}.{skill_id}', 'Unknown skill reference')

    history = _history_by_id(db, [row['id'] for row, _ in rows['history']])
    history_fields = ('employee_id', 'event_id', 'status', 'occurred_at')
    for row, path in rows['history']:
        if row['employee_id'] not in employee_ids:
            raise ImportValidationError(f'{path}.employee_id', 'Unknown employee reference')
        if row['event_id'] not in event_ids:
            raise ImportValidationError(f'{path}.event_id', 'Unknown event reference')
        previous = history.get(row['id'])
        if previous and any(getattr(previous, field) != row[field] for field in history_fields):
            raise ImportValidationError(path, 'Existing history ID has different data; it was not overwritten')

    new_employees = [row for row, _ in rows['employees'] if row['id'] not in employees]
    new_history = [row for row, _ in rows['history'] if row['id'] not in history]
    summary = {'employees_added': len(new_employees), 'history_added': len(new_history), 'dry_run': dry_run, 'schema': 'demo-v1'}
    if dry_run:
        return summary

    # All validation happens before the first mutation. No history gain is
    # applied here, including multiple occurrences with distinct history IDs.
    try:
        if catalog_row:
            catalog_row.payload = merged
        else:
            db.add(Catalog(id=1, payload=merged))
        for row in new_employees:
            db.add(Employee(id=row['id'], profile=row))
        db.flush()
        for row in new_history:
            db.add(Activity(**row))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return summary
