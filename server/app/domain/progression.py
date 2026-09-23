from collections import Counter, defaultdict


# Invalidate persisted recommendations when deterministic calculations change.
DOMAIN_VERSION = 'kit-progression-v3'


def gain_for(level: int, gain: int, max_level: int) -> int:
    return max(0, min(gain, max_level - level, 5 - level))


def skill_level(employee: dict, skill_id: str) -> int | None:
    # Only the official README defines an absent skill as zero. demo-v1 keeps
    # its existing unknown-value semantics.
    default = 0 if employee.get('source_format') == 'kit-v1' else None
    return employee['skills'].get(skill_id, default)


def trajectory(employee: dict, catalog: dict) -> dict:
    rule = next((r for r in catalog['grade_rules'] if r['role'] == employee['role'] and r['grade'] == employee['grade']), None)
    names = {s['id']: s['name'] for s in catalog['skills']}
    if not rule:
        status = 'highest_grade' if employee.get('source_format') == 'kit-v1' and employee['grade'] == 'Lead' else 'no_grade_rule'
        return {'next_grade': None, 'coverage': None, 'skills': [], 'status': status, 'critical_requirements_met': None}
    items = []
    critical = set(rule.get('critical_skills', []))
    for skill_id, required in rule['requirements'].items():
        level = skill_level(employee, skill_id)
        items.append({'id': skill_id, 'name': names[skill_id], 'level': level, 'required': required, 'gap': max(0, required - level) if level is not None else None, 'critical': skill_id in critical})
    denominator = sum(x['required'] for x in items)
    known = all(x['level'] is not None for x in items)
    coverage = round(100 * sum(min(x['level'], x['required']) for x in items) / denominator) if denominator and known else None
    critical_items = [item for item in items if item['critical']]
    critical_met = all(item['gap'] == 0 for item in critical_items) if critical_items and all(item['gap'] is not None for item in critical_items) else None
    return {'next_grade': rule['next_grade'], 'coverage': coverage, 'skills': items, 'status': 'ready' if known else 'missing_skills', 'critical_requirements_met': critical_met}


def event_changes(employee: dict, event: dict, names: dict[str, str]) -> dict:
    """Expected changes; completion persists these same server-calculated values.

    An unmeasured skill has no calculable gain. In particular, it is never
    initialized to zero by attending an event with an effect on that skill.
    """
    changes = {}
    for skill_id, effect in event['effects'].items():
        level = skill_level(employee, skill_id)
        if level is None:
            continue
        delta = gain_for(level, effect['gain'], effect['max_level'])
        if delta:
            changes[skill_id] = {'name': names[skill_id], 'before': level, 'after': level + delta, 'gain': delta}
    return changes


def _history_group(event: dict) -> tuple:
    return event['type'], event.get('format') if event.get('source_format') == 'kit-v1' else None


def _next_session(employee: dict, event: dict, history: list[dict]) -> str | None:
    """Choose one actionable occurrence; the official snapshot is simulation today."""
    cutoff = employee['snapshot_date']
    completed_dates = [item['occurred_at'] for item in history
                       if item['event_id'] == event['id'] and item['status'] == 'completed']
    last_completed = max(completed_dates, default='')
    return next((session for session in sorted(event['upcoming_sessions'])
                 if session >= cutoff and session > last_completed), None)


def _rank_candidates(employee: dict, catalog: dict, history: list[dict], path: dict) -> tuple[list[dict], dict]:
    gaps = {x['id']: x['gap'] for x in path['skills'] if x['gap'] is not None}
    unknown = {x['id'] for x in path['skills'] if x['gap'] is None}
    critical = {item['id'] for item in path['skills'] if item['critical']}
    completed = {h['event_id'] for h in history if h['status'] == 'completed'}
    names = {s['id']: s['name'] for s in catalog['skills']}
    event_types = {event['id']: _history_group(event) for event in catalog['events']}
    history_by_type = defaultdict(Counter)
    for item in history:
        event_type = event_types.get(item['event_id'])
        if event_type is not None:
            history_by_type[event_type][item['status']] += 1
    result = []
    blockers = Counter()
    for event in catalog['events']:
        official = event.get('source_format') == 'kit-v1'
        repeatable = official and event['id'] == 'EV_036' and event.get('repeatable', False) and event.get('format') != 'self_paced'
        if official and event['mandatory']:
            blockers['mandatory'] += 1
            continue
        if event['id'] in completed and not repeatable:
            blockers['completed'] += 1
            continue
        if event['roles'] and employee['role'] not in event['roles']:
            blockers['role'] += 1
            continue
        if event['grades'] and employee['grade'] not in event['grades']:
            blockers['grade'] += 1
            continue
        session_date = None
        if official:
            if any(skill_level(employee, skill_id) is None or skill_level(employee, skill_id) < minimum
                   for skill_id, minimum in event['prerequisites'].items()):
                blockers['prerequisites'] += 1
                continue
            if event['format'] != 'self_paced':
                session_date = _next_session(employee, event, history)
                if session_date is None:
                    blockers['no_upcoming_session'] += 1
                    continue
        changes = event_changes(employee, event, names)
        benefit = sum(min(change['gain'], gaps.get(skill_id, 0)) for skill_id, change in changes.items())
        if not benefit:
            if any(skill_id in unknown and effect['gain'] > 0 and effect['max_level'] > 0 for skill_id, effect in event['effects'].items()):
                blockers['unknown_skill'] += 1
            elif any(gaps.get(skill_id, 0) > 0 and effect['gain'] > 0 for skill_id, effect in event['effects'].items()):
                blockers['skill_cap'] += 1
            else:
                blockers['no_relevant_gain'] += 1
            continue
        related = history_by_type[_history_group(event)]
        skipped = related['missed'] + related['no_show'] + related['declined'] + related['dropped']
        successes = related['completed']
        critical_benefit = sum(min(change['gain'], gaps.get(skill_id, 0)) for skill_id, change in changes.items() if skill_id in critical)
        # Critical skills are explicitly promotion-relevant in the kit. Giving
        # their gap reduction double weight is an advisory ranking choice, not
        # an organizer-defined progress formula or an automatic promotion.
        weighted_benefit = benefit + critical_benefit
        score = weighted_benefit * max(0.35, 1 - skipped * 0.15) + min(successes, 3) * 0.1
        requirement_text = '; '.join(f"{x['name']}: {x['level']} → {x['required']}" for x in path['skills'] if x['id'] in changes and x['gap'] is not None and x['gap'] > 0)
        evidence = [
            {'factor': 'grade', 'text': f"{employee['role']}, {employee['grade']} → {path['next_grade']}"},
            {'factor': 'skill_gap', 'text': requirement_text},
            {'factor': 'next_level', 'text': f"Активность закрывает {benefit} ур. разрыва по требованиям {path['next_grade']}."},
            {'factor': 'history', 'text': f"В формате «{event['type']}»: завершено {successes}, пропусков/отказов {skipped}." if related else 'Истории участия в этом формате пока нет; предпочтения неизвестны.'},
        ]
        if official:
            evidence[2]['text'] += f' Из них по критическим навыкам: {critical_benefit}.'
            evidence[3]['text'] = (
                f"Тип «{event['type']}», формат «{event['format']}»: завершено {successes}, "
                f"неявок {related['no_show']}, отказов {related['declined']}, прервано {related['dropped']}, "
                f"в процессе {related['in_progress']}, просрочено {related['overdue']}."
                if related else 'Истории участия в этом типе и формате пока нет; предпочтения неизвестны.'
            )
        result.append({**event, 'changes': changes, 'benefit': benefit, 'critical_benefit': critical_benefit,
                       'score': round(score, 3), 'evidence': evidence,
                       **({'occurrence_id': session_date, 'session_date': session_date} if official else {})})
    return sorted(result, key=lambda x: (-x['score'], x['id'])), dict(blockers)


def candidates(employee: dict, catalog: dict, history: list[dict]) -> list[dict]:
    return _rank_candidates(employee, catalog, history, trajectory(employee, catalog))[0]


def development_plan(employee: dict, catalog: dict, history: list[dict]) -> dict:
    """Profile calculations plus actionable, additive HR no-step diagnostics."""
    path = trajectory(employee, catalog)
    options, blockers = _rank_candidates(employee, catalog, history, path)
    no_step = None
    if not options:
        reason = path['status'] if path['status'] != 'ready' else 'no_eligible_activity'
        if reason == 'highest_grade':
            detail = 'Lead — высший грейд в официальном наборе; требования следующего грейда отсутствуют.'
        elif reason == 'no_grade_rule':
            detail = 'Не заданы требования следующего грейда для этой роли и текущего грейда.'
        elif reason == 'missing_skills':
            missing = ', '.join(item['name'] for item in path['skills'] if item['level'] is None)
            detail = f'Неизвестны уровни навыков: {missing}. Доступного шага по известным разрывам нет.'
        elif not any(item['required'] > 0 for item in path['skills']):
            detail = 'В правиле следующего грейда нет положительных требований; прогресс не вычисляется.'
        elif all(item['gap'] == 0 for item in path['skills']):
            detail = 'Все известные требования следующего грейда по навыкам уже выполнены.'
        elif not catalog['events']:
            detail = 'Каталог активностей пуст.'
        else:
            labels = {
                'completed': 'уже завершены',
                'role': 'не подходят по роли',
                'grade': 'не подходят по текущему грейду',
                'unknown_skill': 'требуют уточнения навыков',
                'skill_cap': 'достигнут предел прироста навыка',
                'no_relevant_gain': 'не закрывают известные разрывы следующего грейда',
                'mandatory': 'обязательные назначения HR не входят в рекомендации',
                'prerequisites': 'не выполнены предварительные требования',
                'no_upcoming_session': 'нет доступной будущей сессии',
            }
            detail = 'Нет доступной активности: ' + '; '.join(f'{labels[key]} — {count}' for key, count in sorted(blockers.items())) + '.'
        no_step = {'reason': reason, 'reason_detail': detail, 'blockers': blockers}
    return {'trajectory': path, 'available': options, 'no_step': no_step}
