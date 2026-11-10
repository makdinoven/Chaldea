# FEAT-210: Админка айтемов и мобов — раскрывающиеся плашки, «Готов», фильтры

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-10 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сделать разделы «Айтемы» (`/admin/items`, `components/ItemsAdminPage/`) и «Мобы» (`/admin/mobs`, `components/Admin/MobsPage/`) так же эргономичными, как админку НПС из FEAT-208 + FEAT-209 (обе сделаны, НЕ закоммичены — работаем поверх рабочей копии; см. `features/DONE-FEAT-208-admin-npc-ergonomics.md`, `features/DONE-FEAT-209-admin-npc-region-filter-ready.md`, код в `components/AdminNpcsPage/`).

Общие паттерны НПС-админки (раскрывающаяся плашка, вкладки, состояние в адресе, защита несохранённых правок, создание отдельной плашкой, «Готов») желательно вынести в переиспользуемые компоненты/хуки, а не копировать трижды — решит архитектор (НПС-админку при этом не ломать).

Страницы «Активные мобы» и «Группы мобов» НЕ трогаем.

### Бизнес-правила — общее (как у НПС)
- Список — компактные плашки без кнопок; клик раскрывает под плашкой анимированную подложку, повторный — сворачивает; одновременно раскрыт один элемент, страница доскролливает к нему.
- В подложке — вкладки-тумблеры, под ними выбранный раздел. Опасные действия — в шапке подложки справа (удаление с подтверждением).
- Открытый элемент и вкладка — в адресе (`?item=&tab=` / `?mob=&tab=`), перезагрузка/ссылка/«назад» работают; элемент не с текущей страницы — закреплённой плашкой сверху; кривые параметры — тихий сброс.
- Несохранённые правки — «Уйти без сохранения?» при смене вкладки/сворачивании/раскрытии другого + `beforeunload`.
- «Создать» — такая же плашка сверху с одной вкладкой «Основное»; после сохранения — обычный раскрытый элемент со всеми вкладками.
- Поиск, фильтры, сортировка и страница сохраняются, пока админ работает в подложке.
- **«Готов»**: переключатель в шапке подложки; готовая плашка — лёгкий полупрозрачный золотой фон + ✓, подсказка «Отметил <кто>, <когда>»; общий для всех админов, хранится на сервере; фильтр «Все / Готовые / Не готовые» (в адресе). Игрокам нигде не виден. Права — чтение как у списка раздела, переключение как у редактирования раздела.
- Мобильные 360px+: вкладки листаются горизонтально.

### Айтемы
- Плашка: иконка, название, ID, тип, редкость. Категории сверху и сортировка по колонкам остаются.
- Вкладки: длинную форму предмета (`ItemForm`, ~1000 строк, + ItemEffectSections, ItemConversionsEditor, ItemXpBuffsEditor) разрезать по смыслу, вариант PM: «Основное» (название, тип, редкость, цена, картинка…), «Свойства и эффекты», «Превращения», «Бафы опыта». Точную раскладку подбирает аналитик/архитектор; вкладки, не относящиеся к типу предмета, скрывать. Если разрез формы на вкладки ломает сохранение (одна форма = один submit) — архитектор решает, как сохранять (например, общая форма с вкладками-секциями и одной кнопкой «Сохранить»).
- В шапке: «Выдать» (открывает существующее окно IssueItemModal) и «Удалить».
- Фильтры по типу и редкости (если их ещё нет), в адресе.

### Мобы
- Плашка: аватар, имя, ID, уровень, тип моба (тир/обычный/элита/босс — как есть в данных), число мест спавна.
- Вкладки: «Основное» (AdminMobTemplateForm), «Характеристики» (MobStatsEditor), «Навыки», «Лут», «Спавны» (из AdminMobDetail). Отдельный экран «Подробнее» исчезает.
- В шапке: «Удалить».
- Фильтр «Страна → Регион» по местам спавна моба (моб попадает в регион, если хотя бы одно его место спавна — локация этого региона, иерархия как в FEAT-209), в адресе.

### Edge Cases
- Ошибки API — видимые, на русском.
- Удаление — подложка закрывается, адрес очищается.
- Предмет/моб сменил тип — набор вкладок обновляется после сохранения.

### Вопросы к пользователю (если есть)
- [x] Делать как у НПС, «Готов» в обоих разделах, фильтр по региону у мобов, тип/редкость у айтемов, «Активные мобы»/«Группы мобов» не трогать → «Как предлагаешь, запускай»

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| inventory-service | 3 columns on `items`, new admin list endpoint, new ready toggle, migration 036 | `app/models.py` (`Items`), `app/schemas.py`, `app/main.py` (near `get_item_admin` ~325), new `app/alembic/versions/036_item_admin_ready.py`, `docs/services/inventory-service.md` |
| character-service | 3 columns on `mob_templates`, list filters + fields, ready toggle, migration 049; small refactor of the FEAT-209 geo filter into a shared helper | `app/models.py` (`MobTemplate` ~235), `app/schemas.py` (`MobTemplateResponse` ~958, `MobTemplateDetailResponse` ~1010), `app/crud.py` (`get_mob_templates` ~1685), `app/main.py` (`admin_list_mob_templates` ~3459, `admin_list_npcs` ~3003), `app/reputation_crud.py`, new `app/alembic/versions/049_mob_admin_ready.py`, `docs/services/character-service.md` |
| frontend | shared expandable-list kit, NPC page migrated onto it, items page and mobs page rebuilt | `src/components/Admin/ExpandableList/*` (new), `src/components/AdminNpcsPage/*`, `src/components/ItemsAdminPage/*`, `src/components/Admin/MobsPage/*` (not `AdminActiveMobs.tsx`), `src/api/items.ts`, `src/api/mobs.ts`, `src/api/npcAdmin.ts`, new `src/api/adminGeo.ts` |

No Nginx / Docker / RabbitMQ / new permissions / new packages. The routes stay as they are: `admin/items` (`items:read`), `admin/mobs` (`mobs:manage`), see `App.tsx:224,296`. `admin/active-mobs` and `admin/mob-packs` are out of scope.

### Items — frontend today (`components/ItemsAdminPage/`)
- `ItemsAdminPage.tsx` (94 lines). `?category=` is already in the URL (replace, validated against `ITEM_CATEGORIES`). Opening the edit/create form **replaces the list**: `editingId`/`creating` state, `ItemForm` rendered instead of `ItemList`, list remounted on close via `refreshKey`. `IssueItemModal` is opened from the list with the row `ItemData`; it uses only `id` and `name` of `initialItem` (`IssueItemModal.tsx:66-67`).
- `ItemList.tsx` (351 lines) loads the **whole catalogue** once via `fetchAllItems()` → walks the **public** `GET /inventory/items` in pages of 500 (fat `schemas.Item` with effects/damage/xp_buffs, `selectinload`). Category chips with counts, search (name or exact id), filters **type** (only types of the category), **rarity**, resource **subcategory**, sort by id/name/type/rarity (table headers on md+, select on mobile). All filters/sort are local state, **not in URL**; type/subcategory reset on category change. No pagination (renders every row). Row actions: «Изменить», «Выдать», «Удалить» (`window.confirm` → `DELETE /inventory/items/{id}`, `items:delete`).
- `ItemForm.tsx` (1032 lines): **one state object** `item: ItemFormState` + side state (`imgFile`, `crop`, `recropping`, `conversionsDraft`, `refiningRules`, `createdId`, `rarityNote`). `fetchItem(id)` → admin `GET /inventory/admin/items/{id}` (`items:read`, fat). **One `<form onSubmit>`**: client validation (rarity cap, furniture room, seed, house flags, battle config, xp buffs, conversions draft) → `PUT /inventory/items/{id}` (`items:update`, full `ItemCreate` payload from `buildItemPayload`) or `POST /inventory/items` → optional image upload/recrop (photo-service) → **then** `PUT /inventory/admin/items/{id}/conversions` (needs the id of a new item). On success it calls `onSuccess()` → page closes the form. No dirty tracking. HTML `required` is used on: name, repair_power, whetstone_level/group, tool_category, furniture_room_type.
- Sections and their visibility (from `itemFormRules.rulesFor(type, is_food)` + direct type checks):
  - always: base grid (name, type, rarity if `itemHasRarity`, level, price, stack, unique, description), image/crop fieldset; recipe note if `recipe`.
  - «Экипировка» (armor subclass / weapon kind + damage type / durability / sockets / fast slot bonus) — equipment & jewelry, not tools.
  - «Еда» checkbox (`consumable`), «Походный рюкзак» (`cloak`), «Личность» (`head`), «Восстановление» (`consumable`/`scroll`), «Свиток возвращения» + «Опознание» (`scroll`), «Ресурс» + `SeedSection` (`resource`), «Инструмент сбора» (`gathering_tool`), «Мебель» (`furniture`).
  - «Боевые эффекты» (`ItemEffectSections`) and «Ускорение опыта» (`ItemXpBuffsEditor`) — consumable (not food) / scroll.
  - «Переработка» (`ItemConversionsEditor`, own fetch of `GET /inventory/admin/items/{id}/conversions`, reports a draft `{ready, dirty, conversions, invalid}` via `onChange`) — resource whose subcategory is refinable/raw.
  - Modifiers (Характеристики / Сопротивления / Уязвимости) — equipment, jewelry, gem, rune, food.
  - gem/rune/misc/recipe have no type-specific section except modifiers (gem/rune).
- Changing the type in the form already resets the fields of the old type (`handleTypeChange`).

### Items — backend (inventory-service owns `items`)
- `GET /inventory/items` — **public, no auth**, `response_model=List[schemas.Item]`, params `q, item_types, exclude_types, resource_subcategory, page, page_size ≤ 500`; no rarity filter, no total. Used by many player screens → must not carry admin fields.
- `GET /inventory/admin/items/{item_id}` (`items:read`) — fat `schemas.Item`; `PUT /inventory/items/{id}` takes `schemas.ItemCreate` (copies declared fields only). `schemas.Item` is a whitelist (orm_mode) → a new ORM column is invisible unless declared.
- **Route-order trap**: `GET /inventory/{character_id}/items` is registered at `main.py:522`; a new `GET /inventory/admin/items` must be declared **before** it (e.g. next to `get_item_admin` ~325), otherwise `admin` is matched as `character_id` → 422.
- Auth: `auth_http.require_permission(...)` returns `UserRead` with `username` (inventory-service `auth_http.py:9-11`). `items:read|create|update|delete` exist → no permission migration.
- Latest migration: `035_item_stealth_modifier` (down `034_item_mask`); style: `sa.inspect` `_has_column` guard + `op.add_column`. Next = **036**. Memory gotcha: no ENUM changes on `items` (table lock) — adding plain columns is fine (MySQL 8 instant add). Other writers of `items`: only inventory-service ORM + two old migrations with explicit-column `INSERT` → `NOT NULL DEFAULT 0` is safe. photo-service mirror model maps only its own columns.
- Tests: SQLite + `Base.metadata.create_all`; admin-route test precedent `tests/test_feat171_admin_item_route.py`, conversions admin `tests/test_item_conversions_admin.py`.

### Mobs — frontend today (`components/Admin/MobsPage/`)
- `AdminMobTemplates.tsx` (323): list via **redux** `mobsSlice` (`search`, `tierFilter`, `page`, `pageSize=20` in the store; thunk `fetchMobTemplates` → `GET /characters/admin/mob-templates?q&tier&page&page_size`). Table + mobile cards; actions «Подробнее» (replaces the page with `AdminMobDetail` via early return), «Редактировать» (inline `AdminMobTemplateForm` above the table), «Удалить» (`window.confirm` + thunk). Button «Заполнить опыт по формуле» (`POST .../fill-xp`) — keep.
- `AdminMobTemplateForm.tsx` (501): props `editingId, onClose`; loads `GET /characters/admin/mob-templates/{id}`; fields name/description/tier/level/class/sex/base_attributes (points per level + derived preview)/xp/gold/respawn + avatar file; submit → redux thunks `createMobTemplate`/`updateMobTemplate` (they toast) → `POST /photo/change_mob_avatar` → `onClose()`. No dirty tracking.
- `AdminMobDetail.tsx` (156): redux `fetchMobTemplate`/`selectedTemplate` (cleared on unmount); header + own tabs `skills | loot | spawns | stats`; children get data from the detail: `AdminMobSkills {templateId, skills, onUpdate}` (has `hasChanges`), `AdminMobLoot {templateId, lootTable, onUpdate}`, `AdminMobSpawns {templateId, spawns, onUpdate}` (local `entries` from props, explicit «Сохранить» → thunks `updateMobSkills/Loot/Spawns` → `onUpdate` = refetch detail), `MobStatsEditor {templateId, templateName, idClass, baseAttributes}` (edits attributes of **active mob instances** of the template: `GET/PUT /attributes/...`, no dirty tracking). Each child has its own h3 headers, no back buttons.
- `api/mobs.ts`: `MobTemplateListItem` (id, name, tier, level, avatar, xp/gold, respawn), `fetchMobTemplates(params)` (also used by `AdminMobSkills` for «copy skills from»), `fetchMobTemplate`, `deleteMobTemplate`, etc. `AdminActiveMobs` uses the same api module and slice (must stay untouched).

### Mobs — backend (character-service owns `mob_templates`, `location_mob_spawns`)
- `GET /characters/admin/mob-templates` (`main.py:3459`, sync, `mobs:manage`): `q, tier, page, page_size ≤ 100` → `crud.get_mob_templates` (ORM, `count()`, order by id) → `MobTemplateListResponse{items: List[MobTemplateResponse], total, page, page_size}`; `MobTemplateResponse` = id, name, tier, level, avatar, xp/gold, respawn (orm_mode, used only here). Detail `GET .../{id}` → `MobTemplateDetailResponse` (+ skills, loot_entries, spawn_locations — no location names). `PUT`/`DELETE .../{id}`, `POST .../fill-xp` (no clash with a new `PUT .../{id}/ready`).
- RBAC: mobs have a single permission `mobs:manage` (route + every endpoint) → read and toggle both `mobs:manage`.
- `MobTemplate.tier` ENUM `normal|elite|boss` (this is «тип моба»). `LocationMobSpawn(mob_template_id FK CASCADE, location_id BIGINT indexed, spawn_chance, max_active, is_enabled, UNIQUE(template, location))`.
- Same service as FEAT-209: `reputation_crud.region_location_ids(db, region_ids)` (recursive CTE, MySQL + SQLite) and `country_region_ids(db, country_id)` are directly reusable; the region/country resolution block lives inline in `admin_list_npcs` (`main.py:3021-3034`).
- Public exposure: mob templates reach players only through whitelisting schemas (`MobInLocation` for `/mobs/by_location`) / explicit SQL; battle-service, dungeon-service, photo-service read `mob_templates` with explicit columns / mirror model → new columns don't leak and don't break them.
- Latest migration: `048_npc_admin_ready` (FEAT-209, uncommitted) → next **049**; style: `information_schema`-guarded raw `ALTER TABLE` list.
- Tests: `tests/test_mob_templates.py`, `test_admin_npc_region_ready.py` (geo fixtures over SQLite `Countries/Regions/Districts/Locations` from conftest).

### FEAT-208/209 pieces and how generic they are
| Piece | Generic? | Notes |
|---|---|---|
| `NpcRow.tsx` | shell yes, columns no | plate container + ready gold bg/✓ + badge + chevrons + `AnimatePresence` are generic; avatar/role/location/status cells are NPC-specific |
| `NpcExpandedPanel.tsx` | shell yes | motion height/opacity + scroll-on-open + header (title, right actions) + tabs + keyed body are generic; the `renderSection` switch and Resurrect are NPC-specific |
| `NpcTabs.tsx` | yes | only `NPC_TAB_LABELS` and `layoutId="npc-panel-tab"` are NPC-specific |
| `useNpcPanelUrlState.ts` | yes | parameterise param name + tab-key guard |
| `useDirtyReport.ts` (`useDirtyReport`, `useOpenSnapshotDirty`) | fully | used by 7 NPC editors |
| dirty guard + `beforeunload` + confirm (inline in `AdminNpcsPage`, ~40 lines) | fully | |
| `useNpcListFilterUrlState.ts` + country/region option loading/validation (inline in `AdminNpcsPage`, ~65 lines + JSX) | fully | country/region are generic; `ready` is generic |
| «Готов» chip (in `NpcExpandedPanel`), `readyTooltip`, `fetchCountryOptions`/`fetchCountryRegionOptions` (`api/npcAdmin.ts`) | fully | NPC fields are named `npc_ready*` → needs a tiny adapter to a common `{ready, at, by}` shape |

### Risks
- Splitting `ItemForm` into separately-mounted tabs would lose state and break the single submit + post-save conversions → must stay one form with hidden sections; hidden `required` inputs block native validation silently ("invalid form control is not focusable").
- Item create needs type-specific required fields (furniture room, tool category, repair power…) → a create panel limited to «Основное» could not save those types.
- Items list is fully client-side; replacing the public fat fetch with a slim admin list changes payload shape used by `ItemList`/`IssueItemModal` (only `id`/`name` needed by the modal).
- Route order in inventory-service (`/{character_id}/items`).
- NPC page regression while extracting the shared kit (NPC page is uncommitted FEAT-208/209 work).
- `AdminActiveMobs` shares `api/mobs.ts` and `mobsSlice` → changes there must be additive.

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Approach
One shared **expandable-list kit** in `src/components/Admin/ExpandableList/` extracted from FEAT-208/209; NPC page migrated onto it (behaviour unchanged); items and mobs pages built on it. Section editors stay per-domain. Backend: the «Готов» mark = the FEAT-209 pattern (flag + when + who) as 3 columns on the owning table, a toggle endpoint per section, admin-only list fields. Mobs get the country/region filter through their spawn locations, reusing the FEAT-209 CTE in the same service.

### 3.2 Storage («Готов»)
Same columns in both tables (prefix `admin_` — marks admin-only data):
| Column | Type | Meaning |
|---|---|---|
| `admin_ready` | `TINYINT(1) NOT NULL DEFAULT 0` (`Boolean`, `server_default="0"`) | flag |
| `admin_ready_at` | `DATETIME NULL` | UTC naive, set when the flag becomes true |
| `admin_ready_by` | `VARCHAR(255) NULL` | username snapshot (`current_user.username`) |

- **inventory-service** `items` — migration `036_item_admin_ready` (down `035_item_stealth_modifier`), service style (`_has_column` via `sa.inspect` + `op.add_column` / `op.drop_column`). Plain columns, **no ENUM touched**.
- **character-service** `mob_templates` — migration `049_mob_admin_ready` (down `048_npc_admin_ready`), 048 style (`information_schema` guard, raw `ALTER TABLE … ADD/DROP COLUMN`).
- Ids ≤ 32 chars. Rollback = downgrade to the previous revision (marks lost — accepted pre-beta). No indexes (filters run over small sets / client-side).
- Not added to `ItemCreate`/`MobTemplateCreate`/`MobTemplateUpdate` → regular edit/save never touches the mark; the mark survives edits and dies with the row.

### 3.3 inventory-service API
**A. `GET /inventory/admin/items`** — new, `Depends(require_permission("items:read"))`, sync. **Must be declared before `GET /{character_id}/items`** (put it next to `get_item_admin`). No params; returns **all** items ordered by id as `List[ItemAdminListRow]` built from a column-only query (no relationships loaded):
```
ItemAdminListRow: id:int, name:str, image:Optional[str], item_type:str, item_rarity:Optional[str], item_level:int,
  armor_subclass, weapon_subclass, resource_subcategory: Optional[str],
  admin_ready: bool = False, admin_ready_at: Optional[datetime] = None, admin_ready_by: Optional[str] = None
```
(orm_mode / from row). The admin page switches from the public fat paged fetch to this slim list (strictly lighter than today's fetch). DB error → 500 «Внутренняя ошибка сервера».

**B. `PUT /inventory/admin/items/{item_id}/ready`** — `items:update`, sync. Body `ItemReadyUpdate {ready: bool}` (required, `Extra.forbid`). 404 «Предмет не найден». Idempotent like FEAT-209: `true` on an already-ready item keeps original `at/by`; `true` on not-ready sets `1, utcnow(), username`; `false` → `0, NULL, NULL`. Response 200 `ItemReadyResponse {id, admin_ready, admin_ready_at, admin_ready_by}`. DB error → rollback, log, 500.

**No change** to `GET /inventory/items`, `GET /inventory/items/{id}`, `GET /inventory/admin/items/{id}`, `schemas.Item`, `ItemCreate` → the mark never appears in public responses (and the item editor's PUT payload cannot carry it).

### 3.4 character-service API
**Shared geo helper** in `reputation_crud.py`: `admin_geo_location_ids(db, country_id, region_id) -> Optional[List[int]]` — `None` when neither is given (no geo filter); otherwise exactly the FEAT-209 §3.2 semantics (region checked against the country when both given, else all regions of the country; then `region_location_ids`), returning `[]` for an empty scope. `admin_list_npcs` is refactored to call it (pure extraction, behaviour identical — existing `test_admin_npc_region_ready.py` must stay green).

**A. `GET /characters/admin/mob-templates`** — new optional params (backward compatible): `country_id: int ≥ 1`, `region_id: int ≥ 1`, `ready: bool`.
- Geo: `ids = admin_geo_location_ids(...)`; `[]` → `{items: [], total: 0, page, page_size}`; else `MobTemplate.id IN (SELECT mob_template_id FROM location_mob_spawns WHERE location_id IN ids)` (ORM subquery; disabled spawn rows count — a configured place is a place). Templates without spawns never match a geo filter.
- `ready` → `MobTemplate.admin_ready == ready`. Combines with `q`, `tier`, `count()` and pagination (filtering stays in `crud.get_mob_templates`, new kwargs).
- `MobTemplateResponse` gains `spawn_count: int = 0` (number of `location_mob_spawns` rows of the template, enabled or not; filled by **one** grouped query `SELECT mob_template_id, COUNT(*) … WHERE mob_template_id IN (page ids) GROUP BY mob_template_id` after pagination) and `admin_ready: bool = False`, `admin_ready_at`, `admin_ready_by`.
- `MobTemplateDetailResponse` gains the three `admin_ready*` fields (pinned plate / panel header).

**B. `PUT /characters/admin/mob-templates/{template_id}/ready`** — `mobs:manage`, sync. Body reuses `NpcReadyUpdate {ready: bool}` (Extra.forbid). 404 «Шаблон моба не найден». Same idempotency rules. Response `MobReadyResponse {id, admin_ready, admin_ready_at, admin_ready_by}`. DB error → rollback, log, 500 «Внутренняя ошибка сервера».

No other schema touched → `/mobs/by_location` (`MobInLocation`) and every other public response stay without the mark. Rate limiting: not needed (admin-only, Nginx global limits). Invalid query types → FastAPI 422.

### 3.5 Shared frontend kit — `src/components/Admin/ExpandableList/`
All TS, no `React.FC`, Tailwind + design-system classes only. Extracted from the FEAT-208/209 code (same markup/classes/animation), generalised by props:
| File | Contract (dev may refine names, not behaviour) |
|---|---|
| `readyMark.ts` | `interface ReadyMark { ready: boolean; at: string \| null; by: string \| null }`; `readyTooltip(by, at)` (moved from `api/npcAdmin.ts`) |
| `ExpandableRow.tsx` | plate shell: `{open, onToggle, avatar: ReactNode, title: string, subtitle?: ReactNode, ready?: ReadyMark \| null, cells?: ReactNode, gridClassName: string, badge?: string, rowRef?, placeholderTitle? , children? (panel)}` — `<button aria-expanded>`, gold translucent bg + ✓ with tooltip when ready, chevrons (mobile/desktop), `AnimatePresence` for the panel, `scroll-mt-4` |
| `ExpandedPanelShell.tsx` | `{title, actions?: ReactNode, tabs?: ReactNode, bodyKey: string, scrollTargetRef, children}` — motion height/opacity 0.25 easeOut, scroll on `open` animation complete, header (gold title left, actions right, wraps on mobile), tabs, keyed body `min-w-0` |
| `PanelTabs.tsx` | generic `<K extends string>{tabs: K[], labels: Record<K,string>, active: K, onSelect, layoutId: string}` — horizontal scroll `overflow-x-auto gold-scrollbar`, `nav-link`, motion underline |
| `ReadyToggle.tsx` | `{mark: ReadyMark, pending: boolean, onToggle, entityHint: string}` — `chip-outline` (+`chip-outline-active`), «✓ Готов» / «Готов», `aria-pressed`, tooltip |
| `ReadyFilterSelect.tsx` | `{value: boolean \| null, onChange}` — «Готовность: все / Готовые / Не готовые» |
| `useReadyFilterUrlState.ts` | `?ready=1\|0`, replace, garbage removed → `{ready, setReady}` |
| `useGeoFilter.ts` + `GeoFilterSelects.tsx` | `?country=&region=` URL state + options loading (`api/adminGeo.ts`) + validation/silent reset exactly as FEAT-209 → `{countryId, regionId, settled, selectProps}`; component renders the two selects (region disabled without country); caller passes `onChanged` (→ page 1) |
| `usePanelUrlState.ts` | generic `usePanelUrlState<K>(param, isTabKey, defaultTab)` → `{target: number \| 'new' \| null, rawTarget, tab, open(target, tab?), setTab, close, normalize}` (push for open/tab/close, replace for normalize; functional `setSearchParams`) |
| `useDirtyGuard.ts` | `{panelDirty, onDirtyChange (stable), guard(action), pendingLeave, confirmLeave, cancelLeave}` + `beforeunload` while dirty + reset when panel closes (takes `panelOpen`) ; page renders the existing `ConfirmationModal` with FEAT-208 texts |
| `useDirtyReport.ts` | `useDirtyReport`, `useOpenSnapshotDirty` moved verbatim from `AdminNpcsPage/` |
| `src/api/adminGeo.ts` | `GeoOption`, `fetchCountryOptions`, `fetchCountryRegionOptions` moved from `api/npcAdmin.ts` (which keeps `setNpcReady`) |

**NPC migration (minimal-risk):** `AdminNpcsPage` uses the kit hooks (`usePanelUrlState('npc', …)`, `useGeoFilter`, `useReadyFilterUrlState`, `useDirtyGuard`) and components (`GeoFilterSelects`, `ReadyFilterSelect`); `NpcRow` becomes a thin wrapper over `ExpandableRow` (NPC cells, `npc_ready*` → `ReadyMark`); `NpcExpandedPanel` uses `ExpandedPanelShell` + `PanelTabs` (`layoutId="npc-panel-tab"`) + `ReadyToggle` and keeps its `renderSection` switch + Resurrect. Delete `NpcTabs.tsx`, `useNpcPanelUrlState.ts`, `useNpcListFilterUrlState.ts`, `AdminNpcsPage/useDirtyReport.ts`; NPC editors only change the `useDirtyReport` import path. URL contract (`?npc&tab&country&region&ready`), texts and visuals unchanged.

### 3.6 Items page
**URL:** `?category=` (existing) `&type=&rarity=&ready=1|0&item=<id|new>&tab=<key>`. `type` must belong to the current category (else silently removed, replace); `rarity` ∈ `RARITY_LABELS` keys; category change clears `type` (as today). Search, subcategory, sort, page — local state (kept while working in the panel because the page never unmounts).

**List:** load `GET /inventory/admin/items` once (and after save/delete/ready refetch or patch). Filtering/sorting stays client-side as today, plus `ready`. Client-side pagination `ITEMS_PAGE_SIZE = 50` with `AdminPagination`, reset to page 1 on any filter/search/category/sort change. Sorting: a header strip on md+ aligned with the plate grid (clickable ID / Название / Тип / Редкость with ↑↓ like today), existing sort select on mobile. Category chips with counts stay.

**Plate (`ItemRow`, over `ExpandableRow`):** icon (rounded square, like today's thumb), name + ✓, `#id`, type (+ subclass / resource subcategory line), rarity coloured (`—` for rarity-less). Open item not in the current visible page/filter → pinned plate «Открыт по ссылке» from the loaded catalogue (no extra request); id not in the catalogue → toast «Предмет не найден» + params cleared.

**Panel header actions:** `ReadyToggle` (edit mode), «Выдать» (opens existing `IssueItemModal`; widen its `initialItem` prop type to `{ id: number; name: string }`-compatible — it reads only those), «Удалить» (`ConfirmationModal` → `DELETE /inventory/items/{id}` → toast, remove row, params cleared, dirty reset).

**Form = one form, tabs are sections (save model).** `ItemForm` keeps the single state and the single `<form onSubmit>`; it renders `PanelTabs` itself (tab set depends on the **live** form type) and wraps every section group in `<div data-item-tab="<key>" hidden={activeTab !== key}>` — inactive sections stay **mounted** (state, `ItemConversionsEditor` draft and its own fetch survive tab switches). One footer under the tabs, always visible: «Сохранить»/«Создать» + «Отмена» (= collapse via guard). Tab switching inside the item panel is **not** dirty-guarded (nothing is lost).
| Tab key | Label | Content | Visible when (live state) |
|---|---|---|---|
| `general` | Основное | base grid, recipe note, «Изображение» | always |
| `props` | Свойства | Экипировка, Еда, Походный рюкзак, Личность, Восстановление, Свиток возвращения, Опознание, Ресурс + SeedSection, Инструмент сбора, Мебель | any of these renders (all types except gem, rune, recipe, misc) |
| `modifiers` | Модификаторы | gem/rune/food hint + Характеристики / Сопротивления / Уязвимости | `rules.modifiers` |
| `effects` | Боевые эффекты | `ItemEffectSections` | `rules.battleEffects` |
| `xp` | Бафы опыта | `ItemXpBuffsEditor` | `rules.buff` |
| `conversions` | Переработка | `ItemConversionsEditor` (= PM's «Превращения»; label matches its existing legend) | `conversionsSubcategory !== null` |
Put keys/labels and `itemTabsFor(itemType, isFood, hasConversions)` in `ItemsAdminPage/itemTabKeys.ts`. Tabs follow the **live** type (not saved) because a type change must let the admin fill the new type's required fields before saving; therefore **create mode also shows all tabs of the chosen type** (deliberate deviation from «create = one tab»: furniture/tools/repair kits cannot be created otherwise). Active tab = URL `tab` if in the current set else `general` (normalize with replace once the form has loaded).
- **Hidden required fields:** `onInvalidCapture` on the form: on the first `invalid` event of a submit, find `closest('[data-item-tab]')` of the target; if it is not the active tab → switch to it and toast «Заполните обязательные поля на вкладке «<label>»». Client validation toasts (rarity cap, furniture, seed, battle, xp, conversions) additionally switch to the tab of the offending section where obvious (dev's judgement; at minimum the message is visible).
- **After save** the form stays open: page bumps a `formSeq` used in the form `key` → remount → reload from `GET /inventory/admin/items/{id}` (fresh snapshot, conversions reloaded); created item → `normalize(newId, currentTab-or-general)`; list refetched (type/rarity/name/icon may change → plate and tab set update). Conversions-failed-after-create path keeps today's behaviour (form stays, `createdId`).
- **Dirty:** `JSON(item) !== snapshot` (snapshot after load; initial state for create) `|| imgFile || (recropping && crop) || conversionsDraft?.dirty` → `useDirtyReport` → page guard (collapse / open other / create / delete).
- `ItemsAdminPage.tsx` becomes the list page (or hosts `ItemList` which renders plates) — dev's choice of file split, but files stay in `ItemsAdminPage/`. New: `ItemRow.tsx`, `ItemExpandedPanel.tsx`, `itemTabKeys.ts`, `useItemListFilterUrlState.ts`. `api/items.ts`: `fetchAdminItemList()`, `setItemReady(id, ready)`, `ItemAdminListRow`/`ItemReadyResponse` types. `SeedSection`, `ItemEffectSections`, `ItemXpBuffsEditor`, `ItemConversionsEditor` unchanged.

### 3.7 Mobs page
**URL:** `?mob=<id|new>&tab=<key>&country=&region=&ready=1|0`. Search, tier, page — local state (page fetches with them; pagination server-side 20 as today).
- `AdminMobTemplates.tsx` rewritten on the kit, list via `api/mobs.fetchMobTemplates` with local state (no longer the redux list; `mobsSlice` untouched — `AdminActiveMobs` and the editors' thunks keep using it). Filters row: search, tier (Все типы/Обычный/Элитный/Босс), `GeoFilterSelects`, `ReadyFilterSelect`, «Заполнить опыт по формуле», «Создать моба». List requested only after geo validation settles (FEAT-209 rule).
- **Plate (`MobRow`):** avatar, name + ✓, `#id · N ур.`, tier chip (existing colours/labels), «Спавнов: N» (`spawn_count`). Pinned plate for off-page/deep-linked mob from `GET …/mob-templates/{id}` (`spawn_count = spawn_locations.length`); 404 → toast «Моб не найден» + params cleared.
- **Panel (`MobExpandedPanel`):** header actions `ReadyToggle` + «Удалить» (`ConfirmationModal` «Удалить шаблон моба? Это действие нельзя отменить.» → `api.deleteMobTemplate` → toast, row removed, params cleared). Tabs (`mobTabKeys.ts`): `general` Основное (`AdminMobTemplateForm`), `stats` Характеристики (`MobStatsEditor`), `skills` Навыки, `loot` Лут, `spawns` Спавны — all always; create → `general` only. The panel loads the detail itself (`api.fetchMobTemplate`, local state, not redux) for skills/loot/spawns/stats props; sub-editor `onUpdate` → reload detail + refetch list (spawn_count). Sections keyed by `${id}-${tab}` (remount per tab, like NPC) → **tab switch is dirty-guarded** here.
- **Editors (minimal diff):** `AdminMobTemplateForm` props → `{editingId, onSaved(id, created), onCancel, onDirtyChange?}`; title h2 removed (panel header names the mob); stays open after update (re-snapshot); create → `normalize(newId,'general')`. Dirty = form ≠ loaded snapshot || avatarFile. `MobStatsEditor`: `onDirtyChange?` (attributes ≠ snapshot taken on load/save). `AdminMobSkills`: forward existing `hasChanges`. `AdminMobLoot`/`AdminMobSpawns`: `onDirtyChange?` (entries ≠ entries derived from props). Delete `AdminMobDetail.tsx` (no other importers).
- `api/mobs.ts` (additive only): list params `country_id/region_id/ready`, `MobTemplateListItem` + `spawn_count, admin_ready, admin_ready_at, admin_ready_by`, detail + `admin_ready*`, `setMobReady(id, ready)`.

### 3.8 Ready toggle UX (both sections, as FEAT-209)
No optimistic update; button disabled while pending; on success patch the row/pinned from the response, toast «Отмечено: готов» / «Отметка «Готов» снята», refetch the list if the `ready` filter is active (the open element then becomes pinned); on error toast «Не удалось изменить отметку «Готов»» (+ `detail`), state unchanged.

### 3.9 Security
- New endpoints: auth via `require_permission` (JWT + RBAC through user-service `/users/me`): items list `items:read`, item toggle `items:update`, mob list/toggle `mobs:manage`. Bodies `Extra.forbid`, `ready: bool` required; query ints `ge=1`; SQL via ORM / expanding bindparams (no string interpolation). Errors Russian, no internals. No rate limiting needed beyond Nginx defaults.
- No leak: marks only in `ItemAdminListRow`, `ItemReadyResponse`, `MobTemplateResponse` (admin list), `MobTemplateDetailResponse` (admin detail), `MobReadyResponse`.
- Frontend: URL params parsed strictly (positive int / `new` / whitelisted keys), garbage silently reset; every API error → Russian toast.

### 3.10 Data flow
```
Items:  URL ?category&type&rarity&ready&item&tab ─> ItemsAdminPage ─GET /inventory/admin/items (items:read, slim, all)
        panel: ItemForm ─GET /inventory/admin/items/{id} ; PUT|POST /inventory/items ; photo upload ; PUT /inventory/admin/items/{id}/conversions
        «Готов» ─PUT /inventory/admin/items/{id}/ready (items:update) → items.admin_ready* ; «Выдать» ─IssueItemModal ─POST /inventory/{cid}/items
Mobs:   URL ?country&region&ready&mob&tab ─> AdminMobTemplates ─GET /characters/admin/mob-templates?q&tier&country_id&region_id&ready&page
          character-service: Regions → region_location_ids CTE → mob_templates.id IN (location_mob_spawns by location) ; spawn_count grouped
        options ─GET /locations/countries/lookup, /locations/countries/{id}/details
        «Готов» ─PUT /characters/admin/mob-templates/{id}/ready (mobs:manage) → mob_templates.admin_ready*
```

### 3.11 Cross-service
No contract change for other services: new endpoints are admin-only and additive; `GET /inventory/items` and every public/internal item and mob response unchanged; new columns have server defaults (raw inserters and mirror models unaffected).

## 4. Tasks (filled by Architect, updated by PM — in English)

Parallelism: #1, #2, #3 start together. #4 and #5 start after #3 (they build on the kit) and run **in parallel** — #4 touches only `ItemsAdminPage/*` + `api/items.ts`, #5 only `Admin/MobsPage/*` (not `AdminActiveMobs.tsx`) + `api/mobs.ts`; neither edits `Admin/ExpandableList/*` (if the kit needs a change, it is additive and coordinated through PM). Live checks of #4/#5 need #1/#2. Sub-agents never commit or push.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | inventory-service per §3.2/§3.3: migration `036_item_admin_ready`, `Items` columns, `GET /inventory/admin/items` (declared before `/{character_id}/items`, column-only query, `ItemAdminListRow`), `PUT /inventory/admin/items/{item_id}/ready` (`ItemReadyUpdate`/`ItemReadyResponse`, idempotent who/when). Update `docs/services/inventory-service.md`. | Backend Developer | DONE | `services/inventory-service/app/models.py`, `schemas.py`, `main.py`, new `alembic/versions/036_item_admin_ready.py`, `docs/services/inventory-service.md` | — | `py_compile` passes; existing inventory tests green; migration upgrade/downgrade/upgrade OK in the container; `GET /inventory/admin/items` returns slim rows (not 422); `GET /inventory/items` / `/items/{id}` / `/admin/items/{id}` unchanged (no `admin_ready*`) |
| 2 | character-service per §3.2/§3.4: migration `049_mob_admin_ready`, `MobTemplate` columns, `reputation_crud.admin_geo_location_ids` + `admin_list_npcs` refactored onto it, `country_id/region_id/ready` on `GET /admin/mob-templates` (spawn subquery) + `spawn_count` (one grouped query) + `admin_ready*` in `MobTemplateResponse` and `MobTemplateDetailResponse`, `PUT /admin/mob-templates/{template_id}/ready` (`MobReadyResponse`). Update `docs/services/character-service.md`. | Backend Developer | DONE | `services/character-service/app/models.py`, `schemas.py`, `crud.py`, `main.py`, `reputation_crud.py`, new `alembic/versions/049_mob_admin_ready.py`, `docs/services/character-service.md` | — | `py_compile` passes; `test_admin_npc_region_ready.py`, `test_admin_npc_list.py`, `test_mob_templates.py` green; migration OK in the container (`alembic current` = 049); filters correct on live MySQL; `/mobs/by_location` has no `admin_ready*` |
| 3 | Frontend shared kit per §3.5 in `src/components/Admin/ExpandableList/` + `src/api/adminGeo.ts`; migrate the NPC page onto it (delete `NpcTabs.tsx`, `useNpcPanelUrlState.ts`, `useNpcListFilterUrlState.ts`, `AdminNpcsPage/useDirtyReport.ts`; NPC editors only change the import path; `api/npcAdmin.ts` keeps `setNpcReady`). NPC behaviour, URL contract, texts and look unchanged. | Frontend Developer | DONE | new `src/components/Admin/ExpandableList/*`, new `src/api/adminGeo.ts`, `src/api/npcAdmin.ts`, `src/components/AdminNpcsPage/*` | — | `/admin/npcs` re-checked live: expand/collapse + scroll, tabs by role, `?npc&tab&country&region&ready` reload/back/garbage reset, pinned plate, create, dirty prompt, «Готов» toggle + gold plate, 360px; no `React.FC`; Tailwind/design system; `npx tsc --noEmit` + `npm run build` pass (in Docker) |
| 4 | Items page per §3.6 (+§3.8): slim admin list, plates `ItemRow`, sort header strip, client pagination 50, URL `type/rarity/ready/item/tab`, pinned plate, create plate, `ItemExpandedPanel` header (Готов / Выдать / Удалить), `ItemForm` as one form with tab sections (`itemTabKeys.ts`, live-type tab set, hidden sections stay mounted, invalid-field tab switch, one footer, stays open after save via remount, dirty report), `IssueItemModal` prop type widened. | Frontend Developer | DONE | `src/components/ItemsAdminPage/*` (new `ItemRow.tsx`, `ItemExpandedPanel.tsx`, `itemTabKeys.ts`, `useItemListFilterUrlState.ts`), `src/api/items.ts` | #3 (kit), #1 (live) | Every item type shows exactly its tabs; type change in «Основное» updates tabs live; save from any tab works (incl. conversions after create, image upload); hidden required field → switches to its tab with a Russian toast; furniture/tool can be created; filters/sort/category/page preserved while working; `?category&type&rarity&ready&item&tab` survive reload, garbage reset; delete closes + clears params; Выдать opens the modal preselected; Готов toggles plate; 360px; tsc + build pass |
| 5 | Mobs page per §3.7 (+§3.8): `AdminMobTemplates` on the kit with local list state, `MobRow`, `MobExpandedPanel` (tabs Основное/Характеристики/Навыки/Лут/Спавны, header Готов/Удалить), country→region + ready filters in URL, pinned plate, create plate; editors get `onDirtyChange` (+ form `onSaved/onCancel`, stays open); delete `AdminMobDetail.tsx`; `api/mobs.ts` additive changes. | Frontend Developer | DONE | `src/components/Admin/MobsPage/AdminMobTemplates.tsx`, `AdminMobTemplateForm.tsx`, `MobStatsEditor.tsx`, `AdminMobSkills.tsx`, `AdminMobLoot.tsx`, `AdminMobSpawns.tsx`, delete `AdminMobDetail.tsx`, new `MobRow.tsx`, `MobExpandedPanel.tsx`, `mobTabKeys.ts`; `src/api/mobs.ts` | #3 (kit), #2 (live) | Plate shows avatar/name/id/level/tier/spawn count; region filter matches mobs spawning in the region (nested districts/child locations); spawns save updates the count; dirty prompt on every editable tab; `?mob&tab&country&region&ready` survive reload; «Активные мобы»/«Группы мобов» still work; 360px; tsc + build pass |
| 6 | Pytest for #1: admin list (auth 401/403 without `items:read`, slim fields, ordering, includes `admin_ready*`, `/inventory/admin/items` not swallowed by `/{character_id}/items`); toggle (set/unset, idempotent keeps at/by, by = username, 404, 403 with only `items:read`, 422 missing/extra body); `PUT /inventory/items/{id}` keeps the mark; public `GET /inventory/items` and `/items/{id}` and admin detail have no `admin_ready*`; migration 036 imports with correct `down_revision`. | QA Test | DONE | new `services/inventory-service/app/tests/test_item_admin_ready.py` | #1 | New tests + full inventory suite pass |
| 7 | Pytest for #2: mob geo filter (spawn in district region, nested sub-district, location with own region, child location inheriting, child with own other region excluded, country = union, foreign region with country → empty, unknown → empty, no spawns excluded, disabled spawn counts, mob with spawns in two regions appears in both, combo with `q/tier/ready` + pagination `total`); `spawn_count` values; toggle (set/unset/idempotent/username/404/403 without `mobs:manage`/422); detail has `admin_ready*`; `/mobs/by_location` has none; NPC geo regression after the helper refactor; migration 049. | QA Test | DONE | new `services/character-service/app/tests/test_admin_mob_region_ready.py` (reuse fixtures style of `test_admin_npc_region_ready.py`) | #2 | New tests + full character-service suite pass |
| 8 | Review: code vs §3, CLAUDE.md rules; py_compile + pytest (inventory, character); tsc + build (frontend container); live check in Chrome on localhost (desktop + 360px): NPC page regression, items (each type's tabs, create furniture, save from a non-general tab, conversions, image, Выдать, delete, Готов, filters/URL), mobs (tabs, region filter on real data, spawns count, dirty prompts, Готов, delete, URL); verify public item/mob responses carry no mark. | Reviewer | DONE | all | #1–#7 | Checklist passed, live verification recorded in section 5 |

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-10 — **PASS**

#### Scope checked
- inventory-service: migration 036 (plain `add_column`s with `_has_column` guards, `down_revision=035`, no ENUM touched), `Items.admin_ready*`, `GET /inventory/admin/items` (`items:read`, column-only query, declared before `/{character_id}/items`), `PUT /inventory/admin/items/{id}/ready` (`items:update`, idempotent, Extra.forbid, Russian 404/500). `schemas.Item`/`ItemCreate` untouched.
- character-service: migration 049 (information_schema-guarded `ALTER TABLE ... ADD/DROP COLUMN`, down 048), `MobTemplate.admin_ready*`, `crud.get_mob_templates` (`location_ids` subquery, `ready`), `mob_template_spawn_counts` (one grouped query), `reputation_crud.admin_geo_location_ids` (NPC list refactored onto it, semantics identical), `PUT /admin/mob-templates/{id}/ready` (`mobs:manage`). `MobTemplateResponse`/`MobTemplateDetailResponse` are used only by the two admin routes; `MobInLocation` untouched; no `SELECT *` / positional `INSERT` readers of `items` / `mob_templates` in any service.
- frontend: `Admin/ExpandableList/*` kit, NPC page on the kit, items page (`ItemsAdminPage`, `ItemRow`, `ItemExpandedPanel`, `itemTabKeys`, `useItemListFilterUrlState`, `ItemForm` one form with tab panes, `IssueItemModal`), mobs page (`AdminMobTemplates`, `MobRow`, `MobExpandedPanel`, `mobTabKeys`, editors with `onDirtyChange`), `api/items.ts`, `api/mobs.ts` (additive), `api/adminGeo.ts`, `api/npcAdmin.ts`; PM fix in `GrantPerkModal`, `GrantTitleModal`, `ProfessionsAdminPage`; `PanelTabs` active-tab scroll-into-view.
- Rules: no `React.FC`, no `any`, no SCSS/CSS imports in touched components, all new files TS, Tailwind + design-system classes, every API error → Russian toast, Pydantic v1 syntax, sync style kept in both services. No dangling imports of the deleted `ItemList.tsx`, `AdminMobDetail.tsx`, `NpcTabs.tsx`, `useNpcPanelUrlState.ts`, `useNpcListFilterUrlState.ts`, `AdminNpcsPage/useDirtyReport.ts`.

#### Small fixes made by Reviewer
1. Deleted `src/api/characters.js` — its only export `fetchCharacters()` lost its last consumers with the PM fix (and was the broken non-paginated call itself). Dead code.
2. `useItemListFilterUrlState.ts`: `rawRarity in RARITY_LABELS` → `Object.prototype.hasOwnProperty.call(...)` (`?rarity=constructor` was accepted as valid). Verified live: now silently removed.
3. `MobStatsEditor`: removed the unused `templateName` prop (and its pass-through in `MobExpandedPanel`).

#### Notes (non-blocking)
- Mobs «Удалить» is not dirty-guarded (items is); deleting discards the panel anyway, acceptable.
- Errors of the inventory axios client on a pure network failure carry axios' English message (pre-existing client behaviour, not new).
- `ItemXpBuffsEditor` is cramped at 360px inside the panel (pre-existing editor layout, no page overflow).

#### Automated Check Results
- [x] `py_compile` (all modified/new backend files incl. migrations and tests) — PASS
- [x] `pytest` inventory-service: `test_item_admin_ready.py` + `test_migrations_024_025.py` — 66 passed
- [x] `pytest` character-service: `test_admin_mob_region_ready.py` + `test_admin_npc_region_ready.py` + `test_admin_npc_list.py` + `test_mob_templates.py` — 179 passed (full suites per QA: inventory 2499, character 9839 — not re-run)
- [x] `npx tsc --noEmit` (frontend container) — PASS, 0 errors (re-run after reviewer fixes)
- [x] `vite build` to /tmp (frontend container) — PASS (re-run after reviewer fixes)
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome, localhost, admin) — PASS

#### Live Verification Results
- API: `GET /inventory/admin/items` 200, 66 slim rows with `admin_ready*`; public `/inventory/items`, `/inventory/items/{id}`, admin `/inventory/admin/items/{id}` and `/characters/mobs/by_location` contain no `admin_ready`; mob list rows carry `spawn_count` + `admin_ready*`; `country_id=7` → 6 mobs (other countries 0, matching spawn data).
- `/admin/items`: categories + counts, plates, sort strip; expand → tabs; «Сохранить» without changes on item 4 → admin payload byte-identical before/after; tab sets per type (weapon/body/belt/cloak = Основное/Свойства/Модификаторы; consumable/scroll = +Боевые эффекты/Бафы опыта; furniture/whetstone/repair kit/plain resource = Основное/Свойства; trophy = +Переработка; recipe = Основное only); unavailable `tab` normalised to `general`; off-category items pinned «Открыт по ссылке»; hidden required field (repair kit «Свойства» select cleared, submit from «Основное») → switched to «Свойства» + toast «Заполните обязательные поля на вкладке «Свойства»», no PUT sent; collapse with unsaved changes → «Уйти без сохранения?», confirm → closed, item unchanged in DB; «Готов» on/off → gold plate + ✓ + tooltip «Отметил …», toasts, ready=1 filter keeps the open item pinned; «Выдать» opens IssueItemModal with the item preselected, server character search finds «Ашари» (closed without issuing); `?item=99999` → «Предмет не найден» + params cleared; garbage `item/tab/type/rarity/ready` → silently cleared.
- `/admin/mobs`: all 5 tabs on mob 7, loot edit → tab switch asks «Уйти без сохранения?» (confirmed, nothing saved), «Готов» on/off; country→region selects (7 regions of Шинзо) filter the list; reload of `?mob=56&tab=skills&country=7&region=14&ready=xx` restores mob/tab/filters, drops `ready=xx`; `?mob=new&tab=loot` → `general` only; `?mob=99999` → «Моб не найден» + cleared.
- `/admin/npcs` regression: plate expand, 6 tabs by role, tab in URL, country filter keeps the open NPC, history back works.
- PM-fixed modals: «Выдать перк», «Выдать титул», «Установить ранг» (professions) open without crash and find «Ашари» via server search.
- 360px (same-origin iframe): no horizontal page overflow on items and mobs; tab strip scrolls, active last tab («Бафы опыта», «Спавны») scrolled into view.
- Console errors: none. Cleanup: 0 ready items / mobs / NPCs left; no test data created; mob 7 loot unchanged.

## 6. Logging (all agents — in Russian)

```
[LOG] 2026-11-10 — PM: фича создана, запускаю анализ и проектирование
[LOG] 2026-11-10 20:00 — Analyst: начал анализ: админки айтемов и мобов, бэкенд inventory-service (items) и character-service (mob_templates), наработки FEAT-208/209
[LOG] 2026-11-10 20:30 — Analyst: анализ завершён: список айтемов грузит весь каталог через публичный GET /inventory/items и фильтрует на клиенте (тип/редкость есть, но не в адресе, пагинации нет); форма предмета — одно состояние и один submit + переработка после сохранения; мобы и их спавны живут в character-service рядом с хелпером region_location_ids из FEAT-209; права у мобов одно — mobs:manage
[LOG] 2026-11-10 20:35 — Architect: начал проектирование
[LOG] 2026-11-10 21:00 — Architect: спроектировано: общий набор компонентов/хуков в Admin/ExpandableList (НПС переезжает на него), «Готов» = 3 колонки на items (inventory 036) и mob_templates (character 049), новые GET /inventory/admin/items, PUT .../ready для айтемов и мобов, фильтр мобов по стране/региону через места спавна; форма предмета остаётся одной формой с вкладками-секциями и одной кнопкой «Сохранить»; 8 задач (2 Backend, 3 Frontend, 2 QA, Reviewer); при создании предмета видны все вкладки его типа (иначе мебель/инструменты не создать)
[LOG] 2026-11-10 22:10 — Frontend Dev: задача #3 готова: общий набор Admin/ExpandableList (ExpandableRow, ExpandedPanelShell, PanelTabs, ReadyToggle, ReadyFilterSelect, GeoFilterSelects, хуки usePanelUrlState/useDirtyGuard/useDirtyReport/useReadyFilterUrlState/useGeoFilter, readyMark, api/adminGeo.ts), админка НПС переведена на него без видимых изменений; tsc и vite build в контейнере прошли; живая проверка /admin/npcs (раскрытие/сворачивание, вкладки по ролям, адрес и «назад», сброс мусора и чужого региона, закреплённая плашка, вопрос о несохранённом, создание и удаление тестового НПС, «Готов» вкл/выкл — готовых не осталось, 360px) — без ошибок в консоли. Попутно: правки адреса теперь берут свежий location.search, поэтому несколько одновременных сбросов не затирают друг друга
[LOG] 2026-11-10 21:40 — Backend Dev: задача #2 готова: миграция character 049_mob_admin_ready (3 колонки admin_ready* на mob_templates, upgrade/downgrade/upgrade в контейнере ок), общий хелпер reputation_crud.admin_geo_location_ids (список НПС переведён на него без изменения поведения), GET /admin/mob-templates + country_id/region_id/ready и spawn_count/admin_ready* в строках, admin_ready* в деталях, PUT /admin/mob-templates/{id}/ready (mobs:manage); контракт §3 не менялся, docs обновлены
[LOG] 2026-11-10 21:45 — Backend Dev: начал задачу #1 (inventory-service)
[LOG] 2026-11-10 22:15 — Backend Dev: задача #1 завершена, изменено 6 файлов: миграция 036_item_admin_ready (3 колонки admin_ready* на items; upgrade/downgrade/upgrade в контейнере ок), GET /inventory/admin/items (тонкий список, объявлен до /{character_id}/items) и PUT /inventory/admin/items/{id}/ready (идемпотентно, кто/когда); публичные/админ-карточки без отметки (проверено вживую); тест-голова миграций в test_migrations_024_025.py сдвинута на 036; весь набор inventory: 2452 passed, 1 skipped; документация обновлена
[LOG] 2026-11-10 22:45 — QA: задача #6 готова: test_item_admin_ready.py — 47 тестов (список /inventory/admin/items: 401/403/200 по items:read, не перехватывается /{character_id}/items, порядок по id, тонкие поля, отметка видна; «Готов»: поставить/снять, повтор не меняет кто/когда, кто = username, 404/422/500, 403 для читателя без items:update; публичный список/карточка, админ-карточка и internal без admin_ready*; правка предмета отметку не трогает; миграция 036 → 035). Весь набор inventory: 2499 passed, 1 skipped
[LOG] 2026-11-10 23:30 — Frontend Dev: задача #5 готова: «Мобы» на общем наборе — плашки MobRow (аватар, имя, ID, уровень, тип, «Спавнов: N»), подложка MobExpandedPanel (вкладки Основное/Характеристики/Навыки/Лут/Спавны, в шапке «Готов» и «Удалить»), фильтры страна→регион и готовность в адресе, ?mob=&tab=, закреплённая плашка, создание отдельной плашкой; редакторы сообщают о несохранённом, форма остаётся открытой после сохранения; экран «Подробнее» (AdminMobDetail) удалён; api/mobs.ts — только добавления. tsc и vite build в контейнере прошли. Живая проверка: раскрытие/вкладки, правка и сохранение, статы экземпляра, навыки/лут/спавны добавить+убрать на тестовом мобе (счётчик спавнов обновляется), фильтр Мидденгерд→регион 9, «Готов» вкл/выкл (готовых не осталось), восстановление и сброс мусора в адресе, вопрос о несохранённом, 360px, тестовый моб удалён, «Активные мобы»/«Стаи мобов» открываются, ошибок в консоли нет. Набор Admin/ExpandableList не менялся
[LOG] 2026-11-10 23:40 — Frontend Dev: задача #4 готова: страница айтемов на общем наборе — плашки ItemRow (иконка, название, ID, тип+подкласс/подкатегория, редкость), полоса сортировки над плашками (md+), клиентская пагинация по 50, тип/редкость/готовность в адресе (+ ?item&tab), закреплённая плашка «Открыт по ссылке», плашка создания; ItemForm — одна форма с вкладками-секциями (Основное/Свойства/Модификаторы/Боевые эффекты/Бафы опыта/Переработка по живому типу, скрытые секции остаются смонтированными, одна кнопка «Сохранить», после сохранения форма перечитывается), шапка: Готов/Выдать/Удалить; старый ItemList.tsx удалён (список теперь в ItemsAdminPage.tsx). tsc и vite build в контейнере прошли. Вживую: «сохранить без изменений» на 11 предметах всех типов — данные не меняются (кроме price NULL→0 у 5 предметов: так было и раньше, buildItemPayload не трогал), вкладки по каждому типу, переключение типа меняет вкладки сразу, незаполненная комната мебели → переход на «Свойства» + тост, созданы и удалены тестовые мебель и руда (руда — с вкладки «Переработка»), «Уйти без сохранения?», адрес после перезагрузки и сброс мусора, «Предмет не найден», Готов вкл/выкл (готовых не осталось), 360px без горизонтальной прокрутки, ошибок в консоли нет
[LOG] 2026-11-10 23:40 — Frontend Dev: обнаружен баг: окно «Выдать» роняло страницу (chars.filter is not a function — /characters/list стал постраничным); в IssueItemModal исправлено (серверный поиск персонажей), такой же баг в окнах выдачи перка/титула и в профессиях — добавлен в ISSUES.md, не трогал
[LOG] 2026-11-10 23:40 — Frontend Dev: общий набор Admin/ExpandableList не менял
[LOG] 2026-11-10 23:50 — QA: задача #7 готова: test_admin_mob_region_ready.py — 50 тестов (фильтр мобов по стране/региону через места спавна: район, вложенный подрайон, свой регион у локации, наследование от родителя и его отсутствие при своём регионе, выключенный спавн считается, моб без спавнов не попадает, моб в двух регионах — в обоих и один раз в стране, чужой/неизвестный регион и страна → пусто; вместе с q/tier/ready и пагинацией; spawn_count; хелпер admin_geo_location_ids и совпадение результатов со списком НПС; «Готов»: поставить/снять, повтор не меняет кто/когда, правка шаблона отметку не трогает, 404/422, 403 без mobs:manage, 401; /mobs/by_location и /bestiary без admin_ready*; миграция 049 → 048 и одна голова). Весь набор character-service: 9839 passed, 2 skipped
[LOG] 2026-11-10 19:28 — Reviewer: ревью FEAT-210 — PASS. py_compile, новые тесты (inventory 66, character 179), tsc и сборка в контейнере, docker compose config — ок. Вживую проверены айтемы (вкладки по типам, сохранение без изменений, переход на вкладку с обязательным полем, «Готов», «Выдать», адрес), мобы (все вкладки, фильтр страна→регион, несохранённое, «Готов», адрес), НПС, три починенных окна выдачи, 360px; ошибок в консоли нет, готовых отметок не осталось. Мелкие правки: удалён мёртвый api/characters.js, строгая проверка ?rarity, убран неиспользуемый проп templateName
[LOG] 2026-11-10 — PM: ревью PASS, фича закрыта
```

## 7. Completion Summary (filled by PM on completion — in Russian)

- Айтемы и мобы переделаны как НПС: плашки без кнопок, раскрывающаяся подложка с вкладками, адрес помнит выбор, защита несохранённых правок, создание плашкой сверху, «Готов» (золотистая плашка + ✓, фильтр, общий для админов).
- Айтемы: форма предмета разложена на вкладки по смыслу (одна форма, одно «Сохранить»), фильтры по типу и редкости, «Выдать» и «Удалить» в шапке. Новый GET /inventory/admin/items, PUT .../ready, миграция inventory 036.
- Мобы: вкладки «Основное», «Характеристики», «Навыки», «Лут», «Спавны»; экран «Подробнее» убран; фильтр «Страна → Регион» по местам спавна; число мест спавна. PUT /characters/admin/mob-templates/{id}/ready, миграция character 049.
- Общие компоненты вынесены в Admin/ExpandableList, админка НПС переведена на них без видимых изменений.
- Попутно починено (было на проде): «Выдать предмет», «Выдать перк», «Выдать титул» и выбор персонажа в профессиях падали белым экраном из-за постраничного списка персонажей.
- Тесты: inventory 2499, character 9839 — зелёные. Ревью PASS.

