# FEAT-207: Фракции — этап 3 (территории, пассивки, враги, запрет)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-06 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Третий, последний этап фракций. Строится поверх FEAT-205 (ядро: фракции, очки, звания, враждебность, тайные фракции) и FEAT-206 (экономика: казна, тик, пожертвования, интендант). Оба этапа сделаны локально и ещё НЕ запушены — этот этап ложится поверх незакоммиченной рабочей копии.

Пять частей:
1. Закрытые локации и данжи фракций.
2. Пассивки на званиях.
3. Очки за убийство врагов фракции.
4. Членство как преступление в крае.
5. Пожертвование предметов.

### Бизнес-правила (предложения PM; пользователь может поправить)

**1. Закрытые локации и данжи**
- Админ в редакторе локации/данжа ставит «только для фракции X, от звания N» (звание опционально — тогда достаточно членства). Можно несколько фракций на одну локацию? — нет, одна фракция на локацию (YAGNI).
- Не-участник (или звание ниже N) не может войти: перемещение отклоняется с понятной русской ошибкой. Локация видна на карте/в списке соседей с отметкой «Закрыто: <фракция>».
- Локация тайной фракции для не-участников показывается как «Закрыто» без имени фракции (не раскрывать).
- Данж фракции: войти может группа, только если КАЖДЫЙ участник группы проходит условие.
- Админы/модераторы проходят без проверки (для отладки) — если это уже принято в похожих проверках доступа; иначе не делать.
- Игрок, который стоит в закрытой локации и вышел/исключён/потерял право — выкидывается в ближайшую открытую соседнюю локацию (или в штаб/станцию края — решит архитектор), с записью в журнале фракций.
- Уже идущий забег данжа при потере членства не прерывается.

**2. Пассивки на званиях**
- Новый тип награды звания — «пассивка»: набор модификаторов из уже существующего словаря модификаторов (статы, резисты, крит, уклонение, урон и т.п. — то, что умеет бой/экипировка). Название + описание пассивки для игрока.
- В отличие от разовых наград, пассивка действует, пока игрок состоит во фракции и имеет это звание (или выше). Выход/исключение — снимается; повторное вступление и возврат звания — снова действует (это не повторная награда).
- Пассивки разных фракций и разных званий складываются. Действуют в бою (PvP/PvE/данжи).
- Во вкладке «Фракции» видно активные пассивки; в каталоге/лестнице званий — какие пассивки даёт звание.

**3. Очки за убийство врагов фракции**
- Админ задаёт для фракции список врагов и сколько очков даёт победа:
  - конкретные мобы / NPC (по шаблону моба или NPC);
  - участники враждебных фракций (пары враждебности из этапа 1) — за победу в PvP.
- Очки получают все члены фракции из победившей стороны, которые участвовали в бою.
- Защита от фарма в PvP: за одного и того же противника — не чаще раза в 24 ч; дневной лимит очков с убийств на фракцию (по умолчанию 50, настройка).
- Тайные участники враждебной фракции НЕ считаются врагами (иначе очки раскрывают членство).
- Штраф враждебности из этапа 1 (−50 % у враждебных фракций, где игрок состоит) действует и на эти очки, как на любые очки.
- «Победа» = как в существующих наградах за бой (кто считается победителем — по текущей логике battle-service).

**4. Членство как преступление в крае**
- Админ отмечает фракцию «вне закона в крае X» (можно несколько краёв) и тяжесть по шкале закона края (FEAT-198).
- Открытый участник такой фракции, находясь в крае, где она вне закона, считается правонарушителем: стража реагирует так же, как на розыск (проверки стражи при проходе мимо/патрулях FEAT-203/204, тюрьма страны FEAT-202) — правонарушение «членство в запрещённой фракции».
- Тайный участник: стража при проверке может раскрыть членство с шансом (через существующую механику скрытности FEAT-201 — тот же бросок, что для обнаружения); раскрытие → правонарушение, но членство в профиле остаётся тайным для других игроков.
- Правонарушение за членство фиксируется не чаще раза в N времени (не спамить штрафами при каждом шаге) — настройка, по умолчанию раз в сутки на край.
- Игрок видит во вкладке «Фракции» и в каталоге предупреждение «В крае X эта фракция вне закона».

**5. Пожертвование предметов**
- В диалоге пожертвования (этап 2) можно сдать предметы, а не только марки.
- Ценность предмета = его цена на рынке края штаба фракции (как считает экономика); очки по тому же курсу 10 марок = 1 очко и в общий дневной лимит 50 очков.
- Предмет уходит фракции: попадает в её казну-склад и продаётся в тик на рынок края (деньги в казну) — или иначе, как решит архитектор с сохранением инварианта экономики (деньги не появляются из воздуха).
- Нельзя сдавать: экипированное, привязанное/квестовое, без цены.

### UX / Пользовательский сценарий
1. Игрок видит на карте «Закрыто: Орден Х», вступает, получает звание — проходит.
2. Получает звание с пассивкой — во вкладке «Фракции» появляется блок «Пассивки» с бонусами; в бою они работают.
3. Побеждает моба из списка врагов или участника враждебной фракции — «+N очков фракции» в результатах/журнале.
4. Заходит в край, где его фракция вне закона, — видит предупреждение; стража может оштрафовать/арестовать.
5. Сдаёт предметы в пожертвование — получает очки.
6. Админ: в редакторе фракции новые вкладки/блоки — враги (с очками), края вне закона (с тяжестью), лимиты; в редакторе звания — пассивка; в редакторе локации/данжа — ограничение по фракции.

### Edge Cases
- Локация закрыта для фракции, которую админ деактивировал — локация открывается (или остаётся закрытой для всех — решит архитектор, вариант PM: открывается).
- Игрок в группе, один из группы не член — группа не входит в данж фракции, ошибка называет причину без раскрытия тайных фракций.
- Перемещение по маршруту патруля/стражи (NPC) через закрытые локации — ограничение только для персонажей игроков.
- Пассивки не должны дублироваться при одновременном членстве на разных званиях одной фракции (берётся набор всех полученных званий до текущего — или только текущего — решит архитектор; вариант PM: суммируются пассивки всех званий до текущего включительно).
- Все сроки — обратным отсчётом.

### Вопросы к пользователю (если есть)
- [x] Общий объём этапа 3 → «Делай этап 3» (решения выше — предложения PM, пользователь может поправить)

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

All line numbers refer to the current **uncommitted** working copy (FEAT-205/206 on top of `34e0d0d`).

### Affected Services

| Service | Type of change | Key files |
|---|---|---|
| character-service (sync, Alembic `alembic_version_character`) | owner of all faction logic: location/dungeon access rule, eject, rank passives, enemies + kill points, outlaw regions + law hook, item donations, admin | `faction_core.py`, `faction_crud.py`, `faction_admin_crud.py`, `faction_econ.py`, `faction_econ_crud.py`, `faction_pass.py`, `faction_api.py`, `law_crud.py`, `patrol_crud.py`, `main.py` (`update_location`, `_prepare_move`), `crud.py` (`execute_teleport`, `apply_admin_move`), `models.py`, `schemas.py`, migration `047_*` |
| locations-service (async) | `Locations` gate columns, move pre-check, closed marks in neighbours / region map | `main.py` (move_and_post / quick_move), `crud.py` (client details, region details), `faction_read.py`, `schemas.py`, `models.py`, migration `059_*` |
| dungeon-service (async) | `dungeons` gate columns, per-member entry check | `gameplay.py` (`_check_entrant`, `start_run`), `models.py`, `schemas.py`, migration `010_*` |
| battle-service (async) | faction battle-result callback (kill points); passives only if the "battle-time" option is chosen | `main.py` (`_finalize_battle`, `build_participant_info`) |
| character-attributes-service (sync) | only if passives are stored as attribute deltas (option P-A): include faction source in `rebuild_derived_stats` | `crud.py:185` |
| inventory-service | **no change expected** (item removal can follow the guild/mint precedent of direct `character_inventory` writes) | — |
| user-service | probably no new permission (see §7) | `alembic/versions/0036_*` only if needed |
| frontend | admin faction editor (enemies, outlaw regions, limits, rank passive), location + dungeon editors, neighbours/map/dungeon entrance marks, faction tab passives/warnings, item donation dialog | see §6 |
| party-service | none — `/party/internal/active-members` already returns the squad (`dungeon-service/app/http_clients.py:60`) | — |

### Existing Patterns
- character-service: sync SQLAlchemy, raw parameterised SQL on other services' tables (shared DB), flows return `FlowResult` (notices + deliveries) committed by `faction_api._write` (`faction_api.py:108`), post-commit side effects via `_dispatch` (`faction_api.py:134`). Idempotency by `faction_log UNIQUE(event_key, faction_id)` (`faction_crud.py:375/387`). Day counters: `faction_donation_days` + `ensure_day_row` own-transaction pattern (`faction_econ_crud.py:426`).
- locations-service: async, reads faction tables through `faction_read.py` (tolerant: SQL error → "no faction data", `faction_read.py:65`); messages `MSG_MEMBERS_ONLY` / `MSG_RANK_NEEDED` already exist (`faction_read.py:25-26`).
- dungeon-service: async; no faction reader yet; reads the shared DB raw (e.g. `_surface_busy`, `gameplay.py:972`).
- No staff/admin bypass exists in any comparable gate (quest faction gate, teleport reputation gate, plot gate) → per §1 «иначе не делать».
- Memory note: hidden/password locations are "future"; **no location access model exists yet** — this is the first one.

---

### 1. Location movement / entry paths

**Player move (locations-service, async):**
- `POST /locations/{dest}/move_and_post` — `main.py:1406`. Order: ownership → `check_not_locked_for_post` (jail/prison, `main.py:242`) → battle/gathering → profile via HTTP → travel cooldown → neighbour check (`main.py:1476-1489`, `LocationNeighbor`) → stamina → post length → **`crud.create_post` commits the post (`main.py:1531`)** → `_update_character_location` (`main.py:1561` → `main.py:306`) → cooldown, stamina, etc.
- `POST /locations/{dest}/quick_move` — `main.py:1700`; same shape, `no_quick_move` check `main.py:1763`, post created `main.py:1812` **before** `_update_character_location` (`main.py:1817`).
- Known debt: the post is committed before the move can be refused (`docs/ISSUES.md:852`). ⇒ the faction gate must be checked in locations-service **before `create_post`** (via `faction_read`), and re-checked authoritatively in character-service.
- `_update_character_location` passes a 409 detail through to the player (`main.py:320-328`) — a faction refusal from character-service surfaces with its Russian text for free.

**Authoritative write (character-service):** `PUT /characters/internal/{id}/update_location` — `main.py:2358`. Locks the character row (`main.py:2389`), refuses jail/encounter (`main.py:2392-2396`), sets location, runs `law_crud.check_entry` (`main.py:2407`) in the same commit. Best place for the authoritative faction gate (row already locked, `source` known, NPC skip trivial: `character.is_npc`).

**Other ways a player lands in a location (must be considered):**
| Path | File:line | Faction gate? |
|---|---|---|
| Teleport master | `crud.execute_teleport` `crud.py:3799` (move at `3902`, law check `3913`); options + locks `teleport_lock_reasons` `crud.py:3774` (FEAT-197 reputation gate per link — natural place to add a `locked_reason` for a closed target) | yes (refuse + show lock) |
| Admin teleport / jail / flee-back / home scroll | `crud.apply_admin_move` `crud.py:4141`; jail `law_flows.py:101`, flee back `law_flows.py:230` | admin: no; jail/flee-back: architect (jail inside a faction location = unlikely, recommend no gate) |
| Dungeon knockout return | `main.py:4345` (`return_location_id`) — puts character back on the dungeon location | no gate; the eject sweep handles it |
| Character creation start location | `main.py:531-534` | no |
| NPC/guard patrol move | `patrol_crud.step_guard` writes `guard.current_location_id` directly (`patrol_crud.py:269`) — never goes through update_location | automatically exempt (brief: players only) |

**Neighbours / map for the frontend:**
- Location page: `GET /locations/{id}/client/details` (`main.py:1288`) → `crud.get_client_location_details` (`crud.py:2528`); neighbours built at `crud.py:2575-2590` (`{id, name, recommended_level, image_url, energy_cost}`; schema `NeighborClient` `schemas.py:670`). The endpoint has an optional `character_id` query and optional user (`main.py:1291`, `1301`) — but the crud call does not receive `character_id` today (`main.py:1329`). A closed mark can be viewer-independent («Закрыто: X» / «Закрыто» for secret); a viewer-aware "you may enter" flag needs `character_id` passed down.
- Region map: region details `crud.py` ~`760-790` (`map_items`), admin-only world graph `main.py:2097`.
- Admin details `crud.py:1215-1250` (neighbors without names).

**Dungeon entry (dungeon-service):**
- `POST /dungeons/{id}/sessions` (solo, `main.py:405`) and `POST /dungeons/{id}/party-run` (`main.py:418`) → `gameplay.start_run` (`gameplay.py:1025`).
- Per-entrant check `_check_entrant` (`gameplay.py:989`): location, activity lock, battle/gathering. Leader failing → HTTP error (`gameplay.py:1050-1053`). **Party members failing are SKIPPED, not refused** (`gameplay.py:1062-1077`, `skipped_members` returned). The brief wants the whole group refused if any member fails the faction gate — this is a deliberate deviation from today's skip rule (see Q1).
- Dungeon list at a location: `GET /dungeons/at-location/{location_id}` (`main.py:375`, response `DungeonAtLocationResponse`) — place for a «Закрыто: X» flag; frontend `components/DungeonPage/DungeonEntrance.tsx`, api `api/dungeons.ts:605`.
- `dungeons` table: `models.py:11-50` (no gate columns). Dungeon-service reading faction tables: raw SQL like `_surface_busy`, or an internal character-service endpoint (architect). Secrecy: refusal text for a secret faction must not name it.

**"Eject to nearest open location" building blocks:**
- Forced-move helper: `main._prepare_move` (`main.py:931`) — refuses in battle / dungeon run (409), cancels gathering, expires gates (HTTP to locations). Then `crud.apply_admin_move(..., event_type=..., commit=False)` (`crud.py:4141`), exactly as `law_flows.send_to_jail` (`law_flows.py:70-115`).
- Neighbour lookup: `patrol_crud.neighbours_of` (`patrol_crud.py:93`, both directions stored). BFS for "nearest open" is new code.
- Fallback: region guard station `law_facility.station_location(db, region_id)` (`law_facility.py:62`, `Regions.jail_location_id`) or faction HQ (`factions.hq_location_id`). `reputation_crud.location_region` (`reputation_crud.py:170`).
- Triggers: leave (`faction_crud.leave` `:702`), admin expel (`faction_admin_crud.expel` `:781`), pass auto-expel (`faction_pass.check_member` `:64`), faction hidden/deleted, admin putting a gate on an occupied location, rank change on rejoin. Because `_prepare_move` is async + HTTP and refuses in battle/dungeon, eject needs **post-commit attempt + a retry sweep in `faction_pass.run_pass`** (`faction_pass.py:139`, every 5 min) of "players standing where they may not stand".

### 2. Passive modifiers

- Battle snapshot: `build_participant_info` (`battle-service/app/main.py:331`) takes `attributes` from `GET /attributes/internal/{id}` (`battle_engine.fetch_full_attributes`, `battle_engine.py:39`) — the **stored totals** in `character_attributes` (equipment, perks, food already folded in). Subclass passive = `passive` key from skills-service (`main.py:369-391`).
- Subclass passives (`passives.py`, 2229 lines, `docs/SUBCLASS-PASSIVES.md`) are hard-coded mechanics (hooks H0–H25), **not** a modifier dictionary — not reusable for data-driven faction passives.
- `buffs.aggregate_modifiers` (`buffs.py:498`) aggregates in-battle effect magnitudes and pushes primary → derived (`_DERIVED_PER_POINT`, FEAT-195 caps with `base_attributes`).
- Data-driven passive modifiers already exist as **perks** in character-attributes-service: `perks.bonuses.flat` (`models.py:114-128`), applied as stored deltas via `crud._apply_modifiers_internal` (`crud.py:664`) / `apply_attribute_modifiers`; admin edit re-applies deltas to all holders (`main.py:197-247`), delete reverses (`main.py:251-290`). **`rebuild_derived_stats` (`crud.py:185`) recomputes derived stats from equipment + perks + food only**; primaries/damage/crit damage/vul_* are "already totals" and untouched (`crud.py:194-195`).
- Modifier key dictionary: `VALID_FLAT_BONUS_KEYS` (`character-attributes-service/app/crud.py:449-460`): health/mana/energy/stamina, 7 primaries incl. stealth, damage, dodge, res_effects, 12 res_*, critical_hit_chance, critical_damage, 12 vul_*. Internal apply endpoint `POST /attributes/{id}/apply_modifiers` (`main.py:789`, X-Internal-Token).
- Two implementation options for the Architect:
  - **P-A stored deltas** (like equipment/perks): apply/reverse via apply_modifiers on rank-up / leave / expel / rejoin / admin edit of a rank passive; needs an "applied" ledger per (character, faction) for exact reversal, an outbox for the HTTP calls (pattern `faction_reward_deliveries`), and `rebuild_derived_stats` + `admin/recalculate_all` (`main.py:1144`, `1298`) must add the faction source, otherwise a recalculation silently drops derived faction bonuses. Shows in profile stats; affects stealth used by law detection.
  - **P-B battle-time injection**: battle-service `build_participant_info` fetches `GET /characters/internal/factions/{cid}/passive-modifiers` (soft-fail like the subclass lookup) and folds them into the snapshot attributes (primary → derived via the `_DERIVED_PER_POINT` logic). No drift, instant on membership loss, only in battle (matches «Действуют в бою»), not in profile stats / dungeon stat checks / stealth.
- Frontend reusable editor: `components/Admin/PerksPage/PerkForm.tsx:125-167` `ATTRIBUTE_BONUS_OPTIONS` (grouped key→label list, not exported — extract to a shared module); labels `ProfilePage/constants.ts:113` `STAT_LABELS`; player display examples `ProfilePage/PerksTab/PerkDetailModal.tsx`.

### 3. Battle end rewards / kill hooks

- Single ending: `_finalize_battle` (`battle-service/app/main.py:2531`), used by killing blow (`main.py:4513/4525`) and timeout sweeper (`main.py:6781`). Winner = `winner_team` (last team alive).
- PvE rewards: `_distribute_pve_rewards` (`main.py:471`) — defeated = `hp<=0 and team != winner_team`; mob detection via `GET /characters/internal/mob-reward-data/{cid}`; **winners = alive members of the winning team only** (`main.py:502`). Bestiary `POST /characters/internal/record-mob-kill` (`main.py:601` → char `main.py:4151` → `crud.record_mob_kill` `crud.py:2768`, idempotent only per (character, template) — not per battle, unusable as a key).
- NPC kills: `main.py:2711-2759` → `PUT /characters/internal/npc-status/{id}` with `killer_character_ids` = **all** winning-team characters, alive or fallen (`main.py:2715-2719`) → char `main.py:4075` → `shadow_crud.npc_kill_consequences` (FEAT-197/199 reputation + crime, keyed by battle_id).
- Mob template resolution in battle-service already exists: `active_mobs JOIN mob_templates` (`main.py:730-743`). NPCs have no template — an "NPC enemy" is a concrete `characters.id` (`is_npc=1`, `npc_role != 'mob'`).
- Battle types: `pve`, `pvp_training`, `pvp_death`, `pvp_attack` (`models.py:20-24`); guard fights are `pvp_attack` tagged with `law_encounter_id` (`main.py:1676`). PvP has no reputation/crime hook today (`law_core.CRIME_PVP_ATTACK` defined, unused).
- Best hook: a new fire-and-forget callback after `_notify_law_battle_end` (`main.py:2763`), pattern `_post_law_callback` (`main.py:1769`, 3 retries): `POST /characters/internal/factions/battle-result {battle_id, battle_type, winner_team, participants:[{character_id, team, alive}], defeated:[{character_id, mob_template_id|null}]}`; character-service keys everything by `battle_id` in `faction_log.event_key` (e.g. `faction:kill:b<battle>:c<cid>`), applies `change_points` + hostile penalty exactly like `donate` (`faction_econ_crud.py:493-509`) / `quest_completed` (`faction_crud.py:740`), `recheck_ranks`, dispatch post-commit. Daily kill cap: add a column to `faction_donation_days` or a sibling day table; 24 h per-opponent rule: a small `(character, faction, victim)` table or a `faction_log` lookup by event_key prefix.
- «+N очков фракции в результатах»: the battle result payload (`BattleRewards`, `main.py:623`, WS `battle_finished` `main.py:2856`) is built before/independently of character-service; showing faction points there needs a synchronous call — otherwise journal + notification only (Q4).

### 4. Law / crime

- Crime record: `law_crud.record_crime` (`law_crud.py:377`) / `register_crime` (`law_crud.py:440`): `crime_type` VARCHAR(30) (`models.py:1297`), idempotent per `event_key` (UNIQUE), skips NPCs, **always adds hidden infamy** (`law_crud.py:413-415`), `floor` param lifts wanted to at least a level threshold (`law_core.add_wanted` `law_core.py:310`). Severity scale = `law_levels` (suspect/offender/criminal/villain/enemy with `min_value`, `law_core.py:201-207`) → "severity" for an outlaw faction maps naturally to a level code → `floor = level.min_value` (+ optional points).
- Crime types live as constants `law_core.py:33-39`; frontend labels `components/Admin/ReputationPage/shadowLabels.ts:6-7`.
- Guard check on entry (FEAT-198/203): `law_crud._check` (`law_crud.py:594`): exits if no region / no live guards / flee cooldown; then `wanted <= 0 and not outlaw → no encounter` (`law_crud.py:619`); detection roll `detection_chance_for` (`law_crud.py:519`: marker base × guards × stealth reduction × fame/mask × level %) → slip (`law_crud.py:631-638`) or encounter. Called from `update_location` (`main.py:2407`), teleport (`crud.py:3913`) and patrols (`check_patrol_arrival` `law_crud.py:544`).
- **Plug-in point for membership:** inside `_check`, before the `wanted <= 0` exit: if the character is an active member of a faction outlawed in `region_id`, and no membership crime in this region within the cooldown → `register_crime(crime_type='faction_membership', floor=…, event_key='law:faction:c<cid>:f<fid>:r<region>:<period>')`, then re-read wanted and continue to the normal roll/encounter. For a **secret** faction the crime is recorded only on a successful detection roll (same `lc.roll_succeeds`), and must not leak the faction into public texts.
- Patrol prefilter: `patrol_crud._sweep_candidates` (`patrol_crud.py:193`) adds `_SQL_SUSPECTS` (`patrol_crud.py:187-190`: wanted > 0 OR negative reputation) — must get a third `OR EXISTS (faction_members m JOIN faction_outlaw_regions o … status='active' AND o.region_id=:r)` branch, otherwise patrols never check outlawed members with zero wanted.
- Country prison (FEAT-202): `law_facility.resolve_jail` (`law_facility.py`), threshold `country_prison_min_level` — works unchanged once wanted is raised.
- Dedupe/cooldown precedents: `event_key` UNIQUE on `law_crimes`/`law_log`; flee cooldown via `law_encounters.cooldown_until` (`law_crud.py:501`); period key strings (e.g. `t%Y%m%d…` in `knock_out_guard`, `law_crud.py:476`).

### 5. Item donations

- Stage-2 donation: `faction_econ_crud.donate` (`faction_econ_crud.py:454`): owner, active member, day row, points via `fe.donation_points` (marks counter → points, daily cap), hostile penalty, `recheck_ranks`, then the ledger op `faction_donation character → faction` LAST (`faction_econ_crud.py:516-525`). Route `faction_api.py:608`; dialog `ProfilePage/FactionsTab/DonateFactionDialog.tsx`.
- **Strong precedent for taking items from the bag:** FEAT-193 guild hand-in `economy_guild_crud.hand_in` (`economy_guild_crud.py:617`) and the mint: `economy_mint_crud.take_plain_stacks` (`economy_mint_crud.py:533`) — direct `character_inventory` writes in the same transaction, only plain stacks (no enhancement/gems/durability), rows locked asc id. Equipped items live in `equipment_slots`, so they are excluded automatically.
- Exclusions available: quest items `economy_guild_crud.quest_item_ids` (`:446`, `quest_objectives` collect/deliver); off-market via `econ_core.effective_item_group` (`econ_core.py:815`: scroll/recipe/legendary+ or admin override / no group → off-market = "без цены"). **There is no "bound" flag on items** (`inventory-service/app/models.py` — only `is_unique`); "привязанное" = quest/off-market/non-plain unless the Architect defines more.
- Pricing in the HQ region: `region_quotes` (`economy_guild_crud.py:335`, best merchant bid / cheapest ask), `econ_core.item_base_price` (`:836`), `market_mult` / `market_ask` / `market_bid` / `wholesale_price` (`econ_core.py:845-885`), `units_per_item` (`:995`). Requires a **participating HQ region**; factions without HQ / with a non-simulated HQ get no item price (Q6).
- Ledger invariant: an item donation moves no money at donation time (no ledger op; idempotency needs its own UNIQUE key, e.g. a `faction_item_donations` row). Selling the stock later = the mirror of the stage-2 restock: in `faction_step` (`faction_econ_crud.py:659`) a `purse(hq) → faction` leg inside the same `faction_tick` op + region goods stock `+= units` (precedent: merchants "residents buy", `econ_merchant.py:11-20`, `merchant_legs` `:190`), capped by the regional purse budget (`econ_purse_share_pct`). Reusing `OP_FACTION_TICK` needs **no econ_core change** (no ×4 copy edit, `scripts/check_econ_copies.sh` untouched). Alternative: donated items feed `faction_qm_items.stock` of the quartermaster (no sale, no ledger).
- Global lock order (FEAT-206 §3.6): `… faction_donation_days → faction_qm_purchases → character_inventory → characters → econ_accounts …` — an item donation fits (members → day row → inventory; no accounts).

### 6. Frontend touch points
- Admin faction editor: `components/Admin/FactionsPage/FactionEditor.tsx` (351), `RanksEditor.tsx`, `RankFormModal.tsx` (286 — add passive block), `FactionSettingsTab.tsx` (kill cap / outlaw cooldown), `HostilitiesTab.tsx`; reuse `adminShared.tsx`.
- Location editor: `components/AdminLocationsPage/EditForms/EditLocationForm/EditLocationForm.tsx` (526) — check whether it is already TS/Tailwind before touching (CLAUDE.md §10.8–10.9).
- Dungeon editor: `components/Admin/DungeonsPage/AdminDungeonForm.tsx` (530).
- Neighbours: `components/pages/LocationPage/NeighborsSection.tsx` (already has `enabledIds` dimming for prison, FEAT-202) + `LocationPage.tsx:813`; types `pages/LocationPage/types.ts`; teleport `TeleportMenu.tsx`; region map `components/WorldPage/RegionInteractiveMap/RegionInteractiveMap.tsx`; dungeon list `components/DungeonPage/DungeonEntrance.tsx`.
- Player: `components/ProfilePage/FactionsTab/FactionsTab.tsx`, `FactionMembershipCard.tsx` (passives, outlaw warning), `DonateFactionDialog.tsx` (items), catalog `components/pages/FactionsPage/FactionCard.tsx` (ranks → passives, outlaw regions); api `src/api/factions.ts`.

### 7. Migrations / permissions
- character-service: last `046_faction_economy.py` → next **`047_*`** (revision id ≤ 32 chars).
- locations-service: last `058_quest_faction_vouchers.py` → next **`059_*`** (`Locations.faction_id`, `faction_min_rank_id`, no cross-service FK — quests pattern).
- dungeon-service: last `009_session_battle_state.py` → next **`010_*`** (`version_table=alembic_version_dungeon`).
- battle-service: last `009_battle_law_encounter.py` → `010_*` only if a column is needed (callback approach needs none).
- character-attributes-service: last `009_add_stealth.py` (only if P-A needs a table).
- user-service: last `0035_faction_economy_perm.py` → `0036_*` only if a new permission is introduced. Existing `factions:edit` / `factions:settings` (0034) can cover enemies/outlaw/limits/passives; location gate uses `locations:update`, dungeon gate `dungeons:edit` (`dungeon-service/app/main.py:64`). If any new permission is added → explicit seed section in `test_rbac_permissions.py` (CLAUDE.md §10.13).

### Cross-Service Dependencies (new / changed)
- locations-service → shared DB faction tables (`faction_read`, existing) for the move pre-check and closed marks.
- character-service `update_location` / `execute_teleport` → own faction tables (authoritative gate).
- dungeon-service → faction tables (raw SQL) or character-service internal endpoint (new).
- battle-service → `POST /characters/internal/factions/battle-result` (new, internal token).
- character-service → locations-service `notify_character_left_location` / `cancel_gathering` (existing, via `_prepare_move`) for eject.
- P-A only: character-service → `POST /attributes/{id}/apply_modifiers` (existing) and attributes-service → faction tables (raw) in `rebuild_derived_stats`. P-B only: battle-service → new `GET /characters/internal/factions/{cid}/passive-modifiers`.

### Risks
1. **Orphan post on refused move** (`ISSUES.md:852`): gate must run in locations-service before `create_post`, plus the authoritative check in `update_location`.
2. **Eject cannot run in battle / dungeon** (`_prepare_move` 409s) → must be a retried sweep; until it runs the player stands in a closed location (acceptable, document).
3. **P-A drift**: stored deltas + `rebuild_derived_stats` forgetting the faction source = silent loss of bonuses on recalculation; rank/passive admin edits must re-apply to holders (perk pattern). P-B avoids it but passives are invisible outside battle.
4. **Secrecy leaks**: closed marks, dungeon refusal text for a party member, kill-point journal ("за победу над участником «X»"), crime texts/notifications and law logs must never name a secret faction to others; a secret member's membership crime must not appear in public profiles (crime list is owner/staff only today — verify).
5. **Infamy side effect**: every `record_crime` adds hidden infamy (`law_crud.py:413`) — a daily membership crime slowly raises infamy (may affect fame/infamy-gated faction conditions).
6. **Patrol prefilter** must be extended or outlawed members with zero wanted are never checked by patrols.
7. **PvP farming**: `pvp_training` duels between friends could farm points (daily cap mitigates); PvE winners exclude fallen allies today but NPC kill reputation includes them — pick one rule.
8. **Hidden faction (`is_active=0`)**: FEAT-205 decided members keep working; the brief says a closed location opens — consistent only if "deactivated" = hidden; delete is blocked once a faction had members.
9. **Item pricing** needs a simulated HQ region; tick sale must respect the purse cap or donated stock accumulates (needs an admin view).
10. Uncommitted base: everything builds on FEAT-205/206 working copy; FEAT-206 tick lock order must be extended consistently (`econ_tick.py` docstring).

### Open Questions (for PM → user; non-technical)
- **Q1.** Party at a faction dungeon with one non-member: refuse the whole group (brief) or keep today's rule «вход без него» (the member is skipped and the rest enter)?
- **Q2.** Do training duels (`pvp_training`) count as PvP kills for faction points, or only real fights (`pvp_death`, attacks)?
- **Q3.** Do fallen allies of the winning side get kill points (they "participated"), or only survivors (like mob XP today)?
- **Q4.** Is «+N очков фракции» in the faction journal + notification enough, or must it appear in the battle result window too (more work)?
- **Q5.** Eject target: nearest open neighbour, else the faction HQ, else the region guard station — OK?
- **Q6.** Factions whose HQ is in a region without the market simulation: item donations disabled («у фракции нет рынка») — OK?
- **Q7.** Should the faction passive also show in profile stats / work outside battle (e.g. +stealth helps against guards), or battle-only? (decides P-A vs P-B)
- **Q8.** Membership offense: is the crime recorded only when guards are present and notice the character (stealth roll for open members too), or automatically on entering the region for open members?

## 3. Architecture Decision (filled by Architect — in English)

Builds on `DONE-FEAT-205` §3 («205 §3.x») and `DONE-FEAT-206` §3 («206 §3.x»), both uncommitted in the working copy.
Nothing there is redesigned. User answers Q1–Q8 (§2) are final and applied below.

### 3.0 Open questions for PM

No blocking questions. Architect defaults (product-visible, each a setting or one-line change):

1. **Access rules live in ONE character-service table** (`faction_access_rules`), not in columns of `Locations` /
   `dungeons`. ⇒ **no locations 059, no dungeon 010, no user 0036** migration. Reasons: one rule implementation and
   one admin API, `ON DELETE CASCADE` from `factions` (a deleted faction cannot leave a location closed forever), rank
   FK protection, the faction editor can list all territories of a faction. The location / dungeon editors still get
   the field (they call the faction admin API).
2. **Hidden faction (`is_active = 0`) ⇒ its territories open for everyone** (PM variant). Secret ≠ hidden.
3. **Passives = cumulative**: all ranks of the ladder up to and including the current one (PM variant).
4. **Passive keys = battle keys only**: 5 battle primaries (strength, agility, intelligence, endurance, luck), damage,
   dodge, res_effects, 12 `res_*`, critical_hit_chance, critical_damage, 12 `vul_*`. No health/mana/energy/stamina
   (would be a free heal every battle start), no charisma/stealth (do nothing in battle; Q7 = battle-only).
5. **Kill-point daily cap is separate from the donation cap** (own counter, default 50 per faction per character per
   UTC day, global setting + optional per-faction override). Item donations share the 206 donation cap (§1.5).
6. **Membership crime**: points 0 + wanted *floor* = `min_value` of the chosen severity level (e.g. «Преступник» →
   wanted ≥ 300). Like every crime it adds the minimum hidden infamy (`law_crud.record_crime`, `shadow_core.infamy_gain`
   min gain) — accepted, documented.
7. **Item donations enabled only when the faction's economy actually ticks** (206 `not_ticking_reason(...) is None`:
   template set, HQ in a participating region, economy on, faction not hidden) — otherwise «Фракция сейчас не
   принимает предметы: <reason>». This is the concrete form of Q6 (only a ticking faction can sell the items on).
8. **Eject is not done for**: admin teleport, jail / flee-back, home teleport scroll, dungeon knockout return —
   these may land a player in a closed location; the 5-min sweep ejects him afterwards (documented).
9. **Membership crime text never names the faction** (crime label «Членство в запрещённой фракции»), for open and
   secret factions alike — simpler and leak-proof.

### 3.1 Overview and ownership

| Concern | Owner | Notes |
|---|---|---|
| Access rules (locations + dungeons), authoritative move gate, teleport gate, eject + sweep, enemies + kill points, outlaw regions + membership crime, rank passives, item donations + faction item stock + tick sale | **character-service** (sync, migration `047_faction_territory`) | new modules `faction_territory.py` (access rules, gate, eject), `faction_kills.py` (battle-result → points), `faction_items.py` (item donations + stock); `faction_core.py` (pure: access decision, passive validation/sum, kill-point maths), `faction_econ.py` (pure: sale planning), `faction_econ_crud.py` / `econ_tick` (sale in the step), `law_crud._check` + `patrol_crud` (crime hook), `faction_pass.py` (eject sweep) |
| Move pre-check (before the post is committed), viewer-aware neighbour marks, region-map marks | **locations-service** (async, no migration) | `faction_read.py` extended (raw parameterised SQL, tolerant) |
| Dungeon entry check (whole party), list marks | **dungeon-service** (async, no migration) | calls new character-service internal endpoints via `http_clients.py` |
| Passive injection at battle start, battle-result callback | **battle-service** (no migration) | `build_participant_info`, new `_notify_faction_battle_end` after `_notify_law_battle_end` |
| Permissions | **none new** | `factions:read` / `factions:edit` / `factions:settings` (0034) cover everything |
| `econ_core.py` ×4 | **unchanged** | item sales are legs of the existing `faction_tick` op (`purse(hq) → faction`); `scripts/check_econ_copies.sh` untouched |
| inventory-service, party-service, user-service | no change | items leave the bag by direct `character_inventory` writes (guild / mint precedent) |

No Nginx / Docker / env changes (new paths under `/characters/`, `/locations/`, `/dungeons/`; internal ones under
`/characters/internal/` are already 403 at the gateway).

### 3.2 Data model — character-service migration `047_faction_territory`

Revision id `047_faction_territory` (≤ 32 chars). No MySQL ENUMs; explicit indexes on FK columns; FKs to
`characters` / `factions` `ON DELETE CASCADE`; cross-service ids (`Locations`, `dungeons`, `Regions`, `items`,
`mob_templates`) validated by raw SELECT, no FK. Downgrade drops the new tables/columns in reverse order (pre-beta data
loss acceptable).

```sql
CREATE TABLE faction_access_rules (          -- §1.1 closed locations / dungeons (one faction per target)
  id INT PK AUTO_INCREMENT,
  kind VARCHAR(10) NOT NULL,                  -- location | dungeon
  target_id BIGINT NOT NULL,                  -- Locations.id | dungeons.id (validated exists)
  faction_id INT NOT NULL FK→factions ON DELETE CASCADE,             -- INDEX
  min_rank_id INT NULL FK→faction_ranks ON DELETE RESTRICT,          -- INDEX; must belong to faction_id
  created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
  UNIQUE (kind, target_id)
);

ALTER TABLE faction_ranks                     -- §1.2 passive of a rank
  ADD passive_name VARCHAR(100) NULL,
  ADD passive_description VARCHAR(500) NULL,
  ADD passive_modifiers JSON NULL;            -- {key: int}, keys ⊂ FACTION_PASSIVE_KEYS (§3.0 #4), 1..10 keys,
                                              -- values -100..100, != 0; NULL/{} = no passive

CREATE TABLE faction_enemies (               -- §1.3
  id INT PK, faction_id INT NOT NULL FK CASCADE,
  kind VARCHAR(10) NOT NULL,                  -- mob (ref = mob_templates.id) | npc (ref = characters.id, is_npc=1,
                                              -- npc_role != 'mob') | hostile (ref = 0: open members of hostile factions)
  ref_id BIGINT NOT NULL DEFAULT 0,
  points INT NOT NULL,                        -- 1..10000
  UNIQUE (faction_id, kind, ref_id)
);
ALTER TABLE factions ADD kill_points_daily_cap INT NULL;      -- NULL = global setting; 0..100000

ALTER TABLE faction_donation_days ADD kill_points INT NOT NULL DEFAULT 0;   -- kill-point day counter (own cap)

CREATE TABLE faction_pvp_kills (             -- 24 h per-opponent rule
  character_id INT NOT NULL FK→characters CASCADE,
  faction_id INT NOT NULL FK→factions CASCADE,                       -- INDEX
  victim_id INT NOT NULL FK→characters CASCADE,                      -- INDEX
  last_at DATETIME NOT NULL,
  PRIMARY KEY (character_id, faction_id, victim_id)
);

CREATE TABLE faction_outlaw_regions (        -- §1.4
  id INT PK, faction_id INT NOT NULL FK CASCADE,
  region_id BIGINT NOT NULL,                  -- Regions.id (validated), INDEX
  level_code VARCHAR(16) NOT NULL,            -- law level code (law_levels / law_core.LEVEL_CODES)
  UNIQUE (faction_id, region_id)
);

CREATE TABLE faction_item_stock (            -- §1.5 donated items waiting for the tick sale
  faction_id INT NOT NULL FK CASCADE, item_id INT NOT NULL, quantity INT NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (faction_id, item_id)
);

ALTER TABLE faction_settings
  ADD kill_points_daily_cap INT NOT NULL DEFAULT 50,          -- 0..100000 (0 = kills give no points)
  ADD pvp_kill_repeat_hours INT NOT NULL DEFAULT 24,          -- 0..720
  ADD outlaw_check_cooldown_hours INT NOT NULL DEFAULT 24,    -- 1..720 (per character per region)
  ADD econ_item_sale_share_pct INT NOT NULL DEFAULT 2;        -- 0..20 (% of the HQ purse per tick, all factions)

ALTER TABLE faction_economy ADD last_item_sales BIGINT NOT NULL DEFAULT 0;
ALTER TABLE faction_econ_history ADD item_sales BIGINT NOT NULL DEFAULT 0, ADD items_sold INT NOT NULL DEFAULT 0;
```

Guards added to existing admin deletes: rank delete → 409 «Звание используется как условие доступа к территории»
(RESTRICT FK, checked explicitly first). Faction delete: rules / enemies / outlaw rows cascade; `faction_item_stock`
with quantity > 0 → 409 «На складе фракции остались предметы» (pattern of the treasury guard). `law_crimes.crime_type`
is VARCHAR(30) — new value `faction_membership` needs no migration.

### 3.3 Pure rules (`faction_core.py`, `faction_econ.py`, no DB)

**Access decision** `access_decision(rule, faction{name, is_secret, is_active}, membership{rank_sort}|None,
min_rank{name, sort_order}|None) -> (allowed: bool, label: str|None)`:

| case | allowed | label (player-facing) |
|---|---|---|
| no rule, or faction hidden (`is_active=0`) / missing | True | None |
| active member, rank ok (no min rank, or held `sort_order` ≥ min) | True | «Территория фракции «X»» |
| public faction, not a member | False | «Закрыто: X» (location) / error «Только для членов фракции «X»» |
| public faction, member below rank | False | «Закрыто: нужно звание «Y» во фракции «X»» |
| secret faction, not a member | False | «Закрыто» — faction never named |
| secret faction, member below rank | False | «Закрыто: нужно звание «Y» во фракции «X»» (he is a member — he may know) |
| viewer unknown (public map) | null | public: «Закрыто: X»; secret: «Закрыто» |

Move refusal texts: «Вход только для членов фракции «X»», «Нужно звание «Y» во фракции «X»», secret non-member
«Сюда вас не пускают». The same function is the source of truth; locations-service `faction_read` re-implements it
(async) and QA asserts parity with a shared case table.

**Passives**: `FACTION_PASSIVE_KEYS` (§3.0 #4); `validate_passive(name, description, modifiers)` (422 Russian:
unknown key, value out of range/0, > 10 keys, name required when modifiers set); `active_passives(ladder, held_rank)`
→ ranks with `sort_order ≤ held.sort_order` and non-empty modifiers; `sum_modifiers([...])` → `{key: int}`.

**Kill points** `kill_gain(enemy_points: list[int], cap, today_before) -> (gain, today_after)`: `raw = sum`,
`gain = max(0, min(raw, cap − today_before))`. Hostile penalty = existing `hostile_penalty(gain, pct)`.

**Tick sale** (in `plan_faction_step`, new optional inputs `sale_rows: [SaleRowIn(item_id, group, quantity,
item_price)]`, `budgets.sales`): processed **with the income (step 1)**, before wages, so the money can pay wages.
Per row ascending item_id: `price = econ_core.wholesale_price(item_price, group.price_mult, wholesale_share)`,
`units = econ_core.units_per_item(item_base, group_base)` (row skipped if price or units = 0);
`n = min(quantity, sale_budget_left // price, purse_left // price)`; income `n × price`; `stock_delta[group] += n ×
units`; `sale[item_id] = n`. One leg `purse(hq) → faction` (amount = total sales, `LEG_MAIN`). New plan fields
`item_sales`, `items_sold`, `sale`. Existing callers pass nothing → identical results (regression test).

### 3.4 Part 1 — closed locations / dungeons

**Authoritative gate (character-service, `faction_territory.location_refusal(db, character, location_id) ->
str|None`)** — one indexed SELECT on `faction_access_rules (kind='location', target_id)`; if a rule exists, reads
faction + membership + ranks. NPCs → always None (patrols never pass here anyway).
- `PUT /characters/internal/{id}/update_location` (`main.py:2358`): after the lock checks (`main.py:2392-2396`), when
  `moving` → refusal → `db.rollback()`, **409** with the text (locations-service passes 409 detail through,
  `main.py:320-328`). Prison moves are not special-cased.
- `crud.execute_teleport` (`crud.py:3799`): before any charge → 403 with the text. `crud.teleport_lock_reasons`
  (`crud.py:3774`): option whose target location is refused gets `locked_reason` (only if not already locked).
- `apply_admin_move` / jail / flee-back / home scroll / dungeon return: **no gate** (§3.0 #8).

**Pre-check (locations-service)** in `move_and_post` and `quick_move` **before `crud.create_post`** (after the
neighbour check): `faction_read.location_access(session, character_id, dest)` → refused → **403** with the same text.
A read error → no pre-check (authoritative check still runs; known orphan-post debt `ISSUES.md:852` unchanged).

**Neighbour / map marks (locations-service)**:
- `GET /locations/{id}/client/details?character_id=`: neighbours gain `access_label: str|null`,
  `access_allowed: bool|null`. Viewer-aware only when `current_user` owns `character_id` (raw `SELECT user_id FROM
  characters`); otherwise public labels and `access_allowed = null`. `crud.get_client_location_details` gets an
  optional `viewer_character_id`. One batched read of rules for all neighbour ids; none → nothing else read.
- Region details `map_items` of type location: `access_label` (public form only, no viewer).
- Faction tables unreadable → no marks (logged warning).

**Dungeons (dungeon-service → character-service internal)**:
- `gameplay.start_run` (`gameplay.py:1025`): after the party is assembled (leader + non-skipped members — existing
  skip rules for other checks unchanged), call `POST /characters/internal/factions/access/check` with all
  `member_ids`. `allowed = false` → **403** with `detail` (whole party refused). HTTP failure → **503**
  «Не удалось проверить доступ к подземелью — попробуйте позже» (fail closed). Messages (built by character-service):
  solo/leader public «Подземелье только для членов фракции «X»» / «Нужно звание «Y» во фракции «X»»; party public
  «Подземелье только для членов фракции «X» — не проходят: Имя1, Имя2» (rank variant analogous); secret faction
  (any failing member) «Подземелье закрыто — войти могут не все участники отряда» (solo: «Подземелье закрыто»).
  A running session is never touched (§1.1).
- `GET /dungeons/at-location/{location_id}?character_id=` (optional): one call to
  `POST /characters/internal/factions/access/labels` → `DungeonAtLocationResponse` gains `access_label`,
  `access_allowed` (viewer-aware only if character-service confirms `characters.user_id == user.id`). Failure → fields
  null.

**Eject** (`faction_territory`):
- `players_in_closed(db, location_id=None, limit=200)`: `characters (is_npc=0) JOIN faction_access_rules
  (kind='location', target_id = current_location_id) JOIN factions (is_active=1)`, then `location_refusal` in Python.
- `pick_target(db, character, location_id, rule)`: (1) neighbours (`patrol_crud.neighbours_of`, ascending id) that
  are not refused for him; (2) the rule faction's `hq_location_id` if ≠ current and not refused; (3)
  `law_facility.station_location(region)`; none → skip (warning log, retried next pass).
- `async eject(db, character_id) -> notices`: skip if in battle / dungeon run / jail / law encounter (activity lock
  or `_prepare_move` 409 → retried by the pass); `db.rollback()` → `_main()._prepare_move(db, cid, from, "faction")`
  → re-lock + re-check refusal (still refused, still there) → `crud.apply_admin_move(..., event_type="faction_eject",
  description=«Выдворен с закрытой территории: «A» → «B»», commit=False)` → `faction_log` event `ejected`
  (`event_key faction:eject:c<cid>:l<loc>:<YYYYmmddHHMMSS>`) in the rule faction → commit → notice (owner)
  «Вас выдворили из «A» в «B»: это территория фракции «X»» (secret non-member: «…: это закрытая территория»).
  Pattern = `law_flows.send_to_jail` (`law_flows.py:70-115`).
- Triggers: `faction_pass.run_pass` new step 3 «eject sweep» (`asyncio.run(eject(...))` per character, own session,
  like `law_pass.py:68`); post-commit best effort after player `leave` and admin `expel` routes (awaited in the
  async route, errors only logged); post-commit after an admin rule PUT on a location (sweep limited to that target).

### 3.5 Part 2 — rank passives (battle-time injection, Q7)

- character-service `GET /characters/internal/factions/{character_id}/passive-modifiers` (internal token) →
  `{"modifiers": {key: int}}` — sum over all ACTIVE memberships (hidden factions included, 205 §3.0 #6) of
  `active_passives`. Unknown / NPC character → `{"modifiers": {}}`.
- battle-service `build_participant_info` (`main.py:331`): only when `is_npc` is false (after the subclass lookup),
  `fetch_faction_passives(char_id)` (timeout 3 s, soft-fail = no passives, `logger.warning`), then
  `faction_passives.apply(attr, modifiers)` (new small module): every key `attr[k] = (attr.get(k) or 0) + v`; for the
  5 primaries additionally the derived stats via `buffs._DERIVED_PER_POINT` with `stat_caps.effective_delta(base,
  base + v)` (FEAT-195 caps; mirrors attributes-service) — the snapshot therefore carries the passive for the whole
  battle (like initiative, fixed at start). No writes to `character_attributes`, no recalc risk.
- Display: private faction view + catalog/public ranks (§3.9). Not in profile stats.

### 3.6 Part 3 — kill points

**battle-service** `_notify_faction_battle_end(db, battle_id, battle_state, winner_team)` called right after
`_notify_law_battle_end` (`main.py:2763`) when `winner_team is not None`; fire-and-forget `asyncio.create_task`
with the `_post_law_callback` retry pattern (`main.py:1769`, 3 tries). Payload:
`{battle_id, battle_type, winner_team, participants: [{character_id, team, alive: hp>0, mob_template_id|null}]}`;
`mob_template_id` resolved for losing participants with one `active_mobs JOIN mob_templates` query (pattern
`main.py:730-743`). Sent for every finished battle with a winner (cheap; character-service decides). No
battle-result window change (Q4).

**character-service** `POST /characters/internal/factions/battle-result` → `faction_kills.apply_battle(db, payload)`:
1. winners = non-NPC participants of `winner_team` (alive **and fallen**, Q3); losers = the rest. No winner with an
   active membership (one SELECT) → `{applied: []}`.
2. Enemy points per defeated loser `d`, per winner faction A (A's `faction_enemies`):
   - mob: `d.mob_template_id` ∈ A's `mob` rows (NPC-ness re-checked in DB);
   - npc: `d` is NPC with `npc_role != 'mob'` ∈ A's `npc` rows;
   - hostile: `battle_type ∈ {pvp_death, pvp_attack}` (**not** `pvp_training`, Q2) and `d` is a non-NPC **active
     member of a NON-secret faction B** with a hostility pair (A,B) (secret members never count) and A has a `hostile`
     row; plus the 24 h rule (`faction_pvp_kills` last_at older than `pvp_kill_repeat_hours`, else 0 for `d`). One
     victim counts once per A even if he is in several hostile factions.
3. Per winner **one transaction** (lock order §3.10): `faction_members` of the winner (A's + hostile ones, asc id,
   `_lock_members` of 206) → `faction_donation_days(cid, A, day)` (ensured beforehand, `ensure_day_row`) →
   `faction_pvp_kills` upserts → `kill_gain` with cap `factions.kill_points_daily_cap ?? settings.kill_points_daily_cap`
   → `change_points(EV_KILL)` with `event_key = faction:kill:b<battle_id>:c<cid>` (UNIQUE(event_key, faction_id) =
   idempotent; duplicate → skip that faction) → hostile penalty exactly like `donate` (key `…:hostile:<A>`) →
   `recheck_ranks` → commit. gain 0 (cap) → journal row with 0 + text «лимит на сегодня исчерпан», no notice.
4. Post-commit: notices (owner) «Победа над врагами фракции «X»: +N очков» (secret faction X — owner is a member,
   naming is fine; victims are never named), `deliver_pending` (rank rewards) — via `faction_hooks.dispatch_result`.
Journal text (`EV_KILL = "kill"`): «Победа над врагами фракции: +N очков». Response `{applied: [{character_id,
faction_id, points_delta}], duplicate: bool}`.

### 3.7 Part 4 — membership as a crime (Q8)

**Hook in `law_crud._check`** (`law_crud.py:594`), after the flee-cooldown exit (`:614`) and before the
`wanted <= 0` exit (`:619`):
```
fm = faction_territory.outlaw_membership(db, cid, region_id)   # None | (level_code, open: bool)
#   = the character's ACTIVE memberships of factions with a faction_outlaw_regions row for region_id;
#     an open (non-secret) one wins over secret ones; among them the most severe level (law level order)
if fm and membership_crime_recent(db, cid, region_id, now, cooldown_h): fm = None
#   SELECT 1 FROM law_crimes WHERE character_id AND region_id AND crime_type='faction_membership'
#   AND created_at > now - outlaw_check_cooldown_hours
if wanted <= 0 and not outlaw and fm is None: return _NO_ENTRY
level = level_for(wanted); outlaw floor as today; if fm: level = level_at_least(level, fm.level_code, levels)
detection: if fm and fm.open -> detected without a roll (recognised automatically)
           else existing roll (secret members: the FEAT-201 stealth roll, Q8); slip -> unchanged slip path, no crime
if fm: register_crime(crime_type=CRIME_FACTION_MEMBERSHIP, points=0, floor=<level fm>.min_value,
                      event_key=f"law:fmember:{cid}:{region_id}:{now:%Y%m%d%H%M%S%f}", location_id, now,
                      settings, levels) -> re-read wanted, recompute level -> encounter as today
```
- `CRIME_FACTION_MEMBERSHIP = "faction_membership"` in `law_core.py`; frontend label «Членство в запрещённой
  фракции». Crime rows / law logs / encounter texts never carry the faction id or name. Once the cooldown blocks a new
  crime, the character is handled purely by his (raised) wanted — no fine spam per step.
- Works for entry (`update_location`), teleport (`crud.py:3913`) and patrols (`check_patrol_arrival`) since all use
  `_check`. Country prison (FEAT-202) works unchanged via the raised wanted.
- **Patrol prefilter** `patrol_crud._SQL_SUSPECTS` (`patrol_crud.py:187`): third branch
  `OR EXISTS (SELECT 1 FROM faction_members m JOIN faction_outlaw_regions o ON o.faction_id = m.faction_id
  WHERE m.character_id = c.id AND m.status = 'active' AND o.region_id = :r)`.
- Warnings for the player: private view + catalog list the outlaw regions (§3.9).

### 3.8 Part 5 — item donations

**Eligibility** (`faction_items.py`): active member (404 «Вы не состоите в этой фракции»); faction ticks (§3.0 #7,
else 409 «Фракция сейчас не принимает предметы: <reason>»); per item: plain stacks only (no enhancement/gems/
durability — `take_plain_stacks` rule, `economy_mint_crud.py:533`), not a quest item
(`economy_guild_crud.quest_item_ids`), on-market with a group (`effective_item_group`), group present in the HQ
region (`econ_region_goods` row) and `wholesale_price > 0`; else 400 «Предмет «N» нельзя пожертвовать: <причина>»
(причины: «квестовый предмет», «не продаётся на рынке края штаба», «улучшенный или повреждённый предмет»).
Equipped items are not in `character_inventory` → excluded automatically.

**Value** = `wholesale_price` in the HQ region at donation time × quantity (the same price the tick will receive) →
marks-equivalent added to the 206 donation day row (`marks`, `points` via `fe.donation_points`, same 10:1 rate and
same daily cap 50 — §1.5).

**Flow** `donate_items(db, cid, fid, items[], request_id)` — one transaction, router `_write` commits:
`event_key = faction:donate_items:c<cid>:<request_id>` pre-check in `faction_log` → 409 «Это пожертвование уже
выполнено» (race → IntegrityError → 409 by `_write`); `ensure_day_row` + `ensure_stock_rows` (own short transactions
first) → `_lock_members` (faction + hostile, asc id) → `faction_item_stock` rows (asc item_id) FOR UPDATE →
`faction_donation_days` FOR UPDATE → `take_plain_stacks` per item (asc item_id; not enough → 400 «Недостаточно
предметов «N»») → stock `quantity += n` → points + hostile penalty (as `donate`) → log `EV_DONATION` with the event_key
(text «Пожертвование предметов (N шт.) на M марок: +P очков») → `recheck_ranks`. **No ledger op** at donation time
(no money moves), world sum unchanged. Post-commit: notices, `deliver_pending`.

**Tick sale** (`faction_econ_crud.plan_pass` + `faction_step`): `plan_pass` computes `sales` wants (stock value) and
splits `floor(purse × econ_item_sale_share_pct %)` of the HQ region between its factions (`fe.split_cap`) →
`Budgets.sales` (new field, default 0). `faction_step`: sale groups added to `wanted_groups` (goods rows locked in the
same ascending pass) → after `faction_qm_items`, lock `faction_item_stock` rows (quantity > 0, asc item_id) → planner
§3.3 → the sale leg is part of the single `faction_tick` op (metadata `item_sales: {item_id: n}`) → stock rows −n,
region goods `stock += units`, `last_item_sales`, history `item_sales` / `items_sold`. Rows whose item can no longer
be sold stay (admin sees them). Non-ticking factions never sell (and cannot receive items, §3.0 #7).

### 3.9 API contracts

Errors `{"detail": "<Russian>"}`. Player endpoints: JWT + `_require_owner` (403 «Это не ваш персонаж»); private views
via `visibility.require_private_access`; admin: `require_permission`; internal: `verify_internal_token`.
**Route order**: static admin paths `/admin/factions/access/...` before `/admin/factions/{faction_id}`; internal
`/internal/factions/access/...` and `/internal/factions/battle-result` are static POSTs (no clash).

#### character-service — internal

| Method & path | Request | Response |
|---|---|---|
| `POST /characters/internal/factions/access/check` | `{kind: location\|dungeon, target_id:int, character_ids: [int] 1..20}` | `{rule: bool, allowed: bool, failed_character_ids: [int], detail: str\|null}` (§3.4 texts; names from `characters.name`) |
| `POST /characters/internal/factions/access/labels` | `{kind, target_ids: [int] ≤200, character_id: int\|null, user_id: int\|null}` | `{items: [{target_id, access_label, access_allowed: bool\|null}]}` — only targets with an active rule; viewer-aware only if `characters.user_id == user_id` |
| `GET /characters/internal/factions/{character_id}/passive-modifiers` | — | `{modifiers: {key: int}}` |
| `POST /characters/internal/factions/battle-result` | §3.6 (`participants` ≤ 50, `battle_type` str) | `{applied: [...], duplicate: bool}`; idempotent per battle |

#### character-service — player

| Method & path | Request | Response | Errors |
|---|---|---|---|
| `GET /characters/{cid}/factions` (extended) | — | each **active** membership + `passives: [{rank_id, rank_name, name, description, modifiers}]`, `outlaw_regions: [{region_id, region_name, level_name}]`; `donation` + `items_enabled: bool`, `items_disabled_reason: str\|null`; top-level `passive_total: {key: int}` | as before |
| `GET /characters/factions/catalog`, `GET /characters/factions/{fid}/public` (extended) | — | ranks + `passive: {name, description, modifiers}\|null`; faction + `outlaw_regions` (all factions — not membership-revealing) | as before |
| `GET /characters/{cid}/factions/{fid}/donate-items` | — | `{enabled, reason\|null, marks_per_point, daily_cap, points_today, marks_today, resets_in_seconds, items: [{item_id, name, image, item_rarity, quantity, unit_value}]}` (eligible plain stacks only) | 403, 404 |
| `POST /characters/{cid}/factions/{fid}/donate-items` | `{items: [{item_id: conint(≥1), quantity: conint(strict, 1..9999)}] 1..20 unique item ids, request_id: ^[A-Za-z0-9-]{8,64}$}` | `{points_delta, points_after, points_today, daily_cap, value_total, items_given, rank_ups}` | 400 item / not enough, 403 NPC/not own, 404 not member, 409 duplicate / not ticking, 422 |

#### character-service — admin

| Method & path | Permission | Contract |
|---|---|---|
| `GET /admin/factions/access/{kind}/{target_id}` | factions:read | `{rule: {faction_id, faction_name, min_rank_id, min_rank_name}\|null}` |
| `PUT /admin/factions/access/{kind}/{target_id}` | factions:edit | `{faction_id, min_rank_id\|null}`; target exists (404 «Локация не найдена» / «Подземелье не найдено»), faction exists, rank of that faction (422); upsert; post-commit eject sweep for a location |
| `DELETE /admin/factions/access/{kind}/{target_id}` | factions:edit | idempotent `{ok: true}` |
| `GET /admin/factions/{fid}/territory` | factions:read | `[{kind, target_id, target_name, min_rank: {id,name}\|null}]` |
| `GET /admin/factions/{fid}/enemies` / `PUT` | read / factions:edit | PUT replaces `{enemies: [{kind, ref_id\|null, points 1..10000}] ≤50, kill_points_daily_cap: int\|null 0..100000}`; mob template exists, NPC exists & is_npc & not mob, one `hostile` row max, duplicates 422; GET adds names |
| `GET /admin/factions/{fid}/outlaw-regions` / `PUT` | read / factions:edit | PUT replaces `{regions: [{region_id, level_code}] ≤50}`; region exists, level code valid, unique regions |
| `POST/PUT /admin/factions/…/ranks` (extended) | factions:edit | + `passive_name`, `passive_description`, `passive_modifiers` (§3.3 validation) |
| `GET/PUT /admin/factions/settings` (extended) | read / factions:settings | + 4 fields §3.2 bounds |
| `GET /admin/factions/{fid}/economy` (extended) | factions:read | + `item_stock: [{item_id, name, quantity, unit_value\|null}]`, `last.item_sales` |

#### locations-service

| Method & path | Change |
|---|---|
| `POST /locations/{dest}/move_and_post`, `POST /locations/{dest}/quick_move` | 403 faction pre-check before `create_post`; 409 pass-through from character-service unchanged |
| `GET /locations/{id}/client/details?character_id=` | neighbours + `access_label`, `access_allowed` (§3.4); schema `NeighborClient` optional fields |
| region details | `map_items` (locations) + `access_label` |

#### dungeon-service

| Method & path | Change |
|---|---|
| `POST /dungeons/{id}/sessions`, `POST /dungeons/{id}/party-run` | 403 whole-party refusal / 503 check unavailable (§3.4) |
| `GET /dungeons/at-location/{location_id}?character_id=` | + `access_label`, `access_allowed` (optional fields) |

### 3.10 Global lock order (supersedes 206 §3.6)

`econ_regions (asc region_id) → econ_region_goods (asc region_id, group_code) → econ_region_events → econ_caravans →
econ_guild_orders → econ_guild_xp_days → econ_mint_seasons → npc_shop_items → econ_banks → bank_deposits →
bank_loans → faction_members (asc id) → faction_economy (asc faction_id) → faction_qm_items (asc id) →
**faction_item_stock (asc faction_id, item_id)** → faction_debts (asc id) → faction_donation_days →
**faction_pvp_kills** → faction_qm_purchases → character_inventory → characters (asc id) → econ_accounts (asc id) →
character_attributes`. Item donation = members → item_stock → day rows → inventory (no accounts). Kill points =
members → day rows → pvp_kills (+ rank grants / debt INSERTs, as 206 `donate`). Tick = regions → goods → economy →
qm rows → item_stock → debts → op. Law paths (`update_location`, patrols) lock `characters` first and only **read**
faction tables (no faction locks) — unchanged order. Update the `econ_tick.py` docstring and the
character-service doc.

### 3.11 Security / secrecy

- **Auth** per §3.9; viewer-aware labels only for an owned character (locations: own check; dungeon: character-service
  check with `user_id`); internal endpoints token-only (gateway already blocks `/characters/internal/`).
- **Secrecy**: secret faction never named to non-members (closed label «Закрыто», refusal «Сюда вас не пускают»,
  dungeon party text generic); secret members never count as PvP enemies; membership crime carries no faction data;
  passives in the battle snapshot are folded numbers (no faction names); outlaw regions are not membership data.
- **Validation**: whitelists (passive keys, enemy kinds, access kinds, level codes), bounds §3.2/§3.9, existence
  checks (locations, dungeons, regions, mob templates, NPCs, ranks of the same faction), strict ints, parameterised
  SQL only.
- **Rate limiting / anti-abuse**: application level — kill-point daily cap + 24 h per-opponent rule + `pvp_training`
  excluded; item donations idempotent by `request_id`, share the 50-point daily cap, ≤ 20 lines × 9999; battle
  callback idempotent per battle. No new Nginx zone (no amplifying action).
- **Money**: no ledger op at donation; tick sale inside the single `faction_tick` op → world invariant
  `sum(characters) + sum(accounts) = 0` must hold in every test.
- Errors Russian, no stack traces.

### 3.12 Frontend

TypeScript + Tailwind + design-system classes (`docs/DESIGN-SYSTEM.md`: `gold-text`, `gray-bg`, `btn-blue`,
`btn-line`, `modal-overlay`, `modal-content`, `input-underline`, …), no `React.FC`, 360 px, every API error shown in
Russian (`apiErrorMessage` → toast / inline), `pendingRef` + `newRequestId()` for the item donation, `fetchProfile`
not needed (no money). All touched files are already `.tsx`.

- **`src/api/factions.ts`**: types + functions for every new/extended character-service endpoint (player + admin).
  `src/api/dungeons.ts`: `getDungeonsAtLocation(locationId, characterId?)` + `access_label/access_allowed` fields.
- **Shared** `src/constants/attributeBonusOptions.ts`: extract `ATTRIBUTE_BONUS_OPTIONS` from
  `Admin/PerksPage/PerkForm.tsx:125-167` (PerkForm imports it — no behaviour change) + `FACTION_PASSIVE_KEYS` filter.
  `ProfilePage/constants.ts` `STAT_LABELS` for display.
- **Admin faction editor** (`Admin/FactionsPage/*`): `RankFormModal.tsx` «Пассивка» block (name, description,
  modifier rows key + value, add/remove, ≤ 10); new `EnemiesEditor.tsx` (rows: kind «Моб» / «NPC» / «Участники
  враждебных фракций», picker — mob templates from existing `/characters/admin/mob-templates`, NPC select, points;
  daily cap with «по умолчанию» placeholder); new `OutlawRegionsEditor.tsx` (region select + law level select from
  the law levels API used by the reputation admin); new `TerritoryTab.tsx` (faction's closed locations/dungeons, add
  via location/dungeon select + optional rank, remove); `FactionEditor.tsx` wires the three sections;
  `FactionSettingsTab.tsx` + 4 settings; `FactionEconomyPanel.tsx` / `FactionEconLists.tsx` item stock list + last
  item sales. Buttons gated by `hasPermission('factions:edit' | 'factions:settings')`.
- **`FactionAccessField.tsx`** (new, `Admin/FactionsPage/`): faction select + rank select (ranks of the chosen
  faction) + Save / Remove, loads `GET /admin/factions/access/{kind}/{id}`; used in
  `AdminLocationsPage/EditForms/EditLocationForm/EditLocationForm.tsx` (existing location only) and
  `Admin/DungeonsPage/AdminDungeonForm.tsx` (existing dungeon only); rendered only with `factions:read`, editable with
  `factions:edit`. Hint text: «Тайная фракция: не-участники видят просто «Закрыто»».
- **Location page**: `LocationPage.tsx:172` passes `?character_id=<active>`; `pages/LocationPage/types.ts` neighbour
  fields; `NeighborsSection.tsx` shows `access_label` (lock icon + small text) and dims when `access_allowed ===
  false` (move button disabled with the label as reason; the server error is still shown if it happens);
  `TeleportMenu.tsx` — verify `locked_reason` already renders (no change if so).
  `WorldPage/RegionInteractiveMap/RegionInteractiveMap.tsx`: lock marker + label in the location tooltip.
- **Dungeon entrance** `DungeonPage/DungeonEntrance.tsx`: label; enter buttons disabled when `access_allowed ===
  false`; 403/503 details from start shown.
- **Profile «Фракции»**: `FactionMembershipCard.tsx` — block «Пассивки» (each rank passive: name, description,
  modifiers with `STAT_LABELS`, +sign) and total; warning banner «В крае «X» эта фракция вне закона (Y)» per region;
  journal renders new `kill` / `ejected` texts from the backend (no change if generic). `DonateFactionDialog.tsx` —
  two tabs «Марки» (existing) / «Предметы»: list of eligible items with quantity steppers, value and points preview
  (respecting `points_today` / `daily_cap`, «очков за сегодня больше не будет»), confirm step; disabled tab with
  `items_disabled_reason`.
- **Catalog** `pages/FactionsPage/FactionCard.tsx`: rank ladder shows each rank's passive; outlaw regions warning.
- **Crime label**: `Admin/ReputationPage/shadowLabels.ts` `faction_membership: 'Членство в запрещённой фракции'`
  (+ any player-side crime label map, if one exists — verify).

### 3.13 Data flows

```
Move: client ─► locations move_and_post: neighbour ✓ ─► faction_read pre-check (403) ─► create_post ─►
      PUT char /internal/{id}/update_location: lock row → location_refusal (409) → law _check (+membership crime) → commit
Dungeon: start_run: leader+party assembled ─► POST char /internal/factions/access/check ─► 403 whole party | continue
Eject: leave/expel/rule PUT (post-commit) and faction pass (5 min) ─► players_in_closed ─► _prepare_move (HTTP
      locations) ─► tx apply_admin_move + faction_log ejected ─► notice
Battle start: build_participant_info ─► GET char /internal/factions/{cid}/passive-modifiers ─► folded into snapshot
Battle end: _finalize_battle ─► (law callback) ─► POST char /internal/factions/battle-result (bg task, 3 retries)
      per winner tx: members → day row → pvp_kills → points (+hostile) → ranks ─► notices, deliver_pending
Guard check (entry/teleport/patrol): _check ─► outlaw membership? cooldown? ─► open: detected / secret: roll ─►
      register_crime(floor) ─► encounter
Item donation: tx members → item_stock → day row → inventory −n → stock +n → points → ranks (no money)
6 h tick: faction step ─► … qm rows → item_stock → debts ─► faction_tick op (… + purse(hq) → faction item sales)
```

### 3.14 Cross-service validation

- All response changes are additive optional fields (old clients ignore them). `update_location` keeps its contract
  (409 + detail already passed through). `DungeonAtLocationResponse` / `NeighborClient` gain optional fields.
- New HTTP edges: dungeon → character (2 internal endpoints; dungeon already calls character-service), battle →
  character (2 internal endpoints; already calls it). Graph in CLAUDE.md unchanged in direction.
- Deploy order tolerance: locations `faction_read` treats a missing `faction_access_rules` table as "no rules";
  dungeon start fails closed with 503 only if character-service is unreachable; battle-service passive lookup and
  callback are soft-fail (404 from an older character-service → no passives / logged).
- `econ_core` ×4 untouched (sale uses `faction_tick` + existing kinds); `plan_faction_step` new inputs default to
  "none" → stage-2 behaviour identical.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Every agent: No commits, no pushes, no `git add`, no `git stash`, no `git checkout`/`reset`.** The user commits once
at the end (push to main = prod deploy). Backend devs run `python -m py_compile` on every modified file and their
service's tests inside the container; frontend devs run `npx tsc --noEmit` and `npm run build` inside the frontend
container (no node on the host). Each agent writes a Russian `[LOG]` line in §6.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | **character-service: schema + pure rules.** Migration `047_faction_territory` + models (§3.2, settings defaults, delete guards for rank/faction); `faction_core.py`: `access_decision` + texts, `FACTION_PASSIVE_KEYS`, `validate_passive`, `active_passives`, `sum_modifiers`, `kill_gain`, `EV_KILL`/`EV_EJECTED` + history texts; `faction_econ.py`: `Budgets.sales`, `SaleRowIn`, sale planning inside `plan_faction_step` (§3.3, defaults keep stage-2 results); `law_core.CRIME_FACTION_MEMBERSHIP`; settings model/bounds extended. | Backend Developer | DONE | `services/character-service/app/alembic/versions/047_faction_territory.py`, `app/models.py`, `app/faction_core.py`, `app/faction_econ.py`, `app/law_core.py`, `app/schemas.py`, `app/faction_admin_crud.py` | — | Migration up/down clean on MySQL (container); pure functions deterministic; py_compile passes |
| 2 | **character-service: territory.** `faction_territory.py` (rule read/upsert/delete, `location_refusal`, labels, party check texts, `outlaw_membership`, `players_in_closed`, `pick_target`, async `eject`); gate in `main.update_location` (409) and `crud.execute_teleport` (403 before charge) + `teleport_lock_reasons`; internal `access/check`, `access/labels`; admin access GET/PUT/DELETE + `{fid}/territory` (route order); eject sweep step in `faction_pass.run_pass` + post-commit eject after leave / admin expel / rule PUT. | Backend Developer | DONE | `app/faction_territory.py`, `app/main.py`, `app/crud.py`, `app/faction_api.py`, `app/faction_pass.py`, `app/schemas.py` | 1 | Non-member move → 409 with text; secret faction never named to non-members; NPCs unaffected; hidden faction = open; eject picks neighbour → HQ → station, skips battle/dungeon and retries; py_compile passes |
| 3 | **character-service: passives, kills, crime.** Rank passive fields in admin rank create/update; `GET /internal/factions/{cid}/passive-modifiers`; `faction_kills.py` + `POST /internal/factions/battle-result` (§3.6: winners incl. fallen, `pvp_training` excluded, secret victims excluded, 24 h rule, daily cap with per-faction override, hostile penalty, idempotent per battle, notices); admin enemies + outlaw-regions GET/PUT; `law_crud._check` membership hook (§3.7) + `patrol_crud._SQL_SUSPECTS` third branch; private view / catalog / public extensions (passives, passive_total, outlaw_regions). | Backend Developer | DONE | `app/faction_kills.py`, `app/faction_api.py`, `app/faction_admin_crud.py`, `app/faction_crud.py`, `app/law_crud.py`, `app/patrol_crud.py`, `app/schemas.py` | 1 | Same battle twice → no double points; cap and 24 h rule hold; open outlawed member stopped without roll, secret only on a successful roll, crime once per cooldown per region; patrols find zero-wanted outlawed members; existing law tests green; py_compile passes |
| 4 | **character-service: item donations + tick sale.** `faction_items.py` (options + donate flow §3.8, lock order §3.10, idempotency via faction_log key); routes `GET/POST /{cid}/factions/{fid}/donate-items`; private view `items_enabled/reason`; `plan_pass` sales budget split + `faction_step` sale (stock rows, goods stock, history/last columns, metadata); economy admin view `item_stock`; faction delete guard for stock; `econ_tick.py` docstring lock order; `docs/services/character-service.md` section «Фракции — этап 3» (tables, endpoints, lock order, eject, crime). | Backend Developer | DONE | `app/faction_items.py`, `app/faction_econ_crud.py`, `app/econ_tick.py`, `app/faction_api.py`, `app/faction_crud.py`, `app/schemas.py`, `docs/services/character-service.md` | 1 (2, 3 for the doc) | Items leave the bag only with a successful donation; same request_id → 409; non-ticking faction → 409 with reason; quest/off-market/enhanced → 400; tick sells within the cap, world sum = 0; econ_core files untouched (`sh scripts/check_econ_copies.sh` ok); py_compile passes |
| 5 | **locations-service: pre-check + marks.** `faction_read.py`: rules read (tolerant), `location_access` (parity with `faction_core.access_decision`), labels (viewer-aware / public); pre-check in `move_and_post` and `quick_move` before `create_post` (403); `get_client_location_details(..., viewer_character_id)` with ownership check; `NeighborClient` + region `map_items` `access_label`; `docs/services/locations-service.md`. | Backend Developer | DONE | `services/locations-service/app/faction_read.py`, `app/main.py`, `app/crud.py`, `app/schemas.py`, `docs/services/locations-service.md` | 1 (table/columns) | Refused move creates no post; non-owned `character_id` gets public labels only; missing tables → no marks, moves still work; py_compile passes |
| 6 | **dungeon-service + battle-service.** dungeon: `http_clients.check_faction_access` / `faction_access_labels`; `start_run` whole-party check (403 / 503), `at-location` optional `character_id` + fields; battle: `fetch_faction_passives` + `faction_passives.apply` in `build_participant_info` (non-NPC, soft-fail, derived via `_DERIVED_PER_POINT` + `effective_delta`), `_notify_faction_battle_end` after `_notify_law_battle_end` (bg task, retries, mob_template_id); docs `docs/services/dungeon-service.md`, `docs/services/battle-service.md`. | Backend Developer | DONE | `services/dungeon-service/app/http_clients.py`, `app/gameplay.py`, `app/main.py`, `app/schemas.py`, `services/battle-service/app/main.py`, `app/battle_engine.py`, `app/faction_passives.py`, docs | 2, 3 (contracts) | Party with one non-member refused as a whole, skip rule for other checks unchanged; character-service down → passives absent, battle starts; callback never blocks the ending; py_compile passes |
| 7 | **Frontend: admin.** `api/factions.ts` admin functions/types; `constants/attributeBonusOptions.ts` extraction (PerkForm imports it); `RankFormModal` passive block; `EnemiesEditor`, `OutlawRegionsEditor`, `TerritoryTab` wired in `FactionEditor`; settings fields; economy item stock; `FactionAccessField` in `EditLocationForm` and `AdminDungeonForm`; `shadowLabels.ts` crime label (§3.12). | Frontend Developer | DONE | `src/api/factions.ts`, `src/constants/attributeBonusOptions.ts`, `src/components/Admin/PerksPage/PerkForm.tsx`, `src/components/Admin/FactionsPage/*`, `src/components/AdminLocationsPage/EditForms/EditLocationForm/EditLocationForm.tsx`, `src/components/Admin/DungeonsPage/AdminDungeonForm.tsx`, `src/components/Admin/ReputationPage/shadowLabels.ts` | 2, 3, 4 | tsc + build pass; all admin flows work live with Russian errors; permission-gated; usable at 360 px; perk form unchanged in behaviour |
| 8 | **Frontend: player.** `api/factions.ts` player functions/types, `api/dungeons.ts`; neighbours marks + `character_id` in details call; region map marker; `DungeonEntrance` label/disable/errors; `FactionMembershipCard` passives + outlaw warnings; `DonateFactionDialog` «Предметы» tab; catalog `FactionCard` passives + outlaw regions (§3.12). | Frontend Developer | DONE | `src/api/factions.ts`, `src/api/dungeons.ts`, `src/components/pages/LocationPage/{LocationPage,NeighborsSection,types}.tsx/ts`, `src/components/WorldPage/RegionInteractiveMap/RegionInteractiveMap.tsx`, `src/components/DungeonPage/DungeonEntrance.tsx`, `src/components/ProfilePage/FactionsTab/*`, `src/components/pages/FactionsPage/FactionCard.tsx` | 2, 3, 4, 5, 6 (7 for the shared api module edits) | tsc + build pass; closed neighbour shown and dimmed; item donation with confirm + preview + errors; 360 px OK |
| 9 | **QA: character-service — territory, passives, kills.** Extend `tests/faction_world.py` (DDL `faction_access_rules` etc., `Locations`/`LocationNeighbors`/`Regions`, `active_mobs`/`mob_templates`, `dungeons` minimal); tests: `access_decision` table (public/secret/rank/hidden/deleted faction); `update_location` 409 + NPC exempt + teleport 403 / `locked_reason`; eject target order, battle/dungeon skip (mock `_prepare_move`), journal + notice, sweep; internal check texts (party, secret generic) and labels (owner vs foreign `user_id`); passives sum (cumulative, multi-faction, left member none, hidden faction still on); battle-result (mob/npc/hostile, `pvp_training` 0, secret victim 0, fallen winner gets points, 24 h rule, daily cap + override, hostile penalty, duplicate battle); admin validation 422/409 + permission 403; rank/faction delete guards; secrecy assertions (no secret name in any non-member text). | QA Test | DONE | `services/character-service/app/tests/faction_world.py`, `app/tests/test_faction_territory.py`, `app/tests/test_faction_passives_kills.py` | 1, 2, 3 | All new tests pass in the container; full existing suite green |
| 10 | **QA: character-service — crime + item donations + tick sale.** Membership crime: open member stopped without roll, secret only on roll (patch `detection_rng`), slip → no crime, cooldown per region, floor = level min_value, no faction data in crime/log rows, patrol prefilter finds zero-wanted outlawed member, existing law/patrol tests green; item donations: eligibility reasons, plain-stack only, quest item, not ticking 409, idempotency 409, not-enough 400, daily cap shared with marks donation, hostile penalty; tick: sale within `econ_item_sale_share_pct`, goods stock +units, stock −n, resumed run no double sale, stage-2 tick results unchanged when no stock; **world invariant after every money flow**; `sh scripts/check_econ_copies.sh` ok. | QA Test | DONE | `app/tests/test_faction_outlaw.py`, `app/tests/test_faction_items.py` | 1, 3, 4 | All new tests pass; existing econ/law/faction suites green |
| 11 | **QA: locations / dungeon / battle.** locations: pre-check 403 creates no post (mock HTTP), 409 pass-through unchanged, marks viewer-aware only for owner, public labels, tolerant to missing tables, parity cases with task 9's table; dungeon: solo refusal, party whole refusal with names (public) / generic (secret), other-check skips unchanged, 503 on HTTP failure, at-location fields; battle: passives folded into snapshot (primary → derived with caps), soft-fail, NPC skipped, callback payload (fallen winners, mob_template_id) and never raising. Sync-wrapper style (no pytest-asyncio in containers). | QA Test | DONE | `services/locations-service/app/tests/test_faction_access.py`, `services/dungeon-service/app/tests/test_faction_dungeon_access.py`, `services/battle-service/app/tests/test_faction_battle.py` | 5, 6 | All new tests pass in the containers; existing suites green |
| 12 | **Docs/ISSUES.** Confirm docs of tasks 4–6 updated; `docs/ISSUES.md`: note «forced moves (admin/jail/home scroll/dungeon return) may land in a closed location until the 5-min eject sweep» and «membership crime adds minimal infamy» as LOW known behaviour (only if not covered in service docs). | Backend Developer | DONE | `docs/ISSUES.md`, `docs/services/*.md` | 4, 5, 6 | Docs reflect §3; no stale entries |
| 13 | **Review.** Full review vs §3 (secrecy, idempotency, lock order, money invariant, CLAUDE.md frontend rules), py_compile / tsc / build re-run, pytest in character / locations / dungeon / battle, `check_econ_copies.sh`, live verification in Chrome on localhost (closed neighbour + refused move without orphan post, member passes, eject after leave, faction dungeon party refusal, passive visible in battle snapshot, mob kill → points in journal, outlaw region stop by guards, item donation + manual tick sale, admin tabs, 360 px). | Reviewer | TODO | — | 1–12 | PASS with automated + live results in §5 |

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-06
**Result:** PASS (no blocking code defects; one deploy risk for PM, see "Risks")

#### Scope reviewed
Stage-3 changes on top of the uncommitted FEAT-205/206 tree: migration `047_faction_territory`, `faction_territory.py`,
`faction_kills.py`, `faction_items.py`, `faction_core.py` (access decision, passives, kill gain), `law_crud._check` hook +
`_outlaw_membership`, `patrol_crud._SQL_SUSPECTS` third branch, `faction_pass` eject step, `main.update_location` (409) /
`crud.execute_teleport` (403 before charge) / `teleport_lock_reasons`, `faction_api` routes; locations-service
`faction_read` access marks + pre-check in `move_and_post` / `quick_move` + `client/details` owner check; dungeon-service
`check_faction_access` (fail closed 503) / `faction_access_labels` (soft-fail) / `start_run` whole-party check;
battle-service `faction_passives.py`, `build_participant_info` injection, `_notify_faction_battle_end`; frontend
TerritoryTab, EnemiesEditor, OutlawRegionsEditor, FactionAccessField, RankFormModal passive block, FactionPassives,
useItemDonation / DonateFactionDialog, NeighborsSection, DungeonEntrance, FactionCard.

#### Findings
- **Correctness vs §1/§3:** the access table (public / secret / rank / hidden / deleted) matches §3.3 in both copies
  (character-service `faction_core.access_decision`, locations `faction_read.access_decision`); hidden faction opens its
  territory; NPCs exempt; dungeon refusal for a secret faction is generic. Passives cumulative over the ladder, battle keys
  only (35 keys in the admin select). Kill points: winners incl. fallen, `pvp_training` excluded, secret victims excluded
  (`open_only`), 24 h rule, daily cap with per-faction override, hostile penalty, idempotent via the `faction_log` key per
  (battle, winner), checked before `faction_pvp_kills` is touched. Membership crime: open member detected without a roll,
  secret only on a successful roll, cooldown per region, floor = level `min_value`, no faction data in crime rows.
- **Economy invariant:** item donation moves no money (no ledger op); the sale is a leg of the existing `faction_tick` op.
  `scripts/check_econ_copies.sh` — all shared copies identical (econ_core x4 untouched).
- **Lock order / idempotency:** item donation members -> item_stock (asc item_id) -> day row -> inventory; kills members ->
  day rows -> pvp_kills; matches §3.10. `ensure_day_row` / `ensure_stock_rows` run in their own short transactions first.
  Donation idempotent by `request_id` (409 «Это пожертвование уже выполнено»).
- **Security:** internal endpoints `verify_internal_token` (401 without token in-container, 403 at the gateway — checked);
  admin endpoints `require_permission(factions:read|edit)`; player endpoints `_require_owner`; viewer-aware labels only for
  the user's own character (locations `owned_character`, character-service `viewer_character`). Pydantic bounds +
  server-side whitelists (kinds, keys, level codes, existence checks). Parameterised SQL (table names in f-strings are fixed
  constants). Russian error texts, no internals leaked.
- **Cross-service:** all response changes are additive optional fields; new edges dungeon -> character and battle ->
  character use the existing internal-token pattern; the battle callback is fire-and-forget with 3 retries and never
  blocks the battle ending.
- **Frontend rules:** all touched/new files `.tsx`, Tailwind + design-system classes (`gray-bg`, `gold-text`, `btn-blue`,
  `btn-line`, `site-link`, `rounded-card`), no `React.FC`, no `any`, no new SCSS; every API call shows a Russian error
  (toast / inline with «Повторить»).
- **Tests:** stage-3 test files exist in all four services (character: territory / passives_kills / outlaw / items /
  sanity; locations: test_faction_access; dungeon: test_faction_dungeon_access; battle: test_faction_battle).

#### Non-blocking notes (LOW — later task, not required for this feature)
| # | File | Note |
|---|------|------|
| 1 | `services/character-service/app/faction_territory.py:363` `players_in_closed` | The SQL takes the first 200 characters standing on any active-rule location (ordered by id) **before** the Python access filter. With >200 *allowed* members standing in closed locations, refused players beyond that window are never ejected by the sweep. Fix: exclude allowed members in SQL (LEFT JOIN the active membership) or page until exhausted. Irrelevant at current player counts. |
| 2 | `faction_territory.eject` called from async routes (`faction_api._eject`, `admin_put_access`) | Sync SQLAlchemy queries run directly on the event loop (only the HTTP part is awaited) — a short loop block per ejected player. Could wrap the DB parts in `run_in_threadpool`. |
| 3 | `services/dungeon-service/app/gameplay.py:1079` | Every dungeon start (also of non-faction dungeons) now needs character-service; an outage -> 503 (fail closed by design §3.4). Documented; noting the new hard dependency. |

#### Risks for PM
- **CI duration (character-service):** local full suite `9744 passed, 2 skipped in 777 s (12 m 57 s)` (pytest time; 733 s
  wall; it ran in parallel with other suites — QA measured 718 s sequentially). This is **above the 9-minute CI job
  limit**: the character-service test job will likely time out on push regardless of code correctness. Stage 3 adds only
  ~25 s; the suite as a whole is over budget. Needs a decision before the push (raise the job timeout, split the job /
  `pytest -n`, or trim slow tests) — a DevSecOps task, not a code fix of this feature.

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (no output)
- [x] `npm run build` (frontend container) — PASS (built in 1 m 16 s; only the usual chunk-size warning)
- [x] `py_compile` — PASS (character: 19 files incl. migration 047; locations 4; dungeon 4; battle 3)
- [x] `pytest` character-service — PASS: 9744 passed, 2 skipped (777 s)
- [x] `pytest` locations-service (`--asyncio-mode=auto`, as in CI) — PASS: 2976 passed, 4 skipped (290 s)
- [x] `pytest` dungeon-service (`--asyncio-mode=auto`) — PASS: exit code 0, 0 failed / 0 errors (54 s)
- [x] `pytest` battle-service (`--asyncio-mode=auto`) — PASS: 1890 passed, 10 skipped (141 s)
  (a first run without `--asyncio-mode=auto` showed async-fixture errors in pre-existing files — a runner-flag artefact;
  CI passes the flag)
- [x] `sh scripts/check_econ_copies.sh` — PASS (all shared copies identical)
- [x] `docker compose config` — PASS
- [x] `alembic current` (character-service) — `047_faction_territory (head)`
- [x] Live verification (Chrome, localhost) — PASS

#### Live Verification Results
- `/admin/factions` -> secret faction «Тестовая Тень» -> «Территория и враги»: closed location «Рвы Кейли» (#196) via the
  picker; row appeared with a toast. Rank modal: passive with an empty value -> Russian toast «Пассивка: значение от -100 до
  100, не 0»; with Сила +5 -> saved (`{"strength": 5}`). Enemies: empty mob -> «Моб: выберите, кого именно»; hostile row
  saved; outlaw region Геттенхорн / Преступник saved («Края, где фракция вне закона, сохранены»).
- `GET /locations/197/client/details`: non-member (char 761) -> `access_label «Закрыто», access_allowed false` (secret
  faction not named); member (763) -> «Территория фракции «Тестовая Тень»», true; anonymous -> «Закрыто», null.
- Refused move: `move_and_post` and `quick_move` to #196 for 761 -> **403 «Сюда вас не пускают»**; posts count unchanged
  (172 / max id 990167), character stayed at 197 (no orphan post).
- Location page as the non-member: neighbour card dimmed with a lock + «Закрыто»; at **360 px** (iframe) no horizontal
  overflow (scrollWidth 345).
- Internal `passive-modifiers`: 763 -> `{"strength": 5}` (cumulative from rank 1 while holding rank 4), 761 -> `{}`;
  no token -> 401; via the gateway -> 403.
- Profile «Фракции»: block «Пассивки (в бою)» — «Ревью-пассивка · звание «Послушник» +5 Сила»; fine at 360 px.
- Donation dialog, tab «Предметы»: 9 eligible stacks with unit values, steppers, points preview («даст +5 очков», 18 из 50);
  360 px layout fits. The donation itself was not re-submitted (already verified live by the frontend developer).
- Catalog `/factions`: «В крае «Геттенхорн» эта фракция вне закона (Преступник)».
- Console errors: NONE on the admin factions, location, profile and catalog pages.
- Test data reverted afterwards (rule, passive, enemies, outlaw rows removed; active character restored to 763).
- Not exercised live (covered by tests): faction dungeon party refusal, eject after leave, mob kill -> points, guard stop
  of an outlawed member, tick item sale.

## 6. Logging (all agents — in Russian)

```
[LOG] 2026-11-06 — PM: фича создана (этап 3 фракций), запускаю анализ кодовой базы
[LOG] 2026-11-06 — Codebase Analyst: анализ завершён — пути перемещения/телепорта/входа в данж, пассивки (перки vs инъекция в бой), хук конца боя, точка подключения закона и патрулей, сдача предметов по образцу гильдии; 8 вопросов к пользователю в разделе 2
[LOG] 2026-11-06 14:17 — Architect: спроектировано — правила доступа в одной таблице character-service (миграции locations 059 / dungeon 010 / user 0036 не нужны), пассивки только в бою (инъекция в battle-service), колбэк конца боя для очков, правонарушение «членство» внутри проверки стражи, сдача предметов на склад фракции с продажей в тик (econ_core ×4 не меняется); 13 задач, ~14 новых/изменённых API-контрактов
[LOG] 2026-11-06 15:40 — Backend Developer: задачи #1–#6 и #12 сделаны. Миграция character 047_faction_territory (5 таблиц + новые колонки) применена локально, downgrade/upgrade чистые; модули faction_territory / faction_kills / faction_items; ворота хода (409) и телепорта (403), выдворение (после выхода/исключения/правила + шаг 5-минутного прохода); пассивки в снимке боя (battle-service faction_passives); колбэк конца боя → очки за врагов; правонарушение «членство» в проверке стражи + фильтр патрулей; сдача предметов на склад фракции и продажа склада в шаге тика (econ_core ×4 не тронут); locations — предпроверка хода до поста и отметки соседей/карты; dungeon — проверка всей группы (403/503) и отметки списка
[LOG] 2026-11-06 15:40 — Backend Developer: контракты §3.9 не менялись; уточнения для фронта: items_enabled / items_disabled_reason лежат внутри membership.donation; GET enemies отдаёт name и ref_id=null для hostile; GET outlaw-regions отдаёт region_name / level_code / level_name; история экономики + item_sales / items_sold
[LOG] 2026-11-06 15:40 — Backend Developer: обновлены 3 существующих теста под аддитивные поля (настройки фракций, DDL-проверки 045/046 пропускают колонки 047, поля соседей в locations) и harness данжей (фейки check_faction_access / faction_access_labels); добавлен быстрый tests/test_faction_stage3_sanity.py (11 тестов)
[LOG] 2026-11-06 15:40 — Backend Developer: обнаружен баг (FEAT-206, не связан с этапом 3): teardown test_econ_dungeon не удаляет таблицу factions → 22 ERROR в dungeon-service; добавлен в ISSUES.md (MEDIUM)
[LOG] 2026-11-06 — Frontend Developer: задача #7 (админка) готова — пассивка в редакторе звания, вкладка фракции «Территория и враги» (территория, враги с очками и своим лимитом, края «вне закона» с тяжестью), 4 новые настройки, склад предметов и продажи в экономике фракции, поле «Только для фракции» в редакторах локации и подземелья, ярлык правонарушения «Членство в запрещённой фракции»; список характеристик вынесен в constants/attributeBonusOptions.ts (перки ведут себя как раньше)
[LOG] 2026-11-06 — Frontend Developer: задача #8 (игрок) готова — отметки «Закрыто…» у соседних локаций (запрет — затемнено и не кликается), замок на карте края, отметка и блокировка входа в подземелье, пассивки и предупреждения «вне закона» в профиле и каталоге, вкладка «Предметы» в пожертвовании (выбор, предпросмотр очков, подтверждение, request_id). Функция api: существующая fetchDungeonsAtLocation получила characterId вместо новой getDungeonsAtLocation
[LOG] 2026-11-06 — Frontend Developer: проверено — tsc --noEmit и npm run build в контейнере frontend проходят; вживую на localhost: закрытие локации из вкладки «Территория», отметка у соседа (своя фракция / чужая — затемнено), пожертвование 1 предмета ушло и записалось в журнал, консоль без ошибок; временная фракция удалена, правило снято. Не проверено вживую: пассивки/враги/края с данными, мобильная ширина, вход в подземелье фракции
[LOG] 2026-11-06 — QA Test: задача #11 готова — locations test_faction_access.py (42 теста: предпроверка хода 403 до поста в move_and_post/quick_move, проброс 409, отметки соседей, владелец персонажа, паритет текстов с character-service, нет таблиц → нет отметок), dungeon test_faction_dungeon_access.py (21: отказ всей группе 403, тайная фракция без имени, пропуски по другим проверкам не меняются, 503 при недоступности character-service, отметки списка), battle test_faction_battle.py (37: пассивки в снимке с производными и капами, NPC не запрашивается, мягкий отказ, колбэк конца боя — payload, ретраи, не ломает завершение)
[LOG] 2026-11-06 — QA Test: баг исправлен — teardown test_econ_dungeon не удалял таблицу factions (22 ERROR); добавлена в _ECON_TABLES, запись в ISSUES.md помечена DONE
[LOG] 2026-11-06 — QA Test: полные прогоны в контейнерах — locations 2976 passed / 4 skipped, battle 1890 passed / 10 skipped, dungeon 903 passed / 1 skipped (0 ошибок, включая test_econ_dungeon*)
[LOG] 2026-11-06 — QA Test: задача #9 готова — character-service test_faction_territory.py (41: таблица решения доступа, ворота хода 409 и телепорта 403 до списания + locked_reason, выдворение сосед → штаб → караульня, пропуск в бою/при 409 _prepare_move, журнал и уведомление, 5-минутный проход, выдворение после выхода и PUT правила, internal check/labels с владельцем и валидацией, токен на 4 internal-эндпоинтах, админ-правила и права, удаление фракции со складом, тайная фракция нигде не названа), test_faction_passives_kills.py (43: валидация пассивок, накопительная сумма по званиям и фракциям, админ-звание с пассивкой, профиль/каталог, очки за мобов/NPC/враждебных, правило 24 ч и его настройка, дневной лимит общий/свой/0, штраф враждебности, повышение звания, валидация колбэка и врагов, границы настроек); в faction_world.py добавлены фикстура tw и хелперы
[LOG] 2026-11-06 — QA Test: задача #10 готова — test_faction_outlaw.py (15: открытый участник без броска, тайный только при успешном броске, проскальзывание без правонарушения, пол = порог ступени, самая тяжёлая ступень и приоритет открытой фракции, раз в кулдаун на край, края независимы, без стражи/другой край/вышедший — ничего, в строках закона нет данных фракции, фильтр патрулей, патруль и update_location), test_faction_items.py (30: список только обычных стопок, причины отказа, всё-или-ничего, 409 «не тикает» ×4 и повтор request_id, 422 включая инъекции, общий лимит с марками, штраф враждебности, нет операций в леджере; продажа в тик в пределах доли кошелька, повтор прогона без двойной продажи, доля 0 и квестовый предмет не продаются, деление бюджета между фракциями края, админ-вид склада; чистые тесты планировщика; инвариант мира = 0); scripts/check_econ_copies.sh — ok
[LOG] 2026-11-06 — QA Test: багов в коде не найдено. Замечание: ключ правонарушения «членство» с точностью до секунды (now без микросекунд) — коллизии невозможны при кулдауне ≥ 1 ч, тесты передают разное время. Полный прогон character-service в контейнере: 9744 passed / 2 skipped за 718 с (новые 129 тестов ≈ 25 с)
[LOG] 2026-11-06 16:20 — Reviewer: начал проверку этапа 3
[LOG] 2026-11-06 17:05 — Reviewer: проверка завершена, результат PASS. Тесты зелёные (character 9744, locations 2976, battle 1890, dungeon — 0 падений), tsc/build ок, копии econ_core идентичны; вживую — закрытая локация без имени тайной фракции, отказ хода без поста, пассивки, враги, края вне закона, вкладка «Предметы», 360 px, консоль чистая. Риск: полный прогон character-service ~13 мин — больше 9-минутного лимита CI. Два мелких замечания (окно 200 в проходе выдворения, синхронная БД в async-выдворении) — не блокируют
[LOG] 2026-11-06 — PM: ревью PASS, исправлен лимит выброса в players_in_closed, фича закрыта
```

## 7. Completion Summary (filled by PM on completion — in Russian)

- Этап 3 фракций сделан: закрытые локации и данжи фракций (с выбросом потерявших право: соседняя открытая → штаб → отделение стражи), пассивки на званиях (действуют только в бою), очки за победы над врагами фракции (мобы/NPC/открытые участники враждебных фракций; 1 раз в 24 ч за противника, лимит в день), членство как преступление в крае (ловит стража при проверке; тайных — через бросок скрытности), пожертвование предметов (продаются в тик фракции, инвариант экономики соблюдён).
- Миграция: character 047_faction_territory. econ_core не менялся.
- Тесты: character 9744, locations 2976, battle 1890, dungeon — всё зелёное; исправлена ошибка тестов экономики данжей из этапа 2.
- Ревью: PASS. После ревью PM исправил лимит в поиске игроков для выброса (keyset-постранично).
- Риск: полный прогон тестов character-service локально ~12 мин при лимите CI 9 мин (в CI раньше шёл ~5 мин).

