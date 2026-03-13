# CLAUDE.md — Chaldea AI Team Development

Единый операционный стандарт для всех AI-агентов, работающих в репозитории Chaldea.
Цель: ускорять разработку без потери качества, безопасности и предсказуемости изменений.

---

## 1. О проекте

Chaldea — браузерная RPG-игра с микросервисной архитектурой на одном инстансе (Docker Compose).
Игроки создают персонажей, исследуют мир, прокачивают навыки, экипируют предметы и сражаются в пошаговых PvP-боях.

### Технологический стек

| Слой | Технология |
|------|-----------|
| Backend (все 10 сервисов) | Python 3, FastAPI, SQLAlchemy, Pydantic <2.0 |
| Frontend | React 18, Vite, Redux Toolkit, React Router v6, Axios, SCSS |
| Основная БД | MySQL 8.0 (единая база `mydatabase` для всех сервисов) |
| Документная БД | MongoDB 6.0 (логи и снапшоты боёв) |
| Кэш / State | Redis 7 (состояние боёв, Pub/Sub) |
| Очереди | RabbitMQ (уведомления, Celery broker) |
| Фоновые задачи | Celery (worker + beat, только для battle-service) |
| API Gateway | Nginx (port 80) |
| Файловое хранилище | S3-совместимое (s3.twcstorage.ru), boto3 |
| Оркестрация | Docker Compose |

### Сервисы и порты

| Сервис | Порт | Путь в репозитории | Особенности |
|--------|------|--------------------|-------------|
| user-service | 8000 | `services/user-service/` | JWT-аутентификация, sync SQLAlchemy |
| photo-service | 8001 | `services/photo-service/` | Raw PyMySQL (не ORM), S3, Pillow |
| character-attributes-service | 8002 | `services/character-attributes-service/` | Sync SQLAlchemy |
| skills-service | 8003 | `services/skills-service/` | Async SQLAlchemy (aiomysql) |
| inventory-service | 8004 | `services/inventory-service/` | Sync SQLAlchemy |
| character-service | 8005 | `services/character-service/` | Sync SQLAlchemy, presets.py с игровыми данными |
| locations-service | 8006 | `services/locations-service/` | Async SQLAlchemy (aiomysql) |
| notification-service | 8007 | `services/notification-service/` | SSE, RabbitMQ consumers, pika |
| battle-service | 8010 | `services/battle-service/` | Async (aiomysql + Motor + aioredis), Celery |
| autobattle-service | 8011 | `services/autobattle-service/` | Stateless, Redis Pub/Sub, httpx |
| frontend | 5555 | `services/frontend/app-chaldea/` | Vite dev server |
| api-gateway (Nginx) | 80 | `docker/api-gateway/` | Роутинг по path prefix |

### Структура репозитория

```
chaldea/
├── CLAUDE.md                    # Этот файл (глобальные правила для AI-агентов)
├── docker-compose.yml           # Оркестрация всех сервисов
├── docker/                      # Dockerfile и конфиги для каждого сервиса
│   ├── api-gateway/nginx.conf   # Маршрутизация Nginx
│   ├── mysql/                   # MySQL init, backup, restore
│   └── <service>/Dockerfile     # Dockerfile каждого сервиса
├── services/                    # Исходный код сервисов
│   ├── <service>/app/           # FastAPI-приложение (main.py, models.py, schemas.py, crud.py, ...)
│   └── frontend/app-chaldea/    # React-приложение
├── docs/                        # Документация
│   ├── ARCHITECTURE.md          # Общий обзор архитектуры
│   ├── ISSUES.md                # Известные проблемы и tech debt
│   └── services/<service>.md    # Детальная документация каждого сервиса
└── backup.sh                    # Скрипт бэкапа БД
```

### Типовая структура backend-сервиса

```
services/<service>/app/
├── main.py               # FastAPI app, роуты, CORS, startup events
├── models.py             # SQLAlchemy ORM-модели
├── schemas.py            # Pydantic-схемы (request/response)
├── crud.py               # Бизнес-логика и запросы к БД
├── database.py           # Engine, SessionLocal, Base, get_db()
├── config.py             # Settings из переменных окружения
├── rabbitmq_consumer.py  # RabbitMQ consumer (ЗАКОММЕНТИРОВАН в большинстве сервисов)
└── requirements.txt      # Python-зависимости
```

---

## 2. Межсервисные зависимости

Критически важно понимать — **сервисы активно вызывают друг друга по HTTP**. Изменение API-контракта одного сервиса может сломать несколько других.

### Граф HTTP-зависимостей

```
character-service ──> inventory-service, skills-service, character-attributes-service, user-service
locations-service ──> character-service, character-attributes-service
inventory-service ──> character-attributes-service
battle-service ──> character-attributes-service, character-service, skills-service, inventory-service
autobattle-service ──> battle-service
user-service ──> character-service, locations-service
notification-service ──> user-service
```

### RabbitMQ очереди (активные)

- `user_registration`: user-service -> notification-service
- `general_notifications`: notification-service (consumer + producer)
- Celery (broker RabbitMQ): battle-service -> celery-worker (задача `save_log`)

### Общая БД

Все сервисы работают с одной MySQL-базой `mydatabase`. Каждый сервис "владеет" своими таблицами, но физически они в одной БД. При изменении схемы таблицы учитывай, что другие сервисы могут читать эту таблицу напрямую (например, photo-service обновляет поля в `users`, `characters`, `items`, `skills` и др.).

---

## 3. Роль агента

Ты — инженер в мультисервисной платформе. Твоя ответственность:

1. **Сохранить работоспособность** существующей системы.
2. Делать **минимально достаточные** и проверяемые изменения.
3. Явно показывать **риски, допущения и ограничения**.
4. Оставлять проект в более понятном состоянии, чем до правки.

---

## 4. Базовые принципы

1. **Сначала понимание, потом изменение** — перед правкой изучи точку входа, зависимости и путь данных. Прочитай документацию в `docs/services/<service>.md`.
2. **Минимальный дифф** — меняй только то, что необходимо для задачи.
3. **Явные допущения** — если чего-то не хватает (контекст, env, сервис), фиксируй это в ответе.
4. **Проверяемость** — каждая правка должна сопровождаться способом проверки.
5. **Обратная совместимость** — ломающее изменение допустимо только при явном обосновании.
6. **Безопасность важнее удобства** — не добавляй секреты в код/логи/документацию.
7. **Кросс-сервисное мышление** — любая правка может затронуть другие сервисы. Проверяй граф зависимостей выше.

---

## 5. Workflow для задач

### Шаг 1. Уточнение зоны изменений
- Определи, какие сервисы/папки затронуты.
- Проверь `docs/services/<service>.md` для понимания эндпоинтов, таблиц и зависимостей.
- Найди существующие паттерны реализации и следуй им.

### Шаг 2. План
- Сформулируй короткий план из 3–6 шагов.
- Отметь риски: миграции, API-контракты, кросс-сервисные эффекты, кеш, очереди.

### Шаг 3. Реализация
- Держи изменения атомарными.
- Не делай скрытых рефакторингов «по пути».
- Следуй паттернам конкретного сервиса (sync vs async, ORM vs raw SQL).

### Шаг 4. Проверка
- Синтаксическая проверка / линт (если применимо).
- Тесты в затронутом сервисе.
- Проверка, что кросс-сервисные вызовы не сломаны.

### Шаг 5. Отчёт
В финальном сообщении:
- Что изменено и где.
- Почему выбран такой подход.
- Что и как проверено.
- Что осталось риском / требует отдельной задачи.

---

## 6. Качество кода

1. Следуй стилю конкретного сервиса — не смешивай sync и async подходы внутри одного сервиса.
2. Предпочитай читаемость микро-оптимизациям.
3. Не добавляй магические значения без именованных констант.
4. YAGNI — не усложняй архитектуру без необходимости.
5. Новая логика = тест или объяснение, почему тест невозможен.
6. Ошибки должны быть информативными, но без утечки чувствительных данных.

---

## 7. Работа с данными и контрактами

Перед изменениями API / событий / схемы БД:
- Проверь потребителей контракта (см. граф зависимостей в секции 2).
- Оцени обратную совместимость.
- Если меняется схема — опиши стратегию миграции и rollback.
- Для очередей и фоновых задач учитывай идемпотентность.

Сервисы с миграциями (Alembic): character-service, character-attributes-service, skills-service, inventory-service.
Сервисы без миграций: user-service (Alembic есть, но legacy), locations-service, notification-service, battle-service, photo-service.

**Правило (см. T2 в `docs/ISSUES.md`):** если задача затрагивает сервис без Alembic — добавить его в рамках текущей работы (init, initial-миграция, `alembic` в requirements.txt). Отдельным коммитом от основной задачи.

---

## 8. Безопасность и секреты

**Запрещено:**
- Коммитить ключи, токены, пароли, приватные сертификаты.
- Логировать секреты или персональные данные.
- Использовать «временные» бэкдоры.

**Обязательно:**
- Секреты только через `.env` / переменные окружения.
- В примерах — только маскированные значения.
- При добавлении нового секрета — добавить его в docker-compose.yml через `environment:`.

---

## 9. Git-конвенции

1. Один commit = одна логическая цель.
2. Формат commit message:
   - `feat(<service>): краткое описание`
   - `fix(<service>): краткое описание`
   - `refactor(<service>): краткое описание`
   - `docs(<scope>): краткое описание`
3. Не смешивай функциональные изменения и форматирование.
4. Не трогай нерелевантные файлы.

---

## 10. Важные особенности кодовой базы

Эти нюансы нужно помнить при работе с проектом:

1. **Pydantic <2.0** — все backend-сервисы используют Pydantic v1 синтаксис (`class Config: orm_mode = True`, а не `model_config`).
2. **Смешанный sync/async** — user-service, character-service, inventory-service, character-attributes-service используют sync SQLAlchemy. locations-service, skills-service, battle-service используют async (aiomysql).
3. **photo-service — особый** — использует raw PyMySQL с DictCursor вместо SQLAlchemy ORM.
4. **RabbitMQ consumers закомментированы** в character-service, skills-service, inventory-service, character-attributes-service. Вместо них используются прямые HTTP-вызовы.
5. **Единая БД** — все сервисы подключены к одному MySQL-инстансу. Нет изоляции на уровне БД.
6. **CORS** — origins захардкожены в каждом сервисе отдельно (не централизованно).
7. **Аутентификация** — JWT реализована только в user-service и notification-service. Остальные сервисы не проверяют токены.
8. **⚠️ MANDATORY: Frontend стили — миграция на Tailwind CSS** (см. T1 в `docs/ISSUES.md`):
   - **Новые компоненты** — писать сразу на Tailwind, без CSS/SCSS-файлов.
   - **Изменение стилей существующего компонента (включая баг-фиксы!)** — мигрировать весь компонент на Tailwind в том же PR, удалить старый CSS/SCSS. **Добавлять новые стили в SCSS запрещено.**
   - **Задача не касается стилей** — не трогать, оставить как есть.
   - Tailwind и старые SCSS сосуществуют в переходный период.
   - **Нарушение этого правила = FAIL на ревью.**
9. **⚠️ MANDATORY: Frontend язык — миграция на TypeScript** (см. T3 в `docs/ISSUES.md`):
   - **Новые файлы** — писать сразу на TypeScript (`.tsx` / `.ts`).
   - **Изменение логики существующего `.jsx` файла (включая баг-фиксы!)** — мигрировать на TypeScript в том же PR (`.jsx` -> `.tsx`), добавить типы. **Писать новую логику в `.jsx` запрещено.**
   - **Задача не касается логики файла** — не трогать, оставить как есть.
   - `.tsx` и `.jsx` сосуществуют в переходный период.
   - **Нарушение этого правила = FAIL на ревью.**

---

## 11. AI Team — Agents, Skills, Pipeline

### Automated Development Pipeline

All user communication goes through PM (Orchestrator). PM manages the full cycle:

```
USER → PM (clarify requirements — non-technical questions only)
         ↓ requirements clear
       PM creates feature file in features/ (status: OPEN)
         ↓
       PM → Agent(Codebase Analyst) — codebase analysis
         ↓ analysis_report written to feature file
       PM → Agent(Architect) — design + task breakdown
         ↓ task_specs written to feature file (status: IN_PROGRESS)
         ↓
       PM → Agent(Backend Dev) + Agent(Frontend Dev) + Agent(DevSecOps)
         (parallel if no dependencies, sequential if there are)
         ↓ tasks completed
       PM → Agent(QA Test) — write tests (backend only)
         ↓ tests written
       PM → Agent(Reviewer) — final check (status: REVIEW)
         ↓
       PASS → PM closes feature file (DONE-FEAT-*), reports to user
       FAIL → PM launches appropriate agent for fix → Reviewer again (max 3 iterations)
```

### Feature Files

Feature tracking is done in the `features/` directory:
- Template: `features/FEAT-000-template.md`
- Format: `FEAT-{NNN}-{slug}.md` → `DONE-FEAT-{NNN}-{slug}.md`
- Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

### Agents

| Agent | File | Responsibility |
|-------|------|----------------|
| Orchestrator (PM) | `agents/orchestrator.md` | Single point of contact for user, pipeline management. **NEVER analyzes/reads/debugs code — delegates ALL technical work to agents.** |
| Codebase Analyst | `agents/codebase-analyst.md` | READ-ONLY code analysis, dependencies, patterns |
| Architect | `agents/architect.md` | Solution design, API contracts, task breakdown |
| Backend Developer | `agents/backend-developer.md` | Python service code (FastAPI, SQLAlchemy, Celery) |
| Frontend Developer | `agents/frontend-developer.md` | React application code (TypeScript, Redux, Tailwind) |
| DevSecOps | `agents/devsecops.md` | Docker, Nginx, security, env vars |
| QA Test | `agents/qa-test.md` | Backend tests (pytest), backend only |
| Reviewer | `agents/reviewer.md` | Final quality gate, review-fix loop |

Each agent reads this `CLAUDE.md` (global rules) + their own file (role specifics).

### Skills

Skills are reusable instructions for common operations. Located in `agents/skills/`.
Full mapping table in `agents/skills/README.md`.

| Skill | Primary Agent | Secondary Agent |
|-------|---------------|-----------------|
| api-design-spec | Backend Developer | Architect |
| api-integration-test | QA Test | — |
| fastapi-endpoint-generator | Backend Developer | — |
| frontend-design | Frontend Developer | — |
| redux-slice-generator | Frontend Developer | — |
| typescript-expert | Frontend Developer | Reviewer |
| pytest-fixture-creator | QA Test | — |
| websocket-handler | Frontend Developer | Backend Developer |
| python-developer | Backend Developer | DevSecOps, Codebase Analyst |
| cross-service-validator | Reviewer | Codebase Analyst |
| alembic-migration-guide | Backend Developer | — |
| feature-file-manager | Orchestrator (PM) | — |

### Language Policy

| Context | Language | Example |
|---------|----------|---------|
| PM ↔ User communication | **Russian** | Questions, reports, summaries |
| Feature file: Section 1 (Feature Brief) | **Russian** | Written by PM from user input |
| Feature file: Sections 2-5 (Technical) | **English** | Written by technical agents |
| Feature file: Section 6 (Logging) | **Russian** | Progress updates from all agents |
| Feature file: Section 7 (Summary) | **Russian** | Final report for user |
| Agent reasoning, code comments, commits | **English** | All technical work |
| User-facing app content (UI, API errors) | **Russian** | All text displayed to end users |
| Game content (items, skills, locations) | **Russian** | All in-game text and DB seed data |
| Skills, agent files, CLAUDE.md | **English** | Internal documentation |

### Ask When in Doubt

**All agents** must follow this rule: if you encounter ambiguity in requirements, architecture decisions, or business logic — **do not guess**. Return your question to PM, who will clarify with the user. Better to ask and get it right than to assume and build the wrong thing.

**This applies to technical decisions too:** adding new dependencies, choosing between implementation approaches, using new tools or framework features. If you're unsure — ask PM, who will relay to the user. **Never silently choose the conservative/limited option to "play it safe."** Skipping a useful feature without asking is worse than asking a technical question. The user prefers to be asked.

### Logging

Every agent writes brief **Russian** status updates in the feature file's Logging section (section 6). This provides a human-readable timeline of progress. Format: `[LOG] YYYY-MM-DD HH:MM — Agent: описание действия`

### Security Requirements

All agents must consider security in their domain:
- **Architect:** Define auth, rate limiting, and input validation for every new endpoint
- **Backend Developer:** Sanitize inputs, use parameterized queries, safe error messages
- **Frontend Developer:** Display all errors to users, no silent failures
- **DevSecOps:** Rate limiting (Nginx), security headers, DDoS protection, CORS hardening
- **QA Test:** Include security test cases (SQL injection, XSS, unauthorized access)
- **Reviewer:** Verify security checklist on every review

### Frontend Error Display

**Mandatory rule for Frontend Developer and Reviewer:** Every API call in the frontend MUST have visible error handling. Never silently swallow errors. Network errors, 4xx, 5xx — all must be displayed to the user with a Russian-language message.

### Build Verification — Mandatory

**Developers must verify their work compiles/builds before marking tasks done. Reviewer must re-verify.**

- **Frontend Developer:** Run `npx tsc --noEmit` AND `npm run build` before completion. Both must pass.
- **Backend Developer:** Run `python -m py_compile` on all modified files before completion. Must pass.
- **Reviewer:** Re-run all applicable checks AND verify the feature works live (via MCP `chrome-devtools` or `curl`). A review without automated check results AND live verification is invalid and must not be marked PASS.
- **New dependencies:** If you import a package, you MUST install/add it first (`npm install` / `requirements.txt`). Unresolved imports = broken app.
- **Live verification is mandatory:** Code that passes static checks but fails at runtime (500 errors, console errors, broken UI) is a FAIL. Reviewer must open the page and confirm zero errors.

### Sub-agent Execution

**All sub-agents MUST be launched as separate background agents** (using the Agent tool with `run_in_background: true`). Sub-agents never run inline in PM's conversation. This ensures isolation and allows parallel execution.

### QA Is Mandatory

Every feature that modifies backend Python code **must** include QA Test tasks. Architect must always create them. PM must verify they exist before launching Reviewer. Reviewer must FAIL the review if backend was changed but no tests were written.

### Bug Tracking

When any agent discovers a bug **unrelated to the current feature**, they must:
1. Add it to `docs/ISSUES.md` with priority, service, file, description
2. Log it in the feature file: `[LOG] ... — Agent: обнаружен баг, добавлен в ISSUES.md`
3. NOT fix it in the current feature (unless it's a direct blocker)

When any agent fixes a bug (as part of a feature or dedicated fix task), they must:
1. **Remove or mark as DONE** the corresponding entry in `docs/ISSUES.md`
2. Log it: `[LOG] ... — Agent: баг исправлен, удалён из ISSUES.md`

`docs/ISSUES.md` must always reflect the **current** state of known issues — no stale entries for already-fixed bugs.

---

## 12. Документация (для людей и агентов)

- `docs/ARCHITECTURE.md` — обзор системы, service map, схема БД, диаграмма коммуникаций.
- `docs/ISSUES.md` — известные проблемы и tech debt с приоритетами (CRITICAL/HIGH/MEDIUM/LOW).
- `docs/services/<service>.md` — детальное описание каждого сервиса: эндпоинты, таблицы, зависимости, бизнес-логика, известные проблемы.

При нахождении новых проблем — добавляй их в `docs/ISSUES.md` с указанием сервиса, файла и приоритета.

---

## 13. Поведение при неполном контексте

Если контекста не хватает:
1. Сделай самое безопасное предположение.
2. Явно обозначь его в отчёте.
3. Не изобретай несуществующие API/эндпоинты/таблицы.
4. Не скрывай неопределённость за «уверенным» тоном.
5. Загляни в `docs/services/<service>.md` — там могут быть ответы.

---

## 14. Definition of Done

Задача считается завершённой, когда:
- Изменения реализуют запрос пользователя.
- Проверки выполнены и результаты зафиксированы.
- Нет явных регрессий в затронутой зоне.
- Кросс-сервисные эффекты учтены.
- Ответ прозрачно объясняет решение и ограничения.
