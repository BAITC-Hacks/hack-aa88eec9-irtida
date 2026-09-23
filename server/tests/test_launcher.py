"""Launcher commands are checked without installing packages or starting a server."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location('career_quest_launcher', Path(__file__).resolve().parents[2] / 'run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module.shutil, 'which', lambda name: 'npm')
    commands = []
    monkeypatch.setattr(module, 'run', lambda command, cwd=None: commands.append([str(value) for value in command]))
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    return module, commands


@pytest.mark.parametrize(('argv', 'port'), [([], 8000), (['--port', '8017'], 8017), (['--port', '65535'], 65535)])
def test_launcher_port_matches_server_and_display_preserving_origins(launcher, monkeypatch, capsys, argv, port):
    module, commands = launcher
    allowed = 'http://127.0.0.1:8017'
    monkeypatch.setenv('ALLOWED_ORIGINS', allowed)

    module.main(argv)

    assert commands[-1][1:] == ['-m', 'uvicorn', 'app.main:app', '--app-dir', 'server', '--host', '127.0.0.1', '--port', str(port)]
    assert ['npm', 'run', 'build'] in commands[:-1]
    assert f'http://127.0.0.1:{port}' in capsys.readouterr().out
    assert module.os.environ['ALLOWED_ORIGINS'] == allowed


@pytest.mark.parametrize('port', ['0', '-1', '65536', 'not-a-port'])
def test_launcher_rejects_invalid_port_before_bootstrap(launcher, port):
    module, commands = launcher

    with pytest.raises(SystemExit) as error:
        module.main(['--port', port])

    assert error.value.code == 2
    assert commands == []
