import copy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from app import auth
from app.config import Settings
from app.db import Employee, Recommendation
from app.localization import LocalizationMiddleware, localize, requested_locale
from app.main import create_app


def test_translations_preserve_ids_canonical_roles_numeric_progress_and_input():
    source = {'employee': {'id': 'K1', 'role': 'Sales Manager', 'skills': {'SK_PYTHON': 3}},
              'skill_catalog': [{'id': 'SK_DESIGN', 'name': 'System Design', 'level': 2}],
              'available': [{'id': 'EV_036', 'title': 'Public Speaking Club', 'projected_coverage': 47}],
              'trajectory': {'coverage': 42}}
    before = copy.deepcopy(source)
    for locale, name in [('ru', 'Проектирование систем'), ('en', 'System Design'), ('kk', 'Жүйелерді жобалау')]:
        result = localize(source, locale)
        assert result['skill_catalog'][0]['name'] == name
        assert result['skill_catalog'][0]['id'] == 'SK_DESIGN'
        assert result['employee']['role'] == 'Sales Manager'
        assert result['employee']['skills'] == {'SK_PYTHON': 3}
        assert result['trajectory']['coverage'] == 42
        assert result['available'][0]['projected_coverage'] == 47
    assert source == before


def test_evidence_is_translated_from_facts_not_guessed_from_prose():
    source = {'factor': 'next_level', 'text': 'old cache text',
              'facts': {'benefit': 3, 'critical': 2, 'next_grade': 'Senior', 'official': True}}
    assert '3 skill-gap' in localize(source, 'en')['text']
    assert '3 деңгейге' in localize(source, 'kk')['text']
    assert '3 ур.' in localize(source, 'ru')['text']


def test_locale_fallback_and_browser_tags():
    assert requested_locale([]) is None
    assert requested_locale([(b'accept-language', b'kk-KZ,ru;q=0.9')]) == 'kk'
    assert requested_locale([(b'accept-language', b'fr,en-US;q=0.8')]) == 'en'
    assert requested_locale([(b'accept-language', b'fr')]) is None
    assert requested_locale([(b'accept-language', b'en;q=0,kk;q=0.5,ru;q=0.9')]) == 'ru'
    assert requested_locale([(b'accept-language', b'en;q=nan,kk;q=invalid,ru;q=0')]) is None


def test_employee_names_are_never_translated_by_catalog_label_matching():
    source = {'employee': {'id': 'SK_LEADERSHIP', 'name': 'Leadership', 'role': 'Sales Manager'},
              'no_step': [{'id': 'E1', 'name': 'System Design', 'reason': 'highest_grade'}],
              'accounts': [{'display_name': 'Leadership', 'username': 'Leadership'}],
              'skill_catalog': [{'id': 'any-id', 'name': 'Leadership', 'level': 3}],
              'available': [{'id': 'EV_ANY', 'title': 'Leadership Foundations',
                             'changes': {'any-id': {'name': 'Leadership', 'before': 2, 'after': 3, 'gain': 1}}}]}
    for locale in ('ru', 'en', 'kk'):
        result = localize(source, locale)
        assert result['employee']['name'] == 'Leadership'
        assert result['no_step'][0]['name'] == 'System Design'
        assert result['accounts'] == source['accounts']
        assert result['employee']['id'] == 'SK_LEADERSHIP'
    assert localize(source, 'kk')['skill_catalog'][0]['name'] == 'Көшбасшылық'
    assert localize(source, 'ru')['available'][0]['changes']['any-id']['name'] == 'Лидерство'


@pytest.mark.parametrize(('detail', 'expected'), [
    ('Каталог активностей пуст.', 'catalog is empty'),
    ('Все известные требования следующего грейда по навыкам уже выполнены.', 'already met'),
    ('В правиле следующего грейда нет положительных требований; прогресс не вычисляется.', 'no positive targets'),
])
def test_specific_no_step_causes_take_precedence_over_generic_blockers(detail, expected):
    source = {'reason': 'no_eligible_activity', 'reason_detail': detail, 'blockers': {'completed': 2}}
    assert expected in localize(source, 'en')['reason_detail']
    assert localize(source, 'kk')['reason_detail'] != detail
    assert localize(source, 'ru')['reason_detail'] == detail


def test_no_step_preserves_blocker_counts_and_unknown_skill_names():
    source = {'reason': 'no_eligible_activity', 'reason_detail': 'Нет доступной активности',
              'blockers': {'mandatory': 4, 'prerequisites': 3, 'no_upcoming_session': 2}}
    result = localize(source, 'en')
    assert result['blockers'] == source['blockers']
    assert 'mandatory HR assignments are excluded — 4' in result['reason_detail']
    assert 'prerequisites are not met — 3' in result['reason_detail']
    assert 'no available upcoming session — 2' in result['reason_detail']
    missing = {'reason': 'missing_skills', 'reason_detail': 'Неизвестны уровни навыков: System Design, External skill. Доступного шага по известным разрывам нет.', 'blockers': {}}
    result = localize(missing, 'kk')['reason_detail']
    assert 'Жүйелерді жобалау, External skill' in result


def test_evidence_history_labels_are_localized_without_changing_fact_tokens():
    source = {'factor': 'history', 'text': 'Original', 'facts': {'type': 'workshop', 'format': 'offline',
              'counts': {'completed': 2, 'no_show': 1}, 'official': True, 'skipped': 1}}
    expected = {'ru': 'Практикум / Очно', 'en': 'Workshop / In person', 'kk': 'Практикум / Офлайн'}
    for locale, prefix in expected.items():
        result = localize(source, locale)
        assert result['text'].startswith(prefix)
        assert result['facts'] == source['facts']


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CAREER_QUEST_AUTO_IMPORT', 'false')
    settings = Settings(database_url=f'sqlite:///{tmp_path / "locale.db"}', provider='rules', demo_mode=True, cookie_secure=False)
    with TestClient(create_app(settings), headers={'X-Requested-With': 'CareerQuest'}) as api:
        yield api


def test_actual_http_locales_keep_cache_canonical_and_progress_unchanged(client):
    with client.app.state.sessions() as db:
        employee = db.get(Employee, 'E001')
        employee.profile = {**employee.profile, 'name': 'Leadership'}
        db.commit()
    assert client.post('/api/v1/auth/demo', json={'account': 'E001'}).status_code == 200
    first = client.post('/api/v1/employees/E001/recommendations').json()
    canonical = client.get('/api/v1/employees/E001').json()
    with client.app.state.sessions() as db:
        cached = copy.deepcopy(db.scalar(select(Recommendation)).payload)
    for locale in ('en', 'kk', 'ru'):
        response = client.get('/api/v1/employees/E001', headers={'Accept-Language': locale})
        assert response.status_code == 200
        assert response.headers['content-language'] == locale
        assert 'accept-language' in response.headers['vary'].lower()
        assert int(response.headers['content-length']) == len(response.content)
        profile = response.json()
        assert profile['employee']['name'] == 'Leadership'
        assert profile['employee']['id'] == canonical['employee']['id']
        assert profile['employee']['skills'] == canonical['employee']['skills']
        assert profile['trajectory']['coverage'] == canonical['trajectory']['coverage']
        for actual, original in zip(profile['trajectory']['skills'], canonical['trajectory']['skills']):
            assert {key: actual[key] for key in ('id', 'level', 'required', 'gap', 'critical')} == {key: original[key] for key in ('id', 'level', 'required', 'gap', 'critical')}
        recommendation = client.post('/api/v1/employees/E001/recommendations', headers={'Accept-Language': locale}).json()
        assert recommendation['cached'] is True
        assert [event['id'] for event in recommendation['items']] == [event['id'] for event in first['items']]
        with client.app.state.sessions() as db:
            assert db.scalar(select(Recommendation)).payload == cached
    assert client.get('/api/v1/employees/E001').json() == canonical


def test_actual_auth_and_csrf_errors_translate_without_echoing_input_or_bypassing_permissions(client, monkeypatch):
    monkeypatch.setattr(auth, 'verify_password', lambda password, stored: False)
    credentials = {'username': 'private-user', 'password': 'private-synthetic-password', 'role': 'hr'}
    for locale, expected in [('en', 'Invalid username, password or role'), ('kk', 'Пайдаланушы аты, құпиясөз немесе рөл қате'), ('ru', 'Неверные имя пользователя, пароль или роль')]:
        response = client.post('/api/v1/auth/login', json=credentials, headers={'Accept-Language': locale})
        assert response.status_code == 401
        assert response.json() == {'detail': expected}
        assert credentials['password'] not in response.text
        assert credentials['username'] not in response.text
        assert not response.cookies
    denied = client.post('/api/v1/auth/demo', json={'account': 'hr'}, headers={'Accept-Language': 'en', 'X-Requested-With': ''})
    assert denied.status_code == 403 and 'header is required' in denied.json()['detail']
    origin = client.post('/api/v1/auth/demo', json={'account': 'hr'}, headers={'Accept-Language': 'kk', 'Origin': 'https://untrusted.example'})
    assert origin.status_code == 403 and 'рұқсат' in origin.json()['detail']
    assert client.post('/api/v1/auth/demo', json={'account': 'E001'}).status_code == 200
    for path in ('/api/v1/hr/overview', '/api/v1/hr/accounts', '/api/v1/employees/E002'):
        response = client.get(path, headers={'Accept-Language': 'en'})
        assert response.status_code == 403
        assert set(response.json()) == {'detail'}
        assert 'E002' not in response.text


def test_validation_errors_translate_but_keep_field_paths_and_do_not_echo_secrets(client):
    response = client.post('/api/v1/auth/login', json={'username': 'private-user', 'password': 'pvt#5', 'role': 'employee'}, headers={'Accept-Language': 'kk'})
    assert response.status_code == 422
    issue = response.json()['detail'][0]
    assert issue['loc'] == ['body', 'password']
    assert issue['type'] == 'too_short'
    assert '12' in issue['msg'] and 'Ұзындығы' in issue['msg']
    assert 'pvt#5' not in response.text and 'private-user' not in response.text
    assert 'input' not in issue


def test_middleware_handles_json_shapes_chunking_headers_and_non_json_safely():
    async def shaped(request):
        payload = {'reason': {'unrecognized': True}, 'factor': 'history', 'text': 'Old text', 'facts': [1], 'events': [None, {'roles': 7}], 'skills': []}
        return JSONResponse(payload, headers={'Vary': 'Origin, accept-language'})

    async def invalid(request):
        return Response(b'not-json', media_type='application/json')

    async def html(request):
        return Response('<p>Unchanged</p>', media_type='text/html')

    async def streamed(request):
        async def chunks():
            yield b'{"skill_catalog":['
            yield b'{"id":"SK_LEAD","name":"Leadership","level":3}]}'
        return StreamingResponse(chunks(), media_type='application/json', headers={'Vary': 'Origin'})

    app = Starlette(routes=[Route('/api/v1/shaped', shaped), Route('/api/v1/invalid', invalid), Route('/api/v1/html', html), Route('/api/v1/streamed', streamed)])
    app.add_middleware(LocalizationMiddleware)
    with TestClient(app) as api:
        response = api.get('/api/v1/shaped', headers={'Accept-Language': 'en'})
        assert response.status_code == 200
        assert response.json()['reason'] == {'unrecognized': True}
        assert response.json()['text'] == 'Old text'
        assert response.headers['vary'].lower().split(', ') == ['origin', 'accept-language']
        assert api.get('/api/v1/invalid', headers={'Accept-Language': 'kk'}).content == b'not-json'
        response = api.get('/api/v1/html', headers={'Accept-Language': 'kk'})
        assert response.text == '<p>Unchanged</p>' and 'content-language' not in response.headers
        canonical = api.get('/api/v1/shaped')
        assert 'content-language' not in canonical.headers
        assert 'accept-language' in canonical.headers['vary'].lower()
        streamed_result = api.get('/api/v1/streamed', headers={'Accept-Language': 'kk'})
        assert streamed_result.json()['skill_catalog'][0] == {'id': 'SK_LEAD', 'name': 'Көшбасшылық', 'level': 3}
        assert int(streamed_result.headers['content-length']) == len(streamed_result.content)
        assert streamed_result.headers['vary'] == 'Origin, Accept-Language'
