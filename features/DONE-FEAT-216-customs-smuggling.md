# FEAT-216: Таможня и контрабанда

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-18 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Таможня и контрабанда (следующий этап после морских караванов FEAT-215). У игроков пространственный инвентарь — обыскивать их бессмысленно, поэтому таможня работает **только с физическими грузами: караванами** (сухопутными и морскими). Даёт смысл границам и две новые роли игрокам: таможенник и контрабандист.

### Бизнес-правила
1. **Посты.** Админ отмечает локацию галочкой «Таможня» (по аналогии с «Порт»). Законный караван из другой страны обязан пройти через пост страны назначения — маршрут строится через него. Порт с таможней досматривает всё, что приходит морем. Нет поста у страны — досмотра нет.
2. **Запреты.** У каждой страны в админке — список запрещённых групп товаров. Законная торговля такой группой в эту страну не идёт. Спрос остаётся → часть таких сделок уходит контрабандистам с наценкой (~+50 % к цене, параметр). Тюки с налётов (краденое) — контрабанда везде.
3. **Досмотр законного каравана.** На посту караван стоит ~30 мин (параметр) и платит пошлину физически — в казну страны. Пока стоит, на него можно напасть, как в воротах.
4. **Таможенник-игрок.** Нанимается у нового НПС «Таможенник» на посту, несёт вахту в пограничных локациях. Мимо идёт контрабандный караван → шанс заметить (внимательность таможенника против скрытности каравана). Заметил → бой с охраной контрабандистов, законный (не преступление). Победа → товар в казну страны (конфискат), таможеннику доля конфиската, слава и репутация у этой страны.
5. **Контрабандист-игрок.** Охрана контрабандного каравана нанимается у Скупщика (не у Караванщика), платят больше обычной охраны. Караван пойман и бой проигран → охране преступление в этой стране. Для обычных игроков контрабандный караван выглядит как простой (не помечен «контрабанда»).
6. **Без игроков-таможенников.** Контрабандные караваны обходят посты, но существующие патрули стражи могут их остановить с небольшим шансом — таможня работает, даже если никто не на вахте.
7. **Взятки — позже**, не в этой фиче.

### UX / Пользовательский сценарий
1. Админ ставит галочку «Таможня» на пограничной локации/порту, задаёт стране запрещённые группы.
2. Законный караван идёт через пост, стоит на досмотре, платит пошлину, едет дальше.
3. Игрок нанимается таможенником, стоит на вахте; мимо проходит контрабандный караван — уведомление/бой; победа — доля конфиската.
4. Другой игрок нанимается у Скупщика охранять «простой» караван (на деле контрабандный), получает повышенную плату, рискует преступлением.

### Edge Cases
- Нет поста у страны — досмотра нет, контрабанде некого обходить.
- Пост недостижим по дорогам — как с воротами (сделки нет / абстрактно по параметру FEAT-215).
- Морской контрабандный караван: порт прибытия с таможней — обходит (высадка в другом порту?) — решает архитектор.
- Таможенник и контрабандист — один и тот же игрок / одна группа.
- Пространственный инвентарь игроков таможня НЕ трогает.

### Вопросы к пользователю (если есть)
- [x] Что досматриваем? → Только караваны (инвентарь игроков пространственный).
- [x] Посты → галочка «Таможня» на локации, законный караван обязан пройти пост, порт с таможней — для моря.
- [x] Запреты → группы товаров по стране; контрабанда с наценкой ~50 %; краденое — контрабанда везде.
- [x] Досмотр → ~30 мин стоянки + физическая пошлина в казну; можно напасть.
- [x] Таможенник-игрок → найм у НПС «Таможенник», вахта, шанс заметить, законный бой, доля конфиската + слава + репутация.
- [x] Контрабандист-игрок → найм у Скупщика, повышенная плата, преступление при поимке, караван замаскирован.
- [x] Без игроков → патрули стражи ловят контрабанду с небольшим шансом.
- [x] Взятки → позже.
- [x] (после анализа) Обнаружение → «внимательность» таможенника = его скрытность (stealth); скрытность каравана = базовый параметр + лучшая скрытность игроков-охранников контрабанды; формула шанса — как у стражи (law_core.detection_chance).
- [x] (после анализа) Конфискат → товар на склад региона, где поймали (на его рынок); деньги покупателя из эскроу — в казну страны как штраф, из них доля таможеннику; покупатель теряет деньги (риск контрабанды).
- [x] (после анализа) «Краденое — контрабанда везде» → УБРАНО: тюки остаются в инвентаре игроков и продаются только Скупщику, таможня их не касается.
- [x] (после анализа) Патрули без таможенников → без игроков в охране — конфискация без боя; с игроками в охране — бой охраны против патруля (шанс отбиться).
- [x] (после анализа) Контрабанда идёт и между странами с закрытой торговлей (нет торговой пары).

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-service (core) | caravan routing via customs post, inspection hold, physical duty, contraband planning / routing / masking, customs-officer job + NPC role, smuggler escort hiring at the fence, detection (officer / patrol), legal fight vs contraband guards (reuse of raid lifecycle), confiscation, crime for smugglers, rewards, admin (banned groups per country, params) | `econ_caravan.py`, `economy_caravan_crud.py`, `caravan_route.py`, `caravan_pass.py`, `caravan_raid_crud.py`, `caravan_api.py`, `caravan_escort_crud.py` / `caravan_escort_api.py`, `fence_crud.py`, `sea_cargo.py`, `patrol_crud.py`, `shadow_crud.py` / `law_crud.py` / `law_core.py`, `reputation_core.py`, `econ_core.py` (if new op), `econ_sim.py`, `schemas.py`, `models.py`, `economy_api.py`, new migration `055_*`, new module(s) e.g. `customs_*.py` |
| locations-service | `Locations.is_customs` flag (model, schemas, create/update, read payloads), migration `061_*`; `reputation_core.py` copy if a reputation action is added; `econ_core.py` copy if a ledger op is added | `app/models.py:142-156`, `app/schemas.py:120/137/164/178/775`, `app/crud.py` (location create/update ~1036/1104, read dicts 409/426/740/1316/2813/3330), `app/main.py:785/814`, `alembic/versions/061_*.py` |
| battle-service | only if the legal customs fight needs a new entry point (the caravan-raid endpoint requires the leader's `caravan` post gate and a free, unlocked leader) — possibly no migration if the existing `battles.caravan_raid_id` tag is reused | `app/main.py:1918-2003` (B1), `2006-2070` (end notify), `2368-2383` (`/result`), `6723` (join forbidden) |
| inventory-service / dungeon-service | byte-identical `econ_core.py` copy only (if a new op type is added); IS `activity_lock.py` only if a new lock reason is added | `app/econ_core.py`, `app/activity_lock.py` |
| frontend | location admin «Таможня» checkbox; economy admin: banned groups per country + new params + contraband flag in caravan list/detail + op label; NPC role «Таможенник» + modal; fence modal: smuggler escort hire; crime / fame / reputation labels | `components/AdminLocationsPage/EditForms/EditLocationForm/EditLocationForm.tsx` (is_port at 54/75/126/207/273/353/553), `components/Admin/EconomyPage/EconomyCaravans.tsx` (PairsCard 394-590), `components/Admin/EconomyPage/economyLabels.ts:49`, `constants/npc.ts:1-26`, `components/pages/LocationPage/NpcProfileModal.tsx:459/499`, `FenceModal/`, `CaravaneerModal/`, `CaravanSection.tsx`, `components/Admin/ReputationPage/shadowLabels.ts:3-14`, `types/economy.ts` |

### Existing Patterns
- character-service: sync SQLAlchemy, Pydantic v1, Alembic (head `054_sea_caravans`, `alembic_version_character`). Economy code = pure modules (`econ_caravan.py`, `caravan_route.py`, `patrol_core.py`, `sea_core.py`) + `*_crud.py` DB layers with raw SQL on foreign tables (`Locations`, `LocationNeighbors`, `Regions`, `action_gates` — plain reads, never locked) and documented global lock orders (`economy_caravan_crud.py:1-45`). Every caravan / raid / escort step is its own short transaction; idempotency via ledger `idempotency_key` (`caravan_key(id, part)`) and conditional UPDATE claims (`law_done`, `faction_done`, `rewards_done`).
- locations-service: async SQLAlchemy (aiomysql), Alembic head `060_sea_zones` (`alembic_version_locations`). Ports were added exactly the way a customs flag would be: column + index in `060_sea_zones.py:30-57`, model `models.py:142-155`, validation `crud.py:7187-7240` (`validate_sea_fields`), admin list `GET /locations/admin/sea-ports` (`main.py:4400-4412`, `require_permission("locations:read")`). Ports/zones are edited as locations — no new permission.
- battle-service: async; raid battles are `pve` battles tagged by a nullable int column (`caravan_raid_id` 010, `sea_raid_id` 011) and reported back to character-service internal callbacks (`X-Internal-Token`).
- Auth: player endpoints JWT + owner check (`caravan_api.py:110`, `caravan_escort_crud._player`); NPC flows also require the locations-service `npc_dialogue` post gate (`caravan_escort_api.py:71-85`, fail-closed) + NPC reputation tier gate; admin endpoints `require_permission("economy:read" / "economy:settings")` (`economy_api.py:1000-1020`).
- Sim params live in JSON `econ_sim_settings.params` (`models.py:762-769`) → new params need **no migration**: `econ_sim.SimParams` defaults (`econ_sim.py:~150-190`), bounds `schemas.py:~2100-2170` + update schema `~2592`, `CARAVAN_PARAM_KEYS` (`economy_caravan_crud.py:106-121`), frontend labels.
- NPC roles are free strings (`characters.npc_role String(50)`, `models.py:65`); a new role = backend constant + `constants/npc.ts` entry + a button in `NpcProfileModal.tsx` (pattern: `fence` 459, `caravaneer` 499, `captain` 519). Reputation NPC-kill weight falls back to `ROLE_FALLBACK` (−150) unless added to `reputation_core.DEFAULT_NPC_ROLE_WEIGHTS` (`reputation_core.py:108-118`).
- Crime types / fame sources / reputation actions are free strings (`law_crimes.crime_type String(30)` `models.py:1491`; fame `source String(30)`); reputation actions are DB rows seeded by migration (pattern: migration 051 added `caravan_escort` / `caravan_defense`; `reputation_core.DEFAULT_ACTIONS` `reputation_core.py:95-106`, LS copy must stay identical).

### 1. Routes, gates, mandatory waypoint, «Таможня» flag
- Pure routing: `caravan_route.py` — `build_adjacency` (`:22`), BFS `shortest_route(adj, blocked, start, goal, max_steps)` (`:37-67`; intermediate `blocked` nodes = dungeons never walked through, endpoints always allowed; reasons `no_gate|no_path|too_long`), `effective_gate(override, station)` (`:70-76`).
- Gates: `economy_caravan_crud.region_gates` (`:387-402`) — gate = `econ_regions.trade_gate_location_id` (admin override, A7 `PUT /admin/economy/caravans/gates/{region_id}`, `caravan_api.py:58`) else `Regions.jail_location_id` (guard station). Graph: `load_road_graph` (`:375-384`, two plain SELECTs on `LocationNeighbors` + `Locations.id, marker_type`).
- `RoutePlanner` (`economy_caravan_crud.py:432-521`), built once per tick caravan pass (`build_planner` `:524-532`, called from `econ_tick._caravan_pass` `econ_tick.py:1665`): `route(from_region, to_region)` (gate→gate BFS, cached), `_leg(start, goal)` (cached BFS between arbitrary nodes), `sea_route` (land1 + land2 via per-run sea pairs, best by length), `reach` (land → sea → abstract fallback by `caravan_no_path_abstract`).
- **Waypoint insertion precedent:** `SeaRoute` already concatenates two BFS legs (`land1 + land2`, `split_index`) — the same `_leg` cache can build `gate_A … post … gate_B` (minimal over the destination country's posts). The chosen route is stored on the row at dispatch (`dispatch` `:549-665`, `row.route`, `route_index`, `current_location_id`); a waypoint index column (like `sea_split_index`) would mark the post. Contraband routing = BFS with posts added to `blocked` (needs a new param or set on `RoutePlanner`; `shortest_route` already takes `blocked`). Note endpoints are always allowed — a buyer gate that is itself a customs post cannot be bypassed.
- Dispatch re-validates `planner.route` vs the plan kind (`:582-596`) — any new kind (contraband / via-post) must be re-checked there too.
- Ports flag (template for «Таможня»): LS `Location.is_port` (`models.py:142`), `ix_locations_is_port`; schemas `LocationCreate/Update/Read` (`schemas.py:120,137,164,178,775`); create/update normalisation (`crud.py:1036-1037`, `1104-1106`), read dicts (`crud.py:409,426,740,1316,2813,3330`; `main.py:785,814`); frontend checkbox `EditLocationForm.tsx:553`. CS reads LS columns by raw SQL with a **deploy-skew fallback chain** (`sea_crud.location_infos` `sea_crud.py:152-166`: full SELECT → without new columns → minimal). CS test fixtures create their own `Locations` DDL (`tests/econ_contract_cases.py:112,1435`, `tests/sea_world.py`, `test_feat171_character_visibility.py:179`, `test_admin_move_character.py:86`) — the new column must be optional in readers or added to those fixtures.

### 2. Duty today
- Planning: `econ_caravan.route()` (`econ_caravan.py:151-161`) — domestic: no duty; foreign: only for an enabled pair, `duty_pct` from `econ_trade_pairs`. `price_caravan` (`:164-171`) `duty = floor(value × duty_pct/100)`; buyer pays `value + duty (+ freight)` (`plan_caravans` `:305-323`, `clamp_dispatch` `:337-366`).
- Dispatch: op `caravan_dispatch` buyer purse (+ region treasury for food) → singleton `caravan_escrow` (`economy_caravan_crud.py:644-660`, key `caravan:c<id>:pay`).
- Delivery (abstract `finish` `:729-800`; physical `deliver_physical` `:915-965`): op `caravan_delivery` escrow → seller purse + escrow → **buyer country treasury** (`_country_or_world`, `:725`); after a raid the duty is pro-rated (`econ_caravan.remaining_payout` `:408-421`). Cancel refunds via `refund_split` (`:424-434`). Escrow sub-invariant: `escrow_expected` (`economy_caravan_crud.py:196-203`) = Σ(paid_purse + paid_treasury − raid_paid − freight_paid) of in-transit caravans.
- **Precedent for a mid-route escrow payout:** FEAT-215 sea freight `sea_cargo.charge_freight` (`sea_cargo.py:212-245`): own op `caravan_freight`, escrow → port region treasury (+ explicit country-tax leg), idempotent key, columns `freight_paid` / `freight_op_id`; then `remaining_payout(..., freight=)`, `refund_split(..., freight_paid)`, `raid_marks_cap` (`econ_caravan.py:437-439`) and `escrow_expected` all subtract it. A physical duty at the post needs the same set: `duty_paid` / `duty_op_id` columns, a payout escrow → country of the post (or of `to_country_id`), and every formula above (+ escort `_seller_part` `caravan_escort_crud.py:249-253`, `pools`) adjusted so the duty is not paid twice / not raidable after payment / not refunded on cancel. Abstract foreign caravans keep paying duty on delivery (no physical post).
- New op type → `econ_core.OP_*` + `CARAVAN_OP_TYPES` (`econ_core.py:155-164`, `OP_TYPES` `:194-203`) in 4 byte-identical copies (CS/IS/LS/dungeon; `scripts/check_econ_copies.sh`) + label `economyLabels.ts:49`. Alternative without a new op: a second `caravan_delivery`-type op with another key (Architect decision).

### 3. Trade groups / pairs / banned list / contraband planning
- Groups: `econ_goods_groups` (`models.py:562-578`, `code String(32)` PK) → `econ_sim.GroupDef` (`econ_sim.py:246`). Pairs: `econ_trade_pairs` (country_a < country_b, `is_enabled`, `duty_pct`; `models.py:1020-1033`), admin `PUT /admin/economy/caravans/pairs` (`economy_api.py:1008-1020`, `economy_caravan_crud.upsert_pair` `:1151-1170`, overview `:1104-1148`), frontend `PairsCard` (`EconomyCaravans.tsx:394-590`). Pairs are **symmetric**; a ban is **per destination country** — cannot live on the pair row.
- Per-country config precedent: `econ_mints` (one row per `Countries.id`, no FK, `models.py:977-988`). A banned-groups list fits as a new per-country table (or `country_id + group_code` rows); JSON list of codes is the `econ_fences.accepted_groups` pattern (`models.py:1243-1255`, normalised by `fence_crud.normalize_groups/parse_groups` `:67-93`).
- `plan_caravans` (`econ_caravan.py:217-334`) is pure and deterministic: per group, buyers by need level, candidates filtered by `route()` (pair rule) and `reach()`. Banned routing would be a branch at the candidate step (`:283-293`): legal candidate dropped when the buyer country bans the group; a share (param) of that demand becomes a contraband plan with `price × (1 + markup)` and no duty. `CaravanPlan` (`:88-117`) needs a kind/flag; `clamp_dispatch` recomputes value/duty from `unit_price`/`duty_pct` — a markup baked into `unit_price` survives it. Called twice in `_caravan_pass` (path-blind pre-plan `econ_tick.py:1661`, then with `reach` `:1675`) and the snapshot `load_snapshot` (`economy_caravan_crud.py:255-308`) carries `pairs` — the banned map must be loaded there too. UNIQUE `uq_econ_caravans_dispatch (run, from, to, group)` (`models.py:1093-1094`) — fine as long as a tuple is either legal or contraband in one run.
- Domestic trade currently ignores pairs entirely (`route()` same-country branch) — a ban as specified only touches imports.

### 4. Stop / hold mechanics
- Movement: `caravan_pass.step_caravan` (`caravan_pass.py:174-213`) every ~55 s (`RUN_INTERVAL_SECONDS`, claim on `econ_sim_settings.caravan_pass_last_run_at`): due rows (`next_move_at <= now`) advance one location; `next_move_at = now + step_delay` (`caravan_step_minutes` ± 25 %, `economy_caravan_crud.py:535-537`). Arrival = `index == len(route)-1` → `arrived_at` (delivery by `_deliver_arrived`).
- Gate departure window = simply a longer first `next_move_at` (`departure_delay`, `caravan_departure_minutes`, `:540-546`). A ~30 min inspection stop can be the same trick on arriving at the post index (`next_move_at = now + inspection_minutes`), plus a marker/column for UI and for charging the duty once. While standing it appears in `caravan_raid_crud.caravans_here` (`:170-213`; any physical caravan at the character's location, state + `departs_in_sec`) → raidable exactly like at the gate (raid still needs the RP post gate, `has_open_gate` `:219-229`).
- `held_by` (`economy_caravan_crud.py:1075-1087`) = raid active, or the FEAT-211 «post hold» (a pending RP post / open `caravan` action gate naming the caravan, one window `caravan_post_hold_max_min`, `hold_started_at`) — a different concept (holding for a writer), not the gate window.
- Edge cases in code: if the post is the **final node** (buyer gate) `step_caravan` sets `arrived_at` immediately (`:196-212`) — no stop; same for a sea caravan whose landing port is the buyer gate (`sea_cargo._unload` `sea_cargo.py:248-260` sets `arrived_at`). Inspection at the destination needs an explicit hold before arrival. Sea `waiting`/`aboard` stages skip stepping (`:181-183`).

### 5. NPC roles, escort hiring, fence, masking
- Escort hiring: «Караванщик» (`CARAVANEER_ROLE = "caravaneer"`, `caravan_escort_crud.py:58`), `resolve_caravaneer` (`:288-297`, NPC alive, same location), API gate order in `caravan_escort_api.py:11-85` (owner → `npc_dialogue` post gate over HTTP → NPC tier gate), `caravaneer_view` (`:374-398`) lists caravans **preparing at this location** (`_preparing_here` `:363-371`: physical, in transit, `route_index == 0`, never raided), `hire` (`:405-436`): checks seats (`caravan_escort_seats`), one job (`characters.escort_caravan_id`), activity lock, battle, gathering, wanted / reputation ≥ «Скиталец» in the **seller** region (`_character_refusal` `:335-360`). Pay: `pools` (`:240-246`) = `caravan_escort_fee_share` (+ bonus if repelled) of the seller part, paid inside the delivery op (`pay_plan` `:669-680`). Rewards: `reward_one` (`:763-824`; reputation `caravan_escort` in seller+buyer regions, defense rep + fame `SOURCE_CARAVAN_DEFENSE`, faction points).
- Fence «Скупщик» (`FENCE_ROLE = "fence"`, `fence_crud.py:32`): admin settings `econ_fences` (`price_pct`, `accepted_groups`, `cash_target`), refill in the tick; the player selling flow (bales) is in locations-service (`crud.py:5324-5440`). **A fence stands anywhere in its region, not necessarily at the trade gate**, while hiring today requires the caravan, NPC and player at the same gate location (`_caravan_refusal` `:314-323`). Fence-based hiring therefore needs a new rule (fence must stand at the gate, or a "meet at the gate" flow) — Architect question.
- Masking of escorts (FEAT-212): `caravan_escort_public.py` (public location = `hire_location_id`, lock hidden), used in public `short_info`/`public`/`list`/`profile`, user-service masked fetch, party by-location (see `DONE-FEAT-212` §3.6). Lock reason `caravan_escort` with a neutral message in 4 `activity_lock.py` copies. Caravan masking for strangers: `caravans_here` (`caravan_raid_crud.py:170-213`) shows only group, guard count, state, timer; LS post-gate text shows «Караван: <группа>» (`locations-service crud.py:4094-4103`). A contraband flag must stay out of these, out of `caravaneer_view`, and only appear in admin A4/A5 (`_caravan_out`/`caravan_detail` `economy_caravan_crud.py:1217-1424`) and the smuggler's own escort job view (`escort_job` `:457-511`).

### 6. Detection, legal fight, confiscation, payouts
- **No "внимательность" stat exists** (11 primary stats incl. `stealth` 009 in character-attributes; `docs/services/character-service.md:2289` says explicitly «Противовеса (внимательности стражи) нет»), and caravans have no stealth. Existing maths: `law_core.detection_chance` (`law_core.py:417-436`: base by marker × per-guard × (1 − stealth reduction) × fame/mask × level, clamped), `law_crud.stealth_info` (`law_crud.py:210-218`), `roll_succeeds` (`law_core.py:396-402`, RNG seam `law_crud.detection_rng`/`rng`).
- Triggers available: (a) caravan steps into a location — `step_caravan` (`caravan_pass.py:198-202`, caravan row locked only; detection + battle must run after commit); (b) a patrol guard steps into a location — `patrol_crud.step_guard` → `_sweep` (`patrol_crud.py:210-283`, today only sweeps players); (c) static guards at a location — `law_crud.guards_at` (`law_crud.py:492-494`). Patrol config/tables: `guard_patrols`, `guard_patrol_points` (`models.py:1564-1600`), law pass `law_pass._guard_patrols` (`law_pass.py:170`).
- Legal fight reuse: raid lifecycle `caravan_raid_crud` — `begin_raid` (`:267-310`, UNIQUE one raid per caravan `uq_econ_caravan_raids_caravan`, leader activity-lock check, RP gate check), `spawn_guards` (`:313-354`, hidden `dungeon` mobs from the guard pool + active escorts, ≤5), `battle_client.create_caravan_raid_battle` (`battle_client.py:72-98`) → BS `/battles/internal/caravan-raid` (`battle-service main.py:1918-2003`: requires leader at the location, not in battle, **not activity-locked**, **consumes the leader's `caravan` post gate** → 403 otherwise; battle type `pve` → no PvP crime), settlement `settle_raid` (`:586-658`: won → `_pay_out` marks from escrow `caravan_raid_marks_share` + stolen units → bales), `law_step` → `shadow_crud.caravan_raid_consequences` (crime `caravan_attack` for the raiders, `shadow_crud.py:318-419`), `raid_faction_points`, escort plan (`_escort_plan`/`_apply_escort_plan`). For customs all outcome branches differ (no crime for officer, crime for escorts, confiscation instead of loot) → a `kind` on `econ_caravan_raids` or a separate table; the UNIQUE "one raid per caravan" means a caravan inspected by customs could no longer be raided by bandits and vice versa (decision needed).
- Automatic (pass-driven) battle start precedent: `sea_raid_crud.start_raid` (`sea_raid_crud.py:323-370`) calls `asyncio.run(battle_client.create_sea_raid_battle(...))` from the scheduler thread, with claim / abandon / poll fallbacks — the template if customs detection should start the fight without the officer's click.
- Confiscation money/goods: caravan close goes through `cancel_physical` (`economy_caravan_crud.py:993-1016`, op `caravan_cancel`, goods back to origin, refund to buyer) or `deliver_physical`; neither fits "goods/value to the country treasury" — a new close branch/op is needed. Countries have only a marks treasury (`AccountRef.country`), no goods stock (stock is per region, `econ_region_goods`).
- Payouts: fame `renown_crud.add_fame` (`renown_crud.py:149`, free-string source; add e.g. `customs_seizure`), reputation `reputation_crud.apply_reputation` per **region** (no country-level reputation; echo via `echo_pct`), new action row via migration + `DEFAULT_ACTIONS` (CS + LS copies). Officer share: ledger leg → `AccountRef.character(cid)`.

### 7. Crime hooks
- `law_crud.register_crime` / `record_crime` (`law_crud.py:377-410`, idempotent by `event_key`, NPC skipped, infamy added) — single-member pattern ready in `sea_pass.register_stowaway_crime` (`sea_pass.py:228-258`; reported vs masked + suspicion), group pattern in `shadow_crud.caravan_raid_consequences`. New crime type constant in `law_core.py:33-43` (e.g. `smuggling`), label in `shadowLabels.ts:3-14`, weight as a param (stowaway uses `sea_settings.stowaway_wanted_points`). Crimes/wanted are per **region** (`law_crimes.region_id`, `read_wanted(…, region_id)` `law_crud.py:334`); "в этой стране" = region of the post / fight location.
- Escorts of a lost fight: `_escort_plan` already knows who fell / stayed; their character ids are on `econ_caravan_raids.escort_ids`.

### Cross-Service Dependencies
```
character-service ──raw SQL──> Locations (+ new is_customs), LocationNeighbors, Regions, Countries, action_gates, post_gate_requests (LS tables)
character-service ──HTTP──> battle-service POST /battles/internal/caravan-raid (or a new customs entry)  [X-Internal-Token]
battle-service ──HTTP──> character-service POST /characters/internal/caravans/raid-result (+ GET /battles/internal/{id}/result poll)
character-service ──HTTP──> locations-service npc_dialogue gate check (locations_client.check_npc_gate) for NPC flows
character-service ──HTTP──> inventory-service (bales delivery — only if confiscation/loot still produces bales)
locations-service ──raw SQL──> econ_caravans (post gate validation / labels), econ_fences (fence flows)
frontend ──> /characters/caravans/*, /characters/admin/economy/*, /locations/* (admin location edit)
```

### DB Changes
- character-service (migration `055_*`, revises `054_sea_caravans`; revision id ≤ 32 chars):
  - `econ_caravans`: contraband flag (+ markup info), customs waypoint (location id / route index), inspection marker (e.g. `customs_until` / `inspected_at`), `duty_paid` + `duty_op_id` (physical duty), confiscation result fields; index if queried by flag.
  - new table: per-country banned groups (pattern `econ_mints` / `accepted_groups` JSON).
  - new table: customs officer jobs / watches (character, post location, country, status, timestamps) — and possibly `characters.customs_*` column if it becomes an activity lock (would touch 4 `activity_lock.py` copies).
  - `econ_caravan_raids`: `kind` (raid | customs | patrol) and officer/payout columns, or a separate `econ_customs_checks` table.
  - seed rows: new `reputation_actions` (e.g. customs seizure), maybe `reputation_npc_role_weights` for `customs`.
  - Params (markup, contraband share, inspection minutes, detection chances, smuggler fee share, officer share, crime points) → JSON `econ_sim_settings.params`, no migration.
- locations-service (migration `061_*`, revises `060_sea_zones`): `Locations.is_customs BOOL NOT NULL DEFAULT 0` + index.
- battle-service: none if the `caravan_raid_id` tag is reused; a new tag column only if a separate customs battle type is chosen (head `011_battle_sea_raid`).
- inventory-service (`037_stolen_bales`), character-attributes-service (`009_add_stealth`): no changes expected (a new "внимательность" stat would need CAS migration `010_*` + inventory item modifier + stat caps copies — big; see questions).

### Risks
- **econ_core copies:** a new op type (e.g. `caravan_duty`, `caravan_confiscation`) must be added to all 4 byte-identical copies (CS, IS, LS, dungeon) — `scripts/check_econ_copies.sh` fails CI otherwise; `econ_contract_cases.py` copies likewise if touched; `reputation_core.py` CS↔LS identical if a reputation action is added.
- **activity_lock copies:** a customs-duty lock reason touches CS (canonical, differs), BS = LS (identical md5), IS (own fallback chain) — last fix `73cb1d6`; plus the BS raid endpoint refuses activity-locked leaders (`_ensure_not_activity_locked`), so an officer "on duty" lock would block the officer's own fight unless special-cased.
- **Money invariant:** physical duty and confiscation change `escrow_expected`, `remaining_payout`, `refund_split`, `raid_marks_cap`, escort `_seller_part`; missing one = escrow drift (checked by the economy invariant tests). Mitigation: mirror the FEAT-215 freight changes one-to-one.
- **Lock order:** new steps must follow the documented global order (`economy_caravan_crud.py` docstring: sea_ships → … → econ_caravans → econ_caravan_raids → escorts → … → characters (one sorted call) → econ_accounts); patrol step locks guard character first — a caravan check from the patrol path must run in a separate transaction after the guard commit (as `_sweep` does).
- **Deploy skew:** CS reads `Locations.is_customs` by raw SQL; LS migration may run after CS starts → fallback chain like `sea_crud.location_infos`. Single-head tests must be updated: CS `tests/test_sea_caravans_core.py:301`, `tests/test_admin_mob_region_ready.py:511`; LS `tests/test_sea_zones.py`.
- **Routing regressions:** inserting a post changes route lengths (`caravan_route_max_steps` → `too_long`), may make some pairs unreachable (edge case «пост недостижим») and changes `reach()` → planner tests in `test_econ_caravan.py`, `test_physical_caravans.py`, `test_sea_caravans*.py` will shift. Posts at the final node / landing port need an explicit pre-arrival hold.
- **Masking leaks:** contraband flag must not leak via `caravans_here`, `caravaneer_view`, LS post-gate labels, battle names/logs, CharacterLog of raiders, WS notices.
- **CI time:** character-service suite ~20 min locally vs CI `timeout-minutes: 25` (`.github/workflows/ci.yml:87`, per-test `--timeout=30`). New tests must reuse the `test_physical_caravans` / `test_caravan_raids` worlds and stay lean (FEAT-212 rule: a new file > ~60 s = refactor); pure logic tested in pure-module tests.
- **No attention stat / caravan stealth:** the brief's «внимательность против скрытности» has no backing data — needs a decision before design (see questions).

### Questions for the Architect (technical)
1. Customs fight: extend `econ_caravan_raids` with a `kind` (keeps BS tag `caravan_raid_id`, no BS migration, but UNIQUE one-raid-per-caravan) or a separate table + BS tag? Does the officer need the RP `caravan` post gate (BS consumes it today) or is the fight auto-started by the pass (`sea_raid_crud` pattern)?
2. Physical duty op: new op type (4 econ_core copies) or a keyed `caravan_delivery`-type op; duty to the post's country or to `to_country_id` (normally the same)?
3. Which post a legal caravan uses (nearest of the destination country, minimal total path), and handling of the post as final node / landing port; contraband BFS blocking all posts or only the destination country's.
4. Sea: legal sea caravan landing at a non-customs port of a country that has posts — reroute land2 through a post, or only customs ports inspect? Contraband sea caravan: choose a non-customs alight port (filter in `sea_route`) or drop to abstract/no deal?
5. Officer duty: activity lock (touches 4 copies, blocks travel) or a plain job row; can the officer move between border locations while on duty?
6. Fence hiring: fence must stand at the seller gate, or the hire is remote with a "go to the gate" step?

### Ambiguities for the user (few)
1. «Внимательность таможенника против скрытности каравана»: no such stat exists. Use an existing stat of the officer (e.g. intelligence/luck) vs a fixed/param caravan stealth (or the smuggler escorts' stealth), or add a new stat «Внимательность»?
2. Confiscation: goods have no country stock — should the confiscated cargo become marks in the country treasury (its value), or go as goods into the post region's market stock? And the buyer's prepaid money: refunded or forfeited?
3. «Тюки с налётов — контрабанда везде»: customs inspects only caravans, bales live in player inventories — does this mean fences ship bought bales out in contraband caravans, or simply that stolen goods are never legal trade? 
4. Patrol stop without players: plain confiscation (no fight), or a fight between the guard NPC and the smuggler escorts if there are any? And do contraband deals also happen between countries whose pair is closed (no trade at all), or only for banned groups of open pairs?

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Summary of decisions (answers to the Analyst's questions)

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| A1 | Customs fight: `kind` on `econ_caravan_raids` or a separate table + BS tag? | **`kind` column on `econ_caravan_raids`** (`raid` \| `customs` \| `patrol`), BS tag `battles.caravan_raid_id` reused → **no battle-service migration**, end-notify / `/result` / poll / expire / stale-start machinery reused as is. The UNIQUE "one raid row per caravan" is **kept**: a caravan has at most one fight in its life (bandit raid OR customs/patrol fight). | Every reader (`active_raid_status`, `held_by`, escort `repelled` bonus, `caravans_here`, `escort_job`, admin detail) keeps working unchanged; a repelled customs fight even gives smuggler escorts the existing "repelled" bonus for free. Cost: a contraband caravan that already fought (bandits or customs) cannot be fought again — listed as PM question Q1. |
| A2 | Does the officer need the RP `caravan` post gate? Who starts the fight? | **Officer: no post gate; the officer clicks «Досмотреть»** after a detection alert (see 3.6). **Patrol with player escorts: the pass starts the fight automatically** (FEAT-214 `sea_raid_crud.start_raid` pattern, `asyncio.run` from the scheduler thread, claim/abandon). Both go through one **new BS endpoint `POST /battles/internal/customs-fight`** (no gate consumption, enforcer side may be one player leader (+ free squad) or NPC guards). | Forcing an offline officer into a fight is bad UX; a short hold + click keeps agency, allows a group, and costs one endpoint. Patrols have no player on the enforcer side, so they must be server-started. A legal action must not consume an RP raid gate. |
| A3 | Physical duty ledger op | **New op `caravan_duty`** (escrow → country treasury, untaxed) and **new op `caravan_seizure`** (escrow → country treasury fine + escrow → officers' share) in `econ_core.CARAVAN_OP_TYPES` — all **4 byte-identical copies** (CS / IS / LS / dungeon, `scripts/check_econ_copies.sh`). | Ledger readability (admin op list, labels) and the FEAT-215 `caravan_freight` precedent; a keyed `caravan_delivery` would mislabel money that is not a delivery. |
| A4 | Duty goes to which country? | The **destination country** (`to_country_id`, via the existing `_country_or_world`) — the post is always chosen among the destination country's posts, so it is the post's country too. | Same account as today's on-delivery duty; no change for abstract caravans. |
| A5 | Which post a legal caravan uses | Only **foreign legal physical** caravans whose **destination country has ≥ 1 post** are routed via a post: the post `P` minimising `len(leg(gate_A, P)) + len(leg(P, gate_B))` (ties by location id) among that country's posts; total length still bounded by `caravan_route_max_steps`. No post reachable → no land route for this pair (→ sea, → `caravan_no_path_abstract` fallback, exactly like a missing road). Domestic caravans never visit customs. | Smallest deterministic rule, reuses the planner's cached `_leg`. |
| A6 | Post at the final node / at the landing port | Inspection is a **state of the caravan at its `customs_index`**, not a side effect of moving: the step that reaches `customs_index` starts the inspection instead of arriving; the next due step after `customs_until` clears it and only then arrives / moves on. A sea caravan landing at a customs port (`customs_index == sea_split_index + 1`) starts the inspection inside `sea_cargo._unload` (no instant `arrived_at`). | Covers final node, landing port and `customs_index == 0` with one rule. |
| A7 | Sea routing (legal) | Legal sea caravan to a country with posts: `land2` must pass a post of that country — the landing port itself if it is a customs port, else `leg(alight, P) + leg(P, goal)`; the best (board, alight, P) by total length. | "Порт с таможней досматривает всё, что приходит морем" + no silent bypass via a non-customs port. |
| A8 | Contraband routing | **Physical only** (no abstract contraband — there would be nothing to detect). Land: BFS with `blocked ∪ all_posts` (all countries' posts); **the buyer gate must not be a post** (else no contraband deal for that region); the seller gate may be a post (exports are not inspected). Sea: legs avoid posts the same way, the **alight port must not be a customs port**, the board port may be anything. Contraband uses `caravan_physical_max_active` slots (+ sea slots) like any physical caravan; physical caravans off → no contraband. | Smugglers avoid every post; endpoint rule from the Analyst (BFS endpoints are always allowed). |
| A9 | Officer duty — activity lock? | **No activity lock** — a plain job row `econ_customs_officers`. The officer is "on watch" whenever he stands in a location of his country, is not in battle and is not activity-locked (jail, unconscious, escort…). He travels, fights, gathers freely. → **no `activity_lock.py` copy is touched.** | The BS raid/customs endpoints refuse activity-locked leaders; a lock would block the officer's own fight and cost 4 copies. |
| A10 | Fence hiring location | Hire at the fence **anywhere in the fence's region**; the fence lists contraband caravans *preparing* (`route_index 0`, departure window) at **its region's trade gate**; on hire the character is **moved to the caravan** (raw write like `move_escorts`; "Скупщик проводит вас к каравану"), `hire_location_id` = the fence's location (the FEAT-212 public mask then shows him at the fence). Same endpoint as the caravaneer hire (`POST /caravans/{id}/escort/hire` with the fence's `npc_id`). | Fences stand anywhere; no new "meet at the gate" step. |
| A11 | Patrol detection without player officers | On every contraband caravan **step into a location that is not its final node**, guard NPCs at that location (`law_crud.guards_at`, static or patrolling) of a country where the goods are illegal roll a small chance. Success: no active player escorts → **confiscation without a fight**; escorts present → auto fight guards (team 0, ≤ 5) vs escorts (team 1, no caravan mobs). BS answers 409 "no defenders" (all escorts unavailable) → confiscation without a fight. | User decision; trigger is the caravan step (no change in `patrol_crud`). |
| A12 | Where the goods are illegal | A contraband caravan is illegal in country X iff `X == to_country_id` **or** its group is banned in X. Officers/guards of X detect it only inside X's territory. | Covers "into the banning country" and closed-pair smuggling with one rule. |
| A13 | Detection formula (user decision) | `customs_core.detection_chance(base, attention_pct, reduction_pct, lo, hi) = clamp(base × (1 + attention/100) × (1 − reduction/100), lo, hi)` (2 decimals); `attention_pct = shadow_core.stealth_reduction_pct(officer effective stealth)` (officer's «внимательность» = his stealth, same curve as the guards' stealth maths); `reduction_pct = stealth_reduction_pct(customs_caravan_stealth + max effective stealth of active escorts)` (`law_crud.stealth_info`). Patrol: `clamp(customs_patrol_detect_pct × (1 − reduction/100), 0, hi)`. Roll = `law_core.roll_succeeds` with an RNG seam `customs_crud.rng`. | "Как у стражи": same stealth curve and roll; pure function, unit-testable. |

### 3.1 Contraband lifecycle (state machine)

Caravan columns (new): `is_contraband`, `customs_state` (`NULL` no post | `pending` | `inspecting` | `cleared`), `customs_alert_*`, `seized_*`.

```
LEGAL foreign physical caravan with a post on its route (customs_state = pending):
  dispatch ─► steps … ─► reaches customs_index ─► INSPECTING (customs_until = now + customs_inspection_minutes,
             duty charged: op caravan_duty escrow → to-country, duty_paid set)        [raidable like at the gate]
           ─► next due step ≥ customs_until ─► CLEARED ─► moves on / arrives (if the post is the final node) ─► delivery
             (delivery pays the seller only; duty part = 0 because duty_paid is settled)

CONTRABAND caravan (is_contraband = 1, never has a post, duty = 0, unit_price × (1 + markup)):
  dispatch ─► departure window at seller gate (smugglers hired at the fence) ─► steps …
     each step into a non-final location of a country where it is illegal → CHECK (after the step commit):
       officer on watch rolls OK ─► ALERT (customs_alert_officer_id, customs_alert_until = now + customs_alert_minutes;
                                    held_by = "customs", caravan does not move)
            officer clicks «Досмотреть» in time ─► fight kind=customs (officer[+free squad] vs caravan mobs + escorts)
                 won  ─► SEIZED (caravan cancelled, reason seized_customs) + escort crimes + officer share/fame/rep
                 repelled ─► moves on (one fight per caravan → never checked/raided again); escorts get the bonus
                 aborted/expired ─► as raids today
            alert expires ─► moves on (may be detected again at the next location)
       else guards roll OK:
            no active escorts (or BS 409 no defenders) ─► SEIZED (reason seized_patrol), no crime, no reward
            escorts ─► auto fight kind=patrol (guards vs escorts) ─► won: SEIZED + escort crimes; repelled: moves on
  ─► arrives ─► delivery (seller gets value incl. markup minus the smuggler escorts' pay)
```

Abstract caravans: unchanged (legal foreign abstract caravans still pay the duty on delivery; contraband is never abstract).

### 3.2 Money invariants

Escrow sub-invariant becomes `escrow == Σ (paid_purse + paid_treasury − raid_paid − freight_paid − duty_paid)` of in-transit caravans (`escrow_expected`).

* **Duty at the post** (`customs_crud.charge_duty`, inside the step / unload transaction, after the caravan + escort/character locks): `_, duty_now = econ_caravan.remaining_payout(value, duty, paid_total, raid_paid, freight=freight)` (pro-rated if raided before the post) → op `caravan_duty`, legs `escrow → _country_or_world(to_country_id)`, `apply_tax=False`, key `caravan:c<id>:duty`, `location_id` = post; `duty_paid = duty_now`, `duty_op_id`. Duty 0 → no op, still `duty_paid = 0` and state `inspecting`.
* **Pure helper changes** (`econ_caravan.py`, all mirrored on FEAT-215 freight):
  * `remaining_payout(value, duty, paid_total, raid_paid, freight=0, duty_paid=None)` — `duty_paid is None` = not settled (today's behaviour); an int = settled: returns `(paid_total − freight − raid_paid − duty_paid, 0)` (≥ 0).
  * `refund_split(paid_purse, paid_treasury, raid_paid, freight_paid=0, duty_paid=0)` — `duty_paid` leaves pro rata like freight.
  * `raid_marks_cap(paid_total, freight, raid_paid, duty_paid=0)`.
  * Callers: `deliver_physical`, `_cancel_legs`, `caravan_raid_crud._pay_out`, `caravan_escort_crud._seller_part`, `escrow_expected`, admin detail — pass `duty_paid` when `customs_state in ('inspecting','cleared')`, else `None`/0.
* **Seizure** (`customs_crud.confiscate`, op `caravan_seizure`, key `caravan:c<id>:seize`, untaxed): `R = paid_total − raid_paid − freight_paid − duty_paid` (the whole escrow rest; a reserved-but-uncharged sea freight is part of it). `officer_pool = floor(R × customs_officer_share)` for kind `customs` (0 for `patrol`), split `floor(pool / n)` among the fight's player attackers (`raid.attacker_ids` ∩ players); remainder + `R − pool` → `AccountRef.country(seizure country)` (location of the fight / check; no country → world). The buyer gets nothing back (user decision). Goods `units − stolen − sunk` → `econ_region_goods` of the **seizure region** (if it participates and has the group row), else back to the origin region, else written off (log) — same fallback style as `_cancel_legs`. Caravan → `status = cancelled`, `cancel_reason = seized_customs | seized_patrol`, `finish_op_id` = the seizure op, `seized_region_id`, `seized_country_id`; active escorts → `cancelled` via `cancel_escorts` (no pay).
* **Contraband pricing**: `unit_price = round4(price × (1 + customs_contraband_markup_pct/100))`, `duty_pct = 0`, `duty = 0`; `clamp_dispatch` keeps the baked-in price. Freight applies to contraband sea caravans as usual.
* **Smuggler pay**: `pools()` uses `customs_smuggler_fee_share` instead of `caravan_escort_fee_share` when `is_contraband` (bonus share unchanged); paid inside the delivery op as today.
* **Refunds**: a legal caravan cancelled after the post refunds `paid − raid_paid − freight_paid − duty_paid` (duty already in the treasury stays there). Seizure never refunds.

### 3.3 Lock order (supersedes FEAT-215 §3.6)

`sea_ships → sea_passes → econ_regions (asc) → econ_region_goods (asc) → econ_region_events → econ_caravans (asc) → econ_caravan_raids → econ_caravan_escorts (asc) → econ_customs_officers (asc character_id) → econ_caravan_raid_shares → econ_caravan_sea_losses → sea_raids → … → characters (asc, ONE sorted call) → econ_accounts (asc) → character_attributes`.

* Step tx (duty): `econ_caravans(row) → escorts → characters (move_escorts) → econ_accounts`.
* Unload tx (duty at a customs landing port): existing `_settle_hold` order; the duty legs post after the freight, same tx.
* Alert tx: `econ_caravans(row)` only.
* Inspect start (Tx A of the fight): `econ_caravans(row) → [INSERT econ_caravan_raids]`; alert columns cleared in the same tx.
* Settlement: existing `settle_raid` (caravan → raid → escorts → characters → accounts). For `customs`/`patrol` kinds no money moves here.
* Seizure tx: `econ_regions (asc: seizure, from, to) → econ_region_goods (asc) → econ_caravans(row) → escorts → econ_customs_officers (asc) → characters (one sorted call: escorts ∪ paid officers) → econ_accounts`. Skipped (retried) while an economy run is `running`, exactly like `_deliver_arrived`.
* Enlist / resign: `econ_customs_officers(row) → characters(row)`. `econ_country_bans` is never locked (admin replace = DELETE + INSERT in one tx). Locations-service tables stay plain reads.
* Detection rolls are plain reads; HTTP to battle-service is always outside any transaction.

### 3.4 DB Changes

**locations-service — `061_customs_posts`** (revises `060_sea_zones`):
```sql
ALTER TABLE Locations ADD COLUMN is_customs TINYINT(1) NOT NULL DEFAULT 0;
CREATE INDEX ix_locations_is_customs ON Locations (is_customs);
-- downgrade: DROP INDEX ix_locations_is_customs; DROP COLUMN is_customs
```
Model `Location.is_customs`; `LocationCreate/Update/Read` (+ every read dict that already carries `is_port`: `crud.py:409,426,740,1316,2813,3330`, `main.py:785,814`); create/update normalisation like `is_port`. Validation: a customs flag is refused (400 «Таможня не может стоять на корабле или в море») on ship locations and sea-zone locations (same detection as `validate_sea_fields`). No new permission (location edit). Single-head test `tests/test_sea_zones.py` → `061_customs_posts`.

**character-service — `055_customs_smuggling`** (revises `054_sea_caravans`; id ≤ 32 chars; idempotent `_has_column`/`_has_table` guards like 051/054):
```sql
ALTER TABLE econ_caravans
  ADD COLUMN is_contraband TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN markup_pct DECIMAL(6,2) NULL,
  ADD COLUMN customs_index INT NULL,                 -- route index of the post (NULL = no post)
  ADD COLUMN customs_location_id BIGINT NULL,
  ADD COLUMN customs_state VARCHAR(16) NULL,         -- pending | inspecting | cleared
  ADD COLUMN customs_until DATETIME NULL,
  ADD COLUMN duty_paid INT NOT NULL DEFAULT 0,       -- same type as freight_paid
  ADD COLUMN duty_op_id BIGINT NULL,
  ADD COLUMN customs_alert_officer_id INT NULL,
  ADD COLUMN customs_alert_until DATETIME NULL,
  ADD COLUMN seized_region_id INT NULL,
  ADD COLUMN seized_country_id INT NULL;
CREATE INDEX ix_econ_caravans_contraband ON econ_caravans (is_contraband, status);

ALTER TABLE econ_caravan_raids
  ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'raid',    -- raid | customs | patrol
  ADD COLUMN officer_paid INT NOT NULL DEFAULT 0,
  ADD COLUMN seized_done TINYINT(1) NOT NULL DEFAULT 0;   -- confiscation claim (followups)
-- uq_econ_caravan_raids_caravan stays (one fight per caravan)

CREATE TABLE econ_country_bans (
  country_id INT NOT NULL, group_code VARCHAR(32) NOT NULL, created_at DATETIME NOT NULL,
  PRIMARY KEY (country_id, group_code)               -- no FKs (econ_mints style)
);
CREATE TABLE econ_customs_officers (
  character_id INT NOT NULL PRIMARY KEY, country_id INT NOT NULL,
  npc_id INT NULL, location_id BIGINT NULL,          -- where he enlisted
  status VARCHAR(16) NOT NULL,                       -- active | resigned
  enlisted_at DATETIME NOT NULL, ended_at DATETIME NULL,
  seizures INT NOT NULL DEFAULT 0, earned BIGINT NOT NULL DEFAULT 0,
  INDEX ix_econ_customs_officers_country (status, country_id)
);
-- seeds (insert-if-missing, delete on downgrade):
--   reputation_actions: ('customs_seizure', 'Конфискация контрабанды', 20, NULL, is_builtin=1, has_source=1, 57)
--   reputation_npc_role_weights: ('customs', -300)  (if the table has role rows)
```
Rollback: downgrade drops the new tables/columns/index and the seed rows. Single-head tests: `tests/test_sea_caravans_core.py:301`, `tests/test_admin_mob_region_ready.py:511` → `055_customs_smuggling`.

**battle-service**: none. **inventory / dungeon / character-attributes**: none (only the `econ_core.py` copy).

**Deploy skew**: CS reads `Locations.is_customs` by raw SQL with a fallback (column missing → no posts at all), like `sea_crud.location_infos`. CS test fixtures that create their own `Locations` DDL keep working without the column.

### 3.5 New sim params (`econ_sim_settings.params` JSON — no migration)

Added to `econ_sim.SimParams`, bounds in `schemas.py` (`~2100-2170` + the update schema), a new `CUSTOMS_PARAM_KEYS` tuple next to `CARAVAN_PARAM_KEYS` (same admin caravan params card), frontend labels + hints.

| key | type | default | bounds | meaning |
|-----|------|---------|--------|---------|
| `customs_enabled` | int | 1 | 0–1 | master switch: posts route/inspect, contraband planned, detection runs |
| `customs_inspection_minutes` | int | 30 | 0–240 | stop at the post (0 = duty without a stop) |
| `customs_contraband_share` | float | 0.3 | 0–1 | share of a blocked deal (banned group / closed pair) that goes to smugglers |
| `customs_contraband_markup_pct` | float | 50 | 0–500 | contraband price markup |
| `customs_caravan_stealth` | int | 20 | 0–200 | base stealth of a contraband caravan |
| `customs_detect_base_pct` | float | 35 | 0–100 | officer base chance |
| `customs_detect_min_pct` | float | 5 | 0–100 | clamp (validated min ≤ max) |
| `customs_detect_max_pct` | float | 90 | 0–100 | clamp |
| `customs_patrol_detect_pct` | float | 5 | 0–100 | guards' chance (before the caravan's stealth) |
| `customs_alert_minutes` | int | 10 | 1–60 | how long a detected caravan waits for the officer's «Досмотреть» |
| `customs_officer_share` | float | 0.2 | 0–1 | officers' share of the fine |
| `customs_seizure_fame` | int | 30 | 0–1000 | fame per seizure (source `customs_seizure`) |
| `customs_smuggler_fee_share` | float | 0.10 | 0–0.5 | smuggler escort pay pool (vs 0.05 legal) |
| `customs_smuggling_wanted_points` | int | 40 | 0–1000 | wanted points of the `smuggling` crime |

### 3.6 Backend design by module

**Pure modules**
* `econ_caravan.py`: `CaravanPlan.contraband: bool = False`, `markup_pct: float = 0.0`; `plan_caravans(..., bans=None, contraband_reach=None)`: at the candidate step, for a foreign pair: legal candidate iff `route()` allows it **and** the group is not in `bans[buyer_country]`; otherwise, when `contraband_reach` is given and `customs_enabled` and `share > 0`, a contraband candidate with `travel_runs = caravan_travel_foreign`, duty 0, marked-up price, `want = floor3(min(need, supply) × share)`, `how = contraband_reach(seller, buyer)` (None → no candidate). Candidates sort legal before contraband (extra rank key). Sea contraband consumes `sea_slots`. `bans is None` / `contraband_reach is None` → exactly today's output (all existing tests stay green). Money helpers per 3.2.
* `customs_core.py` (new, pure): constants (kinds, states, reasons, crime type alias), `detection_chance`, `patrol_chance`, `caravan_stealth(base, escort_effective_stealths)`, `illegal_in(country_id, caravan_to_country, group_code, bans)`, `officer_split(pool, n)`, `normalize_ban_codes(codes, known)`.
* `law_core.py`: `CRIME_SMUGGLING = "smuggling"`. `shadow_core.py`: `SOURCE_CUSTOMS_SEIZURE = "customs_seizure"`. `reputation_core.py` (CS **and** LS copy, identical): `ACTION_CUSTOMS_SEIZURE` in `DEFAULT_ACTIONS` (`"Конфискация контрабанды", 20, None, True, 57`) and `"customs": -300` in `DEFAULT_NPC_ROLE_WEIGHTS`.
* `econ_core.py` ×4: `OP_CARAVAN_DUTY = "caravan_duty"`, `OP_CARAVAN_SEIZURE = "caravan_seizure"` in `CARAVAN_OP_TYPES`.

**Planner / dispatch (`economy_caravan_crud.py`, `econ_tick.py`)**
* `region_gates` also returns the region's `country_id`; `load_customs_posts(db)` → `{country_id: [location ids]}` + `customs_ports` set (`is_customs AND is_port`) with the is_customs-missing fallback; `load_bans(db)` → `{country_id: frozenset(codes)}` (table missing → `{}`), carried on `Snapshot.bans`.
* `RoutePlanner(..., posts_by_country, customs_ports, customs_enabled)`: `legal_route(from, to) -> (route, customs_index) | (None, reason)` (A5, cached), `sea_route` gains the post-on-land2 rule (A7) and returns `customs_index`; `contraband_route` / `contraband_sea_route` / `contraband_reach` (A8, caches keyed separately); `reach` uses `legal_route`. `customs_enabled = 0` → today's behaviour exactly.
* `econ_tick._caravan_pass`: pass `bans` and, when customs is on, `contraband_reach` to both `plan_caravans` calls (the path-blind pre-plan uses an always-land `contraband_reach` so closed-pair contraband is not lost by the early exit).
* `dispatch`: contraband plans re-validated (still foreign, still blocked — closed pair or banned —, `planner.contraband_*` route exists, physical slot free) else `skipped`; legal plans skipped when the group became banned. Stores `is_contraband`, `markup_pct`, and for legal routes with a post `customs_index`, `customs_location_id`, `customs_state = 'pending'`. Contraband → `choose_physical` bypassed (always physical).

**Inspection (`caravan_pass.step_caravan`, `sea_cargo._unload`, `customs_crud`)**
* `customs_crud.start_inspection(db, row, now, params)` (charges duty, `customs_state='inspecting'`, `customs_until`, `next_move_at = customs_until`); called by the step when the new index (or the current one on a due step) equals `customs_index` with state `pending` — before the "arrived" branch; due step at `customs_index` with state `inspecting` → `cleared`, then the normal arrive/move logic. `_unload` calls it when the landing index equals `customs_index`.
* `settle_raid` (any kind): `next_move_at = max(now + step_delay, customs_until)` while inspecting. `held_by` gains `"customs"` (open, unexpired alert); a customs hold never sets `hold_started_at` (that is the RP post window).
* `caravans_here`: new state `inspection` (legal caravans only, so nothing leaks) with `departs_in_sec` = time to `customs_until`; new fields `can_inspect` (true only for the alerted officer, alert open) and `inspect_in_sec`. `escort_job`: state `inspection`, plus `is_contraband` (the escort's own job only).

**Officer job & admin (`customs_crud.py`, `customs_api.py`, new; router in `main.py`)** — see API 3.7. Enlist checks (in order): owner/player → NPC role `customs` alive, same location, NPC location has a region with a country → `npc_dialogue` gate (HTTP, fail-closed) → NPC tier gate → not already an active officer (of any country) → not activity-locked / not in battle → not wanted in the NPC's region → reputation ≥ «Скиталец» there. Resign: anytime, anywhere. Officers who become wanted are not dismissed, they just do not roll while wanted in the location's region.

**Detection, fights, seizure (`customs_crud.py` + hooks)**
* `caravan_pass`: `_step_caravans` collects the ids it moved (`moved` outcome, not `arrived`); new step `_customs_checks(factory, ids, now, params, rng)` runs **after the step loop and before `_deliver_arrived`**, each caravan best effort in its own transactions: read → officers' rolls → alert tx + notice/CharacterLog to the officer («Вы заметили подозрительный караван (<группа>). Досмотрите его в течение N мин»); else guards' roll → patrol: no escorts → `confiscate_tx(kind=patrol)`; escorts → `begin_check` (raid row `kind='patrol'`, `leader_character_id` = first guard) → `battle_client.create_customs_battle` (`asyncio.run`) → `mark_fighting` / `abandon_start`; BS 409 `no_defenders` → abandon + confiscate. Skipped entirely while an economy run is `running` (no roll at all for that step).
* Officer `POST /caravans/{id}/inspect` (API handler, async like the raid start): `begin_check(kind='customs')` (caravan locked: contraband, in transit, not arrived, no raid row, alert open for **this** officer, officer at the caravan's location, officer active and not locked) — every failure is the generic 404 «Здесь нечего досматривать» (no contraband leak) except lock/battle (409 own text) → clears the alert → `spawn_guards` (unchanged: mobs + active escorts) → `create_customs_battle(leader=officer, group)` → `mark_fighting`; failures → `abandon_start` (alert NOT restored; caravan moves on).
* `settle_raid` branches by `kind`: `raid` unchanged. `customs`/`patrol`: `won` → no `_pay_out`; escort plan as today (`won` → all placed escorts fall out); caravan frozen (`next_move_at = NULL`); notices («Контрабанда задержана» to officers, escorts as today). `repelled` → caravan moves on; officer notice «Контрабандисты отбились». `aborted`/`expired` as today.
* `raid_followups` for won `customs`/`patrol` raids: (1) `confiscate_tx` claimed by `seized_done` + op idempotency (postponed while an economy run is `running`); (2) `law_step` → `customs_crud.consequences` (claims `law_done`): `smuggling` crime (`register_crime`, status `reported`, points `customs_smuggling_wanted_points`, `event_key = law:smuggling:r<raid>:<cid>`, region = `raid.region_id`) for every escort of the caravan whose row ended `fallen` or `cancelled`; for `customs` kind: each player attacker gets fame `customs_seizure_fame` (`renown_crud.add_fame`, source `customs_seizure`, key `fame:customs:r<raid>:<cid>`) and reputation `customs_seizure` in the seizure region (`echo=True`, key per raid/character), `econ_customs_officers.seizures/earned` updated for enlisted ones inside the seizure tx. `raid_faction_points` and `deliver_bales` are skipped for non-`raid` kinds. Notices published after commits.
* `raid_share_by_battle`: `raid = False` for non-`raid` kinds (the victory window shows ordinary PvE rewards).
* Patrol fights: the guards defeated by escorts follow the existing battle-end rules for NPC guards (e.g. a `guard_defeat` crime through the usual hooks) — no special casing.

**Smugglers at the fence (`caravan_escort_crud.py`, `caravan_escort_api.py`)**
* `resolve_caravaneer` → `resolve_hiring_npc` accepting role `caravaneer` or `fence` (context carries `role`, `region_id`).
* `caravaneer_view` / caravaneer hire: contraband caravans excluded (they never appear at a caravaneer).
* New `smuggler_view(ctx)` (`GET /caravans/fence/{npc_id}`): contraband caravans preparing at the trade gate of the fence's region (`from_region_id = fence region`, `route_index 0`, no raid row), same item shape as the caravaneer view + `gate_location_name`; pay estimate from `customs_smuggler_fee_share`.
* `hire` with a fence context: caravan must be contraband from the fence's region and preparing at its gate; `_character_refusal` without the wanted / reputation checks, plus refusal «Вы служите на таможне» for an active officer; inserts the escort row with `hire_location_id = fence location`, then moves the character to `caravan.current_location_id` (raw write, `house_room_id = NULL`, same as `move_escorts`). CharacterLog «Нанялся в охрану каравана у скупщика».
* `pools()` picks the smuggler fee share for contraband; `reward_one` for contraband: no reputation, no defense fame, no faction deed — pay only (row still marked `rewards_done`).
* Masking audit (acceptance): `is_contraband` must not appear in `caravans_here`, `caravaneer_view`, LS post-gate labels, battle names/logs, raiders' CharacterLog/notices, `caravan_escort_public`, WS notices to anyone except the escort himself and the alerted/winning officer; admin A4/A5 and region-card lines show it only in admin.

### 3.7 API Contracts

All player endpoints: JWT (`get_current_user_via_http`) + owner check (`character_id` belongs to the user, player character). NPC flows: `npc_dialogue` post gate (fail-closed) + NPC tier gate, in the FEAT-212 order. Errors in Russian, no internals.

#### C1 `GET /characters/customs/officer/{npc_id}?character_id=` — the «Таможенник» window
```json
{ "npc_id": 1, "country_id": 2, "country_name": "…", "location_id": 10,
  "job": { "country_id": 2, "country_name": "…", "status": "active", "enlisted_at": "…", "seizures": 3, "earned": 450 } | null,
  "can_enlist": true, "reason": null,
  "params": { "officer_share": 0.2, "alert_minutes": 10 } }
```
404 NPC not found / not a customs NPC, 400 not at the NPC, 403 gate / tier.

#### C2 `POST /characters/customs/officer/{npc_id}/enlist` — body `{ "character_id": 5 }` → 201 `{ "job": {…} }`
409 already an officer / locked / in battle; 403 wanted / reputation / gates. Idempotent by PK (an `active` row → 409 «Вы уже служите на таможне»).

#### C3 `POST /characters/customs/resign` — body `{ "character_id": 5 }` → 200 `{ "ok": true }` (409 «Вы не служите на таможне»).

#### C4 `GET /characters/customs/job?character_id=` → `{ "job": {…} | null }`

#### C5 `POST /characters/caravans/{caravan_id}/inspect` — body `{ "character_id": 5, "group": false }` → 201 `{ "raid_id": 7, "battle_id": 99 }`
404 «Здесь нечего досматривать» (any non-eligibility that could reveal contraband), 409 lock / in battle / already fighting, 503 battle-service down. **Rate limit**: nginx — extend the FEAT-211 location regex to `^/characters/caravans/\d+/(raid|inspect)$` (zone `caravan_raid_limit`, 6 r/m, burst 3) in `nginx.conf` **and** `nginx.prod.conf`.

#### C6 `GET /characters/caravans/here` (changed, additive)
Items gain `"can_inspect": false, "inspect_in_sec": null`; `state` may be `"inspection"`.

#### C7 `GET /characters/caravans/fence/{npc_id}?character_id=` — smuggler hire list
Same shape as `CaravaneerViewOut` (`npc_id, location_id, my_escort_caravan_id, seats_enabled, caravans[{id, group_code, group_name, departs_in_sec, has_seats, pay_estimate, can_hire, reason}]`) + `gate_location_id`, `gate_location_name`. 404 not a fence, 400 not at the fence, 403 gates.

#### C8 `POST /characters/caravans/{caravan_id}/escort/hire` (changed) — body unchanged `{ character_id, npc_id }`; `npc_id` may be a fence. Response `EscortJobOut` + `"is_contraband": bool` (also in C9).

#### C9 `GET /characters/caravans/escort` (changed, additive) — `is_contraband`, `state` may be `inspection`.

#### A1 `GET /characters/admin/economy/caravans/customs` — `require_permission("economy:read")`
```json
{ "countries": [ { "country_id": 2, "name": "…", "banned_groups": ["weapons"],
                   "posts": [ { "location_id": 10, "name": "…", "is_port": false } ] } ],
  "groups": [ { "code": "weapons", "name": "Оружие" } ] }
```

#### A2 `PUT /characters/admin/economy/caravans/customs/{country_id}` — `require_permission("economy:settings")`
Body `{ "banned_groups": ["weapons"] }` (list, ≤ 64, each a known `econ_goods_groups.code`, deduped; empty = no bans) → the country item. 404 unknown country, 400 unknown code.

#### A3 (changed, additive) caravan list / detail (`_caravan_out`, `caravan_detail`): `is_contraband`, `markup_pct`, `customs_state`, `customs_location_id/name`, `duty_paid`, `seized_region_id/name`, `seized_country_id`; `cancel_reason` ∈ `+ seized_customs | seized_patrol`; detail `raid.kind`, `raid.officer_paid`. Optional list filter `kind=contraband` (A4 `kind` param gets one more value).

#### A4 (changed) params GET/PUT — the 14 new keys of 3.5.

#### B1 battle-service `POST /battles/internal/customs-fight` — `X-Internal-Token` (nginx already blocks `/battles/internal/` outside)
Request (Pydantic v1):
```json
{ "caravan_raid_id": 7, "caravan_id": 3, "location_id": 10,
  "leader_character_id": 5 | null, "group": false,
  "enforcer_npc_ids": [] , "guard_character_ids": [101, 102], "escort_character_ids": [6] }
```
Exactly one of `leader_character_id` / non-empty `enforcer_npc_ids` (else 400). Leader: same checks as B1 caravan-raid (at the location, not in battle, `_ensure_not_activity_locked`), attackers = leader or `_free_squadmates` when `group`, escorts filtered out of attackers; **no action-gate consumption**. Enforcer NPCs and guard mobs: `_ensure_caravan_guards`. Escorts: `_escort_available`. NPC-enforcer mode with zero placed escorts → 409 `«Защитников каравана нет»` (CS confiscates without a fight). Team-size check per team ≤ `BATTLE_MAX_TEAM_SIZE` (400). Battle `pve`, tagged `caravan_raid_id` (existing end notify / `/result` unchanged), escorts flagged `autobattle_forbidden`. Response = `CaravanRaidBattleCreated` shape (`battle_id, participants, next_actor, deadline_at, attacker_character_ids, escort_character_ids`). CS `battle_client.create_customs_battle(...)`.

#### Locations-service (changed): `POST/PUT /locations/...` location create/update and reads carry `is_customs: bool` (existing `locations:create/update` permissions).

### 3.8 Security Considerations
* **Auth**: all player endpoints JWT + ownership; NPC windows behind the dialogue gate + tier gate; admin endpoints `economy:read` / `economy:settings` (existing permissions → no RBAC migration, no new rows in `permissions`); internal BS endpoint `X-Internal-Token`.
* **Rate limiting**: inspect shares the raid zone (6 r/m); the enlist/resign/hire endpoints are idempotent and lock-protected (no zone, like FEAT-212 hire).
* **Validation**: Pydantic `ge=1` ids; ban codes checked against the groups table; params bounds; LS validation of the flag.
* **Information leaks**: contraband is server-side only; inspect returns one generic 404 for every reason that could reveal a caravan is contraband; the alert notice goes only to the detecting officer.
* **Abuse**: one fight per caravan; an officer cannot be a smuggler at the same time (both-way refusal); BS removes escorts from the attacker side (same user's squad); officer share is only paid from a won fight; patrol confiscation pays nobody.

### 3.9 Frontend Components (all TypeScript, Tailwind, design-system classes, no `React.FC`, 360px+, every API error shown in Russian)
* `components/AdminLocationsPage/EditForms/EditLocationForm/EditLocationForm.tsx` — «Таможня» checkbox next to «Порт» (+ type `is_customs`). If the form still has SCSS for that block, follow T1 for the touched markup.
* `components/Admin/EconomyPage/CustomsBansCard.tsx` (new, in the caravans admin tab): per country — banned groups multi-select (chips), list of posts (read-only, hint: posts are set in the location editor), save per country; uses A1/A2.
* `EconomyCaravans.tsx` (params list), `paramHints.ts`, `types/economy.ts`: the 14 params; caravan list/detail: «Контрабанда» badge, customs state («Ожидает досмотра / На досмотре / Досмотрен»), duty paid, seizure reason labels; `economyLabels.ts`: ops `caravan_duty` «Пошлина на таможне», `caravan_seizure` «Конфискация контрабанды», reasons `seized_customs` «Конфисковано таможней», `seized_patrol` «Конфисковано стражей».
* `components/Admin/ReputationPage/shadowLabels.ts`: crime `smuggling` «Контрабанда», fame source `customs_seizure` «Конфискация контрабанды».
* `constants/npc.ts`: role `customs` «Таможенник» + icon.
* `components/pages/LocationPage/CustomsOfficerModal/CustomsOfficerModal.tsx` (new) + button in `NpcProfileModal.tsx` (pattern of `caravaneer`/`captain`), dialogue-gate hint in `npcDialogueGate.ts`; `api/customs.ts`, `types/customs.ts` (new).
* `CaravanSection.tsx`: state «На досмотре» with the timer; «Досмотреть» (solo / with the group, like the raid buttons) when `can_inspect`, with the alert countdown → navigate to the battle.
* `FenceModal/FenceModal.tsx`: new section «Охрана контрабанды» (C7 list, «Наняться» → C8, then navigate to the caravan location); `api/caravanEscort.ts`, `types/caravanEscort.ts` (`is_contraband`, `inspection`).
* Own escort job panel: «Контрабанда» badge and the `inspection` state label.

### 3.10 Data Flow
```
Tick ─► econ_tick._caravan_pass ─► load_snapshot(+bans) ─► build_planner(+posts) ─► plan_caravans(bans, contraband_reach)
     ─► dispatch (legal: route via post, customs_state=pending | contraband: post-free route, is_contraband)
Caravan pass (≈55 s) ─► step_caravan ─► at post: start_inspection ─► ledger caravan_duty (escrow → to-country)
                     ─► _customs_checks(moved contraband) ─► officer roll ─► alert ─► WS notice to officer
                                                        └► guard roll ─► confiscate_tx | begin_check + BS /internal/customs-fight
Officer ─► FE CaravanSection «Досмотреть» ─► nginx (rate limit) ─► CS POST /caravans/{id}/inspect
        ─► begin_check + spawn_guards ─► BS POST /battles/internal/customs-fight ─► battle (pve, caravan_raid_id)
BS battle end ─► CS POST /characters/internal/caravans/raid-result ─► settle_raid(kind) ─► followups:
        confiscate_tx (ledger caravan_seizure: escrow → country + officers; goods → seizure region)
        consequences (smuggling crimes for escorts; fame + reputation for officers)
Smuggler ─► FE FenceModal ─► CS GET /caravans/fence/{npc} | POST /caravans/{id}/escort/hire (npc = fence)
          ─► LS npc_dialogue gate check (HTTP) ─► escort row + move to the caravan gate
Admin ─► LS location edit (is_customs) ; CS A1/A2 bans ; params card
```

### 3.11 Risks
* **econ_core ×4**, **reputation_core CS↔LS** — must stay byte-identical (CI scripts). No `activity_lock.py` change.
* **Escrow drift** if any helper call misses `duty_paid` → the escrow invariant tests catch it; QA asserts the invariant after duty, raid-after-duty, cancel-after-duty, seizure.
* **Planner regressions**: `customs_enabled = 0` or no posts/bans must reproduce today's plans byte-for-byte (QA asserts on the existing planner fixtures).
* **Closed-pair contraband starts right after deploy** if `customs_enabled = 1` (PM question Q3).
* **NPCs on team 0** in a `pve` battle (patrol fight): Backend must verify the battle engine drives NPC participants on either team (law-encounter fights are the precedent); if not, patrol fights fall back to confiscation without a fight and this is reported to PM.
* **CI time**: new DB tests must reuse the `test_physical_caravans` / `test_caravan_raids` worlds; ≤ ~60 s per new file; pure logic in pure tests.

### 3.12 Questions for PM (defaults chosen, not blocking — please confirm with the user)
1. **One fight per caravan**: a contraband caravan that beat off customs (or was already raided by bandits) cannot be inspected / raided again on that trip; likewise a caravan that customs already fought cannot be robbed later.
2. **Officer fight starts by click**: a detected caravan waits `customs_alert_minutes` (10) for the officer's «Досмотреть»; no click → it moves on. The officer may bring his group.
3. **Contraband from day one**: `customs_enabled = 1` by default → as soon as the update is out, countries **without a trade pair** start getting contraband caravans (30 % of the blocked deals, +50 % price) even before any admin sets bans or posts. Alternative: default off until the admin switches it on.
4. **Watch area**: an officer is on watch anywhere in his country's territory (not only in border locations), whenever he is not in battle / jailed / unconscious / escorting.
5. **No checks at the caravan's destination node**: contraband that reaches the buyer's gate is delivered (officers and guards catch it only on the way). Seller's gate departure window is not checked either.
6. **Patrol fight**: guards at the location (up to 5) vs the player escorts only (the caravan's hired NPC guards do not fight the law).
7. **Officer rewards**: only a share of the fine (20 %) split among the officer and his group members who fought, fame 30, reputation «Конфискация контрабанды» +20 in the seizure region; no salary. Hiring needs reputation ≥ «Скиталец» and no wanted status in the NPC's region.
8. **Smugglers**: hired at the fence anywhere in the region, instantly «проведены» to the caravan at the region's trade gate; pay pool 10 % (vs 5 % for legal escorts); no reputation / fame / faction points for smuggling runs; crime «Контрабанда» (40 wanted points) for every escort of a seized caravan; no wanted/reputation requirement to sign up.
9. **Seized goods** go to the market of the region where they were caught (fallback: back to the seller's region); the buyer's money goes to that country's treasury (minus the officers' share).
10. **Contraband is never abstract**: a pair without a road / sea route that avoids all posts gets no contraband at all; contraband also never goes to a region whose trade gate is itself a customs post.
11. **Legal duty at the post**: the duty is paid at the post (before arrival) and is safe from later raids; a raid before the post reduces it pro rata.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Rules for all backend tasks: sync SQLAlchemy in CS, async in LS/BS, Pydantic v1, `python -m py_compile` on every touched file, update `docs/services/<service>.md`, Russian user-facing texts, **no git commit / push**. Byte-identical copies: `econ_core.py` ×4 (`scripts/check_econ_copies.sh`), `reputation_core.py` CS↔LS.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **LS: «Таможня» flag.** Migration `061_customs_posts` (column + index, idempotent, downgrade); model; `LocationCreate/Update/Read`; create/update normalisation and every read dict/payload that carries `is_port`; validation (no flag on ship / sea-zone locations, 400 Russian text); update single-head test to 061; docs. | Backend Developer | DONE | `services/locations-service/app/models.py`, `schemas.py`, `crud.py`, `main.py`, `alembic/versions/061_customs_posts.py`, `app/tests/test_sea_zones.py`, `docs/services/locations-service.md` | — | Migration upgrades/downgrades on MySQL; `is_customs` round-trips through admin create/update/read; py_compile OK; existing LS tests green. |
| 2 | **CS foundation.** Migration `055_customs_smuggling` per §3.4 (columns, `econ_country_bans`, `econ_customs_officers`, raid `kind/officer_paid/seized_done`, seed rows, downgrade); models; `econ_core` ops `caravan_duty`/`caravan_seizure` in all 4 copies; `reputation_core` action + `customs` role weight in CS+LS copies; `law_core.CRIME_SMUGGLING`, `shadow_core.SOURCE_CUSTOMS_SEIZURE`; new pure `customs_core.py` (§3.6); 14 params (`SimParams`, bounds, update schema, `CUSTOMS_PARAM_KEYS` in the params read/write); money helpers `remaining_payout/refund_split/raid_marks_cap` with `duty_paid` + every caller + `escrow_expected` (§3.2); single-head tests → 055. | Backend Developer | DONE | `character-service/app/alembic/versions/055_customs_smuggling.py`, `models.py`, `econ_core.py` (+ IS/LS/dungeon copies), `reputation_core.py` (+ LS copy), `law_core.py`, `shadow_core.py`, `customs_core.py` (new), `econ_sim.py`, `schemas.py`, `economy_caravan_crud.py`, `econ_caravan.py`, `caravan_raid_crud.py`, `caravan_escort_crud.py`, tests single-head files | — | Copies identical (scripts pass); migration up/down on MySQL; with `duty_paid` unset all helpers return today's values; py_compile OK; existing CS economy/caravan tests green. |
| 3 | **CS planning & routing.** Bans/posts loaders with deploy-skew fallback; `Snapshot.bans`; `region_gates` country; `RoutePlanner` legal-via-post (land + sea land2 rule), contraband land/sea routes and `contraband_reach` (§3.0 A5/A7/A8); `plan_caravans(bans, contraband_reach)` (§3.6); `econ_tick._caravan_pass` wiring incl. the path-blind pre-plan; `dispatch` re-validation and storing `is_contraband/markup_pct/customs_*`. `customs_enabled = 0` or no posts/bans ⇒ identical plans to today. | Backend Developer | DONE | `econ_caravan.py`, `economy_caravan_crud.py`, `econ_tick.py`, `caravan_route.py` (only if a helper is needed) | #2 | Planner unit cases from §3.0 behave as specified; legacy planner tests unchanged and green; py_compile OK. |
| 4 | **CS inspection at the post.** `customs_crud.start_inspection` + `charge_duty` (op `caravan_duty`, idempotent key); `step_caravan` pending→inspecting→cleared incl. post at final node and `customs_index 0`; `sea_cargo._unload` hook for a customs landing port; `settle_raid` respects `customs_until`; `held_by` `"customs"` (without touching `hold_started_at`); `caravans_here` state `inspection` + `can_inspect/inspect_in_sec`; `escort_job` `inspection` + `is_contraband`; admin `_caravan_out`/`caravan_detail` new fields and reasons. | Backend Developer | DONE | `customs_crud.py` (new), `caravan_pass.py`, `sea_cargo.py`, `caravan_raid_crud.py`, `economy_caravan_crud.py`, `caravan_escort_crud.py`, `schemas.py`, `caravan_escort_schemas.py` | #2, #3 | Legal caravan stops `customs_inspection_minutes` at the post, pays duty once to the destination country, escrow invariant holds after duty / raid-after-duty / cancel-after-duty; py_compile OK. |
| 5 | **CS officer job + admin bans API.** `customs_api.py` router (C1–C4, A1, A2) registered in `main.py`; enlist/resign/job/view in `customs_crud` (gate order §3.6, lock order §3.3); NPC role constant `customs`; bans read/replace with validation; schemas. | Backend Developer | DONE | `customs_api.py` (new), `customs_crud.py`, `schemas.py`, `main.py`, `locations_client.py` (reuse only) | #2 | Endpoints follow §3.7 contracts and error codes; permissions `economy:read/settings` on A1/A2; py_compile OK. |
| 6 | **BS: customs fight endpoint.** `POST /battles/internal/customs-fight` per §3.7 B1 (schema, leader vs NPC-enforcer modes, no gate consumption, 409 no defenders, `caravan_raid_id` tag, escort flag); verify NPC participants on team 0 are driven by the engine (report to PM if not); CS `battle_client.create_customs_battle`; docs. | Backend Developer | DONE | `services/battle-service/app/main.py`, `schemas.py`, `services/character-service/app/battle_client.py`, `docs/services/battle-service.md` | — | Endpoint creates the battle in both modes; existing caravan-raid / sea-raid endpoints unchanged; py_compile OK; BS tests green. |
| 7 | **CS detection, fights, seizure, consequences.** `_customs_checks` step in `caravan_pass` (after stepping, before delivery; moved non-final caravans only; skipped while an economy run is running); officer rolls → alert + notice; patrol rolls → confiscation or auto fight (`begin_check`, `asyncio.run`, abandon/409 fallback); `POST /caravans/{id}/inspect` (C5); `settle_raid` kind branches; `raid_followups` confiscation (`seized_done`, op `caravan_seizure`, goods to seizure region, officer split, counters) + `consequences` (smuggling crimes, fame, reputation); skip bales/faction/victory-window for non-raid kinds. | Backend Developer | DONE | `customs_crud.py`, `customs_api.py` (or `caravan_api.py` for C5), `caravan_pass.py`, `caravan_raid_crud.py`, `economy_caravan_crud.py`, `shadow_crud.py`/`law_crud.py` (reuse), `renown_crud.py`/`reputation_crud.py` (reuse), `schemas.py` | #3, #4, #5, #6 | Full flows of §3.1 work; seizure op balances (R paid out exactly, escrow invariant holds); one generic 404 for non-eligible inspect; no contraband leak per §3.6 audit list; py_compile OK. |
| 8 | **CS smugglers at the fence.** `resolve_hiring_npc` (caravaneer \| fence); caravaneer excludes contraband; `smuggler_view` (C7) + fence hire path in `hire` (C8, refusal for officers, move to caravan, hire location = fence); smuggler fee share in `pools`; `reward_one` pay-only for contraband; API wiring + schemas. | Backend Developer | DONE | `caravan_escort_crud.py`, `caravan_escort_api.py`, `caravan_escort_schemas.py`, `caravan_escort_public.py` (verify only) | #2, #3 | Smuggler can be hired only at a fence of the seller region for a preparing contraband caravan; caravaneer never lists contraband; pay uses the smuggler share; py_compile OK. |
| 9 | **Nginx rate limit for inspect** — extend the FEAT-211 raid location regex to `(raid|inspect)` in both configs. | DevSecOps | DONE | `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf` | — | `nginx -t` OK on both; other `/characters/caravans/` routes unaffected. |
| 10 | **Frontend admin.** «Таможня» checkbox in the location editor; `CustomsBansCard` (A1/A2); 14 params with labels + hints; caravan list/detail badges/states/reasons; op labels; crime/fame labels; NPC role «Таможенник». | Frontend Developer | DONE | `EditLocationForm.tsx`, `components/Admin/EconomyPage/CustomsBansCard.tsx` (new), `EconomyCaravans.tsx`, `paramHints.ts`, `economyLabels.ts`, `types/economy.ts`, `api/` economy admin client, `shadowLabels.ts`, `constants/npc.ts` | #1, #2, #5 (contracts) | `npx tsc --noEmit` + `npm run build` pass; Tailwind/TS/no React.FC/mobile 360px; all errors shown in Russian. |
| 11 | **Frontend player.** `CustomsOfficerModal` + NpcProfileModal button + dialogue hint; CaravanSection «На досмотре» + «Досмотреть» (solo/group) → battle; FenceModal «Охрана контрабанды» (list, hire, navigate); escort job contraband badge + `inspection` state; `api/customs.ts`, `types/customs.ts`, `api/caravanEscort.ts`, `types/caravanEscort.ts`. | Frontend Developer | DONE | `components/pages/LocationPage/CustomsOfficerModal/CustomsOfficerModal.tsx` (new), `NpcProfileModal.tsx`, `npcDialogueGate.ts`, `CaravanSection.tsx`, `FenceModal/FenceModal.tsx`, escort job panel component, `api/customs.ts`, `types/customs.ts`, `api/caravanEscort.ts`, `types/caravanEscort.ts` | #5, #7, #8 (contracts) | tsc + build pass; flows usable at 360px; every API error visible in Russian; no contraband marker shown to non-escorts. |
| 12 | **QA LS**: `is_customs` create/update/read, validation refusal on ship / sea-zone location, migration head 061. Keep it in the existing location test style (fast). | QA Test | DONE | `services/locations-service/app/tests/test_customs_posts.py` (new) | #1 | pytest green, < 30 s. |
| 13 | **QA BS**: customs-fight endpoint — leader mode (no gate consumed, squad, escorts filtered), NPC-enforcer mode, 409 no defenders, 400 both/none modes, team-size 400, internal token required. | QA Test | DONE | `services/battle-service/app/tests/test_customs_fight.py` (new) | #6 | pytest green. |
| 14 | **QA CS pure** (no DB): `plan_caravans` with bans / closed pair / share / markup / legal-first ordering / `bans=None` identical output; money helpers with `duty_paid`; `customs_core` detection/patrol chance clamps, caravan stealth, `illegal_in`, officer split; planner routing via a post, post unreachable, contraband avoiding posts, buyer gate = post, sea landing-port rules (use small in-memory graphs). | QA Test | DONE | `character-service/app/tests/test_customs_core.py` (new) | #2, #3 | pytest green, whole file < 5 s. |
| 15 | **QA CS DB flows** reusing the `test_physical_caravans` / `test_caravan_raids` / `sea_world` worlds (add `is_customs` to the world `Locations` DDL only where needed): inspection stop + duty + escrow invariant (incl. post = final node), raid during inspection, officer enlist/resign/refusals, detection → alert → inspect (battle client mocked) → settle won → seizure op/goods/officer share/crimes/fame/rep, repelled path, patrol confiscation without escorts and auto-fight start (mocked, 409 fallback), fence smuggler view/hire/move/pay share, caravaneer excludes contraband, masking (caravans_here / caravaneer view never expose contraband), admin bans GET/PUT (permissions, validation). RNG via seams, no sleeps. | QA Test | DONE | `character-service/app/tests/test_customs_flows.py` (new; split in two files only if > ~60 s) | #4, #5, #7, #8 | pytest green; new file(s) ≤ ~60 s each; full CS suite still fits the 25-min CI limit. |
| 16 | **Review**: contracts BE↔FE↔tests, copies identical (econ_core ×4, reputation_core ×2), migrations up/down, escrow invariant, lock order, masking audit, security checklist, py_compile / tsc / build / pytest, live check (admin flag + bans, officer window, fence list, caravan section). | Reviewer | DONE | all | #1–#15 | Checklist passed. |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-18
**Result:** PASS

#### Checks
- [x] Types match (Pydantic ↔ TS interfaces) — `customs_schemas.py` ↔ `types/customs.ts`, `SmugglerViewOut` / `EscortJobOut.is_contraband` ↔ `types/caravanEscort.ts`, `caravans_here` (`can_inspect`, `inspect_in_sec`, state `inspection`) ↔ `types/caravans.ts`, admin A1/A2/A3 ↔ `types/economy.ts`
- [x] API contracts consistent (backend ↔ frontend ↔ tests); BS B1 `CustomsFightCreate` ↔ CS `battle_client.create_customs_battle` (escort `max_items=4` = `caravan_escort_seats` bound 0–4)
- [x] Byte-identical copies: `scripts/check_econ_copies.sh` — all identical (econ_core ×4, econ_contract_cases ×4, reputation_core CS = LS md5 `4fe4176f…`); no `activity_lock.py` touched
- [x] Migrations: `055_customs_smuggling` (21 chars) / `061_customs_posts` (17 chars), single heads; down → up on dev MySQL inside the containers OK for both
- [x] Money: `duty_paid` threaded through `remaining_payout` / `refund_split` / `raid_marks_cap` / `_seller_part` / `escrow_expected` / `_cancel_legs` / admin detail; seizure pays out exactly `R = paid − raid_paid − freight_paid − duty_paid`; idempotency keys `caravan:c<id>:duty` / `:seize`, claims `seized_done` → `law_done`; lock order of the seizure tx matches §3.3
- [x] Masking: `caravans_here` never exposes the flag (contraband shows as an ordinary caravan, `can_inspect` only for the alerted officer — verified live with a second character), caravaneer view/hire 404 for contraband, `is_contraband` only in the escort's own job and admin, inspect returns one generic 404 «Здесь нечего досматривать»
- [x] No stubs/TODO without tracking
- [x] `py_compile` (syntax compile of all 58 touched/new .py files) — OK
- [x] `npx tsc --noEmit` (frontend container) — OK, 0 errors
- [x] `npm run build` (frontend container) — OK
- [x] `pytest` — BS full suite 2235 passed / 10 skipped; LS full suite 3349 passed / 5 skipped; CS customs/caravan/sea/econ/reputation files 1689 passed; IS econ 518 passed; dungeon econ contract/flows passed (rc 0)
- [x] `docker compose config` — OK; `nginx -t` OK for the new `nginx.conf` and for `nginx.prod.conf` (temp copy without certs) inside api-gateway
- [x] Security checklist passed: JWT + ownership on C1–C5/C7/C8, NPC dialogue gate (fail-closed) + tier gate, `economy:read` / `economy:settings` on A1/A2, `X-Internal-Token` on B1, Pydantic bounds (`conint(strict, ge=1)`, `Extra.forbid`, list caps), ban codes validated, Russian error texts without internals; inspect rate-limited (6 r/m burst 3 — 429 observed live after the burst)
- [x] Frontend displays all errors to user (toasts + inline, Russian); Tailwind only, no new SCSS, no `React.FC`, TS
- [x] User-facing strings in Russian

#### Live Verification Results (localhost, Chrome, admin / Ашари 763)
- `/admin/economy` → «Караваны»: «Таможня и контрабанда» params render with hints; changed «Ожидание "Досмотреть"» 10 → 11, saved (GET confirms 11), restored to 10. CustomsBansCard loads all countries; banned «Оружие» for Мидденгерд → toast «запрещено групп — 1», A1 confirms `["weapons"]`; restored to empty.
- `/admin/locations` → Холм Эха (197) edit: «Таможня (пост досмотра караванов)» checkbox saved; A1 lists the post, `/locations/197/details` → `is_customs: true`; restored to 0.
- NPC Петя (33) temporarily given role `customs` + an open `npc_dialogue` gate: NPC card shows «Таможенник», profile button «Таможня» opens CustomsOfficerModal; enlist (confirm dialog) → toast + «Ваша служба» block (Мидденгерд, 0/0); resign → back to «Поступить на таможню».
- Synthetic zero-value caravans at 197 (no ledger effect): legal one shows «На досмотре — ещё ~25 мин»; contraband one with an alert for 763 shows «Досмотреть» + countdown to 763 only (character 764 sees `can_inspect:false`, inspect → 404 «Здесь нечего досматривать», then nginx 429). Real `caravan_pass.step_caravan` on MySQL: pending → `inspecting` at the post (customs_until +30 min, duty 0 → no op); post as final node: due step → `cleared` → `arrived` (rolled back).
- Петя as `fence`: FenceModal tab «Охрана контрабанды» lists the contraband caravan (gate Холм Эха), «Наняться» disabled with «Вы служите на таможне — скупщик не станет с вами связываться»; caravaneer endpoints 404 for contraband.
- 360px iframe: caravan section fits (scrollWidth = clientWidth), buttons stack.
- Console errors: none. CS/LS logs: no errors except one expected `Unknown column seized_done` during the deliberate migration down/up window.
- Not done live: a real officer/patrol fight and a non-zero duty/seizure op — the dev world has no trade pairs, no trade gates and no physical caravans (values ≪ `caravan_physical_min_value`), so these money paths rely on the QA DB tests (`test_customs_flows`, `test_customs_inspection`, `test_customs_detection`, escrow invariant asserts).
- Cleanup: test caravans 635–637, officer row, 2 CharacterLog rows, action gate 201 deleted; Петя back to `merchant`; 197 `is_customs = 0`; bans empty; params restored. The running api-gateway got the new `nginx.conf` via `docker cp` + reload (same as the working tree; the image itself is rebuilt on deploy).

#### Fixes made by Reviewer
- `services/character-service/app/caravan_escort_crud.py` (`reward_one`): whitespace typo `faction =faction_kills…` → `faction = faction_kills…` (escort + smuggler tests re-run: 35 passed).

#### Notes (non-blocking)
1. The migration down/up on dev dropped and recreated `econ_country_bans` / `econ_customs_officers` (dev had no rows of value; `Locations.is_customs` was 0 everywhere).
2. `caravans_here`: while an alert is open the contraband caravan is `held` for everyone — the same state as a legal caravan held by an RP raid post, so it does not reveal contraband, but it is a weak signal. Acceptable per §3.6 (`held_by` = customs).
3. `can_inspect` stays true for the alerted character for the rest of the alert window even after he resigns (the button then gets the generic 404). Cosmetic; could additionally check `is_active_officer` in `caravans_here`.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| — | — | No blocking issues | — | — |

---

## 6. Logging (filled by all agents — in Russian)

Running log of progress updates. Each agent writes brief Russian entries here.

```
[LOG] 2026-11-18 — PM: фича создана по ответам пользователя (вариант «а»: таможня только для караванов), запускаю анализ
[LOG] 2026-11-18 — Analyst: анализ завершён — затронуты character-service (ядро), locations-service (флажок «Таможня», миграция 061), фронтенд; battle-service и копии econ_core/activity_lock — по решению архитектора. Стата «внимательность» нет, у каравана нет скрытности; есть 4 вопроса к пользователю
[LOG] 2026-11-18 — PM: пользователь принял предложения по 4 вопросам аналитика (обнаружение через скрытность, конфискат на склад региона + штраф в казну, тюки не трогаем, патрули без игроков — конфискация без боя, контрабанда и при закрытой торговле); передаю архитектору
[LOG] 2026-11-18 — Architect: спроектировано 16 задач (LS флажок «Таможня», CS: планирование контрабанды и маршрут через пост, досмотр с пошлиной, таможенник, обнаружение и конфискация, контрабандисты у Скупщика; BS эндпоинт боя таможни; nginx; фронт админки и игрока; QA ×4; ревью), 15 API-контрактов, 11 игровых умолчаний на подтверждение
[LOG] 2026-11-18 — PM: пользователь подтвердил все 11 решений архитектора по умолчанию (§3.12); запускаю задачи 1, 2, 6, 9 параллельно
[LOG] 2026-11-18 — Backend Dev: задача 1 готова — флажок «Таможня» (`Locations.is_customs`, миграция 061_customs_posts с откатом), схемы, создание/правка, все выдачи рядом с `is_port`; таможню нельзя ставить на палубу или в морскую зону (400); single-head теста в LS нет — проверка цепочки 061 остаётся за QA (задача 12); документация обновлена
[LOG] 2026-11-18 — Backend Dev: задача 6 готова — в battle-service эндпоинт POST /battles/internal/customs-fight (режимы «таможенник» и «патруль», без траты гейта поста, 409 «Защитников каравана нет», метка caravan_raid_id, флаг автобоя для охранников), в CS battle_client.create_customs_battle, документация обновлена. Проверено: NPC в команде 0 ходят сами (автобой регистрирует всех NPC независимо от команды). Тесты BS: 2173 passed
[LOG] 2026-11-18 — Backend Dev: задача 2 готова — миграция CS 055_customs_smuggling (колонки караванов и налётов, таблицы econ_country_bans / econ_customs_officers, сиды customs_seizure и роли customs; up → down → up на MySQL пройдены), модели, операции caravan_duty / caravan_seizure во всех 4 копиях econ_core (+ econ_contract_cases), действие репутации и роль «customs» в reputation_core CS = LS, CRIME_SMUGGLING, SOURCE_CUSTOMS_SEIZURE, чистый customs_core.py, 14 параметров (+ правило min ≤ max для шанса таможенника), duty_paid в remaining_payout / refund_split / raid_marks_cap и всех вызовах + escrow_expected; без duty_paid всё как раньше. Тесты: CS 2492 passed (после правки 3 тестов под новые ключи), контракт econ в IS/LS/dungeon зелёный, копии идентичны
[LOG] 2026-11-18 — DevSecOps: задача 9 готова — в nginx.conf и nginx.prod.conf регулярка лимита набегов расширена до `^/characters/caravans/\d+/(raid|inspect)$` (общая зона caravan_raid_limit, 6 r/m, burst 3); `nginx -t` пройден для dev и для prod (прод-конфиг проверен во временной копии внутри контейнера api-gateway с самоподписанным сертификатом); прод не перезагружался
[LOG] 2026-11-18 — QA Test: задача 13 готова — tests/test_customs_fight.py (62 теста): токен, оба/ни одного режима 400, лимиты команд 400, один id в стражах и мобах 400, режим таможенника (гейт не тратится, отряд, эскорт выкинут из атакующих), режим стражи-НПС, 409 «Защитников каравана нет», метка caravan_raid_id. Багов не найдено. BS: 2235 passed, 10 skipped
[LOG] 2026-11-18 — QA Test: задача 12 готова — tests/test_customs_posts.py (33 теста, ~11 с): флажок «Таможня» через создание/правку (crud и роуты), null при правке не трогает значение, выдачи (детали локации, региона, клиентские детали, граф карты); отказ 400 «Таможня не может стоять на корабле или в море» для морской зоны, палубы, создания таможенной морской зоны и превращения таможни в зону, на отказе ничего не пишется; миграция 061_customs_posts: id ≤ 32, родитель 060_sea_zones, единственная голова. Багов не найдено. Вместе с test_sea_zones/test_client_details/test_econ_contract: 589 passed
[LOG] 2026-11-18 — Backend Dev: задача 3 готова — загрузка запретов (`Snapshot.bans`) и постов таможни (`Locations.is_customs` сырым SQL, нет колонки → постов нет), страна края в `region_gates`; `RoutePlanner.legal_route` ведёт иностранный законный караван через пост страны назначения (море — через порт высадки-пост или пост на второй сухопутной части), пост недостижим → суша недоступна (дальше море / абстрактный запасной путь); контрабанда обходит все посты, не заканчивается на посту и не высаживается в таможенном порту, только физическая; `plan_caravans(bans, contraband_reach)` — законные раньше, доля/наценка, без пошлины, занимает физический слот; предплан тика с «всегда сушей» для контрабанды; `dispatch` перепроверяет и пишет `is_contraband/markup_pct/customs_*`. Таможня выключена или нет постов/запретов → законные планы как раньше. Тесты: 552 passed (караваны/море/тик) + 15 новых в tests/test_customs_planning.py; документация обновлена
[LOG] 2026-11-18 — Backend Dev: задача 5 готова — служба таможенника и запреты стран: новый роутер customs_api.py (C1 окно «Таможенник», C2 найм, C3 увольнение, C4 своя служба; A1/A2 запреты и посты по странам с правами economy:read / economy:settings), customs_crud.py (порядок проверок §3.6: владелец → НПС «customs» → та же локация → страна → гейт «Диалог с НПС» → тир НПС → уже служит → блокировка/бой → розыск → репутация ≥ «Скиталец»; блокировки §3.3), customs_schemas.py; роутер подключён в main.py первым (иначе /admin/economy/caravans/customs съедал бы {caravan_id}); смоук-тест tests/test_customs_officer_api.py (4 теста); связанные тесты CS 1033 passed; вживую через шлюз A1 отдаёт страны и группы, A2 с неизвестной группой → 400; документация обновлена
[LOG] 2026-11-18 — QA Test: задача 14 готова — tests/test_customs_core.py (59 тестов, ~3.7 с, без БД): plan_caravans — таможня выключена / bans=None = как раньше, запрет без contraband_reach убирает сделку, запрет в стране продавца или третьей стране не мешает, контрабандой идёт только запрещённая группа, наценка 0/50/100/250 % и отрицательная = 0, доля 1.0, законные раньше даже более дорогих и морских (и забирают последний физический слот), каждая контрабанда занимает слот, открытая пара без законного пути не уходит в контрабанду, внутренняя торговля игнорирует запреты; contraband_price; settled_duty / remaining_payout / refund_split / raid_marks_cap с duty_paid; customs_core — шансы таможенника и патруля с границами, скрытность каравана, illegal_in / is_banned, доля и раздел таможенникам, normalize_ban_codes (ошибки, too_many); RoutePlanner — причины no_gate/no_path, выбор ближайшего поста и ничья по id, посты чужих стран не мешают законным, лимит шагов через пост, пост у ворот продавца (индекс 0), подземелья, контрабанда и пост на воротах покупателя любой страны, contraband_reach (суша/море с фрахтом/никогда не абстрактно), морские правила A7 (высадка в таможенном порту, обход через нетаможенный порт только с заходом на пост, внутренний рейс без таможни, уход на море при недостижимом посте) и A8. Вместе с test_customs_planning: 74 passed. Багов не найдено
[LOG] 2026-11-18 — Frontend Dev: задача 10 готова — галочка «Таможня» в редакторе локаций (рядом с «Порт», выключена для морской зоны, ошибка 400 бэкенда показывается тостом); новая карточка «Таможня» во вкладке «Караваны» (по странам: посты только для чтения, запрещённые группы фишками, сохранение по стране, ошибки на русском); группа из 14 параметров «Таможня и контрабанда» с подсказками и проверкой «минимум ≤ максимум»; в списке и карточке каравана — метка «контрабанда» с наценкой, этап досмотра, уплаченная пошлина, пост, конфискация (причина, где поймали), вид боя (налёт / досмотр таможни / стража) и доля таможенникам; фильтр «Контрабанда»; подписи операций caravan_duty / caravan_seizure, причин seized_customs / seized_patrol, преступления «Контрабанда», источника славы customs_seizure и роли НПС «Таможенник». Все новые поля каравана необязательные (задача 4 ещё не сделана). tsc и build в контейнере пройдены
[LOG] 2026-11-18 — Backend Dev: задача 4 готова — досмотр на посту: customs_crud.start_inspection / charge_duty (операция caravan_duty в казну страны назначения, ключ caravan:c<id>:duty, после набега до поста — пропорционально), шаг каравана pending → inspecting → cleared (пост в середине, в конце пути и в воротах продавца), высадка в таможенном порту запускает досмотр после фрахта, settle_raid не сокращает досмотр, held_by «customs» без окна поста, caravans_here: состояние inspection + can_inspect/inspect_in_sec, работа охранника: inspection + is_contraband, админка: поля таможни и конфискации, kind/officer_paid налёта, фильтр kind=contraband. Тесты: новый tests/test_customs_inspection.py (10) + тест порта-таможни в test_sea_caravans.py; 3 старых теста дополнены новыми ключами; документация обновлена
[LOG] 2026-11-18 — Backend Dev: задача 8 готова — контрабандисты у Скупщика: resolve_hiring_npc (караванщик | скупщик), караванщик не видит и не нанимает контрабанду (404), новый GET /characters/caravans/fence/{npc_id} (C7: контрабанда края скупщика у торговых ворот, как обычные караваны + gate_location_id/name, оценка платы от customs_smuggler_fee_share), найм C8 через тот же POST …/escort/hire с npc_id скупщика (без розыска/репутации, отказ 403 действующему таможеннику, место найма = скупщик, перенос к каравану), пул платы контрабандистам 10 %, ходка контрабанды — только плата (без репутации/славы/фракций). Старый тест «роль fence → 404» переведён на другую роль. Тесты: новый tests/test_caravan_smugglers.py (8) + эскорт/таможня/налёты/физические/морские — 447 passed; документация обновлена
[LOG] 2026-11-18 — Backend Dev: задача 7 готова — проверка контрабанды после шага каравана (только сдвинувшиеся, не в конечном узле; пропуск при выключенной таможне и идущем прогоне экономики): таможенники на вахте в локации своей страны (внимательность = скрытность через ту же кривую, скрытность каравана = база + лучший охранник) → тревога и уведомление только ему (WS customs_alert); иначе бросок стражи: без охранников-игроков — конфискация без боя, с охраной — автобой стражи (asyncio.run), 409 «Защитников нет» — конфискация без боя. POST /characters/caravans/{id}/inspect (C5): один общий 404 «Здесь нечего досматривать», бой kind=customs. settle_raid для customs/patrol: без денег, победа замораживает караван; конфискация (caravan_seizure: доля таможенникам, остаток стране изъятия, товар на склад региона изъятия, счётчики службы, seized_done) и последствия (преступление «Контрабанда» охране, слава и репутация таможеннику) — в доследствиях налёта; тюки/фракции/окно победы для таможни выключены. Тест tests/test_customs_detection.py (12); прогон связанных тестов CS зелёный; документация обновлена
[LOG] 2026-11-18 — Frontend Dev: задача 11 готова — окно «Таможенник» (CustomsOfficerModal: страна поста, своя служба с конфискациями и заработком, «Поступить на таможню» / «Оставить службу» с подтверждением, подсказка про пост «Диалог с НПС») и кнопка «Таможня» у НПС с ролью customs; в блоке караванов состояние «На досмотре — ещё ~N мин» и кнопка «Досмотреть» (одному / с группой, обратный отсчёт окна тревоги) → переход в бой, все ошибки 404/409/429/503 тостом; у Скупщика вкладка «Охрана контрабанды» (список тайного груза у торговых ворот, найм с подтверждением → переход в локацию каравана); в панели охраны состояние «на досмотре у таможни» с таймером и метка «тайный груз» только самому охраннику; уведомление customs_alert — тост со звуком боя и ссылкой колокольчика на локацию, customs — обычный тост; types/customs.ts, api/customs.ts, types/caravanEscort.ts, api/caravanEscort.ts. tsc и build в контейнере пройдены
[LOG] 2026-11-18 — QA Test: задача 15 готова — tests/test_customs_flows.py (22 теста, ~12 с): настоящая математика скрытности (внимательность таможенника, скрытность каравана с очками подкласса, шанс патруля), таможенник не на вахте (розыск/тюрьма/бой/сам охранник), досмотр группой с остатком доли в казну и славой/репутацией каждому, 409 для заблокированного, отбитый патруль → контрабандистам только плата (+бонус), опрос/истечение боёв таможни и патруля, товар конфиската (регион изъятия → регион продавца → списание), палуба → регион боя, эскроу после фрахта и пошлины, налёт во время досмотра не сокращает стоянку, маскировка (чужие видят обычный караван, тревога — только таможеннику, карточка контрабандиста), отказы найма, админ-запреты (401/403/422/400). Багов не найдено. Связанные тесты: 420 passed (2 мин); полный прогон CS прерван по нехватке памяти на хосте около 63 % — без падений до этого места
[LOG] 2026-11-18 20:40 — Reviewer: начал проверку
[LOG] 2026-11-18 21:15 — Reviewer: проверка завершена, результат PASS — копии econ_core/reputation_core идентичны, миграции 055/061 откатываются и накатываются на MySQL, tsc/build чистые, тесты BS 2235, LS 3349, CS (таможня/караваны/море/экономика) 1689, IS/dungeon econ — зелёные; вживую проверены галочка «Таможня», параметры и запреты в админке, окно «Таможенник» (поступить/уйти), «Охрана контрабанды» у скупщика, «На досмотре»/«Досмотреть» в блоке караванов, маскировка и лимит 429; исправлена опечатка-пробел в caravan_escort_crud.reward_one; тестовые данные убраны
[LOG] 2026-11-18 — PM: ревью PASS, полный набор CS 11044 прошли (21:22); фича закрыта, жду команду на коммит
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
Таможня и контрабанда для караванов (инвентарь игроков пространственный — его не трогаем). Галочка «Таможня» у локаций; законный караван из другой страны проходит пост страны назначения, стоит на досмотре и платит пошлину в казну. У стран — запреты групп товаров; запрещённое и торговля между странами без торговой пары уходит контрабандистам с наценкой в обход постов. НПС «Таможенник»: игрок поступает на службу, замечает контрабанду (его скрытность против скрытности каравана), досматривает (бой), получает долю конфиската, славу и репутацию. Патрули ловят контрабанду сами (без игроков в охране — конфискация без боя). Охрану контрабанды нанимает Скупщик, плата выше, при поимке — преступление «Контрабанда». Конфискат — на рынок региона поимки, деньги покупателя — в казну страны.

### Что изменилось от первоначального плана
- «Краденое — контрабанда везде» убрано: тюки в инвентаре, досматривать нечего.
- Вахта таможенника — на всей территории страны, не только у границ.
- Взятки — позже.

### Оставшиеся риски / follow-up задачи
- Живьём не проверен настоящий бой таможни/патруля и ненулевая пошлина/конфискат (на локалке нет торговых пар и ворот) — покрыто тестами БД.
- Пока открыт сигнал таможеннику, караван всем виден как «задержан» (так же выглядит законный караван на посту налёта).
- Таможня включена по умолчанию: между странами без торговли пойдёт контрабанда сразу после деплоя.
