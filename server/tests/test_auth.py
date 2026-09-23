import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import digest, hash_password, verify_password
from app import auth, setup_account
from app.config import ROOT, Settings
from app.db import AccountSession, AuthAttempt, Catalog, Employee, Invitation, LoginSession, UserAccount
from app.ingest import ImportValidationError, import_bundle
from app.import_service import load_kit
from app.main import create_app
from app.schemas import DatasetBundle

HEADERS = {'X-Requested-With': 'CareerQuest'}
PASSWORD = 'synthetic-auth-password-2026'


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f'sqlite:///{tmp_path / "auth.db"}', demo_mode=False,
                    provider='rules', cookie_secure=False, allow_test_setup=True)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), headers=HEADERS) as api:
        with api.app.state.sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            import_bundle(db, DatasetBundle.model_validate_json((ROOT / 'examples/demo.json').read_text(encoding='utf-8')))
        yield api


def setup(client, username='first.hr'):
    return client.post('/api/v1/auth/setup', json={'username': username, 'password': PASSWORD, 'display_name': 'First HR'})


def login(client, username='first.hr', role='hr', password=PASSWORD):
    return client.post('/api/v1/auth/login', json={'username': username, 'password': password, 'role': role})


def invitation(client, role='employee', employee_id='E001'):
    response = client.post('/api/v1/hr/invitations', json={'role': role, 'employee_id': employee_id})
    assert response.status_code == 200, response.text
    return response.json()['invite_code']


def register(client, code, username='member.one', role='employee', **extra):
    return client.post('/api/v1/auth/register', json={
        'username': username, 'password': PASSWORD, 'invite_code': code, 'role': role, **extra,
    })


def test_password_hashes_are_salted_and_verification_rejects_wrong_values():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second and PASSWORD not in first
    assert first.startswith('scrypt$')
    assert verify_password(PASSWORD, first)
    assert not verify_password('wrong-password', first)
    assert not verify_password(PASSWORD, 'invalid stored hash')


def test_normal_default_disables_demo(monkeypatch):
    monkeypatch.delenv('DEMO_MODE', raising=False)
    assert Settings().demo_mode is False
    assert Settings().allow_test_setup is False


def test_first_setup_status_cookie_and_one_time_lock(client):
    assert client.get('/api/v1/auth/status').json() == {
        'setup_required': True, 'registration': 'invite', 'demo_enabled': False,
    }
    assert client.get('/api/v1/auth/demo-accounts').json() == {'enabled': False, 'accounts': []}
    assert client.post('/api/v1/auth/demo', json={'account': 'hr'}).status_code == 403
    response = setup(client)
    assert response.status_code == 200
    assert response.json() == {'role': 'hr', 'employee_id': None, 'username': 'first.hr', 'display_name': 'First HR'}
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie and 'max-age=28800' in cookie
    assert client.get('/api/v1/auth/me').json() == response.json()
    assert client.get('/api/v1/auth/status').json()['setup_required'] is False
    assert setup(client, 'another.hr').status_code == 409
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(UserAccount)) == 1
        account = db.scalar(select(UserAccount))
        assert account.password_hash != PASSWORD and account.employee_id is None


def test_setup_rejects_nonloopback_and_does_not_trust_forwarded_headers(settings):
    settings.allow_test_setup = False
    with TestClient(create_app(settings), headers={**HEADERS, 'X-Forwarded-For': '127.0.0.1'}, client=('198.51.100.20', 50000)) as remote:
        assert setup(remote).status_code == 403
        assert remote.get('/api/v1/auth/status').json()['setup_required'] is True
    with TestClient(create_app(settings), headers=HEADERS, client=('127.0.0.1', 50000)) as local:
        assert setup(local).status_code == 200


def test_two_simultaneous_setup_requests_create_only_one_hr(settings):
    with TestClient(create_app(settings), headers=HEADERS) as first:
        with TestClient(create_app(settings), headers=HEADERS) as second:
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = [pool.submit(setup, first, 'first.hr'), pool.submit(setup, second, 'other.hr')]
                assert sorted(item.result().status_code for item in pending) == [200, 409]
            with first.app.state.sessions() as db:
                assert db.scalar(select(func.count()).select_from(UserAccount)) == 1


@pytest.mark.parametrize('password', ['xqZ$7', 'x' * 129])
def test_weak_or_oversized_password_rejected_without_echo(client, password):
    response = client.post('/api/v1/auth/setup', json={'username': 'first.hr', 'password': password, 'display_name': 'HR'})
    assert response.status_code == 422
    assert password not in response.text
    assert all('input' not in error for error in response.json()['detail'])
    assert client.get('/api/v1/auth/status').json()['setup_required'] is True


def test_username_normalization_password_role_checks_and_session_rotation(client):
    assert setup(client, 'First.HR').status_code == 200
    original_cookie = client.cookies.get('cq_session')
    assert login(client, 'FIRST.HR', role='employee').status_code == 401
    assert login(client, 'first.hr', password='synthetic-wrong-password').status_code == 401
    response = login(client, 'FIRST.HR')
    assert response.status_code == 200 and response.json()['username'] == 'first.hr'
    assert client.cookies.get('cq_session') != original_cookie
    with client.app.state.sessions() as db:
        assert db.get(LoginSession, digest(original_cookie)) is None
        assert db.get(AccountSession, digest(original_cookie)) is None
        assert db.scalar(select(func.count()).select_from(LoginSession)) == 1


def test_invitation_registration_binds_employee_and_rejects_role_escalation(client, settings):
    assert setup(client).status_code == 200
    code = invitation(client)
    with client.app.state.sessions() as db:
        row = db.get(Invitation, digest(code))
        assert row and row.code_hash != code and row.used_at is None
    with TestClient(create_app(settings), headers=HEADERS) as member:
        assert register(member, code, role='hr').status_code == 403
        assert register(member, code, employee_id='E002').status_code == 422
        response = register(member, code)
        assert response.status_code == 200
        assert response.json()['employee_id'] == 'E001' and response.json()['role'] == 'employee'
        assert member.get('/api/v1/employees/E001').status_code == 200
        for path in ('/employees/E002', '/employees', '/hr/overview', '/hr/accounts', '/catalog'):
            assert member.get('/api/v1' + path).status_code == 403
        assert member.post('/api/v1/hr/invitations', json={'role': 'hr', 'employee_id': None}).status_code == 403
        assert member.post('/api/v1/imports', json={}).status_code == 403
        assert register(member, code, username='second.member').status_code == 422
        assert login(member, 'member.one', role='hr').status_code == 401
        assert login(member, 'member.one', role='employee').status_code == 200
        # Session metadata cannot elevate a real account's server-owned role.
        with member.app.state.sessions() as db:
            session = db.get(LoginSession, digest(member.cookies.get('cq_session')))
            session.role, session.employee_id = 'hr', None
            db.commit()
        assert member.get('/api/v1/auth/me').json()['role'] == 'employee'
        assert member.get('/api/v1/hr/overview').status_code == 403
    assert client.post('/api/v1/hr/invitations', json={'role': 'employee', 'employee_id': 'E001'}).status_code == 409


def test_invited_hr_can_register_only_with_hr_invitation(client, settings):
    setup(client)
    code = invitation(client, 'hr', None)
    with TestClient(create_app(settings), headers=HEADERS) as second:
        response = register(second, code, 'second.hr', 'hr')
        assert response.status_code == 200 and response.json()['employee_id'] is None
        accounts = second.get('/api/v1/hr/accounts').json()
        assert {item['username'] for item in accounts} == {'first.hr', 'second.hr'}
        assert all(set(item) == {'id', 'username', 'display_name', 'role', 'employee_id', 'created_at'} for item in accounts)
        assert all('password' not in item and 'password_hash' not in item for item in accounts)


def test_invite_requires_valid_profile_role_and_unexpired_code(client, settings):
    assert client.post('/api/v1/hr/invitations', json={'role': 'hr'}).status_code == 401
    setup(client)
    for body in ({'role': 'employee'}, {'role': 'hr', 'employee_id': 'E001'}, {'role': 'admin'}):
        assert client.post('/api/v1/hr/invitations', json=body).status_code == 422
    assert client.post('/api/v1/hr/invitations', json={'role': 'employee', 'employee_id': 'MISSING'}).status_code == 404
    code = invitation(client)
    with client.app.state.sessions() as db:
        db.get(Invitation, digest(code)).expires_at = time.time() - 1
        db.commit()
    with TestClient(create_app(settings), headers=HEADERS) as member:
        assert register(member, code).status_code == 422
        assert register(member, 'x' * 43).status_code == 422
        assert member.get('/api/v1/auth/me').status_code == 401


def test_invitation_single_use_is_atomic_across_app_instances(client, settings):
    setup(client)
    code = invitation(client)
    with TestClient(create_app(settings), headers=HEADERS) as first:
        with TestClient(create_app(settings), headers=HEADERS) as second:
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = [pool.submit(register, first, code, 'member.one'), pool.submit(register, second, code, 'member.two')]
                assert sorted(item.result().status_code for item in pending) == [200, 422]
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(UserAccount).where(UserAccount.employee_id == 'E001')) == 1


def test_auth_throttle_persists_failures_and_survives_restart(client, settings):
    for _ in range(10):
        assert login(client, username='unknown.member').status_code == 401
    assert login(client, username='unknown.member').status_code == 429
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AuthAttempt)) == 20
    with TestClient(create_app(settings), headers=HEADERS) as restarted:
        assert login(restarted, username='unknown.member').status_code == 429


def test_accounts_sessions_and_logout_survive_restart_and_expire(client, settings):
    setup(client)
    token = client.cookies.get('cq_session')
    with TestClient(create_app(settings), headers=HEADERS) as restarted:
        restarted.cookies.set('cq_session', token)
        assert restarted.get('/api/v1/auth/me').json()['username'] == 'first.hr'
        assert restarted.get('/api/v1/auth/status').json()['setup_required'] is False
        assert restarted.post('/api/v1/auth/logout').status_code == 200
        assert restarted.get('/api/v1/auth/me').status_code == 401
    assert client.get('/api/v1/auth/me').status_code == 401
    assert login(client).status_code == 200
    with client.app.state.sessions() as db:
        db.get(LoginSession, digest(client.cookies.get('cq_session'))).expires_at = time.time() - 1
        db.commit()
    assert client.get('/api/v1/auth/me').status_code == 401


def test_demo_session_is_rejected_when_demo_mode_is_disabled(client):
    token = 'synthetic-old-demo-session'
    with client.app.state.sessions() as db:
        db.add(LoginSession(token_hash=digest(token), role='hr', employee_id=None, expires_at=time.time() + 1000))
        db.commit()
    client.cookies.set('cq_session', token)
    assert client.get('/api/v1/auth/me').status_code == 401
    assert client.get('/api/v1/hr/overview').status_code == 401


def test_hr_catalog_is_full_normalized_data_without_private_profiles_or_history(client):
    assert client.get('/api/v1/catalog').status_code == 401
    setup(client)
    result = client.get('/api/v1/catalog').json()
    expected = json.loads((ROOT / 'examples/demo.json').read_text(encoding='utf-8'))
    assert set(result) == {'skills', 'events', 'grade_rules', 'counts'}
    for key in ('skills', 'events', 'grade_rules'):
        assert result[key] == expected[key]
        assert result['counts'][key] == len(expected[key])


def test_auth_mutations_keep_csrf_and_origin_checks(client):
    body = {'username': 'first.hr', 'password': PASSWORD, 'display_name': 'HR'}
    assert client.post('/api/v1/auth/setup', json=body, headers={'X-Requested-With': ''}).status_code == 403
    assert client.post('/api/v1/auth/setup', json=body, headers={'Origin': 'https://untrusted.example'}).status_code == 403
    assert client.get('/api/v1/auth/status').json()['setup_required'] is True


def test_password_work_has_bounded_concurrent_memory(monkeypatch):
    state = {'active': 0, 'peak': 0}
    lock = threading.Lock()

    def derive(*args, **kwargs):
        with lock:
            state['active'] += 1
            state['peak'] = max(state['peak'], state['active'])
        time.sleep(0.04)
        with lock:
            state['active'] -= 1
        return b'x' * 32

    monkeypatch.setattr(auth.hashlib, 'scrypt', derive)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(list(pool.map(hash_password, ['synthetic'] * 4))) == 4
    assert state['peak'] == 2


@pytest.mark.parametrize('linked', ['account', 'invitation'])
def test_direct_kit_replacement_preserves_account_and_invitation_links(client, linked):
    from test_kit_import import synthetic_files
    with client.app.state.sessions() as db:
        if linked == 'account':
            db.add(UserAccount(id='synthetic-account', username='linked.member', display_name='Synthetic member',
                               password_hash='unused', role='employee', employee_id='E001', created_at=time.time()))
        else:
            db.add(Invitation(code_hash=digest('synthetic-invitation'), role='employee', employee_id='E001',
                              created_at=time.time(), expires_at=time.time() + 1000, used_at=None))
        db.commit()
        before = {employee.id: employee.profile for employee in db.scalars(select(Employee))}
        catalog = db.get(Catalog, 1).payload
    with client.app.state.sessions() as db:
        with pytest.raises(ImportValidationError, match='учётными записями или приглашениями'):
            load_kit(db, synthetic_files(), replace_demo=True)
    with client.app.state.sessions() as db:
        assert {employee.id: employee.profile for employee in db.scalars(select(Employee))} == before
        assert db.get(Catalog, 1).payload == catalog


def test_first_hr_cli_uses_hidden_password_and_shares_one_time_guard(settings, monkeypatch, capsys):
    monkeypatch.setenv('DATABASE_URL', settings.database_url)
    monkeypatch.setattr(setup_account.sys, 'argv', ['setup_account'])
    monkeypatch.setattr(setup_account.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    inputs = iter(['terminal.hr', 'Terminal HR'])
    monkeypatch.setattr('builtins.input', lambda _prompt: next(inputs))
    monkeypatch.setattr(setup_account.getpass, 'getpass', lambda _prompt: PASSWORD)
    assert setup_account.main() == 0
    assert setup_account.main() == 1
    assert PASSWORD not in capsys.readouterr().out
    with TestClient(create_app(settings), headers=HEADERS) as client:
        assert login(client, 'terminal.hr').status_code == 200
        assert setup(client).status_code == 409


def test_first_hr_cli_rejects_noninteractive_password_input(monkeypatch, capsys):
    monkeypatch.setattr(setup_account.sys, 'argv', ['setup_account'])
    monkeypatch.setattr(setup_account.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    assert setup_account.main() == 1
    assert 'interactive terminal' in capsys.readouterr().out
