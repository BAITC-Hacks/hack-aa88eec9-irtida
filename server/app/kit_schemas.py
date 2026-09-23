"""The supplied Career Quest 1.0 kit contract, independent of demo-v1."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, field_validator, model_validator

from .schemas import HistoryInput, Identifier, Level, Role, StrictModel

SNAPSHOT_DATE = date(2026, 10, 1)
HISTORY_START = date(2024, 10, 1)
HISTORY_END = date(2026, 9, 30)
GRADE_ORDER = ('Junior', 'Middle', 'Senior', 'Lead')
KitGrade = Literal['Junior', 'Middle', 'Senior', 'Lead']
KitDate = Annotated[date, BeforeValidator(HistoryInput.canonical_date)]
Percent = Annotated[int, Field(strict=True, ge=0, le=100)]


class KitMeta(StrictModel):
    dataset: Literal['Career Quest']
    version: Literal['1.0']
    as_of_date: KitDate

    @field_validator('as_of_date')
    @classmethod
    def snapshot_date(cls, value):
        if value != SNAPSHOT_DATE:
            raise ValueError('The supplied kit snapshot date must be 2026-10-01')
        return value


class KitSkill(StrictModel):
    skill_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    type: Literal['hard', 'soft']
    category: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=5000)


class KitRoleProfile(StrictModel):
    role: Role
    grade: KitGrade
    required_skills: dict[Identifier, Level]
    critical_skills: list[Identifier]

    @field_validator('critical_skills')
    @classmethod
    def unique_critical_skills(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('Duplicate critical skill')
        return value


class KitSkillsFile(StrictModel):
    meta: KitMeta
    proficiency_scale: dict[str, str]
    skills: list[KitSkill] = Field(max_length=1000)
    role_profiles: list[KitRoleProfile] = Field(max_length=1000)

    @field_validator('proficiency_scale')
    @classmethod
    def all_levels(cls, value):
        if set(value) != {str(level) for level in range(6)}:
            raise ValueError('Proficiency scale must define levels 0 through 5')
        return value


class CareerGoal(StrictModel):
    target_role: Role
    target_grade: KitGrade


class KitEmployee(StrictModel):
    employee_id: Identifier
    full_name: str = Field(min_length=1, max_length=200)
    department: str = Field(min_length=1, max_length=200)
    role: Role
    grade: KitGrade
    manager_id: Identifier | None
    hire_date: KitDate
    tenure_months: int = Field(strict=True, ge=0, le=1200)
    work_format: Literal['office', 'hybrid', 'remote']
    preferred_language: Literal['kk', 'ru', 'en']
    career_goal: CareerGoal | None
    skills: dict[Identifier, Level]
    last_review_date: KitDate

    @model_validator(mode='after')
    def dates_and_tenure(self):
        if not self.hire_date <= self.last_review_date <= SNAPSHOT_DATE:
            raise ValueError('hire_date <= last_review_date <= 2026-10-01 is required')
        months = (SNAPSHOT_DATE.year - self.hire_date.year) * 12 + SNAPSHOT_DATE.month - self.hire_date.month - (SNAPSHOT_DATE.day < self.hire_date.day)
        if self.tenure_months != months:
            raise ValueError('tenure_months must equal full months from hire_date to 2026-10-01')
        return self


class KitEmployeesFile(StrictModel):
    meta: KitMeta
    employees: list[KitEmployee] = Field(max_length=2000)


class KitSkillEffect(StrictModel):
    skill_id: Identifier
    gain: int = Field(strict=True, ge=0)
    max_level: Level


class KitEvent(StrictModel):
    event_id: Identifier
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(max_length=10000)
    type: Literal['compliance', 'onboarding', 'course', 'workshop', 'mentoring', 'certification', 'meetup']
    format: Literal['online', 'offline', 'self_paced']
    duration_hours: float = Field(strict=True, gt=0, le=100000, allow_inf_nan=False)
    mandatory: bool = Field(strict=True)
    target_roles: list[Role] = Field(max_length=100)
    target_grades: list[KitGrade] = Field(max_length=4)
    develops_skills: list[KitSkillEffect] = Field(max_length=1000)
    prerequisites: dict[Identifier, Level]
    upcoming_sessions: list[KitDate] = Field(max_length=1000)

    @field_validator('target_roles', 'target_grades', 'upcoming_sessions')
    @classmethod
    def unique_values(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('Duplicate list entry')
        return value

    @field_validator('develops_skills')
    @classmethod
    def unique_effects(cls, value):
        if len(value) != len({effect.skill_id for effect in value}):
            raise ValueError('Duplicate develops_skills skill_id')
        return value

    @model_validator(mode='after')
    def sessions(self):
        if self.format == 'self_paced' and self.upcoming_sessions:
            raise ValueError('self_paced events must have no upcoming_sessions')
        if any(day < SNAPSHOT_DATE for day in self.upcoming_sessions):
            raise ValueError('upcoming_sessions must be on or after 2026-10-01')
        return self


class KitEventsFile(StrictModel):
    meta: KitMeta
    events: list[KitEvent] = Field(max_length=1000)


class KitHistory(StrictModel):
    record_id: Identifier
    employee_id: Identifier
    event_id: Identifier
    date: KitDate
    due_date: KitDate | None
    status: Literal['completed', 'in_progress', 'dropped', 'no_show', 'declined', 'overdue']
    completion_pct: Percent
    score: Percent | None
    feedback_rating: Annotated[int, Field(strict=True, ge=1, le=5)] | None
    assigned_by: Literal['self', 'manager', 'hr']

    @model_validator(mode='after')
    def status_and_dates(self):
        if not HISTORY_START <= self.date <= HISTORY_END:
            raise ValueError('History date must be within 2024-10-01 through 2026-09-30')
        ranges = {'completed': (100, 100), 'in_progress': (0, 95), 'dropped': (5, 95), 'no_show': (0, 0), 'declined': (0, 0), 'overdue': (0, 95)}
        low, high = ranges[self.status]
        if not low <= self.completion_pct <= high:
            raise ValueError(f'completion_pct for {self.status} must be {low}..{high}')
        if self.due_date is not None and self.due_date < self.date:
            raise ValueError('due_date cannot precede date')
        if self.status == 'overdue' and (self.due_date is None or self.due_date >= SNAPSHOT_DATE):
            raise ValueError('overdue requires due_date before 2026-10-01')
        if self.status == 'declined' and self.assigned_by == 'self':
            raise ValueError('declined is an assignment from manager or hr')
        return self
