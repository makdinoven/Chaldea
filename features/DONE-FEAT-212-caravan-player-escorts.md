# FEAT-212: Охрана караванов из игроков (караваны, этап 3)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-12 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Третий этап физических караванов (этапы 1+2 — FEAT-211, на проде с `d9ab152` + окно добычи `c482c8b`). Игроки могут наниматься охранниками к караванам: едут «внутри каравана», невидимые для других, и при налёте внезапно оказываются в бою на стороне охраны — «сюрприз» для налётчиков. Плюс маленькая связка с фракциями (очки за охрану/налёты).

Связанные системы: физические караваны и налёты (FEAT-211: `caravan_route.py`, `caravan_pass.py`, `caravan_api.py`, `caravan_raid_crud.py`, `econ_caravans`, `econ_caravan_raids`), экономика и ledger (инвариант суммы денег = 0, `econ_core.py` — копии в 4 сервисах), закон/розыск/репутация/слава (FEAT-197…204), фракции (FEAT-205…207: очки, пожертвования, победы над врагами), бой (battle-service, `POST /battles/internal/caravan-raid`, автобой autobattle-service), посты в локациях (locations-service), роли НПС (админка НПС, `Admin/ExpandableList`, роль «Скупщик» FEAT-211 как образец).

### Бизнес-правила

**Найм**
- Новая роль НПС **«Караванщик»** (ставит админ). Он стоит у торговых ворот региона (ворота = поле «Торговые ворота» или отделение стражи, как в FEAT-211).
- У караванщика видны караваны, которые **готовятся к отправке** из этих ворот (или уже стоят в воротах и ещё не ушли), и кнопка «Наняться в охрану». Нанимают только у ворот, перед отправкой / пока караван в начальной локации. Вскочить в караван по пути нельзя.
- Мест для игроков: не больше **2–3** на караван (настройка); всего бойцов охраны (мобы + игроки) не больше 5 (лимит команды в бою).
- Кого берут: **не в розыске** в регионе продавца и с репутацией там **не ниже нейтральной**. Обычные ограничения активности (не в бою, не в тюрьме, не без сознания, не в подземелье и т.п.).
- Один персонаж — одна охрана одновременно.

**В пути**
- Охранник «внутри каравана»: его локация переезжает вместе с караваном.
- Его **не видно** в списке игроков локации; в блоке каравана — только «охрана N» без игроков (N = мобы, как сейчас). Налётчики не знают, что внутри есть игроки.
- Сам ходить не может (перемещение заблокировано, пока он в охране).
- Посты в общую хронику локации не пишет (чтобы не выдать себя); есть **«караванный» канал** — посты/сообщения, которые видят только охранники этого же каравана.
- **Видит весь маршрут** каравана (откуда, куда, через какие локации, где сейчас) — он «свой». Слить маршрут налётчикам может только сам, через живое общение (осведомители — естественным образом, без отдельной механики).
- Может **сойти** в любой момент: остаётся в текущей локации, без оплаты, обратно в этот караван его не возьмут.

**Налёт («сюрприз»)**
- При налёте охранники-игроки автоматически оказываются в бою на стороне охраны (команда каравана) — вместе с мобами.
- В бою ходят **только сами**, автобоя для охранников нет (решение пользователя): охранник обязан быть готов к бою; не сходил за 24 ч — вылетает по общему правилу таймаута.
- Охранник пал в бою — обычные последствия проигранного боя.
- Налётчики, напавшие на караван с охранниками-игроками, — без дополнительных преступлений сверх налёта (налёт уже преступление).

**Оплата (экономика, деньги не из воздуха)**
- Плата охране — доля стоимости груза (настройка, по умолчанию **5 %**), её отчисляет **продавец** из сделки; делится поровну между охранниками-игроками.
- Выплата — когда караван **дошёл**.
- Охрана **отбила налёт** — надбавка (настройка) всем охранникам каравана.
- Караван **ограбили** — плата урезается на долю украденного.
- Сошёл по пути — ничего.

**Репутация и слава**
- Доставил груз — растёт репутация в регионах продавца и покупателя.
- Отбил налёт — растёт сильнее, плюс немного славы.

**Фракции (маленький пункт)**
- Админ в настройках фракции может отметить «охрана караванов» и/или «налёты на караваны» как дело фракции. Тогда за доставленный под охраной караван / за удачный налёт членам фракции капают очки — по существующим правилам начисления (дневные лимиты как у побед/пожертвований). Тайные фракции — как сейчас (не раскрываются).

### UX / Пользовательский сценарий
1. Игрок приходит к торговым воротам, открывает караванщика, видит «Караван (продовольствие) — отправляется через ~N мин, мест в охране 2 из 3, плата ~X марок» и нанимается.
2. Караван уходит — игрок вместе с ним; у него на странице — блок «Вы в охране каравана»: маршрут, текущая локация, сколько осталось, караванный канал, кнопка «Сойти с каравана».
3. Налётчики нападают — бой: мобы-охранники + игрок-охранник (сюрприз). Охранник ходит сам (таймаут 24 ч).
4. Караван дошёл — охраннику плата (+надбавка, если отбили налёт), репутация, уведомление, запись в журнале.
5. Админ: ставит НПС-караванщика, видит охранников в подробностях каравана, настраивает долю платы, надбавку, лимит мест, отмечает фракциям «охрана/налёты».

### Edge Cases
- Караван отменён (регион исчез и т.п.) — охранники остаются в текущей локации, без платы (или по правилам архитектора), уведомление.
- Караван стоит в ожидании налёта / в бою — охранник тоже стоит.
- Охранник ушёл в оффлайн надолго — караван всё равно едет; в бою — общий таймаут хода 24 ч, автобоя нет.
- Охранник оказывается в тюрьме/без сознания/в бою по другой причине — архитектор решит (вариант PM: такое невозможно, пока он в охране, т.к. он заблокирован; после поражения в налёте — без сознания, «выпадает» из каравана в текущей локации).
- Налётчик сам нанимается охранником в этот же караван (крыса) — разрешено; при налёте «своих» он в команде каравана (сюрприз для своих же). Архитектор: не дать ему одновременно быть в обеих командах.
- Инвариант экономики (сумма денег мира = 0) — после каждого шага.
- Все тексты — на русском; сроки — обратным отсчётом.

### Вопросы к пользователю (если есть)
- [x] Найм → у НПС «Караванщик» у ворот, до отправки
- [x] Невидимость, блок перемещения, караванный канал, «Сойти» → как предлагает PM
- [x] Сюрприз: 2–3 игрока, всего ≤5 → да. Автобой для охранников — **НЕТ** (уточнение пользователя 2026-11-12)
- [x] (вопросы анализа, 2026-11-12) Окно найма: караван после появления **стоит в воротах «готовится к отправке» ~45 мин** (настройка), потом трогается
- [x] Найм у караванщика **требует пост-намерение «Диалог с НПС»** (как у скупщика). **Гильдию торговцев тоже перевести на обязательный пост** «Диалог с НПС» (сейчас без поста)
- [x] Публичные карточки: пока игрок в охране — в карточке/списках **застывает локация найма**, причина блокировки не показывается; спрятать охранника в списке отрядов на локации и в сообщениях «цель занята»
- [x] Баг из ISSUES.md (любой игрок может выключить чужой автобой, в т.ч. мобу) — **закрыть в рамках фичи**: выключать автобой может только владелец персонажа
- [x] Оплата 5 % от продавца, при доставке, надбавка за отбитый налёт, урезка при ограблении → да
- [x] Репутация/слава за доставку и отбитый налёт → да
- [x] Маршрут охраннику виден целиком (вариант «а») → да
- [x] Кого берут: не в розыске и репутация ≥ нейтральной в регионе продавца → да
- [x] Фракции: отметки «охрана/налёты» как дело фракции → маленьким пунктом, да
- [x] Осведомители отдельной механикой — не делаем

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Paths are relative to `services/`. CS = character-service, BS = battle-service, LS = locations-service, IS = inventory-service, AB = autobattle-service. All line numbers verified on `c482c8b`.

### Affected Services

| Service | Type of changes | Key files |
|---|---|---|
| character-service | core: escort rows + hire/leave + caravaneer NPC role + escort stepping inside `caravan_pass` + escort fee in `deliver_physical` + raid roster (escorts to team 1) + escort lock reason + reputation/fame/faction awards + admin reads + new SimParams + migration 051 | `economy_caravan_crud.py` (`dispatch` :411-491, `deliver_physical` :676-740, `held_by` :812), `caravan_pass.py` (`step_caravan` :95-121), `caravan_raid_crud.py` (`begin_raid` :223, `spawn_guards` :264, `settle_raid` :439), `caravan_api.py` (A1/A2 :118-192), `battle_client.py:71-98`, `activity_lock.py`, `main.py` (`update_location` :2359-2448, `/by_location` :2271, `short_info` :2507-2582), `law_crud.py:555` (patrol arrival lock), `reputation_core.py:93-101`, `faction_kills.py`, `econ_sim.py:149-176`, `schemas.py:2000-2150,2525+`, `models.py` |
| battle-service | raid create accepts escort players for team 1 (exempt from the escort lock), escort autobattle on missed / offline turns, lock column in `activity_lock.py` | `main.py:1885-1944` (B1), `:947-1034` (`_assemble_battle`), `:898-913` (`_ensure_not_activity_locked`), `:6932-7101` (`handle_expired_turn`), `activity_lock.py:148-196`, schemas `CaravanRaidBattleCreate` |
| autobattle-service | possibly: a "take over after N minutes / on missed turn" mode, and an owner for internally registered players (see Risk R4 / bug added to ISSUES.md) | `app/main.py:154-222` |
| locations-service | lock reason in its `activity_lock.py` copy (movement / posts / NPC / houses refuse automatically); maybe nothing else | `activity_lock.py:148-196`, `main.py:236-268,1040,1436,1729` |
| inventory-service | lock column in its `activity_lock.py` copy (trade/teleport refuse automatically) | `activity_lock.py:148-196`, `main.py:1814-1840` (trade) |
| party-service | hide escorts from `GET /party/by-location` (raw SQL) | `crud.py:127-135`, `main.py:213-240` |
| frontend | caravaneer modal (hire), «Вы в охране каравана» panel/banner + caravan channel + «Сойти», lock reason texts, admin: caravaneer role + tab, escorts in caravan detail, new params + hints, faction flags, journal label (if new op type) | `constants/npc.ts:23,52`, `AdminNpcsPage/npcTabKeys.ts`, `NpcExpandedPanel.tsx:92`, `LocationPage/NpcProfileModal.tsx:431-449`, `hooks/useActivityLock.ts:20-26`, `CommonComponents/ActivityLockBanner.tsx`, `LocationPage/LocationPage.tsx:1045-1081`, `LocationPage/CaravanSection.tsx`, `Admin/EconomyPage/CaravanDetail.tsx`, `EconomyCaravans.tsx:49-81`, `paramHints.ts:638+`, `economyLabels.ts:46-48`, `Admin/FactionsPage/EnemiesEditor.tsx` |
| dungeon-service / user-service | none (dungeon reads the lock via CS HTTP `gameplay.py:993`; no new permission needed if existing `economy:*`/`npcs:*` suffice) | — |

### 1. Caravan lifecycle (character-service)

- **Dispatch happens only inside the 6 h economy tick**: `econ_tick._caravan_pass` (`econ_tick.py:1621`, called at `:1421`), slots `floor(unix / 21600)` (`econ_tick.py:5`) → 00/06/12/18 UTC. `RoutePlanner` built at `econ_tick.py:1663`, `dispatch_tx` at `:1673`. A physical row is born **already standing at the seller's gate** with `route_index=0`, `current_location_id=route[0]`, `next_move_at = now + step_delay(params, u)` (`economy_caravan_crud.py:466-472`), `step_delay` = `caravan_step_minutes` (18) ± 25 % (`:406-408`, `econ_sim.py:163`). **There is no "preparing to depart" state**: the only hire window today is ~13.5–22.5 min after a tick (plus a possible post-hold, see below), 4 times a day. The UI already gets the countdown (`caravans_here` `departs_in_sec`, `caravan_raid_crud.py:186-189`). A pre-departure window needs either a new param (e.g. first `next_move_at = now + departure_minutes`) or a new state — architect decision.
- **Gates**: route start/end = `econ_regions.trade_gate_location_id` (override) else `Regions.jail_location_id` (guard station) — `region_gates()` `economy_caravan_crud.py:352-367`, `caravan_route.effective_gate` (`caravan_route.py:70`), `law_facility.station_location` (`law_facility.py:62-67`). So "the caravaneer stands at the gate" = NPC whose `current_location_id` equals `RoutePlanner.gate(from_region_id)`; a caravan is "at the start gate" while `route_index == 0 AND arrived_at IS NULL AND status='in_transit'`.
- **Stepping** `caravan_pass.step_caravan` (`caravan_pass.py:95-121`): one tx, locks only `econ_caravans(row)` (`_lock_caravan`); held (`held_by` :812-821: raid `starting|fighting`, or post hold inside the single 2 h window) → no move; else `route_index += 1`, `current_location_id = route[i]`; last node → `arrived_at`. The pass runs every ~55 s from `econ_scheduler.run_scheduled_once` (`econ_scheduler.py:102-109`), throttled by `claim_run` (`caravan_pass.py:47-55`). **This is the natural place to move escorts**: in the same tx, after the caravan row, lock the escort `characters` rows (asc id) and write `current_location_id` (lock order `econ_caravans → … → characters`, `economy_caravan_crud.py:24-28` — consistent). Note: the raw write must also clear `house_room_id` (as every move does, `main.py:2405`) and must NOT go through `update_location` (law entry check, faction territory refusal) — escorts are "inside" the wagon.
- **Delivery** `deliver_physical` (`economy_caravan_crud.py:676-740`), called by `_deliver_arrived` (`caravan_pass.py:173-197`, skipped while an economy run is `running`). Lock order: regions ×≤2 → goods ×≤2 → `econ_caravans(row)` → accounts. Seller money: `seller_part, duty_part = econ_caravan.remaining_payout(value, duty, paid, raid_paid)` (`econ_caravan.py:352-364`), legs `escrow → seller purse (seller_part)`, `escrow → buyer country (duty_part)`, op `caravan_delivery`, key `caravan:c<id>:done` (`:699-705,726-733`). **The escort fee can be carved out right here**: extra legs `escrow → character(escort)` with `seller_part −= fee`; the escrow sub-invariant `escrow == Σ(paid − raid_paid)` of in-transit rows (`escrow_expected` :161-168) stays intact because everything still leaves the escrow in the same op at delivery. Character accounts must be locked before `econ_accounts` (precedent `_pay_out` `caravan_raid_crud.py:518-520`). Cancel branch (`:707-723`, `caravan_cancel` full refund) — escorts get nothing there. "Robbed → fee cut" falls out naturally if the fee is a share of the **remaining** value (`value × R/(paid)` or of `seller_part`).
- **Ledger op types**: `econ_core.validate_operation` (`econ_core.py:508-550`) checks only that `op_type ∈ OP_TYPES` and that source kinds (emission/adjustment) are not touched — **it does not restrict leg account kinds per op type**. So escort legs inside the existing `caravan_delivery` op need **no econ_core change**. A dedicated op type (e.g. `caravan_escort`, cleaner journal/admin filters) means: `econ_core.py:156-161` (`CARAVAN_OP_TYPES`) + `tests/econ_contract_cases.py` in CS (canonical) copied byte-for-byte to IS/LS/dungeon (`scripts/check_econ_copies.sh:43-53`), + frontend label `economyLabels.ts:46-48`. Bonus for a repelled raid needs a funding decision (seller share again at delivery = invariant-safe; anything else = a new money source).
- **Cancel / end paths escorts must be released on**: delivered, cancelled (`deliver_physical` both branches), plus raid outcomes. No admin "cancel caravan" endpoint exists. Delivery waits while `econ_tick_runs.status='running'` (`caravan_pass.py:157-161`).

### 2. Raid flow and battle

- **Start** (`caravan_api.py:152-192`): `begin_raid` (Tx A, `caravan_raid_crud.py:223-261`: caravan lock, same location, UNIQUE raid row per caravan, gate pre-check) → `spawn_guards` (`:264-304`, count = `caravan.guard_count` clamped to `MAX_GUARDS=5` `:70,281`, mobs `spawn_type='dungeon'`) → `battle_client.create_caravan_raid_battle` (`battle_client.py:71-98`) → `mark_fighting` (Tx B). **One raid per caravan ever** (UNIQUE `caravan_id`, also for `repelled`) → "отбили налёт" can happen at most once per caravan.
- **`begin_raid` does not check the leader's activity lock** — BS does it (`main.py:1919`) after guards are spawned (then cleanup). The "rat" case (raider is an escort of the same caravan): with an escort lock reason the leader is refused by BS `_ensure_not_activity_locked`, and squadmates who are escorts are silently skipped by `_free_squadmates` (`main.py:1267`) → no one can be in both teams, provided the escort lock exists. An escort also cannot write the raid post (posts are refused under any lock, `LS main.py:1040`).
- **B1** `POST /battles/internal/caravan-raid` (`BS main.py:1885-1944`): team size check only on guards (`:1902`), leader checks (`:1908-1919`), `_ensure_caravan_guards` requires **NPCs** at the location (`:1862-1882`) — escorts cannot be passed as `guard_character_ids`; a separate list (e.g. `escort_character_ids`) is needed, with: player, at the location, not in a battle, lock-free except the escort reason (exemption pattern = `allow_dungeon_session_id` in `_ensure_not_activity_locked` `:898-913`), and `len(escorts)+len(guards) ≤ BATTLE_MAX_TEAM_SIZE` (5, `config.py:21`). Teams: `CARAVAN_RAIDER_TEAM=0`, `CARAVAN_GUARD_TEAM=1` (`:1854-1855`); `_assemble_battle(player_ids, teams, "pve", loc, caravan_raid_id=…)` (`:1933-1937`). CS must spawn `min(guard_count, 5 − escorts)` mobs (brief: total ≤ 5).
- **Turn order** = initiative over all participants (memory: teams do not alternate) — an escort may act first; the first deadline is `now + TURN_TIMEOUT_HOURS` (24 h, `config.py:11`, `main.py:966`).
- **Autobattle**: `_assemble_battle` registers **only NPC participants** with AB `POST /internal/register` (`main.py:1013-1032`). AB internal register (`AB main.py:188-207`) adds the pid to `ALLOWED` and acts immediately and on every `battle:*:your_turn` (`:82-101`) — there is **no "act only if the player did not move in N minutes" mode**; `SPEED slow` is just a 3 s delay (`config.py:15`, `main.py:347`). Registries are **in-memory** (`main.py:46-53`) — lost on an AB restart. So "escort plays himself, autobattle only when offline / late" needs new logic: e.g. a short per-escort deadline in BS whose expiry triggers AB instead of dropping, or an AB "deferred" mode. Registering escorts with `/internal/register` at creation = autobattle from the first turn (the player can switch it off via public `/autobattle/unregister`, which passes when `OWNER` is unset — see R4).
- **Missed turn today** (`handle_expired_turn` BS `main.py:6932-7101`, swept every 60 s): after the 24 h deadline the participant is **dropped** (`hp=0`, `dropped_out`), battle continues or finishes via `_finalize_battle(by_timeout=True)`. Deadline is recomputed with the global `TURN_TIMEOUT_HOURS` in 5 places (`main.py:966,4745,5246,5524,7062`) — no per-battle / per-participant override exists.
- **Defeated player on the surface PvE**: no unconsciousness and no location change — only resources synced back (`_finalize_battle` `main.py:2776+`, `_sync_final_resources`). `unconscious_until` is set only by the dungeon wipe (`CS main.py:4453-4477`, `/internal/activity-lock/knockout`, reusable) and for KO'd guard NPCs (`law_crud.py:471`). So "без сознания после поражения" = an explicit CS call in settlement (decision).
- **End hooks**: `_notify_caravan_battle_end` (`main.py:1977-1993`) → CS `/characters/internal/caravans/raid-result` → `settle_raid` (`caravan_raid_crud.py:439-501`, statuses won/repelled/aborted/expired); poll fallback in the pass. Escort payout/bonus/reputation would hook into the `repelled` branch (`:483-487`) or be deferred to delivery. PvE rewards for team-1 winners: defeated raiders are players → no mob XP/loot (`_distribute_pve_rewards` handles mobs only); faction kill points for pve ignore player losers (`faction_kills.py:185-187`).
- Join requests to raid battles are already refused (`CARAVAN_JOIN_FORBIDDEN`, `main.py:1859`).

### 3. Location, movement and activity locks

- **Lock model**: columns on `characters` owned by CS; `compute_lock` priority jail > law_encounter > unconscious > dungeon > asleep > reading (`CS activity_lock.py:62-86`), `lock_message` Russian texts (`:113-133`). **Four copies, NOT CI-guarded** (not in `check_econ_copies.sh`): CS (133 lines, pure), BS = LS (identical md5, async DB read `_LOCK_SQL` `:148-152` + legacy fallback `:153-163` for deploy skew), IS (sync twin). A new reason (e.g. `caravan_escort` from a nullable `characters.caravan_escort_id`) must be added to all four + the SQL in 3 + `lock_for_character` (`:89-97`) + `law_crud.check_patrol_arrival` which calls `compute_lock` with explicit args (`law_crud.py:555-560`).
- **Where the lock already blocks** (automatic once the reason exists): LS move (`check_not_locked_for_post` `main.py:242-257` used by `move_and_post` :1436, `check_not_locked_for_move` :260-268 used by `quick_move` :1729), posts (:1040), NPC shop/fence/dialogue/quests (:2785,3100,3284,3404,3607,3778), loot, houses (`houses.py` 18 sites), tag-player (:1386); BS 24 call sites (mob/pack/party attacks, PvP attack — victim too `main.py:5421+` "Цель", join requests :6249); IS trade (`main.py:1840-1841`, target too), home teleport, backpack; CS bank/mint/guild/faction QM/territory, teleport master (`crud.py:3870`), dungeon entry via CS internal lock (`main.py:4386-4427`), faction eject skips busy characters (`faction_territory._busy` :418-422), patrol arrival skips locked (`law_crud.py:555`).
- **Gaps**: CS `PUT /characters/internal/{id}/update_location` refuses only `law_encounter` and (non-prison) `jail` (`main.py:2393-2397`) — it trusts LS for the other reasons; an escort reason should be added there too (defence in depth). Admin teleport / home teleport go through `_prepare_move` (`main.py:932-970`) which checks only battle + dungeon. Gathering is not an activity lock — the hire must check it separately (CS does not read `gathering_sessions`; LS owns it, `models.py:767`; BS uses LS `/locations/internal/gathering-status`).
- **Message leak**: the lock message is shown to the other side when the escort is the target (`subject="Цель"` in PvP attack, `"Целевой персонаж"` in trade) — the text must not say «в охране каравана» to third parties.
- Other movers that must leave escorts alone: patrol `step_guard` moves only NPCs; faction eject (`faction_territory.py:425-480`) skips locked; caravan routes may cross faction-closed locations (the escort is moved by raw write, no territory check).

### 4. Visibility — every place an escort must be hidden

1. **Location players list**: LS `get_client_location_details` (`crud.py:2566-2728`) → `get_players_in_location` (`crud.py:2796-2815`) → CS `GET /characters/by_location` (`main.py:2271-2302`, ORM filter `current_location_id == loc AND is_npc == False`). Same endpoint is called by the frontend `api/squads.ts:150-155` and feeds gathering nodes (`crud.py:2683`). Filter here hides escorts from PlayersSection (PvP / trade / invite buttons).
2. **Squads on a location**: party-service `GET /party/by-location` (`party-service/app/main.py:213-240`) uses its own raw SQL `get_character_ids_at_location` (`crud.py:127-135`) — **independent of (1)**, would show an escort in his squad here.
3. **Public character reads expose `current_location_id`**: `GET /characters/{id}/short_info` (public, `main.py:2570-2582`; body `:2507-2547`) — also exposes **`activity_lock` with its `reason`** to anonymous callers; `GET /characters/{id}/public` (`crud.py:735`), `GET /characters/list` (`main.py:2583+`, `:2655`). Polling any of these reconstructs an escort's route and reveals the escort status (lock reason). Frontend does not render it on public pages, but the API is open.
4. **Patrol sweep** `_SQL_PRESENT` (`patrol_crud.py:184`) — then `check_patrol_arrival` skips locked characters (no leak, only a needed lock arg).
5. **Battle spectating** `battle_visibility.py:100-106` (anyone at the location may watch an active battle) — fine; after the raid starts escorts are visible as participants (that is the surprise).
6. Admin NPC/character lists — admin only, fine.
- **Location posts** (`LS models.py:175-196`, `posts.location_id`) are public everywhere: `GET /{location_id}/posts/`, `/posts/latest` (homepage, across all locations, `crud.py:2043+`), character post stats. A caravan channel on `posts` would need a new column + filters in all those reads + XP/quest side effects (`main.py:1088-1133`) — heavy and leak-prone.
- **Reusable chat mechanisms**: notification-service global chat — channels are an ENUM `general|trade|help` (`chat_models.py:11`), not private; messenger conversations (`messenger_models.py:15-60`) are **user-level OOC** chats created by a user (`messenger_routes.py:224+`, rate-limited, no internal create API); dungeon run chat (FEAT-176, `dungeon-service/app/chat.py`, Redis, 200 lines per run, `gameplay.py:1563-1583`) is the closest precedent in shape (per-group, transient, members-only) but lives in dungeon-service; **CS has no Redis**. Simplest fit: a small CS table (e.g. `econ_caravan_messages`) or JSON log on the escort/caravan, members-only reads — architect decision.

### 5. NPC role pattern (fence, FEAT-211)

- Backend role is a free `String(50)` (`CS models.py:65`), no validation; constant `FENCE_ROLE = "fence"` (`fence_crud.py:32`); settings table `econ_fences` per NPC with admin A11/A12 (`fence_api.py`, `fence_crud.py:168` refuses when role ≠ fence → 409). Player endpoints for the fence live in **LS** (`main.py:3395-3428`, `_require_fence_access`: owner, activity lock, `fence_terms`, `_require_npc_gate` = FEAT-145 `npc_dialogue` post gate + reputation tier gate `main.py:1012-1027`, same location). The guild NPC (`guild`) is the CS-side precedent: `economy_guild_crud.resolve_guild` (`:398-417`: owner, role, alive, lock on write, same location) — **no `npc_dialogue` post gate** there. With an ~18 min hire window an `npc_dialogue` post requirement is practically prohibitive (decision).
- Frontend: `constants/npc.ts:23` (`NPC_ROLES` entry) + `:52` (icon); `AdminNpcsPage/npcTabKeys.ts` (`NpcTabKey` union, `NPC_TAB_KEYS`, `NPC_TAB_LABELS`, `ROLE_TABS` keyed by **saved** role); `NpcExpandedPanel.tsx:92` (`case 'fence'` → `FenceSettingsPanel` with `onDirtyChange`); player button in `LocationPage/NpcProfileModal.tsx:431-449` (`npc.npc_role === 'fence' && isCharacterHere && characterId`) opening a modal. Reputation kill weight: a new role falls to `ROLE_FALLBACK` −150 unless added to `_PEACEFUL_ROLES` (`reputation_core.py:104-113`, copied to LS).
- A caravaneer may need no settings table at all (the gate is regional) — then no admin tab; or a tab listing the gate's caravans. Caravaneer at a non-gate location → nothing to show (A6 «Дороги и ворота» card already lists effective gates).

### 6. Reputation and fame

- Actions: `reputation_core.DEFAULT_ACTIONS` (`:93-101`, tuple `(code, name, points, daily_cap, has_source, sort_order)`), codes `:38-46`; copied byte-for-byte to LS (`check_econ_copies.sh` group `reputation_core`). Rows seeded by migration (`038_reputation.py:177-179` INSERT … WHERE NOT EXISTS; `050_physical_caravans.py:136-139` precedent of a later update). New positive actions (e.g. `caravan_escort` «Охрана каравана», `caravan_defense` «Отбит налёт») = migration INSERT + `DEFAULT_ACTIONS` + LS copy; `test_reputation_core.py` counts the seed (was adjusted in FEAT-211).
- `reputation_crud.apply_reputation(db, character_id, region_id, action, idem_key, delta=None, echo=True, …)` (`:417+`): idempotent per `(idem_key, origin region)`, daily cap for automatic positive deltas (`:454`), echo to same-country regions at `echo_pct`; **automatic positive changes already feed fame** via `shadow_core.fame_from_reputation` (`shadow_core.py:334-340`, `fame_rep_ratio`, hook `reputation_crud.py:505`) — "plus some fame" for a repelled raid may need nothing extra, or an explicit `renown_crud.add_fame(db, character_id, points, source, event_key)` (`renown_crud.py:149`). Two regions (seller + buyer) → two calls with distinct keys; `echo=False` to avoid double echo inside one country (FEAT-211 precedent `caravan_raid_consequences`).

### 7. Factions

- Points: `faction_crud.change_points(db, member, delta, event_type, now, event_key=, reason=)` (`faction_crud.py:727`), idempotent via `faction_log` UNIQUE(event_key, faction_id) (`models.py:1858-1871`, `event_type` VARCHAR(30)). Day caps per (character, faction, UTC day) in `faction_donation_days` (`models.py:2009-2019`: `marks`, `points` (donations), `kill_points` (FEAT-207)). Kill pattern `faction_kills.apply_battle/_apply_winner` (`:166-302`): memberships of winners, `fc.kill_cap` (faction `kill_points_daily_cap` or global), `fc.kill_gain`, hostile penalty, `recheck_ranks`, notices. **Secret factions**: kill points are awarded to secret members too (`_active_memberships` without `open_only`), notices only to the player — same rule fits.
- **Minimal flags**: `faction_enemies` (`models.py:2107-2119`: `kind VARCHAR(10)` mob|npc|hostile, `ref_id`, `points`, UNIQUE(faction, kind, ref)) already models "дело фракции" with a singleton precedent (`hostile`, ref 0, «может быть только одна», `faction_kills.py:36`). New kinds `escort` / `raid` (≤10 chars — `caravan_escort` would NOT fit) with ref 0 + points reuse the admin UI (`EnemiesEditor.tsx`, which also edits the kill cap) and the kill day cap. Alternative = two booleans on `factions` (+ migration) and a fixed points param.

### 8. Law checks for hiring

- Wanted in region: `law_crud.read_wanted(db, cid, region_id, settings, now) > 0` (`law_crud.py:334-344`, effective with decay); the patrol prefilter uses stored `character_wanted.value > 0` (`patrol_crud.py:184-190`).
- Reputation ≥ neutral: neutral tier = `wanderer` «Скиталец» (−99…99, `reputation_core.py:83-92`); `reputation_crud.gate_failure(db, cid, region_id, "wanderer")` returns «Нужна репутация: …» or None (`:247-258`), or `rc.meets(effective(...), code, tiers)`. Seller region = `econ_caravans.from_region_id`. Outlaw factions (FEAT-207) are a separate signal (`faction_outlaw_regions`) — decide whether it counts.

### 9. Frontend

- Location page: `CaravanSection.tsx` (FEAT-211; A1 polling 60 s, countdown, dimmed when `locked`) rendered at `LocationPage.tsx:889`; the lock text block replacing the post editor `LocationPage.tsx:1045-1081` (per-reason strings); site-wide `ActivityLockBanner` (`Layout.tsx:55`, reasons jail/law_encounter/asleep/…) — natural home of a «Вы в охране каравана» strip with a link/drawer (route, position, countdown, channel, «Сойти»). `useActivityLock.ts:20-26` union `ActivityLockReason` must gain the reason. Battle victory window already asks `GET /characters/caravans/raids/by-battle/{id}` (`caravan_api.py:128-137`) — an escort share could reuse it.
- NPC modal: `NpcProfileModal.tsx` role buttons (banker/minter/fence/guild at `:396-468`) — add «Караваны» for `caravaneer`.
- Admin: `CaravanDetail.tsx` (route/hold/raid card `:91-160`) → escorts list; `EconomyCaravans.tsx` `CARAVAN_PARAMS` / `PHYSICAL_PARAMS` (`:49-81`) + `paramHints.ts` (`:638+`) for new keys (fee share, bonus, seats, departure window); `economyLabels.ts:46-48` if a new op type. Backend param plumbing: `econ_sim.SimParams` (`:149-176`), bounds `schemas.py:2000+` (`:2101-2110`), `ECON_SIM_INT_PARAMS` (`:2147`), update schema (`:2525+`), read schema (`:3281`), `CARAVAN_PARAM_KEYS` (`economy_caravan_crud.py:76-87`); a test excludes `fence_` keys from a seed (FEAT-211 log) — new prefixes may need the same.

### 10. Migrations

- Heads: CS `050_physical_caravans` (→ next 051), IS `037_stolen_bales`, BS `010_battle_caravan_raid`, LS `058_quest_faction_vouchers`, user-service `0035_faction_economy_perm`. Revision ids ≤ 32 chars (e.g. `051_caravan_escorts` = 19). MySQL gotchas (memory): create the FK index before the FK; avoid ENUM ALTER (use VARCHAR); idempotent column checks like 050. Tests asserting "single head == 050" exist in `test_admin_mob_region_ready.py` and `test_reputation_core.py` → must move to 051.
- Likely DDL (CS only): `characters.caravan_escort_id` (or a lock column) — note `characters` is read by every service's lock SQL; new table `econ_caravan_escorts` (caravan_id, character_id, joined_at, left_at, status, payout, bonus, …, UNIQUE active per character); channel storage; reputation_actions seed rows; faction kinds need no DDL (VARCHAR(10)). BS: none if escorts go as a new request field (team assembly only); a per-participant autobattle flag would live in Redis state, no DDL.

### 11. Tests to reuse

- CS `tests/test_physical_caravans.py` (world fixture `world` :84-104 built on `test_econ_tick.factory`, `_physical_world` :111, `_dispatch` :127, `_pass` :160, `_walk` :171, `_check` :145 = world-sum + escrow invariant, locations `L_GATE1…` :53-62, `raider` fixture :175); `tests/test_caravan_raids.py` (`rw` :118-159, `api` :166-180, `_start` :209, `_settle` :217, `_gold` :224, `_person` :112); `tests/test_fences.py`; `tests/econ_contract_cases.py` (`WORLD_SUM_SQL`). BS `tests/test_caravan_raid_battle.py` (B1, team cap, `_free_squadmates`, callbacks); LS `tests/test_caravan_gate_fence.py`; lock tests per service (`test_activity_lock*.py`, `test_activity_lock_law_priority.py`, `test_feat175_locks.py`, `test_law_lock.py`).

### Existing Patterns

- CS: sync SQLAlchemy, raw parameterised SQL for foreign tables, Pydantic v1, Alembic `alembic_version_character`; every multi-step flow = short own transactions under the documented global lock order (`economy_caravan_crud.py:24-30`); idempotency keys on ledger ops (`caravan:c<id>:<part>`), reputation, faction log; notices published after commit (`law_notify.Notice`); HTTP never inside a transaction (`db.rollback()` before calls, e.g. `law_flows.py:89`).
- BS: async; internal endpoints behind `/internal/` + `verify_internal_token`; tag columns on `battles` + fire-and-forget callbacks with 3 retries + CS poll fallback.
- LS/IS/BS read CS-owned lock columns directly from the shared DB through their `activity_lock.py` copy; CS is the only writer.
- Frontend: Tailwind + design-system classes, no `React.FC`, 360 px, Russian errors via `apiErrorMessage`.

### Cross-Service Dependencies (new/used)

- CS → BS `POST /battles/internal/caravan-raid` (extended payload: escorts); BS → CS raid-result callback (exists); CS → BS poll `GET /battles/internal/{id}/result` (exists).
- BS → AB `POST /internal/register` (exists, NPC-only today) — for escorts, possibly a new deferred mode.
- CS → LS? only if gathering must be checked/cancelled at hire (`locations_client.cancel_gathering` exists, or raw read of `gathering_sessions`).
- party-service ← shared DB: must learn to exclude escorts (raw SQL on `characters`).
- LS/IS/BS ← shared DB `characters.<escort column>` via `activity_lock.py` copies.
- CS → notification (RabbitMQ `general_notifications`) for hire/delivery/payout notices (exists via `law_notify`).

### DB Changes (likely)

- CS 051: escort table + `characters` lock column (+ index), optional caravan message table, `reputation_actions` INSERTs, possibly a departure field on `econ_caravans` (or reuse `next_move_at`), params in `econ_sim_settings.params` JSON (no DDL).
- No changes expected in IS / LS / user-service; BS none unless a per-participant DB flag is chosen.

### Risks

- **R1 Hire window is tiny**: physical caravans exist only after a 6 h tick and leave their gate after ~13.5–22.5 min (`economy_caravan_crud.py:471`) → without a departure delay hardly anyone can hire. → Architect: departure window param (and show it to the caravaneer).
- **R2 Leaks of the hidden escort**: (a) public `short_info` returns `activity_lock.reason` + `current_location_id` anonymously (`main.py:2570-2582`); (b) `/characters/{id}/public`, `/characters/list` return `current_location_id`; (c) party-service `/party/by-location` own SQL; (d) lock messages shown to third parties («Цель …», «Целевой персонаж …»); (e) caravan block `guard_count` must remain mobs only. → filter/neutralise each; a test per surface.
- **R3 Offline escorts in battle**: no "autobattle on missed turn" mechanism; missed turn = drop after 24 h (`BS main.py:6932-7101`), and an offline first actor freezes the raid (and the caravan, held while `fighting`, up to `caravan_raid_battle_max_hours`=48). AB state is in-memory (lost on restart). → design a takeover (short escort deadline → AB) and test it.
- **R4 Autobattle unregister without owner** (pre-existing bug, added to `docs/ISSUES.md`): public `POST /autobattle/unregister` passes when `OWNER[pid]` is unset (`AB main.py:213-215`) — every internally registered participant (all mobs today, escorts tomorrow) can be switched off by any logged-in user; the mob then never moves and is dropped at the 24 h deadline → free PvE victory. For FEAT-212 a raider could switch off an offline escort's autobattle.
- **R5 Lock copies drift**: 4 `activity_lock.py` copies, not CI-checked; BS/LS/IS SQLite fixtures mostly lack even the law columns and rely on the legacy fallback (`activity_lock.py:153-163`, matches only `jailed_until`/`law_encounter_id` in the error) — a new column in `_LOCK_SQL` will raise in those fixtures (memory «тихие отказы»: wrong-schema fixtures) unless the fallback is extended. 
- **R6 World-money invariant**: fee/bonus must come out of the escrow inside the delivery op (or another real account), never from nowhere; `escrow_expected` formula unchanged only if nothing is paid from escrow before delivery. A bonus paid at `repelled` time from escrow would require `raid_paid`-like accounting. Test `_check` after every step.
- **R7 Raid team composition**: guards spawned = `guard_count` (up to 5) today; must be reduced by the number of escorts; BS validates guard list only. Escorts defeated → stay in the caravan or drop (decision); escorts in battle must not be moved by stepping (caravan is held during `fighting`, OK).
- **R8 CS update_location** does not enforce non-law locks (`main.py:2393-2397`); fine today because LS checks first, but any other caller could move an escort. Admin/home teleport (`_prepare_move`) ignores locks except battle/dungeon.
- **R9 CI time**: CS full suite ~15.5 min locally / ~8–9 min in CI vs the 15-min job cap (`.github/workflows/ci.yml:87`). New CS tests must be lean (reuse `test_physical_caravans` fixtures, no new heavy world builds); BS tests run with `--timeout=30` per test (`ci.yml:63`).
- **R10 Escort inside closed faction territory / patrol zones**: raw location writes skip faction access and law entry by design; after «Сойти» the character stands there — faction eject and patrols will handle him normally (acceptable, document).

### Questions for PM / user

1. **Окно найма**: караван сейчас появляется у ворот только в момент пересчёта экономики (4 раза в сутки) и уходит через ~15–20 мин. Добавить «сборы перед отправкой» (например, 30–60 мин стоянки у ворот после пересчёта)? Это задерживает и доставку.
2. **Пост-намерение для караванщика**: у скупщика нужен пост «Диалог с НПС»; у гильдии — нет. Требовать пост для найма? (С коротким окном — почти невозможно.)
3. **Публичные данные персонажа**: открытая карточка (`short_info`) показывает всем локацию и причину блокировки. Прятать у охранника локацию/«в охране» во всех публичных карточках (вся команда игроков увидит «скрыто»)?
4. **Оффлайн-охранник**: автобой сразу с первого хода (игрок может выключить сам) или только если не сходил за N минут (нужен новый механизм)? Сколько N?

Technical (architect): fee/bonus funding and op type (`caravan_delivery` legs vs new `caravan_escort`), departure window, escort lock column/reason + neutral third-party message, BS escort list + lock exemption, guard count reduction, autobattle takeover design, defeated-escort rule (KO via `/internal/activity-lock/knockout`?), channel storage, faction kinds vs booleans, which faction day counter (kill_points vs new).

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Verified facts / corrections to the analysis

- **Guild gate already exists for hand-in**: `POST /characters/economy/guild/npc/{id}/hand-in` already requires an open `npc_dialogue` gate naming the guild NPC (`economy_api.py:1121-1131`, `locations_client.check_npc_gate`, fail-closed 503, `MSG_GATE_CLOSED`, since `f8f7729`). Only the **window** (`GET /characters/economy/guild/npc/{id}`, `economy_api.py:1046`) is open. "Guild requires the post" therefore = gate the GET view the same way (3.11). PM may tell the user that hand-in was already gated.
- **More public leaks than listed**: user-service `GET /users/{user_id}/characters` (public) and `GET /users/{user_id}/profile` (stranger variant) build character cards from CS **internal** `short_info` (`user-service/main.py:305-347`, callers `:2026`, `:2105`) → `current_location` + `activity_lock` reach any viewer. Covered in 3.6.
- **Battle-service checks activity locks only at battle creation / join / party flows** (`_ensure_not_activity_locked` call sites 1079-7668), never on turn actions → an escort with the escort lock can act normally inside the raid battle; only B1 needs an exemption.
- **Escorts are players** → `_assemble_battle` never registers them with autobattle (NPC-only, `main.py:1013-1032`). No autobattle work is needed (user decision); the 24 h sweeper drop applies unchanged.
- `lock_message` third-party subjects in use: `"Цель"`, `"Целевой персонаж"`, `"Другой участник обмена"`, `"Персонаж инициатора"`, `"Игрок"`, a character name (`CS main.py:4426`). Self calls use the default `"Персонаж"` or `"Ваш персонаж"`. Default subject is also used for some targets → the escort text must be neutral for everyone (3.5).
- CS already has `_is_in_battle` (`main.py:903`) and `locations_client.check_npc_gate` (`locations_client.py:328`); `gathering_sessions` has `character_id`, `status`, `complete_at` (LS `models.py:755+`).

### 3.1 Overview

```
6 h tick dispatch() ── physical caravan born at the seller gate, route_index 0,
                       next_move_at = now + caravan_departure_minutes (45)  ← "сборы"
player at gate ── npc_dialogue post naming the «Караванщик» ──► C1 list caravans preparing here
              ── C2 hire ──► econ_caravan_escorts row (active) + characters.escort_caravan_id = caravan
                              (activity lock reason `caravan_escort`: no walking/posts/trade/attacks…)
caravan_pass step (same tx) ──► caravan row moves ──► active escorts' characters.current_location_id moves
escort ── C3 own job (full route) / C5-C6 caravan channel / C4 «Сойти» (stays, no pay, no rejoin)
raid A2 ──► spawn mobs = max(1, min(guard_count, 5 − escorts)) ──► BS B1 team 1 = mobs + escorts (players, no autobattle)
battle end ──► callback + fallen_character_ids ──► settle: won → all escorts fall out; repelled → fallen ones fall out
arrival ──► deliver_physical: caravan_delivery op gets extra legs escrow → escort (fee [+bonus]) carved from seller part
         ──► escort released at destination gate ──► rewards step: reputation seller+buyer, defense rep + fame, faction points
public cards / location lists / squads ──► escort hidden, public location frozen at hire location
```

### 3.2 Departure window ("сборы")

- New SimParam `caravan_departure_minutes` (default 45, 0–720, int). In `economy_caravan_crud.dispatch()` for a physical row: `next_move_at = now + timedelta(minutes=departure)` when `departure > 0`, else the current `step_delay(params, u)`. Nothing else changes (stepping, holds, A1 `departs_in_sec` already count down to `next_move_at`).
- "Preparing" (hire window) = `is_physical=1 AND status='in_transit' AND arrived_at IS NULL AND route_index = 0` and **no raid row** for the caravan. A post hold at the gate simply lengthens the window. Abstract caravans unaffected. Caravans already on the road at deploy are unaffected.

### 3.3 Data model (CS migration `051_caravan_escorts`)

Manual, MySQL-safe, idempotent column/table checks like 050:

- `characters` + `escort_caravan_id BIGINT NULL` + index `ix_characters_escort_caravan (escort_caravan_id)`. CS is the only writer; BS/LS/IS/party read it raw.
- `econ_caravan_escorts`:
  `id BIGINT PK AI`, `caravan_id BIGINT NOT NULL`, `character_id INT NOT NULL`, `status VARCHAR(16) NOT NULL` (`active|left|fallen|delivered|cancelled|released`), `hire_location_id BIGINT NULL` (public frozen location), `in_raid BOOL NOT NULL DEFAULT 0`, `fee BIGINT NOT NULL DEFAULT 0`, `bonus BIGINT NOT NULL DEFAULT 0`, `payout_op_id BIGINT NULL`, `rewards_done BOOL NOT NULL DEFAULT 0`, `joined_at DATETIME NOT NULL`, `ended_at DATETIME NULL`;
  `UNIQUE uq_caravan_escort (caravan_id, character_id)` (= no rejoin after «Сойти»), index `(character_id, status)`, index `(status, rewards_done)`. No FKs (style of econ tables).
- `econ_caravan_messages`: `id BIGINT PK AI`, `caravan_id BIGINT NOT NULL`, `character_id INT NOT NULL`, `body VARCHAR(500) NOT NULL`, `created_at DATETIME NOT NULL`; index `(caravan_id, id)`, index `(character_id, created_at)`.
- `econ_caravan_raids` + `escort_ids JSON NULL`, `faction_done BOOL NOT NULL DEFAULT 0`; then `UPDATE econ_caravan_raids SET faction_done = 1` (no retroactive faction points for pre-deploy raids).
- `reputation_actions` INSERT … WHERE NOT EXISTS: `caravan_escort` «Охрана каравана» `points=10, daily_cap=40, has_source=1, sort_order=55, is_builtin=1`; `caravan_defense` «Отбит налёт на караван» `points=25, daily_cap=NULL, has_source=1, sort_order=56, is_builtin=1`. Mirror in `reputation_core.DEFAULT_ACTIONS` (+ codes `ACTION_CARAVAN_ESCORT`, `ACTION_CARAVAN_DEFENSE`) and copy byte-for-byte to LS `reputation_core.py` (`scripts/check_econ_copies.sh` green).
- Downgrade drops all of the above (active escorts simply lose the lock; pre-beta).
- Tests asserting the single head `050` (`test_admin_mob_region_ready.py`, `test_reputation_core.py`) → `051`; seed counts in `test_reputation_core.py` updated.
- Other services: **no migrations** (BS, LS, IS, party, user-service, AB). Heads unchanged: BS `010`, LS `058`, IS `037`, user `0035`.

Models: `models.EconCaravanEscort`, `models.EconCaravanMessage`, new columns on `Character` / `EconCaravanRaid`.

### 3.4 Settings (SimParams JSON, no DDL — `econ_sim.SimParams`, bounds in `schemas.py`, int keys in `ECON_SIM_INT_PARAMS`, update/read schemas, `CARAVAN_PARAM_KEYS` so the caravans admin card edits them)

| Key | Default | Range | Meaning |
|---|---|---|---|
| `caravan_departure_minutes` | 45 | 0–720 (int) | caravan stands at the seller gate after birth (hire window) |
| `caravan_escort_seats` | 3 | 0–4 (int) | player seats per caravan; 0 = hiring off. ≤4 keeps ≥1 mob |
| `caravan_escort_fee_share` | 0.05 | 0–0.5 | escort pay pool = share of the seller's remaining proceeds |
| `caravan_escort_bonus_share` | 0.03 | 0–0.5 | extra pool when the caravan's raid was repelled (same source) |
| `caravan_escort_defense_fame` | 5 | 0–1000 (int) | fame per escort for a repelled raid (on delivery) |

Reputation amounts live in `reputation_actions` (admin-editable). Faction points live in `faction_enemies.points` (3.10).

### 3.5 Activity lock reason `caravan_escort` (all 4 copies)

- CS `activity_lock.py`: `REASON_CARAVAN_ESCORT = "caravan_escort"`; `compute_lock(..., escort_caravan_id=None)` (new trailing kwarg); priority **jail > law_encounter > unconscious > dungeon > caravan_escort > asleep > reading**; lock dict shape unchanged; `lock_for_character` passes `getattr(character, "escort_caravan_id", None)`.
- `lock_message` for this reason is **neutral for every subject**: `f"{subject}: действие сейчас недоступно"` (never mentions caravans; the escort learns the reason from his own banner, 3.12). 
- BS / LS (identical files, keep identical md5) and IS (sync twin): `_LOCK_SQL` gains `escort_caravan_id` as the 7th column, `_lock_from_row` passes `escort_caravan_id=_col(row, 6)`. **Deploy-skew fallback chain**: full SQL → on "unknown/no such column" mentioning `escort_caravan_id` → the FEAT-198 SQL (6 columns) → on a missing law column → the legacy SQL (4 columns). Generalise `_is_missing_law_column` into `_is_missing_column(exc, names)`. Warning log texts in Russian like the existing ones.
- CS callers: `law_crud.check_patrol_arrival` passes the new arg (`law_crud.py:555-560`); `PUT /characters/internal/{id}/update_location` refuses `caravan_escort` (409, `lock_message`) in addition to law reasons (defence in depth, `main.py:2393-2397`).
- Admin / home teleport `_prepare_move` (`main.py:932`): if the character is an active escort → release him first (`escort_crud.release(db, cid, status='released')`, CharacterLog, notice «Вы сняты с охраны каравана»), then move as usual.
- Everything that already refuses locked characters now refuses escorts automatically (LS move/quick move/posts/NPC/loot/houses/tag, BS attacks/PvP/joins/parties, IS trade/home teleport/backpack, CS bank/mint/guild/faction QM/teleport/dungeon entry, faction eject skip, patrol skip).

### 3.6 Visibility (escort hidden; public location frozen)

Helper module `caravan_escort_public.py` (CS, pure-ish): `public_location_id(db, ch)` → `hire_location_id` of the active escort row when `ch.escort_caravan_id` is set, else `ch.current_location_id`; `public_lock(ch)` → `compute_lock(...)` **without** the escort column (an escort shows as unlocked); batch variant for lists `public_locations(db, ids) -> {id: loc}` (one query).

Surfaces:
1. `GET /characters/by_location` (`main.py:2271`): ORM filter `Character.escort_caravan_id.is_(None)` → escorts disappear from LS PlayersSection, gathering nodes, `api/squads.ts`.
2. party-service `get_character_ids_at_location` (`crud.py:127-135`): `AND escort_caravan_id IS NULL`; on unknown-column error (CS 051 not applied / SQLite fixture) retry the old SQL (warning log).
3. `GET /characters/{id}/short_info` (public): `current_location_id` → `public_location_id`, `activity_lock` → `public_lock`. The internal twin keeps real values by default and gets `?masked=true` (same masking) for service consumers that serve strangers.
4. `GET /characters/{id}/public` (`crud.py:735`) and `GET /characters/list` (`main.py:2583+`): `current_location_id` masked (batch for the list).
5. user-service: `_fetch_character_short(cid, masked=True)` for `GET /users/{id}/characters` and `GET /users/{id}/profile`; `/users/me` keeps the real call (owner banner, header). Additive query param; CS ignores nothing (old CS without the param just returns real data — acceptable during deploy).
6. Third-party lock messages: neutral (3.5).
7. A1 `caravans_here` `guard_count` stays the stored mob count (never includes escorts).
8. Battles: once the raid starts the escorts are visible as participants (the surprise). Accepted.

Admin reads (economy:read) show escorts (3.13 A4/A5).

### 3.7 Hiring at «Караванщик» (NPC role `caravaneer`)

- Role value `caravaneer` (free string, no settings table, no admin tab). Reputation kill weight falls to `*` (−150) — no change.
- **C1 view** and **C2 hire** share the precheck (banker/guild order): 1) JWT + owner + player; 2) NPC exists, `is_npc`, role `caravaneer`, not dead → 404 «Караванщик не найден»; 3) character at the NPC's location → 400 «Вы не у караванщика»; 4) **`npc_dialogue` gate** via `locations_client.check_npc_gate` (HTTP **outside** any DB transaction; fail-closed: `GateUnavailable` → 503 «Не удалось проверить обращение к караванщику, попробуйте позже»; closed → 403 «Нужен пост-намерение «Диалог с НПС» с этим персонажем»); 5) NPC reputation tier gate `reputation_crud.require_npc_tier` (403).
- C1 lists caravans "preparing" (3.2) whose `current_location_id` = NPC location, ascending id, each with per-caravan eligibility (`can_hire`, `reason`) so the UI explains refusals.
- **C2 hire checks** (Tx: lock `econ_caravans(row)` FOR UPDATE → count active escorts → lock `characters(row)` FOR UPDATE → insert escort → set column → commit), errors in this order:
  - caravan missing / not physical / not in_transit → 404 «Караван не найден»; `route_index > 0` or `arrived_at` → 409 «Караван уже ушёл»; NPC location ≠ caravan location → 400 «Этот караван собирается не здесь»; raid row exists → 409 «На этот караван уже напали»;
  - `caravan_escort_seats == 0` → 409 «Караванщик сейчас не нанимает охрану»; active escorts ≥ seats → 409 «Мест в охране больше нет»;
  - character already an escort (`escort_caravan_id` not NULL) → 409 «Вы уже в охране каравана»; escort row for (caravan, character) exists (left / fallen earlier) → 409 «В этот караван вас больше не возьмут» (also the UNIQUE IntegrityError);
  - activity lock (any reason) → 409 `lock_message`; `_is_in_battle` → 409 «Персонаж в бою»; active gathering (`gathering_sessions` `status='active'`, raw read; table missing → skip) → 409 «Сначала закончите сбор ресурсов»;
  - wanted in the **seller region** (`law_crud.read_wanted(db, cid, from_region_id, law settings, now) > 0`) → 403 «Вас разыскивают в краю, откуда идёт караван — караванщик не возьмёт»; reputation in the seller region below `wanderer` (`reputation_crud.gate_failure(db, cid, from_region_id, "wanderer")`) → 403 with that text («Нужна репутация: …»). Seller region gone → skip both checks. Outlaw faction status is NOT checked (not in the brief).
  - success: row `status='active'`, `hire_location_id = character.current_location_id`, `joined_at=now`; character `escort_caravan_id = caravan.id`, `house_room_id = NULL`. CharacterLog `caravan_escort` «Нанялся в охрану каравана (<группа>)». Notice after commit (WS `caravan_escort`).
- One job at a time = the column under the row lock. Seats race = caravan row lock.

### 3.8 On the road

- **Stepping** (`caravan_pass.step_caravan`, same tx): after the caravan row moved (`moved` / `arrived`), select active escorts of the caravan (`ORDER BY character_id`, FOR UPDATE), lock their `characters` rows asc, `UPDATE characters SET current_location_id = :loc, house_room_id = NULL WHERE id IN (…) AND escort_caravan_id = :caravan`. Raw write — no law entry check, no faction territory refusal (escorts are inside the wagon; after leaving, normal eject/patrol rules apply). Held caravans (raid / post) do not move escorts.
- **C3 own job** returns the full route (names), current index/location, state (`preparing|on_road|held|under_attack|arrived`), `next_move_in_sec`, seller/buyer region names, fellow active escorts (id, name, avatar), seats, `pay_estimate` (per head now), `raid_status` (`null|repelled|...`), `battle_id` when the escort is in the raid battle.
- **Caravan channel** (CS table, no Redis, no LS posts): C5 read (active escorts of that caravan only; `after_id` paging, max 100 per call, oldest→newest), C6 write (active escort only; body stripped 1..500 chars → 400 «Сообщение: от 1 до 500 символов»; throttle: the character's last message < 3 s ago → 429 «Слишком часто — подождите пару секунд»). Rendered as plain text. Messages are deleted by housekeeping 7 days after the caravan finished.
- **C4 «Сойти»**: owner; active escort → else 404 «Вы не в охране каравана»; raid `starting|fighting` → 409 «Идёт бой — сойти с каравана нельзя». Tx: lock caravan → escort row → character; status `left`, `ended_at`, column NULL. The character stays where the caravan is (his real location). No pay, no rewards, no rejoin (UNIQUE). CharacterLog + notice.
- **Housekeeping** (new pass step 7, cheap, best effort): (a) escort rows `active` whose caravan is no longer `in_transit` → `released` + column cleared (crash safety); (b) `characters.escort_caravan_id` set without a matching active row → cleared; (c) messages of caravans finished > 7 days → deleted (batch 1000).

### 3.9 Raid with escorts ("сюрприз")

- **A2 / `begin_raid`**: early refusal when the raider is activity-locked (any reason, 409 `lock_message`) — spares a guard spawn; BS still re-checks.
- **`spawn_guards`**: `escorts` = active escorts of the caravan (asc character id); `mobs = max(1, min(guard_count or formula, MAX_GUARDS − len(escorts)))`.
- **`battle_client.create_caravan_raid_battle(..., escort_character_ids)`**: additive payload field. Response `escort_character_ids` = escorts actually placed (missing in an old BS → `[]`).
- **`mark_fighting`**: stores `raid.escort_ids` and sets `in_raid = 1` on those escort rows.
- **BS B1** (`CaravanRaidBattleCreate.escort_character_ids: List[int] = []`, ≤ 4): `len(guards) + len(escorts) ≤ BATTLE_MAX_TEAM_SIZE` else 400; duplicates removed; each escort is **silently skipped** unless: player (`is_npc = 0`), `current_location_id == location_id`, not in an active battle, activity lock `reason in (None, "caravan_escort")` (new helper `_escort_available`; this is the only lock exemption). `leader_id in escorts` → 409 neutral `lock_message`. Attackers (leader / `_free_squadmates`) are filtered `not in escorts` (a squadmate escort is already skipped by its lock — this is defence in depth for the "rat"). Teams: attackers 0, guards + escorts 1. Escorts are players → not registered with autobattle. Response adds `escort_character_ids`.
- **Fallen escorts**: BS `_notify_caravan_battle_end(db, battle_id, winner_team, aborted=False, state=None)` adds `fallen_character_ids` = character ids of participants with `hp <= 0` or `dropped_out` in the final state (finish path passes `battle_state`; force-finish → `[]`). `GET /battles/internal/{id}/result` adds `fallen_character_ids` (from Redis state when present; else `dropped_out_at IS NOT NULL` rows ∪ all participants of the losing team). Both additive.
- **CS settlement** (`settle_raid`, Tx 1; `RaidResultIn.fallen_character_ids: Optional[List[int]] = None`; poll path reads the same key):
  - `won` → every escort in `raid.escort_ids` falls out (`fallen`);
  - `repelled` → escorts ∩ `fallen_character_ids` fall out (field missing → none);
  - `aborted` → escorts stay;
  - `expired` → escorts `released` (the caravan leaves while the battle may still run);
  - falling out: status, `ended_at`, column NULL; the character stays at the raid location. **No KO, no extra penalty** ("обычные последствия проигранного боя" — surface PvE has none). No pay.
  - Lock order inside Tx 1: caravan → raid → escort rows (asc id) → shares → **one** `_lock_characters(raiders ∪ escorts)` asc → accounts.
  - Notices: fallen «Охрана каравана разбита — вы выбыли из каравана»; repelled survivors «Налёт отбит! Надбавка будет выплачена по прибытии». CharacterLog for fallen.
- **Rat case**: an escort is locked → cannot lead a raid (CS + BS refuse), is skipped as a squadmate, and is only ever placed on team 1. Never in both teams.
- No extra crime for raiding a caravan with escorts (existing raid crime only).

### 3.10 Pay, reputation, fame, factions

**Pay (inside the existing `caravan_delivery` op, no econ_core change, no new op type):** in `deliver_physical`, delivered branch, after `seller_part, duty_part = remaining_payout(...)` (already cut by `raid_paid` → "robbed → fee cut" falls out):
- `n` = active escorts (rows locked FOR UPDATE after the caravan row, asc id); `n = 0` → unchanged behaviour.
- `fee_pool = floor(seller_part × caravan_escort_fee_share)`; `bonus_pool = floor(seller_part × caravan_escort_bonus_share)` if the caravan's raid status is `repelled`, else 0; `pool = min(fee_pool + bonus_pool, seller_part)`.
- per head: `fee_i = fee_pool // n`, `bonus_i = bonus_pool // n` (remainders stay with the seller); `seller_part −= n × (fee_i + bonus_i)`.
- legs: existing two + `escrow → character(escort)` of `fee_i + bonus_i` per escort (skip zero). Characters locked asc before accounts (lock order regions → goods → caravan → escorts → characters → accounts). `apply_tax=False` (as the op today). Metadata adds `escorts: [{character_id, fee, bonus}]`.
- escort rows → `delivered`, `fee`, `bonus`, `payout_op_id`, `ended_at`; column NULL (character stays at the destination gate). CharacterLog «Охрана каравана (<группа>): плата N марок (+M за отбитый налёт)». `FinishResult` gets `notices: list = field(default_factory=list)`; `_deliver_arrived` publishes after the commit.
- Cancel branch: escorts → `cancelled`, no pay, column NULL, notice «Караван отменён — оплаты не будет», no rewards.
- World sum = 0 and the escrow sub-invariant are untouched (all money still leaves the escrow in the same op at delivery). Seller account fallback (`_country_or_world`) works the same.

**Rewards (new pass step 6 `escort_rewards`, separate tx per escort — never with economy locks):** rows `status='delivered' AND rewards_done=0`; claim with a conditional `UPDATE … SET rewards_done=1 WHERE id=:id AND rewards_done=0`; then, idempotent keys:
- `apply_reputation(action='caravan_escort', region=from_region, echo=False, idem_key=f"caravan_escort:{caravan}:{cid}:r{region}")` and the same for `to_region` (distinct; skip a gone region; one call when equal);
- if the caravan's raid was `repelled` and this escort had `in_raid=1`: `caravan_defense` in both regions (same key scheme) + `renown_crud.add_fame(points=caravan_escort_defense_fame, source=<new source constant 'caravan_defense'>, event_key=f"caravan_defense:{caravan}:{cid}")` when > 0 (register the source constant where renown sources are validated);
- faction points (below) for kind `escort`;
- publish tier / fame / faction notices after commit. Failure → rollback (claim rolled back) → retried next pass.

**Factions** (no DDL — `faction_enemies.kind` VARCHAR(10)): new kinds `escort` «Охрана караванов» and `raid` «Налёты на караваны» in `faction_core.ENEMY_KINDS`; singleton like `hostile` (`ref_id = 0`, one row each, `points` 1..10000); `put_enemies` validation + messages «Строка «Охрана караванов» может быть только одна» / «…«Налёты на караваны»…». New `faction_kills.apply_caravan_deed(db, character_id, kind, event_key, now) -> FlowResult`: active memberships (secret included, notices only to the player) of factions having that kind → `fc.kill_gain([points], kill_cap(faction), day_row.kill_points)` (same day counter and cap as kills) → `fcr.change_points(..., event_type=EV_CARAVAN_ESCORT|EV_CARAVAN_RAID ('caravan_escort'|'caravan_raid'), event_key=…)` (UNIQUE event_key per faction = idempotent) → `recheck_ranks`. Notices «Охрана каравана — дело фракции «X»: +N очков» / «Налёт на караван — дело фракции «X»: +N очков». No hostile penalty.
- escort: event key `faction:caravan_escort:c<caravan>:<cid>`, on delivered (rewards step).
- raid: for `won` raids, players of the share rows, event key `faction:caravan_raid:r<raid>:<cid>`, in a new followup `raid_faction_points` (claims `faction_done` like `law_done`), run wherever `law_step` runs (callback path and `raid_followups`).

### 3.11 Guild window gate

`GET /characters/economy/guild/npc/{npc_id}` becomes `async`: precheck (`resolve_guild(..., write=False)` in threadpool, transaction closed) → `locations_client.check_npc_gate` (503 `MSG_GATE_UNAVAILABLE` / 403 `MSG_GATE_CLOSED`) → view in threadpool. Hand-in unchanged (already gated). Frontend `GuildModal` already shows the load error; verify the 403 text is shown and add the hint line (3.12).

### 3.12 API contracts (all Pydantic v1, Russian errors, frontend shows every error)

| # | Method / path | Service | Auth | Request | Response |
|---|---|---|---|---|---|
| C1 | `GET /characters/caravans/caravaneer/{npc_id}?character_id=` | CS | JWT owner + npc_dialogue gate + tier | — | `{npc_id, location_id, my_escort_caravan_id: int\|null, seats_enabled: bool, caravans: [{id, group_code, group_name, departs_in_sec: int\|null, seats_total, seats_taken, pay_estimate: int, can_hire: bool, reason: str\|null}]}` — no from/to/route/value |
| C2 | `POST /characters/caravans/{caravan_id}/escort/hire` | CS | as C1 | `{character_id: int, npc_id: int}` | 201 `EscortJob` (= C3 body); 400/403/404/409/503 (3.7) |
| C3 | `GET /characters/caravans/escort?character_id=` | CS | JWT owner | — | `{escort: EscortJob\|null}`; `EscortJob = {caravan_id, group_code, group_name, from_region_name, to_region_name, route: [{index, location_id, name}], route_index, current_location_id, current_location_name, state, next_move_in_sec: int\|null, seats_total, escorts: [{character_id, name, avatar}], pay_estimate, raid_status: str\|null, battle_id: int\|null, joined_at}` |
| C4 | `POST /characters/caravans/escort/leave` | CS | JWT owner | `{character_id}` | `{left: true, location_id}`; 404/409 |
| C5 | `GET /characters/caravans/escort/messages?character_id=&after_id=0` | CS | JWT owner, active escort | — | `{caravan_id, messages: [{id, character_id, name, avatar, body, created_at}]}` (≤100) ; 404 «Вы не в охране каравана» |
| C6 | `POST /characters/caravans/escort/messages` | CS | JWT owner, active escort | `{character_id, text: str}` | 201 message item; 400/404/429 |
| A3 | `POST /characters/internal/caravans/raid-result` (ext.) | CS | internal | + `fallen_character_ids: Optional[List[int]]` | unchanged |
| A4 | `GET /characters/admin/economy/caravans` (ext.) | CS | economy:read | — | items + `escort_count` (active) |
| A5 | `GET /characters/admin/economy/caravans/{id}` (ext.) | CS | economy:read | — | + `escorts: [{character_id, name, status, joined_at, ended_at, fee, bonus, in_raid}]`, raid + `escort_ids` |
| A10 | economy settings GET/PUT (ext.) | CS | economy:settings | new keys 3.4 | — |
| G1 | `GET /characters/economy/guild/npc/{npc_id}` (ext.) | CS | JWT owner + npc_dialogue gate | — | unchanged body; new 403/503 |
| S1 | `GET /characters/{id}/short_info`, `/characters/{id}/public`, `/characters/list` | CS | public | — | masked location / lock (3.6) |
| S2 | `GET /characters/internal/{id}/short_info?masked=false` | CS | internal | + `masked: bool = False` | masked when true |
| F1 | faction enemies admin PUT/GET (ext.) | CS | existing faction perms | kinds `escort`, `raid` (ref 0) | unchanged shape |
| B1 | `POST /battles/internal/caravan-raid` (ext.) | BS | internal | + `escort_character_ids: List[int] = []` | + `escort_character_ids` |
| B2 | `GET /battles/internal/{id}/result` (ext.) + raid callback payload | BS | internal | — | + `fallen_character_ids: List[int]` |
| P1 | `GET /party/by-location` | party | unchanged | — | escorts excluded |
| U1 | `GET /users/{id}/characters`, `/users/{id}/profile` | user | unchanged | — | masked location / lock |
| AB1 | `POST /autobattle/unregister`, `/autobattle/speed` | AB | JWT | unchanged | owner-only (3.14) |

Endpoints C1–C6 live in a new router module `caravan_escort_api.py` (async endpoints, sync crud via threadpool, HTTP never inside a DB transaction), included in `main.py`; crud in new `caravan_escort_crud.py`; schemas in new `caravan_escort_schemas.py` (keeps `schemas.py` edits to the SimParams bounds only).

Rate limiting: C6 app-level throttle (3 s per character); C2 is naturally bounded (UNIQUE, row locks, one job per character); no nginx change (the FEAT-211 raid regex location is exact and does not match the new paths). Internal routes behind `/internal/` + token.

### 3.13 Admin

- NPC role `caravaneer` «Караванщик» + icon in `constants/npc.ts` (role picker, labels). No settings tab.
- Economy → Караваны: the 5 new params (section «Охрана из игроков») with `paramHints`; list column/badge «охрана-игроки N»; `CaravanDetail` escorts table (name, status label, joined/ended, fee, bonus, «в бою»).
- Factions → enemies editor: two singleton kinds «Охрана караванов» / «Налёты на караваны» with points (no target picker), the existing kill cap applies; faction journal labels for `caravan_escort` / `caravan_raid` event types if a label map exists.
- No new permissions (existing `economy:*`, `npcs:*`, faction perms) → `test_rbac_permissions.py` untouched.

### 3.14 Autobattle owner fix (ISSUES.md HIGH)

`autobattle-service/app/main.py`: new async helper `_resolve_owner(pid) -> Optional[int]`: `OWNER.get(pid)`, else the battle from `PID_BATTLE` → `get_battle_state` → participant `character_id` → `get_character_owner` (None for NPCs/mobs or when unresolvable). `/unregister`: pid not in `ALLOWED` and not in `OWNER` → `{"ok": true}` no-op (idempotent, reveals nothing); else owner ≠ `user.id` (incl. None) → 403 «Вы не можете отменить автобой чужого персонажа». `/speed`: same owner rule (404 when not registered stays). `/mode`, `/feedback` already safe. Mark the ISSUES.md entry DONE (strike-through + «Исправлено (FEAT-212)»).

### 3.15 Global lock order (update docstrings in `economy_caravan_crud.py`, `caravan_raid_crud.py`)

`econ_regions → econ_region_goods → econ_region_events → econ_caravans (asc) → econ_caravan_raids → econ_caravan_escorts (asc id) → econ_caravan_raid_shares → … → characters (asc id, ONE sorted lock call per tx) → econ_accounts (asc) → character_attributes`. Reputation / fame / faction rows only in their own transactions (rewards step, raid followups). Messages table: plain inserts, never locked.

### 3.16 Frontend (player)

- `hooks/useActivityLock.ts`: reason `caravan_escort`.
- `CommonComponents/ActivityLockBanner.tsx`: for `caravan_escort` a strip «Вы в охране каравана» + button «Караван» opening `CaravanEscortModal`.
- `LocationPage/LocationPage.tsx`: lock text block for the reason («Вы едете с караваном: ходить, писать посты и торговать нельзя, пока не сойдёте») + button opening the modal.
- New `components/CaravanEscort/CaravanEscortModal.tsx` (+ small parts): C3 (poll 30 s) — group, from → to, route as a vertical list with the current stop highlighted, countdown (`useCountdownTo`), state line, fellow escorts, pay estimate, raid line (with link to the battle when `battle_id`); channel C5 (poll 15 s while open, `after_id`) + input C6 (Enter / button, 500 max, counter); «Сойти с каравана» with a confirmation («Вы останетесь здесь, оплаты не будет, обратно в этот караван не возьмут») → C4 → `getMe()` refresh.
- New `LocationPage/CaravaneerModal/CaravaneerModal.tsx`: C1 list (group, «отправится через», «мест N из M», «плата ~X марок»), disabled rows show `reason`; «Наняться в охрану» → confirmation (can't walk, raids fought by yourself, 24 h per turn, «Сойти» anytime without pay) → C2 → toast + `getMe()` + open `CaravanEscortModal`. 403 gate text shown with the hint «Напишите пост с намерением «Диалог с НПС», указав караванщика».
- `NpcProfileModal.tsx`: button «Караваны» for `npc_role === 'caravaneer' && isCharacterHere && characterId`.
- `GuildModal.tsx`: on 403 show the API text + the same hint.
- `api/caravanEscort.ts`, `types/caravanEscort.ts` (new). Tailwind + design-system classes (`modal-overlay`, `modal-content`, `gold-text`, `btn-blue`, `btn-line`…), no `React.FC`, 360 px, every error toast/inline in Russian.

### 3.17 Security

- C1–C6: JWT + ownership; location derived server-side; escort-only channel reads/writes (membership re-checked on every call); body length + throttle; plain-text rendering (React escapes). C1/C2 behind the moderator-visible npc_dialogue post (fail-closed).
- Hidden-escort guarantees: tests per surface (3.6) and per neutral message.
- B1/A3/B2: internal prefix + token; escorts validated by BS (location, player, not in battle, only the escort lock exempted).
- AB fix closes the "switch off someone else's autobattle" hole.
- SQL parameterised; JSON columns from server-side ints.

### 3.18 Risks / accepted simplifications

- Deploy skew: BS/LS/IS/party read `escort_caravan_id` before CS 051 runs → fallback SQL (3.5/3.6). Old BS ignores `escort_character_ids` → escorts simply not placed in that raid.
- Poll-fallback settlement cannot see a killed escort on the **winning** team once Redis state expired → he stays in the caravan (only if the callback was lost).
- `pay_estimate` in C1 reveals the approximate caravan value and `seats_taken` reveals the number of escorts to anyone with a dialogue post at the gate (see Q1).
- Escorts move by raw writes through faction-closed territory / patrol zones; after «Сойти» normal rules apply (R10).
- Delivery waits while an economy run is `running` (minutes); escorts wait locked at the destination gate.
- CI time: CS suite is near the cap → one lean CS test file reusing `test_physical_caravans` / `test_caravan_raids` fixtures.

### 3.19 Questions for PM / user (defaults are implemented unless the user says otherwise)

1. **Мест в охране «2 из 3» у караванщика** — это видно любому, кто написал пост у караванщика, включая будущих налётчиков (они узнают, сколько игроков внутри). По умолчанию показываем, как в брифе. Альтернатива — показывать только «есть места / мест нет».
2. **Обычная кнопка автобоя** (которую игрок включает себе сам в любом бою) — по умолчанию охранникам её НЕ запрещаем (система сама ничего не включает, это его личный выбор). Альтернатива — запретить охранникам включать автобой в налёте.
3. **Павший охранник** — по умолчанию выпадает из каравана в локации налёта без «без сознания» (обычные последствия наземного боя, как сказал пользователь). Вариант PM — ещё и «без сознания» на N часов.
4. **Гильдия торговцев**: сдача товаров уже требовала пост «Диалог с НПС»; теперь пост потребуется и чтобы просто открыть окно гильдии. Ок?

**PM decisions on 3.19 (2026-11-12, binding — override defaults above):**
1. Caravaneer shows only «есть места» / «мест нет» — NOT the count of seats/escorts (keeps the surprise). Hire response/escort's own panel may show the count to the escort himself.
2. Escorts must NOT be able to enable autobattle in a caravan-raid battle (user: «не надо им автобой вообще»). Battle-service/autobattle-service refuse `/autobattle/register` for a participant who is an escort of that raid (escort_character_ids) with a Russian 403 message; frontend hides/disables the autobattle toggle for them. Include in Tasks 4/6/7 and QA 11/13.
3. Fallen escort — default (falls out at the raid location, no knockout).
4. Guild window requires the post — OK.

**Implementation notes — Tasks 4/5/6 + PM decision 2 (Backend Developer, 2026-11-12):**
- **Autobattle ban for escorts (contract for Task 7 / QA 11, 13).** battle-service B1 passes the placed escorts to
  `_assemble_battle(..., autobattle_forbidden_character_ids=...)`, which sets `autobattle_forbidden: true` on their
  participants in the Redis state (`init_battle_state` copies the key, missing → `false`). The flag is exposed per
  participant at `runtime.participants[pid].autobattle_forbidden` (bool, always present) in `GET /battles/{id}/state`,
  `GET /battles/internal/{id}/state`, the WS runtime (`_build_runtime`) and spectate. autobattle-service `/register`
  reads it from the internal state and answers **403 «Охранникам каравана автобой недоступен — в налёте вы ходите сами»**.
  `/register` with `battle_id = 0` now falls back to the participant's last battle from `PID_BATTLE`, so the check
  (and the existing ownership check) cannot be skipped with a zero id. **Frontend:** hide/disable the autobattle toggle
  when the viewer's own participant has `autobattle_forbidden === true`, and show the 403 text if it still happens.
  The check lives in autobattle-service (it already fetches the state for ownership) — no new BS endpoint.
- **Lock fallback detection fixed.** The DB error text echoes the whole SQL, so the old substring check
  (`"jailed_until" in msg`) matched every unknown-column error. `_is_missing_column(exc, names)` now compares only the
  column the DB names (MySQL «Unknown column 'x'», SQLite «no such column: x»). Chain: full → law SQL (051 missing) →
  legacy (039 missing); a missing law column on the first query jumps straight to legacy.
- **B1 rat filter:** an escort id equal to a guard id is ignored; attackers are filtered `not in escorts` before
  escorts are validated.
- **user-service:** `/users/{id}/profile` is masked for every viewer except the profile owner (owner sees real data,
  like `/users/me`); `/users/{id}/characters` always masked. `?masked=true` is sent only when masking.
- **party-service:** `escort_caravan_id IS NULL` filter with legacy-SQL retry on the named-missing-column error.
- Existing tests that pinned the old behaviour were adjusted minimally: AB `test_unregister_unowned_pid_*` /
  `test_no_owner_entry_*` → 403; BS/LS lock-row mocks match `"jailed_until, law_encounter_id" ... "FROM characters"`;
  user-service fakes accept `masked`.

**Implementation notes — Task 2 (Backend Developer, 2026-11-12):**
- **C1 shape (PM decision 1):** items are `{id, group_code, group_name, departs_in_sec, has_seats, pay_estimate, can_hire,
  reason}` — `seats_total` / `seats_taken` are NOT returned. `pay_estimate` in C1 = `fee_pool // seats` (the guaranteed
  pay per head when every seat is taken) so it cannot leak the current escort count. C3 (escort himself) keeps
  `seats_total`, the escort list and `pay_estimate` = `(fee_pool + bonus_pool if repelled) // active escorts`.
- **C5 paging:** `after_id=0` → the latest 100 (oldest → newest), `after_id>0` → the next 100 after it.
- **Hooks for Task 3:** `caravan_escort_crud.STATUS_*`, `_lock_characters`, `_active_rows_locked(db, caravan_id)` (active
  rows FOR UPDATE asc id), `_clear_columns(db, caravan_id, ids)`, `_log`, `_notice`, `release`; faction raid points =
  `faction_kills.apply_caravan_deed(db, cid, faction_core.ENEMY_RAID, f"faction:caravan_raid:r{raid}:{cid}", now)` (own
  commits, call with no open tx). C3 `battle_id` is filled when the raid is `starting|fighting` and the escort row has
  `in_raid=1` or his id is in `raid.escort_ids` (Task 3 `mark_fighting` sets them). C4 refuses while the raid is active.
  The rewards step reads `in_raid` / raid status `repelled` for the defense reputation + fame.
- `FinishResult` gained `notices` (published by `caravan_pass._deliver_arrived`); `run_pass` stats gained
  `escort_rewards`, `escort_housekeeping`. Lock-order docstring updated in `economy_caravan_crud.py` only —
  `caravan_raid_crud.py`'s docstring is left to Task 3.

**Implementation notes — Task 3 (Backend Developer, 2026-11-12):**
- `battle_client.create_caravan_raid_battle(..., escort_character_ids=())` returns `escort_character_ids` (missing →
  `[]`). The A2 endpoint passes the kwarg **only when the caravan has escorts** (a raid without escorts makes exactly
  the FEAT-211 call, so the existing `FakeBattle` stand-in keeps working); placed = response ∩ sent.
- `RaidStart.escort_ids`, `caravan_raid_crud.active_escort_ids(db, caravan_id)`; `mark_fighting(..., *, escort_ids=())`
  stores `[]` when nobody was placed (NULL only for pre-deploy raids / lost Tx B).
- Settlement fallback when `escort_ids` is NULL (callback faster than Tx B / re-attached raid): guard-team players of
  `battle_participants` that are still active escorts of this caravan. Settlement also sets `in_raid = 1` on the placed
  rows (so the defense rewards work even if Tx B was lost).
- `settle_raid(..., fallen_character_ids=None)`; `battle_result(..., fallen_character_ids=None)`; the poll reads
  `fallen_character_ids` from the result dict (absent → None → nobody falls on `repelled`).
- Messages: won «Охрана каравана разбита — вы выбыли из каравана»; repelled-fallen «Вы пали в бою за караван — вы выбыли
  из каравана, оплаты не будет» (spec reused the won text — a separate one reads better); survivors «Налёт отбит!
  Надбавка будет выплачена по прибытии»; expired «Бой за караван затянулся — караван ушёл дальше без вас».
- `raid_faction_points(db, raid_id, now)` applies the deeds first, then sets `faction_done` (deeds are idempotent per
  faction, so a crash in between only repeats no-ops); returns the number of applied faction deeds; runs in
  `finish_raid` after the law step and as a new loop in `raid_followups`.

## 4. Tasks (filled by Architect, updated by PM — in English)

**Rules for every developer task:** no `git commit/push/add/stash/checkout/reset`; backend → `python -m py_compile` on touched files (in Docker per project workflow); frontend → `npx tsc --noEmit` + `npm run build` in the container; update `docs/services/<service>.md`; Russian `[LOG]` line in section 6.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | CS foundation: migration 051 (3.3), models, SimParams 3.4 (econ_sim, schemas bounds/int keys/read+update schemas, `CARAVAN_PARAM_KEYS`), departure delay in `dispatch()` (3.2), CS `activity_lock.py` reason + neutral message (3.5), `law_crud.check_patrol_arrival` arg, `update_location` refusal, `_prepare_move` escort release hook (calls a small `release` helper created here in `caravan_escort_crud.py`), `reputation_core` actions + LS copy, public masking module + S1/S2 + `/by_location` filter (3.6 items 1,3,4), head tests 050→051 | Backend Developer | DONE | CS `alembic/versions/051_caravan_escorts.py`, `models.py`, `econ_sim.py`, `schemas.py`, `economy_caravan_crud.py` (dispatch only), `activity_lock.py`, `law_crud.py`, `main.py`, `crud.py`, `reputation_core.py`, `caravan_escort_public.py` (new), `caravan_escort_crud.py` (new, release only), tests head asserts; LS `app/reputation_core.py`; docs | — | Migration up/down on MySQL; `check_econ_copies.sh` green; new physical caravan waits `caravan_departure_minutes` at the gate; a character with `escort_caravan_id` is locked with the neutral message, hidden from `/by_location`, public short_info/public/list show `hire_location_id` and unlocked; internal short_info real unless `masked=true`; existing CS tests green |
| 2 | CS escort core: `caravan_escort_crud.py` + `caravan_escort_schemas.py` + `caravan_escort_api.py` C1–C6 (3.7, 3.8), router include in `main.py`; stepping escorts in `step_caravan`; delivery pay + release + notices in `deliver_physical` (3.10 pay); pass steps 6 `escort_rewards` and 7 housekeeping; reputation/fame/faction escort rewards; faction kinds `escort`/`raid` + `apply_caravan_deed` (3.10); admin A4/A5 escort fields; guild view gate G1 (3.11); lock-order docstrings 3.15 | Backend Developer | DONE | CS `caravan_escort_crud.py`, `caravan_escort_schemas.py` (new), `caravan_escort_api.py` (new), `main.py` (include), `caravan_pass.py`, `economy_caravan_crud.py`, `caravan_api.py` (admin reads), `faction_core.py`, `faction_kills.py`, `renown`/`shadow_core` source constant, `economy_api.py` (guild GET), docs | 1 | Hire only at a caravaneer at the gate during preparing, with a dialogue post (fail-closed), all refusals of 3.7 with exact texts; seats/one-job/no-rejoin enforced; escorts move with the caravan; leave works and is refused during a raid; channel members-only + throttle; delivery pays fee (+bonus if repelled) from the seller part in `caravan_delivery`, world sum 0 + escrow invariant ok; cancel → no pay; rewards rep both regions, defense rep + fame, faction points under the kill cap, idempotent; guild GET needs the post |
| 3 | CS raid integration: `begin_raid` lock pre-check, mob count reduction in `spawn_guards`, `battle_client` escorts field, `mark_fighting` escort_ids/in_raid, `settle_raid` fallen/released handling with single sorted character lock, A3 `fallen_character_ids` + poll path, followup `raid_faction_points` (`faction_done`) (3.9, 3.10 raid) | Backend Developer | DONE | CS `caravan_raid_crud.py`, `battle_client.py`, `caravan_api.py` (A3 schema), `schemas.py` (raid result schema only if it lives there), docs | 2 | Mobs = max(1, min(guard_count, 5−escorts)); escorts sent to B1; won → all escorts fall out; repelled → only fallen ones; aborted → stay; expired → released; escort can't lead a raid; faction raid points once per raid; existing raid tests green |
| 4 | BS: B1 `escort_character_ids` (validation, skip rules, team 1, response), `_escort_available`, attackers ∩ escorts filter, `fallen_character_ids` in the caravan callback and in `/internal/{id}/result`, `activity_lock.py` column + fallback chain (3.5) | Backend Developer | DONE | BS `app/main.py`, `app/schemas.py`, `app/activity_lock.py`; `docs/services/battle-service.md` | — (contract 3.12) | B1 with escorts builds team 1 = guards + escorts, total ≤ 5 else 400; locked-by-other-reason / elsewhere / in-battle escorts skipped; leader escort refused; callback and result carry fallen ids; lock SQL works with and without the new column; existing BS tests green |
| 5 | LS + IS `activity_lock.py` column + fallback chain (LS byte-identical to BS); party-service `get_character_ids_at_location` filter with fallback; user-service `_fetch_character_short(masked=True)` for `/users/{id}/characters` and `/users/{id}/profile` | Backend Developer | DONE | LS `app/activity_lock.py`; IS `app/activity_lock.py`; party-service `app/crud.py`; user-service `main.py`; docs of these services | — (contract 3.5/3.6) | md5 LS == BS copy; escort-locked character refused with the neutral text in LS/IS; party by-location hides escorts, works on an old schema; user profile/characters cards show the masked location |
| 6 | Autobattle owner fix (3.14) + ISSUES.md entry marked DONE | Backend Developer | DONE | `services/autobattle-service/app/main.py`; `docs/ISSUES.md`; `docs/services/autobattle-service.md` | — | Non-owner unregister/speed of an internally registered mob or someone else's character → 403; owner → ok; unknown pid unregister → ok no-op |
| 7 | Frontend player (3.16): lock reason, banner, LocationPage lock text, `CaravanEscortModal` (job, route, countdown, channel, «Сойти»), `CaravaneerModal`, NpcProfileModal button, GuildModal 403 hint, api/types | Frontend Developer | DONE | `hooks/useActivityLock.ts`, `CommonComponents/ActivityLockBanner.tsx`, `pages/LocationPage/LocationPage.tsx`, `pages/LocationPage/NpcProfileModal.tsx`, `pages/LocationPage/CaravaneerModal/CaravaneerModal.tsx` (new), `components/CaravanEscort/CaravanEscortModal.tsx` (+ parts, new), `pages/LocationPage/GuildModal/GuildModal.tsx`, `api/caravanEscort.ts`, `types/caravanEscort.ts` (new) | contracts 3.12 (live needs 2) | tsc + build pass; hire → banner + modal; route/countdown/channel/leave work; all errors visible in Russian; 360 px; no React.FC; Tailwind only |
| 8 | Frontend admin (3.13): role `caravaneer` label/icon, 5 params + hints, list escort count, CaravanDetail escorts, faction enemies kinds `escort`/`raid` (singletons, no target), faction event labels, types/api | Frontend Developer | DONE | `constants/npc.ts`, `Admin/EconomyPage/EconomyCaravans.tsx`, `CaravanDetail.tsx`, `paramHints.ts`, `types/economy.ts`, `api/economyAdmin.ts`, `Admin/FactionsPage/EnemiesEditor.tsx`, `api/factions.ts` (+ faction journal label map if any) | contracts 3.12 (live needs 2, 3) | tsc + build pass; params save; escorts visible in detail; enemies editor saves the new kinds and refuses duplicates; 360 px |
| 9 | QA CS escorts: hire happy path + every refusal of 3.7 (gate closed/unavailable mocked, tier, wanted, rep, seats, one job, rejoin, lock, battle, gathering, not preparing, raid exists), departure delay, stepping moves escorts (and not while held), leave (+ refused during raid), channel auth/length/throttle, delivery pay split/remainder/bonus/robbery cut + `_check` invariant, cancel no pay, rewards (rep both regions, defense + fame, faction points + cap, idempotent re-run), housekeeping, masking surfaces (by_location, short_info public/internal masked, public, list) and neutral message, guild GET gate, A4/A5 fields, security (other user's character 403) | QA Test | DONE | CS `app/tests/test_caravan_escorts.py` (new; reuse `test_physical_caravans` / `test_caravan_raids` fixtures, keep lean) | 2 | All pass; CS suite time not visibly increased (> ~60 s new file = refactor) |
| 10 | QA CS raid integration: mob reduction, B1 payload (mocked BS) incl. old-BS response without the field, mark_fighting in_raid, settle won/repelled(with/without fallen ids)/aborted/expired, rat (escort leader refused before spawn), faction raid points once | QA Test | DONE | CS `app/tests/test_caravan_raids.py` (extend) | 3 | All pass |
| 11 | QA BS: B1 escorts validation/skip/team/total cap/leader escort, attackers filter, fallen ids in callback payload and result endpoint, lock fallback chain with old fixture schema | QA Test | DONE | BS `app/tests/test_caravan_raid_battle.py` (extend), lock test file | 4 | All pass under `--timeout=30` |
| 12 | QA LS/IS/party/user-service: neutral lock message + fallback chain (LS, IS), party by-location filter + fallback, user-service masked fetch | QA Test | DONE | LS/IS lock tests (extend existing `test_activity_lock*.py`), party-service tests, user-service tests | 5 | All pass |
| 13 | QA AB: unregister/speed owner rules (internal mob, foreign character, own character, unknown pid) | QA Test | DONE | `autobattle-service/app/tests/test_autobattle_auth.py` (extend) | 6 | All pass |
| 14 | Docs: `docs/ARCHITECTURE.md` (party/user-service read `characters.escort_caravan_id` / masked short_info), service docs consistency | Backend Developer | DONE | `docs/ARCHITECTURE.md` | 1–6 | Docs match the code |
| 15 | Review: all checks (`check_econ_copies.sh`, py_compile, pytest per touched service, tsc/build), live on localhost: caravan at the gate, dialogue post, hire, invisible in lists/cards, moves with caravan, channel, raid with escort on team 1, repelled → bonus at delivery, invariant ok, «Сойти», guild post required, autobattle unregister refused | Reviewer | TODO | — | 1–14 | PASS |
| 16 | Mask public CS `GET /characters/{id}/profile` for escorts (3.6 leftover from Task 1): internal twin `GET /characters/internal/{id}/profile` (X-Internal-Token, real values); LS location checks (move_and_post, move, drop, pickup) and dungeon-service `get_character_profile` switched to the twin with 404 → public fallback (deploy skew); BS (name/avatar), AB (`user_id`), LS post details/invite stay public (unaffected by the mask); frontend does not call this route (uses `full_profile`) → no owner variant needed; nginx already blocks `/characters/internal/` | Backend Developer | DONE | CS `app/main.py`; LS `app/main.py`; dungeon `app/http_clients.py`; tests: CS `test_caravan_escorts.py` (+1), LS `test_escort_profile_internal.py` (new), dungeon `test_profile_internal_feat212.py` (new); docs character/locations/dungeon-service.md | 1 | Public profile of an escort = hire location + unlocked; internal = real; 401 without token; LS/dungeon read the twin and fall back on 404 |

**Parallel groups (file-disjoint):**
- Wave 1: 1, 4, 5, 6 (4/5/6 touch other services only; 5's LS file must equal 4's BS file → 5 copies BS `activity_lock.py` after 4, or the same developer does both); 7/8 may start on the contracts.
- Wave 2: 2 (after 1); 11 (after 4), 12 (after 5), 13 (after 6).
- Wave 3: 3 (after 2); 9 (after 2).
- Wave 4: 10 (after 3); 7/8 finalisation + live check; 14.
- Wave 5: 15.

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-12 — **PASS** (with 2 reviewer fixes)

Scope: all 93 uncommitted paths (`git status` / `git diff`, read-only git only) against §1 brief, PM decisions on 3.19 and §3 design.

#### Correctness vs brief / PM decisions — verified
- C1 shows only `has_seats` («есть места» / «мест нет») + `pay_estimate = fee_pool // seats` (no count leak); C3 (the escort himself) shows «Игроков в охране: 1 из 3».
- Hire/view need the `npc_dialogue` gate (fail-closed 503 / 403), checked with no open DB transaction; the guild window GET is gated the same way (`test_econ_guild_api.py`).
- Escort autobattle: BS flags `autobattle_forbidden`, AB `/register` → 403, UI hides the toggle (2D/3D). **Gap found and fixed (fix #1).**
- AB owner rule for `/unregister` and `/speed` (a mob pid → 403 live).
- Hidden escort: `/by_location`, public `short_info`, `/public`, `/list`, `/{id}/profile` (internal twin for LS/dungeon with 404 fallback), user-service cards (masked internal short_info), party `/by-location` — all verified live; the lock message is neutral («Персонаж: действие сейчас недоступно») for every subject.
- Rat: a group raid by Ашари whose squadmate Годрик is an escort → Годрик only on team 1 (live). Team cap: mobs = max(1, min(guard_count, 5 − escorts)).
- Money: escort pay = extra legs `escrow → character` inside the same `caravan_delivery` op, carved from the seller part; live op 1855: 920 seller + 80 escort = 1000 = the escrow release; admin summary invariant `ok: true`; `check_econ_copies.sh` green.
- Rewards idempotent (claim `rewards_done`, idem keys for reputation / fame, faction `event_key`); live: rep +10 / +25 in both regions, fame +5 `caravan_defense`.
- Lock order caravan → raid → escort rows → characters (one sorted lock) → accounts is consistent in hire / leave / step / settle / deliver / release; no deadlock cycle found.
- Deploy skew: BS/LS/IS lock SQL chain (full → law → legacy) matches only the column the DB names; party fallback now uses the same rule (fix #2); an old BS without `escort_character_ids` → nobody placed; LS/dungeon profile twin 404 → public route.
- Security: C1–C6 JWT + owner; channel members-only, 1..500 chars, 3 s throttle (429), plain-text rendering (`<script>` shown as text live); internal routes behind `/internal/` + token (`/characters/internal/764/profile` from outside → 403); parameterised SQL only.
- Frontend: Tailwind only, no SCSS, TS, no `React.FC`, design-system classes, all errors toasted / inline in Russian; 360 px (iframe 360 wide): caravaneer modal, escort modal and the «Сойти» confirmation fit, document scrollWidth 343.

#### Reviewer fixes
| # | File | Fix |
|---|------|-----|
| 1 | `services/autobattle-service/app/main.py` (`handle_turn`) | **Bug (reproduced live):** `/autobattle/register` with `battle_id = 0` for a pid that has not had a `your_turn` yet skips every check, so anyone (e.g. a raider) could put an escort on autobattle → AB would play his turns, violating PM decision 2. Added a guard in `handle_turn`: a participant flagged `autobattle_forbidden` never acts and is removed from `ALLOWED / OWNER / SPEED`. Live: escort pid 763 registered with `battle_id=0` → on his turn AB logged «autobattle forbidden (caravan escort) — unregistered» and did not act. Tests: `tests/test_handle_turn.py::TestHandleTurnEscortForbidden` (2). The generic pre-existing hole (bid=0 skips the ownership check for ordinary players; `allowed` list returned to anyone) → `docs/ISSUES.md` MEDIUM; `docs/services/autobattle-service.md` updated. |
| 2 | `services/party-service/app/crud.py` (`_is_missing_escort_column`) | Matched `escort_caravan_id` anywhere in the error text (the DB echoes the SQL) → any unknown-column error would silently fall back to the legacy SQL. Now parses the column the DB names (MySQL / SQLite), the same rule as the `activity_lock.py` copies. A test case with the SQL echo added to `test_party_enrichment.py`. |

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (frontend container)
- [x] `npm run build` — PASS (built in 1 m 9 s)
- [x] `py_compile` — PASS (all touched .py in CS, BS, LS, IS, party, AB, dungeon, user)
- [x] `pytest` — PASS: character 10181 passed / 2 skipped (13 m 48 s); battle 2065 passed (`--asyncio-mode=auto`); locations 3146 passed; inventory 2543 passed; user 799 passed; party 77 passed (incl. the new case); autobattle 176 passed (incl. 2 new); dungeon exit code 0 (no failures)
- [x] `scripts/check_econ_copies.sh` — PASS («All shared copies are identical»)
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome, http://localhost) — PASS

#### Live Verification Results (user 4; Годрик 764 = escort, Ашари 763 = raider)
- Setup: gates 9 → 197 «Холм Эха», 10 → 190; physical caravan #542 (tools, 1000 marks) via `dispatch_tx`, standing 45 min at the gate (`caravan_departure_minutes`); NPC 33 «Петя» → «Караванщик» via the admin NPC page (role list has 🐫 «Караванщик»).
- Without a dialogue post: C1 → 403 «Нужен пост-намерение «Диалог с НПС» с этим персонажем». Ашари (wanted in region 9) → row refused «Вас разыскивают в краю…».
- Wrote the «Диалог с НПС» post (Петя) → NPC modal «Караваны» → caravaneer modal («есть места», плата ~16) → confirmation → toast, banner «Вы в охране каравана» + escort modal (route of 9 stops, countdown, «1 из 3», ~50 марок). Channel: message sent, HTML shown as text, a second message within 3 s → «Слишком часто — подождите пару секунд».
- Locked: quick_move → 409 «Персонаж: действие сейчас недоступно»; C1 «Вы уже в охране каравана». Hidden: by_location(197) without 764; public short_info / profile → location 197 + unlocked; party by-location dropped 764 from his squad.
- Step: forced `next_move_at` → the pass moved the caravan and 764 to 196; by_location(196) without 764, public short_info still 197.
- Raid: Ашари raid post + group attack → battle 330: team 0 = Ашари only, team 1 = 3 Бакэзори + Годрик (raid `escort_ids=[764]`, `in_raid=1`). As Годрик: the autobattle toggle is replaced by «Охранникам каравана автобой недоступен…», `/register` 403, «Сойти» → 409 «Идёт бой — сойти с каравана нельзя», C3 `under_attack` + battle_id. Годрик won (raider hp lowered in Redis) → raid `repelled`, «escorts out [], stay [764]».
- Delivery: fast-forwarded route → delivered; escort row `delivered` fee 50 + bonus 30, CharacterLog «плата 50 марок (+30 за отбитый налёт)», column cleared, Годрик at the destination gate; rewards applied once.
- «Сойти»: second caravan #543, hired inside a 360 px iframe → «Сойти с каравана» → confirm → job null, banner gone, C1 «В этот караван вас больше не возьмут».
- Admin: Экономика → Караваны: section «Охрана из игроков» with the 5 params; detail API shows escorts (status, fee, bonus, в бою) and raid `escort_ids`. Factions → «Территория и враги» explains the new kinds; duplicate `escort` → 422 «Строка «Охрана караванов» может быть только одна».
- Console: no errors on location, battle (3D) and admin pages.
- Cosmetic (pre-existing, not FEAT-212): the end-of-battle window says «Победитель: Бакэзори» (team leader name) when the escort's team wins.

#### Local test data left / changed (pre-beta, dev only)
- Restored: NPC 33 role back to `merchant`; `econ_regions.trade_gate_location_id` of regions 9 / 10 back to NULL; Ашари 763 back to location 197; user 4 current character back to 763.
- Left: caravans #542 (delivered, escort paid, raid #7 repelled, battle 330 finished) and #543 (physical, in transit — runs its stored route and delivers); escort rows for 764 (#542 `delivered`, #543 `left`); one channel message; posts by Годрик at 197 (dialogue) and Ашари at 196 (raid gate consumed); Годрик 764 now at 197 with +80 marks, rep +35 in regions 9 and 10, fame +39; the 3 spawned guard mobs despawned.


## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-12 — PM: фича создана по решениям пользователя («как предлагаешь, запускай»), запускаю анализ
[LOG] 2026-11-12 02:55 — Analyst: анализ завершён — затронуто 7 сервисов (character, battle, autobattle, locations, inventory, party, frontend). Ключевое: окна «сборов» у каравана нет (уходит из ворот через ~15–20 мин после пересчёта); плату охране можно вырезать из доли продавца в той же операции доставки без правки econ_core; автобоя «если не сходил» нет; охранника выдают публичная карточка short_info (локация + причина блокировки) и список отрядов на локации. Обнаружен баг: чужой автобой (в т.ч. мобов) может выключить любой игрок — добавлен в ISSUES.md. 4 вопроса пользователю
[LOG] 2026-11-12 — PM: ответы пользователя: сборы ~45 мин — да; пост «Диалог с НПС» для найма нужен, и гильдии торговцев тоже сделать обязательным; публичные карточки маскировать; автобоя охранникам НЕ делать (таймаут 24 ч); баг с чужим автобоем закрыть в фиче. Запускаю архитектора
[LOG] 2026-11-12 — Architect: спроектировано 15 задач (6 backend, 2 frontend, 5 QA, docs, ревью), 6 новых эндпоинтов + 12 расширений контрактов; миграция только character-service 051. Плата охране — доп. проводки в существующей операции доставки из доли продавца (надбавка за отбитый налёт — оттуда же), сборы 45 мин через next_move_at, новая причина блокировки caravan_escort с нейтральным текстом, маскировка в 7 публичных местах (включая профиль/персонажей в user-service — анализ их пропустил). Уточнение: сдача товаров гильдии уже требовала пост, без поста открывалось только окно — закрываем и его. 4 вопроса к PM в 3.19
[LOG] 2026-11-12 — Backend Dev: задача 1 готова — миграция character-service 051 (колонка охраны у персонажа, таблицы охраны и караванного канала, поля налёта, 2 действия репутации; вверх/вниз на MySQL проверено), 5 новых настроек, «сборы» 45 мин у ворот, причина блокировки caravan_escort с нейтральным текстом, отказ в update_location, снятие с охраны при админ-переносе, маскировка охранника в by_location / short_info / public / list (internal short_info — реальный, ?masked=true — маска), reputation_core скопирован в locations-service. Добавлен лёгкий тест-файл test_caravan_escort_foundation.py (7 тестов)
[LOG] 2026-11-12 — Backend Dev: задачи 4/5/6 готовы. battle-service: B1 принимает охранников-игроков (команда каравана, лимит 5, «крыса» не попадает в налётчики), павшие в колбэке и в /result, флаг `autobattle_forbidden` в состоянии боя; activity_lock с причиной caravan_escort и цепочкой отката (BS = LS по md5, IS — синхронный близнец). Найден и исправлен попутно: откат блокировки ловил «нет колонки» по подстроке во всём тексте SQL — теперь по имени колонки из ошибки. party-service прячет охранников из отрядов на локации, user-service маскирует чужие карточки. autobattle: выключать/менять скорость может только владелец, охранникам налёта автобой запрещён (403); запись в ISSUES.md закрыта
[LOG] 2026-11-12 — Backend Dev: задача 2 готова — караванщик (C1 список «есть места/мест нет» без чисел, C2 найм с постом «Диалог с НПС» и всеми отказами), «Вы в охране» (C3), «Сойти» (C4), караванный канал (C5/C6, 3 с между сообщениями), охранники едут вместе с караваном, плата из доли продавца в той же операции доставки (+надбавка за отбитый налёт), отмена без оплаты, награды (репутация в обоих краях, слава и репутация за отбитый налёт, очки фракций «Охрана/Налёты караванов» под лимитом побед), уборка, админка (охранники в списке и карточке каравана), окно гильдии теперь тоже по посту. Добавлен лёгкий тест test_caravan_escort_core.py (5 тестов)
[LOG] 2026-11-12 — QA: задача 9 готова — test_caravan_escorts.py (26 тестов, ~10 с): все отказы найма (тир НПС, розыск и репутация в краю продавца, места выключены, блокировка, бой, сбор, караван ушёл / не те ворота / уже был налёт / не физический, мёртвый караванщик), караванщик не выдаёт число охранников, охрана едет с караваном и стоит при удержании/налёте, сошедший остаётся, плата делится с остатком продавцу + надбавка за отбитый налёт, урезка при ограблении, инвариант денег, отмена без оплаты, награды (репутация в обоих краях, оборона + слава, очки фракции под лимитом, повтор без дублей), уборка, скрытие на живых эндпоинтах, админка A4/A5, безопасность (401/403, инъекции и длина в канале). Багов не найдено; окно гильдии и «сборы» уже покрыты другими файлами
[LOG] 2026-11-12 — Backend Dev: задача 3 готова — налёт с охранниками: лидера с блокировкой (в т.ч. охранника) не пускает до спавна охраны, мобов меньше на число охранников (минимум 1), охранники уходят в B1 и записываются в налёт (escort_ids, in_raid), итог: победа налётчиков — все охранники выбывают, отбили — выбывают только павшие (fallen_character_ids из колбэка/опроса; старый battle-service — никто), прерван — остаются, затянулся — сняты с охраны; очки фракций за удачный налёт один раз (faction_done). Тесты рейдов/караванов/охраны зелёные (446), check_econ_copies зелёный
[LOG] 2026-11-12 — QA: задача 10 готова — test_caravan_raids.py дополнен 25 тестами (~11 с): число мобов max(1, min(охрана, 5−охранники)), охранники уходят в B1 только если они есть, записываются только размещённые (ответ ∩ отправленные), старый battle-service без поля — никто; in_raid/escort_ids; итог: победа — все размещённые выбывают в локации налёта без оплаты (лог + уведомление), отбили — выбывают только павшие, остальные получают плату с надбавкой при доставке, без списка павших — все остаются, прерван — остаются, затянулся — сняты; откат на команду охраны из battle_participants; охранник не может вести налёт (409 до спавна), охранник-сопартиец остаётся на стороне каравана; очки фракций за налёт один раз (колбэк, повтор через followups, не за проигрыш); опрос читает fallen_character_ids; внутренний токен A3 без изменений. Багов не найдено. Прогон 5 файлов караванов /охраны: 267 тестов, 58 с
[LOG] 2026-11-12 — Frontend Dev: задача 7 готова — причина блокировки «Вы в охране каравана» (полоса с кнопкой «Караван» и блок на странице локации), окно охранника (маршрут списком с текущей точкой, обратный отсчёт до следующего перехода, состояние, другие охранники, ожидаемая плата, налёт со ссылкой на бой, караванный канал с опросом раз в 15 с, «Сойти с каравана» с подтверждением внутри окна), окно караванщика (только «есть места / мест нет», плата, причина отказа, подтверждение найма), кнопка «Караваны» у НПС, подсказка про пост «Диалог с НПС» у караванщика и в гильдии. Автобой: по флагу `autobattle_forbidden` у своего участника кнопки автобоя скрыты (2D и 3D), текст 403 показывается тостом. WS-событие caravan_escort обновляет /users/me
[LOG] 2026-11-12 — Frontend Dev: задача 8 готова — роль «Караванщик» (🐫), 5 настроек «Охрана из игроков» с подсказками, значок «охрана-игроки N» в списке караванов, охранники в карточке каравана (статус, даты, плата/надбавка, «в бою») и число охранников в налёте, типы врагов фракции «Охрана караванов» / «Налёты на караваны» (одна строка каждого, без цели), источник славы «Отбитый налёт на караван». Журнал фракции текст получает с сервера — отдельные подписи не нужны. tsc --noEmit и npm run build в контейнере — без ошибок
[LOG] 2026-11-12 06:10 — Backend Dev: задача 16 готова — публичный профиль персонажа (/characters/{id}/profile) больше не выдаёт охранника: показывает локацию найма и «свободен»; настоящие локация и блокировка — во внутреннем двойнике /characters/internal/{id}/profile (снаружи nginx отдаёт 403). На двойник переведены проверки локаций (перемещение, пост с переходом, выброс и подбор лута) и вход в данж; при старом character-service — откат на публичный путь. Бой (имя/аватар) и автобой (владелец) остались на публичном — маска их не задевает. Фронтенд этот путь не вызывает. Тесты: CS 85 прошло, LS 3125+4, данжи 908; живьём на деве: публичный — локация найма, внутренний — реальная с блокировкой охраны, без токена 401.
[LOG] 2026-11-12 06:40 — QA: задачи 11–13 готовы. battle-service (test_caravan_raid_battle.py, +70 тестов): охранники в налёте — команда каравана, лимит 5, тихий пропуск недоступных, лидер-охранник 409 нейтрально, «крыса» не попадает в налётчики, флаг autobattle_forbidden в состоянии, павшие в колбэке и /result, цепочка отката блокировки на старой схеме. locations/inventory: нейтральный текст и откат (IS — на настоящем SQLite), party: охранники скрыты из отрядов на локации + старая схема, user-service: маскировка карточек, autobattle: правила владельца для /unregister и /speed, отказ охранникам в /register (в т.ч. с battle_id=0). Все наборы зелёные, багов не найдено
[LOG] 2026-11-12 — Backend Dev: задача 14 готова — ARCHITECTURE.md: таблицы миграции 051 (escort_caravan_id и кто его читает, econ_caravan_escorts, econ_caravan_messages), user-service берёт маскированный short_info, party-service прячет охранников SQL-ом, внутренний профиль для locations/dungeon, B1 escort_character_ids и fallen_character_ids в колбэке и /result, autobattle — флаг autobattle_forbidden и правило владельца; frontend.md — раздел FEAT-212 (окно караванщика, окно охранника, полоса блокировки, автобой скрыт). Документы сервисов сверены с кодом — явных расхождений нет
[LOG] 2026-11-12 — Backend Dev: ускорен тест battle-service test_internal_headers.py::test_no_internal_call_is_missing_headers — ast.get_source_segment заново резал весь main.py (~360 КБ) на каждом вызове; теперь строки режутся один раз, функции-построители URL собираются один раз, проверка та же. Было 102,5 с, стало 0,4 с; совпадение со stdlib проверено на ~2300 узлах (0 расхождений), все 33 теста файла зелёные. Такие же свипы в других сервисах (dungeon, battle-pass, char-attrs, IS, LS, autobattle) идут 0,3–3,5 с — не трогал
[LOG] 2026-11-12 — Reviewer: ревью PASS. Все проверки зелёные (character 10181, battle 2065, locations 3146, inventory 2543, user 799, party 77, autobattle 176, dungeon без падений; tsc и сборка; копии экономики идентичны). Живьём прошёл весь путь: пост «Диалог с НПС» → найм у караванщика → канал → невидимость → шаг каравана → налёт с охранником в команде каравана → отбили → оплата 50 + 30 при доставке → «Сойти» на 360 px. Исправил сам: (1) автобой мог сыграть за охранника, если зарегистрировать его с battle_id=0 до его первого хода — теперь handle_turn проверяет флаг и снимает такого с автобоя (подтверждено живьём, +2 теста); общая дыра с battle_id=0 для обычных игроков добавлена в ISSUES.md; (2) откат party-service на старый SQL срабатывал на любую «unknown column» — теперь сверяет имя колонки (+1 тест)
```

## 7. Completion Summary (filled by PM on completion — in Russian)

Охрана караванов из игроков сделана, ревью PASS (2026-11-12). Найм у «Караванщика» в воротах во время сборов (~45 мин), только с постом «Диалог с НПС»; гильдия торговцев тоже требует пост. Охранник едет с караваном, скрыт во всех публичных местах, видит маршрут, караванный канал, «Сойти». В налёте — в команде каравана (всего ≤5), автобой охранникам запрещён. Плата 5 % (+3 % за отбитый налёт) из выручки продавца при доставке, репутация в обоих краях и слава за отбитый налёт, очки фракциям за охрану/налёт. Закрыта дыра с чужим автобоем. Миграция character 051. Ускорен медленный тест battle-service (102 с → 0,4 с). Найдено и записано в ISSUES (MEDIUM): register автобоя с battle_id=0 для обычных игроков; окно победы пишет «Победитель: <моб>» при победе стороны охраны.
