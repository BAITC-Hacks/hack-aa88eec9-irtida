# Параллельная работа двух ChatGPT-аккаунтов

Исходная ветка: `feature/career-quest-mvp`.

Запускайте две задачи одновременно:

- Backend + AI + данные: [BACKEND_TASK.md](BACKEND_TASK.md)
- Frontend + UX: [FRONTEND_TASK.md](FRONTEND_TASK.md)

Каждый аккаунт должен создать свою ветку от одной исходной версии:

```bash
git fetch origin
git switch feature/career-quest-mvp
git pull --ff-only origin feature/career-quest-mvp
```

Backend-аккаунт продолжает в `work/backend-kit-ai`, frontend-аккаунт — в `work/frontend-ux`.

## Границы владения

| Область | Backend-аккаунт | Frontend-аккаунт |
| --- | --- | --- |
| `server/**` | Владелец | Не изменяет |
| `web/**` | Не изменяет | Владелец |
| `examples/backend-*` | Владелец | Не изменяет |
| `docs/BACKEND_HANDOFF.md` | Владелец | Не изменяет |
| `docs/FRONTEND_HANDOFF.md` | Не изменяет | Владелец |
| `README.md`, `TASKS.md`, Docker/Compose, CI | Не изменять во время параллельной работы | Не изменять во время параллельной работы |
| `.env`, ключи, база, официальный кит | Никогда не коммитить | Никогда не коммитить |

Backend обязан сохранить существующие URL и поля API. Если это невозможно, он описывает совместимое расширение в `docs/BACKEND_HANDOFF.md`; frontend не угадывает будущий контракт.

## Общий API-контракт на время параллельной работы

- `GET /api/v1/auth/demo-accounts`
- `POST /api/v1/auth/demo`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `GET /api/v1/employees`
- `GET /api/v1/employees/{employee_id}`
- `POST /api/v1/employees/{employee_id}/recommendations`
- `POST /api/v1/employees/{employee_id}/events/{event_id}/complete`
- `GET /api/v1/hr/overview`
- `POST /api/v1/imports?dry_run=true|false`
- `GET /api/v1/health`

Все изменяющие запросы отправляют `X-Requested-With: CareerQuest`, сессия хранится в HttpOnly cookie. Frontend не хранит API-ключи и не обращается к OpenAI/NVIDIA напрямую.

## Порядок объединения

1. Оба аккаунта запускают свои тесты и коммитят только свою область.
2. Backend передаёт имя ветки, commit SHA, результат `pytest` и `docs/BACKEND_HANDOFF.md`.
3. Frontend передаёт имя ветки, commit SHA, результат `npm run build` и `docs/FRONTEND_HANDOFF.md`.
4. В интеграционной ветке сначала объединить backend, затем frontend.
5. Запустить `python -m pytest -q`, `cd web && npm run build`, затем пройти браузером основной сценарий.
6. Только после интеграции обновить общий README и сценарий защиты.

## Общий критерий готовности

- Оригинальный набор и дополнительные профили жюри импортируются без ручной переделки.
- Живая AI-рекомендация укладывается в 10 секунд и использует минимум три фактора.
- Выполнение активности корректно применяет `gain`/`max_level`, повторный запрос не удваивает прирост.
- Профиль, рекомендации, прогресс и три обязательных HR-среза работают через UI.
- Сотрудник не видит чужие профили и HR-экран.
- Интерфейс не выдаёт rules fallback или кэш за свежий AI-ответ.
- `.env`, ключи, локальная БД, персональные данные и официальный кит не попадают в Git.

## Если осталось меньше часа

Остановить дополнительное оформление и второй AI-провайдер. Завершить импорт официального формата, один основной AI-провайдер, обязательный user flow, проверки и репетицию.
