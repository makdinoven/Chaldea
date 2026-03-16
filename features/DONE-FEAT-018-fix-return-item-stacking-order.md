# FEAT-018: Баг — возврат предмета добавляется к стаку с наименьшим количеством

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-16 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-018-fix-return-item-stacking-order.md` → `DONE-FEAT-018-fix-return-item-stacking-order.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
При снятии предмета из быстрого слота (или экипировки) и возврате в инвентарь, предмет добавляется к стаку с наименьшим количеством. Правильное поведение — добавлять к стаку с наибольшим количеством, стремясь заполнить его до максимума. Это логичнее для игрока и помогает консолидировать инвентарь.

### Бизнес-правила
- При возврате предмета в инвентарь — заполнять стак с наибольшим количеством до max_stack_size
- Если самый полный стак заполнен — переходить к следующему по убыванию
- Если все стаки полные — создать новый слот

### UX / Пользовательский сценарий
1. У персонажа два стака зелий: 5 штук и 18 штук (макс стак 20)
2. Игрок снимает зелье из быстрого слота
3. Ожидание: зелье добавляется к стаку с 18 → становится 19
4. Реальность: зелье добавляется к стаку с 5 → становится 6

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| inventory-service | bug fix (sort order) | `services/inventory-service/app/crud.py` |

### Bug Location

**`return_item_to_inventory()`** in `crud.py` line 160:
```python
.order_by(models.CharacterInventory.quantity.asc()).first()
```
This picks the slot with the **lowest** quantity. It should use `.desc()` to pick the **highest** quantity slot first, filling stacks toward `max_stack_size`.

### Callers of `return_item_to_inventory()`
- `main.py` → `unequip_item()` endpoint (`POST /{character_id}/unequip`) — line 335
- `main.py` → `equip_item()` endpoint (`POST /{character_id}/equip`) — line 252 (when replacing an equipped item)
- `crud.py` → `recalc_fast_slots()` — line 322 (when disabling a fast slot that has an item)

### Comparison with `add_item_to_inventory` endpoint

`POST /{character_id}/items` in `main.py` lines 112-116 queries existing slots with **no ORDER BY** — it iterates all non-full slots and fills them. Since it processes all slots anyway (not just `.first()`), the ordering issue does not affect correctness there, though adding DESC ordering would make behavior more predictable.

### Existing Patterns
- inventory-service: sync SQLAlchemy, Pydantic <2.0, Alembic present

### Cross-Service Dependencies
- No API contract changes — this is an internal sorting fix
- `equip_item` and `unequip_item` call `character-attributes-service` for modifiers, but those calls are unaffected

### DB Changes
- None required — pure logic fix

### The Fix
Change `.asc()` to `.desc()` on line 160 of `crud.py`:
```python
.order_by(models.CharacterInventory.quantity.desc()).first()
```

### Risks
- Risk: none — minimal change, single line, no API/schema changes

---

## 3. Architecture Decision (filled by Architect — in English)

One-line fix: change `.order_by(quantity.asc())` to `.order_by(quantity.desc())` in `return_item_to_inventory()` so the most-filled stack is chosen first. No API, schema, or migration changes needed.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Agent | Task | Status |
|---|-------|------|--------|
| 1 | Backend Dev | Fix sort order in `return_item_to_inventory()`: `.asc()` → `.desc()` | DONE |
| 2 | QA Test | Write test for `return_item_to_inventory()` stacking order | DONE |
| 3 | Reviewer | Final review and live verification | DONE |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-16
**Result:** PASS

#### Code Review
- Fix is correct: `.order_by(models.CharacterInventory.quantity.desc()).first()` selects the highest-quantity partial stack first
- Single-line change, no API/schema/migration impact
- No cross-service contract changes
- No security concerns (internal sorting logic only)
- Tests are well-structured, cover all edge cases: highest stack, full stack fallback, no stacks, all full, non-stackable, three partial stacks

#### Automated Check Results
- [x] `npx tsc --noEmit` — N/A (no frontend changes)
- [x] `npm run build` — N/A (no frontend changes)
- [x] `py_compile` — PASS (crud.py, test_return_item_stacking.py)
- [x] `pytest` — PASS (29/29 sync tests pass; 12 pre-existing failures in test_rabbitmq_consumer.py due to missing pytest-asyncio — unrelated to this feature)
- [x] `docker-compose config` — PASS
- [x] Live verification — PASS

#### Live Verification Results
- Endpoint tested: `POST /inventory/1/equip`, `POST /inventory/1/unequip`, `GET /inventory/1/items`
- Console errors: NONE
- Feature workflow: PASS
  - Before: character 1 had two stacks of item_id=1: qty=16 and qty=10
  - Equipped consumable (qty=16 became 15, qty=10 stayed)
  - Unequipped from fast_slot_1: item returned to the highest-quantity stack (inv_id=2, qty=15 -> 16)
  - Lower stack (inv_id=5, qty=10) was untouched — correct behavior confirmed
- API responses: all 200 OK

#### Pre-existing issues noted
- `test_rabbitmq_consumer.py`: 12 async tests fail due to missing `pytest-asyncio` package (pre-existing, not related to this feature)

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-16 20:00 — PM: фича создана, запускаю анализ
[LOG] 2026-03-16 20:05 — Analyst: анализ завершён. Баг в crud.py:160 — order_by(quantity.asc()) вместо desc(). Затронут 1 сервис, фикс в 1 строку.
[LOG] 2026-03-16 20:10 — Backend Dev: задача #1 завершена, изменён 1 файл (crud.py:160 — asc→desc). py_compile пройден.
[LOG] 2026-03-16 20:20 — QA: тесты написаны для return_item_to_inventory(), 6 тестов в test_return_item_stacking.py. py_compile пройден.
[LOG] 2026-03-16 20:30 — Reviewer: начал проверку. Код корректен, py_compile пройден, 29/29 тестов пройдены, docker-compose валиден.
[LOG] 2026-03-16 20:35 — Reviewer: живая верификация пройдена — unequip возвращает предмет в стак с наибольшим количеством. Результат: PASS.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Исправлен порядок сортировки в `return_item_to_inventory()`: `.asc()` → `.desc()`
- Теперь предметы возвращаются в стак с наибольшим количеством (заполняют до максимума)
- Написано 6 тестов для функции

### Оставшиеся риски / follow-up задачи
- Нет
