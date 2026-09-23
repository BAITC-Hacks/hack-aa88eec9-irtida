"""Small deterministic context selector; no embeddings or vector database."""
from .dataset_loader import CareerFramework, GRADES
from .schemas import EmployeeContext, PersonalizationError


def select_context(user: EmployeeContext, framework: CareerFramework) -> dict:
    if (user.current_role, user.current_grade) not in framework.role_profiles:
        raise PersonalizationError("unknown_current_role_or_grade")
    levels = {s.skill_id: s.level for s in user.skills}
    if not levels.keys() <= framework.skills.keys():
        raise PersonalizationError("unknown_skill_id")
    completed = {}
    for quest in user.completed_quests:
        if quest.event_id not in framework.events:
            raise PersonalizationError("unknown_completed_event")
        completed.setdefault(quest.event_id, []).append(quest.completed_at)

    target_role = user.target_role or user.current_role
    target_grade = user.target_grade
    if target_role != user.current_role and target_grade is None:
        raise PersonalizationError("target_grade_required_for_role_change")
    if target_grade is None:
        grade_index = GRADES.index(user.current_grade)
        target_grade = GRADES[grade_index + 1] if grade_index < len(GRADES) - 1 else None
    if target_grade is not None and (target_role, target_grade) not in framework.role_profiles:
        raise PersonalizationError("unknown_target_role_or_grade")
    base = {
        "snapshotDate": framework.snapshot_date.isoformat(),
        "language": user.language,
        "currentRole": user.current_role,
        "currentGrade": user.current_grade,
        "targetRole": target_role,
        "targetGrade": target_grade,
        "levelScale": "integer 0–5; missing official-kit skills are level 0",
        "skills": [], "gaps": [], "candidates": [],
        "completedEventIds": sorted(completed),
        "status": "ready",
    }
    if target_grade is None:
        base["status"] = "highest_grade"
        return base
    profile = framework.role_profiles[(target_role, target_grade)]
    # Includes current-role skills as well as target skills; never includes name/userId.
    relevant = set(profile["required_skills"]) | set(framework.role_profiles[(user.current_role, user.current_grade)]["required_skills"])
    base["skills"] = [{"skillId": sid, "skill": framework.skills[sid]["name"], "level": levels.get(sid, 0)} for sid in sorted(relevant)]
    for sid, required in profile["required_skills"].items():
        current = levels.get(sid, 0)
        if required > current:
            skill = framework.skills[sid]
            base["gaps"].append({
                "skillId": sid, "skill": skill["name"], "description": skill["description"],
                "currentLevel": current, "requiredLevel": required, "gap": required - current,
                "critical": sid in profile["critical_skills"],
            })
    base["gaps"].sort(key=lambda g: (-int(g["critical"]), -g["gap"], g["skillId"]))
    if not base["gaps"]:
        base["status"] = "requirements_met"
        return base
    gaps = {g["skillId"]: g for g in base["gaps"]}
    for event in framework.events.values():
        eid = event["event_id"]
        if event["mandatory"] or user.current_role not in event["target_roles"] or user.current_grade not in event["target_grades"]:
            continue
        if eid in completed and eid != "EV_036":
            continue
        if any(levels.get(sid, 0) < required for sid, required in event["prerequisites"].items()):
            continue
        session = None
        if event["format"] != "self_paced":
            # An undated previous club completion is ambiguous. Do not suggest a repeat.
            if eid == "EV_036" and any(d is None for d in completed.get(eid, [])):
                continue
            previous = max(completed[eid]) if eid in completed else None
            dates = [d for d in event["upcoming_sessions"] if d >= framework.snapshot_date and (previous is None or d > previous)]
            if not dates:
                continue
            session = dates[0]
        effects = []
        for effect in event["develops_skills"]:
            sid = effect["skill_id"]
            current = levels.get(sid, 0)
            increase = max(0, min(effect["gain"], effect["max_level"] - current, 5 - current))
            if sid in gaps and increase > 0:
                effects.append({"skillId": sid, "increase": increase, "fromLevel": current,
                                "toLevel": current + increase, "requiredLevel": gaps[sid]["requiredLevel"]})
        if not effects:
            continue
        score = sum(min(x["increase"], gaps[x["skillId"]]["gap"]) * (2 if gaps[x["skillId"]]["critical"] else 1) for x in effects)
        base["candidates"].append({
            "eventId": eid, "title": event["title"], "description": event["description"],
            "type": event["type"], "format": event["format"], "durationHours": event["duration_hours"],
            "sessionDate": session.isoformat() if session else None,
            # Main backend currently uses the ISO session date as occurrence_id.
            "occurrenceId": session.isoformat() if session else None,
            "effects": effects, "score": score,
        })
    base["candidates"].sort(key=lambda e: (-e["score"], e["durationHours"], e["eventId"]))
    base["candidates"] = base["candidates"][:8]
    if not base["candidates"]:
        base["status"] = "no_eligible_activity"
    return base
