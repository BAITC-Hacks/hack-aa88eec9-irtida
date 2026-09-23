# Задание для Frontend / UX аккаунта

Ниже находится готовый prompt. Передайте его отдельному ChatGPT/Codex-аккаунту вместе со ссылкой на репозиторий.

---

Ты работаешь над frontend и UX проекта Career Quest для HackAlem AI. Времени мало: доведи обязательный пользовательский сценарий до надёжной 2–3-минутной демонстрации.

Репозиторий: `https://github.com/BAITC-Hacks/hack-aa88eec9-irtida`

Исходная ветка: `feature/career-quest-mvp`.

Создай собственную ветку:

```bash
git fetch origin
git switch feature/career-quest-mvp
git pull --ff-only origin feature/career-quest-mvp
git switch -c work/frontend-ux
```

Сначала прочитай `README.md`, `TASKS.md`, `docs/DEMO.md`, `web/src/api.ts`, `web/src/main.tsx` и `web/src/style.css`. Запусти текущий интерфейс и пройди оба сценария через браузер до изменений.

## Твоя область

Можно изменять:

- `web/**`
- frontend-зависимости внутри `web/package.json` и `web/package-lock.json`, только при реальной необходимости
- новый `docs/FRONTEND_HANDOFF.md`

Не изменяй `server/**`, backend-тесты/fixtures, `.env.example`, общие README/TASKS, Docker/Compose, CI и файлы backend-агента.

Никогда не добавляй API-ключи во frontend, `VITE_*`, код, localStorage, логи или fixtures. Не коммить `.env`, реальные персональные данные, официальный закрытый датасет, `node_modules` или `dist`.

## P0. Сценарий сотрудника

1. Сохрани быстрый демо-вход и явно покажи, что это синтетические данные.
2. Профиль должен сразу объяснять: текущий грейд → следующий грейд → skill gaps → покрытие требований.
3. Рекомендации показывают 1–3 шага, ожидаемый прирост и минимум три понятных фактора.
4. Пользователь чётко различает свежий AI-ответ (`mode=ai`), rules fallback, сохранённый ответ (`cached=true`) и отсутствие подходящего шага.
5. Нельзя визуально выдавать fallback за AI. `provider`/`model` показывай только для настоящего AI-ответа.
6. Выполнение активности должно иметь понятное loading/error/success состояние, обновлять навыки, траекторию и историю без ручной перезагрузки.
7. Защити от повторных кликов на рекомендации и completion во время запроса.

## P0. HR-сценарий

1. Сохрани три обязательных среза: часто проседающие навыки, сотрудники без доступного шага с причиной, участие completed/missed/declined.
2. Добавь понятные empty/loading/error states и не представляй неизвестный уровень как нулевой.
3. Переход из HR-списка в профиль должен быть очевидным, с понятным возвратом в HR-обзор.
4. Импорт должен показывать выбранные файлы, состояние dry-run, количество принятых записей и конкретную ошибку сервера.
5. Пока backend-ветка не передала новый контракт, сохрани текущий JSON-import. Не придумывай multipart URL. Можно подготовить изолированный UI-компонент для последующего подключения.

## P0. Демонстрационная надёжность

1. Проверь desktop 1440/1024, tablet 768 и mobile 360 px.
2. Исправь переполнение таблиц, карточек, кнопок и длинных названий.
3. Добавь доступные labels, focus states, keyboard navigation и корректные status/alert regions.
4. Не загружай внешние шрифты, изображения или CDN-ресурсы: интерфейс должен работать без интернета после сборки.
5. Не добавляй тяжёлую UI-библиотеку ради нескольких компонентов.
6. Для AI показывай ненавязчивый прогресс и сохраняй возможность понять fallback.
7. Сохрани русский интерфейс. Казахскую локализацию делай только после полного P0.

## Текущий API-контракт

Не меняй backend. Используй существующий `api<T>()`, HttpOnly cookie и заголовок `X-Requested-With: CareerQuest`.

- `GET /auth/demo-accounts` → `{ enabled, accounts[] }`
- `POST /auth/demo` → `{ role, employee_id }`
- `GET /employees/{id}` → `Profile`
- `POST /employees/{id}/recommendations` → `Recommendations`
- `POST /employees/{id}/events/{event_id}/complete` → `{ profile, already_completed }`
- `GET /hr/overview` → `Metrics`
- `POST /imports?dry_run=true|false` → summary или стандартная `{ detail }` ошибка

Если не хватает поля, не меняй сервер и не угадывай схему. Опиши запрос backend-команде в `docs/FRONTEND_HANDOFF.md`, включая желаемый JSON-пример и UX, которому это поле нужно.

## Проверка

Запусти:

```bash
cd web
npm ci
npm run build
```

Через браузер проверь employee login, профиль, рекомендации и режимы AI/rules/cached/no-candidates, выполнение и reload, HR-вход и три среза, валидный/невалидный импорт, mobile viewport и keyboard-only сценарий.

Автоматический frontend-тест добавляй только для критического сценария и только если он стабилен. Не трать время на snapshot-тесты, повторяющие разметку.

## Результат

Создай `docs/FRONTEND_HANDOFF.md` с commit SHA, изменёнными файлами, desktop/mobile состояниями, результатом сборки/тестов, UX для AI/fallback/cache/errors, запросами к backend и ограничениями.

Закоммить изменения в `work/frontend-ux` и отправь ветку. Не создавай PR и не объединяй ветки без отдельной команды пользователя.

---
