# Интеграция Career Quest

Актуальная доработка от **2026-09-23**, репозиторий `BAITC-Hacks/hack-aa88eec9-irtida`, ветка `main`. React и FastAPI работают с одним origin и одной SQLite. Backend — источник допустимости действий, skill gain и прогресса. Инструкция запуска — [README](../README.md), защита — [DEMO](DEMO.md), сверка с ТЗ — [TZ_AUDIT](TZ_AUDIT.md).

## Проверенные контракты

| API | Поведение |
| --- | --- |
| GET `/auth/status` | Состояние первичной настройки; не раскрывает профили |
| POST `/auth/setup` | Первый HR, только loopback, атомарно и однократно |
| POST `/auth/login` | username/password/role; роль проверяется сервером |
| POST `/auth/register` | Одноразовое приглашение определяет роль и employee_id |
| GET `/auth/me`, POST `/auth/logout` | Серверная HttpOnly cookie, истечение/отзыв сессии |
| GET `/hr/accounts`, POST `/hr/invitations` | Только HR, приглашение действует 24 часа |
| GET `/employees`, GET `/catalog`, GET `/hr/overview` | Только HR; весь Kit, агрегаты, причины отсутствия шага |
| GET `/employees/{id}` | Только владелец или HR; profile, skill_catalog, trajectory, history, available, recommendation |
| POST `/employees/{id}/recommendations` | 1–3 ID из допустимого списка; ai/rules/fallback/no_candidates и cached |
| POST `/employees/{id}/events/{event_id}/complete` | Только владелец; серверный полный профиль и already_completed. EV_036 требует occurrence_id |
| POST `/imports/kit` | Только HR; исходный multipart files, dry_run и атомарный commit |
| POST `/imports` | Сохранён отдельный demo-v1 импорт для synthetic fixtures |

В `skill_catalog` поле типа навыка называется **kind**, как в нормализованном каталоге. Original Kit использует type, который преобразует importer. UI показывает рассчитанные сервером projected_coverage, critical_benefit и changes. Повторный импорт/выполнение не удваивает прирост. `Accept-Language: ru|en|kk` изменяет только представление: ID, canonical role, числа и база остаются неизменными. role_label/role_labels предназначены для подписей интерфейса.

Изменяющие запросы требуют `X-Requested-With: CareerQuest` и разрешённого Origin. 401 завершает сессию, 403 запрещает действие, 409 обозначает конфликт, 413/415/422 — ошибки входа, 429 — квоту, 503 — временную недоступность. POST автоматически не повторяется. Валидация не отражает пароли/коды приглашений в ответах. Scrypt работает с отдельной солью, число одновременных вычислений ограничено.

Demo-вход отключён по умолчанию. Исторические `/auth/demo` endpoints доступны только при явном DEMO_MODE=true для тестов. Это не обычный вход продукта.

## Kit и точность расчётов

Подтверждены **200 профилей, 60 навыков, 40 событий, 2 743 участия, 8 ролей**. Срез — 2026-10-01. Воспроизводятся 318 завершений строго после последней оценки. Импорт сохраняет 544 повтора mandatory-событий с предупреждением; прирост у них отсутствует. Файлы организаторов не изменяются и не включаются в Git.

Первый local launcher импортирует Kit в `data/career-quest-kit.db`; исходная трёхпрофильная demo-база остаётся отдельной. В текущей рабочей базе полный Kit уже загружен, аккаунтов пользователей ещё нет. Будущий повторный запуск сохраняет прогресс и аккаунты. Замена demo запрещена при прогрессе и связанных аккаунтах/приглашениях.

Нет публичных рейтингов, автоматического повышения грейда или наград за обязательные процессы. HR считает записи участия; совместимый missed уже включает no_show. Lead не имеет следующего грейда в исходном наборе.

## Воспроизводимые проверки

Из корня, после установки зависимостей (на Linux/macOS `npm` вместо `npm.cmd`):

```powershell
$env:CAREER_QUEST_KIT_DIR=(Resolve-Path 'career_quest_dataset/case_1/career_quest_dataset').Path
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pip check
npm.cmd --prefix web test
npm.cmd --prefix web run build
npm.cmd --prefix web run test:integration
npm.cmd --prefix web run test:e2e
git diff --check
```

Без Kit env backend пропускает проверки внешних файлов, HTTP integration явно сообщает SKIP. CI использует независимые synthetic fixtures. E2E требует установленного Edge на Windows; `CQ_BROWSER_CHANNEL=chrome` выбирает Chrome. Все browser accounts/passwords синтетические, база отдельная временная, пользовательский профиль браузера не используется. Скриншоты остаются в игнорируемом `web/test-results/`.

## Результаты доработки

- **Backend: 250 passed, 0 failed**, с полным Kit. Один существующий warning Starlette о httpx/TestClient. `pip check` — без конфликтов.
- **Frontend: 32 passed, 0 failed**: API-клиент, auth bodies, React SSR, импорт, completion, статусы, три языка. TypeScript/Vite production build проходит.
- **HTTP integration: PASS, 45 типизированных ответов.** Полный Kit, dry-run/commit/reimport/422, обычные и повторные EV_036, fallback, новый парольный вход, первый HR, приглашение, профиль Customer Support, регистрация, запрет чужого доступа/смены роли, три языка, сохранение после перезапуска.
- **Headless Edge E2E: PASS.** Настройка HR через UI, импорт synthetic 40 событий/60 навыков, пять разделов HR, фильтр, профиль, приглашение, регистрация сотрудника, рекомендации, выполнение, reload, logout/login, RU/EN/KK и мобильный viewport 390 px. Браузерные ошибки проверены; горизонтального переполнения на проверенном мобильном экране нет.
- **Launcher smoke: PASS.** Реальный занятый порт 49457 → 49458, разрешённый local origin, production HTML, health и первый setup. Завершён только дочерний процесс этого теста. Рабочий Kit сохранён.
- Локальный диагностический замер расчётов на 200 профилях: HR ~90 мс, самый медленный профиль ~39 мс; это время Python-расчёта без сети/браузера, не SLA. Наибольший контекст модели — 11 987 символов при лимите 24 000. Есть допустимый следующий шаг у 159 из 200 сотрудников; причины остальных видны HR.

Живой cloud AI не проверен: ключи не настроены, фактический режим rules. Docker smoke в этой сессии не выполнялся. Автоматические тесты провайдера не являются подтверждением живого LLM или сетевой задержки. GitHub Actions проверяется отдельно после публикации; локальные результаты не выдаются за статус CI.

## Следующие технические шаги

Подключение и оценка живой LLM на проверочных профилях, корпоративный SSO/MFA и отзыв доступа, восстановление пароля, PostgreSQL/миграции, резервные копии, интеграция LMS. Казахский UI требует редакторской проверки носителем; произвольные описания импортированных данных остаются на языке источника.

Исторические BACKEND_HANDOFF/FRONTEND_HANDOFF сохранены для контекста исходных веток; их ограничения auth, локализации и browser QA больше не описывают текущее состояние.
