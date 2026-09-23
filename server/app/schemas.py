from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')]
Level = Annotated[int, Field(strict=True, ge=0, le=5)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class EmployeeInput(StrictModel):
    id: Identifier
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=100)
    grade: str = Field(min_length=1, max_length=50)
    tenure_months: int = Field(ge=0, le=1200)
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
    roles: list[str] = Field(max_length=50)
    grades: list[str] = Field(max_length=20)
    effects: dict[Identifier, Effect]


class GradeRule(StrictModel):
    role: str = Field(min_length=1, max_length=100)
    grade: str = Field(min_length=1, max_length=50)
    next_grade: str = Field(min_length=1, max_length=50)
    requirements: dict[Identifier, Level]


class HistoryInput(StrictModel):
    id: Identifier
    employee_id: Identifier
    event_id: Identifier
    status: Literal['completed', 'missed', 'declined']
    occurred_at: date


class DatasetBundle(StrictModel):
    schema_version: Literal['demo-v1'] = 'demo-v1'
    employees: list[EmployeeInput] = Field(default_factory=list, max_length=2000)
    skills: list[SkillInput] = Field(default_factory=list, max_length=1000)
    events: list[EventInput] = Field(default_factory=list, max_length=1000)
    grade_rules: list[GradeRule] = Field(default_factory=list, max_length=200)
    history: list[HistoryInput] = Field(default_factory=list, max_length=100000)

    @model_validator(mode='after')
    def unique_ids(self):
        for name in ('employees', 'skills', 'events', 'history'):
            ids = [item.id for item in getattr(self, name)]
            if len(ids) != len(set(ids)):
                raise ValueError(f'Duplicate IDs in {name}')
        keys = [(x.role, x.grade) for x in self.grade_rules]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate role/grade rule')
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
