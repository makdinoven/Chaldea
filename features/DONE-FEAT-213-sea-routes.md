# FEAT-213: Морские пути — порты, корабли и морские участки караванов

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-15 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

> **Бриф переработан 2026-11-16 (v2).** Первая версия («рейс-таймер» с блокировкой «на борту») отменена пользователем в пользу кораблей-локаций. Части v1, уже сделанные (T1 схема CS, T3 порты и маршруты LS, T4 типы операций экономики, T2 частично), не закоммичены: архитектор решает, что из них оставить, что переделать, что откатить.

### Описание
Страны за морем оторваны друг от друга: пути рисуются внутри региона, регионы соединяются стрелками, а телепорт через НПС редкий и дорогой. Нужно морское сообщение — и для игроков, и потом для караванов экономики.

Главная идея пользователя: **корабль — это настоящая локация**, а не таймер. На палубе работает всё, что есть в обычной локации: посты, НПС, бои, отыгрыш. За НПС-Капитаном скрывается локация его корабля.

### Бизнес-правила

**Корабли и капитаны — уникальные постоянные сущности**
- Админ создаёт корабль один раз: имя, капитан (уникальный НПС с характером и описанием), палуба (своя локация с картинкой и описанием), число мест, маршрут, время сборов в порту, скорость (время на морскую зону).
- Капитан физически ходит по миру: стоит в портовой локации, пока корабль в порту; при отплытии поднимается на борт и исчезает из порта для всех; в море стоит на палубе; по прибытии сходит в порт назначения и ждёт там следующего отплытия.
- Маршрут — линия из нескольких портов с остановками (не только туда-обратно). Дойдя до конца, корабль идёт обратно (или по кругу — на усмотрение архитектора, по умолчанию туда-обратно по линии).
- В каждом порту корабль стоит время сборов (например 30 минут), затем отплывает.

**Как попасть на борт** (в порту, у Капитана; нужен пост-намерение «Диалог с НПС», как у Караванщика)
- В диалоге видно: куда идёт корабль (следующие остановки), когда отплытие, цена, свободные места.
- Способы:
  - **Билет** — оплата марками до выбранного порта маршрута. Деньги — по образцу телепорта (в казну региона порта, страна получает налог).
  - **Работа матросом** — бесплатно, но до отплытия нужно отписать на палубе пост определённой длины (настройка); не отписал — проезд не засчитан, считается «зайцем» (или высаживается — на усмотрение архитектора, но без бесплатного проезда).
  - **Зайцем** — подняться на борт без оплаты: проверка скрытности; если поймали — преступление по законам края порта (как в системе тени/закона), безбилетника высаживают.
- После оплаты/найма из портовой локации на палубу открывается переход, проходит только тот, у кого есть право (по образцу закрытых фракционных локаций). Заходит постом, как в обычную локацию.
- **Опоздал — сам виноват**: заплатил, но не поднялся на борт до отплытия — деньги сгорают.
- Мест ограниченное число.
- С Капитаном можно говорить и на палубе в пути — например, оплатить следующий участок, не сходя на берег.

**Отплытие и плавание**
- При отплытии переход порт↔палуба закрывается, Капитан исчезает из порта. Все, кто на палубе, плывут.
- В море с палубы никуда не уйти (у палубы нет выходов). Игрок может быть офлайн — он просто остаётся на корабле.
- Корабль переходит из морской зоны в зону по пути к следующему порту.

**Прибытие**
- Корабль швартуется, Капитан сходит в порт, переход палуба↔порт снова открыт; пассажиры сходят постом.
- Кто не сошёл — плывёт дальше по маршруту, но за следующий участок нужно платить снова (иначе он безбилетник).

**Моря — скрытый раздел мира**
- Морские зоны не рисуются на картах областей. Создаётся скрытая страна (условно «Моря»), её регионы — моря («Море Эйдонэи», «Внутреннее море»), локации — морские зоны («Пролив Ветров», «Северный залив»).
- Соседство зон админ задаёт так же, как соединяет локации внутри региона (тем же редактором); между морями — стрелками переходов между регионами.
- Порт на суше указывает, к какой морской зоне он выходит.
- Игроки в морские зоны никогда не заходят: зона — это только «где сейчас корабль». Морские зоны НЕ должны связываться с сушей обычными переходами и НЕ должны попадать в сухопутные маршруты караванов.
- Путь корабля между портами по зонам система прокладывает сама (кратчайший по соседству зон); админ может поправить вручную.
- На палубе видно «Корабль сейчас: Пролив Ветров, море Эйдонэи».
- Картинку-карту моря можно загрузить потом (необязательно).

**Встречи кораблей (этап 1)**
- Корабли в одной морской зоне в одно время видят друг друга («Вдали виден корабль „Морская дева“»). Сцепка бортов и переход между кораблями — этап пиратов, не сейчас.

### Этапы
1. **Этот этап (FEAT-213):** корабли-локации, уникальные капитаны, маршрут с остановками, три способа попасть на борт, сгорающий билет, скрытая страна «Моря» с зонами и соседством, движение корабля по зонам, видимость соседних кораблей.
2. Потом: шторма и налёты монстров на палубу, грузы караванов на кораблях (караваны по морю), таможня и контрабанда в портах.
3. Потом: пираты, свои корабли игроков и фракций.

### UX / Пользовательский сценарий
1. Игрок приходит в порт, видит Капитана среди НПС локации.
2. Пишет пост «Диалог с НПС», открывает диалог: маршрут, следующие остановки, время до отплытия, цена, места.
3. Выбирает способ: билет до порта / работа матросом / пробраться зайцем.
4. В порту появляется переход на палубу; игрок заходит постом и ждёт отплытия, отыгрывая на палубе.
5. Отплытие: Капитан исчезает из порта, корабль в море; на палубе видно, в какой зоне корабль и какие корабли рядом.
6. Прибытие: игрок сходит постом в порт назначения.

### Edge Cases
- Корабль удалили / сломали маршрут, пока на борту люди — никто не должен застрять навсегда (безопасная высадка).
- Порт удалили или он перестал быть портом — корабль пропускает его / безопасно высаживает.
- Капитана-НПС удалили или админ переставил его вручную.
- Игрок на палубе в бою/без сознания при прибытии.
- Двойная оплата — деньги списываются один раз.
- Безбилетник прячется до отплытия; проверка в момент отплытия.
- Админ телепортирует игрока с палубы.

### Вопросы к пользователю
- [x] Маршрут с остановками → да.
- [x] Опоздавший на борт → деньги сгорают, «сам виноват».
- [x] Кто не сошёл в порту → плывёт дальше, но за следующий участок платит снова.
- [x] Встречи кораблей на этапе 1 → только видеть соседей в зоне.
- [x] Моря → скрытая страна «Моря», зоны = локации, без рисования на картах областей.
- [x] (2026-11-17, по 3.19) Остался на палубе без билета → высаживают без последствий.
- [x] Матрос не дописал пост → высаживают без последствий.
- [x] Свиток телепорта домой в открытом море → работает, путь теряется.
- [x] Непойманный «заяц» → бесплатный проезд без следов (по умолчанию).
- [x] Цена → базовая + за каждую морскую зону, на каждом корабле; деньги в казну региона порта отправления с налогом стране, как телепорт.
- [x] Билеты на отряд → не нужны, каждый покупает сам.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

All paths below are relative to `services/`. CS = character-service, LS = locations-service, BS = battle-service,
IS = inventory-service, PS = party-service, FE = `frontend/app-chaldea/src`.

### 2.1 Affected services

| Service | Changes | Key files |
|---|---|---|
| character-service | sea routes / voyages / tickets / Captain (most likely, see 2.9), new lock reason, caravan sea legs (stage 2), new econ op types, scheduler step | `activity_lock.py`, `models.py`, `caravan_route.py`, `economy_caravan_crud.py`, `caravan_pass.py`, `caravan_escort_*.py` (template), `crud.py` (teleport = template), `main.py` (`_prepare_move`, `update_location`, `/by_location`), `law_crud.py:555`, `caravan_escort_public.py:61`, `econ_core.py`, `econ_scheduler.py`, new alembic 052 |
| locations-service | lock copy (new column), maybe `Locations.is_port` + public sea-route read for the world map (if LS owns geography), `econ_core.py` copy | `activity_lock.py`, `models.py`, `crud.py`, `main.py`, `econ_core.py`, alembic 060 |
| battle-service | lock copy only (SQL + fallback chain) | `activity_lock.py` |
| inventory-service | lock copy + `econ_core.py` copy | `activity_lock.py`, `econ_core.py` |
| dungeon-service | `econ_core.py` copy only (reads the lock over HTTP — nothing else) | `econ_core.py` |
| party-service | `_AT_LOCATION_SQL` (only if passengers must be hidden from location lists) | `app/crud.py:128-165` |
| user-service | RBAC migration only if a new permission is chosen (latest `0035_faction_economy_perm`) | `alembic/versions/` |
| frontend | lock reason, banner, Captain modal, voyage modal + channel, admin: port flag, Captain role, sea-route editor, world-map layer, econ labels | see 2.4 / 2.7 |
| notification-service | none (ws_type is free-form, `consumers/general_notification.py:72`) | — |

### 2.2 Physical caravans and routing (FEAT-211/212) — the template

**Model** `EconCaravan` (`character-service/app/models.py:1035`, table `econ_caravans`): physical fields from migration 050 —
`is_physical`, `route` (JSON list of Locations ids, start gate ... end gate), `route_index`, `current_location_id`,
`next_move_at`, `arrived_at`, `hold_started_at`, `guard_count`, `stolen_units`, `raid_paid`. Indexes `ix_econ_caravans_move`,
`ix_econ_caravans_loc`. No FKs (econ table style, `_EconId` BigInteger PK). Related: `EconCaravanRaid` (:1092, UNIQUE caravan_id),
`EconCaravanEscort` (:1150, UNIQUE (caravan_id, character_id), statuses active/left/fallen/delivered/cancelled/released),
`EconCaravanMessage` (:1177, the channel), `EconCaravanGuardTemplate` (:1194).

**Route computation** — `caravan_route.py` (pure, no DB):
- `build_adjacency` (:21) builds an undirected adjacency from `LocationNeighbors` rows (incl. `is_auto_arrow` cross-region rows).
- `shortest_route` (:36) = BFS by **hop count**, deterministic (ascending ids), `blocked` = `marker_type='dungeon'` locations,
  returns `(None, 'no_gate'|'no_path'|'too_long')`; `max_steps` = `params.caravan_route_max_steps`.
- `effective_gate` (:70): region trade gate = `econ_regions.trade_gate_location_id` (admin override) else `Regions.jail_location_id` (guard station) else none.
- `economy_caravan_crud.load_road_graph` (:350) = two plain SELECTs (`LocationNeighbors`, `Locations.marker_type`);
  `region_gates` (:362); `RoutePlanner` (:385) caches `route(from_region, to_region)` per pass; `build_planner` (:411).
- **No land path** → `planner.route` returns `(None, reason)` → `econ_caravan.choose_physical` (`econ_caravan.py:320`) returns False
  when `not has_route` → the caravan is dispatched **abstract** (old `travel_runs` behaviour, "минуя дороги"). So stage 2's
  fallback rule already holds by construction; sea legs only need to make `planner.route` find more routes.
- `dispatch` (`economy_caravan_crud.py:430`): on physical → `row.route`, `route_index=0`, `current_location_id=road[0]`,
  `next_move_at = now + departure_delay` (:421, `caravan_departure_minutes`, the gathering/«сборы» window at the gate),
  `guard_count`. The planner is called *after* the money/goods locks; ledger op `caravan_dispatch` (purse/treasury → escrow).

**Mover** — `caravan_pass.py` (called by `econ_scheduler.run_scheduled_once`, `econ_scheduler.py:102-109`; scheduler thread
polls every 60 s, `ECON_TICK_ENABLED` default 1 in both compose files). Throttle `claim_run` (:54) on
`econ_sim_settings.caravan_pass_last_run_at`, `RUN_INTERVAL_SECONDS=55`. **`run_pass` returns None when
`caravans_available` is false or `econ_tick.is_tick_enabled` is false (:218)** — caravans freeze with the economy.
Steps: raids (stale/battles/followups) → `_step_caravans` → `_deliver_arrived` (skipped while an econ run is `running`)
→ `escort_rewards` → `escort_housekeeping`. `step_caravan` (:102): if `held_by` (raid active, or a 3.4 "post hold" inside
the one-time window) → `held`; else `route_index += 1`, `current_location_id = route[index]`,
`escort_crud.move_escorts(db, row)` (:123), and either `arrived` or `next_move_at = now + step_delay` (:416, `caravan_step_minutes` ±25 %).
Every location step has the same duration — there is no per-edge duration today.

**Holds / raidability** — `held_by` (`economy_caravan_crud.py:841`), `post_hold` (:808, open `action_gates` of type
`caravan` naming the caravan at its location, or pending `post_gate_requests`), `post_window_open` (:833).
Raid start `caravan_raid_crud.begin_raid` (:238) requires `row.current_location_id == leader's location`, not arrived,
no raid row yet (one raid per caravan, ever), a guard pool, and an open combat gate (`has_open_gate` :217).
`caravans_here` (:169) lists every physical in-transit not-arrived caravan with `current_location_id == my location`.
→ For "invulnerable at sea" both `caravans_here` and `begin_raid` (and `held_by`'s post hold) need a sea-leg check;
otherwise a caravan whose `current_location_id` points at a port while it is at sea would be listed and attackable.

**Escorts (FEAT-212)** — `caravan_escort_crud.py`: hire at a «Караванщик» (`CARAVANEER_ROLE="caravaneer"`, :58) standing at
the gate; a caravan is *preparing* (hireable) while physical, in transit, not arrived, `route_index==0`, never raided
(`_preparing_here` :362). `hire` (:404) locks caravan → escort rows → character, sets `characters.escort_caravan_id`,
clears `house_room_id`, logs `CharacterLog(event_type='caravan_escort')`, returns a `law_notify.Notice`.
`_character_refusal` (:334) = order to copy for tickets: already busy → activity lock message → `_in_battle` (:148, raw SQL
on `battles`/`battle_participants`) → `_gathering` (:154, `gathering_sessions`) → wanted / reputation in the seller region.
`leave` (:511) = «Сойти» (stays where the caravan is). `release` (:196) = ended from outside (admin/home teleport).
`move_escorts` (:599) = raw `UPDATE characters SET current_location_id, house_room_id=NULL WHERE ... AND escort_caravan_id=:car`
(no law entry check, no faction territory refusal, no `character-left-location` cleanup). Lock order comment at :17-21.
Escorts are hidden from public lists (`caravan_escort_public.py`, `/characters/by_location` `main.py:2302`, PS
`_AT_LOCATION_SQL`) — passengers are public per the brief, so that masking must **not** be copied.

**HTTP API** — `caravan_escort_api.py` C1–C6 (prefix `/characters`), `caravan_api.py` (admin roads/gates/guards A5-A9 under
`/characters/admin/economy/caravans/...` with `require_permission("economy:read"|"economy:settings")`, player A1/A2 raids).
Router include order `main.py:4924-4933` (static paths before the main `/characters` router).

**Params** — `economy_caravan_crud.CARAVAN_PARAM_KEYS` (:83) live in `econ_sim_settings`; FE list in
`FE/components/Admin/EconomyPage/EconomyCaravans.tsx:~60-90` + hints in `paramHints.ts`. `caravan_departure_minutes` is the
"like caravans" default for the boarding window.

### 2.3 Activity lock

- Canonical `character-service/app/activity_lock.py` (145 lines). Reasons (:29-40): `dungeon`, `unconscious`, `asleep`,
  `reading`, `jail`, `law_encounter`, `caravan_escort`. `compute_lock` (:68) priority:
  **jail > law_encounter > unconscious > dungeon > caravan_escort > asleep > reading**. Source columns on `characters`
  (CS-owned, CS is the only writer): `dungeon_session_id`, `unconscious_until`, `asleep_since`, `reading_since`,
  `jailed_until`, `law_encounter_id`, `escort_caravan_id` (models.py:120, index `ix_characters_escort_caravan`, migration 051).
  `lock_message` (:122) — Russian refusal texts; escort is neutral on purpose («действие сейчас недоступно») — a voyage needs
  a normal public text (e.g. «… в плавании»).
- Copies: `locations-service/app/activity_lock.py`, `battle-service/app/activity_lock.py` (async), `inventory-service/app/activity_lock.py`
  (sync), each 248 lines. **Upper part must equal the canonical file byte-for-byte** up to the marker
  `\n# ----...\n# Shared-DB read` — test `locations-service/app/tests/test_law_locations.py:203`
  `test_activity_lock_copies_share_the_canonical_upper_part` (CRLF normalised, canonical `.rstrip()`).
  Lower part per copy: `_LOCK_SQL` (7 columns), deploy-skew fallbacks `_LOCK_SQL_LAW` (no escort col, migration 051 missing)
  and `_LOCK_SQL_LEGACY` (no law cols, 039 missing), `_is_missing_column` regex, `_lock_from_row` (:~200),
  `get_activity_lock`, `check_not_activity_locked` (409). A new column = new full SQL + one more fallback level in **3 copies**.
- Explicit (non-`lock_for_character`) callers that pass every column by keyword and must get the new kwarg:
  `character-service/app/law_crud.py:555` (patrol arrival), `character-service/app/caravan_escort_public.py:61`.
- HTTP consumers: dungeon-service `http_clients.get_activity_lock` (:508) → CS `GET /characters/internal/{id}/activity-lock`
  (`main.py:4435`, `schemas.ActivityLockResponse` :1159 — `reason` is a free `str`); user-service `/users/me` passes
  `activity_lock` dict through (`user-service/main.py:365`, schema `Optional[dict]`). No enum to extend server-side.
- CS move guards: `update_location` (`main.py:2376`) refuses `law_encounter`/`caravan_escort` explicitly (:2407) —
  add the voyage reason there; `execute_teleport` (`crud.py:3876`), home teleport (`main.py:1093`) refuse any lock;
  `_prepare_move` (`main.py:934`) releases an escort before admin/home/jail/faction forced moves (`release` +
  `law_notify.publish`) — a voyage needs the same treatment (admin teleport of a passenger must end the voyage or be refused).
  `faction_territory._busy` (:418) and `law_crud.check_patrol_arrival` skip any locked character.
- LS posting: `check_not_locked_for_post` (`locations-service/app/main.py:258`) blocks posts while locked (only the jail
  exception) — passengers can't post in locations; the passenger channel replaces it.
- FE: `FE/hooks/useActivityLock.ts` (`ActivityLockReason` union, per-reason branch, `TIMED_REASONS={'unconscious','jail'}`
  — a voyage with an `until` would fit the timed path, so the banner can show a countdown);
  `FE/components/CommonComponents/ActivityLockBanner.tsx:98` (escort branch opens `CaravanEscortModal`);
  `FE/components/pages/LocationPage/LocationPage.tsx:1061` (reason-specific text); `FE/hooks/useWebSocket.ts:63`
  `LAW_LOCK_REFRESH_TYPES` (ws types that trigger `getMe()` — add the voyage ws type).

### 2.4 Trade gates, NPC roles, Captain

- **Trade gate is not a location flag**: it is `econ_regions.trade_gate_location_id` (CS table, one per region) with the guard
  station fallback; admin A7 `PUT /characters/admin/economy/caravans/gates/{region_id}` (`caravan_api.py:59`,
  `economy_caravan_crud.set_gate` :1205, refuses dungeons/other regions); FE `Admin/EconomyPage/CaravanRoadsCard.tsx`
  + `api/economyAdmin.ts:354 putCaravanGate`. A "port" can have many per region, so a per-location flag fits better;
  the nearest existing per-location boolean is `Locations.no_quick_move` / `is_starting` (LS `models.py:139-141`),
  edited in `FE/components/AdminLocationsPage/EditForms/EditLocationForm/EditLocationForm.tsx` (:35, :191, :403) and
  serialized in LS `crud.py` (≈ :407, :732, :1025, :1282, :3273 world graph).
- **NPC roles are free strings**: `characters.npc_role String(50)` (models.py:65), no backend enum/validation
  (schemas.py:778/804/838/881 `Optional[str]`). Backend constants per module: `TELEPORT_ROLE="teleport_master"`
  (`crud.py:3772`), `FENCE_ROLE="fence"` (`fence_crud.py:32`, duplicated in LS `crud.py:5269`), `CARAVANEER_ROLE` (escort crud :58).
  FE list `FE/constants/npc.ts` (`NPC_ROLES` + `NPC_ROLE_ICONS`; `caravaneer` 🐫 is last). Admin NPC role-only tabs
  `FE/components/AdminNpcsPage/npcTabKeys.ts` (`ROLE_TABS`; caravaneer has no tab — Captain needs none either unless the
  architect wants per-NPC route binding). `main.py:3317-3350` has side effects on role change (teleport links purge, guard
  role) — check if Captain role removal needs anything.
- **Player window**: `FE/components/pages/LocationPage/NpcProfileModal.tsx` — `caravaneerOpen` state (:57), swap to
  `CaravaneerModal` (:200), button (:486, `npc.npc_role === 'caravaneer' && isCharacterHere && characterId`).
  `CaravaneerModal/CaravaneerModal.tsx` (246 lines) is the template for a Captain modal.
- **Dialogue-post gate**: FE `pages/LocationPage/npcDialogueGate.ts` (`isNpcDialogueGateError` detects the 403 text containing
  «Диалог с НПС»; per-NPC hint constants). BE: `caravan_escort_api._caravaneer_context` (:71) — read tx closed → 
  `locations_client.check_npc_gate(character_id, location_id, npc_id)` (`locations_client.py:328`, LS
  `GET /locations/internal/action-gate`, fail-closed 503/403) → `reputation_crud.require_npc_tier`. Endpoints that do HTTP
  are `async` with sync crud in `run_in_threadpool`. Copy exactly for the Captain.

### 2.5 World map / graph

- `LocationNeighbors` (LS `models.py:164`): one row per direction, UNIQUE (location_id, neighbor_id) since 059,
  `energy_cost`, `path_data` JSON, `is_auto_arrow`. **Sea routes must NOT be stored here**: these rows are walkable by
  `move_and_post`/`quick_move` and feed the caravan BFS and the admin graph as land roads.
- Region transitions: `RegionTransitionArrow` (:628, paired arrows), `ArrowNeighbor` (:641, `path_data`);
  `crud.sync_cross_region_neighbors` (LS `crud.py:6692`) materialises N×M `is_auto_arrow` LocationNeighbors. Not reusable
  for sea (it creates walkable edges), but it is the precedent for "admin draws a connector, the graph is derived".
- Admin `/map` (`FE/components/WorldMapPage/WorldMapPage.tsx`, `MapCanvas.tsx`, `EdgeInspector.tsx`, `layout.ts`) is a
  **computed force/packing layout** of the graph (LS `GET /locations/map/graph`, `main.py:2130`, strict admin,
  `crud.get_world_graph` :3222) — not geographic; sea edges could be added there as a distinct edge kind for admins, but it
  is not the player map.
- **Player world map** = `FE/components/WorldPage/WorldPage.tsx` (routes `/world`, `/world/area/:id`, `/world/country/:id`,
  `/world/region/:id`, App.tsx:161-164). At area level `InteractiveMap` renders `FloatingStructuresLayer`
  (`WorldPage.tsx:~889 showFloatingStructures={viewLevel==='area' && ...}`, `InteractiveMap.tsx:63`).
- **Closest analogue for a drawn sea line**: Floating structures (FEAT-123) — LS `FloatingStructure` (`models.py:655`,
  `route_json` list of `{x,y}` in **percent of the area map image**, `area_id`), public `GET /locations/map/floating-structures`
  (`main.py:4262`), admin `/locations/admin/floating-structures`, FE admin `AdminLocationsPage/FloatingRouteEditor.tsx`
  (waypoint editor: click append, shift-click insert, right-click delete, drag; uses area `map_image_url`) +
  `waypointUtils.ts` (pure helpers, reusable), player `WorldPage/FloatingStructuresLayer.tsx` (`interpolatePolyline`
  — could also animate a ship along the line by voyage progress).
- Coordinate frames differ: `Locations.map_x/map_y` are on the region map, `Countries.x/y` on the area map. A sea line on
  the area map therefore has free endpoints (admin draws it to the coast); ports in countries of **different Areas**
  can't be drawn on one image — the route needs an `area_id` like floating structures.
- `Countries.is_hidden` exists; the admin graph filters hidden countries. Public sea routes touching a hidden country —
  decide whether to hide them.

### 2.6 Movement and the voyage arrival analogue

- Player move: LS `POST /locations/{dest}/move_and_post` (`main.py:1427`) and `quick_move` (:1728): ownership →
  `check_not_locked_for_post` → not in battle / gathering → neighbour + stamina + cooldown → `_update_character_location`
  (:323) = CS `PUT /characters/internal/{id}/update_location` (internal token) → stamina, cooldown, battle-pass event,
  `battles/internal/party/leave-on-move`. Note `move_and_post` allows a move to anywhere when `current_location_id` is NULL
  (:~1462) — do not NULL the location during a voyage.
- CS `update_location` (`main.py:2376`): row lock, lock refusal, faction territory refusal, clears `house_room_id`,
  `law_crud.check_entry(..., source)` (guards on entry), commit, then encounter/slip notices.
- **Teleport master** (`crud.execute_teleport`, `crud.py:3848`) — closest analogue of a paid voyage: user's current character,
  row `with_for_update`, lock refusal, same location as the NPC, reputation gate (`npc_gate_failure`/`gate_failure`),
  `faction_territory.location_refusal(target)`, cooldown, `econ_ledger.post_operation(OP_TELEPORT, character → payer_account(source location))`
  (`InsufficientFunds` → 402 `insufficient_gold`), then `current_location_id = target`, `house_room_id=None`,
  `law_crud.check_entry(..., "teleport")` in the same commit, then **after commit** best-effort
  `locations_client.notify_character_left_location_sync` (expire action gates / gate requests in the old location +
  party leave-on-move). Admin/home teleport use the async `_prepare_move` (aborts on cleanup failure).
- **Escort ride analogue**: `move_escorts` — raw UPDATE inside the pass transaction, no cleanup/law/faction checks.
  A voyage arrival in the scheduler is offline-safe like this, but should decide whether the arrival counts as an entry
  (`check_entry` with `SOURCE_TELEPORT`-like source; `law_core.MOVE_SOURCES` :75 lists only move/quick_move — a new source
  constant would be needed) and whether to call `character-left-location` at boarding (gates in the departure port).
- Internal LS endpoints: `GET /locations/internal/action-gate` (:4509), `POST /locations/internal/action-gate/consume` (:4527),
  `POST /locations/internal/cancel-gathering` (:4631), `POST /locations/internal/character-left-location` (:4666).

### 2.7 Economy ledger

- `econ_ledger.post_operation(db, op_type, legs, source_service, location_id|region_id, metadata, idempotency_key, apply_tax)`
  (CS `econ_ledger.py:217`), never commits; raises `InsufficientFunds`, `DuplicateOperation` (idempotency key reused —
  the double-click guard), `EconomyError`.
- Accounts: `AccountRef.character/region/country/purse/world/caravan_escrow` (`econ_core.py:270-310`). Treasuries
  (region/country/world) may go negative (`NEGATIVE_ALLOWED_KINDS` :92) → a boarding refund from a treasury never fails.
- Tax: an inflow `character → region_treasury` automatically gets a `region → country` tax leg (`add_tax_legs`,
  `TAX_SOURCE_KINDS`). Teleport pays `payer_account(location)` = `treasury_for_location` = **region** treasury (else world)
  (`crud.py:2509`, `econ_ledger.py:115`). The brief says "country treasury of the departure port": either
  `AccountRef.country(country_id)` via `econ_ledger.resolve_location` (:105) with `apply_tax=False`, or region treasury +
  auto tax like the teleport — Architect's choice; money is conserved either way.
- Op types: `econ_core.py:111-193` (`OP_TELEPORT="teleport"` :119, caravan set :156-161), `OP_TYPES` (:185) validated in
  `validate_operation` (:517). New ops (fare, refund) must be added to **all four byte-identical `econ_core.py` copies**
  (CS, IS, LS, dungeon-service) — CI guard `scripts/check_econ_copies.sh` (sha256 groups: econ_core ×4,
  `tests/econ_contract_cases.py` ×4, econ_ledger sync CS/IS, async LS/dungeon). `econ_operations.op_type` is `String(50)`
  (models.py:509) — no DB enum. FE label map `FE/components/Admin/EconomyPage/economyLabels.ts:14`.
- An "escrow until departure" would need a new account kind (`ACCOUNT_KINDS`, `SINGLETON_NAMES`) — more econ_core churn;
  paying the treasury immediately and refunding on «Сойти» avoids that.

### 2.8 Channel, notifications, party

- Channel: `econ_caravan_messages` + `caravan_escort_crud.messages` (:560, last 100 / after_id paging) and `post_message`
  (:573, 1..500 chars, 3 s throttle per character, membership = active escort row). FE polls — **no websocket**:
  `FE/components/CaravanEscort/CaravanEscortChannel.tsx` (`POLL_MS=15_000`), `CaravanEscortModal.tsx` (`POLL_MS=30_000`),
  `CaravanEscortRoute.tsx`, API `FE/api/caravanEscort.ts`, types `FE/types/caravanEscort.ts`. Housekeeping deletes
  messages 7 days after the caravan finished (`MESSAGES_KEEP`, `escort_housekeeping` :857).
- Notifications: `law_notify.Notice(user_id, message, ws_type, category, data)` + `law_notify.publish` (sync pika to
  `general_notifications`, best-effort, call **after commit**; `character-service/app/law_notify.py`). notification-service
  stores and forwards `ws_type` as the WS message type; FE `useWebSocket.ts` refreshes `/users/me` for types in
  `LAW_LOCK_REFRESH_TYPES`.
- Party: CS has **no party-service client** (`config.py` has no `PARTY_SERVICE_URL`). Existing lookup used by group actions:
  PS `GET /party/internal/active-members?character_id&location_id` (`party-service/app/main.py:181`, X-Internal-Token) →
  `{party_id, leader_character_id, member_character_ids}` = accepted members co-located at the location (includes the
  caller). BS `_squad_roster` (`battle-service/app/main.py:1219`) + `_free_squadmates` (:1244: skip gathering via LS
  `internal/gathering-status`, in battle, activity-locked) is the exact "who of my squad is free here" logic the party
  ticket purchase needs. Options: add `PARTY_SERVICE_URL` (+ internal token) to CS config/compose, or read
  `party_members`/`parties` (PS tables, `status='accepted'`) directly from the shared DB (precedent: CS reads `battles`,
  `gathering_sessions`, `dungeon_sessions` by raw SQL). PS models: `parties`, `party_members` (status enum invited/accepted).
  PS migration head: `001_initial_party`.

### 2.9 Ownership facts (sea routes / voyages) — not a decision

For character-service:
- It owns `characters` and is the **only writer** of lock columns (`activity_lock.py` docstring); the voyage lock column
  must live there anyway.
- Caravans, escorts, channel, raids, scheduler (`econ_scheduler`/`caravan_pass`), econ params and ledger posting
  patterns (teleport fare) are all CS; stage 2 routing (`RoutePlanner`) runs inside the CS econ tick and already reads LS
  tables (`LocationNeighbors`, `Locations`, `Regions`) by raw SQL.
- NPC roles, Captain resolution, reputation/law/faction gates, `law_notify` are CS.
- CS already has `locations_client` (npc gate, left-location cleanup, cancel gathering).

For locations-service:
- It owns geography (`Locations`, `LocationNeighbors`, arrows, Areas/Countries), the map editors and the floating-structure
  waypoint precedent (`route_json` on the area map, public read endpoint); a per-location `is_port` flag fits
  `Locations` columns + `EditLocationForm`.
- LS is async; moving a character still goes through CS `update_location` (LS never writes `current_location_id`).
- A LS-owned voyage table would need CS to read it for the lock (like LS-owned `asleep_since` is written by LS on
  `characters` — precedent: houses in LS write `asleep_since`/`reading_since`/`house_room_id`, see models.py:72-84) —
  i.e. there IS a precedent of LS writing lock columns on `characters`, contradicting the "CS only writer" note for
  newer columns.
- A hybrid is possible: port flag + route geometry in LS (map data), voyages/tickets/lock/econ in CS reading the LS table
  by raw SQL (like `load_road_graph`).

### 2.10 Alembic heads and conventions

| Service | Head revision | Next |
|---|---|---|
| character-service | `051_caravan_escorts` (`app/alembic/versions/051_caravan_escorts.py`) | `052_...` |
| locations-service | `059_location_neighbor_unique` | `060_...` |
| battle-service | `010_battle_caravan_raid` | (no change expected) |
| inventory-service | `037_stolen_bales` | (no change expected) |
| party-service | `001_initial_party` | (no change expected) |
| user-service | `0035_faction_economy_perm` | only if a new permission |

Conventions: revision id string == file stem, `NNN_slug`, **≤ 32 chars** (alembic_version column limit); per-service
`version_table`; auto-migration on container start; MySQL FK columns need explicit indexes; econ-style tables have no FKs and
BigInteger PKs; new nullable `characters` columns need the deploy-skew fallback in every lock copy (see 2.3). RBAC: existing
permissions `economy:read`/`economy:settings` (caravan admin), `locations:update`/`locations:delete` (map editor).
A new permission requires a user-service migration **and** an explicit seed in `test_rbac_permissions.py` (CLAUDE.md §10.13).

### 2.11 Risks

- **Caravan pass is frozen when the economy tick is off** (`caravan_pass.run_pass` :218). Player voyages must not depend on
  that — a separate pass/claim (like `law_pass`/`faction_pass`, own `*_settings.pass_last_run_at`) is safer.
- **Lock copies**: forgetting a copy or the fallback level breaks CI (byte-identical test) or 500s during deploy skew
  (new column read before CS migration runs). Two explicit `compute_lock` callers (law_crud:555, caravan_escort_public:61).
- **Lock priority**: decide where the voyage sits; a passenger must not be jailed/knocked out at sea (patrol arrival and
  faction eject already skip locked characters).
- **Location semantics during a voyage**: keeping `current_location_id` = departure port makes passengers appear in port
  lists, party rosters (`active-members`) and `caravans_here`; NULL breaks `move_and_post` assumptions. Decide explicitly.
- **Hop-count BFS**: a sea edge = 1 hop; `caravan_route_max_steps` and "shortest" would prefer sea arbitrarily. Weighted
  routing or a separate leg model may be needed; `route` JSON has no per-leg type — sea legs need extra data
  (e.g. parallel `route_legs`/sea-leg indexes) and `step_caravan` needs per-leg duration.
- **Invulnerability**: `caravans_here`, `begin_raid`, `held_by`/post hold, `_preparing_here` all key on
  `current_location_id`/`route_index`; each needs a sea-leg guard. Escorts riding a sea leg go through `move_escorts`.
- **Deletion edge cases**: Locations FKs are `ondelete=CASCADE`; a voyage must snapshot destination ids (no FK) and land
  passengers even if the route/port/location is gone (fallback location needed if the destination location itself was deleted).
- **Forced moves**: `_prepare_move` (admin/home teleport, jail, faction eject) must handle a passenger (release or refuse).
- **Money**: double "Купить" → idempotency key + UNIQUE (voyage, character); party purchase = one op with N legs or N ops —
  partial failure handling; refunds on «Сойти» and on cancelled voyages.
- **World map**: area-image coordinates only; routes across Areas not drawable on one map; hidden countries.
- **Party lookup from CS**: new cross-service dependency (CS → PS) or a raw read of PS tables; update the dependency graph doc.
- CI time: character-service tests already take ~7 min (CI limit raised to 15 min).

---

## 3. Architecture Decision (filled by Architect — in English)

> **v2 (2026-11-16/17).** Ships are real locations. The v1 design («timed voyage» + `voyage` activity lock + port-pair
> routes) is superseded and kept for reference in **Appendix A** at the end of this file. Section 3.18 lists, for every
> piece of the uncommitted v1 work, whether it is kept, changed or reverted. Abbreviations as in section 2. Times are
> naive UTC everywhere (project convention).

### 3.1 Core idea and ownership

A ship = a row in CS `sea_ships` bound 1:1 to an ordinary `Locations` row (the **deck**) and to an NPC (the **Captain**).
Passengers simply stand on the deck (`characters.current_location_id = deck`), so everything a location has — posts, NPCs,
battles, loot, party, gathering — works on board with zero new code. The ship "moves" by changing **its own state**
(docked port / current sea zone), never by moving passengers. The only passenger moves the system makes are «высадить на
берег» (put ashore) at departure and the safe landing in broken-data cases.

| Data / logic | Owner | Why |
|---|---|---|
| Sea geography: `Locations.is_port` (kept from v1), `Locations.is_sea_zone`, `Locations.port_sea_zone_id`; zone adjacency = ordinary `LocationNeighbors` between zones (same region editor, arrows between seas); validations that keep zones/decks off the land graph | **LS** | LS owns `Locations`, neighbours, arrows and the admin location editors. |
| Ships, stops, passes (tickets / sailor jobs / stowaway attempts), sea settings, the **sea pass** (departures, zone stepping, arrivals, Captain placement), put-ashore + law entry check, stowaway crime, fares/refunds, Captain dialogue API, deck header API, ship admin API | **CS** | CS runs the scheduler thread, is the only writer of `characters` positions for system moves (precedent `move_escorts`, patrols move guard NPCs), owns NPC-role flows (Caravaneer/teleport templates), law/shadow, ledger, `law_notify`. |
| Port↔deck passage during a player move + passages in the location page | **LS reads CS tables** (`sea_ships`, `sea_passes`, `sea_ship_stops`) by raw SQL in a new tolerant module `sea_read.py` | Precedent: `faction_read.py` reads CS faction tables for the same purpose (move pre-check + viewer-aware marks), LS `crud.py:173` reads `econ_caravans`. CS re-checks authoritatively in `update_location` under the ship row lock (3.6). |

No new HTTP dependency, no new service, **no activity-lock change** (3.2), no RBAC migration (3.16).

### 3.2 Why there is no `voyage` lock — movement audit (verified in code)

| Way to change a character's location | Code | Effect on a deck / at sea | Guard needed |
|---|---|---|---|
| Move with post / quick move | LS `move_and_post` (`main.py:1495-1515`) and `quick_move` (`:1803-1821`) require a `LocationNeighbors(current → dest)` row (except NULL location) | A deck has **no** neighbour rows (invariant G4) → at sea nobody can step off; the only way on/off is the passage, which exists only while docked | **G1** passage check (LS pre-check + CS authoritative); **G2** a sea zone is never a destination |
| CS `update_location` (called by both moves) | `main.py:2399-2470` | the authoritative point for G1/G2 | G1/G2 under ship-row lock |
| Teleport master | `crud.execute_teleport` (`crud.py:~3848`): character must stand next to the teleport NPC; target = the link's target | A deck/zone as a teleport **target** would be a back door onto a ship at sea | **G3**: refuse deck/zone targets at link creation (`create_teleport_link`) and at execution |
| Home teleport scroll | `main.py:1073` (IS → CS internal) | Leaving a deck by scroll is allowed on purpose (magical escape; the player only loses his ride). Target is the house location — a deck/zone target is refused by G3 (houses could in theory be placed on a deck plot) | G3 on the target |
| Admin move | `main.py:988` (`characters:teleport`) | Allowed onto/off a deck (moderation). A sea zone target is refused (nobody may stand in a zone) | G2 for zones only |
| Faction eject | `faction_territory.eject` → `pick_target` = neighbours / HQ / station | Only from a closed location; a deck has no neighbours, HQ/station are land | none |
| Jail / law encounter | `law_crud._check` needs live guards **at the location** (`guards_at`); `send_to_jail` comes from an encounter | No guards on decks (patrols walk `LocationNeighbors`, `patrol_crud.neighbours_of`, never reach a deck) | none |
| Patrol guard moves | `patrol_crud.py:272` over neighbours | never reaches a deck | none |
| Caravan escorts | `move_escorts` along caravan roads (land BFS) | sea zones are a separate component of the graph (G4) | none |
| Dungeon knock-out return | `main.py:4508` returns to the dungeon's location | unrelated | none |
| Gathering / battles / party / dungeon entry | all key on co-location | work on deck as on any location (desired) | departure handles busy characters (3.9) |

Guards: **G1** deck entry/exit only through the passage of a docked ship (rights for entry); **G2** sea zones are never a
destination of any move (LS moves, CS `update_location`, admin move, teleports); **G3** teleport targets (teleport links,
home teleport) can't be a deck or a zone; **G4** graph separation: a deck has no `LocationNeighbors`/arrow links, a zone links
only to zones (LS refuses mixed links; `sync_cross_region_neighbors` skips mixed pairs). G4 alone keeps zones out of caravan
BFS (`economy_caravan_crud.load_road_graph` — BFS from land gates never reaches a disconnected component), patrols and faction
eject. The admin world graph already drops hidden countries (`crud.get_world_graph`, `Country.is_hidden`) — plus an explicit
`is_sea_zone` filter as defence.

### 3.3 Data model

#### LS migration `060_sea_zones` — rewrite of the unshipped `060_sea_routes` (revision id 13 chars; down_revision `059_location_neighbor_unique`)

```sql
ALTER TABLE Locations ADD COLUMN is_port TINYINT(1) NOT NULL DEFAULT 0;            -- kept from v1
CREATE INDEX ix_locations_is_port ON Locations (is_port);
ALTER TABLE Locations ADD COLUMN is_sea_zone TINYINT(1) NOT NULL DEFAULT 0;        -- a sea zone (hidden «Моря» country)
CREATE INDEX ix_locations_is_sea_zone ON Locations (is_sea_zone);
ALTER TABLE Locations ADD COLUMN port_sea_zone_id BIGINT NULL;                     -- the zone a port opens to
CREATE INDEX ix_locations_port_sea_zone ON Locations (port_sea_zone_id);           -- explicit FK index (MySQL gotcha)
ALTER TABLE Locations ADD CONSTRAINT fk_locations_port_sea_zone
  FOREIGN KEY (port_sea_zone_id) REFERENCES Locations(id) ON DELETE SET NULL;
-- NO sea_routes table (v1 dropped)
```
Rollback: drop FK, indexes, the three columns.

#### CS migration `052_sea_ships` — rewrite of the unshipped `052_sea_voyages` (revision id 13 chars; down_revision `051_caravan_escorts`)

Econ-style tables: `_EconId` BigInteger PKs, **no FKs** (decks/ports/NPCs/characters may disappear; names are snapshotted
where shown later). **No `characters` column, no `econ_caravans` columns.**

```sql
CREATE TABLE sea_ships (
  id               BIGINT PK AUTO_INCREMENT,
  name             VARCHAR(100) NOT NULL,
  captain_npc_id   INT NULL,                  -- characters.id (is_npc, npc_role 'captain'); NULL = no captain
  deck_location_id BIGINT NOT NULL,           -- Locations.id, the deck
  capacity         INT NOT NULL DEFAULT 10,   -- passenger seats (tickets) per trip, 0..200
  crew_slots       INT NOT NULL DEFAULT 2,    -- sailor jobs per trip, 0..20 (0 = no hiring)
  boarding_minutes INT NOT NULL DEFAULT 30,   -- «сборы» at every stop, 1..1440
  zone_minutes     INT NOT NULL DEFAULT 10,   -- time per sea zone, 1..1440
  fare_base        INT NOT NULL DEFAULT 10,   -- ticket = fare_base + fare_per_zone × zones of the covered legs
  fare_per_zone    INT NOT NULL DEFAULT 5,
  is_loop          TINYINT(1) NOT NULL DEFAULT 0,   -- 0 = there and back along the line (default), 1 = circle
  is_active        TINYINT(1) NOT NULL DEFAULT 1,
  -- state (written only by sea_crud / sea_pass, under the ship row lock)
  status           VARCHAR(10) NOT NULL DEFAULT 'docked',   -- docked | sailing
  stop_index       INT NOT NULL DEFAULT 0,    -- docked: at stops[stop_index]; sailing: the stop it left
  next_stop_index  INT NULL,                  -- sailing: the stop it heads to
  direction        TINYINT NOT NULL DEFAULT 1,              -- +1 / -1 (there-and-back)
  trip_no          INT NOT NULL DEFAULT 0,    -- departures made; the NEXT departure is trip_no + 1
  docked_port_id   BIGINT NULL,               -- docked: the port location (LS reads it), NULL at sea
  next_port_id     BIGINT NULL,               -- sailing: the destination port (snapshot)
  current_zone_id  BIGINT NULL,               -- sea zone Locations.id (docked = the port's zone)
  leg_path         JSON NULL,                 -- sailing: zone ids of the current leg (snapshot at departure)
  leg_pos          INT NOT NULL DEFAULT 0,    -- index into leg_path
  departs_at       DATETIME NULL,             -- docked & active: planned departure
  next_zone_at     DATETIME NULL,             -- sailing: when it enters the next zone / arrives
  last_port_id     BIGINT NULL,               -- last port it was docked at (safe-landing fallback)
  blocked_reason   VARCHAR(64) NULL,          -- why it can't depart (admin display): no_path | no_valid_stop | no_deck
  created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
  UNIQUE KEY uq_sea_ships_deck (deck_location_id),
  UNIQUE KEY uq_sea_ships_captain (captain_npc_id),            -- NULLs repeat
  INDEX ix_sea_ships_depart (status, departs_at),
  INDEX ix_sea_ships_sail (status, next_zone_at),
  INDEX ix_sea_ships_port (docked_port_id),
  INDEX ix_sea_ships_zone (current_zone_id)
);

CREATE TABLE sea_ship_stops (                 -- the line of ports, ordered
  id               BIGINT PK AUTO_INCREMENT,
  ship_id          BIGINT NOT NULL,
  idx              INT NOT NULL,              -- 0..n-1
  port_location_id BIGINT NOT NULL,
  path_override    JSON NULL,                 -- manual zone ids for the leg stops[idx] -> stops[idx+1]
                                              -- (for a loop, the last stop's override = last -> first);
                                              -- the reverse leg of there-and-back uses it reversed
  UNIQUE KEY uq_sea_ship_stops (ship_id, idx),
  INDEX ix_sea_ship_stops_port (port_location_id)
);

CREATE TABLE sea_passes (                     -- the right to be aboard: ticket / sailor job / stowaway attempt
  id                 BIGINT PK AUTO_INCREMENT,
  ship_id            BIGINT NOT NULL,
  character_id       INT NOT NULL,
  kind               VARCHAR(10) NOT NULL,    -- ticket | sailor | stowaway
  first_trip         INT NOT NULL,            -- trip numbers covered (inclusive); sailor/stowaway: first = last
  last_trip          INT NOT NULL,
  from_port_id       BIGINT NOT NULL,         -- snapshots for display
  to_port_id         BIGINT NOT NULL,
  from_name          VARCHAR(255) NULL,
  to_name            VARCHAR(255) NULL,
  zones              INT NOT NULL DEFAULT 0,  -- zones of the covered legs (price basis)
  fare               BIGINT NOT NULL DEFAULT 0,
  fare_op_id         BIGINT NULL,             -- econ_operations.id (sea_fare)
  refund_op_id       BIGINT NULL,             -- econ_operations.id (sea_refund)
  post_floor_id      BIGINT NULL,             -- sailor: MAX(posts.id) when hired; only later posts count
  status             VARCHAR(12) NOT NULL,    -- active | completed | burnt | ashore | caught | refunded | expired
  created_at DATETIME NOT NULL, ended_at DATETIME NULL,
  INDEX ix_sea_passes_ship (ship_id, status, first_trip),
  INDEX ix_sea_passes_char (character_id, status)
);

CREATE TABLE sea_settings (
  id INT PK,                                   -- seeded row id = 1
  pass_last_run_at       DATETIME NULL,        -- the sea pass claim
  sailor_post_min_chars  INT NOT NULL DEFAULT 800,       -- 300..20000 (post length after stripping HTML)
  stowaway_base_pct      DECIMAL(5,2) NOT NULL DEFAULT 60, -- crew notice base chance, 0..100
  stowaway_wanted_points INT NOT NULL DEFAULT 50,        -- 1..1000 wanted points of a caught stowaway
  path_max_zones         INT NOT NULL DEFAULT 200        -- BFS limit per leg, 10..1000
);
INSERT INTO sea_settings (id) VALUES (1);
```
Rollback: drop the 4 tables. Pass statuses: `active` (valid), `completed` (ride done / ended by admin route change),
`burnt` (ticket holder not aboard at departure — no refund), `ashore` (sailor who didn't work, put ashore), `caught`
(stowaway caught), `refunded` (ship removed/deactivated/route changed before the pass started), `expired`
(sailor/stowaway holder not aboard at departure).

### 3.4 Ship state machine, trips, legs (pure `sea_core.py`, no DB)

- **Stop sequence.** `stops = [p0 … pn-1]`, n ≥ 2. There-and-back (default): 0,1,…,n-1,n-2,…,0,1,… (direction flips at the
  ends). Loop: 0,1,…,n-1,0,1,… `next_stop(i, direction, n, is_loop) -> (j, new_direction)`;
  `future_stops(ship, count) -> [(trip_no, from_idx, to_idx)]` starting from the next departure (docked: from `stop_index`;
  sailing: from `next_stop_index`).
- **Trips.** Every departure increments `trip_no` (trip k = the k-th departure, from one stop to the next). The next
  departure is always `trip_no + 1`. A pass covers trips `first_trip..last_trip`.
- **Leg path.** Zones from `port_sea_zone_id(from)` to `port_sea_zone_id(to)` inclusive: manual override if set and valid
  (first/last = those zones, consecutive ids adjacent, all `is_sea_zone`), else BFS over zone-only adjacency — reuse
  `caravan_route.build_adjacency` + `caravan_route.shortest_route(adj, blocked=set(), start, goal, max_steps=path_max_zones)`
  (deterministic, ascending ids) on the edges `SELECT location_id, neighbor_id FROM LocationNeighbors` restricted to
  `Locations.is_sea_zone = 1` ids. Same zone for both ports → path `[z]`. Leg duration = `len(path) × zone_minutes`.
  The path is computed **at departure** and snapshotted in `leg_path` (admin graph edits affect later legs only);
  the Captain dialogue/editor compute it on the fly for prices/ETAs.
- **States.**
  - `docked` at `stop_index`: `docked_port_id = stops[stop_index]`, `current_zone_id` = that port's zone, `departs_at` set
    while active (NULL while inactive), Captain stands in the port, passage open.
  - `sailing` from `stop_index` to `next_stop_index`: `docked_port_id = NULL`, `next_port_id` snapshot, `leg_path`,
    `leg_pos`, `current_zone_id = leg_path[leg_pos]`, `next_zone_at`; Captain stands on the deck; no passage.
- **ETA** (for the dialogue): docked → `departs_at + Σ legs × zone_minutes + boarding_minutes × (intermediate stops)`;
  sailing → `next_zone_at + (len(leg_path) − leg_pos − 1) × zone_minutes` for the current leg, then as above.
- **Fare** of a ticket for trips `k0..k1` = `fare_base + fare_per_zone × Σ len(leg_path)` of those legs (≥ 0).

### 3.5 Passes (boarding rights)

| Kind | Gives | Cost | Trips | Seats | Check at departure |
|---|---|---|---|---|---|
| `ticket` | passage to the deck while docked + staying aboard | fare (3.11) | `first_trip = trip_no+1` … `last_trip` = the trip arriving at the chosen stop (any of the next `n−1` stops of the sequence) | `capacity`: for every trip t in the range, `count(active tickets covering t) < capacity` | holder aboard → sails; not aboard → `burnt` (no refund, «сам виноват») |
| `sailor` | passage + staying aboard for **one** trip (`trip_no+1`) | free | one | `crew_slots` per trip | holder aboard **and** has a post on the deck with `posts.id > post_floor_id` and plain length ≥ `sailor_post_min_chars` (the boarding post counts) → sails; aboard without such a post → put ashore, status `ashore` (no crime); not aboard → `expired` |
| `stowaway` | passage (an attempt to sneak in) for one trip | free | one | not counted | holder aboard → stealth roll vs crew (3.9): not caught → sails free; caught → crime + put ashore, status `caught`; not aboard → `expired` |

- One **active** pass per character per ship covering a given trip (a second purchase/hire → 409 «У вас уже есть место на
  этом рейсе»). A ticket bought while aboard at sea (from the Captain on deck) starts at the next departure (from the next
  stop) — this is «оплатить следующий участок не сходя на берег».
- At arrival of trip k every active pass with `last_trip == k` → `completed`; the holder, if still aboard at the next
  departure without a new pass, is put ashore (3.9).
- At departure of trip k every active pass covering k whose holder is **not** on the deck → `burnt` (ticket) / `expired`
  (sailor, stowaway). This also burns the rest of a multi-stop ticket of someone who walked off at an intermediate stop.
- Entitlement for the passage (LS) and for staying aboard (CS) = `kind IN (ticket,sailor,stowaway) AND status='active' AND
  first_trip <= k <= last_trip` with `k = trip_no + 1` (docked ship).

### 3.6 Port ↔ deck passage (G1)

- Exists only while the ship is `docked` (and its deck exists). **Board**: from `docked_port_id` to the deck, requires
  `is_active = 1` and an entitled pass for `trip_no + 1`. **Disembark**: from the deck to `docked_port_id`, anyone (no right
  needed, also when the ship is inactive).
- It is **not** a `LocationNeighbors` row: caravans, patrols, faction eject, admin graph never see it.
- Move cost: `PASSAGE_ENERGY_COST = 0` (named constant in LS `sea_read.py`) → no stamina, no travel cooldown. Only by a
  **post** (`move_and_post`); `quick_move` refuses passages («На борт и на берег сходят только постом»). Post-intent rules,
  faction location access (a faction ship later), `check_entry` with guards in the port — all as for a normal move.
- **LS pre-check** (`move_and_post`, before the post is created): when no neighbour row exists, `sea_read.passage(session,
  character_id, current, dest)` → `None` (not a passage → the old 400 «Целевая локация не является соседней», or
  «Корабль в море — сойти на берег нельзя» when `current` is a deck at sea) | `(allowed=True)` → `movement_cost = 0` |
  `(allowed=False, refusal)` → 403 («Нужен билет, место матроса или попытка пробраться зайцем — поговорите с капитаном» /
  «Корабль выключен — посадки нет»). A sea-zone destination → 400 «В открытое море не выйти» (both moves; G2).
- **CS authoritative check** (`update_location`, `main.py:2399`), with the **lock order ship → character**:
  1. read `current_location_id` without a lock; `sea_crud.lock_ships_for_move(db, current, new)` =
     `SELECT … FROM sea_ships WHERE deck_location_id IN (:cur, :new) ORDER BY id FOR UPDATE`;
  2. lock the character (existing line); if its `current_location_id` changed meanwhile → 409 «Попробуйте ещё раз»;
  3. `sea_crud.move_refusal(db, character, current, new, ships)` → text or None: new is a zone → «В открытое море не выйти»;
     new is a deck → ship docked at `current`, active, entitled → else «Корабль уже отплыл» / the LS texts; current is a deck
     and new ≠ current → ship docked and `new == docked_port_id` → else «Корабль в море — сойти на берег нельзя».
     Refusal → rollback, 409.
  This closes the race «boarding post vs departure» (the departure holds the same ship lock, 3.9).
- **Location page** (LS `get_client_location_details`): neighbours get passage entries (built by `sea_read.passages_for`):
  in a port, for each docked active ship where the **viewer** (`viewer_character_id`, already resolved for FEAT-207 marks)
  is entitled: `{id: deck, name: "Корабль «{name}»", image_url: deck image, recommended_level, energy_cost: 0,
  passage: "board", ship_id, access_label: null, access_allowed: true}` — invisible to everyone else (brief: only those with
  a right see it); on a deck of a docked ship: `{id: port, name, …, energy_cost: 0, passage: "disembark", ship_id}` for any
  viewer. Top-level additions: `is_sea_zone: bool`, `ship_id: Optional[int]` (this location is a deck), `docked_ships:
  [{id, name}]` (public «У причала: …» in a port). Reads are tolerant: missing CS tables (deploy skew / tests) → no passages,
  `ship_id = null`, `docked_ships = []` with one WARNING (pattern of `faction_read._rows`).

### 3.7 Captain flows (CS `sea_crud.py`, `sea_api.py`, `sea_schemas.py`)

- `CAPTAIN_ROLE = "captain"` (backend constant in `sea_core.py`; FE `constants/npc.ts` `{value:'captain', label:'Капитан'}`,
  icon ⚓). A Captain is bound to at most one ship (`uq_sea_ships_captain`). No role-change side effects (no hook in
  `main.py:3317-3350`): if a bound Captain loses the role, dies or is deleted, the ship shows «капитана нет» (sales closed)
  until the admin binds another Captain; the ship keeps its schedule, nobody is stranded.
- **Captain context** (template `caravan_escort_api._caravaneer_context`): owner + player character (404/403) → NPC exists,
  `is_npc`, role `captain`, `npc_status != 'dead'`, not knocked out, bound to a ship (404 «Капитан не найден» /
  «Этот капитан сейчас без корабля») → the character stands at the Captain's location (400 «Нужно находиться рядом с
  капитаном»). In port (docked) the Captain is in the port; at sea he is on the deck — so the same rule covers «купить в
  порту» and «оплатить следующий участок на палубе». For **ticket / sailor** additionally (read tx closed first):
  `locations_client.check_npc_gate` (FEAT-145 «Диалог с НПС», fail-closed 503/403, caravaneer texts) →
  `reputation_crud.require_npc_tier`. The **view** needs only presence (so the modal opens and shows the dialogue hint).
- **Eligibility** for a pass (order, Russian texts): activity lock → `activity_lock.lock_message`; ship inactive / no next
  leg (no path / no valid stop) → 409 «Корабль сейчас не ходит»; already an active pass covering the next trip → 409.
  (Teleport parity: no wanted check; battle/gathering do not matter — the passage move itself refuses them.)
- **Ticket purchase** (`buy_ticket(db, ctx, ship_id, to_trip)`, no commit; caller commits, then publishes notices). Lock
  order **ship → passes → character**: lock ship; recompute `future_stops` and the legs (refuse a `to_trip` outside the
  next `n−1` trips); seats for every covered trip; INSERT pass (`kind=ticket`, snapshots, `zones`, `fare`), flush; post
  `OP_SEA_FARE` (3.11) with idempotency key `sea_fare:{pass_id}`, store `fare_op_id`; `InsufficientFunds` → rollback → 402
  `{"error":"insufficient_gold","message": insufficient_funds_message(db),"required":fare,"balance":b}`;
  `CharacterLog(event_type='sea')`. Double click: serialized on the ship lock → second request 409.
- **Sailor job** (`hire_sailor`): same context + gate; `crew_slots` for `trip_no+1`; INSERT pass `kind=sailor`,
  `post_floor_id = SELECT COALESCE(MAX(id),0) FROM posts` (raw read of the LS table; ids avoid any timezone question).
- **Stowaway attempt** (`sneak(db, character_id, ship_id)`): no Captain dialogue gate, no reputation gate; the character must
  stand in the ship's `docked_port_id` (or already on its deck); ship docked and active; INSERT pass `kind=stowaway` for
  `trip_no+1`. The response is neutral («Вы пытаетесь незаметно пробраться на борт»). Shown in the Captain modal as the
  third option (as the brief says), but the endpoint is per ship, not per Captain.
- No cancellation/refund by the player (burnt = «сам виноват»; brief).

### 3.8 The sea pass (CS `sea_pass.py`)

- Called from `econ_scheduler.run_scheduled_once` right after `run_faction_pass` via `run_sea_pass(factory)` (logs and
  swallows). Like law/faction passes it runs **even when the economy tick is switched off in the DB**. Own throttle:
  conditional UPDATE claim on `sea_settings.pass_last_run_at`, `RUN_INTERVAL_SECONDS = 25` (every 60 s poll runs it).
  Missing table/row (skew) → `None`. Tests: `run_pass(factory, now=..., force=True)`.
- One short transaction **per ship** (failures logged, retried next pass). Per ship, in order:
  1. **Sanity**: deck location missing → safe landing of anyone whose `current_location_id` is the old deck id (3.10),
     `is_active = 0`, `blocked_reason = 'no_deck'`.
  2. **Docked & active & `departs_at <= now`** → departure (3.9).
  3. **Sailing & `next_zone_at <= now`** → step: `leg_pos += 1`; if `< len(leg_path)` → `current_zone_id`,
     `next_zone_at += zone_minutes` (loop while still due — offline catch-up, bounded by the path length); else arrival (3.10).
  4. **Captain placement**: if the Captain exists, is an alive NPC and stands somewhere else than expected (docked → 
     `docked_port_id`, sailing → deck) → `UPDATE characters SET current_location_id` (admin manual moves are reverted; a log
     line). Missing/dead Captain → nothing (sales closed, the ship still sails).
- Notices: `law_notify.Notice(user_id, text, ws_type="sea", category=CATEGORY_PROGRESS, data={"character_id","ship_id",
  "event"})`, published **after** commit.

### 3.9 Departure (trip k = trip_no + 1)

1. Lock ship. Next stop + leg path (3.4); no valid next stop / no path → stay docked, `blocked_reason` set, `departs_at`
   unchanged (retried every pass; admin sees it). Invalid next stops are skipped as in 3.10.
2. Lock active passes covering k, then the player characters standing on the deck (`is_npc = 0`, ascending id,
   `FOR UPDATE`).
3. For each character on the deck: entitled ticket → stays; sailor pass → stays if the sailor post exists (posts read:
   `SELECT content FROM posts WHERE character_id=:c AND location_id=:deck AND id > :floor`, plain length via the same regex as
   LS `crud.strip_html_tags`, copied as `sea_core.plain_length`), else `ashore`; stowaway pass → **roll** (below);
   nothing → put ashore. A character **in an active battle** (raw SQL like `caravan_escort_crud._in_battle`) is never moved:
   he stays aboard this trip (a battle bound to the deck must stay resolvable; known minor gap, logged).
4. **Stowaway roll** (FEAT-199/201 machinery): `info = law_crud.stealth_info(db, cid)`, `masked = shadow_crud.wears_mask`,
   `fame = shadow_crud.fame_witness_pct(...)` (0 if masked), `chance = shadow_core.member_chance(stowaway_base_pct,
   info.reduction_pct, masked, fame)` clamped to `law_settings.detect_min_pct..detect_max_pct`;
   `caught, roll = law_core.roll_succeeds(chance, law_crud.detection_rng())`. Not caught → sails, pass stays `active` (no
   record of a crime). Caught → pass `caught`; crime `law_core.CRIME_STOWAWAY = "stowaway"` (new constant; `crime_type` is a
   free String(30)) in the **port's region** with `points = stowaway_wanted_points`, `event_key =
   f"law:stowaway:{pass_id}"`, `location_id = port`, witness snapshot (`witness_chance_pct`, `witness_roll_pct`,
   `stealth_reduction_pct`): not masked → `register_crime(status=CRIME_REPORTED)` (wanted at once); masked →
   `register_crime(status=CRIME_MASKED, reveal_until, next_roll_at)` + `shadow_crud.add_suspicion(..., suspicion_masked)` —
   exactly the single-member branch of `shadow_crud.npc_kill_consequences`; then put ashore.
5. **Put ashore** (`sea_crud.put_ashore(db, ch, port_id, reason)`): `current_location_id = port` (fallback 3.10 when the
   port vanished), `house_room_id = NULL`, `CharacterLog(event_type='sea')`, `law_crud.check_entry(db, ch, port,
   law_core.SOURCE_VOYAGE, from_location_id=deck)` in the same transaction (a caught stowaway may meet the guards at once).
   After commit, best effort: `locations_client.notify_character_left_location_sync(cid, deck)` (expires gates on the
   deck + party leave-on-move) and LS cancel-gathering for anyone who was gathering on the deck (async client run like the
   faction pass runs async ejects); encounter/slip notices like `execute_teleport`.
6. Burn/expire passes covering k whose holder is not on the deck (3.5).
7. Ship → `sailing`: `trip_no = k`, `next_stop_index`, `direction`, `next_port_id`, `leg_path`, `leg_pos = 0`,
   `current_zone_id = leg_path[0]`, `next_zone_at = now + zone_minutes`, `last_port_id = docked_port_id`,
   `docked_port_id = NULL`, `departs_at = NULL`, `blocked_reason = NULL`; Captain → deck.
8. Notices: sailing passengers «Корабль «X» отплыл из {порт}. Следующая остановка — {порт}, прибытие ≈ через N мин»; put
   ashore «Корабль «X» отплыл без вас: вас высадили в {порт} (нет билета на этот рейс)»; sailor «Капитан высадил вас: вы не
   отработали матросом (нужен пост на палубе от N символов)»; caught «Команда корабля «X» поймала вас без билета и высадила в
   {порт}»; burnt «Корабль «X» ушёл без вас — билет сгорел».

### 3.10 Arrival, invalid stops, safe landing

- **Arrival** at `next_stop_index` whose port is still valid (`Locations` row exists, `is_port = 1`, zone set): `status =
  docked`, `stop_index = next_stop_index`, `docked_port_id`, `current_zone_id` = its zone, `departs_at = now +
  boarding_minutes` (NULL if inactive), `leg_path = NULL`, Captain → port. Passes with `last_trip == trip_no` → `completed`.
  Notices to players on the deck: «Корабль «X» прибыл в {порт}»; to holders of completed passes still aboard:
  «Ваш билет до {порт} использован. Чтобы плыть дальше, купите новый у капитана до отплытия, иначе вас высадят».
  Players stay on the deck (they leave by a post). Players in battle / unconscious on the deck: nothing happens to them.
- **Invalid next stop** (deleted by a region cascade, unflagged by bypassing LS, zone lost): skip it — take the following
  stop of the sequence and compute a path from the current zone; tickets ending at the skipped stop end at the real arrival
  (their holders simply get there). If **no valid stop exists at all** → **safe landing**.
- **Safe landing** (`sea_crud.safe_land(db, ship, reason)`): every player on the deck → put ashore (no law check when the
  target is a fallback, still `house_room_id = NULL`) to the first existing of: the docked/last valid port of the ship →
  any valid stop of the ship → the default starting location (`SELECT id FROM Locations WHERE is_starting = 1 ORDER BY id
  LIMIT 1`); not-started passes refunded; `is_active = 0`, `blocked_reason`. Used also when the deck vanished (1. in 3.8).
- **Deactivate** (`is_active = 0`): docked → stays docked forever (disembark open, boarding closed); sailing → finishes the
  leg, docks, stays. All passes not yet started (`first_trip > trip_no`) → `refunded`; started ones stay valid until they
  end. **Reactivate** → `departs_at = now + boarding_minutes`.
- **Delete ship** (admin): only when docked (409 «Корабль в море — выключите его и дождитесь швартовки»). Everyone on the
  deck → put ashore to the docked port; not-started passes refunded; started ones `completed`; stops + ship row deleted
  (passes kept as history). The deck location stays (admin deletes it in the locations admin if wanted).
- **Stops edited** (admin, only while docked; the docked port must remain in the new list → its first index becomes
  `stop_index`): not-started passes `refunded`, started ones `completed` (holders must buy again; rare admin action).

### 3.11 Economy

- Ops (T4 of v1, kept): `OP_SEA_FARE` (character → `payer_account(db, from_port_id)` = the **departure port's region
  treasury** (else «Казна Скитальцев»), automatic region → country tax leg — exactly the teleport) and `OP_SEA_REFUND`
  (reverse every posting of `fare_op_id`, untaxed, `leg_type = LEG_REFUND`, key `sea_refund:{pass_id}`; `DuplicateOperation`
  = already refunded). Treasuries may go negative → a refund never fails. Refunds happen only on admin actions
  (deactivate / delete / stops edited) and safe landing — never on a player's choice.
- The comment above `OP_SEA_FARE` in the 4 `econ_core.py` copies is updated to the v2 wording (byte-identical in all four;
  `scripts/check_econ_copies.sh`). Contract cases unchanged.
- FE `economyLabels.ts`: `sea_fare: 'Корабль: билет'`, `sea_refund: 'Корабль: возврат билета'`.

### 3.12 Admin validations

**LS (locations admin):**
- `is_sea_zone = true` (create/update): the location's country is hidden (409 «Морские зоны создаются в скрытой стране
  (например, «Моря»)»), not `is_port`, not `is_starting`, not a deck (`sea_read`), every existing neighbour is a zone
  (409 «Морские зоны соединяются только с морскими зонами»). `is_sea_zone = false` on a zone that still has neighbours or is
  some port's `port_sea_zone_id` → 409.
- `port_sea_zone_id`: must be an `is_sea_zone` location (409), only on `is_port` locations (cleared when `is_port` → false).
- `is_port = false` / location delete: refused while any `sea_ship_stops.port_location_id` references it (409 «Порт входит в
  маршрут корабля «{name}»») — replaces the v1 sea-route check. Deleting a deck location → 409 «Это палуба корабля
  «{name}» — сначала удалите корабль». Deleting a zone used as `port_sea_zone_id` → allowed (FK SET NULL; ships skip
  that port until fixed).
- Neighbour create/update (`POST /{id}/neighbors/`, `POST /{id}/neighbors/update`, `PUT …/path`, cost patch untouched):
  a deck on either side → 409 «Палуба корабля не соединяется переходами»; zone ↔ non-zone → 409. Arrow neighbour create
  (`POST /arrows/{id}/neighbors/`) with a deck → 409; `crud.sync_cross_region_neighbors` skips (and logs) zone ↔ non-zone
  pairs and decks.
- `get_world_graph` also drops `is_sea_zone` locations (defence; the hidden country already drops them).
- The admin locations tree already shows hidden countries (`/locations/admin/data`, `/countries/list`) — sea zones are
  created there (country «Моря» with `is_hidden`, regions = seas, standalone locations = zones, adjacency in the region
  editor, arrows between seas).

**CS (ship admin):** name 1..100; deck exists, in a hidden country, not a zone/port, no `LocationNeighbors` either way and no
`arrow_neighbors` row, not bound to another ship (409s); deck immutable after creation; Captain (optional) is an NPC with
role `captain`, alive, not bound elsewhere; stops 2..30, consecutive stops differ, each `is_port` with a zone; every leg
(incl. last→first for a loop) resolvable — override valid or BFS path found (409 «Нет морского пути между «A» и «B»
(участок N)»); numbers in the ranges of 3.3. Create → `docked` at stop 0, `departs_at = now + boarding_minutes`, Captain
moved to the port in the same transaction. Teleport links (`crud.create_teleport_link`) refuse a deck or zone target (G3).

### 3.13 API contracts

All CS player endpoints: JWT (`get_current_user_via_http`) + owner; Pydantic v1; Russian `detail`. Router `sea_router`
(prefix `/characters`, static `/sea/...` paths) included in `main.py` **before** the main router. Admin:
`require_permission("locations:read"|"locations:create"|"locations:update"|"locations:delete")` (3.16).

#### CS player

| # | Method / path | Notes |
|---|---|---|
| S1 | `GET /characters/sea/captain/{npc_id}?character_id=` | presence only → `CaptainViewOut` |
| S2 | `POST /characters/sea/ships/{ship_id}/tickets` `{character_id, npc_id, to_trip}` | async; context + gate + tier → 201 `PassOut`; 402 insufficient |
| S3 | `POST /characters/sea/ships/{ship_id}/sailor` `{character_id, npc_id}` | async; context + gate + tier → 201 `PassOut` |
| S4 | `POST /characters/sea/ships/{ship_id}/stowaway` `{character_id}` | presence in the docked port / on the deck → 201 `{message}` (neutral) |
| S5 | `GET /characters/sea/decks/{location_id}?character_id=` | the deck header → `DeckViewOut`; 404 when the location is not a deck |

```
CaptainViewOut { npc_id, ship: ShipPublic, balance: int,
                 destinations: [{ to_trip, stop_index, port_id, port_name, region_name, country_name,
                                  zones, fare, eta: datetime, seats_left: int, can_buy: bool, reason: Optional[str] }],
                 sailor: { slots_left: int, min_chars: int, can_hire: bool, reason: Optional[str] },
                 stowaway: { can_try: bool, reason: Optional[str] },        # only where the ship is docked here / on deck
                 my_passes: [PassOut] }
ShipPublic { id, name, captain: Optional[{id, name, avatar}], deck_location_id, status: 'docked'|'sailing', is_active,
             docked_port: Optional[{id, name}], next_port: Optional[{id, name}],
             current_zone: Optional[{id, name, sea_name}],                # sea_name = the zone's region name
             departs_at: Optional[datetime], arrives_at: Optional[datetime],
             stops: [{index, port_id, port_name}], direction: int, is_loop: bool, server_now: datetime }
PassOut { id, ship_id, kind, status, first_trip, last_trip, from_port_id, from_name, to_port_id, to_name, fare,
          created_at, valid_now: bool }
DeckViewOut { ship: ShipPublic, ships_nearby: [{id, name}],     # sailing: same current_zone_id; docked: same port
              passengers_count: int, my_passes: [PassOut] }      # my_passes of character_id (owner-checked)
```
Errors: 404 captain/ship/character; 400 not next to the captain / not in the port; 403 owner / dialogue gate / reputation;
409 «Корабль сейчас не ходит», «У вас уже есть место на этом рейсе», «Мест нет», «Мест для матросов нет», lock text, bad
`to_trip`; 402 insufficient (object detail); 503 gate unavailable.

#### CS admin (prefix `/characters/admin/sea`)

| # | Method / path | Permission | Request → Response |
|---|---|---|---|
| A1 | `GET /ships` | `locations:read` | → `ShipAdminOut[]` (state, captain/deck names, stops with names, legs summary, `passengers_count`, `blocked_reason`) |
| A2 | `POST /ships` | `locations:create` | `ShipCreate` → 201 `ShipAdminOut` |
| A3 | `PATCH /ships/{id}` | `locations:update` | `ShipUpdate` (all optional; `deck_location_id` not accepted; `stops` only while docked) → `ShipAdminOut` |
| A4 | `DELETE /ships/{id}` | `locations:delete` | → 204; 409 while sailing |
| A5 | `POST /legs/preview` | `locations:read` | `{stops: [StopIn], is_loop}` → `[{index, from, to, zones: [{id,name}], minutes_per_zone_hint, override: bool, ok: bool, problem: Optional[str]}]` |
| A6 | `GET /candidates` | `locations:read` | → `{decks: [{id, name, region_name, country_name}], captains: [{id, name, avatar, location_name}]}` (free ones; the edited ship's own may be passed via `?ship_id=`) |
| A7 | `GET /settings`, `PUT /settings` | `locations:read` / `locations:update` | `SeaSettings {sailor_post_min_chars, stowaway_base_pct, stowaway_wanted_points, path_max_zones}` |

```
ShipCreate { name, captain_npc_id: Optional[int], deck_location_id: int, capacity=10, crew_slots=2, boarding_minutes=30,
             zone_minutes=10, fare_base=10, fare_per_zone=5, is_loop=False, is_active=True, stops: List[StopIn] (2..30) }
StopIn     { port_location_id: int, path_override: Optional[List[int]] (1..path_max_zones ids) }
```

#### LS

| # | Method / path | Change |
|---|---|---|
| L5 | `GET /locations/admin/sea-ports` (`locations:read`) | **kept from v1**, rows gain `port_sea_zone_id`, `port_sea_zone_name` |
| L8 | `GET /locations/admin/sea-zones` (`locations:read`) | new → `[{id, name, region_id, region_name, country_name, neighbor_ids: [int]}]` |
| — | `POST /locations/`, `PUT /locations/{id}/update` | `is_sea_zone: Optional[bool]`, `port_sea_zone_id: Optional[int]` (null = leave as is; `0` clears the zone) + 3.12 validations; every serializer that emits `is_port` also emits `is_sea_zone` and `port_sea_zone_id` |
| — | `GET /locations/{id}/client/details` | neighbours may carry `passage: Optional['board'|'disembark']`, `ship_id`; top-level `is_sea_zone`, `ship_id`, `docked_ships` (3.6) — additive |
| — | `POST /locations/{dest}/move_and_post`, `/quick_move` | passage + zone refusals (3.6) |
| v1 L1–L4, L6, L7 | sea-route CRUD + public route reads | **removed** |

### 3.14 Frontend

All new/changed code TypeScript + Tailwind, no `React.FC`, mobile 360 px+, every error visible in Russian, design-system
classes (`modal-overlay`/`modal-content`, `gold-text`, `btn-blue`, `btn-line`, `gray-bg`, …) — read `docs/DESIGN-SYSTEM.md`.

Player:
- `api/sea.ts` + `types/sea.ts` (S1–S5).
- `components/pages/LocationPage/CaptainModal/CaptainModal.tsx` (template `CaravaneerModal.tsx`): ship name + Captain,
  route strip of stops (current/next highlighted, ⇄ or ↻), status line («У причала, отплытие через MM:SS» / «В море:
  {зона}, {море} → {порт}, прибытие ≈ через …»), destinations list (port, country, ETA, fare in `currency_forms`, seats left,
  «Купить билет»), «Наняться матросом» (explains «нужен пост на палубе от N символов до отплытия»), «Пробраться зайцем»
  (confirm with a risk warning), «Мои места» (passes). 402 → «Недостаточно …»; dialogue-gate 403 → existing
  `npcDialogueGate` hint (new Captain hint constant). After a purchase: toast + refetch location details (the passage appears).
- `NpcProfileModal.tsx`: button «Корабль» for `npc_role === 'captain' && isCharacterHere && characterId` (swap like
  `caravaneerOpen`).
- `components/pages/LocationPage/ShipDeckHeader.tsx`: rendered by `LocationPage.tsx` when `details.ship_id`; polls S5 every
  30 s and when a countdown hits 0; shows ship, Captain, status (docked at X / at sea in zone Y of sea Z heading to W), ETA or
  departure countdown (`useCountdownTo`), «Вдали виден корабль «…»» list, my passes («Билет до X» / «Матрос: нужен пост от
  N символов» / nothing → warning «У вас нет места на следующий рейс — при отплытии вас высадят»).
- `components/pages/LocationPage/DockedShips.tsx`: in a port, «У причала: «X»» chips from `details.docked_ships`.
- `NeighborsSection.tsx` + `types.ts`: passage entries get an ⚓ marker and the label «Подняться на борт» / «Сойти на
  берег»; no quick-move action for them (the server refuses anyway).
- `useWebSocket.ts`: `'sea'` added to `LAW_LOCK_REFRESH_TYPES` (refreshes `/users/me` → current location after a put-ashore).
- `Admin/ReputationPage/shadowLabels.ts`: `stowaway: 'Безбилетный проезд'`.
Admin:
- `constants/npc.ts`: Captain role + ⚓ icon.
- `EditLocationForm.tsx`: checkbox «Морская зона» (shown/allowed for locations of hidden countries) and, when `is_port`, a
  select «Выход в море (морская зона)» from L8; 409 texts shown.
- `components/Admin/ShipsPage/ShipsPage.tsx` (`/admin/ships`, `ProtectedRoute requiredPermission="locations:read"`, link in
  `Admin/AdminPage.tsx` with `module: 'locations'`): list of ships (shared `Admin/ExpandableList` pattern of the admin ergonomics work:
  name, state, Captain, port/zone, blocked reason), create/edit form (name, Captain picker and deck picker from A6, numbers
  with hints, loop toggle, active toggle), stops editor (ports from L5, add/remove/reorder; per leg the A5 preview with zone
  names and a manual override editor = an ordered chain of zones picked from L8, each next zone limited to the neighbours of
  the previous), delete with confirm; `SeaSettingsCard.tsx` (A7). Buttons respect `hasPermission('locations:create' |
  'update' | 'delete')`. `api/seaAdmin.ts` + `types/seaAdmin.ts`.
- `economyLabels.ts`: the two op labels.

### 3.15 Edge cases (summary)

| Case | Behaviour |
|---|---|
| Paid but not aboard at departure | ticket `burnt`, no refund (brief) |
| Stayed aboard after the ticket ended | put ashore at the next departure, no crime (see open question 1) |
| Double «Купить» | serialized on the ship lock → second 409; idempotency key per pass |
| Boarding post at the moment of departure | CS `update_location` locks the ship first → either boards before departure (and sails) or gets 409 «Корабль уже отплыл» |
| Player offline | sails, arrives, stays on the deck; put-ashore works offline (raw move + notice) |
| Player in battle on the deck at departure | never moved; sails this trip (logged) |
| Player unconscious / gathering on the deck at departure | treated normally (put ashore if not entitled; gathering cancelled best-effort) |
| Admin teleports a passenger off the deck | allowed; his pass burns at the next departure |
| Home teleport scroll at sea | allowed (open question 3) |
| Teleport / home teleport into a deck or zone | refused (G3) |
| Ship deactivated / deleted / stops edited | 3.10; not-started passes refunded |
| Port deleted by a cascade / unflagged | skipped at arrival; no valid stop → safe landing |
| Deck deleted by a cascade | safe landing of everyone still pointing at it, ship off |
| Captain deleted / killed / role removed | no sales («Капитана нет»), the ship keeps its schedule; a new Captain is bound in the editor |
| Captain moved by an admin | moved back by the next sea pass |
| Sea graph edited | affects legs computed after the edit; a sailing leg keeps its snapshot |
| No sea path for the next leg | ship stays docked, `blocked_reason = no_path`, retried each pass; admin sees it |
| Economy tick switched off in the DB | ships still sail (own pass) |
| Deploy skew (CS 052 not applied, LS already new) | LS `sea_read` tolerant → no passages / no ship blocks; CS sea API 503 «Корабли пока недоступны» when the tables are missing (`sea_available` inspector check) |

### 3.16 Security and RBAC

- Player endpoints: JWT + owner; Captain flows require presence + FEAT-145 dialogue gate + reputation tier (fail-closed);
  stowaway requires presence in the docked port. Inputs validated by Pydantic (`ge=1` ids, bounded ints, override lists
  ≤ `path_max_zones`); raw SQL only with bound parameters; 500 → generic Russian text, details logged.
- Money: ship-row lock + conditional debits + idempotency keys; refunds idempotent; all in the ledger.
- Existing Nginx limits on `/characters/` and `/locations/` apply; no Nginx change.
- **RBAC: no new permission.** Ships/zones/ports are world content edited next to locations; `locations:read/create/
  update/delete` already exist and are held by exactly the people who edit the world (admin gets all automatically). No
  user-service migration, no RBAC test seed (CLAUDE.md §10.13 applies only to new permissions).

### 3.17 Ready for later stages (not built now)

- Position = `sea_ships.current_zone_id` (a `Locations` id) → storms/monster raids can be zone events targeting ships in a
  zone and spawn mobs/battles on `deck_location_id` (mob spawn already works per location).
- Caravans by sea: cargo rows can reference `ship_id` + `first_trip/last_trip` like passes; ports (`is_port`) and the ship
  schedule give the planner real sailing times. The v1 `route_legs` idea is dropped.
- Customs/contraband: hooks at put-ashore/arrival (`check_entry` already runs on landing for put-ashore; arrival will need its
  own hook when goods exist).
- Pirates / player ships: a ship row with an owner; boarding between ships = a temporary passage between two decks in the
  same zone (same mechanism as port↔deck).

### 3.18 v1 work — keep / change / drop

| v1 piece | Decision | Action |
|---|---|---|
| CS migration `052_sea_voyages.py` (untracked; applied locally) | **DROP → replaced** by `052_sea_ships` | PM: local `alembic downgrade 051_caravan_escorts` in the CS container **before** touching files, then delete the file; T2 writes the new one |
| CS `models.py` (`Character.voyage_id`, `EconCaravan.route_legs/at_sea`, `SeaVoyage`, `SeaTicket`, `SeaMessage`, `SeaSetting`) | **DROP** | PM: `git restore`; T2 adds the new models |
| CS `activity_lock.py` (`REASON_VOYAGE`, `voyage_id` kwarg) | **DROP** | PM: `git restore` |
| CS `law_crud.py` (voyage kwarg in `check_patrol_arrival`) | **DROP** | PM: `git restore` |
| CS `caravan_escort_public.py` (voyage kwarg) | **DROP** | PM: `git restore` |
| CS `main.py` (`/by_location` voyage filter, `update_location` voyage refusal) | **DROP** | PM: `git restore` (only these 2 hunks in the diff); T2 adds the v2 changes |
| CS `tests/test_admin_mob_region_ready.py` (head = `052_sea_voyages`) | **DROP → redo** | PM: `git restore`; T2 asserts head `052_sea_ships` |
| CS `law_core.py` (`SOURCE_VOYAGE` in `ENTRY_SOURCES`) | **KEEP** (used for put-ashore `check_entry`); T2 updates its comment and adds `CRIME_STOWAWAY` | none |
| `econ_core.py` ×4 (`OP_SEA_FARE`, `OP_SEA_REFUND`, `SEA_OP_TYPES`) + `tests/econ_contract_cases.py` ×4 | **KEEP** (comment wording updated identically in all 4 copies by T2) | none |
| BS/IS/LS `activity_lock.py` copies, LS `tests/test_activity_lock.py`, BS `tests/test_caravan_raid_battle.py` (T2-partial) | **DROP** (no lock change in v2) | PM: `git restore` all five |
| PS `crud.py` (`voyage_id` roster filter + fallback) | **DROP** (passengers are public, they stand on the deck) | PM: `git restore` |
| LS migration `060_sea_routes.py` (untracked; applied locally) | **CHANGE → rewrite** as `060_sea_zones` (keeps `is_port`, drops `sea_routes`, adds zone columns) | PM: local `alembic downgrade 059_location_neighbor_unique` in the LS container **before** touching files; T1 renames/rewrites the file |
| LS `models.py` (`Location.is_port`, `SeaRoute`) | **CHANGE**: keep `is_port`, remove `SeaRoute`, add zone columns | T1 |
| LS `schemas.py` (`is_port` fields; `SeaRoute*`, `SeaPortRead`) | **CHANGE**: keep `is_port` + `SeaPortRead` (extended), remove the `SeaRoute*` schemas | T1 |
| LS `crud.py` (`is_port` in serializers/create/update, unflag check, sea-route crud) | **CHANGE**: keep `is_port` plumbing and `list_sea_ports`; unflag check reads `sea_ship_stops`; remove route crud/serializers/public reads | T1 |
| LS `main.py` (`sea_router` L1–L7, `is_port` passthrough) | **CHANGE**: keep L5 + `is_port`; remove L1–L4, L6, L7; add L8 | T1 |
| LS `tests/test_client_details.py` (`is_port` key) | **KEEP**, extended by T1 with the new keys | T1 |
| `docs/services/locations-service.md` (sea-routes section) | **CHANGE**: rewrite the section for zones/ports/passages | T1 |
| v1 tasks T5–T16 (voyages, caravan sea legs, world-map sea lines, voyage lock UI) | **DROP** | — |

### 3.19 Open game-design questions (defaults are implemented unless the user decides otherwise)

1. Остался на палубе без билета (забыл сойти / билет кончился) — **по умолчанию высаживаем без последствий**; альтернатива: считать зайцем (проверка скрытности, при поимке — преступление).
2. Матрос не написал пост нужной длины — **по умолчанию высаживаем без последствий**; альтернатива: считать зайцем.
3. Свиток телепорта домой в открытом море — **по умолчанию работает** (игрок просто теряет рейс); альтернатива: в море не действует.
4. Непойманный заяц — **по умолчанию никаких следов** (бесплатный рейс); альтернатива: скрытое преступление, которое могут раскрыть позже, как в «Тени».
5. Деньги за билет — **как у телепорта**: казна края порта отправления + налог стране; цена = база + за каждую морскую зону (админ задаёт для каждого корабля).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Waves:** T0 (PM) → **A:** T1 ∥ T2 → **B:** T3 (after T2) ∥ T6 (after T1) → **C:** T4 (after T1, T3) ∥ T5 (after T1, T2)
∥ T7 (after T2, T3) → **D:** T8.
T1 (LS) and T2/T3 (CS) never touch the same files; T4 and T5 have disjoint file lists (T4 owns `constants/npc.ts`,
`EditLocationForm.tsx`, admin files; T5 owns `LocationPage/*`, `useWebSocket.ts`, `shadowLabels.ts`; each its own `api/`
+ `types/` files). Every backend task: `python -m py_compile` on all touched files; every frontend task: `npx tsc --noEmit`
and `npm run build` inside the frontend container (no node on the host). **No agent commits, pushes, stashes or runs any
state-changing git command** — the user commits once at the end.

**T0 — PM cleanup of v1 (git and local DB; done by the PM, not by agents), in this order:**
1. CS container: `alembic downgrade 051_caravan_escorts` (the v1 file must still exist). LS container: `alembic downgrade
   059_location_neighbor_unique`. Check `alembic current` in both.
2. `git restore` these tracked files:
   `services/character-service/app/activity_lock.py`, `services/character-service/app/caravan_escort_public.py`,
   `services/character-service/app/law_crud.py`, `services/character-service/app/main.py`,
   `services/character-service/app/models.py`, `services/character-service/app/tests/test_admin_mob_region_ready.py`,
   `services/battle-service/app/activity_lock.py`, `services/battle-service/app/tests/test_caravan_raid_battle.py`,
   `services/inventory-service/app/activity_lock.py`, `services/locations-service/app/activity_lock.py`,
   `services/locations-service/app/tests/test_activity_lock.py`, `services/party-service/app/crud.py`.
3. Delete the untracked `services/character-service/app/alembic/versions/052_sea_voyages.py` (and its `__pycache__` entry).
4. Leave untouched (kept/changed by T1/T2): `law_core.py`, the 4 `econ_core.py`, the 4 `econ_contract_cases.py`, LS
   `models.py`/`schemas.py`/`crud.py`/`main.py`/`060_sea_routes.py`/`tests/test_client_details.py`,
   `docs/services/locations-service.md`.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| T1 | LS sea geography + passages (3.3 LS, 3.6, 3.12 LS, 3.13 LS): rewrite `060_sea_routes.py` → `060_sea_zones.py` (revision id `060_sea_zones`); models (keep `is_port`, drop `SeaRoute`, add `is_sea_zone`, `port_sea_zone_id`); schemas (drop `SeaRoute*`, extend `SeaPortRead`, zone fields in location create/update/read, client-details additions); crud: remove sea-route code, keep `list_sea_ports` (+ zone), `list_sea_zones` (L8), zone/port/deck validations on location create/update/delete, neighbour + arrow-neighbour refusals, `sync_cross_region_neighbors` skip, world-graph zone filter, zone fields in every serializer that emits `is_port`; new `sea_read.py` (tolerant raw reads of CS `sea_ships`/`sea_passes`/`sea_ship_stops`: ship by deck, ships docked at a port, entitlement, `passage()`, `passages_for()`, ship names by port/deck) with `PASSAGE_ENERGY_COST = 0`; `move_and_post` / `quick_move` passage + zone refusals; client details passages / `is_sea_zone` / `ship_id` / `docked_ships`; main.py: remove L1–L4, L6, L7, add L8; docs section rewritten | Backend Developer | DONE | `services/locations-service/app/alembic/versions/060_sea_zones.py` (replaces `060_sea_routes.py`), `.../app/models.py`, `.../app/schemas.py`, `.../app/crud.py`, `.../app/main.py`, `.../app/sea_read.py` (new), `.../app/tests/test_client_details.py`, `docs/services/locations-service.md` | T0 | Migration up/down/up clean on MySQL (explicit FK index, id ≤ 32 chars, single head); a deck/zone can't get neighbours; zone↔land links refused everywhere incl. arrow sync; boarding by post works only with a right while docked, disembark only while docked, quick move refuses passages, sea zones refused as destinations; client details additive (old keys unchanged); `sea_read` returns "no ships" when CS tables are missing; existing LS tests green; py_compile passes |
| T2 | CS core (3.3 CS, 3.4, 3.5, 3.6 CS part, 3.7, 3.11, 3.13 player, G2/G3): migration `052_sea_ships.py`; models `SeaShip`, `SeaShipStop`, `SeaPass`, `SeaSetting`; `sea_core.py` (pure: stop sequence, trips, fares, ETA, entitlement, `plain_length`, `CAPTAIN_ROLE`); `sea_crud.py` (load stops/zone graph by raw SQL + `caravan_route` BFS, legs/override validation, Captain context, view, buy ticket, hire sailor, sneak, `lock_ships_for_move`, `move_refusal`, `put_ashore`, `safe_land`, refunds, `sea_available`); `sea_schemas.py`; `sea_api.py` S1–S5 (async where HTTP); `main.py`: router include before the main router, `update_location` ship-lock + `move_refusal` (lock order ship → character), admin move refuses zones, home teleport refuses deck/zone targets; `crud.py`: `execute_teleport` and `create_teleport_link` refuse deck/zone targets; `law_core.py`: `CRIME_STOWAWAY`, comment of `SOURCE_VOYAGE`; econ comment in the 4 `econ_core.py` copies (identical); `test_admin_mob_region_ready.py` head = `052_sea_ships` | Backend Developer | DONE | `services/character-service/app/alembic/versions/052_sea_ships.py` (new), `.../app/models.py`, `.../app/sea_core.py` (new), `.../app/sea_crud.py` (new), `.../app/sea_schemas.py` (new), `.../app/sea_api.py` (new), `.../app/main.py`, `.../app/crud.py`, `.../app/law_core.py`, `services/{character,inventory,locations,dungeon}-service/app/econ_core.py` (comment only), `.../app/tests/test_admin_mob_region_ready.py` | T0 | Migration up/down/up clean on MySQL (single head `052_sea_ships`); contracts per 3.13; lock order ship → passes → characters everywhere; fare to the departure port's region treasury with tax; double purchase = one charge; `update_location` refuses boarding without a right / after departure; teleports into decks/zones refused; `scripts/check_econ_copies.sh` ok; existing CS tests green; py_compile passes |
| T3 | CS sea pass + ship admin (3.8, 3.9, 3.10, 3.12 CS, 3.13 admin): `sea_pass.py` (claim on `sea_settings`, per-ship transactions: sanity, departure with entitlement / sailor post check / stowaway roll + crime via `register_crime` (reported or masked + suspicion) / put ashore with `check_entry(SOURCE_VOYAGE)` / burn+expire / Captain → deck; zone stepping with catch-up; arrival with invalid-stop skip and safe landing; Captain placement; notices after commit; best-effort LS left-location + cancel-gathering); `econ_scheduler.run_sea_pass` wired after the faction pass; `sea_admin.py` (A1–A7 crud + router: create/update/delete/deactivate with refunds, stops edits while docked, legs preview, candidates, settings); router include in `main.py`; docs `docs/services/character-service.md` (sea tables, S/A endpoints, pass), `docs/ARCHITECTURE.md` (LS reads CS sea tables; ships = locations) | Backend Developer | DONE | `services/character-service/app/sea_pass.py` (new), `.../app/sea_admin.py` (new), `.../app/econ_scheduler.py`, `.../app/main.py` (include line only), `.../app/sea_crud.py` (only additions needed by the pass/admin), `docs/services/character-service.md`, `docs/ARCHITECTURE.md` | T2 | Ships sail with the DB economy toggle off; departure/arrival work with nobody online; an unentitled player is put ashore, a caught stowaway gets a crime in the port region; burnt tickets are not refunded; admin delete/deactivate/stops edit refund not-started passes; safe landing never leaves a player on a deck at sea; py_compile passes; existing CS tests green |
| T4 | FE admin (3.14 Admin): Captain role in `constants/npc.ts`; `EditLocationForm.tsx` zone checkbox + port zone select (L8), 409s shown; `ShipsPage.tsx` + `ShipForm.tsx` + `ShipStopsEditor.tsx` (A5 preview, zone-chain override from L8) + `SeaSettingsCard.tsx` at `/admin/ships` (ProtectedRoute `locations:read`, AdminPage link); `api/seaAdmin.ts` + `types/seaAdmin.ts`; `economyLabels.ts` labels | Frontend Developer | DONE | `src/constants/npc.ts`, `src/components/AdminLocationsPage/EditForms/EditLocationForm/EditLocationForm.tsx`, `src/components/Admin/ShipsPage/ShipsPage.tsx` (new), `src/components/Admin/ShipsPage/ShipForm.tsx` (new), `src/components/Admin/ShipsPage/ShipStopsEditor.tsx` (new), `src/components/Admin/ShipsPage/SeaSettingsCard.tsx` (new), `src/api/seaAdmin.ts` (new), `src/types/seaAdmin.ts` (new), `src/components/Admin/AdminPage.tsx`, `src/components/App/App.tsx`, `src/components/Admin/EconomyPage/economyLabels.ts` | T1, T3 | Admin creates zones in a hidden country, binds a port to a zone, creates a ship with 3 stops and a Captain, sees legs/blocked reasons, edits/deactivates/deletes; every API error shown in Russian; tsc + build pass; 360 px usable; no React.FC; Tailwind only |
| T5 | FE player (3.14 Player): `CaptainModal.tsx`; NpcProfileModal «Корабль» button; Captain hint in `npcDialogueGate.ts`; `ShipDeckHeader.tsx`; `DockedShips.tsx`; passages in `NeighborsSection.tsx` + `types.ts`; `LocationPage.tsx` wiring; `api/sea.ts` + `types/sea.ts`; `useWebSocket.ts` `'sea'`; `shadowLabels.ts` `stowaway` | Frontend Developer | DONE | `src/components/pages/LocationPage/CaptainModal/CaptainModal.tsx` (new), `src/components/pages/LocationPage/NpcProfileModal.tsx`, `src/components/pages/LocationPage/npcDialogueGate.ts`, `src/components/pages/LocationPage/ShipDeckHeader.tsx` (new), `src/components/pages/LocationPage/DockedShips.tsx` (new), `src/components/pages/LocationPage/NeighborsSection.tsx`, `src/components/pages/LocationPage/types.ts`, `src/components/pages/LocationPage/LocationPage.tsx`, `src/api/sea.ts` (new), `src/types/sea.ts` (new), `src/hooks/useWebSocket.ts`, `src/components/Admin/ReputationPage/shadowLabels.ts` | T1, T2 | Section 1 UX works live: buy ticket / hire / sneak, passage appears only for the right holder, board by post, deck header shows docked/at-sea/zone/ETA/nearby ships, buy the next leg on deck, put-ashore refreshes the location; errors visible; tsc + build pass; 360 px; no React.FC |
| T6 | QA LS: migration-free unit/API tests for zone/port validations (hidden country, mixed neighbours 409, arrow sync skip, deck neighbour/delete refusal, port unflag/delete with ship stops 409, `port_sea_zone_id` rules), L5/L8 (auth 401/403), client details passages (viewer with/without right, docked/sailing, disembark), `move_and_post` passage allowed/refused/at-sea/zone 400, `quick_move` refuses passages, `sea_read` tolerance when CS tables are missing; security cases (ids as strings, SQL-injection-like names) | QA Test | DONE | `services/locations-service/app/tests/test_sea_zones.py` (new), `services/locations-service/app/tests/test_sea_passages.py` (new), `services/locations-service/app/tests/sea_sqlite.py` (new, shared SQLite world) | T1 | All pass in the LS container; existing LS tests green |
| T7 | QA CS: `sea_core` (sequence there-and-back/loop, trips, fares, ETA, entitlement, plain length); legs (BFS on zones only, override validation, same-zone port); Captain view/gates (dialogue gate 403/503 mocked, tier, presence, dead/unbound Captain); ticket (seats per trip, 402 no charge, double → one charge, ledger to region treasury + country tax, `to_trip` bounds, bought at sea starts next trip); sailor (slots, post floor, length check incl. HTML); stowaway (presence, roll seeded caught/not caught, crime reported vs masked + suspicion, region = port); `update_location` (board with/without right, after departure 409, disembark docked/at sea, zone 409, lock order); G3 teleport/home/admin refusals; sea pass (claim throttle, runs with the economy toggle off, departure burn/expire/put-ashore/in-battle stays, `check_entry` with `voyage`, zone stepping + offline catch-up, arrival completes passes, invalid stop skipped, safe landing fallbacks, deck missing, Captain placement + revert of manual move); admin A1–A7 (validation 409s, deck rules, delete only docked, deactivate/stops edit refunds conserve money) | QA Test | DONE | `services/character-service/app/tests/test_sea_core.py` (new), `.../tests/test_sea_player.py` (new), `.../tests/test_sea_pass.py` (new), `.../tests/test_sea_admin.py` (new) | T2, T3 | All pass; each test ≤ 30 s (CI per-test timeout); CS test DB gets stand-in LS tables (`Locations` with `is_port`/`is_sea_zone`/`port_sea_zone_id`, `LocationNeighbors`, `posts`, `Regions`, `Countries`) like existing fixtures |
| T8 | Review: CLAUDE.md checklist, contracts vs 3.13, migrations on MySQL (CS `052_sea_ships`, LS `060_sea_zones`, single heads), `check_econ_copies.sh`, no lock-copy drift (activity_lock copies identical to HEAD), security; run py_compile / pytest of CS, LS / tsc / build; live verification on localhost: admin creates sea «Моря» with 3 zones, 2 ports bound to zones, a Captain NPC, a ship; buy a ticket, board by post, wait for departure (shorten timings), see zone stepping and a second ship nearby, arrive, disembark; an unentitled player put ashore; stowaway caught → crime visible in the law panel | Reviewer | DONE | — | T1–T7 | PASS only with automated results + live verification recorded in section 5 |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-17
**Result:** PASS

Scope: the whole uncommitted diff (35 tracked files + 29 new files): CS sea core/crud/api/pass/admin, migration `052_sea_ships`, LS `sea_read.py` + crud/main/schemas/models, migration `060_sea_zones`, the 4 `econ_core.py` copies, FE player (Captain modal, deck header, docked ships, passages, ws `sea`) and admin (`/admin/ships`, location form) parts, docs.

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (0 errors)
- [x] `npm run build` (frontend container) — PASS (built in 1m 6s)
- [x] `py_compile` on every touched/new backend file — PASS
- [x] `pytest` character-service (`--asyncio-mode=auto`, container) — PASS: 10453 passed, 2 skipped (14 min)
- [x] `pytest` locations-service (`--asyncio-mode=auto`, container) — PASS: 3300 passed, 5 skipped
- [x] `pytest` inventory-service — PASS: 2545 passed, 1 skipped; dungeon-service (`--timeout=30`) — PASS (exit 0); battle-/party-service — not touched (no diff), not run
- [x] `sh scripts/check_econ_copies.sh` — PASS (all shared copies identical); `activity_lock.py` copies — no diff vs HEAD
- [x] Migrations on local MySQL `fogdatabase`: CS `052_sea_ships` and LS `060_sea_zones` up → down → up clean; single heads (`052_sea_ships`, `060_sea_zones`); revision ids 13 chars; explicit FK index `ix_locations_port_sea_zone`
- [x] `docker compose config` — PASS
- [x] Live verification (Claude in Chrome + API) — PASS

#### Code review
- CLAUDE.md: all new FE files are `.tsx/.ts`, Tailwind only (no new CSS/SCSS), no `React.FC`, no `any`, design-system classes (`gold-text`, `btn-line`, `rounded-card`, `shadow-card`, `modal` shell), every API call shows a Russian error (toast / inline). Pydantic v1, sync SQLAlchemy in CS, async in LS.
- Contracts S1–S5 / A1–A7 / L5 / L8 / client-details additions match `types/sea.ts`, `types/seaAdmin.ts` and the tests; client details are additive.
- Security: JWT + owner on every player endpoint, Captain flows behind presence + FEAT-145 gate (fail-closed 503) + reputation tier; admin endpoints behind `locations:*`; raw SQL is parameterised; 500s return generic Russian texts.
- Locks: ship → passes → character everywhere (`update_location` peeks, locks ships by deck, then the character, 409 on a moved character); departure holds the same ship lock → boarding-vs-departure race closed.
- Sea zones never walkable / never in the land graph: G2 in LS `move_and_post`/`quick_move`, CS `update_location`, admin move; G3 in teleport links / execute / home scroll; G4 neighbour/arrow/sync refusals + world-graph filter; caravans/patrols only BFS over `LocationNeighbors`, which never link zones to land.
- Nobody stranded: disembark passage open whenever docked (also inactive); deletion only while docked with put-ashore; deactivation at sea finishes the leg; deck/port loss → skip / safe landing to last port → any stop → starting location.

#### Live Verification Results
Test world created through the APIs (hidden «Моря (тест)» country with 3 linked zones, a visible test coast with 2 ports bound to zones, 2 decks, 2 Captain NPCs); ship #1 created → edited (rename) → deactivated (ticket refunded: ops sea_fare 25 + tax 2 reversed exactly, balance restored) → reactivated → deleted entirely **in the browser UI** (/admin/ships); ship #2 via A2.
- Refusals: zone in a land country 409, port zone on a non-port 409, zone↔land neighbour 409 (single and bulk), deck neighbour/arrow 409, duplicate deck 409, admin move into a zone 409, move into a zone 400, quick move onto a deck 400 «только постом», boarding without a right 403, leaving the deck at sea 400, double ticket 409, other ship's Captain 400, settings out of range 422.
- Player flow (Ашари 763 / Годрик 764 / Аэлис 761): Captain modal (fares, ETA, seats, sailor, stowaway, my places), ticket bought (passage «Подняться на борт» appears only for the holder), sailor hired, stowaway attempt; boarded by post from the deck page UI; departure: Captain left the port, stowaway caught (chance 100 → crime `stowaway` 50 points in the port region, wanted set), deck header «В море: Пролив…, Море… → Порт…», ETA, «Вдали виден корабль «Тестовый Бриг»», «Рядом у причала» while docked; next leg bought on deck at sea; zone stepping 1→2→3 and reverse; arrival: Captain moved to the port, arrival notice asks to buy only the holder whose ticket ended (PM fix confirmed), the unentitled passenger was put ashore at the next departure and the page followed him to the port; disembark by post to the docked port (wrong port 400).
- Console: zero errors on location/deck/admin pages; 360 px: deck header, Captain modal and /admin/ships fit with no horizontal scroll.
- Cleanup: ships, stops, passes, NPCs, 7 locations, 2 regions, 2 countries, posts/gates, crime, wanted, law log, character logs, notifications removed; sea settings restored; 761/763/764 back in location 197 with original balances (5526 / 30893 / 234) and party 9402 intact. The two balanced ledger operations (sea_fare 1959 + sea_refund 1960) are left as audit records.

#### Non-blocking notes (no fix required for this feature)
| # | File:line | Note | Severity |
|---|-----------|------|----------|
| 1 | `services/character-service/app/sea_pass.py:427-443` | `_land_broken` → `safe_land` → `refund_not_started` and then `active_passes(lock=True)` with `populate_existing()`; the flush between them happens only implicitly (a `begin_nested()` inside `location_infos`), so in the corner case «no landing target and no last port» a refunded pass could be re-read as active and marked completed (money still refunded). Same pattern the PM fixed in `sea_admin`; an explicit `db.flush()` after `safe_land` would make it robust. | LOW |
| 2 | `services/frontend/app-chaldea/src/components/pages/LocationPage/ShipDeckHeader.tsx:44-70` | The header is not reloaded after the character's own boarding post («На борту: N» stays stale until the 30 s poll). | LOW (UX) |
| 3 | `services/frontend/app-chaldea/src/components/pages/LocationPage/CaptainModal/CaptainModal.tsx:66` | `next_port` is always null while docked, so the « → «порт»» suffix of the docked status line never renders (dead branch). | LOW (cosmetic) |

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-17 — PM: ревью PASS; закрыта LOW-находка (flush в _land_broken), две косметические мелочи фронта — в ISSUES.md; фича закрыта
[LOG] 2026-11-17 02:05 — Reviewer: проверка T8 завершена, результат PASS — tsc/build, py_compile, pytest CS 10453 / LS 3300 / IS 2545 / DS зелёные, миграции up/down/up на MySQL, копии econ одинаковые; живая проверка в браузере (создание/правка/выключение с возвратом/удаление корабля в /admin/ships, билет, матрос, заяц пойман → розыск, посадка постом, отплытие, зоны, «вдали виден корабль», прибытие, капитан ходит, безбилетник высажен, сход в порт, 360 px, ноль ошибок консоли); тестовые данные удалены, персонажи и балансы восстановлены; 3 мелких замечания без блокировки
[LOG] 2026-11-17 — PM: исправлены находки QA/фронта: flush после refund_not_started (возврат теперь помечается refunded, xfail-тесты стали обычными); уведомление о прибытии не просит купить билет, если следующий участок уже оплачен (+тест); S5 отдаёт sailor_post_min_chars, шапка палубы показывает длину поста. 262 теста sea_* проходят, tsc/build ок
[LOG] 2026-11-16 — PM: бриф переработан (v2): корабли-локации с уникальными капитанами, скрытая страна «Моря»; v1-дизайн отменён, отправляю архитектору на переработку
[LOG] 2026-11-17 00:30 — Architect: v2 спроектирован — корабли-локации (палуба = обычная локация, капитан-НПС ходит между портами), права на борт (билет / матрос / заяц) по рейсам, сгорающие билеты, скрытая страна «Моря» с морскими зонами, проход корабля по зонам и соседние корабли; блокировка «в плавании» не нужна (палуба без переходов в море) — 8 задач (3 backend, 2 frontend, 2 QA, 1 ревью) + T0 откат v1 для PM; миграции переписываются на месте: CS 052_sea_ships, LS 060_sea_zones; v1 перенесён в приложение A
[LOG] 2026-11-17 01:30 — Backend Developer: T2 готово — миграция CS 052_sea_ships (sea_ships / sea_ship_stops / sea_passes / sea_settings с засеянной строкой, без FK), модели, sea_core (порядок остановок туда-обратно/по кругу, рейсы, цены, ETA, права), sea_crud (план рейсов по морским зонам с ручным путём или BFS, диалог капитана, билет с оплатой в казну края порта отправления + налог стране, матрос, заяц, шапка палубы, блокировки корабль → места → персонаж, высадка/безопасная высадка/возвраты для T3), эндпоинты S1–S5, проверка update_location под блокировкой корабля (вход на палубу только с правом у причала, сход только в порт стоянки, морская зона — никогда), G2 в админ-переносе, G3 в телепортах и свитке дома, CRIME_STOWAWAY, комментарий в 4 копиях econ_core; миграция up/down/up на MySQL чистая, живая проверка S1–S5 и переходов на временных данных (удалены), тесты CS зелёные
[LOG] 2026-11-17 — Backend Developer: T1 готово — миграция LS 060_sea_zones (is_port + is_sea_zone + port_sea_zone_id с явным индексом и FK SET NULL; sea_routes убрана), модели/схемы/crud без кода v1 (L1–L4, L6, L7 удалены, L5 расширен, добавлен L8 /admin/sea-zones), проверки зон/портов/палуб в админке (скрытая страна, зона↔суша, палуба без переходов, порт в маршруте корабля, удаление палубы), пропуск пар в синхронизации стрелок, зоны убраны из графа мира; sea_read.py (терпимые чтения sea_ships/sea_passes/sea_ship_stops) — проход порт↔палуба в move_and_post, отказ quick_move, отказ «в открытое море», проходы/ship_id/docked_ships на странице локации; миграция up/down/up на MySQL чистая, тесты LS 3159 passed, живая проверка curl пройдена, док обновлён
[LOG] 2026-11-17 03:10 — Backend Developer: T3 готово — sea_pass.py (свой захват на sea_settings, работает при выключенной экономике; отплытие: билет — плывёт, матрос без поста и без права — высадка без последствий, заяц — бросок скрытности FEAT-199/201 и преступление «stowaway» в крае порта (в маске — скрытое + подозрение), в бою — не трогаем, сгорание билетов не поднявшихся, путь участка замораживается, капитан на палубу; шаги по зонам с догоном; прибытие с пропуском сломанной остановки и безопасной высадкой; возврат капитана на место), подключение к планировщику после фракций, sea_admin.py A1–A7 (создание/правка/удаление/выключение с возвратами, правка маршрута у причала, предпросмотр участков, кандидаты, настройки); в PlannedLeg добавлено направление; док character-service.md и ARCHITECTURE.md; живая проверка на временной стране «Моря» (3 зоны, 2 порта, палуба, капитан): билет, матрос с постом и без, заяц пойман → розыск в крае порта, безбилетник высажен, сгоревший билет, шаги по зонам, обход сломанного порта, прибытие, капитан ходит и возвращается после ручного переноса, удаление в море 409, безопасная высадка; все тестовые данные удалены, персонажи возвращены
[LOG] 2026-11-17 — QA Test: T6 готово — 141 новый тест LS на реальной SQLite (заглушки таблиц CS sea_ships/sea_ship_stops/sea_passes): зоны и порты при создании/правке (скрытая страна, порт/стартовая/палуба, соседи-суша, снятие флага, port_sea_zone_id, 0 = очистить), отказы зона↔суша и палуба в одиночном/массовом/путевом/стрелочном редактировании, пропуск пар при синхронизации стрелок, удаление палубы и порта в маршруте 409, граф мира без зон, L5/L8 (данные, 401/403), проход порт↔палуба в move_and_post (с правом и без, 0 выносливости, выключенный корабль, в море, зона 400), отказы quick_move, страница локации (проходы/docked_ships/ship_id по зрителю), терпимость sea_read без таблиц CS, безопасность; весь набор LS 3300 passed, 5 skipped; багов не найдено
[LOG] 2026-11-17 — QA Test: T7 готово — 259 новых тестов CS (+2 xfail на найденный баг) в 4 файлах + общий мир sea_world.py (заглушки LS: Locations с is_port/is_sea_zone/port_sea_zone_id/image_url/is_starting, Countries.is_hidden, LocationNeighbors, arrow_neighbors, posts, gathering_sessions; скрытая страна «Моря» с 5 зонами): чистые правила sea_core (туда-обратно/по кругу, пропуск сломанных остановок, рейсы, ручной путь, BFS, цены, места, ETA, длина поста); S1–S5 (401/403, ворота диалога 403/503, тир репутации, контекст капитана 404/400, места, двойная покупка 409 с одним списанием, 402, матрос, заяц, покупка на палубе в море, шапка палубы, 503 без таблиц); деньги в казну края порта отправления + налог стране, возврат точно обратный, деньги мира сохраняются; update_location (посадка с правом и без, после отплытия, выключенный корабль, сход в море/не в тот порт, зона, порядок блокировок и гонка 409); G2/G3 (админ-перенос, свиток дома, execute_teleport, create_teleport_link); проход моря (захват/троттлинг, работает при выключенной экономике, отплытие: билет/сгорание/матрос с постом после найма/заяц с броском скрытности, маска, слава, преступление stowaway с ключом и подозрением, в бою не трогаем, check_entry voyage, отмена сбора; шаги по зонам и догон, прибытие, пропуск сломанной остановки, безопасная высадка с возвратами и запасными точками, пропавшая палуба, возврат капитана); админка A1–A7 (права, 409/422, палуба неизменна, маршрут только у причала, удаление только у причала, выключение/включение, предпросмотр, кандидаты, настройки); безопасность. Весь набор CS зелёный (10454 собрано, 2 xfail). Обнаружен баг (не исправлен, тесты xfail strict): sea_admin.delete_ship и _end_passes_for_route_change вызывают refund_not_started(), а затем сразу перечитывают активные места через active_passes(lock=True) с populate_existing() без flush (autoflush=False и в проде) — возвращённое место перечитывается как active и помечается completed, refund_op_id теряется (деньги при этом возвращаются верно). Исправление: db.flush() после refund_not_started() (или пропуск строк со статусом refunded)
[LOG] 2026-11-17 01:20 — Frontend Developer: T4 готово — роль «Капитан» (⚓) в constants/npc.ts; в форме локации флаги «Порт» + выбор «Выход в море» (L8) и «Морская зона» (только для скрытых стран, несовместима с портом/стартовой точкой), 409 бэкенда показываются тостом; страница /admin/ships (ProtectedRoute locations:read, ссылка в админке): список кораблей на раскрывающихся плашках (где сейчас, отплытие/прибытие, люди на палубе, проблемы: blocked_reason, капитан, сломанные участки), форма создания/правки (имя, палуба и капитан из A6, вместимость/матросы/сборы/скорость/цены с диапазонами, по кругу, «ходит»), редактор остановок с предпросмотром участков A5 и ручной цепочкой зон из соседей L8, удаление с подтверждением, вкладка «Настройки моря» (A7); api/seaAdmin.ts + types/seaAdmin.ts, 422 Pydantic переводятся в русский текст; метки sea_fare/sea_refund; tsc и build зелёные; живая проверка на тестовых данных T5 (просмотр, предпросмотр, ручной путь, 409 «Порт входит в маршрут…», настройки, 360 px) — данные не менялись, новых тестовых данных не создавал
[LOG] 2026-11-17 02:30 — Frontend Developer: T5 готово — окно капитана (кнопка «Корабль» у НПС-капитана: маршрут, отплытие/прибытие с отсчётом, билеты до портов с ценой и местами, матрос, заяц с предупреждением, «Мои места»; работает и на палубе в море), шапка палубы (корабль, капитан, у причала / в море: зона, море → порт, ETA, корабли рядом, мои места и предупреждение «высадят»), «У причала» в порту, переходы ⚓ «Подняться на борт / Сойти на берег» только постом без быстрого перемещения (сход с палубы виден и без билета — через шапку палубы), обработка ws «sea» (тосты по событиям, обновление /users/me и страницы, переход в порт после высадки), метка преступления «Безбилетный проезд»; tsc + build зелёные, живая проверка на временных «Морях» (2 корабля, 3 зоны, 2 порта): покупка билета в порту и в море, посадка, отплытие, «вдали виден корабль», прибытие, высадка безбилетника с переходом, заяц, 360 px; тестовые данные удалены, Ашари/Годрик возвращены
[LOG] 2026-11-15 — PM: фича создана по решению пользователя («по морю как предлагаешь»), запускаю анализ
[LOG] 2026-11-15 21:54 — Codebase Analyst: анализ завершён — разобраны караваны и охрана (FEAT-211/212), блокировка активности и её 3 копии, торговые ворота и роли НПС, карта мира (образец линии — плавающие структуры), телепорт как аналог прибытия, экономика (4 копии econ_core), отряды; раздел 2 заполнен, главные риски: проход караванов замирает при выключенной экономике, копии блокировки, где числится пассажир во время рейса
[LOG] 2026-11-15 22:05 — Architect: спроектировано 16 задач (7 backend, 4 frontend, 4 QA, 1 ревью), 13 новых API-контрактов (LS: 7, CS: 6) + 4 существующих расширены обратно-совместимо; маршруты и флаг порта — в locations-service, рейсы/билеты/блокировка/проход — в character-service, новых разрешений RBAC не нужно (locations:*), миграции CS 052_sea_voyages и LS 060_sea_routes
[LOG] 2026-11-15 22:40 — Backend Developer: T1 готово — миграция CS 052_sea_voyages (voyage_id + индекс, sea_voyages/sea_tickets/sea_messages/sea_settings с засеянной строкой, econ_caravans.route_legs/at_sea), ORM-модели, причина блокировки voyage («… на борту корабля», приоритет после охраны каравана), law_core.SOURCE_VOYAGE, явные вызовы compute_lock, скрытие пассажиров в /characters/by_location и отказ update_location; миграция up/down/up на MySQL чистая, тесты блокировки/закона/караванов зелёные
[LOG] 2026-11-15 22:30 — Backend Developer: T4 готова — в 4 копии econ_core.py добавлены sea_fare/sea_refund (SEA_OP_TYPES в OP_TYPES, не в SOURCE/COMMENT_REQUIRED), в 4 копии econ_contract_cases.py — 2 сценария (билет с налогом + полный возврат; нехватка денег, запрет источников, возврат уводит казну в минус) и SEA_OP_TYPE_NAMES; check_econ_copies.sh ок, контрактные тесты зелёные во всех 4 сервисах
[LOG] 2026-11-15 23:20 — Backend Developer: T3 готово — миграция LS 060_sea_routes (Locations.is_port + индекс, sea_routes с UNIQUE пары, FK CASCADE и явным индексом port_b), модель SeaRoute, схемы со строгой проверкой path_json, эндпоинты L1–L7 (роутер sea_router), нормализация пары с разворотом линии, фильтр скрытых стран / выключенных / не-портов, is_port в create/update и всех сериализаторах, 409 при снятии флага порта с маршрутами; миграция up/down/up на MySQL чистая, живая проверка через curl (создание, дубль, не-порт, скрытая страна, PATCH с разворотом, каскад при удалении локации), тесты LS зелёные; док locations-service.md дополнен
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Корабли — настоящие локации-палубы. У каждого корабля уникальный капитан-НПС: сервер сам переставляет его из порта на палубу при отплытии и обратно при прибытии.
- Маршрут из нескольких портов: туда-обратно или по кругу. В каждом порту корабль стоит время сборов.
- Три способа попасть на борт у капитана, после поста «Диалог с НПС»:
  - билет до выбранного порта: деньги идут в казну региона порта, страна получает налог;
  - работа матросом: нужен пост на палубе заданной длины;
  - «заяц»: бросок скрытности при отплытии, если поймали — преступление в регионе порта.
- Переход порт↔палуба существует только у причала и только для тех, у кого есть право. Ходить через него можно только постом.
- Правила отплытия: опоздавшие теряют билет; кто остался на палубе без права, тех высаживают; игроков в бою не трогают.
- Моря — скрытая страна: регионы — моря, локации — морские зоны с флагом `is_sea_zone`. Порт указывает зону, к которой выходит.
- Зоны никогда не связаны с сушей: туда нельзя пройти, телепортироваться, их не используют караваны и граф мира.
- Путь корабля по зонам строится сам при каждом отплытии, админ может переопределить его вручную.
- Корабли в одной зоне видят друг друга.
- Безопасная высадка при сломанных данных: удалён порт или палуба, маршрут потерял путь.
- Админка «Корабли» с вкладкой «Настройки моря», флаги «Порт» и «Морская зона» в форме локации.
- Интерфейс игрока: окно капитана, шапка палубы, полоса «У причала», уведомления о плавании.
- Тесты: 141 в locations-service, 262 в character-service.

### Что изменилось от первоначального плана
- Версия v1 («рейс-таймер» с блокировкой «на борту», маршруты порт-порт с линиями на карте области) отменена пользователем 2026-11-16 в пользу кораблей-локаций и скрытой страны «Моря».
- Билетов на весь отряд нет, по решению пользователя.

### Оставшиеся риски / follow-up задачи
- Этап 2: шторма и монстры, караваны по морю, таможня и контрабанда. Этап 3: пираты, свои корабли.
- Две косметические мелочи фронта занесены в ISSUES.md (LOW).
- На проде нужно создать страну «Моря», зоны, отметить порты и завести корабли с капитанами.

## Appendix A — v1 design (superseded 2026-11-16)

> Kept for reference only. Do not implement. What of it survives is listed in section 3.18.

### A.3 Architecture Decision (v1)

Abbreviations as in section 2 (CS, LS, BS, IS, PS, FE). Times are naive UTC everywhere (project convention).

#### A.3.1 Ownership (decision)

| Data / logic | Owner | Why |
|---|---|---|
| `Locations.is_port`, `sea_routes` (ports pair, duration, fare, boarding minutes, drawn line, active flag) | **LS** | Geography + map editors live in LS (EditLocationForm, floating-structure waypoint precedent, public `/locations/map/...` reads). Admin CRUD is plain map data. |
| Departures/voyages, tickets, passenger channel, voyage pass, fare/refund ledger posting, `characters.voyage_id` lock column, Captain NPC flow, caravan sea legs | **CS** | CS is the only writer of lock columns, owns NPC-role flows (Caravaneer/teleport template), law entry, `law_notify`, the scheduler and caravans. |
| Cross-reads | CS reads `sea_routes`, `Locations.is_port`, `Countries.is_hidden` by raw SQL (precedent `load_road_graph`, `region_gates`). LS never reads CS sea tables. |

No new HTTP dependency is added. CS reads PS tables `parties`/`party_members` from the shared DB for party tickets (3.6). The dependency graph doc changes only by «CS reads PS tables (shared DB)».

#### A.3.2 Data model

##### LS migration `060_sea_routes` (revision id = file stem, 14 chars; down_revision `059_location_neighbor_unique`)

```sql
ALTER TABLE Locations ADD COLUMN is_port TINYINT(1) NOT NULL DEFAULT 0;
CREATE INDEX ix_locations_is_port ON Locations (is_port);

CREATE TABLE sea_routes (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  port_a_id        BIGINT NOT NULL,              -- always the smaller location id (normalised by crud)
  port_b_id        BIGINT NOT NULL,              -- always the larger one
  duration_minutes INT NOT NULL,                 -- 10..1440
  fare             INT NOT NULL,                 -- 1..1000000 marks per passenger
  boarding_minutes INT NOT NULL DEFAULT 40,      -- 0..180 («сборы у причала»)
  path_json        JSON NULL,                    -- segments, see below; NULL = not drawn yet
  is_active        TINYINT(1) NOT NULL DEFAULT 1,
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_sea_routes_a FOREIGN KEY (port_a_id) REFERENCES Locations(id) ON DELETE CASCADE,
  CONSTRAINT fk_sea_routes_b FOREIGN KEY (port_b_id) REFERENCES Locations(id) ON DELETE CASCADE,
  CONSTRAINT uq_sea_routes_pair UNIQUE (port_a_id, port_b_id),   -- also serves as the FK index for port_a_id
  INDEX ix_sea_routes_port_b (port_b_id)                          -- explicit FK index (MySQL gotcha)
);
```

`path_json` = ordered list of segments from port A to port B, one per Area the line crosses (max 8 segments, 2..300 points each, `x`/`y` in **percent of that Area's map image**, 0..100):

```json
[{"area_id": 1, "points": [{"x": 41.2, "y": 63.0}, {"x": 55.0, "y": 70.4}]},
 {"area_id": 2, "points": [{"x": 3.0, "y": 40.0}, {"x": 22.5, "y": 38.1}]}]
```

First point of segment 0 = the port A anchor; last point of the last segment = the port B anchor; every other segment end is an
"area edge" (the line continues on another Area's map). Rollback: drop table, drop index + column.

##### CS migration `052_sea_voyages` (15 chars; down_revision `051_caravan_escorts`) — ALL CS schema of this feature (stage 1 + 2) in one migration

Econ-style tables: `_EconId` BigInteger PKs, **no FKs** (locations/routes/characters can disappear; everything shown later is snapshotted).

```sql
ALTER TABLE characters ADD COLUMN voyage_id BIGINT NULL;            -- sea_voyages.id; lock reason `voyage`
CREATE INDEX ix_characters_voyage ON characters (voyage_id);

CREATE TABLE sea_voyages (                  -- one departure of one ship in one direction
  id               BIGINT PK AUTO_INCREMENT,
  route_id         BIGINT NOT NULL,          -- LS sea_routes.id (no FK)
  from_location_id BIGINT NOT NULL,          -- departure port (snapshot)
  to_location_id   BIGINT NOT NULL,          -- destination port (snapshot)
  from_name        VARCHAR(255) NULL,        -- snapshots for display after deletions
  to_name          VARCHAR(255) NULL,
  duration_minutes INT NOT NULL,             -- snapshots taken when the departure is created
  boarding_minutes INT NOT NULL,
  fare             BIGINT NOT NULL,
  status           VARCHAR(16) NOT NULL,     -- boarding | sailing | arrived | cancelled
  cancel_reason    VARCHAR(32) NULL,         -- empty | route_closed | destination_lost | ...
  boarding_key     VARCHAR(64) NULL,         -- "{route_id}:{from_location_id}" while boarding, NULL afterwards
  created_at       DATETIME NOT NULL,
  departs_at       DATETIME NOT NULL,        -- created_at + boarding_minutes
  sailed_at        DATETIME NULL,
  arrives_at       DATETIME NULL,            -- sailed_at + duration_minutes
  finished_at      DATETIME NULL,
  UNIQUE KEY uq_sea_voyages_boarding (boarding_key),      -- one boarding departure per route direction (NULLs repeat)
  INDEX ix_sea_voyages_depart (status, departs_at),
  INDEX ix_sea_voyages_arrive (status, arrives_at),
  INDEX ix_sea_voyages_route (route_id, status),
  INDEX ix_sea_voyages_finished (finished_at)
);

CREATE TABLE sea_tickets (
  id                 BIGINT PK AUTO_INCREMENT,
  voyage_id          BIGINT NOT NULL,
  character_id       INT NOT NULL,
  buyer_character_id INT NOT NULL,           -- who paid (refunds go back to the payer)
  fare               BIGINT NOT NULL,
  fare_op_id         BIGINT NULL,            -- econ_operations.id of the sea_fare op
  refund_op_id       BIGINT NULL,
  status             VARCHAR(16) NOT NULL,   -- active | left | landed | refunded | released
  created_at         DATETIME NOT NULL,
  ended_at           DATETIME NULL,
  INDEX ix_sea_tickets_voyage (voyage_id, status),
  INDEX ix_sea_tickets_char (character_id, status)
);

CREATE TABLE sea_messages (                 -- the passenger channel
  id BIGINT PK AUTO_INCREMENT, voyage_id BIGINT NOT NULL, character_id INT NOT NULL,
  body VARCHAR(500) NOT NULL, created_at DATETIME NOT NULL,
  INDEX ix_sea_messages_voyage (voyage_id, id), INDEX ix_sea_messages_char (character_id, created_at)
);

CREATE TABLE sea_settings (id INT PK, pass_last_run_at DATETIME NULL);   -- seeded: INSERT (1, NULL)

-- stage 2
ALTER TABLE econ_caravans ADD COLUMN route_legs JSON NULL;            -- NULL = every leg is land (all old rows)
ALTER TABLE econ_caravans ADD COLUMN at_sea TINYINT(1) NOT NULL DEFAULT 0;
```

`econ_caravans.route_legs`: list of length `len(route) - 1`; entry `i` describes the edge `route[i] → route[i+1]`:
`null` = land, `{"sea": <sea_route_id>, "min": <duration_minutes>, "board": <boarding_minutes>}` = sea (snapshot at dispatch).
Rollback: drop the 4 tables, the 3 columns and the index. Downgrade must also NULL-safe drop (no data migration).

No UNIQUE (voyage, character) on tickets on purpose: a passenger who left during boarding may buy again; the double-click guard
is the locked character row + `voyage_id` (3.6).

#### A.3.3 Activity lock

- New reason `REASON_VOYAGE = "voyage"` in canonical `character-service/app/activity_lock.py`; `compute_lock(..., voyage_id=None)`
  (new last kwarg), `lock_for_character` passes `voyage_id`. **Priority:** jail > law_encounter > unconscious > dungeon >
  caravan_escort > **voyage** > asleep > reading. (A passenger can't get any higher lock while aboard, all those flows refuse
  locked characters; the order only matters for corrupted data.) `_lock()` dict shape is **unchanged** (no new key — tests
  compare whole dicts); the FE reads details from the voyage endpoint.
- `lock_message`: `f"{subject} на борту корабля"` (covers boarding and sea; public — passengers are not secret).
- Docstring: add the FEAT-213 paragraph. The upper part of the 3 copies (LS/BS/IS) stays byte-identical (CI test
  `test_activity_lock_copies_share_the_canonical_upper_part`).
- Copies' lower part: `_LOCK_SQL` gets `voyage_id` as the **8th (last) column**; new `_LOCK_SQL_ESCORT` = the current 7-column SQL
  (fallback when CS 052 is not applied); `_VOYAGE_COLUMNS = ("voyage_id",)`; `_lock_from_row` passes `voyage_id=_col(row, 7)`.
  Fallback chain: full → (missing law col → LEGACY) | (missing escort col → LAW → LEGACY) | (missing voyage col → ESCORT →
  on missing escort col → LAW → on missing law col → LEGACY). Warning text in Russian like the existing ones
  («characters.voyage_id ещё нет (миграция character-service 052 не применена) — блокировка читается без плаваний»).
- Explicit callers: `law_crud.check_patrol_arrival` (:555) and `caravan_escort_public.public_lock` (:61) pass
  `voyage_id=getattr(ch, "voyage_id", None)` (a stranger sees «на борту корабля»; the escort column stays dropped there).
- CS move guards: `update_location` (`main.py:~2407`) adds `REASON_VOYAGE` to the refused set. `execute_teleport` and the home
  teleport already refuse any lock. `_prepare_move` (admin forced move): after the escort release, call
  `sea_crud.release(db, character_id, reason="admin_move")` (ends the ticket with a full refund to the payer, clears
  `voyage_id`, own commit, notice published) — same pattern as `caravan_escort_crud.release`.
- LS `check_not_locked_for_post`/`check_not_locked_for_move`, BS battle joins, IS actions, dungeon-service (HTTP lock),
  faction eject `_busy`, patrol arrival — all refuse/skip any lock already; nothing else to change there.
- FE: `ActivityLockReason` gets `'voyage'` (not in `TIMED_REASONS`; the countdown comes from the voyage endpoint).

#### A.3.4 Where a passenger "is" (decision)

`characters.current_location_id` **stays at the departure port** from boarding until arrival (never NULL — `move_and_post`
treats NULL as "may go anywhere"). `characters.voyage_id IS NOT NULL` (boarding or at sea) hides the passenger from every
"who is here" list — a passenger is on the ship, not on the street. Hidden from the moment of boarding (one column, no join;
the Captain modal shows the passenger count and the voyage view shows the passengers). Queries to adjust:

| # | Query | File | Change |
|---|---|---|---|
| 1 | Location players list (LS location page, dungeon-service use it) | CS `main.py:2297` `/characters/by_location` | add `models.Character.voyage_id.is_(None)` |
| 2 | Party co-located roster (`active-members`, `by-location`, party actions, BS squad roster via PS) | PS `crud.py:128` `_AT_LOCATION_SQL` | add `AND voyage_id IS NULL`; new skew fallback `_AT_LOCATION_SQL_ESCORT` (current SQL) when `voyage_id` is the missing column, then the existing legacy fallback |
| 3 | Battle / raid / escort-hire / gathering / dungeon eligibility | lock copies + CS `lock_for_character` | covered by the lock (3.3) |
| 4 | Patrol arrival, faction eject | CS `law_crud`, `faction_territory._busy` | covered by the lock (explicit kwarg in law_crud) |
| 5 | Battle spectating (`battle_visibility.py:103`) | BS | **not changed**: viewing a port battle log from the ship is harmless and joining is lock-refused |

#### A.3.5 Departure scheduling (decision)

- A departure (`sea_voyages` row, status `boarding`) is created **on the first ticket purchase** for a route direction
  (`route_id`, `from_location_id`) when no boarding departure exists. `departs_at = now + boarding_minutes`. Ships are
  never "always leaving": no buyer → no departure.
- Later buyers join the existing `boarding` departure (even if `departs_at` passed and the pass has not sailed it yet — it sails
  within ≤ 1 scheduler poll). Once it sails (`boarding_key` → NULL) the next purchase creates a new departure.
- `boarding_key` UNIQUE = race guard: two simultaneous first purchases → one INSERT fails with IntegrityError → the API rolls back
  and retries the whole purchase once (then joins the departure the other request created).
- `boarding_minutes = 0` → the departure sails on the next pass (≤ ~60 s).
- Fare, duration, boarding minutes and names are snapshotted on the departure; later admin edits affect only new departures.

#### A.3.6 Player flows (CS, new modules `sea_crud.py`, `sea_api.py`, `sea_schemas.py`)

**Captain role.** `CAPTAIN_ROLE = "captain"` (backend constant in `sea_crud.py`; FE `constants/npc.ts` `{ value: 'captain',
label: 'Капитан' }`, icon ⚓). No admin NPC tab, no role-change side effects (departures are keyed by route, not by NPC).

**Captain context** (copy of `_caravaneer_context`): 1) owner + player character (`require_owner` style, 404/403); 2) NPC exists,
`is_npc`, role `captain`, alive, has a location (404 «Капитан не найден»); 3) same location (400 «Нужно находиться рядом с
капитаном»); read tx closed → 4) `locations_client.check_npc_gate` (FEAT-145 «Диалог с НПС», fail-closed 503/403, same Russian
texts as the caravaneer, `npcDialogueGate.ts` detects them); 5) `reputation_crud.require_npc_tier`. Endpoints that do HTTP are
`async` + sync crud in `run_in_threadpool` (pattern of `caravan_escort_api.py`).

**Routes from a port** (`routes_from(db, location_id)`, raw SQL): `sea_routes` where `port_a_id = :l OR port_b_id = :l`,
`is_active = 1`, both endpoint `Locations.is_port = 1`, the other port exists, and neither port's country `is_hidden`
(country via `econ_ledger.resolve_location`). Deploy skew: `sea_available(db)` = `sea_routes` table and `Locations.is_port`
present (inspector, cached like `gate_tables_available`) — else the Captain answers 503 «Морские рейсы пока недоступны».

**Eligibility of one character** `passenger_refusal(db, ch, route, to_location_id)` in this order (Russian reasons):
`voyage_id` set → «Уже на борту корабля»; activity lock → `lock_message`; `_in_battle` → «В бою»; `_gathering` → «Собирает
ресурсы» (reuse `caravan_escort_crud._in_battle/_gathering`, read-only import); `faction_territory.location_refusal(db, ch,
to_location_id)` → its text. For squadmates also: not at the port → «В другой локации». (Teleport parity: no wanted check.)

**Purchase** (`buy(db, ctx, route_id, for_squad, now)`, no commit; caller commits then publishes notices). Lock order
**voyage → tickets → characters (ascending id)** — same shape as caravan → escorts → characters:
1. Route valid and starts at `ctx.location_id` (else 404 «Маршрут не найден» / 409 «Рейс закрыт»); destination = the other port.
2. Open departure: `SELECT ... FROM sea_voyages WHERE boarding_key = :k FOR UPDATE`; none → INSERT (snapshots) + flush.
3. Candidates: buyer; if `for_squad`, + accepted squadmates (shared-DB read, below). Lock all candidate `characters` rows
   `FOR UPDATE` in ascending id.
4. Buyer refusal → raise (409/403 with the reason). Squadmates: refusal → `skipped[]`, else `boarding[]`.
5. Funds: `total = fare × len(boarding)`; buyer `currency_balance < total` → 402
   `{"error": "insufficient_gold", "message": insufficient_funds_message(db), "required": total, "balance": b}`.
6. Per passenger: INSERT ticket (status `active`, `buyer_character_id`, `fare`), flush, post `OP_SEA_FARE` (3.8) with
   idempotency key `sea_fare:{ticket_id}`, store `fare_op_id`; set `characters.voyage_id`, `house_room_id = NULL`;
   `CharacterLog(event_type='voyage')`. `InsufficientFunds` → rollback → 402 (nothing boarded).
7. Notices (after commit): buyer «Вы на борту: рейс в {to}, отплытие через N мин»; every other passenger «{buyer} купил вам
   билет: рейс в {to}, отплытие через N мин. Сойти на берег можно до отплытия».
Double click: the second request waits on the voyage/characters locks, then sees `voyage_id` → 409 «Уже на борту корабля».

**Party lookup (decision: shared-DB read, not HTTP).** `SELECT pm2.character_id FROM party_members pm JOIN party_members pm2
ON pm2.party_id = pm.party_id AND pm2.status = 'accepted' WHERE pm.character_id = :me AND pm.status = 'accepted'`. Reasons:
the eligibility must be evaluated under the characters' row locks inside the purchase transaction (an HTTP call while holding
locks is forbidden by our pattern, and an HTTP snapshot would race); CS already reads foreign tables (battles, gathering,
dungeons, Locations) this way; no new env var / token / dependency. Missing tables (tests/skew) → squad = empty.

**Leave during boarding** (`leave(db, character_id)`): lock voyage → ticket → character; voyage `boarding` required, else 409
«Корабль уже в море — сойти нельзя»; post `OP_SEA_REFUND` (reverse of the ticket's fare postings, to the payer), ticket
`left`, `voyage_id = NULL`; notice to the passenger (and to the payer if different: «{name} сошёл на берег, билет возвращён»).
The character never moved, so he is simply back on the street of the port.

**Release** (`release(db, character_id, reason)`) — forced end from outside (admin move): any status, full refund to the payer,
ticket `released`, `voyage_id = NULL`. Idempotent (no active ticket → no-op).

**Channel** (copy of escort C5/C6): membership = an `active` ticket of that voyage; last 100 / `after_id` paging; 1..500 chars
after strip; 3 s throttle per character (429 «Слишком часто»); author name/avatar in output.

#### A.3.7 The sea pass (CS `sea_pass.py`, offline-safe, independent of the economy toggle)

Called from `econ_scheduler.run_scheduled_once` right after `run_faction_pass` (new `run_sea_pass(factory)` wrapper that logs
and swallows). Like law/faction passes it runs **even when the economy tick is switched off in the DB** (only the
`ECON_TICK_ENABLED` env that starts the thread matters; default 1 in both compose files). Own throttle: conditional UPDATE claim
on `sea_settings.pass_last_run_at`, `RUN_INTERVAL_SECONDS = 25` (so every 60 s scheduler poll runs it). Missing table/row
(skew) → `None`. Tests call `run_pass(factory, now=..., force=True)`. Each voyage = its own short transaction (best effort,
failures logged, retried next pass). Steps:

1. **Close invalid boarding departures** — every `boarding` voyage whose route is gone / inactive / an endpoint lost `is_port`
   / a port location deleted / a port's country became hidden → `cancelled` (`route_closed`), every active ticket refunded
   (`refunded`), `voyage_id` cleared, `boarding_key = NULL`. Passengers never moved → safe.
2. **Sail** — `boarding` with `departs_at <= now`: lock voyage → active tickets → characters. Tickets whose character is gone,
   `voyage_id` ≠ this voyage or `current_location_id` ≠ `from_location_id` → `released` + refund (defence; normally
   impossible). No passengers left → `cancelled` (`empty`). Else `sailing`, `sailed_at = now`,
   `arrives_at = now + duration_minutes`, `boarding_key = NULL`. After commit: notice «Корабль отплыл. Прибытие в {to} через
   N мин», and best-effort `locations_client.notify_character_left_location_sync(cid, from_location_id)` per passenger (expires
   gates/gate requests in the port + party leave-on-move; like the teleport master).
3. **Arrive** — `sailing` with `arrives_at <= now`: lock voyage → tickets → characters. If the destination location exists:
   per passenger with `voyage_id == voyage.id`: `voyage_id = NULL`, `current_location_id = to_location_id`,
   `house_room_id = NULL`, ticket `landed`, CharacterLog, then `law_crud.check_entry(db, ch, to, law_core.SOURCE_VOYAGE,
   from_location_id=from)` in the same transaction (new constant `SOURCE_VOYAGE = "voyage"` added to `ENTRY_SOURCES`, not to
   `MOVE_SOURCES`). Voyage `arrived`, `finished_at`. After commit: notice «Корабль прибыл в {to}» (+ the encounter / slip
   notices exactly like `execute_teleport` produces them). **Destination location deleted** → passengers stay at the departure
   port (location unchanged, «корабль вернулся в порт отправления»), full refund, voyage `cancelled` (`destination_lost`). If
   the departure location is gone too, the lock is still cleared and the fare refunded (the character is in the same state as
   anyone standing in a deleted location — existing behaviour). Route deletion / port unflag during sailing does **not** affect
   a sailing voyage (all snapshots).
4. **Housekeeping** — `characters.voyage_id` pointing to a voyage that is not boarding/sailing or without an active ticket for
   that character → cleared; active tickets of deleted characters → `released` (no refund: the deletion op already settled the
   wallet); channel messages of voyages finished > 7 days ago → deleted (`MESSAGES_KEEP` like escorts).

Notifications: `law_notify.Notice(user_id, text, ws_type="voyage", category=CATEGORY_PROGRESS, data={"character_id",
"voyage_id", "event": boarded|sailed|arrived|left|cancelled|released})`, published after commit. FE adds `'voyage'` to
`LAW_LOCK_REFRESH_TYPES` (refreshes `/users/me`).

#### A.3.8 Economy

- New op types in **all four** byte-identical `econ_core.py` copies (CS, IS, LS, dungeon-service) + all four
  `tests/econ_contract_cases.py` copies (CI `scripts/check_econ_copies.sh`):
  `OP_SEA_FARE = "sea_fare"` (character → region treasury, taxed like the teleport) and
  `OP_SEA_REFUND = "sea_refund"` (reverse postings, untaxed), `SEA_OP_TYPES = frozenset({...})` added to `OP_TYPES`;
  not in `SOURCE_OP_TYPES` / `COMMENT_REQUIRED_OP_TYPES`. Contract cases: a fare case (char → region + generated country tax
  leg) and a refund case (region → char, country → region; balances back to the start).
- **Where the fare goes (follows the teleport, as instructed):** `payer_account(db, from_location_id)` = the departure port's
  **region treasury** (else «Казна Скитальцев» for an unresolvable location), with the automatic `region → country` tax leg —
  the country of the departure port gets its tax share. (If the game designer wants 100 % in the country treasury, it is a
  one-line change: `AccountRef.country(country_id)` with `apply_tax=False`; see the open question.)
- Refund = read `econ_postings` of `fare_op_id` (joined to `econ_accounts` for kind/ref_id), post every posting reversed
  (`to → from`, same amount) as one `OP_SEA_REFUND` op, `leg_type = LEG_REFUND`, `apply_tax=False`, idempotency key
  `sea_refund:{ticket_id}` (`DuplicateOperation` = already refunded → treat as success). Treasuries may go negative, so a refund
  never fails. Money is conserved exactly even if the tax rate changed meanwhile.
- FE `economyLabels.ts`: `sea_fare: 'Морской рейс: билет'`, `sea_refund: 'Морской рейс: возврат'`.

#### A.3.9 API contracts

All CS player endpoints: JWT (`get_current_user_via_http`) + the character's owner; Pydantic v1; Russian `detail`; existing Nginx
limits on `/characters/` and `/locations/` apply (purchases are serialized by row locks, the channel has the 3 s throttle) — no
Nginx changes. Routers: CS `sea_router` (prefix `/characters`) included in `main.py` **before** the main router (static
`/sea/...` paths). LS: endpoints added to the existing LS routers/prefix `/locations` (admin under `/locations/admin/...`).

##### LS

| # | Method / path | Auth | Request | Response |
|---|---|---|---|---|
| L1 | `GET /locations/admin/sea-routes` | `require_permission("locations:read")` | — | `SeaRouteRead[]` |
| L2 | `POST /locations/admin/sea-routes` | `locations:create` | `SeaRouteCreate` | 201 `SeaRouteRead` |
| L3 | `PATCH /locations/admin/sea-routes/{id}` | `locations:update` | `SeaRouteUpdate` (all optional) | `SeaRouteRead` |
| L4 | `DELETE /locations/admin/sea-routes/{id}` | `locations:delete` | — | 204 |
| L5 | `GET /locations/admin/sea-ports` | `locations:read` | — | `[{id, name, region_id, region_name, country_id, country_name, area_id}]` (all `is_port = 1`) |
| L6 | `GET /locations/map/sea-routes?area_id=` | public | optional `area_id` (only routes having a segment in that area) | `SeaRoutePublic[]` |
| L7 | `GET /locations/map/sea-routes/{id}` | public | — | `SeaRoutePublic` (404 when hidden/inactive/missing) |

```
SeaRouteCreate { port_a_id: int, port_b_id: int, duration_minutes: int (10..1440), fare: int (1..1_000_000),
                 boarding_minutes: int = 40 (0..180), is_active: bool = True, path_json: Optional[List[Segment]] }
Segment        { area_id: int (existing Area), points: List[{x: float 0..100, y: float 0..100}] (2..300) }   # <= 8 segments
SeaRouteRead   { id, port_a_id, port_a_name, port_b_id, port_b_name, port_a_country_id/_name, port_b_country_id/_name,
                 duration_minutes, fare, boarding_minutes, is_active, path_json, created_at, updated_at }
SeaRoutePublic { id, duration_minutes, fare, boarding_minutes,
                 port_a: {location_id, name, region_id, country_id, country_name},
                 port_b: {...}, segments: List[Segment],
                 areas: List[{id, name, map_image_url}] }        # areas referenced by the segments (edge labels, mini-map)
```

Validation (400/404/409, Russian): ports exist and differ; both `is_port` (409 «Локация не отмечена как порт»); pair normalised
`a < b` (swap ports **and reverse `path_json`** — segment order and each point list — so the line still runs A → B); duplicate
pair → 409 «Такой морской маршрут уже есть»; areas exist. L6/L7 return only `is_active` routes whose both ports are still
`is_port` and whose ports' countries are not `is_hidden`; routes with `path_json IS NULL` are still listed (the FE simply draws
nothing) — Captain still sells them.

Location changes: `LocationCreate/LocationUpdate` get `is_port: Optional[bool]` (null = leave as is, like `is_starting`);
every location serializer that already emits `no_quick_move` also emits `is_port` (crud ≈ :407, :421, :732, :1025, :1282, :2764,
:3273 and the region-details locations used by the region map). **Unflagging** a port referenced by any sea route → 409
«Сначала удалите морские маршруты этого порта». Deleting a location cascades its routes (FK); CS handles the consequences (3.7).
RBAC: **no new permission** — sea routes are map data edited in the locations admin, so `locations:read/create/update/delete`
(admin auto-gets all; moderators/editors as for locations). Hence no user-service migration and no RBAC test seed.

##### CS (player)

| # | Method / path | Notes |
|---|---|---|
| S1 | `GET /characters/sea/captain/{npc_id}?character_id=` | async; context steps 1–5 → `CaptainViewOut` |
| S2 | `POST /characters/sea/routes/{route_id}/tickets` body `{character_id, npc_id, for_squad: bool=false}` | async; context → purchase (retry once on `boarding_key` IntegrityError) → 201 `TicketPurchaseOut` |
| S3 | `GET /characters/sea/voyage?character_id=` | own voyage `{"voyage": VoyageOut | null}` |
| S4 | `POST /characters/sea/voyage/leave` body `{character_id}` | → `{left: true, refunded: int, refunded_to_character_id: int}`; 409 at sea |
| S5 | `GET /characters/sea/voyage/messages?character_id=&after_id=0` | → `{voyage_id, messages: [{id, character_id, name, avatar, body, created_at}]}`; 403 «Вы не на корабле» |
| S6 | `POST /characters/sea/voyage/messages` body `{character_id, text}` | 201 message; 400 length; 429 throttle |

```
CaptainViewOut { npc_id, location_id, location_name, balance: int, my_voyage_id: Optional[int],
                 routes: [{ route_id, to_location_id, to_name, to_region_name, to_country_name,
                            duration_minutes, fare, boarding_minutes,
                            departure: Optional[{voyage_id, departs_in_sec: int, passenger_count: int}],
                            can_buy: bool, reason: Optional[str] }],
                 squad: Optional[{ party_id, members: [{character_id, name, avatar, eligible: bool, reason: Optional[str]}] }] }
                 # squad excludes the viewer; null when not in a party; `reason` per route = the viewer's own refusal
TicketPurchaseOut { voyage: VoyageOut, total_fare: int,
                    boarded: [{character_id, name}], skipped: [{character_id, name, reason}] }
VoyageOut { id, route_id, status, from_location_id, from_name, to_location_id, to_name,
            duration_minutes, boarding_minutes, fare, departs_at, sailed_at, arrives_at, server_now,
            passengers: [{character_id, name, avatar}],           # active tickets
            my_ticket: {id, status, fare, buyer_character_id, buyer_name},
            can_leave: bool }                                     # status == boarding
```
Errors (S1/S2): 404 captain/route/character; 400 not next to the captain; 403 owner / dialogue gate / reputation / faction
territory; 409 «Здесь нет порта», «Рейс закрыт», «Уже на борту корабля», lock text, «В бою», «Собирает ресурсы»;
402 insufficient (object detail above); 503 gate unavailable / «Морские рейсы пока недоступны».

##### CS changed contracts (backward compatible, additive)

- `GET /characters/caravans/escort` (C3) job body: `at_sea: bool`, `legs: [{index, kind: 'land'|'sea', minutes: Optional[int]}]`.
- `POST /characters/caravans/escort/leave` (C4): 409 «Караван в море — сойти нельзя» while `at_sea`.
- Admin caravan list/overview rows (`economy_caravan_crud` ≈ :944): `at_sea: bool`, `route_legs`; `current_location_id/name`
  are null while at sea.
- `GET /characters/caravans/caravaneer/{npc_id}` (C1) also lists caravans waiting in **this port** before a sea leg (3.10).

#### A.3.10 Stage 2 — caravans with sea legs (CS)

**Graph.** `load_road_graph` additionally loads sea edges: `SELECT s.id, s.port_a_id, s.port_b_id, s.duration_minutes,
s.boarding_minutes FROM sea_routes s JOIN Locations a ON a.id = s.port_a_id AND a.is_port = 1 JOIN Locations b ON b.id =
s.port_b_id AND b.is_port = 1 WHERE s.is_active = 1` into `RoadGraph.sea: {(a, b) and (b, a): SeaEdge(route_id, minutes,
board)}` (missing table/column → no sea edges). Hidden countries are not filtered (NPC caravans; only players are hidden from them).

**Routing** (`caravan_route.py`, pure): new `fastest_route(adj, sea, blocked, start, goal, max_steps, land_minutes)` →
`(route, legs, reason)`.
- If `sea` is empty → returns `shortest_route(...)` with `legs = None` — **exactly today's behaviour and route choice**.
- Else Dijkstra on time: land edge weight = `max(1, caravan_step_minutes)`, sea edge weight = `minutes + board` (a sea leg is
  never preferred for being one hop). Determinism: heap of `(cost, node)`, neighbours (land ∪ sea endpoints) visited in
  ascending id, relax only on strictly lower cost; when land and sea connect the same pair the cheaper wins, tie → land.
  Dungeons stay blocked. `too_long` when the found path has more than `max_steps` hops (land + sea).
- `legs`: list aligned to edges, `None` for land, `{"sea": route_id, "min": minutes, "board": board}` for sea; if the path has
  no sea edge → `legs = None`.
`RoutePlanner.route()` keeps its signature (callers unchanged) and caches `(route, reason)`; new `RoutePlanner.legs(from, to)`
returns the cached legs for the same key. `dispatch` stores `row.route_legs = planner.legs(...)`.
No path at all (no land, no sea) → abstract caravan as today («минуя дороги») — unchanged.

**Stepping** (`caravan_pass.step_caravan`), with `leg(i)` = sea dict of `route_legs[i]` or None (NULL `route_legs` = all land →
old rows behave exactly as now):
1. `held_by` first, unchanged (at sea it can never hold: no raid can start, `post_hold(None)` is False).
2. `row.at_sea` and due → **land**: `index += 1`, `current_location_id = route[index]`, `at_sea = 0`, `move_escorts`; last index →
   `arrived`; else `next_move_at = now + port_wait(leg(index))` if the next edge is sea, else `step_delay`. Outcome `landed`.
3. Not at sea and `leg(index)` is sea → **sail**: `at_sea = 1`, `current_location_id = NULL`, `next_move_at = now + min`.
   Escorts stay on the departure port's `current_location_id` (`move_escorts` already no-ops on NULL) — they keep the
   `caravan_escort` lock and are hidden as before. Outcome `sailed`.
4. Otherwise the land step as today; after moving to `index`, if `leg(index)` is sea → `next_move_at = now + port_wait` (the
   caravan «грузится» in the port: `port_wait = timedelta(minutes=leg["board"])`, ≥ 1 step when 0) else `step_delay`.
`run_pass` stats gain `sailed` / `landed`. After a raid in a port the existing follow-up sets `next_move_at = now + step_delay`;
then the caravan sails — existing raid rules (one raid ever, continues with what is left).

**Invulnerable at sea** comes from `current_location_id = NULL`: `caravans_here`, `begin_raid` (location equality), LS
`crud.py:173` caravan-gate check, `post_hold`, `_preparing_here` all key on it → nothing to attack or post against. Additional
explicit guards: escort `leave` refuses at sea; `deliver_physical` untouched.

**Hireable in ports.** `_preparing_here` / `_caravan_refusal` accept, besides `route_index == 0`, a caravan that is **waiting in a
port before a sea leg** (`not at_sea`, `route_index > 0`, `leg(route_index)` is sea, `current_location_id == caravaneer's
location`, never raided). Same seats / no-rejoin / pay rules as at the gate.

**Escort/admin views**: C3 adds `at_sea`/`legs`; admin overview rows add `at_sea`/`route_legs` (FE shows «в море»).

#### A.3.11 Frontend

All new code TypeScript + Tailwind, no `React.FC`, mobile 360px+, Russian errors via toast/inline (no silent catches),
design-system classes (`modal-overlay`/`modal-content` via `ModalShell`, `gold-text`, `btn-blue`, `btn-line`, `gray-bg`, …).

Player:
- `api/seaVoyages.ts` + `types/seaVoyages.ts` (S1–S6).
- `components/pages/LocationPage/CaptainModal/CaptainModal.tsx` (template `CaravaneerModal.tsx`): list of routes from this port
  — destination (port, country), duration (ч/мин), fare (`currency_forms`), departure state («Сборы: отплытие через MM:SS,
  на борту N» or «Корабль соберётся через {boarding} мин после первого билета»); buttons «Купить билет» and «Купить на отряд»
  (shows the squad list with ✔/reason before confirming; result lists who boarded and who was skipped with reasons); disabled
  state with the `reason`; 402 → «Недостаточно …»; dialogue-gate 403 → the existing `npcDialogueGate` hint (add a Captain hint).
- `NpcProfileModal.tsx`: button «Морские рейсы» for `npc_role === 'captain' && isCharacterHere && characterId` (swap like
  `caravaneerOpen`).
- `components/SeaVoyage/SeaVoyageModal.tsx`: status (сборы / в море), from → to, countdown to departure or arrival
  (`useCountdownTo`), passengers list, «Сойти на берег» (only `can_leave`, confirm, shows the refund), the channel, and a
  mini-map when the route has segments (L7: area image + polyline + ship marker at `progress = elapsed / duration` along the
  segments laid end to end; reuse `interpolatePolyline` by exporting it from `FloatingStructuresLayer.tsx` or moving it to a
  small util). Polls S3 every 30 s and when the countdown hits 0 («Прибываем…»).
- `components/SeaVoyage/SeaVoyageChannel.tsx`: template `CaravanEscortChannel.tsx`, `POLL_MS = 15_000`.
- Lock UI: `useActivityLock.ts` (`'voyage'`), `ActivityLockBanner.tsx` (voyage branch: «На борту корабля» + button opening
  `SeaVoyageModal`), `LocationPage.tsx:~1061` reason text, `useWebSocket.ts` `'voyage'` in `LAW_LOCK_REFRESH_TYPES`; arrival /
  sailing notifications arrive through the existing notification pipeline (no extra UI needed beyond the refresh).
World map:
- `components/WorldPage/SeaRoutesLayer.tsx`: SVG overlay (`viewBox="0 0 100 100"`, `preserveAspectRatio="none"`,
  `pointer-events-none` except markers) rendered by `InteractiveMap` at **area** level (new prop `seaAreaId?: number`, set by
  `WorldPage` when `viewLevel === 'area'`, not in Citadel/city views). Draws every segment of L6(`area_id`) whose `area_id`
  matches: dashed sea-blue line; ⚓ anchor buttons at port ends (tap/hover card: port, country, duration, fare); at an area-edge
  end a small «→ {area name}» chip navigating to `/world/area/{id}`. Data via a tiny hook `useSeaRoutes(areaId)` (local state,
  visible error toast on failure). Hidden routes never arrive (filtered server-side).
- Region map: location markers with `is_port` get a small ⚓ badge (`RegionInteractiveMap`; `is_port` added to its location
  type).
Admin:
- `constants/npc.ts`: Captain role + icon.
- `EditLocationForm.tsx`: checkbox «Порт (морские рейсы)» next to `no_quick_move` (same Tailwind markup), 409 on unflag shown.
- `components/AdminLocationsPage/SeaRoutesPage.tsx` (`/admin/sea-routes`, `ProtectedRoute requiredPermission="locations:read"`,
  link in `Admin/AdminPage.tsx` with `module: 'locations'`): list (ports, countries, duration, fare, boarding, active,
  drawn yes/no), create/edit form (port selects from L5, numbers with hints, active toggle), delete with confirm, «Нарисовать
  линию» → `SeaRouteEditor.tsx` (template `FloatingRouteEditor.tsx` + `waypointUtils.ts`): segment tabs (add segment = pick an
  Area, draw on its `map_image_url`; reorder/delete segments; click append, shift-click insert, right-click delete, drag);
  saves via L3. Create/edit/delete buttons respect `hasPermission('locations:create'|'update'|'delete')`.
- `api/seaRoutes.ts` + `types/seaRoutes.ts` (L1–L7, also used by the world map layer and the voyage mini-map).
- `economyLabels.ts`: the two op labels.
Stage 2:
- `CaravanEscort/CaravanEscortRoute.tsx` / `CaravanEscortModal.tsx`: sea legs shown as ⚓ «морем, N мин», «в море» state,
  «Сойти» disabled at sea (server text on 409); `types/caravanEscort.ts` fields.
- Admin caravan list (`Admin/EconomyPage/EconomyCaravans.tsx` or the component rendering the overview rows): «в море» instead of
  an empty location.

#### A.3.12 Data flow (purchase → arrival)

```
Player → FE CaptainModal → CS S2 (async)
   CS: owner/NPC/location (read tx) → LS GET /locations/internal/action-gate (no tx open) → rep tier
   CS tx: lock sea_voyages(boarding_key) | INSERT → lock characters (asc) → tickets + econ sea_fare ops
          (character → region treasury, + region → country tax) → characters.voyage_id → COMMIT → RabbitMQ notices
Scheduler thread (every 60 s, own claim) → sea_pass:
   boarding & departs_at<=now → sailing (+ LS character-left-location best effort, notices)
   sailing & arrives_at<=now → characters.current_location_id = destination, voyage_id = NULL, law check_entry → COMMIT → notices
FE: /users/me refresh on ws 'voyage'; SeaVoyageModal polls S3 / S5.
```

#### A.3.13 Edge cases (summary)

| Case | Behaviour |
|---|---|
| Double «Купить» | second request serialized on row locks → 409 «Уже на борту корабля»; fare op idempotency per ticket |
| Two first buyers at once | `boarding_key` UNIQUE → retry joins the other departure |
| Squadmate elsewhere / busy / in battle / gathering / on another ship / closed faction territory at destination | skipped with the reason; buyer sees `boarded`/`skipped` |
| Buyer can't afford the whole squad | 402 with `required`; nothing bought (no partial) |
| Squadmate leaves during boarding | refund goes to the **payer** (reverse postings) |
| Leave at sea | 409 «Корабль уже в море — сойти нельзя» |
| Passenger offline | pass lands him; notice waits in notifications |
| Route deleted / deactivated / port unflagged / port location deleted while **boarding** | departure cancelled on the next pass, everyone refunded, they never left the port |
| Same while **sailing** | voyage completes from snapshots |
| Destination location deleted while sailing | passengers stay in the departure port, refunded (`destination_lost`) |
| Unflag a port with routes | LS 409 (delete routes first) |
| Admin forced move of a passenger | `_prepare_move` releases the ticket with a full refund, then moves |
| Character deleted mid-voyage | housekeeping releases the ticket, no refund |
| Economy tick off in the DB | voyages still sail/arrive (own pass); caravans freeze as before |
| Arrival into guards while wanted | `check_entry(source='voyage')` — same as teleport |
| Caravan at sea | `current_location_id = NULL` → not listed, not raidable, no post holds; escorts stay locked & hidden, can't leave |
| Caravan raided in port | existing raid rules (one raid ever, continues afterwards and then sails) |
| Old in-flight caravans | `route_legs NULL` → all-land stepping exactly as before |
| No sea edges configured | `fastest_route` delegates to BFS → identical routes to today |
| Deploy skew CS 052 not applied | lock copies + PS fall back (3.3, 3.4) |
| Deploy skew LS 060 not applied | CS `sea_available` false → Captain 503 «Морские рейсы пока недоступны», planner without sea edges |

#### A.3.14 Security

- Every CS player endpoint: JWT + owner check; the Captain flow requires presence + FEAT-145 dialogue gate + reputation tier
  (fail-closed). Inputs validated by Pydantic (`ge=1` ids, text 1..500 after strip, bool flags); raw SQL only with bound
  parameters; error texts never leak internals (500 → generic Russian text, details logged).
- LS admin endpoints: `require_permission("locations:*")`; `path_json` strictly validated (types, ranges, counts) — no free
  JSON stored.
- Money: row locks + conditional debits + per-ticket idempotency keys; refunds idempotent; all movements in the ledger.
- Abuse: channel throttle 3 s; squad purchase limited to accepted members of the buyer's own party standing in the same port.

#### A.3.15 Out of scope / follow-ups

Pirates and storms (stage 3), secret routes, public ship markers of other players' voyages on the world map, sea edges in the
admin `/map` force graph, an admin voyages monitor. Technobook article — PM.

---

### A.4 Tasks (v1)

Parallel waves (no two concurrent tasks edit the same file):
**Wave A:** T1, T3, T4 · **Wave B:** T2 (after T1), T5 + T6 (after T1, T3, T4), T8 (after T3, T4) ·
**Wave C:** T7, T9, T10, T11, T12, T13 · **Wave D:** T14, T15 · **Last:** T16.
Every backend task: `python -m py_compile` on all touched files; no commits/pushes by agents (the user commits once at the end).
Every frontend task: `npx tsc --noEmit` and `npm run build` inside the frontend container (no node on the host).

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| T1 | CS schema + canonical lock: migration `052_sea_voyages` (3.2: `characters.voyage_id` + index, `sea_voyages`, `sea_tickets`, `sea_messages`, `sea_settings` seeded row, `econ_caravans.route_legs`/`at_sea`); ORM models; `REASON_VOYAGE` + `compute_lock(voyage_id=)` + priority + message «… на борту корабля» + docstring (3.3); `law_core.SOURCE_VOYAGE` in `ENTRY_SOURCES`; explicit `compute_lock` callers (law_crud:555, `caravan_escort_public.public_lock`); `/characters/by_location` hides `voyage_id IS NOT NULL`; `update_location` refuses `voyage` | Backend Developer | DONE | `services/character-service/app/models.py`, `.../app/alembic/versions/052_sea_voyages.py`, `.../app/activity_lock.py`, `.../app/law_core.py`, `.../app/law_crud.py`, `.../app/caravan_escort_public.py`, `.../app/main.py` | — | Migration upgrade/downgrade clean on MySQL (revision id == stem, ≤ 32 chars, explicit indexes); `_lock()` dict shape unchanged; priority exactly jail > law_encounter > unconscious > dungeon > caravan_escort > voyage > asleep > reading; existing CS tests still green; py_compile passes |
| T2 | Lock copies + party roster: copy the new canonical upper part byte-for-byte into LS/BS/IS `activity_lock.py`; lower part: 8-column `_LOCK_SQL`, `_LOCK_SQL_ESCORT` fallback, `_VOYAGE_COLUMNS`, chain per 3.3, `_lock_from_row` passes `voyage_id`; PS `_AT_LOCATION_SQL` + `AND voyage_id IS NULL` with the `_ESCORT` fallback level (3.4 row 2) | Backend Developer | TODO | `services/locations-service/app/activity_lock.py`, `services/battle-service/app/activity_lock.py`, `services/inventory-service/app/activity_lock.py`, `services/party-service/app/crud.py` | T1 | `test_activity_lock_copies_share_the_canonical_upper_part` passes; each copy works against a schema without `voyage_id` (and without escort / law columns) with a Russian warning; existing BS/IS/LS/PS tests green |
| T3 | LS ports + sea routes: migration `060_sea_routes` (3.2); `Location.is_port`, `SeaRoute` model; schemas (3.9 LS); crud + endpoints L1–L7 with validation, pair normalisation (incl. reversing `path_json`), hidden-country / inactive / non-port filtering, `is_port` in create/update and in every location serializer that emits `no_quick_move` + region-details locations; unflag refusal 409; docs `docs/services/locations-service.md` | Backend Developer | DONE | `services/locations-service/app/models.py`, `.../app/alembic/versions/060_sea_routes.py`, `.../app/schemas.py`, `.../app/crud.py`, `.../app/main.py`, `docs/services/locations-service.md` | — | Endpoints match 3.9 contracts and permissions; deleting a location cascades its routes; unflag with routes → 409; public reads never return hidden/inactive/non-port routes; py_compile passes; existing LS tests green |
| T4 | Economy op types: `OP_SEA_FARE`, `OP_SEA_REFUND`, `SEA_OP_TYPES` added to `OP_TYPES` in all four `econ_core.py` copies; fare + refund cases in all four `tests/econ_contract_cases.py` copies (3.8) | Backend Developer | DONE | `services/{character,inventory,locations,dungeon}-service/app/econ_core.py`, the four `.../app/tests/econ_contract_cases.py` | — | `sh scripts/check_econ_copies.sh` ok; contract case runners pass in all 4 services; ops not in SOURCE/COMMENT_REQUIRED sets |
| T5 | CS voyages (stage 1): `sea_crud.py` (Captain context, routes_from, eligibility, buy incl. squad via shared-DB party read, leave, release, channel, refunds by reversed postings, `sea_available`), `sea_schemas.py`, `sea_api.py` (S1–S6, async where HTTP, retry once on `boarding_key` IntegrityError), `sea_pass.py` (3.7 steps 1–4, own claim on `sea_settings`, notices after commit, LS left-location best effort on sailing), `econ_scheduler.run_sea_pass` wired after the faction pass, `main.py` router include before the main router + `_prepare_move` releases a voyage ticket | Backend Developer | TODO | `services/character-service/app/sea_crud.py` (new), `.../sea_schemas.py` (new), `.../sea_api.py` (new), `.../sea_pass.py` (new), `.../econ_scheduler.py`, `.../main.py` | T1, T3, T4 | Contracts per 3.9; lock order voyage → tickets → characters; fare to `payer_account(from port)` with tax; refunds conserve money; pass runs with the economy tick off in the DB; arrival works with no request from the player; py_compile passes; existing CS tests green |
| T6 | CS caravans with sea legs (stage 2, 3.10): sea edges in `load_road_graph`; `caravan_route.fastest_route` (delegates to BFS when no sea edges); `RoutePlanner.legs`; `dispatch` stores `route_legs`; `step_caravan` sail/land/port-wait + stats; escort `leave` refuses at sea; C3 `at_sea`/`legs`; caravaneer lists caravans waiting in this port before a sea leg (`_preparing_here`/`_caravan_refusal`); admin overview rows `at_sea`/`route_legs` | Backend Developer | TODO | `services/character-service/app/caravan_route.py`, `.../economy_caravan_crud.py`, `.../caravan_pass.py`, `.../caravan_escort_crud.py` (do NOT rename `_in_battle`/`_gathering` — T5 imports them), `.../caravan_escort_schemas.py`, the schema file of the admin caravan overview rows (if separate) | T1, T3 | Old rows (`route_legs NULL`) step exactly as before; graph without sea edges yields identical routes to today; at sea `current_location_id` is NULL and the caravan is in no "here" list; escorts land with the caravan; py_compile passes; existing caravan/escort/raid tests green |
| T7 | Docs: `docs/services/character-service.md` (sea tables, S1–S6, sea pass, lock reason, stage 2 legs), `docs/ARCHITECTURE.md` (CS reads PS `parties`/`party_members` from the shared DB; sea routes in LS), `docs/services/party-service.md` (roster filter); CLAUDE.md §2 graph note «character-service reads party-service tables» if the graph lists shared-DB reads | Backend Developer | TODO | `docs/services/character-service.md`, `docs/ARCHITECTURE.md`, `docs/services/party-service.md` | T2, T5, T6 | Docs describe the shipped contracts; no secrets |
| T8 | FE admin: Captain role in `constants/npc.ts`; `is_port` checkbox in `EditLocationForm.tsx` (409 shown); `SeaRoutesPage.tsx` + `SeaRouteEditor.tsx` (multi-segment, per-Area drawing, reuse `waypointUtils.ts`) at `/admin/sea-routes` with `ProtectedRoute locations:read` and an AdminPage link; `api/seaRoutes.ts` + `types/seaRoutes.ts` (L1–L7); `economyLabels.ts` labels | Frontend Developer | TODO | `src/constants/npc.ts`, `src/components/AdminLocationsPage/EditForms/EditLocationForm/EditLocationForm.tsx`, `src/components/AdminLocationsPage/SeaRoutesPage.tsx` (new), `src/components/AdminLocationsPage/SeaRouteEditor.tsx` (new), `src/components/Admin/AdminPage.tsx`, `src/components/App/App.tsx`, `src/api/seaRoutes.ts` (new), `src/types/seaRoutes.ts` (new), `src/components/Admin/EconomyPage/economyLabels.ts` | T3, T4 | Admin can create/edit/delete/draw routes across 2 Areas; every API error shown in Russian; tsc + build pass; 360px usable; no React.FC; Tailwind only |
| T9 | FE player voyages: `CaptainModal.tsx`, NpcProfileModal button, Captain hint in `npcDialogueGate.ts`, `SeaVoyageModal.tsx` (+ mini-map), `SeaVoyageChannel.tsx`, `api/seaVoyages.ts` + `types/seaVoyages.ts`, lock UI (`useActivityLock.ts`, `ActivityLockBanner.tsx`, `LocationPage.tsx` text, `useWebSocket.ts` `'voyage'`); move `interpolatePolyline` to `src/utils/polyline.ts` and import it in `FloatingStructuresLayer.tsx` | Frontend Developer | TODO | `src/components/pages/LocationPage/CaptainModal/CaptainModal.tsx` (new), `src/components/pages/LocationPage/NpcProfileModal.tsx`, `src/components/pages/LocationPage/npcDialogueGate.ts`, `src/components/SeaVoyage/SeaVoyageModal.tsx` (new), `src/components/SeaVoyage/SeaVoyageChannel.tsx` (new), `src/api/seaVoyages.ts` (new), `src/types/seaVoyages.ts` (new), `src/hooks/useActivityLock.ts`, `src/components/CommonComponents/ActivityLockBanner.tsx`, `src/components/pages/LocationPage/LocationPage.tsx`, `src/hooks/useWebSocket.ts`, `src/utils/polyline.ts` (new), `src/components/WorldPage/FloatingStructuresLayer.tsx` | T5, T8 | Full scenario of section 1 UX works live (buy self/squad, boarding countdown, leave with refund, at sea banner, channel, arrival refresh); errors visible; tsc + build pass; 360px; no React.FC |
| T10 | FE world map: `SeaRoutesLayer.tsx` (segments of the area, ⚓ port anchors with info card, «→ {area}» edge chips), `InteractiveMap` prop `seaAreaId`, `WorldPage` passes it at area level only, ⚓ badge on port markers in `RegionInteractiveMap` | Frontend Developer | TODO | `src/components/WorldPage/SeaRoutesLayer.tsx` (new), `src/components/WorldPage/InteractiveMap/InteractiveMap.tsx`, `src/components/WorldPage/WorldPage.tsx`, `src/components/WorldPage/RegionInteractiveMap/*` (marker component only) | T8 | Routes visible on both Areas of a cross-Area route with working edge chips; nothing drawn for hidden countries; floating structures unaffected; tsc + build pass; 360px |
| T11 | FE stage 2: escort route view shows sea legs / «в море», «Сойти» disabled at sea; admin caravan list shows «в море»; types updated | Frontend Developer | TODO | `src/components/CaravanEscort/CaravanEscortRoute.tsx`, `src/components/CaravanEscort/CaravanEscortModal.tsx`, `src/types/caravanEscort.ts`, the admin caravan overview component under `src/components/Admin/EconomyPage/` | T6 | Correct display for old (no legs) and new caravans; tsc + build pass; 360px |
| T12 | QA lock & lists: `compute_lock`/`lock_message` for `voyage` (priority vs every other reason); `lock_for_character`; LS/BS/IS copies read `voyage_id` and fall back without it (and without escort/law columns); PS roster hides passengers + fallback; CS `/characters/by_location` hides passengers; `update_location` refuses with the voyage text; patrol arrival skips a passenger | QA Test | TODO | new/updated tests in `services/character-service/app/tests/`, `services/locations-service/app/tests/`, `services/battle-service/app/tests/`, `services/inventory-service/app/tests/`, `services/party-service/app/tests/` | T1, T2 | All new tests pass; byte-identical copy test passes |
| T13 | QA LS sea routes: L1–L7 (auth/permissions 401/403, validation ranges, non-port 409, duplicate pair 409, normalisation reverses `path_json`, hidden-country / inactive filtering, area filter), `is_port` create/update/serialization, unflag 409, location delete cascades routes; security cases (malformed JSON, out-of-range points, SQL-injection-like strings) | QA Test | TODO | `services/locations-service/app/tests/test_sea_routes.py` (new) | T3 | All pass in the LS container |
| T14 | QA CS voyages: Captain view (gate order incl. dialogue gate 403/503 mocked, rep tier, not a port, skew 503); purchase self/squad (skipped reasons, 402 no partial, double purchase → one ticket and one charge, concurrent first buyers → one departure); ledger (fare to region treasury + country tax, refund reverses exactly, payer gets squadmate refunds, total money conserved); leave (boarding ok, at sea 409); channel (membership, length, throttle); sea pass (claim throttle, runs with DB economy toggle off, invalid-route cancel + refunds, empty departure, sail → arrive offline, `check_entry` called with `voyage`, destination deleted → stays + refund, housekeeping); `_prepare_move` releases with refund. CS test DB needs LS/PS stand-in tables (`sea_routes`, `Locations.is_port`, `Countries.is_hidden`, `parties`, `party_members`) like existing Locations fixtures | QA Test | TODO | `services/character-service/app/tests/test_sea_voyages.py` (new), `.../tests/test_sea_pass.py` (new) | T4, T5 | All pass; each test ≤ 30 s (CI timeout per test) |
| T15 | QA CS stage 2: `fastest_route` (determinism, sea not preferred when slower, cheaper sea chosen, BFS-identical without sea edges, dungeons blocked, too_long); dispatch stores `route_legs`; `step_caravan` sail/land/port wait; at sea not in `caravans_here`, `begin_raid` refused, LS gate check rejects, no post hold; escorts stay then land with the caravan and can't leave at sea; hire in a port before a sea leg; old rows with `route_legs NULL` unchanged | QA Test | TODO | `services/character-service/app/tests/test_caravan_sea_legs.py` (new) | T6 | All pass; existing FEAT-211/212 tests green |
| T16 | Review: full checklist (CLAUDE.md rules, contracts vs 3.9, lock copies, econ copies script, migrations on MySQL, security), run py_compile / pytest of touched services / tsc / build, live verification on localhost (admin creates 2 ports + route + Captain; buy for squad; leave; sail; arrive offline; map display across Areas; a caravan with a sea leg in the admin list) | Reviewer | TODO | — | T1–T15 | PASS only with automated results + live verification recorded in section 5 |
