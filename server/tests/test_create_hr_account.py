"""Local HR bootstrap must work when the database already has an HR."""

from types import SimpleNamespace

from sqlalchemy import func, select

from app import create_hr_account
from app.db import UserAccount
from test_auth import PASSWORD, client, login, settings, setup


def terminal(monkeypatch, database_url, username, password=PASSWORD, confirmation=PASSWORD):
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setattr(create_hr_account.sys, 'argv', ['create_hr_account'])
    monkeypatch.setattr(create_hr_account.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    answers = iter([username, 'Additional HR'])
    monkeypatch.setattr('builtins.input', lambda _prompt: next(answers))
    secrets = iter([password, confirmation])
    monkeypatch.setattr(create_hr_account.getpass, 'getpass', lambda _prompt: next(secrets))


def test_local_tool_adds_second_hr_to_same_database_without_invitation(client, settings, monkeypatch):
    assert setup(client).status_code == 200
    terminal(monkeypatch, settings.database_url, 'NEW.HR')
    assert create_hr_account.main() == 0
    with client.app.state.sessions() as db:
        accounts = list(db.scalars(select(UserAccount).order_by(UserAccount.username)))
        assert [row.username for row in accounts] == ['first.hr', 'new.hr']
        assert all(row.role == 'hr' and row.employee_id is None and row.password_hash != PASSWORD for row in accounts)
    assert login(client, 'new.hr').status_code == 200
    assert client.get('/api/v1/hr/accounts').status_code == 200
    assert login(client, 'first.hr').status_code == 200


def test_duplicate_and_mismatched_password_never_change_existing_accounts(client, settings, monkeypatch):
    assert setup(client).status_code == 200
    terminal(monkeypatch, settings.database_url, 'FIRST.HR')
    assert create_hr_account.main() == 1
    terminal(monkeypatch, settings.database_url, 'another.hr', confirmation='wrong-synthetic-password')
    assert create_hr_account.main() == 1
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(UserAccount)) == 1


def test_noninteractive_invocation_cannot_create_privileged_account(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "never-created.db"}')
    monkeypatch.setattr(create_hr_account.sys, 'argv', ['create_hr_account'])
    monkeypatch.setattr(create_hr_account.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    assert create_hr_account.main() == 1
    assert not (tmp_path / 'never-created.db').exists()
