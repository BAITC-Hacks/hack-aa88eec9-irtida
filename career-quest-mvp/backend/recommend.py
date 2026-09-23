"""
Career Quest — объяснимый движок рекомендаций.

Задача ядра (см. ТЗ, п.4 и п.9): рекомендация НЕ должна опираться на одно поле
профиля («у кого навык ниже всех — тому и активность»). Итоговый score учитывает
минимум три независимых фактора одновременно:

  1. Разрыв до требования следующего грейда (grade gap)
  2. Критичность навыка для роли / перехода (role-critical hard skill vs. общий soft)
  3. История участия (штраф за систематические пропуски именно этого типа
     активности — повторное назначение таких же активностей с высокой
     вероятностью снова будет проигнорировано)
  4. (доп.) Стаж/грейд — используется для выбора целевого следующего грейда

Из-за пункта 3 сценарий из ТЗ («ниже всего Public Speaking, но он его трижды
пропускал, а критичен System Design») решается корректно: system design получает
более высокий score несмотря на то, что численно его разрыв меньше.
"""
from collections import defaultdict

GRADES = ["Junior", "Middle", "Senior", "Lead"]
NEXT_GRADE = {"Junior": "Middle", "Middle": "Senior", "Senior": "Lead", "Lead": None}

NEGATIVE_STATUSES = {"skipped", "declined"}


def _skills_by_id(skills):
    return {s["skill_id"]: s for s in skills}


def _history_for_employee(history_rows, employee_id):
    return [r for r in history_rows if r["employee_id"] == employee_id]


def _completed_event_ids(emp_history):
    return {r["event_id"] for r in emp_history if r["status"] == "completed"}


def _skip_penalty_by_skill(emp_history, events_by_id, skills_map):
    """Сколько раз сотрудник пропустил/отклонил активности, развивающие каждый навык."""
    penalty = defaultdict(int)
    for row in emp_history:
        if row["status"] not in NEGATIVE_STATUSES:
            continue
        ev = events_by_id.get(row["event_id"])
        if not ev:
            continue
        for sid in ev["skills_developed"]:
            penalty[sid] += 1
    return penalty


def _skill_gap(employee, skill, target_grade):
    if target_grade is None:
        return 0
    current = employee["skills"].get(skill["skill_id"], 0)
    required = skill["grade_requirements"].get(target_grade, 0)
    return max(0, required - current)


def _criticality_weight(skill, employee):
    if skill["category"] == "hard" and skill.get("role_family") == employee["role"]:
        return 1.5  # ролевой hard-навык — прямой блокер перехода на грейд
    if skill["category"] == "soft":
        return 0.8  # soft развивает, но реже прямой блокер
    return 1.0


def score_skill_gaps(employee, skills, emp_history, events_by_id):
    """Возвращает список кандидатов-навыков с разложением score по факторам."""
    skip_penalty = _skip_penalty_by_skill(emp_history, events_by_id, _skills_by_id(skills))
    target_grade = NEXT_GRADE.get(employee["grade"])
    candidates = []
    for skill in skills:
        gap = _skill_gap(employee, skill, target_grade)
        if gap <= 0:
            continue
        crit = _criticality_weight(skill, employee)
        penalty = skip_penalty.get(skill["skill_id"], 0) * 0.6
        score = gap * crit - penalty
        candidates.append({
            "skill_id": skill["skill_id"],
            "skill_name": skill["name"],
            "category": skill["category"],
            "gap": gap,
            "criticality_weight": crit,
            "avoidance_penalty": penalty,
            "avoidance_count": skip_penalty.get(skill["skill_id"], 0),
            "current_level": employee["skills"].get(skill["skill_id"], 0),
            "required_level": skill["grade_requirements"].get(target_grade, 0) if target_grade else None,
            "score": round(score, 2),
        })
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates, target_grade


def _best_event_for_skill(skill_id, employee, events, completed_ids, emp_history):
    """Среди неоконченных событий, развивающих навык и доступных роли, выбрать лучшее."""
    applicable = [
        ev for ev in events
        if skill_id in ev["skills_developed"]
        and ev["audience"] in (employee["role"], "All")
        and ev["event_id"] not in completed_ids
    ]
    if not applicable:
        return None
    # среди применимых предпочитаем тип, который сотрудник реже избегал
    neg_by_type = defaultdict(int)
    for row in emp_history:
        if row["status"] in NEGATIVE_STATUSES:
            neg_by_type[row["event_id"]] += 1
    applicable.sort(key=lambda ev: neg_by_type.get(ev["event_id"], 0))
    return applicable[0]


def _build_rationale(employee, cand, event, target_grade):
    parts = []
    parts.append(
        f"по навыку «{cand['skill_name']}» требуется уровень {cand['required_level']} "
        f"для грейда {target_grade}, сейчас {cand['current_level']} (разрыв {cand['gap']})"
    )
    if cand["category"] == "hard" and event and event["audience"] == employee["role"]:
        parts.append(f"навык напрямую критичен для роли {employee['role']}, а не второстепенный")
    else:
        parts.append("навык учтён с меньшим весом как общий (soft), т.к. не является прямым блокером роли")
    if cand["avoidance_count"] > 0:
        parts.append(
            f"при этом по этому направлению уже было {cand['avoidance_count']} пропуска/отказа — "
            f"это снизило приоритет, но не обнулило его"
        )
    else:
        parts.append("по истории участия сотрудник ранее не избегал активности этого типа")
    parts.append(f"учтён стаж в грейде {employee['grade']} — {employee['tenure_months']} мес.")
    return "; ".join(parts) + "."


def recommend_for_employee(employee, skills, events, history_rows, top_n=3):
    events_by_id = {e["event_id"]: e for e in events}
    emp_history = _history_for_employee(history_rows, employee["employee_id"])
    completed_ids = _completed_event_ids(emp_history)

    candidates, target_grade = score_skill_gaps(employee, skills, emp_history, events_by_id)

    if target_grade is None:
        return {
            "target_grade": None,
            "message": "Сотрудник уже на максимальном грейде (Lead) — рекомендации ориентированы на менторство и передачу экспертизы.",
            "recommendations": [],
        }

    recs = []
    used_events = set()
    for cand in candidates:
        if len(recs) >= top_n:
            break
        event = _best_event_for_skill(cand["skill_id"], employee, events, completed_ids, emp_history)
        if not event or event["event_id"] in used_events:
            continue
        used_events.add(event["event_id"])
        recs.append({
            "event_id": event["event_id"],
            "event_name": event["name"],
            "event_type": event["type"],
            "skill_id": cand["skill_id"],
            "skill_name": cand["skill_name"],
            "gap": cand["gap"],
            "score": cand["score"],
            "factors": {
                "grade_gap": cand["gap"],
                "criticality_weight": cand["criticality_weight"],
                "avoidance_count": cand["avoidance_count"],
                "avoidance_penalty": cand["avoidance_penalty"],
            },
            "rationale": _build_rationale(employee, cand, event, target_grade),
        })

    return {
        "target_grade": target_grade,
        "message": None if recs else "Все ключевые разрывы для следующего грейда закрыты релевантными событиями недоступны.",
        "recommendations": recs,
    }


# ---------------------------------------------------------------------------
# HR-аналитика
# ---------------------------------------------------------------------------

def hr_lagging_skills(employees, skills):
    """Доля сотрудников, не дотягивающих до требования СВОЕГО ТЕКУЩЕГО грейда, по навыку."""
    result = []
    for skill in skills:
        below = 0
        total = 0
        for emp in employees:
            if skill["category"] == "hard" and skill.get("role_family") != emp["role"]:
                continue
            req = skill["grade_requirements"].get(emp["grade"], 0)
            level = emp["skills"].get(skill["skill_id"])
            if level is None:
                continue
            total += 1
            if level < req:
                below += 1
        if total == 0:
            continue
        result.append({
            "skill_id": skill["skill_id"],
            "skill_name": skill["name"],
            "category": skill["category"],
            "below_requirement": below,
            "total_applicable": total,
            "lagging_share": round(below / total, 3),
        })
    result.sort(key=lambda r: r["lagging_share"], reverse=True)
    return result


def hr_employees_without_next_step(employees, skills, events, history_rows):
    without = []
    for emp in employees:
        res = recommend_for_employee(emp, skills, events, history_rows)
        if not res["recommendations"]:
            without.append({
                "employee_id": emp["employee_id"],
                "name": emp["name"],
                "role": emp["role"],
                "grade": emp["grade"],
                "reason": res["message"] or "Нет рекомендаций",
            })
    return without


def hr_event_participation(events, history_rows):
    stats = {ev["event_id"]: {"event_id": ev["event_id"], "name": ev["name"], "type": ev["type"],
                               "completed": 0, "skipped": 0, "declined": 0} for ev in events}
    for row in history_rows:
        s = stats.get(row["event_id"])
        if not s:
            continue
        if row["status"] == "completed":
            s["completed"] += 1
        elif row["status"] == "skipped":
            s["skipped"] += 1
        elif row["status"] == "declined":
            s["declined"] += 1
    out = list(stats.values())
    for s in out:
        total = s["completed"] + s["skipped"] + s["declined"]
        s["total"] = total
        s["completion_rate"] = round(s["completed"] / total, 3) if total else None
    out.sort(key=lambda s: (s["completion_rate"] if s["completion_rate"] is not None else 1))
    return out
