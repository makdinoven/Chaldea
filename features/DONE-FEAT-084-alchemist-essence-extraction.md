# FEAT-084: Алхимик — экстракция эссенций

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-03-26 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-084-alchemist-essence-extraction.md` → `DONE-FEAT-084-alchemist-essence-extraction.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Алхимик может извлекать магические эссенции из кристаллов. Эссенции — универсальные ингредиенты, используемые другими профессиями для крафта (например, зачарователем для создания рун). Это создаёт экономическую связь между профессиями.

### Механика извлечения
- Алхимик выбирает кристалл из своего инвентаря
- Применяет извлечение — шанс успеха 75%
- При успехе: кристалл расходуется, в инвентарь добавляется эссенция соответствующего типа
- При неудаче: кристалл расходуется, эссенция не создаётся
- Не требует дополнительных материалов или инструментов

### Типы кристаллов и эссенций (7 пар)

| Кристалл (вход) | Эссенция (выход) | Стихия |
|-----------------|------------------|--------|
| Кристалл огня | Эссенция огня | Огонь |
| Кристалл воды | Эссенция воды | Вода |
| Кристалл воздуха | Эссенция воздуха | Воздух |
| Кристалл молнии | Эссенция молнии | Молния |
| Кристалл льда | Эссенция льда | Лёд |
| Кристалл света | Эссенция света | Свет |
| Кристалл тьмы | Эссенция тьмы | Тьма |

- Все 14 предметов — item_type = "resource", стакаются
- Кристаллы — дроп с мобов (назначаются в лут через админку)
- Эссенции — ингредиенты для крафта других профессий

### Связь кристалл → эссенция
Нужен механизм привязки: какой кристалл в какую эссенцию превращается. Варианты:
- Новая таблица `essence_recipes` (crystal_item_id → essence_item_id)
- Или поле на предмете (`essence_result_item_id` на кристалле)
- Или админка управляет парами

### Бизнес-правила
- Только алхимик может извлекать эссенции (проверка профессии, slug = "alchemist")
- 1 кристалл → 1 эссенция (при успехе)
- Шанс извлечения: 75%
- При неудаче кристалл теряется, эссенция не создаётся
- Эссенции торгуются как обычные предметы (обмен, в будущем аукцион)
- Извлечение даёт XP профессии алхимику

### UX / Пользовательский сценарий
1. Алхимик открывает таб "Крафт"
2. Видит раздел "Экстракция эссенций" (отдельная секция, как "Заточка" у кузнеца)
3. Видит список кристаллов из своего инвентаря с количеством
4. Выбирает кристалл
5. Видит какая эссенция получится и шанс (75%)
6. Нажимает "Извлечь"
7. Результат: успех (эссенция получена!) или неудача (кристалл потерян)

### Edge Cases
- Что если нет кристаллов в инвентаре? → Показать "Нет кристаллов для извлечения"
- Что если предмет не является кристаллом? → Ошибка валидации
- Что если алхимик в бою? → Ошибка "Нельзя извлекать в бою"

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Existing patterns

- **Sharpening (FEAT-083)** provides the exact pattern: profession-gated mechanic with dedicated endpoints under `/crafting/{character_id}/`, XP awarding with rank-up check, inventory item consumption.
- **Items model** already has `whetstone_level` as a similar "marker field" on items — `essence_result_item_id` follows the same approach.
- **Profession check**: `crud.get_character_profession()` returns `CharacterProfession` with eagerly loaded `profession.ranks`. Slug comparison (`cp.profession.slug == "alchemist"`) is the standard gate.
- **XP awarding + rank-up**: sharpen endpoint awards 10 XP per attempt, checks rank thresholds, calls `auto_learn_recipes_for_rank()` on rank-up.
- **Inventory management**: decrement quantity, delete row if 0; add item by finding existing stack or creating new row.

### Files affected

| File | Change |
|------|--------|
| `models.py` | Add `essence_result_item_id` column + relationship |
| `schemas.py` | Add `ExtractEssenceRequest`, `ExtractEssenceResult`, `CrystalInfo`, `ExtractInfoResponse` |
| `main.py` | Add `GET /extract-info`, `POST /extract-essence` endpoints |
| `alembic/versions/008_add_essence_extraction.py` | Migration: add column + seed 14 items |

### Cross-service impact

- **None.** This feature is self-contained within inventory-service. No other services call or depend on essence extraction. The new `essence_result_item_id` column on `items` is nullable and backward-compatible — photo-service mirror models won't break (they don't reference this column).

---

## 3. Architecture Decision (filled by Architect — in English)

### Approach: marker field on Items table

Add `essence_result_item_id` (Integer, FK to `items.id`, nullable) to the `items` table. If set, the item is a "crystal" that can be extracted into the referenced essence item. No new tables needed — simplest possible approach.

### DB changes

- **Migration 008**: add `essence_result_item_id` column with FK constraint, seed 14 items (7 crystals + 7 essences).

### API contract

**GET `/inventory/crafting/{character_id}/extract-info`**
- Auth: JWT required, ownership check
- Returns: `{ "crystals": [{ inventory_item_id, item_id, name, image, quantity, essence_name, essence_image, success_chance }] }`

**POST `/inventory/crafting/{character_id}/extract-essence`**
- Auth: JWT required, ownership check, battle lock
- Body: `{ "crystal_item_id": int }` (character_inventory.id)
- Validation: alchemist profession, crystal exists, has essence_result_item_id
- Logic: consume 1 crystal, roll 75%, if success add 1 essence, award 10 XP
- Response: `{ success, crystal_name, essence_name, crystal_consumed, xp_earned, new_total_xp, rank_up, new_rank_name }`

### Seed data

7 crystal items (`Кристалл огня/воды/воздуха/молнии/льда/света/тьмы`) — resource, common, max_stack 99.
7 essence items (`Эссенция огня/воды/воздуха/молнии/льда/света/тьмы`) — resource, common, max_stack 99.
Each crystal's `essence_result_item_id` points to its corresponding essence.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### TASK-1: Backend — Migration + Model [DONE]
- Add `essence_result_item_id` to `Items` model
- Create migration `008_add_essence_extraction.py` (column + seed 14 items)
- Files: `models.py`, `alembic/versions/008_add_essence_extraction.py`

### TASK-2: Backend — Schemas [DONE]
- Add `ExtractEssenceRequest`, `ExtractEssenceResult`, `CrystalInfo`, `ExtractInfoResponse`
- Add `essence_result_item_id` to `ItemBase`
- File: `schemas.py`

### TASK-3: Backend — Endpoints [DONE]
- `GET /crafting/{character_id}/extract-info` — list crystals
- `POST /crafting/{character_id}/extract-essence` — perform extraction
- Auth, ownership, battle lock, profession check, XP award, rank-up
- File: `main.py`

### TASK-4: Frontend — Essence extraction UI [DONE]
- Add EssenceExtractionSection component (follow SharpeningSection pattern)
- Show for alchemist profession in Crafting tab
- Crystal list, extract button, result animation

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-26

**Verdict: PASS**

#### Backend

**models.py** — `essence_result_item_id` column and self-referential relationship are correct. FK with `ondelete='SET NULL'` is proper. No regressions to existing fields or relationships.

**schemas.py** — Four new schemas added (`ExtractEssenceRequest`, `ExtractEssenceResult`, `CrystalInfo`, `ExtractInfoResponse`). All use Pydantic v1 style (no `model_config`). `essence_result_item_id` added to `ItemBase` as `Optional[int] = None` — backward compatible. Types match the backend response exactly.

**main.py (endpoints)** —
- `GET /extract-info`: Auth + ownership check present. Correctly filters inventory items by `essence_result_item_id IS NOT NULL`. Returns hardcoded `success_chance: 75`.
- `POST /extract-essence`: Full validation chain — ownership, battle lock, profession check (slug == "alchemist"), crystal existence in inventory, crystal validity (has `essence_result_item_id`). Uses `with_for_update()` for row-level locking — good concurrency safety. Crystal consumption logic correct: decrement, delete row if 0. Success roll: `random.random() < 0.75` — 75% chance, correct. On success: adds/stacks essence in inventory. XP always awarded (10 XP) regardless of success/failure. Rank-up loop handles multi-rank jumps and calls `auto_learn_recipes_for_rank`. Transaction commit at end, rollback on exception. Error messages in Russian.

**Migration 008** — Adds column, creates FK constraint. Seeds 7 essences first, then 7 crystals with subquery references to link them. Downgrade removes crystals first (FK order correct), then essences, then drops column. Clean and idempotent.

**Tests** — 17 tests across 13 classes covering: happy path (success), failure path (crystal consumed, no essence), non-alchemist rejection, no-profession rejection, non-crystal rejection, invalid inventory ID, boundary tests (0.74 success, 0.75 failure, 0.76 failure), XP on success + failure, rank-up, extract-info returns crystals, extract-info empty, auth (401 no token, 403 wrong character), battle lock. Coverage is thorough and boundary conditions are well tested.

**py_compile**: All 4 Python files pass (`models.py`, `schemas.py`, `migration 008`, `test_essence_extraction.py`).

#### Frontend

**types/professions.ts** — `CrystalInfo`, `ExtractInfoResponse`, `ExtractEssenceRequest`, `ExtractEssenceResult` interfaces match backend schemas exactly. All fields typed correctly. TypeScript file (.ts) as required.

**api/professions.ts** — `fetchExtractInfo` and `extractEssence` functions use correct paths (`/crafting/{characterId}/extract-info`, `/crafting/{characterId}/extract-essence`). Payload structure matches backend expectation (`{ crystal_item_id }`). Auth token interceptor already in place from existing client.

**craftingSlice.ts** — New state fields (`extractInfo`, `extractInfoLoading`, `extractLoading`, `extractError`), thunks (`fetchExtractInfo`, `extractEssence`), reducers (`clearExtractInfo`), and selectors all properly wired. Error messages in Russian. No `React.FC` usage.

**EssenceExtractionSection.tsx** —
- TypeScript (.tsx), no `React.FC`, interface-based props — compliant.
- Tailwind-only styling, no CSS/SCSS imports — compliant.
- Uses design system classes: `gold-text`, `btn-blue`, `rounded-card`.
- Responsive: `grid-cols-1 sm:grid-cols-2 md:grid-cols-3`, sized images with `sm:` breakpoints.
- Error handling: uses `toast.error()` for errors and failures, `toast.success()` for successes and rank-ups.
- Empty state handled: "Нет кристаллов для извлечения".
- Loading spinner shown during data fetch.
- After extraction: refreshes extract-info and character profession data.
- All user-facing strings in Russian.

**CraftTab.tsx** — Conditionally renders `EssenceExtractionSection` for `slug === 'alchemist'`, matching the `SharpeningSection` pattern for `slug === 'blacksmith'`. Clean integration with no regressions.

#### Cross-service impact
None. The `essence_result_item_id` column is nullable and only used by inventory-service. No other services reference this column. photo-service mirror models are unaffected.

#### Summary
Clean, minimal implementation following the established sharpening pattern. All validation checks present, 75% chance logic correct, crystal consumed on both success and failure, XP always awarded. Frontend follows all mandatory rules (TypeScript, Tailwind, no React.FC, responsive, Russian strings, error display). No regressions detected.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-26 — PM: фича создана, запускаю анализ + проектирование
[LOG] 2026-03-26 — Backend Dev: анализ завершён, паттерн FEAT-083 (sharpening) полностью подходит
[LOG] 2026-03-26 — Backend Dev: архитектура спроектирована — marker field на items, 2 эндпоинта, миграция с сидом
[LOG] 2026-03-26 — Backend Dev: реализация завершена — models.py, schemas.py, main.py, миграция 008
[LOG] 2026-03-26 — Backend Dev: py_compile пройден для всех файлов, статус IN_PROGRESS
[LOG] 2026-03-26 — QA: написаны тесты для FEAT-084 (essence extraction), 17 тестов в 13 классах, py_compile пройден
[LOG] 2026-03-26 — Frontend Dev: начал задачу #4 — frontend UI для экстракции эссенций
[LOG] 2026-03-26 — Frontend Dev: задача #4 завершена — типы, API, Redux slice, EssenceExtractionSection компонент, интеграция в CraftTab
[LOG] 2026-03-26 — Reviewer: ревью пройдено — PASS. Backend: эндпоинты, миграция, тесты (17) корректны. Frontend: TypeScript, Tailwind, адаптивность, ошибки отображаются. Статус → REVIEW
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
