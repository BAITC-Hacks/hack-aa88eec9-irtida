"""The separate NVIDIA practice module consumes current, authorized Kit state."""

import sys

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.ai import personalization_routes
from app.db import Activity, Employee
from app.import_service import load_kit
from app.main import create_app
from test_kit_import import synthetic_files


HEADERS = {'X-Requested-With': 'CareerQuest'}
ROUTE = '/api/v1/employees/K1/personalization'


@pytest.fixture
def personalized_api(tmp_path, monkeypatch):
    monkeypatch.setenv('NVIDIA_AI_MOCK', 'true')
    monkeypatch.delenv('NVIDIA_API_KEY', raising=False)
    monkeypatch.setenv('AI_DATA_POLICY_APPROVED', 'false')
    settings = Settings(database_url=f'sqlite:///{tmp_path / "personalization.db"}',
                        provider='rules', demo_mode=True, cookie_secure=False)
    with TestClient(create_app(settings), headers=HEADERS) as api:
        with api.app.state.sessions() as db:
            load_kit(db, synthetic_files(), replace_demo=True)
        response = api.post('/api/v1/auth/demo', json={'account': 'K1'})
        assert response.status_code == 200, response.text
        yield api


def test_mock_uses_current_database_skills_and_completion_without_awarding_practice(personalized_api):
    api = personalized_api
    before = api.get('/api/v1/employees/K1').json()
    assert before['employee']['skills']['SK_SPEAK'] == 1
    with api.app.state.sessions() as db:
        history_count = len([row for row in db.query(Activity).filter(Activity.employee_id == 'K1')])

    generated = api.post(ROUTE)
    assert generated.status_code == 200, generated.text
    result = generated.json()
    assert result['mode'] == 'mock'
    assert result['recommendedQuests']
    assert all(quest['kind'] == 'practice_suggestion' and quest['requiresReview']
               and quest['estimatedImpact']['basis'] == 'source_event_completion_only'
               for quest in result['recommendedQuests'])
    assert {quest['sourceEventId'] for quest in result['recommendedQuests']} == {'EV_036'}
    assert all(quest['estimatedImpact']['fromLevel'] == 1 for quest in result['recommendedQuests'])
    with api.app.state.sessions() as db:
        assert db.get(Employee, 'K1').profile['skills']['SK_SPEAK'] == 1
        assert len([row for row in db.query(Activity).filter(Activity.employee_id == 'K1')]) == history_count

    completed = api.post('/api/v1/employees/K1/events/EV_036/complete',
                         json={'occurrence_id': '2026-10-05'})
    assert completed.status_code == 200, completed.text
    assert completed.json()['profile']['employee']['skills']['SK_SPEAK'] == 2
    current = api.post(ROUTE)
    assert current.status_code == 200, current.text
    current_quests = current.json()['recommendedQuests']
    assert current_quests and all(quest['estimatedImpact']['fromLevel'] == 2 for quest in current_quests)
    assert all(quest['sourceSessionDate'] == '2026-10-12' for quest in current_quests)


def test_only_own_staff_profile_can_request_personalization(personalized_api):
    api = personalized_api
    assert api.post('/api/v1/employees/K_LEAD/personalization').status_code == 403
    assert api.post(ROUTE, headers={'X-Requested-With': 'wrong'}).status_code == 403
    assert api.post(ROUTE, json={'skills': [{'skillId': 'SK_SPEAK', 'level': 5}]}).status_code == 422
    assert api.post('/api/v1/auth/demo', json={'account': 'hr'}).status_code == 200
    assert api.post(ROUTE).status_code == 403
    registered = api.post('/api/v1/auth/register', json={
        'username': 'test.client', 'password': 'synthetic-client-password-2026',
        'role': 'client', 'display_name': 'Test client',
    })
    assert registered.status_code == 200, registered.text
    assert api.post(ROUTE).status_code == 403


def test_highest_grade_has_no_candidates_and_no_synthetic_practice(personalized_api):
    api = personalized_api
    assert api.post('/api/v1/auth/demo', json={'account': 'K_LEAD'}).status_code == 200
    response = api.post('/api/v1/employees/K_LEAD/personalization')
    assert response.status_code == 200, response.text
    assert response.json()['mode'] == 'no_candidates'
    assert response.json()['recommendedQuests'] == []


def test_invalid_live_output_is_rejected_without_leaking_model_text(tmp_path, monkeypatch):
    monkeypatch.setenv('NVIDIA_AI_MOCK', 'false')
    monkeypatch.setenv('NVIDIA_API_KEY', 'synthetic-placeholder-key')
    monkeypatch.setenv('AI_DATA_POLICY_APPROVED', 'true')
    async def invalid_output(_client, _prompt, _context):
        return '{"summary":"PRIVATE_MODEL_TEXT"}'
    service_module = sys.modules[personalization_routes.NvidiaCareerAI.__module__]
    monkeypatch.setattr(service_module.NvidiaClient, 'complete', invalid_output)
    settings = Settings(database_url=f'sqlite:///{tmp_path / "invalid-output.db"}',
                        provider='nvidia', demo_mode=True, cookie_secure=False)
    with TestClient(create_app(settings), headers=HEADERS) as api:
        with api.app.state.sessions() as db:
            load_kit(db, synthetic_files(), replace_demo=True)
        assert api.post('/api/v1/auth/demo', json={'account': 'K1'}).status_code == 200
        response = api.post(ROUTE)
        assert response.status_code == 502, response.text
        assert 'PRIVATE_MODEL_TEXT' not in response.text
        assert 'synthetic-placeholder-key' not in response.text
        with api.app.state.sessions() as db:
            assert db.get(Employee, 'K1').profile['skills']['SK_SPEAK'] == 1


def test_live_requires_explicit_cloud_approval_and_never_calls_provider(tmp_path, monkeypatch):
    monkeypatch.setenv('NVIDIA_AI_MOCK', 'false')
    monkeypatch.setenv('NVIDIA_API_KEY', 'synthetic-placeholder-key')
    monkeypatch.setenv('AI_DATA_POLICY_APPROVED', 'false')
    async def forbidden(_client, _prompt, _context):
        pytest.fail('NVIDIA must not be called without the deployment cloud-data setting')
    service_module = sys.modules[personalization_routes.NvidiaCareerAI.__module__]
    monkeypatch.setattr(service_module.NvidiaClient, 'complete', forbidden)
    settings = Settings(database_url=f'sqlite:///{tmp_path / "no-approval.db"}',
                        provider='nvidia', demo_mode=True, cookie_secure=False)
    with TestClient(create_app(settings), headers=HEADERS) as api:
        with api.app.state.sessions() as db:
            load_kit(db, synthetic_files(), replace_demo=True)
        assert api.post('/api/v1/auth/demo', json={'account': 'K1'}).status_code == 200
        response = api.post(ROUTE)
        assert response.status_code == 403
        assert 'synthetic-placeholder-key' not in response.text
