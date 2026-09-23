# Backend / AI — интеграция Career Quest

Дата проверки: 2026-09-23. Ветка: `work/backend-kit-ai`.

**Коммит реализации:** `bcd91686a1dd67d04fc1e6cbd7c70d3047281ae6`.
База: `feature/career-quest-mvp`, `5024da83b41d0412c92ff70f9c33ef39a534c523`.
Этот документ добавлен отдельным следующим коммитом. PR и merge не выполнялись.

Backend готов к интеграции на официальном наборе. **Живой OpenAI-запрос остаётся непроверенным:** в окружении нет ключа. Frontend, общие README/TASKS, Docker/Compose и CI этим backend-изменением не редактировались. Чужие локальные изменения не включены в backend-коммит.

## Что изменено

| Файлы | Назначение |
|---|---|
| `server/app/kit_schemas.py`, `kit_import.py` | Исходный формат Career Quest 1.0, ссылки, JSON/CSV-ошибки, атомарный импорт, восстановление навыков после оценки |
| `server/app/import_service.py`, `import_kit_cli.py` | Безопасный переход с исходного demo, локальный CLI |
| `server/app/ingest.py`, `schemas.py` | Совместимость `demo-v1`, строгая валидация, повторы и конфликты |
| `server/app/db.py` | Новая таблица `import_records` для исходных записей; восстановление busy timeout соединений |
| `server/app/domain/progression.py`, `services.py` | Следующий грейд, critical skills, доступность сессий, ожидаемый прирост, HR |
| `server/app/main.py`, `middleware.py` | Multipart API, occurrence completion, роли, транзакции, квоты и ограничение фактического размера запроса |
| `server/app/ai/providers.py`, `ai/smoke.py` | Валидация AI, единый timeout, один явный синтетический live smoke |
| `server/requirements.txt` | Добавлен `python-multipart==0.0.32` |
| `.env.example` | Новая пустая переменная `AI_DATA_POLICY_APPROVED` |
| `server/tests/test_core.py` | Две AI-проверки явно разрешают обработку синтетических данных |
| `server/tests/test_ai_provider.py`, `test_api_safety.py`, `test_imports.py`, `test_kit_import.py`, `test_kit_api.py`, `test_official_kit_local.py`, `test_progress_hr.py` | Регрессии API, импорта, AI, конкуренции, бизнес-правил и полного набора |
| `docs/BACKEND_HANDOFF.md` | Этот документ |

Исходники кита, `.env`, ключи, базы, временные файлы и окружение не включены. Кит в текущей рабочей папке дополнительно исключён через локальный `.git/info/exclude`; при переносе держите его в уже игнорируемом `data/private/`.

## Правила официального кита

Прочитан приложенный `README.md`/`README.ru.md` Career Quest 1.0. Дата моделирования — **2026-10-01**, история — 2024-10-01…2026-09-30.

- Грейды: Junior → Middle → Senior → Lead. Для перехода используются `required_skills` и `critical_skills` **следующего** грейда текущей роли. Career goal сохраняется, но не заменяет этот маршрут. Для Lead возвращается `highest_grade`.
- Пропущенный навык официального профиля означает **0**. В отдельном `demo-v1` пропущенное значение по-прежнему неизвестно: `null` в траектории, исключено из знаменателя HR-доли.
- Навыки исходного профиля — последняя оценка. Начисляются только `completed` с датой **строго после** `last_review_date`. Равная дате оценки запись уже учтена. Старые завершения не проигрываются повторно.
- Оригинальные записи хранятся локально в `import_records`. При дополнительной истории навыки пересчитываются от исходной оценки в порядке `(date, record_id)`, включая завершения через API. Повтор импорта не сбрасывает локальный прогресс. Изменённая исходная запись с прежним ID отклоняется, а не перезаписывается.
- Прирост: `max(0, min(gain, max_level - current, 5 - current))`. Положительный `gain` больше 5 допустим и обрезается пределом навыка. Числа и evidence строит сервер.
- Покрытие: `sum(min(current, required)) / sum(required) * 100`, округлённое до целого. Это наш показатель покрытия, поскольку README не задаёт единой формулы процента или автоматического повышения. Грейд автоматически не меняется.
- Рекомендации исключают обязательные мероприятия, неподходящую аудиторию, невыполненные prerequisites, отсутствие будущих сессий и завершённые однократные события. Self-paced доступен без даты сессии.
- Повтор разрешён только `EV_036`. Сервер предлагает ближайшую сессию не раньше даты среза и позже последней завершённой сессии. Следующие сессии появляются последовательно.
- Алгоритмический рейтинг учитывает сокращение разрыва, critical skills и историю формата. Critical-разрывы получают вес 2; это объяснимый выбор приложения, а не правило организаторов. Нет правила выбирать минимальный навык.

**Расхождение README и данных:** в исходной истории есть 544 участия в обязательных мероприятиях после уже завершённого такого мероприятия. Они сохранены, импорт возвращает предупреждение `mandatory_history_repeated_after_completion`. Исключение разрешено только для обязательных событий с пустыми эффектами, поэтому повторного начисления не возникает. Правило добровольных повторов не ослаблено.

## Импорт оригинальных файлов

Существующий `POST /api/v1/imports?dry_run=true|false` сохранён для `demo-v1`. Форматы не смешиваются в одной базе: после перехода на кит дополнительные данные отправляйте в `/imports/kit`.

Новый **HR-only** endpoint:

```text
POST /api/v1/imports/kit?dry_run=true|false&replace_demo=true|false
Content-Type: multipart/form-data; boundary=...
X-Requested-With: CareerQuest
Cookie: cq_session=...
```

Передайте файлы с исходными именами. Сервер определяет содержимое по `filename`, без ручного преобразования:

| Файл | Структура |
|---|---|
| `skills.json` | `{meta, proficiency_scale, skills: [...], role_profiles: [...]}` |
| `employees.json` | `{meta, employees: [...]}` |
| `events.json` | `{meta, events: [...]}` |
| `activity_history.csv` | `record_id,employee_id,event_id,date,due_date,status,completion_pct,score,feedback_rating,assigned_by` |

`meta`: `{dataset: "Career Quest", version: "1.0", as_of_date: "2026-10-01"}`. Проверяется оригинальная схема, включая manager, role/grade, skill/event/employee references, даты, статусы, проценты, аудиторию, prerequisites, gain и max_level. Файлы — UTF-8, BOM допустим. Максимум четыре файла и 5 000 000 байт на весь HTTP-запрос, включая multipart. Лимит действует и без Content-Length.

Первый импорт: четыре оригинальных файла. Для дополнений достаточно `employees.json` и/или `activity_history.csv`; справочники можно не повторять. Связанные менеджеры должны существовать или поступать в том же импорте. CSV использует исходные колонки даже при нескольких новых строках.

Точная повторная запись пропускается. Конфликт ID, неверная ссылка или поле отклоняет **весь** запрос. Проверочный импорт не меняет базу; обычный записывается одной транзакцией.

Пример интеграции без изменения текущего JSON API-клиента:

```ts
async function importKit(files: File[], dryRun: boolean, replaceDemo = false) {
  const body = new FormData();
  for (const file of files) body.append("files", file, file.name);
  const response = await fetch(
    `/api/v1/imports/kit?dry_run=${dryRun}&replace_demo=${replaceDemo}`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-Requested-With": "CareerQuest" },
      body,
    },
  );
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `Ошибка ${response.status}`);
  return data;
}
```

**Не задавайте Content-Type вручную**: браузер добавляет multipart boundary. Текущий JSON helper добавляет `application/json`, поэтому для multipart нужен отдельный вызов.

Результат полного набора на пустой базе:

```json
{
  "schema": "kit-v1", "dry_run": false, "snapshot_date": "2026-10-01",
  "employees_added": 200, "history_added": 2743,
  "skills_added": 60, "events_added": 40,
  "completed_after_review": 318, "demo_replaced": false,
  "warnings": [{"code": "mandatory_history_repeated_after_completion", "count": 544, "reason": "..."}]
}
```

`completed_after_review` — число завершений после оценки во всём собранном состоянии, а не число вновь начисленных записей. При точном повторе все `*_added` равны нулю.

Ошибки имеют совместимое строковое `detail` и дополнительный список:

```json
{
  "detail": "activity_history.csv: line 2.event_id: Unknown event reference",
  "errors": [{"source": "activity_history.csv", "path": "line 2.event_id", "reason": "Unknown event reference"}]
}
```

Для JSON путь вида `$.employees[0].skills.SK_SYSTEM_DESIGN`. Существующий frontend может показывать `detail`; улучшенный интерфейс может выделять `source`/`path`. Ошибки `demo-v1` от Pydantic также могут возвращать прежний массив `detail` с `loc`/`msg`.

### Переход с автоматического demo

При обычном запуске пустая база в DEMO_MODE заполняется demo-v1. Для перехода HR явно использует `replace_demo=true` и все четыре файла. Разрешена замена **только неизменённого исходного demo**. Пользовательские импорты или завершения делают такую замену недоступной; используйте новый DATABASE_URL, сохранив старую базу.

Сначала выполните dry-run с тем же флагом, затем обычный запрос. Ошибка и dry-run откатывают замену полностью. Успешная замена отзывает старые employee-сессии; текущая HR-сессия сохраняется. После импорта обновите список сотрудников, HR-обзор и экран входа.

Для локального импорта до старта сервера есть CLI из корня репозитория:

```powershell
$env:DATABASE_URL='sqlite:///./data/private/official-demo.db'
python -m server.app.import_kit_cli 'путь/к/каталогу/четырёх/файлов' --dry-run
python -m server.app.import_kit_cli 'путь/к/каталогу/четырёх/файлов'
```

CLI не запускает автозаполнение demo и ничего не отправляет в сеть. Для существующего нетронутого demo есть `--replace-demo`. Запускайте сервер с тем же DATABASE_URL.

## Существующий API и расширения для frontend

Все прежние URL сохранены. Cookie — HttpOnly; каждый изменяющий запрос требует `X-Requested-With: CareerQuest`, Origin проверяется сервером.

- `GET /api/v1/employees/{id}`: прежние `employee`, `trajectory`, `history`, `available`, `recommendation`.
- `POST /api/v1/employees/{id}/recommendations`: прежние `items`, `mode`, `reason`, `cached`, `provider`, `model`, `elapsed_ms`. Каждый item сохраняет `id`, `title`, `type`, `changes`, `evidence`.
- `POST /api/v1/employees/{id}/events/{event_id}/complete`: прежние `profile` и `already_completed`. Возвращённый `profile` теперь всегда содержит `recommendation: null`; обновите профиль этим ответом, затем при необходимости снова запросите рекомендации.
- `GET /api/v1/hr/overview`: прежние `employee_count`, `gaps`, `no_step`, `participation`.

Совместимые дополнительные поля:

| Поле | Что показывать |
|---|---|
| `employee.source_format`, `snapshot_date`, `last_review_date`, `department`, `work_format`, `preferred_language`, `career_goal` | Контекст официального профиля; базовые `id/name/role/grade/tenure_months/skills` сохранены |
| `trajectory.skills[].critical` | Критический навык следующего грейда |
| `trajectory.critical_requirements_met` | `true/false/null`; не равно автоматическому повышению |
| `trajectory.status = highest_grade` | «Достигнут старший грейд; следующего грейда нет» |
| `item.session_date`, `item.occurrence_id` | Дата предлагаемой сессии; `null` для self-paced и старого demo |
| `item.critical_benefit` | Число уровней закрытого critical-разрыва, рассчитанное сервером |
| `gaps[].id`, `total_gap` | Стабильный skill ID и суммарный разрыв |
| `no_step[].reason_detail`, `blockers` | Готовая причина отсутствия шага и численные причины исключения событий |
| `participation[].no_show/dropped/in_progress/overdue` | Точные дополнительные статусы кита |

`no_step.reason` сохраняет `no_grade_rule`, `missing_skills`, `no_eligible_activity`; добавлен `highest_grade`. Предпочитайте выводить готовый `reason_detail`. `blockers` может включать completed, role, grade, unknown_skill, skill_cap, no_relevant_gain, mandatory, prerequisites, no_upcoming_session.

История сохраняет точные статусы: completed — завершено; in_progress — в процессе; dropped — прекращено; no_show — неявка; declined — отказ; overdue — просрочено. Старый demo также использует missed. HR-поле **`missed` включает `no_show`** для совместимости; при суммировании точных статусов не прибавляйте оба повторно. Это количество записей участия, не уникальных людей.

### Завершение сессии

Для `EV_036` передавайте `occurrence_id` из текущего item. Без него сервер вернёт 422. Для остальных событий запрос без тела остаётся рабочим. Универсальный вариант:

```ts
await api(`/employees/${employeeId}/events/${item.id}/complete`, {
  method: "POST",
  ...(item.occurrence_id
    ? { body: JSON.stringify({ occurrence_id: item.occurrence_id }) }
    : {}),
});
```

Повтор того же occurrence, включая конкурентные запросы, возвращает `already_completed=true`, без повторного прироста. Новая сессия клуба — отдельное прохождение. Произвольная или устаревшая незавершённая сессия возвращает 422: обновите профиль/рекомендации.

Это локальная симуляция кита: завершение scheduled-события записывает дату выбранной сессии; self-paced — дату среза 2026-10-01. Сервер не выдаёт это за подтверждённое посещение реального будущего мероприятия.

### Состояния рекомендаций и ошибки

- `mode=ai, cached=false`: свежий проверенный ответ модели.
- `cached=true`: сохранённый ответ, не новый AI-вызов. `elapsed_ms` — задержка исходного вычисления.
- `mode=rules`: выбран алгоритмический режим.
- `mode=fallback`: AI недоступен/невалиден/не разрешён политикой данных; покажите `reason` и явную отметку резервного подбора.
- `mode=no_candidates`: пустой список — корректное состояние.

401 — нужен вход; 403 — роль/Origin/заголовок; 409 — расчёт уже идёт или профиль изменился; 413 — лимит тела; 415 — неверный формат импорта; 422 — проверка данных/доступности; 429 — лимит AI/входов; 503 — временно недоступна БД. HR может читать и запрашивать рекомендации, но **не может завершать события за сотрудника**.

## AI и запуск

Установите обновлённые зависимости: `python -m pip install -r server/requirements-dev.txt`.

Ключ хранится только в локальном backend `.env`/environment. Не добавляйте его в frontend, VITE-переменные, чат или Git. Для синтетических либо разрешённых организаторами данных:

```dotenv
AI_PROVIDER=openai
OPENAI_MODEL=gpt-4.1-mini
AI_DATA_POLICY_APPROVED=true
```

`OPENAI_API_KEY` нужно заполнить локально отдельно. Без разрешения обработки сервер возвращает явный fallback и не вызывает облако. README предоставленного кита утверждает, что данные синтетические; иного разрешения для будущих реальных загрузок это не даёт.

OpenAI: строгий Structured Outputs JSON Schema с enum допустимых event IDs, `store=false`, temperature 0, max_tokens 200, max_retries 0. Проверяются 1–3 уникальных допустимых ID, JSON, отсутствие лишних полей, отказа и обрезанного ответа. Модель не возвращает числовые объяснения: они берутся из серверного расчёта. Имя/ID сотрудника и сырая история не передаются.

Один общий provider timeout: по умолчанию 7 секунд, максимум 8, включая закрытие клиента. Нет последовательного ожидания второго провайдера. Маршрут дополнительно ограничивает ожидание AI оставшимся бюджетом; короткое ожидание блокировки SQLite не складывается с обычными 5 секундами. При конфликте БД возвращается 503. Кэш: 1 час, fallback — 30 секунд; квоты по умолчанию 6 запросов/минуту на профиль и 300/скользящие сутки на приложение, атомарные между процессами с одной SQLite.

Живой запрос **не выполнен**: команда ниже завершилась `mode=not_run, reason=provider_not_configured`. Поэтому живую задержку/доступность модели и расход credits не заявляем. После локального добавления ключа один запрос на встроенных синтетических данных:

```powershell
python -m server.app.ai.smoke --synthetic
```

Команда не читает профили из БД или файлы кита и не печатает ключи/текст provider-ошибок; возвращает model, mode, elapsed_ms и IDs. NVIDIA оставлен как документированный резерв; live-проверка, failover и денежный учёт не добавлялись.

Проверенные официальные источники API: [gpt-4.1-mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [store=false](https://developers.openai.com/api/docs/guides/migrate-to-responses), [multipart Starlette](https://www.starlette.io/requests/). `store=false` не означает гарантию Zero Data Retention.

## Проверки и оставшиеся ограничения

Финальный прогон: **199 passed, 1 warning, 10.78s**; `python -m pip check` → **No broken requirements found**. Warning — существующее Starlette/httpx deprecation. Полный официальный набор проверен локально; содержимое кита в тесты не встроено.

На Windows для точных команд использовалась существующая `.venv` в PATH и новый игнорируемый basetemp из-за ACL старого временного каталога:

```powershell
$env:CAREER_QUEST_KIT_DIR=(Resolve-Path 'путь/к/четырём/файлам').Path
$env:PYTEST_ADDOPTS='--basetemp=data/private/новая-папка-тестов -p no:cacheprovider'
python -m pytest -q
python -m pip check
```

Без `CAREER_QUEST_KIT_DIR` три проверки внешнего официального набора пропускаются; синтетические тесты продолжают работать без сети и ключей. Проверены дополнительный импорт, конфликты, ошибки, dry-run, reimport после API-завершений, occurrence/concurrency, gain/max_level, critical-vs-lowest contrast, timeout/invalid AI, кэш, Origin, роли, rate limits, фактический размер body, HR на полном наборе и 2 000 синтетических профилях.

Перед публикацией выполнены проверка секретов точного Git index, `git diff --cached --check` и `git status --ignored --short`. Отправлены только backend, новая пустая env-переменная и этот handoff.

Осталось: один live AI smoke с локальным ключом и совместная UI-проверка после frontend-интеграции. UI/build не проверялись этим backend-заданием. DEMO_MODE остаётся режимом **локальной синтетической демонстрации**, без production-auth. Новая таблица создаётся через `create_all`; существующие таблицы не изменены, полноценные миграции/PostgreSQL не добавлялись. Для экономии времени второй провайдер и денежная статистика отложены.
