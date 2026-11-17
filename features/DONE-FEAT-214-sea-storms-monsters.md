# FEAT-214: Шторма и морские монстры

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-17 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Этап 2 морских путей (продолжение FEAT-213, см. `features/DONE-FEAT-213-sea-routes.md`). Сейчас плавание — спокойное ожидание на палубе. Нужны опасности моря: **шторма** (погода по морям, зависит от сезона) и **налёты морских монстров на палубу** (бой для всех на борту). Это даёт игрокам на кораблях повод для отыгрыша и риск.

Караваны по морю, таможня и контрабанда — НЕ в этой фиче (следующий этап).

### Бизнес-правила

**Шторма**
- Погода задаётся на уровне **моря** (регион скрытой страны «Моря»). У каждого моря админ задаёт базовый шанс шторма.
- Шанс зависит от **сезона игрового календаря** (например, зимой чаще) — множители по сезонам, настраиваются админом. Год/сезон брать из существующего игрового календаря, не хардкодить.
- Шторм накрывает одну или несколько соседних морских зон на ограниченное время (порядок 1–3 часа реального времени, настройка), потом стихает (может сместиться в соседнюю зону — на усмотрение архитектора).
- Корабль в шторме:
  - идёт медленнее (время на зону × множитель, настройка, по умолчанию ×2);
  - может быть снесён в соседнюю зону (шанс, настройка) — путь удлиняется, затем корабль снова прокладывает курс к порту;
  - **все на палубе теряют выносливость и HP** («качка»), величины — настройки. Шторм сам по себе не убивает (HP не ниже 1) — **допущение PM**.
- Сильный шторм в зоне порта → капитан **откладывает отплытие**; билеты при этом не сгорают, отплытие переносится.
- Матросы в шторм: пост на палубе во время шторма («держим паруса») уменьшает задержку корабля — предложение PM, пользователь не возражал.
- Видимость: в шапке палубы «⛈️ Шторм в <зона>»; в порту, если шторм в его морской зоне, — «В море неспокойно»; в окне капитана — что отплытие отложено из-за шторма.

**Морские монстры**
- Монстры морских зон назначаются **тем же редактором мобов, что и у обычных локаций** (зона — это локация).
- Когда корабль входит в зону, есть шанс нападения (настройка зоны или моря; архитектор решает где).
- При нападении **бой обязателен для всех на палубе** — пассажиров, матросов и «зайцев» (как с патрулём стражи; боевой пост модератора НЕ нужен). Кто офлайн — по общим правилам таймаута хода.
- Капитан (НПС) в бою не участвует (допущение PM).
- Победа — обычные награды за мобов. Поражение — обычные последствия проигранного PvE-боя.
- Пока идёт бой, корабль стоит на месте, но не дольше настройки (по умолчанию 2 ч); потом плывёт дальше, бой продолжается на палубе (допущение PM, архитектор может предложить лучше).
- Никого на палубе (или все уже в других боях / без сознания) → нападения нет / команда отбилась сама, корабль теряет немного времени.
- Уведомление о нападении всем на борту (WS `sea`).

**Админка**
- Настройки штормов и нападений — в «Админка → Корабли» (настройки моря / зоны), по образцу `sea_settings`.
- Админ видит текущие шторма и нападения.

### UX / Пользовательский сценарий
1. Игрок плывёт; корабль входит в зону со штормом → в шапке «⛈️ Шторм», приходит уведомление, отнимается выносливость/HP, корабль идёт медленнее, может снести с курса.
2. Корабль входит в зону с монстрами → «На палубу взбирается морской змей!» → все на борту попадают в бой.
3. После боя корабль продолжает путь.
4. В порту при шторме капитан говорит, что отплытие откладывается.

### Edge Cases
- Игрок уже в другом бою или без сознания в момент нападения — не втягивается.
- Нападение пришлось на момент прибытия/швартовки — архитектор решает (предпочтительно: у причала не нападают).
- Шторм и монстры одновременно — допустимо.
- Корабль удалили/сменили маршрут во время боя или шторма — никто не застревает, бой не ломается.
- Свиток домой во время боя — по общим правилам боя.
- Сезон меняется во время шторма — шторм доигрывает.

### Вопросы к пользователю
- [x] Бой с монстрами добровольный или обязательный? → **Всех в бой** (пассажиры, матросы, зайцы).
- [x] Если никто не защищается? → Вопрос отпал (бой обязательный).
- [x] Шторм бьёт по пассажирам? → **Да, выносливость и HP.**
- [x] Шторма по сезонам календаря? → **Да.**
- [x] Матросы обязаны защищать? → **Всех в бой.**
- [x] На палубе больше 5 человек (лимит команды в бою)? → **Несколько параллельных боёв**: каждые до 5 человек получают свой отряд монстров.
- [x] (PM по анализу) Без сознания (0 HP) — не втягиваются; у причала нападений нет; поздние могут вступить обычной заявкой; шторм не бьёт тех, кто в бою; сезоны — 4, праздник входит в свой сезон.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Abbreviations: CS = character-service, BS = battle-service, LS = locations-service, CAS = character-attributes-service.
All paths below are relative to `services/`. Times are naive UTC (project convention).

### 2.1 Affected services

| Service | Why |
|---|---|
| CS | `sea_pass.py` (storm/raid hooks in stepping + departure), new sea storm/raid tables + migration `053_*`, `sea_admin.py` settings/monitor, `sea_crud.deck_view` / `captain_view` (storm info), mob spawning (`crud.spawn_mob_from_template`), new `battle_client` call, result callback endpoint + poll. |
| BS | New internal endpoint for a forced deck battle (none of the 3 existing ones fits, see 2.2), new battle tag column (migration `011_*`), callback + `/internal/{id}/result` additive field, join-request rule. |
| CAS | Storm damage: no endpoint today can drain HP/stamina with a floor of 1 (see 2.5). Probably a new internal endpoint. |
| LS | Read-only additions only if the port page must say «В море неспокойно» (`sea_read.passages_for` → `crud.py:2729/2833` `docked_ships`). Zone mob assignment needs no change (2.3). |
| Frontend | `ShipDeckHeader.tsx`, `DockedShips.tsx`, `CaptainModal/CaptainModal.tsx`, `Admin/ShipsPage/SeaSettingsCard.tsx` (+ storms/raids monitor), `hooks/useWebSocket.ts` sea event tones (`:78-80`), `types/sea.ts`. |

### 2.2 How forced / server-started battles work today

**There is no existing "forced PvE for N players with server-spawned mobs" endpoint.** Three internal battle creators exist in
`battle-service/app/main.py`, all `X-Internal-Token`-gated (`verify_internal_token`), nginx blocks `/battles/internal/`:

| Endpoint | Line | Who joins | Lock exemption / preconditions | Tag column |
|---|---|---|---|---|
| `POST /battles/internal/dungeon` | `:1667` | party team 1 + dungeon mobs team 2 | every team-1 char must hold the dungeon lock of that session | `dungeon_session_id` |
| `POST /battles/internal/guard` | `:1740` | 1 player vs 1 guard NPC | player must hold `law_encounter` lock with that id | `law_encounter_id` (BS migr. `009`) |
| `POST /battles/internal/caravan-raid` | `:1912` | leader/squad (team 0) vs guards + player escorts (team 1) | leader must consume a `caravan` post gate (`_consume_action_gate`, `:1137`) | `caravan_raid_id` (BS migr. `010`) |

- **Guard encounters / patrols are not forced battles.** A patrol (`character-service/app/patrol_crud.py` `step_guard` /
  `_sweep` `:210`) only creates a `law_encounter` (activity lock); the player chooses «драться» → `law_flows._fight`
  (`law_flows.py:158`) → `battle_client.create_guard_battle` (`battle_client.py:50`). Ignored encounters are auto-resolved
  (fine/jail) by `law_flows.auto_resolve` (`:382`), never by a battle.
- **Caravan raid = the closest template** (FEAT-211/212), 2-phase:
  1. `caravan_raid_crud.begin_raid` → row `status='starting'`, commit; 2. `spawn_guards` (`caravan_raid_crud.py:284`):
     template chosen by `pick_guard_template` (`:152`, closest `mob_templates.level` to `Locations.recommended_level`),
     `crud.spawn_mob_from_template(db, template_id, location_id, SPAWN_TYPE='dungeon', stat_multiplier=mult)` per guard
     (`SPAWN_TYPE` `:79` — hidden from location lists, `crud.py:2108/2147`), stores `guard_ids`; 3. async
     `battle_client.create_caravan_raid_battle` (`battle_client.py:72`); failure → `abandon_start` (despawn + delete row);
     4. `mark_fighting` (`:400`ish) `starting → fighting` + `battle_id`. Driven from the API (`caravan_api.py:154-204`).
  - End: BS `_notify_caravan_battle_end` (`main.py:2045`, called at `:3118` normal end and `:6016` force-finish/aborted)
    POSTs `/characters/internal/caravans/raid-result` (`caravan_api.py:207`) with 3 retries; lost callbacks are polled by the
    caravan pass `poll_raid_battles` (`caravan_raid_crud.py:965`) via `battle_client.get_battle_result` (`battle_client.py`,
    `GET /battles/internal/{id}/result`, BS `main.py:2202` — returns tags additively: `law_encounter_id`,
    `caravan_raid_id`, `winner_team`, `aborted`, `fallen_character_ids`). Stale `starting` rows expire after 10 min
    (`expire_stale_raids` `:915`); guards are despawned after the end (`despawn_guards` `:841` → `crud.despawn_dungeon_mobs`
    `crud.py:1819`, keeps the hidden `npc_role='mob'` character rows).
  - Law has the same poll fallback: `law_pass._lost_callbacks` (`law_pass.py:84`) — runs `asyncio.run(...)` from the sync
    scheduler thread, so async HTTP from a sync pass is an established pattern.
- **Battle assembly**: `_assemble_battle(db, player_ids, teams, battle_type, location_id, ...tags)` (`main.py:947`) creates
  rows, Redis state, snapshots, and auto-registers every `is_npc` participant with autobattle-service (mobs act by
  themselves). Players do **not** get autobattle automatically → an offline player just times out
  (`TURN_TIMEOUT_HOURS=24`, `config.py:11`) and is dropped.
- **Multiple players on one side**: just several ids with the same team value. Hard cap
  `BATTLE_MAX_TEAM_SIZE = 5` (`config.py:21`, env) — enforced explicitly by each endpoint (`:1097`, `:1281`, `:1399`,
  `:1491`, caravan `:1940`). **A ship deck holds `capacity` (≤200) + `crew_slots` + stowaways — more than 5 players is normal.**
- **Busy checks** in BS: `get_active_battle_for_character` (already in battle), `activity_lock.get_activity_lock` /
  `_ensure_not_activity_locked` (`:898`) / `_is_activity_locked` (`:943`) (dungeon, unconscious, jail, law_encounter,
  caravan_escort, asleep, reading), gathering via LS `/locations/internal/gathering-status` (`_free_squadmates` `:1244`
  skips busy members silently — the pattern to copy: skip, don't fail). `_ensure_npc_available` (`:919`) refuses dead/KO/0-HP
  NPCs. **Players with `current_health <= 0` are not refused anywhere** (a 0-HP player could be pulled in and lose at once).
- CS-side equivalents (sync, raw SQL): `sea_pass.in_battle` (`sea_pass.py:95`), `sea_pass.gathering` (`:102`),
  `activity_lock.lock_for_character` (`character-service/app/activity_lock.py:97`, reasons `:29-40`, priority `:73`).
- **Rewards / loss**: ordinary end-of-battle code applies to any `pve` battle: `_distribute_pve_rewards` (`main.py:479`) —
  XP + loot of defeated mobs (`/characters/internal/mob-reward-data/{id}`) to **alive** winners only, mobs marked dead,
  bestiary kills. Loss of an ordinary PvE fight has **no extra consequence**: the final Redis HP/stamina are written back
  (`_RESOURCE_SYNC_SQL` `main.py:2819`), i.e. the player ends at 0 HP and regenerates. (Knockout exists only for dungeon wipes
  `/characters/internal/activity-lock/knockout` CS `main.py:4533`, and law.)
- **Join requests**: `create_join_request` (`main.py:6555`) lets a co-located player ask to join team 0/1 of an active battle;
  caravan raids forbid it (`:6577`). The architect must decide for sea raids (teams 0/1 allow late boarders to join).
- **Notifying participants**: BS sends `pvp_battle_start` (`main.py:5384`) only in PvP flows; the internal endpoints send
  nothing — the caller (CS) notifies. FE `useWebSocket.ts:258` handles `pvp_battle_start` with a battle link
  (`battlePath(location_id, battle_id)`); a sea notice will need `battle_id` in `data` + a link.

**Conclusion for 2.2**: a new BS endpoint (e.g. `/battles/internal/sea-raid`, `pve`, players team 0 / spawned mobs team 1,
skip busy players instead of failing, new tag `sea_raid_id` + callback + result field) and a CS `sea_raids` row with the
caravan-raid lifecycle (starting → fighting → settled/expired, despawn). The team-size cap must be resolved (2.8 Q1).

### 2.3 Mobs on locations; reuse for sea zones

- Tables (CS `models.py`): `mob_templates` (`:238`: `tier normal/elite/boss`, `level`, `base_attributes`, `xp_reward`, loot
  via `mob_loot_table` `:290`, skills `mob_template_skills` `:276`), **`location_mob_spawns`** (`:303`: `mob_template_id`,
  `location_id` BIGINT no FK, `spawn_chance` 0..100, `max_active`, `is_enabled`, unique per template+location),
  `active_mobs` (`:320`: `status alive/in_battle/dead`, `spawn_type random/manual/dungeon`), packs `mob_packs` /
  `active_mob_packs` (`:363-403`, admin-spawned).
- Editor: **per template**, not per location — FE `Admin/MobsPage/AdminMobSpawns.tsx` (location picker from
  `GET /locations/locations/lookup`, LS `crud.get_locations_lookup` `crud.py:437` — **no filter, sea zones are listed**) →
  `PUT /characters/admin/mob-templates/{id}/spawns` (CS `main.py:3808`, `mobs:manage`, `crud.replace_mob_spawns`
  `crud.py:1801`). So admins can already assign templates to a zone with no code change.
- Natural spawning: `crud.try_spawn_at_location` (`crud.py:1981`) via `POST /characters/internal/try-spawn`
  (`main.py:3837`), called by LS `_try_spawn_mob` (`locations-service/app/main.py:153`) after a post / move
  (`:1151`, `:1708`, `:1966`). **Nobody posts or stands in a zone → zone rules never fire by themselves**, which is exactly
  what we want: the sea pass can read `location_mob_spawns WHERE location_id = current_zone_id AND is_enabled` itself and
  spawn the chosen templates **on the deck** (`spawn_mob_from_template(db, template, deck_id, 'dungeon')`).
- Natural reading of the existing fields for zones (suggestion, architect decides): `spawn_chance` = per-template attack
  chance on zone entry, `max_active` = how many of that template board. Then a per-zone «attack chance» setting isn't needed.
- `spawn_mob_from_template` (`crud.py:1838`) **commits** and makes a sync HTTP call to CAS per mob (10 s timeout) — must run
  **outside** the ship row lock (the per-ship tx in `sea_pass.process_ship`). Level selection exists only as
  `pick_guard_template` (closest level); a zone's `recommended_level` exists on `Locations`. `stat_multiplier` scales stats.

### 2.4 Game calendar (season)

- Owner: LS. `YEAR_SEGMENTS` (`locations-service/app/crud.py:3481`): spring 39 / beltane 10 / summer 39 / lughnasad 10 /
  autumn 39 / samhain 10 / winter 39 / imbolc 10 = `DAYS_PER_YEAR 196`; `compute_game_time` (`:3497`) on the
  `game_time_config` row (epoch + `offset_days`). Public `GET /locations/game-time` (`main.py:2268`) → `computed.segment_name`.
- CS has two ready readers:
  1. HTTP: `locations_client.get_game_segment_sync()` (`character-service/app/locations_client.py:155`) → one of 8 segment
     names or `None` on failure; used once per run by the econ events (`econ_tick.py:1252`, `econ_events.GAME_SEGMENTS`
     `econ_events.py:35`).
  2. Local, no HTTP: `economy_mint_crud.current_period(db)` (`economy_mint_crud.py:121`) reads `game_time_config` raw and
     `econ_mint.period_of` (`econ_mint.py:75`) → 4 seasons, each **season + following festival folded** (49 days). Calendar
     mirror in `econ_mint.py:16-36` (must be kept in sync with LS and FE `utils/gameTime.ts`).
- The architect must choose 4 seasons (option 2, simplest, no HTTP inside the pass) or 8 segments (festivals get own
  multipliers). Either way never hardcode the year.

### 2.5 Damaging HP / stamina server-side

- Fields: `character_attributes.current_health / max_health`, `current_stamina / max_stamina` (+ mana/energy),
  `regen_anchor_at` (FEAT-164 lazy regen). **Every CAS write path first calls `regen.settle_regen` under the row lock**
  (`character-attributes-service/app/regen.py`), crediting rest time since the anchor (battle/dungeon/gathering = busy).
- Existing CAS endpoints (all internal-token):
  - `POST /attributes/{id}/recover` (`main.py:829`): settles, adds `*_recovery` capped at max, floor **0**. Negative values
    are accepted (no validation) → usable as damage but floor is 0, not 1.
  - `POST /attributes/{id}/consume_stamina` (`main.py:951`): settles, subtracts; **400 if insufficient** (no partial).
  - `POST /attributes/internal/settle-regen` (`:534`), satiety (`:558`).
  - No "damage with floor" endpoint exists. Direct-SQL precedents in CS: `law_crud.heal_guard` (`law_crud.py:1083`, full heal
    of a guard NPC), passive XP writes; BS writes resources at battle end (`main.py:2819-2843`, also training loser HP = 1).
- **Pitfalls**: (a) a direct UPDATE skips `settle_regen` (the anchor isn't moved → minor regen accounting drift);
  (b) **characters in a battle**: BS overwrites `current_health/current_stamina` from Redis at the battle end
  (`_sync_final_resources`), so storm damage applied to an in-battle character is lost — skip them (or accept);
  (c) HP floor 1 must be enforced on the server under the row lock (`GREATEST(1, hp - x)` but never raising HP that is
  already < 1). Recommended: a small new CAS internal endpoint (bulk, settle first, floors per resource) called by CS after
  the ship transaction commits.

### 2.6 `sea_pass.py` in detail — hook points

- Scheduler: `econ_scheduler.run_scheduled_once` → `run_sea_pass` (`econ_scheduler.py:93`), daemon thread polling every
  `ECON_TICK_POLL_SECONDS` (default **60 s**, `:32`), so the 25 s claim (`sea_pass.py:45`, `claim_run` `:75` on
  `sea_settings.pass_last_run_at`) means effectively **one pass per minute**. Runs even with the economy tick off.
- `run_pass` (`:599`): one session per ship → `process_ship` (`:535`, ship row `FOR UPDATE`, lock order ship → passes →
  characters) → commit → `after_commit` (`:562`: LS cleanup for those put ashore, law notices, then
  `law_notify.publish(notices)`).
- `process_ship`: deck sanity (`:540-555`) → docked & `departs_at <= now` → `depart` (`:241`) → else sailing &
  `next_zone_at <= now` → `step` (`:509`) → `place_captain`.
- **Zone transitions**: `step` (`:509-532`) loops while `next_zone_at <= now` (offline catch-up, bounded by the path):
  `leg_pos += 1`, `current_zone_id = path[pos]`, `next_zone_at += zone_minutes` (`:520-525`, event `"zone"`); end of path →
  `arrive` (`:462`) → `_dock` (`:386`). Hooks:
  - **zone entered** = the `pos < len(path)` branch (`:521`): monster roll, storm effects; a raid must `break` the catch-up
    loop and hold the ship (`next_zone_at` pushed). Note the catch-up advances `next_zone_at` from the previous
    `next_zone_at`, not from `now` — an extended time per zone (storm ×2) belongs here (`zone_minutes × mult`).
  - Leg start: `depart` sets `current_zone_id = path[0]`, `next_zone_at = now + zone_minutes` (`:357-358`) — the first
    zone is the port's own zone; "no attack at the pier" means no roll at `leg_pos == 0` / at docking (`_dock`).
  - **Drift** (blown into a neighbour zone): `ship.leg_path` is a JSON snapshot; the rerouting precedent is in `arrive`
    (`:481-500`): `sea_core.leg_path(graph.adj, graph.zone_ids, from_zone, to_zone_port, None, params.path_max_zones)`
    → reset `leg_path`, `leg_pos=0`, `current_zone_id`, `next_zone_at`. Adjacency: `sea_crud.zone_graph` (`sea_crud.py:177`).
    ETA displays use `sea_crud.current_arrival` (`:388`) = `next_zone_at + remaining × zone_minutes` — will be optimistic
    under storms (cosmetic, but the Captain/deck header ETAs need a note or a multiplier).
  - **Departure delay**: the departure branch is `process_ship :556-558` (`departs_at <= now`) → a storm check before
    `depart` can push `departs_at` (passes are keyed by `trip_no + 1`, so tickets stay valid automatically; `depart` burns
    only at the actual departure). Port zone = `Locations.port_sea_zone_id` (via `sea_crud.location_infos` `:145`,
    `LocInfo.port_zone_id`).
- **Players on deck**: `sea_crud.deck_players(db, ship, lock=)` (`:917`, `is_npc = 0`, ascending id). Captain is an NPC
  (`place_captain` `:140`) and is never in that list.
- **WS notices**: `sea_crud.notice(user_id, message, character_id, ship_id, event, **data)` (`sea_crud.py:618`) →
  `law_notify.Notice(ws_type="sea", CATEGORY_PROGRESS, data={character_id, ship_id, event, ...})`, appended to
  `ShipOutcome.notices` (`sea_pass.py:62`) and published after commit. Event constants `sea_pass.py:48-55`. FE tones by
  event: `useWebSocket.ts:78-80` (`SEA_ERROR_EVENTS`, `SEA_SUCCESS_EVENTS`, `SEA_BELL_ONLY_EVENTS`), handler `:493`;
  `ShipDeckHeader.tsx:75` reloads on any sea notice of its ship. New events (`storm`, `raid`, `delayed`, `drift`) need
  entries there.
- **`sea_settings` shape**: one row id=1 (`models.py:2311`): `pass_last_run_at`, `sailor_post_min_chars`,
  `stowaway_base_pct`, `stowaway_wanted_points`, `path_max_zones`. Fixed columns, **no JSON column** → any new global setting
  needs DDL (migration) + `SeaParams`/`load_params` (`sea_crud.py:215-227`) + `settings_out`/`save_settings`
  (`sea_admin.py:634/641`) + `SeaSettingsIn/Out` (`sea_schemas.py`) + routes `GET/PUT /admin/sea/settings`
  (`sea_admin.py:744-754`, `locations:read/update`) + FE `SeaSettingsCard.tsx`. Without DDL the only option would be named
  constants. Per-sea settings (base storm chance, season multipliers) need a new table keyed by the sea `region_id`
  (CS owns ship logic; `Regions` belong to LS — econ-style no-FK table in CS is the FEAT-213 precedent). Zone→sea:
  `econ_ledger.resolve_location(db, zone_id)` (`econ_ledger.py:105`) → `(region_id, country_id)`; LS `Countries.is_hidden`
  (`locations-service/app/models.py:42`) marks «Моря».
- **Alembic heads** (verified): CS `052_sea_ships` (down `051_caravan_escorts`); LS `060_sea_zones` (down
  `059_location_neighbor_unique`); BS `010_battle_caravan_raid` (down `009_battle_law_encounter`). Revision ids ≤ 32 chars.

### 2.7 Battle on the deck while the ship moves

- The ship never moves its passengers: `characters.current_location_id` stays the deck; only `sea_ships` state changes.
  `battles.location_id` = deck (BS `models.py:53`). Everything bound to `battles.location_id` keeps working at sea:
  spectate (`main.py:2436-2450`), battle visibility on the location page (`battle_visibility.py:68-105`), join requests
  (`:6579`), location name in the battle page (`:2583`). BS battle actions do **not** check the participant's location.
- Departure never moves a character in an active battle (`sea_pass.depart :276-279`, he "stays aboard", his passes are not
  burnt since he is `aboard`). Arrival does nothing to players. LS refuses moving / posting while in battle
  (`locations-service/app/main.py:370`, `:1479`, `:1782`) → nobody can disembark mid-fight.
- **Breakers**: `sea_crud.safe_land` (`sea_crud.py:977`) — used when the deck is deleted, no valid stop/path, ship deleted by
  admin — puts **every** player ashore, including ones in a battle (no `in_battle` skip). The battle itself survives (no
  location check on actions), but the hidden mobs stay on the old deck id and must be despawned; spectate/join break for
  that battle. If the deck location row is deleted, battles keep a dangling `location_id` (cosmetic).
- Hidden raid mobs (`spawn_type='dungeon'`) on a deck are not in location lists, but they are `characters` with
  `current_location_id = deck` — despawn after the battle (caravan pattern) so they don't accumulate.

### 2.8 Risks and open questions

Risks (technical, for the architect):
1. **Team cap 5** vs. a full deck (2.2). Options: raise the cap for sea raids only, split into several battles, or pick 5
   and leave the rest out (they may join via join requests).
2. **HTTP inside a locked transaction**: mob spawning (CAS HTTP per mob, commits) + BS create (10 s) + autobattle register
   must happen after the ship tx commits → 2-phase `starting/fighting` row, stale-start expiry and poll fallback (copy
   caravan raid). The sea pass is sync in a daemon thread; use `asyncio.run` like `law_pass`.
3. One pass per minute; long HTTP for many ships delays all ships in that pass (sequential loop).
4. Storm damage vs. battle-end resource sync (2.5 b) and vs. regen settle (2.5 a). HP floor 1 needs server enforcement.
5. 0-HP players can be dragged into a forced battle and lose instantly; storms floor HP at 1 but a previous lost fight leaves 0.
6. `safe_land` moves in-battle players (existing gap, more likely now); hold timer (2 h) vs `TURN_TIMEOUT_HOURS = 24` — the
   battle often outlives the hold; arrival/departure with an open deck battle must stay safe (it is today).
7. ETA texts (Captain modal, deck header, departure notice) ignore storm slowdowns/holds.
8. `zone_minutes` minimum 1 and 60 s scheduler granularity: storms "1–3 h" and holds are fine; per-zone effects in
   catch-up after downtime must not fire a burst of damage/raids (cap to one per pass or skip during catch-up).
9. Season source: HTTP (8 segments, can fail → `None`) vs local `current_period` (4 seasons). Decide the fallback (multiplier 1).

Questions for PM (game-design, may go to the user):
- Q1. Deck with more than 5 fighters: one battle with everyone (raise the limit), several parallel battles, or 5 in battle
  and the rest «держат оборону» (not fighting)?
- Q2. Players already at 0 HP (after a lost fight) when monsters attack — pulled in anyway, or skipped like the unconscious?
- Q3. Players busy gathering on the deck — pulled in (gathering cancelled) or skipped?
- Q4. Seasons: 4 seasons (festivals count as the preceding season) or separate multipliers for the 4 festivals too?
- Q5. May other players on the deck (boarded later, came out of another fight) join the monster fight via the usual join
  request, or is the roster fixed at the attack?
- Q6. Storm damage to a player currently in another battle — skip (recommended) or apply?

## 3. Architecture Decision (filled by Architect — in English)

Abbreviations as in section 2 (CS, BS, LS, CAS). Times are naive UTC. Everything extends the FEAT-213 ship design
(`DONE-FEAT-213-sea-routes.md` §3) and copies the FEAT-211/212 caravan-raid battle lifecycle. **No activity-lock change,
no `econ_core.py` / `activity_lock.py` copy is touched** (byte-identical copy rules are therefore not triggered), no RBAC
migration (admin reuses `locations:read` / `locations:update`), no nginx / docker / env change (`/characters/internal/`,
`/attributes/internal/`, `/battles/internal/` are already blocked by nginx).

### 3.1 Ownership and modules

| Piece | Owner | Where |
|---|---|---|
| Storms (weather step), per-sea storm config, raids (rows, roll, mob spawn, start, settle, poll), hold / slowdown / drift / postponed departure, storm damage trigger, WS `sea` notices, admin API | **CS** | new `sea_weather.py` (storms + damage client), new `sea_raid_crud.py` (raid lifecycle), pure helpers in `sea_core.py`, hooks in `sea_pass.py`, views in `sea_crud.py`, admin in `sea_admin.py`, internal callback in `sea_api.py`, schemas in `sea_schemas.py` |
| Forced deck battle + tag + end callback + result field + join rule | **BS** | `main.py`, `schemas.py`, `models.py`, `crud.create_battle`, migration `011` |
| HP / stamina storm damage with floors, after `settle_regen` | **CAS** | new internal endpoint in `main.py` + schemas |
| «В море неспокойно» on the port page | **LS** | `sea_read.py` (tolerant raw read of CS storm tables), `crud.py` location details, `schemas.py` (no migration) |
| UI | **FE** | deck header, captain modal, docked ships, WS tones + battle link, admin Ships page |

### 3.2 Decisions on the open points

| Topic | Decision |
|---|---|
| Storm config level | **Per sea** (= the LS region of the hidden «Моря» country that holds the zone): `enabled`, `chance_per_hour_pct`, `radius`. Everything else (durations, multipliers, damage, drift, postpone, sailor relief, season multipliers) is **global** in `sea_settings`. |
| Attack config level | **Per zone, via the existing mob editor**: `location_mob_spawns` rows of the zone (`location_id = zone`, `is_enabled`). `spawn_chance` = attack chance of that template on zone entry; `max_active` = max monsters per battle group. One global knob `raid_chance_mult` (0 = raids off, default 1.0). No zone/sea attack-chance column. |
| Season | 4 seasons, festival folded into its season: `economy_mint_crud.current_period(db).season` (local, no HTTP). Missing calendar → multiplier 1.0. |
| Team cap | Eligible deck players are split into `ceil(n/5)` groups, **evened out** (6 → 3+3, 11 → 4+4+3), ascending character id; each group = one battle with its own pack. Constant `SEA_RAID_TEAM_MAX = 5` (mirrors BS `BATTLE_MAX_TEAM_SIZE`). |
| Pack size per group | `min(clamp(max_active, 1, 5), len(group))` monsters of the rolled template, stat multiplier 1.0 (see Questions for PM). |
| Who is pulled in | deck players (`is_npc = 0`) that are **not** in an active battle, **not** activity-locked (unconscious, jail, reading, asleep …), `current_health > 0`, **not gathering** (BS `_free_squadmates` parity; see Questions). Captain (NPC) never. |
| No attack at the pier | rolls only at an effective zone entry with `leg_pos >= 1` (never at `leg_pos == 0`, never in `_dock`, never while docked). |
| Catch-up after downtime | only the **effective** step (after stepping, `next_zone_at > now`, i.e. the ship really is in that zone now) applies damage / drift / raid roll. Steps skipped through are "quiet" (slowdown timing still applied, no effects). |
| Storm damage | % of max, once per effective entry into a stormy zone; skips players in an active battle; HP never below 1 and never raised; via a new CAS internal bulk endpoint called **after** the ship tx commits. |
| Hold during a raid | ship holds while it has active raids, at most `raid_hold_max_minutes` (default 120); then sails on, battles continue on the deck. |
| Late joiners | ordinary join request, **team 0 only** (crew side); team 1 → 400. |
| safe_land / delete gap | `safe_land` and `delete_ship` never move a player in an active battle (3.9). |
| "Strong" storm at the port | any active storm covering the port's zone postpones departure (no storm strength levels; see Questions). |

### 3.3 Data model

#### CS migration `053_sea_storms_raids` (revision id 20 chars; down_revision `052_sea_ships`)

Econ-style: BigInteger PKs, **no FKs** (zones, regions, ships, characters may vanish), explicit indexes.

```sql
ALTER TABLE sea_settings
  ADD COLUMN weather_last_run_at        DATETIME NULL,                      -- last weather step (elapsed time base)
  ADD COLUMN storm_min_minutes          INT NOT NULL DEFAULT 60,            -- 10..1440
  ADD COLUMN storm_max_minutes          INT NOT NULL DEFAULT 180,           -- >= min, ..1440
  ADD COLUMN storm_move_pct             DECIMAL(5,2) NOT NULL DEFAULT 30,   -- 0..100 chance to shift at the end
  ADD COLUMN storm_max_moves            INT NOT NULL DEFAULT 2,             -- 0..10
  ADD COLUMN storm_slow_mult            DECIMAL(4,2) NOT NULL DEFAULT 2.00, -- 1.00..10.00 time per zone multiplier
  ADD COLUMN storm_drift_pct            DECIMAL(5,2) NOT NULL DEFAULT 15,   -- 0..100 per stormy entry
  ADD COLUMN storm_hp_pct               DECIMAL(5,2) NOT NULL DEFAULT 10,   -- 0..100 of max_health per stormy entry
  ADD COLUMN storm_stamina_pct          DECIMAL(5,2) NOT NULL DEFAULT 20,   -- 0..100 of max_stamina
  ADD COLUMN storm_postpone_minutes     INT NOT NULL DEFAULT 15,            -- 1..240 one postpone step
  ADD COLUMN storm_postpone_max_minutes INT NOT NULL DEFAULT 240,           -- 0..1440 total cap, then sails anyway
  ADD COLUMN storm_sailor_relief_pct    DECIMAL(5,2) NOT NULL DEFAULT 50,   -- 0..100 of the storm delay removed
  ADD COLUMN season_mult_spring         DECIMAL(4,2) NOT NULL DEFAULT 1.00, -- 0..10
  ADD COLUMN season_mult_summer         DECIMAL(4,2) NOT NULL DEFAULT 0.50,
  ADD COLUMN season_mult_autumn         DECIMAL(4,2) NOT NULL DEFAULT 1.50,
  ADD COLUMN season_mult_winter         DECIMAL(4,2) NOT NULL DEFAULT 2.00,
  ADD COLUMN raid_chance_mult           DECIMAL(4,2) NOT NULL DEFAULT 1.00, -- 0..10 (0 = no raids)
  ADD COLUMN raid_hold_max_minutes      INT NOT NULL DEFAULT 120,           -- 0..1440
  ADD COLUMN raid_repelled_delay_minutes INT NOT NULL DEFAULT 5;            -- 0..120 nobody could fight

ALTER TABLE sea_ships
  ADD COLUMN hold_until          DATETIME NULL,      -- raid hold end (sailing); NULL = not holding
  ADD COLUMN storm_hold_since    DATETIME NULL,      -- docked: departure postponed by a storm since …
  ADD COLUMN storm_extra_minutes INT NOT NULL DEFAULT 0,  -- storm delay added to the current zone
  ADD COLUMN storm_post_floor_id BIGINT NULL;        -- MAX(posts.id) at the stormy entry; NULL = no relief pending

CREATE TABLE sea_storm_seas (                         -- per-sea config, keyed by LS Regions.id
  region_id           BIGINT PRIMARY KEY,
  is_enabled          TINYINT(1) NOT NULL DEFAULT 0,
  chance_per_hour_pct DECIMAL(5,2) NOT NULL DEFAULT 0,   -- 0..100 base chance of a new storm per real hour
  radius              INT NOT NULL DEFAULT 1,            -- 0..5 zones around the centre (same sea only)
  updated_at          DATETIME NOT NULL
);

CREATE TABLE sea_storms (
  id             BIGINT PK AUTO_INCREMENT,
  region_id      BIGINT NULL,                 -- the sea (NULL for an admin storm in a zone without region)
  center_zone_id BIGINT NOT NULL,
  status         VARCHAR(10) NOT NULL,        -- active | ended
  source         VARCHAR(10) NOT NULL,        -- auto | admin
  moves          INT NOT NULL DEFAULT 0,
  started_at     DATETIME NOT NULL,
  ends_at        DATETIME NOT NULL,
  ended_at       DATETIME NULL,
  INDEX ix_sea_storms_active (status, ends_at),
  INDEX ix_sea_storms_region (region_id, status)
);

CREATE TABLE sea_storm_zones (                 -- covered zones (indexed lookup for CS and LS)
  storm_id BIGINT NOT NULL,
  zone_id  BIGINT NOT NULL,
  PRIMARY KEY (storm_id, zone_id),
  INDEX ix_sea_storm_zones_zone (zone_id)
);

CREATE TABLE sea_raids (                       -- one row per battle group
  id               BIGINT PK AUTO_INCREMENT,
  ship_id          BIGINT NOT NULL,
  attack_key       VARCHAR(48) NOT NULL,       -- f"{ship_id}:{trip_no}:{leg_pos}:{drift_n}" — one attack per entry
  group_no         INT NOT NULL,               -- 0..
  deck_location_id BIGINT NOT NULL,
  zone_id          BIGINT NOT NULL,
  mob_template_id  INT NOT NULL,
  monster_name     VARCHAR(255) NULL,          -- snapshot for notices / admin
  player_ids       JSON NOT NULL,              -- planned group
  placed_ids       JSON NULL,                  -- placed by BS
  mob_ids          JSON NULL,                  -- spawned hidden mobs (characters.id)
  battle_id        BIGINT NULL,
  status           VARCHAR(10) NOT NULL,       -- starting | fighting | won | lost | aborted | expired
  mobs_despawned   TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL, started_at DATETIME NULL, ended_at DATETIME NULL,
  UNIQUE KEY uq_sea_raids_group (attack_key, group_no),
  INDEX ix_sea_raids_ship (ship_id, status),
  INDEX ix_sea_raids_status (status, created_at),
  INDEX ix_sea_raids_battle (battle_id)
);
```
Rollback: drop the 4 tables, drop the 4 `sea_ships` and 19 `sea_settings` columns. Models: `SeaStormSea`, `SeaStorm`,
`SeaStormZone`, `SeaRaid`; new columns on `SeaSetting` / `SeaShip`. `sea_crud.SEA_TABLES` stays as is (old tables are
the availability probe); the weather/raid code is tolerant of missing new tables (`DBAPIError` → log once, skip).

#### BS migration `011_battle_sea_raid` (revision id 19 chars; down_revision `010_battle_caravan_raid`)

```sql
ALTER TABLE battles ADD COLUMN sea_raid_id INT NULL;
CREATE INDEX ix_battles_sea_raid_id ON battles (sea_raid_id);
```
Rollback: drop index + column. Model `Battle.sea_raid_id` (as `caravan_raid_id`).

#### LS — no migration.

### 3.4 Pure helpers (`sea_core.py`, no DB — unit-tested)

- `season_mult(season: Optional[str], params) -> Decimal` (unknown/None → 1.0).
- `pass_chance(per_hour_pct, mult, elapsed_minutes) -> Decimal` = `1 − (1 − p)^(elapsed/60)` with `p = min(1, pct×mult/100)`,
  `elapsed` clamped to `[0, 60]` (no burst after downtime).
- `split_groups(ids, cap=5) -> List[List[int]]` — `ceil(n/cap)` groups, sizes differ by ≤ 1, ascending ids.
- `pack_size(max_active, group_len) -> int` = `min(max(1, min(max_active, 5)), group_len)`.
- `storm_zones(adj, zone_sea, center, radius) -> List[int]` BFS limited to the centre's sea.
- `storm_extra(zone_minutes, slow_mult) -> int` = `round(zone_minutes × (slow_mult − 1))`; `relief(extra, pct)` = `floor(extra × pct/100)`.
- `pick_drift(adj, current, next_zone, rng) -> Optional[int]` — a random adjacent sea zone ≠ `next_zone` (None if none).
- RNG: `sea_core.weather_rng()` returns `random.Random()`; tests patch it (law `detection_rng` pattern).

### 3.5 Weather step (CS `sea_weather.py`)

`run_weather(db, now, params)` is called by `sea_pass.run_pass` **once per pass, after the claim and before the ships**,
in its own transaction (failure logged, ships still processed):

1. **End / move due storms** (`status='active' AND ends_at <= now`, `FOR UPDATE`): if `moves < storm_max_moves` and a
   roll of `storm_move_pct` succeeds and the centre has a neighbour zone in the same sea → new centre = random neighbour,
   zones recomputed (`sea_core.storm_zones`), `ends_at = now + uniform(min, max)` minutes, `moves += 1` (a season change
   never affects a running storm). Else `status='ended'`, `ended_at = now`.
2. **Spawn**: `elapsed = now − weather_last_run_at` (None → 1 min); for each `sea_storm_seas` row with `is_enabled` and no
   active `auto`/`admin` storm in that region (max **one** storm per sea): roll `pass_chance(chance_per_hour_pct,
   season_mult, elapsed)`; success → random zone of that sea as centre, zones by `radius`, duration `uniform(min, max)`.
   Zone → sea: `sea_crud.zone_graph(db).zone_ids` resolved with `econ_ledger.resolve_location` (cached per pass).
3. `weather_last_run_at = now`; commit.

Helpers: `storm_at(db, zone_id, now) -> Optional[StormInfo]` (`sea_storm_zones ⋈ sea_storms`, `status='active' AND
ends_at > now`), `storms_for(db, zone_ids, now)` (bulk, for views). Storm start/move/end produce **no** WS notice
(ships report effects on entry).

### 3.6 Ship hooks (`sea_pass.py`)

Order inside `process_ship` (ship row locked, no HTTP): sanity → **raid hold release** → departure (with **storm
postpone**) / step (with **zone effects**) → **sailor relief** → captain placement. New events (stats keys and WS
`data.event`): `storm`, `drift`, `storm_delay`, `storm_relief`, `raid`, `raid_repelled`, `raid_won`, `raid_lost`,
`hold_released`, `hold_expired`.

1. **Departure postpone** (docked & active & `departs_at <= now`, before `depart`): if `storm_at(port zone)` and
   (`storm_hold_since` is NULL or `now − storm_hold_since < storm_postpone_max_minutes`) → `departs_at = now +
   storm_postpone_minutes`; first time (`storm_hold_since` NULL) → set it and notify everyone on the deck once
   («Капитан откладывает отплытие: в море шторм»). Passes are keyed by `trip_no + 1` → tickets stay valid. Otherwise
   `depart` runs and clears `storm_hold_since`.
2. **Zone entry** in `step` (the `pos < len(path)` branch): `base = zone_minutes`; stormy zone → `extra =
   storm_extra(...)`, `next_zone_at += base + extra`, `storm_extra_minutes = extra`, `storm_post_floor_id =
   sea_crud.max_post_id(db)`; else `storm_extra_minutes = 0`, `storm_post_floor_id = NULL`. If the step is **effective**
   (new `next_zone_at > now`) and `pos >= 1`:
   - stormy → collect `storm_damage` targets = deck players not `in_battle` (applied after commit, 3.7) + notice `storm`
     («Корабль попал в шторм в «зона»: качка…»); then drift roll `storm_drift_pct` → `pick_drift` → new path
     `sea_core.leg_path(adj, zone_ids, drift_zone, dest_port_zone, None, path_max_zones)`; path found → `leg_path = path`,
     `leg_pos = 0`, `current_zone_id = drift_zone` (timer unchanged), notice `drift`; else no drift.
   - raid roll (3.8) unless the ship already has an active raid (`starting`/`fighting`).
   - after a drift or raid start the catch-up loop `break`s.
3. **Sailor relief** (sailing, `storm_post_floor_id` not NULL, `storm_extra_minutes > 0`): an aboard holder of an
   active `sailor` pass covering `trip_no` with a deck post `id > storm_post_floor_id` and plain length ≥
   `sailor_post_min_chars` (reuse `sailor_worked`) → `next_zone_at = max(now, next_zone_at − relief(extra, pct))`,
   `storm_post_floor_id = NULL`, notice `storm_relief` («Матросы удержали паруса — корабль идёт быстрее»). Once per zone.
4. **Raid hold release** (sailing, `hold_until` not NULL): no active raid rows of the ship → `shift = max(0, hold_until −
   now)`, `next_zone_at -= shift`, `hold_until = NULL`, event `hold_released`; `hold_until <= now` with raids still
   active → `hold_until = NULL`, notice `hold_expired` («Корабль идёт дальше, бой на палубе продолжается»). While
   `hold_until > now` the ship does not step (`next_zone_at` was pushed anyway, so stepping is naturally late).
5. **Arrival / departure with an open deck battle** stay as today (no one in a battle is moved).
6. ETA displays: `current_arrival` stays optimistic (no change); the header shows the storm/hold state instead.

### 3.7 Storm damage (CAS endpoint + CS client)

`POST /attributes/internal/storm-damage` (X-Internal-Token, `verify_internal_token`; nginx already blocks the prefix):
```
request  StormDamageRequest  {items: [{character_id: int >= 1, health_pct: float 0..100, stamina_pct: float 0..100}]
                              (1..200 items, distinct ids), min_health: int = 1 (ge 1)}
response StormDamageResponse {applied: [{character_id, health_before, health_after, stamina_before, stamina_after}],
                              missing: [int]}
```
Per item, one short transaction: `SELECT … FOR UPDATE` → `regen.settle_regen(db, attr)` → `dh = ceil(max_health ×
health_pct/100)`, `ds = ceil(max_stamina × stamina_pct/100)`; `new_hp = current if current <= min_health else max(min_health,
current − dh)`; `new_st = max(0, current_stamina − ds)`; commit (satiety reconciliation as in `recover` if
`settle_regen` returned True). Missing row → `missing`. Errors → 500 «Ошибка применения урона от шторма».
CS: `sea_weather.apply_storm_damage(targets)` — sync `httpx.post(f"{ATTRIBUTES_SERVICE_URL}internal/storm-damage",
headers=internal token, timeout 10 s)` from `after_commit`; failure → WARNING, no retry (a missed rocking is harmless).
Players in a battle were excluded in CS (their Redis state would overwrite it).

### 3.8 Raids (CS `sea_raid_crud.py` + BS endpoint)

**Roll (inside the ship tx, `sea_pass`)**: candidates = `location_mob_spawns` of `current_zone_id` with `is_enabled`
and an existing template; shuffled by `weather_rng`; first with roll `< spawn_chance × raid_chance_mult` wins (none →
no attack). Eligible = deck players filtered as in 3.2 (`sea_pass.in_battle`, `activity_lock.lock_for_character`,
`character_attributes.current_health > 0` raw read, `sea_pass.gathering`).
- **No eligible** → `next_zone_at += raid_repelled_delay_minutes`, notice `raid_repelled` to all deck players
  («Команда отбилась от «монстр»»), no rows.
- **Else** → groups `split_groups(eligible)`; INSERT one `sea_raids` row per group (`starting`, `attack_key`,
  `player_ids`, template, monster snapshot); `hold_until = now + raid_hold_max_minutes`, `next_zone_at +=
  raid_hold_max_minutes`; notice `raid` to every deck player («На палубу взбирается «монстр»!»). `IntegrityError` on
  `uq_sea_raids_group` → treat as already started. Ship tx commits.

**Start (after commit, `start_pending(db, ship_id)` from `after_commit`, also retried by the pass for rows still
`starting` without mobs)** per row:
1. spawn `pack_size` mobs: `crud.spawn_mob_from_template(db, template, deck_id, SPAWN_TYPE='dungeon')` (commits per mob),
   store `mob_ids`;
2. `asyncio.run(battle_client.create_sea_raid_battle(raid_id, deck_id, player_ids, mob_ids))`;
3. 201 → `mark_fighting` (`starting → fighting`, `battle_id`, `placed_ids`, `started_at`) + per placed player a WS `sea`
   notice `raid` with `battle_id`, `location_id = deck` (FE link); 409/4xx/5xx → `abandon` (despawn mobs, status
   `aborted`, `ended_at`), logged.

**BS `POST /battles/internal/sea-raid`** (`verify_internal_token`, response 201):
```
SeaRaidBattleCreate  {sea_raid_id: int, location_id: int,
                      player_character_ids: List[int] (1..5), mob_character_ids: List[int] (1..5)}
SeaRaidBattleCreated {battle_id, participants: List[int], next_actor: int, deadline_at: datetime,
                      player_character_ids: List[int]}        # the players actually placed
```
- mobs: `_ensure_caravan_guards` gains an optional `message` parameter (default the caravan text, call sites
  unchanged); sea calls it with `SEA_MOBS_UNAVAILABLE = "Морские монстры недоступны"` → 409.
- players: each **silently skipped** unless `is_npc = 0`, `current_location_id == location_id`, no active battle, no
  activity lock (`_is_activity_locked`), `current_health > 0` (raw read of `character_attributes`); duplicates removed.
  None left → 409 `SEA_NO_FIGHTERS = "Некому защищать палубу"`.
- no post gate, no ownership (server-initiated); team 0 = players, team 1 = mobs; `battle_type = "pve"`;
  `_assemble_battle(..., sea_raid_id=...)` (+ `crud.create_battle(sea_raid_id=None)` kwarg, same "only when set" rule).
  Mobs are auto-registered with autobattle as today; players are not.
- Rewards / loss = ordinary PvE end (`_distribute_pve_rewards`), nothing extra.
- **End callback** `_notify_sea_battle_end(db, battle_id, winner_team, aborted)` next to the caravan one (normal end
  `:3118`, force-finish `:6016`): POST `/characters/internal/sea/raid-result` `{battle_id, sea_raid_id, winner_team,
  aborted}`, 3 retries (copy of `_post_caravan_callback`), no-op without the tag.
- `GET /battles/internal/{id}/result` gains `"sea_raid_id"` (additive).
- `create_join_request`: sea raid battle and `req.team != 0` → 400 `SEA_JOIN_TEAM = "Против морских монстров можно
  встать только на сторону экипажа"`; team 0 → normal flow (moderator approval).

**Settle — CS `POST /characters/internal/sea/raid-result`** (`verify_internal_token`, body `SeaRaidResultIn
{battle_id: int, sea_raid_id: int, winner_team: Optional[int], aborted: bool = False}` → `{status}`): lock row;
final already → `already` (only despawn); unknown → `unknown`; `fighting`/`starting` → `aborted` if aborted, `won` if
`winner_team == 0`, else `lost`; `ended_at`; commit; notices to `placed_ids` (`raid_won` «Монстры отбиты!» / `raid_lost`
«Монстры одолели вас»); then `despawn_mobs` (`crud.despawn_dungeon_mobs`, `mobs_despawned = 1`). The ship hold is
released by the next pass (3.6.4) — the callback never locks the ship.

**Pass fallbacks** (`sea_raid_crud.raid_followups(factory, now)` called at the end of `run_pass`, each step best
effort): stale `starting` > 10 min → tagged battle exists → attach (`fighting`); else despawn + `expired`;
`fighting` started > 2 min → `battle_client.get_battle_result` (404 → aborted; finished → settle); final rows with
`mobs_despawned = 0` → despawn. Batch 200.

### 3.9 Safe landing / delete fixes (FEAT-213 gap)

- `sea_crud.safe_land`: players `in_battle` are **not** moved (logged, `LandingResult.kept_in_battle`), no notice.
- `sea_pass.process_ship`: an **inactive** ship with `blocked_reason` set whose deck has players not in battle and no
  disembark (deck gone, or docked with `docked_port_id IS NULL`) → `safe_land` again (re-runs every pass until empty).
  The existing "deck gone" branch already loops while `on_old_deck`; it now also covers players who left their battle.
- `sea_admin.delete_ship`: a deck player in an active battle **or** an active raid row of the ship → 409 `MSG_DELETE_BATTLE
  = "На палубе идёт бой — списать корабль можно после его окончания"`.
- Raid mobs are despawned by raid id regardless of whether the ship / deck still exists.

### 3.10 Player-facing API

`ShipPublicOut` (used by the deck view S5 and the captain view S1) — additive fields:
```
storm:               Optional[StormRefOut]  {zone_id, zone_name, ends_at}   # active storm over current_zone_id
departure_postponed: bool                   # docked and storm_hold_since not NULL
raid:                Optional[RaidStateOut] {monster_name, hold_until: Optional[datetime],
                                             battles: [{battle_id: int}]}   # active (fighting) raids of the ship
```
LS location details (`LocationClientDetails`, built by `sea_read.passages_for`): `sea_unrest: bool = False` — the
location is a port whose `port_sea_zone_id` is covered by an active storm (tolerant raw read of `sea_storm_zones` ⋈
`sea_storms`, missing tables → False, one WARNING). No new public endpoint.

### 3.11 Admin API (CS `sea_admin.py`, prefix `/characters`)

| Method / path | Perm | Body / response |
|---|---|---|
| `GET /admin/sea/settings` / `PUT` | `locations:read` / `locations:update` | `SeaSettingsIn/Out` + the 18 new fields (validated ranges as in 3.3; `storm_max_minutes >= storm_min_minutes` → 400 «Максимальная длительность шторма меньше минимальной») |
| `GET /admin/sea/weather` | `locations:read` | `{season, season_mult, seas: [{region_id, name, zones_count, is_enabled, chance_per_hour_pct, radius}], storms: [{id, region_id, sea_name, center_zone: {id,name}, zones: [{id,name}], started_at, ends_at, moves, source}], raids: [{id, ship_id, ship_name, zone: {id,name}, monster_name, players: [{id,name}], battle_id, status, created_at}]}` — seas = regions holding ≥ 1 `is_sea_zone` location; raids = active + last 20 final |
| `PUT /admin/sea/seas/{region_id}` | `locations:update` | `{is_enabled: bool, chance_per_hour_pct: 0..100, radius: 0..5}` → the sea row; region without sea zones → 404 «Море не найдено» |
| `POST /admin/sea/storms` | `locations:update` | `{zone_id: int ≥ 1, minutes: 10..1440}` → 201 storm; not a sea zone → 400 «Это не морская зона» (centre + its sea's `radius`, `source='admin'`, bypasses the one-per-sea rule) |
| `DELETE /admin/sea/storms/{storm_id}` | `locations:update` | 204, ends an active storm (404 unknown / already ended) |

Pattern: plain `def`, `_read` / `_write` helpers, Russian error texts, `SeaError`. Rate limiting: none beyond the global
nginx limits (admin-only, RBAC-protected; internal endpoints are token-only and blocked externally).

### 3.12 Frontend

- `types/sea.ts`: `StormRef`, `RaidState`, new `ShipPublic` fields, admin types (`SeaWeather`, `SeaStormSea`,
  `SeaStormAdmin`, `SeaRaidAdmin`, extended `SeaSettings`); `SeaNoticeData` gains optional `battle_id`, `location_id`.
- `api/sea.ts`: `getSeaWeather`, `putSeaStormSea`, `createSeaStorm`, `endSeaStorm`.
- `ShipDeckHeader.tsx`: «⛈️ Шторм в «зона»» (until time), «⚔️ На палубе бой с «монстр»» + links to the battles
  (`battlePath(deck, battle_id)`), «Корабль стоит, пока идёт бой (до HH:MM)».
- `CaptainModal.tsx`: when `ship.departure_postponed` — «Отплытие отложено из-за шторма».
- `DockedShips.tsx` (port): when `sea_unrest` — «В море неспокойно» (needs the LS field in the location type).
- `useWebSocket.ts`: tones — error: `storm`, `raid`, `raid_lost`, `drift`; success: `raid_won`, `storm_relief`,
  `raid_repelled`; default: `storm_delay`, `hold_expired`. A `sea` notice with `battle_id` + `location_id` shows a toast
  with a «К бою» link (as `pvp_battle_start`).
- Admin `ShipsPage`: `SeaSettingsCard.tsx` gets «Шторма» / «Нападения» field groups (+ season multipliers); new
  `SeaWeatherCard.tsx` (Tailwind, design system, 360px+): seas table (enable / chance / radius, save per row), active
  storms (zones, ends at, «Завершить»), «Вызвать шторм» (zone select + minutes), raids list (ship, zone, monster,
  players, battle link, status). Every call shows Russian errors. No `React.FC`.

### 3.13 Security

- Internal endpoints (BS `/battles/internal/sea-raid`, CS `/characters/internal/sea/raid-result`, CAS
  `/attributes/internal/storm-damage`): `X-Internal-Token` only, nginx-blocked prefixes, Pydantic bounds (list sizes,
  pct ranges), ids validated server-side (BS re-checks location / battle / lock / HP of every player and mob).
- Admin endpoints: `require_permission("locations:read"|"locations:update")`, all inputs range-checked, ORM/param SQL.
- No user input reaches the sea pass; notices contain only DB names.
- Idempotency: `uq_sea_raids_group`; settle is a conditional status update; despawn guarded by `mobs_despawned`.

### 3.14 Edge cases

| Case | Behaviour |
|---|---|
| Player in another battle / unconscious / 0 HP / gathering at attack | not pulled in (may join team 0 later by request) |
| Attack at docking / at the leg start | impossible (`pos >= 1`, never in `_dock`) |
| Storm + monsters together | both applied on the same entry (damage first, then raid roll) |
| Ship deleted / route changed during a battle | delete refused while a deck battle runs; route change does not move players; raid rows settle and despawn independently |
| Deck deleted during a battle | in-battle players stay on the dangling id until their battle ends, then safe-landed by the next pass |
| Home scroll during the raid | general battle rules |
| Season changes during a storm | storm plays out (multiplier used only at spawn) |
| Lost BS callback | pass polls `fighting` rows; stale `starting` rows expire after 10 min |
| BS refuses (all players became busy) | row `aborted`, mobs despawned, hold released next pass |
| Downtime catch-up | quiet steps, no damage/raid bursts; weather elapsed clamped to 60 min |

### 3.15 Questions for PM (defaults are implemented unless the user decides otherwise)

1. **Pack size**: monsters per battle group = `min(max_active of the zone spawn, players in the group)` (a solo player
   never faces more monsters than the group size). Alternative: always `max_active` (up to 5).
2. **Gathering on deck** at the attack moment → skipped (like other busy states). Alternative: pulled in, gathering
   cancelled.
3. **«Сильный шторм»**: every storm over the port zone postpones departure (no strength levels).
4. **Storm damage cadence**: once per entry into a stormy zone (10 % HP / 20 % stamina of max by default), not per minute.

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | BS: migration `011_battle_sea_raid` + `Battle.sea_raid_id`; `create_battle`/`_assemble_battle` `sea_raid_id` kwarg; `POST /battles/internal/sea-raid` (3.8, skip-not-fail players, optional `message` param of `_ensure_caravan_guards`); `_notify_sea_battle_end` + callback at both end points; `sea_raid_id` in `/internal/{id}/result`; join request team-0-only rule; docs | Backend Developer | DONE | `services/battle-service/app/{main.py,schemas.py,models.py,crud.py}`, `alembic/versions/011_battle_sea_raid.py`, `docs/services/battle-service.md` | — | py_compile passes; endpoint returns 201 with placed players, 409 when none/mobs unavailable; callback no-op for untagged battles; existing caravan/guard/dungeon flows unchanged |
| 2 | CAS: `POST /attributes/internal/storm-damage` (3.7) with settle_regen, floors, schemas; docs | Backend Developer | DONE | `services/character-attributes-service/app/{main.py,schemas.py}`, `docs/services/character-attributes-service.md` | — | py_compile passes; HP never < 1 and never raised, stamina ≥ 0, regen settled first, token required |
| 3 | CS data + weather: migration `053_sea_storms_raids`, models, `sea_core` helpers (3.4), `sea_weather.py` (3.5, storm lookups, CAS damage client), `SeaParams`/`load_params` extension | Backend Developer | DONE | `services/character-service/app/{models.py,sea_core.py,sea_weather.py,sea_crud.py}`, `alembic/versions/053_sea_storms_raids.py` | — | migration up/down on MySQL; storms spawn/move/end per settings & season; one storm per sea; tolerant of missing tables |
| 4 | CS ship hooks + raids: `sea_pass` changes (3.6: postpone, zone effects, drift, relief, hold, quiet catch-up, raid roll), `sea_raid_crud.py` (start/mark/abandon/settle/despawn/followups), `battle_client.create_sea_raid_battle`, internal `POST /characters/internal/sea/raid-result`, safe_land / delete fixes (3.9), WS notices | Backend Developer | DONE | `services/character-service/app/{sea_pass.py,sea_raid_crud.py,battle_client.py,sea_api.py,sea_schemas.py,sea_crud.py,sea_admin.py}` | 1, 2, 3 | py_compile passes; no HTTP inside the ship lock; groups ≤ 5 evened; no attack at pier; hold released / expired correctly; in-battle players never moved |
| 5 | CS views + admin API: `ShipPublicOut` storm/postponed/raid fields (3.10); settings extension; `GET /admin/sea/weather`, `PUT /admin/sea/seas/{id}`, `POST/DELETE /admin/sea/storms` (3.11); docs `character-service.md` | Backend Developer | DONE | `services/character-service/app/{sea_crud.py,sea_admin.py,sea_schemas.py}`, `docs/services/character-service.md` | 3, 4 | endpoints match contracts, RBAC enforced, validation errors in Russian |
| 6 | LS: `sea_unrest` in location details via tolerant `sea_read` read (3.10); docs | Backend Developer | DONE | `services/locations-service/app/{sea_read.py,crud.py,schemas.py}`, `docs/services/locations-service.md` | 3 | py_compile passes; port in a storm → true; missing CS tables → false + warning |
| 7 | FE: types/api, `ShipDeckHeader`, `CaptainModal`, `DockedShips`, `useWebSocket` tones + battle link, admin `SeaSettingsCard` + new `SeaWeatherCard` (3.12) | Frontend Developer | DONE | `services/frontend/app-chaldea/src/{types/sea.ts,api/sea.ts,hooks/useWebSocket.ts}`, `components/pages/LocationPage/{ShipDeckHeader.tsx,DockedShips.tsx,CaptainModal/CaptainModal.tsx}`, `components/Admin/ShipsPage/{SeaSettingsCard.tsx,SeaWeatherCard.tsx,ShipsPage.tsx}`, location types | 5, 6 | `npx tsc --noEmit` and `npm run build` pass; Tailwind only, design system, 360px+, no `React.FC`, all errors shown in Russian |
| 8 | QA BS: sea-raid endpoint (placement/skips incl. 0 HP & locked, 409s, tag, team sizes), end callback payload, result field, join team rule | QA Test | DONE | `services/battle-service/app/tests/test_sea_raid_battle.py` | 1 | pytest green; existing caravan raid tests still pass |
| 9 | QA CAS: storm-damage floors, settle-before-damage, missing ids, token required, bounds | QA Test | DONE | `services/character-attributes-service/app/tests/test_storm_damage.py` | 2 | pytest green |
| 10 | QA CS: `sea_core` helpers; weather step (spawn/season/move/end/clamp); pass hooks (postpone & cap, slowdown, quiet catch-up, drift, damage targets exclude in-battle, sailor relief, hold release/expire, no pier attack, repelled delay); raid lifecycle with mocked BS/CAS (start, abandon, settle idempotent, poll, stale expiry, despawn); safe_land/delete fixes; admin endpoints + RBAC + validation; deck/captain view fields | QA Test | DONE | `services/character-service/app/tests/{sea_storm_world.py,test_sea_storm_core.py,test_sea_weather.py,test_sea_storm_pass.py,test_sea_raids.py,test_sea_weather_admin.py}` | 3, 4, 5 | pytest green; existing sea / caravan tests still pass |
| 11 | QA LS: `sea_unrest` true/false/tolerant | QA Test | DONE | `services/locations-service/app/tests/test_sea_unrest.py` | 6 | pytest green |
| 12 | Review: contracts across BS/CS/CAS/LS/FE, migrations (≤ 32-char ids, FK-free, rollback), security checklist, no lock/copy files touched, tsc + build + py_compile + pytest, live check (admin storm in a zone → deck header, damage, postpone; zone with a mob spawn → raid battle(s) with > 5 players split; callback/despawn) | Reviewer | DONE | all of the above | 1–11 | PASS with automated results and live verification |


## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-17
**Result:** PASS

#### Checklist
- [x] **Contracts BS ↔ CS ↔ CAS ↔ LS ↔ FE.** CS `battle_client.create_sea_raid_battle` → BS `POST /battles/internal/sea-raid` (`sea_raid_id`, `location_id`, `player_character_ids` 1..5, `mob_character_ids` 1..5; response `player_character_ids` = placed). BS `_notify_sea_battle_end` (normal end + force-finish) → CS `POST /characters/internal/sea/raid-result` `{battle_id, sea_raid_id, winner_team, aborted}` = `SeaRaidResultIn`. `GET /battles/internal/{id}/result` gains `sea_raid_id` (additive, used by the poll). CS `sea_weather.apply_storm_damage` → `ATTRIBUTES_SERVICE_URL` (`…/attributes/`) + `internal/storm-damage` = CAS route; payload `{items[{character_id, health_pct, stamina_pct}], min_health: 1}` ≤ 200 items = `StormDamageRequest`. LS `sea_unrest` ↔ FE `LocationData.sea_unrest`; `ShipPublicOut.storm / departure_postponed / raid` ↔ FE `ShipPublic`; admin `SeaWeatherOut` / `StormSeaIn` / `StormCreateIn` ↔ `types/seaAdmin.ts`. All internal calls send `X-Internal-Token`; nginx already blocks the `/internal/` prefixes.
- [x] **Migrations.** CS `053_sea_storms_raids` (20 chars, down `052_sea_ships`), BS `011_battle_sea_raid` (19 chars, down `010_battle_caravan_raid`); single heads (dev containers: `alembic current` = head for both); no FK, no ENUM, every step guarded (idempotent), downgrade drops tables/columns/index.
- [x] **Concurrency / idempotency.** No HTTP inside the ship row lock (damage + raid start in `after_commit`); raid rows only planned in the ship tx (`uq_sea_raids_group`, `attack_key` includes trip/pos/zone/timer); `_claim_start` (`mob_ids IS NULL → []`) gives one starter per row; `mark_fighting` / `settle` are conditional updates; despawn guarded by `mobs_despawned`; callback never locks the ship (hold released by the next pass). Lock order ship → (passes) → characters unchanged; raid rows are locked alone. Quiet catch-up: effects only on the effective entry.
- [x] **Edge cases (Section 1).** In battle / locked / 0 HP / gathering skipped (CS and re-checked by BS); no roll at `leg_pos 0` / docking; storm + raid on the same entry; delete with a deck battle → 409, `safe_land` keeps fighters aboard; season multiplier only at spawn; stale `starting` expiry + poll fallback.
- [x] **Security.** Internal endpoints token-only; admin endpoints `locations:read` / `locations:update`; Pydantic bounds on every input (verified live: 422 for minutes < 10, 400 «Это не морская зона», 404 «Шторм не найден или уже закончился»); raw SQL is parameterised; Russian error texts.
- [x] **Copies.** No `econ_core.py` / `activity_lock.py` copy touched (`git diff --stat` empty).
- [x] **Frontend rules.** All new/changed files `.tsx`/`.ts`, Tailwind + design-system classes (`site-link`, `btn-blue`, `rounded-card`, `text-site-*`), no `React.FC`, no `any`; every admin call shows a Russian error (state + toast); 360 px: admin «Погода» tab has no horizontal scroll (scrollWidth = clientWidth in a 360 px iframe).
- [x] **Docs.** `ARCHITECTURE.md`, `battle-service.md`, `character-attributes-service.md`, `character-service.md`, `locations-service.md` updated. No ISSUES.md entry fixed or newly required by this feature.
- [x] **QA coverage.** Tasks 8–11 DONE: BS `test_sea_raid_battle.py`, CAS `test_storm_damage.py`, CS 5 new files + `sea_storm_world.py`, LS `test_sea_unrest.py`.

#### Fixed during review (trivial)
| # | File:line | Description | Status |
|---|-----------|-------------|--------|
| 1 | `services/character-service/app/sea_raid_crud.py:130` | Monster name snapshot was not trimmed — the dev template « Бакэзори» (leading space in data) rendered as «  Бакэзори» in the deck header / notices. Now `(name or "").strip() or "морской монстр"`. Sea test files re-run: 455 passed. | FIXED |

#### Notes (non-blocking)
- Raid monsters keep their hidden `npc_role='mob'` character rows on the deck after despawn (same established pattern as dungeons / caravan guards, `crud.despawn_dungeon_mobs`); they accumulate over time like the other spawn types.
- The deck header ETA during a raid hold includes the whole hold (`next_zone_at` pushed by `raid_hold_max_minutes`), e.g. «прибытие ≈ через 02:01» — by design (§3.6.6), corrected as soon as the hold is released.
- character-service suite took 23 min when run in parallel with three other suites locally; alone it fits the CI 15-min limit (7 min before this feature + ~356 new tests) but is worth watching.

#### Automated Check Results
- [x] `py_compile` (all modified/new Python files) — PASS
- [x] `pytest` character-service (`--asyncio-mode=auto`, python:3.10 container) — PASS, 10810 passed, 1 skipped
- [x] `pytest` battle-service (`--asyncio-mode=auto`) — PASS, 2182 passed
- [x] `pytest` locations-service (`--asyncio-mode=auto`) — PASS, 3321 passed
- [x] `pytest` character-attributes-service (`--asyncio-mode=auto`) — PASS, 1036 passed, 2 skipped, 1 xpassed
- [x] `npx tsc --noEmit` (frontend container) — PASS (host node_modules lack `react-icons` — stale host install, unrelated)
- [x] `npm run build` / `vite build` (frontend container) — PASS
- [x] `docker compose config` — PASS
- [x] Live verification (Claude in Chrome + API on localhost) — PASS

#### Live Verification Results
Temporary world via admin APIs: hidden country «Моря (тест)» → region «Тестовое море» with 4 linked sea zones + deck; visible «Берег (тест)» with «Порт А» (zone 1) / «Порт Б» (zone 4); Captain NPC; ship «Тестовый бриг» (zone 1 min, boarding 3 min); `PUT /admin/sea/seas/43` radius 0; mob template 49 on zone 3 with spawn_chance 100 / max_active 3; drift 0, postpone step 1 min; 6 characters of user 4 (706, 761–765) on the deck with test tickets.
- `POST /admin/sea/storms` on zone 1 → deck header «⛈️ Шторм в «Тест-зона 1» — до 23:04»; port A page «В море неспокойно» (`sea_unrest=true`, port B false); departure postponed (`storm_hold_since` set, `departs_at` +1 min, one notice per player «Капитан … откладывает отплытие…»), header «Отплытие отложено из-за шторма». Storm ended (204, repeat 404) → ship departed, tickets kept.
- Storm on zone 2 → entry: notice «…попал в шторм…», CAS storm-damage 200: HP −10 % / stamina −20 % of max after regen settle (e.g. 761: 545→490, 180→144), `storm_extra_minutes=1`, sailor floor set, header shows the storm.
- Zone 3 → raid: 2 rows (3+3, same `attack_key`), 3 monsters each, battles 332/333 `pve` tagged, hold 120 min; header «⚔️ На палубе бой с «Бакэзори»!» + «К бою 1 (#332) / К бою 2 (#333)» + «Корабль стоит… (до 00:43)»; link opens `/location/999946/battle3d/333`.
- Admin force-finish both → callbacks 200 → rows `aborted`, `mobs_despawned=1`, `active_mobs` removed; next pass released the hold, ship stepped to zone 4 and docked at port B.
- Admin «Корабли → Погода» tab renders seas / storms / raids. Console errors: NONE on deck, battle and admin pages.
- Cleanup: storms ended, ship deleted via API, settings restored, spawns of template 49 cleared, locations/regions/countries deleted via API; captain + 6 mob characters, raid/storm/pass rows, battles 332/333, test notifications removed; the 6 characters' rows (location, HP, stamina) restored from a pre-test dump.

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-17 — PM: фича создана по ответам пользователя, запускаю анализ
[LOG] 2026-11-17 — PM: пользователь выбрал параллельные бои по 5; передаю архитектору
[LOG] 2026-11-17 — Codebase Analyst: анализ готов (раздел 2): шаблон — налёт на караван (2-фазный старт, скрытые мобы, колбэк + опрос); нужен новый внутренний эндпоинт боя в battle-service; лимит команды 5; сезон есть в CS; урона с порогом HP=1 в attributes-service нет
[LOG] 2026-11-17 20:37 — Architect: спроектировано 12 задач (6 backend, 1 frontend, 4 QA, ревью); миграции CS 053 и BS 011, LS без миграции; новые эндпоинты: BS sea-raid, CS raid-result + 4 админских, CAS storm-damage; 4 вопроса к PM с ответами по умолчанию
[LOG] 2026-11-17 21:30 — Backend Developer: задача 1 готова — battle-service: миграция 011_battle_sea_raid (up/down/up на dev MySQL), POST /battles/internal/sea-raid, колбэк /characters/internal/sea/raid-result, поле sea_raid_id в /internal/{id}/result, вступление только за команду 0, документация; тест головы миграций каравана сделан устойчивым к 011; pytest 2052 passed (13 старых падений test_passives_wave1 — нет плагина async в контейнере, не связаны)
[LOG] 2026-11-17 — Backend Developer: задача 2 готова — CAS POST /attributes/internal/storm-damage (токен, досчёт восстановления до урона, HP ≥ min_health и не поднимается, выносливость ≥ 0), схемы и документация; py_compile ок, pytest CAS 965 passed, живая проверка в контейнере (401 без токена, 422 на границах, missing для чужого id)
[LOG] 2026-11-17 — QA Test: задача 9 готова — test_storm_damage.py, 61 тест (округление вверх, пороги HP/выносливости, HP не поднимается, досчёт восстановления до урона, missing, токен 401, границы/дубли/422, инъекции); весь набор CAS в контейнере: 1026 passed, 12 skipped; багов не найдено
[LOG] 2026-11-17 — Backend Developer: задача 3 готова — миграция CS 053_sea_storms_raids (up/down/up на MySQL), модели SeaStormSea/SeaStorm/SeaStormZone/SeaRaid + новые колонки, хелперы sea_core, sea_weather.py (шаг погоды, storm_at/storms_for, клиент урона CAS), SeaParams расширен; полный набор тестов CS 10453 passed (обновлён тест единственной головы миграций)
[LOG] 2026-11-17 — QA Test: задача 8 готова — test_sea_raid_battle.py, 107 тестов (токен, 422 на границах 1..5 и инъекции, тихие пропуски игроков: НПС/нет/не на палубе/в бою/занят/HP≤0/нет атрибутов, дубли, id монстра в списке игроков, 409 «Некому защищать палубу», 409 монстров с морским текстом, команды 0/1 и pve, тег, колбэк на обычном и принудительном конце, ретраи, поле в /result, вступление только за команду 0, миграция 011); весь набор battle-service: 2159 passed (13 старых падений test_passives_wave1); багов не найдено
[LOG] 2026-11-17 — Backend Developer: задача 4 готова — sea_pass: перенос отплытия в шторм (один раз уведомление, потолок), замедление/урон/снос в шторм только на «настоящем» входе в зону (догонялка тихая), облегчение матросами, удержание корабля на время боя (возврат неиспользованного времени / «идём дальше»), бросок налёта по правилам мобов зоны (не у причала, группы ≤5 поровну, «отбились», если некому); новый sea_raid_crud.py (старт после коммита: мобы → бой BS → fighting, отказ → aborted + деспаун; колбэк/опрос/просроченные старты/деспаун), battle_client.create_sea_raid_battle, POST /characters/internal/sea/raid-result; safe_land не трогает бойцов, списание корабля при бое на палубе — 409; живая проверка на dev (урон шторма через CAS, бой BS с тегом, принудительное завершение → колбэк → aborted + деспаун, повтор → already, без токена 401), данные убраны; полный набор CS 10453 passed, 2 skipped (существующие морские тесты не менялись)
[LOG] 2026-11-17 — Backend Developer: задача 6 готова — locations-service: поле `sea_unrest: bool` в деталях локации (порт, чья port_sea_zone_id под активным штормом; терпимое чтение sea_storm_zones ⋈ sea_storms в sea_read.zone_in_storm, нет таблиц → false + WARNING), схема, документация, тест структуры ответа дополнен; py_compile ок, test_client_details 42 passed, живая проверка: /locations/28/client/details → sea_unrest=false, шторм в транзакции → true, истёкший → false; остальные падения набора — нет плагина async в контейнере, не связаны
[LOG] 2026-11-17 — QA Test: задача 11 готова — test_sea_unrest.py, 16 тестов (порт в активном шторме → true, шторм на несколько зон, аноним; истёкший/завершённый/отменённый → false; шторм в чужой зоне; не-порт с зоной и сама зона → false; порт без зоны; нет таблиц штормов → false + ровно одно предупреждение; граница ends_at); весь набор LS в контейнере: 3316 passed, 5 skipped; багов не найдено
[LOG] 2026-11-17 — Backend Developer: задача 5 готова — ShipPublicOut (капитан S1 и палуба S5): storm / departure_postponed / raid; настройки A7 + 18 чисел шторма/налётов (в PUT необязательны, max < min → 400); новые админские GET /admin/sea/weather, PUT /admin/sea/seas/{id}, POST и DELETE /admin/sea/storms (права locations:read/update); документация задач 3–5 в character-service.md и ARCHITECTURE.md; py_compile ок, полный набор CS 10453 passed, 2 skipped (тест настроек теперь сравнивает прежние 4 поля — ответ стал шире); живая проверка на dev (401 без токена, 422/400/404 с русскими текстами, шторм 201 → завершён 204 → повтор 404; две локации временно помечены морскими и возвращены, тестовые строки удалены)
[LOG] 2026-11-17 — Frontend Developer: задача 7 готова — типы/API (шторм, налёт, перенос отплытия, погода в админке), общий блок SeaShipAlerts (шторм до HH:MM, «Отплытие отложено из-за шторма», «На палубе бой с …» со ссылками «К бою» и стоянкой) в шапке палубы и у капитана, «В море неспокойно» в порту, тона морских уведомлений + всплывашка с кнопкой «К бою» и ссылкой в колокольчике, настройки моря по группам (Плавание/Шторма/Сезоны/Нападения), новая вкладка «Погода» (сезон и множитель, моря с сохранением по строке, активные шторма с «Завершить», вызов шторма, список нападений); tsc и build ок, живая проверка админки на localhost без ошибок консоли (на dev нет морских зон — палубу со штормом вживую не видел)
[LOG] 2026-11-17 — QA Test: задача 10 готова — character-service, 356 тестов в 5 новых файлах + общий хелпер sea_storm_world.py: хелперы sea_core (сезоны, шанс за час с потолком в час, группы 6→3+3 / 11→4+4+3 / >10, размер стаи, зоны шторма в пределах моря, замедление, облегчение, снос); шаг погоды (появление по шансу/сезону, одно море — один шторм, сдвиг/конец, зажим радиуса, выключенное море, нет таблиц → одно предупреждение); хуки рейса (перенос отплытия с потолком и сохранением билетов, замедление, тихая догонялка, снос и бросок монстра в зоне после сноса, урон без бойцов и капитана, облегчение матросами один раз, удержание/возврат времени/«идём дальше», не у причала, «отбились» с задержкой); жизненный цикл налёта (BS 409/обрыв/сбой спавна → aborted + деспаун, частичная расстановка, колбэк won/lost/aborted/already/unknown/чужой бой, токен 401, 422, опрос через 2 мин, протухшие старты, привязка к тегированному бою); safe_land/списание при бое (409); поля storm/departure_postponed/raid в палубе и у капитана; админка (настройки, погода, моря, шторма, 503 без таблиц, RBAC 401/403); весь набор CS в контейнере: 10809 passed, 2 skipped; багов не найдено
[LOG] 2026-11-17 23:55 — Reviewer: проверка завершена, результат PASS — контракты BS/CS/CAS/LS/FE совпадают, миграции 053/011 в порядке, тесты CS 10810 / BS 2182 / LS 3321 / CAS 1036 зелёные, tsc и сборка ок; живая проверка на временном море: шторм в порту (перенос отплытия, «В море неспокойно»), качка −10 % HP / −20 % выносливости, налёт на 6 человек → 2 боя 3+3, колбэк после принудительного завершения, деспаун, снятие стоянки и прибытие; мелкая правка — обрезка пробелов в имени монстра; тестовые данные удалены, персонажи восстановлены
```

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Шторма по морям: шанс в час и радиус на каждое море, множители по 4 сезонам игрового календаря; шторм живёт, смещается и стихает.
- Корабль в шторме: медленнее (×2), может снести в соседнюю зону, все на палубе (кроме тех, кто в бою) теряют 10% HP и 20% выносливости при входе в зону; HP не ниже 1 (новый эндпоинт attributes-service storm-damage).
- Шторм в зоне порта откладывает отплытие (с потолком), билеты не сгорают; в порту — «В море неспокойно».
- Матросский пост в шторм сокращает задержку.
- Морские монстры: шанс нападения и размер отряда — из редактора мобов зоны; бой обязателен для всех на палубе; больше 5 — параллельные бои поровну (6 → 3+3); корабль стоит до 2 ч, потом плывёт, бой продолжается; у причала не нападают; без сознания / в бою / заняты — не втягиваются; опоздавшие вступают только за экипаж.
- Высадка и удаление корабля больше не трогают игроков в бою; удалить корабль во время боя на палубе нельзя.
- Интерфейс: шторм/отложенное отплытие/бой в шапке палубы и окне капитана, уведомления с кнопкой «К бою»; админка «Корабли»: настройки по группам и вкладка «Погода» (моря, шторма, ручной шторм, нападения).
- Миграции: character 053_sea_storms_raids, battle 011_battle_sea_raid.
- Тесты: CS 10810, BS 2182, LS 3321, CAS 1036 — все зелёные; живая проверка на тестовом море пройдена.

### Что изменилось от первоначального плана
- Решение пользователя: больше 5 человек на палубе — параллельные бои.

### Оставшиеся риски / follow-up задачи
- Набор тестов character-service растёт (локально 23 мин при 4 параллельных наборах) — следить за лимитом CI 15 мин.
- Скрытые строки мобов остаются после боя (как у данжей и караванов).
