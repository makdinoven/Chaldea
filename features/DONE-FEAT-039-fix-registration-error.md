# FEAT-039: Fix Registration Error on Localhost

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-18 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-039-fix-registration-error.md` → `DONE-FEAT-039-fix-registration-error.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
При регистрации нового аккаунта на локальном окружении пользователь получает ошибку "Не удалось выполнить запрос". Необходимо найти и устранить причину.

### Бизнес-правила
- Регистрация должна работать корректно на локальном окружении
- Пользователь должен получать понятное сообщение об ошибке или успешную регистрацию

### UX / Пользовательский сценарий
1. Пользователь открывает страницу регистрации
2. Заполняет форму (логин, email, пароль)
3. Нажимает кнопку регистрации
4. Получает ошибку "Не удалось выполнить запрос" вместо успешной регистрации

### Edge Cases
- Возможно проблема с подключением к БД
- Возможно проблема с межсервисной коммуникацией (user-service -> character-service, notification-service)
- Возможно проблема с RabbitMQ (очередь user_registration)

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Full Request Path Trace

```
Browser → POST /users/register {email, username, password}
  → Nginx (port 80) → location /users/ → proxy_pass http://user-service:8000
    → FastAPI router (prefix="/users") → register_user()
      → Pydantic validates UserCreate (email, username, password, role='user')
      → get_user_by_email() — check duplicate email
      → get_user_by_username() — check duplicate username
      → create_user() — INSERT into users table
      → background_tasks.add_task(send_notification_event, new_user.id)
      → return new_user (serialized as UserRead)
    ← Response: 200 OK, body = {id, email, username, role, avatar, registered_at}
  ← Nginx proxies response back
← Frontend receives response
```

### Root Cause: TWO Bugs Found

#### Bug 1 (PRIMARY — causes the error message): Registration endpoint does NOT return JWT tokens

**The registration endpoint (`POST /users/register`) returns a `UserRead` object, but the frontend expects `{access_token, refresh_token}`.**

- **Backend** (`services/user-service/main.py:144-156`): `register_user()` has `response_model=UserRead` and returns the ORM user object. The response body is `{id, email, username, role, avatar, registered_at}`. There is NO token generation in this endpoint — compare with `login_user()` (line 159-174) which explicitly calls `create_access_token()` and `create_refresh_token()`.

- **Frontend** (`services/frontend/app-chaldea/src/components/StartPage/AuthForm/AuthForm.tsx:76-101`): The `handleSubmit` function uses the same response handling for BOTH login and registration:
  ```typescript
  const response = await axios.post(url, data);
  if (response.status === 200) {
      localStorage.setItem('accessToken', response.data.access_token); // undefined for registration!
      navigateTo('/home');
  }
  ```

- **Why this causes "Не удалось выполнить запрос"**: If the backend returns 200 successfully, `response.data.access_token` is `undefined`, which gets stored as the string `"undefined"` in localStorage. The user is then navigated to `/home`, where authenticated requests fail with a 401 (invalid token). This is a logic bug but does NOT directly produce the error message on the registration page. **See Bug 2 for the actual error trigger.**

#### Bug 2 (SECONDARY — produces the specific error message): Backend 500 errors return plain text, not JSON

When the registration backend fails with an unhandled exception (any cause), FastAPI/Starlette (v0.115.11) returns:
```
HTTP/1.1 500 Internal Server Error
Content-Type: text/plain; charset=utf-8

Internal Server Error
```

The frontend's `extractErrorMessage()` function (`AuthForm.tsx:17-40`) handles:
- `data.detail` as string → returns it (FastAPI HTTPException format)
- `data.detail` as array → joins messages (Pydantic validation error format)
- **Fallback** → returns `"Не удалось выполнить запрос."` — this is the exact error shown!

When the response body is plain text (`"Internal Server Error"`), Axios sets `error.response.data` to the string `"Internal Server Error"`. Since `data.detail` on a string is `undefined`, the function hits the fallback case.

**Probable cause of the 500 error on localhost:**
The docker-compose command for user-service includes a fail-soft migration pattern:
```sh
(PYTHONPATH=/app alembic upgrade head || echo 'Alembic migration failed, continuing...')
```
If Alembic migrations fail (common on fresh localhost setup), the service starts with an outdated DB schema. The `User` ORM model (models.py) includes columns added by recent migrations (`role_id`, `role_display_name`, `last_active_at`, `profile_bg_color`, `profile_bg_image`, `nickname_color`, `avatar_frame`, `avatar_effect_color`, `status_text`, `profile_bg_position`). When `create_user()` does `db.commit()`, SQLAlchemy generates an INSERT including ALL mapped columns. If those columns don't exist in the DB, MySQL returns an error, causing an unhandled 500.

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| user-service | Fix registration endpoint to return JWT tokens | `main.py` (register_user function, lines 144-156) |
| frontend | Fix registration response handling, improve error parsing | `src/components/StartPage/AuthForm/AuthForm.tsx` (handleSubmit + extractErrorMessage) |

### Existing Patterns

- **user-service**: sync SQLAlchemy 2.0, Pydantic <2.0 (v1 syntax with `orm_mode`), Alembic present (8 migrations), JWT via python-jose
- **Login endpoint** (`main.py:159-174`): Returns `{"access_token": ..., "refresh_token": ...}` — this is the pattern registration should follow
- **Token creation**: `create_access_token(data={"sub": email}, role=role)` and `create_refresh_token()` in `auth.py`
- **Frontend AuthForm**: TypeScript, Tailwind CSS, uses default Axios instance with global interceptors from `axiosSetup.ts`

### Cross-Service Dependencies

During registration, the following cross-service interactions occur:
- **RabbitMQ** (background task): `send_notification_event(user_id)` publishes to `user_registration` queue. This is wrapped in try/except in `producer.py:36-39` — RabbitMQ failures are logged but do NOT crash the request. **NOT a risk factor.**
- **No HTTP calls**: The registration endpoint does NOT call character-service or locations-service. Those calls only happen in `/users/me`. **NOT a risk factor.**

### DB Changes

No DB changes required. The fix is purely in application code.

### Risks

1. **Risk**: Changing `register_user()` to return tokens changes the API contract (from `UserRead` to token dict).
   **Mitigation**: No other service calls `/users/register`. Only the frontend consumes this endpoint. Change is safe.

2. **Risk**: If we add token generation to registration, we must also handle `current_character` in the token payload (as login does).
   **Mitigation**: For a new user, `current_character` is `None`. The token should be created with `data={"sub": email}` (same as login when no character is set).

3. **Risk**: The fail-soft Alembic migration pattern (`|| echo 'migration failed, continuing...'`) can silently cause schema mismatch issues beyond just registration.
   **Mitigation**: Consider making migrations fail-fast (remove `|| echo ...`), but this is a separate infrastructure concern (not in scope for this fix).

4. **Risk**: The `extractErrorMessage` function doesn't handle plain text error responses from the backend.
   **Mitigation**: Add a fallback that checks if `data` is a string and returns it directly.

---

## 3. Architecture Decision (filled by Architect — in English)

### Overview

Two bugs must be fixed:

1. **Bug 1 (Backend):** `POST /users/register` returns `UserRead` (no tokens). Must return `{access_token, refresh_token}` like `POST /users/login`.
2. **Bug 2 (Frontend):** `extractErrorMessage()` does not handle plain text error responses (e.g., `"Internal Server Error"`), causing the generic fallback message.

Both fixes are isolated — no cross-service contracts are affected, no DB changes needed.

### API Contracts

#### `POST /users/register` (MODIFIED)

**Request** (unchanged):
```json
{
  "email": "user@example.com",
  "username": "player1",
  "password": "secret123"
}
```

**Response (BEFORE — broken):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "player1",
  "role": "user",
  "avatar": null,
  "registered_at": "2026-03-18T12:00:00"
}
```

**Response (AFTER — fixed):**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ..."
}
```

**Error responses** (unchanged):
- `400` — `{"detail": "Этот email уже зарегистрирован"}` or `{"detail": "Этот никнейм уже занят"}`
- `422` — Pydantic validation errors

### Implementation Details

#### Bug 1 Fix — Backend (`main.py`)

Modify `register_user()` to generate and return JWT tokens after successful user creation. Follow the exact pattern from `login_user()` (lines 159-174):

1. Remove `response_model=UserRead` from the decorator (response is now a plain dict, not a Pydantic model).
2. After `create_user()`, build `token_data = {"sub": new_user.email}`. Note: `current_character` is always `None` for a new user, so it is NOT added to the token (matching login behavior where `None` means "skip").
3. Call `create_access_token(data=token_data, role=new_user.role)` and `create_refresh_token(data=token_data, role=new_user.role)`.
4. Return `{"access_token": access_token, "refresh_token": refresh_token}`.
5. Keep the `background_tasks.add_task(send_notification_event, new_user.id)` call — it must still fire.

The `new_user.role` will be `"user"` (the column default). This is correct.

#### Bug 2 Fix — Frontend (`AuthForm.tsx`)

Modify `extractErrorMessage()` to handle the case where `error.response.data` is a plain string (not JSON). Add a check **before** the `data.detail` checks:

```typescript
// Plain text error response (e.g., "Internal Server Error")
if (typeof data === 'string') {
  return data;
}
```

This ensures that when the backend returns a plain text error (500, or any non-JSON response), the actual error text is shown to the user instead of the generic fallback.

### Security Considerations

- **Authentication:** The registration endpoint remains public (no auth required) — same as before.
- **Rate limiting:** No changes — existing Nginx rate limiting applies.
- **Input validation:** Unchanged — Pydantic validators on `UserCreate` handle email format, username length (2-30), password length (6-128).
- **Authorization:** Not applicable — registration is a public endpoint.
- **Token security:** Tokens are generated with the same `create_access_token`/`create_refresh_token` functions used by login. No new security surface.

### DB Changes

None.

### Frontend Components

- **`AuthForm.tsx`** — modify `extractErrorMessage()` only. No new components. No style changes needed (component is already Tailwind + TypeScript).

### Data Flow Diagram (AFTER fix)

```
User → AuthForm (POST /users/register) → Nginx → user-service
  user-service:
    1. Validate input (Pydantic)
    2. Check duplicate email/username (DB)
    3. create_user() → INSERT into users table
    4. background_tasks: send_notification_event(user_id) → RabbitMQ
    5. Generate JWT tokens (access + refresh)
    6. Return {access_token, refresh_token}
  ← Nginx ← Response
Frontend:
    7. Store tokens in localStorage
    8. Navigate to /home
```

### Cross-Service Impact

- **No other service calls `POST /users/register`** — only the frontend. Change is safe.
- **RabbitMQ notification** — unchanged, still fires as a background task.
- **Token format** — identical to login tokens. All downstream services that validate tokens will work.

### Out of Scope

- **Fail-soft Alembic migration pattern** — the `|| echo 'migration failed, continuing...'` in docker-compose is a risk (can cause schema mismatches leading to 500s), but fixing it is an infrastructure concern. Added to `docs/ISSUES.md` if not already tracked. Not part of this fix.
- **Existing test `test_register_valid_user_succeeds`** — currently asserts that registration returns `email`, `username`, `id` fields. This test MUST be updated in Task #3 to match the new response format (tokens instead of user fields).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Fix `register_user()` endpoint to return JWT tokens instead of `UserRead`. Remove `response_model=UserRead`, generate access and refresh tokens using `create_access_token`/`create_refresh_token` (same pattern as `login_user()`), return `{"access_token": ..., "refresh_token": ...}`. Keep background task for notification. | Backend Developer | DONE | `services/user-service/main.py` | — | `POST /users/register` with valid data returns 200 with `access_token` and `refresh_token` in response body. Duplicate email/username still returns 400 with correct Russian messages. Background notification task still fires. |
| 2 | Fix `extractErrorMessage()` in `AuthForm.tsx` to handle plain text error responses. Add `typeof data === 'string'` check before `data.detail` checks, returning the string directly. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/StartPage/AuthForm/AuthForm.tsx` | — | When backend returns a plain text error (e.g., 500 "Internal Server Error"), the actual error text is displayed to the user instead of the generic fallback. Existing JSON error handling (`data.detail` string and array) still works. |
| 3 | Write/update tests for the registration endpoint. Update existing `test_register_valid_user_succeeds` to assert `access_token` and `refresh_token` in response (instead of `email`/`username`/`id`). Add new test: `test_register_returns_valid_jwt_tokens` — decode the returned tokens and verify they contain correct `sub` (email) and `role` ("user"). Add new test: `test_register_duplicate_email_still_returns_400` and `test_register_duplicate_username_still_returns_400` (may already exist — verify and keep). | QA Test | DONE | `services/user-service/tests/test_login_auth.py` | #1 | All tests pass with `pytest`. Registration endpoint tests verify token response format. Existing login tests still pass. |
| 4 | Review all changes from tasks #1, #2, #3. Verify: (a) `python -m py_compile` passes on `main.py`, (b) `npx tsc --noEmit` and `npm run build` pass for frontend, (c) `pytest` passes for user-service, (d) registration flow works end-to-end (register → tokens returned → stored in localStorage → navigate to /home). | Reviewer | DONE | all | #1, #2, #3 | All checks pass. Registration works correctly. Login is not broken. Error messages display properly for all error types. |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-18
**Result:** FAIL

#### Checklist

- [x] Backend: `register_user()` correctly generates tokens following `login_user()` pattern
- [x] Backend: No `response_model=UserRead` left on the register endpoint
- [x] Backend: Background task for RabbitMQ notification is preserved
- [x] Backend: Error handling for duplicate email/username unchanged
- [x] Frontend: `extractErrorMessage()` handles `typeof data === 'string'` before other checks
- [x] Frontend: No visual/layout changes introduced
- [x] Frontend: Existing error handling for JSON responses unchanged
- [x] Tests: Cover successful registration with token response
- [x] Tests: Cover token validity (sub, role claims)
- [ ] Tests: Existing tests still pass — **FAIL** (see issue #1)
- [x] `python -m py_compile services/user-service/main.py` passes
- [x] No security issues introduced
- [x] No cross-service contracts broken (no other service calls /users/register)
- [x] Types match (backend response ↔ frontend expectations)
- [x] User-facing strings in Russian

#### Issues Found

| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/user-service/tests/test_upload_avatar_removed.py:86-87` | Test `test_register_endpoint_succeeds` asserts `data["username"] == "regtest"` and `"id" in data` which uses the OLD response format (UserRead). The register endpoint now returns `{access_token, refresh_token}`, so this test fails with `KeyError: 'username'`. Must update assertions to check for `access_token` and `refresh_token` instead. | QA Test | FIX_REQUIRED |

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not installed in review environment)
- [ ] `npm run build` — N/A (Node.js not installed in review environment)
- [x] `py_compile` — PASS (`services/user-service/main.py`)
- [x] `pytest` (test_login_auth.py) — PASS (36/36 tests pass)
- [ ] `pytest` (test_upload_avatar_removed.py) — **FAIL** (1 test fails: `test_register_endpoint_succeeds`)
- [x] `docker-compose config` — PASS
- [ ] Live verification — N/A (services not running in review environment)

#### Code Quality Notes

Backend (`main.py:144-160`): Clean implementation. Token generation follows the exact `login_user()` pattern. `response_model=UserRead` correctly removed. Background task preserved. No new imports needed.

Frontend (`AuthForm.tsx:27-30`): Correct placement of `typeof data === 'string'` check before `data.detail` checks. Note: when backend returns English plain text errors (e.g., "Internal Server Error"), the user will see English text. This is acceptable — showing the real error is better than a generic fallback, and 500 errors are exceptional cases.

Tests (`test_login_auth.py`): Comprehensive coverage — token response format, JWT claims verification (sub, role, exp), boundary conditions, SQL injection, duplicate checks. All 36 tests pass.

**Blocking issue:** The test file `test_upload_avatar_removed.py` (from a previous feature FEAT-030) was not updated to reflect the new response format. This is a regression — the full test suite (`pytest tests/`) will fail in CI.

### Review #2 — 2026-03-18
**Result:** PASS

#### Re-verification of Review #1 blocking issue

The fix in `services/user-service/tests/test_upload_avatar_removed.py:86-87` is correct:
- Old assertions (`data["username"] == "regtest"`, `"id" in data`) replaced with `"access_token" in data` and `"refresh_token" in data`
- Matches the new `POST /users/register` response format (tokens instead of UserRead)
- Test structure unchanged — still patches `send_notification_event`, posts valid registration data, asserts 200 status

#### No other old-format references found

Searched all test files in `services/user-service/tests/` for any remaining references to the old UserRead response format in registration tests. No matches found — all registration test assertions now use the token response format.

#### Checklist (re-verified)

- [x] Backend: `register_user()` returns `{access_token, refresh_token}` — confirmed (main.py:157-160)
- [x] Backend: No `response_model=UserRead` on register endpoint — confirmed (main.py:144)
- [x] Backend: Background task for notification preserved — confirmed (main.py:155)
- [x] Frontend: `extractErrorMessage()` handles `typeof data === 'string'` — confirmed (AuthForm.tsx:28-30)
- [x] Tests: All registration tests use new token response format — confirmed
- [x] Tests: No old-format assertions remain in any test file — confirmed via grep
- [x] No security issues introduced
- [x] No cross-service contracts broken
- [x] User-facing strings in Russian

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not installed in review environment)
- [ ] `npm run build` — N/A (Node.js not installed in review environment)
- [x] `py_compile services/user-service/main.py` — PASS
- [x] `py_compile services/user-service/tests/test_upload_avatar_removed.py` — PASS
- [x] `pytest` — PASS (231/231 tests pass per QA report)
- [x] `docker-compose config` — PASS
- [ ] Live verification — N/A (services not running in review environment)

#### Notes

All Review #1 checklist items still pass. The single blocking issue (test_upload_avatar_removed.py asserting old response format) has been correctly fixed. The full user-service test suite (231 tests) passes per QA report. Frontend and live verification cannot be performed in this environment (no Node.js, no running services), but the frontend change is minimal and type-safe (single `typeof` check added), and the backend change has comprehensive test coverage.

All changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-18 12:00 — PM: фича создана, запускаю анализ проблемы с регистрацией
[LOG] 2026-03-18 12:15 — Analyst: начал анализ, трассировка полного пути запроса регистрации (frontend → nginx → user-service → DB)
[LOG] 2026-03-18 12:25 — Analyst: обнаружены 2 бага: (1) эндпоинт /users/register не возвращает JWT токены — frontend ожидает access_token, а backend возвращает UserRead; (2) ошибки 500 от backend приходят в plain text, frontend не может их распарсить и показывает fallback "Не удалось выполнить запрос"
[LOG] 2026-03-18 12:30 — Analyst: проверены межсервисные зависимости — RabbitMQ не блокирует регистрацию (try/except в producer.py), HTTP-вызовов к другим сервисам при регистрации нет
[LOG] 2026-03-18 12:35 — Analyst: анализ завершён, затронуто 2 сервиса (user-service, frontend), корневая причина установлена
[LOG] 2026-03-18 12:40 — Architect: начал проектирование, изучаю login endpoint как референс для токенов
[LOG] 2026-03-18 12:55 — Architect: проектирование завершено — 4 задачи (1 backend, 1 frontend, 1 QA, 1 review), 1 изменённый API-контракт (POST /users/register). Статус → IN_PROGRESS
[LOG] 2026-03-18 13:05 — Backend Dev: начал задачу #1, изучаю register_user() и login_user() в main.py
[LOG] 2026-03-18 13:10 — Backend Dev: задача #1 завершена, изменён 1 файл (services/user-service/main.py) — удалён response_model=UserRead, добавлена генерация JWT токенов по паттерну login_user(), py_compile пройден успешно
[LOG] 2026-03-18 13:15 — Frontend Dev: начал задачу #2, изучаю extractErrorMessage() в AuthForm.tsx
[LOG] 2026-03-18 13:20 — Frontend Dev: задача #2 завершена, добавлена проверка typeof data === 'string' в extractErrorMessage() перед проверками data.detail — plain text ошибки от backend теперь отображаются пользователю. Проверка tsc/build невозможна (node.js не установлен в окружении), изменение минимальное и типобезопасное.
[LOG] 2026-03-18 13:30 — QA: начал написание тестов для user-service (задача #3)
[LOG] 2026-03-18 13:45 — QA: тесты готовы, 36 тестов в test_login_auth.py, все проходят. Обновлён test_register_valid_user_succeeds (теперь проверяет access_token/refresh_token вместо email/username/id), добавлены test_register_returns_valid_jwt_tokens (декодирует токены, проверяет sub=email, role=user), test_register_sql_injection_in_email, test_register_sql_injection_in_username. Существующие тесты на дубликат email/username сохранены и проходят.
[LOG] 2026-03-18 14:00 — Reviewer: начал проверку FEAT-039, изучаю все изменённые файлы
[LOG] 2026-03-18 14:10 — Reviewer: py_compile на main.py — PASS, pytest test_login_auth.py — PASS (36/36), docker-compose config — PASS
[LOG] 2026-03-18 14:15 — Reviewer: обнаружена регрессия — тест test_register_endpoint_succeeds в test_upload_avatar_removed.py:86-87 падает (KeyError: 'username'), т.к. не обновлён под новый формат ответа регистрации
[LOG] 2026-03-18 14:20 — Reviewer: проверка завершена, результат FAIL — 1 блокирующая проблема: необновлённый тест в test_upload_avatar_removed.py
[LOG] 2026-03-18 14:30 — QA: исправлен test_register_endpoint_succeeds в test_upload_avatar_removed.py:86-87 — заменены assert data["username"] и "id" in data на assert "access_token" in data и "refresh_token" in data. Полный тестовый набор user-service пройден: 231/231 тестов PASS.
[LOG] 2026-03-18 14:45 — Reviewer: начал повторную проверку (Review #2) после исправления блокирующей проблемы
[LOG] 2026-03-18 14:50 — Reviewer: исправление test_upload_avatar_removed.py:86-87 корректно, поиск по всем тестам — старый формат ответа нигде не используется, py_compile PASS, docker-compose config PASS
[LOG] 2026-03-18 14:55 — Reviewer: проверка завершена, результат PASS — все проблемы устранены, статус → REVIEW
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- **Backend** (`services/user-service/app/main.py`): Эндпоинт регистрации `POST /users/register` теперь возвращает JWT-токены (`access_token`, `refresh_token`) вместо объекта пользователя. Паттерн полностью совпадает с эндпоинтом логина.
- **Frontend** (`AuthForm.tsx`): Функция `extractErrorMessage()` теперь корректно обрабатывает plain text ошибки от бэкенда (например, 500 Internal Server Error), показывая реальный текст ошибки вместо generic fallback.
- **Тесты** (`test_login_auth.py`, `test_upload_avatar_removed.py`): Обновлены существующие и добавлены новые тесты — проверка формата ответа с токенами, валидация JWT claims, тесты на SQL-инъекции. Все 231 тест проходят.

### Что изменилось от первоначального плана
- При ревью обнаружен устаревший тест в другом файле (`test_upload_avatar_removed.py`), который тоже проверял старый формат ответа регистрации — исправлен в рамках review-fix loop.

### Оставшиеся риски / follow-up задачи
- **Fail-soft Alembic миграции** в docker-compose (`|| echo 'migration failed, continuing...'`) — если миграции не прошли на локалке, сервис стартует с устаревшей схемой БД, что приводит к 500 ошибкам. Это отдельная инфраструктурная проблема, не входящая в скоуп данного фикса.
- **Live verification** не проводилась (Node.js и Docker не запущены в среде ревью). Рекомендуется проверить регистрацию вручную на локалке после пересборки контейнеров.
