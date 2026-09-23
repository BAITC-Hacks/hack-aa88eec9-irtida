def gain_for(level: int, gain: int, max_level: int) -> int:
    return max(0, min(gain, max_level - level, 5 - level))


def trajectory(employee: dict, catalog: dict) -> dict:
    rule = next((r for r in catalog['grade_rules'] if r['role'] == employee['role'] and r['grade'] == employee['grade']), None)
    names = {s['id']: s['name'] for s in catalog['skills']}
    if not rule:
        return {'next_grade': None, 'coverage': None, 'skills': [], 'status': 'no_grade_rule'}
    items = []
    for skill_id, required in rule['requirements'].items():
        level = employee['skills'].get(skill_id)
        items.append({'id': skill_id, 'name': names[skill_id], 'level': level, 'required': required, 'gap': max(0, required - level) if level is not None else None})
    denominator = sum(x['required'] for x in items)
    known = all(x['level'] is not None for x in items)
    coverage = round(100 * sum(min(x['level'], x['required']) for x in items) / denominator) if denominator and known else None
    return {'next_grade': rule['next_grade'], 'coverage': coverage, 'skills': items, 'status': 'ready' if known else 'missing_skills'}


def candidates(employee: dict, catalog: dict, history: list[dict]) -> list[dict]:
    path = trajectory(employee, catalog)
    gaps = {x['id']: x['gap'] for x in path['skills'] if x['gap'] is not None}
    completed = {h['event_id'] for h in history if h['status'] == 'completed'}
    names = {s['id']: s['name'] for s in catalog['skills']}
    result = []
    for event in catalog['events']:
        if event['id'] in completed or (event['roles'] and employee['role'] not in event['roles']) or (event['grades'] and employee['grade'] not in event['grades']):
            continue
        changes = {}
        benefit = 0
        for skill_id, effect in event['effects'].items():
            level = employee['skills'].get(skill_id)
            if level is None:
                continue  # Unknown is not zero.
            delta = gain_for(level, effect['gain'], effect['max_level'])
            if delta:
                changes[skill_id] = {'name': names[skill_id], 'before': level, 'after': level + delta, 'gain': delta}
                benefit += min(delta, gaps.get(skill_id, 0))
        if not benefit:
            continue
        related_ids = {e['id'] for e in catalog['events'] if e['type'] == event['type']}
        related = [h for h in history if h['event_id'] in related_ids]
        skipped = sum(h['status'] in {'missed', 'declined'} for h in related)
        successes = sum(h['status'] == 'completed' for h in related)
        score = benefit * max(0.35, 1 - skipped * 0.15) + min(successes, 3) * 0.1
        requirement_text = '; '.join(f"{x['name']}: {x['level']} → {x['required']}" for x in path['skills'] if x['id'] in changes)
        evidence = [
            {'factor': 'grade', 'text': f"{employee['role']}, {employee['grade']} → {path['next_grade']}"},
            {'factor': 'skill_gap', 'text': requirement_text},
            {'factor': 'next_level', 'text': f"Активность закрывает {benefit} ур. разрыва по требованиям {path['next_grade']}."},
            {'factor': 'history', 'text': f"В формате «{event['type']}»: завершено {successes}, пропусков/отказов {skipped}." if related else 'Истории участия в этом формате пока нет; предпочтения неизвестны.'},
        ]
        result.append({**event, 'changes': changes, 'benefit': benefit, 'score': round(score, 3), 'evidence': evidence})
    return sorted(result, key=lambda x: (-x['score'], x['id']))
