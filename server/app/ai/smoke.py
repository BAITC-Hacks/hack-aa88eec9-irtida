"""One opt-in OpenAI call using embedded synthetic data only.

Run from the repository root: python -m server.app.ai.smoke --synthetic
The backend loads OPENAI_API_KEY from its environment/.env; never pass a key here.
"""

import argparse
import asyncio
import json
import time

from ..config import Settings
from ..domain.progression import candidates, trajectory
from .providers import select_events


def synthetic_context() -> dict:
    employee = {
        'role': 'Software Engineer', 'grade': 'Junior', 'tenure_months': 12,
        'skills': {'SYSTEM_DESIGN': 2, 'PUBLIC_SPEAKING': 0},
    }
    catalog = {
        'skills': [
            {'id': 'SYSTEM_DESIGN', 'name': 'System Design', 'kind': 'hard'},
            {'id': 'PUBLIC_SPEAKING', 'name': 'Public Speaking', 'kind': 'soft'},
        ],
        'grade_rules': [{
            'role': 'Software Engineer', 'grade': 'Junior', 'next_grade': 'Middle',
            'requirements': {'SYSTEM_DESIGN': 4, 'PUBLIC_SPEAKING': 1},
        }],
        'events': [
            {'id': 'SYNTH_DESIGN', 'title': 'Synthetic architecture workshop',
             'type': 'workshop', 'roles': ['Software Engineer'], 'grades': ['Junior'],
             'effects': {'SYSTEM_DESIGN': {'gain': 2, 'max_level': 4}}},
            {'id': 'SYNTH_SPEAKING', 'title': 'Synthetic speaking session',
             'type': 'speaking', 'roles': ['Software Engineer'], 'grades': ['Junior'],
             'effects': {'PUBLIC_SPEAKING': {'gain': 1, 'max_level': 3}}},
        ],
    }
    history = [
        {'event_id': 'SYNTH_SPEAKING', 'status': 'missed'},
        {'event_id': 'SYNTH_SPEAKING', 'status': 'declined'},
    ]
    return {
        'profile': employee,
        'trajectory': trajectory(employee, catalog),
        'candidates': candidates(employee, catalog, history),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Make one OpenAI smoke request with embedded synthetic data.')
    parser.add_argument('--synthetic', action='store_true', help='Explicitly opt in to one paid synthetic-only request.')
    args = parser.parse_args(argv)
    if not args.synthetic:
        parser.print_usage()
        print('No request sent. Pass --synthetic to run one synthetic-only request.')
        return 2

    settings = Settings(provider='openai')
    if not settings.openai_key:
        print(json.dumps({'mode': 'not_run', 'reason': 'provider_not_configured', 'synthetic': True}))
        return 2

    context = synthetic_context()
    started = time.monotonic()
    result = {'provider': 'openai', 'model': settings.openai_model, 'synthetic': True, 'cached': False}
    try:
        ids, model = asyncio.run(select_events(settings, context))
        result.update(mode='ai', model=model, event_ids=ids)
        code = 0
    except Exception as exc:
        # Do not print exception text: provider errors may contain request data.
        reason = 'timeout' if isinstance(exc, TimeoutError) else 'invalid_response' if isinstance(exc, ValueError) else 'provider_error'
        result.update(mode='fallback', reason=reason, event_ids=[item['id'] for item in context['candidates'][:3]])
        code = 1
    result['elapsed_ms'] = round((time.monotonic() - started) * 1000)
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
