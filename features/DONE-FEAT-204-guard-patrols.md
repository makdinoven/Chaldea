# FEAT-204: Патрули стражи

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-05 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Пользователь: «Надо сделать НПС категории стражник возможность перемещаться по заданным локациям.» Строится поверх FEAT-198 (закон), FEAT-201 (скрытность), FEAT-202 (тюрьма страны), FEAT-203 (обнаружение стражей при входе) — 201–203 готовы, ревью PASS, НЕ запушены (пользователь: «пока без пуша»); всё в рабочем дереве.

### Решения пользователя (2026-11-05)
1. **Оба режима** движения, выбор у каждого стражника в админке:
   - **Маршрут** — упорядоченный список локаций; по кругу или туда-обратно (выбор).
   - **Зона патруля** — район или набор локаций; стражник раз в интервал уходит в случайную соседнюю локацию внутри зоны (по существующим переходам между локациями).
   - Неподвижный пост остаётся как вариант по умолчанию (патруль выключен).
2. **Патруль ловит и игроков не в сети**: когда стражник приходит в локацию, для каждого разыскиваемого (или «Вне закона») персонажа там — бросок обнаружения (та же формула FEAT-203: скрытность, маска, слава, тяжесть розыска, число стражников); заметил → встреча со стражей (24 ч на выбор, потом авто-решение, как в FEAT-198). «Не надо оставлять персонажа с плохой репутацией где попало».
3. Игроку в локации показывается **примерное время** ухода стражника («скоро уйдёт», «задержится ненадолго», «задержится надолго» — без точных минут).
4. **Интервал** движения по умолчанию 15–30 мин реального времени (PM: по умолчанию 20 мин, у каждого стражника настраивается; можно случайный разброс ±25 %).
5. **Погоня** — потом (не делать; заложить точку расширения).

### Дополнительно (PM, по умолчанию)
- Двигает стражников планировщик (как law_pass / econ_scheduler), проход раз в минуту, у каждого стражника `next_move_at`.
- Стражник не двигается, пока: выбит (KO), в бою, участвует в открытой встрече со стражей, мёртв. Продолжает после.
- Проход патрулём не создаёт встречу тем, у кого уже открыта встреча / кто в тюрьме / у кого действует 1 ч кулдаун после бегства (как в check_entry).
- При обнаружении патрулём игроку уведомление «Вас заметил патруль стражи в «…»»; при незамеченном проходе патруля — без уведомления (или тихое?) — PM: без уведомления.
- Перемещение стражника видно в локации (NPC появляется/исчезает в списке); ночные маршруты — потом.
- Админка: в форме NPC (роль guard) — блок «Патруль»: режим (пост / маршрут / зона), список локаций маршрута (порядок, по кругу / туда-обратно) или зона (район / набор локаций), интервал, разброс.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Baseline = the working tree on 2026-11-05: FEAT-198 committed (`331e4b9`); FEAT-201/202/203 uncommitted (migration head `043_guard_detection`). All line numbers are of the working tree.

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-service | new tables + migration `044_guard_patrols`, pure patrol core, patrol step in the law pass, arrival sweep (reuses the FEAT-203 entry check), admin patrol API, departure hint on the public NPC list, NPC delete / role-change cleanup, `law_settings.patrols_enabled` | `app/patrol_core.py` (new), `app/patrol_crud.py` (new), `app/patrol_api.py` (new), `app/law_crud.py`, `app/law_core.py`, `app/law_notify.py`, `app/law_pass.py`, `app/main.py`, `app/models.py`, `app/schemas.py`, `app/alembic/versions/044_guard_patrols.py` (new), tests |
| locations-service | pass-through of one additive field of `NpcInLocation` (otherwise pydantic drops it) | `app/schemas.py` |
| frontend | departure hint on guard cards, NPC list poll, lock refresh on law WS events, «патруль» wording in the encounter modal, admin «Патруль» panel, district picker, law settings checkbox, log label | `LocationPage.tsx`, `PlayersSection.tsx`, `LocationPage/types.ts`, `GuardEncounterModal.tsx`, `api/law.ts`, `hooks/useWebSocket.ts`, `AdminNpcsPage/AdminNpcsPage.tsx`, `AdminNpcsPage/GuardPatrolPanel.tsx` (new), `api/guardPatrol.ts` (new), `Admin/DungeonsPage/editor/pickers.tsx`, `Admin/ReputationPage/LawSettingsTab.tsx`, `api/lawAdmin.ts`, `Admin/CharactersPage/tabs/LawPanel.tsx` |

### 2.1 How an NPC stores its location and state (character-service `characters`, `models.py:38-118`)
- `current_location_id` BIGINT NULL (`models.py:63`) — the only location field; NPCs have no house room / travel cooldown semantics that matter (they are set only for players).
- `is_npc` (L64), `npc_role` VARCHAR(50) (L65; guards = `'guard'` = `law_core.GUARD_ROLE`, `law_core.py:29`), `npc_status` ENUM alive/dead (L66).
- `unconscious_until` (L71) — on a guard it is the FEAT-198 KO after a lost fight (`law_crud.knock_out_guard`, `law_crud.py:463`); guards never die by battle, only an admin can set `dead`.
- `law_encounter_id` / `jailed_until` (L107-109) — player-only in practice.
- Live-guard predicate used everywhere: `law_crud._SQL_GUARDS` / `guards_at` (`law_crud.py:486-494`): `is_npc=1 AND npc_role='guard' AND npc_status='alive' AND current_location_id=:loc AND (unconscious_until IS NULL OR <= now) ORDER BY id`.

### 2.2 How an NPC's location changes today
- **Only the admin NPC editor.** `POST /characters/admin/npcs` (`main.py:3039-3119`, `NpcCreate.current_location_id`) and `PUT /characters/admin/npcs/{npc_id}` (`main.py:3169-3250`, `NpcUpdate.current_location_id`, plain `setattr` loop L3203-3204, `npcs:update`). No journal row, no side effects for NPCs.
- No internal / scheduled NPC move exists anywhere (`grep current_location_id =` in character-service: player paths only — `main.py:2401` update_location, `crud.py:3876` teleport, `crud.py:4157` `apply_admin_move`, `main.py:4350`; `crud.py:1825` mob spawn creates a row). → the patrol step is the **first** automatic NPC move; it can be a raw `UPDATE characters SET current_location_id` (no house room, no gathering, no journal for NPCs).
- Readers of an NPC's location that react to a move: `GET /characters/npcs/by_location` (`main.py:3329-3356`, public; hides mobs, dead and KO'd NPCs); locations-service `_require_npc_gate` (`locations-service/app/main.py:1004-1016`, dialogue/shop gate is tied to the NPC's current location — a moved guard needs a new `npc_dialogue` post there, acceptable); battle-service `POST /battles/internal/guard` (`battle-service/app/main.py:1730-1745`) **refuses a guard that is not in the player's location** (409 `GUARD_ELSEWHERE`) — so a guard that is in an open encounter must not move (PM rule), and the FEAT-198 fight flow already reverts to `pending` on a 409/502.

### 2.3 Location graph (locations-service tables, readable by raw SQL from character-service)
- `LocationNeighbors` (`locations-service/app/models.py:164-172`): `location_id`, `neighbor_id`, `energy_cost`, `path_data` JSON, `is_auto_arrow`. **Stored in both directions**: `crud.add_neighbor` writes forward + reverse (`crud.py:1064-1120`), `update_location_neighbors` too (`crud.py:2279-2330`); cross-region arrow pairs are materialised as `is_auto_arrow=1` rows in both directions (`crud.sync_cross_region_neighbors`, `crud.py:6350-6427`). → «neighbours of X» = `SELECT neighbor_id FROM LocationNeighbors WHERE location_id = :x` (no need to union the reverse direction).
- `Locations` (`models.py:121-160`): `district_id`, `region_id`, `parent_id`, `type` ('location' | 'subdistrict'), `marker_type`. `Districts` (`models.py:84-101`): `region_id`, `parent_district_id`, `entrance_location_id`.
- **District subtree → locations** already exists in character-service: `law_facility.SQL_PRISON_LOCATIONS` + `prison_location_ids(db, district_id)` (`law_facility.py:31-43, 70-75`) — recursive CTE over nested districts and `Locations.parent_id`, depth-guarded, MySQL 8 + SQLite. Reusable as is for a «zone = district».
- character-service already reads `Locations` / `Regions` / `Districts` by raw `text()` (`law_crud.location_names` L136-142, `reputation_crud.location_region`, `law_facility`). No HTTP to locations-service is needed.
- Public lookups for the admin UI: `GET /locations/locations/lookup?q=` (`locations-service main.py:390`, used by `searchLocations`), `GET /locations/districts/lookup` (`main.py:398-401` → `[{id, name}]`, all districts, no filter).

### 2.4 Scheduler hook
- `econ_scheduler.run_scheduled_once` (`econ_scheduler.py:81-96`) → `run_law_pass` (L72-78) every `ECON_TICK_POLL_SECONDS` (60 s), independent of the economy switch.
- `law_pass.run_pass` (`law_pass.py:186-206`): claim on `law_settings.pass_last_run_at` ≥ 55 s (`claim_run` L44-51 — one runner across processes), then steps `_expired_encounters, _lost_callbacks, _served_terms, _guard_recovery, _reveal_crimes`, each step in try/except, each item in its own transaction, `BATCH_SIZE=200`, stats dict logged when non-zero. → a new step `_guard_patrols` slots in after `_guard_recovery` (a guard whose KO just ended is healed first). Async flows use `asyncio.run` — the patrol step needs none (pure sync DB work + pika publish).

### 2.5 Guard busy checks (all exist, sync, character-service)
- KO / dead: the `_SQL_GUARDS` predicate (2.1).
- Battle: `law_crud.in_active_battle(db, id)` (`law_crud.py:245-251`, `battles` + `battle_participants`, status pending/in_progress, not dropped out); same predicate as `_SQL_IDLE_GUARDS` (`law_pass.py:140-145`) and `main._is_in_battle` (`main.py:901`).
- Open encounter **as guard**: no helper yet; the data is `law_encounters.guard_npc_id` + `status IN lc.ENC_OPEN` (`law_core.py:57-66`; model `models.py:1328-1360`, no index on `guard_npc_id` — the table is small, but the migration adds `ix_law_enc_guard (guard_npc_id, status)`). `pick_free_guard` (`law_crud.py:964-974`) prefers the encounter's guard at `enc.location_id`, so a guard leaving would turn «fight» into `guard_gone`.

### 2.6 Reusing the entry check for «a guard arrives»
- `law_crud.check_entry(db, character, location_id, source, now, *, from_location_id)` (`law_crud.py:534-596`) does everything we need for ONE character: exits (NPC, open encounter, jailed, no region, no live guard, flee cooldown, not wanted & not outlaw, no level), the FEAT-203 roll (`detection_chance_for` L519-531 with `n = len(guards)`, `detection_rng()` seam L92-94), the `slipped` log, the encounter insert (`guard_npc_id = guards[0]`, `source` clamped to move/quick_move/teleport, L585) and `law_encounter_id`. It expects the character row already locked (`lock_character`, L154-158) and never commits.
- Gaps for the patrol variant: (a) the arriving guard should be the encounter's guard (not `guards[0]`); (b) a new source `patrol` (the column is `VARCHAR(20)`, `models.py:1347`; `encounter_out` exposes `source` only to staff, L697); (c) players present but busy must be skipped: in battle, in a dungeon, KO'd, asleep/reading (activity lock, `activity_lock.compute_lock` L62-87), inside a house (`characters.house_room_id`); (d) the notification text («патруль»).
- `from_location_id` stays NULL for a patrol encounter → a successful flee leaves the character in place (`law_flows._flee_move_back`, `law_flows.py:211-243`, returns early) and the 1 h flee cooldown (`law_encounters.cooldown_until`) protects him there.
- Present characters: `SELECT id FROM characters WHERE is_npc = 0 AND current_location_id = :loc` (offline players are included automatically — there is no online filter anywhere in the law code).

### 2.7 Notifications
- `law_notify` (`law_notify.py`): `Notice`, `publish()` after commit (best-effort pika → `general_notifications`), `encounter_message` L80-83 (category `system`, ws_type `law_encounter`), `law_crud.encounter_notice` (`law_crud.py:616-627`).
- notification-service sends a **typed** WS message `{type: ws_type, data: {...ws_data, notification_id, message, category, silent}}` (`notification-service/app/consumers/general_notification.py:121-132`). The frontend has no case for `law_*` → the `default` branch (`useWebSocket.ts:467-487`) adds it to the bell + popup, but **does not refresh `/users/me`**. For entry encounters this did not matter (the move response refreshes the lock); a patrol encounter arrives out of band, so the activity lock (and the `GuardEncounterModal` that `ActivityLockBanner` opens) would stay stale until the next `getMe`.

### 2.8 Frontend: location page NPC list
- `LocationPage.fetchLocationData` (`LocationPage.tsx:162-185`) loads `GET /locations/{id}/client/details` once (and after own actions); no periodic refresh → a guard arriving/leaving is invisible until reload.
- `client/details` (`locations-service main.py:1280…`) gets NPCs from `crud.get_npcs_in_location` (`crud.py:2770-2783`, HTTP `GET /characters/npcs/by_location`) into `LocationClientDetails.npcs: List[NpcInLocation]` (`schemas.py:659-666, 755`) — a **typed** schema, so a new field must be added there too.
- `/characters/npcs/by_location` is public through nginx (`location /characters/`, `docker/api-gateway/nginx.conf:259`; only `/characters/internal/` is blocked, L210) → the page can poll it directly (cheap, no posts/players payload).
- Rendering: `PlayersSection.NpcCard` (`PlayersSection.tsx:188-240`; name L217, role label L219-222); type `NpcInLocation` (`LocationPage/types.ts:78-86`).

### 2.9 Frontend: admin NPC form and pickers
- `AdminNpcsPage.tsx` (948 lines): form L461-709 with a hand-written location search (L597-660, `/locations/locations/lookup`); role-specific panels rendered under the form for an existing NPC: `{formOpen && editingId != null && form.npc_role === 'teleport_master' && <TeleportLinksPanel npcId={editingId} />}` (L712-714) — the pattern for a `GuardPatrolPanel` (own GET/PUT, own save button).
- Reusable pickers: `Admin/DungeonsPage/editor/pickers.tsx` — `EntityPicker` (L293-315, single, kinds `item|mob|location|npc|quest`, L18) and `EntityListPicker` (L318-347, chips, **no reordering**). No `district` kind; `EditCountryForm` (FEAT-202) uses a country-scoped `<select>` (`api/countryPrison.ts`). A `district` kind can be added like `quest` (load `/locations/districts/lookup` once, filter client-side, L69-80 pattern).

### Existing Patterns
- character-service: sync SQLAlchemy; foreign tables via raw `text()`; pure `*_core.py` + `*_crud.py` (caller's transaction, no commit) + `*_api.py` router included before the main router (`main.py:4745-4749`); Pydantic v1; Russian error texts; `secrets.SystemRandom` behind patchable seams; migrations information_schema-guarded, no ENUM, no FK on cross-service tables.
- Auth: admin routes `Depends(require_permission("npcs:read" | "npcs:update"))` (existing permissions → no RBAC migration, no RBAC test change).

### Cross-Service Dependencies
```
locations-service ──HTTP GET /characters/npcs/by_location──> character-service      (+ patrol_departure, additive; schema pass-through)
frontend ──GET /characters/npcs/by_location (poll)──> character-service              (public, existing route)
frontend ──GET/PUT/POST /characters/admin/npcs/{id}/patrol[/step]──> character-service  (new, npcs:read / npcs:update)
character-service ──RabbitMQ general_notifications──> notification-service          (ws_type law_encounter, new text)
character-service reads (raw SQL): LocationNeighbors, Locations, Districts, Regions, battles, battle_participants
battle-service POST /battles/internal/guard: unchanged (already refuses a guard elsewhere — 409)
```

### DB Changes
- New tables `guard_patrols`, `guard_patrol_points`; `law_settings.patrols_enabled`; index `ix_law_enc_guard` on `law_encounters`. Alembic: yes — character-service `044_guard_patrols` (auto-migration at container start).

### Risks
- **A guard pinned by an encounter for up to 24 h** (PM rule «не двигается, пока участвует в открытой встрече»): an AFK player keeps a patrol guard in place until auto-resolution. Accepted; the hint shows «задержится надолго».
- **Offline sweep volume**: a hub location with many players → one locked read per present player per arrival. Mitigation: `PATROL_SWEEP_LIMIT` per arrival, each player in its own short transaction, cheap exits first.
- **Lock order / deadlocks**: patrol row → guard row → (separate transactions) each player row. `update_location` locks only the player row and reads guards without a lock → no cycle.
- **Repeated rolls on ping-pong routes**: an offline wanted player is re-rolled on every arrival → eventually caught. This is the user's intent (decision 2); see Q3.
- **Stale NPC list**: needs the poll (2.8); **stale lock**: needs `getMe` on law WS events (2.7).
- **Existing tests**: `check_entry` is refactored internally — the FEAT-198/203 suites must stay green unchanged.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Summary
| # | Decision |
|---|---|
| P1 | One patrol config per guard NPC in `guard_patrols` (mode `post` / `route` / `zone`); route points and zone locations in `guard_patrol_points` (kept separately, so switching modes does not lose either list). `post` = no movement (the default; no row = post). |
| P2 | The guard is moved by a new step `_guard_patrols` of the existing law pass (once a minute, existing claim); each guard has `next_move_at`; each move is one short transaction with row locks; then each present player is checked in his own transaction. |
| P3 | Arrival check = the FEAT-203 entry check, refactored into a shared core; a new wrapper `check_patrol_arrival` adds the patrol exclusions, uses the arriving guard as the encounter's guard and `source='patrol'`. Same formula, same seam, same encounter, same 24 h timeout. Slip = log row only, no notification (PM). |
| P4 | Departure hint = an additive field `patrol_departure: 'soon' | 'short' | 'long' | null` on the public NPC list; the location page polls the NPC list every 60 s. |
| P5 | Admin: `GET/PUT /characters/admin/npcs/{id}/patrol` + `POST …/patrol/step` («Шаг сейчас») under the existing `npcs:read` / `npcs:update`; a `GuardPatrolPanel` under the NPC form for role `guard`. Global kill switch `law_settings.patrols_enabled` (tab «Закон»). |
| P6 | Pursuit is not built; the step has one explicit seam (`_override_target`) for it. |

### 3.1 Data model — migration `044_guard_patrols` (revision id `044_guard_patrols`, 17 chars; revises `043_guard_detection`)
Every step information_schema-guarded (re-run = no-op), no ENUM, no FK (NPC deletion cleans up explicitly, §3.7).
```sql
CREATE TABLE guard_patrols (
  npc_id            INT          NOT NULL PRIMARY KEY,        -- characters.id of a guard NPC
  mode              VARCHAR(10)  NOT NULL DEFAULT 'post',     -- post | route | zone
  route_style       VARCHAR(10)  NOT NULL DEFAULT 'loop',     -- loop | pingpong
  zone_kind         VARCHAR(10)  NOT NULL DEFAULT 'district', -- district | locations
  zone_district_id  BIGINT       NULL,                        -- Districts.id (subtree), zone_kind=district
  interval_min      SMALLINT     NOT NULL DEFAULT 20,         -- 5..1440
  jitter_pct        SMALLINT     NOT NULL DEFAULT 25,         -- 0..50  (± %)
  next_move_at      DATETIME     NULL,                        -- NULL = not scheduled (post)
  route_index       SMALLINT     NOT NULL DEFAULT 0,          -- position of the guard's current route point
  route_dir         SMALLINT     NOT NULL DEFAULT 1,          -- +1 / -1 (pingpong)
  last_location_id  BIGINT       NULL,                        -- previous location (zone: avoid an immediate backtrack)
  last_moved_at     DATETIME     NULL,
  updated_at        DATETIME     NOT NULL,
  updated_by_user_id INT         NULL,
  KEY ix_guard_patrols_due (mode, next_move_at)
);
CREATE TABLE guard_patrol_points (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  npc_id      INT         NOT NULL,
  kind        VARCHAR(10) NOT NULL,                           -- route | zone
  position    SMALLINT    NOT NULL,                           -- 0..n-1 (route order; zone: just stable order)
  location_id BIGINT      NOT NULL,                           -- Locations.id
  UNIQUE KEY uq_guard_patrol_point (npc_id, kind, position),
  KEY ix_guard_patrol_point_loc (location_id)
);
ALTER TABLE law_settings  ADD COLUMN patrols_enabled TINYINT(1) NOT NULL DEFAULT 1;
CREATE INDEX ix_law_enc_guard ON law_encounters (guard_npc_id, status);
```
Downgrade: drop the index, the column and both tables (configs lost — acceptable pre-beta). Models `GuardPatrol`, `GuardPatrolPoint` (with `default` + `server_default`, SQLite test DBs are built from models), `LawSettings.patrols_enabled`, `LawEncounter` index. Index names ≤ 64, revision id ≤ 32 (MySQL/Alembic gotchas memo).

`law_core`: `LawSettings.patrols_enabled: bool = True`, added to `SETTINGS_FIELDS`, `_BOOL_FIELDS`; `SOURCE_PATROL = "patrol"`. `law_crud._OPTIONAL_SETTINGS` += `patrols_enabled` (an older admin bundle keeps the stored value); `schemas.LawSettingsFields.patrols_enabled: Optional[bool] = None`.

### 3.2 Pure core `patrol_core.py` (no project imports)
```python
MODE_POST, MODE_ROUTE, MODE_ZONE = "post", "route", "zone"
STYLE_LOOP, STYLE_PINGPONG = "loop", "pingpong"
ZONE_DISTRICT, ZONE_LOCATIONS = "district", "locations"
DEFAULT_INTERVAL_MIN, MIN_INTERVAL_MIN, MAX_INTERVAL_MIN = 20, 5, 1440
DEFAULT_JITTER_PCT, MAX_JITTER_PCT = 25, 50
MIN_POINTS, MAX_ROUTE_POINTS, MAX_ZONE_POINTS = 2, 30, 100
BLOCKED_RETRY = timedelta(minutes=2)       # a blocked guard is looked at again after this
HINT_SOON_MIN, HINT_SHORT_MIN = 5, 15      # ≤5 → soon, ≤15 → short, else long
HINT_SOON, HINT_SHORT, HINT_LONG = "soon", "short", "long"

def validate(mode, style, zone_kind, route_ids, zone_ids, district_id, interval_min, jitter_pct) -> List[str]  # Russian
def next_delay(interval_min, jitter_pct, u: float) -> timedelta   # u ∈ [0,1): interval × (1 + jitter × (2u − 1)), ≥ 1 min
def route_step(points, index, direction, style, current_location) -> Tuple[int, int, int]   # (target, new_index, new_dir)
def zone_step(current, zone: Sequence[int], neighbours: Sequence[int], last, pick) -> Tuple[Optional[int], bool]
                                                                    # (target, jumped)
def departure_bucket(next_move_at, now, held: bool) -> Optional[str]
```
- **Route**: if `current_location == points[index]` → advance: loop `(index+1) % n`; pingpong `index+dir`, reversing `dir` at either end (n=2 alternates). If the guard is not on its route point (admin moved it / route edited): if `current` is in `points` → resync `index` to its first position and advance from there; else → target `points[0]`, index 0 (the guard «returns to the route»; a jump, no adjacency needed). Consecutive points need not be neighbours (admin's choice; the API returns a soft warning, §3.6).
- **Zone**: candidates = `neighbours(current) ∩ zone − {current}`; drop `last` when another candidate remains (no immediate backtrack); pick uniformly with the seam. No candidate (isolated, or the guard is outside the zone): jump to a uniformly random zone location ≠ current (`jumped=True`, logged at INFO). Zone with < 2 locations at run time (district emptied) → no move, `next_move_at` = now + interval (logged WARNING).
- **Hint**: `held` (open encounter as guard) → `long`; `next_move_at` None → None; remaining ≤ 5 min (incl. overdue/blocked-retry) → `soon`; ≤ 15 → `short`; else `long`. With the default 20 min ±25 % a guard shows «надолго» → «ненадолго» → «скоро».

### 3.3 Step `law_pass._guard_patrols` + `patrol_crud.step_guard`
`_guard_patrols(db, now, stats)` — only when `settings.patrols_enabled`. Due ids: `SELECT npc_id FROM guard_patrols WHERE mode IN ('route','zone') AND next_move_at <= :now ORDER BY next_move_at, npc_id LIMIT :n` (BATCH_SIZE). For each: `outcome = patrol_crud.step_guard(db, npc_id, now, force=False)`; per-item try/except + rollback; stats `patrol_moves`, `patrol_blocked`, `patrol_checked`, `patrol_encounters`, `patrol_slips`. Order in `run_pass`: after `_guard_recovery`, before `_reveal_crimes`.

`step_guard(db, npc_id, now, *, force) -> StepOutcome` (sync; commits — it is a flow, like the pass items):
1. **Txn A (the move)**: `SELECT … FROM guard_patrols WHERE npc_id=:id FOR UPDATE` (not on SQLite). Exit if missing, mode `post`, or (`not force` and `next_move_at > now`) → idempotent: a second runner / a replay after `step-now` finds the moved `next_move_at` and does nothing.
2. Lock the guard row (`law_crud.lock_character`). **Blocked** (no move, `next_move_at = now + BLOCKED_RETRY`, commit, outcome `blocked` + reason): not an NPC / `npc_role != 'guard'` (reason `not_guard`), `npc_status='dead'` (`dead`), `unconscious_until > now` (`ko`), `law_crud.in_active_battle` (`battle`), open encounter as guard — new `law_crud.guard_held(db, npc_id)` = `EXISTS law_encounters WHERE guard_npc_id=:g AND status IN ENC_OPEN` (`encounter`). `force` does not bypass blocks.
3. Target: `_override_target(db, patrol, now)` → **always None now** (the pursuit seam, P6); else route/zone per §3.2 (zone set = `law_facility.prison_location_ids(db, zone_district_id)` for `district`, the stored points for `locations`; neighbours = `SELECT neighbor_id FROM LocationNeighbors WHERE location_id=:cur`; existing-location filter `SELECT id FROM Locations WHERE id IN (...)` so a deleted location is skipped). RNG seam: `patrol_crud.patrol_rng()` (defaults to `law_crud.rng()`), used for the zone pick and the jitter.
4. No target / target == current → `next_move_at = now + next_delay(...)`, commit, outcome `stayed`.
5. Move: `UPDATE characters SET current_location_id=:t WHERE id=:g`; patrol: `last_location_id = current`, `route_index/dir` from §3.2, `last_moved_at = now`, `next_move_at = now + next_delay(...)`; commit. (No `law_log` row per move — too noisy; INFO log line only.)
6. **Arrival sweep** (after the move is committed — a sweep failure never undoes the move): `present = SELECT id FROM characters WHERE is_npc = 0 AND current_location_id = :t ORDER BY id LIMIT PATROL_SWEEP_LIMIT (200)`. For each id, its **own transaction (Txn B_i)**: `ch = law_crud.lock_character(db, id)`; `res = law_crud.check_patrol_arrival(db, ch, t, guard_id=npc_id, now=now)`; commit; if `res.encounter` → `law_notify.publish([law_crud.encounter_notice(db, res.encounter)])` after the commit; slip → no notification (PM). Per-character try/except + rollback.

### 3.4 `law_crud` refactor (behaviour of `check_entry` unchanged)
```python
def _check(db, character, location_id, source, now, *, from_location_id=None, guard_id=None) -> EntryResult
    # = today's check_entry body; encounter guard = guard_id if guard_id in guards else guards[0];
    # source clamp list += lc.SOURCE_PATROL
def check_entry(...same signature...) -> EntryResult:  return _check(...)
def check_patrol_arrival(db, character, location_id, *, guard_id, now) -> EntryResult:
    if character is None or character.is_npc or int(character.current_location_id or 0) != int(location_id): return _NO_ENTRY
    if activity_lock.lock_for_character(character)["locked"]: return _NO_ENTRY     # jail / encounter / KO / dungeon / asleep / reading
    if character.house_room_id: return _NO_ENTRY                                   # inside a house (Q1)
    if in_active_battle(db, character.id): return _NO_ENTRY
    return _check(db, character, location_id, lc.SOURCE_PATROL, now, guard_id=guard_id)
def guard_held(db, npc_id) -> bool
```
- Everything else is FEAT-203 as is: flee cooldown before the roll, wanted/outlaw/level, `detect_enabled` off → always detected, `detection_chance_for` with `n = len(guards_at(...))` (includes the arriving guard and any post guards), `detection_rng()`, slip log (`reason='patrol'`), encounter `from_location_id=NULL`, `expires_at = now + encounter_timeout_hours` (24 h), auto-resolution by the existing pass.
- `encounter_notice`: when `enc.source == SOURCE_PATROL` use `law_notify.patrol_encounter_message(location_name, expires_at, now)` → **«Вас заметил патруль стражи в «{location}». Решите, как поступить, в течение {remaining}»** (fallback without the name); same ws_type `law_encounter`, category `system`.
- `encounter_out` (player DTO) += `"by_patrol": enc.source == SOURCE_PATROL` (additive).

### 3.5 Departure hint (public NPC list)
- character-service `get_npcs_by_location` (`main.py:3329`): for the guards in the result, one query `SELECT npc_id, mode, next_move_at FROM guard_patrols WHERE npc_id IN (...) AND mode IN ('route','zone')` + one `guard_held` batch query (`SELECT DISTINCT guard_npc_id FROM law_encounters WHERE guard_npc_id IN (...) AND status IN (...)`); `patrol_departure = departure_bucket(...)` when `law_settings.patrols_enabled`, else None. `schemas.NpcInLocation.patrol_departure: Optional[str] = None`.
- locations-service `schemas.NpcInLocation.patrol_departure: Optional[str] = None` (pass-through only).
- Players see only the bucket; never minutes.

### 3.6 Admin API (new router `patrol_api.py`, prefix `/characters`, included before the main router)
`GET /characters/admin/npcs/{npc_id}/patrol` — `npcs:read` → 200 `PatrolOut`; 404 «NPC не найден» (not an NPC / mob).
```json
{ "npc_id": 41, "npc_role": "guard", "mode": "route", "route_style": "pingpong",
  "route": [{"location_id": 100, "name": "Рынок"}, {"location_id": 101, "name": "Ворота"}],
  "zone_kind": "district", "zone_district_id": null, "zone_district_name": null, "zone_locations": [],
  "interval_min": 20, "jitter_pct": 25,
  "current_location_id": 100, "current_location_name": "Рынок",
  "next_move_at": "2026-11-05T12:20:00", "last_moved_at": "2026-11-05T12:00:00",
  "blocked_reason": null, "patrols_enabled": true, "warnings": [] }
```
No row → defaults (`mode: "post"`, 20 / 25, empty lists). `blocked_reason` ∈ `null | not_guard | dead | ko | battle | encounter` (live, same checks as the step). `warnings` (Russian, soft): consecutive route points that are not neighbours («„Рынок“ и „Ворота“ не соседние — стражник перейдёт напрямую»), zone locations in several regions, a district zone without internal passages.

`PUT /characters/admin/npcs/{npc_id}/patrol` — `npcs:update`. Body:
```json
{ "mode": "post|route|zone", "route_style": "loop|pingpong", "route_location_ids": [100, 101],
  "zone_kind": "district|locations", "zone_district_id": 7, "zone_location_ids": [100, 101, 102],
  "interval_min": 20, "jitter_pct": 25 }
```
→ 200 `PatrolOut`. 400 (Russian): role ≠ guard and mode ≠ post («Патруль доступен только стражникам»); unknown mode/style/kind; interval ∉ [5, 1440]; jitter ∉ [0, 50]; route: < 2 or > 30 points, an unknown location, the same location twice in a row; zone `locations`: < 2 or > 100, duplicates, unknown ids; zone `district`: unknown district or < 2 locations in its subtree. 404 NPC. Writes (one transaction, patrol row `FOR UPDATE`): upsert the row; replace the points of the submitted kinds (both lists are stored whatever the mode); `updated_at/by`. Scheduling: mode `post` → `next_move_at = NULL`; switching to route/zone or changing the points/interval → `next_move_at = now + next_delay`, route `index` = position of the current location in the route if present (dir +1) else 0. A save that changes nothing about movement keeps `next_move_at`.

`POST /characters/admin/npcs/{npc_id}/patrol/step` — `npcs:update` → `step_guard(force=True)` → 200 `{"outcome": "moved|stayed|blocked|not_patrolling", "blocked_reason": …, "from_location_id", "to_location_id", "checked": n, "encounters": n, "slipped": n, "patrol": PatrolOut}`. Encounter notices published after the commits, as in the pass. («Шаг сейчас» — for admins and for live verification without waiting 20 min.)

Pydantic v1 schemas `PatrolIn` (validators: lists of positive ints, dedupe check stays in core) / `PatrolOut` / `PatrolStepOut`.

### 3.7 Other backend touch points
- `admin_update_npc` (`main.py:3169`): role changed away from `guard` → `UPDATE guard_patrols SET mode='post', next_move_at=NULL` (points kept). Admin location change → nothing (the step resyncs / returns to the route).
- `admin_delete_npc` (`main.py:3253`): delete `guard_patrol_points` + `guard_patrols` of the NPC in the same transaction as the row delete.
- `law_settings` admin GET/PUT: `patrols_enabled` (optional on input).

### 3.8 Frontend
- **Player — hint**: `LocationPage/types.ts` `NpcInLocation.patrol_departure?: 'soon' | 'short' | 'long' | null`; `PlayersSection.NpcCard` — a small muted line under the role label for guards: «скоро уйдёт» / «задержится ненадолго» / «задержится надолго» (constants map; nothing when null).
- **Player — NPC list refresh**: `LocationPage` polls `GET /characters/npcs/by_location?location_id={id}` every 60 s (named constant) while `document.visibilityState === 'visible'`, merging only `npcs` into `location` (no spinner, no full details reload); a failed poll shows nothing new but must not be silent forever — show one `toast.error('Не удалось обновить список НПС')` per streak (reset on success). Also re-poll on `visibilitychange` → visible.
- **Player — lock refresh**: `useWebSocket` — for WS types `law_encounter`, `law_jailed`, `law_released`, `law_resolved` keep the existing default bell/popup behaviour AND `dispatch(getMe())`, so `ActivityLockBanner` / `GuardEncounterModal` appear for an encounter created by a patrol.
- **Player — modal wording**: `api/law.ts` encounter type `by_patrol?: boolean`; `GuardEncounterModal` shows «Вас заметил патруль стражи» as the lead line when true.
- **Admin — `GuardPatrolPanel.tsx`** (new, `components/AdminNpcsPage/`), rendered like `TeleportLinksPanel` when `formOpen && editingId != null && form.npc_role === 'guard'`: mode segmented control «Пост / Маршрут / Зона»; route: ordered list (add via location `EntityPicker`, ↑ / ↓ / ×), style «По кругу / Туда-обратно»; zone: «Район / Набор локаций» → district picker or location `EntityListPicker`; «Интервал, мин» (5–1440), «Разброс, %» (0–50) with hint «20 мин ± 25 % = 15–25 мин»; status line (current location, next move as relative time, `blocked_reason` in Russian, global switch off notice); warnings list; buttons «Сохранить патруль» and «Шаг сейчас». Client validation mirrors §3.6; all API errors shown (`detail`). `api/guardPatrol.ts` typed client. The NPC list row may show a 🚶 mark for patrolling guards — optional, skip if it needs a backend change.
- **Admin — pickers**: `pickers.tsx` new kind `district` (load `/locations/districts/lookup` once, cache, filter by name/id; lookup from the same cache).
- **Admin — law settings**: `LawSettingsTab.tsx` group «Стража» + checkbox «Патрули стражи ходят» (`patrols_enabled`); `api/lawAdmin.ts` type. `LawPanel.tsx` source label `patrol: 'патруль'`.
- All: TypeScript, Tailwind + design-system classes, 360 px adaptive, no `React.FC`, Russian texts.

### 3.9 Security
- Admin endpoints: JWT + `npcs:read` / `npcs:update` (existing permissions → no RBAC migration / test change). All ids validated against existing rows; bounded list sizes and numbers (no unbounded loops: sweep limit, batch limit, max points).
- Player data: the public NPC list adds only a 3-value bucket; no exact time, no wanted info. Rolls server-side (`secrets.SystemRandom`), chance/roll only in `law_log` (staff).
- The poll uses an existing public endpoint (60 s per open tab, visible tabs only) — no new rate limiting needed.
- No new internal endpoints; no client input reaches the scheduler.

### 3.10 Deploy skew
- Migration 044 runs before uvicorn in the same container; the pass/route code reading the new tables only runs after it. Ships with uncommitted 201/202/203 (041 → 044 in one deploy).
- Old locations-service: drops `patrol_departure` → no hint on the details payload (the direct poll still has it). Old frontend: ignores the field; notifications still pop.
- Old admin bundle saving law settings without `patrols_enabled` → value kept.
- battle-service unchanged; a guard that moved away before a fight start gets the existing 409 → the existing revert path.

### 3.11 Extension point — pursuit (not implemented)
`patrol_crud._override_target(db, patrol, now) -> Optional[int]` is called before the route/zone logic and returns None. A future «погоня» sets a target (e.g. the `from_location_id` of a fled encounter) and the rest of the step (move, sweep, scheduling) is reused unchanged. No columns are added for it now.

### Data Flow Diagram
```
econ_scheduler thread (60 s) → law_pass.run_pass (claim ≥55 s)
  → _guard_patrols: due guard_patrols (next_move_at ≤ now)
     → Txn A: patrol FOR UPDATE → guard FOR UPDATE → blocked? (KO/dead/battle/encounter/not guard) → retry +2 min
              → target (route / zone random walk over LocationNeighbors ∩ zone / pursuit seam) → UPDATE characters
              → next_move_at = now + 20 min ± 25 % → COMMIT
     → for each player in the new location (≤200), Txn B_i: player FOR UPDATE → check_patrol_arrival
              → exclusions (lock / house / battle) → _check (FEAT-203: cooldown, wanted, level, roll)
                  detected → law_encounters(source=patrol) + law_encounter_id → COMMIT → notice «Вас заметил патруль…»
                  slipped  → law_log(slipped, reason=patrol) → COMMIT (no notice)
notification-service → WS {type: law_encounter} → bell + popup + getMe → ActivityLockBanner → GuardEncounterModal
Player page: poll GET /characters/npcs/by_location (60 s) → guard appears/disappears + patrol_departure bucket
Admin: GuardPatrolPanel → GET/PUT /characters/admin/npcs/{id}/patrol, POST …/patrol/step
```

### Open business questions (defaults applied unless the user says otherwise)
- **Q1** Characters **inside a house** (incl. asleep / reading there): default — **the patrol does not check them** (guards do not break into homes; also avoids a sleeping/reading lock colliding with a jail move). Alternative: check them too.
- **Q2** Characters **in battle / in a dungeon / knocked out** in the location: default — **skipped** at this arrival (checked on a later arrival if still there).
- **Q3** **No grace** after slipping past a patrol: every arrival is a new roll (a ping-pong route re-rolls an offline wanted player every ~40 min). Default — as decided («не оставлять где попало»); alternative: a per-character grace (e.g. 2 h) after a slip.
- **Q4** A **successful flee** from a patrol encounter: the character stays in place (there is no «where from») and the 1 h flee cooldown in this location protects him. Default — as is; alternative: push him to a random neighbouring location.
- **Q5** Route points **need not be adjacent** (the guard «steps» directly; admin gets a soft warning). Default — allowed.
- **Q6** A **blocked guard** (KO, battle, encounter) resumes from where it stands; a guard moved by an admin goes back to its route at the next step (a direct jump). Default — as described.
- **Q7** Global switch «Патрули стражи ходят» in the «Закон» tab (on by default). Default — added (cheap kill switch).

---

### PM decisions on open questions (2026-11-05)
- Q1–Q7: defaults accepted.
- **Main risk resolved (PM):** a patrol guard waits for a player's answer to an open encounter for **at most 30 minutes** (setting `patrol_encounter_hold_min`, default 30), then resumes the patrol. If the player later picks «Драться» and that guard is gone, the existing flow picks another free guard in the location; if none — the existing `guard_gone` result applies. Fine / surrender / flee stay available. «Задержится надолго» hint while held.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**All dev / QA / docs tasks: do NOT commit, push, or `git add` — the user commits once at the end.**

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **character-service data + core:** migration `044_guard_patrols` (§3.1, guarded, idempotent, downgrade); models `GuardPatrol`, `GuardPatrolPoint`, `LawSettings.patrols_enabled`, `LawEncounter` index; `law_core` (`patrols_enabled` field/bool/settings fields, `SOURCE_PATROL`); `law_crud._OPTIONAL_SETTINGS` + settings out/in; schema `LawSettingsFields.patrols_enabled`; pure `patrol_core.py` (§3.2: constants, `validate`, `next_delay`, `route_step`, `zone_step`, `departure_bucket`). No commits/pushes/`git add`. | Backend Developer | DONE | `app/alembic/versions/044_guard_patrols.py`, `app/models.py`, `app/law_core.py`, `app/law_crud.py`, `app/schemas.py`, `app/patrol_core.py` | — | `py_compile` OK; migration up/down/re-run idempotent on the dev MySQL; old admin payload without `patrols_enabled` keeps the value. |
| 2 | **character-service step + arrival:** `law_crud._check` refactor (check_entry unchanged), `check_patrol_arrival`, `guard_held`, patrol source in the clamp, `encounter_notice` patrol text + `law_notify.patrol_encounter_message`, `encounter_out.by_patrol`; `patrol_crud.py` (`patrol_rng`, zone/route resolution via raw SQL incl. `law_facility.prison_location_ids` and `LocationNeighbors`, `_override_target` seam, `step_guard` with Txn A + per-player Txn B, outcome dataclass); `law_pass._guard_patrols` step + stats (§3.3–3.4). No commits/pushes/`git add`. | Backend Developer | DONE | `app/law_crud.py`, `app/law_notify.py`, `app/patrol_crud.py`, `app/law_pass.py` | 1 | Blocked guards don't move and retry in 2 min; moves are idempotent under a replay; sweep failure keeps the move; FEAT-198/203 suites still green unchanged; py_compile OK. |
| 3 | **character-service API + hint + cleanup:** `patrol_api.py` (GET/PUT patrol, POST step, §3.6, `npcs:read`/`npcs:update`, Russian 400/404, warnings), router include before the main router; `get_npcs_by_location` + `patrol_departure` (§3.5), `NpcInLocation.patrol_departure`; `admin_update_npc` role-away → post; `admin_delete_npc` cleanup (§3.7). No commits/pushes/`git add`. | Backend Developer | DONE | `app/patrol_api.py`, `app/main.py`, `app/schemas.py` | 1, 2 | Contracts exactly as §3.6; `npcs/by_location` unchanged for non-guards; py_compile OK. |
| 4 | **locations-service pass-through:** `schemas.NpcInLocation.patrol_departure: Optional[str] = None`. No commits/pushes/`git add`. | Backend Developer | DONE | `locations-service/app/schemas.py` | 3 (contract) | Field passes through `client/details`; py_compile OK; locations-service suite green. |
| 5 | **Frontend player:** hint on guard cards (`types.ts`, `PlayersSection.tsx`); NPC list poll 60 s (visible tab, merge `npcs`, error toast per streak) in `LocationPage.tsx`; `useWebSocket` `getMe` on `law_encounter/law_jailed/law_released/law_resolved` (keep bell + popup); `api/law.ts` `by_patrol` + «Вас заметил патруль стражи» in `GuardEncounterModal.tsx` (§3.8). No commits/pushes/`git add`. | Frontend Developer | DONE | `LocationPage/types.ts`, `PlayersSection.tsx`, `LocationPage.tsx`, `hooks/useWebSocket.ts`, `api/law.ts`, `GuardEncounterModal.tsx` | 3, 4 | TS only, no `React.FC`, Tailwind, 360 px; `npx tsc --noEmit` + `npm run build` pass (in Docker). |
| 6 | **Frontend admin:** `GuardPatrolPanel.tsx` + `api/guardPatrol.ts` (§3.8), rendered in `AdminNpcsPage.tsx` for role guard; `pickers.tsx` kind `district`; `LawSettingsTab.tsx` checkbox «Патрули стражи ходят» + `api/lawAdmin.ts`; `LawPanel.tsx` source `patrol: 'патруль'`. No commits/pushes/`git add`. | Frontend Developer | DONE | `AdminNpcsPage/GuardPatrolPanel.tsx`, `api/guardPatrol.ts`, `AdminNpcsPage/AdminNpcsPage.tsx`, `Admin/DungeonsPage/editor/pickers.tsx`, `Admin/ReputationPage/LawSettingsTab.tsx`, `api/lawAdmin.ts`, `Admin/CharactersPage/tabs/LawPanel.tsx` | 3 | Route reorder works; zone by district / by locations; client validation mirrors §3.6; all errors shown; design system; 360 px; tsc + build pass. |
| 7 | **QA character-service:** test world gets `LocationNeighbors` (+ `Districts`/`Locations.parent_id` if missing) DDL and a `patrol_rng` patch helper; `patrol_core` unit tests (validate bounds/messages, `next_delay` bounds incl. jitter 0/50, `route_step` loop/pingpong/resync/off-route, `zone_step` neighbours∩zone, no-backtrack, isolated jump, `departure_bucket` thresholds/held/None); migration 044 test (tables, column, index, idempotent); step: blocked reasons (KO, dead, battle, open encounter as guard, not guard) → no move + retry; due/not-due idempotency; `force`; move updates location + state; sweep: wanted offline player detected → encounter `source=patrol`, guard = arriving guard, `from_location_id` NULL, notice text «Вас заметил патруль…»; slipped → log `slipped` reason `patrol`, no notice; exclusions (jailed, open encounter, flee cooldown, in house, in battle, dungeon, KO, NPCs, not wanted); `n_guards` includes the arriving guard; `detect_enabled` off → always encounter; `patrols_enabled` off → no moves, hint None; admin API GET defaults/PUT validation (every 400)/404/RBAC (`npcs:read` vs `npcs:update`)/step endpoint; `npcs/by_location` hint buckets; role change → post; NPC delete cleanup; check_entry regression (existing suites green). No commits/pushes/`git add`. | QA Test | DONE | `character-service/app/tests/test_guard_patrols.py` (new), `tests/patrol_world.py` (new, optional), adjust fixtures | 1, 2, 3 | All new + existing character-service tests pass in the container. |
| 8 | **QA locations-service:** `client/details` passes `patrol_departure` through (mocked character-service response with and without the field). No commits/pushes/`git add`. | QA Test | DONE | `locations-service/app/tests/…` | 4 | locations-service suite green in the container. |
| 9 | **Docs:** `docs/services/character-service.md` (patrols: tables, migration 044, step, arrival check, API, hint, settings switch), `docs/services/locations-service.md` (`NpcInLocation.patrol_departure`), `docs/ARCHITECTURE.md` table list if it lists law tables; `docs/ISSUES.md` only if something new is found. No commits/pushes/`git add`. | QA Test | DONE | docs | 1–4 | Docs match the code. |
| 10 | **Review:** code vs §3; py_compile; character-service + locations-service suites; tsc + build; migration 044 on the dev DB. **Live verification on localhost** (Chrome allowed): admin sets a route (2–3 locations, pingpong) and a zone (district) for a guard, «Шаг сейчас» moves it, the location page shows the guard appear/disappear within ≤60 s and the hint text; a wanted character (offline or in another tab) standing in the target location gets an encounter after «Шаг сейчас» (with detection min raised to 100 % or `detect_enabled` off), bell + popup «Вас заметил патруль стражи…», lock + modal with «патруль» wording; a slip with stealth high/min lowered → no notification, `slipped` row in LawPanel; KO'd / held guard does not move (blocked reason shown); global switch off stops moves and hides hints; zero console errors; player payloads carry only the bucket. | Reviewer | DONE | all | 1–9 | PASS only with automated results + live verification recorded in §5. |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-05
**Result:** PASS (also the deploy gate for FEAT-201/202/203/204 on top of `331e4b9`)

#### Code review vs §1/§3 (all verified)
- `patrol_core`: route loop/pingpong (n=2 alternates, reversal at both ends, resync when the guard is elsewhere on the route, jump back to `points[0]` when off-route), loop rejects first==last; zone = neighbours ∩ zone − current, no immediate backtrack when another candidate exists, isolated/outside → uniform jump; `next_delay` clamps jitter 0..50 and ≥ 1 min; hint buckets ≤5 / ≤15 / else, held → `long`.
- `patrol_crud.step_guard`: Txn A (patrol `FOR UPDATE` → guard `FOR UPDATE`), not-due exit = idempotent replay, orphan config removed, blocks (not_guard/dead/KO/battle/encounter-held) → `next_move_at = now + 2 min`, `force` never bypasses a block; move committed before the sweep; sweep = one transaction per present player (≤ 200), notice published after each commit, slips silent. Lock order patrol → guard, players separately → no cycle with `update_location`.
- 30-min hold (PM): `held_guards` = any `fighting` encounter or a `pending` one younger than `patrol_encounter_hold_min` (migration default 30, validated 0..1440); the hint uses the same predicate.
- `check_patrol_arrival` exclusions (activity lock incl. jail/encounter/KO/dungeon/asleep/reading, house, battle) then the shared `_check` (cooldown, wanted/outlaw, level, FEAT-203 roll with `n = guards here`); arriving guard becomes the encounter guard; `from_location_id` NULL; `check_entry` behaviour unchanged (FEAT-198/203 suites green).
- Admin API: `npcs:read` / `npcs:update`, Russian 400/404, bounded inputs (`max_items=200` + core limits), unknown locations/district rejected, 409 on concurrent insert; scheduling reset only when the movement config changes. Router included before the main router.
- `admin_update_npc` role away from guard → `post`; `admin_delete_npc` deletes points + config in the same transaction; `law_settings.patrols_enabled` / `patrol_encounter_hold_min` optional on input (old admin bundle keeps values).
- Migration `044_guard_patrols` revises `043_guard_detection`, information_schema-guarded, no ENUM/FK, index names ≤ 64, revision id 17 chars.
- Frontend: NPC poll 60 s only while visible + on `visibilitychange`, merges only `npcs`, one toast per failing streak; `getMe` on `law_encounter/law_jailed/law_released/law_resolved` (types match `law_notify.WS_*`); modal «Вас заметил патруль стражи» via `by_patrol`; `GuardPatrolPanel` (no `React.FC`, Tailwind + design-system classes, `sm:` breakpoints, all API errors shown); `district` picker kind; «Патрули стражи ходят» + hold minutes in «Закон»; `patrol: 'патруль'` in LawPanel. TS types ↔ Pydantic schemas match.
- Performance: the pass handles ≤ 200 due guards per minute; per arrival ≤ 200 players, each a short locked transaction (~6–8 small queries for a non-wanted player). Fine for the current population (see note 2). Poll: one cheap public GET per open visible location tab per minute (2 batched queries for hints).

#### Automated Check Results
- [x] `py_compile` — PASS (80 modified/new .py files across services)
- [x] pytest (throwaway python:3.10 containers, CI args): character-service **8988 passed, 1 skipped** (`test_guard_patrols.py` alone 228 passed in 30 s); locations-service **2839 passed**; battle-service **1859 passed**; inventory-service **2448 passed**; character-attributes-service **975 passed, 2 skipped, 1 xpassed**; user-service **776 passed**; dungeon-service econ (`test_econ_contract`, `test_econ_dungeon`, `test_econ_dungeon_flows`) + `test_feat175_entry` — exit 0
- [x] `sh scripts/check_econ_copies.sh` — all copies identical
- [x] `npx tsc --noEmit` (frontend container) — PASS, 0 errors
- [x] `vite build` (frontend container) — PASS
- [x] `docker compose config` — PASS (dev and dev+prod)
- [x] Alembic: one head per service — attributes `009_add_stealth`, inventory `035_item_stealth_modifier`, locations `057_country_prison_district`, character `044_guard_patrols`, battle `009_battle_law_encounter`, user `0033`; dev DB on the same heads; 044 downgrade → upgrade → upgrade (no-op) on the dev MySQL — OK
- [x] Live verification — PASS (below)

#### Live Verification Results (http://localhost, admin, active character Ашари 763)
- Admin `/admin/npcs`, guard «Тайко Сарада» (386, Казармы Хатамото): «Маршрут», «Туда-обратно», points 1177 → 1178 → 1183 via the search box, «Сохранить патруль» → toast, status «Следующий шаг: через 21:42».
- «Шаг сейчас» → «Стражник перешёл: Казармы Хатамото → Подземелье Замка Кёджо; проверено: 3, задержано: 2, проскользнули: 0»; status immediately «Стоит: стражник задерживает нарушителя». Two encounters `source=patrol`, guard 386, `from_location_id` NULL (online 763 + offline 765). Notifications «Вас заметил патруль стражи в «Подземелье Замка Кёджо». Решите, как поступить, в течение 1 д»; the encounter modal («ВАС ЗАМЕТИЛ ПАТРУЛЬ СТРАЖИ», «… подходит к вам») opened at once in both open tabs via WS → getMe.
- Location page 1183: after the next poll (60 s) the guard appeared in «НПС» (count 1 → 2) with «задержится надолго»; `/characters/npcs/by_location` returns only the bucket (`long` / null).
- Hold cap: encounters aged 31 min → guard no longer held, `blocked_reason` null, «Шаг сейчас» moves 1183 → 1178.
- KO (`unconscious_until` +1 h) → step `blocked` / `ko`. PUT validation: unknown district → 400 «Район не найден»; interval 3 + duplicate point → 400 with both Russian messages.
- Zone «Район: Замок Кёджо» (UI shows the district chip): step 1178 → 1177 (no backtrack to 1183); with detection forced to 0 % the wanted offline character there slipped — `law_log slipped / reason=patrol`, **no** notification.
- Switch «Патрули стражи ходят» off in «Закон» (UI save): due guard not moved by the scheduled pass, hints null; on again → the next pass moved it (1177 → 1179, `law pass: {'patrol_moves': 1, …}`).
- Encounter answered «Заплатить штраф» → lock + banner cleared.
- FEAT-201/203 sanity: profile shows «Скрытность 0 / −0 % к шансу быть замеченным»; quick move into a guarded location with detection 0 % → toast «Вы проскользнули мимо стражи» + notification, `law_log slipped / quick_move`. FEAT-202 country prison banner not re-exercised live (no country prison configured for this region; covered by the FEAT-202 review and suites).
- Console errors: none on the admin, reputation, location and profile pages; service logs: no 5xx (only the two intentional 400s).
- Local data restored from the pre-test mysqldump.

#### Issues Found
No blocking issues.

| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `.github/workflows/ci.yml:87` | Deploy risk, not a code bug: CI test step has `timeout-minutes: 6`; character-service took 4:44 for 8220 tests on `331e4b9`, now 8988 tests (+228 patrol tests ≈ 30 s locally) → est. ~5:20–5:40 in CI. Consider raising to 8 before the push so a slow runner does not block the deploy. | PM / DevSecOps | NOTE |
| 2 | `patrol_crud.py:182` | Perf note: the sweep runs the full `_check` (row lock + ~6–8 queries) for every present player, wanted or not; region/guards/settings are re-read per player. Fine now; if hubs grow, prefilter ids by `character_wanted`/outlaw. | Backend Developer | NOTE |
| 3 | `GuardPatrolPanel.tsx:265` | Cosmetic: in a district zone the step result shows the from-location as `#1179` (names come only from the stored lists + current location). | Frontend Developer | NOTE |
| 4 | `GuardPatrolPanel.tsx:162` | Cosmetic: «Шаг сейчас» (`force`) moves the guard even when the global switch is off (fine for admins), while the `not_patrolling` text says «или патрули выключены». Client validation does not mirror the loop first==last rule (server 400 is shown). | Frontend Developer | NOTE |

---

## 6. Logging (filled by all agents — in Russian)

Running log of progress updates. Each agent writes brief Russian entries here.

```
[LOG] 2026-11-05 — PM: фича создана по решениям пользователя (оба режима, ловит и оффлайн, примерное время, 20 мин, погоня потом); запускаю анализ+проектирование
[LOG] 2026-11-05 — Analyst: проанализированы хранение локации НПС, переходы LocationNeighbors (двусторонние), шаг law_pass, check_entry FEAT-203, уведомления, список НПС на странице локации и админка НПС
[LOG] 2026-11-05 — Architect: спроектировано: таблицы guard_patrols + guard_patrol_points (миграция 044_guard_patrols), шаг патрулей в law_pass, проверка прибывшим стражником всех разыскиваемых в локации (формула FEAT-203), подсказка «скоро уйдёт / ненадолго / надолго», админ-API и панель «Патруль», рубильник в «Законе»; 10 задач, 7 открытых вопросов с дефолтами
[LOG] 2026-11-05 — Backend Dev: задачи 1–4 готовы: миграция 044_guard_patrols (таблицы guard_patrols / guard_patrol_points, law_settings.patrols_enabled + patrol_encounter_hold_min = 30, индекс ix_law_enc_guard), patrol_core / patrol_crud / patrol_api, шаг патрулей в law_pass, проверка прибывшим патрулём (формула FEAT-203, source=patrol), уведомление «Вас заметил патруль стражи в «…»», подсказка patrol_departure, очистка при удалении НПС / смене роли; встреча держит стражника максимум 30 мин (настройка). Миграция up/down/up на fogdatabase OK, py_compile OK; character-service 8760 passed (в test_law_core.py дописаны колонки 044 и 2 поля в позиционную строку настроек), locations-service 2827 passed
[LOG] 2026-11-05 18:40 — QA: написаны тесты character-service tests/test_guard_patrols.py (228 тестов: patrol_core, шаг патруля, блокировки и удержание встречей 30 мин, проход по прибытии с исключениями, подсказка, админ-API + RBAC, настройки, миграция 044, «Драться» после ухода патрульного) и locations-service tests/test_npc_patrol_departure.py (8 тестов, проброс patrol_departure)
[LOG] 2026-11-05 19:10 — QA: полные прогоны в контейнерах: character-service 8988 passed / 1 skipped, locations-service 2835 passed / 4 skipped; багов не найдено
[LOG] 2026-11-05 19:10 — QA: документация обновлена — character-service.md (раздел «Патрули стражи (FEAT-204)», файлы, таблицы, шаг прохода закона), locations-service.md (NpcInLocation.patrol_departure), ARCHITECTURE.md (таблицы и поток патрулей)
[LOG] 2026-11-05 — Frontend Dev: задачи 5–6 готовы: подсказка «скоро уйдёт / задержится ненадолго / надолго» на карточке стражника, опрос списка НПС раз в 60 с (только видимая вкладка, один тост на серию ошибок), getMe по WS law_encounter/law_jailed/law_released/law_resolved, строка «Вас заметил патруль стражи» в модалке встречи; админка: GuardPatrolPanel (пост/маршрут/зона, порядок точек ↑/↓/×, по кругу/туда-обратно, район или набор локаций, интервал/разброс с подсказкой, статус с обратным отсчётом, причина простоя, предупреждения, «Шаг сейчас» с итогом), вид «district» в pickers.tsx, в «Законе» — «Патрули стражи ходят» и «Сколько стражник ждёт ответа, мин», источник «патруль» в LawPanel. tsc --noEmit и npm run build в контейнере — OK
[LOG] 2026-11-05 19:00 — Reviewer: начал финальную проверку FEAT-204 и общий допуск к деплою 201–204; снят дамп локальной БД
[LOG] 2026-11-05 19:20 — Reviewer: тесты в контейнерах зелёные (character 8988, locations 2839, battle 1859, inventory 2448, attributes 975, user 776, dungeon econ + feat175_entry), tsc/build/compose/econ-копии OK, по одной голове Alembic в каждом сервисе; живая проверка: маршрут «туда-обратно», «Шаг сейчас» — стражник пришёл и задержал онлайн- и оффлайн-разыскиваемых, модалка открылась сразу, подсказка «задержится надолго», удержание снимается через 30 мин, KO блокирует, зона по району, тихое проскальзывание, рубильник выключает проход; 201/203 — строка скрытности и тост проскальзывания на месте
[LOG] 2026-11-05 19:25 — Reviewer: проверка завершена, результат PASS; блокеров нет, 4 заметки (запас по таймауту CI для character-service, нагрузка прохода по игрокам, две косметики в панели); локальная БД восстановлена из дампа
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- ...

### Что изменилось от первоначального плана
- ...

### Оставшиеся риски / follow-up задачи
- ...

**Статус: DONE (2026-11-05), ревью PASS.** Патрули стражи: маршрут (по кругу / туда-обратно) или зона (район / набор локаций), шаг раз в 20 мин ±25 %; при приходе — проверка всех разыскиваемых в локации, включая не в сети (формула FEAT-203); подсказка «скоро уйдёт / задержится»; ждёт ответа на встречу не дольше 30 мин; панель «Патруль» в админке с «Шаг сейчас»; общий выключатель. CI: таймаут шага тестов поднят 6 → 9 мин (тестов character-service стало ~9000). Выкатывается вместе с FEAT-201–203.
