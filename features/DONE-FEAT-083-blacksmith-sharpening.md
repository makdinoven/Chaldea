# FEAT-083: Кузнец — заточка снаряжения

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-26 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-083-blacksmith-sharpening.md` → `DONE-FEAT-083-blacksmith-sharpening.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Кузнец может затачивать оружие и броню из своего инвентаря, повышая характеристики предмета. Заточка работает по системе поинтов — кузнец выбирает конкретный стат и точит именно его. Заточка требует расходный предмет — точильный камень, который бывает разного качества и определяет шанс успеха.

### Система поинтов заточки
- Каждый предмет имеет **бюджет 15 поинтов** заточки
- Кузнец выбирает **конкретный стат** предмета и точит именно его
- **Существующий стат** (уже есть на предмете): 1 поинт за +1 / +0.1%
- **Новый стат** (которого нет на предмете): 2 поинта за +1 / +0.1%
- Максимум **+5 на один стат** (+0.5% для сопротивлений)
- 15 поинтов — суммарный бюджет на предмет, неважно как распределены

**Пример:** Меч с уроном 20 и силой 5.
- Кузнец точит урон +5 (5 поинтов) и силу +5 (5 поинтов) = 10 поинтов потрачено
- Осталось 5 поинтов. Кузнец добавляет ловкость (нового стата нет на предмете) — стоит 2 поинта за +1
- Ловкость +2 = 4 поинта, итого 14 из 15 потрачено, остался 1 поинт (на новый стат не хватает — нужно 2)

### Механика заточки
- Кузнец выбирает предмет из своего инвентаря (только оружие и броня)
- Выбирает конкретный стат для заточки
- Выбирает точильный камень из инвентаря
- Применяет заточку — шанс успеха зависит от качества камня
- При успехе: выбранный стат +1/+0.1%, поинт(ы) тратятся из бюджета
- При неудаче: камень расходуется, поинты НЕ тратятся, стат не меняется

### Повышение статов при заточке
**Основные характеристики (атрибуты и урон)** — повышаются на +1:
- Сила, Ловкость, Интеллект, Выносливость
- Мана, Энергия, Здоровье, Выносливость (stamina)
- Урон, Точность, Уклонение
- Харизма, Удача

**Сопротивления и крит** — повышаются на +0.1%:
- Все res_*_modifier поля (физ, режущ, дробящ, колющ, маг, огн, вод, возд, земл, свят, тёмн)
- Крит шанс, Крит урон

### Точильные камни (новые предметы)
| Качество | Шанс успеха | item_rarity |
|----------|-------------|-------------|
| Обычный точильный камень | 25% | common |
| Редкий точильный камень | 50% | rare |
| Легендарный точильный камень | 75% | legendary |

- Это полноценные предметы в таблице items (item_type = "resource")
- Могут назначаться мобам в лут, торговцам, крафтиться и т.д.
- Расходуются при каждой попытке заточки (и при успехе, и при неудаче)

### Бизнес-правила
- Только кузнец может затачивать (проверка профессии)
- Точить можно только оружие и броню (item_type: head, body, cloak, belt, main_weapon, additional_weapons, shield)
- Бюджет заточки: 15 поинтов на предмет
- Максимум на один стат: +5 (или +0.5% для сопротивлений)
- Существующий стат = 1 поинт за улучшение, новый стат = 2 поинта
- Камень расходуется при каждой попытке (и при успехе, и при неудаче)
- При неудаче поинты не тратятся, стат не меняется
- Предмет показывает суммарное количество потраченных поинтов (например, "Железный меч [7/15]")

### UX / Пользовательский сценарий
1. Кузнец открывает таб "Крафт"
2. Видит раздел "Заточка" (помимо рецептов)
3. Выбирает предмет из инвентаря (показываются только оружие/броня)
4. Видит текущие статы предмета, потраченные/оставшиеся поинты, бонусы заточки
5. Выбирает конкретный стат для заточки (из списка доступных)
6. Выбирает точильный камень из инвентаря, видит шанс успеха
7. Нажимает "Заточить"
8. Результат: успех (стат увеличен, поинт потрачен) или неудача (камень потрачен, стат не изменился)

### Edge Cases
- Что если поинты закончились (15/15)? → Кнопка заточки неактивна, "Бюджет заточки исчерпан"
- Что если конкретный стат уже +5? → Этот стат недоступен для заточки
- Что если нет точильных камней? → Показать "Нет точильных камней"
- Что если предмет экипирован? → Можно точить экипированный предмет (не нужно снимать)
- Что если предмет не в инвентаре кузнеца? → Ошибка, нужно сначала получить предмет через обмен
- Что если хочет добавить новый стат, но осталось только 1 поинт? → Недоступно (нужно 2 поинта для нового стата)

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1 Item Model Architecture (CRITICAL FINDING)

**File:** `services/inventory-service/app/models.py`

The `items` table is a **shared catalog** of item definitions — NOT per-character instances. Multiple characters can own the same `item_id` via `character_inventory` (which stores `character_id`, `item_id`, `quantity`). The `items.name` column has `unique=True`.

**Implication:** We CANNOT add `enhancement_level` to the `items` table or modify item modifier fields directly, because that would change the item for ALL owners simultaneously.

**Solution:** Add `enhancement_level` to the `character_inventory` table (per-instance data). Sharpening bonuses are calculated dynamically at read time: `effective_modifier = base_modifier + (enhancement_bonus * enhancement_level)`.

### 2.2 Item Stat Fields

**Main stat modifiers** (Integer, default 0) on `Items` model:
- `strength_modifier`, `agility_modifier`, `intelligence_modifier`, `endurance_modifier`
- `health_modifier`, `energy_modifier`, `mana_modifier`, `stamina_modifier`
- `charisma_modifier`, `luck_modifier`
- `damage_modifier`, `dodge_modifier`

**Resistance modifiers** (Float, default 0.0):
- `res_physical_modifier`, `res_catting_modifier`, `res_crushing_modifier`, `res_piercing_modifier`
- `res_magic_modifier`, `res_fire_modifier`, `res_ice_modifier`, `res_watering_modifier`
- `res_electricity_modifier`, `res_wind_modifier`, `res_sainting_modifier`, `res_damning_modifier`
- `res_effects_modifier`

**Combat float modifiers** (Float, default 0.0):
- `critical_hit_chance_modifier`, `critical_damage_modifier`

**Recovery fields** (Integer, default 0):
- `health_recovery`, `energy_recovery`, `mana_recovery`, `stamina_recovery`

**Vulnerability modifiers** (Float, default 0.0):
- `vul_physical_modifier`, `vul_catting_modifier`, `vul_crushing_modifier`, etc.

### 2.3 Sharpenable Item Types

From the feature brief, these `item_type` values are sharpenable:
`head`, `body`, `cloak`, `belt`, `main_weapon`, `additional_weapons`, `shield`

NOT sharpenable: `ring`, `necklace`, `bracelet`, `consumable`, `resource`, `scroll`, `misc`, `blueprint`, `recipe`

### 2.4 Equipment / Apply Modifiers Flow

**Equip flow** (`services/inventory-service/app/main.py:287`):
1. Verify item in inventory
2. If slot occupied, unequip old item (return to inventory + send negative modifiers)
3. Decrement inventory quantity, set slot.item_id
4. Call `apply_modifiers_in_attributes_service(character_id, plus_mods)` via HTTP POST to character-attributes-service
5. Commit

**`build_modifiers_dict()`** (`services/inventory-service/app/crud.py:195`):
Iterates all `*_modifier` fields on the Items object, building a dict like `{"strength": 5, "res_fire": 0.3}`. Maps field names: `strength_modifier` -> key `"strength"`, `res_fire_modifier` -> key `"res_fire"`.

**`apply_modifiers` endpoint** (`services/character-attributes-service/app/main.py:503`):
POST `/{character_id}/apply_modifiers` accepts a dict of deltas. For `health/mana/energy/stamina` it recalculates `max_*` and `current_*`. For everything else it simply adds the delta to the current value.

**Key insight for sharpening:** When an equipped item is sharpened, we need to apply the DELTA (the incremental stat gain from +N to +N+1) to character attributes via `apply_modifiers`. This is a simple incremental call — no need to unequip/re-equip.

### 2.5 Profession Check Pattern

**`get_character_profession()`** (`services/inventory-service/app/crud.py:828`):
Returns `CharacterProfession` with eagerly loaded `profession` and `ranks`. The `profession.slug` field identifies the profession type (e.g., `"blacksmith"`).

**Craft endpoint pattern** (`services/inventory-service/app/main.py:1261`):
1. `verify_character_ownership()` — auth check
2. `check_not_in_battle()` — battle lock
3. `crud.get_character_profession()` — get profession
4. Validate profession matches, rank sufficient
5. Execute in transaction, commit/rollback

### 2.6 CraftTab Frontend

**File:** `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/CraftTab.tsx`

Structure: CraftTab -> ProfessionSelect (if no profession) OR ProfessionInfo + RecipeList (if has profession).

Uses Redux slice `craftingSlice.ts` with thunks. API calls go through `api/professions.ts` client (baseURL: `/inventory`).

The sharpening UI section should be added alongside RecipeList when the character is a blacksmith. It's a separate concern from recipes.

### 2.7 EquipmentSlot Model

**File:** `services/inventory-service/app/models.py:124`

`EquipmentSlot` has `character_id`, `slot_type`, `item_id`. When checking if an item is equipped, we query `EquipmentSlot.character_id == X AND EquipmentSlot.item_id == Y`.

### 2.8 Whetstone Items

Whetstones will be regular items with `item_type = "resource"`, `max_stack_size > 1`. Distinguished by a naming convention or a new flag. Since we need to identify them programmatically, we should add a `subtype` field or use a naming convention. Simplest approach: use `item_type = "resource"` and identify whetstones by specific item IDs or a dedicated flag/column.

Given the architecture, using a dedicated boolean `is_whetstone` on the Items model (or a new `item_subtype` column) is cleanest. However, the simplest approach consistent with current patterns is to identify whetstones by convention and pass `whetstone_item_id` from the frontend. The backend validates the item exists, is a resource, and is in the character's inventory.

**Decision:** Add a `whetstone_level` column (Integer, nullable, default NULL) to `items`. Values: 1=common (25%), 2=rare (50%), 3=legendary (75%). NULL means it's not a whetstone. This is cleaner than name-based matching and allows admin to create whetstones via the existing item admin UI.

### 2.9 Alembic State

Inventory-service has Alembic configured with migrations 001-006. Next migration: `007_add_sharpening_system.py`. Version table: `alembic_version_inventory`.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Core Design: Per-Instance Enhancement on `character_inventory`

Since `items` is a shared catalog, enhancement MUST be per-instance. Add `enhancement_level` (Integer, default 0) to the `character_inventory` table. This field tracks how many times a specific inventory entry has been sharpened.

**Why not a separate `item_enhancements` table?** Unnecessary complexity. Enhancement is a simple integer counter per inventory row. The stat bonuses are computed deterministically from the base item stats and enhancement level.

### 3.2 Database Changes

**Migration `007_add_sharpening_system.py`:**

1. Add `enhancement_level` (Integer, default 0, server_default="0") to `character_inventory`
2. Add `whetstone_level` (Integer, nullable, default NULL) to `items` — identifies whetstones and their quality tier

Also add `enhancement_level` to `equipment_slots` table — when an item is equipped, its enhancement level must be preserved. Currently equip moves item from inventory to slot; the enhancement level must travel with it.

### 3.3 Stat Increase Logic

Per enhancement level, for each non-zero modifier on the base item:

| Modifier Category | Increase per Level | Fields |
|---|---|---|
| **Main stats** (Integer modifiers) | +1 | `strength_modifier`, `agility_modifier`, `intelligence_modifier`, `endurance_modifier`, `health_modifier`, `energy_modifier`, `mana_modifier`, `stamina_modifier`, `charisma_modifier`, `luck_modifier`, `damage_modifier`, `dodge_modifier` |
| **Resistances** (Float modifiers) | +0.1 | All `res_*_modifier` fields |
| **Combat floats** | +0.1 | `critical_hit_chance_modifier`, `critical_damage_modifier` |
| **Vulnerabilities** | NOT affected | All `vul_*_modifier` fields — sharpening does not change vulnerabilities |
| **Recovery** | NOT affected | `health_recovery`, `energy_recovery`, `mana_recovery`, `stamina_recovery` |

**Computation formula:**
```
effective_modifier = base_modifier + (enhancement_level * increment)
```
where `increment` is +1 for integer stats, +0.1 for float stats. Only applied when `base_modifier != 0`.

**Implementation:** A helper function `compute_enhancement_bonuses(item: Items, enhancement_level: int) -> dict` returns the delta modifiers dict (in the same format as `build_modifiers_dict` output). This dict can be passed directly to `apply_modifiers`.

### 3.4 Sharpening Endpoint

```
POST /inventory/crafting/{character_id}/sharpen
Body: { "inventory_item_id": int, "whetstone_item_id": int }
```

**Note:** We use `inventory_item_id` (the `character_inventory.id` PK) instead of `item_id` because a character may have multiple stacks of the same item with different enhancement levels.

**Validation steps:**
1. `verify_character_ownership()` — auth
2. `check_not_in_battle()` — battle lock
3. Get character profession, verify `profession.slug == "blacksmith"`
4. Get inventory entry by `inventory_item_id`, verify belongs to `character_id`
5. Get base item, verify `item_type` is sharpenable
6. Verify `enhancement_level < 5`
7. Get whetstone from inventory (by `whetstone_item_id`), verify it has `whetstone_level` set
8. Determine success chance from `whetstone_level`: 1=25%, 2=50%, 3=75%
9. Consume whetstone (decrement quantity or delete row)
10. Roll random: on success, increment `enhancement_level`
11. If item is currently equipped, apply the incremental stat delta to character attributes via `apply_modifiers`
12. Award crafting XP (10-30 depending on enhancement level)
13. Commit and return result

**Response schema `SharpenResult`:**
```json
{
  "success": true/false,
  "item_name": "Железный меч",
  "new_enhancement_level": 3,
  "old_enhancement_level": 2,
  "whetstone_consumed": true,
  "stat_changes": {"strength": 1, "damage": 1, "res_physical": 0.1},
  "xp_earned": 15,
  "new_total_xp": 200,
  "rank_up": false,
  "new_rank_name": null
}
```

### 3.5 Equipped Item Handling

When sharpening an equipped item:
1. Check `equipment_slots` for a row where `character_id = X AND item_id = Y`
2. If found, the item is equipped — after incrementing enhancement_level, compute the delta for ONE level and call `apply_modifiers_in_attributes_service()` with the positive delta
3. Also update `enhancement_level` on the `equipment_slots` row

When equipping/unequipping enhanced items, `build_modifiers_dict` must account for enhancement. Modify the function to accept an optional `enhancement_level` parameter and add the enhancement bonuses to the base modifiers.

### 3.6 Display: "+N" in Item Name

The "+N" suffix should be computed on the frontend (display only), NOT stored in the DB name field. The `enhancement_level` field is returned in inventory/equipment API responses, and the frontend prepends it: `${item.name} +${enhancement_level}`.

### 3.7 Whetstone Items

Three whetstone items to be seeded in the migration:

| Name | item_type | item_rarity | whetstone_level | max_stack_size | Description |
|---|---|---|---|---|---|
| Обычный точильный камень | resource | common | 1 | 99 | Шанс заточки: 25% |
| Редкий точильный камень | resource | rare | 2 | 99 | Шанс заточки: 50% |
| Легендарный точильный камень | resource | legendary | 3 | 99 | Шанс заточки: 75% |

### 3.8 Frontend Architecture

**New components:**
- `SharpeningSection.tsx` — main sharpening UI, displayed in CraftTab for blacksmiths
- `SharpeningModal.tsx` — confirmation modal with item details, whetstone selector, chance display

**Redux additions to `craftingSlice.ts`:**
- New state: `sharpenLoading`, `sharpenError`
- New thunk: `sharpenItem`

**API additions to `api/professions.ts`:**
- `sharpenItem(characterId, payload)` — POST to `/crafting/{character_id}/sharpen`

**Type additions to `types/professions.ts`:**
- `SharpenRequest`, `SharpenResult`

**CraftTab changes:**
- When `characterProfession.profession.slug === 'blacksmith'`, render `<SharpeningSection>` between ProfessionInfo and RecipeList
- SharpeningSection fetches inventory items (weapons/armor) and whetstones from existing inventory API

### 3.9 Inventory API Response Changes

The `enhancement_level` field must be included in all inventory/equipment API responses. Update:
- `ItemResponse` schema — add `enhancement_level: int = 0`
- `EquipmentSlot` schema — add `enhancement_level: int = 0` (from the slot row)
- `CharacterInventory` schema — add `enhancement_level: int = 0`

The equip/unequip endpoints must preserve `enhancement_level` when moving items between inventory and equipment slots.

### 3.10 Cross-Service Impact

- **character-attributes-service**: No changes needed. The existing `apply_modifiers` endpoint handles incremental deltas, which is exactly what sharpening produces.
- **battle-service**: Reads equipment stats at battle start. Since stats are already applied to character attributes, no changes needed.
- **photo-service**: Has mirror models for `items` table — needs `whetstone_level` column added to its mirror model if it reads that column. Since photo-service only reads image/name fields, this is low risk.
- **frontend**: Inventory display components should show "+N" for enhanced items.

### 3.11 Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Enhancement lost on equip/unequip | Store `enhancement_level` on both `character_inventory` and `equipment_slots`; copy value during equip/unequip |
| Enhancement lost on trade | Trade system moves inventory rows — `enhancement_level` travels with the row |
| Modifier calculation drift | Compute bonuses deterministically from `enhancement_level` + base stats; never store computed values |
| photo-service mirror model mismatch | Add `whetstone_level` to photo-service mirror model in same migration |

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 4.1 — Backend: Database Migration (Backend Developer)
**Status:** DONE
**Service:** inventory-service
**Files:** `services/inventory-service/app/alembic/versions/007_add_sharpening_system.py`, `services/inventory-service/app/models.py`

1. Create Alembic migration `007_add_sharpening_system.py`:
   - Add `enhancement_level` (Integer, default 0, server_default="0") to `character_inventory`
   - Add `enhancement_level` (Integer, default 0, server_default="0") to `equipment_slots`
   - Add `whetstone_level` (Integer, nullable, default NULL) to `items`
   - Seed 3 whetstone items (Обычный точильный камень / Редкий / Легендарный) with `item_type="resource"`, appropriate `item_rarity`, `whetstone_level` = 1/2/3, `max_stack_size=99`
2. Update `models.py`:
   - Add `enhancement_level = Column(Integer, default=0, server_default="0")` to `CharacterInventory`
   - Add `enhancement_level = Column(Integer, default=0, server_default="0")` to `EquipmentSlot`
   - Add `whetstone_level = Column(Integer, nullable=True, default=None)` to `Items`
3. Update `schemas.py`:
   - Add `enhancement_level: int = 0` to `ItemResponse`, `CharacterInventory`, `EquipmentSlotBase`
   - Add `whetstone_level: Optional[int] = None` to `ItemBase`, `Item`
   - Add `SharpenRequest` schema: `inventory_item_id: int`, `whetstone_item_id: int`
   - Add `SharpenResult` schema (see 3.4)
4. Update photo-service mirror model if it mirrors `items` columns that include new fields.

**Depends on:** nothing
**Verify:** `python -m py_compile models.py schemas.py`; migration applies cleanly

### Task 4.2 — Backend: Sharpening Logic & Endpoint (Backend Developer)
**Status:** DONE
**Service:** inventory-service
**Files:** `services/inventory-service/app/crud.py`, `services/inventory-service/app/main.py`

1. In `crud.py`, add helper:
   ```python
   SHARPENABLE_TYPES = {'head', 'body', 'cloak', 'belt', 'main_weapon', 'additional_weapons', 'shield'}

   MAIN_STAT_FIELDS = [
       'strength_modifier', 'agility_modifier', 'intelligence_modifier', 'endurance_modifier',
       'health_modifier', 'energy_modifier', 'mana_modifier', 'stamina_modifier',
       'charisma_modifier', 'luck_modifier', 'damage_modifier', 'dodge_modifier',
   ]

   RESISTANCE_FIELDS = [
       'res_effects_modifier', 'res_physical_modifier', 'res_catting_modifier',
       'res_crushing_modifier', 'res_piercing_modifier', 'res_magic_modifier',
       'res_fire_modifier', 'res_ice_modifier', 'res_watering_modifier',
       'res_electricity_modifier', 'res_wind_modifier', 'res_sainting_modifier',
       'res_damning_modifier', 'critical_hit_chance_modifier', 'critical_damage_modifier',
   ]

   def compute_enhancement_delta(item: models.Items) -> dict:
       """Compute the stat delta for ONE enhancement level (from +N to +N+1).
       Only includes stats where the base item has a non-zero modifier."""
       delta = {}
       for field in MAIN_STAT_FIELDS:
           base_val = getattr(item, field, 0) or 0
           if base_val != 0:
               key = field.replace('_modifier', '')
               delta[key] = 1  # +1 per level for integer stats
       for field in RESISTANCE_FIELDS:
           base_val = getattr(item, field, 0) or 0
           if base_val != 0:
               key = field.replace('_modifier', '')
               delta[key] = 0.1  # +0.1 per level for float stats
       return delta
   ```

2. Modify `build_modifiers_dict()` to accept optional `enhancement_level: int = 0` parameter. When > 0, add enhancement bonuses to the base modifiers:
   ```python
   def build_modifiers_dict(item_obj, negative=False, enhancement_level=0):
       # ... existing logic builds mods dict ...
       # After building base mods, add enhancement bonuses
       if enhancement_level > 0:
           for field in MAIN_STAT_FIELDS:
               base_val = getattr(item_obj, field, 0) or 0
               if base_val != 0:
                   key = field.replace('_modifier', '')
                   mods[key] = mods.get(key, 0) + enhancement_level * 1
           for field in RESISTANCE_FIELDS:
               base_val = getattr(item_obj, field, 0) or 0
               if base_val != 0:
                   key = field.replace('_modifier', '')
                   mods[key] = mods.get(key, 0) + enhancement_level * 0.1
       if negative:
           mods = {k: -v for k, v in mods.items()}
       return mods
   ```
   **IMPORTANT:** This changes the existing `build_modifiers_dict` signature. Update ALL callers in `main.py` (equip/unequip) to pass `enhancement_level` from the equipment slot or inventory row.

3. In `main.py`, add the sharpen endpoint:
   ```
   @router.post("/crafting/{character_id}/sharpen")
   async def sharpen_item(character_id, req: schemas.SharpenRequest, ...)
   ```
   Follow the validation steps from section 3.4. Use `random.random() < success_chance` for the roll. Award XP: `5 + (current_enhancement_level * 5)`.

4. Update equip endpoint to read `enhancement_level` from inventory row and write it to equipment slot.
5. Update unequip endpoint to read `enhancement_level` from equipment slot and write it back to inventory row.
6. Update `build_modifiers_dict` calls in equip/unequip to pass `enhancement_level`.

**Depends on:** Task 4.1
**Verify:** `python -m py_compile crud.py main.py`; manual test with curl

### Task 4.3 — Frontend: Sharpening UI (Frontend Developer)
**Status:** DONE
**Service:** frontend
**Files (new):**
- `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/SharpeningSection.tsx`
- `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/SharpeningModal.tsx`

**Files (modified):**
- `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/CraftTab.tsx`
- `services/frontend/app-chaldea/src/redux/slices/craftingSlice.ts`
- `services/frontend/app-chaldea/src/api/professions.ts`
- `services/frontend/app-chaldea/src/types/professions.ts`

1. **Types** (`types/professions.ts`):
   - Add `SharpenRequest { inventory_item_id: number; whetstone_item_id: number; }`
   - Add `SharpenResult { success: boolean; item_name: string; new_enhancement_level: number; old_enhancement_level: number; whetstone_consumed: boolean; stat_changes: Record<string, number>; xp_earned: number; new_total_xp: number; rank_up: boolean; new_rank_name: string | null; }`

2. **API** (`api/professions.ts`):
   - Add `sharpenItem(characterId, payload: SharpenRequest): Promise<SharpenResult>`

3. **Redux** (`redux/slices/craftingSlice.ts`):
   - Add state fields: `sharpenLoading`, `sharpenError`
   - Add thunk `sharpenItem`
   - Add selectors

4. **SharpeningSection.tsx**:
   - Fetch character inventory (use existing inventory API), filter to weapons/armor items
   - Fetch whetstones from inventory (items where `whetstone_level` is set — need to expose this in inventory response OR filter by known whetstone item names/types)
   - Display list of sharpenable items with current enhancement level
   - On item click, open SharpeningModal

5. **SharpeningModal.tsx**:
   - Show selected item with current stats and enhancement level
   - Whetstone selector (dropdown of available whetstones with success chance)
   - "Заточить" button
   - Result display: success animation (stats glow) or failure (whetstone consumed message)
   - Disable button if item is +5

6. **CraftTab.tsx**:
   - Conditionally render `<SharpeningSection>` when `characterProfession.profession.slug === 'blacksmith'`

7. **Enhancement display across app**: Show "+N" suffix on item names when `enhancement_level > 0` in inventory views and equipment display.

8. **Responsive**: All new components must work on 360px+ screens.

**Depends on:** Task 4.2
**Verify:** `npx tsc --noEmit && npm run build`

### Task 4.4 — QA: Backend Tests (QA Test)
**Status:** DONE
**Service:** inventory-service
**Files (new):** `services/inventory-service/app/tests/test_sharpening.py`

Test cases:
1. **Happy path**: Blacksmith sharpens a weapon with common whetstone, mock random to succeed. Verify enhancement_level incremented, whetstone consumed, correct stat delta returned.
2. **Failed sharpening**: Mock random to fail. Verify enhancement_level unchanged, whetstone still consumed.
3. **Max level**: Try to sharpen +5 item. Expect 400 error.
4. **Non-blacksmith**: Character with alchemist profession tries to sharpen. Expect 400 error.
5. **Wrong item type**: Try to sharpen a consumable/resource. Expect 400 error.
6. **No whetstone**: Try with invalid whetstone_item_id. Expect 400/404 error.
7. **Invalid whetstone**: Try with a non-whetstone item as whetstone. Expect 400 error.
8. **Equipped item sharpening**: Sharpen an equipped item. Verify enhancement_level updated on equipment slot and stat delta applied to attributes (mock httpx call).
9. **Enhancement preserved on equip/unequip**: Equip a +3 item, unequip it, verify enhancement_level is preserved in inventory.
10. **compute_enhancement_delta**: Unit test that only non-zero base stats produce deltas, with correct +1 / +0.1 values.
11. **build_modifiers_dict with enhancement**: Verify the function returns correct total modifiers with enhancement.

**Depends on:** Task 4.2
**Verify:** `pytest tests/test_sharpening.py -v`

### Task 4.5 — Review (Reviewer)
**Status:** DONE

Review checklist:
- [ ] Migration applies and rolls back cleanly
- [ ] Sharpening endpoint validates all business rules
- [ ] Enhancement level preserved through equip/unequip/trade flows
- [ ] Equipped item sharpening applies stat delta to character attributes
- [ ] build_modifiers_dict correctly includes enhancement bonuses
- [ ] Frontend compiles (`tsc --noEmit` + `npm run build`)
- [ ] All backend tests pass
- [ ] Live verification: sharpen an item, verify stats change in character profile
- [ ] Responsive design works on 360px+
- [ ] Error messages displayed to user in Russian
- [ ] No SCSS added (Tailwind only)
- [ ] All new files are TypeScript

**Depends on:** Tasks 4.1-4.4

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-26
**Result:** PASS

#### Type and Contract Verification
- Backend `SharpenRequest` schema (inventory_item_id, whetstone_item_id, stat_field, source) matches frontend `SharpenRequest` interface — **OK**
- Backend `SharpenResult` response fields match frontend `SharpenResult` interface — **OK** (all 14 fields aligned)
- Backend `SharpenInfoResponse` (item_name, item_type, points_spent, points_remaining, stats, whetstones) matches frontend type — **OK**
- Backend `SharpenStatInfo` and `SharpenWhetstoneInfo` match frontend interfaces — **OK**
- API URLs: frontend uses `/crafting/${characterId}/sharpen` and `/crafting/${characterId}/sharpen-info/${itemRowId}` — matches backend router — **OK**
- `enhancement_points_spent` and `enhancement_bonuses` added to both `CharacterInventory` and `EquipmentSlot` schemas (backend) and `InventoryItem`/`EquipmentSlotData` (frontend profileSlice) — **OK**

#### Point-Based Mechanic Verification
- `MAX_ENHANCEMENT_POINTS = 15`, `MAX_STAT_SHARPEN = 5` in crud.py — **OK**
- Point cost: 1 for existing stat (base_val != 0), 2 for new stat (base_val == 0) — **OK** (main.py:1847-1849)
- Budget check: `item_row.enhancement_points_spent + point_cost > MAX_ENHANCEMENT_POINTS` — **OK** (main.py:1852)
- Per-stat max: `current_count >= MAX_STAT_SHARPEN` — **OK** (main.py:1843)
- Enhancement stored as JSON dict `{stat_field: count}` in `enhancement_bonuses` column — **OK**

#### Enhancement Preservation Through Equip/Unequip
- **Equip:** Reads `enhancement_points_spent` and `enhancement_bonuses` from inventory row, copies to equipment slot (main.py:354-368) — **OK**
- **Unequip:** Reads from equipment slot, copies to newly created inventory row (main.py:441-457), then clears slot (main.py:467-468) — **OK**
- `build_modifiers_dict` called with `enhancement_bonuses` parameter in both equip (main.py:373) and unequip (main.py:461) — **OK**, stats correctly applied/removed including enhancement bonuses

#### Equipped Item Sharpening
- When `source == "equipment"`, reads from `EquipmentSlot` row (main.py:1806-1815) — **OK**
- After successful sharpening, updates bonuses on the slot row and calls `apply_modifiers_in_attributes_service` with stat delta (main.py:1892-1901) — **OK**
- Delta computation: +1 for MAIN_STAT_FIELDS, +0.1 for FLOAT_STAT_FIELDS — **OK**

#### build_modifiers_dict Enhancement Logic
- Enhancement bonuses loop (crud.py:349-358): iterates bonuses dict, maps field to key, applies count*1 or count*0.1, adds to mods — **OK**
- Negative mode: enhancement bonuses are also negated via the final `{k: -v for k, v in mods.items()}` — **OK**
- Tests confirm: base + enhancement = correct totals, negative mode works — **OK**

#### Whetstone Items
- Migration seeds 3 items with correct whetstone_level (1, 2, 3), item_type="resource", rarity=(common, rare, legendary) — **OK**
- Downgrade removes them by name — **OK**
- `WHETSTONE_CHANCE = {1: 0.25, 2: 0.50, 3: 0.75}` — **OK**

#### Success Chance Logic
- `random.random() < success_chance` — **OK** (main.py:1877)
- Whetstone always consumed regardless of outcome (main.py:1871-1874) — **OK**

#### Code Standards
- [x] Pydantic <2.0 syntax (`class Config: orm_mode = True`) — **OK**
- [x] Sync SQLAlchemy in inventory-service (consistent with existing codebase) — **OK**
- [x] `sharpen_item` endpoint is `async def` to use `await apply_modifiers_in_attributes_service` — consistent with equip/unequip pattern
- [x] No hardcoded secrets — **OK**
- [x] No `React.FC` usage — **OK** (all components use `const Foo = ({ x }: Props) => {`)
- [x] All new frontend files are `.tsx` / `.ts` — **OK**
- [x] All styles use Tailwind, no new SCSS — **OK**
- [x] UI strings in Russian — **OK** (errors, labels, buttons all Russian)
- [x] Error messages displayed to user via `toast.error()` — **OK** (SharpeningModal handles both fulfilled and rejected cases)
- [x] Responsive: `grid-cols-2 sm:grid-cols-3 md:grid-cols-4`, modal `max-w-lg mx-4`, `flex-col sm:flex-row` for buttons — **OK**
- [x] Alembic migration 007 present with correct revision chain — **OK**

#### Security
- [x] Auth check via `verify_character_ownership` — **OK**
- [x] Battle lock check — **OK**
- [x] No SQL injection vectors (all queries use ORM) — **OK**
- [x] Error messages don't leak internals (generic "Ошибка при заточке предмета" for 500s) — **OK**
- [x] `with_for_update()` on inventory/equipment rows to prevent race conditions — **OK**

#### Automated Check Results
- [x] `py_compile` — PASS (all 5 backend files: models.py, schemas.py, crud.py, main.py, 007_add_sharpening_system.py)
- [x] `pytest` — PASS (27/27 sharpening tests pass, 216 total tests pass, 19 pre-existing errors in test_endpoint_auth.py — unrelated)
- [x] `npx tsc --noEmit` — N/A (node.js not installed on review machine; Frontend Dev confirmed pass in LOG)
- [x] `npm run build` — N/A (node.js not installed on review machine; Frontend Dev confirmed pass in LOG)
- [ ] `docker-compose config` — N/A (docker not available in review environment)
- [ ] Live verification — N/A (services not running in review environment)

#### Notes
- The 19 test errors in `test_endpoint_auth.py` are pre-existing (fixture teardown issues with duplicated test runs) and unrelated to FEAT-083
- Frontend build verification was done by Frontend Dev (confirmed in LOG entry). TypeScript types are correctly aligned with backend schemas based on code review.
- The `regex` parameter in `Query("inventory", regex="^(inventory|equipment)$")` on line 1695 is deprecated in favor of `pattern` — minor, non-blocking, pre-existing pattern in codebase

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-26 — PM: фича создана, запускаю анализ
[LOG] 2026-03-26 — Codebase Analyst + Architect: анализ завершён. Ключевое открытие: таблица items — каталог шаблонов (shared), НЕ per-instance. enhancement_level добавляется в character_inventory и equipment_slots. Написаны секции 2, 3, 4. Статус: IN_PROGRESS.
[LOG] 2026-03-26 — Backend Dev: начал задачи #4.1 и #4.2. Реализована система поинтовой заточки (новая механика): models.py (3 новых поля), schemas.py (SharpenRequest/Result/InfoResponse + source), crud.py (константы, хелперы, обновлён build_modifiers_dict с enhancement_bonuses), main.py (POST /sharpen, GET /sharpen-info + поддержка экипированных предметов, обновлены equip/unequip для переноса enhancement данных), миграция 007. Все файлы прошли py_compile. Изменено 5 файлов.
[LOG] 2026-03-26 — Frontend Dev: задача #4.3 завершена. Добавлены типы (SharpenStatInfo, SharpenWhetstoneInfo, SharpenInfoResponse, SharpenRequest, SharpenResult), API (fetchSharpenInfo, sharpenItem), Redux (sharpenInfo, sharpenInfoLoading, sharpenLoading + thunks + selectors), компоненты SharpeningSection и SharpeningModal, интеграция в CraftTab для кузнецов, отображение бейджа заточки +N на ItemCell и EquipmentSlot. tsc --noEmit и npm run build прошли без новых ошибок.
[LOG] 2026-03-26 — QA: написаны тесты для sharpening системы — 27 тестов в test_sharpening.py. Покрыты: happy path, неудачная заточка, стоимость поинтов (1/2), лимит поинтов (15), лимит стата (+5), проверка профессии, типы предметов, валидация stat_field, точильные камни, sharpen-info эндпоинт, заточка экипированного предмета, XP, build_modifiers_dict с enhancement, безопасность (401/403/400). Все 27 тестов проходят.
[LOG] 2026-03-26 — Reviewer: проверка завершена, результат PASS. Все контракты backend/frontend совпадают, поинтовая механика корректна, enhancement сохраняется при equip/unequip, py_compile и pytest пройдены. Код соответствует стандартам (Tailwind, TypeScript, no React.FC, Russian strings, responsive).
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
