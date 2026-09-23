import asyncio
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.ai import providers
from app.config import ROOT, Settings
from app.domain.progression import gain_for
from app.main import create_app

HEADERS = {'X-Requested-With': 'CareerQuest'}


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f'sqlite:///{tmp_path / "test.db"}', provider='rules', demo_mode=True, cookie_secure=False)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), headers=HEADERS) as test_client:
        yield test_client


def login(client, account='E001'):
    response = client.post('/api/v1/auth/demo', json={'account': account})
    assert response.status_code == 200


def recommendation(client, employee='E001'):
    return client.post(f'/api/v1/employees/{employee}/recommendations')


@pytest.mark.parametrize(('level', 'gain', 'maximum', 'expected'), [(2, 1, 4, 1), (4, 3, 4, 0), (5, 1, 3, 0), (3, 3, 5, 2)])
def test_gain_caps_and_never_decreases(level, gain, maximum, expected):
    assert gain_for(level, gain, maximum) == expected


def test_auth_and_role_boundaries(client):
    assert client.get('/api/v1/employees/E001').status_code == 401
    login(client)
    assert client.get('/api/v1/employees/E002').status_code == 403
    assert client.get('/api/v1/hr/overview').status_code == 403
    assert client.post('/api/v1/imports', json={}).status_code == 403
    login(client, 'hr')
    assert client.get('/api/v1/employees/E002').status_code == 200
    assert client.post('/api/v1/employees/E001/events/EV_DESIGN/complete').status_code == 403


def test_csrf_and_origin(client):
    assert client.post('/api/v1/auth/demo', json={'account': 'hr'}, headers={'X-Requested-With': ''}).status_code == 403
    assert client.post('/api/v1/auth/demo', json={'account': 'hr'}, headers={'Origin': 'https://untrusted.example'}).status_code == 403


def test_demo_auth_disabled(settings):
    settings.demo_mode = False
    with TestClient(create_app(settings), headers=HEADERS) as client:
        assert client.get('/api/v1/auth/demo-accounts').json()['enabled'] is False
        assert client.post('/api/v1/auth/demo', json={'account': 'hr'}).status_code == 403


def test_recommendations_consider_next_grade_and_history(client):
    login(client)
    result = recommendation(client).json()
    assert result['mode'] == 'rules'
    assert 1 <= len(result['items']) <= 3
    assert result['items'][0]['id'] in {'EV_DESIGN', 'EV_MENTOR'}
    assert result['items'][0]['id'] != 'EV_SPEAK'
    assert {e['factor'] for e in result['items'][0]['evidence']} == {'grade', 'skill_gap', 'next_level', 'history'}
    assert recommendation(client).json()['cached'] is True
    assert client.get('/api/v1/employees/E001').json()['recommendation']['cached'] is True


def test_complete_persists_is_idempotent_and_invalidates_cache(client):
    login(client)
    recommendation(client)
    before = client.get('/api/v1/employees/E001').json()['trajectory']['coverage']
    first = client.post('/api/v1/employees/E001/events/EV_DESIGN/complete').json()
    assert first['profile']['employee']['skills']['SK_SYSTEM_DESIGN'] == 3
    assert first['profile']['trajectory']['coverage'] > before
    assert not first['already_completed']
    assert client.post('/api/v1/employees/E001/events/EV_DESIGN/complete').json()['already_completed']
    reloaded = client.get('/api/v1/employees/E001').json()
    assert reloaded['employee']['skills']['SK_SYSTEM_DESIGN'] == 3
    assert reloaded['recommendation'] is None
    assert len([h for h in reloaded['history'] if h['status'] == 'completed']) == 1
    next_result = recommendation(client).json()
    assert next_result['cached'] is False
    assert 'EV_DESIGN' not in {r['id'] for r in next_result['items']}


def test_concurrent_completion_only_awards_once(client):
    login(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post('/api/v1/employees/E001/events/EV_DESIGN/complete'), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert sum(not r.json()['already_completed'] for r in responses) == 1
    assert client.get('/api/v1/employees/E001').json()['employee']['skills']['SK_SYSTEM_DESIGN'] == 3


def test_invalid_completion_does_not_change_profile(client):
    login(client)
    before = client.get('/api/v1/employees/E001').json()['employee']
    assert client.post('/api/v1/employees/E001/events/EV_SQL/complete').status_code == 422
    assert client.get('/api/v1/employees/E001').json()['employee'] == before


def test_import_dry_run_atomicity_and_repeat(client):
    login(client, 'hr')
    bundle = json.loads((ROOT / 'examples/additional-profile.json').read_text(encoding='utf-8'))
    assert client.post('/api/v1/imports?dry_run=true', json=bundle).json()['employees_added'] == 1
    assert client.get('/api/v1/employees/E004').status_code == 404
    broken = copy.deepcopy(bundle)
    broken['history'][0]['event_id'] = 'DOES_NOT_EXIST'
    assert client.post('/api/v1/imports', json=broken).status_code == 422
    assert client.get('/api/v1/employees/E004').status_code == 404
    assert client.post('/api/v1/imports', json=bundle).json()['employees_added'] == 1
    assert client.post('/api/v1/imports', json=bundle).json()['history_added'] == 0
    assert client.get('/api/v1/employees/E004').json()['employee']['skills']['SK_SYSTEM_DESIGN'] == 2
    assert recommendation(client, 'E004').status_code == 200


@pytest.mark.parametrize('bad_level', [-1, 6, True, '3'])
def test_import_rejects_bad_levels(client, bad_level):
    login(client, 'hr')
    bundle = json.loads((ROOT / 'examples/additional-profile.json').read_text(encoding='utf-8'))
    bundle['employees'][0]['skills']['SK_PYTHON'] = bad_level
    assert client.post('/api/v1/imports', json=bundle).status_code == 422


def test_unknown_skill_is_not_zero(client):
    login(client, 'hr')
    bundle = json.loads((ROOT / 'examples/additional-profile.json').read_text(encoding='utf-8'))
    del bundle['employees'][0]['skills']['SK_SYSTEM_DESIGN']
    assert client.post('/api/v1/imports', json=bundle).status_code == 200
    profile = client.get('/api/v1/employees/E004').json()
    assert profile['trajectory']['coverage'] is None
    assert recommendation(client, 'E004').json()['items'] == []


def test_no_grade_rule_and_hr_counts(client):
    login(client, 'hr')
    assert recommendation(client, 'E003').json()['mode'] == 'no_candidates'
    overview = client.get('/api/v1/hr/overview').json()
    assert overview['employee_count'] == 3
    assert any(x['id'] == 'E003' for x in overview['no_step'])
    speaking = next(e for e in overview['participation'] if e['id'] == 'EV_SPEAK')
    assert speaking['missed'] == 2 and speaking['declined'] == 1


def test_provider_failure_is_honest_fallback(client, settings, monkeypatch):
    settings.provider = 'openai'
    settings.cloud_data_approved = True
    async def fail(*args):
        raise TimeoutError('sensitive provider information')
    monkeypatch.setattr(providers, 'select_events', fail)
    login(client)
    result = recommendation(client).json()
    assert result['mode'] == 'fallback'
    assert result['provider'] is None
    assert 'sensitive' not in json.dumps(result)
    assert result['items']


def test_daily_ai_cap(client, settings):
    settings.provider, settings.per_day = 'openai', 0
    settings.cloud_data_approved = True
    login(client)
    assert recommendation(client).status_code == 429


@pytest.mark.parametrize(('content', 'valid'), [('{"event_ids":["EV_DESIGN"]}', True), ('{"event_ids":["invented"]}', False), ('{"event_ids":["EV_DESIGN","EV_DESIGN"]}', False), ('not json', False)])
def test_provider_validates_model_output(settings, monkeypatch, content, valid):
    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=self)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def create(self, **kwargs):
            assert kwargs['response_format']['json_schema']['strict']
            assert kwargs['store'] is False
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=content))])
    monkeypatch.setattr(providers, 'AsyncOpenAI', FakeClient)
    settings.provider, settings.openai_key = 'openai', 'unit-test-placeholder'
    operation = providers.select_events(settings, {'candidates': [{'id': 'EV_DESIGN'}]})
    if valid:
        assert asyncio.run(operation)[0] == ['EV_DESIGN']
    else:
        with pytest.raises(ValueError):
            asyncio.run(operation)


def test_logout_revokes_session(client):
    login(client)
    token = client.cookies.get('cq_session')
    assert client.post('/api/v1/auth/logout').status_code == 200
    client.cookies.set('cq_session', token)
    assert client.get('/api/v1/auth/me').status_code == 401


def test_nvidia_uses_compatible_endpoint_without_openai_only_options(settings, monkeypatch):
    class NvidiaClient:
        def __init__(self, **kwargs):
            assert kwargs['base_url'] == 'https://integrate.api.nvidia.com/v1'
            self.chat = SimpleNamespace(completions=self)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def create(self, **kwargs):
            assert kwargs['model'] == settings.nvidia_model
            assert 'response_format' not in kwargs and 'store' not in kwargs
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='{"event_ids":["EV_DESIGN"]}'))])
    monkeypatch.setattr(providers, 'AsyncOpenAI', NvidiaClient)
    settings.provider, settings.nvidia_key = 'nvidia', 'unit-test-placeholder'
    assert asyncio.run(providers.select_events(settings, {'candidates': [{'id': 'EV_DESIGN'}]}))[0] == ['EV_DESIGN']
