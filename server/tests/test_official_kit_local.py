"""Optional local verification; official source files are never copied into Git.

Set CAREER_QUEST_KIT_DIR to the directory containing the four supplied files.
Ordinary CI skips these tests and uses the independent synthetic kit fixtures.
"""

import csv
import io
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db import Activity, Catalog, Employee, ImportRecord, connect
from app.domain.progression import candidates, trajectory
from app.import_service import load_kit
from app.services import hr_overview


@pytest.fixture(scope='module')
def official_sources():
    directory = os.getenv('CAREER_QUEST_KIT_DIR')
    if not directory:
        pytest.skip('CAREER_QUEST_KIT_DIR is not set; official files stay local')
    root = Path(directory)
    filenames = ('employees.json', 'events.json', 'skills.json', 'activity_history.csv')
    assert all((root / filename).is_file() for filename in filenames), 'Kit directory must contain the four original files'
    files = {filename: (root / filename).read_bytes() for filename in filenames}
    sources = {name: json.loads(files[name].decode('utf-8-sig')) for name in filenames if name.endswith('.json')}
    sources['history'] = list(csv.DictReader(io.StringIO(files['activity_history.csv'].decode('utf-8-sig'))))
    return files, sources


@pytest.fixture
def official_database(tmp_path, official_sources):
    files, _ = official_sources
    engine, sessions = connect(f'sqlite:///{tmp_path / "official-local.db"}')
    try:
        with sessions() as db:
            load_kit(db, files)
        yield sessions
    finally:
        engine.dispose()


def independently_replay(sources):
    """Compute the documented assessment/replay result without backend helpers."""
    skills = [item['skill_id'] for item in sources['skills.json']['skills']]
    employees = {item['employee_id']: item for item in sources['employees.json']['employees']}
    events = {item['event_id']: item for item in sources['events.json']['events']}
    expected = {employee_id: {skill_id: employee['skills'].get(skill_id, 0) for skill_id in skills}
                for employee_id, employee in employees.items()}
    for row in sorted(sources['history'], key=lambda item: (item['date'], item['employee_id'], item['event_id'], item['record_id'])):
        employee_id = row['employee_id']
        if row['status'] != 'completed' or row['date'] <= employees[employee_id]['last_review_date']:
            continue
        for effect in events[row['event_id']]['develops_skills']:
            skill_id = effect['skill_id']
            before = expected[employee_id][skill_id]
            after = min(before + effect['gain'], effect['max_level'], 5)
            expected[employee_id][skill_id] = max(before, after)
    return expected


def test_official_full_import_dry_run_write_and_repeat(tmp_path, official_sources):
    files, sources = official_sources
    assert len(sources['employees.json']['employees']) == 200
    assert len(sources['skills.json']['skills']) == 60
    assert len(sources['events.json']['events']) == 40
    assert len(sources['history']) == 2743
    engine, sessions = connect(f'sqlite:///{tmp_path / "official-repeat.db"}')
    try:
        with sessions() as db:
            load_kit(db, files, dry_run=True)
        with sessions() as db:
            assert db.get(Catalog, 1) is None
            for model in (Employee, Activity, ImportRecord):
                assert db.scalar(select(func.count()).select_from(model)) == 0
        with sessions() as db:
            first = load_kit(db, files)
        with sessions() as db:
            profiles = {row.id: row.profile for row in db.scalars(select(Employee))}
            assert len(profiles) == 200
            assert len(db.get(Catalog, 1).payload['skills']) == 60
            assert len(db.get(Catalog, 1).payload['events']) == 40
            assert db.scalar(select(func.count()).select_from(Activity)) == 2743
        with sessions() as db:
            repeated = load_kit(db, files)
        with sessions() as db:
            assert {row.id: row.profile for row in db.scalars(select(Employee))} == profiles
            assert db.scalar(select(func.count()).select_from(Activity)) == 2743
        assert first['employees_added'] == 200
        assert first['history_added'] == 2743
        assert repeated['employees_added'] == repeated['history_added'] == 0
    finally:
        engine.dispose()


def test_official_replay_next_grade_and_eligible_events(official_database, official_sources):
    _, sources = official_sources
    expected = independently_replay(sources)
    raw_employees = {item['employee_id']: item for item in sources['employees.json']['employees']}
    raw_rules = {(item['role'], item['grade']): item for item in sources['skills.json']['role_profiles']}
    grades = ('Junior', 'Middle', 'Senior', 'Lead')
    changed_profiles = 0
    with official_database() as db:
        catalog = db.get(Catalog, 1).payload
        histories = defaultdict(list)
        for item in db.scalars(select(Activity)):
            histories[item.employee_id].append({'id': item.id, 'event_id': item.event_id,
                                               'status': item.status, 'occurred_at': item.occurred_at})
        for row in db.scalars(select(Employee)):
            employee = row.profile
            assert employee['skills'] == expected[row.id]
            raw = raw_employees[row.id]
            if any(expected[row.id][key] != raw['skills'].get(key, 0) for key in expected[row.id]):
                changed_profiles += 1
            assert employee['snapshot_date'] == '2026-10-01'
            assert employee['source_format'] == 'kit-v1'
            path = trajectory(employee, catalog)
            grade_index = grades.index(employee['grade'])
            if grade_index == len(grades) - 1:
                assert path['next_grade'] is None
                assert path['status'] == 'highest_grade'
            else:
                next_grade = grades[grade_index + 1]
                next_rule = raw_rules[(employee['role'], next_grade)]
                assert path['next_grade'] == next_grade
                assert {item['id']: item['required'] for item in path['skills']} == next_rule['required_skills']
                assert {item['id'] for item in path['skills'] if item['critical']} == set(next_rule['critical_skills'])
                assert all(item['level'] == expected[row.id][item['id']] for item in path['skills'])
            completed = {item['event_id'] for item in histories[row.id] if item['status'] == 'completed'}
            for candidate in candidates(employee, catalog, histories[row.id]):
                assert candidate['mandatory'] is False
                assert not candidate['roles'] or employee['role'] in candidate['roles']
                assert not candidate['grades'] or employee['grade'] in candidate['grades']
                assert all(expected[row.id][skill_id] >= minimum for skill_id, minimum in candidate['prerequisites'].items())
                assert candidate['id'] not in completed or candidate['id'] == 'EV_036'
                if candidate['format'] == 'self_paced':
                    assert candidate['session_date'] is None
                else:
                    assert candidate['session_date'] >= '2026-10-01'
                    assert candidate['session_date'] in candidate['upcoming_sessions']
                    assert candidate['occurrence_id'] == candidate['session_date']
    assert changed_profiles > 0, 'The actual kit must exercise completion replay after last review'


def test_official_hr_all_profiles_events_gaps_and_exact_status_counts(official_database, official_sources):
    _, sources = official_sources
    expected_skills = independently_replay(sources)
    next_grades = {'Junior': 'Middle', 'Middle': 'Senior', 'Senior': 'Lead'}
    raw_rules = {(item['role'], item['grade']): item for item in sources['skills.json']['role_profiles']}
    expected_gaps = defaultdict(lambda: {'eligible': 0, 'affected': 0, 'total_gap': 0})
    for employee in sources['employees.json']['employees']:
        if employee['grade'] not in next_grades:
            continue
        rule = raw_rules[(employee['role'], next_grades[employee['grade']])]
        for skill_id, required in rule['required_skills'].items():
            gap = max(0, required - expected_skills[employee['employee_id']][skill_id])
            counts = expected_gaps[skill_id]
            counts['eligible'] += 1
            counts['affected'] += int(gap > 0)
            counts['total_gap'] += gap
    statuses = ('completed', 'no_show', 'declined', 'dropped', 'in_progress', 'overdue')
    expected_participation = Counter((row['event_id'], row['status']) for row in sources['history'])
    with official_database() as db:
        overview = hr_overview(db)
    assert overview['employee_count'] == 200
    assert len(overview['participation']) == 40
    assert {row['id'] for row in overview['gaps']} == set(expected_gaps)
    for row in overview['gaps']:
        counts = expected_gaps[row['id']]
        assert {key: row[key] for key in counts} == counts
        assert row['unknown'] == 0
        assert row['percent'] == round(100 * counts['affected'] / counts['eligible'])
    assert all(row['reason'] and row['reason_detail'] for row in overview['no_step'])
    for row in overview['participation']:
        for status in statuses:
            assert row[status] == expected_participation[(row['id'], status)]
        assert row['missed'] == row['no_show']
    assert sum(row[status] for row in overview['participation'] for status in statuses) == 2743
