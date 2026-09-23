"""Map the current, authorized Career Quest snapshot to NVIDIA practice advice.

The database remains authoritative for skill levels and eligible activities.  No
source Kit files or employee history are reread, and this module makes no API call.
"""

from dataclasses import dataclass
from datetime import date

if __package__.startswith('server.'):
    from server.nvidia_career_ai import CareerFramework, EmployeeContext, PersonalizationError
else:
    from nvidia_career_ai import CareerFramework, EmployeeContext, PersonalizationError

from ..domain.progression import candidates, trajectory


@dataclass(frozen=True)
class SnapshotFrameworkProvider:
    framework: CareerFramework

    def load_framework(self) -> CareerFramework:
        return self.framework


def prepare_personalization(
    employee: dict, catalog: dict, history: list[dict]
) -> tuple[SnapshotFrameworkProvider, EmployeeContext, set[str]]:
    """Prepare one request from the *current* DB profile and official Kit catalog.

    The existing progression service defines eligibility, including participation
    history.  The practice module may narrow that list but cannot expand it.
    """
    if employee.get('source_format') != 'kit-v1' or catalog.get('source_format') != 'kit-v1':
        raise PersonalizationError('kit_required')
    if any(event.get('source_format') != 'kit-v1' for event in catalog.get('events', [])):
        raise PersonalizationError('kit_required')

    path = trajectory(employee, catalog)
    allowed = {event['id'] for event in candidates(employee, catalog, history)}
    snapshot = date.fromisoformat(catalog.get('snapshot_date') or employee['snapshot_date'])
    skills = {
        skill['id']: {
            'skill_id': skill['id'],
            'name': skill['name'],
            'description': skill.get('description', ''),
        }
        for skill in catalog['skills']
    }
    profiles = {
        (profile['role'], profile['grade']): profile.copy()
        for profile in catalog.get('role_profiles', [])
    }
    # The original Kit has all 32 profiles.  Keep imported next-grade rules
    # authoritative if a compatible catalog lacks an original profile.
    for rule in catalog['grade_rules']:
        profiles.setdefault((rule['role'], rule['next_grade']), {
            'role': rule['role'],
            'grade': rule['next_grade'],
            'required_skills': rule['requirements'],
            'critical_skills': rule.get('critical_skills', []),
        })
    profiles.setdefault((employee['role'], employee['grade']), {
        'role': employee['role'], 'grade': employee['grade'],
        'required_skills': {}, 'critical_skills': [],
    })
    events = {}
    for event in catalog['events']:
        event_id = event['id']
        events[event_id] = {
            'event_id': event_id,
            'title': event['title'],
            'description': event.get('description', ''),
            'type': event['type'],
            'format': event['format'],
            'duration_hours': event['duration_hours'],
            'mandatory': event['mandatory'],
            # Keep every event ID for completed-history validation.  Only IDs
            # already approved by the host's multi-factor policy have audience.
            'target_roles': event['roles'] if event_id in allowed else [],
            'target_grades': event['grades'],
            'prerequisites': event['prerequisites'],
            'develops_skills': [
                {'skill_id': skill_id, **effect}
                for skill_id, effect in event['effects'].items()
            ],
            'upcoming_sessions': [date.fromisoformat(value) for value in event['upcoming_sessions']],
        }
    framework = CareerFramework(snapshot, skills, profiles, events)
    completed = [
        {'eventId': record['event_id'], 'completedAt': record['occurred_at']}
        for record in history if record['status'] == 'completed'
    ]
    context = EmployeeContext.model_validate({
        'userId': employee['id'],
        'currentRole': employee['role'],
        'currentGrade': employee['grade'],
        'targetRole': employee['role'],
        'targetGrade': path['next_grade'],
        'skills': [
            {'skillId': skill_id, 'level': level}
            for skill_id, level in employee['skills'].items()
        ],
        'completedQuests': completed,
        'language': employee.get('preferred_language', 'ru'),
        'skillsState': 'current',
    })
    return SnapshotFrameworkProvider(framework), context, allowed
