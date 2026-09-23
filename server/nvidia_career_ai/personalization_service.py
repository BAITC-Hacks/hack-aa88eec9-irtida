"""Integration entry point: deterministic grounding + at most one NVIDIA call."""
import json
from typing import Protocol

from pydantic import ValidationError

from .context import select_context
from .dataset_loader import FrameworkProvider, unique_json_object
from .nvidia_client import NvidiaClient, NvidiaSettings
from .prompts import SYSTEM_PROMPT
from .schemas import (AIDraft, EmployeeContext, EstimatedImpact, FocusSkill,
                      PersonalizationError, PersonalizationResult, RecommendedQuest)


class CompletionClient(Protocol):
    async def complete(self, system_prompt: str, context: dict) -> str: ...


def parse_response(raw: str, context: dict) -> AIDraft:
    """Reject malformed, duplicate, ungrounded or oversized responses; no repair call."""
    try:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > 32_000:
            raise ValueError("oversized output")
        payload = json.loads(raw, object_pairs_hook=unique_json_object,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")))
        draft = AIDraft.model_validate(payload)
        gap_ids = {g["skillId"] for g in context["gaps"]}
        focus_ids = [f.skill_id for f in draft.focus_skills]
        candidates = {e["eventId"]: e for e in context["candidates"]}
        quest_ids = [q.source_event_id for q in draft.recommended_quests]
        if len(set(focus_ids)) != len(focus_ids) or not set(focus_ids) <= gap_ids:
            raise ValueError("invalid focus")
        if len(set(quest_ids)) != len(quest_ids):
            raise ValueError("duplicate quest")
        for quest in draft.recommended_quests:
            if quest.source_event_id not in candidates or quest.skill_id not in focus_ids:
                raise ValueError("unknown quest")
            if quest.skill_id not in {e["skillId"] for e in candidates[quest.source_event_id]["effects"]}:
                raise ValueError("unrelated skill")
        if any(not text.strip() for text in [draft.summary, draft.next_step, *[f.reason for f in draft.focus_skills],
                                             *[v for q in draft.recommended_quests for v in (q.title, q.description, q.reason)]]):
            raise ValueError("blank text")
        return draft
    except (ValueError, TypeError, ValidationError, RecursionError):
        raise PersonalizationError("invalid_ai_response") from None


def _grounding(gap: dict, context: dict) -> str:
    return (f"{gap['skill']}: {gap['currentLevel']}/5 → required {gap['requiredLevel']}/5; "
            f"target {context['targetRole']} / {context['targetGrade']}. "
            f"Critical requirement: {'yes' if gap['critical'] else 'no'}.")


def _mock_draft(context: dict) -> str:
    """Deterministic local example generated from THIS employee's eligible catalog."""
    gaps = {g["skillId"]: g for g in context["gaps"]}
    focus = {}
    quests = []
    templates = {
        "SK_PYTHON": ("Refactor and test one Python function", "Choose one function in a small Python service. Add type hints and three tests (success, invalid input, boundary); compare runtime before and after one focused refactor. Submit the diff and a short results note."),
        "SK_API_DESIGN": ("Specify and test one versioned API endpoint", "Define request, response, validation and error cases for one endpoint. Write an OpenAPI example and a small test demonstrating a valid and an invalid request; explain one versioning decision."),
        "SK_SYSTEM_DESIGN": ("Design a reliable request flow", "Draw the path of one request through a small service, database and cache. Describe what happens when the cache or database fails and list two tradeoffs in a one-page design note."),
        "SK_CONTAINERS": ("Containerize one small service", "Write a Dockerfile for a small service, run it locally and document build, run and health-check commands. Submit the Dockerfile and a reproducible README."),
        "SK_PUBLIC_SPEAKING": ("Present one technical decision in three minutes", "Record a three-minute explanation of one work decision for a non-specialist audience. Include the problem, two alternatives and your conclusion; ask a peer for two concrete suggestions."),
    }
    for event in context["candidates"]:
        # Prefer different focus skills within the three-slot limit.
        choices = sorted(event["effects"], key=lambda e: (e["skillId"] in focus, not gaps[e["skillId"]]["critical"], -gaps[e["skillId"]]["gap"]))
        effect = choices[0]
        sid = effect["skillId"]
        if sid not in focus and len(focus) == 3:
            continue
        gap = gaps[sid]
        focus[sid] = {"skillId": sid, "reason": _grounding(gap, context), "priority": "high" if gap["critical"] else "medium"}
        title, description = templates.get(sid, (
            f"Apply {gap['skill']} to one {context['currentRole']} work example",
            f"Choose one work example related to {event['title']}. Apply the supplied learning objective: {event['description']} Produce a one-page before/after explanation and ask a peer to review how you used {gap['skill']}.",
        ))
        quests.append({"sourceEventId": event["eventId"], "skillId": sid, "title": title,
                       "description": description, "reason": _grounding(gap, context), "difficulty": "medium"})
        if len(quests) == 3:
            break
    return json.dumps({"summary": f"MOCK: practical exercises for {context['currentRole']} ({context['currentGrade']}) toward {context['targetRole']} ({context['targetGrade']}).",
                       "focusSkills": list(focus.values()), "recommendedQuests": quests,
                       "nextStep": f"Start with: {quests[0]['title']}. Have the exercise reviewed; it does not automatically award skill points."})


class NvidiaCareerAI:
    def __init__(self, dataset: FrameworkProvider, settings: NvidiaSettings | None = None,
                 client: CompletionClient | None = None):
        self.dataset = dataset
        self.settings = settings or NvidiaSettings.from_env()
        self.client = client or NvidiaClient(self.settings)

    def build_context(self, user_context: EmployeeContext | dict) -> dict:
        user = EmployeeContext.model_validate(user_context)
        return select_context(user, self.dataset.load_framework())

    async def generate_career_personalization(self, user_context: EmployeeContext | dict) -> PersonalizationResult:
        context = self.build_context(user_context)
        framework = self.dataset.load_framework()
        common = dict(snapshot_date=framework.snapshot_date, target_role=context["targetRole"], target_grade=context["targetGrade"])
        warnings = list(framework.warnings)
        if context["status"] != "ready":
            return PersonalizationResult(**common, mode="no_candidates", summary=context["status"],
                                         focus_skills=[], recommended_quests=[],
                                         next_step="Review the target and available development options with a mentor; no eligible catalog event was selected.", warnings=warnings)
        if self.settings.mock:
            raw = _mock_draft(context)
            warnings.append("mock_mode_no_nvidia_request; mock prose is English")
        else:
            # Exactly one request. Missing key, API errors and invalid JSON are explicit errors.
            raw = await self.client.complete(SYSTEM_PROMPT, context)
        draft = parse_response(raw, context)
        gaps = {g["skillId"]: g for g in context["gaps"]}
        candidates = {e["eventId"]: e for e in context["candidates"]}
        focus = [FocusSkill(**f.model_dump(), skill=gaps[f.skill_id]["skill"], current_level=gaps[f.skill_id]["currentLevel"],
                            required_level=gaps[f.skill_id]["requiredLevel"], gap=gaps[f.skill_id]["gap"], critical=gaps[f.skill_id]["critical"])
                 for f in draft.focus_skills]
        quests = []
        for q in draft.recommended_quests:
            event = candidates[q.source_event_id]
            effect = next(e for e in event["effects"] if e["skillId"] == q.skill_id)
            impact = EstimatedImpact.model_validate({**effect, "skill": gaps[q.skill_id]["skill"]})
            quests.append(RecommendedQuest(**q.model_dump(), source_event_title=event["title"],
                          source_session_date=event["sessionDate"], source_occurrence_id=event["occurrenceId"],
                          estimated_impact=impact, grounding=_grounding(gaps[q.skill_id], context)))
        return PersonalizationResult(**common, mode="mock" if self.settings.mock else "nvidia",
                                     model=None if self.settings.mock else self.settings.model,
                                     summary=draft.summary, focus_skills=focus, recommended_quests=quests,
                                     next_step=draft.next_step, warnings=warnings)
