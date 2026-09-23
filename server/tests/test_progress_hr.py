import copy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event as sql_event

from app.config import Settings
from app.db import Activity, Catalog, Employee, connect
from app.domain.progression import candidates, development_plan, gain_for, trajectory
from app.main import create_app
from app.services import hr_overview


@pytest.fixture
def development_data():
    employee = {
        'id': 'SYNTHETIC', 'name': 'Synthetic employee', 'role': 'Engineer',
        'grade': 'Middle', 'tenure_months': 12, 'skills': {'DESIGN': 2, 'SPEAK': 1},
    }
    catalog = {
        'skills': [
            {'id': 'DESIGN', 'name': 'System Design', 'kind': 'hard'},
            {'id': 'SPEAK', 'name': 'Public Speaking', 'kind': 'soft'},
        ],
        'grade_rules': [{'role': 'Engineer', 'grade': 'Middle', 'next_grade': 'Senior',
                         'requirements': {'DESIGN': 4, 'SPEAK': 3}}],
        'events': [
            {'id': 'DESIGN_WORKSHOP', 'title': 'Design workshop', 'type': 'workshop',
             'roles': ['Engineer'], 'grades': ['Middle'], 'effects': {'DESIGN': {'gain': 1, 'max_level': 4}}},
            {'id': 'SPEAKING_CLUB', 'title': 'Speaking club', 'type': 'speaking',
             'roles': [], 'grades': [], 'effects': {'SPEAK': {'gain': 1, 'max_level': 4}}},
        ],
    }
    return employee, catalog


def test_lowest_skill_does_not_override_next_grade_and_related_history(development_data):
    employee, catalog = development_data
    previous_speaking = {**catalog['events'][1], 'id': 'PAST_SPEAKING'}
    previous_workshop = {**catalog['events'][0], 'id': 'PAST_WORKSHOP'}
    catalog['events'].extend([previous_speaking, previous_workshop])
    history = [
        {'event_id': 'PAST_SPEAKING', 'status': 'missed'},
        {'event_id': 'PAST_SPEAKING', 'status': 'declined'},
        {'event_id': 'PAST_SPEAKING', 'status': 'missed'},
        {'event_id': 'PAST_WORKSHOP', 'status': 'completed'},
    ]
    assert min(employee['skills'], key=employee['skills'].get) == 'SPEAK'
    options = candidates(employee, catalog, history)
    design = next(item for item in options if item['id'] == 'DESIGN_WORKSHOP')
    speaking = next(item for item in options if item['id'] == 'SPEAKING_CLUB')
    assert options[0]['id'] == 'DESIGN_WORKSHOP'
    assert design['score'] == 1.1
    assert speaking['score'] == 0.55
    assert {entry['factor'] for entry in design['evidence']} == {'grade', 'skill_gap', 'next_level', 'history'}
    assert 'System Design: 2 → 4' in design['evidence'][1]['text']
    assert 'пропусков/отказов 3' in speaking['evidence'][3]['text']
    assert 'PAST_WORKSHOP' not in {item['id'] for item in options}


def test_unknown_skill_and_known_zero_have_distinct_progress_and_gain(development_data):
    employee, catalog = development_data
    employee['skills'] = {'SPEAK': 3}
    unknown = trajectory(employee, catalog)
    assert unknown['coverage'] is None
    assert unknown['status'] == 'missing_skills'
    assert unknown['skills'][0]['level'] is None
    assert unknown['skills'][0]['gap'] is None
    assert candidates(employee, catalog, []) == []
    employee['skills']['DESIGN'] = 0
    known = trajectory(employee, catalog)
    assert known['coverage'] == 43
    assert known['skills'][0]['gap'] == 4
    assert candidates(employee, catalog, [])[0]['changes']['DESIGN']['before'] == 0


def test_gain_above_met_requirement_is_not_counted_as_closing_a_gap(development_data):
    employee, catalog = development_data
    employee['skills']['SPEAK'] = 4
    catalog['events'][0]['effects']['SPEAK'] = {'gain': 1, 'max_level': 5}
    option = candidates(employee, catalog, [])[0]
    assert option['changes']['SPEAK']['after'] == 5
    assert option['benefit'] == 1
    assert option['evidence'][1]['text'] == 'System Design: 2 → 4'


@pytest.mark.parametrize(('level', 'gain', 'maximum', 'expected'), [
    (0, 5, 5, 5), (2, 5, 3, 1), (4, 5, 5, 1),
    (5, 5, 5, 0), (4, 2, 3, 0), (0, 5, 0, 0), (1, 0, 5, 0),
])
def test_gain_limits_at_zero_event_cap_and_global_cap(level, gain, maximum, expected):
    assert gain_for(level, gain, maximum) == expected


def test_audience_completed_and_unrelated_gains_are_ineligible(development_data):
    employee, catalog = development_data
    design = catalog['events'][0]
    catalog['events'] = [
        {**design, 'id': 'WRONG_ROLE', 'roles': ['Analyst']},
        {**design, 'id': 'WRONG_GRADE', 'grades': ['Junior']},
        {**design, 'id': 'DONE'},
        {**design, 'id': 'CAPPED', 'effects': {'DESIGN': {'gain': 2, 'max_level': 2}}},
        {**design, 'id': 'ZERO_GAIN', 'effects': {'DESIGN': {'gain': 0, 'max_level': 5}}},
    ]
    plan = development_plan(employee, catalog, [{'event_id': 'DONE', 'status': 'completed'}])
    assert plan['available'] == []
    assert plan['no_step']['reason'] == 'no_eligible_activity'
    assert plan['no_step']['blockers'] == {'role': 1, 'grade': 1, 'completed': 1, 'skill_cap': 1, 'no_relevant_gain': 1}
    assert 'не подходят по роли' in plan['no_step']['reason_detail']
    assert 'достигнут предел прироста навыка' in plan['no_step']['reason_detail']


def test_no_step_distinguishes_missing_rule_missing_measurement_and_met_requirements(development_data):
    employee, catalog = development_data
    employee['grade'] = 'Senior'
    assert development_plan(employee, catalog, [])['no_step']['reason'] == 'no_grade_rule'
    employee['grade'] = 'Middle'
    employee['skills'] = {'SPEAK': 3}
    unknown = development_plan(employee, catalog, [])['no_step']
    assert unknown['reason'] == 'missing_skills'
    assert 'System Design' in unknown['reason_detail']
    employee['skills']['DESIGN'] = 4
    met = development_plan(employee, catalog, [])
    assert met['trajectory']['coverage'] == 100
    assert met['no_step']['reason'] == 'no_eligible_activity'
    assert 'уже выполнены' in met['no_step']['reason_detail']
    # Coverage is not an automatic grade promotion.
    assert employee['grade'] == 'Middle'


def test_zero_requirement_denominator_is_not_reported_as_completion(development_data):
    employee, catalog = development_data
    catalog['grade_rules'][0]['requirements'] = {'DESIGN': 0}
    plan = development_plan(employee, catalog, [])
    assert plan['trajectory']['coverage'] is None
    assert plan['available'] == []
    assert 'нет положительных требований' in plan['no_step']['reason_detail']


def test_expected_changes_equal_actual_changes_and_preserve_unknowns(tmp_path, development_data):
    employee, catalog = development_data
    employee['skills'] = {'DESIGN': 2, 'SPEAK': 4}
    catalog['skills'].append({'id': 'UNMEASURED', 'name': 'Unmeasured skill', 'kind': 'hard'})
    catalog['grade_rules'][0]['requirements'] = {'DESIGN': 5, 'SPEAK': 5}
    catalog['events'][0]['effects'] = {
        'DESIGN': {'gain': 4, 'max_level': 3},
        'SPEAK': {'gain': 4, 'max_level': 5},
        'UNMEASURED': {'gain': 4, 'max_level': 5},
    }
    settings = Settings(database_url=f'sqlite:///{tmp_path / "actual.db"}', provider='rules', demo_mode=True)
    app = create_app(settings)
    with TestClient(app, headers={'X-Requested-With': 'CareerQuest'}) as client:
        with app.state.sessions() as db:
            row = db.get(Catalog, 1)
            row.payload = {key: [*row.payload[key], *catalog[key]] for key in ('skills', 'grade_rules', 'events')}
            db.add(Employee(id=employee['id'], profile=employee))
            db.commit()
        assert client.post('/api/v1/auth/demo', json={'account': employee['id']}).status_code == 200
        expected = client.get('/api/v1/employees/SYNTHETIC').json()['available'][0]['changes']
        response = client.post('/api/v1/employees/SYNTHETIC/events/DESIGN_WORKSHOP/complete')
        assert response.status_code == 200
        profile = response.json()['profile']
        assert profile['employee']['skills'] == {'DESIGN': 3, 'SPEAK': 5}
        assert profile['history'][0]['changes'] == expected
        assert profile['recommendation'] is None
        assert profile['employee']['grade'] == 'Middle'
        repeat = client.post('/api/v1/employees/SYNTHETIC/events/DESIGN_WORKSHOP/complete').json()
        assert repeat['already_completed'] is True
        assert repeat['profile']['employee']['skills'] == profile['employee']['skills']


def test_full_synthetic_hr_dataset_aggregates_unknowns_participation_and_uses_three_queries(tmp_path, development_data):
    employee, catalog = development_data
    # 2,000 synthetic employees: the maximum size of a demo-v1 employee bundle.
    # Only the design event is available to Engineers in this fixture.
    catalog['events'][1]['roles'] = ['Presenter']
    engine, sessions = connect(f'sqlite:///{tmp_path / "hr.db"}')
    try:
        with sessions() as db:
            db.add(Catalog(id=1, payload=catalog))
            for index in range(2000):
                profile = copy.deepcopy(employee)
                profile['id'] = f'SYN_{index:04d}'
                profile['name'] = f'Synthetic {index:04d}'
                cohort = index // 500
                profile['skills'] = {'DESIGN': 2, 'SPEAK': 0} if cohort == 0 else {'SPEAK': 0}
                if cohort >= 2:
                    profile['skills'] = {'DESIGN': 4, 'SPEAK': 3}
                if cohort == 3:
                    profile['grade'] = 'Senior'
                db.add(Employee(id=profile['id'], profile=profile))
            db.flush()
            for index in range(1500):
                status = ('missed', 'declined', 'completed')[index // 500]
                db.add(Activity(id=f'H_{index:04d}', employee_id=f'SYN_{index:04d}',
                                event_id='DESIGN_WORKSHOP', status=status, occurred_at='2026-01-01', changes=None))
            db.commit()
        queries = []

        def count_queries(_connection, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith('SELECT'):
                queries.append(statement)

        sql_event.listen(engine, 'before_cursor_execute', count_queries)
        with sessions() as db:
            overview = hr_overview(db)
        assert len(queries) == 3
        assert overview['employee_count'] == 2000
        by_skill = {gap['id']: gap for gap in overview['gaps']}
        assert by_skill['DESIGN'] == {
            'id': 'DESIGN', 'name': 'System Design', 'affected': 500, 'eligible': 1000,
            'unknown': 500, 'total_gap': 1000, 'percent': 50,
        }
        assert by_skill['SPEAK']['eligible'] == 1500
        assert by_skill['SPEAK']['affected'] == 1000
        assert by_skill['SPEAK']['unknown'] == 0
        assert by_skill['SPEAK']['percent'] == 67
        assert len(overview['no_step']) == 1500
        assert sum(row['reason'] == 'missing_skills' for row in overview['no_step']) == 500
        assert sum(row['reason'] == 'no_grade_rule' for row in overview['no_step']) == 500
        participation = {row['id']: row for row in overview['participation']}
        assert participation['DESIGN_WORKSHOP']['completed'] == 500
        assert participation['DESIGN_WORKSHOP']['missed'] == 500
        assert participation['DESIGN_WORKSHOP']['declined'] == 500
        assert participation['SPEAKING_CLUB']['completed'] == 0
    finally:
        engine.dispose()


@pytest.fixture
def kit_development_data(development_data):
    """Own synthetic normalized records, following the official documented rules."""
    employee, catalog = development_data
    employee.update(source_format='kit-v1', snapshot_date='2026-10-01')
    employee['skills'] = {'DESIGN': 2, 'SPEAK': 0}
    catalog['grade_rules'][0]['critical_skills'] = ['DESIGN']
    catalog['grade_rules'][0]['requirements'] = {'DESIGN': 4, 'SPEAK': 1}
    for item in catalog['events']:
        item.update(source_format='kit-v1', mandatory=False, prerequisites={},
                    format='online', upcoming_sessions=['2026-10-01', '2026-10-15'], repeatable=False)
    catalog['events'][0]['prerequisites'] = {'DESIGN': 2}
    catalog['events'][1]['id'] = 'EV_036'
    catalog['events'][1]['repeatable'] = True
    return employee, catalog


def test_kit_missing_skills_are_zero_and_critical_requirement_is_explicit(kit_development_data):
    employee, catalog = kit_development_data
    del employee['skills']['SPEAK']
    path = trajectory(employee, catalog)
    assert path['status'] == 'ready'
    assert path['coverage'] == 40
    assert path['critical_requirements_met'] is False
    speaking = next(item for item in path['skills'] if item['id'] == 'SPEAK')
    assert speaking['level'] == 0 and speaking['gap'] == 1
    assert speaking['critical'] is False
    assert candidates(employee, catalog, [])[1]['changes']['SPEAK']['before'] == 0
    employee['skills']['DESIGN'] = 4
    assert trajectory(employee, catalog)['critical_requirements_met'] is True
    assert trajectory(employee, catalog)['coverage'] == 80
    assert employee['grade'] == 'Middle'


def test_kit_lead_is_highest_grade_not_an_unconfigured_grade(kit_development_data):
    employee, catalog = kit_development_data
    employee['grade'] = 'Lead'
    plan = development_plan(employee, catalog, [])
    assert plan['trajectory']['next_grade'] is None
    assert plan['trajectory']['coverage'] is None
    assert plan['trajectory']['status'] == 'highest_grade'
    assert plan['no_step']['reason'] == 'highest_grade'
    assert 'высший грейд' in plan['no_step']['reason_detail']


def test_kit_critical_gap_ranking_and_exact_participation_evidence(kit_development_data):
    employee, catalog = kit_development_data
    history = [{'event_id': 'EV_036', 'status': status, 'occurred_at': '2026-09-01'}
               for status in ('no_show', 'declined', 'dropped', 'in_progress')]
    options = candidates(employee, catalog, history)
    assert options[0]['id'] == 'DESIGN_WORKSHOP'
    assert options[0]['critical_benefit'] == 1
    assert options[0]['benefit'] == 1
    assert options[0]['score'] == 2
    assert options[1]['id'] == 'EV_036'
    assert options[1]['score'] == 0.55
    evidence = options[1]['evidence'][3]['text']
    assert 'неявок 1' in evidence and 'отказов 1' in evidence
    assert 'прервано 1' in evidence and 'в процессе 1' in evidence


@pytest.mark.parametrize(('changes', 'blocker'), [
    ({'mandatory': True}, 'mandatory'),
    ({'prerequisites': {'DESIGN': 3}}, 'prerequisites'),
    ({'prerequisites': {'MISSING': 1}}, 'prerequisites'),
    ({'upcoming_sessions': []}, 'no_upcoming_session'),
    ({'upcoming_sessions': ['2026-09-30']}, 'no_upcoming_session'),
    ({'roles': ['Analyst']}, 'role'),
    ({'grades': ['Senior']}, 'grade'),
])
def test_kit_mandatory_prerequisites_audience_and_schedule(kit_development_data, changes, blocker):
    employee, catalog = kit_development_data
    catalog['events'] = [catalog['events'][0]]
    catalog['events'][0].update(changes)
    plan = development_plan(employee, catalog, [])
    assert plan['available'] == []
    assert plan['no_step']['blockers'] == {blocker: 1}
    assert plan['no_step']['reason_detail']


def test_kit_self_paced_and_snapshot_session_boundary(kit_development_data):
    employee, catalog = kit_development_data
    scheduled = candidates(employee, catalog, [])[0]
    assert scheduled['session_date'] == '2026-10-01'
    assert scheduled['occurrence_id'] == '2026-10-01'
    catalog['events'][0].update(format='self_paced', upcoming_sessions=[])
    self_paced = candidates(employee, catalog, [])[0]
    assert self_paced['session_date'] is None
    assert self_paced['occurrence_id'] is None


def test_kit_recurring_club_selects_next_uncompleted_occurrence(kit_development_data):
    employee, catalog = kit_development_data
    catalog['events'] = [catalog['events'][1]]
    catalog['grade_rules'][0]['requirements']['SPEAK'] = 4
    history = [{'id': 'PAST', 'event_id': 'EV_036', 'status': 'completed', 'occurred_at': '2026-09-01'}]
    first = candidates(employee, catalog, history)[0]
    assert first['occurrence_id'] == '2026-10-01'
    history.append({'id': 'FIRST', 'event_id': 'EV_036', 'status': 'completed', 'occurred_at': first['occurrence_id']})
    second = candidates(employee, catalog, history)[0]
    assert second['occurrence_id'] == '2026-10-15'
    history.append({'id': 'SECOND', 'event_id': 'EV_036', 'status': 'completed', 'occurred_at': second['occurrence_id']})
    assert candidates(employee, catalog, history) == []
    assert development_plan(employee, catalog, history)['no_step']['blockers'] == {'no_upcoming_session': 1}


def test_kit_completed_nonrecurring_and_self_paced_events_cannot_repeat(kit_development_data):
    employee, catalog = kit_development_data
    history = [{'event_id': 'DESIGN_WORKSHOP', 'status': 'completed', 'occurred_at': '2026-09-01'}]
    catalog['events'][0]['repeatable'] = True  # Only the documented club is repeatable.
    assert 'DESIGN_WORKSHOP' not in {item['id'] for item in candidates(employee, catalog, history)}
    catalog['events'][1].update(format='self_paced', upcoming_sessions=[])
    history.append({'event_id': 'EV_036', 'status': 'completed', 'occurred_at': '2026-09-01'})
    assert candidates(employee, catalog, history) == []


def test_kit_hr_preserves_all_statuses_and_legacy_missed_aggregate(tmp_path, kit_development_data):
    employee, catalog = kit_development_data
    engine, sessions = connect(f'sqlite:///{tmp_path / "kit_hr.db"}')
    try:
        with sessions() as db:
            db.add(Catalog(id=1, payload=catalog))
            db.add(Employee(id=employee['id'], profile=employee))
            db.flush()
            statuses = ['completed', 'no_show', 'no_show', 'declined', 'dropped', 'in_progress', 'overdue']
            for index, status in enumerate(statuses):
                db.add(Activity(id=f'H_{index}', employee_id=employee['id'], event_id='EV_036',
                                status=status, occurred_at='2026-09-01', changes=None))
            db.commit()
        with sessions() as db:
            overview = hr_overview(db)
        counts = next(row for row in overview['participation'] if row['id'] == 'EV_036')
        assert counts['completed'] == 1
        assert counts['no_show'] == counts['missed'] == 2
        assert counts['declined'] == counts['dropped'] == counts['in_progress'] == counts['overdue'] == 1
        assert overview['employee_count'] == 1
        assert overview['no_step'] == []  # HR includes occurrence dates when evaluating the recurring club.
    finally:
        engine.dispose()
