# FEAT-215: Караваны по морю

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
Этап 2 морских путей (продолжение FEAT-213 корабли и FEAT-214 шторма/монстры; караваны — FEAT-211 физические караваны и налёты, FEAT-212 охрана из игроков). Сейчас экономика торгует между странами и без дороги: если сухопутного пути нет, караван абстрактный (едет по таймеру). Нужно, чтобы заморская торговля шла **физически через порты и корабли**.

### Бизнес-правила

**Маршрут**
- Если между регионом-продавцом и регионом-покупателем нет сухопутной дороги, но можно доплыть, караван идёт: по суше до своего порта → грузится на корабль → плывёт (возможно с пересадкой — на усмотрение архитектора) → сходит в порту назначения → по суше до региона-покупателя.
- **Если ни сухопутного, ни морского пути нет — сделки нет** (караван не отправляется). Решение пользователя. Это меняет текущее поведение: абстрактная торговля «без дороги» прекращается. *(PM-допущение: если путь есть, мелкие караваны по-прежнему могут быть абстрактными по существующему правилу «крупные/межстрановые — физические, мелкие — случайно»; архитектор уточняет, как оценивать «есть путь» для абстрактных.)*
- «Морской путь есть» = существует активный корабль, маршрут которого проходит через подходящие порты (порт у стороны продавца и порт у стороны покупателя) в нужном направлении.

**Корабли и трюм**
- Грузы возят **существующие корабли** (те же, что возят пассажиров). У корабля появляется **трюм**: вместимость под грузы отдельно от мест пассажиров (настройка корабля в админке).
- Караван ждёт в порту корабль, идущий в нужную сторону; грузится при стоянке, плывёт с ним, выгружается в нужном порту.
- **Фрахт**: караван платит за перевозку, деньги — в казну региона порта отправления + налог страны (как за билеты, FEAT-213). Деньги не из воздуха — из средств каравана/покупателя (архитектор вписывает в инвариант эскроу).
- На палубе видно «В трюме груз каравана». Охранники-игроки (FEAT-212) плывут с грузом.

**Налёт в море**
- Груз можно грабить прямо в море: игрок на палубе нападает на охрану каравана (как налёт на суше, FEAT-211).
- Преступление — **по законам края, откуда корабль вышел** (порт отправления текущего участка).
- Последствия, добыча, репутация — как у сухопутного налёта.

**Монстры**
- Если на корабль напали морские монстры (FEAT-214) и защитники **проиграли** — **часть груза каравана теряется** («утащили в пучину»). Доля — настройка. Деньги/экономика — как при налёте (покупатель получает меньше товара).
- Охрана каравана (NPC) в бою с монстрами — на усмотрение архитектора (можно не участвовать).

**Не в этой фиче**
- Таможня и контрабанда в портах — следующий этап.
- Пираты, свои корабли — этап 3.

### UX / Пользовательский сценарий
1. Экономика отправляет караван за море; он едет по суше в порт.
2. В порту караван стоит у причала, ждёт корабль; игроки видят его там.
3. Корабль пришёл — караван грузится; на палубе «В трюме груз каравана».
4. В море игрок может напасть на охрану груза → бой → добыча, преступление по закону порта отправления.
5. Нападение монстров и поражение — часть груза теряется.
6. В порту назначения караван выгружается и едет дальше по суше.
7. Админ в экономике видит караваны в пути, включая этап «ждёт корабль / в море на корабле N».

### Edge Cases
- Корабль удалили/выключили/сменили маршрут, пока караван ждёт или в трюме — караван не должен потеряться (безопасная выгрузка, перепланировка или отмена с возвратом — архитектор).
- Трюм полон — караван ждёт следующий рейс (с пределом ожидания?).
- Налёт и нападение монстров одновременно.
- Охранники-игроки опоздали на корабль.
- Сделка рассчитана, но морской путь пропал до отправки — сделки нет.

### Вопросы к пользователю
- [x] Возить на существующих кораблях или отдельных грузовых? → **Как предлагает PM: существующие корабли с трюмом.**
- [x] Грабить в море? → **Можно, по законам края, откуда корабль выплыл.**
- [x] Монстры победили — терять часть груза? → **Да.**
- [x] Нет морского пути? → **Сделки нет, пока нет морского пути.**
- [x] Таможня/контрабанда? → **Следующий этап.**
- [x] (после анализа, ответ «по умолчанию») Трюм — в караванах за рейс (одно число в админке корабля).
- [x] Пустая палуба — монстры не нападают, груз цел.
- [x] Груз утонул — как при налёте: покупатель заплатил и получает меньше товара, продавцу платят полностью.
- [x] Мелкие заморские караваны — **только кораблём**, «по таймеру» остаются лишь мелкие сухопутные (PM-допущение выше отменено).
- [x] Ожидание корабля в порту — максимум 24 ч, потом сделка отменяется и деньги возвращаются покупателю.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Abbreviations: CS character-service, LS locations-service, BS battle-service, IS inventory-service. All CS paths are
under `services/character-service/app/`. CS is sync SQLAlchemy, Pydantic v1, Alembic present (manual MySQL-safe
migrations); everything below lives in the CS scheduler thread (`econ_scheduler.run_scheduled_once`, order law →
faction → **sea** → **caravan** passes, `econ_scheduler.py:118-121`).

### Affected services

| Service | Type of change | Main files |
|---|---|---|
| CS | core of the feature: planning with sea reachability, sea stage of physical caravans (wait / board / sail / unload), cargo hold, freight op, raid at sea (region override), monster cargo loss, escort exemptions, admin reads | `econ_caravan.py`, `economy_caravan_crud.py`, `caravan_pass.py`, `caravan_route.py`, `econ_tick.py`, `sea_pass.py`, `sea_crud.py`, `sea_core.py`, `sea_raid_crud.py`, `sea_admin.py`, `caravan_raid_crud.py`, `shadow_crud.py`, `caravan_escort_crud.py`, `econ_core.py`, `models.py`, `schemas.py`, new migration `054_*` |
| IS / LS / dungeon-service | only if `econ_core.py` / `tests/econ_contract_cases.py` change (byte-identical copies) | `econ_core.py`, `tests/econ_contract_cases.py` |
| LS | probably none: caravan gate validation and gate names already key on `econ_caravans.current_location_id` (works for a deck) | `crud.py:153-177`, `crud.py:4094-4103` |
| BS | probably none (caravan-raid B1 and sea-raid endpoints key on `location_id`; a deck is a plain location) | — |
| Frontend | admin caravan list/detail sea stage, roads card «нет пути», ShipForm cargo field, deck header cargo line | see 2.5 |

### 2.1 Caravan dispatch and routing today

**Planning is path-blind.** `econ_caravan.plan_caravans` (`econ_caravan.py:186-280`) matches sellers/buyers per goods
group; the only "can these two trade" test is `route()` (`econ_caravan.py:127-137`): same country → domestic, else an
enabled `econ_trade_pairs` row, else None. No geography at all. Candidates are sorted by `travel_runs` then price
(`:249`), budgets (`purse_left`/`treasury_left`) are consumed as plans are appended (`:266-269`). Consequence for
FEAT-215: if «no land and no sea path → no deal» is enforced only at dispatch, the planner will already have spent the
buyer's per-run budget and the seller's surplus on an unreachable pair and will not try the next seller — reachability
must enter `plan_caravans` (e.g. a `reachable(from_region, to_region)` predicate / pair map passed in, like `pairs`).

**Tick pass.** `econ_tick._caravan_pass` (`econ_tick.py:1621-1682`): abstract arrivals (`advance_and_finish`) → snapshot
(`load_snapshot`, `economy_caravan_crud.py:230-279`) → `plan_caravans` (`:1657`) → planner built **only when plans exist
and `caravan_physical_enabled`** (`:1659-1670`); a planner failure is logged and the run stays abstract (`:1664-1667`)
→ `dispatch_tx` per plan (`:1671-1682`). Under the new rule both fallbacks ("physical disabled" / "planner failed" →
abstract everything) need a decision: without a graph the code cannot know whether a path exists.

**Dispatch.** `economy_caravan_crud.dispatch` (`economy_caravan_crud.py:430-510`): locks regions ×2 → seller goods →
re-checks pair (`:449-460`) → locks purse/treasury/escrow balances → `clamp_dispatch` (`:466-469`) → builds the row
(`:471-478`, `travel_runs/runs_left` always written) → **physical decision** (`:479-491`): `planner.route(from,to)`
(land BFS between the two regions' trade gates), `physical_roll`, `choose_physical(value, countries, has_route, active,
params, u)` (`econ_caravan.py:320-333`: off / no road / cap → abstract; value ≥ min or foreign → physical; else small
chance). Physical row: `route` JSON, `route_index=0`, `current_location_id=route[0]`, `next_move_at = now +
departure_delay` (FEAT-212 hire window, `:421-427`), `guard_count`. Then goods leave the seller and `caravan_dispatch`
(purse+treasury → escrow, `apply_tax=False`, key `caravan:c<id>:pay`, `:499-509`). **Plug point:** between `:480` and
`:491` — today `road is None` silently yields an abstract caravan (`choose_physical` rule 2, `econ_caravan.py:325-326`);
FEAT-215 turns it into: land road → as today; else sea plan → physical sea caravan; else `DispatchResult("skipped")`.
Note `planner.route` caches per `(from,to)` (`:399-408`); `RoutePlanner.active` counts physical caravans for the cap
(`:385-393`, incremented after commit in `dispatch_tx` `:525-526`).

**Graph.** `load_road_graph` (`:350-359`) = all `LocationNeighbors` + dungeon markers; `region_gates` (`:362-377`) =
override `econ_regions.trade_gate_location_id` else `Regions.jail_location_id`; `caravan_route.shortest_route`
(`caravan_route.py:36-67`, BFS, deterministic, `no_gate | no_path | too_long`). Sea zones are a disconnected component
(FEAT-213 G4) so land BFS never crosses water; ports (`Locations.is_port`, `port_sea_zone_id`) are ordinary land nodes
→ "seller gate → port" and "port → buyer gate" are plain `shortest_route` calls on the same graph.

**Stepping / arrival** (`caravan_pass.py`): `run_pass` returns None when the economy tick is disabled in the DB
(`:218`) — unlike the sea pass, which runs regardless (`sea_pass.py:3-6`). `step_caravan` (`:102-129`): lock caravan
row → `held_by` (raid active or post hold, `economy_caravan_crud.py:841-850`) → `route_index += 1`,
`current_location_id = route[i]`, `move_escorts` (`:123`), last index → `arrived_at`. `_deliver_arrived` (`:181-207`,
skipped while a tick run is `running`) → `deliver_physical` (`economy_caravan_crud.py:696-769`). A sea caravan needs a
new state between "arrived at the boarding port" and "continue on land from the landing port": today a route is one
flat list and arrival = last index. Options the data allows: (a) one flat route `[gate…portA, portB…gate]` + a
`sea_leg_index` marking where the land route is interrupted, plus a `stage` column (`land | waiting | aboard`), or
(b) separate `route` (land 1) / `route2` (land 2) columns. `next_move_at` must be NULL/ignored while waiting/aboard so
`_due_ids` (`caravan_pass.py:93-99`) skips it.

**Abstract caravans** never look at paths (rows `is_physical=0`, `advance`/`finish` by tick counters,
`economy_caravan_crud.py:551-649`); `card_caravans` shows only abstract ones (`:1028`).

**Escrow invariant.** Sub-invariant `escrow == Σ(paid_purse + paid_treasury − raid_paid)` of `in_transit` rows
(`escrow_expected`, `:171-178`; checked in `economy_crud.py:194-205`, summary `ok`). Raid money: `_pay_out`
(`caravan_raid_crud.py:632-686`) posts `caravan_raid` escrow → raider characters (`marks ≤ paid_total − raid_paid`),
`raid_paid += marks`, `stolen_units += …`. Delivery pays the rest: `remaining_payout(value, duty, paid_total,
raid_paid)` (`econ_caravan.py:352-364`) minus escort pay (`pay_plan`, `:726-729`); cancel refunds via `refund_split`
(`econ_caravan.py:367-375`). Units on the road: `units − stolen_units` in `load_snapshot` (`:274-277`), `deliver_physical`
(`:714`), `economy_guild_crud.py:196`.

### 2.2 Ships (FEAT-213/214)

- **State** (`models.py:2217-2264`): `status docked|sailing`, `stop_index/next_stop_index/direction`, `trip_no`
  (departures made; next = `trip_no+1`), `docked_port_id`, `next_port_id`, `last_port_id`, `leg_path`/`leg_pos`,
  `departs_at`, `next_zone_at`, `hold_until`, `is_active`, `blocked_reason`; `capacity` = passenger seats per trip,
  `crew_slots`. Stops: `sea_ship_stops (ship_id, idx, port_location_id, path_override)` (`:2267-2282`). Passes
  (`:2285-2313`) cover trips `first_trip..last_trip` with snapshots and `fare_op_id/refund_op_id` — the natural template
  for a "cargo pass" (FEAT-213 §3.17 already sketches «cargo rows can reference ship_id + first_trip/last_trip»).
- **Plan / schedule:** `sea_crud.plan(db, ship, count)` (`sea_crud.py:369-410`) = the next trips with zone paths,
  skipping invalid stops (`valid_stop_indexes` `:358-366`); `sea_core.future_trips` (`sea_core.py:165`), `covers`
  (`:246`), `seats_left(capacity, taken, trips)` (`:255`), `fare` (`:241`). "A sea path exists from portA to portB" =
  an active ship whose `plan(…, n−1)` contains a leg from A followed (same direction, possibly several trips) by an
  arrival at B — exactly how `captain_view` lists destinations (`sea_crud.py:613-635`). Transfers would chain two
  ships' plans.
- **Boarding / alighting of passengers:** players only. Departure (`sea_pass.depart`, `sea_pass.py:267-402`) locks
  ship → passes → deck players (`deck_players`, `sea_crud.py:972-975`, `is_npc=0`) and **puts ashore everyone without a
  covering pass** (`:344-352`) — except players in a battle (`:306-309`). Arrival `_dock` (`:421-457`) completes passes
  with `last_trip <= trip_no` but moves nobody. So passengers leave by their own post; the system only "puts ashore".
- **Where a caravan could be "aboard":** (a) `econ_caravans.current_location_id = deck_location_id` while sailing —
  then everything keyed on location works unchanged: player view `caravans_here` (`caravan_raid_crud.py:169-210`, the
  deck page shows the caravan → `CaravanSection`), LS caravan gate validation (`LS crud.py:153-177`), raid start
  (`begin_raid` same-location check `:256`), BS B1 (leader/guards/escorts at `location_id`), guard spawn on the deck;
  (b) only a link (`ship_id` + trips) with the caravan location left at the port → no raid at sea possible without new
  code. Option (a) also needs a ship link (`ship_id`, `board_trip`/`last_trip`, `board_port_id`, `alight_port_id`)
  for unloading, capacity counting and admin display.
- **Hooks for cargo** (all inside the per-ship transaction, ship row locked, `process_ship` `:762-797`):
  departure — after `pl = plan(...)` (`:272`) and before the ship flips to sailing (`:374-392`): load waiting caravans
  at `docked_port_id` whose next sea leg this trip serves (cargo capacity per trip, like `_taken` `sea_crud.py:319-327`);
  `_dock` (`:421-457`): unload caravans whose `alight` port = this port (move caravan + escorts to the port, resume
  land stepping); `arrive` re-route (`:514-543`, skipped stop) and `_land_broken` / `safe_land` (`:460-487`,
  `sea_crud.py:1033-1067`): cargo must land at the landing target too or be cancelled/re-planned; admin
  `update_ship` route change (`sea_admin.py:665-686`, docked only), deactivate (`:688-698`, refunds not-started passes),
  `delete_ship` (`:714-747`, docked only; refunds + puts ashore) — each needs a cargo branch. `ShipOutcome`
  (`sea_pass.py:85-98`) is the place to carry caravan notices / LS cleanup for after-commit.
- **FEAT-214 raid lifecycle:** roll on effective zone entry (`_zone_effects` `sea_pass.py:552-596`): no eligible deck
  player → `raid_repelled`, no rows, +5 min (`:575-583`); else `plan_raid` one `sea_raids` row per group ≤ 5
  (`sea_raid_crud.py:175-195`), ship `hold_until` (`:587-590`); start after commit (`start_pending` `:367-386`); settle
  via BS callback `/characters/internal/sea/raid-result` or poll → `settle` (`sea_raid_crud.py:400-441`): status
  `won | lost | aborted | expired`, `lost` at `:423-424`. **Cargo-loss trigger point:** `settle` when the new status
  is `lost` (it is a separate short tx, does not lock the ship; idempotent via the conditional status). Caveats: one
  attack may produce several groups (several rows share `attack_key`) — "lost" needs an aggregation rule (any group
  lost? all?); an unmanned deck never produces a battle (`raid_repelled`), so cargo on an empty ship is never lost.
  `eligible_players` (`:143-160`) skips activity-locked characters → player **escorts (lock `caravan_escort`) are never
  pulled into monster fights**, and BS sea-raid also skips locked players.

### 2.3 Caravan raids and escorts on a deck

- **Raid start** (`caravan_raid_crud.begin_raid` `:238-281`): caravan physical + in_transit + same location as the
  leader + no raid row + not arrived + guard pool + open `caravan` post gate at that location (`has_open_gate`
  `:217-226`). Nothing assumes land except the **region**: `region_id = econ_ledger.resolve_location(location)`
  (`:267`). A deck lives in a **hidden country** (`sea_admin.validate_deck` `:478-482`) → the crime region would be the
  hidden «ships» region, not the departure port's. That `raid.region_id` is then used for the ledger op region
  (`_pay_out` `:656`) and as the crime / reputation region (`shadow_crud.caravan_raid_consequences` uses
  `raid.region_id` first, `shadow_crud.py:341`). **Plug point:** set `region_id` from the ship's departure port of the
  current leg (`ship.last_port_id` while sailing, `docked_port_id` when docked) when the caravan stands on a deck.
- Guard spawn (`spawn_guards` `:284-325`) picks the template by `Locations.recommended_level` and the multiplier by
  `marker_type` of the raid location (`:293-303`) — the deck's values (admins must set the deck's recommended level).
- Witnesses (`shadow_crud.py:351-366`): forced only when city guards stand at the location (`law_crud.guards_at`) — never
  on a deck (patrols never reach decks); base chance from the deck's `marker_type`.
- Post hold (`post_hold` `economy_caravan_crud.py:808-830`): holds caravan stepping only; it cannot hold a ship. In a
  port it can make a waiting caravan miss its ship (one 2 h window per caravan, `post_window_open` `:833-838`).
- `held_by` "raid" while `starting/fighting` (`:841-850`) — at sea the ship keeps sailing; if it docks at the alighting
  port during a caravan raid, unloading has to wait or the cargo rides on (ship departs after `boarding_minutes`).
- **Escorts** (`caravan_escort_crud.py`): hire only while "preparing" = `route_index == 0` at the seller gate
  (`:313-318`, `:362-368`); `move_escorts` (`:599-614`) raw-writes escorts' `current_location_id` to the caravan's
  location (bypasses the deck passage check G1 — fine for boarding). Problems on a deck: (1) `sea_pass.depart` puts
  ashore any deck player without a pass (`sea_pass.py:344-352`) → escorts would be landed at departure unless exempted
  (they are `is_npc=0` and appear in `deck_players`); same for `safe_land` / `delete_ship`; (2) «Сойти» (`leave`
  `:511-537`) at sea leaves the ex-escort on the deck without a pass → put ashore at the next departure (acceptable) ;
  (3) escorts are hidden from `/characters/by_location` but `deck_view.passengers_count` counts them
  (`sea_crud.py:850-852`) — small leak of the hidden escorts; (4) escort lock excludes them from monster fights (2.2).
  Raids on a deck with escorts work as on land (B1 checks escorts at `location_id`).

### 2.4 Freight payment

- Ops: `OP_SEA_FARE`/`OP_SEA_REFUND` (`econ_core.py:179-184`), caravan ops `CARAVAN_OP_TYPES` (`:155-161`), union
  `OP_TYPES` (`:191-200`). `econ_core.py` and `tests/econ_contract_cases.py` are byte-identical in CS/IS/LS/dungeon
  (`scripts/check_econ_copies.sh`, groups `econ_core`, `econ_contract_cases`); contract cases pin
  `CARAVAN_OP_TYPE_NAMES` (`econ_contract_cases.py:839-860`).
- Passenger fare: `buy_ticket` (`sea_crud.py:706-752`) posts `sea_fare` character → `treasury_for_location(from_port)`
  (`econ_ledger.py:115-118`: port region treasury, else world) with default `apply_tax=True`; the country tax leg is
  added automatically only when the source kind is in `TAX_SOURCE_KINDS` (`econ_core.py:103-105`:
  character, auction escrow/storage, population purse, bank deposits; `tax_region_ids` `:560-567`, `add_tax_legs`
  `:578-594`). **`caravan_escrow` is not a tax source** → an escrow → port-treasury leg would get no country tax.
  Options: add `KIND_CARAVAN_ESCROW` to `TAX_SOURCE_KINDS` (safe for existing caravan ops — dispatch/delivery/cancel/raid
  all post `apply_tax=False`, `economy_caravan_crud.py:502,754`, `caravan_raid_crud.py:656`), or post an explicit tax
  leg, or route freight purse → treasury at dispatch. Any `econ_core` edit = 4 copies + contract case.
- Escrow-safe freight: a new column (e.g. `freight_paid`) must enter `escrow_expected` (`Σ(paid − raid_paid −
  freight_paid)`), `remaining_payout` / `refund_split` (today they only subtract `raid_paid`), the raid marks cap
  (`_pay_out` `:642`), escort pools (`_seller_part`, `caravan_escort_crud.py:248`) and the admin rows. The freight must
  be inside the buyer's paid amount (plan cost `value + duty`, `econ_caravan.py:71-91`) or come out of the seller part —
  who bears it is an architect/economy decision. Refund of freight when a sea leg is cancelled by an admin action
  mirrors `refund_pass` (`sea_crud.py:978-1005`, reverses every posting, untaxed, idempotent key).

### 2.5 Frontend

- Admin caravans: `EconomyCaravans.tsx` (params `CARAVAN_PARAMS`/`PHYSICAL_PARAMS`/`ESCORT_PARAMS` `:49-90`, kind
  filter `:677-770`, badge «по дорогам» `:605`, result text `:659`), `CaravanDetail.tsx` (route chain with current
  position `:111-166`, `held_by` labels `:166`) — must show the sea stage («ждёт корабль в порту X», «в море на корабле
  N», trip/ETA); `CaravanRoadsCard.tsx` (A6 «нет дороги», reasons `no_gate|no_path|too_long`) — needs «по морю» /
  «нет ни суши, ни моря». Types `types/economy.ts:1400-1491`, API `api/economyAdmin.ts`, labels `economyLabels.ts` (new
  op label if a freight op is added).
- Ship admin: `ShipsPage/ShipForm.tsx` numeric fields `NumKey` + `NUM_FIELDS` (`:35-48`) — a cargo-hold field fits the
  same table; `types/seaAdmin.ts` (`capacity` `:69`, `:110`), `api/seaAdmin.ts`, backend `ShipCreate/ShipUpdate/
  ShipAdminOut` (`sea_admin.py:111-225`), `update_ship` numeric loop (`:648-650`).
- Player: `CaravanSection.tsx` (deck shows caravans automatically if `current_location_id = deck`; its countdown
  `departs_in_sec` from `next_move_at` `:259-260` is meaningless aboard); `ShipDeckHeader.tsx` (`passengers_count`
  `:145`) — place for «В трюме груз каравана» (S5 `deck_view` `sea_crud.py:830-855` would need a cargo field);
  `CaravanEscortModal.tsx` route (`:188-190`) — escort's own view of the sea stage.

### 2.6 Migration heads and head-pinning tests

| Service | Head | Pinned by |
|---|---|---|
| CS | `053_sea_storms_raids` (down `052_sea_ships`) | `tests/test_admin_mob_region_ready.py:509-515` (asserts 053 is not a down_revision) → must add `053` to downs and assert the new head |
| LS | `060_sea_zones` | no head-pinning test found |
| BS | `011_battle_sea_raid` | `tests/test_sea_raid_battle.py:1027-1037`, `tests/test_caravan_raid_battle.py:1217-1235` (only if a BS migration is added) |
| IS | `037_stolen_bales` | `tests/test_migrations_024_025.py:130`, `tests/test_stolen_bales.py:92,109` (only if an IS migration is added) |

Expected DB changes (CS only): `econ_caravans` sea columns (stage, ship link, ports, trips, lost/freight amounts),
`sea_ships.cargo_capacity` (or similar), possibly a `sea_cargo` link table modelled on `sea_passes`; SimParams keys
(no DDL) for loss share / wait limit / freight rate. Revision ids ≤ 32 chars.

### 2.7 Risks

- **Lock order.** Sea: `sea_ships → sea_passes → characters → econ_accounts` (`sea_crud.py:15`). Caravans:
  `econ_regions → goods → econ_caravans → raids → escorts → characters → accounts` (`economy_caravan_crud.py:21-37`).
  Boarding/unloading inside the ship tx means `sea_ships → econ_caravans → escorts → characters`; nothing may lock a
  caravan then a ship (raid settle, step, delivery must never touch `sea_ships`). Monster cargo loss in `sea_raid_crud
  .settle` locks raid → caravan (no ship) — fine.
- **Two passes, two switches.** Sea pass ignores the economy tick switch, caravan pass obeys it (`caravan_pass.py:218`):
  ships keep carrying/unloading cargo while the economy is frozen; delivery waits for a running tick
  (`caravan_pass.py:184-186`).
- **Plan vs dispatch drift.** Reachability must be in `plan_caravans` (2.1); sea availability can vanish between plan
  and dispatch (brief: «сделки нет») and between dispatch and boarding (ship deleted/deactivated/rerouted) → need a
  cancel path with full refund (`deliver_physical` cancel branch returns goods to the origin, `:732-750`).
- **Escrow sub-invariant** breaks unless freight is accounted (2.4). Monster loss without money movement keeps it;
  with a refund it needs an op type.
- **Escorts on a deck** are put ashore at departure / safe landing unless exempted (2.3).
- **Wait in port forever** (no ship, full hold, inactive ship) — needs a limit + cancel/re-plan.
- **CI time:** CS suite is close to the 15-min CI limit (FEAT-214 summary) → lean tests.
- **`physical_max_active` cap / `caravan_physical_enabled=0`** currently force abstract; for sea pairs the rule is open.

### 2.8 Questions

Technical (Architect):
1. Data shape: flat route + `stage`/`sea_*` columns on `econ_caravans`, or a `sea_cargo` link table like `sea_passes`
   (trips, ports, freight op ids, status)? Transfers (two ships) imply the link table.
2. Who boards/unloads: sea pass in the ship tx (natural, ship locked) — then lock order `ship → caravan` must be
   documented globally.
3. Reachability input to `plan_caravans`: precomputed pair map per run from land graph + active ships' plans; what if
   the planner cannot be built (today → abstract)?
4. Freight: rate formula (per caravan vs per unit/value vs reuse `fare_base + fare_per_zone × zones`), who pays (buyer
   inside escrow vs seller part), tax mechanism (`TAX_SOURCE_KINDS` vs explicit leg vs new op `caravan_freight`).
5. Monster loss aggregation for multi-group attacks, and on an empty deck (no battle).
6. Escort exemptions in `depart` / `safe_land` / `delete_ship`, and whether escorts fight monsters (today excluded by
   the activity lock).
7. Caravan raid during docking at the alighting port (unload waits vs rides on).

Non-technical (user, via PM; analyst's recommended default in brackets):
1. Вместимость трюма — в чём считать: число караванов на рейс или объём товара? [число караванов за рейс, по умолчанию
   2–3; проще для админов].
2. Если монстры напали, а на палубе некому защищаться (никого нет) — груз теряется? [нет, теряется только при
   проигранном бою, как в брифе].
3. Потерянный в пучине груз: деньги — покупатель просто получает меньше товара, продавец получает полную цену, или
   покупателю возвращается доля? [покупатель получает меньше товара, продавцу платится полностью — как страховки нет;
   деньги никуда не исчезают].
4. Мелкие караваны «за море» тоже могут быть абстрактными (по таймеру), если морской путь есть? [нет — заморские
   всегда физические через корабль, иначе трюм и налёты в море не имеют смысла; абстрактные — только по суше].
5. Предел ожидания корабля в порту, после которого сделка отменяется с возвратом денег и товара? [24 реальных часа].

## 3. Architecture Decision (filled by Architect — in English)

Scope: character-service (core), the four byte-identical `econ_core.py` / `econ_contract_cases.py` copies (one new op
type), frontend (admin economy, ship form, deck header, caravan section / escort modal). No changes in LS, BS, IS logic,
no new endpoints, no Nginx / Docker changes. All money stays inside the ledger; no new money source.

### 3.0 Answers to the analyst's technical questions (2.8)

| # | Decision |
|---|---|
| 1 | **Columns on `econ_caravans`, no link table.** One flat `route` = land leg 1 + land leg 2, `sea_split_index` = index of the boarding port in `route`; `route[sea_split_index + 1]` = the landing port. **No transfers** in this stage: one sea leg on one ship (the ship may pass intermediate stops while the cargo stays in the hold). Transfers need a per-leg link table and multiply the wait / strand cases; postponed (Q-PM-1). |
| 2 | **The sea pass boards and unloads, inside the per-ship transaction.** New global lock order (§3.6): `sea_ships → sea_passes → econ_caravans → econ_caravan_escorts → characters (one sorted call) → econ_accounts`. Nothing ever locks `sea_ships` after `econ_caravans`; the ship tx never locks `econ_regions`, `econ_region_goods` or `econ_caravan_raids` (raid status is a plain read). |
| 3 | `plan_caravans` gets a pure **reachability callable** (`reach(from, to) → Reach | None`) built per tick run by an extended `RoutePlanner` (land BFS + a per-run sea-pair map from active ships' plans). The planner is now **always** built before `plan_caravans` (also with `caravan_physical_enabled = 0`, it is needed to know whether a land path exists). Planner build failure → **no caravans this run** (logged), never the old "everything abstract". |
| 4 | Freight = `floor(value × caravan_sea_freight_pct / 100)` (SimParam, default 5 %). **The buyer pays it** at dispatch as part of the escrowed cost (`value + duty + freight`). It is **charged on unloading** at the landing port (escrow → boarding-port region treasury + explicit country-tax leg), new op `caravan_freight`; a voyage that never completes never charges freight, so no freight refund op exists. `caravan_escrow` stays **out** of `TAX_SOURCE_KINDS` (the contract pins that); the tax leg is computed by CS with `core.tax_amount(F, country_tax_rate)`. |
| 5 | Cargo loss per attack (`attack_key`) is applied **once, when every group row of the attack is final**: `share = caravan_sea_loss_pct × lost_groups / decided_groups` (decided = won + lost; aborted / expired ignored; 0 decided → no loss). Empty deck → `raid_repelled`, no rows → no loss (existing behaviour, user decision). |
| 6 | Escorts sail with their caravan: exempted from the "no ticket → ashore" rule at departure, moved with the caravan on unload / strand. **Escorts and NPC guards do not fight sea monsters** (escorts keep the `caravan_escort` activity lock → `eligible_players` skips them; unchanged). They do defend against player raids on the deck exactly as on land. |
| 7 | **Unloading waits for an active caravan raid** (`held_by == "raid"`); the unload check runs on every sea pass for docked ships, so a raid that ends during the boarding window unloads normally. If the ship departs first, the caravan rides on and is handled by the generic rule at the next docking (unload if back at its landing port, else strand → cancel). |

### 3.1 Caravan kinds after this feature

| Pair situation (seller gate ↔ buyer gate) | Result |
|---|---|
| Land path exists | as today: physical or abstract by `choose_physical` (abstract = "мелкие сухопутные по таймеру") |
| No land path, sea route exists (§3.3) | **always physical sea caravan** (needs `caravan_physical_enabled = 1` and a free `caravan_physical_max_active` slot) |
| Neither | **no deal** (not planned at all) |

Behaviour change (user decision): pairs without any path (including regions with no trade gate: `no_gate`) stop trading.
The roads card (§3.9) makes such regions visible to the admin.

### 3.2 Data model — CS migration `054_sea_caravans` (down `053_sea_storms_raids`)

Revision id `054_sea_caravans` (16 chars). Manual MySQL-safe migration in the style of 050–053 (idempotent column adds
via inspector, explicit index names, FK columns indexed). Downgrade drops everything added.

`econ_caravans` (new columns, all nullable / defaulted → existing rows are plain land caravans):

| Column | Type | Meaning |
|---|---|---|
| `sea_stage` | VARCHAR(12) NULL | NULL = land caravan; `to_port` → `waiting` → `aboard` → `landed`; `stranded` (ship lost, awaiting cancel) |
| `sea_split_index` | INT NULL | index of the boarding port in `route` |
| `sea_board_port_id` | INT NULL | boarding port location (LS `Locations`, no FK — like `current_location_id`) |
| `sea_alight_port_id` | INT NULL | landing port location |
| `sea_ship_id` | INT NULL | ship that took the cargo (set at boarding, kept for history; no FK, ship ids are never reused; stranded before a delete) |
| `sea_waiting_since` | DATETIME NULL | arrival at the boarding port (wait-limit clock) |
| `sea_boarded_at` / `sea_unloaded_at` | DATETIME NULL | timestamps for admin |
| `freight` | INT NOT NULL DEFAULT 0 | reserved freight (part of `paid_purse + paid_treasury`) |
| `freight_paid` | INT NOT NULL DEFAULT 0 | freight actually charged (0 or `freight`) |
| `freight_op_id` | BIGINT NULL | the `caravan_freight` operation |
| `sunk_units` | DECIMAL(16,3) NOT NULL DEFAULT 0 | units lost to monsters |

Indexes: `ix_econ_caravans_sea_wait (sea_stage, sea_board_port_id)`, `ix_econ_caravans_sea_ship (sea_ship_id, sea_stage)`.
`cancel_reason` (VARCHAR(32)) gets new values `sea_wait_expired`, `sea_route_lost`, `no_path` (dispatch never stores
`no_path`; listed only for completeness of labels).

`sea_ships.cargo_capacity INT NOT NULL DEFAULT 2` — caravans per trip (admin 0..20; 0 = the ship carries no cargo).

`sea_raids`: `caravan_ids JSON NULL` (caravans in the hold at the moment the attack was planned, written on every group
row), `cargo_settled_at DATETIME NULL` (loss applied / nothing to apply).

New table `econ_caravan_sea_losses`: `id BIGINT PK AI`, `caravan_id INT NOT NULL FK → econ_caravans.id ON DELETE
CASCADE`, `ship_id INT NULL`, `attack_key VARCHAR(48) NOT NULL`, `lost_groups INT`, `decided_groups INT`,
`loss_pct DECIMAL(6,2)`, `units_lost DECIMAL(16,3)`, `created_at DATETIME`, `UNIQUE uq_caravan_sea_loss (caravan_id,
attack_key)` (leading column covers the FK index). Idempotency of the loss.

SimParams (no DDL; `econ_sim.SimParams` + bounds in `schemas.py` + admin params UI):
`caravan_sea_freight_pct` float 5.0 [0, 50]; `caravan_sea_wait_hours` int 24 [1, 168];
`caravan_sea_loss_pct` float 25.0 [0, 100].

Head-pinning: `tests/test_admin_mob_region_ready.py` — add `assert "053_sea_storms_raids" in downs` and
`assert "054_sea_caravans" not in downs` (single head). Rollback: `alembic downgrade 053_sea_storms_raids`; sea
caravans in flight should be cancelled by the admin first (otherwise they lose their stage and become broken rows —
acceptable pre-beta).

### 3.3 Reachability and planning

**Sea pairs (per tick run, `sea_cargo.sea_pairs(db)`):** for every active ship: `sea_crud.plan(db, ship, 2 × len(stops))`;
for each leg *i* departing from port A walk the following legs and collect every `to_port` B until a leg arrives back
at A (or the plan ends) — pair (A, B) with zones = Σ leg zones. Keep the minimal zones per (A, B) and the ship ids.
Pure helper `sea_core.serves(legs, a, b) -> Optional[int]` (zones or None) implements "B is reached from A without
revisiting A" and is reused at boarding / docking. Missing sea tables → empty map.

**Region-to-region (`RoutePlanner`, extended):** `route(from, to)` unchanged (land gate BFS). New `sea_route(from, to)`
→ `SeaRoute(land1, land2, board_port, alight_port, zones)`: over all (A, B) in the sea map, `land1 = shortest_route(gate
(from) → A)`, `land2 = shortest_route(B → gate(to))` (same graph / max steps; cached per (gate, port)); choose minimal
`len(land1) + len(land2) + zones`, ties by (A, B) ids. Ports are `Locations.is_port = 1`; the land BFS never enters water
(G4). `reach(from, to)`: land road → `Reach("land", freight_pct=0)`; else, only if `caravan_physical_enabled`, sea route
→ `Reach("sea", freight_pct)`; else None.

**`econ_caravan` (pure):**
- `CaravanPlan` gets `freight: int = 0`, `freight_pct: float = 0.0`; `cost = value + duty + freight`; the invariant
  becomes `paid_purse + paid_treasury == value + duty + freight`.
- `plan_caravans(..., reach=None, sea_slots=None)`: `reach is None` → legacy behaviour (keeps old pure tests valid).
  Otherwise a candidate needs `route()` (country / pair rule, unchanged) **and** `reach()`; sea candidates are skipped
  when `sea_slots` is exhausted (decremented per sea plan; `sea_slots = max_active − active`). Sort key adds the kind
  after travel_runs (land before sea). `affordable_units(budget, price, duty_pct + freight_pct)`; `freight = floor(value
  × freight_pct / 100)`; `split_payment(value + duty + freight, …)`.
- `clamp_dispatch` recomputes freight with the plan's `freight_pct`.
- Money helpers take freight into account: `remaining_payout(value, duty, paid_total − freight, raid_paid)` at the call
  sites (or a `freight` kwarg — implementer's choice, one way consistently); `refund_split(paid_purse, paid_treasury,
  raid_paid + freight_paid)`; raid marks cap `≤ paid_total − freight − raid_paid`.

**Tick (`econ_tick._caravan_pass`):** build the planner (now including sea pairs) **before** `plan_caravans`, pass
`reach` and `sea_slots`; planner failure → log, return without dispatching. `caravan_physical_enabled = 0` → land pairs
still trade (abstract), sea pairs do not.

**Dispatch (`economy_caravan_crud.dispatch`):** land road → as today. No road → `planner.sea_route()`; None, physical off,
or cap reached → `DispatchResult("skipped")` (the deal is dropped — "морской путь пропал до отправки"). A plan whose kind
changed (land planned, no road now; or `freight` mismatch) → recompute via `clamp_dispatch` with the sea freight pct or
skip — implementer keeps it simple: skip if the plan's `freight_pct` disagrees with the dispatch kind. Sea row:
`is_physical = 1`, `route = land1 + land2`, `sea_split_index = len(land1) − 1`, ports, `sea_stage = "to_port"`,
`freight = final.freight`, `current_location_id = route[0]`, `next_move_at = now + departure_delay` (escort hire window
unchanged), `guard_count`. The dispatch op posts `paid_purse + paid_treasury` (incl. freight) into escrow.

### 3.4 Caravan stages

```
dispatch ──► to_port (land leg 1, caravan pass steps it) ──► waiting (at board port, next_move_at NULL)
   waiting ──► aboard (sea pass, departure of a serving ship with a free hold slot; current_location_id = deck)
   waiting ──(caravan_sea_wait_hours elapsed)──► cancelled `sea_wait_expired` (caravan pass)
   aboard ──► landed (sea pass, docked at alight port, no active caravan raid; freight charged; land leg 2 stepping)
   aboard ──(ship lost / rerouted / deactivated / deleted)──► stranded (at the landing / docked port) ──► cancelled `sea_route_lost` (caravan pass)
   landed ──► arrived ──► deliver_physical (unchanged)
```

- `step_caravan`: when the step reaches `route_index == sea_split_index` with stage `to_port` (or the first step when
  `sea_split_index == 0`) → `sea_stage = "waiting"`, `sea_waiting_since = now`, `next_move_at = NULL`, outcome
  `"at_port"`. Arrival logic unchanged (`sea_split_index < len(route) − 1` always).
- Caravan pass new step `_sea_housekeeping` (after raid steps, before stepping; obeys the economy switch like the whole
  caravan pass): waiting rows past the limit and `stranded` rows → `cancel_physical(db, id, reason, now)` in its own tx.
- `cancel_physical` = the cancel branch of `deliver_physical` extracted (lock order regions → goods → caravan → escorts →
  characters → accounts): goods `units − stolen_units − sunk_units` return to the origin, `refund_split(paid_purse,
  paid_treasury, raid_paid + freight_paid)` back to the buyer, escorts cancelled (no pay, as FEAT-212 cancel), op
  `caravan_cancel`. A waiting caravan with an active raid is skipped until the raid ends.
- Delivery (`deliver_physical`): units `units − stolen_units − sunk_units`; payout from `paid_total − freight`; guard: any
  unpaid reserved freight (`freight − freight_paid > 0`) goes back to the buyer purse as an extra leg of
  `caravan_delivery` (theoretical — sea caravans reach delivery only after unloading).
- Every "units on the road" read uses `units − stolen_units − sunk_units`: `load_snapshot` inbound, `deliver_physical`,
  `economy_guild_crud.py:196`, raid `_pay_out` left units.

### 3.5 Sea pass hooks (new module `sea_cargo.py`, called from `sea_pass` / `sea_admin`)

All inside the ship transaction (ship row already locked); notices go into `ShipOutcome.notices` (escorts get WS notices
«Караван погружен на корабль …», «Груз выгружен в …», «Корабль потерян, караван возвращается»).

- **`dock_cargo(db, ship, now, out)`** — called from `_dock` and **every pass for every docked ship** (active or not),
  in `process_ship` after the sanity block and before `depart`. For each `aboard` caravan of the ship (locked asc id):
  docked port == `sea_alight_port_id` → if `held_by(...) == "raid"` keep aboard, else **unload**: `current_location_id
  = sea_alight_port_id`, `route_index = sea_split_index + 1`, stage `landed`, `sea_unloaded_at`, `next_move_at = now +
  step_delay` (or `arrived_at = now` if that index is the last), escorts moved (`move_escorts`), **freight charged**
  (§3.7). Otherwise, if the ship is inactive or `serves(plan from here, here, alight) is None` → **strand** at the
  docked port. Catches admin route change / deactivation of a docked ship (≤ 1 pass, before any departure).
- **Boarding in `depart`** — after passes are locked, before the deck players lock: waiting caravans with
  `sea_board_port_id = docked_port_id`, status in_transit, ordered by id, locked; skip those with `held_by(...)` not
  None (raid or post hold — they wait for the next ship); board while `cargo_capacity − aboard_count > 0` and
  `serves(plan(2×stops), docked_port, alight)` is not None. Board = stage `aboard`, `sea_ship_id`, `sea_boarded_at`,
  `current_location_id = deck`. The escorts' characters of all caravans aboard (incl. just boarded) are included in the
  **single sorted characters lock** together with the deck players (implement by extending the `deck_players` lock to
  `id IN (deck ids ∪ escort ids)`), then escorts are moved to the deck.
- **Escort exemption in `depart`**: a deck player whose `escort_caravan_id` is a caravan aboard this ship (active
  escort row) sails without a pass (no ashore, no ticket burn). Escorts are never late: they ride inside the wagon by
  construction (activity lock), so "охрана опоздала" cannot happen.
- **Strand (`strand_all(db, ship, target, now, out)`)** — used by `_land_broken`, the "deck vanished" sanity branch,
  `safe_land` callers and `delete_ship`: every `aboard` caravan of the ship without an active caravan raid →
  `current_location_id = target` (landing target / docked port), stage `stranded`, escorts moved there; with an active
  raid it stays `aboard` and the next pass's `dock_cargo` strands it (the broken ship is docked/inactive by then). No
  target → leave aboard and log error (same as players). The caravan pass then cancels stranded rows.
- **`arrive` reroute** (skipped stop) needs no special code: the caravan stays aboard; at the next docking `dock_cargo`
  unloads or strands it.
- **`delete_ship`** (docked only): `strand_all` at the docked port first; if any aboard caravan has an active caravan
  raid → 409 «На корабле идёт налёт на караван — удалите корабль позже».
- **Deactivate / route change** (`update_ship`): no special code (next pass `dock_cargo`); waiting caravans are not
  bound to a ship and simply wait for another serving ship or the wait limit.
- Monster raid planning (`_zone_effects` → `plan_raid`): write `caravan_ids` = ids of caravans `aboard` this ship (plain
  read, ship is locked) on every group row. Eligibility of defenders unchanged (escorts excluded by lock).

**Switches:** the sea pass ignores the economy switch (as FEAT-213): boarding / unloading / freight continue while the
economy tick is off, so cargo is never stuck on a deck. Stepping on land, wait-limit / strand cancels and delivery obey
the switch (caravan pass). After re-enabling, overdue waiting caravans are cancelled at once (accepted).

### 3.6 Global lock order (supersedes FEAT-212 3.15 / FEAT-213 3.7 for these tables)

`sea_ships (asc) → sea_passes → econ_regions → econ_region_goods → econ_region_events → econ_caravans (asc) →
econ_caravan_raids → econ_caravan_escorts (asc) → econ_caravan_sea_losses → sea_raids → … (FEAT-207 chain) … →
characters (asc, ONE sorted call per tx) → econ_accounts (asc) → character_attributes`.
In practice the ship tx never takes the region / goods / caravan-raid locks, and no caravan / raid / delivery code path
locks `sea_ships`. Document it in `sea_crud.py`, `sea_cargo.py` and `economy_caravan_crud.py` module docstrings.

### 3.7 Money: freight, escrow sub-invariant, tax

- `econ_core` (4 byte-identical copies): `OP_CARAVAN_FREIGHT = "caravan_freight"` added to `CARAVAN_OP_TYPES` (thus
  `OP_TYPES`). `tests/econ_contract_cases.py` (4 copies): `CARAVAN_OP_TYPE_NAMES` gets `"caravan_freight"`. Nothing else
  in econ_core changes; `caravan_escrow` stays out of `TAX_SOURCE_KINDS`. `sh scripts/check_econ_copies.sh` must pass.
- Freight op (at unload, ship tx): `F = caravan.freight`; `treasury = econ_ledger.treasury_for_location(board_port)`;
  if it is a region treasury with a country: `tax = core.tax_amount(F, settings.country_tax_rate)`, legs
  `escrow → region (F − tax)`, `escrow → country (tax)`; else one leg `escrow → treasury (F)`. `apply_tax=False`,
  `region_id` = board port region, idempotency key `caravan:c<id>:freight`, metadata (caravan, ship, ports, freight,
  tax). Then `freight_paid = F`, `freight_op_id`. F = 0 → no op.
- Escrow sub-invariant: `escrow == Σ(paid_purse + paid_treasury − raid_paid − freight_paid)` over in_transit rows
  (`escrow_expected`). Delivery pays `paid_total − freight − raid_paid` (seller + duty + escorts); cancel refunds
  `paid_total − raid_paid − freight_paid`; raid marks cap `paid_total − freight − raid_paid`; escort pool
  `_seller_part` uses `paid_total − freight`. Every in_transit row drains the escrow to zero at finish.
- Sea loss moves **no money** (buyer receives fewer units, seller paid in full — user decision).
- Admin labels: `caravan_freight` → «Фрахт каравана».

### 3.8 Raids at sea and monster loss

- **Player raid on a deck** (`caravan_raid_crud.begin_raid`): if the caravan's `sea_stage == "aboard"`, `raid.region_id
  = resolve_location(departure port)` where departure port = `ship.docked_port_id` when docked, else `ship.last_port_id`
  (plain read of `sea_ships` by `sea_ship_id`, no lock); fallback = current behaviour. Everything else (guards on the
  deck, gates, B1, loot, crimes, reputation via `raid.region_id`) is unchanged. `_pay_out`: left units subtract
  `sunk_units`, marks cap subtracts `freight`. A raid on a `waiting` caravan in the port works as on land.
- Player view A1 `caravans_here` adds `sea_stage` and returns `departs_in_sec = null` for `waiting` / `aboard`.
- **Monster loss** (`sea_raid_crud`): after `settle` commits a final status (callback path and poll / followups), call
  `apply_cargo_loss_tx(factory, attack_key)` (own tx): read all rows of the attack (plain); not all final or
  `cargo_settled_at` set → return. Otherwise for each id in `caravan_ids` (lock caravans asc, skip non-in_transit):
  `units_lost = floor3((units − stolen − sunk) × loss_pct/100 × lost/decided)`; insert `econ_caravan_sea_losses` (UNIQUE
  → already), `sunk_units += units_lost`; then set `cargo_settled_at` on all rows of the attack. Notices to active
  escorts «Часть груза утащили в пучину». `raid_followups` fallback: final attacks with `cargo_settled_at IS NULL` and
  non-empty `caravan_ids` → same function (catches lost callbacks / crashes).
- Simultaneous player raid and monster attack: independent; units math always uses the current remaining units.

### 3.9 Admin and player API (contract additions, all backward compatible; no new endpoints)

- Admin caravan list / detail (existing endpoints): new fields `sea_stage`, `sea_split_index`, `sea_board_port_id/
  _name`, `sea_alight_port_id/_name`, `sea_ship_id/_name`, `sea_waiting_since`, `sea_wait_deadline` (= since + limit),
  `sea_boarded_at`, `sea_unloaded_at`, `freight`, `freight_paid`, `sunk_units`; detail also `sea_losses: [{attack_key,
  units_lost, loss_pct, created_at}]`. `kind` filter accepts `sea` (`sea_board_port_id IS NOT NULL`).
- Roads card (A6): `no_road` keeps its shape but lists only pairs with **neither** land nor sea; new list `by_sea:
  [{from_region_id, from_name, to_region_id, to_name, directions: "both"|"forward"|"backward", board_port_name,
  alight_port_name}]` for pairs without land road but with a sea route in ≥ 1 direction.
- Ship admin: `cargo_capacity` in `ShipCreate` (default 2, 0..20), `ShipUpdate` (optional), `ShipAdminOut`; plus
  read-only `cargo_aboard: int`.
- Deck view S5 (`deck_view`): `cargo: [{caravan_id, group_name, alight_port_name}]`; `passengers_count` excludes active
  escorts (hidden-escort leak fix).
- Escort view (data behind `CaravanEscortModal`): `sea_stage`, `sea_board_port_name`, `sea_alight_port_name`,
  `sea_split_index`, `ship_name`.
- Security: no new endpoints; admin reads/writes keep their existing admin guards and Pydantic bounds; player views keep
  "own location only" and never expose value / from / to.

### 3.10 Frontend

- `EconomyCaravans.tsx`: kind filter option «по морю», badge «по морю», result texts for `sea_wait_expired` («не
  дождался корабля») / `sea_route_lost` («корабль потерян»); params group «Морские караваны» (3 new keys).
- `CaravanDetail.tsx`: route chain with a «⚓ море» separator between `sea_split_index` and the next node; stage line
  («едет в порт X», «ждёт корабль в порту X, отмена через …», «в трюме корабля N → порт Y», «сошёл в порту Y»,
  «застрял: корабль потерян»); freight / paid / sunk units; sea losses list.
- `CaravanRoadsCard.tsx`: section «Только по морю» from `by_sea`; «нет ни суши, ни моря» for `no_road`.
- `ShipForm.tsx` + `types/seaAdmin.ts`: numeric field «Трюм (караванов за рейс)» 0..20; ships list shows `cargo_aboard`.
- `ShipDeckHeader.tsx` + `types/sea.ts`: line «В трюме груз каравана» (× count) when `cargo.length > 0`.
- `CaravanSection.tsx`: no countdown for `waiting` / `aboard`, label «ждёт корабль» / «в трюме». `CaravanEscortModal.tsx`:
  sea segment in the route.
- `economyLabels.ts`: `caravan_freight` op label, new cancel reasons. All Tailwind, mobile 360px+, no `React.FC`,
  errors displayed in Russian. Touched `.jsx` files (if any) migrate to `.tsx`.

### 3.11 Risks

- Behaviour change: regions without a gate / path stop trading entirely (user decision); visible on the roads card.
- CI time: CS suite near the 15-min limit → QA keeps tests lean (pure tests + a few targeted integration tests reusing
  `sea_world.py` / physical-caravan fixtures).
- Plan horizon `2 × stops` of `plan()` per active ship per tick run and per boarding / docking with cargo — small
  (ships are few); `dock_cargo` first runs a cheap COUNT and skips ships without cargo.
- Migration rollback discards sea stage data of in-flight caravans.

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | Foundation: migration `054_sea_caravans` (§3.2), ORM models, SimParams + bounds (3 keys), `OP_CARAVAN_FREIGHT` in all 4 `econ_core.py` copies + `CARAVAN_OP_TYPE_NAMES` in all 4 `econ_contract_cases.py`, head-pinning test update. | Backend Developer | DONE | `services/character-service/app/alembic/versions/054_sea_caravans.py`, `models.py`, `econ_sim.py`, `schemas.py` (param bounds only), `{character,inventory,locations,dungeon}-service/app/econ_core.py`, `…/tests/econ_contract_cases.py`, `tests/test_admin_mob_region_ready.py` | — | `alembic upgrade head` / `downgrade 053_sea_storms_raids` work on MySQL; `sh scripts/check_econ_copies.sh` ok; `py_compile` passes; contract cases pass in all 4 services. |
| 2 | Planning & dispatch: `sea_core.serves`, `sea_cargo.sea_pairs`, `RoutePlanner.sea_route` + `reach`, `econ_caravan` changes (plan freight, `reach`/`sea_slots`, clamp, money helpers), `_caravan_pass` (planner always, failure → no dispatch), `dispatch` sea branch, `escrow_expected`, escort `_seller_part`, roads `by_sea` (§3.3, §3.7, §3.9). | Backend Developer | DONE | `econ_caravan.py`, `sea_core.py`, `sea_cargo.py` (new: reachability part), `economy_caravan_crud.py`, `econ_tick.py`, `caravan_escort_crud.py` | 1 | Unreachable pairs never planned; sea pair → physical sea row with correct route/split/ports/freight; escrow invariant holds; old pure tests with `reach=None` unchanged. |
| 3 | Caravan-pass stages & admin reads: `step_caravan` → `waiting`, `_sea_housekeeping` (wait limit, stranded), `cancel_physical` extraction, delivery with freight/sunk, `sunk_units` in all units-on-road reads, admin list/detail fields + `kind=sea`, caravan schemas (§3.4, §3.9). | Backend Developer | DONE | `caravan_pass.py`, `economy_caravan_crud.py`, `economy_guild_crud.py`, `schemas.py` | 2 | Stage transitions as in §3.4; cancels refund `paid − raid_paid − freight_paid` and return goods; admin endpoints return the new fields. Parallel with 4 and 5 (only task 3 edits `schemas.py`). |
| 4 | Sea pass cargo: `sea_cargo` board / `dock_cargo` / `strand_all` / freight op; hooks in `process_ship`, `depart` (boarding, escort exemption, single sorted character lock), `_dock`, `_land_broken`, sanity branch; `plan_raid` `caravan_ids`; `sea_admin` `cargo_capacity` + `cargo_aboard` + `delete_ship` strand / 409; `deck_view` cargo + escort-free passenger count; lock-order docstrings (§3.5–3.7, §3.9). | Backend Developer | DONE | `sea_cargo.py`, `sea_pass.py`, `sea_crud.py`, `sea_raid_crud.py` (plan_raid only), `sea_admin.py` | 2 | Hold capacity respected; escorts sail and land with cargo; freight op `caravan_freight` with tax leg to the port's country; stranded on safe landing / delete / reroute; no lock taken out of order. Parallel with 3 and 5 (5 edits `sea_raid_crud.py` after 4's `plan_raid` change — coordinate, or run 5 after 4 if one developer). |
| 5 | Raids at sea & monster loss: `begin_raid` region override, `_pay_out` sunk/freight, A1 `sea_stage` + no countdown, escort view sea fields, `apply_cargo_loss_tx` after `settle` + followups fallback, escort notices; update `docs/services/character-service.md` (sea caravans, lock order, new params / op) (§3.8, §3.9). | Backend Developer | DONE | `caravan_raid_crud.py`, `caravan_escort_crud.py` (escort view), `sea_raid_crud.py`, `docs/services/character-service.md` | 2, 4 | Raid on deck registers crime in the departure port's region; loss applied once per attack with the lost/decided share; idempotent; no money moves. |
| 6 | Admin economy UI: caravans list/detail sea stage, kind filter, params group, roads card `by_sea`, op/reason labels (§3.10). | Frontend Developer | DONE | `components/Admin/EconomyPage/EconomyCaravans.tsx`, `CaravanDetail.tsx`, `CaravanRoadsCard.tsx`, `economyLabels.ts`, `types/economy.ts`, `api/economyAdmin.ts` | contract §3.9 (can start in parallel with 2–5; live check after 3) | `npx tsc --noEmit` + `npm run build` pass; sea stage visible; mobile 360px; errors shown in Russian. |
| 7 | Ship form & player views: `cargo_capacity` field, `cargo_aboard` in list, deck header «В трюме груз каравана», `CaravanSection` stage labels, `CaravanEscortModal` sea segment (§3.10). | Frontend Developer | DONE | `components/Admin/ShipsPage/ShipForm.tsx` (+ list), `types/seaAdmin.ts`, `api/seaAdmin.ts`, `components/pages/LocationPage/ShipDeckHeader.tsx`, `CaravanSection.tsx`, `types/sea.ts`, `components/CaravanEscort/CaravanEscortModal.tsx` | contract §3.9 (parallel with 6; live check after 4, 5) | tsc + build pass; field saves; deck shows cargo line; no countdown aboard. |
| 8 | Pure-logic tests: `sea_core.serves` (pendulum, loop, revisit cut-off), `plan_caravans` with `reach`/`sea_slots`/freight, `clamp_dispatch` freight, money helpers with freight, loss share math, migration head test. | QA Test | DONE | `tests/test_sea_caravans_core.py` (new) | 1, 2 | Lean, fast, deterministic; all pass. |
| 9 | Integration tests (reuse `sea_world.py` / physical-caravan fixtures): dispatch sea row; no path → no deal; waiting → boarding with capacity + escort exemption; unload + `caravan_freight` op + tax + escrow invariant; wait-limit cancel; strand on safe landing / delete / route change → cancel with refund; raid on deck region override; monster loss aggregation (2 groups: 1 won 1 lost) + idempotency + empty deck no loss; deck view cargo; ship admin `cargo_capacity`. | QA Test | DONE | `tests/test_sea_caravans.py` (new) | 3, 4, 5 | All pass; suite time increase kept small (< ~60 s). |
| 10 | Review: cross-service (econ copies, contract), lock order, escrow invariant, CI-sized tests, FE rules (Tailwind, TS, no React.FC, mobile, errors), live check on localhost (admin caravans, ship form, deck). | Reviewer | DONE | all of the above | 1–9 | PASS with automated checks + live verification recorded in Section 5. |

Parallelism: 1 → 2 → {3, 4} in parallel → 5 (after 4) ; 6 and 7 in parallel with backend from the contract; 8 after 2;
9 after 3–5; 10 last.

### PM decision on the questions below (user, 2026-11-18)

Defaults 1, 2, 3, 5 accepted. **Q4 overridden: escorts (players) DO fight sea monsters like everyone on deck** («охрану тоже в бой»).
Implementation note: the FEAT-214 monster raid must include player escorts aboard (CS raid player selection and the BS
`/battles/internal/sea-raid` skip rule — escorts carry a caravan-escort activity lock, which must not exclude them from a
sea-raid battle; any other activity lock still skips). NPC caravan guards still do not fight monsters. Escorts keep
their hidden-in-caravan behaviour for player raids.

### Questions for PM (defaults chosen, not blocking)

1. **Пересадки** (два корабля) не делаем на этом этапе: караван плывёт одним кораблём (тот может заходить в промежуточные
   порты). Если прямого корабля нет — сделки нет. Ок?
2. **Фрахт** = 5 % стоимости груза (настройка), платит покупатель вместе с товаром; деньги в казну порта отправления
   списываются при выгрузке (если рейс сорвался — фрахт не берётся, возвращается покупателю). Ок?
3. **Доля потери груза** при проигрыше монстрам = 25 % (настройка); при нескольких группах — пропорционально доле
   проигравших групп.
4. **Охрана** (игроки и NPC) с морскими монстрами не дерётся — только защищает груз от игроков-грабителей.
5. Корабль потерян / перестал ходить в нужный порт, пока караван в трюме → караван высаживается в ближайший порт и
   **отменяется** (товар возвращается продавцу, деньги покупателю), без перепланировки по суше.

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-18
**Result:** PASS (one MEDIUM contract bug found live and fixed by the reviewer; non-blocking notes below)

#### Checklist
- [x] **econ copies / contract.** `sh scripts/check_econ_copies.sh` — all shared copies identical; `OP_CARAVAN_FREIGHT` in `CARAVAN_OP_TYPES` (4 copies), `CARAVAN_OP_TYPE_NAMES` updated (4 copies); `caravan_escrow` stays out of `TAX_SOURCE_KINDS`, tax leg posted explicitly.
- [x] **Migration CS 054.** Id `054_sea_caravans` (16 chars), down `053_sea_storms_raids`, single head (head test updated), guarded idempotent DDL, full downgrade; `econ_caravan_sea_losses.caravan_id` BIGINT FK -> `econ_caravans.id` (BIGINT) ON DELETE CASCADE, leading column of `uq_caravan_sea_loss` covers the FK index; `ix_econ_caravans_sea_wait` / `_sea_ship` present on dev MySQL (head = 054).
- [x] **Lock order.** Ship tx: `sea_ships -> sea_passes -> econ_caravans (asc) -> escorts (asc) -> characters (ONE sorted call: deck + escorts) -> accounts` in `board` / `dock_cargo` / `strand_all`; when `dock_cargo` moved escorts the departure is skipped in that tx (no second character lock). Caravan pass / cancel / delivery never lock `sea_ships` (plain reads only: `departure_port`, `_ship_name`, admin join). Cargo loss: caravans -> losses -> `UPDATE sea_raids` in its own tx after `settle` committed. No HTTP inside these locks (LS cleanup / notices after commit via `ShipOutcome` / `law_notify.publish`).
- [x] **Money.** Escrow sub-invariant `sum(paid - raid_paid - freight_paid)`: dispatch +value+duty+freight; freight op -F (region F-tax + country tax); delivery -(paid - freight - raid_paid) - unpaid-freight guard; cancel -(paid - raid_paid - freight_paid); raid cap `paid - freight - raid_paid`; escort pool from `paid - freight`; sea loss moves no money. Verified live to the mark (below).
- [x] **Idempotency.** Freight: key `caravan:c<id>:freight` + `freight_paid` guard; loss: UNIQUE `(caravan_id, attack_key)` + `cargo_settled_at` + followup fallback; cancel re-checks its condition under the row lock and skips raided caravans; unload waits for an active raid.
- [x] **Economy switch.** Sea pass boards / unloads / charges regardless; stepping, wait-limit / strand cancels and delivery obey the switch (caravan pass), as designed (§3.5).
- [x] **BS escort exemption.** `_sea_fighter_available` and CS `eligible_players` exempt only `reason == caravan_escort`; any other lock still skips (BS test added).
- [x] **FE rules.** Tailwind only, TS only, no `React.FC`, no new SCSS, tokens exist (`text-site-blue`, `text-gold-light`, `text-stat-energy`, `text-site-red`), errors via the existing toast / `apiErrorMessage`; deck page at 360 px: no horizontal scroll (scrollWidth 345).
- [x] **Docs.** `docs/services/character-service.md` «Караваны по морю (FEAT-215)» (reviewer fixed one sentence: the loss share is proportional to lost / decided groups, not «all groups lost»).
- [x] **QA.** Tasks 8/9 DONE: `test_sea_caravans_core.py`, `test_sea_caravans.py` (15 integration tests).
- [x] **Security.** No new endpoints; admin reads / writes keep existing guards and Pydantic bounds (`cargo_capacity` 0..20); player views never expose value / regions; Russian messages.

#### Issues Found
| # | File:line | Description | Severity | Status |
|---|-----------|-------------|----------|--------|
| 1 | `services/character-service/app/schemas.py:3514` | `CaravanRoadsOut` had no `by_sea` field, so the response model silently dropped it: `GET /admin/economy/caravans/roads` never returned `by_sea` and the roads card kept the old «Нет дороги» block (found live). Added `CaravanBySeaOut` + `by_sea: List[...] = []`; re-verified live, re-ran `test_econ_caravan_api` / `test_sea_caravans` / `test_physical_caravans` (213 passed). No test covers `by_sea` through the API — worth adding in a later QA pass. | MEDIUM | FIXED (Reviewer) |
| 2 | `.github/workflows/ci.yml` (`timeout-minutes: 15`) | CS suite took **17:06** locally (10879 passed, 1 skipped), measured with the whole dev stack, Vite, Chrome and the live check running in parallel; the developer measured 14:41–14:52 alone. Either way it is at / over the 15-min CI step limit: raise the limit or split the CS job before pushing. | MEDIUM (deploy risk, not code) | OPEN — PM decision |
| 3 | `services/character-service/app/sea_raid_crud.py:158`, `services/battle-service/app/main.py:2102` | The exemption keys on the top-priority lock reason; `caravan_escort` outranks `asleep` / `reading`, so a sleeping / reading escort is still pulled into a monster fight. Same pattern as the existing `_escort_available`; acceptable. | LOW | note |
| 4 | `services/character-service/app/sea_pass.py:795-800` | Branch «broken docked ship without a port, players kept by a battle» calls `safe_land` without `strand_all` first, so escorts land apart from the hold; the hold is stranded at `landing_target` one pass later (normally the same place). Corner case. | LOW | note |
| 5 | (deploy note) | On the local dump no econ region has a trade gate (`jail_location_id` NULL, no override) -> every pair is `no_gate` -> after FEAT-215 no inter-region caravans at all on dev (by design: «нет пути — нет сделки»). Check the prod roads card right after deploy. | INFO | — |

Pre-existing issue noted (not FEAT-215): the hidden «Моря» country appears in the admin trade-pairs list — added to `docs/ISSUES.md` (LOW).

#### Automated Check Results
- [x] `py_compile` (all modified / new Python files) — PASS
- [x] `sh scripts/check_econ_copies.sh` — PASS
- [x] `pytest` character-service (`--asyncio-mode=auto`, python:3.10) — PASS, 10879 passed, 1 skipped, **17:06** (see #2)
- [x] `pytest` battle-service (`--asyncio-mode=auto`) — PASS, 2183 passed
- [x] `pytest` locations-service (`--asyncio-mode=auto`) — PASS, 3321 passed
- [x] `pytest` dungeon-service (`--asyncio-mode=auto --timeout=30 --timeout-method=signal`) — PASS (exit 0, no F/E; this suite prints no summary line)
- [x] `pytest` inventory-service (`--asyncio-mode=auto`) — PASS, 2546 passed
- [x] `npx tsc --noEmit` (frontend container) — PASS (0 errors)
- [x] `npm run build` / `vite build` (frontend container) — PASS
- [x] `docker compose config` — PASS
- [x] Live verification (Claude in Chrome + API on localhost) — PASS

#### Live Verification Results
Temporary world on dev MySQL: hidden country «Моря (тест)» -> region «Тестовое море» with 3 linked zones + a deck; «Порт А (тест)» (Шепшир, region 10, country 6, zone 1) and «Порт Б (тест)» (Хикари, region 15, country 7, zone 3), each linked only to a test gate (trade-gate overrides of regions 10 / 15) -> no land path; trade pair 6–7; Captain NPC (admin API); ship «Тестовый когг» (admin API, `cargo_capacity` 1, boarding / zone 1 min, A <-> B).
- Planner: `reach(10, 15)` = sea, freight 5 %; roads card «Только по морю (1): Шепшир ↔ Хикари: ⚓ в обе стороны, Порты: Порт А → Порт Б», «Нет ни суши, ни моря (9)» (after fix #1).
- Dispatch (direct `dispatch_tx`, as the tests do): caravan #619 tools 9.981 u, value 229 + duty 22 + freight 11 = 262 from purse 15; route `[gate A, port A, port B, gate B]`, split 1, stage `to_port`; escrow 244 -> 506 (expected = balance).
- Caravan pass -> `waiting` at port A; admin list (filter «По морю») badge «по морю», «Фрахт: 11 марок (в резерве)», detail chain «Порт А ⚓ море Порт Б», «ждёт корабль в порту Порт А (тест), отмена через 23:57:43».
- Live sea pass: the ship returned to A and departed trip 3 -> «caravan 619 boarded»; stage `aboard`, location = deck; admin detail «aboard / Тестовый когг»; deck page header «В трюме груз каравана» (also in a 360 px iframe); ships list showed «трюм 0/1» before boarding.
- Docked at port B -> `landed`, `route_index` 2; op `caravan_freight` #2082: escrow -> region_treasury 10 = 10, -> country_treasury 6 = 1 (tax of the boarding port's country), key `caravan:c619:freight`; next caravan pass -> arrived -> `caravan_delivery` #2083: 229 -> purse 10, 22 -> country 7; escrow back to 244 (= expected). 262 in = 11 + 229 + 22 out.
- Ship form «Трюм (караванов за рейс)» shows the value; changed to 0 and saved in the UI (DB = 0); with hold 0 a new dispatch is `skipped` (no sea pair -> no deal).
- Cancel path: caravan #620 dispatched -> `waiting`, `sea_waiting_since` back-dated 25 h -> caravan pass `sea_cancelled` 1, `cancel_reason = sea_wait_expired`, `caravan_cancel` #2085 refunds 262 (incl. the reserved freight) to purse 15, goods back to region 10, escrow 244.
- Console: zero errors on /admin/economy, /admin/ships and the deck location page; API calls 200 / 204.
- Cleanup: ship (deactivated -> docked -> deleted 204), stops / passes, Captain NPC (admin DELETE), caravans 619 / 620, 8 locations + neighbours, region 45, country 21, trade pair 6–7, gate overrides back to NULL; tools stock of regions 10 / 15 restored to 64.468 / 30.325. The balanced ledger ops #2081–2085 stay as audit records (the delivered caravan moved 262 from purse 15 to purse 10 / treasuries; the cancelled one netted to zero). No characters were changed.

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-18 — PM: фича создана по ответам пользователя, запускаю анализ
[LOG] 2026-11-18 — PM: пользователь принял значения по умолчанию на 5 вопросов аналитика; передаю архитектору
[LOG] 2026-11-18 — PM: вопросы архитектора — по умолчанию, кроме охраны: игроки-охранники тоже идут в бой с морскими монстрами
[LOG] 2026-11-18 — Analyst: анализ завершён — ядро в character-service (планирование с учётом моря, этап «трюм», фрахт, налёт в море, потеря груза), копии econ_core при новом типе операции, фронт админки караванов и кораблей; 7 технических и 5 вопросов пользователю
[LOG] 2026-11-18 — Architect: спроектировано 10 задач (5 backend, 2 frontend, 2 QA, ревью); миграция CS 054, новая операция caravan_freight (4 копии econ_core), без новых эндпоинтов; 5 решений по умолчанию вынесены PM
[LOG] 2026-11-18 — Backend Dev: задача 1 готова — миграция CS 054_sea_caravans (поля моря и фрахта у караванов, трюм корабля, caravan_ids у морских налётов, таблица потерь груза), ORM-модели, 3 параметра симуляции с границами, операция caravan_freight во всех 4 копиях econ_core; миграция up/down/up на MySQL прошла, копии сверены, тесты зелёные
[LOG] 2026-11-18 — Backend Dev: задача 2 готова — планировщик видит морские пары (sea_cargo.sea_pairs, sea_core.serves), RoutePlanner.sea_route/reach; без суши и моря сделки нет, планировщик строится всегда (сбой — караваны в этом прогоне не идут); морской караван при отправке получает маршрут суша+суша, точку посадки, порты, фрахт (платит покупатель); эскроу-инвариант и доля продавца для охраны учитывают фрахт; в карточке дорог список «по морю»; старые тесты абстрактных караванов получили дорогу через узел, полный набор тестов character-service зелёный
[LOG] 2026-11-18 — Frontend Dev: задачи 6 и 7 готовы — админка караванов (этап моря, фильтр «По морю», группа «Морские караваны», карточка дорог «Только по морю», фрахт/утонувший груз, причины отмены, операция «Фрахт каравана»), трюм в форме и списке кораблей, «В трюме груз каравана» на палубе, метки «ждёт корабль/в трюме» без таймера, морской участок в окне охраны; tsc и build прошли, старый бэкенд не ломает экраны
[LOG] 2026-11-18 — QA: задача 8 готова — чистые тесты test_sea_caravans_core.py (serves/reached_from: маятник, кольцо, отсечка при возврате; планирование с reach/sea_slots/фрахтом; clamp_dispatch; денежные помощники с фрахтом; голова миграции 054): 37 прошли, 7 тестов доли потери груза отложены (skip) до появления помощника из задачи 5
[LOG] 2026-11-18 — Backend Dev: задача 3 готова — караван в порту посадки переходит в «ждёт корабль» и больше не шагает; проход караванов отменяет ждущих дольше лимита (sea_wait_expired) и застрявших (sea_route_lost) через вынесенный cancel_physical (товар без украденного/утонувшего — продавцу, оплата без налёта и взятого фрахта — покупателю, охрана без оплаты); доставка платит из оплаты без фрахта, невзятый фрахт возвращается покупателю; утонувшие единицы вычтены во всех чтениях «в пути»; админский список/карточка отдают морские поля, срок ожидания, потери груза, фильтр kind=sea; схемы расширены; полный набор тестов character-service зелёный
[LOG] 2026-11-18 — Backend Dev: задача 4 готова — морской проход возит грузы: посадка ждущих караванов при отплытии (в пределах трюма, только если корабль идёт в нужный порт), охрана плывёт без билета, выгрузка в порту назначения со списанием фрахта (казна края порта отправления + налог страны), высадка «застрявших» при поломке/удалении/смене маршрута; удалить корабль с налётом на груз нельзя (409); в трюме видно на палубе, охрана не считается пассажирами; caravan_ids у морских налётов; по решению пользователя охрана-игроки дерутся с морскими монстрами (CS и battle-service), тест BS добавлен; тесты CS и BS зелёные
[LOG] 2026-11-18 — Backend Dev: задача 5 готова — налёт на караван в трюме записывает преступление в край порта отправления корабля; добыча налёта учитывает утонувший груз, фрахт налётчикам не достаётся; в списке караванов локации и в окне охраны видны морской этап и порты, таймера у «ждёт корабль/в трюме» нет; потеря груза от монстров (econ_caravan.cargo_loss_units, sea_raid_crud.apply_cargo_loss) — один раз на налёт, доля = процент × проигравшие/решённые группы, деньги не двигаются, страховка в проходе кораблей, охране уведомление «утащили в пучину»; 7 отложенных тестов доли потери включились; раздел «Караваны по морю (FEAT-215)» в docs/services/character-service.md; полный набор CS: 10861 прошли (14:52 — впритык к лимиту CI 15 мин)
[LOG] 2026-11-18 — QA: задача 9 готова — интеграционные тесты test_sea_caravans.py (17 тестов, ~7 с): отправка морского каравана (маршрут, точка посадки, порты, фрахт), без пути сделки нет, ожидание → трюм (вместимость, корабль идёт в нужный порт, охрана без билета) → выгрузка с фрахтом (казна края порта отправления + налог страны) → доставка; отмена по 24 ч и при поломке/удалении/смене маршрута с возвратом; 409 при налёте; налёт в трюме судится по порту отправления, фрахт не добыча; потеря груза от монстров (1 из 2 групп → половина доли, один раз), пустая палуба — без нападения; охрана дерётся с монстрами; палуба и админки. Багов не найдено; полный набор CS: 10878 прошли, 2 пропущены (14:41)
[LOG] 2026-11-18 04:20 — Reviewer: проверка завершена, результат PASS — копии econ одинаковые, миграция 054 корректна, порядок блокировок и деньги (эскроу, фрахт, отмена) сходятся; найден и исправлен баг: схема ответа «Дороги и ворота» теряла список by_sea (карточка не показывала пары «только по морю»); тесты CS 10879 (17:06 — дольше лимита CI 15 мин, решение за PM), BS 2183, LS 3321, IS 2546, DS зелёные, tsc/build ок; живая проверка: караван в порт → ждёт → в трюме («В трюме груз каравана» на палубе) → выгрузка с фрахтом 10 + 1 налог → доставка, отмена по 24 ч с полным возвратом, поле «Трюм» в форме корабля; тестовый мир удалён, запасы восстановлены; в ISSUES.md добавлена мелочь про скрытую страну в списке пар
[LOG] 2026-11-18 — PM: на проде 248 пар регионов без дороги (и 2 региона без ворот) — строгое «нет пути — нет сделки» остановило бы почти всю торговлю; пользователь выбрал мягкий вариант: новый параметр caravan_no_path_abstract (по умолчанию 1) — без дороги и моря пара торгует абстрактно, с морским путём — только кораблём; переключатель в группе «Морские караваны»; лимит шага тестов CI поднят до 25 мин
```

## 7. Completion Summary (filled by PM on close — in Russian)

Сделано: торговля между регионами без сухопутной дороги идёт морем — караван едет по суше до порта, ждёт корабль
(до 24 ч, потом отмена с полным возвратом), плывёт в трюме, выгружается с фрахтом 5 % в казну порта и доезжает до
покупателя. Трюм корабля задаётся в админке кораблей. Налёт на корабль с грузом судят по закону региона порта
отправления; поражение морским монстрам уносит до 25 % груза; охрана-игроки дерутся с монстрами. Пары без дороги и без
моря пока торгуют по-старому (абстрактно) — это выключается параметром «Невидимая торговля без дороги и моря», когда мир
будет дорисован. Лимит тестов CI поднят до 25 минут.
