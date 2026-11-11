# FEAT-211: Физические караваны и налёты

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-10 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сейчас NPC-караваны экономики (FEAT-192, `econ_caravans`, `econ_caravan.py`, `economy_caravan_crud.py`, эскроу «Караваны в пути») абстрактны: регион-продавец отправляет партию в тик (6 ч), покупатель платит в эскроу, через `travel_runs` тиков караван «доезжает». Делаем их физическими — караван едет по локациям — и даём игрокам-«плохишам» нападать на них и грабить. Это этапы 1+2 общего плана (этап 3 — наёмная охрана из игроков, осведомители, фракционные очки — НЕ делаем).

Связанные системы: экономика (FEAT-181…194, ledger, инвариант суммы денег = 0), закон/тень/скрытность/стража/тюрьма (FEAT-198…204), репутация (FEAT-197/199), фракции (FEAT-205…207), патрули стражи (FEAT-204 — механика движения NPC по локациям), бой (battle-service, PvE против мобов), группы (party-service), инвентарь (inventory-service, новые предметы), торговцы NPC (FEAT-183).

### Бизнес-правила

**Этап 1 — движение**
- Физическими становятся: все **крупные** караваны (порог ценности — настройка экономики) и все **межстрановые**; **мелкие** — случайно, с шансом/частотой из настройки (чтобы встречались, но не забивали локации). Остальные караваны работают по-старому (абстрактно).
- При отправке караван строит маршрут по связям локаций от главной локации региона-продавца до главной локации региона-покупателя (как определить «главную» и как ходить между регионами — решит аналитик; если пути нет — караван остаётся абстрактным).
- Движение: одна локация примерно за 15–20 мин реального времени (настройка), средний маршрут 2–4 ч. Доставка (товар на склад покупателя, деньги продавцу, пошлина) — когда караван реально дошёл, а не по тикам.
- **Видимость:** караван виден ТОЛЬКО в локации, где он сейчас стоит: «Торговый караван: <группа товара>, охрана N». Откуда и куда едет — НЕ показывать нигде игрокам (ни в локации, ни в карточке региона, ни на карте) — игроки должны сами учить маршруты. Админ видит всё (маршрут, позицию).
- Караван в бою/после налёта ведёт себя по правилам этапа 2.

**Этап 2 — налёт**
- Игрок (или группа игроков) в той же локации, что и караван, может «Напасть на караван». Ограничения на нападающего (уровень, «без сознания», в бою, в тюрьме и т.п.) — как у существующего нападения на NPC/мобов.
- Бой против охраны каравана: охрана — мобы, сила зависит от ценности груза и опасности края (формула — архитектор; настройки в админке экономики).
- На один караван — один налёт (повторно нельзя, пока он в пути).
- **Победа налётчиков:** добыча — доля груза:
  - **марки** — доля денег покупателя из эскроу;
  - **товар** — новые предметы-«тюки» по 12 группам товаров («Тюк зерна», «Слиток руды»…), количество — от доли груза; с отметкой **«краденое»**.
  - Доля добычи — настройка. Делится между участниками-победителями (правило — архитектор).
  - Оставшееся едет дальше (или караван разворачивается — решит архитектор, вариант PM: едет дальше с остатком).
- **Поражение налётчиков:** обычные последствия проигранного боя; караван едет дальше.
- **Сбыт краденого:** обычные торговцы краденые тюки НЕ покупают; покупает **скупщик краденого** — новая роль NPC, платит дешевле (настройка). Незамаранные тюки (на будущее, напр. за охрану) — продаются обычным торговцам. Деньги скупщика — из его кассы/экономики края (инвариант суммы денег соблюдается).
- **Экономика:** покупатель заплатил, но получил меньше товара → в регионе-покупателе меньше товара, цены растут. Марки, ушедшие налётчикам, — из эскроу (деньги не создаются из воздуха). Продавцу — по правилам архитектора (вариант PM: продавец получает оплату только за доставленное, а за украденное — доля, ушедшая налётчикам, просто перешла к ним; покупатель за украденное не платит повторно и денег не возвращает — товар «сгорел» в пути).
- **Последствия для налётчика:** преступление по закону края, где произошёл налёт (новый тип правонарушения «налёт на караван», тяжесть — настройка), розыск, проверка скрытности (нераскрытое преступление), падение репутации в крае налёта и в краях продавца и покупателя, рост дурной славы — через существующие механизмы FEAT-197…204.
- В журнале/уведомлениях налётчика — результат налёта и добыча.

### UX / Пользовательский сценарий
1. Игрок в локации видит блок «Торговый караван: руда, охрана 4» (без маршрута) и кнопку «Напасть».
2. Нажимает (один или группой) → бой с охраной.
3. Победил → получил марки и тюки «Слиток руды (краденое)», стал разыскиваемым/дурная слава выросла (если не скрылся).
4. Идёт к скупщику краденого и продаёт тюки.
5. Админ в «Экономике» видит физические караваны: маршрут, позицию, налёты, украденное.

### Edge Cases
- Караван в локации, где стоит стража — нападение всё равно возможно, но стража/закон реагируют (решит архитектор по системе FEAT-203).
- Регион назначения исчез/вышел из экономики — существующая отмена каравана (возврат денег) работает и для физического.
- Сервис боя недоступен — нападение не начинается, видимая ошибка.
- Караван дошёл, пока шёл бой — решит архитектор (вариант PM: караван в бою стоит на месте).
- Инвариант экономики (сумма денег мира = 0) — после каждого шага.
- Все тексты — на русском; сроки — обратным отсчётом.

### Вопросы к пользователю (если есть)
- [x] Добыча → и марки, и товар (тюки)
- [x] Скорость → «как предлагаешь» (15–20 мин на локацию, 2–4 ч маршрут)
- [x] Что физическое → крупные и межстрановые; мелкие — случайно раз в N времени
- [x] Защита игроками → этап 3 (игрок прячется внутри каравана, «сюрприз» при нападении) — НЕ сейчас
- [x] Видимость → только в текущей локации, без «откуда/куда»; маршруты знают только «свои»
- [x] Скупщик краденого, отметка «краденое», этапы 1+2 одной фичей → «Как предлагаешь, запускай»
- [x] (после анализа) Боевой пост для налёта → нужен, как у нападения на мобов: пока пост ждёт модератора, караван стоит на месте, но не дольше 2 ч (настройка) — потом пост сгорает, караван едет дальше.
- [x] (после анализа) Начало/конец маршрута → по умолчанию отделение стражи региона (FEAT-202/204, назначены во всех 23 регионах на проде); в админке поле «Торговые ворота региона» для переопределения. Нет пути — караван остаётся абстрактным, в админке список «нет дороги между X и Y».
- [x] (после анализа) Краденые тюки → продажа скупщику и передача между игроками; аукцион, заказы гильдии, интендант фракции — запрещены.
- [x] (после анализа) Скупщик → **новая роль НПС «Скупщик»** с собственным функционалом: в админке НПС у роли своя вкладка (по паттерну ролевых вкладок «Магазин»/«Телепорты»/«Патруль» из FEAT-208/210 — Admin/ExpandableList), настройки скупки (например процент от рыночной цены края, какие группы товаров берёт, касса скупщика); у игрока — окно продажи краденого этому НПС. Ставит админ.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Paths are relative to `services/`. "CS" = character-service, "LS" = locations-service, "BS" = battle-service, "IS" = inventory-service. Local dev DB is `fogdatabase` (not `mydatabase`); the numbers below come from the local DB (prod lore/geography differs, see Risks).

### Affected Services

| Service | Type of changes | Key files |
|---|---|---|
| character-service | core: physical caravan state + route + stepping pass + delivery outside the tick + raid flow (guards spawn, battle create, battle-end callback, loot, crime/reputation/infamy) + admin reads + region-card hiding + new SimParams | `econ_caravan.py`, `economy_caravan_crud.py`, `econ_tick.py` (`_caravan_pass`), `econ_scheduler.py`, `patrol_crud.py` (reuse), `shadow_crud.py`/`law_crud.py`/`reputation_crud.py`/`renown_crud.py` (reuse), `economy_sim_crud.py:982`, `economy_api.py:997-1035`, `econ_sim.py:149-157`, `schemas.py:2085-2135,2525+`, `models.py:1029`, `econ_core.py` (new op type), new migration 050 |
| battle-service | tag a battle as a caravan raid + report its end to CS (copy of the FEAT-198 law tag/callback) | `main.py:946-960` (`_assemble_battle`), `main.py:1698-1813` (guard battle + law callback pattern), `main.py:2760-2828` (battle-end hooks), `models.py:75-82`, `crud.py:16` (`create_battle`), new migration 010 |
| inventory-service | 12 (or 24) new "тюк" item templates via migration; nothing else unless a per-instance flag is chosen | `models.py:19-112` (items), `models.py:301-312` (character_inventory), `main.py:712` (`POST /inventory/internal/characters/{id}/items`), migration 037 |
| locations-service | fence ("скупщик") pricing / refusal of stolen goods for normal merchants in the sell path; `econ_core.py` byte copy | `main.py:3249-3360` (`sell_to_npc`), `crud.py:4743-4840` (`quote_bid(s)`, `get_sell_offers`), `crud.py:4423` (`merchant_market`), `econ_core.py` copy |
| dungeon-service | only the `econ_core.py` byte copy (if a new op type is added) | `app/econ_core.py` |
| user-service | new permission(s) only if a separate admin right is wanted (economy perms exist: `alembic/versions/0032_add_economy_permissions.py`) | migration 0036 (optional) |
| frontend | location caravan block + «Напасть» (solo / group), region card must stop showing physical caravans' from/to, admin caravan list (route/position/raids/stolen), new SimParams hints, NPC role `fence` label | `components/pages/LocationPage/LocationPage.tsx:850-862`, `EnemiesSection.tsx` (pattern), `components/WorldPage/RegionEconomyCard.tsx:146-172,310`, `components/Admin/EconomyPage/EconomyCaravans.tsx`, `paramHints.ts`, `constants/npc.ts:1-27`, `types/economy.ts`, `api/regionEconomy.ts`, `api/economyAdmin.ts` |
| party-service | none (read-only use of `GET /party/internal/active-members`) | — |

### 1. Current caravans (FEAT-192)

- **Pure planner** `CS/app/econ_caravan.py`: `route()` (`:127-137`) — same country → `caravan_travel_domestic` runs, no duty; different countries only when `econ_trade_pairs` pair is enabled → `caravan_travel_foreign` runs + `duty_pct`. **No location graph is used at all** (docs `docs/services/character-service.md:1276`: «Граф соседства не нужен»). `plan_caravans()` (`:186-280`) is deterministic, food first; one plan = one (seller, buyer, group). `clamp_dispatch()` (`:285-308`) re-checks against locked rows.
- **DB layer** `CS/app/economy_caravan_crud.py`: `dispatch()` `:279-343` (lock 2 regions asc → seller goods → INSERT `econ_caravans` (UNIQUE `dispatch_run_id, from, to, group`) → `stock -= units` → `caravan_dispatch` op: buyer purse (+ buyer region treasury for food) → `caravan_escrow`, key `caravan:c<id>:pay`). `advance()` `:393-400` only decrements `runs_left`. `finish()` `:407-478`: delivery (`goods.stock += units` at destination; escrow → seller purse = value, escrow → buyer country = duty; `caravan_delivery`, key `caravan:c<id>:done`) or cancel (goods back to origin, full refund; `caravan_cancel`, key `:back`). `finish()` is **tied to the tick run**: it uses `run_id`, `last_run_id`, and postpones if a region already ticked in this run (`:427-431`). `advance_and_finish()` `:481-522` iterates all `in_transit` rows each tick.
- **Tick pass** `CS/app/econ_tick.py:1595-1641` `_caravan_pass`: arrivals first, then snapshot → plan → `dispatch_tx` per plan. Called at `econ_tick.py:1401` before the region loop. Tick = 6 h slot run from `econ_scheduler.run_scheduled_once` (`econ_scheduler.py:89-107`).
- **Model** `CS/app/models.py:1029-1068` `EconCaravan`: no location/route/position/guards/raid columns; `status` VARCHAR(16) (`in_transit|delivered|cancelled`), `cancel_reason` VARCHAR(32), units DECIMAL(16,3), money BIGINT, no FK, no ENUM (migration `035_econ_caravans`).
- **Escrow** account kind `caravan_escrow` (singleton, ref_id 0). Sub-invariant: `escrow_balance == Σ(paid_purse + paid_treasury) of in_transit` — `economy_caravan_crud.py:126-138`, checked in summary `economy_crud.py:196-205` (part of `ok`) and `economy_caravan_crud.py:573`. **A raid that pays marks out of escrow breaks this formula** unless the formula subtracts the raided part (new column, e.g. `stolen_paid`).
- **Ops**: `OP_CARAVAN_DISPATCH/DELIVERY/CANCEL`, `CARAVAN_OP_TYPES` (`CS/app/econ_core.py:155-159`); all `apply_tax=False`.
- **Admin API** (`CS/app/economy_api.py:997-1035`): `GET /characters/admin/economy/caravans/overview`, `PUT .../caravans/pairs` (economy:settings), `GET .../caravans` (list, filters status/region/group; `SQL_CARAVAN_LIST` `economy_caravan_crud.py:607-619`, `_caravan_out` `:621-632`). Frontend `components/Admin/EconomyPage/EconomyCaravans.tsx`.
- **Region card leak**: `card_caravans()` `economy_caravan_crud.py:664-706` returns, per side (incoming/outgoing), the **other region's id/name and country** for caravans in transit or delivered within 24 h; served via `economy_sim_crud.py:982` (public region economy card) and rendered in `frontend/.../WorldPage/RegionEconomyCard.tsx:146-172` («везут руду из …»). For physical caravans this must be filtered (in transit at least; arguably also «delivered in last 24 h», since it reveals the pair afterwards).
- **Params** (`CS/app/econ_sim.py:149-157`, ranges `schemas.py:2085-2091`, int keys `:2134`, update schema `:2525+`): `caravans_enabled=1`, `caravan_surplus_share=.25`, `caravan_purse_share=.25`, `caravan_treasury_food_share=.5`, `caravan_travel_domestic=1`, `caravan_travel_foreign=2`, `caravan_min_value=10`, `caravan_max_per_run=200`. Stored in `econ_sim_settings.params` JSON (no DDL for new keys).
- **Volume/value (local DB, 5 participating regions, 2 countries, 0 enabled pairs)**: 10–17 caravans per run (≈13 avg, every 6 h), 504 total. Value: 414 < 50, 59 in 50–199, 20 in 200–999, 11 ≥ 1000 (max 6144; food avg 540, other groups avg 19–129). **Units are fractional**: jewelry avg 0.1 units, armor/weapons/household/magic ≈ 0.5–1.2 units per caravan; food ≈ 344 units, wood ≈ 32. So "N тюков from units" needs a value- or unit-based conversion that handles < 1 unit. No foreign caravans exist locally (no enabled pairs).

### 2. Movement and the location graph

- **Patrols (FEAT-204)** `CS/app/patrol_crud.py`: `step_guard()` `:232-283` (lock patrol row → lock guard → `blocked_reason()` `:125-141` (dead/KO/battle/encounter) → target → write `characters.current_location_id` directly → commit → per-player arrival sweep in own txns `:210-229`). `due_guards()` `:286-293` selects by `next_move_at <= now`. Interval `interval_min` default 20, jitter 25 % (`patrol_core.py:25`, `next_delay` `:86`). Driven by `law_pass._guard_patrols` (`law_pass.py:170-188`) inside the law pass (claim every 55 s, `law_pass.py:41,48-55`), which runs from `econ_scheduler.run_scheduled_once` every 60 s (`econ_scheduler.py:30,89-98`). A separate pass with its own throttle exists as precedent: `faction_pass` (`RUN_INTERVAL_SECONDS = 300`, `faction_pass.py:34-45`). **Caveat**: the economy tick runs synchronously in the same scheduler thread (`econ_scheduler.py:107`), so steps stall while a tick is running.
- A caravan is **not** a `characters` row; it cannot reuse `step_guard` directly, but the shape (row lock → due check → next location → `next_move_at` with jitter → commit) and the scheduler hook are directly reusable. The route is fixed, so the step is just `route_index += 1` (like `patrol_core.route_step`).
- **Graph**: `LocationNeighbors` (LS `models.py:164-172`, bidirectional rows, `energy_cost`, `is_auto_arrow`). `patrol_crud.neighbours_of()` `:93-99` reads it by raw SQL. **Cross-region edges exist and are materialised in the same table**: region transition arrows (`region_transition_arrows` / `arrow_neighbors`, LS `models.py:622-641`) are synced into `LocationNeighbors` rows with `is_auto_arrow=1` (`LS/app/crud.py:6433-6510` `sync_cross_region_neighbors`). So one BFS over `LocationNeighbors` covers inter-region travel. Local DB: 2287 locations, 4644 edge rows, 16 cross-region edge rows (14 auto-arrow), **0 cross-country edges**; 34 arrows, all within one country. Of the 5 economy regions, region 34 and the country-7 regions 14/15 have no arrows locally → their caravans would have no path (stay abstract).
- **Region "main location"**: there is no capital/hub field. Candidates: `Regions.entrance_location_id` (LS `models.py:63`) — **set for 0 of 27 regions locally**; `Districts.entrance_location_id` (1 set); `Regions.jail_location_id` (`:66`); `Locations.is_starting` / `quick_travel_marker`; or the location of a merchant NPC of the region. Region of a location: `COALESCE(Locations.region_id, Districts.region_id)` via `econ_core.SQL_RESOLVE_LOCATION` / `econ_ledger.resolve_location` (`CS/app/econ_ledger.py:105-112`, used by `reputation_crud.location_region` `:219`). Location rows with `marker_type='dungeon'` and `subdistrict` type exist and should probably be excluded from paths.
- **Pathfinding helpers**: none in CS/LS. Only a BFS over dungeon rooms in `dungeon-service/app/crud.py:3,409` (`deque`). A BFS over ~2.3k nodes / ~4.6k edges is trivial in-process (load once per dispatch pass).

### 3. Showing an entity in a location

- Location page `frontend/.../pages/LocationPage/LocationPage.tsx`: NPCs via `GET /characters/npcs/by_location` (`:199-215`; CS `main.py:3409-3439`, excludes mobs/dead/KO guards, patrol hint only coarse), mobs via `fetchMobsByLocation` (`:455`; CS `main.py:3883`, `crud.get_mobs_at_location` `:2077`, excludes `spawn_type='dungeon'`), packs via `/characters/mob-packs/by_location` (CS `main.py:4065`), players via `/characters/by_location` (CS `main.py:2271`). Enemies block: `EnemiesSection.tsx` (rendered at `LocationPage.tsx:855-861`, attack buttons `EnemiesSection.tsx:273-318` incl. «Группой»/«Соло»). A caravan block would be a new sibling section (or an entry in EnemiesSection).
- **Privacy**: these by_location reads are public GETs taking any `location_id` (no auth, no presence check). A caravan endpoint built the same way would let anyone scan all locations and reconstruct routes; it needs a "character is in this location" check (JWT + ownership + `current_location_id`), like `sell_to_npc` does (`LS/main.py:3263-3275`).
- Do **not** model guards as a placed `active_mob_packs` row at the caravan's location: packs are listed in «Противники» and do not move.

### 4. Attack flow today

- **Mob attack** BS `main.py:1159-1193` (`POST /battles/mob-attack`) and party version `:1196-1312` (`POST /battles/party/mob-attack`: leader pulls co-located squadmates from party-service `GET /party/internal/active-members`, skips gatherers/in-battle/activity-locked, cap `BATTLE_MAX_TEAM_SIZE=5` `config.py:21`). Packs: `:1319`, `:1372` (`_get_pack_roster` from CS `/characters/internal/mob-pack/{id}`).
- Restrictions applied: ownership, same location, `get_active_battle_for_character`, `_ensure_not_activity_locked` (`activity_lock.py:25-34` reasons: dungeon, unconscious, asleep, reading, jail, law_encounter), `_ensure_npc_available` (dead/KO NPC). **No level check exists** on mob attacks.
- **Combat gate (FEAT-145)**: every surface mob/pack attack requires consuming a moderator-approved «боевой пост» naming the target (`_consume_combat_gate` BS `main.py:1117-1137` → LS `/locations/internal/action-gate/consume`; UI «Нужен боевой пост» `EnemiesSection.tsx:282-287`). The brief does not mention a post for caravan raids — **needs a decision** (see Questions).
- **Service-initiated battle precedents**: dungeon (`POST /battles/internal/dungeon`, BS `main.py:1633+`; mobs spawned on demand by CS `POST /characters/internal/spawn-dungeon-mobs` `main.py:4297-4348` with `stat_multiplier`, `spawn_type='dungeon'` hidden from location lists, despawned after by `/internal/despawn-dungeon-mobs` `:4351`) and the guard battle (`POST /battles/internal/guard` BS `main.py:1698-1764`, tagged by `battles.law_encounter_id` → `_assemble_battle(..., law_encounter_id=)` `:946-960` → end callback `_notify_law_battle_end` `:1797-1813` → CS `POST /characters/internal/law/battle-result` (`law_api.py:204`), plus a lost-callback poll in `law_pass._lost_callbacks` via `GET /battles/internal/{id}/result` (`BS main.py:1926-1960`). A caravan raid fits this pattern: new nullable tag column on `battles` (BS migration 010) + callback + poll fallback. `spawn_mob_from_template` (`CS/crud.py:1817`) creates a `characters` row per mob + HTTP to character-attributes-service, so spawning guards **at attack time** (dungeon style) is far cheaper than at dispatch.
- **Battle end hooks** (BS `main.py:2760-2828`): `_distribute_pve_rewards` (`:478-620`: for each defeated mob → `GET /characters/internal/mob-reward-data/{id}` → XP via `/characters/{id}/add_rewards`, loot-table items via IS `POST /inventory/internal/characters/{id}/items`, `active-mob-status` dead, bestiary `record-mob-kill`; mobs give **no gold** since 2026-10-25); non-mob NPC deaths → CS `PUT /characters/internal/npc-status/{id}` (reputation + crime via `shadow_crud.npc_kill_consequences`, CS `main.py:4198-4256`); law callback; faction callback `_notify_faction_battle_end` (`:1861`, kill points for mob templates listed as faction enemies — `faction_kills.py`). Guard mobs spawned from regular templates would also drop their loot tables / give XP / faction points unless excluded.
- Battle type enum `pve|pvp_training|pvp_death|pvp_attack` (BS `models.py:20-24`) — a new value means an ENUM ALTER; a tag column on `pve` avoids it. Turn timeout is 24 h (`config.py:11`), so a raid battle can last days.

### 5. Law / shadow / reputation

- **Offense type already reserved**: `CRIME_CARAVAN_ATTACK = "caravan_attack"` (`CS/app/law_core.py:36-37`, «reserved for future sources»); admin label exists (`frontend/.../ReputationPage/shadowLabels.ts:7`). Reputation action `caravan_attack` «Нападение на караван» −100 is seeded builtin with `has_source=0` (`reputation_core.py:42,94-102`; migration `038_reputation.py:62`).
- **Crime pipeline to reuse**: `shadow_crud.npc_kill_consequences()` (`shadow_crud.py:212-306`) is the template: one group witness roll (`sc.base_pct(location marker)`, per-member stealth `law_crud.stealth_info` `law_crud.py:210-218`, mask `wears_mask`, fame), witnessed → `reputation_crud.apply_npc_kill_for` + `law_crud.register_crime(status=reported)` (wanted applied at once, `law_crud.py:440-460`); unseen/masked → deferred crime (`unwitnessed|masked`, `reveal_until`, `next_roll_at`) + region suspicion (`add_suspicion`), revealed later by `law_pass._reveal_crimes`. Infamy is added for every crime row inside `record_crime` (`law_crud.py:377-414` → `renown_crud.add_infamy`). Notices published after commit via `KillOutcome.publish()` (`shadow_crud.py:187-192`, `law_notify`).
- **Limit**: one `law_crimes` row stores exactly one deferred reputation change (`reputation_delta/key/reason`, `models.py:1320-1322`) for its own region. Reputation loss in the **seller's and buyer's regions** (brief) is not expressible as one crime row; options: separate `apply_reputation` calls (immediate, `reputation_crud.py:417`, idempotent per key, echo to same-country regions at `echo_pct`=20 %), or extra rows. Also note `apply_reputation` already echoes to all other regions of the same country, which may double-count when seller/buyer are in the raid's country.
- Guard presence (FEAT-203): forced witness only for guard-encounter battles (`is_guard_encounter_battle`); location marker drives base witness %. Patrol arrival sweep (`patrol_crud._sweep_candidates` `:196-207`) will pick the raider up afterwards via wanted/negative reputation.

### 6. Items, merchants, fence

- `items` (IS `models.py:19-112`): `name` VARCHAR(100) **UNIQUE**; `item_type` ENUM (`head…furniture`; ENUM ALTER locks the big table — memory note: prefer VARCHAR/avoid ENUM changes); `resource_subcategory` ENUM; `price`, `max_stack_size`, flags `is_food`, `is_mask`, `is_elite_trophy`, `admin_ready`. Item seeding by migration has precedent (IS `alembic/versions/007_add_sharpening_system.py:42-48`). `character_inventory` (`models.py:301-312`) has **no per-instance flag** (stacks keyed by item_id; only identify/enhancement/sockets/durability). So «краденое» is either a separate template (12 stolen + 12 clean = 24 items, distinct names) or an item-level flag column (`items.is_stolen`).
- **Goods group mapping**: `econ_core.auto_item_group` (`LS/app/econ_core.py:441-465`) + admin override table `econ_item_groups` (owned by CS, migration `028_econ_living_regions.py:321`) with `group_code` + `off_market`; `effective_item_group` `:815-833`. 12 groups (local `econ_goods_groups`): food, ore_metal, wood, herbs, hides_textiles, magic, weapons, armor, jewelry, potions, tools, household.
- **Sell path** (LS `main.py:3249-3360` `sell_to_npc`): ownership, activity lock, **FEAT-145 npc_dialogue gate** (`_require_npc_gate`), same location, `merchant_market()` (`crud.py:4423-4452`: "living" if the NPC is alive, has a location in a simulated region — **`npc_role` is not checked**; any NPC with `npc_shop_items` rows is a merchant), reputation terms (outlaw refused), `quote_bids()` (`crud.py:4766-4791` → `quote_bid` `:4743` → `econ_core.shop_row_bid`): an explicit shop row with `sell_price` wins; a living merchant without a row also buys **any on-market item of his goods groups** at `floor(base × bid_share)` × region mult. Payment: living → `pay_player_from_merchant` (NPC character account → player, invariant-safe), legacy → treasury → player. `get_sell_offers` `crud.py:4802-4840`.
  - Consequence: stolen bales mapped to a goods group and on-market would be **auto-bought by ordinary living merchants** dealing in that group. Making them `off_market` (econ_item_groups override or auto rule) stops the auto-bid but then a fence also has no default price → fence logic needs its own pricing branch (e.g. role `fence` → buys stolen items at `group price × fence_share`) in `quote_bid`. Shop rows created manually by an admin would still bypass any rule.
  - Other outlets for stolen items: player-to-player trade (`TradeModal`), auction (FEAT auction NPC), guild orders (`economy_guild_crud`, FEAT-193 accepts on-market items of a group), faction item donations (`faction_items.py:1-10`, "on-market with a goods group"), minter (ore). All need a stolen check if the rule is strict.
- **NPC roles**: free `String(50)` (`CS/models.py:65`), **no backend validation**; frontend list `frontend/.../constants/npc.ts:1-27` (`NPC_ROLES`, `NPC_ROLE_LABELS`, `NPC_ROLE_ICONS`), reputation role weights `reputation_npc_role_weights` + `_PEACEFUL_ROLES` (`reputation_core.py:105-106`) decide kill points (a new role falls to the `*` fallback). Local counts: merchant 147, guard 113, bandit 17, mercenary 12, mob 94, …

### 7. Economy invariant

- `econ_core.py` is byte-identical in CS, IS, LS, dungeon-service (`scripts/check_econ_copies.sh:43-47`, plus `tests/econ_contract_cases.py` copies); sync ledger CS/IS, async ledger LS/dungeon. `validate_operation` rejects unknown op types (`econ_core.py:515`) and any leg touching source kinds outside `SOURCE_OP_TYPES` (`:543`). `econ_operations.op_type` is VARCHAR(50) (no DDL).
- Raid payout = `caravan_escrow → character(raider)` (marks share). No existing op type fits semantically (`caravan_cancel` is defined as refund to buyer accounts; reusing it would mislabel history and admin filters). **A new op kind (e.g. `caravan_raid`) is effectively unavoidable** → edit CS `econ_core.py` (`CARAVAN_OP_TYPES`) and copy byte-for-byte to the other 3 services (+ contract cases if they enumerate op types). Partial delivery after a raid = existing `caravan_delivery` with reduced value (or value of the remaining units), seller paid only for delivered part — no new op needed for that. Fence sale = existing `npc_shop_sell` / merchant path (NPC account → player). Escrow sub-invariant formula must change (see §1).
- Inbound "on the road" units feed planning and guild thresholds (`load_snapshot` inbound, `guild_open_threshold_pct` `econ_sim.py:161`); stolen units must be subtracted.

### 8. Migrations, permissions, background loops

- Next migrations: **CS 050** (after `049_mob_admin_ready`), **IS 037** (after `036_item_admin_ready`), **LS 059** (after `058_quest_faction_vouchers`), **BS 010** (after `009_battle_law_encounter`), user-service **0036** (after `0035_faction_economy_perm`). Revision ids ≤ 32 chars.
- Permissions: `economy:read` / `economy:settings` already guard the caravan admin API — likely sufficient; any new permission must be seeded explicitly in `user-service/tests/test_rbac_permissions.py`.
- Background loops in CS: one daemon thread `econ_scheduler` (60 s poll) → reputation decay → law pass (55 s claim; incl. patrols) → faction pass (300 s claim) → economy tick (6 h slot). A caravan stepping pass would be a fourth claimed pass there (or a step inside the law pass). Env kill switch `ECON_TICK_ENABLED` disables the whole thread (`econ_scheduler.py:28,41-42`).

### Existing Patterns

- CS: sync SQLAlchemy, raw parameterised SQL for foreign tables, Pydantic v1, Alembic (`alembic_version_character`), every multi-step flow = own short transactions with a documented global lock order (`economy_caravan_crud.py:13-19`), idempotency keys on ledger ops / crimes / reputation, notices published after commit.
- BS: async; service-to-service callbacks fire-and-forget with 3 retries + poll fallback.
- LS: async; owns `npc_shop_items`, Locations/Neighbors; byte-copies of econ_core/reputation_core.

### Cross-Service Dependencies (new/used)

- CS → BS: create raid battle (new internal endpoint, like `/battles/internal/guard`); BS → CS: raid battle-result callback (new), CS → BS poll `GET /battles/internal/{id}/result` (exists).
- CS → party-service `GET /party/internal/active-members` (exists) for group raids, or the raid is started by BS like `party/mob-attack`.
- CS → IS `POST /inventory/internal/characters/{id}/items` (exists) for bales.
- CS → character-attributes-service (inside `spawn_mob_from_template`) for guard mobs.
- LS sell path reads items/econ_item_groups (shared DB) for the stolen/fence rule.

### DB Changes (likely)

- CS 050: `econ_caravans` + columns (e.g. `is_physical`, route JSON or child table `econ_caravan_route(caravan_id, position, location_id)`, `route_index`, `current_location_id`, `next_move_at`, `guard_count`/power, `raid_status`/`raided_at`/`raid_battle_id`, `stolen_units`, `stolen_paid`); new raid table (participants, payout, crime ids) if needed; seed `econ_item_groups` rows for the bales; possibly fence settings in SimParams JSON (no DDL).
- IS 037: insert 12/24 bale items (or `items.is_stolen` column).
- BS 010: `battles.caravan_id` (nullable, indexed) tag.
- LS: probably none (fence by role + item flag).

### Risks

- **Path availability**: no region hub field is filled (0/27 `entrance_location_id` locally), 0 cross-country edges locally, several economy regions have no arrows → most caravans could stay abstract unless admins fill hubs/arrows on prod. → Architect must define the hub rule + an admin warning list "regions without hub / without path"; check prod data before rollout.
- **Escrow sub-invariant / summary `ok`** breaks unless the expected formula accounts for raided money. → new column + updated `escrow_expected`, tests on world sum 0 after every step.
- **Delivery outside the tick** conflicts with `finish()`'s run-based guards (`last_run_id`, "region already ticked → postpone"). → separate delivery function with the same lock order; decide interaction with a concurrently running tick (tick and stepping run in the same thread today, so no true concurrency unless a manual run via admin API).
- **Stalled caravans**: battles can last up to days (24 h turn timeout); "caravan in battle stays put" may freeze delivery and money in escrow for long. → cap / time-out rule.
- **Route privacy**: public by_location-style endpoints let anyone scrape positions; region card currently names counterpart regions; admin-only fields must not leak into public schemas.
- **Guard mobs side effects**: regular mob templates bring XP, loot tables, bestiary entries, faction kill points; leftover `characters` rows. → dungeon-style spawn/despawn, decide reward exclusions.
- **Stolen goods leakage** through trade/auction/guild orders/faction donations/merchant auto-bid unless all outlets check the stolen mark.
- **Fractional units** (0.1–1.2 for expensive groups) vs integer bales.
- **econ_core byte copies** (4 services) + CI guard; forgetting one = CI fail.
- **FEAT-145 combat gate**: if raids require a post, a moderator must approve before the caravan moves on (15–20 min) — practically impossible; if not, raids are the first gate-free surface attack.

### Questions for PM / user

1. **Боевой пост**: нападение на мобов сейчас требует одобренного модератором «боевого поста». Для налёта на караван пост нужен или нет? (Караван уходит через 15–20 мин — с постом успеть почти нельзя.)
2. **«Главная локация» края**: в базе нет «столицы региона»; поле «вход в регион» не заполнено ни у одного из 27 регионов локально. Можно ли попросить админов заполнить его (и межстрановые переходы — локально их нет вовсе), или выбирать автоматически?
3. **Краденое в обход скупщика**: можно ли краденые тюки передавать/продавать другим игрокам (обмен, аукцион), сдавать в заказы гильдии или фракции? Или краденое продаётся только скупщику?

Technical (architect): hub rule, stepping pass placement, guard spawn timing/strength formula, bale conversion for fractional units, op type name, reputation in seller/buyer regions (immediate vs deferred with the crime), stolen-mark representation (24 templates vs `items.is_stolen`), delivery-during-battle rule, caravan cancellation while physical/raided.

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Verified facts / corrections to the analysis

- **Combat gate**: a NEW post grants its gates immediately (`LS main.py:1076-1084` → `crud.create_action_gates`); moderator approval exists only for gates added later by editing a post (`post_gate_requests`, `crud.py:1614-1636`, approval `crud.py:4057-4145`). So "post waiting for a moderator" = a pending `post_gate_requests` row. The caravan hold (3.4) covers both: an open gate and a pending request.
- Region guard station = `Regions.jail_location_id`, read by `law_facility.station_location()` (`CS law_facility.py:62-68`).
- `misc` items have no goods group (`econ_core.auto_item_group`, `_ITEM_TYPE_GROUPS` has no `misc`) → `effective_item_group` makes them **off-market**. Ordinary living merchants' auto-bid (`econ_core.shop_row_bid` `:1158`), guild orders (`economy_guild_crud.py:572-576,643`) and faction donations (`faction_items.py:108`) already refuse such items. Stolen bales are `misc` → those outlets need no new code (tests only).
- Everything else in section 2 (escrow sub-invariant `economy_crud.py:196-205`, `finish()` tied to run ids, `card_caravans` leak, `_assemble_battle` tag pattern, law callback + poll, `spawn_mob_from_template` committing, `npc_kill_consequences`, `quote_bids`, op type validation) confirmed.

### 3.1 Overview

```
6 h tick (_caravan_pass) ── dispatch() ──► physical? (rule 3.2) ──► route (BFS) stored on econ_caravans row
                                                   │no / no road → abstract (old behaviour)
caravan_pass (new, every ~55 s, scheduler thread) ─┼─► step due caravans (route_index+1) unless HELD
                                                   ├─► deliver arrived caravans (escrow → seller/duty; goods)
                                                   ├─► raid housekeeping (poll lost callbacks, expire, payouts, bales)
player in location ── GET /characters/caravans/here ─► block «Торговый караван: руда, охрана 4» [Напасть]
post with gate «caravan» (LS) ─► open action_gate (holds the caravan ≤ 2 h)
[Напасть] ─► CS POST /characters/caravans/{id}/raid ─► raid row (UNIQUE caravan) ─► spawn guards (hidden mobs)
            ─► BS POST /battles/internal/caravan-raid (consumes gate, party roster, pve battle tagged caravan_raid_id)
battle end ─► BS → CS POST /characters/internal/caravans/raid-result (+ poll fallback)
            ─► win: escrow → raiders (op caravan_raid), stolen_units, bales via IS, crime/reputation/infamy
            ─► loss/abort: nothing; caravan moves on
player ─► fence NPC (role «fence») ─► LS GET/POST /locations/npcs/{id}/fence/... (NPC cash → player, npc_shop_sell)
6 h tick ─► fence refill: region purse → fence cash up to its target (merchant_trade)
```

### 3.2 Physical selection and routes (character-service)

**Region trade gate** (start/end of every route): `econ_regions.trade_gate_location_id` (new, admin override «Торговые ворота края») else `Regions.jail_location_id` (guard station) else none. No gate on either side → abstract.

**Graph**: `LocationNeighbors` (both directions stored, cross-region auto-arrow rows included), loaded once per caravan pass of the tick into memory (`caravan_route.load_graph(db)`: one SELECT of edges + one SELECT of `Locations.id, marker_type`). Intermediate nodes exclude `marker_type='dungeon'`. Endpoints are always allowed. **Shortest path by hop count** (BFS, neighbours in ascending id → deterministic). Path longer than `caravan_route_max_steps` hops → no road.

**Rule** (pure, `econ_caravan.choose_physical(...)`), evaluated in `dispatch()` after `clamp_dispatch` (final value known):
1. `caravan_physical_enabled = 0` → abstract;
2. route missing → abstract;
3. active physical in transit ≥ `caravan_physical_max_active` → abstract;
4. `value >= caravan_physical_min_value` (large) OR `from_country != to_country` → physical;
5. else physical when `u < caravan_physical_small_chance`, `u` = deterministic hash of `(run_id, from, to, group)` → [0,1) (stable across a resumed run).

Route planner (`RoutePlanner`: graph + gates + active physical count) is built once in `econ_tick._caravan_pass` before the dispatch loop and passed to `dispatch_tx(..., planner=)`; the planner increments its local counter on every physical dispatch. A failure to build the planner → logged, all caravans of this run abstract (never fails the tick).

Physical row at dispatch: `is_physical=1`, `route` = JSON list of location ids (start … end, length ≥ 2), `route_index=0`, `current_location_id=route[0]`, `next_move_at = now + next_delay(caravan_step_minutes, 25 %, u)` (reuse `patrol_core.next_delay`), `guard_count = econ_caravan.guard_count(value, params)`. `travel_runs/runs_left` are still written (NOT NULL) but ignored for physical rows.

### 3.3 Stepping and delivery (new module `caravan_pass.py`)

Called from `econ_scheduler.run_scheduled_once` **after** `run_faction_pass` and **before** the economy tick, wrapped like the others (`run_caravan_pass`, failures logged, never block the tick). Own claim: `UPDATE econ_sim_settings SET caravan_pass_last_run_at=:now WHERE id=1 AND (… IS NULL OR … <= now-55 s)` (faction_pass pattern). Skipped when `econ_tick.is_tick_enabled()` is false (economy frozen → caravans frozen) or `caravans_available()` is false. Steps, each best effort, own short transactions, batch 200:

1. `_stale_raids` — `starting` raids older than 10 min with no `battle_id` → guards despawned, raid row DELETED (the caravan may be raided again; a late callback for a deleted raid is ignored).
2. `_raid_battles` — `fighting` raids started > 2 min ago: poll `battle_client.get_battle_result(battle_id)`; finished → `settle_raid(...)` (same function as the callback); 404 → treated as aborted; still running and older than `caravan_raid_battle_max_hours` → raid `expired` (no loot), caravan released (a later callback finds the raid not `fighting` → only despawns guards).
3. `_raid_followups` — `won` raids with `law_done=0` → law step; shares with `bales > 0 AND bales_delivered_at IS NULL` → IS add-items, then mark; raids with `guards_despawned=0` and final status → despawn.
4. `_step_caravans` — `is_physical=1 AND status='in_transit' AND next_move_at <= now AND arrived_at IS NULL` ascending id. Per caravan, one tx: lock `econ_caravans` row → re-check → **held?** (3.4) → if held: set `hold_started_at` if NULL, commit, skip; else `route_index += 1`, `current_location_id = route[route_index]`, `next_move_at = now + next_delay(...)`; when `route_index == len(route)-1` → `arrived_at = now`. Commit.
5. `_deliver_arrived` — rows with `arrived_at IS NOT NULL AND status='in_transit'`; **skipped entirely while an economy run is `running`** (`econ_tick_runs.status='running'`), so a region is never changed in the middle of a resumable run. `deliver_physical(db, caravan_id, now)` = same lock order as `finish()` (`econ_regions ×≤2 asc → econ_region_goods ×≤2 asc → econ_caravans(row) → econ_accounts`), no run-id logic:
   - destination participates and has the goods row → `dest.stock += units - stolen_units`; remaining escrow `R = paid_purse + paid_treasury - raid_paid`; `duty' = floor(duty × R / (value + duty))` (`duty` when `raid_paid = 0`), `seller' = R - duty'`; op `caravan_delivery` legs escrow→seller purse `seller'`, escrow→buyer country `duty'`; key `caravan:c<id>:done`; metadata adds `physical: true, stolen_units, raid_paid`; status `delivered`, `finished_at=now`, `finished_run_id=NULL`.
   - else cancel exactly like `finish()` (goods `units - stolen_units` back to origin when it exists), refund of `R` split: `purse_back = paid_purse - floor(raid_paid × paid_purse / (paid_purse + paid_treasury))`, `treasury_back = R - purse_back`; op `caravan_cancel`, key `:back`.
   - Duplicate ops → `DuplicateOperation` → rolled back, counted as already.

Abstract path changes: `in_transit_rows()` / `advance_and_finish()` only `is_physical = 0`.

Pure helpers in `econ_caravan.py`: `choose_physical`, `guard_count`, `guard_multiplier`, `remaining_payout(value, duty, paid_total, raid_paid) -> (seller, duty)`, `refund_split(paid_purse, paid_treasury, raid_paid)`, `stolen(units, unit_price, share) -> (units, value)`, `bale_count(stolen_value, bale_price)`, `split_loot(marks, bales, attacker_ids, leader_id)`. New pure `caravan_route.py`: `shortest_route(adj, blocked, start, goal, max_steps)`, `effective_gate(override, station)`.

### 3.4 Hold rules (stepping pass, read-only raw SQL on LS tables)

A caravan does not step while ANY of:
- its raid row is `starting` or `fighting` (no time cap here except `caravan_raid_battle_max_hours` via step 2);
- **post hold**, only while `hold_started_at IS NULL OR now < hold_started_at + caravan_post_hold_max_min`: an `action_gates` row `action_type='caravan' AND target_ref=:caravan_id AND location_id=:current AND status='open'`, or a `post_gate_requests` row `status='pending' AND location_id=:current` whose `gates` JSON has `{"action_type":"caravan","targets":[…caravan_id…]}`.

`hold_started_at` is set once (first time held) and never reset → one 2-hour window per caravan for the whole route (stalling cannot be repeated by a griefer). After the window the gate stays open but becomes useless as soon as the caravan leaves (the raid requires the caravan at the gate's location, and gate consumption matches `location_id`).

### 3.5 Visibility (player)

- New `GET /characters/caravans/here?character_id=` (JWT + owner). Location = the character's own `current_location_id` (no location parameter → no remote scanning). Returns only physical in-transit caravans at that location, **never** from/to, route or value.
- `card_caravans()` (public region card) gets `AND c.is_physical = 0` → physical caravans never appear in region cards (neither in transit nor delivered). No other public read exposes caravans.
- Admin reads (economy:read) show everything.

### 3.6 Raid start (character-service orchestrates, battle-service builds the fight)

`POST /characters/caravans/{caravan_id}/raid` (async endpoint, sync crud via threadpool):

1. Owner check (`_require_owner` pattern from `law_api.py:59`); character not NPC.
2. Tx A: lock caravan row FOR UPDATE; checks → errors (Russian):
   404 «Караван не найден» (missing / not physical / not in_transit); 400 «Каравана нет в вашей локации» (`current_location_id` ≠ character's); 409 «Этот караван уже ограблен или на него уже напали» (raid row exists); 409 «Караван уже прибыл» (`arrived_at` set); 409 «Охрана караванов не настроена — налёт невозможен» (empty guard pool). INSERT `econ_caravan_raids` (status `starting`, leader, is_group, location, region of the location) — UNIQUE `caravan_id` = one raid per caravan; IntegrityError → the same 409. Commit.
3. Guards: template = pool entry whose `mob_templates.level` is closest to `Locations.recommended_level` of the caravan's location (ties → lower id); count = `guard_count` stored on the row; multiplier = `guard_multiplier(value, marker_type, params)`; `crud.spawn_mob_from_template(db, tpl, location, "dungeon", stat_multiplier=m)` N times (dungeon spawn type = hidden from location lists, existing despawn semantics). Store `guard_ids`, `guard_template_id`, `guard_mult`. Spawn failure → despawn the ones created, delete raid row, 500 «Не удалось собрать охрану каравана».
4. `battle_client.create_caravan_raid_battle(...)` → BS (3.7). BS 4xx → despawn, delete raid row, relay BS status + detail; network/5xx → same cleanup, 503 «Сервис боя недоступен — налёт не начат».
5. Tx B: raid → `fighting`, `battle_id`, `attacker_ids` (from BS), `started_at`. Commit. Response `{raid_id, battle_id}`; frontend navigates to the battle page.

Activity / restriction checks are those of the mob attack (not in battle, not activity-locked: jail / dungeon / unconscious / law encounter / reading / asleep), done by BS on every pulled attacker (leader must be free). **No level check** (none exists for mobs).

### 3.7 Battle-service contract

- Migration `010_battle_caravan_raid`: `battles.caravan_raid_id INT NULL` + index. Model + `crud.create_battle(..., caravan_raid_id=None)` + `_assemble_battle(..., caravan_raid_id=None)` (passed only when set, like `law_encounter_id`).
- `POST /battles/internal/caravan-raid` (`verify_internal_token`), body `CaravanRaidBattleCreate {caravan_raid_id: int, caravan_id: int, leader_character_id: int, group: bool, guard_character_ids: List[int] (1..5), location_id: int}`:
  leader exists, `current_location_id == location_id`, not in battle (409 «Персонаж уже в бою»), `_ensure_not_activity_locked`; guards are NPCs at the location and free (409 «Охрана каравана недоступна»); group → the same co-located squad roster as `party_mob_attack` (party-service active-members, skip gatherers / in battle / activity-locked, cap `BATTLE_MAX_TEAM_SIZE`), extracted into a shared helper `_free_squadmates(leader_id, loc)` used by both endpoints without behaviour change (400 «Вы не состоите в отряде» / «Нет соотрядцев на этой локации», 503 «Сервис отрядов недоступен»); then **gate consumption** with `action_type='caravan'`, `target_ref=caravan_id` (generalise `_consume_combat_gate` into `_consume_action_gate(character_id, location_id, action_type, target_ref)`; mob attacks keep `combat`) → 403 «Нужен боевой пост с этим караваном, чтобы напасть»; then `_assemble_battle(attackers + guards, [0…]+[1…], "pve", loc, caravan_raid_id=…)`.
  Response 201 `{battle_id, participants, next_actor, deadline_at, attacker_character_ids: List[int]}`.
- End hooks: `_notify_caravan_battle_end(db, battle_id, winner_team, aborted=False)` after the law notify in the finish path, and with `aborted=True` in the force-finish path (`main.py:5721` area); fire-and-forget POST `/characters/internal/caravans/raid-result` `{battle_id, caravan_raid_id, winner_team, aborted}` with 3 retries (copy of `_post_law_callback`).
- `GET /battles/internal/{id}/result` adds `caravan_raid_id` (additive).
- `POST /battles/{battle_id}/join-request`: battles with `caravan_raid_id` → 400 «К налёту на караван нельзя присоединиться».
- PvE rewards for the guards stay as for any mob (XP, template loot, bestiary) — admins pick guard templates accordingly.

### 3.8 Raid settlement (character-service)

`POST /characters/internal/caravans/raid-result` (`verify_internal_token`) and the poll call the same `caravan_raid_crud.settle_raid(db, raid_id, battle_id, winner_team, aborted, now)`. Raider team = 0, guard team = 1 (constants).

**Tx 1 (economy)**, lock order `econ_caravans(row) → econ_caravan_raids(row) → econ_caravan_raid_shares (insert) → characters (asc, ledger) → econ_accounts (asc)`:
- raid not `starting/fighting` → no-op (`already`); `battle_id` from the payload is accepted when the row is still `starting`.
- aborted → `aborted`; winner ≠ 0 or None → `repelled`.
- winner 0 → `won`: `(stolen_units, stolen_value) = stolen(units - previous stolen, unit_price, caravan_raid_goods_share)`; `marks = floor((paid_purse + paid_treasury) × caravan_raid_marks_share)`; `bales = bale_count(stolen_value, bale.price)` where the bale is the IS item with `is_stolen=1 AND bale_group=:group` (round-half-up; missing item / price ≤ 0 → 0 bales); split among `attacker_ids` that are players (`is_npc=0`): marks equal, remainder to the leader; bales round-robin starting with the leader. Ledger `caravan_raid` legs `caravan_escrow → character(raider)` for every share > 0, `apply_tax=False`, key `caravan:c<id>:raid`, `region_id` = raid region, metadata `{caravan_id, raid_id, battle_id, group_code, stolen_units, stolen_value, bales}`. Caravan: `stolen_units += …`, `raid_paid += marks`. Raid: totals + `payout_op_id`. Shares rows. `CharacterLog` per raider (`event_type='caravan_raid'`, «Налёт на караван (<группа>): добыча N марок, M тюков»).
- Every outcome: caravan `next_move_at = now + next_delay(...)` (moves on with the rest), `finished_at` on the raid.
- Commit; then notices (after commit, `law_notify.Notice`, category progress): win «Налёт удался: N марок и M тюков «<bale>»», loss «Охрана каравана отбилась», abort — none.

**Tx 2 (law)** for `won` only — `shadow_crud.caravan_raid_consequences(db, raid, caravan, now)` (new, modelled on `npc_kill_consequences` `shadow_crud.py:212-306`):
- crime type `lc.CRIME_CARAVAN_ATTACK`; reputation delta = `reputation_actions['caravan_attack'].points` (builtin −100, admin-editable = «тяжесть»); wanted points = `lc.crime_weight(delta)`; region = raid region; event key `crime:caravan_raid:<raid_id>:<cid>`; reputation key `caravan_raid:<raid_id>:<cid>`; `victim_id=NULL`, `battle_id`, `location_id`.
- witness: forced when `not s.witness_enabled` or **city guards are at the location** (`law_crud.guards_at(db, location, now)` non-empty — FEAT-203 reaction), else one group roll exactly like the kill (marker base %, stealth, mask, fame). Witnessed unmasked → `apply_reputation(action='caravan_attack', region=raid region)` + `register_crime(status=reported)` (wanted at once); unseen / masked → deferred crime with snapshot + suspicion (existing reveal pass applies the raid-region reputation later).
- **Seller and buyer regions** (only on the witnessed path, at once): `apply_reputation(action='caravan_attack', region=r, delta=round(delta × caravan_rep_trade_share), echo=False, idem_key=caravan_raid:<raid_id>:<cid>:r<r>)` for each distinct region in `{from_region_id, to_region_id} − {raid region}` that still exists. Deferred crimes do not touch seller/buyer (accepted simplification).
- Infamy: automatic through `record_crime` → `renown_crud.add_infamy`.
- raid `law_done=1` in the same tx; commit; `KillOutcome.publish()`.

**After**: bales via IS `POST /inventory/internal/characters/{id}/items` (`{item_id, quantity}`), mark `bales_delivered_at`; failures retried by the pass (a crash between IS success and the mark can double-deliver once — logged, accepted). Despawn guards (`ActiveMob` rows `spawn_type='dungeon'` of `guard_ids`, factor the body of `despawn_dungeon_mobs_endpoint` into `crud.despawn_dungeon_mobs(db, ids)`), `guards_despawned=1`.

Defeat: no crime, no reputation (brief: «обычные последствия проигранного боя»).

### 3.9 Economy ledger and invariants

- `econ_core.py` (canonical CS): `OP_CARAVAN_RAID = "caravan_raid"  # escrow -> raiders (marks share of a raided caravan)`, added to `CARAVAN_OP_TYPES` (→ `OP_TYPES`). Nothing else changes. Copy byte-for-byte to IS, LS, dungeon-service.
- `tests/econ_contract_cases.py` (canonical CS): `CARAVAN_OP_TYPE_NAMES` += `"caravan_raid"`, one CASE (escrow → two characters, untaxed, no sources, never negative). Copy to the 3 other services. `sh scripts/check_econ_copies.sh` must be green.
- Escrow sub-invariant: `escrow_expected = Σ(paid_purse + paid_treasury − raid_paid)` of `in_transit` (one SQL change in `escrow_expected`; summary `ok` unchanged in shape).
- Inbound "on the road": `load_snapshot` and `economy_guild_crud.py:196` use `SUM(units - stolen_units)`.
- World sum = 0 after every step: dispatch (purse→escrow), raid (escrow→characters), delivery/cancel (escrow→seller/duty/refund — exactly the rest), fence sale (NPC→player), fence refill (purse→NPC). No source accounts touched.
- Frontend journal label `caravan_raid: 'Караван: налёт'`.

### 3.10 Stolen bales (inventory-service)

Decision: **separate item templates with an item-level flag**, not a per-instance flag (`character_inventory` stacks by `item_id`; a per-instance flag would have to travel through trade, storage, auction, houses, mail…).
- Migration `037_stolen_bales`: `items.is_stolen BOOLEAN NOT NULL DEFAULT 0`, `items.bale_group VARCHAR(32) NULL` (VARCHAR, no ENUM ALTER), INSERT 12 items (skip a name that already exists): `item_type='misc'`, `item_rarity='common'`, `max_stack_size=999`, `price=50` (admin tunes later), `is_stolen=1`, `bale_group=<code>`, `description` «Краденый товар. Его купит только скупщик.», names:
  food «Тюк зерна (краденое)», ore_metal «Слиток руды (краденое)», wood «Связка древесины (краденое)», herbs «Тюк трав (краденое)», hides_textiles «Тюк кож и тканей (краденое)», magic «Ящик магических материалов (краденое)», weapons «Ящик оружия (краденое)», armor «Тюк доспехов (краденое)», jewelry «Шкатулка украшений (краденое)», potions «Ящик зелий (краденое)», tools «Ящик инструментов (краденое)», household «Тюк утвари (краденое)».
  Downgrade: delete those 12 rows (inventory rows cascade per existing FKs — verify; pre-beta data loss accepted), drop both columns.
- Model + item read schemas expose `is_stolen` and `bale_group` (read-only; not in `ItemCreate` → a normal edit keeps them, like `admin_ready`).
- `misc` ⇒ off-market ⇒ ordinary merchant auto-bid, guild orders and faction donations already refuse (3.0). **Auction**: `deposit_to_auction_storage` refuses `is_stolen` → 400 «Краденое нельзя выставить на аукцион». Player-to-player trade stays allowed.

### 3.11 Fence («Скупщик», role `fence`)

- NPC role value `fence` (free string; frontend label «Скупщик», icon). Reputation kill weight falls to `*` (−150) — no change.
- CS table `econ_fences` (settings per NPC): `npc_id INT PK` (no FK), `is_active BOOL NOT NULL DEFAULT 1`, `price_pct SMALLINT NOT NULL DEFAULT 40` (1..100, % of the region market value), `accepted_groups JSON NULL` (NULL/[] = all 12 groups), `cash_target BIGINT NOT NULL DEFAULT 2000` (0..10 000 000), `updated_at`, `updated_by`.
- **Price** per bale: `floor(items.price × price_mult(region, bale_group) × price_pct / 100)`; `price_mult` = `econ_region_goods.price_mult` of the fence's region (1.0 when the region is not simulated or has no row); < 1 → «не берёт». No reputation cut and **no outlaw refusal** (the fence serves criminals). The FEAT-145 `npc_dialogue` gate and the NPC tier gate (`_require_npc_gate`) apply as for any NPC trade.
- **Cash**: the fence pays from his own NPC account (`crud.pay_player_from_merchant`, op `npc_shop_sell`, metadata `fence: true`); 409 «У скупщика сейчас нет денег» when short. Bought bales are destroyed (removed from the player via IS with the player JWT, exactly like `sell_to_npc` steps 4-5 incl. the return-on-failure path; nothing is stocked).
- **Refill (closed economy)**: in the 6 h tick, after the region loop, `_fence_pass(session_factory, run_id, params)`: per participating region, fences that are `is_active`, role `fence`, alive, located in the region (ascending npc id); one tx per region: lock `econ_regions(row)` → fence `characters` (asc) → `econ_accounts`; budget `floor(purse × fence_purse_share)`; each fence gets `min(cash_target − cash, budget left)`; op `merchant_trade` legs `population_purse → character(fence)`, `apply_tax=False`, key `fence:<run>:r<region>`, metadata `{fence: true}`. Existing op type, no econ_core change. Failure → rolled back, counted, retried next tick.
- LS endpoints (3.13) read `econ_fences` by raw SQL (shared DB, CS-owned table — same as other CS tables LS reads).
- Ordinary merchants: `quote_bids` drops items with `items.is_stolen = 1` for everyone (covers explicit admin shop rows too). LS admin shop-row create/update refuses stolen items (400 «Краденое нельзя продавать в магазине»).

### 3.12 Post gate «caravan» (locations-service, no migration)

- `GATED_POST_TYPES += 'caravan'`, `GATE_SYMBOL_COST['caravan'] = 500` (a raid is a heavy action, like PvP), `GATE_LABELS['caravan'] = 'налёта на караван'`. `action_gates.action_type` is VARCHAR(20) — fits.
- Target validation on create **and** on edit-request: every caravan target must be `econ_caravans` with `is_physical=1 AND status='in_transit' AND arrived_at IS NULL AND current_location_id = post location`, else 400 «Каравана нет в этой локации». (Mob targets keep their current behaviour.)

### 3.13 API contracts

All bodies Pydantic v1; all user-facing errors Russian; frontend must show every error.

| # | Method / path | Service | Auth | Request | Response |
|---|---|---|---|---|---|
| A1 | `GET /characters/caravans/here?character_id=` | CS | JWT, owner | — | `{location_id, caravans: [{id, group_code, group_name, guard_count, state: "on_road"\|"held"\|"under_attack"\|"raided", departs_in_sec: int\|null, can_attack: bool, reason: str\|null}]}` (no from/to/value/route) |
| A2 | `POST /characters/caravans/{caravan_id}/raid` | CS | JWT, owner; nginx rate limit 6 r/m | `{character_id: int, group: bool=false}` | 201 `{raid_id, battle_id}`; 400/403/404/409/500/503 (3.6, 3.7) |
| A3 | `POST /characters/internal/caravans/raid-result` | CS | X-Internal-Token | `{battle_id, caravan_raid_id, winner_team: int\|null, aborted: bool}` | `{status: "won"\|"repelled"\|"aborted"\|"already"\|"unknown"}` (unknown raid → 200 unknown) |
| A4 | `GET /characters/admin/economy/caravans` (extended) | CS | economy:read | + `kind=all\|physical\|abstract` | items + `is_physical, current_location_id/name, route_index, route_len, next_move_at, arrived_at, hold_started_at, guard_count, stolen_units, raid_paid, raid_status` |
| A5 | `GET /characters/admin/economy/caravans/{id}` | CS | economy:read | — | A4 item + `route: [{index, location_id, name, region_id, region_name}]`, `held_by: "post"\|"raid"\|null`, `raid: {id, status, leader_id/name, is_group, battle_id, attackers: [{id,name,marks,bales}], marks, stolen_units, stolen_value, bales, guard_template_id/name, guard_mult, created_at, finished_at}\|null` |
| A6 | `GET /characters/admin/economy/caravans/roads` | CS | economy:read | — | `{regions: [{region_id, name, country_name, station_location_id/name, gate_override_id/name, gate_location_id/name, gate_source: "override"\|"station"\|"none"}], no_road: [{from_region_id, from_name, to_region_id, to_name, reason: "no_gate"\|"no_path"\|"too_long"}]}` over participating regions; pairs = same-country pairs + enabled foreign pairs (unordered) |
| A7 | `PUT /characters/admin/economy/caravans/gates/{region_id}` | CS | economy:settings | `{location_id: int\|null}` | A6 region item; 404 «Край не найден»; 400 «Локация не принадлежит этому краю» / «Подземелье не может быть торговыми воротами» |
| A8 | `GET /characters/admin/economy/caravans/guards` | CS | economy:read | — | `{templates: [{mob_template_id, name, level}]}` |
| A9 | `PUT /characters/admin/economy/caravans/guards` | CS | economy:settings | `{mob_template_ids: List[int]}` (≤ 20, unique) | same; 400 «Шаблон моба не найден: N» |
| A10 | existing economy settings PUT/GET | CS | economy:settings | new SimParams keys (3.14) | — |
| A11 | `GET /characters/admin/npcs/{npc_id}/fence` | CS | npcs:read | — | `{npc_id, is_active, price_pct, accepted_groups: [str], cash_target, cash, region_id, region_name, refill_active: bool}` (defaults when no row) |
| A12 | `PUT /characters/admin/npcs/{npc_id}/fence` | CS | npcs:update | `{is_active, price_pct (1..100), accepted_groups: List[str], cash_target (0..10 000 000)}` | A11; 404 «НПС не найден»; 409 «Настройки скупки доступны только скупщику» (role ≠ fence); 400 «Неизвестная группа товаров» |
| A13 | `GET /locations/npcs/{npc_id}/fence/offers?character_id=` | LS | JWT, owner, activity lock, npc_dialogue + tier gate, same location | — | `[{item_id, item_name, item_image, group_code, group_name, unit_price, max_quantity}]`; 404 «Скупщик не найден» (not role fence / inactive / dead) |
| A14 | `POST /locations/npcs/{npc_id}/fence/sell` | LS | as A13 | `{character_id, item_id, quantity (1..999)}` | `ShopTransactionResponse` shape; 400 «Скупщик это не берёт», 409 «У скупщика сейчас нет денег» |
| B1 | `POST /battles/internal/caravan-raid` | BS | X-Internal-Token | 3.7 | 3.7 |

Rate limiting: A2 via nginx (`limit_req` zone `caravan_raid_limit` 6 r/m, burst 3, `/characters/caravans/` POST location — both `nginx.conf` and `nginx.prod.conf`). A13/A14 follow the existing shop endpoints (no limit). Internal endpoints are behind `/…/internal/` (nginx 403 outside) + token.

### 3.14 Settings (SimParams JSON, no DDL; ranges in `schemas.py`, int keys in `ECON_SIM_INT_PARAMS`, `CARAVAN_PARAM_KEYS` extended so the caravans admin card edits them)

| Key | Default | Range | Meaning |
|---|---|---|---|
| `caravan_physical_enabled` | 1 | 0–1 | new physical caravans on/off |
| `caravan_physical_min_value` | 1000 | 1–10 000 000 | «крупный» threshold (marks) |
| `caravan_physical_small_chance` | 0.1 | 0–1 | chance for a smaller domestic caravan |
| `caravan_physical_max_active` | 30 | 0–1000 | cap of physical caravans on the road |
| `caravan_step_minutes` | 18 | 5–120 | minutes per location (±25 % jitter) |
| `caravan_route_max_steps` | 40 | 2–200 | longer routes = no road |
| `caravan_post_hold_max_min` | 120 | 0–1440 | max wait for a raid post (one window per caravan) |
| `caravan_raid_battle_max_hours` | 48 | 1–336 | a raid battle running longer is ignored |
| `caravan_raid_marks_share` | 0.2 | 0–1 | share of escrow money taken |
| `caravan_raid_goods_share` | 0.3 | 0–1 | share of units taken (→ bales) |
| `caravan_guard_count_base` | 2 | 1–5 | guards of a cheap caravan |
| `caravan_guard_value_per_extra` | 1000 | 1–10 000 000 | +1 guard per this value |
| `caravan_guard_count_max` | 5 | 1–5 | cap (battle team size) |
| `caravan_guard_mult_per_1000` | 0.1 | 0–5 | stat multiplier growth per 1000 marks |
| `caravan_guard_mult_max` | 2.0 | 1–10 | multiplier cap (value part) |
| `caravan_guard_mult_dangerous` | 1.25 | 1–5 | extra factor on `dangerous` locations |
| `caravan_rep_trade_share` | 0.5 | 0–1 | seller/buyer region reputation loss vs the raid region |
| `fence_purse_share` | 0.1 | 0–1 | share of a region purse fences may refill from per tick |

Formulas: `guard_count = clamp(base + floor(value / per_extra), 1, max)`; `guard_multiplier = min(mult_max, 1 + per_1000 × value / 1000) × (mult_dangerous if marker == 'dangerous' else 1)`. Danger of the land also enters through the template choice (level nearest to the location's recommended level).

### 3.15 DB changes summary

- **CS 050** `050_physical_caravans` (manual, MySQL-safe, idempotent column checks like earlier economy migrations):
  - `econ_caravans` + `is_physical BOOL NOT NULL DEFAULT 0`, `route JSON NULL`, `route_index SMALLINT NOT NULL DEFAULT 0`, `current_location_id BIGINT NULL`, `next_move_at DATETIME NULL`, `arrived_at DATETIME NULL`, `hold_started_at DATETIME NULL`, `guard_count SMALLINT NOT NULL DEFAULT 0`, `stolen_units DECIMAL(16,3) NOT NULL DEFAULT 0`, `raid_paid BIGINT NOT NULL DEFAULT 0`; indexes `ix_econ_caravans_move (is_physical, status, next_move_at)`, `ix_econ_caravans_loc (current_location_id, status)`.
  - `econ_caravan_raids`: `id BIGINT PK AI`, `caravan_id BIGINT NOT NULL UNIQUE`, `leader_character_id INT NOT NULL`, `is_group BOOL NOT NULL DEFAULT 0`, `location_id BIGINT NOT NULL`, `region_id BIGINT NULL`, `status VARCHAR(16) NOT NULL` (starting|fighting|won|repelled|aborted|expired), `battle_id INT NULL` (index), `attacker_ids JSON NULL`, `guard_ids JSON NULL`, `guard_template_id INT NULL`, `guard_mult DECIMAL(6,3) NULL`, `marks BIGINT NOT NULL DEFAULT 0`, `stolen_units DECIMAL(16,3) NOT NULL DEFAULT 0`, `stolen_value BIGINT NOT NULL DEFAULT 0`, `bales INT NOT NULL DEFAULT 0`, `payout_op_id BIGINT NULL`, `law_done BOOL NOT NULL DEFAULT 0`, `guards_despawned BOOL NOT NULL DEFAULT 0`, `created_at DATETIME NOT NULL`, `started_at DATETIME NULL`, `finished_at DATETIME NULL`; index `(status, id)`.
  - `econ_caravan_raid_shares`: `id BIGINT PK AI`, `raid_id BIGINT NOT NULL`, `character_id INT NOT NULL`, `marks BIGINT NOT NULL DEFAULT 0`, `bales INT NOT NULL DEFAULT 0`, `bale_item_id INT NULL`, `bales_delivered_at DATETIME NULL`; UNIQUE `(raid_id, character_id)`.
  - `econ_caravan_guard_templates`: `mob_template_id INT PK` (FK `mob_templates.id` ON DELETE CASCADE — CS owns it; create the FK index first per the MySQL gotcha), `created_at`.
  - `econ_regions` + `trade_gate_location_id BIGINT NULL` (no FK — LS table).
  - `econ_fences` (3.11).
  - `econ_sim_settings` + `caravan_pass_last_run_at DATETIME NULL`.
  - `UPDATE reputation_actions SET has_source = 1 WHERE code = 'caravan_attack'` (and `reputation_core.DEFAULT_ACTIONS` caravan → `True`, copied byte-for-byte to LS `reputation_core.py`).
  - Downgrade drops everything above (raided in-transit rows would break the escrow sub-invariant on downgrade — documented; pre-beta).
- **IS 037** (3.10). **BS 010** (3.7). **LS**: none (059 not needed). **user-service**: none (existing `economy:read/settings`, `npcs:read/update` suffice).

### 3.16 Global lock order (supersedes FEAT-207 3.10; documented in `econ_tick.py` and `economy_caravan_crud.py` docstrings)

`econ_regions (asc region_id) → econ_region_goods (asc region_id, group_code) → econ_region_events → econ_caravans (asc id) → econ_caravan_raids (asc id) → econ_caravan_raid_shares → econ_guild_orders → … (unchanged FEAT-207 chain) … → character_inventory → characters (asc id) → econ_accounts (asc id) → character_attributes`. Law/reputation rows are written only in the separate law transaction (Tx 2), never together with economy locks. The step tx locks only `econ_caravans(row)`; delivery takes regions → goods → caravan (never caravan first). `econ_fences`, `econ_caravan_guard_templates`, LS gate tables: plain reads, never locked.

### 3.17 Frontend

Player (`components/pages/LocationPage/`):
- `CaravanSection.tsx` (new, Tailwind, design-system classes, 360px): rendered after `EnemiesSection` in `LocationPage.tsx`; loads A1 on mount, after actions and every 60 s; card «Торговый караван: <группа>, охрана N», state line («Стоит в ожидании», «Идёт бой», «Уже ограблен»), «Уйдёт примерно через N мин» countdown; buttons «Напасть» and «Напасть группой» (only when in a party — same source as `EnemiesSection`); disabled with «Нужен боевой пост» when `/locations/action-gate/status` has no `caravan` gate with this id; success → navigate to the battle like `EnemiesSection`; every error shown in Russian.
- `gateConstants.ts`: `caravan` in `GATE_COST` (500), `GATE_LABEL` («Налёт на караван»), `GATE_STYLE`, `GATE_ORDER`; `LocationPage.tsx` passes `gateOptions.caravan` = caravans here (`{id, name: "Караван: <группа>"}`).
- `FenceModal/FenceModal.tsx` (new): offers list (A13), quantity input, «Продать», result and errors; opened from `NpcProfileModal.tsx` for `npc_role === 'fence'` and the character in the location (button «Сбыть краденое», like banker/minter).
- `constants/npc.ts`: role `fence` «Скупщик» + icon.
- `api/caravans.ts`, `api/fence.ts`, `types/caravans.ts` (new).

Admin:
- `EconomyPage/EconomyCaravans.tsx`: new params in `CARAVAN_PARAMS` (section «Физические караваны и налёты») with `paramHints.ts` texts; list kind filter (Все / Физические / Абстрактные), badge «по дорогам», raid status; row expands into `CaravanDetail.tsx` (route with current position highlighted, hold, raid card with attackers/loot).
- `EconomyPage/CaravanRoadsCard.tsx` (new): table of regions with station / override / effective gate, override location picker (locations of that region), «нет дороги» list.
- `EconomyPage/CaravanGuardsCard.tsx` (new): pool of guard mob templates (add/remove, level shown).
- `economyLabels.ts`: `caravan_raid`. `types/economy.ts`, `api/economyAdmin.ts` additions.
- NPC admin: `npcTabKeys.ts` + tab `fence` «Скупка» for saved role `fence`; `NpcExpandedPanel.tsx` renders `FenceSettingsPanel.tsx` (new; A11/A12; price %, groups multi-select, cash target, active toggle, current cash/region; `onDirtyChange` like `GuardPatrolPanel`). `api/npcAdmin.ts` addition.
- Every new component: no `React.FC`, Tailwind only, mobile 360px, errors visible.

### 3.18 Security

- A1/A2: JWT + ownership; location derived server-side from the character (no scanning); A2 additionally rate-limited, guarded by UNIQUE raid row, consumes a moderator-trackable post gate; raid team validated by BS (no foreign characters can be pulled except own party, as for mobs).
- A3/B1: internal prefix + `X-Internal-Token`.
- Admin endpoints: existing permissions; no new permission → `test_rbac_permissions.py` untouched.
- All SQL parameterised; JSON columns written from server-side ints only; no secrets.
- Public schemas never include `from/to/route/value`; a dedicated test asserts the A1 response keys.

### 3.19 Risks / accepted simplifications

- Prod geography: if stations/arrows are missing the feature degrades to abstract caravans; A6 «нет дороги» tells the admins what to fill. PM should look at A6 on prod after deploy.
- Steps stall while the 6 h tick runs (same scheduler thread) — minutes, acceptable.
- Fence refill takes money from residents without returning goods (stolen goods leave the economy). Simple and closed; can be refined later.
- Deferred (unseen) raids do not hit seller/buyer reputation.
- A crash between IS bale delivery and the DB mark can deliver bales twice (logged).

## 4. Tasks (filled by Architect, updated by PM — in English)

**Rules for every developer task:** no `git commit/push/add/stash/checkout/reset`; backend → `python -m py_compile` on touched files (in Docker per project workflow); frontend → `npx tsc --noEmit` + `npm run build` in the container; update the service doc in `docs/services/<service>.md`; Russian `[LOG]` line in section 6.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | Ledger op `caravan_raid` (3.9) + contract case; copy `econ_core.py` and `tests/econ_contract_cases.py` byte-for-byte to IS/LS/dungeon; `reputation_core.DEFAULT_ACTIONS` caravan has_source → True, copy to LS | Backend Developer | DONE | CS `app/econ_core.py`, `app/tests/econ_contract_cases.py`, `app/reputation_core.py`; same files in inventory/locations/dungeon (`econ_core`, contract cases) and LS `reputation_core.py` | — | `sh scripts/check_econ_copies.sh` green; existing econ contract tests pass in all 4 services |
| 2 | CS stage 1: migration 050 (all of 3.15 CS), models, pure `econ_caravan` helpers + new `caravan_route.py`, RoutePlanner + physical selection in `dispatch()`/`_caravan_pass`, new `caravan_pass.py` (claim, steps 4-5 of 3.3, hold rules 3.4; steps 1-3 as stubs calling functions task 3 fills), scheduler hook, `deliver_physical`, abstract path filters, escrow/inbound/card changes, SimParams 3.14, admin A4–A9 + new router module `caravan_api.py` (included in `main.py`), lock-order docstrings 3.16, extraction of the body of `despawn_dungeon_mobs_endpoint` into `crud.despawn_dungeon_mobs(db, ids)` (endpoint calls it, behaviour unchanged) | Backend Developer | DONE | CS `alembic/versions/050_physical_caravans.py`, `models.py`, `schemas.py`, `econ_sim.py`, `econ_caravan.py`, `caravan_route.py` (new), `caravan_pass.py` (new), `caravan_api.py` (new), `economy_caravan_crud.py`, `economy_guild_crud.py`, `econ_tick.py`, `econ_scheduler.py`, `crud.py`, `main.py`; `docs/services/character-service.md` | 1 | Migration up/down on MySQL; a large / foreign / chance-picked caravan gets a BFS route between gates and steps one location per interval; held by an open `caravan` gate or pending request ≤ window; delivered on arrival with correct money; destination gone → refund; abstract caravans unchanged; summary invariant ok; region card has no physical caravans; A4–A9 work with permissions |
| 3 | CS stage 2 raid: A1, A2, A3 (in `caravan_api.py`), `caravan_raid_crud.py` (start 3.6, settle 3.8, follow-ups/poll/expire filling `caravan_pass` steps 1-3), `battle_client.create_caravan_raid_battle`, guard spawn + despawn via `crud.despawn_dungeon_mobs` (from task 2), `shadow_crud.caravan_raid_consequences`, notices, character logs, bales via IS | Backend Developer | DONE | CS `caravan_raid_crud.py` (new), `caravan_api.py`, `caravan_pass.py`, `battle_client.py`, `shadow_crud.py`, `schemas.py`; docs (does NOT touch `main.py`, `econ_tick.py`) | 2 | Raid only in same location, one per caravan, guards hidden and despawned; win pays escrow share to raiders + bales, caravan continues with the rest; crime/witness/mask/stealth/guards-present forced; reputation in raid + seller/buyer regions; infamy; loss/abort → nothing; BS down → 503 and no leftovers; lost callback settled by poll; world sum 0 |
| 4 | CS fence: A11/A12 (`fence_api.py`, included in `main.py`), `fence_crud.py`, `_fence_pass` in the tick (3.11) | Backend Developer | DONE | CS `fence_api.py` (new), `fence_crud.py` (new), `econ_tick.py` (fence hook only), `fence_schemas.py` (new, Pydantic v1), `main.py` (router include only); docs (does NOT touch `schemas.py`) | 2 | Settings saved only for role fence; refill purse→fence up to target within `fence_purse_share`, idempotent per run, invariant ok |
| 5 | BS: migration 010, tag column, B1 endpoint, `_free_squadmates` + `_consume_action_gate` extraction (no behaviour change for mobs), end/abort callbacks, result field, join-request refusal | Backend Developer | DONE | BS `alembic/versions/010_battle_caravan_raid.py`, `models.py`, `crud.py`, `main.py`, `schemas.py`, `config.py` (if needed); `docs/services/battle-service.md` | — | B1 creates a pve battle team 0 attackers / team 1 guards only with a `caravan` gate; callback on finish and force-finish; join refused; mob attacks unchanged |
| 6 | IS: migration 037 (columns + 12 bales), model/schemas read fields, auction refusal | Backend Developer | DONE | IS `alembic/versions/037_stolen_bales.py`, `models.py`, `schemas.py`, `crud.py`; `docs/services/inventory-service.md` | — | 12 items exist with is_stolen/bale_group; auction deposit of a bale → 400; item edit keeps the flags |
| 7 | LS: gate type `caravan` + target validation (3.12); stolen refusal in `quote_bids` and admin shop rows; fence A13/A14 | Backend Developer | DONE | LS `crud.py`, `main.py`, `schemas.py`; `docs/services/locations-service.md` | 1 (file-disjoint; runtime needs 2, 6) | Post with caravan gate only for a caravan in the location (create + edit request); merchants never buy stolen; fence buys accepted groups at the formula price from his cash, item returned on failure, outlaw allowed |
| 8 | Nginx rate limit for A2 (dev + prod configs) | DevSecOps | DONE | `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf` | — | `nginx -t` ok; 7th POST within a minute → 503/429 per existing zone style; other `/characters/` routes unaffected |
| 9 | Frontend player: CaravanSection, gate constants + gate options, FenceModal + NpcProfileModal button, npc role constant, api/types (3.17 player) | Frontend Developer | DONE (live unverified: backend A1/A2/A5-A9/A11-A14 not yet in place) | `LocationPage/CaravanSection.tsx` (new), `LocationPage/FenceModal/FenceModal.tsx` (new), `LocationPage/LocationPage.tsx`, `LocationPage/gateConstants.ts`, `LocationPage/NpcProfileModal.tsx`, `constants/npc.ts`, `api/caravans.ts`, `api/fence.ts`, `types/caravans.ts` (new) | 3, 7 (contracts fixed — can start on 3.13) | tsc + build pass; block shows only group + guards; attack solo/group; post gate selectable; fence sale works; errors visible; 360px |
| 10 | Frontend admin: caravans params/filter/detail, roads card, guards card, journal label, NPC tab «Скупка» with FenceSettingsPanel (3.17 admin) | Frontend Developer | DONE (live unverified: backend A1/A2/A5-A9/A11-A14 not yet in place) | `Admin/EconomyPage/EconomyCaravans.tsx`, `CaravanDetail.tsx`, `CaravanRoadsCard.tsx`, `CaravanGuardsCard.tsx` (new), `paramHints.ts`, `economyLabels.ts`, `types/economy.ts`, `api/economyAdmin.ts`, `AdminNpcsPage/npcTabKeys.ts`, `AdminNpcsPage/NpcExpandedPanel.tsx`, `AdminNpcsPage/FenceSettingsPanel.tsx` (new), `api/npcAdmin.ts` | 2, 4 (contracts fixed — can start on 3.13) | tsc + build pass; all admin views work; dirty guard on the fence tab; 360px |
| 11 | QA CS stage 1: pure helpers (route BFS, selection, guard formulas, payout/refund splits), dispatch physical/abstract, stepping + holds (gate / pending request / window / raid), delivery & cancel with and without raid, escrow sub-invariant & world sum, inbound subtraction, region card filter, A4–A9 auth/validation | QA Test | DONE | CS `app/tests/test_physical_caravans.py` (new) | 2 | All pass; no regressions in existing caravan tests |
| 12 | QA CS stage 2 + fence: raid start errors and cleanup (BS 4xx/5xx mocked), one raid per caravan, settle won/repelled/aborted/duplicate, poll + expire, loot split, ledger op, crime witnessed/unseen/masked/guards-present, seller/buyer reputation, bales delivery retry, A1 key whitelist (no from/to), fence API + refill, security (other user's character 403, SQL-ish inputs) | QA Test | DONE | CS `app/tests/test_caravan_raids.py`, `app/tests/test_fences.py` (new) | 3, 4 | All pass |
| 13 | QA BS: B1 validation, gate consumption type/target, party roster, tag on battle, callback finish/abort, result field, join refusal, mob attack regression | QA Test | DONE | BS `app/tests/test_caravan_raid_battle.py` (new) | 5 | All pass |
| 14 | QA IS: migration items, schema fields, auction refusal, guild/faction-style off-market (misc) check via econ_core | QA Test | DONE | IS `app/tests/test_stolen_bales.py` (new) | 6 | All pass |
| 15 | QA LS: caravan gate create/edit validation + cost, merchants refuse stolen (row and auto-bid), fence offers/sell (price, groups, cash, return on failure, gate, outlaw allowed, wrong role 404) | QA Test | DONE | LS `app/tests/test_caravan_gate_fence.py` (new) | 7 | All pass |
| 16 | Docs: `docs/ARCHITECTURE.md` (new CS→BS raid call, BS→CS callback), `docs/ISSUES.md` if anything found | Backend Developer | DONE | `docs/ARCHITECTURE.md` | 3, 5, 7 | Docs match the code |
| 17 | Review: all checks (`check_econ_copies.sh`, py_compile, pytest per service, tsc/build), live verification on localhost (route on a local pair with gates set, step, raid with a post, win/loss, fence sale, admin views, invariant ok) | Reviewer | DONE | — | 1–16 | PASS |

**Parallel groups (file-disjoint):**
- Wave 1: 1, 5, 6, 8 (and 9/10 may start against the contracts).
- Wave 2: 2 (after 1), 7 (after 1).
- Wave 3: 3 and 4 in parallel (after 2; 4 touches only `fence_*`, the fence hook in `econ_tick.py` and a router include in `main.py`; 3 touches neither `econ_tick.py` nor `main.py`; only 3 edits `schemas.py`). 11 after 2; 13 after 5; 14 after 6; 15 after 7.
- Wave 4: 12 (after 3, 4), 9/10 finalisation, 16.
- Wave 5: 17.

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-12
**Result:** PASS

#### Automated Check Results
- [x] `py_compile` (all modified/new .py in character, battle, inventory, locations, dungeon — inside containers) — PASS
- [x] `sh scripts/check_econ_copies.sh` — PASS (all shared copies identical)
- [x] pytest, new/touched files only (full suites were run green by QA; the character full suite was deliberately not re-run — memory):
  - character: test_physical_caravans, test_caravan_raids, test_fences, test_econ_caravan_api, test_econ_sim, test_reputation_core, test_admin_mob_region_ready — 508 passed
  - battle: test_caravan_raid_battle — 112 passed
  - inventory: test_stolen_bales, test_migrations_024_025 — 52 passed
  - locations (`--asyncio-mode=auto`, as in CI): test_caravan_gate_fence, test_econ_locations_flows, test_npc_shop_admin_market, test_reputation_trade — 352 passed
  - dungeon: `-k econ` — all passed
- [x] `npx tsc --noEmit` — PASS (re-run after the reviewer fix below)
- [x] `vite build` (to /tmp in the frontend container) — PASS
- [x] `nginx -t` — PASS (both configs carry the same `caravan_raid_limit` zone + regex location above `/characters/`)

#### Live Verification Results (localhost, Chrome, admin user, character Ашари 763)
- A7: gates 9 → «Холм Эха», 10 → «Тракт Дункана» via API (location of another region → 400 «Локация не принадлежит этому краю»); A9 guard pool = template 49; A6 lists the «нет дороги» pairs.
- Dispatched a caravan through `dispatch_tx` + `RoutePlanner` → #528 physical, BFS route of 9 locations, 3 guards (with no gates the same plan stayed abstract — #527 — as designed).
- `/location/197`: block «Торговые караваны» — «Торговый караван: Продовольствие, охрана 3», countdown, «Напасть» disabled + «Нужен боевой пост…»; no origin/destination/route text anywhere on the page. A1 for another user's character → 403, without JWT → 401.
- Post editor offers «Налёт на караван · 500 симв./цель» with «Караван: Продовольствие»; post published → gate open → button enabled; group/solo chooser (character is in a party); solo raid → 201 → battle #328 (pve, `caravan_raid_id=5`, guards team 1).
- Won the fight in the 3D UI → raid `won`, 259 marks (20 % of escrow) + 8 «Тюк зерна (краденое)» delivered, share row, guards despawned, `caravan_attack` crime reported in region 9, notifications «Вас разыскивают…», «Жители… стали относиться хуже», «Налёт удался: 259 марок и 8 тюков…». The block then shows «Этот караван уже ограблен…». Repeat raid → 409; burst of POSTs → 429 (rate limit works).
- Admin «Экономика → Караваны»: Все/Физические/Абстрактные filter, badges «по дорогам» / «налёт: ограблен», detail with the full route, current position and raid card; «Дороги и ворота» and «Охрана караванов» cards render. Summary invariant `ok: true`, ledger sum 0, caravan escrow expected = actual (4067).
- Public region cards 9/10: no physical caravans in `caravans`.
- Merchant NPC 33 refuses a bale (400 «Этот NPC не покупает данный предмет», absent from sell-offers). NPC 33 → role `fence`: A11/A12 (unknown group → 400 «Неизвестная группа товаров»), admin tab «Скупка» renders and saves; player «Сбыть краденое» → FenceModal → confirm → «Продано: «Тюк зерна (краденое)» ×1 за 17 марок» (floor(50 × 0.878 × 40 %)).
- 360 px (iframe): `/location/197` and the NPC «Скупка» tab — no horizontal overflow.
- Console: zero errors on location, battle, admin economy and admin NPC pages; all caravan/fence requests 2xx (besides the deliberate 409/429 probes).
- Restored: gates NULL, guard pool empty, NPC 33 back to `merchant`, its `econ_fences` row deleted. Left (legit, invariant-safe state): test caravans #527 (abstract) and #528 (physical, raided — will deliver the rest), +8/−1 bales and +259 marks on Ашари, test post 990168 (gate consumed).

#### Fixed by Reviewer
| # | File | Fix |
|---|------|-----|
| 1 | `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCard.tsx:92` | `GATE_BADGE_META` had no `caravan` entry → a raid post showed the raw badge «caravan». Added `caravan` 🐫 «Налёт на караван» (site-red). tsc re-run PASS; verified live. |

#### Notes (non-blocking, no FIX_REQUIRED)
| # | Where | Note | Owner |
|---|-------|------|-------|
| 1 | `caravan_raid_crud.py:481` (`settle_raid` → `_pay_out`) | Payout does not re-check `caravan.status == in_transit`. No current path delivers/cancels a caravan while its raid is `starting/fighting` (raid holds stepping, delivery needs `arrived_at`), so this is defensive only; a one-line guard would protect the escrow sub-invariant against future cancel paths. | Backend Developer (optional) |
| 2 | brief §1 vs §3.8 | A witnessed raid changes reputation in the seller's and buyer's regions (tier notices name them) — reveals the caravan's from/to regions post factum. Mandated by the brief, so not a defect; PM may confirm with the user. | PM (question) |
| 3 | battle victory modal | Shows «Нет наград за этот бой» after a won raid (loot arrives via notification + inventory). Cosmetic follow-up. | Frontend (follow-up) |
| 4 | `caravan_pass.step_caravan` | A raid hold also sets `hold_started_at` (starts the single post window). Harmless — after any raid the post hold no longer applies. | — |

Security: A1/A2 JWT + owner (403/401 verified), location derived server-side, A2 rate-limited (429 verified) + UNIQUE raid row + gate consumed by BS; A3/B1 internal prefix (nginx 403 verified) + token; admin endpoints on economy:read/settings and npcs:read/update; SQL parameterised (IN lists via `in_params` / expanding binds); public schemas carry no from/to/route/value; stolen goods refused by merchants (rows + auto-bid), admin shop rows, auction deposit, guild/faction (misc = off-market); player-to-player trade allowed per brief. Migrations: plain columns/tables, no ENUM change on `items`, idempotent, revision ids ≤ 32 chars. Frontend: new files .tsx, Tailwind only, no React.FC, Russian visible errors, design-system classes.

## 6. Logging (all agents — in Russian)

```
[LOG] 2026-11-10 — PM: фича создана (этапы 1+2 физических караванов), запускаю анализ
[LOG] 2026-11-10 20:26 — Analyst: анализ завершён — затронуто 6 сервисов (character, battle, inventory, locations, dungeon (копия econ_core), frontend; user — опционально). Ключевое: граф локаций с межрегиональными переходами уже есть, «столицы края» нет; тип преступления и действие репутации «нападение на караван» уже зарезервированы; нужен новый тип операции ledger; 3 вопроса пользователю
[LOG] 2026-11-11 — PM: пользователь ответил на вопросы аналитика (пост с ожиданием до 2 ч, ворота = отделение стражи, краденое — скупщик + передача, новая роль НПС «Скупщик»), запускаю архитектора
[LOG] 2026-11-11 21:05 — Architect: начал проектирование, проверил ссылки аналитика (караваны, патрули, гейты постов, бой со стражей, продажа торговцу, econ_core)
[LOG] 2026-11-11 21:30 — Architect: уточнение к анализу — боевой гейт выдаётся сразу при публикации поста; модератор нужен только для гейта, добавленного правкой поста. Удержание каравана покрывает оба случая
[LOG] 2026-11-11 21:50 — Architect: спроектировано 17 задач, 15 API-контрактов, миграции character 050 / inventory 037 / battle 010 (locations и user — без миграций); статус → IN_PROGRESS
[LOG] 2026-11-11 22:50 — Backend Dev: задача #6 готова — миграция inventory 037 (items.is_stolen, items.bale_group + 12 краденых тюков), поля в модели и схеме Item, аукцион отказывает краденому (400), документация inventory-service; upgrade/downgrade/upgrade проверены (откат с тюком в инвентаре тоже), полный набор тестов inventory зелёный (тест «голова миграций» переведён на 037)
[LOG] 2026-11-11 22:50 — DevSecOps: задача #8 готова — зона caravan_raid_limit (6 r/m, burst 3, 429) для POST /characters/caravans/{id}/raid в nginx.conf и nginx.prod.conf; nginx -t ок для обоих, вживую на деве 5-й запрос подряд → 429, остальные /characters/ не затронуты
[LOG] 2026-11-11 23:40 — Backend Dev: задача #5 готова — battle-service: миграция 010 (battles.caravan_raid_id), POST /battles/internal/caravan-raid (гейт поста «caravan», отряд через общий _free_squadmates), колбэк итога налёта в character-service при завершении и принудительном завершении, поле caravan_raid_id в /internal/{id}/result, отказ во вступлении в налёт; _consume_combat_gate стал обёрткой над _consume_action_gate. Миграция up/down/up ок, тесты сервиса 1890 passed / 10 skipped. Дополнение к контракту: _squad_roster вынесен отдельно, чтобы порядок ошибок групповой атаки на моба не изменился
[LOG] 2026-11-11 23:59 — QA: задача #13 готова — tests/test_caravan_raid_battle.py (112 тестов): B1 (токен, валидация, лидер, охрана, лимит команды, соло/отряд), гейт «caravan» с id каравана и только последним шагом, _squad_roster/_free_squadmates, тег caravan_raid_id, колбэк при завершении и принудительном завершении (aborted), сбой колбэка не ломает конец боя, поле в /internal/{id}/result, отказ во вступлении, регрессия групповой атаки на моба (порядок ошибок прежний), цепочка миграции 010. Полный набор battle-service: 2012 passed
[LOG] 2026-11-11 23:55 — QA: задача #14 готова — tests/test_stolen_bales.py (33 теста): миграция 037 прогоняется по-настоящему через Alembic на SQLite (12 тюков по группам товаров, идемпотентность, пропуск существующего имени, откат и повторный подъём, цепочка ревизий и единственная голова), поля is_stolen/bale_group в схеме, правка предмета их сохраняет и не может поменять, аукцион отказывает краденому (400, инвентарь не тронут) и принимает обычный misc, тюки вне рынка в econ_core (торговец не покупает, группы не расширяют). Полный набор inventory: 2533 passed, 1 skipped
[LOG] 2026-11-11 23:59 — Frontend Dev: задачи #9 и #10 готовы — игрок: блок «Торговые караваны» на странице локации (только группа товара и охрана, без маршрута; «Напасть»/«Напасть группой», «Нужен боевой пост», обратный отсчёт, опрос раз в минуту), тип поста «Налёт на караван» (500 символов) с караванами локации в целях, роль НПС «Скупщик» и окно «Сбыть краденое»; админка: параметры «Физические караваны и налёты» с подсказками, фильтр Все/Физические/Абстрактные, значки «по дорогам» и статус налёта, раскрытие каравана (маршрут с текущей позицией, удержание, налёт с добычей), карточки «Дороги и ворота» и «Охрана караванов», метка журнала «Караван: налёт», вкладка НПС «Скупка» (FenceSettingsPanel, защита несохранённых изменений). tsc и vite build зелёные. Вживую не проверено — эндпоинтов A1/A2/A5–A9 (caravan_api.py) и A11–A14 (скупщик) локально ещё нет; проверит ревьюер. Замечание к бэкенду: GET /caravans/{id} надо объявить после /caravans/overview, /roads, /guards, иначе статические пути перехватит параметр
[LOG] 2026-11-12 00:30 — Backend Dev: задача #1 готова — операция ledger caravan_raid (эскроу → налётчики, без налога) + контрактный кейс; econ_core.py и econ_contract_cases.py скопированы байт-в-байт в inventory/locations/dungeon, reputation_core (caravan_attack has_source=True) — в locations; check_econ_copies.sh зелёный, контрактные тесты зелёные во всех 4 сервисах
[LOG] 2026-11-12 00:30 — Backend Dev: задача #2 готова — character-service этап 1: миграция 050 (up/down/up ок), модели, caravan_route.py (BFS), хелперы econ_caravan, RoutePlanner и выбор физических в dispatch, caravan_pass.py (захват 55 с, шаги 1–3 — заглушки под caravan_raid_crud.expire_stale_raids/poll_raid_battles/raid_followups, шаг/удержание/доставка), хук в планировщике, deliver_physical, фильтры абстрактного пути, эскроу/«в пути»/карточка края, 18 параметров, админка A4 (в economy_api) и A5–A9 (caravan_api.py, /{id} объявлен после статических путей), crud.despawn_dungeon_mobs, документация. Вживую на деве: маршрут 9→10 из 8 локаций, шаги, удержание гейтом/заявкой/налётом и окно 2 ч, доставка, инвариант эскроу ок. Поправлены 3 старых теста под новый контракт (ключи overview/списка, сид репутации с учётом 050, исключение fence_ в сиде параметров) + тест «единственная голова миграций» переведён на 050. Полный набор character-service: 9871 passed, 2 skipped, единственное падение (голова миграций) исправлено
[LOG] 2026-11-12 01:20 — Backend Dev: задача #7 готова — locations-service: тип поста «caravan» (500 символов) с проверкой цели при создании, переходе и заявке на ретро-гейт (400 «Каравана нет в этой локации»), караваны в очереди модерации заявок; обычные торговцы не берут краденое (quote_bids), админ-строки лавки с краденым → 400; скупщик A13/A14 (цена floor(price × множитель края × % / 100), принятые группы, касса скупщика, возврат тюка при сбое, без отказа «Вне закона»); документация. Миграции нет. Набор locations: 2977 passed; в двух старых фикстурах добавлена колонка items.is_stolen (общая копия MERCHANT_SQLITE_DDL её не содержит); SQL проверен вживую на MySQL; check_econ_copies.sh зелёный
[LOG] 2026-11-12 02:10 — Backend Dev: задача #4 готова — скупщик: A11/A12 (fence_api.py, fence_crud.py, fence_schemas.py, роутер в main.py), настройки сохраняются только для роли «fence» (409 иначе), 400 на неизвестную группу и диапазоны; _fence_pass в тике (после фракций, до банков): кошелёк края → касса скупщиков до цели в пределах fence_purse_share, одна операция merchant_trade, ключ fence:<run>:r<region> (повтор → дубль, пропуск); документация. Вживую на деве: GET/PUT/401/404/409/400 ок, пополнение 10769 марок, сумма мира не изменилась, повтор в том же прогоне → DuplicateOperation (проверка в откатываемой транзакции, тестовые правки НПС 33 возвращены); check_econ_copies.sh зелёный
[LOG] 2026-11-12 02:40 — QA: задача #15 готова — tests/test_caravan_gate_fence.py (148 тестов): гейт «caravan» (500 символов за цель, проверка каравана в локации на SQLite: физический, в пути, не прибыл, стоит здесь, иначе 400), вызов проверки при создании поста, move_and_post (локация назначения) и заявке на ретро-гейт (отказ не оставляет заявки), караван в очереди модерации; обычные торговцы не берут краденое (строка админа и автоскупка по группе, продажа 400, ничего не движется), админ-строки лавки с краденым → 400, удаление работает; скупщик A13/A14: формула цены (обычный и живой край, свой %), принятые группы (список/[]/NULL/мусорный JSON), касса скупщика и 409 до инвентаря, возврат тюка при сбое зачисления, отказ/недоступность инвентаря, гейт диалога, другая локация, «Вне закона» продаёт скупщику (настоящие чтения репутации), не тот НПС 404, чужой персонаж 403, SQL-подобный ввод 422. Полный набор locations-service: 3125 passed, 4 skipped
[LOG] 2026-11-12 02:40 — Backend Dev: задача #3 готова — character-service этап 2: caravan_raid_crud.py (старт налёта с предпроверкой гейта поста, охрана из пула по уровню локации, бой через battle-service, итог won/repelled/aborted/expired, доля эскроу налётчикам операцией caravan_raid, тюки через inventory-service, журнал и уведомления, шаги прохода expire/poll/followups; потерянная Tx B восстанавливается по battles.caravan_raid_id), A1/A2/A3 в caravan_api.py (A1 без откуда/куда), battle_client.create_caravan_raid_battle, shadow_crud.caravan_raid_consequences (свидетели/маска/скрытность, стража в локации — принудительно, репутация края налёта + продавца и покупателя, дурная слава); раскрытие отложенного налёта применяет действие caravan_attack. Вживую на деве: маршрут 197→190 (9 локаций), без поста 403 без спавна охраны, с постом бой 326 → победа → 259 марок + 8 тюков «Тюк зерна (краденое)», преступление (не замечен, отложено), охрана убрана, караван доехал с остатком (1299 = 259 + 1040), инвариант ок, сумма мира 0; принудительное завершение боя → aborted без добычи; ветка со свидетелями проверена в откатываемой транзакции (−100 край налёта, −50 край покупателя). Ворота/пул охраны на деве возвращены как были. Документация character-service
[LOG] 2026-11-12 02:50 — QA: задача #11 готова — tests/test_physical_caravans.py (115 тестов, ~20 с): чистые хелперы (BFS в обход подземелий, нет ворот/пути/слишком длинно, ворота края, выбор физического — крупный/межстрановый/шанс/выкл/лимит, охрана и множитель, остаток выплаты и возврат после налёта, краденое/тюки/дележ), отправка физический vs абстрактный (тик физический не двигает и не завершает), проход: захват 55 с, замороженная экономика, контракт шагов налёта (модуля нет → 0, есть → вызываются, падение шага изолировано), шаг по локации за проход, удержание гейтом/заявкой/окно 2 ч одно на маршрут/налёт, доставка и отмена (край вышел/удалён) с налётом и без, отложено при running-прогоне, идемпотентность; после каждого шага сумма денег мира 0 и эскроу = Σ(оплачено − raid_paid); «в пути» минус украденное; карточка края без физических; админка A4–A9 (401/403/read vs settings, валидация). Полный набор character-service: 9987 passed, 2 skipped
[LOG] 2026-11-12 03:00 — Backend Dev: задача #16 готова — docs/ARCHITECTURE.md сверен с кодом: character → battle (POST /battles/internal/caravan-raid + опрос /internal/{id}/result), battle → character (колбэк /characters/internal/caravans/raid-result, aborted при принудительном завершении), character → inventory (тюки налётчикам), locations → inventory (сбыт тюка скупщику), SQL-чтения econ_caravans/econ_fences/econ_goods_groups из locations, новые таблицы и колонки (character 050, inventory 037, battle 010). В CLAUDE.md §2 граф дополнен двумя устаревшими рёбрами (character → battle, locations → inventory). Новых проблем для ISSUES.md не найдено
[LOG] 2026-11-12 03:40 — QA: задача #12 готова — tests/test_caravan_raids.py (83 теста, ~25 с) и tests/test_fences.py (33 теста, ~9 с): старт налёта (проверка гейта лидера до спавна охраны, отказы 404/400/409, отказ/падение battle-service 4xx/5xx/сеть → без налёта и без охраны, сбой спавна → 500 и уборка), один налёт на караван, итог won/repelled/aborted/дубль/чужой бой/неизвестный налёт, дележ марок (остаток лидеру, НПС ничего) и тюков, операция caravan_raid из эскроу без налога, тюки через inventory с повтором, опрос/просрочка/зависший starting/потерянная Tx B, A1 без откуда/куда/цены, 401/403/404/422 и SQL-подобный ввод; закон: свидетели/не замечен/маска/стража в локации и выключатель свидетелей — принудительно, репутация края налёта + продавца/покупателя, дурная слава, «тяжесть» из админки, раскрытие отложенного налёта действием caravan_attack; скупщик A11/A12 (роль fence 409, 400/422, права) и пополнение кассы (в пределах доли кошелька, идемпотентно в прогоне, сумма мира 0). Полный набор character-service: 10103 passed, 2 skipped за 15:37 локально — близко к лимиту CI 15 мин
[LOG] 2026-11-12 00:00 — Reviewer: начал проверку (код, py_compile, check_econ_copies, тесты новых файлов, tsc/build, nginx -t)
[LOG] 2026-11-12 01:00 — Reviewer: живая проверка на деве — ворота, физический караван, пост «Налёт на караван», налёт и победа (марки + тюки, преступление, уведомления), повтор 409, лимит 429, админка караванов/дорог/охраны, вкладка «Скупка», продажа тюка скупщику, торговец отказывает; инвариант ок, 360px ок, ошибок в консоли нет; тестовые настройки возвращены
[LOG] 2026-11-12 01:05 — Reviewer: мелкая правка — бейдж поста «Налёт на караван» в PostCard (был сырой «caravan»)
[LOG] 2026-11-12 01:10 — Reviewer: проверка завершена, результат PASS (4 необязательных замечания в разделе 5)
[LOG] 2026-11-12 — PM: ревью PASS, фича закрыта
```

## 7. Completion Summary (filled by PM on completion — in Russian)

- Караваны стали физическими: крупные и межстрановые (и мелкие — случайно) идут по дорогам между «торговыми воротами» регионов (по умолчанию отделение стражи), ~18 мин на локацию; доставка — по прибытии. Нет дороги — караван абстрактный, админка показывает «нет дороги».
- Игрок видит караван только в своей локации: товар и охрана, без «откуда/куда».
- Налёт: пост с отметкой «Налёт на караван» (караван ждёт модерацию до 2 ч за маршрут), бой с охраной (сила от ценности груза и опасности места), один налёт на караван. Победа — доля марок покупателя + краденые тюки (12 новых предметов); преступление «нападение на караван» со свидетелями/скрытностью, репутация в крае налёта, у продавца и покупателя, дурная слава.
- Краденое: торговцы, аукцион, гильдия и интендант не берут; новая роль НПС «Скупщик» со вкладкой «Скупка» и своей кассой (пополняется в тик).
- Миграции: character 050, inventory 037, battle 010; новая операция книги `caravan_raid` во всех 4 копиях econ_core.
- Тесты: character 10103, battle 2012, inventory 2533, locations 3125 — зелёные. Ревью PASS (живой налёт, скупщик, админка, 360px).
- Риск: полный прогон тестов character-service локально ~15.5 мин (в CI обычно вдвое быстрее, лимит 15 мин).

