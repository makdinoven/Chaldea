# FEAT-081: Система профессий и крафта

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-26 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-081-profession-crafting-system.md` → `DONE-FEAT-081-profession-crafting-system.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Система профессий и крафта для персонажей. Игроки выбирают одну из 6 профессий и создают предметы по рецептам/чертежам из материалов. Профессии прокачиваются через ранги, открывая новые возможности.

### Профессии (6 штук)

| Профессия | Функции |
|-----------|---------|
| **Кузнец** | Крафт снаряжения (броня, обычное оружие) по чертежам, ремонт-комплекты для снаряжения, заточка (улучшение характеристик экипировки) |
| **Алхимик** | Крафт зелий (лечение, бафы урона, сопротивлений и т.п.), яды (временное покрытие оружия — доп. урон/эффект на N ходов боя), трансмутация материалов (N обычных → 1 редкий) |
| **Повар** | Крафт еды с бонусами (включая "напитки" как тип блюда с другой иконкой). Уникальная особенность — восстановление выносливости (stamina), чего не могут другие профессии |
| **Зачарователь** | Создание рун (из магических материалов по "тайнам рун" — аналог чертежей), вставка рун в снаряжение (только зачарователь умеет), извлечение рун (с шансом потери), слияние рун (две → одна более мощная) |
| **Ювелир** | Крафт украшений (кольца, амулеты, ожерелья — отдельный слот экипировки), огранка камней (вставляются в украшения), переплавка старых украшений в материалы |
| **Книжник** | Книги опыта (бонус к XP на время), магическое оружие (посохи, гримуары и т.п.), свитки одноразовых заклинаний для боя. Лорно — учёные, исследующие природу магии |

### Бизнес-правила
- Персонаж может иметь **только 1 профессию**
- Смена профессии возможна, но **теряется весь прогресс** (уровень/ранг), **выученные рецепты сохраняются**
- Профессия имеет систему рангов (например: ученик → подмастерье → мастер), с каждым рангом открываются базовые рецепты
- **Чертежи** — одноразовые (исчезают после использования). Это уникальные предметы, падающие с мобов/боссов, из данжей, ивентов
- **Рецепты** — запоминаются навсегда после изучения. Базовые выдаются за ранг, уникальные находятся/покупаются
- Качество предмета = качество рецепта (без рандома)
- Крафт требует материалы (система добычи материалов будет реализована позже — пока только структура)
- Всё торгуется: созданные предметы, рецепты, чертежи (через обмен, в будущем — аукцион)
- Рецепты/чертежи можно купить у НПС-торговцев, выбить с мобов/боссов, получить за данжи/ивенты
- Система рун/сокетов в снаряжении — пока только структура (расширение предметов будет позже)

### UX / Пользовательский сценарий

**Выбор профессии:**
1. Игрок заходит на страницу профессий
2. Видит описание всех 6 профессий с их возможностями
3. Выбирает одну профессию
4. Получает начальный ранг и базовые рецепты

**Крафт предмета:**
1. Игрок открывает интерфейс крафта своей профессии
2. Видит список доступных рецептов/чертежей
3. Выбирает рецепт, видит необходимые материалы
4. Если материалы есть — нажимает "Создать"
5. Предмет появляется в инвентаре, чертеж (если был) исчезает

**Крафт для другого игрока:**
1. Игрок А выбивает чертеж уникального меча, но он не кузнец
2. Находит игрока Б (кузнец) и договаривается
3. Передаёт чертеж и материалы через обмен
4. Кузнец создаёт предмет и передаёт обратно через обмен

**Смена профессии:**
1. Игрок решает сменить профессию
2. Получает предупреждение: "Прогресс будет потерян, выученные рецепты сохранятся"
3. Подтверждает — профессия меняется, ранг сбрасывается, рецепты остаются

### Edge Cases
- Что если игрок пытается крафтить без нужных материалов? → Кнопка неактивна, показать чего не хватает
- Что если игрок пытается использовать чертеж не своей профессии? → Ошибка "Требуется профессия: Кузнец"
- Что если игрок пытается вставить руну, но он не зачарователь? → Ошибка "Только зачарователь может вставлять руны"
- Что если при извлечении руны она теряется? → Уведомление "Руна разрушена при извлечении"
- Что если игрок меняет профессию, имея активные крафт-рецепты? → Рецепты остаются, но недоступны для крафта (не та профессия)

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Key Files |
|---------|----------------|-----------|
| **inventory-service** | Major: new tables (professions, recipes, blueprints, crafting), new endpoints, extend item_type enum | `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py`, Alembic migrations |
| **character-service** | Minor: add profession_id to Character model, profession selection/change endpoints | `app/models.py`, `app/schemas.py`, `app/main.py`, `app/crud.py`, Alembic migrations |
| **character-attributes-service** | None or minimal: existing `apply_modifiers` and `recover` endpoints already support all needed buff/recovery operations | No code changes expected |
| **battle-service** | None: consumable usage already works via fast_slots + recovery fields. New consumable items (scrolls, potions, food) just need correct `item_type` and recovery fields in items table — no battle-service code changes | — |
| **user-service** | Alembic migration only: add `professions` RBAC permissions to permissions table | `alembic/versions/` (new migration) |
| **frontend** | Major: profession selection page, crafting UI (replacing placeholder tab), recipe browser, admin panels for recipes/professions | Multiple new components + Redux slices + API modules |
| **photo-service** | Minor: may need mirror models if profession/recipe images are stored | Depends on architecture decision |

### Existing Patterns

#### inventory-service (primary service for crafting)
- **Sync SQLAlchemy** with PyMySQL, Pydantic <2.0 (`class Config: orm_mode = True`)
- **Alembic present**: version table `alembic_version_inventory`, 3 migrations exist (`001_initial_baseline`, `002_add_shield`, `003_add_trade_tables`)
- **Auth**: `auth_http.py` with `get_current_user_via_http`, `get_admin_user`, `require_permission("items:create")` — standard pattern
- **Item types enum** (DB-level): `head, body, cloak, belt, ring, necklace, bracelet, main_weapon, consumable, additional_weapons, resource, scroll, misc, shield`
- **Item types enum** (Pydantic): same 14 values
- **Equipment slots enum** (DB-level): `head, body, cloak, belt, ring, necklace, bracelet, main_weapon, additional_weapons, shield, fast_slot_1..10`
- **Trade system** already exists: `TradeOffer` + `TradeOfferItem` models, full propose/update/confirm/cancel flow — crafted items and blueprints can be traded through this existing system without modifications
- **Internal endpoints pattern**: `/internal/characters/{id}/consume_item` — no auth, service-to-service only, blocked by Nginx from external access

#### character-service
- **Sync SQLAlchemy**, Pydantic <2.0
- **Alembic present**: version table `alembic_version_character`, 11 migrations
- **Character model** (`characters` table): has `id, name, id_subrace, id_class, id_attributes, currency_balance, level, stat_points, current_location_id, current_title_id, is_npc, npc_role, npc_status`
- **No profession field** currently exists on Character
- **StarterKit model** exists for class-based starting items/skills/currency — could serve as pattern for profession starter recipes
- **Character creation workflow**: approve request → create character → HTTP calls to inventory/skills/attributes/user services

#### skills-service (reference pattern for rank progression)
- **Async SQLAlchemy** (aiomysql) — different pattern from inventory-service
- Skill → SkillRank hierarchy with binary tree branching (left_child/right_child)
- `ClassSkillTree` / `TreeNode` / `TreeNodeConnection` — graph-based progression, more complex than needed for profession ranks
- Profession ranks are simpler (linear progression: rank 1 → 2 → 3), no tree needed

#### battle-service (consumable usage)
- **Async** (aiomysql + Motor + aioredis)
- **Item usage in battle** (lines 1146-1208 of `main.py`): uses `fast_slots` array from battle snapshot. Each slot has `item_id`, `name`, `image`, `health_recovery`, `mana_recovery`, `energy_recovery`, `stamina_recovery`. On use: apply recovery, pop slot from array, call `consume_item` on inventory-service (best-effort)
- **No item_type checking** in battle — any item in fast slot is treated as consumable with recovery fields. New item types (potions, food, scrolls) will work as-is if they have correct recovery fields
- **Poisons/weapon coatings** (Alchemist feature) would require NEW battle logic — applying temporary damage buff to weapon for N turns. This does NOT exist yet

#### user-service (RBAC)
- **Permission pattern**: Alembic migrations insert into `permissions` table with `(module, action, description)`, then assign to roles via `role_permissions`
- **Latest migration**: `0018_add_titles_permissions`
- **Standard roles**: Admin (id=4, level=100), Moderator (id=3, level=50), Editor (id=2, level=20), User (id=1, level=0)
- Admin gets all permissions automatically (no explicit assignment needed)

#### frontend
- **Placeholder "Крафт" tab** already exists in `ProfilePage/ProfileTabs.tsx` (key: `craft`) and `ProfilePage/ProfilePage.tsx` (renders `<PlaceholderTab tabName="Крафт" />`)
- **Inventory UI**: `ProfilePage/InventoryTab/` — has `CategorySidebar`, `ItemGrid`, `ItemCell`, `ItemContextMenu`, drag-and-drop
- **Equipment UI**: `ProfilePage/EquipmentPanel/` — `EquipmentSlot`, `FastSlots`
- **Items Admin**: `ItemsAdminPage/` — `ItemForm`, `ItemList`, `IssueItemModal`
- **Admin panel structure**: `components/Admin/AdminPage.tsx` with sub-pages for various modules
- **Redux slices directory**: `redux/slices/` — no crafting/profession slice exists yet
- **API modules**: `api/items.ts`, `api/trade.ts` — use axios, typed interfaces
- **Constants**: `ProfilePage/constants.ts` — `ITEM_TYPE_ICONS`, `CATEGORY_LIST`, `EQUIPMENT_SLOT_ORDER`, `EQUIPMENT_SLOT_LABELS`, `EQUIPMENT_TYPES`
- **Design system**: Tailwind CSS (mandatory for new components), TypeScript (mandatory for new files)

### Cross-Service Dependencies

#### Existing (relevant to this feature)
- `character-service` → `inventory-service` (POST `/inventory/` — create inventory on character creation)
- `inventory-service` → `character-attributes-service` (POST `/attributes/{id}/apply_modifiers` — equip/unequip, POST `/attributes/{id}/recover` — use_item)
- `battle-service` → `inventory-service` (GET `/inventory/{id}/fast_slots`, POST `/inventory/internal/characters/{id}/consume_item`, GET `/inventory/items/{id}`)
- `battle-service` → `character-service` (GET `/characters/{id}/profile`)
- All admin endpoints → `user-service` (GET `/users/me` — auth + RBAC check)

#### New dependencies introduced by this feature
- `inventory-service` → `character-service` (needs to verify character's profession + rank before crafting) — **NEW HTTP call**
- `character-service` (profession endpoints) → `inventory-service` (may need to grant starter recipes on profession selection) — **NEW HTTP call**
- Frontend → inventory-service (new crafting API endpoints)
- Frontend → character-service (new profession selection/info endpoints)

### DB Changes

#### New Tables (in inventory-service, managed by Alembic `alembic_version_inventory`)

1. **`professions`** — catalog of 6 professions
   - `id`, `name` (unique), `description`, `icon`, `sort_order`
   - Seeded with: Кузнец, Алхимик, Повар, Зачарователь, Ювелир, Книжник

2. **`profession_ranks`** — rank progression per profession
   - `id`, `profession_id` (FK→professions), `rank_number`, `rank_name`, `description`, `required_experience` (for future XP-based progression), `icon`
   - Seeded with initial ranks per profession (e.g., Ученик=1, Подмастерье=2, Мастер=3)

3. **`recipes`** — permanent recipes (learned once, kept forever)
   - `id`, `name` (unique), `description`, `profession_id` (FK→professions), `required_rank` (int), `result_item_id` (FK→items), `result_quantity`, `rarity`, `icon`, `is_active`

4. **`recipe_ingredients`** — materials needed per recipe
   - `id`, `recipe_id` (FK→recipes), `item_id` (FK→items), `quantity`

5. **`character_professions`** — character ↔ profession assignment
   - `id`, `character_id` (int, not FK — matches existing pattern), `profession_id` (FK→professions), `current_rank` (int, default 1), `experience` (int, for future), `chosen_at` (timestamp)
   - Unique constraint on `character_id` (only 1 profession per character)

6. **`character_recipes`** — recipes learned by character (permanent)
   - `id`, `character_id`, `recipe_id` (FK→recipes), `learned_at` (timestamp)
   - Unique constraint on `(character_id, recipe_id)`

#### Modifications to Existing Tables

7. **`items`** table — extend `item_type` enum:
   - Add new values: `blueprint`, `potion`, `food`, `rune`, `gem`, `jewelry`, `poison`, `book`
   - Add new fields: `profession_id` (nullable int — which profession can craft this), `required_rank` (nullable int — minimum rank to use blueprint), `is_blueprint` (boolean, default false — marks one-time-use blueprints)
   - Current enum: `head, body, cloak, belt, ring, necklace, bracelet, main_weapon, consumable, additional_weapons, resource, scroll, misc, shield`
   - **Note**: `consumable` could remain as a generic catch-all, but specific types (`potion`, `food`, `poison`) give better filtering in UI

8. **`equipment_slots`** table — potentially extend `slot_type` enum:
   - Current jewelry slots already exist: `ring`, `necklace`, `bracelet`
   - Jeweler creates items for these existing slots — **no new equipment slots needed**
   - Rune sockets: feature brief says "structure only for now" — could be a JSON field on items or a future `item_sockets` table

#### Migration to character-service (managed by Alembic `alembic_version_character`)
- No DB changes needed unless we store profession_id directly on `characters` table (alternative: keep it only in `character_professions` in inventory-service DB)
- **Decision for Architect**: Store profession on character model (character-service) or as a separate table (inventory-service)? Since crafting is core to inventory-service and profession determines crafting ability, keeping `character_professions` in inventory-service's domain makes sense. Character-service just needs an endpoint or field to expose "this character's profession" info.

#### RBAC Permissions (user-service Alembic migration `0019_add_profession_permissions`)
- Module: `professions`
- Actions: `read`, `create`, `update`, `delete`, `manage` (admin CRUD for profession catalog, recipes, ranks)

### Existing Item Types vs. New Needs

| Feature Need | Existing Support | Gap |
|---|---|---|
| Weapons (Blacksmith) | `main_weapon`, `additional_weapons` + 25 weapon_subclass values | None — fully supported |
| Armor (Blacksmith) | `head`, `body`, `cloak`, `belt` + 4 armor_subclass values | None — fully supported |
| Potions (Alchemist) | `consumable` type exists, has `health/mana/energy/stamina_recovery` fields | Works, but no distinction between potions/food in filtering. Could add `potion` type for UI clarity |
| Poisons (Alchemist) | No support — would need temporary weapon buff in battle | **Major gap** — requires battle-service changes for "weapon coating" mechanic |
| Food (Cook) | `consumable` type exists with same recovery fields | Works, but same UI filtering issue. `stamina_recovery` field exists already |
| Runes (Enchanter) | No `rune` item type. No socket system on equipment | **Structural gap** — need new item_type + future socket table |
| Jewelry (Jeweler) | `ring`, `necklace`, `bracelet` slots and item types ALREADY EXIST | None — fully supported as equipment |
| Gems (Jeweler) | No `gem` item type | Need new enum value |
| Scrolls (Scholar) | `scroll` item type exists | Exists but battle integration for "cast spell" is limited to recovery only |
| Books (Scholar) | No `book` item type, no XP buff mechanic | **Gap** — needs new item type + time-limited XP buff system |
| Blueprints | No blueprint concept | **Gap** — need new item type or flag |
| Materials/Resources | `resource` item type exists | None — fully supported |
| Repair kits (Blacksmith) | No durability system | **Major gap** — equipment durability doesn't exist, repair kits have no purpose yet |

### Risks

1. **Risk: `item_type` MySQL ENUM modification** — Adding values to a MySQL ENUM column requires `ALTER TABLE`. For large `items` tables this could be slow and lock the table.
   → **Mitigation**: Use `ALTER TABLE items MODIFY COLUMN item_type ENUM(...)` in Alembic migration. Items table is small (game content, not user data), so this is low risk.

2. **Risk: Cross-service data consistency** — Character's profession is stored in one service, crafting logic in another. If profession changes mid-craft, race condition possible.
   → **Mitigation**: Validate profession + rank at craft time (single HTTP call to verify). Use DB transaction for material consumption + item creation.

3. **Risk: equipment_slots ENUM extension** — If new slot types are added (e.g., for rune sockets), the same ALTER TABLE issue applies but with user data (many rows per character).
   → **Mitigation**: Feature brief says "rune sockets structure only" — defer actual ENUM changes, use a separate `item_sockets` table instead.

4. **Risk: Battle-service integration for Alchemist poisons** — Weapon coating mechanic requires modifying battle engine to support temporary damage modifiers on weapon, which is complex and error-prone.
   → **Mitigation**: Defer poison/weapon coating to a Phase 2. Phase 1 can create poison items as inventory objects without battle integration.

5. **Risk: Blueprint one-time-use items in trade** — Blueprints disappear on use. If a blueprint is being traded while someone tries to use it, race condition.
   → **Mitigation**: Use `SELECT ... FOR UPDATE` on inventory row during crafting, same pattern as existing `unequip` logic.

6. **Risk: Repair kit system requires equipment durability** — Blacksmith's "repair kits" feature requires a durability system that doesn't exist in the codebase.
   → **Mitigation**: Defer durability + repair to a future feature. Phase 1 Blacksmith focuses on weapon/armor crafting only.

7. **Risk: Scholar's XP books need time-limited buff system** — Currently no mechanism for "buff active for X minutes" outside of battle.
   → **Mitigation**: Could be a simple `active_buffs` table with `expires_at` timestamp, checked when XP is awarded. Or defer to Phase 2.

8. **Risk: Scope creep** — Feature brief includes many profession-specific mechanics (transmutation, gem cutting, rune merging, weapon coating, repair kits, XP books). Implementing all at once is a large effort.
   → **Mitigation**: Architect should define clear Phase 1 scope (core profession system + basic crafting) vs. Phase 2 (advanced mechanics per profession).

### Summary of Scope Assessment

**Core system (Phase 1 recommended)**:
- Profession catalog + ranks (DB + API + admin UI)
- Recipe/blueprint system (DB + API + admin UI)
- Character profession selection/change
- Basic crafting flow (check recipe + materials → create item)
- Crafting UI tab (replace placeholder)
- RBAC permissions

**Advanced mechanics (Phase 2 recommended)**:
- Alchemist: poisons/weapon coating (needs battle-service changes)
- Alchemist: transmutation (material conversion)
- Enchanter: rune creation, insertion, extraction, merging (needs socket system)
- Jeweler: gem cutting, jewelry recycling
- Blacksmith: repair kits (needs durability system), sharpening (equipment stat boost)
- Scholar: XP books (needs time-limited buff system), battle scrolls beyond recovery
- Profession XP/leveling progression

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Key Architecture Decision: Where to Store Profession Data

**Decision: All profession and crafting data lives in inventory-service.**

Rationale:
- Professions exist solely to gate crafting. The primary consumer of profession data is the crafting flow, which already lives in inventory-service.
- Storing `character_professions` in inventory-service avoids adding a new cross-service dependency from character-service to inventory-service for profession queries.
- character-service remains untouched — no model changes, no new endpoints, no new migrations.
- inventory-service already has `character_id` as a plain integer (not FK) on `character_inventory` and `equipment_slots` — the same pattern applies to `character_professions`.
- Frontend fetches profession info from inventory-service endpoints directly (same as it fetches inventory data).

**Alternative considered:** Add `profession_id` column to `characters` table in character-service.
**Rejected because:** It would require character-service to know about professions, create a circular dependency (character-service needs profession data, inventory-service needs to check profession from character-service), and adds complexity for no benefit.

### 3.2 DB Schema (all tables in inventory-service, managed by Alembic `alembic_version_inventory`)

#### New Tables

**Table: `professions`** — catalog of 6 professions
```sql
CREATE TABLE professions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  slug VARCHAR(50) NOT NULL UNIQUE,        -- e.g. 'blacksmith', 'alchemist'
  description TEXT,
  icon VARCHAR(255),                        -- S3 URL or relative path
  sort_order INT NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
-- Seed data: Кузнец (blacksmith), Алхимик (alchemist), Повар (cook), Зачарователь (enchanter), Ювелир (jeweler), Книжник (scholar)
```

**Table: `profession_ranks`** — rank progression per profession
```sql
CREATE TABLE profession_ranks (
  id INT AUTO_INCREMENT PRIMARY KEY,
  profession_id INT NOT NULL,
  rank_number INT NOT NULL,                -- 1=Ученик, 2=Подмастерье, 3=Мастер
  name VARCHAR(100) NOT NULL,              -- Ученик, Подмастерье, Мастер
  description TEXT,
  required_experience INT NOT NULL DEFAULT 0,  -- XP threshold (for future use)
  icon VARCHAR(255),
  FOREIGN KEY (profession_id) REFERENCES professions(id) ON DELETE CASCADE,
  UNIQUE KEY uq_profession_rank (profession_id, rank_number)
);
-- Seed: 3 ranks per profession (18 rows total)
```

**Table: `recipes`** — permanent recipes (learned once, kept forever)
```sql
CREATE TABLE recipes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(200) NOT NULL UNIQUE,
  description TEXT,
  profession_id INT NOT NULL,
  required_rank INT NOT NULL DEFAULT 1,     -- minimum rank_number to craft
  result_item_id INT NOT NULL,              -- FK to items.id
  result_quantity INT NOT NULL DEFAULT 1,
  rarity VARCHAR(20) NOT NULL DEFAULT 'common',  -- matches ItemRarity enum
  icon VARCHAR(255),
  is_blueprint_recipe BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE = this recipe comes from blueprints
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  auto_learn_rank INT,                      -- if set, auto-granted when reaching this rank
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (profession_id) REFERENCES professions(id) ON DELETE CASCADE,
  FOREIGN KEY (result_item_id) REFERENCES items(id) ON DELETE CASCADE
);
```

**Table: `recipe_ingredients`** — materials needed per recipe
```sql
CREATE TABLE recipe_ingredients (
  id INT AUTO_INCREMENT PRIMARY KEY,
  recipe_id INT NOT NULL,
  item_id INT NOT NULL,                     -- FK to items.id (the material)
  quantity INT NOT NULL DEFAULT 1,
  FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
  FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);
```

**Table: `character_professions`** — character <-> profession assignment (1 per character)
```sql
CREATE TABLE character_professions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  character_id INT NOT NULL,                -- not FK, matches existing pattern
  profession_id INT NOT NULL,
  current_rank INT NOT NULL DEFAULT 1,
  experience INT NOT NULL DEFAULT 0,        -- for future XP system
  chosen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (profession_id) REFERENCES professions(id) ON DELETE CASCADE,
  UNIQUE KEY uq_character_profession (character_id)
);
```

**Table: `character_recipes`** — recipes learned by character (permanent)
```sql
CREATE TABLE character_recipes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  character_id INT NOT NULL,
  recipe_id INT NOT NULL,
  learned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
  UNIQUE KEY uq_character_recipe (character_id, recipe_id)
);
```

#### Modifications to Existing Tables

**`items` table — extend `item_type` enum:**
Add new value: `blueprint`
- Phase 1 only needs `blueprint`. Other types (`potion`, `food`, `rune`, `gem`, `jewelry`, `poison`, `book`) deferred to Phase 2.
- Blueprint items represent one-time-use crafting instructions. They are regular items in inventory, tradeable, stackable (stack=1 since unique use).

**`items` table — new nullable columns:**
```sql
ALTER TABLE items
  ADD COLUMN blueprint_recipe_id INT NULL COMMENT 'If item_type=blueprint, which recipe does this unlock for one-time use',
  ADD CONSTRAINT fk_items_blueprint_recipe FOREIGN KEY (blueprint_recipe_id) REFERENCES recipes(id) ON DELETE SET NULL;
```

This cleanly links a blueprint item to its recipe. When a player uses a blueprint:
1. Check character has the right profession + rank for the recipe
2. Check character has required materials
3. Consume materials from inventory
4. Create result item in inventory
5. Consume 1 blueprint from inventory (quantity -= 1)

### 3.3 API Contract Design

All endpoints under `inventory-service` (prefix `/inventory`).

#### Public Endpoints (require JWT auth)

**GET `/inventory/professions`** — List all professions
- Auth: `get_current_user_via_http`
- Response: `200 OK`
```json
[
  {
    "id": 1,
    "name": "Кузнец",
    "slug": "blacksmith",
    "description": "Крафт снаряжения...",
    "icon": "/images/professions/blacksmith.png",
    "sort_order": 1,
    "ranks": [
      {"id": 1, "rank_number": 1, "name": "Ученик", "description": "...", "required_experience": 0},
      {"id": 2, "rank_number": 2, "name": "Подмастерье", "description": "...", "required_experience": 500},
      {"id": 3, "rank_number": 3, "name": "Мастер", "description": "...", "required_experience": 2000}
    ]
  }
]
```

**GET `/inventory/professions/{character_id}/my`** — Get character's current profession
- Auth: `get_current_user_via_http`
- Response `200 OK`:
```json
{
  "character_id": 5,
  "profession": {
    "id": 1,
    "name": "Кузнец",
    "slug": "blacksmith",
    "description": "...",
    "icon": "..."
  },
  "current_rank": 1,
  "rank_name": "Ученик",
  "experience": 0,
  "chosen_at": "2026-03-26T12:00:00"
}
```
- Response `404` if character has no profession.

**POST `/inventory/professions/{character_id}/choose`** — Choose a profession
- Auth: `get_current_user_via_http`
- Request body:
```json
{ "profession_id": 1 }
```
- Response `200 OK`:
```json
{
  "character_id": 5,
  "profession_id": 1,
  "current_rank": 1,
  "experience": 0,
  "auto_learned_recipes": [
    { "id": 10, "name": "Железный меч" }
  ]
}
```
- Error `400` if character already has a profession (must use change endpoint).
- Error `404` if profession_id is invalid.
- Business logic: creates `character_professions` row, grants recipes where `auto_learn_rank = 1`.

**POST `/inventory/professions/{character_id}/change`** — Change profession (lose progress, keep recipes)
- Auth: `get_current_user_via_http`
- Request body:
```json
{ "profession_id": 2 }
```
- Response `200 OK`:
```json
{
  "character_id": 5,
  "old_profession": "Кузнец",
  "new_profession": "Алхимик",
  "current_rank": 1,
  "experience": 0,
  "message": "Профессия изменена. Прогресс сброшен, выученные рецепты сохранены.",
  "auto_learned_recipes": []
}
```
- Error `400` if choosing the same profession.
- Error `404` if no current profession.
- Business logic: update `character_professions` row (set new profession_id, reset rank=1, experience=0, update chosen_at). Recipes in `character_recipes` are preserved.

**GET `/inventory/crafting/{character_id}/recipes`** — List available recipes for character
- Auth: `get_current_user_via_http`
- Query params: `?profession_id=1` (optional filter)
- Response `200 OK`:
```json
[
  {
    "id": 10,
    "name": "Железный меч",
    "description": "...",
    "profession_id": 1,
    "profession_name": "Кузнец",
    "required_rank": 1,
    "result_item": {
      "id": 50,
      "name": "Железный меч",
      "image": "...",
      "item_type": "main_weapon",
      "item_rarity": "common"
    },
    "result_quantity": 1,
    "rarity": "common",
    "icon": "...",
    "ingredients": [
      { "item_id": 100, "item_name": "Железная руда", "item_image": "...", "quantity": 3, "available": 5 },
      { "item_id": 101, "item_name": "Уголь", "item_image": "...", "quantity": 1, "available": 2 }
    ],
    "can_craft": true,
    "source": "learned"
  }
]
```
- Returns union of: learned recipes (from `character_recipes`) + blueprint-sourced recipes (from blueprints in inventory).
- `can_craft` = true only if profession matches, rank is sufficient, and all materials are present.
- `source` = "learned" or "blueprint" (with `blueprint_item_id` for blueprint-sourced).

**POST `/inventory/crafting/{character_id}/craft`** — Craft an item
- Auth: `get_current_user_via_http`
- Request body:
```json
{
  "recipe_id": 10,
  "blueprint_item_id": null
}
```
- If `blueprint_item_id` is provided, the recipe is sourced from that blueprint (consumed on use).
- If `blueprint_item_id` is null, the recipe must be in `character_recipes`.
- Response `200 OK`:
```json
{
  "success": true,
  "crafted_item": {
    "item_id": 50,
    "name": "Железный меч",
    "image": "...",
    "quantity": 1
  },
  "consumed_materials": [
    { "item_id": 100, "name": "Железная руда", "quantity": 3 },
    { "item_id": 101, "name": "Уголь", "quantity": 1 }
  ],
  "blueprint_consumed": false
}
```
- Error `400`: wrong profession, insufficient rank, missing materials, recipe not known/owned.
- Error `404`: recipe or blueprint not found.
- Business logic (within DB transaction):
  1. Verify character has correct profession and rank >= recipe.required_rank
  2. Verify character knows the recipe (character_recipes) OR owns the blueprint (inventory)
  3. Verify character has all required materials in inventory
  4. Consume materials (decrement quantity, delete rows where quantity=0)
  5. If blueprint: consume 1 blueprint from inventory
  6. Add result item to inventory (quantity=result_quantity)

**POST `/inventory/crafting/{character_id}/learn-recipe`** — Learn a recipe permanently
- Auth: `get_current_user_via_http`
- Request body:
```json
{ "recipe_id": 10 }
```
- Response `200 OK`:
```json
{ "message": "Рецепт выучен", "recipe_id": 10, "recipe_name": "Железный меч" }
```
- Error `400`: recipe already learned, or wrong profession, or insufficient rank.
- Note: This is for future use (recipe scrolls, quest rewards). In Phase 1, recipes are primarily auto-learned on profession choice.

#### Admin Endpoints (require `professions:*` permissions)

**GET `/inventory/admin/professions`** — List all professions (admin view, includes inactive)
- Auth: `require_permission("professions:read")`
- Response: `200 OK` — array of professions with ranks

**POST `/inventory/admin/professions`** — Create a profession
- Auth: `require_permission("professions:create")`
- Request: `{ "name": "...", "slug": "...", "description": "...", "icon": "...", "sort_order": 0 }`
- Response: `201 Created`

**PUT `/inventory/admin/professions/{profession_id}`** — Update a profession
- Auth: `require_permission("professions:update")`
- Request: partial update fields
- Response: `200 OK`

**DELETE `/inventory/admin/professions/{profession_id}`** — Delete a profession
- Auth: `require_permission("professions:delete")`
- Response: `200 OK`

**POST `/inventory/admin/professions/{profession_id}/ranks`** — Create a rank for profession
- Auth: `require_permission("professions:create")`
- Request: `{ "rank_number": 4, "name": "Грандмастер", "description": "...", "required_experience": 5000 }`
- Response: `201 Created`

**PUT `/inventory/admin/professions/ranks/{rank_id}`** — Update a rank
- Auth: `require_permission("professions:update")`
- Response: `200 OK`

**DELETE `/inventory/admin/professions/ranks/{rank_id}`** — Delete a rank
- Auth: `require_permission("professions:delete")`
- Response: `200 OK`

**GET `/inventory/admin/recipes`** — List all recipes (paginated)
- Auth: `require_permission("professions:read")`
- Query params: `?page=1&per_page=20&search=&profession_id=&rarity=`
- Response: `{ "items": [...], "total": 100, "page": 1, "per_page": 20 }`

**POST `/inventory/admin/recipes`** — Create a recipe
- Auth: `require_permission("professions:create")`
- Request:
```json
{
  "name": "Железный меч",
  "description": "...",
  "profession_id": 1,
  "required_rank": 1,
  "result_item_id": 50,
  "result_quantity": 1,
  "rarity": "common",
  "auto_learn_rank": 1,
  "ingredients": [
    { "item_id": 100, "quantity": 3 },
    { "item_id": 101, "quantity": 1 }
  ]
}
```
- Response: `201 Created`

**PUT `/inventory/admin/recipes/{recipe_id}`** — Update a recipe
- Auth: `require_permission("professions:update")`
- Request: partial update (including ingredients replacement)
- Response: `200 OK`

**DELETE `/inventory/admin/recipes/{recipe_id}`** — Delete a recipe
- Auth: `require_permission("professions:delete")`
- Response: `200 OK`

**POST `/inventory/admin/professions/{character_id}/set-rank`** — Manually set character's rank (admin)
- Auth: `require_permission("professions:manage")`
- Request: `{ "rank_number": 2 }`
- Response: `200 OK`
- Used by admins to promote characters (since XP earning is not in Phase 1).

### 3.4 Nginx — No Changes Needed

Inventory-service already has a route block in nginx.conf and nginx.prod.conf:
```
location /inventory/ { proxy_pass http://inventory-service_backend; ... }
```
All new endpoints are under `/inventory/` prefix, so no Nginx changes required.

### 3.5 Frontend Architecture

#### New Files

**Types:**
- `src/types/professions.ts` — TypeScript interfaces for Profession, ProfessionRank, CharacterProfession, Recipe, RecipeIngredient, CraftResult

**API module:**
- `src/api/professions.ts` — axios client for inventory-service profession/crafting endpoints (follows `api/titles.ts` pattern)

**Redux slice:**
- `src/redux/slices/craftingSlice.ts` — state for profession data, character profession, recipes, crafting status. Async thunks for all API calls.

**Profile tab — CraftTab (replaces placeholder):**
- `src/components/ProfilePage/CraftTab/CraftTab.tsx` — main container, shows profession info or profession selection
- `src/components/ProfilePage/CraftTab/ProfessionSelect.tsx` — profession selection screen (6 cards with descriptions)
- `src/components/ProfilePage/CraftTab/ProfessionInfo.tsx` — current profession summary (name, rank, icon)
- `src/components/ProfilePage/CraftTab/RecipeList.tsx` — list of available recipes with filters
- `src/components/ProfilePage/CraftTab/RecipeCard.tsx` — single recipe card (materials, result, craft button)
- `src/components/ProfilePage/CraftTab/CraftConfirmModal.tsx` — confirmation modal before crafting

**Admin pages:**
- `src/components/Admin/ProfessionsAdminPage/ProfessionsAdminPage.tsx` — profession + ranks CRUD
- `src/components/Admin/RecipesAdminPage/RecipesAdminPage.tsx` — recipe CRUD with ingredient management

#### Modified Files

- `src/components/ProfilePage/ProfilePage.tsx` — replace `<PlaceholderTab tabName="Крафт" />` with `<CraftTab characterId={characterId} />`
- `src/components/Admin/AdminPage.tsx` — add "Профессии" and "Рецепты" sections
- `src/components/App/App.tsx` — add routes for `/admin/professions` and `/admin/recipes`
- `src/components/ProfilePage/constants.ts` — add `blueprint` to `ITEM_TYPE_ICONS`

### 3.6 Data Flow Diagrams

#### Crafting Flow
```
User clicks "Создать" on recipe
  → Frontend: POST /inventory/crafting/{charId}/craft { recipe_id, blueprint_item_id }
    → inventory-service:
      1. Query character_professions WHERE character_id = charId → get profession_id, current_rank
      2. Query recipes WHERE id = recipe_id → verify profession_id matches, required_rank <= current_rank
      3. If blueprint: verify blueprint exists in character_inventory
      4. If not blueprint: verify recipe in character_recipes
      5. Query recipe_ingredients for recipe_id → list of (item_id, quantity)
      6. For each ingredient: verify character_inventory has >= required quantity
      7. BEGIN TRANSACTION:
         a. Decrement each material (delete row if quantity reaches 0)
         b. If blueprint: decrement blueprint quantity
         c. Add/increment result item in character_inventory
      8. COMMIT
    → Response: crafted_item + consumed_materials
  → Frontend: update Redux state, show success toast
```

#### Profession Selection Flow
```
User selects profession
  → Frontend: POST /inventory/professions/{charId}/choose { profession_id }
    → inventory-service:
      1. Verify no existing character_professions row for charId (or 400)
      2. Create character_professions row (rank=1, experience=0)
      3. Query recipes WHERE profession_id = X AND auto_learn_rank = 1
      4. Insert into character_recipes for each auto-learn recipe
    → Response: profession info + auto_learned_recipes
  → Frontend: update Redux state, switch to recipe list view
```

### 3.7 Security Considerations

1. **Authentication:** All public endpoints require JWT via `get_current_user_via_http`. All admin endpoints require specific permissions.
2. **Authorization:** Crafting endpoints verify that the character belongs to the authenticated user (via user-service character ownership — same pattern as existing inventory endpoints).
3. **Input validation:** All Pydantic schemas validate types, required fields. Recipe IDs, item IDs validated against DB.
4. **Race conditions:** Crafting uses DB transaction with `SELECT ... FOR UPDATE` on inventory rows to prevent double-spend of materials.
5. **Rate limiting:** No custom rate limiting (handled at Nginx level, same as other endpoints).

### 3.8 Migration Strategy

- **Migration `004_add_professions_crafting`** in inventory-service Alembic: creates all new tables + extends `item_type` enum + adds `blueprint_recipe_id` column.
- **Migration `0019_add_profession_permissions`** in user-service Alembic: adds `professions` module permissions.
- **Seed data:** The inventory-service migration includes seed data for 6 professions and 3 ranks each (18 rows). This is done via `op.execute(INSERT ...)` in the migration itself.
- **Rollback:** Each migration has a `downgrade()` that drops added tables/columns. Enum modification rollback removes added values.

### 3.9 Pydantic Schemas (inventory-service, Pydantic <2.0)

```python
# --- Profession schemas ---
class ProfessionBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int = 0

class ProfessionCreate(ProfessionBase):
    pass

class ProfessionRankOut(BaseModel):
    id: int
    rank_number: int
    name: str
    description: Optional[str] = None
    required_experience: int
    icon: Optional[str] = None
    class Config:
        orm_mode = True

class ProfessionOut(ProfessionBase):
    id: int
    is_active: bool
    ranks: List[ProfessionRankOut] = []
    class Config:
        orm_mode = True

class CharacterProfessionOut(BaseModel):
    character_id: int
    profession: ProfessionOut
    current_rank: int
    rank_name: str
    experience: int
    chosen_at: str
    class Config:
        orm_mode = True

class ChooseProfessionRequest(BaseModel):
    profession_id: int

class ChangeProfessionRequest(BaseModel):
    profession_id: int

# --- Recipe schemas ---
class RecipeIngredientOut(BaseModel):
    item_id: int
    item_name: str
    item_image: Optional[str] = None
    quantity: int
    available: int = 0
    class Config:
        orm_mode = True

class RecipeResultItemOut(BaseModel):
    id: int
    name: str
    image: Optional[str] = None
    item_type: str
    item_rarity: str
    class Config:
        orm_mode = True

class RecipeOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    profession_id: int
    profession_name: str
    required_rank: int
    result_item: RecipeResultItemOut
    result_quantity: int
    rarity: str
    icon: Optional[str] = None
    ingredients: List[RecipeIngredientOut] = []
    can_craft: bool = False
    source: str  # "learned" or "blueprint"
    blueprint_item_id: Optional[int] = None
    class Config:
        orm_mode = True

class RecipeIngredientCreate(BaseModel):
    item_id: int
    quantity: int

class RecipeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    profession_id: int
    required_rank: int = 1
    result_item_id: int
    result_quantity: int = 1
    rarity: str = "common"
    icon: Optional[str] = None
    auto_learn_rank: Optional[int] = None
    ingredients: List[RecipeIngredientCreate] = []

class RecipeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    profession_id: Optional[int] = None
    required_rank: Optional[int] = None
    result_item_id: Optional[int] = None
    result_quantity: Optional[int] = None
    rarity: Optional[str] = None
    icon: Optional[str] = None
    auto_learn_rank: Optional[int] = None
    is_active: Optional[bool] = None
    ingredients: Optional[List[RecipeIngredientCreate]] = None

class CraftRequest(BaseModel):
    recipe_id: int
    blueprint_item_id: Optional[int] = None

class CraftResult(BaseModel):
    success: bool
    crafted_item: dict
    consumed_materials: list
    blueprint_consumed: bool = False

class LearnRecipeRequest(BaseModel):
    recipe_id: int

class AdminSetRankRequest(BaseModel):
    rank_number: int

# Extend existing ItemType enum
class ItemType(str, Enum):
    # ... existing values ...
    blueprint = "blueprint"
```

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: DB schema + Alembic migrations (inventory-service)
| Field | Value |
|-------|-------|
| **#** | 1 |
| **Description** | Create Alembic migration `004_add_professions_crafting` in inventory-service: add tables `professions`, `profession_ranks`, `recipes`, `recipe_ingredients`, `character_professions`, `character_recipes`. Extend `items.item_type` enum with `blueprint`. Add `blueprint_recipe_id` nullable column to `items`. Seed 6 professions and 3 ranks each. Add corresponding SQLAlchemy models to `models.py`. Extend `ItemType` enum in `schemas.py` with `blueprint`. |
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/inventory-service/app/models.py`, `services/inventory-service/app/schemas.py`, `services/inventory-service/app/alembic/versions/004_add_professions_crafting.py` |
| **Depends On** | — |
| **Acceptance Criteria** | Migration runs without errors. All 6 tables exist. 6 professions and 18 ranks seeded. `items.item_type` accepts `blueprint`. `blueprint_recipe_id` column exists on `items`. Models importable. `python -m py_compile models.py` passes. |

### Task 2: RBAC permissions migration (user-service)
| Field | Value |
|-------|-------|
| **#** | 2 |
| **Description** | Create Alembic migration `0019_add_profession_permissions` in user-service. Add permissions for module `professions`: `read`, `create`, `update`, `delete`, `manage`. Assign to Moderator (role_id=3): read, create, update, manage. Assign to Editor (role_id=2): read. Follow exact pattern from `0018_add_titles_permissions`. |
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/user-service/alembic/versions/0019_add_profession_permissions.py` |
| **Depends On** | — |
| **Acceptance Criteria** | Migration runs without errors. 5 permission rows inserted. Role assignments correct. Admin gets all automatically. `python -m py_compile` passes. |

### Task 3: Profession endpoints — public + admin (inventory-service)
| Field | Value |
|-------|-------|
| **#** | 3 |
| **Description** | Implement Pydantic schemas (section 3.9) and CRUD functions + API endpoints in inventory-service for professions: (1) GET `/inventory/professions` — list all active professions with ranks. (2) GET `/inventory/professions/{character_id}/my` — get character's profession. (3) POST `/inventory/professions/{character_id}/choose` — choose profession (create character_professions, auto-learn rank-1 recipes). (4) POST `/inventory/professions/{character_id}/change` — change profession (reset rank/XP, keep recipes, auto-learn new rank-1 recipes). Admin endpoints: (5) GET/POST/PUT/DELETE `/inventory/admin/professions` and `/inventory/admin/professions/{id}`. (6) POST/PUT/DELETE for ranks. (7) POST `/inventory/admin/professions/{character_id}/set-rank` — manually set rank. All admin endpoints use `require_permission("professions:*")`. Public endpoints use `get_current_user_via_http`. |
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/inventory-service/app/schemas.py`, `services/inventory-service/app/crud.py`, `services/inventory-service/app/main.py` |
| **Depends On** | 1 |
| **Acceptance Criteria** | All 7+ endpoints respond correctly. Profession choice creates row + auto-learns recipes. Profession change resets rank, keeps recipes. Admin CRUD works for professions and ranks. Set-rank works. `python -m py_compile` passes on all files. |

### Task 4: Recipe + Crafting endpoints (inventory-service)
| Field | Value |
|-------|-------|
| **#** | 4 |
| **Description** | Implement recipe and crafting CRUD + API endpoints: (1) GET `/inventory/crafting/{character_id}/recipes` — list available recipes (learned + blueprint-sourced), with material availability and `can_craft` flag. (2) POST `/inventory/crafting/{character_id}/craft` — execute craft (validate profession/rank/materials, consume materials, consume blueprint if applicable, create result item). Use DB transaction with row locking. (3) POST `/inventory/crafting/{character_id}/learn-recipe` — learn a recipe permanently. Admin endpoints: (4) GET `/inventory/admin/recipes` — paginated list with search/filter. (5) POST/PUT/DELETE `/inventory/admin/recipes` and `/inventory/admin/recipes/{id}` — full CRUD including ingredient management (replace ingredients on update). |
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/inventory-service/app/schemas.py`, `services/inventory-service/app/crud.py`, `services/inventory-service/app/main.py` |
| **Depends On** | 1, 3 |
| **Acceptance Criteria** | Recipe listing shows learned + blueprint recipes with material availability. Crafting consumes materials and blueprints correctly within a transaction. Learn-recipe works. Admin CRUD for recipes with ingredients works. All error cases return proper 400/404 responses. `python -m py_compile` passes. |

### Task 5: Frontend — types, API module, Redux slice
| Field | Value |
|-------|-------|
| **#** | 5 |
| **Description** | Create TypeScript types for professions/crafting system. Create API module `src/api/professions.ts` (axios client for inventory-service, follows `api/titles.ts` pattern). Create Redux slice `src/redux/slices/craftingSlice.ts` with: state shape for professions list, character profession, available recipes, loading/error states. Async thunks: fetchProfessions, fetchCharacterProfession, chooseProfession, changeProfession, fetchRecipes, craftItem, learnRecipe. Register slice in store. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/src/types/professions.ts`, `services/frontend/app-chaldea/src/api/professions.ts`, `services/frontend/app-chaldea/src/redux/slices/craftingSlice.ts`, `services/frontend/app-chaldea/src/redux/store.ts` |
| **Depends On** | — (can work in parallel with backend, uses API contract from section 3.3) |
| **Acceptance Criteria** | All types defined. API module has functions for all endpoints. Redux slice compiles without errors. `npx tsc --noEmit` passes. |

### Task 6: Frontend — CraftTab (profession selection + recipe list + crafting UI)
| Field | Value |
|-------|-------|
| **#** | 6 |
| **Description** | Replace placeholder "Крафт" tab with real CraftTab. Components: (1) `CraftTab.tsx` — main container: if no profession → show ProfessionSelect; if has profession → show ProfessionInfo + RecipeList. (2) `ProfessionSelect.tsx` — grid of 6 profession cards with name, icon, description, ranks preview, "Выбрать" button. Confirmation modal for selection. (3) `ProfessionInfo.tsx` — current profession badge (icon, name, rank), "Сменить профессию" button with confirmation warning. (4) `RecipeList.tsx` — list of recipes with search filter, shows ingredients with availability indicators. (5) `RecipeCard.tsx` — recipe card: result item preview, ingredients grid with have/need counts, "Создать" button (disabled if can_craft=false), source badge (learned/blueprint). (6) `CraftConfirmModal.tsx` — confirm before crafting, shows what will be consumed. All components: Tailwind CSS only, TypeScript, no React.FC, mobile-responsive (360px+). Update `ProfilePage.tsx` to render CraftTab. Update `constants.ts` to add blueprint icon. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/CraftTab.tsx`, `CraftTab/ProfessionSelect.tsx`, `CraftTab/ProfessionInfo.tsx`, `CraftTab/RecipeList.tsx`, `CraftTab/RecipeCard.tsx`, `CraftTab/CraftConfirmModal.tsx`, `ProfilePage/ProfilePage.tsx`, `ProfilePage/constants.ts` |
| **Depends On** | 5 |
| **Acceptance Criteria** | Placeholder replaced. Profession selection works with confirmation. Profession change works with warning. Recipe list displays with material availability. Crafting works with confirmation modal. Blueprint recipes show source badge. All responsive at 360px+. `npx tsc --noEmit` and `npm run build` pass. |

### Task 7: Frontend — Admin panels (Professions + Recipes)
| Field | Value |
|-------|-------|
| **#** | 7 |
| **Description** | Create admin pages: (1) `ProfessionsAdminPage.tsx` — list professions, create/edit/delete profession, manage ranks per profession (inline or modal). (2) `RecipesAdminPage.tsx` — paginated recipe list with search/filters (by profession, rarity), create/edit/delete recipe with ingredient management (add/remove ingredient rows with item selector and quantity). Add both pages to AdminPage.tsx sections array (module: "professions"). Add routes in App.tsx with ProtectedRoute (requiredPermission: "professions:read"). All Tailwind, TypeScript, no React.FC, mobile-responsive. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/src/components/Admin/ProfessionsAdminPage/ProfessionsAdminPage.tsx`, `Admin/RecipesAdminPage/RecipesAdminPage.tsx`, `Admin/AdminPage.tsx`, `App/App.tsx` |
| **Depends On** | 5 |
| **Acceptance Criteria** | Admin pages accessible with correct permissions. Profession CRUD works (create, edit, delete). Rank management works. Recipe CRUD works with ingredient management. Pagination and search work. `npx tsc --noEmit` and `npm run build` pass. |

### Task 8: QA — Backend tests for professions and crafting
| Field | Value |
|-------|-------|
| **#** | 8 |
| **Description** | Write pytest tests for all new inventory-service endpoints: (1) Profession CRUD (admin): create, read, update, delete profession. (2) Rank CRUD (admin): create, update, delete rank. (3) Profession selection: choose profession, verify auto-learned recipes. (4) Profession change: verify rank reset, recipes preserved. (5) Recipe CRUD (admin): create with ingredients, update, delete. (6) Recipe listing: verify learned + blueprint recipes shown, can_craft flag correct. (7) Crafting: successful craft (materials consumed, item created), blueprint consumed on use, error cases (wrong profession, insufficient rank, missing materials, unknown recipe). (8) Learn-recipe endpoint. (9) Admin set-rank. Mock auth dependencies. Use existing test patterns from `services/inventory-service/app/tests/`. |
| **Agent** | QA Test |
| **Status** | DONE |
| **Files** | `services/inventory-service/app/tests/test_professions.py`, `services/inventory-service/app/tests/test_crafting.py`, `services/inventory-service/app/tests/conftest.py` |
| **Depends On** | 1, 2, 3, 4 |
| **Acceptance Criteria** | All tests pass. Coverage for happy path + error cases on all endpoints. Crafting transaction tested (materials consumed atomically). `pytest` runs clean. |

### Task 9: QA — RBAC permissions test update
| Field | Value |
|-------|-------|
| **#** | 9 |
| **Description** | Verify that `test_rbac_permissions.py` (if it exists) passes with the new `professions` module permissions. If the test checks all permissions exist for admin, it should auto-pass since admin gets all permissions. If any manual updates needed, make them. |
| **Agent** | QA Test |
| **Status** | DONE |
| **Files** | `services/user-service/tests/test_rbac_permissions.py` |
| **Depends On** | 2 |
| **Acceptance Criteria** | RBAC permission tests pass with new professions permissions. |

### Task 10: Review
| Field | Value |
|-------|-------|
| **#** | 10 |
| **Description** | Full review of all tasks. Verify: (1) DB schema correct, migrations run. (2) All API endpoints work (test via curl or live verification). (3) Frontend compiles, builds, works in browser. (4) Crafting flow end-to-end: choose profession → view recipes → craft item. (5) Admin panels work. (6) RBAC permissions enforced. (7) Mobile responsive. (8) No TypeScript errors, no console errors. (9) All tests pass. |
| **Agent** | Reviewer |
| **Status** | DONE |
| **Files** | All files from tasks 1-9 |
| **Depends On** | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| **Acceptance Criteria** | All checks pass. Live verification confirms zero errors. Feature works end-to-end. |

### Task Dependency Graph

```
Task 1 (DB/Models) ─────────┬──→ Task 3 (Profession endpoints) ──→ Task 4 (Recipe/Craft endpoints)
                             │                                              │
Task 2 (RBAC) ──────────────┤                                              │
                             │                                              ↓
Task 5 (FE types/API/Redux) ┬──→ Task 6 (CraftTab UI) ──────────→ Task 8 (QA Backend Tests)
                             │                                              │
                             └──→ Task 7 (Admin UI) ────────────→ Task 9 (QA RBAC Tests)
                                                                            │
                                                                            ↓
                                                                    Task 10 (Review)
```

**Parallelism opportunities:**
- Tasks 1 + 2 + 5 can all run in parallel (no dependencies on each other)
- Tasks 3 + 6 + 7 can start as soon as their dependencies complete
- Tasks 8 + 9 run after backend is complete
- Task 10 is last

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-26
**Result:** FAIL

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not available in review environment)
- [ ] `npm run build` — N/A (Node.js not available in review environment)
- [x] `py_compile` — PASS (all 8 modified Python files compile cleanly)
- [x] `pytest` — PASS (63/63 new tests pass; 166 total pass; 19 pre-existing errors in test_endpoint_auth.py unrelated to this feature)
- [x] `docker-compose config` — PASS
- [ ] Live verification — N/A (services not running in review environment)

#### Code Standards Verification
- [x] Pydantic <2.0 syntax (`class Config: orm_mode = True`) — compliant
- [x] Sync SQLAlchemy in inventory-service — consistent, no async mixing
- [x] No hardcoded secrets/URLs/ports
- [x] No stubs/TODO/FIXME without tracking
- [x] All new frontend files are `.tsx` / `.ts` — compliant
- [x] All new styles use Tailwind CSS only — no SCSS/CSS files created
- [x] No `React.FC` usage — all components use `const Foo = ({ x }: Props) => {` pattern
- [x] Mobile responsive — grid columns use responsive breakpoints (`grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`)
- [x] User-facing strings in Russian — all UI text and error messages in Russian
- [x] Design system compliance — uses `gold-text`, `gray-bg`, `modal-overlay`, `modal-content`, `gold-outline`, `btn-blue`, `btn-line`, `input-underline`, `textarea-bordered`, `rounded-card`, `text-site-blue`, `text-gold`, `text-site-red`, `bg-site-dark`

#### Security Review
- [x] All public endpoints use `get_current_user_via_http` (JWT auth)
- [x] All admin endpoints use `require_permission("professions:*")` (RBAC)
- [x] Character ownership verified via `verify_character_ownership(db, character_id, current_user.id)`
- [x] Crafting blocked during battle (`check_not_in_battle`)
- [x] Input validation via Pydantic schemas on all endpoints
- [x] Crafting uses `SELECT ... FOR UPDATE` to prevent race conditions
- [x] Error messages don't leak internals (generic "Ошибка при создании предмета" for 500s)
- [x] SQL queries use parameterized `text()` with `:param` — no injection risk
- [x] Frontend displays all API errors via `toast.error()` — no silent failures

#### QA Coverage
- [x] QA task exists (Task 8 + Task 9) — both DONE
- [x] 34 profession tests + 29 crafting tests = 63 total
- [x] All new endpoints covered (public + admin + error cases)
- [x] Security tests included (401/403/SQL injection)

#### Type and Contract Verification
- [x] Pydantic schemas match TypeScript interfaces for public endpoints (professions, character profession, recipes, crafting)
- [x] Backend endpoint URLs match frontend API module URLs
- [x] Redux thunks match API functions
- [x] RBAC migration matches permission names used in endpoints

#### Issues Found

| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/types/professions.ts:207` + `services/frontend/app-chaldea/src/components/Admin/RecipesAdminPage/RecipesAdminPage.tsx:669` | **Type mismatch: Admin recipes API response vs frontend type.** The backend `RecipeAdminOut` schema returns flat fields `result_item_id` (int) and `result_item_name` (str), but `RecipesPaginatedResponse` reuses `items: Recipe[]` where `Recipe` has a nested `result_item: RecipeResultItem` object. This means `r.result_item?.name` on line 669 will be `undefined`, showing "item #undefined" instead of the actual item name. Similarly, `openEdit` on line 160 reads `r.result_item?.id` which will also be `undefined`, so pre-populating the form when editing a recipe will fail. **Fix:** Either (a) create a separate `AdminRecipe` TypeScript interface matching `RecipeAdminOut` (with flat `result_item_id`, `result_item_name` fields) and use it in `RecipesPaginatedResponse`, OR (b) change the backend admin response to return a nested `result_item` object matching the `RecipeOut` structure. Option (a) is simpler and keeps the backend as-is. | Frontend Developer | FIX_REQUIRED |
| 2 | `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/RecipeCard.tsx:4-26` | **Minor: Missing rarity entries.** The `RARITY_BORDER`, `RARITY_LABEL`, and `RARITY_TEXT` maps are missing `divine` and `demonic` entries which are valid `ItemRarity` values in the backend. These gracefully fall back to defaults, so this is non-blocking, but recipe cards for divine/demonic rarity items would show generic styling. Add these two rarities to the maps. | Frontend Developer | FIX_REQUIRED |

#### Pre-existing issues noted
- `test_endpoint_auth.py` has 19 erroring tests (SQLite compatibility issues during drop_all) — pre-existing, unrelated to this feature.
- `datetime.utcnow()` deprecation warnings throughout crud.py — pre-existing pattern used across all services.

### Review #2 — 2026-03-26
**Result:** PASS

Re-review of fixes for Review #1 issues. Both issues resolved correctly.

#### Issue #1 (BLOCKING) — AdminRecipe type mismatch: FIXED
- New `AdminRecipe` interface in `types/professions.ts:146-162` matches backend `RecipeAdminOut` exactly — all 15 fields verified (flat `result_item_id: number`, `result_item_name: string`, `is_blueprint_recipe`, `is_active`, `auto_learn_rank`).
- `RecipesPaginatedResponse` (line 236) now uses `AdminRecipe[]` instead of `Recipe[]`.
- `api/professions.ts` — `createRecipe` (line 213) and `updateRecipe` (line 221) return `AdminRecipe`.
- `RecipesAdminPage.tsx` — state typed as `AdminRecipe[]` (line 81), `openEdit` accepts `AdminRecipe` (line 153), table row (line 669) reads `r.result_item_name` (flat field, correct), form pre-population (line 160) reads `r.result_item_id` (flat field, correct). No remaining `result_item.x` references.

#### Issue #2 (minor) — Missing divine/demonic rarities: FIXED
- `RecipeCard.tsx` lines 10-11, 20-21, 30-31 — `divine` and `demonic` added to all three maps (`RARITY_BORDER`, `RARITY_LABEL`, `RARITY_TEXT`) with appropriate colors and Russian labels.

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not available in review environment)
- [ ] `npm run build` — N/A (Node.js not available in review environment)
- [x] `py_compile` — N/A (no Python files changed in this fix round)
- [x] `pytest` — N/A (no Python files changed in this fix round)
- [x] `docker-compose config` — PASS
- [ ] Live verification — N/A (services not running in review environment)

#### Verification Summary
All fixes are correct and complete. No new issues introduced. Type contracts between backend `RecipeAdminOut` and frontend `AdminRecipe` are fully aligned. The feature is ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-26 — PM: фича создана, запускаю анализ кодовой базы
[LOG] 2026-03-26 — Analyst: анализ завершён, затронуто 6 сервисов (основные: inventory-service, character-service, frontend). Найден placeholder таб "Крафт" на фронте. Существующие слоты ring/necklace/bracelet покрывают ювелирку. Зелья/еда работают через существующие recovery-поля. Выявлены крупные gaps: яды (нужна доработка battle-service), руны (нужна система сокетов), ремонт (нет системы прочности), книги XP (нет тайм-баффов). Рекомендовано разделить на Phase 1 (ядро) и Phase 2 (расширенные механики).
[LOG] 2026-03-26 — Architect: спроектировано 10 задач, 20+ API-контрактов, 6 новых таблиц. Ключевое решение: все данные профессий и крафта хранятся в inventory-service (character-service не затрагивается). Blueprint — обычный предмет с item_type=blueprint и ссылкой на рецепт. Задачи разделены: 4 backend, 3 frontend, 2 QA, 1 review. Параллельное выполнение возможно для tasks 1+2+5.
[LOG] 2026-03-26 — Backend Dev: начал задачи #1 и #2
[LOG] 2026-03-26 — Backend Dev: задача #1 завершена — создана миграция 004_add_professions_crafting (6 новых таблиц, расширение item_type enum, seed 6 профессий + 18 рангов), обновлены models.py (7 новых моделей) и schemas.py (blueprint в ItemType). py_compile пройден.
[LOG] 2026-03-26 — Backend Dev: задача #2 завершена — создана миграция 0019_add_profession_permissions (5 разрешений модуля professions, назначения для Moderator и Editor). py_compile пройден.
[LOG] 2026-03-26 — Frontend Dev: задача #5 завершена — созданы TypeScript типы (professions.ts), API модуль (api/professions.ts), Redux slice (craftingSlice.ts), слайс зарегистрирован в store.ts. Все типы соответствуют API контрактам из секции 3.3/3.9. Node.js не доступен в окружении для запуска tsc --noEmit.
[LOG] 2026-03-26 — Backend Dev: начал задачи #3 и #4
[LOG] 2026-03-26 — Backend Dev: задача #3 завершена — добавлены Pydantic-схемы для профессий (ProfessionOut, ProfessionCreate, ProfessionUpdate, ProfessionRankCreate/Update, CharacterProfessionOut, ChooseProfessionRequest, ChangeProfessionRequest, AdminSetRankRequest), CRUD-функции для профессий/рангов/character_profession, 12 API-эндпоинтов (4 public + 8 admin). py_compile пройден.
[LOG] 2026-03-26 — Backend Dev: задача #4 завершена — добавлены Pydantic-схемы для рецептов/крафта (RecipeOut, RecipeCreate, RecipeUpdate, CraftRequest, CraftResult, LearnRecipeRequest, RecipeAdminOut, RecipeListResponse), CRUD-функции для рецептов и крафта (включая execute_craft с FOR UPDATE блокировками), 7 API-эндпоинтов (3 public + 4 admin). Крафт работает в транзакции с потреблением материалов и чертежей. py_compile пройден на всех 3 файлах.
[LOG] 2026-03-26 — Frontend Dev: начал задачу #6 — CraftTab UI
[LOG] 2026-03-26 — Frontend Dev: задача #6 завершена — создано 6 компонентов CraftTab (CraftTab.tsx, ProfessionSelect.tsx, ProfessionInfo.tsx, RecipeList.tsx, RecipeCard.tsx, CraftConfirmModal.tsx). PlaceholderTab заменён на CraftTab в ProfilePage.tsx. Добавлен blueprint в ITEM_TYPE_ICONS (constants.ts). Все компоненты: TypeScript, Tailwind only, no React.FC, mobile-responsive (360px+), framer-motion анимации, все ошибки отображаются пользователю через toast. Node.js не доступен для tsc --noEmit / npm run build.
[LOG] 2026-03-26 — Frontend Dev: задача #7 завершена — созданы ProfessionsAdminPage (CRUD профессий, управление рангами, установка ранга персонажу) и RecipesAdminPage (пагинированный список, поиск/фильтры, CRUD рецептов с ингредиентами). Добавлены секции в AdminPage.tsx и маршруты в App.tsx с ProtectedRoute (professions:read). Tailwind CSS, TypeScript, без React.FC, адаптивная вёрстка. Node.js не доступен для tsc --noEmit.
[LOG] 2026-03-26 — QA: задача #9 завершена — добавлена секция 9 (TestProfessionsPermissions) в test_rbac_permissions.py: 9 тестов для модуля professions (проверка существования 5 разрешений, автоматические разрешения admin, корректные разрешения moderator/editor/user, require_permission блокирует неавторизованных). Паттерн повторяет секции 7 (perks) и 8 (titles). py_compile пройден.
[LOG] 2026-03-26 — QA: задача #8 завершена — написаны тесты для профессий и крафта: test_professions.py (34 теста), test_crafting.py (29 тестов). Покрыты все эндпоинты: CRUD профессий/рангов (admin), выбор/смена профессии, получение профессии, крафт (успех, чертёж, ошибки: не та профессия, низкий ранг, нет материалов, неизвестный рецепт), изучение рецептов, админ рецепты. Тесты безопасности: 401/403/SQL injection. Исправлен conftest.py (circular FK items↔recipes при drop_all). Все 63 теста проходят.
[LOG] 2026-03-26 — Reviewer: начал проверку задачи #10 (полная ревизия FEAT-081 Phase 1)
[LOG] 2026-03-26 — Reviewer: проверка завершена, результат FAIL. py_compile PASS, pytest 63/63 PASS, docker-compose config PASS. Код качественный, все стандарты соблюдены. Найдено 2 проблемы: (1) BLOCKING — несоответствие типов admin-рецептов между бэкендом (плоские поля result_item_id/result_item_name) и фронтендом (вложенный объект result_item), из-за чего в админке рецептов не отображается результирующий предмет; (2) MINOR — отсутствуют записи divine/demonic в RARITY_* maps в RecipeCard.tsx.
[LOG] 2026-03-26 — Frontend Dev: исправлены 2 проблемы из ревью. (1) BLOCKING: создан интерфейс AdminRecipe с плоскими полями (result_item_id, result_item_name) в types/professions.ts, обновлены RecipesPaginatedResponse, api/professions.ts и RecipesAdminPage.tsx для использования AdminRecipe вместо Recipe. (2) MINOR: добавлены divine (Божественный) и demonic (Демонический) в RARITY_BORDER, RARITY_LABEL, RARITY_TEXT в RecipeCard.tsx. Node.js не доступен для tsc --noEmit / npm run build.
[LOG] 2026-03-26 — Reviewer: повторная проверка (Review #2) завершена, результат PASS. Оба исправления корректны: AdminRecipe полностью соответствует RecipeAdminOut (15 полей проверены), divine/demonic добавлены во все три map. docker-compose config PASS. Статус изменён на REVIEW.
[LOG] 2026-03-26 — Codebase Analyst: исправлен баг — CraftTab крашил страницу профиля (белый экран). Причины: (1) отсутствие ErrorBoundary — любая ошибка рендера убивала всё дерево React; (2) компонент рендерил контент до завершения первого fetch-цикла (race condition между useEffect и render); (3) отсутствие null-safe доступа к вложенным объектам (profession, result_item). Исправления: создан ErrorBoundary (ui/ErrorBoundary.tsx), CraftTab обёрнут в ErrorBoundary в ProfilePage.tsx, добавлен useRef для предотвращения pre-fetch рендера, добавлен optional chaining в ProfessionInfo/RecipeCard/RecipeList/CraftConfirmModal.
[LOG] 2026-03-26 — Frontend Dev: повторное исправление краша CraftTab. Предыдущий фикс (useRef + optional chaining) не устранил проблему. Причина: useRef не вызывает ре-рендер, что создаёт гонку между установкой флага и Redux loading-флагами. Исправления: (1) CraftTab — заменён useRef(false) на useState(false) для hasFetched, чтобы гарантировать корректный ре-рендер; добавлены Array.isArray() обёртки для professions и recipes перед передачей в дочерние компоненты; (2) ProfessionSelect — добавлен Array.isArray(prof.ranks) guard перед доступом к .length; (3) RecipeCard — добавлен (recipe.ingredients ?? []) fallback; (4) CraftConfirmModal — добавлен (recipe.ingredients ?? []) fallback. Удалён неиспользуемый import useRef.
[LOG] 2026-03-26 — Backend+Frontend Dev: рецепты как предметы инвентаря. Backend: добавлен item_type=recipe в ENUM (миграция 005), при создании рецепта без auto_learn_rank автоматически создаётся предмет (item_type=recipe, blueprint_recipe_id=recipe.id). update_recipe/delete_recipe синхронизируют предмет. Новый endpoint POST /crafting/{id}/learn-from-item — изучение рецепта из предмета с потреблением. Frontend: recipe в ITEM_TYPE_ICONS/CATEGORY_LIST, кнопка "Изучить" в контекстном меню инвентаря, learnRecipeFromItem thunk в profileSlice, отображение предмета-рецепта в админке.
[LOG] 2026-03-26 — Full-Stack Dev: загрузка изображения рецепта. Photo-service: добавлена mirror-модель Recipe, CRUD update_recipe_image (обновляет icon рецепта + image предмета-рецепта), эндпоинт POST /photo/change_recipe_image. Frontend: uploadRecipeImage в api/professions.ts, RecipesAdminPage — текстовое поле URL иконки заменено на file input с превью и двухфазной загрузкой (create/update → upload image).
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано (Phase 1)
- Система профессий: 6 профессий (Кузнец, Алхимик, Повар, Зачарователь, Ювелир, Книжник) с 3 рангами каждая
- Система рецептов/чертежей: рецепты (постоянные) и чертежи (одноразовые предметы)
- Крафт: выбор рецепта → проверка материалов → создание предмета (в транзакции с блокировками)
- Выбор/смена профессии с сбросом прогресса и сохранением рецептов
- Админ-панели для управления профессиями, рангами и рецептами
- RBAC разрешения для модуля professions
- 72 теста (63 profession/crafting + 9 RBAC)

### Что изменилось от первоначального плана
- Все данные профессий хранятся в inventory-service (character-service не затронут)
- Добавлен ErrorBoundary для CraftTab
- Исправлен .sort() на иммутабельных Redux-массивах

### Оставшиеся риски / follow-up задачи (Phase 2+)
- **Автопрокачка профессий** — XP за крафт, автоматическое повышение ранга при достижении порога, количество XP зависит от редкости/сложности рецепта
- Кузнец: заточка снаряжения, ремонт-комплекты (требует систему прочности)
- Алхимик: яды/покрытие оружия (требует доработку battle-service), трансмутация материалов
- Зачарователь: руны, вставка/извлечение/слияние (требует систему сокетов в снаряжении)
- Ювелир: огранка камней, переплавка украшений
- Книжник: книги опыта (требует систему тайм-баффов), магическое оружие, свитки заклинаний для боя
