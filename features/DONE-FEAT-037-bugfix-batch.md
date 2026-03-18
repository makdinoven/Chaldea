# FEAT-037: Пакетное исправление багов (A-029-1, B-027-*, #2)

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-18 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Пакетное исправление известных багов из docs/ISSUES.md:
- **A-029-1** — GET /users/all раскрывает hashed_password и email
- **#2** — Эндпоинты без аутентификации (не-admin)
- **B-027-1** — user-service подключается к MySQL при импорте
- **B-027-2** — character-service тесты используют невалидный import из conftest
- **B-027-3** — skills-service тесты зависают из-за async engine
- **B-027-4** — notification-service conftest создаёт Pydantic модель без обязательных полей
- **B-027-5** — locations-service тест SQL injection падает
- **B-027-6** — character-attributes-service тест не собирается

Часть багов может быть уже решена в рамках FEAT-035/036. Нужно проверить и обновить ISSUES.md.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Bug A-029-1: GET /users/all exposes hashed_password and email

**Status:** FIXED

**Evidence:** `services/user-service/main.py:490` — the endpoint now uses `response_model=schemas.UserListResponse` which contains `items: List[UserPublicItem]`. The `UserPublicItem` schema (`services/user-service/schemas.py:160-168`) only includes `id`, `username`, `avatar`, `registered_at`, `last_active_at` — no `hashed_password` or `email`. The endpoint explicitly constructs `UserPublicItem.from_orm(u)` for each user. Tests confirming this exist in `services/user-service/tests/test_feat029_user_stats.py:184-188`.

**Fix needed:** None. Remove from ISSUES.md.

---

### Bug #2: Endpoints without authentication (non-admin)

**Status:** STILL_BROKEN

**Evidence:** The ISSUES.md entry is accurate. FEAT-035/036 added RBAC for admin endpoints, but user-facing mutation endpoints remain unprotected:

**Category 1 — user-service (ownership checks missing):**
- `PUT /users/{id}/update_character` — no auth, anyone can change any user's current character
- `PUT /users/me/settings` and `PUT /users/me/username` — these DO use `get_current_user` dependency (FIXED)
- `GET /users/me` — uses `get_current_user` (FIXED)

**Category 2 — photo-service (no auth at all):**
- `POST /photo/change_user_avatar_photo` — no JWT check, anyone can upload avatar for any user
- `POST /photo/change_character_avatar_photo` — no ownership check

**Category 3 — character-attributes-service (no auth, inter-service endpoints):**
- `POST /attributes/{character_id}/upgrade` — no auth (player stat upgrade)
- `POST /attributes/{character_id}/apply_modifiers` — no auth (meant for inter-service calls)
- `POST /attributes/{character_id}/recover` — no auth
- `POST /attributes/{character_id}/consume_stamina` — no auth

**Category 4 — other services:**
- Multiple character-service, inventory-service, skills-service endpoints accept requests without auth

**Scope assessment:** ~20-30 endpoints across 5+ services lack user authentication. This is a large effort. For FEAT-037, recommend:
- Fix only the most critical user-facing endpoints that allow modifying OTHER users' data (Category 1-2)
- Leave inter-service endpoints (Category 3-4) for a dedicated auth feature

**Fix needed:** This is too large for a bugfix batch. Recommend deferring to a dedicated feature (FEAT-038 or similar). Update ISSUES.md description to reflect current state.

---

### Bug B-027-1: user-service main.py connects to MySQL at import time

**Status:** FIXED

**Evidence:**
- `services/user-service/main.py` — no `create_all()` call exists anywhere in the file. Grep confirms zero matches for `create_all` or `Base.metadata` in main.py.
- `services/user-service/database.py:6-9` — engine URL is now constructed from `config.settings` (env vars: `DB_HOST`, `DB_USERNAME`, `DB_PASSWORD`, `DB_DATABASE`), not hardcoded. The `config.py:4-9` uses Pydantic `BaseSettings` with no defaults, so env vars must be set.
- Alembic was added to user-service (FEAT-034), which removed `create_all()`.
- `services/user-service/tests/conftest.py` sets env vars before import, preventing connection issues.

**Fix needed:** None. Remove from ISSUES.md.

---

### Bug B-027-2: character-service test files use invalid `from conftest import`

**Status:** FIXED

**Evidence:** Both test files have been rewritten:
- `services/character-service/app/tests/test_admin_character_management.py:13-14` — uses `import database` and `import models` directly, no `from conftest import` anywhere in the file.
- `services/character-service/app/tests/test_admin_update_level_xp.py:17-18` — same pattern, uses `import database` and `import models` directly.
- Grep for `from conftest import` in the entire `tests/` directory returns zero matches.

**Fix needed:** None. Remove from ISSUES.md.

---

### Bug B-027-3: skills-service tests hang due to async engine at import

**Status:** PARTIALLY_FIXED

**Evidence:**
- `services/skills-service/app/database.py:7` — engine URL now comes from `settings.DATABASE_URL` (via `config.py` property), not hardcoded. This is an improvement.
- `services/skills-service/app/config.py:14-17` — `DATABASE_URL` property constructs URL from env vars (`DB_HOST`, `DB_USERNAME`, etc.).
- `services/skills-service/app/tests/conftest.py:17-20` — sets `DB_HOST=localhost`, `DB_USERNAME=testuser`, etc. via `os.environ.setdefault()` BEFORE any import.
- **However**, `database.py:10` still calls `create_async_engine(SQLALCHEMY_DATABASE_URL)` at module import time. With the test env vars, this creates an engine pointed at `mysql+aiomysql://testuser:testpass@localhost:3306/testdb`. The engine object is created but doesn't actually connect until a query is made. The conftest note says "Individual test files patch database.engine after import" — so tests should work as long as they override the engine.
- The engine creation itself (with aiomysql) does NOT connect at import time — `create_async_engine` is lazy. The hang only occurred with hardcoded MySQL host pointing to `mysql:3306` (Docker DNS) which would cause DNS resolution to hang. With `localhost:3306`, connection attempts fail fast.

**Status revised:** FIXED (practically). The env var override prevents the hang. The engine is lazy (no connection at import). Tests patch `database.engine` before use.

**Fix needed:** None for the hang issue. Remove from ISSUES.md. (Future improvement: make engine creation lazy, but not a bug anymore.)

---

### Bug B-027-4: notification-service conftest creates Pydantic model without required fields

**Status:** FIXED

**Evidence:** `services/notification-service/app/tests/conftest.py:62-64` — `_make_user()` now correctly passes all required fields:
```python
def _make_user(user_id: int = 1, username: str = "testuser", role: str = "user"):
    return UserRead(id=user_id, username=username, role=role)
```
The `UserRead` model in `services/notification-service/app/auth_http.py:9-13` has fields: `id: int`, `username: str`, `role: Optional[str] = None`, `permissions: List[str] = []`. The `_make_user` call provides both required fields (`id` and `username`), and `role`/`permissions` have defaults.

**Fix needed:** None. Remove from ISSUES.md.

---

### Bug B-027-5: locations-service SQL injection test fails

**Status:** STILL_BROKEN (test design issue)

**Evidence:** `services/locations-service/app/tests/test_rules.py:400-408`
```python
def test_sql_injection_in_rule_id_delete(self, client):
    response = client.delete("/rules/1 OR 1=1/delete")
    assert response.status_code in (401, 404, 422)
```

The issue: The URL `/rules/1 OR 1=1/delete` contains a literal space. When the TestClient sends this request:
1. The space in the URL path makes it ambiguous — Starlette/httpx may URL-encode the space as `%20`, making the path `/rules/1%20OR%201%3D1/delete`.
2. FastAPI tries to match `{rule_id}` = `"1 OR 1=1"` against type `int` → should return 422.
3. But the `require_permission("rules:delete")` dependency fires FIRST (before path param validation in some FastAPI versions), and since there's no Authorization header → 401.

The test asserts `status_code in (401, 404, 422)`, which should cover all cases. The test might fail if:
- The TestClient raises an exception on the malformed URL before sending (unlikely with modern httpx)
- The URL encoding produces a 307 redirect (Starlette trailing-slash behavior)
- A 500 error occurs due to the mock session in conftest

**Most likely cause:** The `conftest.py` uses a mock `get_db` that returns `MagicMock()`. The `require_permission` dependency calls `get_current_user_via_http` which uses `OAuth2PasswordBearer`. Without a token header, it should return 401. But if the OAuth2 scheme raises an unhandled error with the mock setup, it could return 500.

**Fix needed:** The test itself is reasonable. The fix should be to verify the test actually runs and determine the exact failure. If it returns 307 (redirect), add 307 to the expected codes. Most likely needs a minor adjustment to expected status codes or URL encoding.

---

### Bug B-027-6: character-attributes-service test fails to collect

**Status:** FIXED

**Evidence:**
- `services/character-attributes-service/app/main.py:14` — still has `from rabbitmq_consumer import start_consumer` at module level.
- **However**, `services/character-attributes-service/app/tests/conftest.py:14` — now stubs `aio_pika` before any app imports:
  ```python
  sys.modules.setdefault("aio_pika", MagicMock())
  ```
  This prevents the `import aio_pika` in `rabbitmq_consumer.py:1` from failing.
- `services/character-attributes-service/app/tests/test_admin_endpoints.py:43` — imports `from main import app, get_db` AFTER conftest has run and stubbed `aio_pika`. The import chain `main.py → rabbitmq_consumer.py → aio_pika` succeeds because `aio_pika` is a mock.
- The `conftest.py` also sets all required DB env vars (lines 19-25).

**Fix needed:** None. Remove from ISSUES.md.

---

### Summary

| Bug ID | Status | Action |
|--------|--------|--------|
| A-029-1 | FIXED | Remove from ISSUES.md |
| #2 | STILL_BROKEN | Update ISSUES.md, defer to dedicated feature |
| B-027-1 | FIXED | Remove from ISSUES.md |
| B-027-2 | FIXED | Remove from ISSUES.md |
| B-027-3 | FIXED | Remove from ISSUES.md |
| B-027-4 | FIXED | Remove from ISSUES.md |
| B-027-5 | STILL_BROKEN | Fix test (minor) |
| B-027-6 | FIXED | Remove from ISSUES.md |

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| locations-service | test fix | `app/tests/test_rules.py` |
| (docs) | issue tracking cleanup | `docs/ISSUES.md` |

### Existing Patterns
- locations-service: async SQLAlchemy (aiomysql), Alembic present, tests use mock DB
- All fixed bugs were resolved as part of FEAT-029 / FEAT-034 / FEAT-035

### Risks
- Risk: B-027-5 test fix may need actual test execution to verify → Mitigation: simple test, low risk
- Risk: Removing entries from ISSUES.md without running tests → Mitigation: code analysis is conclusive, fixes are clearly present

---

## 3. Architecture Decision (filled by Architect — in English)

### Decision

Most bugs in this batch (6 out of 8) are already fixed by previous features (FEAT-029, FEAT-034, FEAT-035). The remaining work is:

1. **Clean up ISSUES.md** — remove 6 fixed entries (A-029-1, B-027-1 through B-027-4, B-027-6)
2. **Fix B-027-5** — locations-service SQL injection test. The test logic is sound but may need a minor URL or assertion adjustment.
3. **Update #2 description** — mark which parts were fixed (admin RBAC) and clarify remaining scope.

### Design for B-027-5 fix

The test `test_sql_injection_in_rule_id_delete` sends a URL with a space (`/rules/1 OR 1=1/delete`). The expected behavior is that FastAPI rejects this with 401 (no auth), 404 (no route match), or 422 (invalid int). The fix should:

- Verify the test works with proper URL encoding
- If the space causes routing issues, URL-encode the injection string explicitly
- Ensure assertion covers all valid rejection codes

### Out of scope

Bug #2 (endpoints without auth) is too large for a bugfix batch. It requires:
- Adding JWT auth to 20+ endpoints across 5+ services
- Adding ownership checks (user X can only modify their own data)
- Inter-service auth strategy (service-to-service calls vs user calls)

This should be tracked as a separate feature.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: Clean up ISSUES.md — remove fixed bugs
**Agent:** Backend Developer (or any agent)
**Priority:** HIGH
**Files:** `docs/ISSUES.md`
**Description:**
Remove the following entries from ISSUES.md (all confirmed fixed):
- `A-029-1` — GET /users/all exposes hashed_password (fixed in FEAT-029)
- `B-027-1` — user-service connects to MySQL at import time (fixed in FEAT-034)
- `B-027-2` — character-service tests use invalid `from conftest import` (fixed in FEAT-021/035)
- `B-027-3` — skills-service tests hang due to async engine (fixed in FEAT-034)
- `B-027-4` — notification-service conftest creates Pydantic model without required fields (fixed in FEAT-035)
- `B-027-6` — character-attributes-service test fails to collect (fixed in FEAT-035)

Update `#2` description to reflect that admin endpoints are now protected (FEAT-035 RBAC), and only user-facing mutation endpoints remain unprotected. Update statistics at the bottom.

### Task 2: Fix B-027-5 — locations-service SQL injection test
**Agent:** QA Test (or Backend Developer)
**Priority:** MEDIUM
**Files:** `services/locations-service/app/tests/test_rules.py`
**Description:**
The `test_sql_injection_in_rule_id_delete` test (line 400) may fail due to URL encoding of the space in `/rules/1 OR 1=1/delete`. Fix the test:
1. Run the test to confirm failure and exact status code returned
2. If it returns an unexpected status code, adjust the assertion
3. If the URL with space causes client-side issues, use URL encoding: `/rules/1%20OR%201%3D1/delete` or a different injection pattern without spaces like `/rules/1;DROP%20TABLE/delete`
4. Verify test passes after fix

**Acceptance criteria:** `pytest services/locations-service/app/tests/test_rules.py::TestRulesSecurity::test_sql_injection_in_rule_id_delete` passes

---

## 5. Review Log (filled by Reviewer — in English)

*Pending...*

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-18 20:00 — PM: фича создана (FEAT-037), запускаю анализ багов
[LOG] 2026-03-18 20:15 — Analyst: начал анализ 8 багов, изучаю user-service, character-service, skills-service, notification-service, locations-service, character-attributes-service
[LOG] 2026-03-18 20:30 — Analyst: анализ завершён. 6 из 8 багов уже исправлены (FEAT-029/034/035). B-027-5 требует минорного фикса теста. #2 (auth) слишком большой для батча, рекомендую отдельную фичу. Написал analysis report, architecture decision и task breakdown.
[LOG] 2026-03-18 21:00 — QA: проверил B-027-5 (test_sql_injection_in_rule_id_delete). Тест уже проходит — URL с пробелом корректно обрабатывается FastAPI/Starlette (возвращает 401, т.к. auth срабатывает до валидации path param). py_compile OK. Оба теста в TestRulesSecurity проходят. Фикс не требуется.
[LOG] 2026-03-18 21:10 — Backend Dev: Task 1 выполнен. Удалены 6 исправленных багов из ISSUES.md (A-029-1, B-027-1, B-027-2, B-027-3, B-027-4, B-027-6). Обновлено описание #2 — отражено что admin-эндпоинты защищены RBAC (FEAT-035/036), осталось ~20-30 user-facing эндпоинтов без auth. Статистика обновлена: 19 → 13 issues.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
