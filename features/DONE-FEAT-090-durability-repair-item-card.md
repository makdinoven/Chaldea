# FEAT-090: Система прочности, ремонт-комплекты, карточка предмета

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-26 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-090-durability-repair-item-card.md` → `DONE-FEAT-090-durability-repair-item-card.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Часть 1: Система прочности

#### Описание
Оружие и броня имеют прочность, которая снижается в бою. При прочности 0 предмет перестаёт давать статы (как будто не экипирован). Для ремонта используются ремонт-комплекты, которые крафтит кузнец.

#### Какие предметы имеют прочность
- head (шлем), body (броня), cloak (плащ)
- main_weapon (оружие), additional_weapons (доп. оружие)
- НЕ имеют прочности: belt, shield, ring, necklace, bracelet, consumable, resource, scroll, gem, rune, misc, blueprint, recipe

#### Поля прочности (per-instance)
- `max_durability` на items (шаблон) — максимальная прочность предмета (задаётся в админке, например 100)
- `current_durability` на character_inventory и equipment_slots — текущая прочность (per-instance, default = max_durability при получении)

#### Снижение прочности в бою
- **Оружие** (main_weapon, additional_weapons): -1 прочности за каждую атаку персонажа
- **Броня** (head, body, cloak): -1 прочности за каждое получение урона
- Реализуется в battle-service — при обработке action добавляется логика снижения прочности
- После боя обновлённая прочность сохраняется в inventory-service

#### Эффект нулевой прочности
- Предмет остаётся экипированным, но его модификаторы НЕ применяются (как будто пустой слот)
- При проверке `build_modifiers_dict`: если `current_durability == 0`, модификаторы = 0
- Визуально: предмет показывается красным / с иконкой поломки

#### Ремонт-комплекты
| Комплект | Восстановление | item_rarity |
|----------|---------------|-------------|
| Обычный ремонт-комплект | 25% от max_durability | common |
| Редкий ремонт-комплект | 50% от max_durability | rare |
| Эпический ремонт-комплект | 75% от max_durability | epic |
| Легендарный ремонт-комплект | 100% от max_durability | legendary |

- item_type = "resource", с маркером `repair_power` (int: 25/50/75/100)
- Любой игрок может использовать ремонт-комплект
- Кузнец крафтит их по рецептам

#### Эндпоинт ремонта
`POST /inventory/{character_id}/repair-item`
- Body: `{ "inventory_item_id": int, "repair_kit_item_id": int, "source": "inventory"|"equipment" }`
- Валидация: предмет имеет прочность, ремонт-комплект в инвентаре
- Логика: current_durability += repair_power% от max_durability (cap at max)
- Если предмет экипирован и был сломан (был 0, стал >0): применить модификаторы обратно
- Ремонт-комплект расходуется

### Часть 2: Карточка предмета (Item Detail Card)

#### Описание
При нажатии на предмет в инвентаре и кнопку "Описание" открывается полная карточка предмета с детальной информацией.

#### Содержимое карточки
- **Изображение** предмета (крупное)
- **Название** с бейджем заточки (+N) если есть
- **Тип** и **редкость** (с цветом)
- **Описание** (текстовое)
- **Прочность** — полоска current/max (если предмет имеет прочность)
- **Статы/модификаторы** — полный список с учётом заточки
- **Заточка** — потрачено поинтов X/15, детали по статам
- **Камни/Руны в слотах** — список вставленных с их бонусами
- **Опознание** — статус опознан/нет

#### UX
1. Правый клик на предмете → "Описание" в контекстном меню
2. Открывается модальное окно с полной информацией
3. Красивая карточка в стиле RPG, с разделителями по секциям

### Edge Cases
- Что если предмет без прочности? → Секция прочности не показывается
- Что если прочность 0? → Красная полоска, текст "Сломан", иконка поломки
- Что если предмет неопознан? → Карточка показывает "???" вместо статов
- Что если нет ремонт-комплекта? → "Нет ремонт-комплектов"
- Что если предмет уже полной прочности? → Кнопка ремонта неактивна

---

## 2. Codebase Analysis (Analyst)

### 2.1. Items model (`services/inventory-service/app/models.py`)

**Current state:** `Items` table has ~60 columns covering modifiers, damage types, sockets, buff fields, etc. No durability fields exist.

**Fields to add:**
- `max_durability = Column(Integer, default=0)` — 0 means "no durability system for this item type". Positive value = max durability (e.g. 100).
- `repair_power = Column(Integer, nullable=True)` — Only set on repair kit items. Values: 25/50/75/100 (percent of max_durability restored).

### 2.2. CharacterInventory and EquipmentSlot models

**CharacterInventory** (`character_inventory` table): per-instance fields are `is_identified`, `enhancement_points_spent`, `enhancement_bonuses` (JSON), `socketed_gems` (JSON).

**EquipmentSlot** (`equipment_slots` table): per-instance fields are `is_enabled`, `enhancement_points_spent`, `enhancement_bonuses` (JSON), `socketed_gems` (JSON).

**Fields to add to both:**
- `current_durability = Column(Integer, nullable=True)` — NULL means "full durability" (equals max_durability from Items template). When explicitly set, tracks actual wear. 0 = broken.

### 2.3. `build_modifiers_dict` (`services/inventory-service/app/crud.py`, line 355)

**Current signature:** `build_modifiers_dict(item_obj, negative=False, enhancement_bonuses=None, gem_items=None) -> dict`

Builds a dict of all non-zero modifiers from the item, enhancement bonuses, and gem bonuses. Called during equip/unequip to send deltas to character-attributes-service.

**Change needed:** Add optional parameter `current_durability: Optional[int] = None`. If `item_obj.max_durability > 0` and `current_durability == 0`, return empty dict `{}` (item is broken, provides no stats). This is the single gatekeeper — all equip/apply flows pass through this function.

### 2.4. Equip/unequip flow (`services/inventory-service/app/main.py`)

**Equip flow (line 289):**
1. Validates item exists, is in inventory, is identified
2. Finds slot via `find_equipment_slot_for_item`
3. If slot occupied: returns old item to inventory (copies enhancement_points_spent, enhancement_bonuses, socketed_gems), subtracts old modifiers
4. Reduces inventory quantity, sets slot.item_id, copies enhancement data
5. Applies positive modifiers via `apply_modifiers_in_attributes_service`
6. Commits, recalcs fast slots

**Changes needed for equip:**
- Copy `current_durability` from inventory row to equipment slot (step 4)
- Pass `current_durability` to `build_modifiers_dict` so broken items apply zero mods (step 5)
- When old item is unequipped back to inventory, copy `current_durability` from slot to inventory row (step 3)

**Unequip flow (line 428):** Mirror of equip — same changes needed for durability transfer.

### 2.5. Battle-service action flow (`services/battle-service/app/main.py`)

**`_make_action_core` (line 975)** — the core turn logic:

1. Load Redis battle state
2. Validate ownership, turn order
3. Decrement buff durations / cooldowns
4. Validate skill ownership
5. Fetch attacker attributes + weapon
6. **SUPPORT** skill — apply self/enemy effects
7. **DEFENSE** skill — apply self/enemy effects
8. **ITEM** usage from fast slot
9. **ATTACK** skill — compute damage via `compute_damage_with_rolls`, subtract HP, apply enemy effects
10. Pay skill costs, set cooldowns
11. Check HP <= 0 → finish battle if someone dies
12. Write turn to DB, update Redis state

**Durability loss injection points:**
- **Weapon durability (-1 per attack):** After section 9 (ATTACK skill), when `attack_id` is set and damage was dealt. Decrement durability of attacker's `main_weapon` and `additional_weapons` in battle state.
- **Armor durability (-1 per damage received):** Also in section 9, after damage is dealt to defender. Decrement durability of defender's `head`, `body`, `cloak` in battle state.

### 2.6. Battle-service snapshot (`build_participant_info`, line 125)

**Current snapshot** (stored in Redis + MongoDB) contains: `participant_id`, `character_id`, `name`, `avatar`, `attributes`, `skills`, `fast_slots`.

**Equipment durability is NOT in the snapshot.** The snapshot is read-only (used for display). The mutable battle state (`battle_state["participants"]`) tracks HP, mana, energy, stamina, buffs, cooldowns.

**Design decision:** Add equipment durability data to `battle_state["participants"][pid]` at battle start. This will be a new dict `equipment_durability` mapping slot_type to `{item_id, current_durability, max_durability}`. This keeps it mutable during battle without changing the snapshot schema.

### 2.7. Battle-service → inventory-service communication

**Current communication:**
- `inventory_client.py` has: `get_item()`, `consume_item()`, `get_fast_slots()`
- `battle_engine.py` has: `fetch_main_weapon()` — calls `GET /inventory/{cid}/equipment` and `GET /inventory/items/{item_id}`
- At battle end: resources (HP, mana, energy, stamina) are synced via direct SQL `UPDATE character_attributes` (line 1346)

**No existing endpoint for updating equipment state from battle-service.** Need to create `POST /inventory/internal/update-durability` that battle-service calls at battle end to persist durability changes.

### 2.8. Frontend ItemContextMenu (`services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/ItemContextMenu.tsx`)

**Current actions:**
1. "Описание" — placeholder, shows toast "Описание предмета скоро будет доступно"
2. "Опознать" — for unidentified items
3. "Снять" — for equipped items
4. "Надеть" — for equipment items in inventory
5. "Использовать" — for consumables/buff items
6. "Изучить" — for recipe items
7. "Выбросить" / "Удалить" — drop items
8. "Бросить на локацию" — drop to location
9. "Продать" — placeholder

**Changes needed:**
- "Описание" → open ItemDetailModal instead of toast
- Add "Починить" action for items with durability (opens repair kit selector or directly repairs)

### 2.9. Frontend ItemCell (`services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/ItemCell.tsx`)

Shows item image, rarity border, quantity badge, enhancement badge, unidentified overlay. **No durability indicator.**

**Changes needed:** Add durability bar overlay at the bottom of the cell when item has `max_durability > 0`. Red bar when durability = 0.

### 2.10. Frontend types (`services/frontend/app-chaldea/src/redux/slices/profileSlice.ts`)

- `ItemData` — needs `max_durability`, `repair_power` fields
- `InventoryItem` — needs `current_durability` field
- `EquipmentSlotData` — needs `current_durability` field

---

## 3. Architecture Design (Architect)

### 3.1. DB Changes — Migration 014

**File:** `services/inventory-service/app/alembic/versions/014_add_durability_system.py`

```sql
-- items table: template-level durability + repair power
ALTER TABLE items ADD COLUMN max_durability INT NOT NULL DEFAULT 0;
ALTER TABLE items ADD COLUMN repair_power INT DEFAULT NULL;

-- character_inventory: per-instance durability
ALTER TABLE character_inventory ADD COLUMN current_durability INT DEFAULT NULL;

-- equipment_slots: per-instance durability
ALTER TABLE equipment_slots ADD COLUMN current_durability INT DEFAULT NULL;

-- Seed 4 repair kit items
INSERT INTO items (name, item_type, item_rarity, item_level, max_stack_size, is_unique, repair_power, description)
VALUES
  ('Обычный ремонт-комплект', 'resource', 'common', 1, 99, 0, 25, 'Восстанавливает 25% прочности предмета'),
  ('Редкий ремонт-комплект', 'resource', 'rare', 1, 99, 0, 50, 'Восстанавливает 50% прочности предмета'),
  ('Эпический ремонт-комплект', 'resource', 'epic', 1, 99, 0, 75, 'Восстанавливает 75% прочности предмета'),
  ('Легендарный ремонт-комплект', 'resource', 'legendary', 1, 99, 0, 100, 'Восстанавливает 100% прочности предмета');
```

**Null semantics for `current_durability`:** NULL = full (equals max_durability). Explicit 0 = broken. This avoids needing to update all existing rows.

### 3.2. Inventory-service changes

#### 3.2.1. Models (`models.py`)

Add to `Items`:
```python
max_durability = Column(Integer, default=0)
repair_power = Column(Integer, nullable=True)
```

Add to `CharacterInventory`:
```python
current_durability = Column(Integer, nullable=True)
```

Add to `EquipmentSlot`:
```python
current_durability = Column(Integer, nullable=True)
```

#### 3.2.2. Schemas (`schemas.py`)

Add to `ItemBase`:
```python
max_durability: int = 0
repair_power: Optional[int] = None
```

Add to `EquipmentSlotBase`:
```python
current_durability: Optional[int] = None
```

Add new schemas:
```python
class RepairItemRequest(BaseModel):
    inventory_item_id: int      # ID of inventory row or equipment slot ID
    repair_kit_item_id: int     # item_id of the repair kit
    source: str                 # "inventory" or "equipment"

class RepairItemResponse(BaseModel):
    success: bool
    new_durability: int
    max_durability: int
    repair_kit_consumed: bool

class UpdateDurabilityEntry(BaseModel):
    slot_type: str
    new_durability: int

class UpdateDurabilityRequest(BaseModel):
    character_id: int
    entries: List[UpdateDurabilityEntry]

class ItemDetailResponse(BaseModel):
    """Full item card data."""
    item: Item
    current_durability: Optional[int] = None
    max_durability: int = 0
    enhancement_points_spent: int = 0
    enhancement_bonuses: Optional[dict] = None
    socketed_gems: Optional[list] = None
    is_identified: bool = True
    source: str  # "inventory" or "equipment"
```

#### 3.2.3. `build_modifiers_dict` changes (`crud.py`)

```python
def build_modifiers_dict(item_obj, negative=False, enhancement_bonuses=None, gem_items=None, current_durability=None):
    # NEW: if item has durability system and is broken, return empty
    if item_obj.max_durability > 0 and current_durability is not None and current_durability <= 0:
        return {}
    # ... rest unchanged
```

#### 3.2.4. Durability constant

```python
DURABILITY_SLOT_TYPES = {'head', 'body', 'cloak', 'main_weapon', 'additional_weapons'}
```

#### 3.2.5. Equip/unequip changes (`main.py`)

**Equip:** After `slot.item_id = db_item.id`, also copy:
```python
slot.current_durability = inv_slot.current_durability
```
Pass `current_durability=slot.current_durability` to `build_modifiers_dict` calls.

**Unequip:** When returning item to inventory, copy:
```python
new_inv_row.current_durability = slot.current_durability
```

**Old item swap during equip:** Similarly copy `current_durability` from slot to new inventory row.

#### 3.2.6. New endpoint: `POST /inventory/{character_id}/repair-item`

Logic:
1. Find repair kit in inventory by `repair_kit_item_id`, verify `repair_power` is set
2. Find target item by `inventory_item_id` + `source` ("inventory" → CharacterInventory row, "equipment" → EquipmentSlot)
3. Get item template, verify `max_durability > 0`
4. Calculate: `restore_amount = ceil(max_durability * repair_power / 100)`
5. `old_durability = current_durability if current_durability is not None else max_durability`
6. `new_durability = min(old_durability + restore_amount, max_durability)`
7. If source=equipment and old was 0 and new > 0: call `apply_modifiers_in_attributes_service` with positive mods (item "comes alive")
8. Update current_durability, consume 1 repair kit, commit
9. Return new durability values

#### 3.2.7. New endpoint: `GET /inventory/{character_id}/item-detail/{inventory_item_id}`

Query param: `source=inventory|equipment`

Returns `ItemDetailResponse` with full item data including durability, enhancement, gems, identified status.

#### 3.2.8. New internal endpoint: `POST /inventory/internal/update-durability`

Called by battle-service after battle ends. Body: `UpdateDurabilityRequest`.

For each entry: update `equipment_slots.current_durability` where `character_id` and `slot_type` match. If durability drops to 0 from positive: subtract modifiers via `apply_modifiers_in_attributes_service` (negative call). This ensures character stats reflect broken equipment.

### 3.3. Battle-service changes

#### 3.3.1. Equipment durability in battle state

At battle start (`build_participant_info` or battle creation), fetch equipment for each participant and store:

```python
participant["equipment_durability"] = {
    "main_weapon": {"item_id": 5, "current_durability": 100, "max_durability": 100},
    "additional_weapons": {"item_id": 8, "current_durability": 50, "max_durability": 100},
    "head": {"item_id": 12, "current_durability": 80, "max_durability": 100},
    "body": None,  # empty slot
    "cloak": None,
}
```

**Fetch via:** `GET /inventory/{cid}/equipment` — already used by `fetch_main_weapon`. Extend to get all equipment + item details for durability slots.

New function in `inventory_client.py`:
```python
async def get_equipment_durability(character_id: int) -> dict:
    """Returns {slot_type: {item_id, current_durability, max_durability}} for durability-eligible slots."""
```

#### 3.3.2. Durability loss during battle

In `_make_action_core`, after section 9 (ATTACK):

```python
# --- Durability loss ---
WEAPON_SLOTS = ["main_weapon", "additional_weapons"]
ARMOR_SLOTS = ["head", "body", "cloak"]

# Attacker's weapons lose 1 durability per attack
if attack_id and attack_id > 0:
    attacker_equip = participant_info.get("equipment_durability", {})
    for slot_type in WEAPON_SLOTS:
        slot_data = attacker_equip.get(slot_type)
        if slot_data and slot_data["max_durability"] > 0 and slot_data["current_durability"] > 0:
            slot_data["current_durability"] = max(0, slot_data["current_durability"] - 1)
            if slot_data["current_durability"] == 0:
                turn_events.append({"event": "item_broken", "who": request.participant_id, "slot": slot_type})

# Defender's armor loses 1 durability per damage received
if attack_id and attack_id > 0 and any(e.get("event") == "damage" for e in turn_events):
    defender_equip = defender_info.get("equipment_durability", {})
    for slot_type in ARMOR_SLOTS:
        slot_data = defender_equip.get(slot_type)
        if slot_data and slot_data["max_durability"] > 0 and slot_data["current_durability"] > 0:
            slot_data["current_durability"] = max(0, slot_data["current_durability"] - 1)
            if slot_data["current_durability"] == 0:
                turn_events.append({"event": "item_broken", "who": defender_pid, "slot": slot_type})
```

#### 3.3.3. Persist durability after battle

In the battle finish block (section 10.5, after line 1342), after resource sync:

```python
# Sync equipment durability back to inventory-service
for pid_str, pdata in battle_state["participants"].items():
    equip_dur = pdata.get("equipment_durability", {})
    entries = []
    for slot_type, slot_data in equip_dur.items():
        if slot_data and slot_data["max_durability"] > 0:
            entries.append({"slot_type": slot_type, "new_durability": slot_data["current_durability"]})
    if entries:
        try:
            await update_durability(pdata["character_id"], entries)
        except Exception as e:
            logger.error(f"Failed to sync durability for character {pdata['character_id']}: {e}")
```

New function in `inventory_client.py`:
```python
async def update_durability(character_id: int, entries: list[dict]) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{BASE}/inventory/internal/update-durability",
            json={"character_id": character_id, "entries": entries},
        )
        r.raise_for_status()
        return r.json()
```

### 3.4. Frontend changes

#### 3.4.1. Types (`profileSlice.ts`)

```typescript
// Add to ItemData:
max_durability: number;
repair_power: number | null;

// Add to InventoryItem:
current_durability: number | null;

// Add to EquipmentSlotData:
current_durability: number | null;
```

#### 3.4.2. API (`api/inventoryApi.ts` — new or extend existing)

```typescript
export const repairItem = (characterId: number, body: RepairItemRequest) =>
  axios.post(`${BASE_URL}/inventory/${characterId}/repair-item`, body);

export const getItemDetail = (characterId: number, itemId: number, source: string) =>
  axios.get(`${BASE_URL}/inventory/${characterId}/item-detail/${itemId}`, { params: { source } });
```

#### 3.4.3. Redux actions (`profileSlice.ts`)

```typescript
export const repairItem = createAsyncThunk('profile/repairItem', ...);
export const fetchItemDetail = createAsyncThunk('profile/fetchItemDetail', ...);
```

#### 3.4.4. ItemDetailModal (new component)

`services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/ItemDetailModal.tsx`

Full-screen modal with:
- Large item image with rarity border
- Name + enhancement badge
- Type / rarity / level
- Description text
- Durability bar (if max_durability > 0): green/yellow/red gradient, "current/max" text
- Stats/modifiers table with enhancement bonuses highlighted
- Socket slots with gem names
- Identification status

Design: Tailwind, responsive (360px+), uses design system tokens (`modal-overlay`, `modal-content`, `gold-text`, etc.).

#### 3.4.5. Durability bar in ItemCell and EquipmentSlot

Small horizontal bar at the bottom of the cell:
- Green (>50%), Yellow (25-50%), Red (<25%), Empty+Red when 0
- Only shown when `max_durability > 0`
- Width: proportional to `current_durability / max_durability`
- When 0: add red tint overlay or broken icon

#### 3.4.6. ItemContextMenu changes

- "Описание" → dispatch action to open ItemDetailModal with item data
- "Починить" → new action, shown when item has `max_durability > 0` and `current_durability < max_durability`. Opens repair flow (select repair kit from inventory, call repair endpoint).

### 3.5. Cross-service impact analysis

| Change | Affected services | Risk |
|--------|-------------------|------|
| `items.max_durability` column | inventory-service, photo-service (mirror), admin panel | LOW — additive column, default 0 |
| `items.repair_power` column | inventory-service, photo-service (mirror) | LOW — nullable, no existing code reads it |
| `character_inventory.current_durability` | inventory-service | LOW — nullable, NULL = full |
| `equipment_slots.current_durability` | inventory-service | LOW — nullable, NULL = full |
| `build_modifiers_dict` signature | inventory-service equip/unequip, admin | MEDIUM — callers must pass new param |
| New internal endpoint | inventory-service, battle-service | LOW — new endpoint, no existing callers |
| Battle state schema | battle-service, autobattle-service, frontend (battle UI) | MEDIUM — new field in participants |
| Frontend types | profileSlice, ItemCell, EquipmentSlot, ItemContextMenu | LOW — additive fields |

### 3.6. Nginx changes

None required — all new endpoints use existing service path prefixes (`/inventory/...` and `/battle/...`).

### 3.7. photo-service mirror models

photo-service mirrors `Items` model. After migration 014 adds `max_durability` and `repair_power`, photo-service's mirror model should also add these columns. However, since photo-service only reads/updates specific fields (image URLs), this is non-blocking — the columns will exist in the DB and photo-service will simply ignore them unless its mirror model is updated.

**Recommendation:** Update photo-service mirror model in a follow-up task if needed. Not a blocker.

---

## 4. Task Breakdown

### Task 1: Migration + Models (Backend Developer)
**Service:** inventory-service
**Files:**
- `services/inventory-service/app/alembic/versions/014_add_durability_system.py` — NEW
- `services/inventory-service/app/models.py` — add `max_durability`, `repair_power` to Items; `current_durability` to CharacterInventory and EquipmentSlot
- `services/inventory-service/app/schemas.py` — add new fields to ItemBase, EquipmentSlotBase; add RepairItemRequest, RepairItemResponse, UpdateDurabilityRequest, UpdateDurabilityEntry, ItemDetailResponse schemas

**Acceptance criteria:**
- Migration runs without errors
- 4 repair kit items seeded
- Models and schemas updated
- `python -m py_compile` passes for all modified files

---

### Task 2: Backend inventory-service logic (Backend Developer)
**Service:** inventory-service
**Files:**
- `services/inventory-service/app/crud.py` — modify `build_modifiers_dict` to accept and check `current_durability`; add `DURABILITY_SLOT_TYPES` constant; add helper `get_effective_durability(item, current_durability) -> int`
- `services/inventory-service/app/main.py` — modify equip/unequip to copy `current_durability`; pass it to `build_modifiers_dict`; add 3 new endpoints: repair-item, item-detail, internal/update-durability

**Dependencies:** Task 1

**Acceptance criteria:**
- `build_modifiers_dict` returns {} for broken items
- Equip/unequip preserves durability between inventory and equipment
- Repair endpoint works: consumes kit, restores durability, re-applies mods if item was broken
- Item-detail endpoint returns full card data
- Internal update-durability works and subtracts mods when item breaks
- `python -m py_compile` passes

---

### Task 3: Backend battle-service (Backend Developer) — DONE
**Service:** battle-service
**Files:**
- `services/battle-service/app/inventory_client.py` — add `get_equipment_durability()`, `update_durability()`
- `services/battle-service/app/main.py` — load equipment durability at battle start; add durability loss in `_make_action_core`; persist durability at battle end
- `services/battle-service/app/redis_state.py` — add `equipment_durability` to initial battle state

**Dependencies:** Task 2 (internal endpoint must exist)

**Acceptance criteria:**
- [x] Equipment durability loaded into battle state at battle start
- [x] Weapon durability decreases by 1 per attack action
- [x] Armor durability decreases by 1 per damage received
- [x] "item_broken" event emitted when durability reaches 0
- [x] Durability persisted to inventory-service at battle end
- [x] `python -m py_compile` passes

---

### Task 4: Frontend types, API, Redux (Frontend Developer)
**Service:** frontend
**Files:**
- `services/frontend/app-chaldea/src/redux/slices/profileSlice.ts` — add durability fields to ItemData, InventoryItem, EquipmentSlotData; add repairItem and fetchItemDetail thunks; add itemDetailModal state
- `services/frontend/app-chaldea/src/api/inventoryApi.ts` — add repair and item-detail API calls (new file or extend existing)

**Dependencies:** Task 2 (API contracts)

**Acceptance criteria:**
- Types compile (`npx tsc --noEmit`)
- Redux actions for repair and item detail work
- State management for ItemDetailModal (open/close, data)

---

### Task 5: Frontend ItemDetailModal (Frontend Developer)
**Service:** frontend
**Files:**
- `services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/ItemDetailModal.tsx` — NEW
- `services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/ItemContextMenu.tsx` — "Описание" opens modal

**Dependencies:** Task 4

**Acceptance criteria:**
- Modal opens from context menu "Описание"
- Shows all item info: image, name, type, rarity, description, durability bar, modifiers, enhancement, gems, identification
- Responsive (360px+)
- Tailwind only (no SCSS)
- `npx tsc --noEmit` and `npm run build` pass

---

### Task 6: Frontend durability display + repair UI (Frontend Developer)
**Service:** frontend
**Files:**
- `services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/ItemCell.tsx` — add durability bar
- `services/frontend/app-chaldea/src/components/ProfilePage/EquipmentPanel/EquipmentSlot.tsx` — add durability bar
- `services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/ItemContextMenu.tsx` — add "Починить" action
- `services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/RepairModal.tsx` — NEW (repair kit selection modal)

**Dependencies:** Task 4, Task 5

**Acceptance criteria:**
- Durability bar visible on items with max_durability > 0
- Color-coded: green/yellow/red
- Broken items show red overlay or broken icon
- "Починить" action in context menu for items needing repair
- Repair flow: select kit → confirm → API call → success toast → UI updates
- Responsive (360px+)
- `npx tsc --noEmit` and `npm run build` pass

---

### Task 7: QA Tests (QA Test)
**Service:** inventory-service, battle-service
**Files:**
- `services/inventory-service/app/tests/test_durability.py` — NEW
- `services/battle-service/app/tests/test_durability.py` — NEW

**Dependencies:** Tasks 1-3

**Test cases:**
1. `build_modifiers_dict` returns {} when current_durability=0 and max_durability>0
2. `build_modifiers_dict` returns normal mods when current_durability>0
3. `build_modifiers_dict` returns normal mods when max_durability=0 (no durability system)
4. Equip copies current_durability from inventory to slot
5. Unequip copies current_durability from slot to inventory
6. Repair endpoint: validates repair kit, restores correct percentage, caps at max
7. Repair endpoint: re-applies modifiers when item goes from 0 to >0
8. Repair endpoint: rejects if item has no durability
9. Repair endpoint: consumes repair kit
10. Internal update-durability endpoint: updates correct slots
11. Internal update-durability: subtracts mods when durability drops to 0
12. Battle: weapon durability decreases on attack
13. Battle: armor durability decreases on damage received
14. Battle: item_broken event emitted at 0
15. Battle: durability persisted after battle end

---

### Task 8: Review (Reviewer)
**Dependencies:** Tasks 1-7

**Checklist:**
- Migration runs cleanly, rollback works
- All 3 services compile
- Cross-service contracts match (inventory internal endpoint ↔ battle client)
- Frontend builds (`tsc --noEmit` + `npm run build`)
- Live verification: equip/unequip with durability, repair flow, battle durability loss
- Mobile responsive (360px+)
- No SCSS added (Tailwind only)
- No `React.FC`
- Error messages in Russian for user-facing endpoints

---

## 5. API Contracts

### 5.1. `POST /inventory/{character_id}/repair-item`

**Auth:** JWT (user must own character)

**Request:**
```json
{
  "inventory_item_id": 42,
  "repair_kit_item_id": 101,
  "source": "equipment"
}
```
- `inventory_item_id`: For source="inventory" — CharacterInventory.id. For source="equipment" — EquipmentSlot.id.
- `repair_kit_item_id`: item_id of the repair kit item (must be in character's inventory)
- `source`: "inventory" or "equipment"

**Response 200:**
```json
{
  "success": true,
  "new_durability": 75,
  "max_durability": 100,
  "repair_kit_consumed": true
}
```

**Errors:**
- 400: "Предмет не имеет прочности"
- 400: "Предмет уже имеет полную прочность"
- 404: "Предмет не найден"
- 404: "Ремонт-комплект не найден"
- 400: "Этот предмет не является ремонт-комплектом"

---

### 5.2. `GET /inventory/{character_id}/item-detail/{inventory_item_id}?source=inventory|equipment`

**Auth:** JWT (user must own character)

**Response 200:**
```json
{
  "item": { ... full Item schema ... },
  "current_durability": 50,
  "max_durability": 100,
  "enhancement_points_spent": 3,
  "enhancement_bonuses": {"strength_modifier": 2, "damage_modifier": 1},
  "socketed_gems": [42, null, 15],
  "is_identified": true,
  "source": "inventory"
}
```

---

### 5.3. `POST /inventory/internal/update-durability` (service-to-service)

**Auth:** None (internal endpoint, not exposed via Nginx)

**Request:**
```json
{
  "character_id": 7,
  "entries": [
    {"slot_type": "main_weapon", "new_durability": 85},
    {"slot_type": "head", "new_durability": 0},
    {"slot_type": "body", "new_durability": 45}
  ]
}
```

**Response 200:**
```json
{
  "status": "ok",
  "updated": 3,
  "mods_removed_for": ["head"]
}
```

When `new_durability` = 0 and previous was > 0, subtract modifiers via `apply_modifiers_in_attributes_service`. `mods_removed_for` lists slot_types where this happened.

---

### 5.4. Battle state — equipment_durability schema

Added to `battle_state["participants"][pid]`:
```json
{
  "equipment_durability": {
    "main_weapon": {"item_id": 5, "current_durability": 100, "max_durability": 100},
    "additional_weapons": null,
    "head": {"item_id": 12, "current_durability": 80, "max_durability": 100},
    "body": {"item_id": 15, "current_durability": 100, "max_durability": 100},
    "cloak": null
  }
}
```

---

## 6. Logging

[LOG] 2026-03-26 — Codebase Analyst + Architect: analysis complete, architecture designed, tasks broken down. Status set to IN_PROGRESS.
[LOG] 2026-03-26 — Backend Developer: Task 3 (battle-service durability) выполнен. Добавлены: get_equipment_durability/update_durability в inventory_client.py, equipment_durability в Redis state, потеря прочности оружия/брони в _make_action_core, синхронизация прочности в inventory-service при завершении боя. py_compile пройден.
[LOG] 2026-03-26 — Backend Dev: начал задачи #1 и #2 (миграция + inventory-service backend)
[LOG] 2026-03-26 — Backend Dev: задача #1 завершена — миграция 014_add_durability_system.py создана (max_durability, repair_power, current_durability, 4 ремонт-комплекта). Модели и схемы обновлены.
[LOG] 2026-03-26 — Backend Dev: задача #2 завершена — build_modifiers_dict с проверкой прочности, equip/unequip копируют current_durability, 3 новых эндпоинта (repair-item, item-detail, internal/update-durability). py_compile пройден для 5 файлов.

---

## 7. Summary (filled by PM after completion — in Russian)

*Pending...*
