# FEAT-086: Ювелир — камни, слоты, переплавка

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-26 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-086-jeweler-gems-sockets.md` → `DONE-FEAT-086-jeweler-gems-sockets.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Ювелир получает три уникальные механики: вставка камней в слоты украшений, извлечение камней, и переплавка украшений в материалы. Также создаётся единая система слотов предметов, которая будет использоваться и зачарователем для рун в будущем.

### Механика 1: Система слотов (универсальная)
- Каждый предмет может иметь N слотов (задаётся админкой, поле `socket_count` на предмете)
- По умолчанию `socket_count = 0` (нет слотов)
- Слоты хранятся per-instance (на character_inventory / equipment_slots), т.к. разные экземпляры одного предмета могут иметь разные камни
- Система универсальна — ювелир вставляет камни в украшения, зачарователь потом будет вставлять руны в оружие/броню

### Механика 2: Вставка камней (только ювелир)
- Ювелир выбирает украшение (ring, necklace, bracelet) из своего инвентаря
- Выбирает камень из инвентаря
- Вставляет камень в свободный слот
- Камень даёт бонусы к статам (указаны на камне как модификаторы)
- Если предмет экипирован — бонусы камня применяются к персонажу сразу
- Камень расходуется из инвентаря при вставке

### Механика 3: Извлечение камней (только ювелир)
- Ювелир может достать камень из слота украшения
- Шанс сохранения камня зависит от ранга профессии:
  - Ученик (ранг 1): 10% сохранение (90% разрушение)
  - Подмастерье (ранг 2): 40% сохранение (60% разрушение)
  - Мастер (ранг 3): 70% сохранение (30% разрушение)
- При успехе: камень возвращается в инвентарь, слот освобождается
- При неудаче: камень уничтожается, слот освобождается
- Бонусы камня снимаются с персонажа (если предмет экипирован)

### Механика 4: Переплавка украшений (только ювелир)
- Ювелир может разобрать украшение на материалы
- Возвращается часть ингредиентов из рецепта, по которому было создано украшение
- Формула: ~50% ингредиентов (округление вниз, минимум 1 от каждого)
- Если украшение не было создано по рецепту (например, дроп с моба) — возвращается фиксированный ресурс "Ювелирный лом"
- Камни в слотах уничтожаются при переплавке (нужно сначала извлечь)
- Украшение удаляется из инвентаря

### Камни как предметы
- Камни — обычные предметы в таблице items
- Новый item_type: "gem" (уже добавлен в enum в FEAT-081, но не используется — проверить)
- Камни имеют модификаторы статов (strength_modifier, res_fire_modifier и т.д.) — те же поля что у обычного снаряжения
- Камни создаются ювелиром по рецептам из материалов
- Камни торгуются как обычные предметы

### Бизнес-правила
- Только ювелир может вставлять/извлекать камни и переплавлять украшения
- Вставка камней: только в украшения (ring, necklace, bracelet) с свободными слотами
- Количество слотов задаётся в админке на предмете
- Слоты per-instance (на inventory/equipment row, не на item template)
- Извлечение: шанс зависит от ранга (10%/40%/70%)
- Переплавка: только украшения, возвращает ~50% ингредиентов
- Все операции дают XP профессии (10 XP)

### UX / Пользовательский сценарий

**Вставка камня:**
1. Ювелир открывает секцию "Камни и слоты" в табе крафта
2. Выбирает украшение с свободными слотами
3. Видит текущие слоты (пустые/занятые) и статы украшения
4. Выбирает камень из инвентаря
5. Видит какие бонусы даст камень
6. Нажимает "Вставить"
7. Камень вставлен, статы обновились

**Извлечение камня:**
1. Ювелир выбирает украшение с вставленным камнем
2. Выбирает конкретный слот с камнем
3. Видит шанс сохранения (зависит от ранга)
4. Нажимает "Извлечь"
5. Результат: камень сохранён и в инвентаре, или камень уничтожен

**Переплавка:**
1. Ювелир выбирает украшение
2. Видит что получит (список ингредиентов ~50%)
3. Предупреждение если есть камни в слотах
4. Нажимает "Переплавить"
5. Украшение исчезает, материалы появляются в инвентаре

### Edge Cases
- Что если все слоты заняты? → Кнопка "Вставить" неактивна
- Что если нет камней в инвентаре? → Показать "Нет камней"
- Что если при переплавке в слотах есть камни? → Предупреждение "Камни будут уничтожены!"
- Что если украшение экипировано? → Можно вставлять/извлекать (статы применяются сразу)
- Что если украшение не имеет рецепта (дроп)? → Переплавка даёт "Ювелирный лом"

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1 Items Model (`services/inventory-service/app/models.py`)

**item_type enum:** Currently contains: `head`, `body`, `cloak`, `belt`, `ring`, `necklace`, `bracelet`, `main_weapon`, `consumable`, `additional_weapons`, `resource`, `scroll`, `misc`, `shield`, `blueprint`, `recipe`. **`gem` is NOT present** — must be added via ALTER ENUM in the migration. The feature brief claimed it was added in FEAT-081, but that is incorrect.

**socket_count field:** Does NOT exist on the `items` table. Must be added.

**Modifier fields:** Gems will reuse the same modifier fields that all items already have (`strength_modifier`, `agility_modifier`, `res_fire_modifier`, etc.) — no new columns needed on `items` for gem stats. Gems are just regular items with `item_type='gem'` and non-zero modifier values.

**Pydantic ItemType enum (`schemas.py`):** Also lacks `gem` — must add it.

### 2.2 Per-Instance Data (`character_inventory` / `equipment_slots`)

Both tables already have per-instance fields from FEAT-083 (sharpening):
- `enhancement_points_spent` (Integer, default 0)
- `enhancement_bonuses` (Text/JSON, nullable)

These are properly copied between inventory and equipment on equip/unequip (lines 331-341 and 449-458 of `main.py`). The socket data (`socketed_gems`) needs the same treatment — add a new `socketed_gems` Text column to both tables and copy it during equip/unequip.

Helper functions `get_enhancement_bonuses()` / `set_enhancement_bonuses()` in `crud.py` (lines 71-80) parse/serialize JSON. We need analogous `get_socketed_gems()` / `set_socketed_gems()` helpers.

### 2.3 Equip/Unequip Flow (`main.py` lines 288-408, 414-486)

**Equip:**
1. Saves `enhancement_points_spent` and `enhancement_bonuses` from inventory row
2. Removes item from inventory
3. Sets slot's item_id + copies enhancement data to slot
4. Calls `build_modifiers_dict(item, enhancement_bonuses=...)` → `apply_modifiers_in_attributes_service()`

**Unequip (reverse):**
1. Saves enhancement data from slot
2. Returns item to inventory + copies enhancement data to new inventory row
3. Calls `build_modifiers_dict(item, negative=True, enhancement_bonuses=...)` → removes modifiers

**Impact for sockets:**
- `socketed_gems` JSON must be copied alongside `enhancement_bonuses` in both directions
- `build_modifiers_dict()` must also accept and process gem bonuses (load gem item objects, sum their modifiers)
- Slot clearing must also reset `socketed_gems = None`

### 2.4 build_modifiers_dict (`crud.py` lines 253-366)

Signature: `build_modifiers_dict(item_obj, negative=False, enhancement_bonuses=None)`.
Currently adds base item modifiers + sharpening bonuses from `enhancement_bonuses` dict.

**Proposed change:** Add `socketed_gems_items: list[Items] = None` parameter. For each gem item in the list, add its modifier values to the total `mods` dict. This keeps the function signature clean and avoids DB queries inside the pure function.

### 2.5 Recipe System (for smelting)

**Recipe model** (`models.py` lines 224-247): Has `result_item_id` and `ingredients` relationship to `RecipeIngredient` (item_id + quantity).

**Smelting approach:** To find what recipe created a jewelry item, query `Recipe` where `result_item_id == item.id` and `profession.slug == 'jeweler'`. If no recipe found (item is a drop), return fallback "Ювелирный лом" resource.

**No `source_recipe_id` tracking needed** on inventory rows — we can reverse-lookup recipes by `result_item_id`. This is clean because each unique item (by item_id) maps to at most one recipe. Multiple recipe matches could exist in theory, but in practice each jewelry item has one recipe.

**Ingredient return formula:** For each `RecipeIngredient`, return `max(1, floor(quantity * 0.5))`.

### 2.6 Frontend CraftTab (`CraftTab.tsx`)

Profession-specific sections are conditionally rendered:
- `characterProfession.profession.slug === 'blacksmith'` → `<SharpeningSection>`
- `characterProfession.profession.slug === 'alchemist'` → `<EssenceExtractionSection>` + `<TransmutationSection>`

We need to add: `characterProfession.profession.slug === 'jeweler'` → `<GemSocketSection>` + `<SmeltingSection>`.

Pattern: Each section is a self-contained component that uses `useAppSelector` for inventory/equipment data and has its own modal for the operation. `SharpeningSection.tsx` is the best template — it collects eligible items from inventory+equipment, shows a selection UI, then opens a modal for the actual operation.

### 2.7 Alembic Migrations

Latest migration: `009_add_transmutation_items`. Next migration will be `010_add_gem_sockets`.

### 2.8 Risks & Constraints

1. **MySQL ENUM alteration** — adding `gem` to `item_type` enum requires `ALTER TABLE items MODIFY COLUMN item_type ENUM(...)`. MySQL supports this but it's a DDL lock.
2. **Equip/unequip flow complexity** — socketed_gems must be copied correctly in 4 places (equip: inv→slot, unequip: slot→inv, equip-with-replace: old-slot→inv + inv→new-slot). Missing any copy = data loss.
3. **Gem modifier stacking** — build_modifiers_dict needs DB access to load gem items by ID from the `socketed_gems` JSON. The caller must pre-load gem items and pass them in.
4. **Equipped item operations** — inserting/extracting gems on equipped items requires live modifier recalculation (apply/remove modifiers via attributes service).
5. **No new cross-service dependencies** — all changes are within inventory-service + frontend. Attributes service API is already used.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 DB Schema Changes (Migration 010)

**Table `items`:**
- Add `socket_count` (Integer, default 0, NOT NULL) — number of gem/rune slots this item template supports
- Add `gem` to `item_type` ENUM — new item type for gems
- Seed 1 item: "Ювелирный лом" (item_type='resource', item_rarity='common', max_stack_size=99, description="Ювелирный лом, полученный при переплавке украшений. Используется как ресурс для крафта.")

**Table `character_inventory`:**
- Add `socketed_gems` (Text, nullable) — JSON string, e.g. `[42, null, 15]` where values are `items.id` of inserted gems, `null` = empty slot

**Table `equipment_slots`:**
- Add `socketed_gems` (Text, nullable) — same format, travels with item on equip/unequip

**Pydantic schemas:**
- Add `gem` to `ItemType` enum in `schemas.py`
- Add `socket_count` to `ItemBase`, `Item` schemas
- Add `socketed_gems` to `CharacterInventory`, `EquipmentSlotBase` schemas

### 3.2 Backend: Helper Functions (crud.py)

```python
def get_socketed_gems(row) -> list:
    """Parse socketed_gems JSON from inventory/equipment row. Returns list like [42, None, 15]."""
    if row.socketed_gems:
        return json.loads(row.socketed_gems)
    return []

def set_socketed_gems(row, gems: list):
    """Serialize socketed_gems to JSON on inventory/equipment row."""
    row.socketed_gems = json.dumps(gems) if gems else None

def load_gem_items(db, gem_ids: list) -> list:
    """Load Items objects for non-null gem IDs. Returns list of Items."""
    valid_ids = [gid for gid in gem_ids if gid is not None]
    if not valid_ids:
        return []
    return db.query(Items).filter(Items.id.in_(valid_ids)).all()
```

### 3.3 Backend: build_modifiers_dict Update

Add optional parameter `gem_items: list[Items] = None`:

```python
def build_modifiers_dict(item_obj, negative=False, enhancement_bonuses=None, gem_items=None):
    # ... existing logic ...

    # Add gem bonuses
    if gem_items:
        for gem in gem_items:
            for field in ALL_MODIFIER_FIELDS:
                val = getattr(gem, field, 0) or 0
                if val:
                    key = field.replace('_modifier', '')
                    mods[key] = mods.get(key, 0) + val

    if negative:
        mods = {k: -v for k, v in mods.items()}
    return mods
```

Where `ALL_MODIFIER_FIELDS = MAIN_STAT_FIELDS + FLOAT_STAT_FIELDS + VUL_STAT_FIELDS + RECOVERY_FIELDS` (superset of all modifier columns).

### 3.4 Backend: Equip/Unequip Update

In both equip and unequip flows, `socketed_gems` must be:
1. **Read** from source (inventory or equipment slot) before removal
2. **Written** to destination (equipment slot or new inventory row)
3. **Included** in `build_modifiers_dict()` call — pre-load gem Items, pass as `gem_items`
4. **Cleared** when slot is emptied (`slot.socketed_gems = None`)

This parallels the existing `enhancement_bonuses` copy pattern exactly.

### 3.5 Backend: New Endpoints (main.py)

All endpoints under `/inventory/crafting/{character_id}/`:

#### 3.5.1 GET `/socket-info/{item_row_id}?source=inventory|equipment`
Returns socket state for an item.

**Response schema `SocketInfoResponse`:**
```python
class GemSlotInfo(BaseModel):
    slot_index: int
    gem_item_id: Optional[int] = None
    gem_name: Optional[str] = None
    gem_image: Optional[str] = None
    gem_modifiers: dict = {}  # {stat_name: value}

class AvailableGemInfo(BaseModel):
    inventory_item_id: int  # character_inventory.id
    item_id: int
    name: str
    image: Optional[str] = None
    quantity: int
    modifiers: dict = {}  # {stat_name: value}

class SocketInfoResponse(BaseModel):
    item_name: str
    item_type: str
    socket_count: int
    slots: List[GemSlotInfo] = []
    available_gems: List[AvailableGemInfo] = []
```

**Logic:**
1. Validate jeweler profession
2. Load item row (inventory or equipment), load item template
3. Validate item_type in ('ring', 'necklace', 'bracelet')
4. Parse `socketed_gems` JSON, load gem item data
5. Find all gems in character's inventory (item_type='gem')
6. Return socket state + available gems

#### 3.5.2 POST `/insert-gem`
**Request schema `InsertGemRequest`:**
```python
class InsertGemRequest(BaseModel):
    item_row_id: int       # character_inventory.id or equipment_slots.id
    source: str = "inventory"  # "inventory" or "equipment"
    slot_index: int        # which socket slot (0-based)
    gem_inventory_id: int  # character_inventory.id of the gem to insert
```

**Response schema `InsertGemResult`:**
```python
class InsertGemResult(BaseModel):
    success: bool
    item_name: str
    gem_name: str
    slot_index: int
    xp_earned: int
    new_total_xp: int
    rank_up: bool
    new_rank_name: Optional[str] = None
```

**Logic:**
1. Validate jeweler profession
2. Load item row, validate type in ('ring', 'necklace', 'bracelet')
3. Validate slot_index < socket_count and slot is empty
4. Load gem from inventory, validate item_type='gem', quantity >= 1
5. Consume gem (quantity -= 1, delete if 0)
6. Update socketed_gems JSON at slot_index
7. If item is equipped: recalculate modifiers — apply gem's positive modifiers via attributes service
8. Award 10 XP to profession
9. Return result

#### 3.5.3 POST `/extract-gem`
**Request schema `ExtractGemRequest`:**
```python
class ExtractGemRequest(BaseModel):
    item_row_id: int
    source: str = "inventory"
    slot_index: int
```

**Response schema `ExtractGemResult`:**
```python
class ExtractGemResult(BaseModel):
    success: bool
    item_name: str
    gem_name: str
    gem_preserved: bool    # True = gem returned to inventory, False = destroyed
    preservation_chance: int  # percentage shown to user
    slot_index: int
    xp_earned: int
    new_total_xp: int
    rank_up: bool
    new_rank_name: Optional[str] = None
```

**Logic:**
1. Validate jeweler profession, get current_rank
2. Load item row, validate type in ('ring', 'necklace', 'bracelet')
3. Validate slot_index has a gem
4. Determine preservation chance: rank 1 → 10%, rank 2 → 40%, rank 3 → 70%
5. Roll random: if preserved → add gem back to inventory; if not → gem destroyed
6. Clear socketed_gems at slot_index (set to null)
7. If item is equipped: remove gem's modifiers via attributes service (negative)
8. Award 10 XP to profession
9. Return result with `gem_preserved` flag

#### 3.5.4 GET `/smelt-info/{item_row_id}`
Returns what smelting would yield.

**Response schema `SmeltInfoResponse`:**
```python
class SmeltIngredientReturn(BaseModel):
    item_id: int
    name: str
    image: Optional[str] = None
    quantity: int  # how many will be returned

class SmeltInfoResponse(BaseModel):
    item_name: str
    item_type: str
    has_gems: bool            # warn user if gems will be destroyed
    gem_count: int
    has_recipe: bool          # True = recipe found, False = will return junk
    ingredients: List[SmeltIngredientReturn] = []  # what you'll get
```

**Logic:**
1. Validate jeweler profession
2. Load item from inventory (NOT equipment — must unequip first), validate type in ('ring', 'necklace', 'bracelet')
3. Check socketed_gems for any non-null entries → `has_gems`, `gem_count`
4. Query `Recipe` where `result_item_id == item.item_id` and `recipe.profession.slug == 'jeweler'`
5. If recipe found: for each ingredient, return `max(1, floor(quantity * 0.5))`
6. If no recipe: return [{"Ювелирный лом", quantity: 1}]

#### 3.5.5 POST `/smelt`
**Request schema `SmeltRequest`:**
```python
class SmeltRequest(BaseModel):
    inventory_item_id: int  # character_inventory.id
```

**Response schema `SmeltResult`:**
```python
class SmeltResult(BaseModel):
    success: bool
    item_name: str
    gems_destroyed: int
    materials_returned: list  # [{name, quantity}]
    xp_earned: int
    new_total_xp: int
    rank_up: bool
    new_rank_name: Optional[str] = None
```

**Logic:**
1. Validate jeweler profession
2. Load item from inventory (NOT equipment), validate type in ('ring', 'necklace', 'bracelet')
3. Count and destroy socketed gems (just clear them, don't return to inventory)
4. Find recipe by result_item_id → calculate 50% ingredients → add to inventory
5. If no recipe → add 1x "Ювелирный лом" to inventory
6. Delete the jewelry item from inventory (quantity -= 1, delete row if 0)
7. Award 10 XP to profession
8. Return result

### 3.6 Frontend Architecture

**New components** (all in `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/`):
- `GemSocketSection.tsx` — item selection list + opens modal (pattern: `SharpeningSection.tsx`)
- `GemSocketModal.tsx` — socket visualization, insert/extract actions (pattern: `SharpeningModal.tsx`)
- `SmeltingSection.tsx` — item selection list + opens modal
- `SmeltingModal.tsx` — shows ingredients to be returned, confirm button

**Redux:** Add async thunks + state to `craftingSlice.ts`:
- `fetchSocketInfo(characterId, itemRowId, source)` → GET `/socket-info/...`
- `insertGem(characterId, request)` → POST `/insert-gem`
- `extractGem(characterId, request)` → POST `/extract-gem`
- `fetchSmeltInfo(characterId, itemRowId)` → GET `/smelt-info/...`
- `smeltItem(characterId, request)` → POST `/smelt`

**CraftTab.tsx update:** Add conditional rendering for jeweler:
```tsx
{characterProfession.profession.slug === 'jeweler' && (
  <>
    <GemSocketSection characterId={characterId} />
    <SmeltingSection characterId={characterId} />
  </>
)}
```

**Types** (in `types/professions.ts` or new `types/gems.ts`):
- `SocketInfoResponse`, `GemSlotInfo`, `AvailableGemInfo`
- `InsertGemRequest`, `InsertGemResult`
- `ExtractGemRequest`, `ExtractGemResult`
- `SmeltInfoResponse`, `SmeltIngredientReturn`
- `SmeltRequest`, `SmeltResult`

### 3.7 Key Design Decisions

1. **socketed_gems as JSON array** — matches the enhancement_bonuses pattern (JSON Text column). Array format `[gem_id, null, gem_id]` is simple and preserves slot ordering.
2. **Smelting only from inventory** — equipped items must be unequipped first. This avoids complex modifier recalculation during smelting.
3. **No source_recipe_id tracking** — reverse-lookup via `Recipe.result_item_id` is sufficient and avoids schema bloat.
4. **gem_items passed to build_modifiers_dict** — callers pre-load gem Items from DB, keeping the function pure (no DB access inside).
5. **Preservation chance by rank** — hardcoded constants (10%/40%/70%), not stored in DB. Simple and matches how whetstone chances are hardcoded.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: DB Migration — gem sockets schema
**Agent:** Backend Developer
**Status:** DONE
**Files:**
- `services/inventory-service/app/alembic/versions/010_add_gem_sockets.py` (new)
- `services/inventory-service/app/models.py` (modify)
- `services/inventory-service/app/schemas.py` (modify)

**Spec:**
1. Create Alembic migration `010_add_gem_sockets`:
   - ALTER `items.item_type` ENUM to add `'gem'` value
   - Add `socket_count` (Integer, NOT NULL, server_default="0") to `items`
   - Add `socketed_gems` (Text, nullable) to `character_inventory`
   - Add `socketed_gems` (Text, nullable) to `equipment_slots`
   - Seed 1 item: "Ювелирный лом" (item_type='resource', item_rarity='common', price=10, max_stack_size=99, description="Ювелирный лом, полученный при переплавке украшений. Используется как ресурс для крафта.")
   - Downgrade: reverse all changes
2. Update `Items` model: add `socket_count = Column(Integer, default=0)` and add `'gem'` to item_type Enum
3. Update `CharacterInventory` model: add `socketed_gems = Column(Text, nullable=True)`
4. Update `EquipmentSlot` model: add `socketed_gems = Column(Text, nullable=True)`
5. Update `schemas.py`:
   - Add `gem = "gem"` to `ItemType` enum
   - Add `socket_count: int = 0` to `ItemBase`
   - Add `socketed_gems: Optional[str] = None` to `CharacterInventory`, `EquipmentSlotBase`

**Verify:** `python -m py_compile models.py`, `python -m py_compile schemas.py`

---

### Task 2: Backend — socket/gem insert & extract logic
**Agent:** Backend Developer
**Status:** DONE
**Depends on:** Task 1
**Files:**
- `services/inventory-service/app/crud.py` (modify)
- `services/inventory-service/app/main.py` (modify)
- `services/inventory-service/app/schemas.py` (modify)

**Spec:**
1. Add to `crud.py`:
   - `get_socketed_gems(row) -> list` — parse JSON, return list
   - `set_socketed_gems(row, gems: list)` — serialize to JSON
   - `load_gem_items(db, gem_ids) -> list[Items]` — load gem Items by IDs
   - `JEWELRY_TYPES = ['ring', 'necklace', 'bracelet']` constant
   - `GEM_PRESERVATION_CHANCES = {1: 10, 2: 40, 3: 70}` constant
   - `GEM_XP_REWARD = 10` constant
2. Update `build_modifiers_dict()`: add `gem_items=None` parameter. When provided, iterate each gem's modifier fields and add to mods dict. Place this BEFORE the `negative` flip.
3. Update equip flow (`equip_item` in main.py):
   - Save `socketed_gems` from inventory row before removal
   - Copy to equipment slot after equipping
   - Pre-load gem items, pass to `build_modifiers_dict()` for both old item removal and new item application
   - Clear `socketed_gems = None` when clearing slot
4. Update unequip flow (`unequip_item` in main.py):
   - Save `socketed_gems` from equipment slot
   - Copy to new inventory row after returning item
   - Pre-load gem items, pass to `build_modifiers_dict()`
   - Clear `socketed_gems = None` when clearing slot
5. Add schemas: `SocketInfoResponse`, `GemSlotInfo`, `AvailableGemInfo`, `InsertGemRequest`, `InsertGemResult`, `ExtractGemRequest`, `ExtractGemResult`
6. Add endpoints:
   - `GET /crafting/{character_id}/socket-info/{item_row_id}?source=inventory|equipment` — see section 3.5.1
   - `POST /crafting/{character_id}/insert-gem` — see section 3.5.2
   - `POST /crafting/{character_id}/extract-gem` — see section 3.5.3

**Verify:** `python -m py_compile crud.py`, `python -m py_compile main.py`

---

### Task 3: Backend — smelting logic
**Agent:** Backend Developer
**Status:** DONE
**Depends on:** Task 1
**Files:**
- `services/inventory-service/app/crud.py` (modify)
- `services/inventory-service/app/main.py` (modify)
- `services/inventory-service/app/schemas.py` (modify)

**Spec:**
1. Add schemas: `SmeltInfoResponse`, `SmeltIngredientReturn`, `SmeltRequest`, `SmeltResult`
2. Add to `crud.py`:
   - `find_recipe_for_item(db, item_id, profession_slug='jeweler') -> Optional[Recipe]` — find recipe where result_item_id == item_id and profession matches
   - `calculate_smelt_returns(recipe) -> list[dict]` — for each ingredient, return `{"item_id": ..., "name": ..., "quantity": max(1, quantity // 2)}`
   - `get_junk_item_id(db) -> int` — find "Ювелирный лом" item ID (cache after first lookup)
3. Add endpoints:
   - `GET /crafting/{character_id}/smelt-info/{item_row_id}` — see section 3.5.4
   - `POST /crafting/{character_id}/smelt` — see section 3.5.5
4. Smelting must only work on inventory items (not equipped). Validate item_type in JEWELRY_TYPES.

**Verify:** `python -m py_compile crud.py`, `python -m py_compile main.py`

---

### Task 4: Frontend — types, API, Redux
**Agent:** Frontend Developer
**Status:** DONE
**Depends on:** Tasks 2, 3
**Files:**
- `services/frontend/app-chaldea/src/types/gems.ts` (new)
- `services/frontend/app-chaldea/src/redux/slices/craftingSlice.ts` (modify)

**Spec:**
1. Create `types/gems.ts` with all TypeScript interfaces matching backend response schemas (SocketInfoResponse, InsertGemRequest, InsertGemResult, ExtractGemRequest, ExtractGemResult, SmeltInfoResponse, SmeltRequest, SmeltResult)
2. Add to `craftingSlice.ts`:
   - State fields: `socketInfo`, `socketInfoLoading`, `smeltInfo`, `smeltInfoLoading`, `gemOperationLoading`
   - Async thunks: `fetchSocketInfo`, `insertGem`, `extractGem`, `fetchSmeltInfo`, `smeltItem`
   - Selectors for all new state
3. Update `profileSlice` types if needed to include `socketed_gems` on inventory/equipment items

**Verify:** `npx tsc --noEmit`

---

### Task 5: Frontend — gem socket UI
**Agent:** Frontend Developer
**Status:** DONE
**Depends on:** Task 4
**Files:**
- `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/GemSocketSection.tsx` (new)
- `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/GemSocketModal.tsx` (new)
- `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/CraftTab.tsx` (modify)

**Spec:**
1. `GemSocketSection.tsx` — follows `SharpeningSection.tsx` pattern:
   - Filter inventory + equipment for jewelry items (ring, necklace, bracelet) with socket_count > 0
   - Show list with socket status (e.g., "2/3 камней")
   - Click opens `GemSocketModal`
2. `GemSocketModal.tsx`:
   - Fetch socket-info on open
   - Show socket grid (visual slots: filled with gem icon/name, or empty)
   - Empty slot + gem selected → "Вставить" button
   - Filled slot → "Извлечь" button with preservation chance display
   - Available gems list with modifier preview
   - Success/failure toasts
3. Update `CraftTab.tsx`: add jeweler conditional section
4. All Tailwind, no SCSS. Mobile-responsive (360px+). No React.FC.

**Verify:** `npx tsc --noEmit`, `npm run build`

---

### Task 6: Frontend — smelting UI
**Agent:** Frontend Developer
**Status:** DONE
**Depends on:** Task 4
**Files:**
- `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/SmeltingSection.tsx` (new)
- `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/SmeltingModal.tsx` (new)
- `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/CraftTab.tsx` (modify, if not done in Task 5)

**Spec:**
1. `SmeltingSection.tsx`:
   - Filter inventory for jewelry items (ring, necklace, bracelet)
   - Show list with item info
   - Click opens `SmeltingModal`
2. `SmeltingModal.tsx`:
   - Fetch smelt-info on open
   - Show item being smelted
   - Show materials to be returned (with quantities and icons)
   - Warning if has_gems: "Камни в слотах будут уничтожены!"
   - "Переплавить" confirm button
   - Success toast with materials received
3. All Tailwind, no SCSS. Mobile-responsive. No React.FC.

**Verify:** `npx tsc --noEmit`, `npm run build`

---

### Task 7: QA — backend tests
**Agent:** QA Test
**Status:** DONE
**Depends on:** Tasks 2, 3
**Files:**
- `services/inventory-service/app/tests/test_gem_sockets.py` (new)
- `services/inventory-service/app/tests/test_smelting.py` (new)

**Spec:**
Test cases:
1. **Insert gem:** valid insert, slot occupied error, wrong item type, no free slot, gem not in inventory, not jeweler
2. **Extract gem:** successful preservation, destruction, empty slot error, wrong profession
3. **Socket-info:** returns correct slot state and available gems
4. **Equip/unequip with gems:** verify socketed_gems JSON travels correctly, gem modifiers applied/removed
5. **build_modifiers_dict with gems:** verify gem bonuses are correctly summed
6. **Smelt with recipe:** verify ~50% ingredient return
7. **Smelt without recipe:** verify "Ювелирный лом" returned
8. **Smelt with gems:** verify gems destroyed, warning flag
9. **Smelt equipped item:** verify error (must unequip first)

**Verify:** `pytest` passes

---

### Task 8: Review
**Agent:** Reviewer
**Status:** DONE
**Depends on:** Tasks 1-7
**Spec:** Full review per reviewer checklist. Live verification of all 3 mechanics (insert, extract, smelt).

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-26
**Result:** FAIL

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/types/gems.ts:27` | Field name mismatch: TS type has `sockets: SocketGemInfo[]` but backend returns `"slots"` key. `socketInfo.sockets` will be `undefined` at runtime. Must rename to `slots` in TS type, or rename backend response key to `sockets`. | Frontend Developer | FIX_REQUIRED |
| 2 | `services/frontend/app-chaldea/src/types/gems.ts:24,79` | `item_image` field exists in `SocketInfoResponse` and `SmeltInfoResponse` TS types but backend does not return it. Minor (will be `undefined`), but types should match backend contract. Remove `item_image` from both interfaces. | Frontend Developer | FIX_REQUIRED |

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not available on this machine)
- [ ] `npm run build` — N/A (Node.js not available on this machine)
- [x] `py_compile` — PASS (models.py, schemas.py, crud.py, main.py)
- [x] `pytest` — PASS (42/42 new tests pass, 276 existing tests pass, 1 pre-existing failure + 19 pre-existing errors unrelated to this feature)
- [ ] `docker-compose config` — N/A (docker not available locally)
- [ ] Live verification — N/A (services not running)

#### Detailed Review

**Backend (PASS):**
- Migration `010_add_gem_sockets.py`: Idempotent checks via `_column_exists()`. Enum alteration checks existing column type. Seed uses `INSERT IGNORE`. Downgrade reverses all changes. Correct.
- `models.py`: `socket_count`, `socketed_gems` added to `Items`, `CharacterInventory`, `EquipmentSlot`. `gem` added to item_type enum. Matches migration.
- `schemas.py`: All 5 new endpoint schemas present (`SocketInfoResponse`, `InsertGemRequest/Result`, `ExtractGemRequest/Result`, `SmeltInfoResponse`, `SmeltRequest/Result`). `gem` in `ItemType` enum, `socket_count` in `ItemBase`, `socketed_gems` in `CharacterInventory` and `EquipmentSlotBase`.
- `crud.py`: Helpers (`get_socketed_gems`, `set_socketed_gems`, `load_gem_items`, `get_gem_modifiers_dict`, `find_recipe_for_item`, `calculate_smelt_returns`, `get_junk_item`) are clean and follow existing patterns. `build_modifiers_dict` correctly adds gem bonuses BEFORE the `negative` flip. `JEWELRY_TYPES`, `GEM_PRESERVATION_CHANCES`, `GEM_XP_REWARD` constants are correct.
- `main.py` endpoints: All 5 endpoints follow the established pattern (auth, ownership check, battle lock, profession validation). Equip/unequip flows correctly copy `socketed_gems` alongside `enhancement_bonuses`. `insert-gem` correctly consumes gem, updates socketed_gems, applies modifiers if equipped. `extract-gem` correctly rolls random, handles preservation/destruction, removes modifiers if equipped. `smelt` only works from inventory (not equipment), destroys gems, returns ~50% ingredients or junk. XP awarded in all operations. Error handling with rollback consistent.
- Extraction chances correct: rank 1=10%, rank 2=40%, rank 3=70%.
- Smelting returns: `max(1, quantity // 2)` — correct ~50%.
- No secrets, no SQL injection vectors, error messages in Russian, no stack trace leaks.

**Frontend (FAIL — Issues #1, #2):**
- Issue #1 is a **runtime bug**: `socketInfo.sockets` will be `undefined` because the backend response key is `slots`. The entire socket visualization in `GemSocketModal.tsx` will break (`.filter()` and `.map()` on undefined). This must be fixed before the feature can work.
- Issue #2 is a type accuracy issue. Not a runtime breaker but incorrect types.
- All files are `.tsx` (TypeScript) — correct.
- All styles use Tailwind, no SCSS — correct.
- No `React.FC` usage — correct.
- Responsive design with `sm:`, `md:` breakpoints — correct.
- UI text in Russian — correct.
- Error handling with `toast.error()` on all API failures — correct.
- Design system classes used (`gold-text`, `modal-overlay`, `modal-content`, `gold-outline`, `btn-blue`, `btn-line`, `rounded-card`, `gold-scrollbar`) — correct.

**QA Tests (PASS):**
- 42 tests covering all specified scenarios: insert (happy path, non-jeweler, wrong type, occupied slot, invalid index, no gem, no sockets), extract (preserved, destroyed, rank chances, empty slot), equipped item operations, smelting (with/without recipe, with gems, equipped item, non-jewelry), socket-info, smelt-info, equip/unequip with gems, build_modifiers_dict unit tests, security (401/403), XP. All passing.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-26 — PM: фича создана, запускаю анализ + проектирование
[LOG] 2026-03-26 — Codebase Analyst: анализ завершён. gem НЕ присутствует в item_type enum (вопреки описанию в brief). socket_count и socketed_gems отсутствуют. enhancement_bonuses паттерн (FEAT-083) полностью применим для socketed_gems. Рецепт-реверс для переплавки возможен через Recipe.result_item_id без дополнительных полей.
[LOG] 2026-03-26 — Architect: архитектура спроектирована. 5 новых эндпоинтов, 1 миграция, обновление build_modifiers_dict и equip/unequip. 8 задач создано. Статус: IN_PROGRESS.
[LOG] 2026-03-26 — Frontend Dev: задача #4 завершена. Создан types/gems.ts (типы для сокетов и переплавки), добавлены API-функции в api/professions.ts, обновлён craftingSlice.ts (состояние, thunks, селекторы, reducers), обновлён profileSlice.ts (socketed_gems, socket_count).
[LOG] 2026-03-26 — Backend Dev: начал задачи #1, #2, #3
[LOG] 2026-03-26 — Backend Dev: задача #1 завершена — миграция 010_add_gem_sockets (gem в ENUM, socket_count, socketed_gems, seed Ювелирный лом), обновлены models.py и schemas.py
[LOG] 2026-03-26 — Backend Dev: задача #2 завершена — helpers в crud.py (get/set_socketed_gems, load_gem_items, get_gem_modifiers_dict), build_modifiers_dict с gem_items, equip/unequip копируют socketed_gems, 3 эндпоинта (socket-info, insert-gem, extract-gem)
[LOG] 2026-03-26 — Backend Dev: задача #3 завершена — find_recipe_for_item, calculate_smelt_returns, get_junk_item в crud.py, 2 эндпоинта (smelt-info, smelt), схемы SmeltInfoResponse/SmeltRequest/SmeltResult. py_compile пройден для всех файлов.
[LOG] 2026-03-26 — Frontend Dev: начал задачи #5, #6
[LOG] 2026-03-26 — Frontend Dev: задача #5 завершена — GemSocketSection.tsx (список украшений со слотами из инвентаря+экипировки, индикаторы слотов), GemSocketModal.tsx (визуализация сокетов, вставка камней из списка доступных, извлечение с предупреждением), обновлён CraftTab.tsx для jeweler
[LOG] 2026-03-26 — Frontend Dev: задача #6 завершена — SmeltingSection.tsx (список украшений из инвентаря для переплавки, предупреждение о камнях), SmeltingModal.tsx (превью возвращаемых материалов, двухшаговое подтверждение, предупреждение об уничтожении камней). Все компоненты: TypeScript, Tailwind, адаптивные (360px+), русский UI, toast для ошибок/успехов.
[LOG] 2026-03-26 — QA: тесты написаны, test_gem_sockets.py — 42 теста, все проходят. Покрыты: insert/extract/smelt, socket-info, smelt-info, equip/unequip с камнями, build_modifiers_dict, безопасность (401/403), XP.
[LOG] 2026-03-26 — Reviewer: проверка завершена, результат FAIL. 2 проблемы найдены: (1) несовпадение имени поля slots/sockets между backend и frontend — runtime баг, сокеты не отобразятся; (2) item_image в TS типах отсутствует в backend ответах.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
