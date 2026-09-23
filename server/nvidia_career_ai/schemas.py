"""Public input/output contracts. Skill levels use the kit's 0–5 scale."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from pydantic.alias_generators import to_camel

Grade = Literal["Junior", "Middle", "Senior", "Lead"]
Level = Annotated[StrictInt, Field(ge=0, le=5)]
Text = Annotated[str, Field(min_length=1, max_length=1200, strict=True)]
Identifier = Annotated[str, Field(min_length=1, max_length=100, strict=True)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)


class SkillLevel(Contract):
    skill_id: Identifier
    level: Level


class CompletedQuest(Contract):
    event_id: Identifier
    completed_at: date | None = None


class EmployeeContext(Contract):
    """Already-current skills: service never reapplies history to this input."""
    user_id: Identifier
    current_role: Annotated[str, Field(min_length=1, max_length=120)]
    current_grade: Grade
    target_role: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    target_grade: Grade | None = None
    skills: Annotated[list[SkillLevel], Field(max_length=200)]
    completed_quests: Annotated[list[CompletedQuest], Field(max_length=5000)] = Field(default_factory=list)
    language: Literal["ru", "kk", "en"] = "ru"
    skills_state: Literal["current"] = "current"

    @model_validator(mode="after")
    def unique_skills(self):
        if len({s.skill_id for s in self.skills}) != len(self.skills):
            raise ValueError("duplicate skillId")
        return self


class DraftFocus(Contract):
    skill_id: Identifier
    reason: Text
    priority: Literal["high", "medium", "low"]


class DraftQuest(Contract):
    source_event_id: Identifier
    skill_id: Identifier
    title: Annotated[str, Field(min_length=8, max_length=180, strict=True)]
    description: Annotated[str, Field(min_length=30, max_length=1200, strict=True)]
    reason: Text
    difficulty: Literal["easy", "medium", "hard"]


class AIDraft(Contract):
    summary: Text
    focus_skills: Annotated[list[DraftFocus], Field(min_length=1, max_length=3)]
    recommended_quests: Annotated[list[DraftQuest], Field(min_length=1, max_length=3)]
    next_step: Text


class FocusSkill(DraftFocus):
    skill: str
    current_level: Level
    required_level: Level
    gap: Level
    critical: bool


class EstimatedImpact(Contract):
    skill_id: str
    skill: str
    increase: Level
    from_level: Level
    to_level: Level
    required_level: Level
    basis: Literal["source_event_completion_only"] = "source_event_completion_only"


class RecommendedQuest(DraftQuest):
    kind: Literal["practice_suggestion"] = "practice_suggestion"
    source_event_title: str
    source_session_date: date | None
    source_occurrence_id: str | None
    estimated_impact: EstimatedImpact
    grounding: str
    requires_review: bool = True


class PersonalizationResult(Contract):
    mode: Literal["nvidia", "mock", "no_candidates"]
    model: str | None = None
    snapshot_date: date
    target_role: str
    target_grade: Grade | None
    summary: str
    focus_skills: Annotated[list[FocusSkill], Field(max_length=3)]
    recommended_quests: Annotated[list[RecommendedQuest], Field(max_length=3)]
    next_step: str
    warnings: list[str] = Field(default_factory=list)


class PersonalizationError(ValueError):
    """Safe, stable error code; does not include employee data/model output."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
