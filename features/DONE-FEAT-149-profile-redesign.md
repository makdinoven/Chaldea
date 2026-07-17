# FEAT-149: Редизайн страницы профиля персонажа (/profile) + удаление слота «Щит»

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-07-16 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Визуальный редизайн страницы профиля персонажа (`/profile`) по макету из Claude Design.
Референс сохранён локально: **`features/design-refs/FEAT-149-profile-CharacterProfile.dc.html`** (полный HTML с инлайн-стилями; мобильный адаптив — media query ≤920px внутри того же файла: одна колонка, сжатая сетка экипировки 46px). Мобильный макет (ProfileMobilePreview.dc.html) — тот же файл во фрейме 390×844.

Требования пользователя (дословно):
1. **Меняем только визуальную часть**: расположение, группировку, тени, затемнения. **Стилистику (текущую) не менять** — типографика/цвета/токены остаются текущей дизайн-системы, из макета берём только layout/композицию/принципы затемнений и теней.
2. **Иконки** — использовать те, что уже есть в проекте. **Подписывать текст возле иконок не нужно** (иконки без текстовых подписей).
3. **Убрать слот экипировки «Щит»** — щиты теперь экипируются как доп. оружие (additional weapons), а не в отдельную ячейку.
4. Десктоп — по `CharacterProfile.dc.html`, мобильная версия — адаптив по media queries того же макета (≤920px одна колонка).

### Структура макета (block map)
- **Вкладки сверху** (горизонтальный скролл): Персонаж / Навыки / Перки / Отряд / Сбор / Задания / Бои / Титулы / Крафт / История постов — активная с золотым подчёркиванием.
- **3 панели** (grid `392px / minmax(300px,352px) / 1fr`, высота `calc(100vh - 130px)`, внутренние скроллы; каждая панель: тёмный полупрозрачный фон + blur + золотистая обводка + тень):
  1. **Персонаж (paper doll)**: шапка-identity (круг LVL, имя, титул, раса | класс), портрет с ромбом слотов экипировки вокруг (шлем сверху; слева колонка: осн. оружие, броня, кольцо, пояс; справа: доп. оружие, плащ, ожерелье, браслет — **щита нет**), XP-бар + очки прокачки, валюта + актив. опыт, быстрые слоты (сетка 5 колонок).
  2. **Показатели**: ресурс-бары (здоровье/мана/энергия/выносливость с иконками), Характеристики (строки с многоуровневыми прогресс-барами), «В бою» (сетка 2 колонки карточек-статов), чипы сопротивлений.
  3. **Инвентарь**: заголовок со счётчиком, чипы категорий (гориз. скролл), сетка круглых предметов (auto-fill 64px) с бейджами количества/заточки, пустое состояние.
- **Модалка предмета**: шапка с иконкой/названием/редкостью, описание, статы, прочность, действия (Экипировать-Использовать / Выбросить).
- **Мобильный** (≤920px): одна колонка, панели авто-высоты без внутренних скроллов, сетка экипировки сжимается (слоты 46px, max-width 320px по центру).

### Бизнес-правила
- Все данные реальные (текущие API профиля/инвентаря/атрибутов).
- Слот «Щит» удаляется из UI экипировки; щиты экипируются в слот(ы) доп. оружия. Судьбу уже экипированных щитов и backend-валидации определить при анализе/проектировании.
- Иконки — существующие в проекте, без текстовых подписей рядом.
- Все пользовательские тексты — на русском.

### Edge Cases
- У персонажа уже экипирован щит в слот «щит» — что показывает UI и что с данными?
- Пустые слоты экипировки/быстрых слотов, пустой инвентарь/категория.
- Экран 360px — всё помещается (T5).

### Вопросы к пользователю (если есть)
- [x] Тип предмета «щит»? → **Ответ: тип `shield` остаётся (отдельная категория предметов), но экипируется в слот доп. оружия (Option A из анализа).**
- [x] Щит как выбираемое «оружие» в бою с потерей прочности? → **Ответ: да, ок — никаких особых правил в battle-service.**
- [x] Счётчик инвентаря «N / cap»? → **Ответ: показывать только количество предметов, без лимита (без правок API).**
- [x] Быстрые слоты (в макете 5 колонок, в игре 10 слотов)? → **Ответ: сетка 5×2 со всеми 10 слотами, заблокированные — затемнённые.**

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | visual redesign of /profile "Персонаж" tab + shield-slot removal from UI + shield references cleanup | `src/components/ProfilePage/**` (see component map), `src/components/ProfilePage/constants.ts`, `src/components/ProfilePage/InventoryTab/dnd/constants.ts`, `src/components/ItemsAdminPage/*`, `src/components/AdminNpcsPage/NpcEquipmentEditor.tsx`, `src/components/Auction/AuctionFilters.tsx` |
| inventory-service | shield slot removal: enums, slot creation, equip/compat mapping, Alembic data migration, tests | `app/models.py`, `app/crud.py`, `app/schemas.py`, `app/alembic/versions/` (new migration), `app/tests/test_unequip_shield.py` (+3 tests with shield fixtures) |
| battle-service | NO code references "shield" — verify only (see risks re: shields in `additional_weapons` slot) | `app/battle_engine.py`, `app/inventory_client.py` (read-only impact) |
| character-service, skills-service, autobattle-service, character-attributes-service, party-service, dungeon-service, battle-pass-service | no shield references found (grep) — no changes | — |

### Frontend Component Map (design block → existing component)

Route: `<Route path="profile" element={<ProfilePage />} />` in `src/components/App/App.tsx` (line 315).

| Design block | Existing component(s) | File |
|---|---|---|
| Tabs row (horiz. scroll, gold underline) | `ProfileTabs` — already implements 10 tabs + "История постов" as a `Link` to `/post-history/:id` | `ProfilePage/ProfileTabs.tsx` |
| Tab switch / page shell | `ProfilePage` (local `activeTab` state, `loadProfileData` on mount) | `ProfilePage/ProfilePage.tsx` |
| 3-panel layout of "Персонаж" tab | `CharacterTab` → `LeftColumn` + `CenterColumn` + `RightColumn` (current order: stats-left, paper-doll-center, inventory-right; design order: paper-doll / stats / inventory) | `ProfilePage/CharacterTab/*.tsx` |
| Panel 1: identity header (LVL circle, name, title, race\|class) | Currently split: name/title/race/class + currency + active XP in `LeftColumn`; LVL + XP bar + stat points in `CenterColumn` | `CharacterTab/LeftColumn.tsx`, `CharacterTab/CenterColumn.tsx` |
| Panel 1: portrait + equipment diamond | `AvatarEquipmentGrid` (5-col CSS grid around avatar, avatar upload via photo-service) + `EquipmentSlot` (per-slot, DnD, durability/enh badges) | `CharacterTab/AvatarEquipmentGrid.tsx`, `EquipmentPanel/EquipmentSlot.tsx` |
| Panel 1: XP bar + stat points | `CenterColumn` (uses `profile.level_progress`) | `CharacterTab/CenterColumn.tsx` |
| Panel 1: currency + active XP | `LeftColumn` (`profile.currency_balance`, `attributes.active_experience`, `gold-coins.svg` icon) | `CharacterTab/LeftColumn.tsx` |
| Panel 1: fast slots (design: 5-col grid) | `FastSlots` (currently 2-col grid, 10 slots, enabled/disabled state, DnD) | `EquipmentPanel/FastSlots.tsx` |
| Panel 2: vitals bars | `StatsPanel` (4 resource bars, no icons currently — design wants icon-only labels) | `CharacterInfoPanel/StatsPanel.tsx` |
| Panel 2: attributes with tier bars | `PrimaryStatsSection` (tiered bars for 6 `MAIN_STATS` already exist) | `StatsTab/PrimaryStatsSection.tsx` |
| Panel 2: stat point distribution | `StatDistributionPanel` (shown when `stat_points > 0`) | `StatsTab/StatDistributionPanel.tsx` |
| Panel 2: combat stats grid + resist chips | `DerivedStatsSection` (uses `DERIVED_STATS` incl. all `res_*`) | `StatsTab/DerivedStatsSection.tsx` |
| Panel 3: inventory (categories + grid) | `CategorySidebar` (vertical icon list, `CATEGORY_LIST`; design: horizontal chips) + `ItemGrid` (4-col square grid, `MIN_GRID_CELLS=80` fillers; design: auto-fill 64px circles) + `ItemCell` (qty/enh badges exist) | `InventoryTab/CategorySidebar.tsx`, `InventoryTab/ItemGrid.tsx`, `InventoryTab/ItemCell.tsx` |
| Item detail modal | `ItemDetailModal` (rarity header, description, stats, durability, sockets, repair, actions) + `ItemContextMenu` (equip/use/drop actions) | `InventoryTab/ItemDetailModal.tsx`, `InventoryTab/ItemContextMenu.tsx` |
| DnD equip/unequip | `InventoryDndContext` + `dnd/constants.ts` | `InventoryTab/dnd/*` |
| Also rendered by NPC profile modal | `NpcProfileModal` reuses equipment display | `pages/LocationPage/NpcProfileModal.tsx` (check during impl) |

**T1/T3 status:** the entire `ProfilePage/` tree is already `.tsx` + Tailwind — zero `.jsx` and zero `.scss` files inside it (verified by find/grep). Shared visual classes come from `index.css` `@layer components` (`item-cell`, `item-cell-empty`, `rarity-*`, `stat-bar`, `stat-bar-fill`, `gold-text`, `gold-scrollbar*`, `slot-pulse-compatible`, `skill-point-dot`, `gradient-divider-h`, `rounded-card`). No migration obligations blocking; redesign is pure Tailwind work.

**Icons available (user requires reuse, no text labels):**
- Slot/category SVGs: `src/assets/icons/equipment/` — armor, bag, belt, bracelet, cloak, helmet, necklace, potion, resource, ring, scroll, shield, swap-bag, sword; plus `src/assets/icons/gold-coins.svg`. Mapped via `ITEM_TYPE_ICONS` and `CATEGORY_LIST` in `ProfilePage/constants.ts`.
- Icon library: `lucide-react@^1.7.0` is an installed dependency, already used in `BattlePage/SkillPicker` and `SkillsTab/ResolvedSkillCard` (X, Zap, Droplet, Clock, ...). Vitals icons (heart/droplet/zap/wind from the mock) can come from lucide-react — counts as "existing in project".
- No dedicated per-vital SVG assets exist today (`StatsPanel` uses text labels only).

### Data Availability (design fields vs existing endpoints)

Redux slice: `src/redux/slices/profileSlice.ts` (thunks: fetchProfile, fetchRaceInfo, fetchRaceNames, fetchAttributes, fetchInventory, fetchEquipment, fetchFastSlots, fetchActiveBuffs, equip/unequip/use/drop/identify/repair, fetchItemDetail, upgradeStats, uploadCharacterAvatar).

| Design datum | Source | Available? |
|---|---|---|
| Name, level, avatar, active title + rarity | `GET /characters/{id}/full_profile` | YES |
| Race / class names | `GET /characters/{id}/race_info` + `GET /characters/races` + `CLASS_NAMES` | YES |
| XP bar (cur/next, fraction), stat points | `full_profile.level_progress`, `stat_points` | YES |
| Currency, active XP | `full_profile.currency_balance`, `attributes.active_experience` | YES |
| Vitals current/max (4) | `GET /attributes/{id}` (fallback `full_profile.attributes`) | YES |
| 6 attributes for tier bars | `GET /attributes/{id}` | YES |
| Combat stats (damage, dodge, crit chance/dmg) | attributes (+ class main attr + `main_weapon.damage_modifier` logic in `DerivedStatsSection`) | YES |
| Resists (13 `res_*`) | attributes | YES |
| Equipment slots + item, enhancement badge, durability | `GET /inventory/{id}/equipment` (`enhancement_points_spent`, `current_durability`, `item.max_durability`) | YES |
| Fast slots + quantity | `GET /inventory/characters/{id}/fast_slots` + equipment fast_slot_* rows (merged in `FastSlots`) | YES |
| Inventory items, qty, enh, identified | `GET /inventory/{id}/items` | YES |
| Item modal: desc/stats/durability/sockets | `GET /inventory/{id}/item-detail/{invId}` | YES |
| Inventory counter "N / MAX" (mock shows /120) | **MISSING as API.** Backend has `DEFAULT_INVENTORY_MAX_SLOTS = 50` in inventory-service `crud.py` (`get_inventory_max_slots`), exposed only via internal `GET /internal/characters/{id}/free_slots_check`. No public capacity endpoint; frontend has only `MIN_GRID_CELLS = 80` (a display constant, not a cap) | NO — needs decision |
| Mock stats «Инициатива», «Блок» | **DO NOT EXIST** in `character_attributes` (no initiative/block fields) — mock-only data, must be dropped or substituted with real DERIVED_STATS | N/A |

### Backend — shield slot representation (inventory-service, sync SQLAlchemy, Pydantic v1, Alembic present `alembic_version_inventory`)

- `models.py`: `Items.item_type` ENUM includes `'shield'` (line 14-18); `EquipmentSlot.slot_type` ENUM includes `'shield'` (line 160-166). Tables: `items`, `equipment_slots`.
- `schemas.py` line 24: `ItemType.shield = "shield"` enum member.
- `crud.py`:
  - `create_default_equipment_slots` (line 229): creates 1 `shield` slot per character (plus 10 other equip slots and 10 fast slots).
  - `NPC_EQUIPMENT_SLOTS` (line 21) includes `'shield'`; used by `create_npc_equipment_slots` / `admin_equip_npc_item` / `admin_unequip_npc_item` validation.
  - `is_item_compatible_with_slot` (line 395): strict 1:1 `'shield': ['shield']`.
  - `find_equipment_slot_for_item` (line 417): fixed map `'shield' → 'shield'` slot.
  - Shield participates in `SHARPENABLE_TYPES` (line 46) and `ARMOR_WEAPON_TYPES`/`SOCKETABLE_TYPES` (line 59) — sharpening + gem/rune sockets apply to shields.
  - `DURABILITY_SLOT_TYPES` (line 56) does NOT include `shield` — shields take no battle durability loss today.
- `main.py`: equip/unequip endpoints are slot-agnostic (resolve slot via `find_equipment_slot_for_item`); no literal "shield" strings.
- **`additional_weapons` mechanics:** exactly ONE `additional_weapons` slot per character (single row in `create_default_equipment_slots`); item_type `additional_weapons` maps 1:1 to that slot. So "shields equip as additional weapons" means a shield competes with the one off-hand weapon slot.
- Alembic history: `002_add_shield.py` added `'shield'` to both ENUMs and backfilled shield slot rows (FEAT-041). A new migration would be the reverse.

### Shield-slot consumers (full list)

Backend:
- inventory-service only (files above + tests: `test_unequip_shield.py` — a whole `TestShieldSupport` class asserting shield exists in ENUMs/slots; shield fixtures also in `test_npc_equipment.py`, `test_sharpening.py`, `test_crafting.py`).
- battle-service: NO shield references. `battle_engine.fetch_weapons` reads `main_weapon` + `additional_weapons` slots and uses `damage_modifier`/`primary_damage_type`; `inventory_client.DURABILITY_SLOT_TYPES = {head, body, cloak, main_weapon, additional_weapons}`. No block/shield mechanic exists in combat.
- character-service / skills-service / autobattle-service / character-attributes-service / party-service / dungeon-service / battle-pass-service: zero matches. (Note: `character-service/app/crud.py:205` `send_equipment_slots_request` with slot types chest/legs/feet/weapon/accessory is dead code — no callers; slots are actually created by inventory-service `create_default_equipment_slots` during inventory creation.)
- Seed data: `docker/mysql/init/01-seed-data.sql` has NO shield items (starter items: potions, sword, dagger, staff, body armor, cloak). Starter kits live in DB table `starter_kits` (JSON item lists, admin-managed).

Frontend (all `.tsx`/`.ts`, Tailwind — no T1/T3 debt):
- `ProfilePage/constants.ts`: `ITEM_TYPE_ICONS.shield`, `CATEGORY_LIST` entry `{key:'shield'}`, `EQUIPMENT_SLOT_ORDER`, `EQUIPMENT_SLOT_LABELS.shield`, `EQUIPMENT_TYPES`.
- `ProfilePage/CharacterTab/AvatarEquipmentGrid.tsx` line 141: renders `getSlot('shield')`.
- `ProfilePage/EquipmentPanel/EquipmentPanel.tsx` line 40: `accessorySlots = ['shield', ...]` (legacy panel, check if still routed).
- `ProfilePage/InventoryTab/dnd/constants.ts`: `EQUIPMENT_ITEM_TYPES.shield`, `ITEM_TYPES`, `ITEM_TYPE_LABELS.shield` (DnD compatible-slot mapping).
- `ProfilePage/InventoryTab/ItemDetailModal.tsx` line 22: type label «Щит».
- `ProfilePage/CraftTab/`: `SharpeningSection.tsx` (sharpenable types incl. shield), `RuneSocketSection.tsx`, `GemSocketModal.tsx` (label «Щит»).
- Admin: `ItemsAdminPage/ItemForm.tsx` (item_type select incl. shield), `ItemsAdminPage.tsx` (filter list), `ItemList.tsx` (label); `AdminNpcsPage/NpcEquipmentEditor.tsx` (NPC_SLOT_TYPES + label).
- `Auction/AuctionFilters.tsx`: category filter «Щит».
- (`SkillTreeView/skillLabels.ts` matches are unrelated — Russian words «щит/защита» in skill text.)

### DB Changes (facts for Architect — data migration options)

Live dev DB counts (queried 2026-07-16): **items with item_type='shield': 0; equipped shields: 0; equipment_slots rows with slot_type='shield': 1; shields in character_inventory: 0; shields on auction: 0.** Prod state unknown but the game has never seeded shield items — likely near-zero.

Two tables/fields involved:
1. `equipment_slots.slot_type` ENUM — remove `'shield'` + DELETE existing `slot_type='shield'` rows (must first unequip any equipped shield: move item back to `character_inventory` preserving `enhancement_points_spent`/`enhancement_bonuses`/`socketed_gems`/`current_durability`, and subtract its modifiers via character-attributes — or verify equipped count is 0 and simply delete).
2. `items.item_type` ENUM — decision-dependent:
   - **Option A (keep item type, re-map slot):** keep `item_type='shield'`, change `find_equipment_slot_for_item` / `is_item_compatible_with_slot` so `'shield'` → `additional_weapons` slot. Minimal enum churn (only slot_type ENUM change); shields remain a distinct category/filter in UI and remain sharpenable/socketable.
   - **Option B (retype items):** `UPDATE items SET item_type='additional_weapons' WHERE item_type='shield'`, then drop `'shield'` from `items.item_type` ENUM and remove everywhere (schemas.ItemType, admin forms, auction filters, all label maps). Bigger cross-cutting cleanup; shields lose distinct identity.
   - MySQL ENUM shrink requires no rows carrying the removed value (ALTER fails/truncates otherwise) — data cleanup must run before ALTER in the same migration.
3. Alembic: inventory-service has auto-migration at container start (`alembic_version_inventory`, versions up to 016+). New migration slots in normally. Downgrade path mirrors `002_add_shield.py`.

NPC equipment: `NPC_EQUIPMENT_SLOTS` includes shield; NPC shield slots (if any NPCs have them) are covered by the same `equipment_slots` cleanup.

### Existing Patterns

- inventory-service: sync SQLAlchemy ORM, Pydantic v1 (`orm_mode`), Alembic auto-migration, HTTP auth via `auth_http.py` (`get_current_user_via_http`), equip/unequip are transactional with modifier apply via character-attributes-service HTTP.
- Frontend: Redux Toolkit `createAsyncThunk` + axios, path-prefix API via Nginx (`/inventory/...`, `/characters/...`, `/attributes/...`), Tailwind + `@layer components` classes, `motion/react` animations, `@dnd-kit` drag-and-drop, react-hot-toast for errors (all thunks reject with Russian messages).
- Design tokens: `tailwind.config.js` (`gold`, `site-blue`, `site-bg`, `rarity-*`, `rounded-card`, `shadow-card`, `ease-site`); see `docs/DESIGN-SYSTEM.md`.

### Cross-Service Dependencies

- inventory-service → character-attributes-service (`apply_modifiers` on equip/unequip; must run for any force-unequipped shield during migration).
- inventory-service → character-service (`evaluate-titles` after equip), → attributes (`reconcile-perks`, cumulative stats).
- battle-service → inventory-service `GET /{id}/equipment` (weapons: `main_weapon`, `additional_weapons`; durability slots). If shields become equippable into `additional_weapons`, battle weapon-slot selection will offer a shield as an off-hand "weapon" (damage from `damage_modifier`) and it will start taking battle durability loss (slot-based `DURABILITY_SLOT_TYPES` check in both services).
- frontend Admin NPC editor & admin equip endpoints validate against `NPC_EQUIPMENT_SLOTS`.
- `GET /inventory/{id}/equipment` response shape is unchanged by slot removal (one fewer row) — consumers iterate rows, no breakage expected.

### Risks

- **Risk:** MySQL ENUM ALTER with residual `'shield'` rows fails/corrupts → **Mitigation:** migration must unequip/retype/delete shield rows BEFORE the ALTERs (dev DB already has 0 equipped shields, 1 empty slot row).
- **Risk:** equipped shield force-unequip without modifier subtraction desyncs character attributes → **Mitigation:** count is 0 in dev; migration should still handle it (return to inventory + negative modifiers) or assert-empty.
- **Risk:** battle-service semantics — shield in `additional_weapons` becomes a selectable battle "weapon" and gains durability loss → **Mitigation:** flag to Architect/PM (see Questions); no battle code change strictly required.
- **Risk:** inventory-service tests (`test_unequip_shield.py` TestShieldSupport and shield fixtures in sharpening/crafting/NPC tests) will FAIL after removal → **Mitigation:** QA must rewrite them in the same feature.
- **Risk:** redesign touches DnD wiring (`EquipmentSlot`/`FastSlots`/`ItemGrid` are draggable/droppable) — layout rewrite may break drag-and-drop → **Mitigation:** preserve dnd-kit ids/data contracts; live-verify drag flows.
- **Risk:** design mock shows stats that don't exist (Инициатива, Блок) and a 120-slot counter (backend cap is 50, internal-only) → **Mitigation:** Architect maps design to real `DERIVED_STATS`; counter needs a decision (Questions).
- **Risk:** `-mt-12` shell offset and `calc(100vh-130px)` panel heights must reconcile with the site header layout; mobile ≤920px single-column with auto heights (T5, 360px) → **Mitigation:** follow media-query spec in the reference file.

### Questions for PM

1. **Item type of shields:** keep `item_type='shield'` as a distinct item category that now equips into the `additional_weapons` slot (Option A — recommended by data: zero shield items exist, minimal churn, shields stay filterable/labelable), or fully retype shields into `additional_weapons` items and delete the 'shield' item type everywhere (Option B)? This changes admin item forms, auction filters, and inventory category chips.
2. **Battle consequence:** with a shield in the `additional_weapons` slot, the battle weapon-slot picker will treat it as an off-hand weapon (damage from its `damage_modifier`, durability loss in battle). Acceptable as-is, or should battle-service exclude shields from weapon selection? (Requires battle-service change only in the latter case.)
3. **Inventory counter:** the mock shows «N / 120». Real capacity constant is 50 (inventory-service, internal-only). Should we (a) expose capacity via a small public endpoint and show the real «N / 50», (b) show only the item count without a max, or (c) skip the counter?
4. **Fast slots:** the mock shows a 5-column hotbar; the game has 10 fast slots with enabled/disabled states (disabled slots dimmed). Render all 10 in 5×2 (natural fit) — confirm, or hide disabled slots?

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Summary

Visual-only redesign of the `/profile` "Персонаж" tab to the 3-panel mock layout, plus removal of the `shield` **equipment slot** (Option A, confirmed by user): `shield` stays an **item type** (distinct category, sharpenable, socketable, admin/auction filterable) but now equips into the single `additional_weapons` slot. **No API contract changes, no new endpoints, no battle-service changes, no Redux slice changes.** `GET /inventory/{id}/equipment` simply returns one fewer row; all consumers iterate rows.

### 3.1 Backend — inventory-service (sync SQLAlchemy, Pydantic v1, Alembic auto-migration)

#### Code changes

| File | Change |
|---|---|
| `app/models.py` | Remove `'shield'` from `EquipmentSlot.slot_type` Enum (line ~160). **Keep** `'shield'` in `Items.item_type` Enum — item type survives. |
| `app/schemas.py` | **No change.** `ItemType.shield` stays (item type survives). Verify no slot-type literal mentions `shield` (grep). |
| `app/crud.py` `create_default_equipment_slots` (~line 229) | Remove `'shield'` from `slot_types` list → new characters get 9 equipment slots + 10 fast slots. |
| `app/crud.py` `NPC_EQUIPMENT_SLOTS` (line 21) | Remove `'shield'` → `create_npc_equipment_slots` stops creating it; `admin_equip_npc_item` / `admin_unequip_npc_item` reject `slot_type='shield'` with the existing invalid-slot error. |
| `app/crud.py` `is_item_compatible_with_slot` (~line 395) | Delete the `'shield': ['shield']` key; change `'additional_weapons': ['additional_weapons']` → `'additional_weapons': ['additional_weapons', 'shield']`. |
| `app/crud.py` `find_equipment_slot_for_item` (~line 417) | In the `fixed` map change `'shield': 'shield'` → `'shield': 'additional_weapons'`. |
| `app/crud.py` constants | **Keep unchanged:** `SHARPENABLE_TYPES`, `ARMOR_WEAPON_TYPES`/`SOCKETABLE_TYPES` (item-type based — shields stay sharpenable/socketable), `DURABILITY_SLOT_TYPES` (slot-based; already contains `additional_weapons`, so an equipped shield automatically starts taking battle durability loss — matches user decision, and battle-service `inventory_client.DURABILITY_SLOT_TYPES` already agrees). |
| `app/main.py` | No change expected (equip/unequip are slot-agnostic via `find_equipment_slot_for_item`); grep-verify. |

Behavioral consequences (accepted by user, section 1): a shield in `additional_weapons` competes with the one off-hand weapon; occupied-slot behavior is identical to equipping a second off-hand weapon (existing error/flow — no special case). Battle-service will offer it as a selectable off-hand "weapon" (`damage_modifier`) — intentionally no battle code change.

#### Alembic migration `017_remove_shield_slot.py` (modeled on reversing `002_add_shield.py`)

`down_revision` = current head (verify with `alembic heads`; expected `016_add_gathering_system`'s revision id). Version table: `alembic_version_inventory`, auto-runs at container start (fail-fast).

`upgrade()` — order matters (MySQL ENUM shrink fails if rows carry the removed value); pure SQL, covers both player and NPC rows (NPC slots live in the same `equipment_slots` table):
1. **Move equipped shields to the off-hand slot where it is free** (no attribute change — modifiers stay applied):
   `UPDATE equipment_slots aw JOIN equipment_slots sh ON sh.character_id = aw.character_id AND sh.slot_type='shield' AND sh.item_id IS NOT NULL SET aw.item_id=sh.item_id, aw.enhancement_points_spent=sh.enhancement_points_spent, aw.enhancement_bonuses=sh.enhancement_bonuses, aw.socketed_gems=sh.socketed_gems, aw.current_durability=sh.current_durability, sh.item_id=NULL, sh.enhancement_points_spent=0, sh.enhancement_bonuses=NULL, sh.socketed_gems=NULL, sh.current_durability=NULL WHERE aw.slot_type='additional_weapons' AND aw.item_id IS NULL`
2. **Return remaining equipped shields (off-hand taken) to inventory**, preserving enhancement/socket/durability columns: `INSERT INTO character_inventory (character_id, item_id, quantity, enhancement_points_spent, enhancement_bonuses, socketed_gems, current_durability, ...) SELECT ... FROM equipment_slots WHERE slot_type='shield' AND item_id IS NOT NULL` then NULL-out those slot rows. *Known accepted limitation:* attribute modifiers of such shields are NOT subtracted from `character_attributes` (no HTTP from a migration). Verified counts: dev DB has **0 equipped shields, 0 shield items**; shields were never seeded — this path is a safety net, expected to touch 0 rows.
3. `DELETE FROM equipment_slots WHERE slot_type='shield'` (all now-empty rows).
4. `ALTER TABLE equipment_slots MODIFY COLUMN slot_type ENUM(... without 'shield' ...) NOT NULL` — full current member list minus `shield`. **Do NOT touch `items.item_type`.**

`downgrade()` (rollback strategy — mirror of `002_add_shield.py` upgrade):
1. Re-add `'shield'` to the `slot_type` ENUM (ALTER).
2. Re-insert one empty `shield` slot per character that has equipment slots and lacks one (same `INSERT ... SELECT DISTINCT ... WHERE NOT EXISTS` as 002). Items moved to off-hand/inventory by `upgrade()` are intentionally not moved back (lossless for data, acceptable for rollback).

Rollback of code = git revert; DB rollback = `alembic downgrade -1`. Since `upgrade()` is idempotent-by-construction (steps operate only on `slot_type='shield'` rows), a failed mid-migration container restart re-runs it safely.

### 3.2 Frontend — component architecture

**Breakpoint decision:** mock switches at ≤920px; closest Tailwind breakpoint is `lg` (1024px). Desktop 3-panel grid at `lg:`+, single column below; everything must fit 360px (T5). Rationale: no custom breakpoint proliferation; 920→1024 only widens the "mobile" band, which the single-column layout handles fine.

**Layout (`CharacterTab.tsx`):** replace the current `LeftColumn/CenterColumn/RightColumn` grid with
`grid grid-cols-1 lg:grid-cols-[392px_minmax(300px,352px)_1fr] gap-5 items-start`.
Desktop panels: `lg:h-[calc(100vh-130px)]` with internal `overflow-y-auto gold-scrollbar-wide`; mobile: auto height, no inner scroll. `InventoryDndProvider` continues to wrap all three panels (DnD spans panels 1↔3); `ItemContextMenu` + `ItemDetailModal` stay mounted at this level — **their internals are untouched**.

**New shared shell — `ProfilePage/PanelShell.tsx`:** one wrapper used by all three panels: dark translucent bg + blur + gold border + shadow + optional header row (icon + gold uppercase title + right-side extra). Style with existing tokens only: `bg-site-bg backdrop-blur-[10px] gold-outline relative rounded-card shadow-card`; header row `border-b` via `gradient-divider-h`, title `gold-text text-sm font-medium uppercase tracking-[0.12em]`. No new CSS files; mock's exact rgba values are NOT copied — current design-system tokens per user decision.

**Component map (what moves, what dies, what stays):**

| New component | Content | Source of moved code |
|---|---|---|
| `CharacterTab/CharacterPanel.tsx` (panel 1, 392px) | Identity header (gold LVL circle, name `gold-text uppercase`, active title in rarity color, `раса \| класс`); paper-doll `AvatarEquipmentGrid` (reworked, no shield slot); XP bar + «Очки прокачки»; currency + active XP row (existing `gold-coins.svg`); `FastSlots` 5×2 | name/title/race/class + currency + active XP from `LeftColumn.tsx`; LVL + XP bar + stat points from `CenterColumn.tsx` |
| `CharacterTab/IndicatorsPanel.tsx` (panel 2) | «Показатели»: `StatsPanel` (vitals, icon-only labels), `PrimaryStatsSection` (tier bars — reuse as-is), `StatDistributionPanel` (only when `stat_points > 0`), `DerivedStatsSection` (redesigned: 2-col stat cards + resist chips) | stats stack from `LeftColumn.tsx` |
| `CharacterTab/InventoryPanel.tsx` (panel 3, 1fr) | Header (bag icon + «Инвентарь» + counter = **item count only**, `inventory.length`, no cap — user decision); horizontal category chips row (horiz. scroll); circular item grid; empty-category state | `RightColumn.tsx` |

`LeftColumn.tsx`, `CenterColumn.tsx`, `RightColumn.tsx` are **deleted** after their content is absorbed.

**Reworked components (visual only — DnD ids/data contracts preserved):**
- `AvatarEquipmentGrid.tsx` — new diamond per mock: head top-center; left column top→bottom `main_weapon, body, ring, belt`; right column `additional_weapons, cloak, necklace, bracelet`; **no shield cell** (remove `getSlot('shield')`). Portrait keeps upload flow untouched. Mobile: grid compresses (slot ≈46px, `max-w-[320px] mx-auto`).
- `EquipmentPanel/FastSlots.tsx` — grid `grid-cols-2` → `grid-cols-5` (5×2, all 10 slots; disabled slots stay dimmed `opacity-30` — user decision). Keep droppable ids `drop-fast_slot-${i}` and drag ids exactly.
- `EquipmentPanel/EquipmentSlot.tsx` — visual polish only (circular cell, enh badge per mock position); keep `drop-equipment-*` droppable id, drag data, durability/enh badges logic.
- `CharacterInfoPanel/StatsPanel.tsx` — vitals get **icon-only labels** (no text — user decision): `lucide-react` `Heart / Droplet / Zap / Wind` colored with existing `stat-hp/mana/energy/stamina` tokens + `title` tooltip for a11y; numeric `cur/max` stays right-aligned; bars keep `stat-bar`/`stat-bar-fill` classes.
- `StatsTab/DerivedStatsSection.tsx` — split real `DERIVED_STATS` into: «В бою» 2-col cards (`damage` — with existing class/weapon calc, `dodge`, `critical_hit_chance`, `critical_damage`) and resist chips (`res_*` as rounded-full pills with colored dot + value). **Mock's «Инициатива»/«Блок» do not exist — dropped, real stats only.**
- `InventoryTab/CategorySidebar.tsx` — vertical icon list → **horizontal icon-only chips** (round pills, gold-tinted when active, `title` tooltip; no text labels — user decision), horizontally scrollable, existing `CATEGORY_LIST` icons/keys unchanged (shield category stays).
- `InventoryTab/ItemGrid.tsx` — `grid-cols-4` squares → `grid-template-columns: repeat(auto-fill,minmax(64px,1fr))` circular cells; **drop `MIN_GRID_CELLS` filler cells**, add empty-category state («В этой категории пусто» + dim icon). Droppable `drop-inventory-grid` stays on the scroll container (unequip-by-drop still works with few items).
- `InventoryTab/ItemCell.tsx` — visual fit to 64px circle, qty badge bottom-right / enh badge top-right per mock; drag contract untouched.

**Untouched:** `InventoryDndContext.tsx` (logic), `ItemDetailModal.tsx` internals, `ItemContextMenu.tsx`, `RepairModal.tsx`, `profileSlice.ts` (state/thunks/selectors), `ProfileTabs.tsx` (already matches mock), all other tabs, `NpcProfileModal` (no equipment-slot rendering found — verify only).

### 3.3 Frontend — shield cleanup (shield remains an ITEM TYPE — most files need nothing)

| File | Change |
|---|---|
| `ProfilePage/constants.ts` | Remove `'shield'` from `EQUIPMENT_SLOT_ORDER` and the `shield` key from `EQUIPMENT_SLOT_LABELS` (slot-scoped). **Keep** `ITEM_TYPE_ICONS.shield`, `CATEGORY_LIST` shield entry, `'shield'` in `EQUIPMENT_TYPES` (it is still an equippable item type). |
| `InventoryTab/dnd/constants.ts` | `EQUIPMENT_ITEM_TYPES`: change `shield: 'shield'` → `shield: 'additional_weapons'` (mirrors backend `find_equipment_slot_for_item`). **Keep** `ITEM_TYPES` and `ITEM_TYPE_LABELS.shield` unchanged. |
| `AdminNpcsPage/NpcEquipmentEditor.tsx` | Remove `'shield'` from `NPC_SLOT_TYPES` and the `shield` key from `SLOT_LABELS` (slot-scoped; mirrors backend `NPC_EQUIPMENT_SLOTS`). |
| `EquipmentPanel/EquipmentPanel.tsx` | Legacy — only imported by `ProfilePage/InventoryTab/InventoryTab.tsx`, which is itself unrouted (ProfilePage renders `CharacterTab`). Remove `'shield'` from its `accessorySlots` array for consistency; do not delete files in this feature. |
| `ItemsAdminPage/ItemForm.tsx`, `ItemsAdminPage.tsx`, `ItemList.tsx` | **No change** — item_type select/filter/labels; shield stays a type. Verify only. |
| `Auction/AuctionFilters.tsx` | **No change** — «Щит» is an item-type filter. Verify only. |
| `InventoryTab/ItemDetailModal.tsx` | **No change** — «Щит» is an item-type label. |
| `CraftTab/*` (Sharpening/RuneSocket/GemSocket) | **No change** — item-type based, shields stay sharpenable/socketable. |

### 3.4 Data flow (equip a shield)

```
User drags shield item → drop on additional_weapons slot (frontend: EQUIPMENT_ITEM_TYPES['shield'] → 'additional_weapons', slot pulses)
  → dispatch equipItem → POST /inventory/{characterId}/equip (unchanged contract)
    → inventory-service find_equipment_slot_for_item: 'shield' → additional_weapons slot (FOR UPDATE)
    → occupied? → existing occupied-slot error (Russian toast) ; free? → transactional equip
    → HTTP apply_modifiers → character-attributes-service ; evaluate-titles → character-service (unchanged)
  → fetchEquipment/fetchInventory refresh → shield renders in the off-hand cell
Battle: battle-service fetch_weapons reads additional_weapons row → shield selectable as off-hand weapon, durability loss via existing DURABILITY_SLOT_TYPES (no code change).
```

### 3.5 Security

- No new endpoints; no auth surface change. Equip/unequip keep existing `get_current_user_via_http` ownership checks; admin NPC equip keeps `get_admin_user` RBAC and now server-side rejects `slot_type='shield'` via the shrunk `NPC_EQUIPMENT_SLOTS` (defense in depth vs. stale clients).
- Migration is static SQL — no user input, no secrets, safe error surface.
- Frontend: all thunks already reject with Russian messages via react-hot-toast — every touched flow must keep visible error handling (mandatory rule).
- Rate limiting/input validation: unchanged (no new inputs).

### 3.6 Key risks carried into tasks

1. ENUM shrink ordering (mitigated: data cleanup before ALTER in one migration, dev counts verified 0/0/1-empty).
2. DnD regressions from layout rewrite (mitigated: droppable/draggable ids and data payloads are frozen contracts; Reviewer live-verifies drag flows).
3. Stale `test_unequip_shield.py` TestShieldSupport + shield fixtures will fail → QA task rewrites them in this feature.
4. `-mt-12` shell offset vs `calc(100vh-130px)` panel heights — FE task must reconcile with the site header without page-level horizontal scroll at 360px.

No open questions — all four user decisions in section 1 cover the ambiguities found by the Analyst.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Parallelism: T1 (backend) ∥ T3 (frontend scaffolding) start together — the HTTP contract is unchanged, only internal mappings move. T4 ∥ T5 run in parallel after T3 (disjoint file ownership). T2 after T1. T6 last.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | **Remove shield equipment slot (Option A)**: strip `'shield'` from `EquipmentSlot.slot_type` ENUM in models, from `create_default_equipment_slots` and `NPC_EQUIPMENT_SLOTS`; remap `is_item_compatible_with_slot` (`additional_weapons` accepts `['additional_weapons','shield']`) and `find_equipment_slot_for_item` (`'shield' → 'additional_weapons'`); keep `Items.item_type` ENUM, `schemas.ItemType`, SHARPENABLE/SOCKETABLE sets untouched. New Alembic migration `017_remove_shield_slot.py` exactly per section 3.1 (move equipped shields to free off-hand → else to inventory preserving enh/socket/durability cols → delete shield slot rows → ENUM ALTER; downgrade mirrors 002). | Backend Developer | DONE | `services/inventory-service/app/models.py`, `app/crud.py`, `app/alembic/versions/017_remove_shield_slot.py` | — | `python -m py_compile` on all modified files passes; `alembic upgrade head` succeeds on dev DB and `equipment_slots` has zero `shield` rows; `alembic downgrade -1` restores ENUM + empty shield slots; new character/NPC slot creation yields no shield slot; `curl` equip of a shield item lands in `additional_weapons`; equip with occupied off-hand returns the existing Russian occupied-slot error; grep of `main.py`/`schemas.py` confirms no slot-type `shield` literals remain |
| 2 | **QA: rewrite shield tests for off-hand semantics.** Rework `test_unequip_shield.py` (drop `TestShieldSupport` assertions about the shield slot; add: shield equips into `additional_weapons`; equip when off-hand occupied fails; unequip returns shield with enh/durability preserved; `create_default_equipment_slots` creates no shield slot; `is_item_compatible_with_slot('shield','additional_weapons') is True` and `('shield','shield') is False`; `admin_equip_npc_item` rejects `slot_type='shield'`). Fix shield fixtures in `test_npc_equipment.py`, `test_sharpening.py`, `test_crafting.py` (shield item type stays valid — only slot expectations change). Include a security case: equip endpoint without/with foreign JWT still rejected. | QA Test | DONE | `services/inventory-service/app/tests/test_unequip_shield.py`, `tests/test_npc_equipment.py`, `tests/test_sharpening.py`, `tests/test_crafting.py` | 1 | Full inventory-service `pytest` suite green; new cases cover all behaviors listed; no test references the `shield` slot_type as valid |
| 3 | **FE scaffolding: 3-panel layout + shared shell + constants/dnd remap.** Rewrite `CharacterTab.tsx` to `grid-cols-1 lg:grid-cols-[392px_minmax(300px,352px)_1fr]` (panels: paper doll / indicators / inventory; `lg:h-[calc(100vh-130px)]` + inner `gold-scrollbar-wide` scroll on desktop, auto height below `lg`). Create `PanelShell.tsx` (tokens per section 3.2). Create `CharacterPanel.tsx` / `IndicatorsPanel.tsx` / `InventoryPanel.tsx` as shells that initially absorb the existing LeftColumn/CenterColumn/RightColumn content **wholesale** (build stays green; T4/T5 restyle internals). Update `constants.ts` (remove `shield` from `EQUIPMENT_SLOT_ORDER`/`EQUIPMENT_SLOT_LABELS` only) and `dnd/constants.ts` (`EQUIPMENT_ITEM_TYPES.shield = 'additional_weapons'`); remove `'shield'` from legacy `EquipmentPanel.tsx` `accessorySlots`. Delete `LeftColumn.tsx`/`CenterColumn.tsx`/`RightColumn.tsx` once absorbed. | Frontend Developer | DONE | `ProfilePage/CharacterTab/CharacterTab.tsx`, `ProfilePage/PanelShell.tsx` (new), `CharacterTab/CharacterPanel.tsx` (new), `CharacterTab/IndicatorsPanel.tsx` (new), `CharacterTab/InventoryPanel.tsx` (new), `CharacterTab/LeftColumn.tsx` (delete), `CharacterTab/CenterColumn.tsx` (delete), `CharacterTab/RightColumn.tsx` (delete), `ProfilePage/constants.ts`, `InventoryTab/dnd/constants.ts`, `EquipmentPanel/EquipmentPanel.tsx` | — | `npx tsc --noEmit` and `npm run build` pass; /profile renders 3 panels in mock order on desktop and single column <1024px; DnD equip/unequip still works; dragging a shield item highlights the `additional_weapons` slot; no `React.FC`, Tailwind only, design-system tokens only |
| 4 | **FE panel 1 — paper doll redesign.** In `CharacterPanel.tsx`: identity header (gold LVL circle, name, rarity-colored title, `раса \| класс`), then reworked `AvatarEquipmentGrid` (diamond per mock: head top; left `main_weapon/body/ring/belt`; right `additional_weapons/cloak/necklace/bracelet`; **no shield cell**; portrait upload flow untouched; mobile ≈46px slots, `max-w-[320px] mx-auto`), XP bar + «Очки прокачки», currency + active XP row (`gold-coins.svg`), `FastSlots` as 5×2 grid of all 10 slots (disabled dimmed). Visual polish of `EquipmentSlot.tsx` (circular cell, enh badge) preserving all DnD ids/data and badge logic. Icons: existing project SVGs only, no text labels next to icons. | Frontend Developer | DONE | `CharacterTab/CharacterPanel.tsx`, `CharacterTab/AvatarEquipmentGrid.tsx`, `EquipmentPanel/FastSlots.tsx`, `EquipmentPanel/EquipmentSlot.tsx` | 3 | `npx tsc --noEmit` + `npm run build` pass; no shield slot rendered; fast slots show 5×2 with disabled ones dimmed; drag-equip/unequip and context menu work on desktop and touch; layout fits 360px without horizontal scroll |
| 5 | **FE panels 2+3 — indicators & inventory redesign + NPC editor slot cleanup.** Panel 2 (`IndicatorsPanel.tsx`): `StatsPanel` vitals with lucide-react icon-only labels (Heart/Droplet/Zap/Wind, stat-* color tokens, `title` tooltips), `PrimaryStatsSection` tier bars, `StatDistributionPanel` when points > 0, `DerivedStatsSection` reworked into «В бою» 2-col cards (damage/dodge/crit chance/crit dmg, existing calc props) + `res_*` resist chips — **real stats only, no Инициатива/Блок**. Panel 3 (`InventoryPanel.tsx`): header with item-count-only counter, `CategorySidebar` → horizontal icon-only chip row (scrollable), `ItemGrid` → auto-fill 64px circular cells without `MIN_GRID_CELLS` fillers + empty-category state (Russian), `ItemCell` circular w/ qty/enh badges; keep `drop-inventory-grid` + all drag contracts. Remove `'shield'` from `NPC_SLOT_TYPES`/`SLOT_LABELS` in `NpcEquipmentEditor.tsx`. `ItemDetailModal`/`ItemContextMenu` internals untouched. | Frontend Developer | DONE | `CharacterTab/IndicatorsPanel.tsx`, `CharacterInfoPanel/StatsPanel.tsx`, `StatsTab/DerivedStatsSection.tsx`, `StatsTab/PrimaryStatsSection.tsx` (light), `StatsTab/StatDistributionPanel.tsx` (light), `CharacterTab/InventoryPanel.tsx`, `InventoryTab/CategorySidebar.tsx`, `InventoryTab/ItemGrid.tsx`, `InventoryTab/ItemCell.tsx`, `AdminNpcsPage/NpcEquipmentEditor.tsx` | 3 | `npx tsc --noEmit` + `npm run build` pass; vitals show icons without text labels; combat cards + resist chips render real values; category chips scroll horizontally, filter works, shield category still present; unequip by dragging to grid works; empty category shows Russian empty state; NPC editor offers no shield slot; fits 360px |
| 6 | **Review + live verification.** Re-run: inventory-service pytest, `py_compile`, `npx tsc --noEmit`, `npm run build`, `alembic upgrade head` on dev. Live (MCP chrome-devtools, admin creds from memory refs): /profile desktop ≥1024px shows 3 mock-ordered panels with zero console errors; create/equip a **shield item → lands in off-hand slot**, occupied off-hand shows Russian error, unequip returns it; DnD inventory↔equipment↔fast-slots; fast slots 5×2 dimmed-disabled; category chips filter incl. «Щит»; item modal actions; resize 920px and 360px — single column, no horizontal scroll, touch DnD; admin NPC editor has no shield slot; auction filter «Щит» still works. Verify `docs/ISSUES.md` reflects any bugs found. | Reviewer | DONE | — | 1, 2, 3, 4, 5 | All automated checks green; all live checks pass with zero console/network errors; review verdict PASS recorded in section 5 |

Task statuses final: 1-5 DONE, 6 DONE (Review #1 PASS).

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-07-17
**Result:** PASS

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (0 errors)
- [x] `npm run build` — PASS (built successfully; pre-existing SCSS deprecation warnings + chunk-size warning only, unrelated to this feature)
- [x] `py_compile` — PASS (`crud.py`, `models.py`, `test_npc_equipment.py`, `test_unequip_shield.py`, `017_remove_shield_slot.py`)
- [x] `pytest` inventory-service full suite — PASS (**444 passed, 0 failed**, fresh Pydantic-v1 venv)
- [x] `docker-compose config` — PASS
- [x] Migration state on dev DB — `alembic_version_inventory = 017_remove_shield_slot`; `equipment_slots.slot_type` ENUM has no `shield`; 0 shield slot rows
- [x] Live verification (chrome-devtools + curl) — PASS (details below)

#### Code Review
- Backend diff exactly matches section 3.1: slot ENUM shrunk (`models.py`), `create_default_equipment_slots` / `NPC_EQUIPMENT_SLOTS` without shield, `is_item_compatible_with_slot` → `additional_weapons: ['additional_weapons','shield']`, `find_equipment_slot_for_item` → `'shield': 'additional_weapons'`. `Items.item_type`, `schemas.ItemType`, SHARPENABLE/SOCKETABLE/ARMOR_WEAPON sets untouched. Grep confirms zero slot-type `shield` literals left in `main.py`/`schemas.py`/`crud.py`/`models.py`.
- Migration 017: data cleanup strictly before ENUM ALTER (move-to-free-off-hand → return-to-inventory preserving enh/sockets/durability → delete slot rows → ALTER); columns match `CharacterInventory`/`EquipmentSlot` models; `downgrade()` mirrors 002; steps operate only on `slot_type='shield'` rows (safe re-run). Known accepted limitation (modifiers of force-returned shields) documented in the file, matches §3.1.
- QA tests: `TestShieldOffhand` (16 tests) + `TestShieldEquipSecurity` (401/403) cover the full task-2 list; occupied off-hand is verified as the standard swap flow (matches actual pre-existing equip behavior — the "fails" wording in task 2 was superseded by reality, correct call). `test_npc_equipment.py` updated to 9 slots.
- Frontend: DnD id/payload contracts untouched (`drop-equipment-*`, `drop-fast_slot-N`, `drop-inventory-grid`, drag ids/data intact — verified in diff and live). No `React.FC`, no new `.jsx`/SCSS, no TODO/FIXME. All UI strings Russian. Icons are existing project SVGs + lucide-react (already a dependency); icon-only labels with `title`/`aria-label` tooltips. Styling uses design-system tokens only (`gold-*`, `site-*`, `stat-*`, `rarity-*`, `rounded-card`, `shadow-card`, `stat-bar`, `gold-outline`, `gradient-divider-h`, `skill-point-dot`); the one inline gradient in `CharacterPanel.tsx` is the pre-existing XP-bar gradient already used in `index.css`/`CharacterCard.tsx` (not a mock hex import).
- Restyled shared sections (`PrimaryStatsSection`, `StatDistributionPanel`, `DerivedStatsSection`, `StatsPanel`) are otherwise consumed only by unrouted legacy components (`StatsTab`, `CharacterInfoPanel`/`InventoryTab`) — no external visual regressions.
- `NpcEquipmentEditor` off-hand picker `item_types='additional_weapons,shield'` matches backend comma-list parsing (`main.py:131`) — verified by curl.

#### Live Verification Results (admin `chaldea@admin.com`, character 1)
- Pages tested: `/profile` (1440px, 1280px, 920px, 360px emulated mobile), `/admin/npcs` (+ equipment editor), `/auction`.
- Console errors: **NONE** (only pre-existing React Router v7 future-flag warnings). Network: all XHR 200, no failed requests.
- Desktop 1440/1280: 3 panels in mock order (paper doll / Показатели / Инвентарь); identity header (LVL circle, name, race | class); 9-slot diamond, **no shield cell**; XP bar + Очки прокачки; currency + Актив. опыт row; fast slots 5×2 (10 cells, disabled dimmed). Vitals icon-only bars; Характеристики tier bars; «В бою» 2-col cards + 13 resist chips; inventory header count-only counter, horizontal category chips (incl. «Щит»), circular auto-fill grid.
- **Shield flow (created test shield id 40 + off-hand dagger id 41 via admin API, cleaned up after):** equip shield → lands in `additional_weapons` (API + UI); drag shield from grid → **only the off-hand slot pulses** (`slot-pulse-compatible`) and drop equips it; equip dagger over shield → graceful swap, shield returns to inventory; unequip preserves item; `POST /unequip?slot_type=shield` → 404 «Слот пуст или не найден».
- DnD flows (PointerSensor, simulated pointer events): inventory→equipment equip (body armor), equipment→grid unequip, occupied-slot swap, potion→fast-slot drop — all work; badges render (qty badge on fast slot).
- Item detail modal: opens from context menu («Описание»), shows rarity/type/durability/description/stats/price, closes cleanly. Context menu actions in Russian.
- Empty category state: «Щит» chip with no shield items shows «В этой категории пусто» + dim bag icon.
- Mobile: 920px single column; 360px emulated (mobile+touch) — `scrollWidth == innerWidth` (no horizontal scroll), diamond compressed ≈46px slots centered, cards/chips wrap, everything reachable.
- NPC editor (created test NPC id 8, deleted after): **9 slots, no «Щит» slot**; «Доп. оружие» picker offers both shield and off-hand weapon; equipping the shield onto the NPC off-hand slot works; unequip works.
- `/auction`: «Щит» item-type filter still present, page loads without errors.

#### Adjudication of Developer Deviations
1. **«Инициатива» kept in «В бою» cards — ACCEPT.** It is a real computed value (FEAT-143), was displayed on this page before the redesign; removing it would be a functional regression. The task's "real stats only" intent is honored — only the non-existent «Блок» was dropped. Tooltip documents the formula.
2. **NPC off-hand picker requests `item_types='additional_weapons,shield'` — ACCEPT.** Mirrors backend slot compatibility exactly; without it shields would be un-equippable on NPCs (admin flow has no DnD). Verified live end-to-end. Backend endpoint natively supports comma-separated `item_types`.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `ProfilePage/constants.ts:98,252` | `MIN_GRID_CELLS` and `DERIVED_STATS` are now dead code after the redesign (non-blocking cleanup) | Frontend Developer | LOGGED as ISSUES.md #26 (LOW), does not block PASS |

#### Pre-existing issues noted
- React Router v7 future-flag console warnings (site-wide, unrelated).
- SCSS `if()` deprecation warnings in `npm run build` from legacy `global.scss`/`TooltipPortal.module.scss` (T1 migration scope, unrelated).

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-07-16 — PM: фича создана, макеты импортированы из Claude Design (features/design-refs/FEAT-149-profile-CharacterProfile.dc.html), запускаю Codebase Analyst
[LOG] 2026-07-16 — Analyst: анализ завершён. Затронуты frontend (весь ProfilePage — уже .tsx/Tailwind, без долгов T1/T3) и inventory-service (ENUM'ы item_type/slot_type, слоты, Alembic-миграция). В живой dev-БД щитов нет: 0 предметов, 0 экипировано, 1 пустой слот. Battle/character/skills/autobattle сервисы «shield» не упоминают. Все данные макета доступны из текущих API, кроме лимита инвентаря (N/120) и несуществующих статов «Инициатива»/«Блок». 4 вопроса к PM (тип предмета щита, поведение в бою, счётчик инвентаря, раскладка быстрых слотов).
[LOG] 2026-07-17 — Architect: проектирование завершено. Вариант A: тип 'shield' остаётся, слот «Щит» удаляется (ENUM slot_type, миграция 017 с переносом экипированных щитов в доп. оружие/инвентарь, откат зеркалит 002). Фронтенд: 3 панели (392px / minmax(300px,352px) / 1fr, брейкпоинт lg=1024px), общий PanelShell, иконки без подписей, быстрые слоты 5×2, счётчик — только количество; DnD-контракты и ItemDetailModal не трогаем. 6 задач: 1 backend ∥ 1 FE-каркас, затем 2 FE параллельно, QA после backend, Reviewer в конце. Вопросов к PM нет.
[LOG] 2026-07-17 — Backend Dev: задача #1 завершена. inventory-service: слот 'shield' убран из ENUM (models.py), из create_default_equipment_slots и NPC_EQUIPMENT_SLOTS; щит теперь экипируется в additional_weapons (is_item_compatible_with_slot, find_equipment_slot_for_item). Тип предмета 'shield', schemas.ItemType и SHARPENABLE/SOCKETABLE не тронуты. Миграция 017_remove_shield_slot: upgrade и downgrade прогнаны на dev-БД (цикл 016→017→016→017 без ошибок, shield-строк 0). py_compile — OK; pytest: 428 passed, 10 failed — все 10 падают только по ожидаемой причине (утверждения про слот 'shield' / 10 NPC-слотов), перепишет QA в задаче #2: test_unequip_shield.py::TestShieldSupport (6 тестов) и test_npc_equipment.py (4 теста).
[LOG] 2026-07-17 — Frontend Dev: задача #3 завершена. Каркас 3-панельной сетки в CharacterTab (grid-cols-1 / lg:grid-cols-[392px_minmax(300px,352px)_1fr], gap-5), создан общий PanelShell.tsx (bg-site-bg + backdrop-blur + gold-outline + shadow-card, опциональная шапка: иконка + золотой заголовок + headerExtra; экспорт PANEL_DESKTOP_HEIGHT_CLASS = lg:h-[calc(100vh-130px)]). Созданы CharacterPanel/IndicatorsPanel/InventoryPanel — контент LeftColumn/CenterColumn/RightColumn перенесён целиком, старые файлы удалены. constants.ts: 'shield' убран из EQUIPMENT_SLOT_ORDER/EQUIPMENT_SLOT_LABELS (тип предмета и категория сохранены); dnd/constants.ts: EQUIPMENT_ITEM_TYPES.shield → 'additional_weapons'; из легаси EquipmentPanel.tsx убран слот 'shield'. Проверки: npx tsc --noEmit — 0 ошибок, npm run build — успешно.
[LOG] 2026-07-17 — QA: задача #2 завершена. test_unequip_shield.py: класс TestShieldSupport переписан в TestShieldOffhand (16 тестов: тип 'shield' сохранён в схемах/модели/заточке/сокетах; слот 'shield' удалён из ENUM и create_default_equipment_slots — 9 слотов экипировки + 10 быстрых; совместимость shield→additional_weapons, shield→shield невалидно; find_equipment_slot_for_item → additional_weapons; экипировка через эндпоинт попадает в additional_weapons; занятый офф-хенд — штатный swap с возвратом старого предмета в инвентарь; снятие с сохранением заточки/прочности; unequip слота 'shield' → 404; admin_equip_npc_item отклоняет slot_type='shield') + TestShieldEquipSecurity (без токена 401, чужой персонаж 403). test_npc_equipment.py: 4 теста обновлены на 9 NPC-слотов. test_sharpening.py/test_crafting.py правок не требуют (используют только тип предмета 'shield'). Полный прогон pytest inventory-service: 444 passed, 0 failed.
[LOG] 2026-07-17 — Frontend Dev: задача #4 завершена. Панель 1 «Персонаж» по макету: шапка-identity в затемнённой полосе (bg-black/20 + gradient-divider-h) — золотой круг LVL (градиент gold-light→gold-dark, свечение), имя gold-text, титул в цвете редкости, раса | класс. AvatarEquipmentGrid переделан в ромб макета: шлем сверху; слева — осн. оружие, броня, кольцо, пояс; справа — доп. оружие, плащ, ожерелье, браслет; ячейка щита удалена (getSlot('shield') убран); мобильный ≤lg — слоты 46px, сетка max-w-[320px] по центру; загрузка портрета не тронута. XP-бар («Опыт» + значения, stat-bar с золотым градиентом) + «Очки прокачки» (skill-point-dot); строка валюта (gold-coins.svg без подписи) + «Актив. опыт» с рамками border-y по макету. FastSlots: сетка 5×2 на все 10 слотов, ячейки резиновые (aspect-square), заблокированные затемнены opacity-30, добавлен бейдж количества снизу-справа; DnD-идентификаторы (drop-fast_slot-N, fast-equipment-*, drop-equipment-*, equipment-*) не изменены. EquipmentSlot: визуально — размер small теперь 46px/56px (моб/десктоп) через Tailwind-классы, инлайн-размеры убраны. Проверки: npx tsc --noEmit — 0 ошибок, npm run build — успешно (built in 11.8s).
[LOG] 2026-07-17 — Frontend Dev: задача #5 завершена. Панель 2 «Показатели»: StatsPanel — виталы с иконками без подписей (lucide Heart/Droplet/Zap/Wind, цвета stat-hp/mana/energy/stamina, русский label в title/aria-label), значения справа (gold-text), бары stat-bar; PrimaryStatsSection — заголовок «Характеристики» с угасающей золотой линией, одна колонка тир-баров; StatDistributionPanel — заголовок секции в том же стиле, одна колонка (панель узкая); DerivedStatsSection переписан: секция «В бою» — карточки 2 колонки (Урон и Инициатива подсвечены золотом; Уклонение/Крит. шанс/Крит. урон обычные) + 13 чипов сопротивлений (res_*) с цветными точками из токенов палитры и полным названием в title. Несуществующий «Блок» из макета отброшен; «Инициатива» сохранена — это реальное вычисляемое значение FEAT-143, уже отображавшееся на странице (отход от буквы задания, помечено PM на решение). Панель 3 «Инвентарь»: счётчик — только количество (font-mono); CategorySidebar — горизонтальный ряд круглых чипов-иконок без текста (title/aria-label, активный — border-gold/50 + bg-gold/10, тонкий 3px скроллбар); ItemGrid — grid repeat(auto-fill,minmax(64px,1fr)), филлеры MIN_GRID_CELLS удалены, пустое состояние «В этой категории пусто» с тусклой иконкой сумки; ItemCell — резиновая круглая ячейка (w-full aspect-square), бейджи кол-ва (низ-право) и заточки (верх-право) сохранены; droppable drop-inventory-grid и все drag-контракты не тронуты. NpcEquipmentEditor: слот 'shield' убран из NPC_SLOT_TYPES/SLOT_LABELS; пикер для additional_weapons теперь запрашивает item_types='additional_weapons,shield' (зеркалит бэкенд, иначе щит нельзя было бы надеть на НПС). Проверки: npx tsc --noEmit — 0 ошибок; npm run build — успешно; live-смоук через chrome-devtools: 1440px — 3 панели, консоль без ошибок; пустая категория — русское пустое состояние; 360px — одна колонка без горизонтального скролла.
[LOG] 2026-07-17 — Reviewer: начал проверку (задача #6): автоматические проверки, код-ревью диффа, live-верификация через chrome-devtools.
[LOG] 2026-07-17 — Reviewer: автоматические проверки зелёные: pytest inventory-service 444 passed, py_compile OK, tsc 0 ошибок, npm run build OK, docker compose config OK; dev-БД на ревизии 017, shield-строк в equipment_slots нет, ENUM сокращён.
[LOG] 2026-07-17 — Reviewer: live-верификация пройдена: /profile (1440/1280/920/360) — 3 панели по макету, ромб из 9 слотов без щита, быстрые слоты 5×2 с затемнёнными недоступными, консоль чистая, все запросы 200. Щит-флоу проверен вживую (созданы и удалены тестовые предметы): экипировка в additional_weapons, подсветка только офф-хенд слота при перетаскивании, swap при занятом слоте, снятие, unequip слота 'shield' → 404. DnD (equip/unequip/swap/быстрый слот), модалка предмета, пустая категория, чипы категорий с «Щит» — работают. NPC-редактор: 9 слотов без щита, пикер офф-хенда предлагает щиты, экипировка щита на НПС работает. Аукцион: фильтр «Щит» на месте.
[LOG] 2026-07-17 — Reviewer: оба отклонения разработчиков приняты (ACCEPT): «Инициатива» — реальное значение FEAT-143, удаление было бы регрессией; item_types='additional_weapons,shield' в пикере НПС — зеркалит бэкенд, иначе щит не надеть на НПС.
[LOG] 2026-07-17 — Reviewer: найден мелкий неблокирующий мусор — неиспользуемые константы MIN_GRID_CELLS и DERIVED_STATS в ProfilePage/constants.ts, добавлено в ISSUES.md (#26, LOW).
[LOG] 2026-07-17 — Reviewer: проверка завершена, результат PASS.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- **Страница `/profile` перекомпонована по макету**: три панели («Персонаж» 392px / «Показатели» / «Инвентарь»), общий `PanelShell` (полупрозрачный фон + blur + золотая обводка + тень) на токенах текущей дизайн-системы; на <1024px — одна колонка, всё помещается на 360px.
- **Панель «Персонаж»**: identity-шапка (золотой круг LVL, имя, титул в цвете редкости, раса | класс), ромб экипировки из 9 слотов вокруг портрета (**слот «Щит» удалён**), XP-бар + очки прокачки, монеты + актив. опыт, быстрые слоты 5×2 (все 10, заблокированные затемнены).
- **Панель «Показатели»**: бары ресурсов с иконками без текстовых подписей (lucide, названия в тултипах), «Характеристики» с тир-барами, «В бою» (карточки 2 колонки) + чипы сопротивлений — все данные реальные («Блок» из макета не существует — не добавлен; «Инициатива» реальная — оставлена).
- **Панель «Инвентарь»**: горизонтальные иконки-чипы категорий, круглая сетка предметов (auto-fill 64px), счётчик = только количество, пустое состояние; DnD-контракты заморожены.
- **Удаление слота «Щит» (Option A)**: тип предмета `shield` сохранён; в inventory-service слот удалён из ENUM/создания слотов/NPC, совместимость перенастроена (щит → слот доп. оружия), миграция `017_remove_shield_slot` (проверена на dev полным циклом up/down/up). Battle-service без изменений — прочность щита в бою работает автоматически. Редактор NPC: слот щита удалён, подборщик доп. оружия предлагает щиты.
- **Тесты**: 444 зелёных в inventory-service (переписаны 10 щитовых + добавлены новые, вкл. security-кейсы 401/403 и graceful swap занятого слота).

### Что изменилось от первоначального плана
- Две согласованные девиации (обе ACCEPT на ревью): «Инициатива» оставлена (реальный показатель FEAT-143); подборщик предметов NPC расширен на `additional_weapons,shield`.
- Ревью пройдено с первого раза (PASS, Review #1), включая живой сценарий: создание щита → экипировка в слот доп. оружия → swap → снятие.

### Оставшиеся риски / follow-up задачи
- ISSUES.md #26 (LOW): неиспользуемые `MIN_GRID_CELLS` и `DERIVED_STATS` в `ProfilePage/constants.ts` — мёртвый код после редизайна, отдельная чистка.
- На prod миграция 017 применится автоматически при деплое (щитов в базе нет — безопасно).
