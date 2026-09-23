"""Atomic import of the four original Career Quest kit files.

Read the supplied README: skills are an assessment, missing means zero, and
completed history strictly after that assessment is replayed exactly once.
Original records stay in the local database for append-only conflict detection.
"""

import copy
import csv
import io
import json
from collections import defaultdict

from pydantic import ValidationError
from sqlalchemy import select

from .db import Activity, Catalog, Employee, ImportRecord
from .domain.progression import gain_for
from .ingest import ImportValidationError
from .kit_schemas import GRADE_ORDER, SNAPSHOT_DATE, KitEmployeesFile, KitEventsFile, KitHistory, KitSkillsFile

FILES = {'employees.json', 'events.json', 'skills.json', 'activity_history.csv'}
CSV_FIELDS = ('record_id', 'employee_id', 'event_id', 'date', 'due_date', 'status', 'completion_pct', 'score', 'feedback_rating', 'assigned_by')
SOURCE_FILE = {'employees': 'employees.json', 'events': 'events.json', 'skills': 'skills.json', 'role_profiles': 'skills.json', 'history': 'activity_history.csv', 'metadata': 'skills.json'}


def _fail(location, reason):
    source, path = location
    raise ImportValidationError(path, reason, source=source)


def _validation_error(source, exc, prefix='$'):
    error = exc.errors(include_url=False, include_input=False)[0]
    path = prefix + ''.join(f'[{part}]' if isinstance(part, int) else f'.{part}' for part in error['loc'])
    raise ImportValidationError(path, error['msg'], source=source) from exc


def _text(source, payload):
    try:
        return payload.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ImportValidationError('$', 'Expected UTF-8 text', source=source) from exc


def _json(source, payload, model):
    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ImportValidationError('$', f'Duplicate JSON object key: {key}', source=source)
            result[key] = value
        return result
    try:
        raw = json.loads(_text(source, payload), object_pairs_hook=unique_fields)
    except json.JSONDecodeError as exc:
        raise ImportValidationError(f'line {exc.lineno}', f'Invalid JSON at column {exc.colno}', source=source) from exc
    try:
        model.model_validate(raw)
    except ValidationError as exc:
        _validation_error(source, exc)
    return raw


def _csv(payload):
    source = 'activity_history.csv'
    reader = csv.reader(io.StringIO(_text(source, payload), newline=''), strict=True)
    try:
        header = next(reader, None)
        if header is None or len(header) != len(set(header)) or set(header) != set(CSV_FIELDS):
            _fail((source, 'line 1'), 'Expected exactly the documented activity_history.csv columns')
        result = []
        for values in reader:
            if not values:
                continue
            location = (source, f'line {reader.line_num}')
            if len(values) != len(header):
                _fail(location, 'CSV column count does not match the header')
            raw = dict(zip(header, values))
            normalized = dict(raw)
            for field in ('completion_pct', 'score', 'feedback_rating'):
                value = raw[field]
                if field != 'completion_pct' and value == '':
                    normalized[field] = None
                elif not value.isascii() or not value.isdigit():
                    _fail((source, f'{location[1]}.{field}'), 'Expected an integer or an allowed empty field')
                else:
                    normalized[field] = int(value)
            normalized['due_date'] = raw['due_date'] or None
            try:
                parsed = KitHistory.model_validate(normalized).model_dump(mode='json')
            except ValidationError as exc:
                _validation_error(source, exc, prefix=location[1])
            result.append((raw, parsed, location))
            if len(result) > 100000:
                _fail(location, 'Maximum 100000 history rows per import')
        return result
    except csv.Error as exc:
        raise ImportValidationError(f'line {reader.line_num}', 'Malformed CSV quoting', source=source) from exc


def _normalized_employee(raw, skill_ids):
    return {
        'id': raw['employee_id'], 'name': raw['full_name'],
        **{key: raw[key] for key in ('role', 'grade', 'tenure_months', 'department', 'manager_id', 'hire_date', 'last_review_date', 'work_format', 'preferred_language', 'career_goal')},
        'skills': {skill_id: raw['skills'].get(skill_id, 0) for skill_id in sorted(skill_ids)},
        'source_format': 'kit-v1', 'snapshot_date': SNAPSHOT_DATE.isoformat(),
    }


def _normalized_event(raw):
    return {
        'id': raw['event_id'], 'title': raw['title'], 'type': raw['type'],
        'roles': raw['target_roles'], 'grades': raw['target_grades'],
        'effects': {effect['skill_id']: {key: effect[key] for key in ('gain', 'max_level')} for effect in raw['develops_skills']},
        **{key: raw[key] for key in ('description', 'format', 'duration_hours', 'mandatory', 'prerequisites', 'upcoming_sessions')},
        'repeatable': raw['event_id'] == 'EV_036', 'source_format': 'kit-v1', 'snapshot_date': SNAPSHOT_DATE.isoformat(),
    }


def import_kit(db, files: dict[str, bytes], dry_run=False):
    """Caller owns BEGIN IMMEDIATE. Validate all data before writing; commit once."""
    if not files or set(files) - FILES:
        raise ImportValidationError('$', 'Supply one or more of the four documented kit filenames', source='upload')
    stored = {(row.source, row.record_id): row for row in db.scalars(select(ImportRecord))}
    raw = defaultdict(dict)
    for (source, record_id), row in stored.items():
        raw[source][record_id] = row.payload
    incoming, locations = {}, {}

    def add(source, record_id, value, location):
        key = source, record_id
        previous = incoming.get(key, stored[key].payload if key in stored else None)
        if previous is not None and previous != value:
            _fail(location, 'Conflicting record ID; the original imported record was not overwritten')
        incoming[key] = value
        locations[key] = location
        raw[source][record_id] = value

    for filename, model, collections in (
        ('skills.json', KitSkillsFile, ('skills', 'role_profiles')),
        ('events.json', KitEventsFile, ('events',)),
        ('employees.json', KitEmployeesFile, ('employees',)),
    ):
        if filename not in files:
            continue
        document = _json(filename, files[filename], model)
        add('metadata', filename, document['meta'], (filename, '$.meta'))
        if filename == 'skills.json':
            add('metadata', 'proficiency_scale', document['proficiency_scale'], (filename, '$.proficiency_scale'))
        for collection in collections:
            id_field = {'skills': 'skill_id', 'events': 'event_id', 'employees': 'employee_id'}.get(collection)
            for index, value in enumerate(document[collection]):
                record_id = value[id_field] if id_field else json.dumps([value['role'], value['grade']], ensure_ascii=False)
                add(collection, record_id, value, (filename, f'$.{collection}[{index}]'))
    if 'activity_history.csv' in files:
        for value, _parsed, location in _csv(files['activity_history.csv']):
            add('history', value['record_id'], value, location)

    def location(source, record_id, suffix=''):
        filename, path = locations.get((source, record_id), (SOURCE_FILE[source], f'$[id={record_id}]'))
        return filename, path + suffix

    metas = [value for key, value in raw['metadata'].items() if key != 'proficiency_scale']
    if metas and any(value != metas[0] for value in metas[1:]):
        _fail(('upload', '$.meta'), 'All kit JSON files must use matching dataset metadata')
    skill_ids = set(raw['skills'])
    if not skill_ids or not raw['role_profiles']:
        _fail(('skills.json', '$'), 'Load skills.json with skill catalog and role profiles before profiles/history')
    roles = {(value['role'], value['grade']): value for value in raw['role_profiles'].values()}
    role_names = {role for role, _ in roles}
    for record_id, value in raw['role_profiles'].items():
        for field in ('required_skills', 'critical_skills'):
            for skill_id in value[field]:
                if skill_id not in skill_ids:
                    _fail(location('role_profiles', record_id, f'.{field}'), 'Unknown skill reference')
        if not set(value['critical_skills']) <= value['required_skills'].keys():
            _fail(location('role_profiles', record_id, '.critical_skills'), 'Critical skills must appear in required_skills')
    for role in role_names:
        if any((role, grade) not in roles for grade in GRADE_ORDER):
            _fail(('skills.json', '$.role_profiles'), 'Each role must define Junior, Middle, Senior and Lead requirements')
        for previous_grade, grade in zip(GRADE_ORDER, GRADE_ORDER[1:]):
            previous, current = roles[role, previous_grade], roles[role, grade]
            if any(current['required_skills'].get(skill_id, 0) < level for skill_id, level in previous['required_skills'].items()):
                _fail(('skills.json', '$.role_profiles'), 'Skill requirements must not decrease at higher grades')

    for record_id, event in raw['events'].items():
        if set(event['target_roles']) - role_names:
            _fail(location('events', record_id, '.target_roles'), 'Unknown role in event audience')
        for index, effect in enumerate(event['develops_skills']):
            if effect['skill_id'] not in skill_ids:
                _fail(location('events', record_id, f'.develops_skills[{index}].skill_id'), 'Unknown skill reference')
        if set(event['prerequisites']) - skill_ids:
            _fail(location('events', record_id, '.prerequisites'), 'Unknown prerequisite skill reference')

    departments = {}
    for record_id, employee in raw['employees'].items():
        if set(employee['skills']) - skill_ids:
            _fail(location('employees', record_id, '.skills'), 'Unknown skill reference')
        if (employee['role'], employee['grade']) not in roles:
            _fail(location('employees', record_id, '.grade'), 'Unknown role/grade profile')
        goal = employee['career_goal']
        if goal and (goal['target_role'], goal['target_grade']) not in roles:
            _fail(location('employees', record_id, '.career_goal'), 'Unknown target role/grade profile')
        department = departments.setdefault(employee['role'], employee['department'])
        if department != employee['department']:
            _fail(location('employees', record_id, '.department'), 'The kit defines one department per role')
        manager_id = employee['manager_id']
        manager = raw['employees'].get(manager_id)
        if manager_id is not None and (not manager or manager_id == record_id or manager['grade'] != 'Lead' or manager['department'] != employee['department']):
            _fail(location('employees', record_id, '.manager_id'), 'Manager must reference another Lead in the same department')
        if manager_id is None and employee['grade'] != 'Lead':
            _fail(location('employees', record_id, '.manager_id'), 'Only department heads (Lead) have no manager')

    catalog_row = db.get(Catalog, 1)
    if catalog_row and catalog_row.payload.get('source_format') != 'kit-v1' and any(catalog_row.payload.get(name) for name in ('skills', 'events', 'grade_rules')):
        _fail(('upload', '$'), 'Cannot mix demo-v1 with kit-v1 rules; use an empty database or explicit pristine-demo replacement')
    catalog = copy.deepcopy(catalog_row.payload) if catalog_row else {'skills': [], 'events': [], 'grade_rules': []}
    normalized = {
        'skills': [{'id': value['skill_id'], 'name': value['name'], 'kind': value['type'], 'category': value['category'], 'description': value['description'], 'source_format': 'kit-v1'} for value in raw['skills'].values()],
        'events': [_normalized_event(value) for value in raw['events'].values()],
        'grade_rules': [
            {'role': role, 'grade': grade, 'next_grade': next_grade,
             'requirements': roles[role, next_grade]['required_skills'], 'critical_skills': roles[role, next_grade]['critical_skills'], 'source_format': 'kit-v1'}
            for role in sorted(role_names) for grade, next_grade in zip(GRADE_ORDER, GRADE_ORDER[1:])
        ],
    }
    for name, entries in normalized.items():
        key = (lambda value: (value['role'], value['grade'])) if name == 'grade_rules' else (lambda value: value['id'])
        existing = {key(value): value for value in catalog[name]}
        for value in entries:
            if key(value) in existing and existing[key(value)] != value:
                _fail(('skills.json' if name != 'events' else 'events.json', '$'), 'Catalog conflicts with existing data; use an empty database or explicit pristine-demo replacement')
            existing[key(value)] = value
        catalog[name] = list(existing.values())
    catalog.update(source_format='kit-v1', snapshot_date=SNAPSHOT_DATE.isoformat(), role_profiles=list(raw['role_profiles'].values()), proficiency_scale=raw['metadata'].get('proficiency_scale', {}))
    event_by_id = {value['id']: value for value in catalog['events']}
    existing_employees = {value.id: value for value in db.scalars(select(Employee))}
    existing_activities = {value.id: value for value in db.scalars(select(Activity))}
    for source, record_id in incoming:
        if source == 'employees' and record_id in existing_employees and (source, record_id) not in stored:
            _fail(location(source, record_id), 'Employee ID already exists outside this kit import')
        if source == 'history' and record_id in existing_activities and (source, record_id) not in stored:
            _fail(location(source, record_id), 'History ID already exists outside this kit import')

    histories = defaultdict(list)
    for record_id, value in raw['history'].items():
        # Stored CSV values retain their original representation for conflicts.
        employee = raw['employees'].get(value['employee_id'])
        event = raw['events'].get(value['event_id'])
        if employee is None:
            _fail(location('history', record_id, '.employee_id'), 'Unknown employee reference')
        if event is None:
            _fail(location('history', record_id, '.event_id'), 'Unknown event reference')
        if value['date'] < employee['hire_date']:
            _fail(location('history', record_id, '.date'), 'Activity cannot precede employee hire_date')
        if value['due_date'] and not event['mandatory']:
            _fail(location('history', record_id, '.due_date'), 'due_date is only allowed for mandatory events')
        if value['status'] == 'overdue' and not event['mandatory']:
            _fail(location('history', record_id, '.status'), 'overdue is only allowed for mandatory events')
        if value['status'] == 'no_show' and event['format'] == 'self_paced':
            _fail(location('history', record_id, '.status'), 'no_show is only allowed for scheduled events')
        if value['score'] and event['type'] not in {'course', 'certification', 'compliance'}:
            _fail(location('history', record_id, '.score'), 'Scores are only allowed for courses, certifications and compliance')
        if not event['mandatory']:
            if event['target_roles'] and employee['role'] not in event['target_roles']:
                _fail(location('history', record_id, '.event_id'), 'Voluntary event does not match employee role')
            if event['target_grades'] and not any(GRADE_ORDER.index(grade) <= GRADE_ORDER.index(employee['grade']) for grade in event['target_grades']):
                _fail(location('history', record_id, '.event_id'), 'Voluntary event must match current or previous employee grade')
        histories[value['employee_id']].append({'id': record_id, 'event_id': value['event_id'], 'status': value['status'], 'occurred_at': value['date']})
    for value in existing_activities.values():
        if value.id not in raw['history'] and value.employee_id in raw['employees']:
            histories[value.employee_id].append({'id': value.id, 'event_id': value.event_id, 'status': value.status, 'occurred_at': value.occurred_at})

    profiles, activity_changes, completed_after_review = {}, {}, 0
    repeated_mandatory = 0
    for employee_id, assessment in raw['employees'].items():
        profile = _normalized_employee(assessment, skill_ids)
        completed = set()
        for activity in sorted(histories[employee_id], key=lambda row: (row['occurred_at'], row['id'])):
            event = event_by_id[activity['event_id']]
            if event['id'] in completed and not event.get('repeatable'):
                if event['mandatory'] and not event['effects']:
                    # Actual kit contains recurring mandatory compliance despite
                    # its general no-repeat rule. Preserve and disclose the data.
                    repeated_mandatory += 1
                else:
                    _fail(location('history', activity['id']), 'Event cannot repeat after completed; only EV_036 is repeatable')
            after_review = activity['occurred_at'] > assessment['last_review_date']
            if after_review and not event['mandatory'] and any(profile['skills'][skill_id] < level for skill_id, level in event['prerequisites'].items()):
                _fail(location('history', activity['id'], '.event_id'), 'Post-assessment participation does not meet event prerequisites')
            changes = None
            if activity['status'] == 'completed':
                completed.add(event['id'])
                if after_review:
                    completed_after_review += 1
                    changes = {}
                    for skill_id, effect in event['effects'].items():
                        before = profile['skills'][skill_id]
                        gain = gain_for(before, effect['gain'], effect['max_level'])
                        if gain:
                            profile['skills'][skill_id] = before + gain
                            changes[skill_id] = {'name': next(skill['name'] for skill in catalog['skills'] if skill['id'] == skill_id), 'before': before, 'after': before + gain, 'gain': gain}
            activity_changes[activity['id']] = changes
        profiles[employee_id] = profile

    new_employee_ids = set(profiles) - existing_employees.keys()
    new_history_ids = set(raw['history']) - existing_activities.keys()
    warnings = []
    if repeated_mandatory:
        warnings.append({'code': 'mandatory_history_repeated_after_completion', 'count': repeated_mandatory,
                         'reason': 'The supplied kit history repeats mandatory events after completion despite its general no-repeat rule; original history is preserved.'})
    summary = {'schema': 'kit-v1', 'dry_run': dry_run, 'snapshot_date': SNAPSHOT_DATE.isoformat(),
               'employees_added': len(new_employee_ids), 'history_added': len(new_history_ids),
               'skills_added': sum(source == 'skills' and (source, record_id) not in stored for source, record_id in incoming),
               'events_added': sum(source == 'events' and (source, record_id) not in stored for source, record_id in incoming),
               'completed_after_review': completed_after_review, 'warnings': warnings}
    if dry_run:
        return summary
    try:
        if catalog_row:
            catalog_row.payload = catalog
        else:
            db.add(Catalog(id=1, payload=catalog))
        for employee_id, profile in profiles.items():
            previous = existing_employees.get(employee_id)
            if previous:
                if previous.profile != profile:
                    previous.profile = profile
                    previous.revision += 1
            else:
                db.add(Employee(id=employee_id, profile=profile))
        db.flush()
        for record_id in new_history_ids:
            value = raw['history'][record_id]
            db.add(Activity(id=record_id, employee_id=value['employee_id'], event_id=value['event_id'],
                            status=value['status'], occurred_at=value['date'], changes=activity_changes[record_id]))
        for record_id, changes in activity_changes.items():
            if record_id in existing_activities:
                existing_activities[record_id].changes = changes
        for key, value in incoming.items():
            if key not in stored:
                db.add(ImportRecord(source=key[0], record_id=key[1], payload=value))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return summary
