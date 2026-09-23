import asyncio
import copy
import json
import time
from types import SimpleNamespace

import pytest

from app.ai import providers, smoke


@pytest.fixture
def settings():
    return SimpleNamespace(
        provider='openai', openai_key='unit-test-placeholder', openai_model='gpt-4.1-mini',
        nvidia_key='unit-test-placeholder', nvidia_model='test-reserve-model', timeout=0.2,
    )


@pytest.fixture
def context():
    return smoke.synthetic_context()


def fake_provider(monkeypatch, content='{"event_ids":["SYNTH_DESIGN"]}', *, finish='stop', refusal=None,
                  enter_delay=0, request_delay=0, exit_delay=0):
    recorded = SimpleNamespace(constructions=[], requests=[], cleanup_started=False, cleanup_finished=False)

    class Client:
        def __init__(self, **kwargs):
            recorded.constructions.append(kwargs)
            self.chat = SimpleNamespace(completions=self)

        async def __aenter__(self):
            await asyncio.sleep(enter_delay)
            return self

        async def __aexit__(self, *args):
            recorded.cleanup_started = True
            await asyncio.sleep(exit_delay)
            recorded.cleanup_finished = True

        async def create(self, **kwargs):
            recorded.requests.append(kwargs)
            await asyncio.sleep(request_delay)
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason=finish, message=SimpleNamespace(content=content, refusal=refusal),
            )])

    monkeypatch.setattr(providers, 'AsyncOpenAI', Client)
    return recorded


def test_openai_request_has_dynamic_strict_schema_and_single_call(settings, context, monkeypatch):
    recorded = fake_provider(monkeypatch)
    selected, model = asyncio.run(providers.select_events(settings, context))
    assert selected == ['SYNTH_DESIGN'] and model == settings.openai_model
    assert len(recorded.constructions) == len(recorded.requests) == 1
    assert recorded.constructions[0]['max_retries'] == 0
    assert recorded.constructions[0]['timeout'] == settings.timeout
    request = recorded.requests[0]
    assert request['store'] is False and request['temperature'] == 0
    assert request['max_tokens'] == 200
    schema = request['response_format']['json_schema']
    assert schema['strict'] is True
    assert schema['schema']['additionalProperties'] is False
    assert schema['schema']['required'] == ['event_ids']
    item_schema = schema['schema']['properties']['event_ids']
    assert item_schema['items']['enum'] == ['SYNTH_DESIGN', 'SYNTH_SPEAKING']
    assert item_schema['maxItems'] == 2
    assert recorded.cleanup_finished


def test_context_contains_factors_but_no_employee_identity_or_raw_history(settings, context, monkeypatch):
    context['profile'].update(id='PRIVATE_ID', name='PRIVATE_PERSON', email='PRIVATE_EMAIL')
    context['history'] = [{'note': 'PRIVATE_HISTORY'}]
    context['trajectory']['private_comment'] = 'PRIVATE_COMMENT'
    context['candidates'][0]['private_note'] = 'PRIVATE_NOTE'
    recorded = fake_provider(monkeypatch)
    asyncio.run(providers.select_events(settings, context))
    text = recorded.requests[0]['messages'][1]['content']
    assert 'PRIVATE_' not in text
    sent = json.loads(text)
    assert set(sent['profile']) == {'role', 'grade', 'tenure_months', 'skills'}
    assert sent['trajectory']['next_grade'] == 'Middle'
    assert {item['factor'] for item in sent['candidates'][0]['evidence']} == {'grade', 'skill_gap', 'next_level', 'history'}
    assert 'untrusted data' in recorded.requests[0]['messages'][0]['content']


@pytest.mark.parametrize('content', [
    'not json', '```json\n{"event_ids":["SYNTH_DESIGN"]}\n```',
    '{"event_ids":[]}', '{"event_ids":["invented"]}',
    '{"event_ids":["SYNTH_DESIGN","SYNTH_DESIGN"]}',
    '{"event_ids":["SYNTH_DESIGN"],"gain":5}',
    '{"event_ids":["SYNTH_DESIGN"],"event_ids":["SYNTH_SPEAKING"]}',
    '{"event_ids":[1]}', '{"event_ids":"SYNTH_DESIGN"}',
    '{"event_ids":["A","B","C","D"]}', 'null',
])
def test_invalid_ai_output_is_rejected(settings, context, monkeypatch, content):
    recorded = fake_provider(monkeypatch, content)
    with pytest.raises(ValueError):
        asyncio.run(providers.select_events(settings, context))
    assert len(recorded.requests) == 1 and recorded.cleanup_finished


@pytest.mark.parametrize(('finish', 'refusal', 'reason'), [
    ('length', None, 'incomplete_response'), ('content_filter', None, 'incomplete_response'),
    ('stop', 'refused', 'refused_response'),
])
def test_incomplete_or_refused_response_is_rejected(settings, context, monkeypatch, finish, refusal, reason):
    fake_provider(monkeypatch, finish=finish, refusal=refusal)
    with pytest.raises(ValueError, match=reason):
        asyncio.run(providers.select_events(settings, context))


def test_lifecycle_uses_one_deadline(settings, context, monkeypatch):
    settings.timeout = 0.12
    recorded = fake_provider(monkeypatch, enter_delay=0.045, request_delay=0.045, exit_delay=0.07)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        asyncio.run(providers.select_events(settings, context))
    assert time.monotonic() - started < 0.4
    assert len(recorded.requests) <= 1
    assert recorded.cleanup_started and not recorded.cleanup_finished


def test_hanging_request_and_cleanup_do_not_receive_two_timeouts(settings, context, monkeypatch):
    settings.timeout = 0.06
    recorded = fake_provider(monkeypatch, request_delay=1, exit_delay=1)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        asyncio.run(providers.select_events(settings, context))
    assert time.monotonic() - started < 0.3
    assert len(recorded.requests) == 1 and recorded.cleanup_started


def test_provider_timeout_is_capped_even_with_direct_settings_override(settings, context, monkeypatch):
    settings.timeout = 100
    recorded = fake_provider(monkeypatch)
    asyncio.run(providers.select_events(settings, context))
    assert recorded.constructions[0]['timeout'] == 8.0


@pytest.mark.parametrize('failure', ['missing_key', 'empty_candidates', 'large_context', 'invalid_timeout', 'unknown_provider'])
def test_invalid_request_fails_before_network(settings, context, monkeypatch, failure):
    recorded = fake_provider(monkeypatch)
    if failure == 'missing_key':
        settings.openai_key = ''
    elif failure == 'empty_candidates':
        context['candidates'] = []
    elif failure == 'large_context':
        context['candidates'][0]['title'] = 'x' * 24001
    elif failure == 'invalid_timeout':
        settings.timeout = float('nan')
    else:
        settings.provider = 'invalid'
    with pytest.raises(ValueError):
        asyncio.run(providers.select_events(settings, context))
    assert recorded.constructions == recorded.requests == []


def test_smoke_requires_explicit_opt_in_without_reading_settings(monkeypatch, capsys):
    def forbidden_settings(**kwargs):
        pytest.fail('Settings must not be read without opt-in')
    monkeypatch.setattr(smoke, 'Settings', forbidden_settings)
    assert smoke.main([]) == 2
    assert 'No request sent' in capsys.readouterr().out


def test_smoke_missing_key_never_contacts_provider(settings, monkeypatch, capsys):
    settings.openai_key = ''
    monkeypatch.setattr(smoke, 'Settings', lambda **kwargs: settings)
    async def forbidden(*args):
        pytest.fail('No request without a configured key')
    monkeypatch.setattr(smoke, 'select_events', forbidden)
    assert smoke.main(['--synthetic']) == 2
    assert json.loads(capsys.readouterr().out)['mode'] == 'not_run'


def test_smoke_uses_embedded_synthetic_data_and_one_call(settings, monkeypatch, capsys):
    monkeypatch.setattr(smoke, 'Settings', lambda **kwargs: settings)
    requests = []
    async def selected(config, context):
        requests.append(copy.deepcopy(context))
        assert config.openai_key == settings.openai_key
        assert 'name' not in context['profile'] and 'id' not in context['profile']
        assert all(item['id'].startswith('SYNTH_') for item in context['candidates'])
        return ['SYNTH_DESIGN'], config.openai_model
    monkeypatch.setattr(smoke, 'select_events', selected)
    assert smoke.main(['--synthetic']) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result['mode'] == 'ai' and result['synthetic'] is True
    assert result['event_ids'] == ['SYNTH_DESIGN'] and result['elapsed_ms'] >= 0
    assert len(requests) == 1 and settings.openai_key not in output


def test_smoke_failure_is_sanitized_and_nonzero(settings, monkeypatch, capsys):
    monkeypatch.setattr(smoke, 'Settings', lambda **kwargs: settings)
    async def failed(*args):
        raise RuntimeError(settings.openai_key)
    monkeypatch.setattr(smoke, 'select_events', failed)
    assert smoke.main(['--synthetic']) == 1
    output = capsys.readouterr().out
    assert settings.openai_key not in output
    result = json.loads(output)
    assert result['mode'] == 'fallback' and result['reason'] == 'provider_error'
