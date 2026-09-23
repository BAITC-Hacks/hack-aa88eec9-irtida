import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from app.config import ROOT, Settings
from app.db import Activity, Catalog, Employee, connect
from app.ingest import ImportValidationError, import_bundle
from app.main import create_app
from app.schemas import DatasetBundle


def fixture_data(name='demo'):
    return json.loads((ROOT / 'examples' / f'{name}.json').read_text(encoding='utf-8'))


@pytest.fixture
def database(tmp_path):
    engine, sessions = connect(f'sqlite:///{tmp_path / "imports.db"}')
    with sessions() as db:
        yield db
    engine.dispose()


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_url=f'sqlite:///{tmp_path / "api.db"}', provider='rules', demo_mode=True, cookie_secure=False)
    with TestClient(create_app(settings), headers={'X-Requested-With': 'CareerQuest'}) as api:
        assert api.post('/api/v1/auth/demo', json={'account': 'hr'}).status_code == 200
        yield api


def counts(db):
    return {table.__tablename__: db.scalar(select(func.count()).select_from(table)) for table in (Employee, Activity, Catalog)}


def test_full_demo_dry_run_then_commit_and_repeat(database):
    bundle = DatasetBundle.model_validate(fixture_data())
    preview = import_bundle(database, bundle, dry_run=True)
    assert preview == {'employees_added': 3, 'history_added': 3, 'dry_run': True, 'schema': 'demo-v1'}
    assert counts(database) == {'employees': 0, 'activity_history': 0, 'catalog': 0}
    assert not database.new and not database.dirty
    assert import_bundle(database, bundle)['employees_added'] == 3
    assert import_bundle(database, bundle)['history_added'] == 0
    assert counts(database) == {'employees': 3, 'activity_history': 3, 'catalog': 1}
    assert database.get(Catalog, 1).payload == {key: fixture_data()[key] for key in ('skills', 'events', 'grade_rules')}


def test_additional_completed_history_does_not_replay_snapshot_gains(database):
    import_bundle(database, DatasetBundle.model_validate(fixture_data()))
    extra = fixture_data('additional-profile')
    extra['history'][0]['status'] = 'completed'
    extra['history'].append({**extra['history'][0], 'id': 'H005', 'occurred_at': '2026-08-21'})
    bundle = DatasetBundle.model_validate(extra)
    assert import_bundle(database, bundle) == {'employees_added': 1, 'history_added': 2, 'dry_run': False, 'schema': 'demo-v1'}
    assert database.get(Employee, 'E004').profile['skills'] == extra['employees'][0]['skills']
    assert import_bundle(database, bundle)['history_added'] == 0
    assert counts(database)['activity_history'] == 5


def test_history_only_bundle_accepts_distinct_occurrences(database):
    import_bundle(database, DatasetBundle.model_validate(fixture_data()))
    history = [dict(id=f'BACKEND_{index}', employee_id='E001', event_id='EV_SPEAK', status='completed', occurred_at='2026-08-21') for index in range(1001)]
    bundle = DatasetBundle(history=history)
    assert import_bundle(database, bundle)['history_added'] == 1001
    assert import_bundle(database, bundle)['history_added'] == 0
    assert database.get(Employee, 'E001').profile['skills']['SK_PUBLIC_SPEAKING'] == 1


def test_exact_duplicate_records_in_every_collection_are_idempotent(database):
    data = fixture_data()
    for key in ('employees', 'skills', 'events', 'grade_rules', 'history'):
        data[key].append(copy.deepcopy(data[key][0]))
    result = import_bundle(database, DatasetBundle.model_validate(data))
    assert result['employees_added'] == 3 and result['history_added'] == 3
    assert {key: len(value) for key, value in database.get(Catalog, 1).payload.items()} == {'skills': 5, 'events': 5, 'grade_rules': 2}


@pytest.mark.parametrize(('collection', 'field', 'changed'), [
    ('employees', 'name', 'Changed'), ('skills', 'name', 'Changed'),
    ('events', 'title', 'Changed'), ('grade_rules', 'next_grade', 'Changed'),
    ('history', 'status', 'completed'),
])
def test_conflicting_duplicate_in_bundle_has_original_path_and_no_writes(database, collection, field, changed):
    data = fixture_data()
    index = len(data[collection])
    data[collection].append({**data[collection][0], field: changed})
    with pytest.raises(ImportValidationError) as caught:
        import_bundle(database, DatasetBundle.model_validate(data))
    assert caught.value.path == f'$.{collection}[{index}]'
    assert f'$.{collection}[0]' in caught.value.reason
    assert counts(database) == {'employees': 0, 'activity_history': 0, 'catalog': 0}


@pytest.mark.parametrize(('collection', 'field', 'changed'), [
    ('employees', 'name', 'Changed'), ('skills', 'name', 'Changed'),
    ('events', 'title', 'Changed'), ('grade_rules', 'next_grade', 'Changed'),
    ('history', 'status', 'completed'),
])
def test_existing_conflicts_do_not_change_catalog_profiles_or_history(database, collection, field, changed):
    original = fixture_data()
    import_bundle(database, DatasetBundle.model_validate(original))
    extra = fixture_data('additional-profile')
    extra.setdefault(collection, []).insert(0, {**original[collection][0], field: changed})
    with pytest.raises(ImportValidationError) as caught:
        import_bundle(database, DatasetBundle.model_validate(extra))
    assert caught.value.path == f'$.{collection}[0]'
    assert counts(database) == {'employees': 3, 'activity_history': 3, 'catalog': 1}
    assert database.get(Employee, 'E004') is None
    assert database.get(Employee, 'E001').profile == original['employees'][0]
    assert database.get(Activity, 'H001').status == 'missed'
    assert database.get(Catalog, 1).payload == {key: original[key] for key in ('skills', 'events', 'grade_rules')}


@pytest.mark.parametrize(('collection', 'field', 'value', 'path'), [
    ('employees', 'skills', {'UNKNOWN': 1}, '$.employees[0].skills.UNKNOWN'),
    ('events', 'effects', {'UNKNOWN': {'gain': 1, 'max_level': 4}}, '$.events[0].effects.UNKNOWN'),
    ('grade_rules', 'requirements', {'UNKNOWN': 4}, '$.grade_rules[0].requirements.UNKNOWN'),
    ('history', 'employee_id', 'UNKNOWN', '$.history[0].employee_id'),
    ('history', 'event_id', 'UNKNOWN', '$.history[0].event_id'),
])
@pytest.mark.parametrize('dry_run', [False, True])
def test_unknown_references_are_atomic_and_source_located(database, collection, field, value, path, dry_run):
    data = fixture_data()
    data[collection][0][field] = value
    with pytest.raises(ImportValidationError) as caught:
        import_bundle(database, DatasetBundle.model_validate(data), dry_run=dry_run)
    assert caught.value.as_dict() == {'source': 'body', 'path': path, 'reason': caught.value.reason}
    assert path in str(caught.value)
    assert counts(database) == {'employees': 0, 'activity_history': 0, 'catalog': 0}


@pytest.mark.parametrize(('field', 'value'), [
    ('gain', -1), ('gain', 6), ('gain', True), ('gain', '1'),
    ('max_level', -1), ('max_level', 6), ('max_level', True), ('max_level', '4'),
])
def test_invalid_effect_bounds_and_types_report_field(field, value):
    data = fixture_data()
    data['events'][0]['effects']['SK_SYSTEM_DESIGN'][field] = value
    with pytest.raises(ValidationError) as caught:
        DatasetBundle.model_validate(data)
    assert caught.value.errors()[0]['loc'] == ('events', 0, 'effects', 'SK_SYSTEM_DESIGN', field)


@pytest.mark.parametrize('value', ['2026-02-30', '20260923', '2026-09-23T00:00:00', '2026-09-23T12:30:00Z', 0, True, 'not-a-date'])
def test_dates_require_canonical_valid_calendar_date(value):
    data = fixture_data()
    data['history'][0]['occurred_at'] = value
    with pytest.raises(ValidationError) as caught:
        DatasetBundle.model_validate(data)
    assert caught.value.errors()[0]['loc'] == ('history', 0, 'occurred_at')


def test_leap_date_and_effect_boundary_values_are_supported(database):
    data = fixture_data()
    data['history'][0]['occurred_at'] = '2024-02-29'
    data['events'][0]['effects']['SK_SYSTEM_DESIGN'] = {'gain': 0, 'max_level': 0}
    data['events'][1]['effects']['SK_SYSTEM_DESIGN'] = {'gain': 5, 'max_level': 5}
    import_bundle(database, DatasetBundle.model_validate(data))
    assert database.get(Activity, 'H001').occurred_at == '2024-02-29'


@pytest.mark.parametrize(('field', 'value'), [('roles', ['']), ('roles', ['   ']), ('roles', [12]), ('grades', [' ']), ('grades', ['Middle', 'Middle'])])
def test_invalid_audience_labels_are_rejected(field, value):
    data = fixture_data()
    data['events'][0][field] = value
    with pytest.raises(ValidationError) as caught:
        DatasetBundle.model_validate(data)
    assert caught.value.errors()[0]['loc'][:3] == ('events', 0, field)


def test_unknown_history_status_is_rejected():
    data = fixture_data()
    data['history'][0]['status'] = 'pending'
    with pytest.raises(ValidationError) as caught:
        DatasetBundle.model_validate(data)
    assert caught.value.errors()[0]['loc'] == ('history', 0, 'status')


def test_concurrent_api_imports_append_only_once(client):
    data = fixture_data('additional-profile')
    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(lambda _: client.post('/api/v1/imports', json=data), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert sorted(response.json()['employees_added'] for response in responses) == [0, 1]
    assert sorted(response.json()['history_added'] for response in responses) == [0, 1]
    profile = client.get('/api/v1/employees/E004').json()
    assert len(profile['history']) == 1


def test_api_error_contains_source_path_and_does_not_partially_import(client):
    data = fixture_data('additional-profile')
    data['history'][0]['event_id'] = 'UNKNOWN'
    response = client.post('/api/v1/imports', json=data)
    assert response.status_code == 422
    assert '$.history[0].event_id' in response.json()['detail']
    assert client.get('/api/v1/employees/E004').status_code == 404
