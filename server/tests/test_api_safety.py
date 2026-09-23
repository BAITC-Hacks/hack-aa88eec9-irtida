import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ai import providers
from app.config import Settings
from app.db import AIRequest, Recommendation
from app.main import create_app
from app.middleware import BodyLimitMiddleware

HEADERS = {'X-Requested-With': 'CareerQuest'}


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url=f'sqlite:///{tmp_path / "api-safety.db"}',
        provider='openai', openai_key='unit-test-placeholder',
        cloud_data_approved=True, demo_mode=True, cookie_secure=False, timeout=0.5,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), headers=HEADERS) as test_client:
        yield test_client


def login(client, account='E001'):
    assert client.post('/api/v1/auth/demo', json={'account': account}).status_code == 200


def recommend(client, employee_id='E001'):
    return client.post(f'/api/v1/employees/{employee_id}/recommendations')


def ai_request_count(client):
    with client.app.state.sessions() as db:
        return db.scalar(select(func.count()).select_from(AIRequest).where(AIRequest.provider != 'login'))


def test_unapproved_cloud_data_uses_fallback_without_call_or_quota(client, settings, monkeypatch):
    settings.cloud_data_approved = False
    settings.per_day = settings.per_minute = 0
    async def forbidden(*args):
        pytest.fail('Unapproved data must never reach a cloud provider')
    monkeypatch.setattr(providers, 'select_events', forbidden)
    login(client)
    response = recommend(client)
    assert response.status_code == 200
    result = response.json()
    assert result['mode'] == 'fallback' and result['reason']
    assert result['provider'] is None and result['model'] is None
    assert result['cached'] is False and result['items']
    assert ai_request_count(client) == 0
    assert recommend(client).json()['cached'] is True
    assert ai_request_count(client) == 0


def test_ai_selects_ids_but_response_numbers_and_evidence_come_from_server(client, monkeypatch):
    calls = []
    async def select_design(settings, context):
        calls.append(context)
        assert 'name' not in context['profile'] and 'id' not in context['profile']
        return ['EV_DESIGN'], 'mock-gpt-4.1-mini'
    monkeypatch.setattr(providers, 'select_events', select_design)
    login(client)
    before = client.get('/api/v1/employees/E001').json()
    response = recommend(client)
    assert response.status_code == 200
    result = response.json()
    assert result['mode'] == 'ai' and result['provider'] == 'openai'
    assert result['model'] == 'mock-gpt-4.1-mini' and result['reason'] is None
    assert result['cached'] is False and len(calls) == 1
    assert [item['id'] for item in result['items']] == ['EV_DESIGN']
    item = result['items'][0]
    assert item['changes']['SK_SYSTEM_DESIGN'] == {
        'name': 'System Design', 'before': 2, 'after': 3, 'gain': 1,
    }
    expected = next(event for event in before['available'] if event['id'] == 'EV_DESIGN')
    assert item['evidence'] == expected['evidence']
    assert {row['factor'] for row in item['evidence']} == {'grade', 'skill_gap', 'next_level', 'history'}
    after = client.get('/api/v1/employees/E001').json()
    assert after['employee'] == before['employee']
    assert after['trajectory']['coverage'] == before['trajectory']['coverage'] == 55
    assert after['recommendation']['cached'] is True
    assert recommend(client).json()['cached'] is True
    assert len(calls) == ai_request_count(client) == 1


@pytest.mark.parametrize('bad_ids', [['invented'], ['EV_DESIGN', 'EV_DESIGN'], [], ['EV_SQL']])
def test_api_revalidates_provider_ids_and_falls_back(client, monkeypatch, bad_ids):
    async def invalid_selection(*args):
        return bad_ids, 'untrusted-model-result'
    monkeypatch.setattr(providers, 'select_events', invalid_selection)
    login(client)
    before = client.get('/api/v1/employees/E001').json()
    response = recommend(client)
    assert response.status_code == 200
    result = response.json()
    assert result['mode'] == 'fallback' and result['reason']
    assert result['provider'] is None and result['model'] is None
    assert [item['id'] for item in result['items']] == [item['id'] for item in before['available'][:3]]
    assert len({item['id'] for item in result['items']}) == len(result['items'])
    assert ai_request_count(client) == 1


def test_api_deadline_cancels_slow_adapter_and_caches_honest_fallback(client, settings, monkeypatch):
    settings.timeout = 0.05
    calls = []
    cancelled = threading.Event()
    async def slow_adapter(*args):
        calls.append(True)
        try:
            await asyncio.sleep(5)
        finally:
            cancelled.set()
        return ['EV_DESIGN'], 'too-late-model'
    monkeypatch.setattr(providers, 'select_events', slow_adapter)
    login(client)
    started = time.monotonic()
    response = recommend(client)
    elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert elapsed < 1.0 and cancelled.is_set()
    result = response.json()
    assert result['mode'] == 'fallback' and result['cached'] is False
    assert result['provider'] is None and result['model'] is None
    assert 0 < result['elapsed_ms'] < 1000
    cached = recommend(client).json()
    assert cached['mode'] == 'fallback' and cached['cached'] is True
    assert cached['items'] == result['items'] and cached['reason'] == result['reason']
    assert client.get('/api/v1/employees/E001').json()['recommendation']['cached'] is True
    assert len(calls) == ai_request_count(client) == 1


def test_completion_during_ai_wait_rejects_stale_recommendation(client, settings, monkeypatch):
    settings.timeout = 2
    entered, release = threading.Event(), threading.Event()
    async def delayed_selection(*args):
        entered.set()
        while not release.is_set():
            await asyncio.sleep(0.005)
        return ['EV_DESIGN'], 'mock-model'
    monkeypatch.setattr(providers, 'select_events', delayed_selection)
    login(client)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(recommend, client)
        try:
            assert entered.wait(timeout=1)
            completed = client.post('/api/v1/employees/E001/events/EV_DESIGN/complete')
            assert completed.status_code == 200
            assert completed.json()['already_completed'] is False
        finally:
            release.set()
        stale = pending.result(timeout=3)
    assert stale.status_code == 409
    profile = client.get('/api/v1/employees/E001').json()
    assert profile['employee']['skills']['SK_SYSTEM_DESIGN'] == 3
    assert profile['recommendation'] is None
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Recommendation)) == 0


def test_two_app_instances_share_last_global_ai_quota_slot(settings, monkeypatch):
    settings.per_day = 1
    calls, calls_lock = [], threading.Lock()
    async def selected(config, context):
        with calls_lock:
            calls.append(context['profile']['role'])
        await asyncio.sleep(0.05)
        return [context['candidates'][0]['id']], 'mock-model'
    monkeypatch.setattr(providers, 'select_events', selected)
    with TestClient(create_app(settings), headers=HEADERS) as first:
        with TestClient(create_app(settings), headers=HEADERS) as second:
            login(first, 'hr')
            login(second, 'hr')
            start = threading.Barrier(2)
            def run(client, employee_id):
                start.wait(timeout=2)
                return recommend(client, employee_id)
            with ThreadPoolExecutor(max_workers=2) as pool:
                requests = [pool.submit(run, first, 'E001'), pool.submit(run, second, 'E002')]
                responses = [future.result(timeout=3) for future in requests]
            assert sorted(response.status_code for response in responses) == [200, 429]
            success = next(response.json() for response in responses if response.status_code == 200)
            assert success['mode'] == 'ai'
            assert len(calls) == ai_request_count(first) == ai_request_count(second) == 1


def test_failed_demo_logins_count_toward_rate_limit(client):
    for _ in range(20):
        assert client.post('/api/v1/auth/demo', json={'account': 'UNKNOWN_EMPLOYEE'}).status_code == 404
    assert client.post('/api/v1/auth/demo', json={'account': 'hr'}).status_code == 429
    assert client.get('/api/v1/auth/me').status_code == 401
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AIRequest).where(AIRequest.provider == 'login')) == 20


def run_body_limit(chunks, declared_length=None, max_bytes=8):
    sent, delivered = [], []
    messages = [{'type': 'http.request', 'body': chunk, 'more_body': index < len(chunks) - 1} for index, chunk in enumerate(chunks)]
    async def receive():
        return messages.pop(0) if messages else {'type': 'http.disconnect'}
    async def send(message):
        sent.append(message)
    async def endpoint(scope, receive, send):
        delivered.append(await receive())
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})
    headers = [] if declared_length is None else [(b'content-length', declared_length)]
    scope = {'type': 'http', 'method': 'POST', 'headers': headers}
    asyncio.run(BodyLimitMiddleware(endpoint, max_bytes=max_bytes)(scope, receive, send))
    return sent, delivered


@pytest.mark.parametrize('declared_length', [None, b'1', b'8', b'9'])
def test_body_limit_counts_streamed_bytes_despite_length_header(declared_length):
    sent, delivered = run_body_limit([b'12345', b'6789'], declared_length)
    assert sent[0]['status'] == 413
    assert delivered == []
    assert 'detail' in json.loads(sent[1]['body'])


@pytest.mark.parametrize('declared_length', [b'-1', b'not-a-number'])
def test_body_limit_rejects_invalid_length(declared_length):
    sent, delivered = run_body_limit([b'{}'], declared_length)
    assert sent[0]['status'] == 400 and delivered == []


@pytest.mark.parametrize('declared_length', [None, b'1', b'8'])
def test_body_limit_replays_exact_boundary_body_once(declared_length):
    sent, delivered = run_body_limit([b'123', b'45678'], declared_length)
    assert sent[0]['status'] == 200
    assert delivered == [{'type': 'http.request', 'body': b'12345678', 'more_body': False}]
