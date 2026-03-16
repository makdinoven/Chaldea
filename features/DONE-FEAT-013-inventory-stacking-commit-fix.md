# FEAT-013: Баг — стекинг предметов не сохраняется (отсутствует db.commit)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-16 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-013-inventory-stacking-commit-fix.md` → `DONE-FEAT-013-inventory-stacking-commit-fix.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
При добавлении предмета в инвентарь персонажа, если предмет стекается с уже существующим слотом (увеличивается quantity), изменения не сохраняются в БД — отсутствует вызов `db.commit()`. Баг обнаружен в FEAT-012 при написании тестов (issue #16 в ISSUES.md).

### Бизнес-правила
- При добавлении предмета, который уже есть в инвентаре, количество должно увеличиваться
- Изменения должны сохраняться в БД

### UX / Пользовательский сценарий
1. У персонажа уже есть предмет X в количестве 5 (макс. стек 20)
2. Выдаём ещё 3 штуки предмета X
3. Ожидание: в инвентаре 8 штук предмета X
4. Реальность: ответ показывает 8, но в БД осталось 5 (commit не вызван)

### Edge Cases
- Что если предмет полностью заполняет стек и создаёт новый слот?
- Что если добавляется частично в существующий и частично в новый слот?

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Bug Description

In `POST /inventory/{character_id}/items` (`services/inventory-service/app/main.py:98-142`), the `add_item_to_inventory` handler has a missing `db.commit()` when items fit entirely into existing inventory slots.

### Root Cause — Detailed Code Trace

The endpoint logic has two phases:

**Phase 1 — Fill existing slots (lines 112-126):**
```python
for slot in existing_slots:
    if remaining == 0:
        break
    space = db_item.max_stack_size - slot.quantity
    to_add = min(space, remaining)
    slot.quantity += to_add
    remaining -= to_add
    db.add(slot)
    inventory_items.append(slot)
# ← NO db.commit() here
```

**Phase 2 — Create new slots (lines 129-140):**
```python
while remaining > 0:
    ...
    db.add(new_slot)
    db.commit()          # ← commit only happens here
    db.refresh(new_slot)
    ...
```

**The bug:** `db.commit()` is called **only inside the `while remaining > 0` loop** (Phase 2). If all items fit into existing slots (Phase 1 reduces `remaining` to 0), Phase 2 never executes, so `db.commit()` is never called. The in-memory SQLAlchemy objects show the updated quantity (returned to the caller), but the changes are never persisted to MySQL. When the session closes in the `get_db()` finally block, the uncommitted changes are discarded.

### Three Distinct Scenarios

| Scenario | Phase 1 | Phase 2 | `commit()` called? | Bug? |
|----------|---------|---------|---------------------|------|
| All items fit in existing slots | Yes, remaining→0 | Skipped | **NO** | **YES — data lost** |
| Partial fit + overflow | Yes, remaining→N | Yes | Yes (in Phase 2) | Partial — Phase 1 changes are committed by Phase 2's commit, so this works by accident |
| No existing slots (or all full) | Skipped | Yes | Yes | No |

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| inventory-service | bugfix — add missing `db.commit()` | `app/main.py` (lines 98-142) |

### Existing Patterns

- inventory-service: **sync SQLAlchemy**, Pydantic <2.0, Alembic present
- No DB schema changes needed — this is purely a logic fix (missing commit call)
- Other endpoints in the same file (`remove_item_from_inventory` at line 174, `use_item` at line 394, `equip_item` at line 280) all call `db.commit()` correctly
- `crud.py:return_item_to_inventory()` (line 149) has the same stacking pattern and correctly calls `db.commit()` after updating `slot.quantity`

### Cross-Service Dependencies

**Who calls `POST /inventory/{character_id}/items`?**

1. **character-service** — `crud.py:send_inventory_request()` calls `POST /inventory/` (the creation endpoint, **not** the `/{character_id}/items` endpoint). This is a different endpoint — no impact.
2. **battle-service** — `inventory_client.py`, `skills_client.py`, `battle_engine.py` all use `GET /inventory/items/{item_id}` (read-only). No impact.
3. **Frontend** — likely calls `POST /{character_id}/items` when granting items. This is where users would experience the bug.

No other service calls `POST /{character_id}/items` via HTTP. The bug is self-contained in inventory-service.

### DB Changes

None required. The `character_inventory` table schema is correct — `quantity` column (Integer) is fine. The issue is purely that the ORM update is not flushed to the database.

### Existing Tests

File: `services/inventory-service/app/tests/test_add_item_to_inventory.py`

The test `test_stacking_fills_existing_slot` (line 90) **directly tests the buggy scenario**:
- Creates an item with `max_stack_size=50`
- Pre-populates inventory with 10 arrows
- Adds 5 more via the endpoint
- Asserts `slot.quantity == 15` by querying the DB

This test **will fail** with the current code because the `db.commit()` is missing — the DB still shows `quantity=10` after the API call.

Additionally, `test_stacking_partial_fill_then_new_slot` (line 141) tests the partial-fit scenario (7 + 8 with max_stack=10). This one likely passes by accident because Phase 2 creates a new slot and its `db.commit()` also persists the Phase 1 changes.

### Risks

- **Risk:** Minimal — single-line fix (add `db.commit()` after the existing-slots loop). No API contract changes, no schema changes, no cross-service impact.
- **Risk:** The current Phase 2 commit pattern (commit inside `while` loop) commits once per new slot created. This is suboptimal but not a bug — a single commit after both phases would be cleaner and more atomic.
- **Mitigation:** The fix should add a single `db.commit()` after both loops (or at minimum after the Phase 1 loop). Moving to a single commit after both phases would also fix the multiple-commit-per-slot issue and make the operation more atomic.

### Recommended Fix

Replace the per-iteration `db.commit()` inside the `while` loop with a single `db.commit()` after both loops complete. This:
1. Fixes the bug (missing commit for Phase 1)
2. Makes the entire operation atomic (either all changes persist or none)
3. Is consistent with `remove_item_from_inventory` which does a single commit at the end

---

## 3. Architecture Decision (filled by Architect — in English)

### Summary

This is a single-file bugfix in `services/inventory-service/app/main.py`. No API contract changes, no DB schema changes, no cross-service impact.

### Fix Design

**Current code** (`add_item_to_inventory`, lines 98-142):
- Phase 1 (fill existing slots): calls `db.add(slot)` but never `db.commit()`.
- Phase 2 (create new slots): calls `db.commit()` inside the `while` loop, once per new slot.

**Fixed code:**
1. Remove `db.commit()` and `db.refresh(new_slot)` from inside the Phase 2 `while` loop.
2. Add a single `db.commit()` after both loops complete.
3. Add `db.refresh(slot)` for each item in `inventory_items` after the commit, so the returned objects reflect DB-generated values (e.g., `id` for newly created slots).

### Why a single commit after both loops

- **Fixes the bug:** Phase 1 changes are now committed.
- **Atomicity:** Either all slot updates + new slot creations succeed, or none do. Currently, if Phase 2 fails mid-way, some new slots are committed and some are not.
- **Consistency with codebase:** `remove_item_from_inventory` (line 174) and `crud.py:return_item_to_inventory()` (line 149) both use a single commit at the end.

### Data Flow (unchanged)

```
Client → POST /{character_id}/items → inventory-service
  → Query Items table (validate item exists)
  → Query CharacterInventory (find existing partial slots)
  → Phase 1: update existing slot quantities in memory
  → Phase 2: create new CharacterInventory rows in memory
  → db.commit()  ← single commit for all changes
  → db.refresh() each returned object
  → Return List[CharacterInventory]
```

### Risks

- **Minimal.** The fix changes commit timing but not business logic. All existing callers receive the same response format.
- **Rollback:** Revert the single commit to restore previous behavior (though previous behavior is buggy).

### Security

No changes to authentication, authorization, or input validation. The endpoint's security posture remains the same (no auth check — existing known issue).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1 — Fix missing db.commit() in add_item_to_inventory

| Field | Value |
|-------|-------|
| **#** | 1 |
| **Description** | In `add_item_to_inventory` endpoint: (1) Remove `db.commit()` and `db.refresh(new_slot)` from inside the Phase 2 `while` loop. (2) Add a single `db.commit()` after both loops. (3) Add a `for slot in inventory_items: db.refresh(slot)` loop after the commit so returned objects have DB-generated values. |
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/inventory-service/app/main.py` (lines 98-142) |
| **Depends On** | — |
| **Acceptance Criteria** | 1. `db.commit()` is called exactly once, after both Phase 1 and Phase 2 loops. 2. All items in `inventory_items` are refreshed before return. 3. `python -m py_compile main.py` passes. |

### Task 2 — Verify existing tests pass, add edge case tests if needed

| Field | Value |
|-------|-------|
| **#** | 2 |
| **Description** | Run all 10 existing tests in `test_add_item_to_inventory.py`. Confirm `test_stacking_fills_existing_slot` now passes. Confirm `test_stacking_partial_fill_then_new_slot` still passes. If any edge cases are missing (e.g., adding to multiple partial stacks simultaneously), add them. |
| **Agent** | QA Test |
| **Status** | DONE |
| **Files** | `services/inventory-service/app/tests/test_add_item_to_inventory.py` |
| **Depends On** | Task 1 |
| **Acceptance Criteria** | 1. All existing tests pass (10/10). 2. `test_stacking_fills_existing_slot` passes (the primary regression test). 3. Any new edge case tests also pass. |

### Task 3 — Final review

| Field | Value |
|-------|-------|
| **#** | 3 |
| **Description** | Review the fix for correctness, atomicity, and consistency with codebase patterns. Verify no regressions. Run tests. |
| **Agent** | Reviewer |
| **Status** | DONE |
| **Files** | `services/inventory-service/app/main.py`, `services/inventory-service/app/tests/test_add_item_to_inventory.py` |
| **Depends On** | Task 1, Task 2 |
| **Acceptance Criteria** | 1. Code matches the architecture decision. 2. All tests pass. 3. No cross-service impact. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-16
**Result:** PASS

#### Code Review
- **Fix correctness:** `db.commit()` removed from inside Phase 2 loop, single `db.commit()` added after both loops (line 140). `db.refresh()` applied to all items in `inventory_items` (lines 141-142). Matches architecture decision exactly.
- **Atomicity:** Both Phase 1 (update existing slots) and Phase 2 (create new slots) are committed in a single transaction. If Phase 2 fails, Phase 1 changes roll back too.
- **No regressions:** New slot creation (Phase 2 only) still works — commit happens after the loop, `db.refresh()` provides DB-generated IDs.
- **Pattern consistency:** Matches `remove_item_from_inventory` (line 176) which also uses single commit at end.
- **Cross-service impact:** None. No API contract changes. No other service calls this endpoint.
- **Security:** No new vectors. Input validation unchanged.
- **Code standards:** Sync SQLAlchemy (correct for inventory-service), Pydantic <2.0, no hardcoded secrets.

#### Test Review
- 12 tests total: 10 original + 2 new edge cases.
- `test_stacking_fills_existing_slot` — the primary regression test — PASS.
- `test_stacking_fills_multiple_partial_slots` and `test_stacking_fills_multiple_slots_and_overflows` — new edge case tests covering multi-slot scenarios — PASS.
- All tests verify DB persistence (query + refresh after API call).

#### Automated Check Results
- [x] `npx tsc --noEmit` — N/A (no frontend changes)
- [x] `npm run build` — N/A (no frontend changes)
- [x] `py_compile` — PASS (main.py + test file)
- [x] `pytest` — PASS (12/12 tests passed)
- [x] `docker-compose config` — PASS
- [x] Live verification (curl) — PASS

#### Live Verification Results
- Endpoint tested: `POST /inventory/1/items` with `{"item_id": 1, "quantity": 3}`
- Pre-condition: character 1 had item_id=1 with quantity=1 (max_stack=20)
- API response: returned slot with quantity=4 (correct)
- Persistence check: `GET /inventory/1/items` confirmed quantity=4 in DB (correct)
- Cleanup: removed 3 items to restore original state
- Result: **PASS** — stacking persists correctly

#### Issue #16 in ISSUES.md
Bug #16 ("add_item_to_inventory не коммитит обновление существующих слотов") is directly fixed by this feature. Marked for removal.

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-16 14:10 — PM: фича создана, запускаю анализ кодовой базы
[LOG] 2026-03-16 14:15 — Analyst: анализ завершён, затронут 1 сервис (inventory-service). Баг подтверждён: db.commit() вызывается только при создании новых слотов (Phase 2), но не при обновлении существующих (Phase 1). Тест test_stacking_fills_existing_slot покрывает этот сценарий и должен падать. Кросс-сервисного влияния нет.
[LOG] 2026-03-16 14:25 — Architect: спроектировано 3 задачи. Фикс простой: один db.commit() после обоих циклов + db.refresh() для всех возвращаемых объектов. Без изменений API/БД/кросс-сервисных контрактов.
[LOG] 2026-03-16 14:35 — Backend Dev: задача #1 завершена. Убран db.commit()/db.refresh() из цикла Phase 2, добавлен единый db.commit() после обоих циклов + db.refresh() для всех элементов inventory_items. py_compile пройден. Изменён 1 файл.
[LOG] 2026-03-16 14:50 — QA: все 10 существующих тестов проходят (12/12 с новыми). test_stacking_fills_existing_slot — PASS (ранее падал). Добавлены 2 edge-case теста: стекинг в несколько частичных слотов и стекинг с переполнением нескольких слотов. py_compile пройден.
[LOG] 2026-03-16 15:10 — Reviewer: начал проверку. Код, тесты, автоматические проверки, живая верификация.
[LOG] 2026-03-16 15:25 — Reviewer: проверка завершена, результат PASS. py_compile PASS, pytest 12/12 PASS, docker-compose config PASS, curl live test PASS. Баг #16 исправлен, удалён из ISSUES.md.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Исправлен баг стекинга предметов: `db.commit()` вынесен после обоих циклов (обновление существующих слотов + создание новых), добавлен `db.refresh()` для всех элементов
- Операция стала атомарной — все изменения сохраняются одним коммитом
- Все 12 тестов проходят (включая ранее падавший `test_stacking_fills_existing_slot`)
- Живая верификация подтвердила: количество предметов корректно увеличивается и сохраняется в БД

### Что изменилось от первоначального плана
- Ничего — план выполнен полностью

### Оставшиеся риски / follow-up задачи
- Нет — баг полностью исправлен, issue #16 удалён из ISSUES.md
