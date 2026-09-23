from sqlalchemy import select

from .db import Activity, Catalog, Employee
from .schemas import DatasetBundle


def import_bundle(db, bundle: DatasetBundle, dry_run=False):
    """Internal demo-v1 adapter. Replace/extend only after reading the official kit."""
    data = bundle.model_dump(mode='json')
    catalog_row = db.get(Catalog, 1)
    catalog = catalog_row.payload if catalog_row else {'skills': [], 'events': [], 'grade_rules': []}
    merged = {}
    for name in ('skills', 'events', 'grade_rules'):
        key = (lambda x: (x['role'], x['grade'])) if name == 'grade_rules' else (lambda x: x['id'])
        entries = {key(x): x for x in catalog[name]}
        for item in data[name]:
            if key(item) in entries and entries[key(item)] != item:
                raise ValueError(f'Conflict in {name}: {key(item)}. Existing data was not overwritten.')
            entries[key(item)] = item
        merged[name] = list(entries.values())
    skill_ids = {s['id'] for s in merged['skills']}
    event_ids = {e['id'] for e in merged['events']}
    employee_ids = set(db.scalars(select(Employee.id))) | {e['id'] for e in data['employees']}
    for row in data['employees']:
        if set(row['skills']) - skill_ids:
            raise ValueError(f"Unknown skills in employee {row['id']}")
        existing = db.get(Employee, row['id'])
        if existing and existing.profile != row:
            raise ValueError(f"Employee {row['id']} already exists with different data")
    for row in merged['events']:
        if set(row['effects']) - skill_ids:
            raise ValueError(f"Unknown skills in event {row['id']}")
    for row in merged['grade_rules']:
        if set(row['requirements']) - skill_ids:
            raise ValueError('Unknown skills in grade rule')
    for row in data['history']:
        if row['employee_id'] not in employee_ids or row['event_id'] not in event_ids:
            raise ValueError(f"Unknown employee or event in history {row['id']}")
        previous = db.get(Activity, row['id'])
        if previous and any(getattr(previous, name) != row[name] for name in ('employee_id', 'event_id', 'status', 'occurred_at')):
            raise ValueError(f"Conflicting history ID {row['id']}")
    new_employees = [e for e in data['employees'] if db.get(Employee, e['id']) is None]
    new_history = [h for h in data['history'] if db.get(Activity, h['id']) is None]
    summary = {'employees_added': len(new_employees), 'history_added': len(new_history), 'dry_run': dry_run, 'schema': 'demo-v1'}
    if dry_run:
        return summary
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
    return summary
