import pytest
from sqlalchemy import func, select

from app.bootstrap import bootstrap_data
from app.config import Settings
from app.db import Activity, Employee, connect
from app import local_server
from test_kit_import import synthetic_files


def test_local_launch_discovers_kit_preserves_database_and_explicit_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(local_server.os, 'environ', dict(local_server.os.environ))
    kit = tmp_path / 'career_quest_dataset/case_1/career_quest_dataset'
    kit.mkdir(parents=True)
    monkeypatch.setattr(local_server, 'ROOT', tmp_path)
    for key in ('CAREER_QUEST_KIT_DIR', 'CAREER_QUEST_AUTO_IMPORT', 'DATABASE_URL', 'DEMO_MODE', 'ALLOWED_ORIGINS'):
        monkeypatch.delenv(key, raising=False)
    local_server.configure_local(8010)
    assert local_server.os.environ['DATABASE_URL'].endswith('data/career-quest-kit.db')
    assert local_server.os.environ['DEMO_MODE'] == 'false'
    assert local_server.os.environ['CAREER_QUEST_AUTO_IMPORT'] == 'true'
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///custom.db')
    monkeypatch.setenv('ALLOWED_ORIGINS', 'https://company.test')
    local_server.configure_local(8011)
    assert local_server.os.environ['DATABASE_URL'] == 'sqlite:///custom.db'
    assert local_server.os.environ['ALLOWED_ORIGINS'] == 'https://company.test,http://localhost:8011,http://127.0.0.1:8011'


def test_kit_bootstrap_once_keeps_employee_progress(tmp_path, monkeypatch):
    for name, content in synthetic_files().items():
        (tmp_path / name).write_bytes(content)
    monkeypatch.setenv('CAREER_QUEST_KIT_DIR', str(tmp_path))
    monkeypatch.setenv('CAREER_QUEST_AUTO_IMPORT', 'true')
    settings = Settings(database_url=f'sqlite:///{tmp_path / "app.db"}')
    engine, sessions = connect(settings.database_url)
    try:
        result = bootstrap_data(sessions, settings)
        assert result['employees_added'] == 2
        with sessions() as db:
            person = db.get(Employee, 'K1')
            person.revision = 7
            db.commit()
        # Once initialized it even works with the source disconnected.
        monkeypatch.setenv('CAREER_QUEST_KIT_DIR', str(tmp_path / 'offline'))
        assert bootstrap_data(sessions, settings) is None
        with sessions() as db:
            assert db.get(Employee, 'K1').revision == 7
            assert db.scalar(select(func.count()).select_from(Activity)) == 2
    finally:
        engine.dispose()


def test_incomplete_kit_fails_without_partial_data(tmp_path, monkeypatch):
    monkeypatch.setenv('CAREER_QUEST_KIT_DIR', str(tmp_path))
    monkeypatch.setenv('CAREER_QUEST_AUTO_IMPORT', 'true')
    settings = Settings(database_url=f'sqlite:///{tmp_path / "app.db"}')
    engine, sessions = connect(settings.database_url)
    try:
        with pytest.raises(RuntimeError, match='Incomplete Career Quest Kit'):
            bootstrap_data(sessions, settings)
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Employee)) == 0
    finally:
        engine.dispose()
