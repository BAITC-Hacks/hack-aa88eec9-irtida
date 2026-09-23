import copy
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

HEADERS = {'X-Requested-With': 'CareerQuest'}


@pytest.fixture
def kit_files():
    # Deliberately synthetic fixtures; never load the private starter kit in CI.
    from test_kit_import import synthetic_files
    return synthetic_files()


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f'sqlite:///{tmp_path / "kit-api.db"}', provider='rules', demo_mode=True, cookie_secure=False)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), headers=HEADERS) as api:
        yield api


def login(client, account='hr'):
    assert client.post('/api/v1/auth/demo', json={'account': account}).status_code == 200


def upload(client, files, query=''):
    parts = [('files', (name, content, 'text/csv' if name.endswith('.csv') else 'application/json')) for name, content in files.items()]
    return client.post('/api/v1/imports/kit' + query, files=parts)


def initialize_kit(client, files):
    login(client)
    result = upload(client, files, '?replace_demo=true')
    assert result.status_code == 200, result.text
    assert result.json()['demo_replaced'] is True
    return result.json()


def profile(client, employee_id='K1'):
    response = client.get(f'/api/v1/employees/{employee_id}')
    assert response.status_code == 200
    return response.json()


def complete(client, occurrence=None):
    kwargs = {} if occurrence is None else {'json': {'occurrence_id': occurrence}}
    return client.post('/api/v1/employees/K1/events/EV_036/complete', **kwargs)


def test_kit_import_is_hr_only(client, kit_files):
    assert upload(client, kit_files).status_code == 401
    login(client, 'E001')
    assert upload(client, kit_files, '?replace_demo=true').status_code == 403
    assert client.get('/api/v1/employees/E001').status_code == 200


def test_demo_replacement_requires_explicit_request_and_dry_run_is_atomic(client, kit_files):
    login(client)
    before = client.get('/api/v1/employees').json()
    assert upload(client, kit_files).status_code == 422
    assert client.get('/api/v1/employees').json() == before
    preview = upload(client, kit_files, '?replace_demo=true&dry_run=true')
    assert preview.status_code == 200, preview.text
    assert preview.json()['dry_run'] is True and preview.json()['demo_replaced'] is False
    assert preview.json()['employees_added'] == 2
    assert client.get('/api/v1/employees').json() == before
    assert client.get('/api/v1/employees/K1').status_code == 404
    assert client.get('/api/v1/auth/me').json()['role'] == 'hr'


def test_bad_kit_replacement_rolls_back_deleted_demo_and_reports_file(client, kit_files):
    login(client)
    before = client.get('/api/v1/hr/overview').json()
    bad_files = dict(kit_files)
    employees = json.loads(bad_files['employees.json'])
    employees['employees'][0]['skills']['UNKNOWN_SKILL'] = 3
    bad_files['employees.json'] = json.dumps(employees).encode()
    failed = upload(client, bad_files, '?replace_demo=true')
    assert failed.status_code == 422
    result = failed.json()
    assert result['errors'][0]['source'] == 'employees.json'
    assert result['errors'][0]['path'] and result['errors'][0]['reason']
    assert client.get('/api/v1/hr/overview').json() == before
    assert client.get('/api/v1/employees/E001').status_code == 200
    assert client.get('/api/v1/employees/K1').status_code == 404


def test_raw_kit_import_and_repeat_preserve_contract_and_historical_gains(client, kit_files):
    result = initialize_kit(client, kit_files)
    assert result['employees_added'] == 2
    assert client.get('/api/v1/employees/E001').status_code == 404
    first = profile(client)
    assert {'employee', 'trajectory', 'history', 'available', 'recommendation'} <= first.keys()
    assert first['employee']['skills']['SK_DESIGN'] == 3
    assert first['employee']['skills']['SK_SPEAK'] == 1
    assert first['trajectory']['next_grade'] == 'Senior'
    repeated = upload(client, kit_files)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()['employees_added'] == repeated.json()['history_added'] == 0
    assert profile(client) == first
    assert client.get('/api/v1/hr/overview').json()['employee_count'] == 2


def test_conflicting_existing_profile_is_not_overwritten(client, kit_files):
    initialize_kit(client, kit_files)
    before = profile(client)
    employees = json.loads(kit_files['employees.json'])
    employees['employees'][0]['full_name'] = 'Synthetic conflicting display name'
    failed = upload(client, {'employees.json': json.dumps(employees).encode()})
    assert failed.status_code == 422
    assert failed.json()['errors'][0]['source'] == 'employees.json'
    assert profile(client) == before


def test_additional_profiles_and_history_import_without_catalog_reupload(client, kit_files):
    initialize_kit(client, kit_files)
    original = json.loads(kit_files['employees.json'])
    employee = copy.deepcopy(next(item for item in original['employees'] if item['employee_id'] == 'K1'))
    employee.update(employee_id='K_EXTRA', full_name='Synthetic additional employee')
    additional = {**original, 'employees': [employee]}
    rows = list(csv.DictReader(io.StringIO(kit_files['activity_history.csv'].decode('utf-8-sig'))))
    record = copy.deepcopy(next(row for row in rows if row['event_id'] == 'EV_036'))
    record.update(record_id='K_EXTRA_HISTORY', employee_id='K_EXTRA', date='2026-09-25')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(record))
    writer.writeheader()
    writer.writerow(record)
    files = {'employees.json': json.dumps(additional).encode(), 'activity_history.csv': stream.getvalue().encode()}
    preview = upload(client, files, '?dry_run=true')
    assert preview.status_code == 200, preview.text
    assert client.get('/api/v1/employees/K_EXTRA').status_code == 404
    applied = upload(client, files)
    assert applied.status_code == 200, applied.text
    assert applied.json()['employees_added'] == applied.json()['history_added'] == 1
    added = profile(client, 'K_EXTRA')
    assert added['employee']['skills']['SK_DESIGN'] == 1
    assert added['employee']['skills']['SK_SPEAK'] == 1
    assert upload(client, files).json()['history_added'] == 0
    assert profile(client, 'K_EXTRA') == added


def test_demo_with_user_progress_cannot_be_replaced(client, kit_files):
    login(client, 'E001')
    assert client.post('/api/v1/employees/E001/events/EV_DESIGN/complete').status_code == 200
    before = client.get('/api/v1/employees/E001').json()
    login(client)
    failed = upload(client, kit_files, '?replace_demo=true')
    assert failed.status_code == 422
    assert 'replace_demo' in failed.json()['detail']
    assert client.get('/api/v1/employees/E001').json() == before
    assert client.get('/api/v1/hr/overview').json()['employee_count'] == 3


def test_replacement_revokes_demo_employee_sessions_but_keeps_hr(settings, client, kit_files):
    login(client)
    with TestClient(create_app(settings), headers=HEADERS) as employee_client:
        login(employee_client, 'E001')
        assert employee_client.get('/api/v1/auth/me').status_code == 200
        replaced = upload(client, kit_files, '?replace_demo=true')
        assert replaced.status_code == 200, replaced.text
        assert employee_client.get('/api/v1/auth/me').status_code == 401
        assert client.get('/api/v1/auth/me').json()['role'] == 'hr'
        assert client.get('/api/v1/hr/overview').json()['employee_count'] == 2


def test_repeatable_completion_requires_current_occurrence_and_employee_role(client, kit_files):
    initialize_kit(client, kit_files)
    assert complete(client, '2026-10-05').status_code == 403
    login(client, 'K1')
    before = profile(client)
    for body in (None, {'occurrence_id': '2026-10-12'}, {'occurrence_id': '2026-10-99'}, {'occurrence_id': 42}, {'extra': True}):
        kwargs = {} if body is None else {'json': body}
        response = client.post('/api/v1/employees/K1/events/EV_036/complete', **kwargs)
        assert response.status_code == 422
    assert profile(client) == before


def test_repeatable_occurrences_award_once_each_and_match_expected_gain(client, kit_files):
    initialize_kit(client, kit_files)
    login(client, 'K1')
    initial = profile(client)
    expected = next(event for event in initial['available'] if event['id'] == 'EV_036')
    assert expected['occurrence_id'] == '2026-10-05'
    assert expected['changes']['SK_SPEAK']['before'] == 1
    assert expected['changes']['SK_SPEAK']['after'] == 2
    first_response = complete(client, expected['occurrence_id'])
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    assert first['already_completed'] is False
    assert first['profile']['employee']['skills']['SK_SPEAK'] == 2
    assert first['profile']['trajectory']['coverage'] == expected['projected_coverage']
    first_history = next(item for item in first['profile']['history'] if item['event_id'] == 'EV_036' and item['occurred_at'] == '2026-10-05')
    assert first_history['changes'] == expected['changes']
    retry = complete(client, '2026-10-05').json()
    assert retry['already_completed'] is True and retry['profile']['employee']['skills']['SK_SPEAK'] == 2
    second_expected = next(event for event in first['profile']['available'] if event['id'] == 'EV_036')
    assert second_expected['occurrence_id'] == '2026-10-12'
    second_response = complete(client, second_expected['occurrence_id'])
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assert second['already_completed'] is False
    assert second['profile']['employee']['skills']['SK_SPEAK'] == 3
    assert second['profile']['trajectory']['coverage'] == second_expected['projected_coverage']
    assert complete(client, '2026-10-12').json()['already_completed'] is True
    assert complete(client, '2026-10-05').json()['already_completed'] is True
    assert len([item for item in profile(client)['history'] if item['event_id'] == 'EV_036' and item['status'] == 'completed']) == 3
    login(client)
    assert upload(client, kit_files).status_code == 200
    assert profile(client)['employee']['skills']['SK_SPEAK'] == 3


def test_same_occurrence_concurrent_requests_do_not_double_award(client, kit_files):
    initialize_kit(client, kit_files)
    login(client, 'K1')
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: complete(client, '2026-10-05'), range(2)))
    assert all(response.status_code == 200 for response in responses)
    assert sum(not response.json()['already_completed'] for response in responses) == 1
    current = profile(client)
    assert current['employee']['skills']['SK_SPEAK'] == 2
    assert sum(item['event_id'] == 'EV_036' and item['occurred_at'] == '2026-10-05' for item in current['history']) == 1


def test_completed_nonrepeatable_kit_event_keeps_no_body_contract(client, kit_files):
    initialize_kit(client, kit_files)
    login(client, 'K1')
    before = profile(client)
    response = client.post('/api/v1/employees/K1/events/EV_DESIGN/complete')
    assert response.status_code == 200
    assert response.json()['already_completed'] is True
    assert response.json()['profile']['employee'] == before['employee']
    assert response.json()['profile']['history'] == before['history']


def test_upload_rejects_unrecognized_duplicate_and_nonmultipart_inputs(client, kit_files):
    login(client)
    assert client.post('/api/v1/imports/kit', json={}).status_code == 415
    assert upload(client, {'unknown.json': b'{}'}).status_code == 422
    payload = kit_files['employees.json']
    duplicate = client.post('/api/v1/imports/kit', files=[
        ('files', ('employees.json', payload, 'application/json')),
        ('files', ('employees.json', payload, 'application/json')),
    ])
    assert duplicate.status_code == 422
    assert upload(client, {'employees.json': payload}, '?replace_demo=true').status_code == 422
    assert client.get('/api/v1/hr/overview').json()['employee_count'] == 3
