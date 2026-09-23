from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')]
Level = Annotated[int, Field(strict=True, ge=0, le=5)]


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError('Must contain a non-whitespace character')
    return value


Role = Annotated[str, Field(min_length=1, max_length=100), AfterValidator(nonblank)]
Grade = Annotated[str, Field(min_length=1, max_length=50), AfterValidator(nonblank)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class EmployeeInput(StrictModel):
    id: Identifier
    name: str = Field(min_length=1, max_length=100)
    role: Role
    grade: Grade
    tenure_months: int = Field(strict=True, ge=0, le=1200)
    skills: dict[Identifier, Level]


class SkillInput(StrictModel):
    id: Identifier
    name: str = Field(min_length=1, max_length=100)
    kind: Literal['hard', 'soft']


class Effect(StrictModel):
    gain: int = Field(strict=True, ge=0, le=5)
    max_level: Level


class EventInput(StrictModel):
    id: Identifier
    title: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=50)
    roles: list[Role] = Field(max_length=50)
    grades: list[Grade] = Field(max_length=20)
    effects: dict[Identifier, Effect]

    @field_validator('roles', 'grades')
    @classmethod
    def unique_audience(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('Duplicate audience entry')
        return values


class GradeRule(StrictModel):
    role: Role
    grade: Grade
    next_grade: Grade
    requirements: dict[Identifier, Level]


class HistoryInput(StrictModel):
    id: Identifier
    employee_id: Identifier
    event_id: Identifier
    status: Literal['completed', 'missed', 'declined']
    occurred_at: date

    @field_validator('occurred_at', mode='before')
    @classmethod
    def canonical_date(cls, value):
        # No timestamps or numeric epoch coercion in the documented demo format.
        if type(value) is date:
            return value
        if isinstance(value, str):
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                pass
            else:
                if parsed.isoformat() == value:
                    return parsed
        raise ValueError('Expected a valid calendar date in YYYY-MM-DD format')


class DatasetBundle(StrictModel):
    schema_version: Literal['demo-v1'] = 'demo-v1'
    employees: list[EmployeeInput] = Field(default_factory=list, max_length=2000)
    skills: list[SkillInput] = Field(default_factory=list, max_length=1000)
    events: list[EventInput] = Field(default_factory=list, max_length=1000)
    grade_rules: list[GradeRule] = Field(default_factory=list, max_length=200)
    history: list[HistoryInput] = Field(default_factory=list, max_length=100000)

    @model_validator(mode='after')
    def nonempty_bundle(self):
        # Exact repeats are idempotent; conflicting repeats are reported by the
        # importer with the precise source path, before any rows are written.
        if not any((self.employees, self.skills, self.events, self.grade_rules, self.history)):
            raise ValueError('Empty bundle')
        return self


class DemoLogin(StrictModel):
    account: Identifier


class Selection(StrictModel):
    event_ids: list[Identifier] = Field(min_length=1, max_length=3)

    @model_validator(mode='after')
    def no_duplicates(self):
        if len(self.event_ids) != len(set(self.event_ids)):
            raise ValueError('Duplicate recommendation')
        return self
