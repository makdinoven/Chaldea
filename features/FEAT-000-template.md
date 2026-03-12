# FEAT-000: [Название фичи]

## Meta

| Field | Value |
|-------|-------|
| **Status** | OPEN |
| **Created** | YYYY-MM-DD |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH / MEDIUM / LOW |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Что делаем и зачем. Бизнес-контекст, мотивация.

### Бизнес-правила
- Правило 1
- Правило 2

### UX / Пользовательский сценарий
1. Игрок делает X
2. Система отвечает Y
3. Результат Z

### Edge Cases
- Что если...?
- Что если...?

### Вопросы к пользователю (если есть)
- [ ] Вопрос 1 → Ответ: ...
- [ ] Вопрос 2 → Ответ: ...

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| service-name | model + endpoint | `app/models.py`, `app/main.py` |

### Existing Patterns
- Sync/Async: ...
- ORM: ...
- Authentication: ...

### Cross-Service Dependencies
```
service-A ──HTTP──> service-B (endpoint: GET /...)
```

### DB Changes
- New tables: ...
- Changes to existing: ...
- Migrations: Alembic needed? (yes/no, is it already set up)

### Risks
- Risk 1: description, mitigation
- Risk 2: description, mitigation

---

## 3. Architecture Decision (filled by Architect — in English)

### API Contracts

#### `POST /endpoint`
**Request:**
```json
{ "field": "type" }
```
**Response:**
```json
{ "field": "type" }
```

### Security Considerations
- Authentication: required / not required (with justification)
- Rate limiting: yes / no (with config)
- Input validation: what fields, what rules
- Authorization: who can access, role checks

### DB Changes
```sql
ALTER TABLE ... ADD COLUMN ...;
```

### Frontend Components
- `ComponentName` — description, location

### Data Flow Diagram
```
User → Frontend → API Gateway → service-A → DB
                                service-A → service-B (HTTP)
```

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Task description | Backend Developer | TODO | `file1.py`, `file2.py` | — | Acceptance criteria |
| 2 | Task description | Frontend Developer | TODO | `Component.tsx` | #1 | Acceptance criteria |
| 3 | Write tests | QA Test | TODO | `test_*.py` | #1 | pytest pass |
| 4 | Review | Reviewer | TODO | all | #1, #2, #3 | Checklist passed |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — YYYY-MM-DD
**Result:** PASS / FAIL

#### Checks
- [ ] Types match (Pydantic ↔ TS interfaces)
- [ ] API contracts consistent (backend ↔ frontend ↔ tests)
- [ ] No stubs/TODO without tracking
- [ ] `python -m py_compile` — OK
- [ ] `npx tsc --noEmit` — OK
- [ ] `npm run build` — OK
- [ ] `pytest` — OK
- [ ] Security checklist passed (rate limiting, input sanitization, auth, error messages)
- [ ] Frontend displays all errors to user
- [ ] User-facing strings in Russian

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `file.py:42` | Issue description | Backend Developer | FIX_REQUIRED |

---

## 6. Logging (filled by all agents — in Russian)

Running log of progress updates. Each agent writes brief Russian entries here.

```
[LOG] YYYY-MM-DD HH:MM — PM: фича создана, запускаю анализ
[LOG] YYYY-MM-DD HH:MM — Analyst: начал анализ кодовой базы
[LOG] YYYY-MM-DD HH:MM — Analyst: анализ завершён, затронуто N сервисов
[LOG] YYYY-MM-DD HH:MM — Architect: начал проектирование
[LOG] YYYY-MM-DD HH:MM — Architect: спроектировано N задач
[LOG] YYYY-MM-DD HH:MM — Backend Dev: начал задачу #1
[LOG] YYYY-MM-DD HH:MM — Backend Dev: задача #1 завершена
[LOG] YYYY-MM-DD HH:MM — Frontend Dev: начал задачу #2
[LOG] YYYY-MM-DD HH:MM — Frontend Dev: задача #2 завершена
[LOG] YYYY-MM-DD HH:MM — QA: тесты написаны, N тестов проходят
[LOG] YYYY-MM-DD HH:MM — Reviewer: проверка завершена, результат PASS
[LOG] YYYY-MM-DD HH:MM — PM: фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- ...

### Что изменилось от первоначального плана
- ...

### Оставшиеся риски / follow-up задачи
- ...
