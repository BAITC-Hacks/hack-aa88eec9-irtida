"""
Career Quest — генератор синтетического стартового датасета.

Строго соответствует объёмам из ТЗ:
  - 200 профилей сотрудников (employees.json)
  - 40 событий/активностей (events.json)
  - 60 навыков hard/soft (skills.json)
  - 24 месяца истории участия (activity_history.csv)

Запуск:  python3 generate_data.py
Данные пишутся в ../data/
"""
import json
import csv
import random
import os

random.seed(42)  # детерминированная генерация — воспроизводимость

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

GRADES = ["Junior", "Middle", "Senior", "Lead"]
GRADE_INDEX = {g: i for i, g in enumerate(GRADES)}
NEXT_GRADE = {"Junior": "Middle", "Middle": "Senior", "Senior": "Lead", "Lead": None}

ROLES = [
    "Backend Engineer",
    "Frontend Engineer",
    "Data Analyst",
    "QA Engineer",
    "DevOps Engineer",
    "Product Manager",
]

# ---------------------------------------------------------------------------
# 1. НАВЫКИ (60): 8 hard-навыков на каждую из 6 ролей (=48) + 12 soft (общие)
# ---------------------------------------------------------------------------
ROLE_HARD_SKILLS = {
    "Backend Engineer": [
        ("SK_BE_PYTHON", "Python"),
        ("SK_BE_SYSDESIGN", "System Design"),
        ("SK_BE_DB", "Databases"),
        ("SK_BE_API", "API Design"),
        ("SK_BE_TEST", "Backend Testing"),
        ("SK_BE_CLOUD", "Cloud Infrastructure"),
        ("SK_BE_MSA", "Microservices"),
        ("SK_BE_SEC", "Security Basics"),
    ],
    "Frontend Engineer": [
        ("SK_FE_JS", "JavaScript"),
        ("SK_FE_REACT", "React"),
        ("SK_FE_CSS", "CSS/UI Layout"),
        ("SK_FE_PERF", "Web Performance"),
        ("SK_FE_A11Y", "Accessibility"),
        ("SK_FE_STATE", "State Management"),
        ("SK_FE_TEST", "Frontend Testing"),
        ("SK_FE_TOOLS", "Browser DevTools"),
    ],
    "Data Analyst": [
        ("SK_DA_SQL", "SQL"),
        ("SK_DA_VIZ", "Data Visualization"),
        ("SK_DA_STAT", "Statistics"),
        ("SK_DA_PY", "Python for Data"),
        ("SK_DA_ETL", "ETL Pipelines"),
        ("SK_DA_ABT", "A/B Testing"),
        ("SK_DA_BI", "Business Intelligence"),
        ("SK_DA_MODEL", "Data Modeling"),
    ],
    "QA Engineer": [
        ("SK_QA_AUTO", "Test Automation"),
        ("SK_QA_MANUAL", "Manual Testing"),
        ("SK_QA_PLAN", "Test Planning"),
        ("SK_QA_BUG", "Bug Tracking"),
        ("SK_QA_CI", "CI/CD for QA"),
        ("SK_QA_API", "API Testing"),
        ("SK_QA_PERF", "Performance Testing"),
        ("SK_QA_DOC", "Test Documentation"),
    ],
    "DevOps Engineer": [
        ("SK_DO_CI", "CI/CD Pipelines"),
        ("SK_DO_CLOUD", "Cloud Platforms"),
        ("SK_DO_CONT", "Containerization"),
        ("SK_DO_MON", "Monitoring & Alerting"),
        ("SK_DO_IAC", "Infrastructure as Code"),
        ("SK_DO_NET", "Networking"),
        ("SK_DO_SEC", "Security Operations"),
        ("SK_DO_AUTO", "Automation Scripting"),
    ],
    "Product Manager": [
        ("SK_PM_STRAT", "Product Strategy"),
        ("SK_PM_ROAD", "Roadmapping"),
        ("SK_PM_STAKE", "Stakeholder Management"),
        ("SK_PM_MARKET", "Market Research"),
        ("SK_PM_AGILE", "Agile Methodology"),
        ("SK_PM_PRIOR", "Prioritization"),
        ("SK_PM_DATA", "Data-Driven Decisions"),
        ("SK_PM_UX", "User Research"),
    ],
}

SOFT_SKILLS = [
    ("SK_SOFT_PUBLIC", "Public Speaking"),
    ("SK_SOFT_LEAD", "Leadership"),
    ("SK_SOFT_TEAM", "Teamwork"),
    ("SK_SOFT_COMM", "Communication"),
    ("SK_SOFT_TIME", "Time Management"),
    ("SK_SOFT_NEGO", "Negotiation"),
    ("SK_SOFT_CRIT", "Critical Thinking"),
    ("SK_SOFT_ADAPT", "Adaptability"),
    ("SK_SOFT_MENTOR", "Mentoring"),
    ("SK_SOFT_CONFLICT", "Conflict Resolution"),
    ("SK_SOFT_EQ", "Emotional Intelligence"),
    ("SK_SOFT_STRAT", "Strategic Thinking"),
]

# требуемый уровень навыка (0-5) для получения соответствующего грейда
# hard-навыки растут быстрее с грейдом, soft — более полого, но Lead требует много soft
HARD_REQ = {"Junior": 1, "Middle": 2, "Senior": 4, "Lead": 5}
SOFT_REQ_LOW = {"Junior": 0, "Middle": 1, "Senior": 2, "Lead": 3}
SOFT_REQ_HIGH = {"Junior": 0, "Middle": 2, "Senior": 3, "Lead": 5}  # для лидерских софтов

LEADERSHIP_SOFT = {"SK_SOFT_LEAD", "SK_SOFT_PUBLIC", "SK_SOFT_STRAT", "SK_SOFT_MENTOR", "SK_SOFT_CONFLICT"}


def build_skills():
    skills = []
    for role, items in ROLE_HARD_SKILLS.items():
        for sid, name in items:
            skills.append({
                "skill_id": sid,
                "name": name,
                "category": "hard",
                "role_family": role,
                "grade_requirements": dict(HARD_REQ),
            })
    for sid, name in SOFT_SKILLS:
        req = SOFT_REQ_HIGH if sid in LEADERSHIP_SOFT else SOFT_REQ_LOW
        skills.append({
            "skill_id": sid,
            "name": name,
            "category": "soft",
            "role_family": None,
            "grade_requirements": dict(req),
        })
    assert len(skills) == 60, f"expected 60 skills, got {len(skills)}"
    return skills


# ---------------------------------------------------------------------------
# 2. СОБЫТИЯ (40): по 5 ролевых на каждую из 6 ролей (=30) + 10 общих soft
# ---------------------------------------------------------------------------
EVENT_TYPES = ["training", "mentoring", "rotation", "assessment", "workshop"]


def build_events(skills_by_role):
    events = []
    eid = 1
    for role in ROLES:
        role_skills = skills_by_role[role]
        for i in range(5):
            etype = EVENT_TYPES[i % len(EVENT_TYPES)]
            picked = random.sample(role_skills, k=min(2, len(role_skills)))
            events.append({
                "event_id": f"EV{eid:03d}",
                "name": f"{role}: {etype.capitalize()} #{i + 1}",
                "type": etype,
                "audience": role,
                "description": f"{etype.capitalize()} программа для роли {role}, развивает {', '.join(n for _, n in picked)}.",
                "skills_developed": {
                    sid: {"gain": random.choice([1, 1, 2]), "max_level": 5}
                    for sid, _ in picked
                },
            })
            eid += 1
    # 10 общих soft-skill событий, доступных всем ролям
    soft_pool = SOFT_SKILLS[:]
    random.shuffle(soft_pool)
    for i in range(10):
        etype = EVENT_TYPES[i % len(EVENT_TYPES)]
        picked = [soft_pool[i % len(soft_pool)], soft_pool[(i + 3) % len(soft_pool)]]
        events.append({
            "event_id": f"EV{eid:03d}",
            "name": f"All Roles: {picked[0][1]} {etype.capitalize()} #{i + 1}",
            "type": etype,
            "audience": "All",
            "description": f"Общая {etype} программа по развитию {picked[0][1]} / {picked[1][1]}.",
            "skills_developed": {
                sid: {"gain": random.choice([1, 1, 2]), "max_level": 5}
                for sid, _ in picked
            },
        })
        eid += 1
    assert len(events) == 40, f"expected 40 events, got {len(events)}"
    return events


# ---------------------------------------------------------------------------
# 3. СОТРУДНИКИ (200)
# ---------------------------------------------------------------------------
FIRST_NAMES = ["Aigerim", "Nursultan", "Dana", "Yerlan", "Saltanat", "Timur", "Aliya",
               "Bekzat", "Madina", "Arman", "Zhanna", "Daniyar", "Gulnaz", "Rustem",
               "Aidana", "Alibek", "Kamila", "Askar", "Zarina", "Miras"]
LAST_NAMES = ["Nurlanov", "Kaskabayev", "Sadykova", "Zhaksybekov", "Tulegenova",
              "Amirov", "Bekova", "Serikov", "Dosymova", "Kairatov"]

TENURE_RANGE = {"Junior": (1, 12), "Middle": (13, 36), "Senior": (37, 72), "Lead": (60, 120)}
# распределение по грейдам, суммарно 200
GRADE_COUNTS = {"Junior": 60, "Middle": 70, "Senior": 50, "Lead": 20}


def sample_level(target, spread=1):
    lvl = target + random.randint(-spread, spread)
    return max(0, min(5, lvl))


def build_employees(skills_by_role):
    employees = []
    eid = 1
    for role in ROLES:
        role_skills = skills_by_role[role]
        per_role = 200 // len(ROLES)
        remainder = 200 % len(ROLES)
        count = per_role + (1 if ROLES.index(role) < remainder else 0)
        # распределяем грейды внутри роли пропорционально GRADE_COUNTS
        grade_seq = []
        for g, c in GRADE_COUNTS.items():
            grade_seq += [g] * round(c / 200 * count)
        while len(grade_seq) < count:
            grade_seq.append(random.choice(GRADES))
        grade_seq = grade_seq[:count]
        random.shuffle(grade_seq)

        for grade in grade_seq:
            emp_id = f"E{eid:04d}"
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            tmin, tmax = TENURE_RANGE[grade]
            tenure = random.randint(tmin, tmax)

            base_by_grade = {"Junior": 1, "Middle": 2, "Senior": 3, "Lead": 4}[grade]
            skills = {}
            # ролевые hard-навыки: базовый уровень чуть ниже текущего грейда (создаёт разрывы к next grade)
            for sid, _ in role_skills:
                skills[sid] = sample_level(base_by_grade, spread=1)
            # soft-навыки: у части сотрудников намеренно занижены (реалистичные разрывы)
            for sid, _ in SOFT_SKILLS:
                lvl = sample_level(max(0, base_by_grade - 1), spread=1)
                skills[sid] = lvl

            # намеренная "ловушка низкого поля": ~15% сотрудников имеют один сильно
            # заниженный soft-навык, который НЕ является узким местом для след. грейда
            if random.random() < 0.15:
                decoy = random.choice(SOFT_SKILLS)[0]
                skills[decoy] = 0

            employees.append({
                "employee_id": emp_id,
                "name": name,
                "role": role,
                "grade": grade,
                "tenure_months": tenure,
                "skills": skills,
            })
            eid += 1
    assert len(employees) == 200, f"expected 200 employees, got {len(employees)}"
    return employees


# ---------------------------------------------------------------------------
# 4. ИСТОРИЯ УЧАСТИЯ (24 месяца), включая пропуски/отказы
# ---------------------------------------------------------------------------
STATUSES = ["completed", "skipped", "declined"]


def build_history(employees, events):
    events_by_audience = {}
    for ev in events:
        events_by_audience.setdefault(ev["audience"], []).append(ev)

    rows = []
    for emp in employees:
        applicable = events_by_audience.get(emp["role"], []) + events_by_audience.get("All", [])
        if not applicable:
            continue
        # у каждого сотрудника есть личная склонность избегать один конкретный тип события
        avoided_type = random.choice(EVENT_TYPES) if random.random() < 0.35 else None

        n_records = random.randint(6, 16)  # не каждый месяц есть активность
        months = sorted(random.sample(range(1, 25), k=min(n_records, 24)))
        for month in months:
            ev = random.choice(applicable)
            if avoided_type and ev["type"] == avoided_type:
                status = random.choices(STATUSES, weights=[15, 55, 30])[0]
            else:
                status = random.choices(STATUSES, weights=[75, 15, 10])[0]
            rows.append({
                "employee_id": emp["employee_id"],
                "event_id": ev["event_id"],
                "month": month,
                "status": status,
            })
    return rows


def main():
    skills = build_skills()
    skills_by_role = {role: items for role, items in ROLE_HARD_SKILLS.items()}
    events = build_events(skills_by_role)
    employees = build_employees(skills_by_role)
    history = build_history(employees, events)

    with open(os.path.join(DATA_DIR, "skills.json"), "w", encoding="utf-8") as f:
        json.dump(skills, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, "events.json"), "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, "employees.json"), "w", encoding="utf-8") as f:
        json.dump(employees, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, "activity_history.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["employee_id", "event_id", "month", "status"])
        writer.writeheader()
        writer.writerows(history)

    print(f"skills.json: {len(skills)}")
    print(f"events.json: {len(events)}")
    print(f"employees.json: {len(employees)}")
    print(f"activity_history.csv rows: {len(history)}")


if __name__ == "__main__":
    main()
