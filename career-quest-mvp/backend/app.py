"""
Career Quest — backend (Flask, чистый stdlib + Flask, без внешних AI-сервисов
по умолчанию — engine полностью explainable и работает офлайн).

Запуск:  python3 app.py
Откроется на http://localhost:8000
"""
import csv
import json
import os
import threading

from flask import Flask, jsonify, request, send_from_directory

import recommend

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__, static_folder=None)
LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# In-memory store, загружается из data/ при старте и персистится обратно
# ---------------------------------------------------------------------------
STORE = {"employees": [], "events": [], "skills": [], "history": []}


def load_all():
    with open(os.path.join(DATA_DIR, "employees.json"), encoding="utf-8") as f:
        STORE["employees"] = json.load(f)
    with open(os.path.join(DATA_DIR, "events.json"), encoding="utf-8") as f:
        STORE["events"] = json.load(f)
    with open(os.path.join(DATA_DIR, "skills.json"), encoding="utf-8") as f:
        STORE["skills"] = json.load(f)
    with open(os.path.join(DATA_DIR, "activity_history.csv"), encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            r["month"] = int(r["month"])
            rows.append(r)
        STORE["history"] = rows


def persist_employees():
    with open(os.path.join(DATA_DIR, "employees.json"), "w", encoding="utf-8") as f:
        json.dump(STORE["employees"], f, ensure_ascii=False, indent=2)


def persist_history():
    with open(os.path.join(DATA_DIR, "activity_history.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["employee_id", "event_id", "month", "status"])
        writer.writeheader()
        writer.writerows(STORE["history"])


def find_employee(employee_id):
    return next((e for e in STORE["employees"] if e["employee_id"] == employee_id), None)


# ---------------------------------------------------------------------------
# Простая ролевая модель (сотрудник видит только себя, HR видит всё).
# В заголовке запроса ожидается X-Role: employee|hr и X-Employee-Id (для employee).
# Это MVP-реализация принципа "разграничение прав сотрудник/HR" из ТЗ.
# ---------------------------------------------------------------------------

def current_role():
    return request.headers.get("X-Role", "hr")  # по умолчанию hr — для простоты локальной демонстрации


def require_hr():
    if current_role() != "hr":
        return jsonify({"error": "forbidden: требуется роль HR"}), 403
    return None


def can_view_employee(employee_id):
    role = current_role()
    if role == "hr":
        return True
    requester_id = request.headers.get("X-Employee-Id")
    return requester_id == employee_id


# ---------------------------------------------------------------------------
# Статика (фронтенд)
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/hr")
def hr_page():
    return send_from_directory(FRONTEND_DIR, "hr.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(FRONTEND_DIR, path)


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------
@app.route("/api/skills")
def api_skills():
    return jsonify(STORE["skills"])


@app.route("/api/events")
def api_events():
    return jsonify(STORE["events"])


# ---------------------------------------------------------------------------
# Сотрудники / профиль / траектория
# ---------------------------------------------------------------------------
@app.route("/api/employees")
def api_employees_list():
    err = require_hr()
    if err:
        return err
    q = request.args.get("q", "").strip().lower()
    items = STORE["employees"]
    if q:
        items = [e for e in items if q in e["employee_id"].lower() or q in e["name"].lower()]
    brief = [{"employee_id": e["employee_id"], "name": e["name"], "role": e["role"],
              "grade": e["grade"], "tenure_months": e["tenure_months"]} for e in items]
    return jsonify(brief)


@app.route("/api/employees/<employee_id>")
def api_employee_profile(employee_id):
    if not can_view_employee(employee_id):
        return jsonify({"error": "forbidden"}), 403
    emp = find_employee(employee_id)
    if not emp:
        return jsonify({"error": "not found"}), 404

    emp_history = [r for r in STORE["history"] if r["employee_id"] == employee_id]
    events_by_id = {e["event_id"]: e for e in STORE["events"]}
    completed = [
        {**r, "event_name": events_by_id[r["event_id"]]["name"]}
        for r in emp_history if r["status"] == "completed" and r["event_id"] in events_by_id
    ]
    target_grade = recommend.NEXT_GRADE.get(emp["grade"])
    candidates, _ = recommend.score_skill_gaps(emp, STORE["skills"], emp_history, events_by_id)

    return jsonify({
        "employee": emp,
        "target_grade": target_grade,
        "completed_activities": sorted(completed, key=lambda r: r["month"]),
        "skill_gaps": candidates,  # уже отсортировано по score, содержит разложение факторов
    })


@app.route("/api/employees/<employee_id>/recommendations")
def api_recommendations(employee_id):
    if not can_view_employee(employee_id):
        return jsonify({"error": "forbidden"}), 403
    emp = find_employee(employee_id)
    if not emp:
        return jsonify({"error": "not found"}), 404
    result = recommend.recommend_for_employee(emp, STORE["skills"], STORE["events"], STORE["history"])
    return jsonify(result)


@app.route("/api/employees/<employee_id>/complete", methods=["POST"])
def api_complete_activity(employee_id):
    if not can_view_employee(employee_id):
        return jsonify({"error": "forbidden"}), 403
    emp = find_employee(employee_id)
    if not emp:
        return jsonify({"error": "not found"}), 404
    body = request.get_json(force=True, silent=True) or {}
    event_id = body.get("event_id")
    month = body.get("month", 25)  # текущий "виртуальный" месяц по умолчанию
    event = next((e for e in STORE["events"] if e["event_id"] == event_id), None)
    if not event:
        return jsonify({"error": "event not found"}), 404

    with LOCK:
        STORE["history"].append({
            "employee_id": employee_id, "event_id": event_id, "month": month, "status": "completed",
        })
        for skill_id, rule in event["skills_developed"].items():
            current = emp["skills"].get(skill_id, 0)
            gained = min(rule.get("max_level", 5), current + rule.get("gain", 1))
            emp["skills"][skill_id] = gained
        persist_employees()
        persist_history()

    result = recommend.recommend_for_employee(emp, STORE["skills"], STORE["events"], STORE["history"])
    return jsonify({"employee": emp, "updated_recommendations": result})


# ---------------------------------------------------------------------------
# Импорт дополнительных профилей / истории (для жюри на защите, п.7 ТЗ)
# ---------------------------------------------------------------------------
@app.route("/api/import", methods=["POST"])
def api_import():
    err = require_hr()
    if err:
        return err
    body = request.get_json(force=True, silent=True) or {}
    new_employees = body.get("employees", [])
    new_history = body.get("history", [])

    with LOCK:
        existing_ids = {e["employee_id"] for e in STORE["employees"]}
        added, updated = 0, 0
        for emp in new_employees:
            if emp["employee_id"] in existing_ids:
                idx = next(i for i, e in enumerate(STORE["employees"]) if e["employee_id"] == emp["employee_id"])
                STORE["employees"][idx] = emp
                updated += 1
            else:
                STORE["employees"].append(emp)
                added += 1
        STORE["history"].extend(new_history)
        persist_employees()
        persist_history()

    return jsonify({"status": "ok", "employees_added": added, "employees_updated": updated,
                     "history_rows_added": len(new_history)})


# ---------------------------------------------------------------------------
# HR-аналитика
# ---------------------------------------------------------------------------
@app.route("/api/hr/lagging-skills")
def api_hr_lagging():
    err = require_hr()
    if err:
        return err
    return jsonify(recommend.hr_lagging_skills(STORE["employees"], STORE["skills"]))


@app.route("/api/hr/no-next-step")
def api_hr_no_next_step():
    err = require_hr()
    if err:
        return err
    return jsonify(recommend.hr_employees_without_next_step(
        STORE["employees"], STORE["skills"], STORE["events"], STORE["history"]))


@app.route("/api/hr/participation")
def api_hr_participation():
    err = require_hr()
    if err:
        return err
    return jsonify(recommend.hr_event_participation(STORE["events"], STORE["history"]))


@app.route("/api/hr/overview")
def api_hr_overview():
    err = require_hr()
    if err:
        return err
    employees = STORE["employees"]
    by_grade = {}
    by_role = {}
    for e in employees:
        by_grade[e["grade"]] = by_grade.get(e["grade"], 0) + 1
        by_role[e["role"]] = by_role.get(e["role"], 0) + 1
    return jsonify({
        "total_employees": len(employees),
        "by_grade": by_grade,
        "by_role": by_role,
        "total_events": len(STORE["events"]),
        "total_history_rows": len(STORE["history"]),
    })


if __name__ == "__main__":
    load_all()
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
