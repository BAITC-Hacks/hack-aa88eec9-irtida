"""Stakeholder roles are permissions; they never rewrite a Kit career role."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import setup_account
from app.db import Activity, Employee, Invitation, UserAccount
from app.main import create_app
from app.services import hr_overview
from test_auth import HEADERS, PASSWORD, client, invitation, login, register, settings, setup

STAFF = ('employee', 'manager', 'operator', 'supervisor')


def public_client(api, username='contact.client', **extra):
    return api.post('/api/v1/auth/register', json={
        'username': username, 'password': PASSWORD, 'role': 'client', 'display_name': 'Contact client', **extra,
    })


def enroll(api, role, employee_id='E001'):
    assert setup(api).status_code == 200
    code = invitation(api, role, employee_id)
    response = register(api, code, f'{role}.member', role)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('role', STAFF)
def test_internal_roles_keep_own_career_and_server_owned_permissions(client, settings, role):
    account = enroll(client, role)
    assert account['role'] == role and account['employee_id'] == 'E001'
    profile = client.get('/api/v1/employees/E001')
    assert profile.status_code == 200
    assert profile.json()['employee']['role'] == 'Backend Engineer'
    assert client.get('/api/v1/employees/E002').status_code == 403
    for path in ('/employees', '/catalog', '/hr/accounts', '/hr/overview'):
        assert client.get('/api/v1' + path).status_code == 403
    assert client.post('/api/v1/imports', json={}).status_code == 403
    assert client.post('/api/v1/hr/invitations', json={'role': 'hr', 'employee_id': None}).status_code == 403
    team_status = 200 if role in {'manager', 'supervisor'} else 403
    assert client.get('/api/v1/team/employees').status_code == team_status
    assert client.get('/api/v1/team/overview').status_code == team_status
    assert login(client, f'{role}.member', role='hr').status_code == 401
    assert login(client, f'{role}.member', role=role).status_code == 200
    assert client.post('/api/v1/employees/E001/recommendations').status_code == 200
    completed = client.post('/api/v1/employees/E001/events/EV_DESIGN/complete')
    assert completed.status_code == 200 and completed.json()['already_completed'] is False
    assert client.post('/api/v1/employees/E002/events/EV_DESIGN/complete').status_code == 403
    # Existing accounts/session schemas persist every new role without migration.
    with TestClient(create_app(settings), headers=HEADERS) as restarted:
        restarted.cookies.set('cq_session', client.cookies.get('cq_session'))
        assert restarted.get('/api/v1/auth/me').json()['role'] == role
        assert restarted.get('/api/v1/employees/E001').json()['employee']['skills']['SK_SYSTEM_DESIGN'] == 3


@pytest.mark.parametrize('role', ['manager', 'supervisor'])
def test_team_is_direct_reports_only_and_never_includes_outside_history(client, role):
    with client.app.state.sessions() as db:
        leader, report, outsider = [db.get(Employee, id_) for id_ in ('E001', 'E002', 'E003')]
        leader.profile = {**leader.profile, 'manager_id': None}
        report.profile = {**report.profile, 'manager_id': 'E001'}
        outsider.profile = {**outsider.profile, 'manager_id': None}
        db.add(Employee(id='INDIRECT', profile={**report.profile, 'id': 'INDIRECT', 'name': 'Indirect report', 'manager_id': 'E002'}))
        db.flush()
        db.add(Activity(id='DIRECT_HISTORY', employee_id='E002', event_id='EV_DESIGN', status='missed', occurred_at='2026-01-01'))
        db.add(Activity(id='OUTSIDE_HISTORY', employee_id='E003', event_id='EV_DESIGN', status='declined', occurred_at='2026-01-01'))
        db.add(Activity(id='INDIRECT_HISTORY', employee_id='INDIRECT', event_id='EV_DESIGN', status='completed', occurred_at='2026-01-01'))
        db.commit()
        expected = Counter((item.event_id, item.status) for item in db.scalars(select(Activity).where(Activity.employee_id == 'E002')))
    enroll(client, role)
    reports = client.get('/api/v1/team/employees').json()
    assert [person['id'] for person in reports] == ['E002']
    assert client.get('/api/v1/employees/E002').status_code == 200
    for employee_id in ('E003', 'INDIRECT'):
        assert client.get(f'/api/v1/employees/{employee_id}').status_code == 403
    assert client.post('/api/v1/employees/E002/recommendations').status_code == 403
    assert client.post('/api/v1/employees/E002/events/EV_DESIGN/complete').status_code == 403
    overview = client.get('/api/v1/team/overview').json()
    assert overview['employee_count'] == 1
    assert all(gap['eligible'] <= 1 and gap['affected'] <= 1 for gap in overview['gaps'])
    assert {item['id'] for item in overview['no_step']} <= {'E002'}
    assert {item['id'] for item in overview['participation']} == {event_id for event_id, _ in expected}
    for item in overview['participation']:
        for status in ('completed', 'missed', 'declined', 'no_show', 'dropped', 'in_progress', 'overdue'):
            assert item[status] == expected[item['id'], status]
    assert client.get('/api/v1/hr/overview').status_code == 403


def test_explicit_empty_employee_scope_never_means_whole_organization(client):
    with client.app.state.sessions() as db:
        assert hr_overview(db, employee_ids=[]) == {
            'employee_count': 0, 'gaps': [], 'no_step': [], 'participation': [],
        }
        assert hr_overview(db)['employee_count'] == 3


def test_client_registration_creates_only_account_and_no_staff_access(client, settings):
    response = public_client(client)
    assert response.status_code == 200
    assert response.json() == {'role': 'client', 'employee_id': None, 'username': 'contact.client', 'display_name': 'Contact client'}
    assert client.get('/api/v1/auth/status').json()['setup_required'] is True
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Employee)) == 3
        assert db.scalar(select(func.count()).select_from(Invitation)) == 0
        account = db.scalar(select(UserAccount))
        assert account.role == 'client' and account.employee_id is None
    for path in ('/employees', '/employees/E001', '/employees/MISSING', '/catalog', '/hr/overview', '/hr/accounts', '/team/employees', '/team/overview'):
        assert client.get('/api/v1' + path).status_code == 403
    for path in ('/employees/E001/recommendations', '/employees/E001/events/EV_DESIGN/complete', '/imports', '/imports/kit', '/hr/invitations'):
        assert client.post('/api/v1' + path, json={}).status_code == 403
    assert login(client, 'contact.client', role='employee').status_code == 401
    assert login(client, 'CONTACT.CLIENT', role='client').status_code == 200
    with TestClient(create_app(settings), headers=HEADERS) as restarted:
        restarted.cookies.set('cq_session', client.cookies.get('cq_session'))
        assert restarted.get('/api/v1/auth/me').json()['role'] == 'client'
        assert restarted.get('/api/v1/employees/E001').status_code == 403


def test_public_registration_cannot_be_used_for_staff_or_profile_binding(client):
    for role in (*STAFF, 'hr'):
        assert public_client(client, role=role).status_code == 422
    assert public_client(client, employee_id='E001').status_code == 422
    assert public_client(client, invite_code='x' * 43).status_code == 422
    for name in ('', '   ', None):
        assert public_client(client, display_name=name).status_code == 422
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(UserAccount)) == 0


def test_client_username_collision_does_not_block_first_hr_setup(client):
    assert public_client(client, username='FIRST.HR').status_code == 200
    assert setup(client).status_code == 409
    assert client.get('/api/v1/auth/status').json()['setup_required'] is True
    assert setup(client, 'another.hr').status_code == 200
    assert client.get('/api/v1/auth/status').json()['setup_required'] is False
    assert client.post('/api/v1/hr/invitations', json={'role': 'client', 'employee_id': None}).status_code == 422
    with client.app.state.sessions() as db:
        assert {account.role for account in db.scalars(select(UserAccount))} == {'client', 'hr'}


def test_client_and_first_hr_username_race_is_atomic(settings):
    with TestClient(create_app(settings), headers=HEADERS) as first:
        with TestClient(create_app(settings), headers=HEADERS) as second:
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = [pool.submit(setup, first, 'Race.Account'), pool.submit(public_client, second, 'race.account')]
                assert sorted(item.result().status_code for item in pending) == [200, 409]
            with first.app.state.sessions() as db:
                accounts = list(db.scalars(select(UserAccount)))
                assert len(accounts) == 1 and accounts[0].username == 'race.account'
                assert first.get('/api/v1/auth/status').json()['setup_required'] == (accounts[0].role == 'client')


def test_terminal_first_hr_setup_ignores_client_only_accounts(client, settings, monkeypatch):
    assert public_client(client).status_code == 200
    monkeypatch.setenv('DATABASE_URL', settings.database_url)
    monkeypatch.setattr(setup_account.sys, 'argv', ['setup_account'])
    monkeypatch.setattr(setup_account.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    entries = iter(['terminal.hr', 'Terminal HR'])
    monkeypatch.setattr('builtins.input', lambda _prompt: next(entries))
    monkeypatch.setattr(setup_account.getpass, 'getpass', lambda _prompt: PASSWORD)
    assert setup_account.main() == 0
    assert login(client, 'terminal.hr', 'hr').status_code == 200


@pytest.mark.parametrize('role', ['manager', 'operator', 'supervisor'])
def test_new_internal_invites_require_existing_profile_and_exact_role(client, role):
    setup(client)
    assert client.post('/api/v1/hr/invitations', json={'role': role, 'employee_id': None}).status_code == 422
    assert client.post('/api/v1/hr/invitations', json={'role': role, 'employee_id': 'MISSING'}).status_code == 404
    code = invitation(client, role)
    assert register(client, code, 'new.member', 'employee').status_code == 403
    response = register(client, code, 'new.member', role)
    assert response.status_code == 200 and response.json()['role'] == role
