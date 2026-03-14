# FEAT-005: Fix exception handling in HTTP helper functions (character-service crud.py)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-12 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-005-fix-http-helpers-exception-handling.md` → `DONE-FEAT-005-fix-http-helpers-exception-handling.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
В character-service `crud.py` есть HTTP-хелперы (send_inventory_request, send_skills_request и др.), которые делают межсервисные HTTP-вызовы. Они используют `except Exception` для обработки сетевых ошибок. Нужно улучшить обработку ошибок: использовать конкретные типы исключений, логировать ошибки через logger.

### Бизнес-правила
- Межсервисные вызовы должны корректно обрабатывать сетевые ошибки
- Ошибки должны логироваться (не print)
- Вызывающий код должен получать понятную информацию об ошибке

### Контекст
- Обнаружено в FEAT-004 как out-of-scope задача
- Эти функции вызываются из `approve_character_request` при одобрении заявки на персонажа
- При ошибке возвращают None, вызывающий код проверяет и возвращает 500

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-service | exception handling refactor | `app/crud.py`, `app/main.py` |

### Existing Patterns

- **Sync/Async:** character-service uses sync SQLAlchemy for DB, but HTTP helpers are `async` using `httpx.AsyncClient`
- **HTTP Library:** All inter-service calls use `httpx` (not `requests`)
- **Good pattern already exists:** `get_full_profile` in `main.py` (lines 379, 398) already catches `httpx.RequestError` — this is the reference pattern
- **Logger:** `logging.getLogger("character-service")` in `main.py`, `logging.getLogger("character-service.crud")` in `crud.py`

### Functions to Fix

**In `crud.py`:**

| # | Function | Line | Exception | Logging | Returns on Error |
|---|----------|------|-----------|---------|-----------------|
| 1 | `send_equipment_slots_request` | 180 | `except Exception` | `print()` | `None` |
| 2 | `send_inventory_request` | 406 | `except Exception` | `print()` | `None` |
| 3 | `send_skills_request` | 435 | `except Exception` | `print()` | `None` |
| 4 | `send_attributes_request` | 462 | `except Exception` | `logger.error()` ✓ | `None` |
| 5 | `assign_character_to_user` | 491 | `except Exception` | `print()` | `False` |
| 6 | `get_character_experience` | 570 | **NO try/except** | none | `None` (on non-200) |
| 7 | `send_skills_presets_request` | 578 | `except Exception` | `print()` | `None` |

**In `main.py`:**

| # | Function | Line | Exception | Logging | Returns on Error |
|---|----------|------|-----------|---------|-----------------|
| 8 | `update_user_with_character` | 175 | `except Exception` | `print()` | `False` |
| 9 | `get_character_profile` (inline httpx call) | 579 | `except Exception` | `logger.error()` ✓ | `""` (fallback) |

### Additional Issue: Duplicate Logger in crud.py

Line 12: `logger = logging.getLogger("character-service.crud")`
Line 460: `logger = logging.getLogger("character-service.utils")` — **overwrites** the first logger. Functions above line 460 use the `.crud` logger, functions below use `.utils`. This should be consolidated to a single `"character-service.crud"` logger.

### Cross-Service Dependencies

All HTTP helpers call other services — no changes to their APIs:
```
send_inventory_request ──HTTP POST──> inventory-service (POST /inventory/)
send_skills_request ──HTTP POST──> skills-service (POST /skills/)
send_skills_presets_request ──HTTP POST──> skills-service (POST /skills/assign_multiple)
send_attributes_request ──HTTP POST──> character-attributes-service (POST /attributes/)
send_equipment_slots_request ──HTTP POST──> inventory-service (POST /inventory/slots — via EQUIPMENT_SERVICE_URL)
assign_character_to_user ──HTTP POST/PUT──> user-service (POST /users/user_characters/, PUT /users/{id}/update_character)
get_character_experience ──HTTP GET──> character-attributes-service (GET /attributes/{id}/experience)
update_user_with_character ──HTTP POST/PUT──> user-service (same as assign_character_to_user)
get_character_profile ──HTTP GET──> user-service (GET /users/{id})
```

### DB Changes

None. This is a pure code-quality refactor — no schema or migration changes.

### Risks

- **Risk:** Catching only `httpx.RequestError` might miss non-network errors (e.g., JSON decode errors from malformed responses). **Mitigation:** Also catch `httpx.HTTPStatusError` if `response.raise_for_status()` is used, but since these functions manually check `status_code`, only `httpx.RequestError` is needed for network-level errors.
- **Risk:** `update_user_with_character` in `main.py` appears to be dead code (never called — `assign_character_to_user` in `crud.py` does the same thing). **Mitigation:** Fix it anyway for consistency, note it as potential dead code for future cleanup.

---

## 3. Architecture Decision (filled by Architect — in English)

### Design

This is an exception-handling refactor with no API, DB, or frontend changes. The design follows the existing good pattern from `get_full_profile` in `main.py`.

### Exception Strategy

All HTTP helper functions use `httpx.AsyncClient`. The correct specific exception hierarchy for httpx:

- `httpx.RequestError` — base class for all request-level errors (connection refused, timeout, DNS failure, etc.)
  - `httpx.ConnectError` — connection refused
  - `httpx.TimeoutException` — request timed out
  - `httpx.ReadError`, `httpx.WriteError`, etc.

**Decision:** Replace `except Exception` with `except httpx.RequestError` in all HTTP helpers. This catches all network/transport errors while allowing programming errors (TypeError, KeyError, etc.) to propagate naturally.

The functions that manually check `response.status_code` and return `None`/`False` on non-200 already handle HTTP-level errors (4xx, 5xx). The `except` block only needs to handle transport-level failures.

### Changes per Function

**crud.py:**

1. **Remove duplicate logger** on line 460. Keep single `logger = logging.getLogger("character-service.crud")` at top.

2. **`send_equipment_slots_request`:** `except Exception` → `except httpx.RequestError`, `print()` → `logger.error()`

3. **`send_inventory_request`:** `except Exception` → `except httpx.RequestError`, all `print()` → `logger.info()`/`logger.error()`

4. **`send_skills_request`:** `except Exception` → `except httpx.RequestError`, all `print()` → `logger.info()`/`logger.error()`

5. **`send_attributes_request`:** `except Exception` → `except httpx.RequestError` (logger already used ✓)

6. **`assign_character_to_user`:** `except Exception` → `except httpx.RequestError`, all `print()` → `logger.info()`/`logger.error()`

7. **`get_character_experience`:** Add `try/except httpx.RequestError` with `logger.error()`, return `None` on error (consistent with other helpers)

8. **`send_skills_presets_request`:** `except Exception` → `except httpx.RequestError`, `print()` → `logger.error()`

**main.py:**

9. **`update_user_with_character`:** `except Exception` → `except httpx.RequestError`, all `print()` → `logger.info()`/`logger.error()`

10. **`get_character_profile` inline call:** `except Exception` → `except httpx.RequestError` (logger already used ✓)

### Return-Value Contract (preserved)

| Function | Returns on success | Returns on error |
|----------|-------------------|-----------------|
| `send_equipment_slots_request` | `dict` (response JSON) | `None` |
| `send_inventory_request` | `dict` (response JSON) | `None` |
| `send_skills_request` | `dict` (response JSON) | `None` |
| `send_attributes_request` | `dict` (response JSON) | `None` |
| `assign_character_to_user` | `True` | `False` |
| `get_character_experience` | `dict` (response JSON) | `None` |
| `send_skills_presets_request` | `dict` (response JSON) | `None` |
| `update_user_with_character` | `True` | `False` |
| `get_character_profile` inline | `str` (username) | `""` (fallback) |

All callers already check for `None`/`False` — no caller changes needed.

### Security Considerations

- No new endpoints, no auth changes
- Error messages logged with `logger.error()` do not leak sensitive data (only status codes, service names, and exception messages)
- No user-facing error message changes

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Fix exception handling in all HTTP helper functions: (a) Remove duplicate logger definition on line 460 of crud.py, keep single `character-service.crud` logger at top. (b) Replace `except Exception` with `except httpx.RequestError` in all 7 functions in crud.py (`send_equipment_slots_request`, `send_inventory_request`, `send_skills_request`, `send_attributes_request`, `assign_character_to_user`, `get_character_experience`, `send_skills_presets_request`). (c) Add try/except to `get_character_experience` which currently has none. (d) Replace all `print()` calls with `logger.info()` or `logger.error()` as appropriate. (e) In main.py: fix `update_user_with_character` — replace `except Exception` with `except httpx.RequestError`, replace `print()` with logger calls. (f) In main.py: fix `get_character_profile` inline httpx call — replace `except Exception` with `except httpx.RequestError`. (g) Preserve all return values (None/False/empty string on error). | Backend Developer | DONE | `services/character-service/app/crud.py`, `services/character-service/app/main.py` | — | All `except Exception` replaced with `except httpx.RequestError`, no `print()` calls remain in HTTP helpers, duplicate logger removed, `get_character_experience` has proper error handling, `python -m py_compile` passes for both files |
| 2 | Write unit tests for the fixed HTTP helper functions: (a) Test each helper with mocked httpx responses (success, non-200, network error). (b) Verify that `httpx.RequestError` is caught and returns None/False. (c) Verify that non-httpx exceptions (e.g., TypeError) propagate upward. (d) Verify logger.error is called on failure. (e) Test `update_user_with_character` and `get_character_profile` inline call similarly. | QA Test | DONE | `services/character-service/tests/test_http_helpers.py` | #1 | All tests pass with `pytest`, coverage for success/failure/network-error paths |
| 3 | Review all changes from tasks #1 and #2 | Reviewer | DONE | all changed files | #1, #2 | Review checklist passed, no `except Exception` remains in HTTP helpers, no `print()` in HTTP helpers, tests cover error paths |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-12
**Result:** FAIL

#### Summary

The core refactor in `crud.py` is correct and well-executed. All 7 HTTP helper functions now use `except httpx.RequestError`, the duplicate logger is removed, `get_character_experience` has proper error handling, and all `print()` calls in helpers are replaced with logger calls. The `update_user_with_character` function in `main.py` is also correctly fixed.

However, two issues were found:

#### Issues Found

| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/character-service/app/main.py:575,579` | **Regression in `get_character_profile`:** `resp.raise_for_status()` (line 575) raises `httpx.HTTPStatusError` on non-2xx responses. `HTTPStatusError` inherits from `httpx.HTTPError`, NOT from `httpx.RequestError`. With the old `except Exception` this was caught silently (returning `""` as fallback). Now with `except httpx.RequestError` (line 579), any non-2xx from user-service will cause an unhandled exception and a 500 error from this endpoint. **Fix:** either catch `httpx.HTTPStatusError` as well (add a second except clause), or replace `raise_for_status()` with a manual `status_code` check (consistent with all other helpers), or catch `httpx.HTTPError` (base class of both). | Backend Developer | FIX_REQUIRED |
| 2 | `services/character-service/app/tests/test_http_helpers.py` | **Missing test coverage for `get_character_profile` inline call.** Task 2 acceptance criteria explicitly required testing this function: "(e) Test `update_user_with_character` and `get_character_profile` inline call similarly." The test file only covers 8 functions (7 crud + `update_user_with_character`). `get_character_profile` is not tested. Note: this endpoint requires a DB session mock, which is more complex, but coverage is still required per the task spec. | QA Test | FIX_REQUIRED |

#### Checklist Results

**crud.py correctness:**
- [x] No `except Exception` in any HTTP helper function (the one at line 221 is in a commented-out block wrapped in triple quotes, not an active HTTP helper)
- [x] All 7 helpers use `except httpx.RequestError`
- [x] No `print()` calls in HTTP helpers — all use `logger.info()`/`logger.error()`
- [x] Duplicate logger removed — only one `logger = logging.getLogger("character-service.crud")` at line 12
- [x] `get_character_experience` now has try/except with `httpx.RequestError`
- [x] Return values preserved (None/False on error)
- [x] `httpx` is properly imported at line 1

**main.py correctness:**
- [x] `update_user_with_character`: uses `except httpx.RequestError`, no `print()` — PASS
- [ ] `get_character_profile` inline: uses `except httpx.RequestError` but `raise_for_status()` throws `HTTPStatusError` which is NOT a subclass of `RequestError` — **REGRESSION** (see issue #1)
- [x] `httpx` is imported at line 1
- [x] No other code changed beyond scope

**Tests quality:**
- [x] Cover 7 crud.py functions — PASS
- [x] Cover `update_user_with_character` from main.py — PASS
- [ ] Missing coverage for `get_character_profile` inline call (see issue #2)
- [x] Test network error → fallback return value
- [x] Test non-httpx exception propagation (TypeError/ValueError)
- [x] Test logger.error is called on network error
- [x] Use proper async test patterns (pytest-asyncio)
- [x] Mock httpx correctly via `patch("crud.httpx.AsyncClient")`

**No scope creep:**
- [x] Only HTTP helper functions changed
- [x] No API contract changes
- [x] No cross-service impact
- [x] No DB/migration changes

**Pre-existing issues noted (not blocking):**
- `approve_character_request` in main.py (lines 68-151) still uses `print()` extensively — this is the calling endpoint, not an HTTP helper, so it is out of scope for this feature. Could be a future cleanup task.
- `except Exception` at main.py:540 in `update_location` is a DB commit error handler, not an HTTP helper — out of scope.

**Compile check:**
- Unable to run `py_compile` (Bash not available). Code was reviewed manually for syntax correctness — no issues found.

### Review #2 — 2026-03-12
**Result:** PASS

#### Fix #1 Verification: `get_character_profile` regression

Confirmed fixed in `services/character-service/app/main.py` lines 570-585:
- `raise_for_status()` is completely removed (grep confirms zero matches in the file)
- Replaced with manual `resp.status_code == 200` check (line 575)
- On non-200: logs error with `logger.error()` including status code and response text (line 580), falls back to `user_nickname = ""` (line 581)
- On `httpx.RequestError`: caught at line 582, logged, falls back to `""` (line 585)
- Pattern is now fully consistent with all other HTTP helpers in both `crud.py` and `main.py`

#### Fix #2 Verification: `TestGetCharacterProfile` tests

Confirmed added in `services/character-service/app/tests/test_http_helpers.py` lines 580-684. The `TestGetCharacterProfile` class contains 5 tests:

1. `test_network_error_returns_empty_nickname` — mocks `httpx.RequestError`, verifies endpoint returns 200 with `user_nickname == ""`
2. `test_success_returns_username` — mocks 200 response with `{"username": "player1"}`, verifies `user_nickname == "player1"`
3. `test_non_200_response_returns_empty_nickname` — mocks 500 response, verifies fallback to `""`
4. `test_character_not_found_returns_404` — no character in DB, verifies 404
5. `test_network_error_logs_error` — verifies `logger.error` is called on `RequestError`

Tests use `conftest.py` fixtures (`client`, `mock_db_session`) with `FastAPI.TestClient` and DB dependency override. Pattern is correct — these are sync tests using `TestClient` (appropriate since the endpoint uses sync `Depends(get_db)` with an async inline httpx call).

Note: `test_success_returns_username` still sets `mock_response.raise_for_status = MagicMock()` (line 629) which is now unnecessary since `raise_for_status()` was removed. This is harmless (unused mock attribute) and does not affect correctness.

#### Re-check of Review #1 items

All items from Review #1 remain correct:
- **crud.py**: Single `logger` definition at line 12 (no duplicate). All 7 HTTP helpers use `except httpx.RequestError`. The only `except Exception` is inside a triple-quoted comment block (line 221). The only `print()` is also inside that commented block (line 222).
- **main.py**: `update_user_with_character` uses `except httpx.RequestError` (line 206). `get_character_profile` uses `except httpx.RequestError` (line 582). The `except Exception` at line 540 is a DB commit handler in `update_location` — out of scope.
- **No scope creep**: No API contract changes, no cross-service impact, no DB changes.

#### Final Checklist

- [x] No `except Exception` in any active HTTP helper function
- [x] No `print()` in any active HTTP helper function
- [x] Single logger definition in crud.py
- [x] `get_character_experience` has proper try/except
- [x] `get_character_profile` uses manual status check (no `raise_for_status`)
- [x] All return-value contracts preserved
- [x] Tests cover all 9 functions (7 crud + 2 main)
- [x] Tests cover: network error, success, non-200, non-network exception propagation, logger calls
- [x] conftest.py provides proper fixtures for endpoint-level tests
- [x] No frontend changes (T1/T3 not applicable)
- [x] No security concerns (no new endpoints, no auth changes, no data leaks in logs)

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-12 20:00 — PM: фича создана на основе follow-up из FEAT-004, запускаю архитектора
[LOG] 2026-03-12 20:15 — Architect: начал проектирование, анализ crud.py и main.py
[LOG] 2026-03-12 20:30 — Architect: найдено 9 функций для исправления (7 в crud.py, 2 в main.py), обнаружен дубликат logger в crud.py. Спроектировано 3 задачи. Статус → IN_PROGRESS
[LOG] 2026-03-12 21:00 — Backend Dev: начал задачу #1
[LOG] 2026-03-12 21:15 — Backend Dev: задача #1 завершена, изменено 2 файла (crud.py, main.py). Удалён дубликат logger, заменены except Exception → except httpx.RequestError в 8 функциях, print() → logger в 7 функциях, добавлен try/except в get_character_experience
[LOG] 2026-03-12 22:00 — QA: начал написание тестов для HTTP-хелперов character-service (задача #2)
[LOG] 2026-03-12 22:30 — QA: тесты готовы, 30 тестов в test_http_helpers.py. Покрыты все 8 функций (7 crud.py + 1 main.py): network error → fallback, non-network exception → propagation, logger.error вызов, success/failure paths. Добавлен pytest-asyncio в requirements.txt
[LOG] 2026-03-12 23:00 — Reviewer: начал проверку всех изменений FEAT-005
[LOG] 2026-03-12 23:15 — Reviewer: проверка завершена, результат FAIL. Найдено 2 проблемы: (1) регрессия в get_character_profile — raise_for_status() выбрасывает HTTPStatusError, который не ловится except httpx.RequestError; (2) отсутствуют тесты для get_character_profile inline call
[LOG] 2026-03-12 23:30 — Backend Dev: исправлена регрессия #1 в get_character_profile (main.py:573-583). Удалён raise_for_status(), заменён ручной проверкой resp.status_code == 200 с logger.error() для non-200 — консистентно со всеми остальными хелперами в файле
[LOG] 2026-03-12 23:45 — QA: добавлены 5 тестов для get_character_profile в test_http_helpers.py: network error → fallback empty string, success → returns username, non-200 → fallback, character not found → 404, network error → logger.error вызов
[LOG] 2026-03-12 23:55 — Reviewer: начал Review #2, проверка исправлений по результатам Review #1
[LOG] 2026-03-12 23:58 — Reviewer: проверка завершена, результат PASS. Оба исправления подтверждены: (1) raise_for_status() удалён, заменён ручной проверкой status_code; (2) 5 тестов для get_character_profile добавлены и корректны. Статус → REVIEW
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Исправлена обработка исключений в 9 HTTP-хелперах character-service: `except Exception` → `except httpx.RequestError`
- Заменены все `print()` на `logger.info()`/`logger.error()` в HTTP-хелперах
- Удалён дубликат logger в crud.py (было два определения с разными именами)
- Добавлен try/except в `get_character_experience` (ранее не было обработки ошибок)
- Удалён `raise_for_status()` в `get_character_profile` — заменён ручной проверкой status_code (консистентно с остальными хелперами)
- Написано 35 тестов для всех 9 HTTP-хелперов

### Что изменилось от первоначального плана
- Ревью #1 выявил регрессию: `raise_for_status()` бросает `HTTPStatusError` который не наследует от `RequestError` — исправлено
- Добавлены тесты для `get_character_profile` (пропущены в первой итерации)

### Оставшиеся риски / follow-up задачи
- `approve_character_request` в main.py всё ещё использует `print()` в основном теле (не HTTP-хелпер, отдельная задача)
- `update_user_with_character` в main.py возможно dead code (дублирует `assign_character_to_user` в crud.py)
