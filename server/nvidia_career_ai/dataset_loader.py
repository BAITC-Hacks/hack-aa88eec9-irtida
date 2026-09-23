"""Read-only Career Quest 1.0 adapter. No DB, cloud calls or data copies."""
import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from .schemas import CompletedQuest, EmployeeContext, PersonalizationError, SkillLevel

GRADES = ("Junior", "Middle", "Senior", "Lead")
FILES = ("skills.json", "employees.json", "events.json", "activity_history.csv")


@dataclass(frozen=True)
class CareerFramework:
    snapshot_date: date
    skills: dict[str, dict]
    role_profiles: dict[tuple[str, str], dict]
    events: dict[str, dict]
    warnings: tuple[str, ...] = ()


class FrameworkProvider(Protocol):
    """Replace with a DB adapter later; never send the full database to AI."""
    def load_framework(self) -> CareerFramework: ...


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _index(rows: list, key: str) -> dict:
    indexed = {row[key]: row for row in rows}
    if len(indexed) != len(rows) or not all(isinstance(k, str) and k for k in indexed):
        raise ValueError("duplicate or empty ID")
    return indexed


def _levels(values: dict, skills: dict):
    if not isinstance(values, dict) or not set(values) <= skills.keys():
        raise ValueError("unknown skill")
    if any(type(v) is not int or not 0 <= v <= 5 for v in values.values()):
        raise ValueError("skill levels must be integer 0–5")


class FileDatasetLoader:
    """Accept the four-file directory or its archive wrapper. Read once at startup."""

    def __init__(self, dataset_path: str | Path):
        root = Path(dataset_path).expanduser().resolve()
        candidates = [root, root / "case_1" / "career_quest_dataset"]
        matching = [p for p in candidates if all((p / f).is_file() for f in FILES)]
        if len(matching) != 1:
            raise PersonalizationError("dataset_directory_missing_or_ambiguous")
        self.path = matching[0]
        try:
            if any((self.path / f).stat().st_size > 5_000_000 for f in FILES):
                raise ValueError("dataset file too large")
            loaded = []
            for name in FILES[:3]:
                with (self.path / name).open(encoding="utf-8-sig") as handle:
                    loaded.append(json.load(handle, object_pairs_hook=unique_json_object))
            skills_doc, employees_doc, events_doc = loaded
            metas = [x["meta"] for x in loaded]
            if any(m != metas[0] for m in metas) or metas[0]["version"] != "1.0" or metas[0]["dataset"] != "Career Quest":
                raise ValueError("mismatched metadata")
            snapshot = date.fromisoformat(metas[0]["as_of_date"])
            skills = _index(skills_doc["skills"], "skill_id")
            profiles = {(p["role"], p["grade"]): p for p in skills_doc["role_profiles"]}
            if len(profiles) != len(skills_doc["role_profiles"]):
                raise ValueError("duplicate role profile")
            events = _index(events_doc["events"], "event_id")
            employees = _index(employees_doc["employees"], "employee_id")
            for (role, grade), profile in profiles.items():
                if grade not in GRADES:
                    raise ValueError("invalid grade")
                _levels(profile["required_skills"], skills)
                if not set(profile["critical_skills"]) <= profile["required_skills"].keys():
                    raise ValueError("unknown critical skill")
            for event in events.values():
                _levels(event["prerequisites"], skills)
                if type(event["mandatory"]) is not bool or event["format"] not in {"online", "offline", "self_paced"}:
                    raise ValueError("invalid event")
                effect_ids = []
                for effect in event["develops_skills"]:
                    effect_ids.append(effect["skill_id"])
                    _levels({effect["skill_id"]: effect["max_level"]}, skills)
                    if type(effect["gain"]) is not int or effect["gain"] < 0:
                        raise ValueError("invalid gain")
                if len(set(effect_ids)) != len(effect_ids):
                    raise ValueError("duplicate event skill")
                event["upcoming_sessions"] = sorted(date.fromisoformat(s) for s in event["upcoming_sessions"])
                if event["format"] == "self_paced" and event["upcoming_sessions"]:
                    raise ValueError("self-paced sessions")
            for employee in employees.values():
                _levels(employee["skills"], skills)
                if (employee["role"], employee["grade"]) not in profiles:
                    raise ValueError("unknown employee role")
                employee["last_review_date"] = date.fromisoformat(employee["last_review_date"])
                if employee["last_review_date"] > snapshot:
                    raise ValueError("future review")
            with (self.path / FILES[3]).open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                required = {"record_id", "employee_id", "event_id", "date", "status", "completion_pct"}
                if not required <= set(reader.fieldnames or []):
                    raise ValueError("missing history columns")
                history = list(reader)
            _index(history, "record_id")
            seen_completed = set()
            mandatory_repeats = 0
            histories = {key: [] for key in employees}
            for row in sorted(history, key=lambda r: (r["date"], r["record_id"])):
                if row["employee_id"] not in employees or row["event_id"] not in events:
                    raise ValueError("unknown history reference")
                row["date"] = date.fromisoformat(row["date"])
                if row["date"] > snapshot:
                    raise ValueError("future history")
                if row["status"] not in {"completed", "in_progress", "dropped", "no_show", "declined", "overdue"}:
                    raise ValueError("unknown history status")
                if not 0 <= int(row["completion_pct"]) <= 100 or (row["status"] == "completed" and int(row["completion_pct"]) != 100):
                    raise ValueError("invalid completion")
                key = (row["employee_id"], row["event_id"])
                if key in seen_completed and row["event_id"] != "EV_036":
                    event = events[row["event_id"]]
                    if event["mandatory"] and not event["develops_skills"]:
                        mandatory_repeats += 1
                    else:
                        raise ValueError("non-repeatable event repeated")
                if row["status"] == "completed":
                    seen_completed.add(key)
                histories[row["employee_id"]].append(row)
            warnings = (f"mandatory_history_repeated_after_completion:{mandatory_repeats}",) if mandatory_repeats else ()
            self._framework = CareerFramework(snapshot, skills, profiles, events, warnings)
            self._employees = employees
            self._histories = histories
        except (ValueError, KeyError, TypeError, OSError, RecursionError):
            raise PersonalizationError("invalid_career_quest_dataset") from None

    def load_framework(self) -> CareerFramework:
        return self._framework

    def employee_ids(self) -> tuple[str, ...]:
        return tuple(self._employees)

    def employee_context(self, employee_id: str, *, honor_career_goal: bool = True, language: str | None = None) -> EmployeeContext:
        if employee_id not in self._employees:
            raise PersonalizationError("unknown_employee")
        employee = self._employees[employee_id]
        levels = dict(employee["skills"])
        completed = []
        for row in self._histories[employee_id]:
            if row["status"] != "completed":
                continue
            completed.append(CompletedQuest(event_id=row["event_id"], completed_at=row["date"]))
            if row["date"] <= employee["last_review_date"]:
                continue
            for effect in self._framework.events[row["event_id"]]["develops_skills"]:
                skill = effect["skill_id"]
                current = levels.get(skill, 0)
                levels[skill] = current + max(0, min(effect["gain"], effect["max_level"] - current, 5 - current))
        goal = employee.get("career_goal") if honor_career_goal else None
        return EmployeeContext(
            user_id=employee_id, current_role=employee["role"], current_grade=employee["grade"],
            target_role=goal["target_role"] if goal else None,
            target_grade=goal["target_grade"] if goal else None,
            skills=[SkillLevel(skill_id=k, level=v) for k, v in levels.items()],
            completed_quests=completed, language=language or employee["preferred_language"],
        )
