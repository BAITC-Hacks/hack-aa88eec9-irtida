import hashlib
import json
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select

from .ai.providers import PROMPT_VERSION
from .db import Activity, Catalog, Employee
from .domain.progression import DOMAIN_VERSION, development_plan, skill_level


def snapshot(db, employee_id):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(404, 'Сотрудник не найден')
    row = db.get(Catalog, 1)
    catalog = row.payload if row else {'skills': [], 'events': [], 'grade_rules': []}
    history = [{'id': h.id, 'event_id': h.event_id, 'status': h.status, 'occurred_at': h.occurred_at, 'changes': h.changes} for h in db.scalars(select(Activity).where(Activity.employee_id == employee_id).order_by(Activity.occurred_at.desc(), Activity.id))]
    return employee.profile, catalog, history


def cache_key(employee, catalog, history, settings):
    context = [employee, catalog, history, settings.provider, settings.openai_model, settings.nvidia_model,
               settings.cloud_data_approved, PROMPT_VERSION, DOMAIN_VERSION]
    return hashlib.sha256(json.dumps(context, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def employee_view(db, employee_id):
    employee, catalog, history = snapshot(db, employee_id)
    names = {e['id']: e['title'] for e in catalog['events']}
    plan = development_plan(employee, catalog, history)
    skills = [{**s, 'level': skill_level(employee, s['id'])} for s in catalog['skills']]
    return {'employee': employee, 'skill_catalog': skills, 'trajectory': plan['trajectory'], 'history': [{**h, 'title': names.get(h['event_id'], h['event_id'])} for h in history], 'available': plan['available'], 'recommendation': None}


def hr_overview(db):
    catalog_row = db.get(Catalog, 1)
    catalog = catalog_row.payload if catalog_row else {'skills': [], 'events': [], 'grade_rules': []}
    gaps, no_step, participation = {}, [], {}
    employees = list(db.scalars(select(Employee).order_by(Employee.id)))
    history_by_employee = defaultdict(list)
    # A full dataset takes three SELECTs, not one history query per employee.
    status_counts = {'completed': 0, 'missed': 0, 'declined': 0, 'no_show': 0, 'dropped': 0, 'in_progress': 0, 'overdue': 0}
    for item in db.scalars(select(Activity)):
        history_by_employee[item.employee_id].append({'id': item.id, 'event_id': item.event_id, 'status': item.status, 'occurred_at': item.occurred_at})
        counts = participation.setdefault(item.event_id, dict(status_counts))
        counts[item.status] += 1
        if item.status == 'no_show':
            counts['missed'] += 1  # Backward-compatible UI aggregate; exact no_show remains available.
    for employee in employees:
        profile = employee.profile
        plan = development_plan(profile, catalog, history_by_employee[employee.id])
        path = plan['trajectory']
        for skill in path['skills']:
            row = gaps.setdefault(skill['id'], {'id': skill['id'], 'name': skill['name'], 'affected': 0, 'eligible': 0, 'unknown': 0, 'total_gap': 0})
            if skill['gap'] is None:
                row['unknown'] += 1
                continue
            row['eligible'] += 1
            row['affected'] += int(skill['gap'] > 0)
            row['total_gap'] += skill['gap']
        if plan['no_step']:
            no_step.append({'id': employee.id, 'name': profile['name'], **plan['no_step']})
    for row in gaps.values():
        row['percent'] = round(100 * row['affected'] / row['eligible']) if row['eligible'] else None
    return {'employee_count': len(employees), 'gaps': sorted(gaps.values(), key=lambda x: (-x['affected'], x['id'])), 'no_step': no_step, 'participation': [{'id': e['id'], 'title': e['title'], **participation.get(e['id'], status_counts)} for e in sorted(catalog['events'], key=lambda item: item['id'])]}
