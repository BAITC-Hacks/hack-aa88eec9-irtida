import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select

from .ai.providers import PROMPT_VERSION
from .db import Activity, Catalog, Employee
from .domain.progression import candidates, trajectory


def snapshot(db, employee_id):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(404, 'Сотрудник не найден')
    row = db.get(Catalog, 1)
    catalog = row.payload if row else {'skills': [], 'events': [], 'grade_rules': []}
    history = [{'id': h.id, 'event_id': h.event_id, 'status': h.status, 'occurred_at': h.occurred_at, 'changes': h.changes} for h in db.scalars(select(Activity).where(Activity.employee_id == employee_id).order_by(Activity.occurred_at.desc(), Activity.id))]
    return employee.profile, catalog, history


def cache_key(employee, catalog, history, settings):
    context = [employee, catalog, history, settings.provider, settings.openai_model, settings.nvidia_model, PROMPT_VERSION]
    return hashlib.sha256(json.dumps(context, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def employee_view(db, employee_id):
    employee, catalog, history = snapshot(db, employee_id)
    names = {e['id']: e['title'] for e in catalog['events']}
    return {'employee': employee, 'trajectory': trajectory(employee, catalog), 'history': [{**h, 'title': names.get(h['event_id'], h['event_id'])} for h in history], 'available': candidates(employee, catalog, history)}


def hr_overview(db):
    catalog_row = db.get(Catalog, 1)
    catalog = catalog_row.payload if catalog_row else {'skills': [], 'events': [], 'grade_rules': []}
    gaps, no_step, participation = {}, [], {}
    employees = list(db.scalars(select(Employee)))
    for employee in employees:
        profile, _, history = snapshot(db, employee.id)
        path = trajectory(profile, catalog)
        for skill in path['skills']:
            row = gaps.setdefault(skill['id'], {'name': skill['name'], 'affected': 0, 'eligible': 0, 'unknown': 0, 'total_gap': 0})
            if skill['gap'] is None:
                row['unknown'] += 1
                continue
            row['eligible'] += 1
            row['affected'] += int(skill['gap'] > 0)
            row['total_gap'] += skill['gap']
        if not candidates(profile, catalog, history):
            reason = path['status'] if path['status'] != 'ready' else 'no_eligible_activity'
            no_step.append({'id': employee.id, 'name': profile['name'], 'reason': reason})
        for item in history:
            counts = participation.setdefault(item['event_id'], {'completed': 0, 'missed': 0, 'declined': 0})
            counts[item['status']] += 1
    for row in gaps.values():
        row['percent'] = round(100 * row['affected'] / row['eligible']) if row['eligible'] else None
    return {'employee_count': len(employees), 'gaps': sorted(gaps.values(), key=lambda x: -x['affected']), 'no_step': no_step, 'participation': [{'id': e['id'], 'title': e['title'], **participation.get(e['id'], {'completed': 0, 'missed': 0, 'declined': 0})} for e in catalog['events']]}
