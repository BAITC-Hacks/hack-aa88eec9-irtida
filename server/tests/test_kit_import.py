"""Synthetic tests for the documented kit shape; no organizer records included."""

import copy
import csv
import io
import json

import pytest
from sqlalchemy import func, select

from app.db import Activity, Catalog, Employee, ImportRecord, connect
from app.ingest import ImportValidationError, import_bundle
from app.kit_import import CSV_FIELDS, import_kit
from app.schemas import DatasetBundle


def history_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def history_rows(files):
    return list(csv.DictReader(io.StringIO(files['activity_history.csv'].decode('utf-8'))))


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


def synthetic_files():
    """Two fictional employees and three events in the original four-file shape."""
    meta = {'dataset': 'Career Quest', 'version': '1.0', 'as_of_date': '2026-10-01'}
    grades = ['Junior', 'Middle', 'Senior', 'Lead']
    skills = {
        'meta': meta, 'proficiency_scale': {str(level): f'Level {level}' for level in range(6)},
        'skills': [{'skill_id': 'SK_DESIGN', 'name': 'System Design', 'type': 'hard', 'category': 'Engineering', 'description': 'Synthetic design skill'},
                   {'skill_id': 'SK_SPEAK', 'name': 'Public Speaking', 'type': 'soft', 'category': 'Communication', 'description': 'Synthetic speaking skill'}],
        'role_profiles': [{'role': 'Engineer', 'grade': grade, 'required_skills': {'SK_DESIGN': design, 'SK_SPEAK': speaking}, 'critical_skills': ['SK_DESIGN']}
                          for grade, design, speaking in zip(grades, [1, 2, 4, 5], [0, 1, 3, 4])],
    }
    employee = {'employee_id': 'K1', 'full_name': 'Synthetic member', 'department': 'Engineering', 'role': 'Engineer', 'grade': 'Middle',
                'manager_id': 'K_LEAD', 'hire_date': '2025-10-01', 'tenure_months': 12,
                'work_format': 'remote', 'preferred_language': 'en', 'career_goal': {'target_role': 'Engineer', 'target_grade': 'Senior'},
                'skills': {'SK_DESIGN': 1}, 'last_review_date': '2026-09-01'}
    lead = {**employee, 'employee_id': 'K_LEAD', 'full_name': 'Synthetic lead', 'grade': 'Lead', 'manager_id': None,
            'hire_date': '2020-10-01', 'tenure_months': 72, 'career_goal': None, 'skills': {'SK_DESIGN': 5, 'SK_SPEAK': 5}}
    event = {'event_id': 'EV_DESIGN', 'title': 'Synthetic design workshop', 'description': 'Synthetic', 'type': 'workshop', 'format': 'online',
             'duration_hours': 2, 'mandatory': False, 'target_roles': ['Engineer'], 'target_grades': ['Junior', 'Middle'],
             'develops_skills': [{'skill_id': 'SK_DESIGN', 'gain': 2, 'max_level': 3}], 'prerequisites': {},
             'upcoming_sessions': ['2026-10-05', '2026-10-12']}
    recurring = {**event, 'event_id': 'EV_036', 'title': 'Synthetic recurring club', 'type': 'meetup', 'target_grades': grades,
                 'develops_skills': [{'skill_id': 'SK_SPEAK', 'gain': 1, 'max_level': 5}]}
    mandatory = {**event, 'event_id': 'EV_COMPLIANCE', 'title': 'Synthetic compliance', 'type': 'compliance', 'format': 'self_paced',
                 'mandatory': True, 'target_grades': grades, 'develops_skills': [], 'upcoming_sessions': []}
    row = {'record_id': 'KH_DESIGN', 'employee_id': 'K1', 'event_id': 'EV_DESIGN', 'date': '2026-09-10',
           'due_date': '', 'status': 'completed', 'completion_pct': '100', 'score': '', 'feedback_rating': '', 'assigned_by': 'self'}
    return {'skills.json': json_bytes(skills), 'employees.json': json_bytes({'meta': meta, 'employees': [employee, lead]}),
            'events.json': json_bytes({'meta': meta, 'events': [event, recurring, mandatory]}),
            'activity_history.csv': history_bytes([row, {**row, 'record_id': 'KH_SPEAK', 'event_id': 'EV_036', 'date': '2026-09-20'}])}


@pytest.fixture
def database(tmp_path):
    engine, sessions = connect(f'sqlite:///{tmp_path / "kit.db"}')
    with sessions() as db:
        yield db
    engine.dispose()


def test_raw_four_file_dry_run_write_and_exact_repeat(database):
    files = synthetic_files()
    preview = import_kit(database, files, dry_run=True)
    assert preview['schema'] == 'kit-v1' and preview['employees_added'] == 2 and preview['history_added'] == 2
    assert database.get(Catalog, 1) is None
    assert database.scalar(select(func.count()).select_from(ImportRecord)) == 0
    assert import_kit(database, files)['completed_after_review'] == 2
    profile = database.get(Employee, 'K1').profile
    assert profile['skills'] == {'SK_DESIGN': 3, 'SK_SPEAK': 1}
    assert profile['source_format'] == 'kit-v1' and profile['snapshot_date'] == '2026-10-01'
    assert import_kit(database, files)['employees_added'] == 0
    assert database.get(Employee, 'K1').profile == profile
    assert database.scalar(select(func.count()).select_from(Activity)) == 2
    rules = database.get(Catalog, 1).payload['grade_rules']
    middle = next(rule for rule in rules if rule['grade'] == 'Middle')
    assert middle['next_grade'] == 'Senior' and middle['requirements']['SK_DESIGN'] == 4
    assert middle['critical_skills'] == ['SK_DESIGN']


def test_supplemental_employee_and_history_share_existing_catalog_and_replay(database):
    files = synthetic_files()
    import_kit(database, files)
    employees = json.loads(files['employees.json'])
    employees['employees'] = [{**employees['employees'][0], 'employee_id': 'K_EXTRA'}]
    extra_history = [{**history_rows(files)[1], 'record_id': 'KH_EXTRA', 'employee_id': 'K_EXTRA'}]
    extra = {'employees.json': json_bytes(employees), 'activity_history.csv': history_bytes(extra_history)}
    result = import_kit(database, extra)
    assert result['employees_added'] == result['history_added'] == 1
    assert database.get(Employee, 'K_EXTRA').profile['skills'] == {'SK_DESIGN': 1, 'SK_SPEAK': 1}
    assert import_kit(database, extra)['history_added'] == 0


def test_late_arriving_history_replays_from_assessment_and_includes_local_completion(database):
    files = synthetic_files()
    import_kit(database, files)
    database.add(Activity(id='completion_local', employee_id='K1', event_id='EV_036', status='completed', occurred_at='2026-10-05', changes={}))
    database.commit()
    earlier = {**history_rows(files)[1], 'record_id': 'KH_EARLIER', 'date': '2026-09-15'}
    import_kit(database, {'activity_history.csv': history_bytes([earlier])})
    assert database.get(Employee, 'K1').profile['skills']['SK_SPEAK'] == 3
    assert database.get(Activity, 'completion_local').changes['SK_SPEAK'] == {'name': 'Public Speaking', 'before': 2, 'after': 3, 'gain': 1}
    import_kit(database, files)
    assert database.get(Employee, 'K1').profile['skills']['SK_SPEAK'] == 3


def test_history_on_or_before_review_is_not_awarded_twice(database):
    files = synthetic_files()
    rows = history_rows(files)
    rows.extend([{**rows[1], 'record_id': 'BEFORE', 'date': '2026-08-31'}, {**rows[1], 'record_id': 'ON_REVIEW', 'date': '2026-09-01'}])
    files['activity_history.csv'] = history_bytes(rows)
    import_kit(database, files)
    assert database.get(Employee, 'K1').profile['skills']['SK_SPEAK'] == 1
    assert database.get(Activity, 'ON_REVIEW').changes is None


def test_gain_respects_event_cap_and_never_decreases_assessment(database):
    files = synthetic_files()
    employees = json.loads(files['employees.json'])
    employees['employees'][0]['skills'] = {'SK_DESIGN': 4, 'SK_SPEAK': 5}
    files['employees.json'] = json_bytes(employees)
    import_kit(database, files)
    assert database.get(Employee, 'K1').profile['skills'] == {'SK_DESIGN': 4, 'SK_SPEAK': 5}
    assert database.get(Activity, 'KH_DESIGN').changes == {}


def test_gain_may_exceed_scale_but_result_is_capped_at_max_level(database):
    files = synthetic_files()
    events = json.loads(files['events.json'])
    events['events'][0]['develops_skills'][0].update(gain=9, max_level=5)
    files['events.json'] = json_bytes(events)
    import_kit(database, files)
    assert database.get(Employee, 'K1').profile['skills']['SK_DESIGN'] == 5
    assert database.get(Activity, 'KH_DESIGN').changes['SK_DESIGN']['gain'] == 4


def test_repeated_mandatory_kit_rows_preserved_with_warning(database):
    files = synthetic_files()
    row = {**history_rows(files)[0], 'event_id': 'EV_COMPLIANCE', 'due_date': '2026-09-30', 'assigned_by': 'hr'}
    files['activity_history.csv'] = history_bytes([{**row, 'record_id': 'CM1'}, {**row, 'record_id': 'CM2', 'date': '2026-09-20'}])
    result = import_kit(database, files)
    assert result['warnings'][0]['code'] == 'mandatory_history_repeated_after_completion'
    assert result['warnings'][0]['count'] == 1
    assert database.get(Employee, 'K1').profile['skills'] == {'SK_DESIGN': 1, 'SK_SPEAK': 0}


def test_voluntary_nonrepeatable_history_after_completed_rejected(database):
    files = synthetic_files()
    rows = history_rows(files)
    rows.append({**rows[0], 'record_id': 'REPEAT', 'date': '2026-09-21'})
    files['activity_history.csv'] = history_bytes(rows)
    with pytest.raises(ImportValidationError, match='cannot repeat'):
        import_kit(database, files)
    assert database.get(Catalog, 1) is None


def test_kit_warning_does_not_allow_repeated_mandatory_skill_awards(database):
    files = synthetic_files()
    events = json.loads(files['events.json'])
    events['events'][0]['mandatory'] = True
    files['events.json'] = json_bytes(events)
    rows = history_rows(files)
    rows.append({**rows[0], 'record_id': 'REPEAT', 'date': '2026-09-21'})
    files['activity_history.csv'] = history_bytes(rows)
    with pytest.raises(ImportValidationError, match='cannot repeat'):
        import_kit(database, files)


@pytest.mark.parametrize(('filename', 'collection', 'field', 'value'), [
    ('employees.json', 'employees', 'full_name', 'Conflicting name'),
    ('events.json', 'events', 'title', 'Conflicting title'),
    ('skills.json', 'skills', 'name', 'Conflicting skill'),
])
def test_conflicts_do_not_overwrite_imported_records_or_live_skills(database, filename, collection, field, value):
    files = synthetic_files()
    import_kit(database, files)
    original = copy.deepcopy(database.get(Employee, 'K1').profile)
    document = json.loads(files[filename])
    document[collection][0][field] = value
    with pytest.raises(ImportValidationError) as caught:
        import_kit(database, {filename: json_bytes(document)})
    assert caught.value.source == filename and caught.value.path == f'$.{collection}[0]'
    assert database.get(Employee, 'K1').profile == original


@pytest.mark.parametrize(('field', 'value'), [('employee_id', 'MISSING'), ('event_id', 'MISSING'), ('status', 'missed'), ('completion_pct', '99'), ('date', '2026-10-01')])
def test_bad_csv_has_filename_and_line_and_is_atomic(database, field, value):
    files = synthetic_files()
    rows = history_rows(files)
    rows[0][field] = value
    files['activity_history.csv'] = history_bytes(rows)
    with pytest.raises(ImportValidationError) as caught:
        import_kit(database, files)
    assert caught.value.source == 'activity_history.csv'
    assert caught.value.path.startswith('line 2')
    assert database.get(Catalog, 1) is None


@pytest.mark.parametrize(('field', 'value'), [('manager_id', 'MISSING'), ('grade', 'Unknown'), ('skills', {'UNKNOWN': 1}), ('tenure_months', 13), ('hire_date', '2026-11-01')])
def test_bad_profile_has_json_path_and_is_atomic(database, field, value):
    files = synthetic_files()
    data = json.loads(files['employees.json'])
    data['employees'][0][field] = value
    files['employees.json'] = json_bytes(data)
    with pytest.raises(ImportValidationError) as caught:
        import_kit(database, files)
    assert caught.value.source == 'employees.json'
    assert caught.value.path.startswith('$.employees[0]')
    assert database.get(Catalog, 1) is None


def test_missing_catalog_cannot_import_employee_subset(database):
    files = synthetic_files()
    with pytest.raises(ImportValidationError, match='Load skills.json'):
        import_kit(database, {'employees.json': files['employees.json']})


def test_exact_csv_duplicate_is_skipped_but_conflicting_same_record_id_rejected(database):
    files = synthetic_files()
    rows = history_rows(files)
    files['activity_history.csv'] = history_bytes([*rows, rows[0]])
    assert import_kit(database, files)['history_added'] == 2
    bad = {**rows[0], 'status': 'dropped', 'completion_pct': '50'}
    with pytest.raises(ImportValidationError, match='Conflicting record ID'):
        import_kit(database, {'activity_history.csv': history_bytes([bad])})
    assert database.get(Activity, 'KH_DESIGN').status == 'completed'


def test_demo_bundle_cannot_mix_with_official_assessment_semantics(database):
    import_kit(database, synthetic_files())
    with pytest.raises(ImportValidationError, match='kit-v1'):
        import_bundle(database, DatasetBundle(skills=[{'id': 'DEMO_SKILL', 'name': 'Demo', 'kind': 'hard'}]))


@pytest.mark.parametrize(('field', 'value'), [('version', '2.0'), ('dataset', 'Other dataset'), ('as_of_date', '2027-10-01')])
def test_unsupported_kit_metadata_is_explicitly_rejected(database, field, value):
    files = synthetic_files()
    document = json.loads(files['skills.json'])
    document['meta'][field] = value
    files['skills.json'] = json_bytes(document)
    with pytest.raises(ImportValidationError) as caught:
        import_kit(database, files)
    assert caught.value.source == 'skills.json' and caught.value.path == f'$.meta.{field}'


def test_score_zero_is_still_invalid_on_workshops(database):
    files = synthetic_files()
    rows = history_rows(files)
    rows[0]['score'] = '0'
    files['activity_history.csv'] = history_bytes(rows)
    with pytest.raises(ImportValidationError, match='Scores are only allowed'):
        import_kit(database, files)


@pytest.mark.parametrize(('field', 'value'), [('gain', -1), ('gain', True), ('gain', '1'), ('max_level', 6)])
def test_event_effect_validation_locates_official_json_field(database, field, value):
    files = synthetic_files()
    events = json.loads(files['events.json'])
    events['events'][0]['develops_skills'][0][field] = value
    files['events.json'] = json_bytes(events)
    with pytest.raises(ImportValidationError) as caught:
        import_kit(database, files)
    assert caught.value.source == 'events.json'
    assert caught.value.path == f'$.events[0].develops_skills[0].{field}'
