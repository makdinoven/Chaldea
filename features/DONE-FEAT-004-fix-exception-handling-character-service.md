# FEAT-004: Fix systemic except Exception pattern in character-service

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-12 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-004-fix-exception-handling-character-service.md` → `DONE-FEAT-004-fix-exception-handling-character-service.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Исправление системного бага ISSUES #21: в character-service 6 эндпоинтов используют `except Exception`, который перехватывает `HTTPException` и превращает все ошибки в 500. Аналогичный баг уже был исправлен для `moderation-requests` в FEAT-003.

### Бизнес-правила
- Эндпоинты должны корректно возвращать 404/400 ошибки, а не 500
- Только реальные ошибки БД должны приводить к 500
- Ошибки должны логироваться через logger, а не print

### Затронутые эндпоинты
1. `approve_character_request`
2. `reject_character_request`
3. `delete_character`
4. `assign_title`
5. `set_current_title`
6. `get_titles_for_character`

### Дополнительно (из FEAT-003)
- `crud.get_moderation_requests()` тоже содержит `except Exception` который глушит ошибки БД — проверить другие crud-функции на аналогичный паттерн

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1 Affected Endpoints in main.py

All endpoints below use `except Exception` which catches `HTTPException` and replaces it with a generic 500 error. They also use `print()` instead of `logger.error()`.

**Endpoints that raise HTTPException inside the try block (HIGH priority — user sees wrong error):**

| # | Endpoint | Line (except) | HTTPException inside try | Effect |
|---|----------|---------------|--------------------------|--------|
| 1 | `approve_character_request` | 154 | 404 (line 74), multiple 500s | All become generic 500 |
| 2 | `reject_character_request` | 223 | 404 (line 219) | 404 becomes 500 |
| 3 | `delete_character` | 170 | 404 (line 168) | 404 becomes 500 |
| 4 | `assign_title` | 284 | 404 (line 282) | 404 becomes 500 |
| 5 | `set_current_title` | 299 | 404 (line 297) | 404 becomes 500 |
| 6 | `get_titles_for_character` | 325 | 404 (line 323) | 404 becomes 500 |

**Endpoints that do NOT raise HTTPException inside try but still use bad pattern (MEDIUM priority — print instead of logger, overly broad catch):**

| # | Endpoint | Line (except) | Notes |
|---|----------|---------------|-------|
| 7 | `create_character_request` | 48 | No HTTPException inside try, but uses print |
| 8 | `get_races_and_subraces` | 239 | No HTTPException inside try, but uses print |
| 9 | `create_title` | 270 | No HTTPException inside try, but uses print |
| 10 | `get_titles` | 311 | No HTTPException inside try, but uses print |

**Already fixed (FEAT-003):**
- `get_moderation_requests` — already uses `except SQLAlchemyError` with `logger.error()`

**Endpoints with correct patterns (no changes needed):**
- `deduct_points` — no try/except wrapper, uses logger, raises HTTPException directly
- `get_full_profile` — uses `except httpx.RequestError`, logger, raises HTTPException correctly
- `get_basic_info`, `get_characters_by_location`, `get_character_profile`, `get_short_info`, `list_characters` — no broad try/except
- `update_location` — uses `except Exception` only around `db.commit()` with proper rollback (acceptable pattern)

### 2.2 Affected Functions in crud.py

| # | Function | Line (except) | Problem |
|---|----------|---------------|---------|
| 1 | `get_moderation_requests` | 315 | `except Exception` returns `{}` — swallows DB errors silently, uses `print()` |

**HTTP helper functions** (`send_inventory_request`, `send_skills_request`, `send_attributes_request`, `send_equipment_slots_request`, `assign_character_to_user`, `send_skills_presets_request`) also use `except Exception` but these intentionally return `None` on network failure — the caller in main.py checks the result and raises HTTPException. These are a separate concern (network error handling vs DB error swallowing) and should not be changed in this feature.

### 2.3 Pattern Reference (from FEAT-003 fix)

The `get_moderation_requests` endpoint was fixed in FEAT-003:
- `except Exception` → `except SQLAlchemyError`
- `print()` → `logger.error()`
- This let `HTTPException` propagate naturally through FastAPI

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Fix Strategy

Apply the same pattern from FEAT-003 consistently across all affected endpoints:

**For endpoints 1-6 (HIGH priority — HTTPException swallowed):**
- Replace `except Exception as e:` with `except SQLAlchemyError as e:`
- Replace `print(f"...")` with `logger.error(f"...")`
- `HTTPException` will now propagate naturally (not caught by SQLAlchemyError handler)

**For endpoints 7-10 (MEDIUM priority — no HTTPException but bad pattern):**
- Same fix: `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`
- These endpoints don't have HTTPException inside the try block, but fixing them prevents future bugs if someone adds one

**For crud.py `get_moderation_requests`:**
- Replace `except Exception` with `except SQLAlchemyError`
- Replace `print()` with `logger.error()`
- Change `return {}` to re-raise the exception so the endpoint handler can return a proper 500
- This matches how other crud functions behave (they don't catch exceptions at all — they let them propagate to the endpoint)

### 3.2 Import Requirements

`SQLAlchemyError` is already imported in main.py (line 3): `from sqlalchemy.exc import SQLAlchemyError`

For crud.py, `SQLAlchemyError` must be added to imports.

### 3.3 Scope Boundaries

**In scope:**
- All 10 `except Exception` blocks in main.py endpoints
- 1 `except Exception` block in crud.py `get_moderation_requests()`
- Replace all `print()` with `logger.error()` / `logger.info()` in affected blocks only

**Out of scope:**
- HTTP helper functions in crud.py (send_inventory_request, etc.) — different concern
- `update_user_with_character` in main.py (line 206) — utility function, not an endpoint
- Other `print()` statements outside the affected try/except blocks
- Any refactoring beyond the exception handling fix

### 3.4 Risk Assessment

- **Risk: LOW** — changing exception type from broader to narrower cannot break existing functionality
- **Risk: NONE for API contracts** — no API changes, only internal error handling
- **Risk: NONE for cross-service** — no inter-service contract changes
- **Rollback:** simple revert of the commit

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: Fix exception handling in main.py and crud.py

| Field | Value |
|-------|-------|
| **#** | 1 |
| **Description** | Fix all `except Exception` blocks in character-service endpoints and crud.py `get_moderation_requests()`. For each: (1) replace `except Exception` with `except SQLAlchemyError`, (2) replace `print()` with `logger.error()`, (3) in crud.py add `from sqlalchemy.exc import SQLAlchemyError` to imports, (4) in crud.py `get_moderation_requests()` re-raise the exception instead of returning `{}` |
| **Agent** | Backend Developer |
| **Status** | TODO |
| **Files** | `services/character-service/app/main.py`, `services/character-service/app/crud.py` |
| **Depends On** | — |
| **Acceptance Criteria** | (1) No `except Exception` remains in any endpoint handler in main.py (excluding `update_location` which has proper rollback pattern and `update_user_with_character` utility). (2) No `except Exception` in `get_moderation_requests` in crud.py. (3) All error logging uses `logger.error()`, not `print()`. (4) `SQLAlchemyError` is imported in crud.py. (5) crud.py `get_moderation_requests()` re-raises exceptions instead of returning `{}`. |

**Detailed changes for main.py (10 endpoints):**

1. `create_character_request` (line 48): `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`
2. `approve_character_request` (line 154): `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`
3. `delete_character` (line 170): `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`
4. `reject_character_request` (line 223): `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`
5. `get_races_and_subraces` (line 239): `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`
6. `create_title` (line 270): `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`
7. `assign_title` (line 284): `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`
8. `set_current_title` (line 299): `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`
9. `get_titles` (line 311): `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`
10. `get_titles_for_character` (line 325): `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`

**Detailed changes for crud.py:**

1. Add `from sqlalchemy.exc import SQLAlchemyError` to imports
2. `get_moderation_requests` (line 315): `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`, replace `return {}` with `raise`

### Task 2: Write tests for fixed endpoints

| Field | Value |
|-------|-------|
| **#** | 2 |
| **Description** | Write pytest tests verifying that `HTTPException` propagates correctly (returns proper status code, not 500) for the 6 high-priority endpoints. At minimum: (1) test that 404 is returned when resource not found (not 500), (2) test that SQLAlchemyError still results in 500. Mock `db` session and crud functions as needed. |
| **Agent** | QA Test |
| **Status** | TODO |
| **Files** | `services/character-service/tests/test_exception_handling.py` (new file) |
| **Depends On** | Task 1 |
| **Acceptance Criteria** | (1) Tests exist for all 6 high-priority endpoints: `approve_character_request`, `reject_character_request`, `delete_character`, `assign_title`, `set_current_title`, `get_titles_for_character`. (2) Each test verifies HTTPException with non-500 status propagates correctly. (3) At least one test verifies SQLAlchemyError produces 500. (4) All tests pass. |

### Task 3: Remove ISSUES #21 from docs/ISSUES.md

| Field | Value |
|-------|-------|
| **#** | 3 |
| **Description** | Remove issue #21 (`except Exception` ловит `HTTPException` в character-service) from `docs/ISSUES.md` since it will be fully resolved by Task 1. |
| **Agent** | Backend Developer |
| **Status** | TODO |
| **Files** | `docs/ISSUES.md` |
| **Depends On** | Task 1 |
| **Acceptance Criteria** | Issue #21 is removed from ISSUES.md. No other issues are modified. |

### Task 4: Review all changes

| Field | Value |
|-------|-------|
| **#** | 4 |
| **Description** | Review all changes from Tasks 1-3. Verify: (1) no `except Exception` remains in endpoint handlers, (2) all error logging uses logger, (3) HTTPException propagation works correctly, (4) crud.py get_moderation_requests re-raises properly, (5) tests are comprehensive and pass, (6) ISSUES.md is updated. |
| **Agent** | Reviewer |
| **Status** | DONE |
| **Files** | All files modified in Tasks 1-3 |
| **Depends On** | Task 1, Task 2, Task 3 |
| **Acceptance Criteria** | (1) Code follows FEAT-003 pattern consistently. (2) No regressions introduced. (3) Tests cover the critical cases. (4) ISSUES.md correctly updated. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-12
**Result:** FAIL

#### Checklist Results

**1. main.py correctness: PASS**
- All 10 `except Exception` blocks in endpoint handlers replaced with `except SQLAlchemyError as e:` — verified via diff.
- All 10 blocks now use `logger.error()` instead of `print()` — verified.
- `HTTPException` will propagate naturally (not caught by `SQLAlchemyError` handler) — correct.
- Remaining `except Exception` at lines 206 (utility `update_user_with_character`), 540 (`update_location` with rollback), 579 (`get_character_profile` httpx call) — all correctly out of scope.
- `SQLAlchemyError` was already imported (line 3) — no change needed.

**2. crud.py correctness: PASS**
- `from sqlalchemy.exc import SQLAlchemyError` added to imports (line 4) — verified.
- `get_moderation_requests()`: `except Exception` → `except SQLAlchemyError`, `print` → `logger.error`, `return {}` → `raise` — all verified.
- `logger` was already defined (line 12) — no change needed.

**3. Tests quality: PASS**
- 20 tests covering all 6 high-priority endpoints — verified.
- Tests cover: 404 propagation (not converted to 500), SQLAlchemyError → 500, success paths, DB detail leak prevention.
- Use mocked DB via `conftest.py` fixtures (`mock_db_session`, `client` with dependency override) — correct.
- Tests follow existing project patterns.

**4. ISSUES.md: FAIL — 2 issues found (see table)**

**5. Undocumented behavior change: FAIL — 1 issue found (see table)**

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `docs/ISSUES.md:1` | First line corrupted: `Gj# Chaldea - Known Issues & Tech Debt` instead of `# Chaldea - Known Issues & Tech Debt`. The `Gj` prefix breaks the markdown heading. | Backend Developer | FIX_REQUIRED |
| 2 | `docs/ISSUES.md` | Issue #21 was NOT present in HEAD (only 20 issues exist, numbered 1-20). The log says "Удалён issue #21" but git diff shows no issue removal — only the line 1 corruption. Either issue #21 was already removed before this feature, or the log is incorrect. Verify and ensure the file is correct. | Backend Developer | FIX_REQUIRED |
| 3 | `services/character-service/app/main.py:254` | Undocumented behavior change in `get_moderation_requests` endpoint: `raise HTTPException(status_code=404, detail="Заявки на модерацию не найдены")` was changed to `return {}`. This changes the API contract (empty result returns 200 with `{}` instead of 404). This change was NOT in the task spec — Task 1 only specified fixing `except Exception` patterns. If this is intentional, it needs to be documented; if not, revert. | Backend Developer | FIX_REQUIRED |

### Review #2 — 2026-03-12
**Result:** PASS

#### Re-verification of Review #1 Issues

**Issue 1 (FIXED — verified):** `docs/ISSUES.md` line 1 is now `# Chaldea - Known Issues & Tech Debt` — no `Gj` prefix. Confirmed fixed.

**Issue 2 (FALSE POSITIVE — verified):** ISSUES.md contains exactly 20 issues (numbered 1-20). Statistics show CRITICAL=2, HIGH=5, MEDIUM=8, LOW=5, total=20. This is correct: issue #21 was added in FEAT-003 (MEDIUM 8→9, total 20→21) and removed in FEAT-004 (MEDIUM 9→8, total 21→20). The agent's log is accurate.

**Issue 3 (FALSE POSITIVE — verified):** The `get_moderation_requests` endpoint in main.py (lines 245-259) uses `except SQLAlchemyError` and returns `{}` on empty result. This is the FEAT-003 state — the 404→200 change was made in FEAT-003, NOT in FEAT-004. FEAT-004 only changed the 10 other endpoints. Confirmed by reading main.py: the `get_moderation_requests` endpoint was not part of Task 1's scope.

#### Full Re-verification Checklist

**1. main.py — 10 endpoint fixes: PASS**
All 10 `except Exception` blocks replaced with `except SQLAlchemyError as e:` + `logger.error()`:
- `create_character_request` (line 48) — `except SQLAlchemyError`, `logger.error`
- `approve_character_request` (line 154) — `except SQLAlchemyError`, `logger.error`
- `delete_character` (line 170) — `except SQLAlchemyError`, `logger.error`
- `reject_character_request` (line 223) — `except SQLAlchemyError`, `logger.error`
- `get_races_and_subraces` (line 239) — `except SQLAlchemyError`, `logger.error`
- `create_title` (line 270) — `except SQLAlchemyError`, `logger.error`
- `assign_title` (line 284) — `except SQLAlchemyError`, `logger.error`
- `set_current_title` (line 299) — `except SQLAlchemyError`, `logger.error`
- `get_titles` (line 311) — `except SQLAlchemyError`, `logger.error`
- `get_titles_for_character` (line 325) — `except SQLAlchemyError`, `logger.error`

Remaining `except Exception` at lines 206 (utility), 540 (rollback), 579 (httpx) — correctly out of scope.

**2. crud.py fix: PASS**
- `from sqlalchemy.exc import SQLAlchemyError` imported (line 4)
- `get_moderation_requests()`: `except SQLAlchemyError` (line 316), `logger.error` (line 317), `raise` (line 318) — correct

**3. Tests: PASS**
- 20 tests in `test_exception_handling.py` covering all 6 high-priority endpoints
- `conftest.py` with `mock_db_session` and `client` fixtures using dependency override
- Coverage: 404 propagation, 200 success paths, 500 on SQLAlchemyError, DB detail leak prevention
- Test structure follows project patterns

**4. ISSUES.md: PASS**
- Line 1 heading correct
- 20 issues, statistics accurate (CRITICAL=2, HIGH=5, MEDIUM=8, LOW=5, total=20)
- Issue #21 successfully removed

**5. Code standards: PASS**
- No `print()` in affected blocks (all use `logger.error`)
- Pydantic <2.0 syntax preserved
- Sync patterns maintained (character-service is sync)
- No hardcoded secrets
- No frontend changes (no Tailwind/TS migration needed)

**6. Security: PASS**
- Error messages do not leak DB internals (generic messages like "Внутренняя ошибка сервера")
- Test `test_500_does_not_leak_db_details` explicitly verifies this

**7. Cross-service impact: PASS**
- No API contract changes — only internal error handling improved
- No inter-service call modifications

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-12 17:00 — PM: фича создана на основе ISSUES #21 (обнаружен в FEAT-003), запускаю архитектора
[LOG] 2026-03-12 17:15 — Architect: анализ завершён. Найдено 10 эндпоинтов с except Exception в main.py (6 HIGH — глушат HTTPException, 4 MEDIUM — только print вместо logger). В crud.py 1 функция get_moderation_requests с тем же паттерном. Спроектировано 4 задачи: fix main.py+crud.py, QA тесты, обновление ISSUES.md, ревью. Статус: IN_PROGRESS.
[LOG] 2026-03-12 17:30 — Backend Dev: задача #1 завершена. В main.py заменены все 10 `except Exception` на `except SQLAlchemyError`, `print` на `logger.error`. В crud.py добавлен импорт SQLAlchemyError, в get_moderation_requests заменён except Exception на except SQLAlchemyError, print на logger.error, return {} на raise. Изменено 2 файла.
[LOG] 2026-03-12 17:35 — Backend Dev: задача #3 завершена. Удалён issue #21 из docs/ISSUES.md, обновлена статистика: MEDIUM 9→8, итого 21→20.
[LOG] 2026-03-12 18:00 — QA: тесты готовы для задачи #2. Создан test_exception_handling.py: 20 тестов для 6 эндпоинтов (approve, reject, delete, assign_title, set_current_title, get_titles_for_character). Проверяется: 404 не превращается в 500, SQLAlchemyError даёт 500, ответ не утекает деталями БД.
[LOG] 2026-03-12 18:30 — Reviewer: начал проверку задач 1-3
[LOG] 2026-03-12 18:45 — Reviewer: проверка завершена, результат FAIL. main.py и crud.py — корректны. Тесты — корректны. Найдено 3 проблемы: (1) повреждение первой строки ISSUES.md (Gj prefix), (2) issue #21 не найден в HEAD — лог некорректен, (3) недокументированное изменение поведения get_moderation_requests (404→200 при пустом результате).
[LOG] 2026-03-12 19:15 — Reviewer: начал повторную проверку (Review #2)
[LOG] 2026-03-12 19:30 — Reviewer: проверка завершена, результат PASS. Issue #1 исправлен (Gj удалён). Issue #2 и #3 — false positive (подтверждено: #21 корректно удалён, get_moderation_requests изменён в FEAT-003, не в FEAT-004). Все 10 except Exception→except SQLAlchemyError корректны. Тесты покрывают все 6 high-priority эндпоинтов. Статус: REVIEW.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Исправлена обработка исключений в 10 эндпоинтах character-service: `except Exception` → `except SQLAlchemyError`
- Заменены все `print()` на `logger.error()` в затронутых блоках
- Исправлена функция `crud.get_moderation_requests()`: теперь re-raise вместо `return {}`
- Написано 20 тестов для 6 high-priority эндпоинтов
- Issue #21 удалён из ISSUES.md
- Исправлена опечатка `Gj` в заголовке ISSUES.md

### Что изменилось от первоначального плана
- Архитектор обнаружил 10 эндпоинтов вместо 6 (4 дополнительных без HTTPException внутри try, но с тем же плохим паттерном)
- Ревью #1 дал FAIL из-за 2 ложных срабатываний и 1 реальной опечатки в ISSUES.md

### Оставшиеся риски / follow-up задачи
- HTTP-хелперы в crud.py (send_inventory_request и др.) используют `except Exception` для сетевых ошибок — отдельная задача
- `update_user_with_character` в main.py — utility function с `except Exception`, не покрыта
