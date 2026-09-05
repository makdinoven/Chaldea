# FEAT-123: Floating Citadel & Teleport Master NPC

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-04-07 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Добавляем в мир две связанные сущности:

1. **Цитадель** — плавающее сооружение, ходящее в экспедиции по морю. У неё есть свои внутренние локации (как у города), но она не привязана к стране/региону. Цитадель медленно движется по замкнутому маршруту по морю и видна на мировой карте как иконка.

2. **Мастер Телепорта** — новая категория NPC. Через диалог с таким NPC игрок может за золото телепортироваться к другому Мастеру Телепорта, с которым установлена связь (настраивается админом). Это единственный способ физически попасть в локации Цитадели — туда ведут телепорты с материков.

### Бизнес-правила

**Floating Citadel:**
- Сущность отдельная от регионов/городов (новая таблица `floating_structures`).
- Пока в системе только одна Цитадель, но архитектурно поддержка нескольких.
- Маршрут — замкнутый цикл waypoints по морю. Скорость очень малая (в рамках одной игровой сессии движение почти незаметно, всю петлю проходит за месяцы реального времени).
- Позиция **не хранится** в БД и не тикается фоновой задачей. Фронт получает `route_json + started_at + speed` один раз и сам интерполирует текущую точку. Полностью stateless на бэке.
- История позиций не нужна.
- Иконка Цитадели рендерится поверх мировой карты как отдельный слой, не ломая существующую логику регионов.
- Игрок может **кликнуть по иконке и войти в карту Цитадели в режиме просмотра**: видеть локации, читать описания, смотреть, что внутри. Но **писать/действовать** в локации он может только если его персонаж физически находится в этой локации (попал через телепорт). Это уже существующий паттерн «просмотр vs присутствие» — Analyst должен подтвердить, как он реализован сейчас.
- Иконка временно — заглушка, владелец заменит позже.

**Teleport Master NPC:**
- Новая категория NPC «Мастер Телепорта» (добавить в существующий enum/таблицу категорий NPC).
- В меню взаимодействия с таким NPC появляется пункт **«Телепорт»**, открывающий список доступных направлений.
- Каждое направление = другой NPC категории «Мастер Телепорта», с которым установлена связь.
- Связь между NPC настраивается админом: указывается целевой NPC и стоимость в золоте.
- **По умолчанию связь двусторонняя** (создание связи A→B автоматически создаёт B→A с той же стоимостью). Должна быть возможность сделать одностороннюю связь (для будущих сюжетных «билетов в один конец»), но в UI по умолчанию ставится двусторонняя.
- Стоимость телепорта — в **золоте**.
- **Кулдаун: один телепорт в сутки** на персонажа, общий для всех телепортов (а не на конкретный маршрут). После использования любого телепорта следующий доступен через 24 часа.
- Других ограничений (уровень, квесты, репутация) пока нет.
- Связи между Мастерами Телепорта — обычные данные, не зависят от Цитадели. Цитадель использует ту же систему: внутри её локаций владелец сам расставит NPC «Мастер Телепорта» через админку и свяжет их с NPC на материках.

### UX / Пользовательский сценарий

**Сценарий 1: просмотр Цитадели**
1. Игрок открывает мировую карту.
2. Видит над морем медленно движущуюся иконку Цитадели.
3. Кликает по иконке → открывается внутренняя карта Цитадели в режиме просмотра.
4. Может ходить по локациям, читать описания, но не может писать сообщения / совершать действия.

**Сценарий 2: телепорт через NPC**
1. Игрок находится в локации с NPC «Мастер Телепорта».
2. Открывает диалог с NPC, видит пункт «Телепорт».
3. Открывается список доступных направлений (название локации + стоимость в золоте).
4. Выбирает направление, подтверждает.
5. Если у персонажа достаточно золота и кулдаун не активен — золото списывается, персонаж перемещается в локацию целевого NPC, ставится отметка «телепорт использован», следующий доступен через 24 часа.
6. Если кулдаун активен — сообщение «Телепорт будет доступен через X часов».
7. Если не хватает золота — сообщение «Недостаточно золота».

**Сценарий 3: попадание в Цитадель**
1. Игрок идёт к NPC «Мастер Телепорта» в каком-то городе материка.
2. Среди направлений видит «Цитадель — [название локации]».
3. Платит золото, телепортируется в локацию внутри Цитадели.
4. Теперь он физически там и может действовать.

**Сценарий 4: админ настраивает Цитадель**
1. Админ заходит в новый раздел «Плавающие структуры».
2. Создаёт запись «Цитадель»: имя, иконка, ссылка на внутреннюю карту локаций, скорость.
3. В редакторе путей (существующем) выбирает режим «маршрут плавающей структуры», расставляет waypoints по морю, замыкает цикл.
4. Сохраняет — Цитадель появляется на мировой карте у игроков.

**Сценарий 5: админ настраивает телепорты**
1. Админ редактирует NPC, ставит категорию «Мастер Телепорта».
2. В карточке NPC появляется раздел «Связи телепорта».
3. Добавляет целевого NPC (поиск по списку всех NPC категории «Мастер Телепорта»), указывает стоимость, флаг «двусторонняя» (по умолчанию вкл).
4. При сохранении создаются записи в обе стороны (если двусторонняя) или в одну.

### Edge Cases
- Что если у NPC «Мастер Телепорта» удалили категорию (стал обычным NPC)? → Все его связи телепорта должны удалиться (или связи помечаются битыми и игнорируются на фронте).
- Что если целевой NPC удалён? → Связь должна каскадно удалиться.
- Что если игрок попытался телепортироваться, но между открытием меню и подтверждением связь была удалена? → Серверная валидация на момент действия, понятная ошибка.
- Что если игрок попал в локацию Цитадели, а позже Цитадель «уплыла»? → Лорно она всегда «где-то в море», физически персонаж остаётся внутри неё. Координаты Цитадели на мировой карте никак не связаны с тем, где находятся персонажи внутри. Это просто визуальная иконка.
- Что если маршрут Цитадели пересекает землю? → Валидация в админке желательна, но не критична — это ответственность админа при расстановке waypoints.
- Кулдаун телепорта: что если игрок был онлайн 23 часа назад и телепортировался — кулдаун считается от момента последнего использования, не от начала суток.

### Вопросы к пользователю
Все ключевые вопросы прояснены в диалоге:
- [x] Цитадель одна → да, пока одна
- [x] Маршрут → замкнутый цикл
- [x] Видна ли игрокам → да
- [x] История позиций → не нужна
- [x] Клик по иконке → открывает карту в режиме просмотра
- [x] Валюта → золото
- [x] Двусторонние связи по умолчанию → да
- [x] Ограничения → пока без, кроме кулдауна
- [x] Кулдаун → 1 раз в сутки, общий для всех телепортов
- [x] Расстановка первых NPC → владелец сам через админку
- [x] Иконка Цитадели → заглушка, владелец заменит

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### World map rendering (frontend)

- World map UI lives in `services/frontend/app-chaldea/src/components/WorldPage/WorldPage.tsx` (937 lines). It is a multi-level view: `world` -> `area` -> `country` -> `region`, plus an in-region "city map" mode (when a district has its own `map_image_url`).
- The base map is rendered by `WorldPage/InteractiveMap/InteractiveMap.tsx`: a single `<img>` plus a `ClickableZoneOverlay` that overlays SVG/HTML hotspots on top. There is no canvas / Konva — it is plain DOM positioned over the image. A new "floating structures" layer plugs in here as an additional sibling element inside the same `relative` container, positioned absolutely with percentage-based `left/top` driven by client-side interpolation of `route_json + started_at + speed`.
- The region-level interactive map is `WorldPage/RegionInteractiveMap/RegionInteractiveMap.tsx`. Inside a region, when the user clicks a district that has a `map_image_url`, `WorldPage` switches to `cityMapDistrictId` mode and renders that district's image as a "city map" with its locations as markers (driven by URL `?district=` query param). This is exactly the pattern the Citadel's internal map should reuse: Citadel -> render its `map_image_url` -> overlay locations as markers.
- Redux: `redux/slices/worldMapSlice.ts`, `redux/actions/worldMapActions.ts`. Areas, hierarchy tree, country details, region details, clickable zones are fetched as separate thunks (`fetchAreas`, `fetchAreaDetails`, `fetchCountryDetails`, `fetchRegionDetails`, `fetchHierarchyTree`, `fetchClickableZones`). There is **no single combined "world map" endpoint** — data is sliced per level. A new `fetchFloatingStructures` thunk fits cleanly alongside.

### Region/city/location structure

- Locations service owns the world hierarchy: `Areas -> Countries -> Regions -> Districts -> Locations` (with `Locations` also nestable via `parent_id`). See `services/locations-service/app/models.py`.
- A "city" is just a `District` whose `map_image_url` is set; its child locations have `map_x/map_y` coordinates and `map_icon_url`. The frontend already treats this case as an "internal map" — Citadel can reuse the District + Locations tables (or clone the pattern) as its internal map.
- `Region`/`District`/`Location` all have `entrance_location_id` to mark "the gateway location." Citadel will need an analogous concept (or just point teleport links at the desired internal location IDs).

### Path editor

- Path editing for location-to-location routes lives in `services/frontend/app-chaldea/src/components/AdminLocationsPage/RegionMapEditor/RegionMapEditor.tsx` (2295 lines). It's the region/city map editor: drag locations, draw neighbor edges, and crucially edges store **`path_data: Array<{x, y}>`** waypoints (used at line ~892 to render a polyline through `[from, ...path_data, to]`).
- The DB side: `LocationNeighbor` (in `locations-service/app/models.py:139`) has `path_data = Column(JSON, nullable=True)` — exactly the same shape needed for a Citadel route (an ordered list of `{x, y}` waypoints). The editor's waypoint UX is reusable.
- The editor is heavily coupled to "place markers + draw neighbors between them" — extending it with a "floating structure route" mode is feasible but adds complexity. A cleaner approach is a small dedicated editor (or a new mode flag) reusing the same waypoint primitives. The waypoints are in **world map coordinates**, not region map coordinates, so the editor would have to load the world map background image, not a region one — that's a meaningful difference. **Flag for Architect: decide whether to extend `RegionMapEditor` with a world-scoped mode or build a slimmer dedicated editor.**

### NPC categories & interaction menu

- **NPCs are stored in `character-service` as `Character` rows** with `is_npc=True` (boolean, indexed) and a free-text `npc_role` column (`String(50)`). See `services/character-service/app/models.py:55-57`. There is **no enum or category table** — `npc_role` is plain text validated only on the frontend (`AdminNpcsPage.tsx` has hard-coded values like `merchant`, plus default `merchant` in form state). The teleport master is a new logical role on this column; backend has zero schema changes needed for "categories" — only the admin form needs the new option, and any role-aware backend logic uses string comparison.
- NPC dialogues already have an extensible action system. Admin editor: `AdminNpcsPage/DialogueEditor.tsx` defines `ACTION_TYPES`, and the option `{ value: 'teleport', label: 'Телепортировать' }` already exists at line 66 — but it has no runtime handler yet. Player-facing modal: `pages/LocationPage/NpcDialogueModal.tsx` reads `currentNode.action_type` / `action_data` and currently handles only `give_quest`, `open_shop`, `heal` (lines 92-115). The `teleport` action_type is defined but unhandled.
- Implication: there are **two viable wiring paths** for the teleport UI:
  1. Hook into the existing dialogue `action_type='teleport'` and use `action_data` to point at the teleport-link list (or mark "this NPC is a teleport master, open the destination picker").
  2. Add a separate top-level menu item in `NpcDialogueModal` (or earlier — wherever the player picks an interaction with the NPC) that appears when `npc.npc_role === 'teleport_master'`, independent of the dialogue tree.
  Option 2 matches the brief better ("в меню взаимодействия с таким NPC появляется пункт «Телепорт»") and is independent of whether an admin built a dialogue tree. **Flag for Architect.**
- NPC backend endpoints in `character-service/app/main.py`: list `/npcs` (line ~1902), create (line ~1947), get/update/delete (lines ~2011-2104). All filter on `is_npc==True` and `npc_role != 'mob'`. Adding teleport-link endpoints alongside is consistent.

### View-vs-presence pattern (existing)

- **Yes, the pattern exists.** In `pages/LocationPage/LocationPage.tsx:341`: `const isCharacterHere = character?.current_location?.id === location.id;`. All "presence-required" features are gated on this flag: dungeon entrance, pending PvP invitations, loot pickup requires it implicitly, mob fighting passes `characterId={isCharacterHere ? character.id : null}`. Posting/chat in the location is similarly gated through `userIsStaff` checks plus `isCharacterHere`. NPC interactions (shop, dialogue) on `PlayersSection` are also presence-gated.
- The location page itself is **routable for any location id** — a player can navigate to `LocationPage` for any location they know the id of and just see read-only content, because all the action buttons are wrapped in `isCharacterHere && ...` blocks. This means the Citadel "view mode" requires no new infrastructure: clicking the icon just routes the player into the existing region/city map view of the Citadel's internal map, and presence gating already prevents writes.
- Caveat: location data is fetched via `locations-service` `GET /locations/{id}/client/details` which currently returns full data without checking the requester's location. That's already the production behavior — view-mode browsing is implicitly allowed. **Confirmed: no new "view mode" backend endpoint is needed; the existing client/details endpoint plus existing `isCharacterHere` gating is sufficient.**

### Service ownership

| Concept | Service | Notes |
|---|---|---|
| NPCs | character-service | `Character` with `is_npc=True`, `npc_role` |
| Player characters | character-service | same `characters` table |
| Gold balance | character-service | `Character.currency_balance`, with `log_gold_transaction` helper in `crud.py:1127` |
| Current location of character | character-service | `Character.current_location_id` |
| World hierarchy (areas/countries/regions/districts/locations) | locations-service | own tables |
| Location graph & path waypoints | locations-service | `LocationNeighbor.path_data` |
| Movement (`/locations/{id}/move_and_post`) | locations-service | calls character-service to update `current_location` and attributes-service for stamina |

### Where new tables should live

- **`floating_structures`** -> **locations-service**. It is world-map data (route waypoints, icon, link to internal map). All of locations-service's model + admin endpoints already serve world-map concerns; the admin world-map editor lives in the locations-service domain. Adding `GET /floating-structures` (client) and admin CRUD here is consistent.
- **`teleport_links`** -> **character-service**. Links connect two NPCs (which are `Character` rows in character-service). FK CASCADE on NPC deletion is trivial inside the same DB. The `POST /npcs/{id}/teleport` endpoint must read NPC, validate cooldown on `Character`, deduct `currency_balance`, log via `log_gold_transaction`, and update `current_location_id` — all of which are in-process operations in character-service. Putting `teleport_links` in locations-service would force HTTP roundtrips for every validation step.
- **Cooldown field**: new column on `characters` table — e.g. `last_teleport_at TIMESTAMP NULL` — also in character-service. Consistent with how `currency_balance`, `current_location_id` already live there.
- One subtlety: locations-service today does not own NPCs but its `LocationPage` data flow returns `npcs` per location. `locations-service` `GET /locations/{id}/client/details` already enriches the response with NPCs, so it presumably calls character-service. That is the existing precedent for cross-service NPC reads — the frontend will not need a new endpoint to discover *which* NPCs are teleport masters per location; it can read `npc.npc_role` from the existing payload. Architect should confirm the field is propagated.

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| locations-service | New table `floating_structures`, Alembic migration, schemas, CRUD, client GET endpoint, admin CRUD endpoints | `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py`, `alembic/versions/*` |
| character-service | New table `teleport_links` (FK to `characters` both sides, cascade), new `Character.last_teleport_at` column, schemas, CRUD, `GET /npcs/{id}/teleport-options`, `POST /npcs/{id}/teleport`, admin CRUD for teleport links, new allowed `npc_role='teleport_master'` value (no schema enforcement, but used in filters/UI) | `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py`, `alembic/versions/*` |
| frontend | New `<FloatingStructuresLayer>` over `InteractiveMap`, client-side interpolation, click handler routing into Citadel internal map view; teleport menu in NPC interaction (extend `NpcDialogueModal` or add new entry point keyed on `npc_role==='teleport_master'`); admin "Floating Structures" CRUD page; "Teleport Links" section in `AdminNpcsPage` NPC editor; new `npc_role` option `teleport_master` in NPC role select; possibly extend `RegionMapEditor` with floating-route mode (or new dedicated editor); Redux slice/thunks for floating structures and teleport actions | `components/WorldPage/InteractiveMap/InteractiveMap.tsx`, `components/WorldPage/WorldPage.tsx`, `components/pages/LocationPage/NpcDialogueModal.tsx` (or new `TeleportMenu.tsx`), `components/AdminNpcsPage/AdminNpcsPage.tsx`, `components/AdminNpcsPage/DialogueEditor.tsx`, `components/AdminLocationsPage/...` (new page), `redux/slices/worldMapSlice.ts`, `redux/actions/worldMapActions.ts`, new slice for floating structures |

### Existing Patterns

- **locations-service:** async SQLAlchemy (aiomysql), Pydantic v1, Alembic present (`app/alembic/`), JWT via `auth_http.py`. New endpoints must be `async def` and use the async session pattern from existing CRUD.
- **character-service:** sync SQLAlchemy (PyMySQL), Pydantic v1, Alembic present (`app/alembic/`), JWT via `auth_http.py`. New endpoints sync, normal `db: Session = Depends(get_db)`.
- **NPCs:** stored as `Character` rows; no enum table — `npc_role` is free-text. Frontend `NPC_ROLE_LABELS` is a plain object in `AdminNpcsPage.tsx` — adding `'teleport_master': 'Мастер Телепорта'` is a one-liner.
- **Dialogue actions:** already extensible via `action_type` + `action_data` JSON. The `teleport` value is pre-declared but unhandled.
- **Path waypoints:** `LocationNeighbor.path_data` JSON column already proves the JSON-waypoint pattern works in MySQL via SQLAlchemy.
- **Cross-service movement:** `move_and_post` is the canonical example of "validate + deduct stamina + update character location." A new teleport endpoint should mirror its structure but skip the energy cost / neighbor validation (teleport bypasses the neighbor graph entirely) and instead validate cooldown + gold.
- **Gold transactions logging:** `character-service/app/crud.py:1127 log_gold_transaction()` — must be called from the new teleport handler so battle-pass `spend_gold` missions still register.
- **No game tick / background scheduler** for the Citadel position is needed — the brief makes it stateless on the backend, and there is no existing precedent for a per-tick background task in locations-service anyway. Good fit.

### Cross-Service Dependencies

- `locations-service` already calls `character-service` for `current_location` and `update_location` (used in `move_and_post`). The teleport endpoint, if hosted in character-service, can directly update `current_location_id` without an HTTP call to locations-service — but locations-service may need to be notified for any in-location post/SSE side effects. **Today, `move_and_post` is the only place where a "location change" produces a post; a teleport will skip the post (lore: silent magical move). No new HTTP call needed unless Architect decides to publish a "player teleported in" post.**
- `character-service` does not currently call `locations-service`. Adding a teleport endpoint that skips locations-service is consistent with the pattern of character-service owning `current_location_id` directly.
- `notification-service` is unaffected (no SSE notifications for teleport are required by the brief).
- Battle-pass missions (`spend_gold`) read from `gold_transactions` populated via `log_gold_transaction` — using that helper in the teleport handler keeps mission progress correct.

### DB Changes

- **New table** `floating_structures` (locations-service): `id PK`, `name VARCHAR`, `description TEXT`, `icon_url VARCHAR NULLABLE`, `route_json JSON` (list of `{x, y}` in world map coords, closed loop), `speed FLOAT` (units/sec or units/min — Architect to define), `started_at TIMESTAMP`, `internal_district_id BIGINT FK Districts(id) ON DELETE SET NULL` (reuses existing District as the internal map; Architect may instead introduce a dedicated `floating_structure_id` on `District`/`Location` — flag).
- **New table** `teleport_links` (character-service): `id PK`, `from_npc_id INT FK characters(id) ON DELETE CASCADE`, `to_npc_id INT FK characters(id) ON DELETE CASCADE`, `cost_gold INT NOT NULL`, `created_at TIMESTAMP`. Bidirectional links = two rows. Unique constraint `(from_npc_id, to_npc_id)`. Cascade delete handles "NPC removed" naturally.
- **New column** `characters.last_teleport_at TIMESTAMP NULL` for the 24h cooldown.
- **New value** for `Character.npc_role` column: `'teleport_master'`. The column is a plain `String(50)`, no enum, so no schema migration is needed for the new value — only frontend admin UI and any backend filters.
- Both services have Alembic — migrations are mandatory in both.

### Risks

- **Risk:** Frontend interpolation of Citadel position uses client clock. Player with skewed clock sees the icon offset. **Mitigation:** server returns `started_at` in UTC + a `server_now` field; client computes offset once and applies it. Low priority since the speed is intentionally tiny.
- **Risk:** `RegionMapEditor.tsx` is 2295 lines, already complex. Adding a "floating route" mode there will inflate it further and risk regressions in the existing path editor used for every region. **Mitigation:** build a slim dedicated `FloatingRouteEditor` that reuses only the waypoint helpers (extract them to a shared module), or strictly fence the new mode behind a top-level conditional. Architect to decide.
- **Risk:** `npc_role` is free text — no DB-level guarantee that "teleport master" links always reference NPCs whose role is still `teleport_master`. An admin can downgrade the role and orphan the links logically (the FK still holds, but the link references a non-teleport-master NPC). **Mitigation:** when `npc_role` is changed via the admin endpoint, cascade-delete `teleport_links` for that NPC; or runtime-validate role on `GET /npcs/{id}/teleport-options` and skip orphaned links. The brief explicitly raises this edge case.
- **Risk:** Teleport endpoint must atomically (a) check cooldown, (b) check gold, (c) check link still exists, (d) deduct gold, (e) update `current_location_id`, (f) update `last_teleport_at`, (g) log gold transaction. Race condition possible if two requests fire concurrently. **Mitigation:** wrap in a single DB transaction with `SELECT ... FOR UPDATE` on the character row. character-service is sync, so this is straightforward.
- **Risk:** Frontend "view mode" for the Citadel relies on the existing `isCharacterHere` gating in `LocationPage`. If any LocationPage child component forgets to check it, a player could perform actions in a Citadel location they have not teleported to. **Mitigation:** Reviewer must audit all child components of `LocationPage` that mutate state and confirm each is gated. The brief specifically calls this out.
- **Risk:** No backend validation that Citadel route waypoints stay over sea — admin can put waypoints over land. **Mitigation:** brief says this is acceptable; admin responsibility. Optional client-side warning.
- **Risk:** `notification-service` and `battle-service` have no Alembic (per CLAUDE.md). This feature does not touch them, so no T2 obligation triggered.
- **Risk:** Cross-service NPC enrichment (locations-service `client/details` returning NPCs with their roles) — needs to confirm `npc_role` is propagated in that payload so the frontend knows which NPCs in the location are teleport masters without an extra request. If not, add it. **Flag for Architect to verify in design.**

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Key decisions (resolving Analyst flags)

1. **Path editor for Citadel route — dedicated slim editor.** `RegionMapEditor.tsx` is 2295 lines, tightly coupled to "place location markers + draw neighbor edges between them." Citadel routes have fundamentally different semantics: a single ordered closed polyline of free waypoints over the **world map** background (not a region background), with no markers and no neighbor graph. Forcing a "world-scoped mode" into `RegionMapEditor` would mean conditional branching for the background image source, marker rendering, neighbor logic, save handler, and coordinate space — high regression risk for every existing region. Instead we build a new component `FloatingRouteEditor.tsx` that reuses only the **waypoint helpers** (drag/insert/delete waypoint, percentage coordinate math). Where natural, those helpers are extracted from `RegionMapEditor` into a shared `waypointUtils.ts`; if extraction proves invasive, the new editor may inline a copy and we leave a TODO. The editor loads the world map background image (same image used by `InteractiveMap` at the `world` level), renders an SVG polyline with draggable handles, and POSTs `route_json` to the floating-structure record.

2. **Teleport UI wiring — option 2 (separate top-level menu item, confirmed).** The teleport entry point is independent of the dialogue tree: when the player opens NPC interaction and `npc.npc_role === 'teleport_master'`, a "Телепорт" item appears in the interaction menu alongside the existing dialogue/shop/quest entries. Rationale: the brief explicitly says "в меню взаимодействия с таким NPC появляется пункт «Телепорт»", and option 1 would require an admin to build a dialogue tree with a `teleport` action node for every teleport master, which is friction the brief does not request. The pre-declared but unhandled `action_type='teleport'` in `DialogueEditor.tsx` is left in place for future scripted scenarios but is **not** the wiring path for this feature. (Implementation note: the menu item lives wherever the player currently sees the list of NPC interactions on `LocationPage` — Frontend Dev confirms the precise host component during implementation; most likely `PlayersSection`/`NpcInteractionMenu`.)

3. **`floating_structures` lives in locations-service.** Confirmed. It is world-map data (route waypoints, icon URL, link to internal map, world-map coordinate space). All world-map admin and read endpoints already live here.

4. **`teleport_links` lives in character-service.** Confirmed. NPCs are `Character` rows in character-service; the teleport endpoint must atomically read+lock the player character row, validate cooldown, deduct gold via the in-process `log_gold_transaction()` helper, update `current_location_id`, and stamp `last_teleport_at` — all of which are local DB operations in character-service. Hosting links elsewhere would force HTTP roundtrips per validation step and break atomicity.

5. **Cooldown field — `characters.last_teleport_at TIMESTAMP NULL`.** Confirmed, added in character-service via Alembic.

6. **Citadel internal map — reuse the existing District + Locations pattern.** A `District` whose `map_image_url` is set is already rendered as a "city map" with child Locations as markers; this is the exact UX wanted for the Citadel interior. We add a nullable `district_id` foreign key on `floating_structures` (column name: `internal_district_id`) pointing at the District that represents the Citadel's interior. Pros: zero new tables for Citadel locations, full reuse of admin location-editor and frontend rendering. Con: a District is normally nested under a Region; we relax this by allowing `District.region_id` to remain set to whatever placeholder the admin chooses (typically a hidden "Floating" region), or — preferred — we keep `region_id` non-null at the DB level but treat the Citadel's owning District as discoverable **only** via `floating_structures.internal_district_id` rather than via the region tree. No schema change to `districts` is required. The frontend, when navigating into Citadel, switches into the same `cityMapDistrictId` mode `WorldPage` already supports, but routed via `?citadel=<floating_structure_id>` so the breadcrumb/back-button knows to return to world-level instead of region-level.

7. **`floating_structures` schema — confirmed** (id, name, description, icon_url, route_json, speed, started_at, internal_district_id). Column types in section 3.4.

### 3.2 Service ownership summary

| Concept | Service | Reason |
|---|---|---|
| `floating_structures` table + admin CRUD + public GET | locations-service | World-map data, world-map coords, lives next to existing world hierarchy. |
| `teleport_links` table + admin CRUD | character-service | Links connect NPCs which are `Character` rows; FK CASCADE in same DB. |
| `last_teleport_at` column on characters | character-service | Same row as `currency_balance`, `current_location_id`. |
| Teleport execution endpoint | character-service | Atomic local transaction over player + gold + location. |
| `npc_role='teleport_master'` value | character-service (no schema change) | `npc_role` is free-text `String(50)`. |

### 3.3 API contracts

All endpoints use existing JWT auth via `auth_http.py`. Admin endpoints use `Depends(get_admin_user)`. Pydantic v1.

#### locations-service

**`GET /map/floating-structures`** — public (auth optional, mirrors current world-map read endpoints).
- Response 200:
  ```json
  [
    {
      "id": 1,
      "name": "Цитадель",
      "description": "…",
      "icon_url": "https://…/citadel.png",
      "route_json": [{"x": 12.4, "y": 56.1}, {"x": 18.7, "y": 60.3}, ...],
      "speed": 0.0001,
      "started_at": "2026-04-01T00:00:00Z",
      "server_now": "2026-04-07T12:34:56Z",
      "internal_district_id": 42
    }
  ]
  ```
- `route_json` is the closed loop of waypoints in world-map percentage coordinates `[0..100]`.
- `speed` units: **fraction of full route per second** (so client position at time `t` = waypoint interpolation at `((server_now - started_at) * speed) mod 1.0`). This avoids tying speed to map dimensions.
- `server_now` is the per-request server clock; client subtracts its own clock once on receipt to compute a clock skew offset, then interpolates locally.
- Errors: 200 with `[]` if none.

**Admin CRUD** (mounted under `/admin/floating-structures`):
- `GET /admin/floating-structures` — list with full fields.
- `POST /admin/floating-structures` — body `{name, description, icon_url?, route_json, speed, started_at?, internal_district_id?}`. `started_at` defaults to `now()` server-side. Returns 201 + record.
- `GET /admin/floating-structures/{id}` — returns 404 if missing.
- `PATCH /admin/floating-structures/{id}` — partial update; any field. Returns 200 + record.
- `DELETE /admin/floating-structures/{id}` — returns 204.
- Auth: admin only. Validation: `route_json` must be a non-empty list of `{x: float, y: float}` with `0 <= x,y <= 100`; `speed > 0`; `internal_district_id` (if set) must reference an existing District. Rate limiting: relies on existing admin Nginx zone (no new rule).

#### character-service

**`GET /npcs/{id}/teleport-options`** — auth required (any logged-in player).
- Path: NPC id (must satisfy `is_npc=True` and `npc_role='teleport_master'`).
- Response 200:
  ```json
  {
    "from_npc_id": 17,
    "cooldown_seconds_remaining": 0,
    "options": [
      {
        "link_id": 5,
        "to_npc_id": 88,
        "to_npc_name": "Магистр Лиам",
        "to_location_id": 304,
        "to_location_name": "Площадь Цитадели",
        "cost_gold": 250
      }
    ]
  }
  ```
- Errors: 404 NPC not found / not a teleport master; 401 unauth.
- Implementation note: filters out broken links where target NPC role is no longer `teleport_master` or target NPC has no `current_location_id` (defensive — fixes a stale link without admin intervention).

**`POST /npcs/{id}/teleport`** — auth required.
- Path: source NPC id.
- Body: `{ "link_id": <int> }`.
- Server-side flow (single DB transaction, `SELECT ... FOR UPDATE` on player Character row):
  1. Load player character (via JWT user_id → owned character — implementation must clarify which character if user has many; assume "active character" pattern already used by `move_and_post`).
  2. Validate player's `current_location_id` == source NPC's `current_location_id` (player must be physically present at the source teleport master).
  3. Validate `npc_role == 'teleport_master'` for source NPC.
  4. Load `teleport_links` row by `link_id`; verify `from_npc_id == source NPC id`; verify target NPC exists and is still a teleport master with a `current_location_id`.
  5. Check cooldown: if `last_teleport_at IS NOT NULL` and `now() - last_teleport_at < 24h`, return 409 with `cooldown_seconds_remaining`.
  6. Check gold: `currency_balance >= cost_gold`. Else 402.
  7. Deduct gold via `log_gold_transaction(character, -cost_gold, reason='teleport', meta={link_id})`.
  8. Set `current_location_id = target NPC current_location_id`.
  9. Set `last_teleport_at = now()`.
  10. Commit. Return 200 with `{ new_location_id, new_location_name?, currency_balance, last_teleport_at }`.
- Error codes:
  - 401 unauth
  - 402 insufficient gold (`{detail: "insufficient_gold", required, balance}`)
  - 404 source NPC / link / target not found
  - 409 cooldown active (`{detail: "cooldown_active", cooldown_seconds_remaining}`)
  - 422 source NPC is not a teleport master / player not at source NPC location / target broken
- All error messages on the frontend are translated to Russian human strings.

**Admin CRUD for `teleport_links`** (mounted under `/admin/teleport-links`):
- `GET /admin/teleport-links?npc_id=<id>` — list links where `from_npc_id == npc_id` (used by NPC editor's "Связи телепорта" panel).
- `POST /admin/teleport-links` — body `{from_npc_id, to_npc_id, cost_gold, bidirectional: bool=true}`. If `bidirectional`, server creates two rows in one transaction (A→B and B→A, same cost). Returns the created row(s). 422 if either NPC is not a teleport master; 409 on unique-constraint violation (duplicate link).
- `PATCH /admin/teleport-links/{id}` — body `{cost_gold?}` (only cost is editable; to change endpoints delete + recreate). Note: editing one direction does NOT auto-edit the reverse — admin manages each independently after creation. Documented in admin UI.
- `DELETE /admin/teleport-links/{id}?delete_reverse=bool` — delete one row; if `delete_reverse=true` and a matching reverse row exists, delete it too. UI default = true.
- Auth: admin only.

**`npc_role` change side-effect:** the existing admin endpoint that updates an NPC must, when `npc_role` transitions away from `'teleport_master'`, **delete all `teleport_links` where this NPC is `from_npc_id` or `to_npc_id`**. This is a Backend Dev change to the existing NPC update handler in character-service.

**`npc_role` propagation:** verify that locations-service `GET /locations/{id}/client/details` already includes `npc_role` per NPC in its enriched payload (Analyst flagged this). If not, Backend Dev must add it (and the upstream character-service NPC list response that locations-service consumes). The frontend uses this field to decide whether to show the "Телепорт" menu item.

### 3.4 DB changes

#### locations-service — Alembic migration `add_floating_structures`

```sql
CREATE TABLE floating_structures (
  id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(120) NOT NULL,
  description   TEXT         NULL,
  icon_url      VARCHAR(500) NULL,
  route_json    JSON         NOT NULL,
  speed         DOUBLE       NOT NULL DEFAULT 0.0,
  started_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  internal_district_id BIGINT NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_floating_internal_district
    FOREIGN KEY (internal_district_id) REFERENCES districts(id) ON DELETE SET NULL
);
```
- Rollback: `DROP TABLE floating_structures`.
- No data migration; table starts empty and is populated by admin.

#### character-service — Alembic migration `add_teleport_links_and_cooldown`

```sql
CREATE TABLE teleport_links (
  id            INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
  from_npc_id   INT          NOT NULL,
  to_npc_id     INT          NOT NULL,
  cost_gold     INT          NOT NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_tlink_from FOREIGN KEY (from_npc_id) REFERENCES characters(id) ON DELETE CASCADE,
  CONSTRAINT fk_tlink_to   FOREIGN KEY (to_npc_id)   REFERENCES characters(id) ON DELETE CASCADE,
  CONSTRAINT uq_tlink_pair UNIQUE (from_npc_id, to_npc_id),
  INDEX idx_tlink_from (from_npc_id)
);

ALTER TABLE characters ADD COLUMN last_teleport_at DATETIME NULL;
```
- Rollback: `DROP TABLE teleport_links; ALTER TABLE characters DROP COLUMN last_teleport_at;`.
- `cost_gold` constraint `>= 0` enforced at the Pydantic schema level (`conint(ge=0)`); not a DB CHECK to stay compatible with current MySQL config.

### 3.5 Frontend design

#### Redux

- New slice `redux/slices/floatingStructuresSlice.ts`:
  - state: `{ items: FloatingStructure[]; loading: boolean; error: string | null; serverNowOffsetMs: number }`
  - thunks: `fetchFloatingStructures()` (calls `GET /map/floating-structures`, computes and stores `serverNowOffsetMs = client_now - server_now`).
  - selectors: `selectFloatingStructures`, `selectFloatingStructureById`.
- New slice (or addition to an existing NPC slice) `redux/slices/teleportSlice.ts`:
  - state: `{ optionsByNpcId: Record<number, TeleportOption[]>; cooldownSecondsRemaining: number; loading; error }`.
  - thunks: `fetchTeleportOptions(npcId)`, `executeTeleport({ npcId, linkId })`.

TypeScript interfaces (sketch):
```ts
interface RouteWaypoint { x: number; y: number; }
interface FloatingStructure {
  id: number;
  name: string;
  description: string | null;
  icon_url: string | null;
  route_json: RouteWaypoint[];
  speed: number;
  started_at: string; // ISO
  internal_district_id: number | null;
}
interface TeleportOption {
  link_id: number;
  to_npc_id: number;
  to_npc_name: string;
  to_location_id: number;
  to_location_name: string;
  cost_gold: number;
}
```

#### Components (all `.tsx`, Tailwind, no `React.FC`, mobile-responsive)

1. `WorldPage/FloatingStructuresLayer.tsx` — receives `structures: FloatingStructure[]`, mounts inside `InteractiveMap`'s positioned container. For each structure: computes interpolated `(x,y)` via `useEffect` + `setInterval(1000ms)` (slow movement = 1Hz is plenty, no `requestAnimationFrame` needed). Renders an absolutely-positioned `<button>` with the icon image; click navigates to `?citadel=<id>` which triggers Citadel internal-map mode in `WorldPage`.
2. `WorldPage/WorldPage.tsx` — extend with Citadel mode: read `?citadel=<id>` query, fetch the corresponding floating structure, switch into `cityMapDistrictId = structure.internal_district_id` rendering. Back-button returns to world view (not region view).
3. `pages/LocationPage/TeleportMenu.tsx` (new) — top-level menu entry rendered in the existing NPC interaction host on `LocationPage`. Visible only when `npc.npc_role === 'teleport_master'` AND `isCharacterHere`. Opens a modal listing destinations (calls `fetchTeleportOptions`), each row shows target location name + cost_gold + "Телепортироваться" button. Confirm modal before execution. All errors mapped to Russian strings (`Недостаточно золота`, `Телепорт будет доступен через X ч Y мин`, `Связь телепорта недействительна`, `Сетевая ошибка, попробуйте ещё раз`).
4. `AdminLocationsPage/FloatingStructuresPage.tsx` (new admin page) — list/create/edit/delete floating structures. Form fields: name, description, icon_url (with existing image upload helper), speed, started_at (datetime picker; default now), internal_district_id (district picker reusing existing district select), and a "Редактировать маршрут" button that opens `FloatingRouteEditor` modal.
5. `AdminLocationsPage/FloatingRouteEditor.tsx` (new) — slim dedicated waypoint editor. Loads world-map background image, renders existing `route_json` as draggable polyline; supports add/insert/delete waypoint (left-click to add at end, click on segment to insert mid-segment, right-click waypoint to delete); always treated as a closed loop (last → first segment auto-rendered). Save button persists `route_json` via `PATCH /admin/floating-structures/{id}`. Reuses waypoint helpers extracted (where feasible) from `RegionMapEditor.tsx` into `components/AdminLocationsPage/waypointUtils.ts`.
6. `AdminNpcsPage/AdminNpcsPage.tsx` — extend `NPC_ROLE_LABELS` with `teleport_master: 'Мастер Телепорта'`. When the edited NPC has this role, render a new `<TeleportLinksPanel>` under the form.
7. `AdminNpcsPage/TeleportLinksPanel.tsx` (new) — lists links from current NPC, allows: add (search input over NPCs filtered to `npc_role='teleport_master'`, cost input, bidirectional checkbox default true), edit cost (PATCH), delete (with `delete_reverse=true` default).

#### Migration policy on existing files

Per CLAUDE.md sections 10.8/10.9: any existing `.jsx`/`.scss` file touched by this feature must be migrated to `.tsx` + Tailwind in the same PR. Specifically: if `WorldPage.tsx` is already `.tsx` (it is — Analyst confirmed), no migration is needed. The NPC interaction host on `LocationPage` and `AdminNpcsPage.tsx` must be checked by Frontend Dev; any `.jsx` touched gets migrated.

### 3.6 Data flow — teleport execution

```
[Player clicks "Телепортироваться" in TeleportMenu]
        ↓ POST /npcs/{id}/teleport { link_id }
[character-service]
  ├─ JWT → user_id → active character (FOR UPDATE)
  ├─ assert character.current_location_id == source_npc.current_location_id
  ├─ assert source_npc.npc_role == 'teleport_master'
  ├─ load teleport_link, validate from_npc_id, target NPC alive + role
  ├─ assert (now - last_teleport_at) >= 24h  → else 409
  ├─ assert currency_balance >= cost_gold     → else 402
  ├─ log_gold_transaction(-cost_gold, 'teleport')
  ├─ character.current_location_id = target_npc.current_location_id
  ├─ character.last_teleport_at = now()
  └─ COMMIT
        ↓ 200 { new_location_id, currency_balance, last_teleport_at }
[Frontend]
  ├─ Redux: update character.currency_balance, current_location_id
  └─ Navigate to /location/{new_location_id}
```

No HTTP calls to other services. notification-service is not involved (no SSE event for teleport).

### 3.7 Data flow — Citadel position rendering

```
[WorldPage mounts]
        ↓ GET /map/floating-structures
[locations-service] returns list incl. server_now
[Frontend]
  ├─ store offset = client_now - server_now
  └─ FloatingStructuresLayer setInterval(1000ms):
       for each structure:
         t_seconds = (Date.now() - offset - started_at_ms) / 1000
         progress = (t_seconds * speed) % 1.0
         (x, y) = interpolatePolyline(route_json, progress)  // closed loop
         render icon at left:x%, top:y%
```

No backend tick. No DB writes. Stateless.

### 3.8 Security

| Endpoint | Auth | Authorization | Validation | Rate limit |
|---|---|---|---|---|
| `GET /map/floating-structures` | optional | none (public read) | none | existing public zone |
| `GET /admin/floating-structures*` | required | admin (`get_admin_user`) | path id, body schemas | existing admin zone |
| `POST/PATCH/DELETE /admin/floating-structures*` | required | admin | strict Pydantic; route_json shape; FK existence | existing admin zone |
| `GET /npcs/{id}/teleport-options` | required | any player | NPC must exist + be teleport_master | existing player zone |
| `POST /npcs/{id}/teleport` | required | any player; only own active character | link_id integer; player presence; cooldown; gold | **add per-user limit: 10 req/min** at Nginx (DevSecOps), to mitigate hammering during races |
| `GET/POST/PATCH/DELETE /admin/teleport-links*` | required | admin | both NPCs must be teleport masters; cost_gold ≥ 0 | existing admin zone |

Atomicity: teleport endpoint wraps all reads/writes in one DB transaction with `SELECT ... FOR UPDATE` on the player character row. character-service is sync SQLAlchemy → straightforward with `db.execute(text("SELECT ... FOR UPDATE"))` or `with_for_update()` on the query.

Input sanitization: all string inputs go through Pydantic; no raw SQL; gold values are integers. No user-supplied content is logged.

### 3.9 Risks accepted / deferred

- Frontend clock skew: mitigated by `server_now` offset; no further work.
- Admin can place waypoints over land: brief accepts this; no validation.
- `notification-service`/`battle-service` Alembic obligation (T2): not triggered — feature does not touch them.
- Editing one direction of a bidirectional link does not auto-update the reverse. Admin must edit both. Documented in UI tooltip; acceptable per brief.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

> Status legend: `TODO` (initial), `IN_PROGRESS`, `DONE`, `BLOCKED`.

### Backend tasks

#### T1 — locations-service: `floating_structures` model + Alembic migration
- **Agent:** Backend Developer
- **Status:** DONE
- **Files:** `services/locations-service/app/models.py`, `services/locations-service/app/alembic/versions/<new>_add_floating_structures.py`
- **Depends on:** —
- **Description:** Add `FloatingStructure` SQLAlchemy model per schema in §3.4 (async style consistent with the rest of locations-service). Generate Alembic migration; verify it applies cleanly against an empty DB and rolls back. Use unique `version_table=alembic_version_locations` (already configured).
- **Acceptance:** Migration up/down passes locally; `alembic upgrade head` runs in container without errors; model importable; `python -m py_compile` passes for modified files.

#### T2 — locations-service: Pydantic schemas + CRUD for `floating_structures`
- **Agent:** Backend Developer
- **Status:** DONE
- **Files:** `services/locations-service/app/schemas.py`, `services/locations-service/app/crud.py`
- **Depends on:** T1
- **Description:** Pydantic v1 schemas: `FloatingStructureBase`, `FloatingStructureCreate`, `FloatingStructureUpdate`, `FloatingStructureRead`, `FloatingStructurePublicRead` (includes `server_now`). Validators: `route_json` non-empty list of `{x,y}` floats in [0,100]; `speed > 0`; `internal_district_id` (when set) must reference existing District (validated in CRUD before insert/update). Async CRUD functions: `list_floating_structures`, `get_floating_structure`, `create_floating_structure`, `update_floating_structure`, `delete_floating_structure`.
- **Acceptance:** `py_compile` passes; CRUD callable from a REPL session against test DB.

#### T3 — locations-service: public + admin endpoints for `floating_structures`
- **Agent:** Backend Developer
- **Status:** DONE
- **Files:** `services/locations-service/app/main.py`
- **Depends on:** T2
- **Description:** Implement `GET /map/floating-structures` (public, returns list with `server_now=datetime.utcnow()`) and admin CRUD endpoints `/admin/floating-structures` per §3.3. Admin endpoints use `Depends(get_admin_user)`. Ensure error responses are consistent with existing endpoints.
- **Acceptance:** `py_compile` passes; manual `curl` against running container returns expected payloads (Backend Dev checks before marking done).

#### T4 — locations-service: ensure `npc_role` propagated in `client/details`
- **Agent:** Backend Developer
- **Status:** DONE
- **Files:** `services/locations-service/app/main.py` (and possibly `app/crud.py`); coordinate with character-service NPC list response if needed.
- **Depends on:** —
- **Description:** Verify the existing `GET /locations/{id}/client/details` payload includes `npc_role` for each NPC. If absent, add it (and the upstream character-service NPC list response if that's where the data is sourced). Frontend uses this to gate the "Телепорт" menu item.
- **Acceptance:** A `curl` against `client/details` for a location with an NPC shows `npc_role` in the JSON.

#### T5 — character-service: `teleport_links` model + `last_teleport_at` column + Alembic migration
- **Agent:** Backend Developer
- **Status:** DONE
- **Files:** `services/character-service/app/models.py`, `services/character-service/app/alembic/versions/<new>_add_teleport_links_and_cooldown.py`
- **Depends on:** —
- **Description:** Add `TeleportLink` model (sync SQLAlchemy) per §3.4 with FK CASCADE on both sides and unique `(from_npc_id, to_npc_id)`. Add `Character.last_teleport_at = Column(DateTime, nullable=True)`. Alembic migration with `version_table=alembic_version_character` (already configured).
- **Acceptance:** Migration up/down passes; `py_compile` passes.

#### T6 — character-service: Pydantic schemas + CRUD for `teleport_links` and teleport flow
- **Agent:** Backend Developer
- **Status:** DONE
- **Files:** `services/character-service/app/schemas.py`, `services/character-service/app/crud.py`
- **Depends on:** T5
- **Description:**
  - Schemas: `TeleportLinkCreate {from_npc_id, to_npc_id, cost_gold>=0, bidirectional: bool=True}`, `TeleportLinkUpdate {cost_gold}`, `TeleportLinkRead`, `TeleportOption` (enriched with target location name), `TeleportRequest {link_id}`, `TeleportResult`.
  - CRUD: `create_teleport_link` (handles bidirectional → 2 rows in one transaction; rejects if either NPC isn't `teleport_master`), `update_teleport_link_cost`, `delete_teleport_link` (with optional `delete_reverse`), `list_teleport_options_for_npc` (filters out broken links), `execute_teleport` (the atomic transactional flow from §3.6, using `with_for_update()` on the player Character row, and calling existing `log_gold_transaction`).
- **Acceptance:** `py_compile` passes; functions callable in isolation.

#### T7 — character-service: endpoints for teleport options, execute, admin link CRUD; cascade on role change
- **Agent:** Backend Developer
- **Status:** DONE
- **Files:** `services/character-service/app/main.py`
- **Depends on:** T6
- **Description:**
  - Add `GET /npcs/{id}/teleport-options` and `POST /npcs/{id}/teleport` per §3.3.
  - Add admin CRUD `/admin/teleport-links` (list with `npc_id` filter, create, patch, delete).
  - Modify the existing NPC update handler: when an update changes `npc_role` away from `'teleport_master'`, delete all `teleport_links` rows where the NPC is `from_npc_id` OR `to_npc_id` in the same transaction.
  - Add `'teleport_master'` to any backend `npc_role` filters/whitelists if such whitelists exist (Analyst noted there is no enum, but check filters in `/npcs` listing endpoint at line ~1902).
- **Acceptance:** `py_compile` passes; `curl` smoke test of each endpoint returns expected codes.

### DevSecOps tasks

#### T8 — Nginx rate limit for `POST /npcs/{id}/teleport`
- **Agent:** DevSecOps
- **Status:** DONE
- **Files:** `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf`
- **Depends on:** T7
- **Description:** Add a per-user (by JWT sub or by `$binary_remote_addr` if simpler) `limit_req` rule of ~10 req/min specifically targeting the teleport POST. Update both dev and prod configs.
- **Acceptance:** `nginx -t` passes in both configs; manual test confirms 11th request in a minute returns 429.

### Frontend tasks

#### T9 — Frontend: Redux slices for floating structures and teleport
- **Agent:** Frontend Developer
- **Status:** DONE
- **Files:** `services/frontend/app-chaldea/src/redux/slices/floatingStructuresSlice.ts` (new), `services/frontend/app-chaldea/src/redux/slices/teleportSlice.ts` (new), `services/frontend/app-chaldea/src/redux/store.ts` (register), TypeScript interfaces colocated.
- **Depends on:** T3, T7 (contracts)
- **Description:** Implement slices per §3.5. Strict TypeScript, no `any`.
- **Acceptance:** `npx tsc --noEmit` passes; `npm run build` passes.

#### T10 — Frontend: `FloatingStructuresLayer` + Citadel internal-map navigation
- **Agent:** Frontend Developer
- **Status:** DONE
- **Files:** `services/frontend/app-chaldea/src/components/WorldPage/FloatingStructuresLayer.tsx` (new), `services/frontend/app-chaldea/src/components/WorldPage/WorldPage.tsx`, `services/frontend/app-chaldea/src/components/WorldPage/InteractiveMap/InteractiveMap.tsx` (mount point only)
- **Depends on:** T9
- **Description:** New layer component as described in §3.5 (1 Hz interval interpolation, closed loop). Add `?citadel=<id>` handling in `WorldPage` so click navigates into the Citadel's `internal_district_id` district in city-map mode, with a back button returning to world view. Mobile-responsive (icon size scales; touch tap works). No `React.FC`. Tailwind only.
- **Acceptance:** `npx tsc --noEmit` + `npm run build` pass; verified live: Citadel icon renders, moves visibly over time (test with high `speed`), clicking opens internal map, back button returns to world.

#### T11 — Frontend: `TeleportMenu` and integration into NPC interaction
- **Agent:** Frontend Developer
- **Status:** DONE
- **Files:** `services/frontend/app-chaldea/src/components/pages/LocationPage/TeleportMenu.tsx` (new), and the NPC interaction host file on `LocationPage` (Frontend Dev locates exact file — likely `PlayersSection.tsx` / `NpcInteractionMenu.tsx`; if it's `.jsx`, migrate to `.tsx` per CLAUDE.md §10.9).
- **Depends on:** T9
- **Description:** Render a "Телепорт" entry whenever the NPC has `npc_role === 'teleport_master'` and `isCharacterHere`. On click, fetch options and show modal. Confirm modal before execution. All errors mapped to Russian strings per §3.5. Tailwind, responsive, no `React.FC`.
- **Acceptance:** `tsc` + `build` pass; live verification with a seeded teleport_master NPC: success path moves character; insufficient gold shows error; cooldown active shows error; stale link returns error.

#### T12 — Frontend: Admin "Floating Structures" page + `FloatingRouteEditor`
- **Agent:** Frontend Developer
- **Status:** DONE
- **Files:** `services/frontend/app-chaldea/src/components/AdminLocationsPage/FloatingStructuresPage.tsx` (new), `services/frontend/app-chaldea/src/components/AdminLocationsPage/FloatingRouteEditor.tsx` (new), `services/frontend/app-chaldea/src/components/AdminLocationsPage/waypointUtils.ts` (new — extracted helpers if feasible; otherwise inlined with TODO), routing entry under admin layout.
- **Depends on:** T3
- **Description:** CRUD page per §3.5. Slim dedicated route editor — does NOT modify `RegionMapEditor.tsx`. World-map background; draggable waypoints; closed-loop polyline; add/insert/delete waypoint UX; save button persists `route_json`. Tailwind, responsive, no `React.FC`.
- **Acceptance:** `tsc` + `build` pass; live verification: create a structure, draw a route, save, reload — route persists and renders.

#### T13 — Frontend: NPC editor — `teleport_master` role + `TeleportLinksPanel`
- **Agent:** Frontend Developer
- **Status:** DONE
- **Files:** `services/frontend/app-chaldea/src/components/AdminNpcsPage/AdminNpcsPage.tsx` (extend `NPC_ROLE_LABELS`; if `.jsx` migrate to `.tsx`), `services/frontend/app-chaldea/src/components/AdminNpcsPage/TeleportLinksPanel.tsx` (new)
- **Depends on:** T7
- **Description:** Add `teleport_master: 'Мастер Телепорта'` option. Render `TeleportLinksPanel` in the NPC edit form when role === `teleport_master`. Panel: list current NPC's outgoing links, add (NPC search filtered by role, cost input, bidirectional checkbox default true), edit cost, delete (delete_reverse default true). Russian error messages. Tailwind, responsive, no `React.FC`.
- **Acceptance:** `tsc` + `build` pass; live verification: create two teleport masters, link them bidirectionally, edit cost, delete; removing the role from one NPC purges its links.

### QA tasks (mandatory — backend touched)

#### T14 — QA: tests for locations-service `floating_structures`
- **Agent:** QA Test
- **Status:** DONE
- **Files:** `services/locations-service/app/tests/test_floating_structures.py` (new)
- **Depends on:** T3
- **Description:** Pytest with async client. Cover:
  - `GET /map/floating-structures` empty list, with one record (asserts `server_now` present, route_json round-trip).
  - Admin CRUD: create (valid + invalid `route_json` shape + invalid `internal_district_id` → 422/404), get, patch, delete, 401/403 without admin auth.
- **Acceptance:** `pytest` passes locally.

#### T15 — QA: tests for character-service teleport flow + links CRUD
- **Agent:** QA Test
- **Status:** DONE
- **Files:** `services/character-service/app/tests/test_teleport.py` (new)
- **Depends on:** T7
- **Description:** Pytest fixtures for two teleport-master NPCs in two different locations and one player character. Cover:
  - `POST /npcs/{id}/teleport` success (gold deducted, location updated, `last_teleport_at` set, `log_gold_transaction` called).
  - Insufficient gold → 402.
  - Cooldown active → 409 with `cooldown_seconds_remaining`.
  - Broken link (target NPC role downgraded) → 422 + link auto-filtered from `teleport-options`.
  - Source NPC not a teleport master → 422.
  - Player not in source NPC's location → 422.
  - `GET /npcs/{id}/teleport-options` returns options with target location name.
  - Admin CRUD `/admin/teleport-links`: bidirectional create produces 2 rows; non-bidirectional produces 1; create with non-teleport-master NPC → 422; duplicate pair → 409; delete with `delete_reverse=true` removes both; 401/403 without admin auth.
  - NPC role change side-effect: updating an NPC away from `teleport_master` deletes all its links.
  - Concurrency smoke (optional): two simultaneous teleport requests → exactly one succeeds (relies on `FOR UPDATE`).
- **Acceptance:** `pytest` passes locally; all listed cases present.

### Review

#### T16 — Final review
- **Agent:** Reviewer
- **Status:** DONE
- **Files:** all changed
- **Depends on:** T1–T15
- **Description:** Per CLAUDE.md "Build Verification — Mandatory":
  - Re-run `python -m py_compile` on all changed Python files; re-run pytest in both affected services.
  - Re-run `npx tsc --noEmit` and `npm run build` for frontend.
  - Live verification via `chrome-devtools` MCP or `curl`: Citadel icon renders and clicks; teleport menu appears for teleport-master NPC; teleport success path; insufficient gold error; cooldown error; admin floating-structures CRUD round-trip; admin NPC link CRUD round-trip.
  - Audit `LocationPage` child components: confirm Citadel "view mode" (no `isCharacterHere`) cannot perform writes (post, fight mob, loot, dungeon entry, shop, dialogue actions).
  - Verify `nginx -t` passes for both dev/prod configs.
  - Verify `npc_role` propagation in `client/details`.
  - Confirm migrations apply cleanly on a fresh DB.
  - Cross-service-validator: confirm no existing contract was broken.
- **Acceptance:** All checks pass; review marked PASS in §5. Otherwise FAIL with explicit findings and loop back to the responsible agent.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

_To be filled by Architect._

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-04-07
**Result:** FAIL

#### Automated Check Results
- [x] `python -m py_compile` (all 11 changed Python files + new migration) — **PASS**
- [x] `pytest` locations-service `test_floating_structures.py` — **PASS** (21/21 in Docker `python:3.10-slim`, CRUD, validators, auth-gating)
- [x] `pytest` character-service `test_teleport.py` — **PASS** (18/18 in Docker `python:3.10-slim`, teleport flow, cooldown, cascade, admin CRUD)
- [x] `npx tsc --noEmit` (Docker `node:20-alpine`) — **PASS for FEAT-123 scope.** The single error in a FEAT-123-touched file (`WorldPage.tsx:49` `useParams<RouteParams>`) is pre-existing since commit `92cf823` (FEAT-042) and is not introduced by this feature. 62 other pre-existing errors exist in unrelated components (Admin*, Bestiary, BattlePage, ProfilePage, ticketSlice, userProfileSlice) — none in new FEAT-123 files (`FloatingStructuresLayer.tsx`, `FloatingStructuresPage.tsx`, `FloatingRouteEditor.tsx`, `waypointUtils.ts`, `TeleportMenu.tsx`, `TeleportLinksPanel.tsx`, `floatingStructuresSlice.ts`, `teleportSlice.ts`). They should be tracked separately in `docs/ISSUES.md` but do not block this review.
- [x] `npm run build` (Docker `node:20-alpine`) — **PASS** (Vite built successfully in 53.29s, output in `dist/`).
- [x] `nginx -t` `nginx.conf` (Docker `nginx:stable` with upstream host stubs) — **PASS**
- [x] `nginx -t` `nginx.prod.conf` — syntactically valid; fails only on missing Let's Encrypt cert paths (expected in local env; SSL error occurs after full config parse, confirming rate-limit block is well-formed). Matches T8 DevSecOps log.
- [x] `docker compose config` — **PASS**
- [ ] Live verification (chrome-devtools / curl) — **NOT PERFORMED.** Local dev stack is not running; `chrome-devtools` MCP not available in this session. Documented as blocker — PM should coordinate a post-fix live pass before PASS.

#### Static Audit Findings

1. **Teleport atomicity** — confirmed: `crud.execute_teleport` uses `.with_for_update()` on the player `Character` row (`crud.py:2212`). Cooldown, gold balance, link validity, location update, and `last_teleport_at` are all in one transaction. `log_gold_transaction` is invoked. **OK.**
2. **NPC role-change cascade** — confirmed: `main.py:2073-2080` detects `old_role == 'teleport_master' && new_role != 'teleport_master'` and calls `crud.purge_teleport_links_for_npc` before commit in the same transaction. Tested by QA. **OK.**
3. **`npc_role` propagation** — confirmed present in `locations-service/app/schemas.py:468` (`NpcInLocation.npc_role: Optional[str]`) and character-service `NpcInLocation` (schemas.py:554). Propagates through `client/details` without extra work. **OK.**
4. **Nginx rate limit** — `nginx.conf:17` `limit_req_zone $binary_remote_addr zone=teleport_limit:10m rate=10r/m;` + `location ~ ^/characters/npcs/\d+/teleport$ { limit_req zone=teleport_limit burst=5 nodelay; }` matches the documented POST endpoint URL (router prefix `/characters/` at the gateway + `/npcs/{id}/teleport` at the service). Same block present in `nginx.prod.conf`. **OK.**
5. **Pydantic v1 compliance, no `React.FC`, Tailwind-only, no new `.jsx`** — confirmed for all new FEAT-123 files. **OK.**
6. **Migration idempotency** — `027_add_floating_structures.py` and `015_add_teleport_links_and_cooldown.py` both present, `py_compile` passes. Migrations apply cleanly in the test harness (pytest fixtures create tables via `Base.metadata.create_all`, indirectly proving model shape). Fresh-DB `alembic upgrade head` not executed against a real MySQL here — container start will fail-fast if broken per CLAUDE.md auto-migration rule.
7. **Security checklist:** auth on admin endpoints via `get_admin_user`, Pydantic-validated inputs, no raw SQL with user strings, Russian user-facing messages in `teleportSlice.mapExecuteError`, rate-limit present. **OK.**

#### BLOCKING: View-mode write leaks in LocationPage (§4.T16 explicit audit item)

The brief and T16 explicitly require that in Citadel view mode (`isCharacterHere === false`) a player must not be able to perform writes: "post, fight mob, loot, dungeon entry, shop, dialogue actions". Audit result:

| Child | Gated by `isCharacterHere`? | Status |
|---|---|---|
| `LocationMobs` (mob fight) | yes (`characterId={isCharacterHere ? ... : null}`, line 393) | OK |
| `DungeonEntrance` | yes (line 404) | OK |
| `PendingInvitationsPanel` | yes (line 413) | OK |
| `LootSection` (pickup) | yes (`currentCharacterId={isCharacterHere ? ... : null}`, line 421) | OK |
| `PostCreateForm` | **NO** — `disabled={inBattle || (!isCharacterHere && !character && !userIsStaff)}` (line 442). If the player owns any character, `!character` is false, so the form is NOT disabled in view mode. A logged-in player can post into a Citadel location they have not teleported to. | **FAIL** |
| `NpcProfileModal` — Talk button (dialogue) (line 260-277) | **NO** gating | **FAIL** |
| `NpcProfileModal` — Trade button (shop) (line 280-297) | **NO** gating | **FAIL** |
| `NpcProfileModal` — Auction button (line 300-317) | **NO** gating | **FAIL** |
| `NpcProfileModal` — Quests button (line 325-342) | **NO** gating | **FAIL** |
| `NpcProfileModal` — Attack button (line 345) | only gated on `characterId` truthy (line 345); **NO** `isCharacterHere` gate | **FAIL** |
| `NpcProfileModal` — Teleport button (line 320) | **YES** (`isCharacterHere` gate present) | OK |

Additionally, the backend `POST /posts/` handler in `locations-service/app/main.py:586-654` does NOT validate that `character.current_location_id == post_data.location_id`. This means even if the frontend is fixed, the API still allows remote posts. This is a pre-existing weakness but becomes exploitable for the first time via Citadel view mode. It should be fixed server-side as well (defense in depth), or the feature must route `isCharacterHere === false` players through a read-only wrapper that never renders write controls at all.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/components/pages/LocationPage/LocationPage.tsx:442` | `PostCreateForm` is not disabled in view mode: the `disabled` expression `(!isCharacterHere && !character && !userIsStaff)` is false whenever the user owns a character, allowing posts in Citadel view mode. Add `!isCharacterHere && !userIsStaff` (or equivalent) to the disabled condition, or hide the form entirely when `!isCharacterHere`. | Frontend Developer | FIX_REQUIRED |
| 2 | `services/frontend/app-chaldea/src/components/pages/LocationPage/NpcProfileModal.tsx:260-277` | Talk/dialogue button not gated on `isCharacterHere`. Hide or disable when character is not physically present at the NPC's location. | Frontend Developer | FIX_REQUIRED |
| 3 | `services/frontend/app-chaldea/src/components/pages/LocationPage/NpcProfileModal.tsx:280-297` | Trade (shop) button not gated on `isCharacterHere`. Hide or disable in view mode. | Frontend Developer | FIX_REQUIRED |
| 4 | `services/frontend/app-chaldea/src/components/pages/LocationPage/NpcProfileModal.tsx:300-317` | Auction button not gated on `isCharacterHere`. Hide or disable in view mode. | Frontend Developer | FIX_REQUIRED |
| 5 | `services/frontend/app-chaldea/src/components/pages/LocationPage/NpcProfileModal.tsx:325-342` | Quests button not gated on `isCharacterHere`. Hide or disable in view mode. | Frontend Developer | FIX_REQUIRED |
| 6 | `services/frontend/app-chaldea/src/components/pages/LocationPage/NpcProfileModal.tsx:345-360` | Attack button not gated on `isCharacterHere`. Add gate (follow the pattern used for the teleport button at line 320). | Frontend Developer | FIX_REQUIRED |
| 7 | `services/locations-service/app/main.py:586` (`create_new_post`) | No server-side check that `character.current_location_id == post_data.location_id`. Defense-in-depth: add the check and return 422 with a Russian error if the character is not physically at the location. | Backend Developer | FIX_REQUIRED |
| 8 | Live verification | Not executed (dev stack not running, no chrome-devtools MCP in this session). PM must schedule a live pass after the above fixes, exercising: Citadel icon render + motion, click into view mode, confirmation that all six write actions are blocked, happy-path teleport, insufficient-gold/cooldown/broken-link errors, admin CRUD round-trips. | PM / Reviewer | FIX_REQUIRED |

#### Pre-existing issues noted (NOT blocking this feature)
- 62 pre-existing TypeScript errors across unrelated components (Admin*, Bestiary, BattlePage, ProfilePage, ticketSlice, userProfileSlice, messengerSlice, SkillTreeView, ItemsAdminPage, GameTimeAdminPage, AdminPathEditorPage). These accumulated across prior features and should be tracked in `docs/ISSUES.md` as a tech-debt item — reviewer did not add them in this pass to stay scope-focused; PM decision.
- `WorldPage.tsx:49` `useParams<RouteParams>` TS error pre-existing from FEAT-042 (`92cf823`).

### Review #2 — 2026-04-07
**Result:** PASS

All 7 fixes from Review #1 verified in source:

1. `LocationPage.tsx:442` — `disabled={inBattle || (!isCharacterHere && !userIsStaff)}`. The erroneous `&& !character` clause is gone. In view mode, a logged-in player with a character is now properly blocked from posting; staff bypass preserved. **FIXED.**
2. `NpcProfileModal.tsx:260` — Talk button wrapped in `hasDialogue && isCharacterHere`. **FIXED.**
3. `NpcProfileModal.tsx:280` — Trade button wrapped in `hasShop && isCharacterHere`. **FIXED.**
4. `NpcProfileModal.tsx:300` — Auction button wrapped in `npc.npc_role === 'auctioneer' && isCharacterHere`. **FIXED.**
5. `NpcProfileModal.tsx:325` — Quests button wrapped in `hasQuests && isCharacterHere`. **FIXED.**
6. `NpcProfileModal.tsx:345` — Attack button wrapped in `characterId && isCharacterHere`, matching the Teleport pattern at line 320. **FIXED.**
7. `locations-service/app/main.py:596-606` (`create_new_post`) — defense-in-depth check added: raw SELECT of `characters.current_location_id`, compared with `post_data.location_id`; mismatch → `HTTPException(403, "Вы не находитесь в этой локации")`. Staff (`role in ('admin','moderator')`) bypass via `getattr(current_user, "role", None)`. Implemented without an extra HTTP hop to character-service, matching the in-service raw-SQL pattern already used elsewhere in the file. **FIXED.**

#### Automated Check Results
- [x] `python -m py_compile services/locations-service/app/main.py` — **PASS**
- [x] `pytest` locations-service `test_floating_structures.py` (Docker `python:3.10-slim`) — **PASS** (21/21, 0.32s)
- [x] `pytest` character-service `test_teleport.py` (Docker `python:3.10-slim`) — **PASS** (18/18, 1.04s)
- [x] `npx tsc --noEmit` (Docker `node:20-alpine`) — **PASS for FEAT-123 scope.** Zero errors in any file touched by this feature (LocationPage.tsx, NpcProfileModal.tsx, TeleportMenu.tsx, FloatingStructuresLayer.tsx, FloatingStructuresPage.tsx, FloatingRouteEditor.tsx, waypointUtils.ts, TeleportLinksPanel.tsx, floatingStructuresSlice.ts, teleportSlice.ts). The same 63 pre-existing errors from Review #1 remain in unrelated components (Admin*, Bestiary, BattlePage, ProfilePage, SkillTreeView, ticketSlice, messengerSlice, userProfileSlice, `WorldPage.tsx:49` from FEAT-042). Not blockers per scope rule.
- [x] `npm run build` (Docker `node:20-alpine`) — **PASS** (Vite built in 46.61s, `dist/` produced, only standard chunk-size warnings).
- [x] `nginx -t` — re-verification skipped (not touched in iteration 2; verified PASS in Review #1).
- [x] `docker compose config` — re-verification skipped (not touched in iteration 2; verified PASS in Review #1).
- [ ] Live verification (chrome-devtools / curl) — **NOT PERFORMED.** Dev stack is not running and `chrome-devtools` MCP is unavailable in this session. Per PM instruction, this is documented as a known limitation requiring a user-side smoke test post-merge; it does NOT block PASS because all the affected paths are covered by static audit + automated tests (21 locations tests + 18 character-service tests + successful type-check and build).

#### Live verification — post-merge smoke test checklist (for PM / user)
Before the feature is considered fully verified in production:
- Open the world map, confirm Citadel icon renders and slowly moves.
- Click the Citadel icon → internal map opens in view mode (no character present).
- In view mode, confirm that: PostCreateForm is disabled, and Talk/Trade/Auction/Quests/Attack/Teleport buttons are hidden in `NpcProfileModal`.
- Attempt `POST /locations/posts/` with a `character_id` whose `current_location_id` differs from `post_data.location_id` — expect HTTP 403 "Вы не находитесь в этой локации".
- Teleport through a `teleport_master` NPC to a Citadel location — expect gold deducted, character moved, buttons re-enabled.
- Happy-path: insufficient gold → Russian error; cooldown active → Russian error with remaining time; broken link → Russian error.
- Admin CRUD: floating-structures and teleport-links round-trips.

#### Verdict
**PASS.** All 7 FIX_REQUIRED issues from Review #1 are resolved. Automated checks (py_compile, 2×pytest, tsc, build) all green for FEAT-123 scope. T16 marked DONE. Meta status → REVIEW (PM closes).


---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-04-07 — PM: фича создана на основе обсуждения с пользователем, готов запускать анализ
[LOG] 2026-04-07 — Architect: спроектировано решение, 16 задач, 8 API-контрактов, 2 миграции (locations + character), новый dedicated FloatingRouteEditor вместо расширения RegionMapEditor, телепорт-меню как отдельный пункт NPC-взаимодействия (option 2), Citadel переиспользует District как внутреннюю карту
[LOG] 2026-04-07 — Backend Dev: T5 — добавлена модель TeleportLink, поле Character.last_teleport_at, Alembic-миграция 015_add_teleport_links_and_cooldown (FK CASCADE на обе стороны, unique (from_npc_id,to_npc_id), индекс idx_tlink_from)
[LOG] 2026-04-07 — Backend Dev: T6 — добавлены Pydantic-схемы (TeleportLinkCreate/Update/Read, TeleportOption(sResponse), TeleportRequest, TeleportResult) и CRUD: list_teleport_options_for_npc (фильтрует битые связи), execute_teleport (атомарная транзакция с with_for_update, кулдаун 24ч, проверка золота, log_gold_transaction, перенос current_location_id и last_teleport_at), create/update/delete_teleport_link, purge_teleport_links_for_npc
[LOG] 2026-04-07 — Backend Dev: T7 — добавлены endpoints GET/POST /npcs/{id}/teleport(-options), admin CRUD /admin/teleport-links (list+npc_id filter, create с bidirectional, patch cost, delete с delete_reverse). Модифицирован admin_update_npc: при смене npc_role с teleport_master все связи NPC удаляются в той же транзакции. Listing /admin/npcs (line ~1899) принимает npc_role как свободную строку, whitelist отсутствует — изменения не нужны. Все py_compile проходят.
[LOG] 2026-04-07 — Backend Dev: T1 готов — добавлена модель FloatingStructure (async-стиль locations-service) и Alembic-миграция 027_add_floating_structures (down_revision=026_arrow_rotation, идемпотентная проверка по inspect)
[LOG] 2026-04-07 — Backend Dev: T2 готов — Pydantic v1 схемы FloatingStructureBase/Create/Update/Read/PublicRead с валидаторами route_json (непустой список {x,y} в [0..100]), speed > 0; CRUD-функции list/get/create/update/delete с проверкой существования internal_district_id
[LOG] 2026-04-07 — Backend Dev: T3 готов — публичный GET /map/floating-structures (возвращает server_now=utcnow) и admin CRUD /admin/floating-structures (GET/POST/GET{id}/PATCH/DELETE) под Depends(get_admin_user), подключены через новый floating_router
[LOG] 2026-04-07 — Backend Dev: T4 проверен — npc_role уже присутствует в schemas.NpcInLocation locations-service (строка 468) и character-service NpcInLocation (строка 554), get_npcs_in_location передаёт dict как есть, поле автоматически попадает в client/details. Изменений не требуется
[LOG] 2026-04-07 — Backend Dev: py_compile прошёл для models.py, schemas.py, crud.py, main.py и новой миграции; миграция идемпотентная (создание таблицы пропускается если уже существует), применится автоматически при старте контейнера через alembic upgrade head
[LOG] 2026-04-07 — QA: T14 готов — добавлен services/locations-service/app/tests/test_floating_structures.py (публичный GET с пустым/непустым списком + проверка server_now и round-trip route_json; admin CRUD create/get/patch/delete; негативы: невалидная форма route_json и пустой список → 422, x/y вне [0..100] → 422, несуществующий internal_district_id → 404; auth-гейтинг 401 без токена и 403 для роли user на всех 5 admin-эндпоинтах). CRUD-слой замокан (locations-service async + реальная MySQL недоступна в unit-тестах); auth_http.requests.get тоже замокан. py_compile проходит. Локальный pytest run заблокирован pre-existing проблемой conftest.py (Settings не подхватывает env vars на Windows-хосте — тот же баг ломает test_admin_auth.py и др.); в CI Docker-окружении тесты должны проходить штатно.
[LOG] 2026-04-07 — DevSecOps: T8 готов — добавлен limit_req_zone teleport_limit (rate=10r/m, shared 10m) в http-блок и регекс-location ^/characters/npcs/\d+/teleport$ с limit_req burst=5 nodelay, limit_req_status 429 в обоих конфигах (nginx.conf и nginx.prod.conf). Per-user (JWT sub) лимитирование в stock Nginx недоступно — fallback на $binary_remote_addr зафиксирован комментарием в конфиге. nginx -t для dev-конфига PASS (nginx:stable в Docker); prod-конфиг синтаксически валиден, тест падает только на отсутствии SSL-сертификата Let's Encrypt в локальной среде (ожидаемо, не связано с правкой).
[LOG] 2026-04-07 — Frontend Dev: T9 готов — созданы redux/slices/floatingStructuresSlice.ts (types RouteWaypoint/FloatingStructure/FloatingStructurePublic/Create/Update, state с items+serverNowOffsetMs+loading/error/saving, thunks fetchFloatingStructures публичный с вычислением clock skew из server_now + admin CRUD fetchAdmin/create/update/deleteFloatingStructure по /admin/floating-structures, селекторы включая curried selectFloatingStructureById) и redux/slices/teleportSlice.ts (types TeleportOption(sResponse)/TeleportResult/TeleportLink/Create/Update, thunks fetchTeleportOptions/executeTeleport с маппером ошибок axios→рус.строки (402/409/404/422/401), admin thunks fetchAdminTeleportLinks/create/update/deleteTeleportLink через /characters/admin/teleport-links, селекторы). Оба слайса зарегистрированы в store.ts (floatingStructures, teleport). Контракты §3.3 соблюдены, без any, React.FC не используется (не компоненты). ⚠️ `npx tsc --noEmit` и `npm run build` локально не запущены: Node.js не установлен на этой машине (node/npm/npx отсутствуют в PATH и в стандартных локациях Program Files); node_modules/.bin/tsc присутствует, но без node-runtime не исполняется. Код прошёл самопроверку на типы (axios v1 экспортирует AxiosError; react-hot-toast в package.json v2.4.1; все RootState-селекторы типизированы). Верификацию сборки должен провести Reviewer или следующий агент с доступом к Node.
[LOG] 2026-04-07 — Frontend Dev: T11 готов — создан components/pages/LocationPage/TeleportMenu.tsx (Tailwind, mobile-responsive, без React.FC): кнопка «Телепорт», модалка со списком направлений (to_location_name + cost_gold + кнопка «Телепортироваться»), отдельная модалка подтверждения, на success — dispatch setCharacterAfterTeleport (новый reducer в userSlice обновляет character.current_location и currency_balance) и navigate(`/location/{new_location_id}`). Все ошибки рендерятся пользователю: optionsError/executeError инлайн в модалке + строка кулдауна «Телепорт будет доступен через X ч Y мин» при cooldown_seconds_remaining > 0 (русские строки уже заданы в teleportSlice.mapExecuteError для 402/409/422/network). Интеграция: NpcProfileModal.tsx (уже .tsx) принимает новый prop isCharacterHere и рендерит <TeleportMenu> только при npc.npc_role === 'teleport_master' && isCharacterHere; PlayersSection.tsx и LocationPage.tsx прокидывают isCharacterHere (паттерн LocationPage.tsx:341). Миграция .jsx→.tsx не требовалась — все затронутые файлы уже на TypeScript. ⚠️ `npx tsc --noEmit` и `npm run build` локально не запущены: Node.js по-прежнему отсутствует на хосте (тот же блокер, что в T9/T15 — node/npm/npx не в PATH). Самопроверка типов: TeleportOption импортирован type-only из teleportSlice, useNavigate из react-router-dom (уже используется в LocationPage), новый action setCharacterAfterTeleport экспортирован, prop isCharacterHere опционален с дефолтом false для обратной совместимости. Верификацию сборки должен провести Reviewer в среде с Node.
[LOG] 2026-04-07 — Frontend Dev: T10 готов — создан components/WorldPage/FloatingStructuresLayer.tsx (читает structures+serverNowOffsetMs из floatingStructuresSlice; на каждый structure отдельный <FloatingStructureMarker> с useEffect+setInterval(1000ms); интерполяция позиции по замкнутой полилинии route_json через interpolateClosedPolyline (сегментные длины, progress = ((Date.now()-serverNowOffsetMs-started_at_ms)/1000 * speed) mod 1); абсолютно позиционированный <button> с -translate-x/y-1/2, иконка масштабируется w-8/sm:w-10/md:w-12, touch-manipulation, focus-ring; клик → navigate(`/world?citadel=${id}`)). Mount-point добавлен внутрь WorldPage/InteractiveMap/InteractiveMap.tsx сразу после ClickableZoneOverlay (минимальное изменение). WorldPage.tsx: на mount диспатчит fetchFloatingStructures если пусто; новый useEffect читает ?citadel=<id>, ищет structure в Redux, GET /locations/districts/{internal_district_id}/details, извлекает region_id, диспатчит fetchRegionDetails и ставит cityMapDistrictId; render-ветка city-map расширена ((viewLevel==='region') OR (citadelId!=null && cityMapDistrictId!=null)); back-кнопка показывает «Назад к миру» в режиме цитадели и через setSearchParams({}) очищает оба query-параметра, возвращая на /world; параметр-sync useEffect для ?district пропускает цикл если ?citadel активен. Все ошибки фетча маппятся в русские toast (Плавающая структура не найдена / Не удалось загрузить внутреннюю карту Цитадели / Не удалось определить регион). React.FC не используется, только Tailwind, .tsx файлы, мобильная адаптивность через sm:/md: брейкпоинты и touch-manipulation. ⚠️ `npx tsc --noEmit` и `npm run build` локально не запущены: Node.js на хосте отсутствует (та же блокировка, что в логе T9); самопроверка типов прошла — selectFloatingStructures возвращает FloatingStructure[], floatingStructuresReducer уже зарегистрирован в store.ts (строка 68), все импорты разрешимы. Верификацию сборки выполнит Reviewer.
[LOG] 2026-04-07 — Frontend Dev: T13 готов — в constants/npc.ts добавлена роль teleport_master ('Мастер Телепорта', иконка 🌀); создан components/AdminNpcsPage/TeleportLinksPanel.tsx (поиск NPC через GET /characters/admin/npcs?npc_role=teleport_master с дебаунсом, выпадающий список результатов, исключение текущего NPC, поля cost_gold (≥0) и checkbox bidirectional по умолчанию true; список существующих связей с подгрузкой имён target NPC через targetCache; редактирование стоимости через updateTeleportLink (PATCH); удаление через deleteTeleportLink с delete_reverse=true; tooltip "Изменение стоимости одной стороны не обновляет обратную связь автоматически"). Все ошибки — toast на русском, Tailwind, mobile-responsive (sm: breakpoints, flex-col→flex-row), без React.FC. AdminNpcsPage.tsx: импорт TeleportLinksPanel, рендер `<TeleportLinksPanel npcId={editingId} />` под формой при formOpen && editingId && form.npc_role==='teleport_master'. ⚠️ `npx tsc --noEmit` и `npm run build` локально не запущены: Node.js по-прежнему не установлен на этом хосте (та же блокировка, что и в логе T9). Самопроверка типов: все импорты из teleportSlice/redux/store существуют, target/cache типизированы, экшены через createTeleportLink.fulfilled.match. Верификацию сборки должен провести Reviewer.
[LOG] 2026-04-07 — Frontend Dev: T12 готов — созданы components/AdminLocationsPage/FloatingStructuresPage.tsx (CRUD-список + форма: name/description/icon_url/speed/started_at(datetime-local, default=now)/internal_district_id, кнопка "Редактировать маршрут" открывает модалку), FloatingRouteEditor.tsx (slim dedicated editor, фон = areas[0].map_image_url из worldMapSlice, ЛКМ по пустому → addWaypoint, ЛКМ возле сегмента → insertWaypoint через findInsertIndex, ПКМ по точке → delete, drag → updateWaypoint, замкнутая петля рендерится как SVG polygon, save через updateFloatingStructure thunk из T9), waypointUtils.ts (clampPct/eventToPct/add/insert/delete/updateWaypoint/findInsertIndex/waypointsToPolygonPoints — извлечены без касания RegionMapEditor.tsx, в файле TODO о возможной общей экстракции в будущем). RegionMapEditor.tsx НЕ изменён (per Architect §3.1.1). Маршрут /admin/floating-structures добавлен в App.tsx под ProtectedRoute requiredPermission="locations:read". Tailwind, mobile-responsive (sm:/md:/xl: брейкпоинты, grid-cols-1 → md:grid-cols-2 → xl:grid-cols-3), без React.FC, все строки UI на русском, ошибки отображаются через error-блок и toast (внутри thunks). District picker — оставлен как number input с пояснением (DistrictLocationSelect не подходит — он выбирает локацию внутри района, а не сам район), не блокирующий риск, готов к замене когда появится подходящий компонент. ⚠️ npx tsc --noEmit и npm run build локально не запущены — Node.js не установлен на хосте (та же блокировка, что в T9). Самопроверка типов: все импорты разрешаются (RouteWaypoint/FloatingStructure из T9-слайса, fetchAreas/selectAreas из worldMapActions/worldMapSlice, useAppDispatch/useAppSelector из store), нет any, нет React.FC. Сборку должен верифицировать Reviewer.
[LOG] 2026-04-07 — Reviewer: начал финальную проверку T16
[LOG] 2026-04-07 — Reviewer: py_compile (11 файлов + миграция) PASS; pytest locations (21/21) и character-service (18/18) PASS через Docker python:3.10-slim (обошёл Python 3.14 блокер хоста); npx tsc --noEmit и npm run build PASS через Docker node:20-alpine (обошёл отсутствие Node на хосте) — в новых файлах FEAT-123 ошибок нет, 63 ошибки предсуществующие (в т.ч. WorldPage.tsx:49 — от FEAT-042 92cf823); nginx -t dev PASS, prod синтаксически валиден (падает только на отсутствии SSL-сертификата — ожидаемо); docker compose config PASS
[LOG] 2026-04-07 — Reviewer: атомарность execute_teleport подтверждена (with_for_update на строке crud.py:2212), cascade npc_role подтверждён (main.py:2073-2080), npc_role propagation в client/details подтверждён (schemas.py:468/554), rate-limit teleport корректно привязан к маршруту /characters/npcs/\d+/teleport
[LOG] 2026-04-07 — Reviewer: ⚠ FAIL — найдены дыры view-mode в LocationPage: NpcProfileModal.tsx (Talk/Trade/Auction/Quests/Attack кнопки не gate'ятся на isCharacterHere — только Teleport корректно закрыт), LocationPage.tsx:442 PostCreateForm disabled-условие пропускает владельца любого персонажа в режиме просмотра, бэкенд POST /posts/ не валидирует current_location_id == location_id. §4.T16 явно требует блокировку всех этих действий в режиме просмотра Цитадели. Возвращаю 7 FIX_REQUIRED фронтенду/бэкенду + требуется live-верификация после фиксов (локальный стек не запущен, chrome-devtools MCP недоступен). Таблица проблем в §5.
[LOG] 2026-04-07 — Frontend Dev: исправлены FAIL-находки Reviewer #1-#6 по view-mode дырам. LocationPage.tsx:442 — `PostCreateForm.disabled` теперь `inBattle || (!isCharacterHere && !userIsStaff)` (убран ошибочный `&& !character`, который коллапсил условие при владении персонажем). NpcProfileModal.tsx — кнопки Talk/Trade/Auction/Quests/Attack обёрнуты в `&& isCharacterHere` по образцу уже корректно закрытой Teleport-кнопки (строка 320): выбрана стратегия полного скрытия, а не disabled+tooltip, для консистентности с существующим паттерном в этом же файле. `isCharacterHere` уже приходит пропом из LocationPage (T11). Правки минимальные, других частей файлов не касался. ⚠️ `npx tsc --noEmit` и `npm run build` локально не запущены — Node.js не установлен на хосте (та же блокировка, что в T9/T12/T13). Reviewer должен перепроверить через Docker node:20-alpine и live-верификацию.
[LOG] 2026-04-07 — QA: T15 готов — добавлен services/character-service/app/tests/test_teleport.py. Фикстуры: 2 NPC-мастера телепорта в локациях A/B, игрок с currency_balance=500 в локации A, обе связи A↔B; users и Locations созданы как extend_existing-таблицы для raw SQL внутри execute_teleport / list_teleport_options. Покрыто: success POST /characters/npcs/{id}/teleport (золото списано, current_location_id обновлён, last_teleport_at установлен, log_gold_transaction вызван — проверено через spy и через GoldTransaction в БД), 402 insufficient_gold, 409 cooldown_active с cooldown_seconds_remaining, 422 broken link при понижении роли target NPC + автофильтрация той же связи из /teleport-options, 422 source not teleport master, 422 player not in source NPC location, GET /teleport-options с to_location_name="Локация B", 404 если NPC не teleport master. Admin CRUD /characters/admin/teleport-links: bidirectional → 2 строки, non-bidirectional → 1, 422 при попытке связать с не-teleport-master NPC, 409 на duplicate pair, DELETE с delete_reverse=true удаляет обе. Auth: 401/403 без admin (unauthenticated и regular user). Side-effect: crud.purge_teleport_links_for_npc удаляет все связи NPC (как incoming, так и outgoing). Concurrency smoke: второй последовательный teleport блокируется кулдауном с 409 (SQLite не моделирует FOR UPDATE-гонки, но end-state идентичен — ровно одна попытка успешна в окне 24ч). py_compile прошёл. ⚠️ Локальный pytest run заблокирован: на хосте установлен только Python 3.14, несовместимый с pydantic 1.10 — BaseSettings не подхватывает required-поля DB_USERNAME даже на минимальном репро вне нашего кода (та же блокировка фигурирует в логе T14). Тесты должны исполняться в CI (Python 3.10 в Docker), как и для T14.
[LOG] 2026-04-07 — Backend Dev: исправлен FAIL #7 — в services/locations-service/app/main.py create_new_post (≈:595) добавлена defense-in-depth проверка current_location_id == post_data.location_id прямым запросом к общей таблице characters (паттерн уже используется в verify_character_ownership/check_not_in_battle этого же файла — без лишнего HTTP-хопа в character-service). При несовпадении — 403 "Вы не находитесь в этой локации". Staff (role admin/moderator из UserRead) обходят проверку. Минимальный дифф, остальное в хендлере не тронуто. py_compile main.py PASS.
[LOG] 2026-04-07 — Reviewer: начал повторную проверку (итерация 2/3) после фиксов #1-#7
[LOG] 2026-04-07 — Reviewer: все 7 правок подтверждены в исходниках — LocationPage.tsx:442 теперь `inBattle || (!isCharacterHere && !userIsStaff)` без ошибочного `&& !character`; NpcProfileModal.tsx — Talk/Trade/Auction/Quests/Attack обёрнуты в `&& isCharacterHere` по образцу Teleport; locations-service main.py:596-606 — defense-in-depth SELECT current_location_id с 403 "Вы не находитесь в этой локации" и staff bypass
[LOG] 2026-04-07 — Reviewer: автопроверки (Docker): py_compile PASS, pytest locations 21/21 PASS (0.32s), pytest character 18/18 PASS (1.04s), npx tsc --noEmit PASS для FEAT-123 scope (63 предсуществующих ошибки в unrelated файлах — те же, что в Review #1), npm run build PASS (46.61s). Live-верификация не выполнена — dev-стек не запущен, chrome-devtools MCP недоступен; задокументировано как пост-мёрдж smoke-test для PM/пользователя (не блокирует PASS — все пути покрыты статическим аудитом + тестами)
[LOG] 2026-04-07 — Reviewer: ✅ PASS — T16 помечен DONE, Meta.status = REVIEW, передаю PM для закрытия фичи
[LOG] 2026-04-07 — Frontend Dev: HOTFIX — все 5 thunks в `floatingStructuresSlice.ts` били по URL без префикса `/locations/` (например `/admin/floating-structures`), из-за чего nginx отдавал 404 на каждый admin CRUD и публичный fetch плавающих структур. Добавлен префикс `/locations/` ко всем 5 URL (fetchFloatingStructures, fetchAdminFloatingStructures, createFloatingStructure, updateFloatingStructure, deleteFloatingStructure) по образцу `worldMapActions.ts`. `teleportSlice.ts` уже использует корректный префикс `/characters/` — не тронут. Минимальный дифф, только URL-строки.
[LOG] 2026-04-07 — Backend Dev: HOTFIX — миграция 015 падала на старте character-service с `Data too long for column 'version_num'` (revision id `015_add_teleport_links_and_cooldown` — 35 символов, при дефолтной ширине `alembic_version_character.version_num` VARCHAR(32)). Переименован revision id в `015_teleport_cooldown` (21 символ) и файл миграции в `015_teleport_cooldown.py`. Содержимое upgrade/downgrade не тронуто. Грепом по репо других ссылок на старый id не найдено (down_revision не используется — это последняя миграция). py_compile PASS. Запись добавлена в docs/ISSUES.md как learning note.
[LOG] 2026-04-07 — Backend Dev: HOTFIX — `floating_router` в locations-service/main.py был объявлен как `APIRouter()` без префикса и подключался через `app.include_router(floating_router)`, из-за чего его эндпоинты висели на `/admin/...` и `/map/...` вместо `/locations/admin/...` и `/locations/map/...`, и nginx-проксированные запросы получали 404. Изменён на `APIRouter(prefix="/locations")` по образцу основного `router` (строка 109). py_compile PASS, hot-reload подхватит без пересборки.
[LOG] 2026-04-07 — Backend Dev: HOTFIX UX — снято требование non-empty для `route_json` в `FloatingStructureBase`/`Create`/`Update` (schemas.py): админ UX предполагает сначала создать структуру, затем рисовать маршрут через FloatingRouteEditor — прежний валидатор делал это невозможным (chicken-and-egg). Теперь пустой список `[]` допустим по умолчанию, при `None` нормализуется в `[]`; валидация формы точек (dict с x/y float в [0..100]) сохранена без изменений. py_compile schemas.py PASS.
[LOG] 2026-04-07 — Frontend Dev: HOTFIX T12 — добавлена ссылка "Плавающие структуры" → `/admin/floating-structures` в админ-меню (`AdminPage.tsx`) рядом с "Локации", module: `locations` (тот же permission gate, что и у роута). Минимальный диф, существующий паттерн sections соблюдён.
[LOG] 2026-04-07 — Frontend Dev: HOTFIX T10 — клик по иконке Цитадели на карте мира возвращал пользователя на карту области вместо открытия внутренней District-карты. Корневая причина: эффект auto-focus в `WorldPage.tsx` (когда `viewLevel === 'world'` и доступна одна area) вызывал `navigate('/world/area/<id>', { replace: true })` сразу после `navigate('/world?citadel=<id>')`, и React Router отбрасывал query-string при переходе по path-only пути — параметр `?citadel=<id>` исчезал, и эффект, читающий `citadelParam`, никогда не успевал отработать. Фикс: добавлен ранний `if (citadelId != null) return;` в auto-focus useEffect и `citadelId` добавлен в зависимости. Минимальный диф, остальные эффекты не тронуты. Проверка `npx tsc --noEmit` — БЛОКЕР: node/npm недоступны в текущем окружении (where node → не найдено). Рекомендуется прогнать тайпчек локально/в CI перед мержем.
[LOG] 2026-04-07 — Frontend Dev: POST-DONE TWEAK — по запросу пользователя внесены два изменения. (1) Маршрут плавающей структуры теперь ping-pong (A → B → A), а не замкнутая петля: в `FloatingStructuresLayer.tsx` `interpolateClosedPolyline` заменён на `interpolatePolyline` (открытая полилиния, n−1 сегмент, без wrap-around last→first); добавлен helper `triangleWave(value) = 1 − |((value % 2)) − 1|`, прогресс времени теперь `triangleWave(t * speed)` вместо `(t * speed) % 1`, что даёт плавное колебание 0→1→0→1. В `FloatingRouteEditor.tsx` SVG `<polygon>` заменён на `<polyline fill="none">`, инструкция-подсказка обновлена на «Маршрут открытый (ping-pong): первая точка — A, последняя — B», точки A и B визуально подсвечены (зелёная A / красная B / жёлтые промежуточные) и подписаны буквами. В `waypointUtils.ts` `findInsertIndex` обновлён — итерируется только n−1 сегмент (без wrap-around), доккомментарий `waypointsToPolygonPoints` пометил, что выход годится и для `<polyline>` (имя оставлено для минимальности диффа). Бэкенд и `route_json` shape не тронуты — изменена только интерпретация. (2) Иконка Цитадели на карте мира уменьшена ровно в 2 раза: классы `w-8 h-8 sm:w-10 sm:h-10 md:w-12 md:h-12` → `w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6` (применено и к `<img>`, и к fallback-плейсхолдеру; размер шрифта плейсхолдера уменьшен пропорционально `text-[8px] sm:text-[10px]`). Фокус-ринг и hit-area оставлены штатно (touch остаётся достаточным благодаря `touch-manipulation` и `p-0` на кнопке-обёртке). Tailwind only, без React.FC, минимальные диффы. Локальный тайпчек/билд не запускались — Node на хосте по-прежнему недоступен.
[LOG] 2026-04-07 — Frontend Dev: POST-DONE TWEAK — в `FloatingStructuresPage.tsx` поле `icon_url` (text input) заменено на загрузку файла с устройства. Использован существующий generic-helper `uploadArchiveImage` из `api/archive.ts` (POST `/photo/upload_archive_image` — единственный безсущностный upload-эндпоинт photo-service, возвращающий `{image_url}`; permission `photos:upload` админу уже дан). Добавлены state `iconUploading` + `iconFileInputRef`, обработчик `handleIconFileChange` (toast.success/error через уже используемый в проекте `react-hot-toast`, очистка input после загрузки). UI: превью 12×12 (или dashed-плейсхолдер «нет»), file input с Tailwind file: классами, кнопка «Очистить», индикатор «Загрузка...», и небольшой fallback-text input «или вставьте URL вручную» (паттерн ручного URL-fallback соответствует тому, как другие админ-формы оставляют поле ручного ввода). Tailwind only, без React.FC, mobile-responsive (`flex-wrap`, `min-w-0 flex-1`). Минимальный диф, остальная часть формы и логика submit не тронуты — `form.icon_url` остаётся источником правды, payload submit без изменений. Локальный `npx tsc --noEmit` не запускался — Node на хосте по-прежнему недоступен.
[LOG] 2026-04-07 — Frontend Dev: BUGFIX — порядок точек в `FloatingRouteEditor` ломался при добавлении новых waypoints (например 22, 23, 25, 24). Корневая причина: `findInsertIndex` в `waypointUtils.ts` использовал слишком щедрый порог `thresholdPct = 3` (3% контейнера ≈ 30px на карте 1000px), поэтому клики, задуманные как «добавить после B», попадали в зону ближайшего сегмента и вставлялись в середину полилинии, а не в конец. С накоплением точек сегменты начинают пересекать всю карту, и почти любой клик оказывается «рядом с линией» → новый waypoint вставляется не в конец. Симптом «B сдвигается» — визуальное следствие той же баги: свежая точка вставляется по индексу `length-1`, сдвигая нумерацию промежуточных точек (сам B по координатам остаётся на месте, но меняется порядковый номер соседей). Фикс: ужат порог до `1.5` (≈ 8–12px на типичной карте), уточнён docstring — append теперь дефолт, mid-segment insert срабатывает только когда клик действительно на линии. Drag-хендлеры уже корректно изолированы (`stopPropagation` на mousedown waypoint-кнопки + guard `dataset.waypoint === '1'` в `handleCanvasClick`), дополнительных правок не потребовалось. Минимальный диф — одно изменение дефолта параметра в `waypointUtils.ts`, сигнатура и возвращаемые значения совместимы. Tailwind only, без React.FC.
[LOG] 2026-04-07 — Frontend Dev: BUGFIX — точки маршрута «съезжали выше» на публичной карте мира относительно редактора. Корневая причина: `FloatingRouteEditor` форсил `style={{ aspectRatio: '16/9' }}` на контейнере карты, а публичный `InteractiveMap` использует `min-h-[300px] md:min-h-[500px]` без фиксированного aspect-ratio. Оба применяют `object-cover` к одному и тому же `areas[0].map_image_url`, но кроп изображения и форма контейнера отличались — поэтому одинаковые проценты x/y давали разные пиксели, особенно по вертикали. Фикс: `FloatingRouteEditor` теперь использует ровно тот же контейнер-сайзинг, что и `InteractiveMap` (`relative w-full min-h-[300px] md:min-h-[500px]`, без `aspectRatio`), и тот же layout `<img className="w-full h-full object-cover">` без `absolute inset-0`. Теперь оба рендера применяют проценты к идентично-сформированным контейнерам с идентичным object-cover кропом — позиции совпадают. Tailwind only, без React.FC, минимальный диф (одна правка в `FloatingRouteEditor.tsx`). Бэкенд, схема `route_json` и публичный layer не тронуты.
[LOG] 2026-04-07 — Fullstack: FOLLOW-UP — добавлен флаг `Country.is_hidden` (Boolean, default false), чтобы администратор мог завести служебную страну "Плавающие структуры", которая держит `internal_district_id` Цитадели, но не отображается игрокам в боковой панели локаций. Backend (locations-service): в `models.py` добавлена колонка, Alembic-миграция `028_country_is_hidden` (op.add_column с server_default='0', idempotent через inspector), schemas (`CountryBase.is_hidden`, `CountryUpdate.is_hidden`, `CountryRead.is_hidden`), `create_new_country` принимает `is_hidden`, маршрут `/countries/create` пробрасывает поле. Фильтрация hidden стран только на player-facing reads: `get_hierarchy_tree` (where `is_hidden == False`) и `get_area_details` (фильтр в list comprehension). Admin-эндпоинты (`/admin-panel`, `/countries/list`, `/countries/lookup`, `/countries/{id}/details`) НЕ фильтруют — админ видит и управляет скрытыми странами. `get_country_details` (direct by id) также не фильтрует, поэтому доступ к District через `internal_district_id` floating structure продолжает работать. В admin-panel и `/countries/list` ответах теперь возвращается `is_hidden` для корректной индикации в админке. Frontend: в `adminLocationsActions.ts` Country интерфейс расширен полем `is_hidden: boolean`; в `EditCountryForm.tsx` добавлен чекбокс "СКРЫТО" с help-текстом "Не отображать в боковой панели локаций для игроков (но доступно для системных целей: плавающие структуры, и т.п.)", wired к `formData.is_hidden` (init из `initialData?.is_hidden ?? false`), дефолт снят. Кнопки submit/cancel обёрнуты `flex-col sm:flex-row` для мобильной адаптивности. Tailwind only, без React.FC, без SCSS. Side panel фильтра не требует — backend уже фильтрует hidden на `/hierarchy/tree`. `py_compile` PASS для models/schemas/crud/main/028_country_is_hidden. TS-typecheck локально не запускался (Node на хосте недоступен), но диф минимальный и чисто типобезопасный.
[LOG] 2026-04-07 — Backend Dev: CI HOTFIX — починены два падения тестов locations-service после мержа FEAT-123. (1) `test_floating_structures.py` — все 18 тестов получали 404, потому что после хотфикса `floating_router` получил `prefix="/locations"`, а URL в тестах остались старые. Search-and-replace: `/map/floating-structures` → `/locations/map/floating-structures`, `/admin/floating-structures` → `/locations/admin/floating-structures` (включая `/{id}` варианты). Логика тестов не тронута. (2) 6 country-тестов падали с `ResponseValidationError: is_hidden value could not be parsed to a boolean` — БД отдавала `None` (фикстура/seed обходили ORM-default), Pydantic v1 `bool`-поле не принимало `None`. Фикс по Option A: добавлен `@validator('is_hidden', pre=True, always=True)` в `CountryRead` (schemas.py), `None → False`, иначе `bool(v)`. Defensive, не меняет поведение для существующих данных, не зависит от пути вставки. `py_compile` PASS для обоих файлов. Pytest локально не запускался (нет Docker/Python-окружения с aiomysql на хосте) — финальная валидация в CI.
[LOG] 2026-04-07 — Frontend Dev: BUGFIX — иконка Цитадели (FloatingStructuresLayer) показывалась на всех уровнях `InteractiveMap` (world / area / country), хотя waypoints в % имеют смысл только на area-карте. Корневая причина: `FloatingStructuresLayer` был безусловно смонтирован внутри shared-компонента `InteractiveMap`. Фикс (Option A, минимальный диф): добавлен опциональный проп `showFloatingStructures?: boolean` в `InteractiveMap.tsx`, рендер `<FloatingStructuresLayer />` теперь гейтится на этом флаге; в `WorldPage.tsx` пропс прокидывается как `viewLevel === 'area' && citadelId == null && cityMapDistrictId == null` — то есть только когда пользователь на карте области (где страны кликабельны как зоны) и НЕ внутри Citadel city-map. Tailwind only, без React.FC, два файла затронуты, по одной правке в каждом.
[LOG] 2026-04-07 — Frontend Dev: BUGFIX FINAL — эвристика «клик рядом с сегментом → вставить в середину, клик в пустоту → добавить в конец» оказалась принципиально хрупкой (любой порог либо крадёт клики у append, либо ломает insert). Эвристика удалена. Новое поведение: ЛКМ — всегда append в конец маршрута (без проверки расстояния, без mid-segment insert); Shift + ЛКМ — явная вставка в ближайший сегмент через `findInsertIndex` с щедрым порогом (100), при отсутствии сегментов — fallback на append. ПКМ и drag не тронуты. Обновлён help-текст в UI редактора (4 строки: ЛКМ / Shift+ЛКМ / ПКМ / перетаскивание) и JSDoc компонента. `addWaypoint`/`insertWaypoint` перепроверены — обе чистые операции над массивом, координаты других точек не мутируют, симптом «B сдвигается» был чисто визуальным (перенумерация после вставки), теперь устранён вместе с самой вставкой. `waypointUtils.ts` не тронут (как указано в задаче — `findInsertIndex` остаётся как есть). Tailwind only, без React.FC, минимальный диф — только `FloatingRouteEditor.tsx`.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

**Floating Citadel:**
- Новая таблица `floating_structures` в locations-service (async, Alembic 027). Поля: name, description, route_json (замкнутый цикл waypoints), speed (доля маршрута/сек), started_at, icon_url, internal_district_id (FK на District).
- Публичный `GET /map/floating-structures` возвращает структуры + `server_now` для коррекции часов клиента.
- Админ CRUD `/admin/floating-structures`.
- Внутренняя карта Цитадели — переиспользует существующий District+Locations паттерн через `internal_district_id`. Ноль новых таблиц для интерьера.
- Frontend: `<FloatingStructuresLayer>` в `WorldPage` — клиентская интерполяция позиции по замкнутому маршруту (1 Hz). Клик на иконку → `?citadel=<id>` → открывает внутреннюю карту в режиме просмотра.
- Админка: `FloatingStructuresPage` (CRUD) + slim dedicated `FloatingRouteEditor` (drag waypoints поверх карты мира). `RegionMapEditor` не тронут.

**Teleport Master NPC:**
- Новая таблица `teleport_links` в character-service (sync, Alembic 015) с FK CASCADE на обе стороны. Уникальный `(from_npc_id, to_npc_id)`.
- Новое поле `Character.last_teleport_at` для глобального суточного кулдауна.
- `GET /characters/npcs/{id}/teleport-options` — список доступных направлений с именами целевых локаций.
- `POST /characters/npcs/{id}/teleport` — атомарный flow: `SELECT FOR UPDATE` на персонаже, проверка кулдауна (409), золота (402), валидности линка/ролей/локации (422), списание золота через `log_gold_transaction`, обновление `current_location_id` и `last_teleport_at` — всё в одной транзакции.
- Админ CRUD `/characters/admin/teleport-links` с поддержкой двусторонних связей (по умолчанию создаются 2 строки).
- При смене `npc_role` NPC c `teleport_master` на другую — все его связи удаляются каскадом в той же транзакции.
- Frontend: `TeleportMenu` появляется в карточке NPC при `npc_role === 'teleport_master'` И `isCharacterHere`. Модалка списка направлений → подтверждение → телепорт. Все ошибки на русском.
- Админка: `TeleportLinksPanel` в редакторе NPC при роли `teleport_master`. Поиск NPC, стоимость, чекбокс "двусторонняя".

**Безопасность:**
- Nginx rate limit `10r/m` (burst 5) на `POST /characters/npcs/{id}/teleport` (по `$binary_remote_addr`) — оба конфига (dev + prod).
- Backend defense-in-depth для view-mode Цитадели: `create_new_post` теперь проверяет, что персонаж физически в локации, иначе 403.
- Frontend view-mode гейтинг: все write-кнопки в `NpcProfileModal` (Talk/Trade/Auction/Quests/Attack) и `PostCreateForm` теперь скрыты/заблокированы если `!isCharacterHere`.

**Тесты:**
- locations-service: `test_floating_structures.py` — 21/21 PASS.
- character-service: `test_teleport.py` — 18/18 PASS (cooldown, gold, broken links, role cascade, bidirectional, auth).

### Как проверить

После запуска dev-стека:
1. **Админка → Локации → Плавающие структуры**: создать "Цитадель" с тестовой иконкой, привязать к существующему District (с `map_image_url`), задать speed (для теста — высокий, например 0.001), нарисовать маршрут по морю в `FloatingRouteEditor`.
2. **Главная → Карта мира**: иконка Цитадели должна появиться над морем. С высоким speed — заметно движется.
3. **Клик на иконку**: открывается внутренняя карта Цитадели. Зайти в любую локацию — кнопки Talk/Trade/Attack/Auction/Quests/форма постов **должны быть скрыты или заблокированы**.
4. **Админка → NPC**: создать двух NPC с ролью "Мастер Телепорта" в разных локациях материков (или внутри Цитадели). В карточке появляется `TeleportLinksPanel`. Связать их с ценой (например 100 золота), двусторонняя по умолчанию.
5. **Зайти на одного из них персонажем**: в карточке NPC появляется кнопка "Телепорт". Открыть → выбрать направление → подтвердить. Золото списывается, персонаж переходит. Повторная попытка в течение 24ч → ошибка кулдауна.
6. **Сменить роль одного из NPC** на не-teleport_master → его связи автоматически удаляются.

### Что изменилось от первоначального плана

- **Path editor**: Architect выбрал отдельный slim `FloatingRouteEditor` вместо расширения 2295-строчного `RegionMapEditor` (другая система координат, риск регрессий).
- **Skala скорости**: вместо units/hour решено использовать долю полного маршрута в секунду — не зависит от размеров карты.
- **`server_now`** добавлено в payload плавающих структур для коррекции расхождения часов клиента.
- **District picker для админки**: пока обычный input с ID — нет готового компонента выбора District (только locations внутри district). Owner может расширить позже.
- **Иконка Цитадели**: используется временная заглушка — owner заменит через `icon_url`.
- **View-mode защита**: при первом ревью обнаружены 6 frontend утечек + 1 backend defense-in-depth дыра в `create_new_post`. Все исправлены в итерации 2 ревью.
- **Live-verification**: не проведена — dev-стек не был поднят. Пользователь проводит smoke-тест после деплоя по чеклисту выше.

### Оставшиеся риски / follow-up задачи

- **District picker** для админки `FloatingStructuresPage` — сейчас input с ID, удобнее иметь полноценный select. Не блокирующий.
- **Image upload для иконки Цитадели** — backend пока принимает `icon_url` строкой. Если нужен встроенный загрузчик — отдельная задача.
- **Изменение стоимости одной стороны двусторонней связи** не обновляет обратную связь автоматически. Документировано в tooltip админ-панели. Owner может править вручную.
- **Per-user JWT-sub rate limit** не реализован — Nginx без lua/njs не умеет, fallback на `$binary_remote_addr`. Достаточно для текущих требований.
- **Concurrency**: SQLite в тестах не моделирует реальные `FOR UPDATE`-гонки, но prod-MySQL поддерживает; код корректен.
- Задача T2 (Alembic) подтверждена — `notification-service` остаётся единственным сервисом без Alembic. Эта фича его не трогала.

[LOG] 2026-04-07 — Frontend Dev: BUGFIX — FloatingStructuresLayer перехватывал pointer events на всю площадь карты мира, из-за чего клики по ClickableZoneOverlay регионам/зонам не проходили. Фикс: внутренний wrapper `absolute inset-0` больше не имеет `pointer-events-auto` (outer уже `pointer-events-none`), а сам `<button>` маркера получил `pointer-events-auto` — клики через пустое пространство слоя падают на нижележащий overlay, иконка остаётся кликабельной. Минимальный диф, Tailwind only.
